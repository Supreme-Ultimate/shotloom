import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# 加载 .env 文件
load_dotenv(BASE_DIR / ".env")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3.5-flash")

UPLOADS_DIR = BASE_DIR / "uploads"
SHOTS_DIR = BASE_DIR / "shots"
THUMBNAILS_DIR = BASE_DIR / "thumbnails"

for d in [UPLOADS_DIR, SHOTS_DIR, THUMBNAILS_DIR]:
    d.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{BASE_DIR / 'app.db'}"

# PySceneDetect 阈值，越低越敏感（默认27）
SCENE_THRESHOLD = float(os.getenv("SCENE_THRESHOLD", "27"))

# 每个镜头视频片段最大文件大小（MB），超过则压缩
MAX_CLIP_SIZE_MB = int(os.getenv("MAX_CLIP_SIZE_MB", "20"))

# AI 分析并发数（每个镜头的分析可以并发执行）
AI_CONCURRENCY = int(os.getenv("AI_CONCURRENCY", "500"))

# JWT 认证密钥（生产环境必须设置随机强密钥）
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please-use-random-32-chars")
JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", str(60 * 60 * 24 * 7)))  # 7 天

# 微信开放平台（网站应用）配置
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")
WECHAT_CALLBACK_URL = os.getenv("WECHAT_CALLBACK_URL", "http://localhost:8000/api/auth/wechat/callback")

# 前端地址（用于微信回调后重定向）
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# 新用户默认积分
INITIAL_CREDITS = int(os.getenv("INITIAL_CREDITS", "100"))
