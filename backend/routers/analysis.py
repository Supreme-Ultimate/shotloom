"""
分析路由：触发分析任务 + SSE 进度推送 + 镜头手动调整
"""
import asyncio
from datetime import timedelta
from redis import Redis
from rq import Queue
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import uuid4

from database import get_db, Video, Shot, VideoAnalysis, User, AnalysisTask
from services.shot_detector import detect_shots
from services.clip_extractor import extract_shot_clips
from services.ai_analyzer import analyze_shot, build_merged_analysis_unit, normalize_model_error
from services.context_analyzer import analyze_chunked_context, analyze_whole_video_context, choose_analysis_strategy
from services.continuity_analyzer import analyze_continuity
from services.video_path import resolve_video_path
from services.credits_service import check_sufficient, deduct
from auth import get_current_user
from config import REDIS_URL, RUN_TASKS_INLINE, SCENE_THRESHOLD, TASK_QUEUE_NAME, TASK_STALE_MINUTES, SAFE_MODEL_VIDEO_DURATION, SHOTS_DIR, SHOT_FALLBACK_ENABLED
from logger import app_logger
from permissions import get_video_for_user
from task_store import cancel_task, create_task, get_task_progress, is_task_cancelled, reconcile_active_task, resolve_video_status, update_task

router = APIRouter(prefix="/api", tags=["analysis"])



class ShotAdjustment(BaseModel):
    shots: List[dict]  # [{start_time, end_time}, ...]


class AnalyzeRequest(BaseModel):
    shot_indices: Optional[List[int]] = None  # None = 全部，否则只分析指定镜头


class ReanalyzeContinuityRequest(BaseModel):
    shot_indices: Optional[List[int]] = None  # None = 使用所有已分析的镜头


class CancelTaskRequest(BaseModel):
    task_id: str


@router.post("/reanalyze-continuity/{video_id}")
async def reanalyze_continuity(
    video_id: int,
    body: ReanalyzeContinuityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重新生成整体分析（不重新分析镜头）"""
    video = get_video_for_user(video_id, current_user, db)

    # 获取所有镜头数据
    shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
    if not shots:
        raise HTTPException(400, "没有镜头数据")

    # 如果指定了 shot_indices，只使用这些镜头
    if body.shot_indices is not None:
        shots = [s for s in shots if s.index in body.shot_indices]
        app_logger.info(f"整体分析选中的镜头: video_id={video_id}, shot_indices={body.shot_indices}")

    # 只使用已分析的镜头
    shots = [s for s in shots if s.analysis]

    if not shots:
        raise HTTPException(400, "没有已分析的镜头数据")

    app_logger.info(f"重新生成整体分析: video_id={video_id}, shot_count={len(shots)}")

    # 准备镜头数据
    shots_data = [
        {"index": s.index, "duration": s.duration, "analysis": s.analysis}
        for s in shots
    ]

    # 生成整体分析
    try:
        report = await analyze_continuity(shots_data)
    except Exception as e:
        app_logger.error(f"整体分析失败: {e}")
        raise HTTPException(500, f"整体分析失败: {normalize_model_error(e)}")

    # 保存结果
    existing = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
    if existing:
        existing.continuity_report = report
    else:
        db.add(VideoAnalysis(video_id=video_id, continuity_report=report))

    db.commit()

    app_logger.info(f"整体分析完成: video_id={video_id}")

    return {"message": "整体分析已更新", "report": report}


@router.post("/detect/{video_id}")
async def detect_shots_endpoint(
    video_id: int,
    threshold: Optional[float] = Query(None, ge=5, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 1: 镜头检测（不调用 AI，只做边界检测）"""
    video = get_video_for_user(video_id, current_user, db)
    effective_threshold = threshold if threshold is not None else SCENE_THRESHOLD

    app_logger.info(f"开始镜头检测: video_id={video_id}, threshold={effective_threshold}")

    video.status = "detecting"
    db.commit()

    try:
        resolved_video_path = resolve_video_path(video.filepath)
        if str(resolved_video_path) != video.filepath:
            app_logger.warning(f"视频路径已迁移: video_id={video_id}, old={video.filepath}, new={resolved_video_path}")
            video.filepath = str(resolved_video_path)
            db.commit()
        shots = detect_shots(str(resolved_video_path), effective_threshold)
        app_logger.info(f"镜头检测完成: video_id={video_id}, shot_count={len(shots)}")
    except Exception as e:
        app_logger.error(f"镜头检测失败: video_id={video_id} | 错误: {e}")
        video.status = "error"
        video.error_msg = normalize_model_error(e)
        db.commit()
        raise HTTPException(500, f"镜头检测失败: {normalize_model_error(e)}")

    # 重新检测会生成新的镜头边界；旧的单镜头分析和整体分析不再适用。
    db.query(Shot).filter(Shot.video_id == video_id).delete()
    db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).delete()

    # 生成缩略图（不生成切片，切片在分析时生成）
    app_logger.info(f"开始生成缩略图: video_id={video_id}, shot_count={len(shots)}")
    from services.clip_extractor import extract_thumbnails_only
    try:
        thumbnails = extract_thumbnails_only(str(resolve_video_path(video.filepath)), shots, video_id)
        app_logger.info(f"缩略图生成完成: video_id={video_id}")
    except Exception as e:
        app_logger.error(f"缩略图生成失败: video_id={video_id} | 错误: {e}")
        thumbnails = [None] * len(shots)

    for s, thumb_path in zip(shots, thumbnails):
        db.add(Shot(
            video_id=video_id,
            index=s.index,
            start_time=s.start_time,
            end_time=s.end_time,
            duration=s.duration,
            thumbnail_path=thumb_path,
        ))

    video.status = "detected"
    video.error_msg = None
    db.commit()

    return {
        "shot_count": len(shots),
        "shots": [
            {"index": s.index, "start_time": s.start_time,
             "end_time": s.end_time, "duration": s.duration}
            for s in shots
        ],
    }


@router.put("/shots/{video_id}/adjust")
def adjust_shots(
    video_id: int,
    body: ShotAdjustment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动调整镜头边界（用户在前端拖动后提交）"""
    video = get_video_for_user(video_id, current_user, db)

    db.query(Shot).filter(Shot.video_id == video_id).delete()
    db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).delete()
    for i, s in enumerate(body.shots):
        start = float(s["start_time"])
        end = float(s["end_time"])
        if end <= start:
            raise HTTPException(400, "镜头结束时间必须大于开始时间")
        db.add(Shot(
            video_id=video_id,
            index=i,
            start_time=start,
            end_time=end,
            duration=round(end - start, 3),
        ))
    video.status = "detected"
    db.commit()
    return {"ok": True, "shot_count": len(body.shots)}


@router.post("/analyze/{video_id}")
async def start_analysis(
    video_id: int,
    body: AnalyzeRequest = AnalyzeRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 2: 启动 AI 分析（异步后台任务）"""
    video = get_video_for_user(video_id, current_user, db)

    shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
    if not shots:
        raise HTTPException(400, "请先进行镜头检测")

    # 筛选要分析的镜头
    if body.shot_indices is not None:
        shots_to_analyze = [s for s in shots if s.index in body.shot_indices]
    else:
        shots_to_analyze = shots

    if not shots_to_analyze:
        raise HTTPException(400, "没有可分析的镜头")

    app_logger.info(f"启动AI分析: video_id={video_id}, shot_count={len(shots_to_analyze)}, user={current_user.email}")

    check_sufficient(current_user.id, len(shots_to_analyze), db)

    task_id = f"task_{uuid4().hex}"
    create_task(task_id, video_id, current_user.id, len(shots_to_analyze), body.shot_indices)
    update_task(task_id, "queued", done=0, total=len(shots_to_analyze))
    app_logger.info(f"[进度初始化] task_id={task_id}, total={len(shots_to_analyze)}")

    video.status = "analyzing"
    video.error_msg = None
    video.current_task_id = task_id  # 保存任务 ID
    db.commit()

    if RUN_TASKS_INLINE:
        asyncio.create_task(_run_analysis(video_id, task_id, current_user.id, body.shot_indices))
    else:
        queue = Queue(TASK_QUEUE_NAME, connection=Redis.from_url(REDIS_URL))
        queue.enqueue("routers.analysis.run_analysis_job", video_id, task_id, current_user.id, body.shot_indices, job_timeout="6h")

    return {"task_id": task_id, "shot_count": len(shots_to_analyze)}


@router.post("/analyze/{video_id}/cancel")
def cancel_analysis(
    video_id: int,
    body: CancelTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """中断当前分析任务，保留已经写入的镜头分析结果。"""
    video = get_video_for_user(video_id, current_user, db)
    if video.current_task_id != body.task_id:
        progress = get_task_progress(body.task_id)
        if not progress:
            raise HTTPException(404, "任务不存在")
    cancel_task(body.task_id, video_id)
    return {"ok": True, "message": "分析已中断，已完成的镜头结果会保留"}


@router.get("/videos/{video_id}/task-status")
def get_task_status(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询视频的任务状态（用于页面刷新后恢复）"""
    video = get_video_for_user(video_id, current_user, db)

    progress = reconcile_active_task(video, timedelta(minutes=TASK_STALE_MINUTES))
    has_active_task = video.current_task_id is not None and progress is not None

    return {
        "has_active_task": has_active_task,
        "task_id": video.current_task_id,
        "video_status": video.status,
        "progress": progress,
    }


@router.get("/progress/{task_id}")
async def progress_stream(task_id: str, token: Optional[str] = Query(None)):
    """SSE 进度流"""
    # EventSource cannot send custom Authorization headers; token validation is
    # handled by adjacent task/video endpoints. Keep task ids unguessable UUIDs.
    _ = token
    app_logger.info(f"[SSE 连接] 客户端连接: task_id={task_id}")

    async def event_generator():
        iteration = 0
        while True:
            iteration += 1
            prog = get_task_progress(task_id)
            if prog is None:
                app_logger.warning(f"[SSE 错误] 任务不存在: task_id={task_id}")
                yield f"data: {json.dumps({'stage': 'not_found'})}\n\n"
                break

            app_logger.info(f"[SSE 发送] 迭代 #{iteration}, task_id={task_id}, stage={prog.get('stage')}, done={prog.get('done')}, total={prog.get('total')}")

            json_data = json.dumps(prog, ensure_ascii=False)

            yield f"data: {json_data}\n\n"

            if prog.get("stage") in ("completed", "error", "cancelled"):
                app_logger.info(f"[SSE 结束] 任务结束: task_id={task_id}, stage={prog.get('stage')}, done={prog.get('done')}, total={prog.get('total')}")
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_analysis(video_id: int, task_id: str, user_id: Optional[int] = None, shot_indices: Optional[List[int]] = None):
    """后台异步分析任务"""
    from database import SessionLocal
    db = SessionLocal()

    def finalize_video_state() -> None:
        """Clear the active task and derive video status from saved shot data."""
        db.expire_all()
        current_video = db.query(Video).populate_existing().filter(Video.id == video_id).first()
        if not current_video:
            return

        current_task = db.query(AnalysisTask).populate_existing().filter(AnalysisTask.id == task_id).first()
        if current_video.current_task_id == task_id:
            current_video.current_task_id = None

        if current_task is None:
            current_video.status = resolve_video_status(video_id)
            if current_video.status != "error":
                current_video.error_msg = None
        elif current_task.stage == "error":
            current_video.status = "error"
            current_video.error_msg = current_video.error_msg or current_task.message or "分析失败"
        elif current_task.stage == "cancelled":
            current_video.status = resolve_video_status(video_id)
            if current_video.status != "error":
                current_video.error_msg = None
        elif current_task.stage == "completed":
            current_video.status = resolve_video_status(video_id)
            if current_video.status != "error":
                current_video.error_msg = None
        else:
            current_video.status = resolve_video_status(video_id)
            if current_video.status != "error":
                current_video.error_msg = None

        db.commit()

    try:
        app_logger.info(f"后台分析任务开始: video_id={video_id}, task_id={task_id}")
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            update_task(task_id, "error", msg="视频不存在")
            return

        shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()

        # 筛选要分析的镜头
        if shot_indices is not None:
            shots_to_analyze = [s for s in shots if s.index in shot_indices]
        else:
            shots_to_analyze = shots

        total = len(shots_to_analyze)
        if total <= 0:
            update_task(task_id, "error", msg="没有可分析的镜头")
            return

        # --- 切割镜头片段（保留原逻辑，便于上下文缺失时回退到单镜头分析）---
        if is_task_cancelled(task_id):
            app_logger.info(f"分析任务已取消，跳过切片: video_id={video_id}, task_id={task_id}")
            return
        update_task(task_id, "cutting_clips", done=0, total=total)
        app_logger.info(f"[进度更新] 开始切割镜头: video_id={video_id}, total={total}, task_id={task_id}")

        from services.shot_detector import ShotBoundary

        shots_to_cut = [s for s in shots_to_analyze if not s.clip_path]
        if shots_to_cut:
            boundaries = [
                ShotBoundary(s.index, s.start_time, s.end_time, s.duration)
                for s in shots_to_cut
            ]
            try:
                source_video_path = str(resolve_video_path(video.filepath))
                if source_video_path != video.filepath:
                    video.filepath = source_video_path
                    db.commit()
                clip_results = extract_shot_clips(source_video_path, boundaries, video_id)
            except Exception as e:
                update_task(task_id, "error", msg=normalize_model_error(e))
                video.status = "error"
                video.error_msg = f"切片失败: {normalize_model_error(e)}"
                db.commit()
                return

            for shot, (clip_path, thumb_path) in zip(shots_to_cut, clip_results):
                shot.clip_path = clip_path
                shot.thumbnail_path = thumb_path
            db.commit()

        if is_task_cancelled(task_id):
            app_logger.info(f"分析任务已取消，跳过 AI 分析: video_id={video_id}, task_id={task_id}")
            return

        source_video_path = str(resolve_video_path(video.filepath))
        if source_video_path != video.filepath:
            video.filepath = source_video_path
            db.commit()
        strategy = choose_analysis_strategy(video.duration, len(shots), len(shots_to_analyze) if shot_indices is not None else None, source_video_path)
        update_task(task_id, "analyzing", done=0, total=total, msg=f"AI 分析中：{strategy.mode}")
        app_logger.info(
            f"[分析路由] video_id={video_id}, mode={strategy.mode}, reason={strategy.reason}, "
            f"shots={len(shots)}, selected={len(shots_to_analyze)}"
        )

        progress_state = {"done": 0}
        progress_lock = asyncio.Lock()
        analyzed_indices: set[int] = set()

        def mark_context_done(count: int, message: str | None = None):
            progress_state["done"] = min(total, progress_state["done"] + count)
            update_task(task_id, "analyzing", done=progress_state["done"], total=total, msg=message)

        async def analyze_one(shot):
            if is_task_cancelled(task_id):
                app_logger.info(f"[分析跳过] 任务已取消，镜头 {shot.index} 不再启动")
                return
            app_logger.info(f"[分析开始] 镜头 {shot.index} 开始回退分析")
            try:
                if not shot.clip_path or not Path(shot.clip_path).exists():
                    raise ValueError("切片失败：未生成可分析的视频片段，请重新检测或调整镜头边界后再分析")
                analysis_unit = None
                if shot.duration < SAFE_MODEL_VIDEO_DURATION:
                    analysis_unit = build_merged_analysis_unit(shots, shot.index)
                    app_logger.info(
                        f"[短镜头合并] 镜头 {shot.index} 时长 {shot.duration:.2f}s，"
                        f"使用镜头 {analysis_unit['analysis_shot_indices']} 合并分析，"
                        f"范围 {analysis_unit['merged_start_time']:.2f}s-{analysis_unit['merged_end_time']:.2f}s"
                    )
                result = await analyze_shot(
                    clip_path=shot.clip_path,
                    shot_index=shot.index,
                    total_shots=total,
                    duration=shot.duration,
                    video_path=source_video_path,
                    start_time=shot.start_time,
                    end_time=shot.end_time,
                    analysis_unit=analysis_unit,
                )
                result.setdefault("analysis_source", result.get("analysis_mode") or "shot_clip")
                result.setdefault("analysis_mode", result.get("analysis_mode") or "shot_clip")
                shot.analysis = result
                app_logger.info(f"[分析成功] 镜头 {shot.index} 回退分析成功")
            except Exception as e:
                safe_error = normalize_model_error(e)
                shot.analysis = {"error": safe_error, "analysis_source": "shot_clip", "analysis_mode": "shot_clip"}
                app_logger.error(f"[分析失败] 镜头 {shot.index} 分析失败: {e}")

            try:
                db.commit()
                app_logger.info(f"[数据库提交] 镜头 {shot.index} 数据已保存")
            except Exception as e:
                app_logger.error(f"[数据库错误] 镜头 {shot.index} 提交失败: {e}")

            async with progress_lock:
                if is_task_cancelled(task_id):
                    return
                progress_state["done"] += 1
                current_done = progress_state["done"]
                update_task(task_id, "analyzing", done=current_done, total=total)
                app_logger.info(f"[进度更新] 镜头 {shot.index} 完成，进度: {current_done}/{total}, task_id={task_id}")

        async def run_fallback_for(missing_shots):
            if not missing_shots:
                return
            if not SHOT_FALLBACK_ENABLED:
                for shot in missing_shots:
                    shot.analysis = {"error": "上下文分析未返回该镜头结果，且单镜头回退已关闭", "analysis_source": strategy.mode, "analysis_mode": strategy.mode}
                db.commit()
                mark_context_done(len(missing_shots), "部分镜头未返回，已记录错误")
                return
            app_logger.info(f"[回退分析] {len(missing_shots)} 个镜头缺少上下文结果，使用单镜头/合并上下文回退")
            await asyncio.gather(*[analyze_one(s) for s in missing_shots])

        def _all_video_shots_analyzed() -> list[Shot]:
            all_shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
            if not all_shots:
                return []
            for shot in all_shots:
                if not shot.analysis or (isinstance(shot.analysis, dict) and shot.analysis.get("error")):
                    return []
            return all_shots

        async def maybe_generate_auto_continuity():
            all_analyzed_shots = _all_video_shots_analyzed()
            if not all_analyzed_shots:
                app_logger.info(f"[整体分析] 跳过自动生成：仍有未分析或错误镜头 video_id={video_id}")
                return

            update_task(task_id, "continuity", done=0, total=1, msg="生成整体分析…")
            shots_data = [
                {"index": s.index, "duration": s.duration, "analysis": s.analysis}
                for s in all_analyzed_shots
            ]
            try:
                report = await analyze_continuity(shots_data)
            except Exception as e:
                app_logger.error(f"[整体分析] 自动生成失败: video_id={video_id} | 错误: {e}", exc_info=True)
                existing = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
                if not existing:
                    existing = VideoAnalysis(video_id=video_id)
                    db.add(existing)
                existing.continuity_report = {"error": f"整体分析失败: {normalize_model_error(e)}"}
                db.commit()
                return

            existing = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
            if not existing:
                existing = VideoAnalysis(video_id=video_id)
                db.add(existing)
            existing.continuity_report = report
            db.commit()
            update_task(task_id, "continuity", done=1, total=1, msg="整体分析完成")
            app_logger.info(f"[整体分析] 自动生成完成: video_id={video_id}, shot_count={len(all_analyzed_shots)}")

        def apply_context_result(result: dict, source_mode: str) -> int:
            written = 0
            shot_results = result.get("shots") or {}
            for shot in shots_to_analyze:
                if shot.index in analyzed_indices:
                    continue
                analysis = shot_results.get(shot.index)
                if not analysis:
                    continue
                analysis.setdefault("analysis_source", source_mode)
                analysis.setdefault("analysis_mode", "whole_video_context" if source_mode == "whole_video" else "chunk_segment_context")
                shot.analysis = analysis
                analyzed_indices.add(shot.index)
                written += 1
            db.commit()
            return written

        async def on_chunk_complete(chunk_result: dict, _chunk: list, chunk_index: int, total_chunks: int):
            written = apply_context_result(chunk_result, "chunk_segment")
            update_task(
                task_id,
                "analyzing",
                done=chunk_index + 1,
                total=total_chunks,
                msg=f"分块上下文分析 {chunk_index + 1}/{total_chunks}：已写入 {written} 个镜头",
            )

        if strategy.mode in ("whole_video", "chunk_segment"):
            context_failed = False
            context_result = {"shots": {}, "segments": []}
            try:
                if strategy.mode == "whole_video":
                    update_task(task_id, "analyzing", done=0, total=1, msg="整片上下文分析中")
                    context_result = await analyze_whole_video_context(source_video_path, shots_to_analyze, video_id=video.id)
                else:
                    context_result = await analyze_chunked_context(
                        source_video_path,
                        shots_to_analyze,
                        SHOTS_DIR,
                        video_id=video.id,
                        on_chunk_complete=on_chunk_complete,
                    )
            except Exception as e:
                context_failed = True
                app_logger.error(f"[上下文分析失败] video_id={video_id}, mode={strategy.mode}, error={e}", exc_info=True)

            if not context_failed:
                if strategy.mode == "whole_video":
                    written = apply_context_result(context_result, strategy.mode)
                    update_task(task_id, "analyzing", done=1, total=1, msg=f"整片上下文分析完成：已写入 {written} 个镜头")

                existing = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
                if not existing:
                    existing = VideoAnalysis(video_id=video_id)
                    db.add(existing)
                existing.segments_report = {
                    "strategy": strategy.mode,
                    "reason": strategy.reason,
                    "shot_count": len(shots_to_analyze),
                    "segments": context_result.get("segments") or [],
                }
                db.commit()


            if is_task_cancelled(task_id):
                app_logger.info(f"分析任务已取消，保留已完成结果: video_id={video_id}, task_id={task_id}")
                return

            missing_shots = [s for s in shots_to_analyze if s.index not in analyzed_indices]
            if context_failed:
                missing_shots = shots_to_analyze
            await run_fallback_for(missing_shots)
        else:
            app_logger.info(f"[并发执行] 开始单镜头/短镜头合并分析 {len(shots_to_analyze)} 个镜头")
            await asyncio.gather(*[analyze_one(s) for s in shots_to_analyze])
            app_logger.info(f"[并发完成] 所有镜头分析完成，最终进度: {progress_state['done']}/{total}")

        if is_task_cancelled(task_id):
            app_logger.info(f"分析任务已取消，保留已完成结果: video_id={video_id}, task_id={task_id}")
            return

        await maybe_generate_auto_continuity()

        if user_id:
            try:
                deduct(user_id, total, video_id, db)
                app_logger.info(f"积分扣除成功: user_id={user_id}, amount={total}, video_id={video_id}")
            except Exception as e:
                app_logger.error(f"积分扣除失败: user_id={user_id} | 错误: {e}")

        db.commit()
        app_logger.info(f"所有数据库操作已完成: video_id={video_id}")

        update_task(task_id, "completed", done=total, total=total)
        app_logger.info(f"[进度更新] 分析任务完成: video_id={video_id}, task_id={task_id}")

    except Exception as e:
        app_logger.error(f"分析任务失败: video_id={video_id}, task_id={task_id} | 错误: {e}", exc_info=True)
        safe_error = normalize_model_error(e)
        update_task(task_id, "error", msg=safe_error)
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = "error"
            video.error_msg = safe_error
            video.current_task_id = None
            db.commit()
    finally:
        try:
            finalize_video_state()
        except Exception as finalize_error:
            app_logger.error(f"视频状态收尾失败: video_id={video_id}, task_id={task_id} | 错误: {finalize_error}", exc_info=True)
        db.close()


def run_analysis_job(video_id: int, task_id: str, user_id: int, shot_indices: Optional[List[int]] = None):
    asyncio.run(_run_analysis(video_id, task_id, user_id, shot_indices))
