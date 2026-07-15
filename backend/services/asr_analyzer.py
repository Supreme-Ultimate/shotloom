"""Qwen file-transcription ASR and deterministic shot-time mapping."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import config as app_config

from config import (
    ASR_API_BASE_URL,
    ASR_MODEL_NAME,
    ASR_POLL_INTERVAL_SECONDS,
    ASR_POLL_TIMEOUT_SECONDS,
    ASR_SIGNED_URL_EXPIRE_SECONDS,
    DASHSCOPE_API_KEY,
)
from database import SessionLocal, Video, VideoTranscript
from services.signed_video_url import build_signed_video_url


def _headers(async_request: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}", "Content-Type": "application/json"}
    if async_request:
        headers["X-DashScope-Async"] = "enable"
    return headers


def _extract_task_id(payload: dict[str, Any]) -> str:
    task_id = (payload.get("output") or {}).get("task_id") or payload.get("task_id")
    if not task_id:
        raise ValueError(f"ASR 未返回 task_id: {payload}")
    return str(task_id)


def _task_status(payload: dict[str, Any]) -> str:
    return str((payload.get("output") or {}).get("task_status") or payload.get("task_status") or "").upper()


def _transcription_url(payload: dict[str, Any]) -> str:
    output = payload.get("output") or {}
    result = output.get("result") or {}
    url = result.get("transcription_url")
    if not url:
        raise ValueError(f"ASR 完成但缺少 transcription_url: {payload}")
    return str(url)


async def ensure_video_transcript(video_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        cached = db.query(VideoTranscript).filter(VideoTranscript.video_id == video_id).first()
        if cached and cached.model == ASR_MODEL_NAME and cached.status == "completed" and cached.result:
            return cached.result
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise ValueError("视频不存在")
        if not DASHSCOPE_API_KEY:
            raise ValueError("未配置 DASHSCOPE_API_KEY，无法运行ASR")
        if not app_config.PUBLIC_VIDEO_BASE_URL:
            raise ValueError("未配置 PUBLIC_VIDEO_BASE_URL，Qwen ASR 无法读取原视频")
        row = cached or VideoTranscript(video_id=video_id, model=ASR_MODEL_NAME, status="pending")
        row.model = ASR_MODEL_NAME
        row.status = "pending"
        row.error_message = None
        if not cached:
            db.add(row)
        db.commit()

        file_url = build_signed_video_url(
            video_id,
            app_config.PUBLIC_VIDEO_BASE_URL,
            expires_in=ASR_SIGNED_URL_EXPIRE_SECONDS,
        )
        payload = {
            "model": ASR_MODEL_NAME,
            "input": {"file_url": file_url},
            "parameters": {"channel_id": [0], "enable_itn": True, "enable_words": True},
        }
        timeout = httpx.Timeout(60.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{ASR_API_BASE_URL}/services/audio/asr/transcription",
                headers=_headers(async_request=True),
                json=payload,
            )
            response.raise_for_status()
            task_id = _extract_task_id(response.json())
            row.provider_task_id = task_id
            row.status = "running"
            db.commit()

            deadline = time.monotonic() + ASR_POLL_TIMEOUT_SECONDS
            task_payload: dict[str, Any] = {}
            while time.monotonic() < deadline:
                await asyncio.sleep(max(1.0, ASR_POLL_INTERVAL_SECONDS))
                status_response = await client.get(
                    f"{ASR_API_BASE_URL}/tasks/{task_id}",
                    headers=_headers(),
                )
                status_response.raise_for_status()
                task_payload = status_response.json()
                status = _task_status(task_payload)
                if status == "SUCCEEDED":
                    break
                if status in {"FAILED", "CANCELED", "CANCELLED", "UNKNOWN"}:
                    raise ValueError(f"ASR任务失败: {task_payload}")
            else:
                raise TimeoutError("ASR任务等待超时")

            result_response = await client.get(_transcription_url(task_payload))
            result_response.raise_for_status()
            result = result_response.json()

        row.status = "completed"
        row.result = result
        row.usage = task_payload.get("usage") or (task_payload.get("output") or {}).get("usage")
        transcripts = result.get("transcripts") or []
        first_transcript = transcripts[0] if transcripts else {}
        first_sentence = ((first_transcript.get("sentences") or [None])[0] if transcripts else None) or {}
        row.language = first_transcript.get("language") or first_sentence.get("language")
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        row = db.query(VideoTranscript).filter(VideoTranscript.video_id == video_id).first()
        if row:
            row.status = "failed"
            row.error_message = str(exc)
            db.commit()
        raise
    finally:
        db.close()


def transcript_sentences(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    sentences: list[dict[str, Any]] = []
    for transcript in (result or {}).get("transcripts") or []:
        transcript_language = transcript.get("language")
        for sentence in transcript.get("sentences") or []:
            try:
                start = int(sentence.get("begin_time"))
                end = int(sentence.get("end_time"))
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            sentences.append({
                "start_ms": start,
                "end_ms": end,
                "text": str(sentence.get("text") or "").strip(),
                "emotion": sentence.get("emotion"),
                "language": sentence.get("language") or transcript_language,
                "words": sentence.get("words") or [],
            })
    return sorted(sentences, key=lambda item: (item["start_ms"], item["end_ms"]))


def transcript_for_range(result: dict[str, Any] | None, start_seconds: float, end_seconds: float) -> list[dict[str, Any]]:
    range_start = int(round(start_seconds * 1000))
    range_end = int(round(end_seconds * 1000))
    segments: list[dict[str, Any]] = []
    for sentence in transcript_sentences(result):
        words = []
        for word in sentence["words"]:
            try:
                word_start = int(word.get("begin_time"))
                word_end = int(word.get("end_time"))
            except (TypeError, ValueError):
                continue
            if min(word_end, range_end) > max(word_start, range_start):
                words.append({"start_ms": word_start, "end_ms": word_end, "text": str(word.get("text") or "")})
        if words:
            segments.append({
                "start_ms": max(range_start, words[0]["start_ms"]),
                "end_ms": min(range_end, words[-1]["end_ms"]),
                "text": "".join(word["text"] for word in words).strip(),
                "emotion": sentence.get("emotion"),
                "language": sentence.get("language"),
            })
        elif min(sentence["end_ms"], range_end) > max(sentence["start_ms"], range_start):
            segments.append({
                "start_ms": max(range_start, sentence["start_ms"]),
                "end_ms": min(range_end, sentence["end_ms"]),
                "text": sentence["text"],
                "emotion": sentence.get("emotion"),
                "language": sentence.get("language"),
                "precision": "sentence_overlap",
            })
    return [segment for segment in segments if segment.get("text")]


def transcript_prompt(segments: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{item['start_ms'] / 1000:.3f}s-{item['end_ms'] / 1000:.3f}s {item['text']}"
        for item in segments
    )


def inject_asr_fields(analysis: dict[str, Any], segments: list[dict[str, Any]], start_seconds: float, end_seconds: float) -> None:
    content = analysis.setdefault("content", {})
    content["time_evidence"] = f"{start_seconds:.3f}s-{end_seconds:.3f}s"
    speech = analysis.setdefault("speech", {})
    speech["transcript_segments"] = segments
    speech["transcript"] = "".join(item["text"] for item in segments) or "无"
    languages = list(dict.fromkeys(str(item["language"]) for item in segments if item.get("language")))
    emotions = list(dict.fromkeys(str(item["emotion"]) for item in segments if item.get("emotion")))
    speech["language"] = "、".join(languages)
    speech["speech_emotion"] = "、".join(emotions)
