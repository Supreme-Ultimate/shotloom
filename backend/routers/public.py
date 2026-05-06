from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from database import SessionLocal, Video
from services.signed_video_url import verify_signed_video_token
from services.video_path import resolve_video_path

router = APIRouter(prefix="/api/public", tags=["public"])

_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}


def _iter_range(path: Path, start: int, end: int):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        chunk_size = 1024 * 1024
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/video/{token}")
def stream_signed_video(token: str, request: Request):
    try:
        payload = verify_signed_video_token(token)
    except ValueError as exc:
        raise HTTPException(403, str(exc))

    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == int(payload["video_id"])).first()
        if not video:
            raise HTTPException(404, "视频不存在")
        path = resolve_video_path(video.filepath)
        if not path.exists():
            raise HTTPException(404, "视频文件不存在")

        media_type = _MEDIA_TYPES.get(path.suffix.lower(), "video/mp4")
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=0, no-store",
        }
        file_size = path.stat().st_size
        range_header = request.headers.get("range")
        if range_header:
            import re
            match = re.search(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else file_size - 1
                end = min(end, file_size - 1)
                headers.update({
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(end - start + 1),
                })
                return StreamingResponse(_iter_range(path, start, end), status_code=206, media_type=media_type, headers=headers)

        headers["Content-Length"] = str(file_size)
        return FileResponse(str(path), media_type=media_type, headers=headers)
    finally:
        db.close()
