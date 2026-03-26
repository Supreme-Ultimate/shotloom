"""积分路由：查余额、查流水"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, User, CreditTransaction
from auth import get_current_user
from services.credits_service import get_balance, get_or_create_credits

router = APIRouter(prefix="/api/credits", tags=["credits"])


@router.get("/me")
def my_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    balance = get_balance(current_user.id, db)
    return {"user_id": current_user.id, "balance": balance}


@router.get("/me/transactions")
def my_transactions(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(CreditTransaction).filter(CreditTransaction.user_id == current_user.id)
    total = query.count()
    txns = query.order_by(CreditTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "balance": get_balance(current_user.id, db),
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
