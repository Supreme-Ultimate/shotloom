"""
连贯性分析服务：汇总所有镜头分析 → 全片整体报告
"""
import asyncio
import json
import re
import time

from openai import OpenAI

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    CONTINUITY_MODEL_NAME,
    MODEL_TRANSIENT_RETRIES,
    MODEL_TRANSIENT_RETRY_DELAY,
)
from prompt_config import build_continuity_prompt, build_continuity_summary
from logger import app_logger
from services.ai_analyzer import is_model_provider_quota_error

_openai_client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL) if DASHSCOPE_API_KEY else None


def _build_summary(shots_data: list, analysis_config: dict | None = None) -> str:
    """Build the model input summary according to prompt config."""
    return build_continuity_summary(shots_data, analysis_config)


def _extract_text_from_response(response) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise ValueError("模型服务未返回有效内容，请稍后手动重试。")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        text = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        if text.strip():
            return text
    raise ValueError("模型服务未返回有效内容，请稍后手动重试。")


def _extract_text_from_stream(chunks) -> str:
    parts: list[str] = []
    for chunk in chunks:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = choices[0].delta
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(item.get("text", "") for item in content if isinstance(item, dict))
    text = "".join(parts)
    if not text.strip():
        raise ValueError("模型服务未返回有效内容，请稍后手动重试。")
    return text


def _parse_json_or_raw(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {"raw": text}


def _is_transient_continuity_error(error: Exception) -> bool:
    if is_model_provider_quota_error(error):
        return False
    message = str(error).lower()
    markers = (
        "ssleoferror",
        "eof occurred in violation of protocol",
        "httpsconnectionpool",
        "max retries exceeded",
        "connection aborted",
        "connection reset",
        "timeout",
        "temporarily",
        "try again",
        "rate limit",
        "internalerror",
    )
    return any(marker in message for marker in markers)


def _call_continuity_model(prompt: str) -> dict:
    if _openai_client is None:
        raise ValueError("未配置 DASHSCOPE_API_KEY，无法生成整体分析")

    attempts = max(1, MODEL_TRANSIENT_RETRIES + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = _openai_client.chat.completions.create(
                model=CONTINUITY_MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_json_or_raw(_extract_text_from_response(response))
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_transient_continuity_error(exc):
                raise
            sleep_seconds = MODEL_TRANSIENT_RETRY_DELAY * attempt
            app_logger.warning(
                f"整体分析模型调用失败，准备重试: attempt={attempt}/{attempts}, "
                f"delay={sleep_seconds:.1f}s, error={exc}"
            )
            time.sleep(sleep_seconds)
    raise last_error or ValueError("整体分析模型调用失败")


async def analyze_continuity(shots_data: list, analysis_config: dict | None = None) -> dict:
    """
    shots_data: list of dicts with keys: index, duration, analysis
    返回连贯性报告字典
    """
    summary = _build_summary(shots_data, analysis_config)
    prompt = build_continuity_prompt(summary, analysis_config)

    loop = asyncio.get_event_loop()
    # 连贯性分析用 OpenAI 兼容接口，保证跟镜头分析使用同一个 base_url/地域。
    return await loop.run_in_executor(None, lambda: _call_continuity_model(prompt))
