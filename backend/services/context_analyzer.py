"""Context-aware analysis router for whole-video and chunked segment passes."""
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import (
    ANALYSIS_ROUTER_MODE,
    WHOLE_VIDEO_MAX_DURATION,
    WHOLE_VIDEO_MAX_SHOTS,
    CHUNK_SEGMENT_DURATION,
    CHUNK_SEGMENT_MAX_SHOTS,
    CHUNK_SEGMENT_OVERLAP_SHOTS,
    CONTEXT_BASE64_MAX_MB,
)
from logger import app_logger
from services.ai_analyzer import _call_model_with_retries, _extract_extended_clip, _extract_json


@dataclass
class AnalysisStrategy:
    mode: str
    reason: str


def choose_analysis_strategy(video_duration: float | None, shot_count: int, selected_count: int | None = None, video_path: str | None = None) -> AnalysisStrategy:
    """Choose the primary source for shot-level analysis."""
    if ANALYSIS_ROUTER_MODE != "auto":
        return AnalysisStrategy(ANALYSIS_ROUTER_MODE, f"forced by ANALYSIS_ROUTER_MODE={ANALYSIS_ROUTER_MODE}")
    if selected_count is not None and selected_count < shot_count:
        return AnalysisStrategy("shot_fallback", "selected-shot reanalysis uses local fallback")
    duration = float(video_duration or 0)
    if video_path:
        size_mb = Path(video_path).stat().st_size / 1024 / 1024 if Path(video_path).exists() else 0
        if size_mb > CONTEXT_BASE64_MAX_MB:
            return AnalysisStrategy("chunk_segment", f"video file {size_mb:.1f}MB exceeds base64 whole-video limit")
    if duration <= WHOLE_VIDEO_MAX_DURATION and shot_count <= WHOLE_VIDEO_MAX_SHOTS:
        return AnalysisStrategy("whole_video", "video within whole-video context limits")
    return AnalysisStrategy("chunk_segment", "video exceeds whole-video context limits")


def _shot_boundaries_text(shots: list) -> str:
    lines = []
    for shot in shots:
        lines.append(
            f"#{shot.index}: {shot.start_time:.3f}s - {shot.end_time:.3f}s "
            f"(display #{shot.index + 1}, duration {shot.duration:.3f}s)"
        )
    return "\n".join(lines)


def _context_prompt(shots: list, mode: str, start_time: float = 0.0) -> str:
    boundaries = _shot_boundaries_text(shots)
    return f"""
你是专业影视拉片分析师。请观看当前视频，并严格按照我提供的镜头边界输出结构化 JSON。

重要规则：
1. 镜头边界是唯一可信边界，不要新增、删除、拆分或重编号镜头；shot_index 和 shot_indices 必须使用边界列表中 # 后面的零基索引。
2. 如果某个镜头很短，请结合前后上下文判断它的内容和作用，但仍必须为该镜头单独输出结果。
3. 请识别对白连续、动作连续、反应链、情绪节拍和叙事段落。
4. 只输出 JSON，不要输出 Markdown。

当前分析模式：{mode}
当前片段在原视频中的起点：{start_time:.3f}s
镜头边界：
{boundaries}

请输出如下 JSON：
{{
  "shots": [
    {{
      "shot_index": 0,
      "shot_scale": "景别",
      "camera_movement": "运镜",
      "composition": "构图",
      "lighting": "光影",
      "color_tone": "色调",
      "content_description": "画面内容、人物动作和表情",
      "on_screen_text": "画面文字，没有则写无",
      "dialogue": "该镜头内可听见的对白/旁白，没有则写无",
      "audio": {{
        "dialogue": "音轨台词",
        "sound_type": "对白/音乐/环境声/音效/无",
        "music": "音乐描述",
        "ambient_sound": "环境声描述",
        "speaker_emotion": "人声情绪"
      }},
      "audiovisual_sync": "声画关系",
      "audio_narrative_role": "声音叙事作用",
      "audio_continuity": {{
        "continues_from_previous": false,
        "continues_to_next": false,
        "unfinished_dialogue": false,
        "notes": "跨镜头音频说明"
      }},
      "action_continuity": {{
        "continues_from_previous": false,
        "continues_to_next": false,
        "notes": "跨镜头动作说明"
      }},
      "what": "这个镜头拍了什么",
      "how": "它如何通过视听语言实现",
      "why": "为什么这样拍",
      "narrative_level": {{"scene": "场景", "event": "事件", "information": "信息"}},
      "emotional_function": "情绪功能",
      "narrative_decision": "叙事决策",
      "rhythm_contribution": "节奏贡献"
    }}
  ],
  "segments": [
    {{
      "segment_index": 0,
      "shot_indices": [0, 1],
      "segment_type": "dialogue_continuity/action_continuity/reaction_chain/montage/emotional_beat/information_reveal/transition/single_shot",
      "title": "段落标题",
      "summary": "段落摘要",
      "merge_reason": "为什么这些镜头属于同一段落",
      "audio_continuity": "对白/音乐/环境声连续性",
      "action_continuity": "动作连续性",
      "editing_logic": "剪辑逻辑",
      "emotional_arc": "情绪推进",
      "narrative_function": "叙事功能"
    }}
  ]
}}
""".strip()


def _normalize_shot_result(raw: dict[str, Any], source: str, chunk_index: int | None = None) -> tuple[int | None, dict[str, Any]]:
    idx = raw.get("shot_index")
    if idx is None:
        idx = raw.get("index")
    try:
        idx = int(idx)
    except Exception:
        return None, {}
    analysis = dict(raw)
    analysis.pop("shot_index", None)
    analysis.pop("index", None)
    analysis.setdefault("analysis_source", source)
    analysis.setdefault("analysis_mode", "whole_video_context" if source == "whole_video" else "chunk_segment_context")
    if chunk_index is not None:
        analysis.setdefault("chunk_index", chunk_index)
    return idx, analysis


def _normalize_segment(raw: dict[str, Any], source: str, chunk_index: int | None = None) -> dict[str, Any] | None:
    indices = raw.get("shot_indices") or []
    try:
        normalized = [int(i) for i in indices]
    except Exception:
        normalized = []
    if not normalized:
        return None
    segment = dict(raw)
    segment["shot_indices"] = normalized
    segment.setdefault("analysis_source", source)
    if chunk_index is not None:
        segment.setdefault("chunk_index", chunk_index)
    return segment


def _call_context_model(video_path: str, shots: list, source: str, start_time: float = 0.0, chunk_index: int | None = None) -> dict[str, Any]:
    prompt = _context_prompt(shots, source, start_time)
    raw = _call_model_with_retries(video_path, prompt)
    if isinstance(raw, str):
        raw = _extract_json(raw)
    shot_map: dict[int, dict[str, Any]] = {}
    for item in raw.get("shots", []):
        idx, analysis = _normalize_shot_result(item, source, chunk_index)
        if idx is not None and analysis:
            shot_map[idx] = analysis
    segments = []
    for item in raw.get("segments", []):
        segment = _normalize_segment(item, source, chunk_index)
        if segment:
            segments.append(segment)
    return {"shots": shot_map, "segments": segments, "raw": raw}


async def analyze_whole_video_context(video_path: str, shots: list) -> dict[str, Any]:
    app_logger.info(f"[上下文分析] 使用整片分析: shots={len(shots)}")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _call_context_model(video_path, shots, "whole_video"))


def build_shot_chunks(shots: list, max_duration: float = CHUNK_SEGMENT_DURATION, max_shots: int = CHUNK_SEGMENT_MAX_SHOTS, overlap_shots: int = CHUNK_SEGMENT_OVERLAP_SHOTS) -> list[list]:
    if not shots:
        return []
    ordered = sorted(shots, key=lambda s: s.index)
    chunks = []
    start = 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered):
            candidate = ordered[start:end + 2]
            duration = candidate[-1].end_time - candidate[0].start_time
            if len(candidate) > max_shots or duration > max_duration:
                break
            end += 1
        chunks.append(ordered[start:end + 1])
        if end >= len(ordered) - 1:
            break
        start = max(end + 1 - overlap_shots, start + 1)
    return chunks


async def analyze_chunked_context(video_path: str, shots: list, temp_dir: str | Path) -> dict[str, Any]:
    chunks = build_shot_chunks(shots)
    app_logger.info(f"[上下文分析] 使用分块段落分析: chunks={len(chunks)}, shots={len(shots)}")
    merged_shots: dict[int, dict[str, Any]] = {}
    merged_segments: list[dict[str, Any]] = []
    temp_dir = Path(temp_dir)
    loop = asyncio.get_event_loop()

    for chunk_index, chunk in enumerate(chunks):
        start = chunk[0].start_time
        end = chunk[-1].end_time
        chunk_path = temp_dir / f"context_chunk_{chunk_index}_{chunk[0].index}_{chunk[-1].index}.mp4"
        try:
            _extract_extended_clip(video_path, str(chunk_path), start, end)
            result = await loop.run_in_executor(
                None,
                lambda: _call_context_model(str(chunk_path), chunk, "chunk_segment", start, chunk_index),
            )
            merged_shots.update(result["shots"])
            merged_segments.extend(result["segments"])
        finally:
            chunk_path.unlink(missing_ok=True)

    return {"shots": merged_shots, "segments": _dedupe_segments(merged_segments)}


def _dedupe_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for segment in segments:
        key = tuple(segment.get("shot_indices", []))
        if not key or key in seen:
            continue
        seen.add(key)
        segment["segment_index"] = len(deduped)
        deduped.append(segment)
    return deduped
