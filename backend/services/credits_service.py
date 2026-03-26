"""积分服务：查余额、扣积分、管理员重置"""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import Credits, CreditTransaction
from config import INITIAL_CREDITS


def get_or_create_credits(user_id: int, db: Session) -> Credits:
    credits = db.query(Credits).filter(Credits.user_id == user_id).first()
    if not credits:
        credits = Credits(user_id=user_id, balance=INITIAL_CREDITS)
        db.add(credits)
        db.add(CreditTransaction(
            user_id=user_id,
            delta=INITIAL_CREDITS,
            reason="initial_grant",
        ))
        db.commit()
        db.refresh(credits)
    return credits


def get_balance(user_id: int, db: Session) -> int:
    credits = get_or_create_credits(user_id, db)
    return credits.balance


def check_sufficient(user_id: int, required: int, db: Session):
    """检查余额是否足够，不足则抛 402"""
    balance = get_balance(user_id, db)
    if balance < required:
        raise HTTPException(
            402,
            f"积分不足：需要 {required} 积分，当前余额 {balance} 积分"
        )


def deduct(user_id: int, shot_count: int, video_id: int, db: Session):
    """扣除积分并记录流水"""
    credits = get_or_create_credits(user_id, db)
    if credits.balance < shot_count:
        raise HTTPException(
            402,
            f"积分不足：需要 {shot_count} 积分，当前余额 {credits.balance} 积分"
        )
    credits.balance -= shot_count
    credits.updated_at = datetime.utcnow()
    db.add(CreditTransaction(
        user_id=user_id,
        delta=-shot_count,
        reason="analysis",
        video_id=video_id,
        shot_count=shot_count,
    ))
    db.commit()


def admin_reset(user_id: int, new_balance: int, operator_id: int, db: Session):
    """管理员重置积分"""
    credits = get_or_create_credits(user_id, db)
    old_balance = credits.balance
    credits.balance = new_balance
    credits.updated_at = datetime.utcnow()
    db.add(CreditTransaction(
        user_id=user_id,
        delta=new_balance - old_balance,
        reason="admin_reset",
    ))
    db.commit()
    return credits
