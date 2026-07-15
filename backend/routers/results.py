from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pathlib import Path
import av

from database import get_db, Shot, VideoAnalysis, VideoTranscript, User
from config import THUMBNAILS_DIR
from auth import get_current_user
from permissions import get_video_for_user
from services.video_path import resolve_video_path
from services.analysis_config import get_or_create_video_config, video_has_results

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/results/{video_id}")
def get_results(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    video = get_video_for_user(video_id, current_user, db)

    shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
    va = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
    config_row = get_or_create_video_config(video_id, db)
    transcript = db.query(VideoTranscript).filter(VideoTranscript.video_id == video_id).first()
    has_results = video_has_results(video_id, db)
    legacy_results = has_results and config_row.active_snapshot is None

    return {
        "video": {
            "id": video.id,
            "filename": video.filename,
            "duration": video.duration,
            "fps": video.fps,
            "status": video.status,
        },
        "shots": [
            {
                "id": s.id,
                "index": s.index,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration": s.duration,
                "thumbnail_path": s.thumbnail_path,
                "clip_path": s.clip_path,
                "analysis": s.analysis,
            }
            for s in shots
        ],
        "overall_analysis": va.continuity_report if va else None,
        "segments": va.segments_report if va else None,
        "analysis_schema": config_row.active_snapshot if has_results else config_row.draft_config,
        "config_revision": config_row.draft_revision,
        "active_config_revision": config_row.active_revision,
        "draft_config_dirty": legacy_results or bool(config_row.active_hash and config_row.active_hash != config_row.draft_hash),
        "transcript_status": transcript.status if transcript else None,
    }


@router.get("/video-file/{video_id}")
def stream_video(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """流式传输视频，支持 Range 请求和缓存"""
    v = get_video_for_user(video_id, current_user, db)
    p = resolve_video_path(v.filepath)
    if not p.exists():
        raise HTTPException(404, "视频文件不存在")

    suffix = p.suffix.lower()
    media_types = {'.mp4': 'video/mp4', '.mov': 'video/quicktime',
                   '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska',
                   '.webm': 'video/webm'}

    # 添加缓存头，缓存 7 天
    headers = {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=604800',  # 7 天
        'ETag': f'"{v.id}-{p.stat().st_mtime}"',
    }

    # 支持 Range 请求（断点续传和拖动进度条）
    range_header = request.headers.get('range')
    if range_header:
        import re
        file_size = p.stat().st_size
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            end = min(end, file_size - 1)

            def iter_file():
                with open(p, 'rb') as f:
                    f.seek(start)
                    remaining = end - start + 1
                    chunk_size = 1024 * 1024  # 1MB chunks
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            headers.update({
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Content-Length': str(end - start + 1),
            })

            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type=media_types.get(suffix, 'video/mp4'),
                headers=headers
            )

    # 完整文件响应
    return FileResponse(
        str(p),
        media_type=media_types.get(suffix, 'video/mp4'),
        headers=headers
    )


@router.get("/thumbnail/{video_id}/{shot_index}")
def get_thumbnail(
    video_id: int,
    shot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_video_for_user(video_id, current_user, db)
    shot = (
        db.query(Shot)
        .filter(Shot.video_id == video_id, Shot.index == shot_index)
        .first()
    )
    if not shot or not shot.thumbnail_path:
        raise HTTPException(404, "缩略图不存在")
    p = Path(shot.thumbnail_path)
    if not p.exists():
        raise HTTPException(404, "缩略图文件不存在")

    # 添加缓存头
    headers = {
        'Cache-Control': 'public, max-age=2592000',  # 30天
        'ETag': f'"{shot.id}-{p.stat().st_mtime}"'
    }
    return FileResponse(str(p), media_type="image/jpeg", headers=headers)


@router.get("/clip/{video_id}/{shot_index}")
def get_clip(
    video_id: int,
    shot_index: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """流式传输镜头切片，支持 Range 请求和缓存"""
    get_video_for_user(video_id, current_user, db)
    shot = (
        db.query(Shot)
        .filter(Shot.video_id == video_id, Shot.index == shot_index)
        .first()
    )
    if not shot or not shot.clip_path:
        raise HTTPException(404, "视频片段不存在")
    p = Path(shot.clip_path)
    if not p.exists():
        raise HTTPException(404, "视频片段文件不存在")

    # 添加缓存头
    headers = {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=604800',  # 7天
        'ETag': f'"{shot.id}-{p.stat().st_mtime}"'
    }

    # 支持 Range 请求（复用 stream_video 的逻辑）
    range_header = request.headers.get('range')
    if range_header:
        import re
        file_size = p.stat().st_size
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            end = min(end, file_size - 1)

            def iter_file():
                with open(p, 'rb') as f:
                    f.seek(start)
                    remaining = end - start + 1
                    chunk_size = 1024 * 1024  # 1MB chunks
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            headers.update({
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Content-Length': str(end - start + 1),
            })

            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type="video/mp4",
                headers=headers
            )

    # 完整文件响应
    return FileResponse(str(p), media_type="video/mp4", headers=headers)


@router.get("/video-thumbnail/{video_id}")
def get_video_thumbnail(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取视频封面（第一帧）"""
    video = get_video_for_user(video_id, current_user, db)

    thumb_path = THUMBNAILS_DIR / f"video_{video_id}_cover.jpg"

    # 如果缓存不存在，提取第一帧
    if not thumb_path.exists():
        try:
            with av.open(str(resolve_video_path(video.filepath))) as container:
                stream = container.streams.video[0]
                for frame in container.decode(stream):
                    img = frame.to_image()
                    img.save(str(thumb_path), quality=85)
                    break
        except Exception as e:
            raise HTTPException(404, f"无法提取封面: {e}")

    # 添加缓存头
    headers = {
        'Cache-Control': 'public, max-age=2592000',  # 30天
        'ETag': f'"{video_id}-{thumb_path.stat().st_mtime}"'
    }
    return FileResponse(str(thumb_path), media_type="image/jpeg", headers=headers)
