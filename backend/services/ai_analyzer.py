"""
AI 分析服务：调用 Qwen 多模态模型分析镜头视频片段。
"""
import base64
import json
import re
import asyncio
from fractions import Fraction
from pathlib import Path

import av
import dashscope
from openai import OpenAI
from dashscope import MultiModalConversation

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, MODEL_NAME, AI_CONCURRENCY, MIN_MODEL_VIDEO_DURATION
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

        extended_seconds = 0.0
        temp_clip_path = clip_path

        # 如果视频片段 < 2 秒且提供了原始视频路径，则创建扩展版本
        if actual_duration < MIN_MODEL_VIDEO_DURATION and video_path:
            source_duration = _get_video_duration(video_path)
            extended_start, extended_end = _compute_extended_bounds(
                start_time,
                end_time,
                source_duration,
                MIN_MODEL_VIDEO_DURATION,
            )
            if extended_end - extended_start < MIN_MODEL_VIDEO_DURATION:
                raise ValueError(
                    f"视频片段太短，且原视频总时长不足 {MIN_MODEL_VIDEO_DURATION:.1f}s，无法满足模型要求"
                )
            extended_seconds = max(0.0, start_time - extended_start)

            # 创建临时扩展版本
            temp_clip_path = clip_path.replace('.mp4', '_extended.mp4')

            try:
                app_logger.info(
                    f"镜头 {shot_index} 时长 {actual_duration:.2f}s < {MIN_MODEL_VIDEO_DURATION}s，"
                    f"扩展上下文 {extended_seconds:.2f}s (从 {extended_start:.2f}s 到 {extended_end:.2f}s)"
                )
                _extract_extended_clip(video_path, temp_clip_path, extended_start, extended_end)
                extended_duration = _get_video_duration(temp_clip_path)
                if extended_duration < MIN_MODEL_VIDEO_DURATION:
                    raise ValueError(f"扩展后视频仍过短: {extended_duration:.2f}s")
            except Exception as e:
                app_logger.error(f"创建扩展视频片段失败: {e}，使用原始片段")
                temp_clip_path = clip_path
                extended_seconds = 0.0

        try:
            user_text = build_shot_prompt(
                shot_index=shot_index + 1,
                total_shots=total_shots,
            )

            # 如果有扩展，在 prompt 中说明
            if extended_seconds > 0:
                user_text += f"\n\n**⚠️ 重要提示 - 请严格遵守**：\n"
                user_text += f"1. 这个视频片段的前 {extended_seconds:.1f} 秒（0-{extended_seconds:.1f}秒）是为了满足技术要求而添加的上下文内容，**不是本镜头的内容**。\n"
                user_text += f"2. **本镜头的实际内容从 {extended_seconds:.1f} 秒开始，到视频结束**（约 {duration:.1f} 秒）。\n"
                user_text += f"3. 在分析时：\n"
                user_text += f"   - 景别、运镜、构图、光影、色调：**只分析 {extended_seconds:.1f} 秒之后的画面**\n"
                user_text += f"   - 画面文字（on_screen_text）：**只提取 {extended_seconds:.1f} 秒之后出现的文字**\n"
                user_text += f"   - 对话（dialogue）：**只记录 {extended_seconds:.1f} 秒之后的对话内容**\n"
                user_text += f"   - 内容描述（content_description）：**只描述 {extended_seconds:.1f} 秒之后发生的事情**\n"
                user_text += f"4. **完全忽略前 {extended_seconds:.1f} 秒的所有内容**，包括字幕、对话、画面文字等。\n"

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: _call_omni_model(temp_clip_path, user_text)
                if _is_omni_model()
                else _call_vl_model(temp_clip_path, user_text),
            )

        finally:
            # 清理临时文件
            if temp_clip_path != clip_path:
                try:
                    Path(temp_clip_path).unlink(missing_ok=True)
                    app_logger.info(f"已删除临时扩展文件: {temp_clip_path}")
                except Exception as e:
                    app_logger.warning(f"删除临时文件失败: {e}")
