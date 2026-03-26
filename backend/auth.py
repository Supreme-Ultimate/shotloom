"""
认证工具：JWT 签发/验证、密码哈希、当前用户依赖注入。
不使用 fastapi-users（减少复杂性），手动实现以保持简洁。
"""
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from config import SECRET_KEY, JWT_LIFETIME_SECONDS
from database import get_db, User

bearer_scheme = HTTPBearer(auto_error=False)


# ─── 密码工具 ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ─── JWT 工具 ─────────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_LIFETIME_SECONDS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> int:
    """解码 JWT，返回 user_id，失败抛 HTTPException"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token 已过期")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token 无效")


# ─── 依赖注入 ─────────────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未提供认证 Token")
    user_id = decode_token(credentials.credentials)
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已禁用")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """不强制登录，有 token 则返回用户，无 token 返回 None"""
    if not credentials:
        return None
    try:
        user_id = decode_token(credentials.credentials)
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except HTTPException:
        return None


def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return current_user
