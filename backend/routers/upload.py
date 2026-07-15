import av
import math
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Video, User, Shot, CreditTransaction, AnalysisTask, AnalysisTaskSnapshot, VideoAnalysisConfig, VideoTranscript, CosUploadSession
from config import COS_PART_SIZE_MB, COS_UPLOAD_ENABLED, MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB, MAX_VIDEO_DURATION_SECONDS, UPLOADS_DIR, SHOTS_DIR, THUMBNAILS_DIR
from auth import get_current_user
from logger import app_logger
from permissions import get_video_for_user
from services.cos_storage import CosStorage

router = APIRouter(prefix="/api", tags=["upload"])
cos_storage = CosStorage() if COS_UPLOAD_ENABLED else None


class CosUploadInitRequest(BaseModel):
    filename: str
    file_size: int
    content_type: str = "application/octet-stream"


class CosUploadPart(BaseModel):
    part_number: int
    etag: str


class CosUploadCompleteRequest(BaseModel):
    parts: list[CosUploadPart]


class CosPartSignRequest(BaseModel):
    part_numbers: list[int]


def _video_upload_response(video: Video) -> dict:
    return {
        "video_id": video.id,
        "filename": video.filename,
        "duration": video.duration,
        "fps": video.fps,
        "width": video.width,
        "height": video.height,
    }


@router.post("/uploads/cos/init")
def init_cos_upload(
    body: CosUploadInitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not COS_UPLOAD_ENABLED or cos_storage is None:
        raise HTTPException(503, "COS 分片上传未启用")

    original_filename = Path(body.filename or "upload").name
    suffix = Path(original_filename).suffix.lower()
    allowed = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的格式 {suffix}，支持：{', '.join(allowed)}")
    if body.file_size <= 0 or body.file_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(413, f"文件过大，最大支持 {MAX_UPLOAD_SIZE_MB} MB")

    session_id = uuid.uuid4().hex
    part_size = COS_PART_SIZE_MB * 1024 * 1024
    part_count = math.ceil(body.file_size / part_size)
    object_key = f"shotloom/users/{current_user.id}/{session_id}{suffix}"
    upload_id = cos_storage.create_multipart_upload(object_key, body.content_type)
    try:
        signed_parts = [
            {
                "part_number": part_number,
                "url": cos_storage.sign_upload_part(object_key, upload_id, part_number),
            }
            for part_number in range(1, part_count + 1)
        ]
    except Exception:
        cos_storage.abort_multipart_upload(object_key, upload_id)
        raise
    session = CosUploadSession(
        id=session_id,
        user_id=current_user.id,
        filename=original_filename,
        content_type=body.content_type,
        file_size=body.file_size,
        part_size=part_size,
        part_count=part_count,
        object_key=object_key,
        cos_upload_id=upload_id,
        status="initiated",
    )
    db.add(session)
    db.commit()

    return {
        "upload_mode": "cos_multipart",
        "session_id": session_id,
        "part_size": part_size,
        "part_count": part_count,
        "parts": signed_parts,
    }


@router.post("/uploads/cos/{session_id}/complete")
def complete_cos_upload(
    session_id: str,
    body: CosUploadCompleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not COS_UPLOAD_ENABLED or cos_storage is None:
        raise HTTPException(503, "COS 分片上传未启用")

    session = db.query(CosUploadSession).filter(
        CosUploadSession.id == session_id,
        CosUploadSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(404, "上传会话不存在")
    if session.status == "completed" and session.video_id:
        video = db.query(Video).filter(Video.id == session.video_id).first()
        if video:
            return _video_upload_response(video)

    parts = sorted(body.parts, key=lambda item: item.part_number)
    expected_numbers = list(range(1, session.part_count + 1))
    if [item.part_number for item in parts] != expected_numbers or any(not item.etag for item in parts):
        raise HTTPException(400, "上传分片不完整")

    if session.status == "initiated":
        cos_storage.complete_multipart_upload(
            session.object_key,
            session.cos_upload_id,
            [{"PartNumber": item.part_number, "ETag": item.etag} for item in parts],
        )
        session.status = "materializing"
        db.commit()
    elif session.status not in {"materializing", "error"}:
        raise HTTPException(409, "上传会话当前状态不可完成")

    suffix = Path(session.filename).suffix.lower()
    save_path = UPLOADS_DIR / f"{session.id}{suffix}"
    temp_path = save_path.with_suffix(f"{save_path.suffix}.download")
    try:
        cos_storage.download_file(session.object_key, temp_path)
        temp_path.replace(save_path)
        meta = get_video_meta(str(save_path))
        duration = float(meta.get("duration") or 0)
        if MAX_VIDEO_DURATION_SECONDS > 0 and duration > MAX_VIDEO_DURATION_SECONDS:
            save_path.unlink(missing_ok=True)
            cos_storage.delete_object(session.object_key)
            session.status = "rejected"
            db.commit()
            max_minutes = MAX_VIDEO_DURATION_SECONDS / 60
            raise HTTPException(413, f"视频时长过长，最大支持 {max_minutes:.0f} 分钟")

        video = Video(
            filename=session.filename,
            filepath=str(save_path),
            duration=duration,
            fps=meta["fps"],
            width=meta["width"],
            height=meta["height"],
            status="uploaded",
            user_id=current_user.id,
            storage_provider="cos",
            storage_key=session.object_key,
        )
        db.add(video)
        db.flush()
        session.status = "completed"
        session.video_id = video.id
        db.commit()
        db.refresh(video)
        app_logger.info(f"COS 视频入库完成: video_id={video.id}, user_id={current_user.id}")
        return _video_upload_response(video)
    except HTTPException:
        raise
    except Exception:
        temp_path.unlink(missing_ok=True)
        session.status = "error"
        db.commit()
        raise


@router.post("/uploads/cos/{session_id}/parts/sign")
def sign_cos_upload_parts(
    session_id: str,
    body: CosPartSignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not COS_UPLOAD_ENABLED or cos_storage is None:
        raise HTTPException(503, "COS 分片上传未启用")
    session = db.query(CosUploadSession).filter(
        CosUploadSession.id == session_id,
        CosUploadSession.user_id == current_user.id,
    ).first()
    if not session or session.status != "initiated":
        raise HTTPException(404, "上传会话不存在")

    part_numbers = sorted(set(body.part_numbers))
    if not part_numbers or len(part_numbers) > 100:
        raise HTTPException(400, "每次需签名 1 到 100 个分片")
    if part_numbers[0] < 1 or part_numbers[-1] > session.part_count:
        raise HTTPException(400, "分片编号超出范围")
    return {
        "parts": [
            {
                "part_number": part_number,
                "url": cos_storage.sign_upload_part(
                    session.object_key,
                    session.cos_upload_id,
                    part_number,
                ),
            }
            for part_number in part_numbers
        ],
    }


@router.delete("/uploads/cos/{session_id}")
def abort_cos_upload(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not COS_UPLOAD_ENABLED or cos_storage is None:
        raise HTTPException(503, "COS 分片上传未启用")
    session = db.query(CosUploadSession).filter(
        CosUploadSession.id == session_id,
        CosUploadSession.user_id == current_user.id,
    ).first()
    if not session or session.status != "initiated":
        raise HTTPException(404, "上传会话不存在")

    cos_storage.abort_multipart_upload(session.object_key, session.cos_upload_id)
    session.status = "aborted"
    db.commit()
    return {"status": "aborted"}


def get_video_meta(filepath: str) -> dict:
    """用 PyAV 获取视频元数据"""
    try:
        with av.open(filepath) as container:
            video_stream = next((s for s in container.streams if s.type == 'video'), None)

            if not video_stream:
                app_logger.warning(f"视频文件无视频流: {filepath}")
                return {"duration": 0, "fps": 25.0, "width": None, "height": None}

            # container.duration 单位是 AV_TIME_BASE (微秒)
            duration = float(container.duration / 1_000_000) if container.duration else 0
            fps = float(video_stream.average_rate) if video_stream.average_rate else 25.0
            width = video_stream.width
            height = video_stream.height

            app_logger.info(f"视频元数据: {filepath} | 时长={duration:.2f}s, fps={fps:.2f}, 分辨率={width}x{height}")
            return {
                "duration": duration,
                "fps": fps,
                "width": width,
                "height": height,
            }
    except Exception as e:
        app_logger.error(f"读取视频元数据失败: {filepath} | 错误: {e}")
        return {"duration": 0, "fps": 25.0, "width": None, "height": None}


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
    original_filename = Path(file.filename or "upload").name
    suffix = Path(original_filename).suffix.lower()
    if suffix not in allowed:
        app_logger.warning(f"上传失败: 不支持的格式 {suffix}")
        raise HTTPException(400, f"不支持的格式 {suffix}，支持：{', '.join(allowed)}")

    save_path = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"

    bytes_written = 0
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                f.close()
                save_path.unlink(missing_ok=True)
                raise HTTPException(413, f"文件过大，最大支持 {MAX_UPLOAD_SIZE_MB} MB")
            f.write(chunk)

    app_logger.info(f"视频上传成功: {save_path} | 用户: {current_user.email}")

    meta = get_video_meta(str(save_path))
    duration = float(meta.get("duration") or 0)
    if MAX_VIDEO_DURATION_SECONDS > 0 and duration > MAX_VIDEO_DURATION_SECONDS:
        save_path.unlink(missing_ok=True)
        max_minutes = MAX_VIDEO_DURATION_SECONDS / 60
        raise HTTPException(
            413,
            f"视频时长过长，最大支持 {max_minutes:.0f} 分钟（{MAX_VIDEO_DURATION_SECONDS:.0f} 秒）",
        )

    video = Video(
        filename=original_filename,
        filepath=str(save_path),
        duration=duration,
        fps=meta["fps"],
        width=meta["width"],
        height=meta["height"],
        status="uploaded",
        user_id=current_user.id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    app_logger.info(f"视频记录创建: video_id={video.id}")

    return {
        "video_id": video.id,
        "filename": video.filename,
        "duration": video.duration,
        "fps": video.fps,
        "width": video.width,
        "height": video.height,
    }


@router.get("/videos")
def list_videos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # The workspace is personal even for admins; cross-user views belong in
    # explicit admin endpoints.
    query = db.query(Video).filter(Video.user_id == current_user.id)
    videos = query.order_by(Video.created_at.desc()).all()

    result = []
    for v in videos:
        shot_count = db.query(Shot).filter(Shot.video_id == v.id).count()
        result.append({
            "id": v.id,
            "filename": v.filename,
            "duration": v.duration,
            "status": v.status,
            "created_at": v.created_at.isoformat(),
            "shot_count": shot_count,
        })
    return result


@router.get("/videos/{video_id}")
def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    v = get_video_for_user(video_id, current_user, db)
    return {
        "id": v.id,
        "filename": v.filename,
        "duration": v.duration,
        "fps": v.fps,
        "width": v.width,
        "height": v.height,
        "status": v.status,
        "error_msg": v.error_msg,
        "created_at": v.created_at.isoformat(),
    }


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除视频及所有相关产物"""
    video = get_video_for_user(video_id, current_user, db)

    app_logger.info(f"开始删除视频: video_id={video_id}, filename={video.filename}")

    # 删除数据库记录
    from database import VideoAnalysis
    db.query(Shot).filter(Shot.video_id == video_id).delete()
    db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).delete()
    db.query(CreditTransaction).filter(CreditTransaction.video_id == video_id).delete()
    db.query(VideoAnalysisConfig).filter(VideoAnalysisConfig.video_id == video_id).delete()
    db.query(VideoTranscript).filter(VideoTranscript.video_id == video_id).delete()
    db.query(CosUploadSession).filter(CosUploadSession.video_id == video_id).delete()
    task_ids = [row[0] for row in db.query(AnalysisTask.id).filter(AnalysisTask.video_id == video_id).all()]
    if task_ids:
        db.query(AnalysisTaskSnapshot).filter(AnalysisTaskSnapshot.task_id.in_(task_ids)).delete(synchronize_session=False)
    db.query(AnalysisTask).filter(AnalysisTask.video_id == video_id).delete()

    # 删除文件系统中的产物
    try:
        if video.storage_provider == "cos" and video.storage_key and cos_storage is not None:
            cos_storage.delete_object(video.storage_key)

        # 删除原视频
        video_path = Path(video.filepath)
        if video_path.exists():
            video_path.unlink()
            app_logger.info(f"已删除视频文件: {video_path}")

        # 删除镜头切片（shots/video_{id}_*.mp4）
        for clip_file in SHOTS_DIR.glob(f"video_{video_id}_*.mp4"):
            clip_file.unlink()
            app_logger.info(f"已删除切片: {clip_file}")

        # 删除缩略图（thumbnails/video_{id}_*.jpg）
        for thumb_file in THUMBNAILS_DIR.glob(f"video_{video_id}_*.jpg"):
            thumb_file.unlink()
            app_logger.info(f"已删除缩略图: {thumb_file}")

    except Exception as e:
        app_logger.error(f"删除文件失败: video_id={video_id} | 错误: {e}")

    # 删除视频记录
    db.delete(video)
    db.commit()

    app_logger.info(f"视频删除完成: video_id={video_id}")
    return {"message": "删除成功"}


@router.get("/video-thumbnail/{video_id}")
def get_video_thumbnail(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取视频封面（第一帧）"""
    video = get_video_for_user(video_id, current_user, db)

    thumb_path = THUMBNAILS_DIR / f"video_{video_id}_cover.jpg"

    # 如果缩略图不存在，生成一个
    if not thumb_path.exists():
        try:
            with av.open(video.filepath) as container:
                video_stream = container.streams.video[0]
                for frame in container.decode(video_stream):
                    img = frame.to_image()
                    img.save(str(thumb_path), "JPEG", quality=85)
                    break
        except Exception as e:
            app_logger.error(f"生成封面失败: video_id={video_id} | 错误: {e}")
            raise HTTPException(500, "生成封面失败")

    return FileResponse(thumb_path, media_type="image/jpeg")
