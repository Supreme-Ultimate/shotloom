"""
分析路由：触发分析任务 + SSE 进度推送 + 镜头手动调整
"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db, Video, Shot, VideoAnalysis, User
from services.shot_detector import detect_shots
from services.clip_extractor import extract_shot_clips
from services.ai_analyzer import analyze_shot
from services.continuity_analyzer import analyze_continuity
from services.credits_service import check_sufficient, deduct
from auth import get_current_user_optional
from config import SCENE_THRESHOLD
from logger import app_logger

router = APIRouter(prefix="/api", tags=["analysis"])

# 全局任务进度存储（简单实现，生产环境建议用 Redis）
_task_progress: dict = {}


class ShotAdjustment(BaseModel):
    shots: List[dict]  # [{start_time, end_time}, ...]


class AnalyzeRequest(BaseModel):
    shot_indices: Optional[List[int]] = None  # None = 全部，否则只分析指定镜头


class ReanalyzeContinuityRequest(BaseModel):
    shot_indices: Optional[List[int]] = None  # None = 使用所有已分析的镜头


@router.post("/reanalyze-continuity/{video_id}")
async def reanalyze_continuity(
    video_id: int,
    body: ReanalyzeContinuityRequest,
    db: Session = Depends(get_db),
):
    """重新生成整体分析（不重新分析镜头）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

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
        raise HTTPException(500, f"整体分析失败: {str(e)}")

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
    threshold: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """Step 1: 镜头检测（不调用 AI，只做边界检测）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

    app_logger.info(f"开始镜头检测: video_id={video_id}, threshold={threshold or SCENE_THRESHOLD}")

    video.status = "detecting"
    db.commit()

    try:
        shots = detect_shots(video.filepath, threshold or SCENE_THRESHOLD)
        app_logger.info(f"镜头检测完成: video_id={video_id}, shot_count={len(shots)}")
    except Exception as e:
        app_logger.error(f"镜头检测失败: video_id={video_id} | 错误: {e}")
        video.status = "error"
        video.error_msg = str(e)
        db.commit()
        raise HTTPException(500, f"镜头检测失败: {e}")

    # 删除旧镜头记录
    db.query(Shot).filter(Shot.video_id == video_id).delete()

    # 生成缩略图（不生成切片，切片在分析时生成）
    app_logger.info(f"开始生成缩略图: video_id={video_id}, shot_count={len(shots)}")
    from services.clip_extractor import extract_thumbnails_only
    try:
        thumbnails = extract_thumbnails_only(video.filepath, shots, video_id)
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
def adjust_shots(video_id: int, body: ShotAdjustment, db: Session = Depends(get_db)):
    """手动调整镜头边界（用户在前端拖动后提交）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

    db.query(Shot).filter(Shot.video_id == video_id).delete()
    for i, s in enumerate(body.shots):
        start = float(s["start_time"])
        end = float(s["end_time"])
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
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Step 2: 启动 AI 分析（异步后台任务）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

    shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
    if not shots:
        raise HTTPException(400, "请先进行镜头检测")

    # 允许重新分析
    if video.status in ("error", "completed"):
        video.status = "analyzing"
        db.commit()

    # 筛选要分析的镜头
    if body.shot_indices is not None:
        shots_to_analyze = [s for s in shots if s.index in body.shot_indices]
    else:
        shots_to_analyze = shots

    app_logger.info(f"启动AI分析: video_id={video_id}, shot_count={len(shots_to_analyze)}, user={current_user.email if current_user else 'anonymous'}")

    # 积分检查（仅对已登录用户）
    if current_user:
        check_sufficient(current_user.id, len(shots_to_analyze), db)

    task_id = f"task_{video_id}"
    _task_progress[task_id] = {"stage": "starting", "done": 0, "total": len(shots_to_analyze)}
    app_logger.info(f"[进度初始化] task_id={task_id}, initial_progress={_task_progress[task_id]}")

    video.status = "analyzing"
    video.current_task_id = task_id  # 保存任务 ID
    db.commit()

    user_id = current_user.id if current_user else None
    asyncio.create_task(_run_analysis(video_id, task_id, user_id, body.shot_indices))

    return {"task_id": task_id, "shot_count": len(shots_to_analyze)}


@router.get("/videos/{video_id}/task-status")
def get_task_status(video_id: int, db: Session = Depends(get_db)):
    """查询视频的任务状态（用于页面刷新后恢复）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "视频不存在")

    has_active_task = video.current_task_id is not None

    return {
        "has_active_task": has_active_task,
        "task_id": video.current_task_id,
        "video_status": video.status,
    }


@router.get("/progress/{task_id}")
async def progress_stream(task_id: str):
    """SSE 进度流"""
    app_logger.info(f"[SSE 连接] 客户端连接: task_id={task_id}, 当前所有任务: {list(_task_progress.keys())}")

    async def event_generator():
        iteration = 0
        while True:
            iteration += 1
            prog = _task_progress.get(task_id)
            if prog is None:
                app_logger.warning(f"[SSE 错误] 任务不存在: task_id={task_id}, 当前任务列表: {list(_task_progress.keys())}")
                yield f"data: {json.dumps({'stage': 'not_found'})}\n\n"
                break

            # 详细记录发送的数据
            app_logger.info(f"[SSE 发送] 迭代 #{iteration}, task_id={task_id}, stage={prog.get('stage')}, done={prog.get('done')}, total={prog.get('total')}, 完整数据={prog}")

            json_data = json.dumps(prog, ensure_ascii=False)
            app_logger.info(f"[SSE JSON] 序列化后的数据: {json_data}")

            yield f"data: {json_data}\n\n"

            if prog.get("stage") in ("completed", "error"):
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
    try:
        app_logger.info(f"后台分析任务开始: video_id={video_id}, task_id={task_id}")
        video = db.query(Video).filter(Video.id == video_id).first()
        shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()

        # 筛选要分析的镜头
        if shot_indices is not None:
            shots_to_analyze = [s for s in shots if s.index in shot_indices]
        else:
            shots_to_analyze = shots

        total = len(shots_to_analyze)

        # --- 切割镜头片段（仅切割需要分析的镜头）---
        _task_progress[task_id] = {"stage": "cutting_clips", "done": 0, "total": total}
        app_logger.info(f"[进度更新] 开始切割镜头: video_id={video_id}, total={total}, task_id={task_id}, progress={_task_progress[task_id]}")

        from services.shot_detector import ShotBoundary

        # 只切割需要分析的镜头（如果还没有 clip_path）
        shots_to_cut = [s for s in shots_to_analyze if not s.clip_path]
        if shots_to_cut:
            boundaries = [
                ShotBoundary(s.index, s.start_time, s.end_time, s.duration)
                for s in shots_to_cut
            ]
            try:
                clip_results = extract_shot_clips(video.filepath, boundaries, video_id)
            except Exception as e:
                _task_progress[task_id] = {"stage": "error", "msg": str(e)}
                video.status = "error"
                video.error_msg = f"切片失败: {e}"
                db.commit()
                return

            for shot, (clip_path, thumb_path) in zip(shots_to_cut, clip_results):
                shot.clip_path = clip_path
                shot.thumbnail_path = thumb_path
            db.commit()

        # --- 逐镜 AI 分析 ---
        _task_progress[task_id] = {"stage": "analyzing", "done": 0, "total": total}
        app_logger.info(f"[进度更新] 开始 AI 分析: video_id={video_id}, total={total}, task_id={task_id}, progress={_task_progress[task_id]}")

        # 使用字典而不是简单变量，避免 nonlocal 的问题
        progress_state = {"done": 0}
        progress_lock = asyncio.Lock()

        async def analyze_one(shot):
            app_logger.info(f"[分析开始] 镜头 {shot.index} 开始分析")
            try:
                result = await analyze_shot(
                    clip_path=shot.clip_path,
                    shot_index=shot.index,
                    total_shots=total,
                    duration=shot.duration,
                    video_path=video.filepath,
                    start_time=shot.start_time,
                    end_time=shot.end_time,
                )
                shot.analysis = result
                app_logger.info(f"[分析成功] 镜头 {shot.index} 分析成功")
            except Exception as e:
                shot.analysis = {"error": str(e)}
                app_logger.error(f"[分析失败] 镜头 {shot.index} 分析失败: {e}")

            # 先提交数据库
            try:
                db.commit()
                app_logger.info(f"[数据库提交] 镜头 {shot.index} 数据已保存")
            except Exception as e:
                app_logger.error(f"[数据库错误] 镜头 {shot.index} 提交失败: {e}")

            # 更新进度（使用字典确保正确更新）
            async with progress_lock:
                progress_state["done"] += 1
                current_done = progress_state["done"]
                _task_progress[task_id] = {"stage": "analyzing", "done": current_done, "total": total}
                app_logger.info(f"[进度更新] 镜头 {shot.index} 完成，进度: {current_done}/{total}, task_id={task_id}, _task_progress={_task_progress[task_id]}")

        # 并发执行（Semaphore 在 ai_analyzer 内控制）
        app_logger.info(f"[并发执行] 开始并发分析 {len(shots_to_analyze)} 个镜头")
        await asyncio.gather(*[analyze_one(s) for s in shots_to_analyze])
        app_logger.info(f"[并发完成] 所有镜头分析完成，最终进度: {progress_state['done']}/{total}")

        # 镜头分析完成，不自动执行整体分析
        video.status = "completed"
        video.current_task_id = None
        db.commit()  # 先提交视频状态
        app_logger.info(f"视频状态已更新为 completed: video_id={video_id}")

        # 按实际镜头数扣除积分
        if user_id:
            try:
                deduct(user_id, total, video_id, db)
                app_logger.info(f"积分扣除成功: user_id={user_id}, amount={total}, video_id={video_id}")
            except Exception as e:
                app_logger.error(f"积分扣除失败: user_id={user_id} | 错误: {e}")

        # 确保所有数据库操作完成后再发送完成消息
        db.commit()  # 再次提交，确保积分扣除也已保存
        app_logger.info(f"所有数据库操作已完成: video_id={video_id}")

        # 最后发送 SSE 完成消息
        _task_progress[task_id] = {"stage": "completed", "done": total, "total": total}
        app_logger.info(f"[进度更新] 分析任务完成: video_id={video_id}, task_id={task_id}, final_progress={_task_progress[task_id]}")

    except Exception as e:
        app_logger.error(f"分析任务失败: video_id={video_id}, task_id={task_id} | 错误: {e}")
        _task_progress[task_id] = {"stage": "error", "msg": str(e)}
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = "error"
            video.error_msg = str(e)
            video.current_task_id = None  # 清除任务 ID
            db.commit()
    finally:
        db.close()
