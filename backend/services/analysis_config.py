"""Versioned, user-editable analysis schemas and per-video snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Callable, Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import AnalysisPreset, Shot, VideoAnalysis, VideoAnalysisConfig
from prompt_config import load_prompt_config

SCHEMA_VERSION = 2
FIELD_TYPES = {"string", "number", "boolean", "string_array", "object", "object_array"}
FIELD_SOURCES = {"vision", "asr", "computed"}
RESERVED_KEYS = {
    "error", "analysis_source", "analysis_mode", "shot_indices", "shot_index",
    "segment_index", "transcript_assignment", "context_shot_summaries",
}
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SCOPE_LIMITS = {"shot": 80, "segment": 40, "overall": 40}
ALLOWED_ASR_FIELDS = {
    "shot.speech.transcript",
    "shot.speech.transcript_segments",
    "shot.speech.language",
    "shot.speech.speech_emotion",
}
ALLOWED_COMPUTED_FIELDS = {"shot.content.time_evidence"}


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_config() -> dict[str, Any]:
    return deepcopy(load_prompt_config())


def _validate_fields(fields: Any, path: str, depth: int = 1) -> int:
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"{path} 必须是非空字段数组")
    if depth > 3:
        raise ValueError(f"{path} 最多支持三层嵌套")
    seen: set[str] = set()
    leaves = 0
    for index, field in enumerate(fields):
        field_path = f"{path}[{index}]"
        if not isinstance(field, dict):
            raise ValueError(f"{field_path} 必须是对象")
        key = str(field.get("key") or "")
        label = str(field.get("label") or "").strip()
        if not KEY_RE.fullmatch(key):
            raise ValueError(f"{field_path}.key 只能使用小写字母、数字和下划线，并以字母开头")
        if key in RESERVED_KEYS:
            raise ValueError(f"{field_path}.key 使用了系统保留字段 {key}")
        if key in seen:
            raise ValueError(f"{path} 存在重复 key: {key}")
        seen.add(key)
        if not label or len(label) > 40:
            raise ValueError(f"{field_path}.label 长度必须为 1-40")
        children = field.get("fields")
        if "fields" in field:
            if not children:
                raise ValueError(f"{field_path}.fields 必须是非空字段数组")
            leaves += _validate_fields(children, f"{field_path}.fields", depth + 1)
            continue
        field_type = field.get("type", "string")
        source = field.get("source", "vision")
        if field_type not in FIELD_TYPES:
            raise ValueError(f"{field_path}.type 不支持: {field_type}")
        if source not in FIELD_SOURCES:
            raise ValueError(f"{field_path}.source 不支持: {source}")
        description = str(field.get("description") or "")
        if len(description) > 500:
            raise ValueError(f"{field_path}.description 不能超过 500 字")
        leaves += 1
    return leaves


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("配置必须是 JSON 对象")
    if int(config.get("version") or 0) != SCHEMA_VERSION:
        raise ValueError(f"配置 version 必须为 {SCHEMA_VERSION}")
    scopes = config.get("scopes")
    if not isinstance(scopes, dict):
        raise ValueError("配置缺少 scopes")
    for scope, limit in SCOPE_LIMITS.items():
        leaves = _validate_fields(scopes.get(scope), f"scopes.{scope}")
        if leaves > limit:
            raise ValueError(f"{scope} 叶子字段最多 {limit} 个，当前 {leaves} 个")
        for field_path, field in iter_leaf_fields(scopes[scope]):
            qualified_path = f"{scope}.{field_path}"
            if field.get("source", "vision") == "asr" and qualified_path not in ALLOWED_ASR_FIELDS:
                raise ValueError(f"{qualified_path} 不是系统支持的 ASR 字段")
            if field.get("source", "vision") == "computed" and qualified_path not in ALLOWED_COMPUTED_FIELDS:
                raise ValueError(f"{qualified_path} 不是系统支持的计算字段")
    prompts = config.get("prompts") or {}
    if not isinstance(prompts, dict):
        raise ValueError("prompts 必须是对象")
    for key, value in prompts.items():
        if len(str(value)) > 4000:
            raise ValueError(f"prompts.{key} 不能超过 4000 字")
    return deepcopy(config)


def iter_leaf_fields(fields: Iterable[dict[str, Any]], prefix: str = ""):
    for field in fields:
        path = f"{prefix}.{field['key']}" if prefix else field["key"]
        children = field.get("fields") or []
        if children:
            yield from iter_leaf_fields(children, path)
        else:
            yield path, field


def scope_fields(config: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    return list((config.get("scopes") or {}).get(scope) or [])


def config_requires_asr(config: dict[str, Any]) -> bool:
    return any(
        field.get("source") == "asr"
        for scope in ("shot", "segment", "overall")
        for _, field in iter_leaf_fields(scope_fields(config, scope))
    )


def ensure_system_preset(db: Session) -> AnalysisPreset:
    preset = db.query(AnalysisPreset).filter(AnalysisPreset.is_system.is_(True)).first()
    config = validate_config(default_config())
    if preset:
        return preset
    preset = AnalysisPreset(
        name=config.get("name") or "短视频运营分析 v2",
        description=config.get("description"),
        schema_version=SCHEMA_VERSION,
        is_system=True,
        user_id=None,
    )
    preset.config = config
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


def get_or_create_video_config(video_id: int, db: Session) -> VideoAnalysisConfig:
    row = db.query(VideoAnalysisConfig).filter(VideoAnalysisConfig.video_id == video_id).first()
    if row:
        return row
    config = validate_config(default_config())
    row = VideoAnalysisConfig(
        video_id=video_id,
        draft_revision=1,
        draft_hash=config_hash(config),
    )
    row.draft_config = config
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def video_has_results(video_id: int, db: Session) -> bool:
    if db.query(Shot).filter(Shot.video_id == video_id, Shot._analysis.is_not(None)).first():
        return True
    return db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first() is not None


def video_config_is_dirty(video_id: int, row: VideoAnalysisConfig, db: Session) -> bool:
    """A draft only requires reanalysis when there are results tied to another/legacy snapshot."""
    if not video_has_results(video_id, db):
        return False
    return row.active_snapshot is None or row.active_hash != row.draft_hash


def activate_video_config(row: VideoAnalysisConfig, db: Session) -> dict[str, Any]:
    config = validate_config(row.draft_config)
    row.active_snapshot = config
    row.active_revision = row.draft_revision
    row.active_hash = row.draft_hash
    db.flush()
    return config


def require_analysis_config(
    video_id: int,
    requested_revision: int | None,
    replace_all: bool,
    db: Session,
    before_activate: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], bool]:
    row = get_or_create_video_config(video_id, db)
    if requested_revision is not None and requested_revision != row.draft_revision:
        raise HTTPException(409, detail={"code": "CONFIG_REVISION_CONFLICT", "current_revision": row.draft_revision})
    has_results = video_has_results(video_id, db)
    legacy_results = has_results and row.active_snapshot is None
    dirty = legacy_results or bool(row.active_hash and row.active_hash != row.draft_hash)
    if dirty and has_results and not replace_all:
        raise HTTPException(409, detail={"code": "CONFIG_CHANGED_REQUIRES_FULL_REANALYSIS"})
    activated = False
    should_activate = row.active_snapshot is None or (dirty and (replace_all or not has_results))
    target_config = row.draft_config if should_activate else row.active_snapshot
    if before_activate:
        before_activate(target_config)
    if should_activate:
        activate_video_config(row, db)
        activated = True
    return row.active_snapshot or row.draft_config, activated


def preset_payload(preset: AnalysisPreset) -> dict[str, Any]:
    return {
        "id": preset.id,
        "name": preset.name,
        "description": preset.description,
        "schema_version": preset.schema_version,
        "is_system": preset.is_system,
        "config": preset.config,
        "updated_at": preset.updated_at.isoformat() if preset.updated_at else None,
    }
