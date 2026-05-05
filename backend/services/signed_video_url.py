"""Short-lived signed URLs for model-side video fetching."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from config import SECRET_KEY, SIGNED_VIDEO_URL_EXPIRE_SECONDS, SIGNED_VIDEO_URL_SECRET

_SCOPE = "ai_analysis"


def _secret(explicit: str | None = None) -> str:
    secret = explicit or SIGNED_VIDEO_URL_SECRET or SECRET_KEY
    if not secret:
        raise ValueError("未配置签名视频 URL 密钥")
    return secret


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_signed_video_token(video_id: int, expires_in: int | None = None, secret: str | None = None) -> str:
    ttl = SIGNED_VIDEO_URL_EXPIRE_SECONDS if expires_in is None else int(expires_in)
    payload = {
        "video_id": int(video_id),
        "scope": _SCOPE,
        "exp": int(time.time()) + max(1, ttl),
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_b64, _secret(secret))
    return f"{payload_b64}.{signature}"


def verify_signed_video_token(token: str, secret: str | None = None) -> dict[str, Any]:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("签名视频 URL token 格式无效") from exc

    expected = _sign(payload_b64, _secret(secret))
    if not hmac.compare_digest(signature, expected):
        raise ValueError("签名视频 URL token 签名无效")

    try:
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise ValueError("签名视频 URL token 内容无效") from exc

    if payload.get("scope") != _SCOPE:
        raise ValueError("签名视频 URL token scope 无效")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("签名视频 URL 已过期")
    if not payload.get("video_id"):
        raise ValueError("签名视频 URL 缺少 video_id")
    return payload


def build_signed_video_url(video_id: int, base_url: str, expires_in: int | None = None) -> str:
    base = base_url.rstrip("/")
    token = create_signed_video_token(video_id, expires_in=expires_in)
    return f"{base}/api/public/video/{token}"
