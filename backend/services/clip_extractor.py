"""
镜头切片服务：PyAV 切割视频片段 + 提取缩略图
"""
import av
from pathlib import Path
from typing import List, Tuple

from config import SHOTS_DIR, THUMBNAILS_DIR
from services.shot_detector import ShotBoundary
from logger import app_logger


def extract_shot_clips(
    video_path: str,
    boundaries: List[ShotBoundary],
    video_id: int
) -> List[Tuple[str, str]]:
    """
    切割视频片段并提取缩略图
    返回：[(clip_path, thumbnail_path), ...]
    """
    results = []

    for shot in boundaries:
        clip_path = SHOTS_DIR / f"video_{video_id}_shot_{shot.index}.mp4"
        thumb_path = THUMBNAILS_DIR / f"video_{video_id}_shot_{shot.index}.jpg"

        try:
            # 切割视频片段（保持原始时间范围，不扩展）
            _extract_clip(video_path, str(clip_path), shot.start_time, shot.end_time)

            # 提取缩略图（中间帧）
            _extract_thumbnail(video_path, str(thumb_path),
                             (shot.start_time + shot.end_time) / 2)

            results.append((str(clip_path), str(thumb_path)))
        except Exception as e:
            app_logger.error(f"切割镜头 {shot.index} 失败: {e}")
            results.append((None, None))

    return results


def extract_thumbnails_only(
    video_path: str,
    boundaries: List[ShotBoundary],
    video_id: int
) -> List[str]:
    """
    只提取缩略图（不切割视频片段）
    返回：[thumbnail_path, ...]
    """
    results = []

    for shot in boundaries:
        thumb_path = THUMBNAILS_DIR / f"video_{video_id}_shot_{shot.index}.jpg"

        try:
            # 提取缩略图（中间帧）
            _extract_thumbnail(video_path, str(thumb_path),
                             (shot.start_time + shot.end_time) / 2)
            results.append(str(thumb_path))
        except Exception as e:
            app_logger.error(f"提取镜头 {shot.index} 缩略图失败: {e}")
            results.append(None)

    return results


def _extract_clip(input_path: str, output_path: str, start_time: float, end_time: float):
    """使用 PyAV 切割视频片段"""
    with av.open(input_path) as in_container:
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


def _extract_thumbnail(video_path: str, output_path: str, time_sec: float):
    """提取指定时间点的帧作为缩略图"""
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        container.seek(int(time_sec * av.time_base))

        for frame in container.decode(stream):
            if frame.time is None:
                continue
            if frame.time >= time_sec:
                img = frame.to_image()
                img.save(output_path, quality=85)
                break
