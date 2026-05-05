"""
AI 分析服务：调用 Qwen 多模态模型分析镜头视频片段。
"""
import base64
import json
import re
import asyncio
import time
from fractions import Fraction
from pathlib import Path

import av
import dashscope
from openai import OpenAI
from dashscope import MultiModalConversation

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    MODEL_NAME,
    AI_CONCURRENCY,
    MIN_MODEL_VIDEO_DURATION,
    SAFE_MODEL_VIDEO_DURATION,
    SHORT_SHOT_MERGE_MAX_SHOTS,
    MODEL_TRANSIENT_RETRIES,
    MODEL_TRANSIENT_RETRY_DELAY,
)
from prompt_config import build_shot_prompt
from logger import app_logger

dashscope.api_key = DASHSCOPE_API_KEY
_openai_client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL) if DASHSCOPE_API_KEY else None

_semaphore = asyncio.Semaphore(AI_CONCURRENCY)


def _extract_json(text: str) -> dict:
    """从模型输出中提取 JSON，兼容带代码块的情况"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 提取 ```json ... ``` 块
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # 提取第一个 { ... }
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    raise ValueError(f"无法从模型输出中提取 JSON：{text[:300]}")


def _get_video_duration(video_path: str) -> float:
    """获取视频文件的实际时长（秒）"""
    if not video_path or not Path(video_path).exists():
        raise ValueError(f"视频片段不存在或切片失败: {video_path}")
    with av.open(video_path) as container:
        if container.duration:
            return container.duration / av.time_base
        # 如果 container.duration 不可用，尝试从视频流获取
        stream = container.streams.video[0]
        if stream.duration:
            return float(stream.duration * stream.time_base)
    return 0.0


def _compute_extended_bounds(
    start_time: float,
    end_time: float,
    source_duration: float,
    min_duration: float = MIN_MODEL_VIDEO_DURATION,
) -> tuple[float, float]:
    """Return bounds that are at least min_duration when the source allows it."""
    extended_start = max(0.0, start_time - max(0.0, min_duration - (end_time - start_time)))
    extended_end = min(source_duration, max(end_time, extended_start + min_duration))
    if extended_end - extended_start < min_duration:
        extended_start = max(0.0, extended_end - min_duration)
    return round(extended_start, 3), round(extended_end, 3)


def build_merged_analysis_unit(
    shots: list,
    target_index: int,
    safe_duration: float = SAFE_MODEL_VIDEO_DURATION,
    max_shots: int = SHORT_SHOT_MERGE_MAX_SHOTS,
) -> dict:
    """Build a neighboring-shot analysis unit for short target shots."""
    if not shots:
        raise ValueError("没有可合并的镜头")

    ordered = sorted(shots, key=lambda s: s.index)
    positions = {shot.index: i for i, shot in enumerate(ordered)}
    if target_index not in positions:
        raise ValueError(f"目标镜头不存在: {target_index}")

    pos = positions[target_index]
    left = right = pos

    def current_duration() -> float:
        return max(0.0, ordered[right].end_time - ordered[left].start_time)

    while current_duration() < safe_duration and (right - left + 1) < max_shots:
        can_left = left > 0
        can_right = right < len(ordered) - 1
        if not can_left and not can_right:
            break
        if not can_left:
            right += 1
            continue
        if not can_right:
            left -= 1
            continue

        left_span = ordered[left].start_time - ordered[left - 1].start_time
        right_span = ordered[right + 1].end_time - ordered[right].end_time
        if left_span <= right_span:
            left -= 1
        else:
            right += 1

    unit_shots = ordered[left:right + 1]
    start = unit_shots[0].start_time
    end = unit_shots[-1].end_time
    return {
        "mode": "merged_context" if len(unit_shots) > 1 else "single",
        "target_shot_index": target_index,
        "analysis_shot_indices": [shot.index for shot in unit_shots],
        "merged_start_time": round(start, 3),
        "merged_end_time": round(end, 3),
        "merged_duration": round(end - start, 3),
        "target_offset_start": round(ordered[pos].start_time - start, 3),
        "target_offset_end": round(ordered[pos].end_time - start, 3),
    }


def _is_transient_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    transient_markers = (
        "receive batching backend response failed",
        "backend response failed",
        "timeout",
        "temporarily",
        "try again",
        "rate limit",
        "internalerror",
    )
    return any(marker in message for marker in transient_markers)


def _call_model_with_retries(video_path: str, user_text: str) -> dict:
    attempts = max(1, MODEL_TRANSIENT_RETRIES + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _call_omni_model(video_path, user_text) if _is_omni_model() else _call_vl_model(video_path, user_text)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_transient_model_error(exc):
                raise
            sleep_seconds = MODEL_TRANSIENT_RETRY_DELAY * attempt
            app_logger.warning(
                f"模型调用失败，准备重试: attempt={attempt}/{attempts}, "
                f"delay={sleep_seconds:.1f}s, error={exc}"
            )
            time.sleep(sleep_seconds)
    raise last_error or ValueError("模型调用失败")




def _is_omni_model() -> bool:
    return "omni" in MODEL_NAME.lower()


def _video_data_url(video_path: str) -> str:
    suffix = Path(video_path).suffix.lower()
    media_type = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
    }.get(suffix, "video/mp4")
    encoded = base64.b64encode(Path(video_path).read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _extract_text_from_openai_stream(chunks) -> str:
    parts: list[str] = []
    for chunk in chunks:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text", ""))
    return "".join(parts)


def _call_omni_model(video_path: str, user_text: str) -> dict:
    if _openai_client is None:
        raise ValueError("未配置 DASHSCOPE_API_KEY，无法调用 Omni 模型")

    completion = _openai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": _video_data_url(video_path)},
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
        modalities=["text"],
        stream=True,
        stream_options={"include_usage": True},
    )
    text = _extract_text_from_openai_stream(completion)
    if not text.strip():
        raise ValueError("Omni API 未返回文本内容")
    return _extract_json(text)


def _call_vl_model(video_path: str, user_text: str) -> dict:
    messages = [
        {
            "role": "user",
            "content": [
                {"video": f"file://{video_path}"},
                {"text": user_text},
            ],
        },
    ]

    response = MultiModalConversation.call(
        model=MODEL_NAME,
        messages=messages,
        fps=5.0,
        max_frames=100,
    )

    if response is None:
        raise ValueError("API 调用返回 None，可能是网络问题或 API 配额不足")

    if not hasattr(response, "output") or response.output is None:
        raise ValueError(f"API 响应格式异常：{response}")

    if not hasattr(response.output, "choices") or not response.output.choices:
        raise ValueError(f"API 响应缺少 choices 字段：{response.output}")

    output = response.output.choices[0].message.content
    if isinstance(output, list):
        text = " ".join(
            item.get("text", "") for item in output if isinstance(item, dict)
        )
    else:
        text = str(output)

    return _extract_json(text)


def _extract_extended_clip(
    source_video_path: str,
    output_path: str,
    start_time: float,
    end_time: float
):
    """从原始视频中提取扩展的视频片段"""
    with av.open(source_video_path) as in_container:
        in_video = in_container.streams.video[0]
        in_audio = in_container.streams.audio[0] if in_container.streams.audio else None
        output_rate = max(1, round(float(in_video.average_rate))) if in_video.average_rate else 25

        with av.open(output_path, 'w') as out_container:
            # 视频流
            out_video = out_container.add_stream('h264', rate=output_rate)
            out_video.width = in_video.width
            out_video.height = in_video.height
            out_video.pix_fmt = 'yuv420p'
            out_video.options = {'crf': '23', 'preset': 'fast'}
            output_time_base = Fraction(1, output_rate)
            out_audio = None
            if in_audio:
                out_audio = out_container.add_stream("aac", rate=in_audio.rate or 44100)
                out_audio.layout = "mono" if not in_audio.layout else in_audio.layout.name
                out_audio.time_base = Fraction(1, out_audio.rate)

            # Seek 到起始位置
            in_container.seek(int(start_time * av.time_base))

            # 处理视频帧
            stop_video = False
            frame_index = 0
            for packet in in_container.demux(in_video):
                for frame in packet.decode():
                    if frame.time is None:
                        continue
                    if frame.time < start_time:
                        continue
                    if frame.time > end_time:
                        stop_video = True
                        break

                    frame.pts = frame_index
                    frame.time_base = output_time_base
                    for pkt in out_video.encode(frame):
                        out_container.mux(pkt)
                    frame_index += 1
                if stop_video:
                    break

            # 刷新编码器
            for pkt in out_video.encode():
                out_container.mux(pkt)

            if out_audio:
                _encode_audio_track(source_video_path, out_container, out_audio, start_time, end_time)


def _encode_audio_track(input_path: str, out_container, out_audio, start_time: float, end_time: float) -> None:
    # Use a fresh demuxer for audio. Re-seeking the video demuxer after H.264
    # decoding can crash native FFmpeg/PyAV on some phone videos.
    with av.open(input_path) as audio_container:
        in_audio = audio_container.streams.audio[0] if audio_container.streams.audio else None
        if not in_audio:
            return

        audio_container.seek(int(start_time * av.time_base))
        stop_audio = False
        sample_cursor = 0
        for packet in audio_container.demux(in_audio):
            for frame in packet.decode():
                if frame.time is None:
                    continue
                if frame.time < start_time:
                    continue
                if frame.time > end_time:
                    stop_audio = True
                    break

                frame.pts = sample_cursor
                frame.time_base = Fraction(1, frame.sample_rate)
                sample_cursor += frame.samples
                for pkt in out_audio.encode(frame):
                    out_container.mux(pkt)
            if stop_audio:
                break

        for pkt in out_audio.encode():
            out_container.mux(pkt)


async def analyze_shot(
    clip_path: str,
    shot_index: int,
    total_shots: int,
    duration: float = 0.0,
    video_path: str = None,
    start_time: float = 0.0,
    end_time: float = 0.0,
    analysis_unit: dict | None = None,
) -> dict:
    """
    分析单个镜头视频片段，返回结构化分析字典

    参数：
        clip_path: 镜头切片文件路径
        shot_index: 镜头索引
        total_shots: 总镜头数
        duration: 镜头原始时长
        video_path: 原始视频文件路径（用于扩展短视频）
        start_time: 镜头在原始视频中的开始时间
        end_time: 镜头在原始视频中的结束时间
    """

    async with _semaphore:
        # 检测视频片段的实际时长
        actual_duration = _get_video_duration(clip_path)

        temp_clip_path = clip_path
        unit = analysis_unit or {
            "mode": "single",
            "target_shot_index": shot_index,
            "analysis_shot_indices": [shot_index],
            "merged_start_time": start_time,
            "merged_end_time": end_time,
            "merged_duration": duration or actual_duration,
            "target_offset_start": 0.0,
            "target_offset_end": duration or actual_duration,
        }

        should_extract_unit = bool(video_path) and (
            unit.get("mode") == "merged_context" or actual_duration < MIN_MODEL_VIDEO_DURATION
        )
        if should_extract_unit:
            extended_start = float(unit.get("merged_start_time", start_time))
            extended_end = float(unit.get("merged_end_time", end_time))
            if extended_end - extended_start < MIN_MODEL_VIDEO_DURATION:
                raise ValueError(
                    f"视频片段太短，合并后仍不足 {MIN_MODEL_VIDEO_DURATION:.1f}s，"
                    "请调高镜头检测阈值或手动合并镜头"
                )

            temp_clip_path = clip_path.replace('.mp4', '_extended.mp4')
            app_logger.info(
                f"镜头 {shot_index} 使用{unit.get('mode', 'single')}分析单元，"
                f"原时长 {actual_duration:.2f}s，分析范围 {extended_start:.2f}s 到 {extended_end:.2f}s，"
                f"包含镜头 {unit.get('analysis_shot_indices')}"
            )
            _extract_extended_clip(video_path, temp_clip_path, extended_start, extended_end)
            extended_duration = _get_video_duration(temp_clip_path)
            if extended_duration + 0.05 < MIN_MODEL_VIDEO_DURATION:
                Path(temp_clip_path).unlink(missing_ok=True)
                raise ValueError(
                    f"合并后视频仍过短: {extended_duration:.2f}s，"
                    "请调高镜头检测阈值或手动合并镜头"
                )

        try:
            user_text = build_shot_prompt(
                shot_index=shot_index + 1,
                total_shots=total_shots,
            )

            if temp_clip_path != clip_path:
                indices = [int(i) + 1 for i in unit.get("analysis_shot_indices", [shot_index])]
                user_text += f"\n\n**⚠️ 合并分析片段 - 请严格遵守**：\n"
                user_text += f"1. 当前输入视频是为了满足模型时长要求构造的分析片段，包含原始镜头 {indices}。\n"
                user_text += f"2. 本次主要分析目标是原始镜头 #{shot_index + 1}，它在当前输入片段中的时间范围是 {unit.get('target_offset_start', 0):.1f}s 到 {unit.get('target_offset_end', duration):.1f}s。\n"
                user_text += "3. 请优先分析目标镜头，不要把前后上下文误认为目标镜头内容。\n"
                user_text += "4. 如果片段中能看出多个原始镜头，请在 JSON 中额外加入 context_shot_summaries 数组，概括每个上下文镜头的景别、动作和作用。\n"
                user_text += "5. 请在 JSON 中额外加入 merged_segment_analysis 字段，说明这些镜头合并观看时的节奏、景别变化和叙事关系。\n"

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: _call_model_with_retries(temp_clip_path, user_text),
            )
            if unit.get("mode") == "merged_context":
                result.setdefault("analysis_mode", "merged_context")
                result.setdefault("target_shot_index", shot_index)
                result.setdefault("analysis_shot_indices", unit.get("analysis_shot_indices", [shot_index]))
                result.setdefault("merged_start_time", unit.get("merged_start_time"))
                result.setdefault("merged_end_time", unit.get("merged_end_time"))
                result.setdefault("target_offset_start", unit.get("target_offset_start"))
                result.setdefault("target_offset_end", unit.get("target_offset_end"))
            return result

        finally:
            # 清理临时文件
            if temp_clip_path != clip_path:
                try:
                    Path(temp_clip_path).unlink(missing_ok=True)
                    app_logger.info(f"已删除临时扩展文件: {temp_clip_path}")
                except Exception as e:
                    app_logger.warning(f"删除临时文件失败: {e}")
