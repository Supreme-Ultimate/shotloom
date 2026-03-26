"""
连贯性分析服务：汇总所有镜头分析 → 全片整体报告
"""
import json
import asyncio

import dashscope
from dashscope import Generation

from config import DASHSCOPE_API_KEY, MODEL_NAME
from prompts.shot_analysis import CONTINUITY_PROMPT
from logger import app_logger

dashscope.api_key = DASHSCOPE_API_KEY


def _build_summary(shots_data: list) -> str:
    """精简每个镜头的分析数据，避免超出上下文长度"""
    summaries = []
    for i, s in enumerate(shots_data):
        a = s.get("analysis") or {}
        summaries.append({
            "index": i + 1,
            "duration": s.get("duration"),
            "shot_scale": a.get("shot_scale"),
            "camera_movement": a.get("camera_movement"),
            "emotional_function": a.get("emotional_function"),
            "rhythm_contribution": a.get("rhythm_contribution"),
            "narrative_decision": a.get("narrative_decision"),
            "what": a.get("what"),
            "why": a.get("why"),
            "audio_sound_type": a.get("audio", {}).get("sound_type"),
            "audiovisual_sync": a.get("audiovisual_sync"),
        })
    return json.dumps(summaries, ensure_ascii=False, indent=2)


async def analyze_continuity(shots_data: list) -> dict:
    """
    shots_data: list of dicts with keys: index, duration, analysis
    返回连贯性报告字典
    """
    summary = _build_summary(shots_data)
    prompt = CONTINUITY_PROMPT.format(shots_summary=summary)

    loop = asyncio.get_event_loop()

    # 连贯性分析用纯文字模型（更快更省）
    # 若 MODEL_NAME 是多模态模型，用 Generation；否则用 MultiModalConversation
    def _call():
        return Generation.call(
            model="qwen-max",  # 纯文字模型用于连贯性总结
            messages=[{"role": "user", "content": prompt}],
            result_format="message",
        )

    response = await loop.run_in_executor(None, _call)
    text = response.output.choices[0].message.content

    import re, json as _json
    try:
        return _json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return _json.loads(match.group(0))
            except Exception:
                pass
    return {"raw": text}
