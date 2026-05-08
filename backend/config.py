import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# 加载 .env 文件
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

ENV = os.getenv("ENV", "development").lower()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3.5-omni-plus")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
CONTINUITY_MODEL_NAME = os.getenv("CONTINUITY_MODEL_NAME", "qwen-max")
PROMPT_CONFIG_PATH = os.getenv("PROMPT_CONFIG_PATH", "")
MIN_MODEL_VIDEO_DURATION = float(os.getenv("MIN_MODEL_VIDEO_DURATION", "2.0"))
SAFE_MODEL_VIDEO_DURATION = float(os.getenv("SAFE_MODEL_VIDEO_DURATION", "3.0"))
SHORT_SHOT_MERGE_MAX_SHOTS = int(os.getenv("SHORT_SHOT_MERGE_MAX_SHOTS", "5"))
MODEL_TRANSIENT_RETRIES = int(os.getenv("MODEL_TRANSIENT_RETRIES", "2"))
MODEL_TRANSIENT_RETRY_DELAY = float(os.getenv("MODEL_TRANSIENT_RETRY_DELAY", "1.0"))
ANALYSIS_ROUTER_MODE = os.getenv("ANALYSIS_ROUTER_MODE", "auto").lower()
SELECTED_CONTEXT_MIN_SHOTS = int(os.getenv("SELECTED_CONTEXT_MIN_SHOTS", "20"))
WHOLE_VIDEO_MAX_DURATION = float(os.getenv("WHOLE_VIDEO_MAX_DURATION", "180"))
WHOLE_VIDEO_MAX_SHOTS = int(os.getenv("WHOLE_VIDEO_MAX_SHOTS", "60"))
CHUNK_SEGMENT_DURATION = float(os.getenv("CHUNK_SEGMENT_DURATION", "300"))
CHUNK_SEGMENT_MAX_SHOTS = int(os.getenv("CHUNK_SEGMENT_MAX_SHOTS", "80"))
CHUNK_SEGMENT_OVERLAP_SHOTS = int(os.getenv("CHUNK_SEGMENT_OVERLAP_SHOTS", "2"))
SHOT_FALLBACK_ENABLED = os.getenv("SHOT_FALLBACK_ENABLED", "true").lower() == "true"
CONTEXT_BASE64_MAX_MB = float(os.getenv("CONTEXT_BASE64_MAX_MB", "8"))
QWEN_VIDEO_INPUT_MODE = os.getenv("QWEN_VIDEO_INPUT_MODE", "auto").lower()
PUBLIC_VIDEO_BASE_URL = os.getenv("PUBLIC_VIDEO_BASE_URL", "").rstrip("/")
SIGNED_VIDEO_URL_EXPIRE_SECONDS = int(os.getenv("SIGNED_VIDEO_URL_EXPIRE_SECONDS", "1800"))
SIGNED_VIDEO_URL_SECRET = os.getenv("SIGNED_VIDEO_URL_SECRET", "")
QWEN_OMNI_OUTPUT_MODALITIES = [m.strip() for m in os.getenv("QWEN_OMNI_OUTPUT_MODALITIES", "text").split(",") if m.strip()]

UPLOADS_DIR = BASE_DIR / "uploads"
SHOTS_DIR = BASE_DIR / "shots"
THUMBNAILS_DIR = BASE_DIR / "thumbnails"

for d in [UPLOADS_DIR, SHOTS_DIR, THUMBNAILS_DIR]:
    d.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'app.db'}")
DB_CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# PySceneDetect 阈值，越低越敏感（默认27）
SCENE_THRESHOLD = float(os.getenv("SCENE_THRESHOLD", "27"))

# 每个镜头视频片段最大文件大小（MB），超过则压缩
MAX_CLIP_SIZE_MB = int(os.getenv("MAX_CLIP_SIZE_MB", "20"))

# AI 分析并发数（每个镜头的分析可以并发执行）
AI_CONCURRENCY = int(os.getenv("AI_CONCURRENCY", "2"))

# 上传限制
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "1024"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = float(os.getenv("MAX_VIDEO_DURATION_SECONDS", "3600"))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "analysis")
RUN_TASKS_INLINE = os.getenv("RUN_TASKS_INLINE", "false").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
TASK_STALE_MINUTES = int(os.getenv("TASK_STALE_MINUTES", "30"))

# JWT 认证密钥（生产环境必须设置随机强密钥）
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please-use-random-32-chars")
if ENV == "production" and (
    not SECRET_KEY
    or SECRET_KEY == "change-me-in-production-please-use-random-32-chars"
    or len(SECRET_KEY) < 32
):
    raise RuntimeError("生产环境必须设置长度至少 32 位的随机 SECRET_KEY")
JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", str(60 * 60 * 24 * 7)))  # 7 天
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "") or None

# 微信开放平台（网站应用）配置
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")
WECHAT_CALLBACK_URL = os.getenv("WECHAT_CALLBACK_URL", "http://localhost:8000/api/auth/wechat/callback")

# 前端地址（用于微信回调后重定向）
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# CORS 白名单
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

# 新用户默认积分
INITIAL_CREDITS = int(os.getenv("INITIAL_CREDITS", "100"))
