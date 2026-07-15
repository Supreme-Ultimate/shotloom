"""Context-aware analysis router for whole-video and chunked segment passes."""
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config as app_config
from config import (
    ANALYSIS_ROUTER_MODE,
    WHOLE_VIDEO_MAX_DURATION,
    WHOLE_VIDEO_MAX_SHOTS,
    CHUNK_SEGMENT_DURATION,
    CHUNK_SEGMENT_MAX_SHOTS,
    CHUNK_SEGMENT_OVERLAP_SHOTS,
    CONTEXT_BASE64_MAX_MB,
    SELECTED_CONTEXT_MIN_SHOTS,
)
from logger import app_logger
from services.ai_analyzer import _call_model_with_retries, _extract_extended_clip, _extract_json
from prompt_config import get_scope_fields
from services.asr_analyzer import inject_asr_fields, transcript_for_range, transcript_prompt


@dataclass
class AnalysisStrategy:
    mode: str
    reason: str


def choose_analysis_strategy(video_duration: float | None, shot_count: int, selected_count: int | None = None, video_path: str | None = None) -> AnalysisStrategy:
    """Choose the primary source for shot-level analysis."""
    if app_config.ANALYSIS_ROUTER_MODE != "auto":
        return AnalysisStrategy(app_config.ANALYSIS_ROUTER_MODE, f"forced by ANALYSIS_ROUTER_MODE={app_config.ANALYSIS_ROUTER_MODE}")
    duration = float(video_duration or 0)
    if selected_count is not None and selected_count < shot_count:
        if selected_count >= SELECTED_CONTEXT_MIN_SHOTS:
            return AnalysisStrategy("chunk_segment", f"selected batch has {selected_count} shots; using chunk context")
        return AnalysisStrategy("shot_fallback", "small selected-shot reanalysis uses local fallback")
    if video_path:
        size_mb = Path(video_path).stat().st_size / 1024 / 1024 if Path(video_path).exists() else 0
        can_use_public_url = app_config.QWEN_VIDEO_INPUT_MODE != "base64" and bool(app_config.PUBLIC_VIDEO_BASE_URL)
        if size_mb > app_config.CONTEXT_BASE64_MAX_MB and not can_use_public_url:
            return AnalysisStrategy("chunk_segment", f"video file {size_mb:.1f}MB exceeds base64 whole-video limit")
    if duration <= app_config.WHOLE_VIDEO_MAX_DURATION and shot_count <= app_config.WHOLE_VIDEO_MAX_SHOTS:
        return AnalysisStrategy("whole_video", "video within whole-video context limits")
    return AnalysisStrategy("chunk_segment", "video exceeds whole-video context limits")


def _shot_boundaries_text(shots: list, start_time: float = 0.0) -> str:
    lines = []
    for shot in shots:
        relative_start = max(0.0, float(shot.start_time) - start_time)
        relative_end = max(relative_start, float(shot.end_time) - start_time)
        lines.append(
            f"#{shot.index}: {relative_start:.3f}s - {relative_end:.3f}s "
            f"(display #{shot.index + 1}, duration {shot.duration:.3f}s, "
            f"原视频时间 {shot.start_time:.3f}s - {shot.end_time:.3f}s)"
        )
    return "\n".join(lines)


def _context_prompt(shots: list, mode: str, start_time: float = 0.0) -> str:
    boundaries = _shot_boundaries_text(shots, start_time=start_time)
    return f"""
你是专业影视拉片分析师。请观看当前视频，并严格按照我提供的镜头边界输出结构化 JSON。

重要规则：
1. 镜头边界是唯一可信边界，不要新增、删除、拆分或重编号镜头；shot_index 和 shot_indices 必须使用边界列表中 # 后面的零基索引。
2. 边界时间是当前输入视频片段内的相对时间；括号中的原视频时间只用于理解上下文，不能用来定位当前输入片段。
3. 按 Qwen3.7 视觉理解方式通看当前输入片段：只分析 storyline、visible text 和可见动作，再把观察结果映射回下方镜头边界；不得声称听见音轨。
4. 必须先输出 global_transcript：把整段视频内所有对白/旁白/歌词按真实出现时间切到最小可听短句/短语，列出 start_time、end_time、speaker、content。
5. 如果一句话跨越镜头边界，必须在 global_transcript 中按镜头边界附近的真实语音时间拆成多条短语级记录；不要输出一条横跨多个镜头的粗时间戳。
6. 每个镜头的描述必须对应它在当前输入片段中的相对时间范围；不要把前一个/后一个镜头的画面、台词或动作挪到本镜头，尤其不要把整段视频的所有台词放进第一个镜头。
7. 每个镜头 audio.dialogue 只能包含与该镜头时间范围重叠的台词；如果 global_transcript 中某句时间戳落在其他镜头，必须写到对应镜头而不是当前镜头。
8. 如果对白、旁白、歌词、动作或音效跨越镜头边界，请在相邻镜头中分别说明可听见/可看见的部分，并用 audio_continuity/action_continuity 标记连续关系。
9. 如果某个镜头很短，请结合前后上下文判断它的内容和作用，但仍必须为该镜头单独输出结果。
10. 请识别对白连续、动作连续、反应链、情绪节拍和叙事段落。
11. 只输出 JSON，不要输出 Markdown。

当前分析模式：{mode}
当前片段在原视频中的起点：{start_time:.3f}s
镜头边界：
{boundaries}

请输出如下 JSON：
{{
  "global_transcript": [
    {{
      "start_time": "台词/旁白/歌词在当前输入片段内的开始时间，例如 3.708s",
      "end_time": "台词/旁白/歌词在当前输入片段内的结束时间，例如 7.208s",
      "speaker": "说话者/旁白/歌手身份、声线、口音或方言",
      "content": "逐字台词/旁白/歌词；没有人声则返回空数组"
    }}
  ],
  "shots": [
    {{
      "shot_index": 0,
      "shot_scale": "景别",
      "camera_movement": "运镜",
      "composition": "构图",
      "lighting": "光影",
      "color_tone": "色调",
      "content_description": "严格对应该镜头相对时间范围内的画面内容、人物动作和表情",
      "time_evidence": "当前输入片段内用于判断该镜头内容的相对时间范围，例如 12.300s-14.533s；必要时说明原视频时间",
      "on_screen_text": "画面文字，没有则写无",
      "dialogue": "该镜头内可听见的对白/旁白，没有则写无",
      "audio": {{
        "dialogue": "逐字记录该镜头相对时间范围内可听见的对话/旁白/歌词；没有则写无",
        "speaker": "说话者/旁白/歌手身份、声线、口音或方言；没有则写无",
        "sound_type": "对白/音乐/环境声/音效/无",
        "music": "音乐描述",
        "ambient_sound": "环境声描述",
        "speaker_emotion": "人声情绪",
        "transcript_timestamps": "该镜头内台词/歌词起止时间；无法判断则写无"
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



_NO_DIALOGUE_VALUES = {"", "无", "没有", "none", "null", "n/a", "无对白", "无台词"}


def _field_example(field: dict[str, Any]) -> Any:
    children = field.get("fields") or []
    if children:
        return {child["key"]: _field_example(child) for child in children}
    field_type = field.get("type", "string")
    if field_type in {"string_array", "object_array"}:
        return []
    if field_type == "number":
        return 0
    if field_type == "boolean":
        return False
    return field.get("description") or ""


def _scope_example(config: dict[str, Any], scope: str) -> dict[str, Any]:
    return {
        field["key"]: _field_example(field)
        for field in get_scope_fields(config, scope, model_only=True)
    }


def _dynamic_context_prompt(
    shots: list,
    mode: str,
    start_time: float,
    analysis_config: dict[str, Any],
    transcript_result: dict[str, Any] | None,
) -> str:
    boundaries = _shot_boundaries_text(shots, start_time=start_time)
    transcript_lines = []
    for shot in shots:
        segments = transcript_for_range(transcript_result, shot.start_time, shot.end_time)
        transcript_lines.append(f"镜头 #{shot.index}:\n{transcript_prompt(segments) or '无台词'}")
    prompts = analysis_config.get("prompts") or {}
    output_schema = {
        "shots": [{"shot_index": 0, **_scope_example(analysis_config, "shot")}],
        "segments": [{"segment_index": 0, "shot_indices": [0], **_scope_example(analysis_config, "segment")}],
    }
    return f"""
{prompts.get('shot_role') or '你是一位专业短视频分析师。'}

不可覆盖的系统规则：
1. 当前模型只负责画面与提供文本的分析，不得声称听见音乐、环境声或音效。
2. 镜头边界和系统ASR是唯一可信的时间与台词来源；不得新增、删除或重编号镜头。
3. shot_index 和 shot_indices 使用下方 # 后的零基索引。
4. 每个镜头必须只描述其时间范围内实际可见的内容；推断与事实要明确区分。
5. 只输出符合给定结构的 JSON，不要 Markdown。

分析模式：{mode}
当前片段原视频起点：{start_time:.3f}s
镜头边界：
{boundaries}

系统ASR（绝对原视频时间）：
{chr(10).join(transcript_lines)}

镜头补充要求：
{prompts.get('shot_instructions') or ''}

段落角色与要求：
{prompts.get('segment_role') or ''}
{prompts.get('segment_instructions') or ''}

输出结构及字段说明：
{__import__('json').dumps(output_schema, ensure_ascii=False, indent=2)}
""".strip()


def _parse_seconds(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_time_range(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, str):
        return None, None
    nums = re.findall(r"-?\d+(?:\.\d+)?", value)
    if len(nums) < 2:
        return None, None
    return float(nums[0]), float(nums[1])


def _is_empty_dialogue(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in _NO_DIALOGUE_VALUES


def _iter_transcript_candidates(raw: dict[str, Any]) -> list[Any]:
    for key in ("global_transcript", "transcript", "speakers_and_transcript", "speakers_transcript"):
        value = raw.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for child_key in ("items", "entries", "segments", "transcript"):
                child = value.get(child_key)
                if isinstance(child, list):
                    return child
    return []


def _normalize_transcript_entry(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    start = _parse_seconds(entry.get("start_time") or entry.get("start") or entry.get("begin"))
    end = _parse_seconds(entry.get("end_time") or entry.get("end") or entry.get("finish"))
    if start is None or end is None:
        start, end = _parse_time_range(entry.get("timestamp") or entry.get("timestamps") or entry.get("time") or entry.get("range"))
    text = entry.get("content") or entry.get("text") or entry.get("dialogue") or entry.get("transcript") or entry.get("lyrics")
    if start is None or end is None or end < start or _is_empty_dialogue(text):
        return None
    return {
        "start": float(start),
        "end": float(end),
        "text": str(text).strip(),
        "speaker": str(entry.get("speaker") or entry.get("role") or "").strip(),
    }




def _entry_overlaps(entry: dict[str, Any], relative_bounds: dict[int, tuple[float, float]]) -> list[tuple[int, float, float]]:
    overlapping = []
    for idx, (shot_start, shot_end) in sorted(relative_bounds.items(), key=lambda item: item[1][0]):
        overlap_start = max(entry["start"], shot_start)
        overlap_end = min(entry["end"], shot_end)
        if overlap_end > overlap_start:
            overlapping.append((idx, overlap_start, overlap_end))
    return overlapping


def _remap_transcript_to_shots(raw: dict[str, Any], shot_map: dict[int, dict[str, Any]], shots: list, start_time: float) -> None:
    """Use the model's global transcript timestamps as the authority for per-shot dialogue."""
    entries = [item for item in (_normalize_transcript_entry(e) for e in _iter_transcript_candidates(raw)) if item]
    if not entries:
        return

    relative_bounds = {
        int(shot.index): (
            max(0.0, float(shot.start_time) - start_time),
            max(0.0, float(shot.end_time) - start_time),
        )
        for shot in shots
    }
    assigned: dict[int, list[dict[str, Any]]] = {idx: [] for idx in relative_bounds}

    coarse_assigned_by_overlap: set[int] = set()
    for entry in sorted(entries, key=lambda item: (item["start"], item["end"])):
        overlaps = _entry_overlaps(entry, relative_bounds)
        if overlaps:
            if len(overlaps) > 1:
                idx, _overlap_start, _overlap_end = max(
                    overlaps,
                    key=lambda item: (item[2] - item[1], item[0]),
                )
                item = dict(entry)
                item["start"] = entry["start"]
                item["end"] = entry["end"]
                assigned[idx].append(item)
                coarse_assigned_by_overlap.add(idx)
            else:
                idx, overlap_start, overlap_end = overlaps[0]
                item = dict(entry)
                item["start"] = overlap_start
                item["end"] = overlap_end
                assigned[idx].append(item)
            continue

        midpoint = (entry["start"] + entry["end"]) / 2
        for idx, (shot_start, shot_end) in relative_bounds.items():
            if shot_start <= midpoint <= shot_end:
                assigned[idx].append(entry)
                break

    if not any(assigned.values()):
        return

    for idx, items in assigned.items():
        analysis = shot_map.setdefault(idx, {})
        audio = analysis.setdefault("audio", {})
        if items:
            dialogue = " ".join(item["text"] for item in items)
            timestamps = "; ".join(f"{item['start']:.3f}s-{item['end']:.3f}s" for item in items)
            speakers = ", ".join(dict.fromkeys(item["speaker"] for item in items if item["speaker"]))
            audio["dialogue"] = dialogue
            audio["transcript_timestamps"] = timestamps
            if speakers:
                audio["speaker"] = speakers
            audio.setdefault("sound_type", "对白/旁白")
            if idx in coarse_assigned_by_overlap:
                audio["transcript_precision"] = "coarse_assigned_by_overlap"
                analysis["transcript_precision"] = "coarse_assigned_by_overlap"
            else:
                audio.pop("transcript_precision", None)
                analysis.pop("transcript_precision", None)
            analysis["dialogue"] = dialogue
        else:
            audio["dialogue"] = "无"
            audio["transcript_timestamps"] = "无"
            if _is_empty_dialogue(analysis.get("dialogue")) or analysis.get("dialogue"):
                analysis["dialogue"] = "无"
        analysis.setdefault("transcript_assignment", "global_transcript_time_overlap")


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


def _call_context_model(
    video_path: str,
    shots: list,
    source: str,
    start_time: float = 0.0,
    chunk_index: int | None = None,
    video_id: int | None = None,
    analysis_config: dict[str, Any] | None = None,
    transcript_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if analysis_config:
        prompt = _dynamic_context_prompt(shots, source, start_time, analysis_config, transcript_result)
    else:
        prompt = _context_prompt(shots, source, start_time)
    raw = _call_model_with_retries(video_path, prompt, video_id=video_id)
    if isinstance(raw, str):
        raw = _extract_json(raw)
    shot_map: dict[int, dict[str, Any]] = {}
    for item in raw.get("shots", []):
        idx, analysis = _normalize_shot_result(item, source, chunk_index)
        if idx is not None and analysis:
            shot_map[idx] = analysis
    if transcript_result is not None:
        for shot in shots:
            analysis = shot_map.setdefault(int(shot.index), {})
            inject_asr_fields(
                analysis,
                transcript_for_range(transcript_result, shot.start_time, shot.end_time),
                shot.start_time,
                shot.end_time,
            )
    else:
        _remap_transcript_to_shots(raw, shot_map, shots, start_time)
    segments = []
    for item in raw.get("segments", []):
        segment = _normalize_segment(item, source, chunk_index)
        if segment:
            segments.append(segment)
    return {"shots": shot_map, "segments": segments, "raw": raw}


async def analyze_whole_video_context(
    video_path: str,
    shots: list,
    video_id: int | None = None,
    analysis_config: dict[str, Any] | None = None,
    transcript_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    app_logger.info(f"[上下文分析] 使用整片分析: shots={len(shots)}")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _call_context_model(
        video_path, shots, "whole_video", video_id=video_id,
        analysis_config=analysis_config, transcript_result=transcript_result,
    ))


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


async def analyze_chunked_context(
    video_path: str,
    shots: list,
    temp_dir: str | Path,
    video_id: int | None = None,
    on_chunk_complete=None,
    analysis_config: dict[str, Any] | None = None,
    transcript_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
            if analysis_config is None and transcript_result is None:
                call = lambda: _call_context_model(str(chunk_path), chunk, "chunk_segment", start, chunk_index, video_id=None)
            else:
                call = lambda: _call_context_model(
                    str(chunk_path), chunk, "chunk_segment", start, chunk_index, video_id=None,
                    analysis_config=analysis_config, transcript_result=transcript_result,
                )
            result = await loop.run_in_executor(None, call)
            merged_shots.update(result["shots"])
            merged_segments.extend(result["segments"])
            if on_chunk_complete:
                maybe_awaitable = on_chunk_complete(result, chunk, chunk_index, len(chunks))
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable
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
