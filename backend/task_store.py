"""Persistent analysis task state backed by the application database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import database
from database import AnalysisTask, Video


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


def is_progress_complete(task: AnalysisTask) -> bool:
    return task.total > 0 and task.done >= task.total


def create_task(task_id: str, video_id: int, user_id: int, total: int, shot_indices: list[int] | None) -> None:
    db = database.SessionLocal()
    try:
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
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            return False
        if is_terminal_stage(task.stage):
            return True

        now = utcnow()
        task.stage = "cancelled"
        task.message = message
        task.updated_at = now
        task.finished_at = now

        resolved_video_id = video_id if video_id is not None else task.video_id
        video = db.query(Video).filter(Video.id == resolved_video_id).first()
        if video and video.current_task_id == task_id:
            video.current_task_id = None
            video.status = "completed" if task.done > 0 else "detected"
            video.error_msg = None
        db.commit()
        return True
    finally:
        db.close()


def mark_task_and_video_error(
    task_id: str,
    message: str = STALE_TASK_MESSAGE,
    video_id: int | None = None,
) -> None:
    """Mark a task failed and clear its active pointer on the owning video."""
    db = database.SessionLocal()
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
    finally:
        db.close()


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
            db.commit()
            video.current_task_id = None
            return None

        should_clear = False
        should_mark_error = False
        if is_terminal_stage(task.stage) or is_progress_complete(task):
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
            current.current_task_id = None
            db.commit()
            video.current_task_id = None
            video.status = current.status
            video.error_msg = current.error_msg
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
