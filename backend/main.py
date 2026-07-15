from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time

from database import init_db
from routers import upload, analysis, results, export, analysis_config
from routers import auth_router, wechat, admin, credits, public
from logger import app_logger
from config import CORS_ORIGINS
from rate_limit import rate_limit_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_logger.info("应用启动中...")
    init_db()
    app_logger.info("数据库初始化完成")
    yield


app = FastAPI(title="ShotLoom", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有 HTTP 请求"""
    start_time = time.time()
    app_logger.info(f"请求开始: {request.method} {request.url.path}")

    response = await call_next(request)

    duration = time.time() - start_time
    app_logger.info(f"请求完成: {request.method} {request.url.path} | 状态码={response.status_code} | 耗时={duration:.3f}s")

    return response


app.middleware("http")(rate_limit_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 原有路由
app.include_router(upload.router)
app.include_router(analysis.router)
app.include_router(results.router)
app.include_router(export.router)
app.include_router(analysis_config.router)

# 新增路由
app.include_router(auth_router.router)
app.include_router(wechat.router)
app.include_router(admin.router)
app.include_router(credits.router)
app.include_router(public.router)


@app.get("/health")
def health():
    return {"status": "ok"}
