"""
管理员路由（需要 is_superuser=True）
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db, User, Video, Shot, Credits, CreditTransaction, VideoAnalysis
from auth import get_current_superuser
from services.credits_service import admin_reset as credits_admin_reset

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ResetCreditsRequest(BaseModel):
    balance: int


@router.get("/users")
def list_users(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """分页获取用户列表，含积分余额和视频数"""
    query = db.query(User)
    if keyword:
        query = query.filter(
            (User.email.contains(keyword)) | (User.display_name.contains(keyword))
        )
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for u in users:
        credits = db.query(Credits).filter(Credits.user_id == u.id).first()
        video_count = db.query(Video).filter(Video.user_id == u.id).count()
        result.append({
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "is_superuser": u.is_superuser,
            "is_active": u.is_active,
            "credits": credits.balance if credits else 0,
            "video_count": video_count,
            "created_at": u.created_at.isoformat(),
            "wechat_linked": bool(u.wechat_openid),
        })

    return {"total": total, "page": page, "page_size": page_size, "data": result}


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    credits = db.query(Credits).filter(Credits.user_id == user_id).first()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
        "credits": credits.balance if credits else 0,
        "created_at": user.created_at.isoformat(),
        "wechat_linked": bool(user.wechat_openid),
    }


@router.get("/users/{user_id}/videos")
def get_user_videos(
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """查看某用户的所有视频"""
    query = db.query(Video).filter(Video.user_id == user_id)
    total = query.count()
    videos = query.order_by(Video.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "data": [
            {
                "id": v.id,
                "filename": v.filename,
                "duration": v.duration,
                "status": v.status,
                "created_at": v.created_at.isoformat(),
                "shot_count": db.query(Shot).filter(Shot.video_id == v.id).count(),
            }
            for v in videos
        ],
    }


@router.get("/users/{user_id}/transactions")
def get_user_transactions(
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """查看某用户的积分流水"""
    query = db.query(CreditTransaction).filter(CreditTransaction.user_id == user_id)
    total = query.count()
    txns = query.order_by(CreditTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "data": [
            {
                "id": t.id,
                "delta": t.delta,
                "reason": t.reason,
                "video_id": t.video_id,
                "shot_count": t.shot_count,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
    }


@router.post("/users/{user_id}/credits/reset")
def reset_credits(
    user_id: int,
    body: ResetCreditsRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_superuser),
):
    """管理员重置用户积分"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if body.balance < 0:
        raise HTTPException(400, "积分不能为负数")

    credits = credits_admin_reset(user_id, body.balance, current_admin.id, db)
    return {"user_id": user_id, "new_balance": credits.balance}


@router.patch("/users/{user_id}/status")
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """启用/禁用用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.is_active = not user.is_active
    db.commit()
    return {"user_id": user_id, "is_active": user.is_active}
