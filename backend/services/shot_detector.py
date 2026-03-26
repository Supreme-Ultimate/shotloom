"""
镜头检测服务
使用 PySceneDetect ContentDetector + AdaptiveDetector 双引擎
"""
from dataclasses import dataclass
from typing import List

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector, AdaptiveDetector

from config import SCENE_THRESHOLD


@dataclass
class ShotBoundary:
    index: int
    start_time: float  # 秒
    end_time: float
    duration: float


def detect_shots(video_path: str, threshold: float = None) -> List[ShotBoundary]:
    """
    检测视频镜头边界，返回镜头列表。
    双引擎：ContentDetector（硬切）+ AdaptiveDetector（渐变/溶解）
    结果取并集后去重合并。
    """
    t = threshold if threshold is not None else SCENE_THRESHOLD

    video = open_video(video_path)
    duration = video.duration.get_seconds()

    # --- ContentDetector（硬切） ---
    sm1 = SceneManager()
    sm1.add_detector(ContentDetector(threshold=t))
    video.seek(0)
    sm1.detect_scenes(video, show_progress=False)
    scenes1 = sm1.get_scene_list()

    # --- AdaptiveDetector（渐变/溶解） ---
    video2 = open_video(video_path)
    sm2 = SceneManager()
    sm2.add_detector(AdaptiveDetector())
    sm2.detect_scenes(video2, show_progress=False)
    scenes2 = sm2.get_scene_list()

    # 合并所有切换点（以秒为单位），去重
    cut_times = set()
    for scene_list in [scenes1, scenes2]:
        for i, (start, _) in enumerate(scene_list):
            if i > 0:
                cut_times.add(round(start.get_seconds(), 3))

    cut_times = sorted(cut_times)

    # 构建边界列表
    boundaries = [0.0] + cut_times + [duration]
    shots = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        dur = round(end - start, 3)
        if dur < 0.5:  # 忽略过短的片段（可能是误检）
            continue
        shots.append(ShotBoundary(
            index=len(shots),
            start_time=round(start, 3),
            end_time=round(end, 3),
            duration=dur,
        ))

    # 重新编号
    for i, s in enumerate(shots):
        s.index = i

    return shots
