"""Helpers for resolving persisted video paths across deployment layouts."""
from pathlib import Path

from config import UPLOADS_DIR


def resolve_video_path(filepath: str) -> Path:
    """Return an existing video path, falling back to the configured uploads dir.

    Older rows may contain absolute paths from a previous deployment directory,
    while the actual upload files live in the shared uploads volume.
    """
    path = Path(filepath)
    if path.exists():
        return path

    fallback = UPLOADS_DIR / path.name
    if fallback.exists():
        return fallback

    return path
