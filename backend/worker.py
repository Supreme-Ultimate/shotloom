"""RQ worker entrypoint for video analysis jobs."""
from __future__ import annotations

import logging

from redis import Redis
from rq.job import Job
from rq import Worker

from config import REDIS_URL, TASK_QUEUE_NAME
from task_store import mark_task_and_video_error


logger = logging.getLogger(__name__)


def _job_context(job: Job) -> tuple[int | None, str | None]:
    args = list(job.args or [])
    if len(args) < 2:
        return None, None
    try:
        video_id = int(args[0])
    except (TypeError, ValueError):
        video_id = None
    task_id = str(args[1]) if args[1] else None
    return video_id, task_id


def _mark_job_failed(job: Job, message: str) -> None:
    video_id, task_id = _job_context(job)
    if not task_id:
        logger.warning("Failed analysis job has no task id: job_id=%s", job.id)
        return
    mark_task_and_video_error(task_id, message=message, video_id=video_id)


def handle_job_exception(job: Job, exc_type, exc_value, traceback) -> bool:
    message = f"分析任务异常中断: {exc_value or exc_type.__name__}"
    _mark_job_failed(job, message)
    return True


def handle_work_horse_killed(job: Job, retpid: int, ret_val: int, rusage) -> None:
    # Native crashes (for example FFmpeg/PyAV SIGFPE) bypass job-level try/except.
    message = f"分析任务异常中断，请重新分析或重新检测镜头（worker exited: {ret_val}）"
    _mark_job_failed(job, message)


def main() -> None:
    redis = Redis.from_url(REDIS_URL)
    worker = Worker(
        [TASK_QUEUE_NAME],
        connection=redis,
        exception_handlers=[handle_job_exception],
        work_horse_killed_handler=handle_work_horse_killed,
    )
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
