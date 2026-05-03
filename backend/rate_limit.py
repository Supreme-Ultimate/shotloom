"""Simple Redis-backed IP rate limiter middleware."""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from redis import Redis

from config import RATE_LIMIT_PER_MINUTE, REDIS_URL

redis_client = Redis.from_url(REDIS_URL, decode_responses=True)


async def rate_limit_middleware(request: Request, call_next):
    if RATE_LIMIT_PER_MINUTE <= 0 or request.url.path == "/health":
        return await call_next(request)

    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else None
    client_ip = client_ip or (request.client.host if request.client else "unknown")
    bucket = int(time.time() // 60)
    key = f"rate:{client_ip}:{bucket}"

    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, 90)
        if count > RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
            )
    except Exception:
        # Do not fail closed if Redis is temporarily unavailable.
        pass

    return await call_next(request)
