import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── 用户表（fastapi-users 兼容，手动定义以避免额外依赖复杂性）─────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # 微信登录用户可为 None
    display_name = Column(String, nullable=True)
    wechat_openid = Column(String, unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── 积分余额表 ─────────────────────────────────────────────────────────────────

class Credits(Base):
    __tablename__ = "credits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    balance = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── 积分流水表 ─────────────────────────────────────────────────────────────────

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    delta = Column(Integer, nullable=False)              # 正数=充值，负数=消费
    reason = Column(String, nullable=False)              # analysis | admin_reset | refund
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=True)
    shot_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── 视频表 ─────────────────────────────────────────────────────────────────────

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # nullable 兼容历史数据
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    duration = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    status = Column(String, default="uploaded")  # uploaded | detecting | detected | analyzing | completed | error
    current_task_id = Column(String, nullable=True)  # 当前正在运行的任务 ID
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── 镜头表 ─────────────────────────────────────────────────────────────────────

class Shot(Base):
    __tablename__ = "shots"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, nullable=False, index=True)
    index = Column(Integer, nullable=False)        # 镜头序号（0-based）
    start_time = Column(Float, nullable=False)     # 秒
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    clip_path = Column(String, nullable=True)      # 切割后的 .mp4 路径
    thumbnail_path = Column(String, nullable=True) # 缩略图路径
    _analysis = Column("analysis", Text, nullable=True)

    @property
    def analysis(self):
        return json.loads(self._analysis) if self._analysis else None

    @analysis.setter
    def analysis(self, value):
        self._analysis = json.dumps(value, ensure_ascii=False) if value else None


# ─── 全片分析表 ─────────────────────────────────────────────────────────────────

class VideoAnalysis(Base):
    __tablename__ = "video_analyses"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, nullable=False, unique=True, index=True)
    _continuity_report = Column("continuity_report", Text, nullable=True)
    _rhythm_report = Column("rhythm_report", Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def continuity_report(self):
        return json.loads(self._continuity_report) if self._continuity_report else None

    @continuity_report.setter
    def continuity_report(self, value):
        self._continuity_report = json.dumps(value, ensure_ascii=False) if value else None

    @property
    def rhythm_report(self):
        return json.loads(self._rhythm_report) if self._rhythm_report else None

    @rhythm_report.setter
    def rhythm_report(self, value):
        self._rhythm_report = json.dumps(value, ensure_ascii=False) if value else None


# ─── 初始化 ─────────────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(bind=engine)
    # SQLite 迁移：为已有 videos 表补充 user_id 列（如果不存在）
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing_cols = [c["name"] for c in inspector.get_columns("videos")] if "videos" in inspector.get_table_names() else []
        if "user_id" not in existing_cols and "videos" in inspector.get_table_names():
            conn.execute(text("ALTER TABLE videos ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
