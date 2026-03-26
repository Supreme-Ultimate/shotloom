"""
AI 分析服务：调用 qwen3-vl-flash 分析镜头视频片段（纯视觉，不含音频）
"""
import json
import re
import asyncio
from pathlib import Path

import av
import dashscope
from dashscope import MultiModalConversation

from config import DASHSCOPE_API_KEY, MODEL_NAME, AI_CONCURRENCY
from prompts.shot_analysis import SHOT_USER_PROMPT
from logger import app_logger

dashscope.api_key = DASHSCOPE_API_KEY

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
    with av.open(video_path) as container:
        if container.duration:
            return container.duration / av.time_base
        # 如果 container.duration 不可用，尝试从视频流获取
        stream = container.streams.video[0]
        if stream.duration:
            return float(stream.duration * stream.time_base)
    return 0.0


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

        with av.open(output_path, 'w') as out_container:
            # 视频流
            out_video = out_container.add_stream('h264', rate=in_video.average_rate)
            out_video.width = in_video.width
            out_video.height = in_video.height
            out_video.pix_fmt = 'yuv420p'
            out_video.options = {'crf': '23', 'preset': 'fast'}

            # 音频流（如果有）
            out_audio = None
            if in_audio:
                out_audio = out_container.add_stream('aac', rate=in_audio.rate or 44100)

            # Seek 到起始位置
            in_container.seek(int(start_time * av.time_base))

            # 处理视频帧
            for packet in in_container.demux(in_video):
                for frame in packet.decode():
                    if frame.time is None:
                        continue
                    if frame.time < start_time:
                        continue
                    if frame.time > end_time:
                        break

                    for pkt in out_video.encode(frame):
                        out_container.mux(pkt)

            # 刷新编码器
            for pkt in out_video.encode():
                out_container.mux(pkt)

            # 处理音频（如果有）
            if in_audio and out_audio:
                in_container.seek(int(start_time * av.time_base))
                for packet in in_container.demux(in_audio):
                    for frame in packet.decode():
                        if frame.time is None:
                            continue
                        if frame.time < start_time:
                            continue
                        if frame.time > end_time:
                            break

                        for pkt in out_audio.encode(frame):
                            out_container.mux(pkt)

                # 刷新音频编码器
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

        MIN_DURATION = 2.0
        extended_seconds = 0.0
        temp_clip_path = clip_path

        # 如果视频片段 < 2 秒且提供了原始视频路径，则创建扩展版本
        if actual_duration < MIN_DURATION and video_path:
            extended_seconds = MIN_DURATION - actual_duration
            extended_start = max(0, start_time - extended_seconds)

            # 创建临时扩展版本
            temp_clip_path = clip_path.replace('.mp4', '_extended.mp4')

            try:
                app_logger.info(
                    f"镜头 {shot_index} 时长 {actual_duration:.2f}s < {MIN_DURATION}s，"
                    f"向前扩展 {extended_seconds:.2f}s (从 {extended_start:.2f}s 到 {end_time:.2f}s)"
                )
                _extract_extended_clip(video_path, temp_clip_path, extended_start, end_time)
            except Exception as e:
                app_logger.error(f"创建扩展视频片段失败: {e}，使用原始片段")
                temp_clip_path = clip_path
                extended_seconds = 0.0

        try:
            user_text = SHOT_USER_PROMPT.format(
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

            # qwen3-vl 系列不使用 system message，所有指令放在 user message 中
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"video": f"file://{temp_clip_path}"},
                        {"text": user_text},
                    ],
                },
            ]

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: MultiModalConversation.call(
                    model=MODEL_NAME,
                    messages=messages,
                    # 视频抽帧参数：确保短视频也能抽取足够的帧数
                    # fps=5.0 表示每 0.2 秒抽一帧，1.5秒视频可抽取约 7-8 帧
                    # 对于短视频（1-3秒），较高的 fps 可以确保抽取足够的帧数
                    fps=5.0,  # 提高抽帧频率，确保短视频有足够帧数
                    max_frames=100,  # 设置最大帧数上限
                ),
            )

            # 检查响应是否有效
            if response is None:
                raise ValueError("API 调用返回 None，可能是网络问题或 API 配额不足")

            if not hasattr(response, 'output') or response.output is None:
                raise ValueError(f"API 响应格式异常：{response}")

            if not hasattr(response.output, 'choices') or not response.output.choices:
                raise ValueError(f"API 响应缺少 choices 字段：{response.output}")

            output = response.output.choices[0].message.content
            # output 可能是列表（多模态）或字符串
            if isinstance(output, list):
                text = " ".join(
                    item.get("text", "") for item in output if isinstance(item, dict)
                )
            else:
                text = str(output)

            return _extract_json(text)

        finally:
            # 清理临时文件
            if temp_clip_path != clip_path:
                try:
                    Path(temp_clip_path).unlink(missing_ok=True)
                    app_logger.info(f"已删除临时扩展文件: {temp_clip_path}")
                except Exception as e:
                    app_logger.warning(f"删除临时文件失败: {e}")
