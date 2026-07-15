"""Analysis presets and per-video editable configuration."""
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import AnalysisPreset, User, get_db
from permissions import get_video_for_user
from services.analysis_config import (
    config_hash,
    ensure_system_preset,
    get_or_create_video_config,
    preset_payload,
    validate_config,
    video_config_is_dirty,
    video_has_results,
)

router = APIRouter(prefix="/api", tags=["analysis-config"])


class ConfigBody(BaseModel):
    config: dict[str, Any]


class VideoConfigBody(ConfigBody):
    revision: int


class PresetBody(ConfigBody):
    name: str
    description: str | None = None


def _owned_preset(preset_id: int, user: User, db: Session) -> AnalysisPreset:
    preset = db.query(AnalysisPreset).filter(AnalysisPreset.id == preset_id).first()
    if not preset:
        raise HTTPException(404, "模板不存在")
    if preset.user_id != user.id or preset.is_system:
        raise HTTPException(403, "无权修改该模板")
    return preset


def _validated_config(config: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_config(config)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


def _validated_name(name: str) -> str:
    value = name.strip()
    if not value or len(value) > 80:
        raise HTTPException(400, "模板名称长度必须为 1-80")
    return value


@router.get("/analysis-presets")
def list_presets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ensure_system_preset(db)
    rows = (
        db.query(AnalysisPreset)
        .filter((AnalysisPreset.is_system.is_(True)) | (AnalysisPreset.user_id == current_user.id))
        .order_by(AnalysisPreset.is_system.desc(), AnalysisPreset.updated_at.desc())
        .all()
    )
    return [preset_payload(row) for row in rows]


@router.post("/analysis-presets")
def create_preset(body: PresetBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    name = _validated_name(body.name)
    config = _validated_config(body.config)
    row = AnalysisPreset(
        user_id=current_user.id,
        name=name,
        description=(body.description or "").strip() or None,
        schema_version=int(config["version"]),
        is_system=False,
    )
    row.config = config
    db.add(row)
    db.commit()
    db.refresh(row)
    return preset_payload(row)


@router.put("/analysis-presets/{preset_id}")
def update_preset(preset_id: int, body: PresetBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = _owned_preset(preset_id, current_user, db)
    row.name = _validated_name(body.name)
    row.description = (body.description or "").strip() or None
    row.config = _validated_config(body.config)
    row.schema_version = int(row.config["version"])
    db.commit()
    db.refresh(row)
    return preset_payload(row)


@router.delete("/analysis-presets/{preset_id}")
def delete_preset(preset_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = _owned_preset(preset_id, current_user, db)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/videos/{video_id}/analysis-config")
def get_video_analysis_config(video_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_video_for_user(video_id, current_user, db)
    row = get_or_create_video_config(video_id, db)
    return {
        "draft_config": row.draft_config,
        "active_snapshot": row.active_snapshot,
        "draft_revision": row.draft_revision,
        "active_revision": row.active_revision,
        "dirty": video_config_is_dirty(video_id, row, db),
        "has_results": video_has_results(video_id, db),
    }


@router.put("/videos/{video_id}/analysis-config")
def save_video_analysis_config(video_id: int, body: VideoConfigBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_video_for_user(video_id, current_user, db)
    config = _validated_config(body.config)
    row = get_or_create_video_config(video_id, db)
    if body.revision != row.draft_revision:
        raise HTTPException(409, detail={"code": "CONFIG_REVISION_CONFLICT", "current_revision": row.draft_revision})
    row.draft_config = config
    row.draft_revision += 1
    row.draft_hash = config_hash(config)
    db.commit()
    return {"ok": True, "draft_revision": row.draft_revision, "dirty": video_config_is_dirty(video_id, row, db)}


@router.post("/videos/{video_id}/analysis-config/apply-preset/{preset_id}")
def apply_preset(
    video_id: int,
    preset_id: int,
    expected_revision: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_video_for_user(video_id, current_user, db)
    preset = db.query(AnalysisPreset).filter(AnalysisPreset.id == preset_id).first()
    if not preset or (not preset.is_system and preset.user_id != current_user.id):
        raise HTTPException(404, "模板不存在")
    row = get_or_create_video_config(video_id, db)
    if expected_revision != row.draft_revision:
        raise HTTPException(409, detail={"code": "CONFIG_REVISION_CONFLICT", "current_revision": row.draft_revision})
    config = _validated_config(deepcopy(preset.config))
    row.draft_config = config
    row.draft_revision += 1
    row.draft_hash = config_hash(config)
    db.commit()
    return {"ok": True, "draft_config": config, "draft_revision": row.draft_revision, "dirty": video_config_is_dirty(video_id, row, db)}


@router.post("/analysis-presets/from-video/{video_id}")
def save_video_as_preset(video_id: int, body: PresetBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_video_for_user(video_id, current_user, db)
    row = get_or_create_video_config(video_id, db)
    return create_preset(
        PresetBody(name=body.name, description=body.description, config=row.draft_config),
        db,
        current_user,
    )
