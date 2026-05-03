"""
认证路由：注册、登录、获取当前用户信息
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db, User, Credits, CreditTransaction
from auth import clear_auth_cookie, create_access_token, get_current_user, hash_password, set_auth_cookie, verify_password
from config import INITIAL_CREDITS

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str | None
    is_superuser: bool
    is_active: bool

    model_config = {"from_attributes": True}


def _create_user_with_credits(db: Session, user: User) -> User:
    """创建用户并初始化积分"""
    db.add(user)
    db.flush()  # 获取 user.id
    credits = Credits(user_id=user.id, balance=INITIAL_CREDITS)
    db.add(credits)
    db.add(CreditTransaction(
        user_id=user.id,
        delta=INITIAL_CREDITS,
        reason="initial_grant",
    ))
    db.commit()
    db.refresh(user)
    return user


@router.post("/register", response_model=dict)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该邮箱已注册")
    if len(body.password) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "密码长度不能少于 6 位")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    user = _create_user_with_credits(db, user)
    token = create_access_token(user.id)
    set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@router.post("/login", response_model=dict)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.hashed_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或密码错误")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")

    token = create_access_token(user.id)
    set_auth_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "is_superuser": user.is_superuser,
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"ok": True}
