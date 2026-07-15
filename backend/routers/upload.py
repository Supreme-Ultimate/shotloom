import av
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db, Video, User, Shot, CreditTransaction, AnalysisTask, AnalysisTaskSnapshot, VideoAnalysisConfig, VideoTranscript
from config import MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB, MAX_VIDEO_DURATION_SECONDS, UPLOADS_DIR, SHOTS_DIR, THUMBNAILS_DIR
from auth import get_current_user
from logger import app_logger
from permissions import get_video_for_user

router = APIRouter(prefix="/api", tags=["upload"])


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
    task_ids = [row[0] for row in db.query(AnalysisTask.id).filter(AnalysisTask.video_id == video_id).all()]
    if task_ids:
        db.query(AnalysisTaskSnapshot).filter(AnalysisTaskSnapshot.task_id.in_(task_ids)).delete(synchronize_session=False)
    db.query(AnalysisTask).filter(AnalysisTask.video_id == video_id).delete()

    # 删除文件系统中的产物
    try:
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
