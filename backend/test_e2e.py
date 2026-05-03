"""
后端端到端测试
覆盖所有交互流程：认证、积分、上传、管理员操作

运行方式：
  cd backend
  .venv/bin/pytest test_e2e.py -v
"""
import io
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch
from fastapi.testclient import TestClient

# ─── 测试数据库配置（内存 SQLite，与生产库完全隔离）────────────────────────────

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


# ─── 创建测试客户端（必须在 import main 之前 patch DB）────────────────────────

import config
config.RUN_TASKS_INLINE = True
import database
database.engine = TEST_ENGINE
database.SessionLocal = TestingSession
from database import Base, get_db, User, Video, Shot, Credits, CreditTransaction, AnalysisTask
from main import app
import routers.analysis as analysis_router

app.dependency_overrides[get_db] = override_get_db

# 建表
Base.metadata.create_all(bind=TEST_ENGINE)

client = TestClient(app, raise_server_exceptions=True)


def clear_client_cookies():
    client.cookies.clear()


async def fake_run_analysis(_video_id, task_id, _user_id=None, _shot_indices=None):
    db = TestingSession()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if task:
            task.stage = "completed"
            task.done = task.total
            db.commit()
    finally:
        db.close()


ORIGINAL_RUN_ANALYSIS = analysis_router._run_analysis
analysis_router._run_analysis = fake_run_analysis


# ─── 工具函数 ───────────────────────────────────────────────────────────────────

def register(email, password="password123", display_name=""):
    return client.post("/api/auth/register", json={
        "email": email, "password": password, "display_name": display_name
    })


def login(email, password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def get_db_session():
    return TestingSession()


def make_superuser(email: str):
    """将某用户设为超级管理员（直接操作测试 DB）"""
    db = get_db_session()
    try:
        user = db.query(User).filter(User.email == email).first()
        user.is_superuser = True
        db.commit()
    finally:
        db.close()


def set_credits(user_id: int, balance: int):
    """直接设置用户积分余额（用于测试 402 场景）"""
    db = get_db_session()
    try:
        credits = db.query(Credits).filter(Credits.user_id == user_id).first()
        credits.balance = balance
        db.commit()
    finally:
        db.close()


def create_video_with_shots(user_id: int, shot_count: int = 3) -> int:
    """在测试 DB 中直接创建视频+镜头记录，绕过真实上传"""
    db = get_db_session()
    try:
        video = Video(
            user_id=user_id,
            filename="test_video.mp4",
            filepath="/tmp/test_video.mp4",
            duration=30.0,
            fps=25.0,
            status="detected",
        )
        db.add(video)
        db.flush()
        for i in range(shot_count):
            db.add(Shot(
                video_id=video.id,
                index=i,
                start_time=float(i * 10),
                end_time=float(i * 10 + 9),
                duration=9.0,
            ))
        db.commit()
        return video.id
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_check(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestRegister:
    def test_register_success(self):
        r = register("new_user@example.com")
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["user_id"], int)

    def test_register_duplicate_email(self):
        register("dup@example.com")
        r = register("dup@example.com")
        assert r.status_code == 400
        assert "已注册" in r.json()["detail"]

    def test_register_short_password(self):
        r = register("short@example.com", password="123")
        assert r.status_code == 400
        assert "密码" in r.json()["detail"]

    def test_register_creates_credits(self):
        """注册后自动创建 100 积分"""
        r = register("credits_check@example.com")
        token = r.json()["access_token"]
        r2 = client.get("/api/credits/me", headers=auth_headers(token))
        assert r2.status_code == 200
        assert r2.json()["balance"] == 100

    def test_register_initial_grant_transaction(self):
        """注册后流水中应有 initial_grant 记录"""
        r = register("tx_check@example.com")
        token = r.json()["access_token"]
        r2 = client.get("/api/credits/me/transactions", headers=auth_headers(token))
        assert r2.status_code == 200
        data = r2.json()
        assert data["total"] >= 1
        assert any(t["reason"] == "initial_grant" for t in data["data"])


class TestLogin:
    @classmethod
    def setup_class(cls):
        register("login_test@example.com", "mypassword")

    def test_login_success(self):
        r = login("login_test@example.com", "mypassword")
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "is_superuser" in data

    def test_login_wrong_password(self):
        r = login("login_test@example.com", "wrongpass")
        assert r.status_code == 401

    def test_login_nonexistent_user(self):
        r = login("nobody@example.com", "pass")
        assert r.status_code == 401

    def test_login_disabled_user(self):
        """禁用用户后登录应返回 403"""
        register("disabled@example.com", "pass123")
        # 直接在 DB 中禁用
        db = get_db_session()
        try:
            user = db.query(User).filter(User.email == "disabled@example.com").first()
            user.is_active = False
            db.commit()
        finally:
            db.close()
        r = login("disabled@example.com", "pass123")
        assert r.status_code == 403


class TestCurrentUser:
    @classmethod
    def setup_class(cls):
        r = register("me_test@example.com", display_name="测试用户")
        cls.token = r.json()["access_token"]

    def test_get_me(self):
        r = client.get("/api/auth/me", headers=auth_headers(self.token))
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "me_test@example.com"
        assert data["display_name"] == "测试用户"
        assert data["is_superuser"] == False

    def test_get_me_no_token(self):
        clear_client_cookies()
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_get_me_invalid_token(self):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer fake.token.here"})
        assert r.status_code == 401


class TestCredits:
    @classmethod
    def setup_class(cls):
        r = register("credits_user@example.com")
        cls.token = r.json()["access_token"]
        cls.user_id = r.json()["user_id"]

    def test_credits_balance(self):
        r = client.get("/api/credits/me", headers=auth_headers(self.token))
        assert r.status_code == 200
        assert r.json()["balance"] == 100

    def test_credits_transactions_list(self):
        r = client.get("/api/credits/me/transactions", headers=auth_headers(self.token))
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert data["balance"] == 100

    def test_credits_requires_auth(self):
        clear_client_cookies()
        r = client.get("/api/credits/me")
        assert r.status_code == 401


class TestUpload:
    @classmethod
    def setup_class(cls):
        r = register("uploader@example.com")
        cls.token = r.json()["access_token"]

    def _dummy_video(self, name="test.mp4"):
        """构造一个假的 mp4 文件（ffprobe 会失败，但端点会用默认值）"""
        return ("file", (name, io.BytesIO(b"fake video content"), "video/mp4"))

    def test_upload_as_user(self):
        r = client.post(
            "/api/upload",
            files=[self._dummy_video()],
            headers=auth_headers(self.token),
        )
        assert r.status_code == 200
        data = r.json()
        assert "video_id" in data
        assert data["filename"] == "test.mp4"

    def test_upload_requires_auth(self):
        clear_client_cookies()
        r = client.post("/api/upload", files=[self._dummy_video("anon.mp4")])
        assert r.status_code == 401

    def test_upload_invalid_format(self):
        r = client.post(
            "/api/upload",
            files=[("file", ("doc.txt", io.BytesIO(b"hello"), "text/plain"))],
            headers=auth_headers(self.token),
        )
        assert r.status_code == 400
        assert "不支持" in r.json()["detail"]


class TestVideoList:
    @classmethod
    def setup_class(cls):
        # 用户A 上传一个视频
        r_a = register("list_a@example.com")
        cls.token_a = r_a.json()["access_token"]
        cls.user_a_id = r_a.json()["user_id"]

        # 用户B 上传一个视频
        r_b = register("list_b@example.com")
        cls.token_b = r_b.json()["access_token"]

        client.post(
            "/api/upload",
            files=[("file", ("user_a.mp4", io.BytesIO(b"vid"), "video/mp4"))],
            headers=auth_headers(cls.token_a),
        )
        client.post(
            "/api/upload",
            files=[("file", ("user_b.mp4", io.BytesIO(b"vid"), "video/mp4"))],
            headers=auth_headers(cls.token_b),
        )

    def test_user_only_sees_own_videos(self):
        r = client.get("/api/videos", headers=auth_headers(self.token_a))
        assert r.status_code == 200
        filenames = [v["filename"] for v in r.json()]
        assert any("user_a" in f for f in filenames)
        assert not any("user_b" in f for f in filenames)

    def test_admin_workspace_only_sees_own_videos(self):
        r_admin = register("workspace_admin@example.com")
        admin_token = r_admin.json()["access_token"]
        make_superuser("workspace_admin@example.com")
        admin_token = login("workspace_admin@example.com").json()["access_token"]

        client.post(
            "/api/upload",
            files=[("file", ("admin_own.mp4", io.BytesIO(b"vid"), "video/mp4"))],
            headers=auth_headers(admin_token),
        )

        r = client.get("/api/videos", headers=auth_headers(admin_token))

        assert r.status_code == 200
        filenames = [v["filename"] for v in r.json()]
        assert any("admin_own" in f for f in filenames)
        assert not any("user_a" in f or "user_b" in f for f in filenames)

    def test_video_not_found(self):
        r = client.get("/api/videos/99999", headers=auth_headers(self.token_a))
        assert r.status_code == 404


class TestAdmin:
    @classmethod
    def setup_class(cls):
        # 普通用户
        r_normal = register("normal_for_admin@example.com")
        cls.normal_token = r_normal.json()["access_token"]

        # 管理员
        r_admin = register("admin@example.com")
        cls.admin_user_id = r_admin.json()["user_id"]
        make_superuser("admin@example.com")
        r_login = login("admin@example.com")
        cls.admin_token = r_login.json()["access_token"]

        # 受测用户
        r_target = register("target_user@example.com")
        cls.target_user_id = r_target.json()["user_id"]

    def test_normal_user_cannot_access_admin(self):
        r = client.get("/api/admin/users", headers=auth_headers(self.normal_token))
        assert r.status_code == 403

    def test_unauthenticated_cannot_access_admin(self):
        clear_client_cookies()
        r = client.get("/api/admin/users")
        assert r.status_code == 401

    def test_admin_list_users(self):
        r = client.get("/api/admin/users", headers=auth_headers(self.admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "data" in data
        assert data["total"] >= 2
        # 每个用户应包含必要字段
        for u in data["data"]:
            for field in ("id", "email", "credits", "video_count", "is_active"):
                assert field in u, f"缺少字段 {field}"

    def test_admin_list_users_keyword_filter(self):
        r = client.get(
            "/api/admin/users?keyword=target_user",
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()["data"]]
        assert any("target_user" in e for e in emails)

    def test_admin_get_user_detail(self):
        r = client.get(
            f"/api/admin/users/{self.target_user_id}",
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == self.target_user_id
        assert data["credits"] == 100

    def test_admin_get_nonexistent_user(self):
        r = client.get("/api/admin/users/99999", headers=auth_headers(self.admin_token))
        assert r.status_code == 404

    def test_admin_reset_credits(self):
        r = client.post(
            f"/api/admin/users/{self.target_user_id}/credits/reset",
            json={"balance": 500},
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        assert r.json()["new_balance"] == 500
        # 验证余额确实变了
        r2 = client.get(
            f"/api/admin/users/{self.target_user_id}",
            headers=auth_headers(self.admin_token),
        )
        assert r2.json()["credits"] == 500

    def test_admin_reset_credits_negative_rejected(self):
        r = client.post(
            f"/api/admin/users/{self.target_user_id}/credits/reset",
            json={"balance": -10},
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 400

    def test_admin_reset_creates_transaction(self):
        """重置积分应产生 admin_reset 流水"""
        r = client.get(
            f"/api/admin/users/{self.target_user_id}/transactions",
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        reasons = [t["reason"] for t in r.json()["data"]]
        assert "admin_reset" in reasons

    def test_admin_disable_user(self):
        r = client.patch(
            f"/api/admin/users/{self.target_user_id}/status",
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        assert r.json()["is_active"] == False

    def test_admin_enable_user(self):
        """再次调用 toggle，恢复启用"""
        r = client.patch(
            f"/api/admin/users/{self.target_user_id}/status",
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        assert r.json()["is_active"] == True

    def test_admin_get_user_videos(self):
        r = client.get(
            f"/api/admin/users/{self.target_user_id}/videos",
            headers=auth_headers(self.admin_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "data" in data


class TestCreditsAnalysis:
    """积分与分析流程：积分充足通过检查，不足返回 402"""

    @classmethod
    def setup_class(cls):
        r = register("analysis_user@example.com")
        cls.token = r.json()["access_token"]
        cls.user_id = r.json()["user_id"]

    def test_analyze_no_shots_returns_400(self):
        """视频没有镜头时，POST /analyze 应返回 400"""
        db = get_db_session()
        try:
            video = Video(
                user_id=self.user_id,
                filename="noshot.mp4",
                filepath="/tmp/noshot.mp4",
                duration=10.0,
                fps=25.0,
                status="detected",
            )
            db.add(video)
            db.commit()
            video_id = video.id
        finally:
            db.close()

        r = client.post(
            f"/api/analyze/{video_id}",
            headers=auth_headers(self.token),
        )
        assert r.status_code == 400
        assert "镜头检测" in r.json()["detail"]

    def test_analyze_sufficient_credits_passes_check(self):
        """余额 100，镜头数 3 → 通过积分检查，返回 200（后台任务启动）"""
        video_id = create_video_with_shots(self.user_id, shot_count=3)
        r = client.post(
            f"/api/analyze/{video_id}",
            headers=auth_headers(self.token),
        )
        # 200 = 积分检查通过，后台任务已启动
        assert r.status_code == 200
        assert r.json()["shot_count"] == 3

    def test_analyze_insufficient_credits_returns_402(self):
        """余额为 0，任何镜头数都应返回 402"""
        # 新建独立用户，确保余额干净
        r = register("broke_user@example.com")
        token = r.json()["access_token"]
        user_id = r.json()["user_id"]
        set_credits(user_id, 0)

        video_id = create_video_with_shots(user_id, shot_count=5)
        r = client.post(f"/api/analyze/{video_id}", headers=auth_headers(token))
        assert r.status_code == 402
        assert "积分不足" in r.json()["detail"]

    def test_analyze_nonexistent_video(self):
        r = client.post(
            "/api/analyze/99999",
            headers=auth_headers(self.token),
        )
        assert r.status_code == 404

    def test_analyze_requires_auth(self):
        clear_client_cookies()
        video_id = create_video_with_shots(self.user_id, shot_count=1)
        r = client.post(f"/api/analyze/{video_id}")
        assert r.status_code == 401


class TestShotAdjust:
    """手动调整镜头边界"""

    @classmethod
    def setup_class(cls):
        r = register("adjust_user@example.com")
        cls.token = r.json()["access_token"]
        cls.user_id = r.json()["user_id"]
        cls.video_id = create_video_with_shots(cls.user_id, shot_count=2)

    def test_adjust_shots(self):
        r = client.put(
            f"/api/shots/{self.video_id}/adjust",
            json={"shots": [
                {"start_time": 0.0, "end_time": 5.0},
                {"start_time": 5.0, "end_time": 12.0},
                {"start_time": 12.0, "end_time": 20.0},
            ]},
            headers=auth_headers(self.token),
        )
        assert r.status_code == 200
        assert r.json()["shot_count"] == 3

    def test_adjust_nonexistent_video(self):
        r = client.put(
            "/api/shots/99999/adjust",
            json={"shots": [{"start_time": 0.0, "end_time": 5.0}]},
            headers=auth_headers(self.token),
        )
        assert r.status_code == 404


class TestAuthorizationBoundaries:
    @classmethod
    def setup_class(cls):
        r_owner = register("owner@example.com")
        cls.owner_token = r_owner.json()["access_token"]
        cls.owner_id = r_owner.json()["user_id"]
        r_other = register("other@example.com")
        cls.other_token = r_other.json()["access_token"]
        cls.video_id = create_video_with_shots(cls.owner_id, shot_count=1)

    def test_other_user_cannot_get_results(self):
        r = client.get(f"/api/results/{self.video_id}", headers=auth_headers(self.other_token))
        assert r.status_code == 403

    def test_other_user_cannot_adjust_shots(self):
        r = client.put(
            f"/api/shots/{self.video_id}/adjust",
            json={"shots": [{"start_time": 0.0, "end_time": 1.0}]},
            headers=auth_headers(self.other_token),
        )
        assert r.status_code == 403

    def test_owner_can_get_results(self):
        r = client.get(f"/api/results/{self.video_id}", headers=auth_headers(self.owner_token))
        assert r.status_code == 200


class TestClipExtractorTimestamps:
    def test_output_rate_rounds_fractional_source_rate(self):
        from fractions import Fraction
        from types import SimpleNamespace
        from services.clip_extractor import _output_rate

        assert _output_rate(SimpleNamespace(average_rate=Fraction(3097600, 129139))) == 24
        assert _output_rate(SimpleNamespace(average_rate=None)) == 25

    def test_audio_encoder_helper_exists_to_preserve_dialogue(self):
        from services.clip_extractor import _encode_audio_track

        assert callable(_encode_audio_track)


class TestAiAnalyzerClipBounds:
    def test_compute_extended_bounds_extends_first_shot_forward(self):
        from services.ai_analyzer import _compute_extended_bounds

        start, end = _compute_extended_bounds(0.0, 1.001, 15.133, 2.0)

        assert start == 0.0
        assert end >= 2.0

    def test_compute_extended_bounds_extends_middle_shot_backward(self):
        from services.ai_analyzer import _compute_extended_bounds

        start, end = _compute_extended_bounds(10.339, 11.506, 15.133, 2.0)

        assert start < 10.339
        assert end == 11.506
        assert end - start >= 2.0


class TestAnalysisWorkerGuards:
    def test_failed_clip_is_not_sent_to_ai(self):
        db = get_db_session()
        try:
            r = register("failed_clip_user@example.com")
            user_id = r.json()["user_id"]
            video = Video(
                user_id=user_id,
                filename="failed_clip.mp4",
                filepath="/tmp/failed_clip.mp4",
                duration=10.0,
                fps=25.0,
                status="detected",
            )
            db.add(video)
            db.flush()
            shot = Shot(
                video_id=video.id,
                index=0,
                start_time=0.0,
                end_time=1.0,
                duration=1.0,
                clip_path=None,
            )
            db.add(shot)
            db.commit()
            video_id = video.id
        finally:
            db.close()

        from task_store import create_task
        create_task("missing_clip_task", video_id, user_id, 1, None)

        with (
            patch.object(analysis_router, "analyze_shot") as analyze_mock,
            patch.object(analysis_router, "extract_shot_clips", return_value=[(None, None)]),
        ):
            import asyncio
            asyncio.run(ORIGINAL_RUN_ANALYSIS(video_id, "missing_clip_task", user_id))
            analyze_mock.assert_not_called()

        db = get_db_session()
        try:
            stored = db.query(Shot).filter(Shot.video_id == video_id, Shot.index == 0).first()
            assert "切片失败" in stored.analysis["error"]
        finally:
            db.close()


class TestProgress:
    def test_progress_not_found(self):
        r = client.get("/api/progress/nonexistent_task_id")
        assert r.status_code == 200
        # SSE 流：第一个事件应包含 not_found
        assert "not_found" in r.text

    def test_task_status_clears_stale_active_task(self):
        r = register("stale_task_user@example.com")
        token = r.json()["access_token"]
        user_id = r.json()["user_id"]
        video_id = create_video_with_shots(user_id, shot_count=3)
        task_id = "task_stale_refresh"
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=31)

        db = get_db_session()
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            video.status = "analyzing"
            video.current_task_id = task_id
            db.add(AnalysisTask(
                id=task_id,
                video_id=video_id,
                user_id=user_id,
                stage="analyzing",
                done=0,
                total=3,
                updated_at=stale_time,
            ))
            db.commit()
        finally:
            db.close()

        r = client.get(f"/api/videos/{video_id}/task-status", headers=auth_headers(token))

        assert r.status_code == 200
        assert r.json()["has_active_task"] is False
        assert r.json()["task_id"] is None

        db = get_db_session()
        try:
            task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
            video = db.query(Video).filter(Video.id == video_id).first()
            assert task.stage == "error"
            assert task.finished_at is not None
            assert "异常中断" in task.message
            assert video.status == "error"
            assert video.current_task_id is None
        finally:
            db.close()


# ─── 运行入口 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"])
