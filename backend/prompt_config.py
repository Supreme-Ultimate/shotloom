"""Load configurable analysis prompts and JSON field schemas."""
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import PROMPT_CONFIG_PATH

DEFAULT_PROMPT_CONFIG = Path(__file__).parent / "prompt_configs" / "default.json"
CONTINUITY_SUMMARY_MAX_CHARS = int(os.getenv("CONTINUITY_SUMMARY_MAX_CHARS", "22000"))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Prompt config must be a JSON object: {path}")
    return data


@lru_cache(maxsize=1)
def load_prompt_config() -> dict[str, Any]:
    path = Path(PROMPT_CONFIG_PATH) if PROMPT_CONFIG_PATH else DEFAULT_PROMPT_CONFIG
    if not path.is_absolute():
        path = Path(__file__).parent.parent / path
    if not path.exists():
        raise FileNotFoundError(f"Prompt config not found: {path}")
    data = _load_json(path)
    if not data.get("shot_fields") or not data.get("continuity_fields"):
        raise ValueError("Prompt config must include shot_fields and continuity_fields")
    return data


def _field_example(field: dict[str, Any]) -> Any:
    if "example" in field:
        return field["example"]
    field_type = field.get("type")
    if field_type == "array":
        return [field.get("description", "...")]
    nested = field.get("fields")
    if nested:
        return {item["key"]: _field_example(item) for item in nested}
    return field.get("description", "...")


def _schema_from_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {field["key"]: _field_example(field) for field in fields}


def _field_lines(fields: list[dict[str, Any]], prefix: str = "") -> list[str]:
    lines: list[str] = []
    for field in fields:
        key = f"{prefix}{field['key']}"
        description = field.get("description", "")
        lines.append(f"- {key}: {description}")
        nested = field.get("fields")
        if nested:
            lines.extend(_field_lines(nested, f"{key}."))
    return lines


def build_shot_prompt(shot_index: int, total_shots: int) -> str:
    config = load_prompt_config()
    schema = _schema_from_fields(config["shot_fields"])
    parts = [
        config.get("role", "你是一位专业的影视分析师。"),
        config.get("shot_prompt_intro", "请分析这段视频片段。").format(
            shot_index=shot_index,
            total_shots=total_shots,
        ),
    ]
    extra = config.get("shot_extra_instructions")
    if extra:
        parts.append(str(extra))
    parts.extend([
        config.get("shot_output_instruction", "直接输出 JSON，不加代码块："),
        json.dumps(schema, ensure_ascii=False, indent=2),
        "字段要求：",
        "\n".join(_field_lines(config["shot_fields"])),
    ])
    return "\n\n".join(parts)


def _get_nested(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _clip_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _compact_continuity_summary(shots_data: list[dict[str, Any]], fields: list[str], max_chars: int) -> str:
    labels = {
        "shot_scale": "景",
        "camera_movement": "运",
        "emotional_function": "情",
        "rhythm_contribution": "节",
        "narrative_decision": "叙",
        "what": "事",
        "why": "因",
        "audio.sound_type": "声",
        "audiovisual_sync": "声画",
    }
    preferred_fields = [
        "shot_scale",
        "camera_movement",
        "emotional_function",
        "rhythm_contribution",
        "narrative_decision",
        "what",
        "why",
        "audio.sound_type",
        "audiovisual_sync",
    ]
    ordered_fields = [field for field in preferred_fields if field in fields] or fields

    def render(field_limit: int, selected_fields: list[str]) -> str:
        lines = [
            "压缩镜头摘要：每行格式为 #镜头号 时长 字段=极简摘要；已覆盖所有镜头，用于整体连贯性、节奏和叙事结构分析。"
        ]
        for i, shot in enumerate(shots_data):
            analysis = shot.get("analysis") or {}
            line_parts = [f"#{i + 1:03d}", f"{float(shot.get('duration') or 0):.1f}s"]
            for field in selected_fields:
                value = _clip_text(_get_nested(analysis, field), field_limit)
                if value:
                    line_parts.append(f"{labels.get(field, field)}={value}")
            lines.append(" ".join(line_parts))
        return "\n".join(lines)

    for field_limit in (24, 16, 10, 6):
        summary = render(field_limit, ordered_fields)
        if len(summary) <= max_chars:
            return summary

    essential_fields = [field for field in ordered_fields if field in {
        "shot_scale",
        "camera_movement",
        "emotional_function",
        "rhythm_contribution",
        "narrative_decision",
    }]
    summary = render(6, essential_fields or ordered_fields[:4])
    if len(summary) <= max_chars:
        return summary

    # Last-resort compression still preserves every shot index and duration.
    lines = ["超压缩镜头摘要：输入较长，仅保留所有镜头的时长、景别、运镜和情绪关键词。"]
    for i, shot in enumerate(shots_data):
        analysis = shot.get("analysis") or {}
        scale = _clip_text(_get_nested(analysis, "shot_scale"), 4)
        move = _clip_text(_get_nested(analysis, "camera_movement"), 4)
        emotion = _clip_text(_get_nested(analysis, "emotional_function"), 4)
        lines.append(f"#{i + 1:03d} {float(shot.get('duration') or 0):.1f}s {scale}/{move}/{emotion}")
    return "\n".join(lines)[:max_chars]


def build_continuity_summary(shots_data: list[dict[str, Any]]) -> str:
    config = load_prompt_config()
    fields = config.get("continuity_summary_fields") or []
    summaries = []
    for i, shot in enumerate(shots_data):
        analysis = shot.get("analysis") or {}
        item: dict[str, Any] = {
            "index": i + 1,
            "duration": shot.get("duration"),
        }
        for field in fields:
            output_key = field.replace(".", "_")
            item[output_key] = _get_nested(analysis, field)
        summaries.append(item)
    summary = json.dumps(summaries, ensure_ascii=False, indent=2)
    if len(summary) <= CONTINUITY_SUMMARY_MAX_CHARS:
        return summary
    return _compact_continuity_summary(shots_data, fields, CONTINUITY_SUMMARY_MAX_CHARS)


def build_continuity_prompt(shots_summary: str) -> str:
    config = load_prompt_config()
    schema = _schema_from_fields(config["continuity_fields"])
    parts = [
        config.get("continuity_role", "你是一位专业的影视分析师。"),
        "镜头数据：",
        shots_summary,
    ]
    extra = config.get("continuity_extra_instructions")
    if extra:
        parts.append(str(extra))
    parts.extend([
        config.get("continuity_output_instruction", "直接输出 JSON，不加代码块："),
        json.dumps(schema, ensure_ascii=False, indent=2),
        "字段要求：",
        "\n".join(_field_lines(config["continuity_fields"])),
    ])
    return "\n\n".join(parts)
