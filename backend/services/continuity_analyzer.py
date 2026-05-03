"""
连贯性分析服务：汇总所有镜头分析 → 全片整体报告
"""
import asyncio

import dashscope
from dashscope import Generation

from config import DASHSCOPE_API_KEY, CONTINUITY_MODEL_NAME
from prompt_config import build_continuity_prompt, build_continuity_summary
from logger import app_logger

dashscope.api_key = DASHSCOPE_API_KEY


def _build_summary(shots_data: list) -> str:
    """Build the model input summary according to prompt config."""
    return build_continuity_summary(shots_data)


async def analyze_continuity(shots_data: list) -> dict:
    """
    shots_data: list of dicts with keys: index, duration, analysis
    返回连贯性报告字典
    """
    summary = _build_summary(shots_data)
    prompt = build_continuity_prompt(summary)

    loop = asyncio.get_event_loop()

    # 连贯性分析用纯文字模型（更快更省），模型可通过 CONTINUITY_MODEL_NAME 配置。
    def _call():
        return Generation.call(
            model=CONTINUITY_MODEL_NAME,
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
