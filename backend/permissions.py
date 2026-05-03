"""Resource access helpers shared by API routers."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database import User, Video


def get_video_for_user(video_id: int, current_user: User, db: Session) -> Video:
    """Return a video only when the current user is allowed to access it."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "视频不存在")

    if current_user.is_superuser:
        return video

    if video.user_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问此视频")

    return video
