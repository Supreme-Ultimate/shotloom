from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pathlib import Path
import av

from database import get_db, Video, Shot, VideoAnalysis
from config import THUMBNAILS_DIR
from logger import app_logger

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/results/{video_id}")
def get_results(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

    shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
    va = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()

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
    }


@router.get("/video-file/{video_id}")
def stream_video(video_id: int, db: Session = Depends(get_db)):
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(404, "视频不存在")
    p = Path(v.filepath)
    if not p.exists():
        raise HTTPException(404, "视频文件不存在")
    suffix = p.suffix.lower()
    media_types = {'.mp4': 'video/mp4', '.mov': 'video/quicktime',
                   '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska',
                   '.webm': 'video/webm'}
    return FileResponse(str(p), media_type=media_types.get(suffix, 'video/mp4'))


@router.get("/thumbnail/{video_id}/{shot_index}")
def get_thumbnail(video_id: int, shot_index: int, db: Session = Depends(get_db)):
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
    return FileResponse(str(p), media_type="image/jpeg")


@router.get("/clip/{video_id}/{shot_index}")
def get_clip(video_id: int, shot_index: int, db: Session = Depends(get_db)):
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
    return FileResponse(str(p), media_type="video/mp4")


@router.get("/video-thumbnail/{video_id}")
def get_video_thumbnail(video_id: int, db: Session = Depends(get_db)):
    """获取视频封面（第一帧）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

    thumb_path = THUMBNAILS_DIR / f"video_{video_id}_cover.jpg"

    # 如果缓存不存在，提取第一帧
    if not thumb_path.exists():
        try:
            with av.open(video.filepath) as container:
                stream = container.streams.video[0]
                for frame in container.decode(stream):
                    img = frame.to_image()
                    img.save(str(thumb_path), quality=85)
                    break
        except Exception as e:
            raise HTTPException(404, f"无法提取封面: {e}")

    return FileResponse(str(thumb_path), media_type="image/jpeg")
