"""Persistent analysis task state backed by the application database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from redis import Redis
from rq import Queue

import database
from database import AnalysisTask, Shot, Video
from config import REDIS_URL, TASK_QUEUE_NAME


TERMINAL_STAGES = {"completed", "error", "cancelled", "not_found"}
STALE_TASK_MESSAGE = "分析任务异常中断，请重新分析或重新检测镜头"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_terminal_stage(stage: str | None) -> bool:
    return stage in TERMINAL_STAGES


def _analysis_queue() -> Queue:
    return Queue(TASK_QUEUE_NAME, connection=Redis.from_url(REDIS_URL))


def _job_task_id(job) -> str | None:
    args = list(getattr(job, "args", []) or [])
    if len(args) < 2:
        return None
    task_id = args[1]
    return str(task_id) if task_id else None


def cleanup_terminal_queue_jobs(task_ids: set[str] | None = None, video_ids: set[int] | None = None) -> int:
    """Remove queued jobs whose tasks are already terminal or missing."""
    db = database.SessionLocal()
    removed = 0
    try:
        try:
            queue = _analysis_queue()
            queued_jobs = list(queue.jobs)
        except Exception:
            return 0

        for job in queued_jobs:
            task_id = _job_task_id(job)
            if not task_id:
                continue
            if task_ids is not None and task_id not in task_ids:
                continue

            task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
            should_remove = task is None or is_terminal_stage(task.stage)
            if task is not None and video_ids is not None and task.video_id not in video_ids:
                should_remove = False
            if not should_remove:
                continue

            try:
                job.delete(remove_from_queue=True)
                removed += 1
            except Exception:
                try:
                    queue.remove(job.id)
                    removed += 1
                except Exception:
                    pass
        return removed
    finally:
        db.close()


def resolve_video_status(video_id: int) -> str:
    """Derive the best visible video status from the saved shot analyses."""
    db = database.SessionLocal()
    try:
        shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
        if not shots:
            return "detected"

        any_analysis = False
        any_error = False
        all_analyzed = True
        for shot in shots:
            analysis = shot.analysis
            if not analysis:
                all_analyzed = False
                continue
            any_analysis = True
            if isinstance(analysis, dict) and analysis.get("error"):
                any_error = True
                all_analyzed = False

        if any_error:
            return "error"
        if all_analyzed and any_analysis:
            return "completed"
        return "detected"
    finally:
        db.close()


def create_task(task_id: str, video_id: int, user_id: int, total: int, shot_indices: list[int] | None) -> None:
    db = database.SessionLocal()
    try:
        cleanup_terminal_queue_jobs()
        task = AnalysisTask(
            id=task_id,
            video_id=video_id,
            user_id=user_id,
            stage="queued",
            done=0,
            total=total,
        )
        task.shot_indices = shot_indices
        db.add(task)
        db.commit()
    finally:
        db.close()


def update_task(task_id: str, stage: str, done: int | None = None, total: int | None = None, msg: str | None = None) -> None:
    db = database.SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            return
        task.stage = stage
        if done is not None:
            task.done = done
        if total is not None:
            task.total = total
        task.message = msg
        task.updated_at = utcnow()
        if is_terminal_stage(stage):
            task.finished_at = utcnow()
        db.commit()
    finally:
        db.close()

    if is_terminal_stage(stage):
        cleanup_terminal_queue_jobs(task_ids={task_id})


def get_task(task_id: str) -> AnalysisTask | None:
    db = database.SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if task:
            db.expunge(task)
        return task
    finally:
        db.close()


def get_task_progress(task_id: str) -> dict[str, Any] | None:
    db = database.SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            return None
        data: dict[str, Any] = {
            "stage": task.stage,
            "done": task.done,
            "total": task.total,
        }
        if task.message:
            data["msg"] = task.message
        return data
    finally:
        db.close()


def is_task_cancelled(task_id: str) -> bool:
    task = get_task(task_id)
    return bool(task and task.stage == "cancelled")


def cancel_task(task_id: str, video_id: int | None = None, message: str = "分析已中断") -> bool:
    db = database.SessionLocal()
    should_cleanup = False
    result = False
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            should_cleanup = True
            return False
        if is_terminal_stage(task.stage):
            should_cleanup = True
            result = True
            return result

        now = utcnow()
        task.stage = "cancelled"
        task.message = message
        task.updated_at = now
        task.finished_at = now

        resolved_video_id = video_id if video_id is not None else task.video_id
        video = db.query(Video).filter(Video.id == resolved_video_id).first()
        if video and video.current_task_id == task_id:
            video.current_task_id = None
            video.status = resolve_video_status(resolved_video_id)
            video.error_msg = None
        db.commit()
        should_cleanup = True
        result = True
        return result
    finally:
        db.close()
        if should_cleanup:
            cleanup_terminal_queue_jobs(task_ids={task_id})
    return result


def mark_task_and_video_error(
    task_id: str,
    message: str = STALE_TASK_MESSAGE,
    video_id: int | None = None,
) -> None:
    """Mark a task failed and clear its active pointer on the owning video."""
    db = database.SessionLocal()
    should_cleanup = False
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        resolved_video_id = video_id
        if task:
            resolved_video_id = task.video_id
            now = utcnow()
            task.stage = "error"
            task.message = message
            task.updated_at = now
            task.finished_at = now

        if resolved_video_id is not None:
            video = db.query(Video).filter(Video.id == resolved_video_id).first()
            if video and video.current_task_id == task_id:
                video.status = "error"
                video.error_msg = message
                video.current_task_id = None
        db.commit()
        should_cleanup = True
    finally:
        db.close()
        if should_cleanup:
            cleanup_terminal_queue_jobs(task_ids={task_id})


def reconcile_active_task(
    video: Video,
    stale_after: timedelta,
    message: str = STALE_TASK_MESSAGE,
) -> dict[str, Any] | None:
    """Return active task progress, or clear stale/terminal task state.

    RQ jobs can die in a child process before Python exception handlers inside
    the job run. This keeps page refresh recovery from restoring a dead task.
    """
    if not video.current_task_id:
        return None

    db = database.SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == video.current_task_id).first()
        current = db.query(Video).filter(Video.id == video.id).first()
        if current is None:
            return None

        if task is None:
            current.current_task_id = None
            current.status = resolve_video_status(current.id)
            if current.status != "error":
                current.error_msg = None
            db.commit()
            video.current_task_id = None
            video.status = current.status
            video.error_msg = current.error_msg
            cleanup_terminal_queue_jobs(video_ids={current.id})
            return None

        should_clear = False
        should_mark_error = False
        if is_terminal_stage(task.stage):
            should_clear = True
        else:
            updated_at = as_aware_utc(task.updated_at) or as_aware_utc(task.created_at) or utcnow()
            should_mark_error = utcnow() - updated_at > stale_after
            should_clear = should_mark_error

        if should_mark_error:
            now = utcnow()
            task.stage = "error"
            task.message = message
            task.updated_at = now
            task.finished_at = now
            current.status = "error"
            current.error_msg = message

        if should_clear:
            if task.stage == "error":
                current.status = "error"
                current.error_msg = task.message or message
            else:
                current.status = resolve_video_status(current.id)
                if current.status != "error":
                    current.error_msg = None
            current.current_task_id = None
            db.commit()
            video.current_task_id = None
            video.status = current.status
            video.error_msg = current.error_msg
            cleanup_terminal_queue_jobs(task_ids={task.id}, video_ids={current.id})
            return None

        progress: dict[str, Any] = {
            "stage": task.stage,
            "done": task.done,
            "total": task.total,
        }
        if task.message:
            progress["msg"] = task.message
        return progress
    finally:
        db.close()
