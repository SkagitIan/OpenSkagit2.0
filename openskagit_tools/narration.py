"""ElevenLabs timestamped narration generation and timing normalization."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .cloudinary_service import upload_generated_asset

logger = logging.getLogger(__name__)

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
NARRATION_STYLE_VERSION = os.environ.get("OPENSKAGIT_NARRATION_STYLE_VERSION", "1")
DEFAULT_MODEL = os.environ.get("ELEVEN_LABS_MODEL", "eleven_multilingual_v2")
DEFAULT_FORMAT = os.environ.get("ELEVEN_LABS_OUTPUT_FORMAT", "mp3_44100_128")
MAX_TEXT_LENGTH = int(os.environ.get("ELEVEN_LABS_MAX_TEXT_LENGTH", "10000"))
STYLE_SETTINGS = {"explainer": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}}


class NarrationError(RuntimeError):
    """A safe ElevenLabs generation failure."""


def _voice_id(voice_id: str | None, voice: str | None) -> tuple[str, str]:
    profiles = {
        "default": os.environ.get("ELEVEN_LABS_DEFAULT_VOICE_ID", ""),
        "explainer": os.environ.get("ELEVEN_LABS_EXPLAINER_VOICE_ID", ""),
        "short_form": os.environ.get("ELEVEN_LABS_SHORT_FORM_VOICE_ID", ""),
    }
    selected_name = voice or ("explainer" if not voice_id else "custom")
    selected_id = voice_id or profiles.get(selected_name, "")
    if not selected_id:
        raise ValueError(
            "No ElevenLabs voice is configured. Supply voice_id or configure ELEVEN_LABS_DEFAULT_VOICE_ID."
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", selected_id):
        raise ValueError("voice_id must be a valid ElevenLabs voice identifier.")
    return selected_id, selected_name


def _alignment_timings(
    text: str, alignment: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, list[str]]:
    warnings: list[str] = []
    if not alignment:
        return (
            [],
            [],
            0.0,
            ["ElevenLabs returned no character alignment; audio is not suitable for precise synchronization."],
        )
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    count = min(len(chars), len(starts), len(ends), len(text))
    if count == 0:
        return [], [], 0.0, ["ElevenLabs returned malformed character alignment."]
    if count != len(chars) or count != len(text):
        warnings.append(
            "Character alignment length differs from the requested script; timings cover the aligned prefix."
        )
    character_alignment = [
        {"character": text[i], "start": float(starts[i]), "end": float(ends[i])} for i in range(count)
    ]
    words: list[dict[str, Any]] = []
    for match in re.finditer(r"\S+", text[:count]):
        begin, finish = match.span()
        aligned = character_alignment[begin:finish]
        if aligned:
            words.append({"word": match.group(0), "start": aligned[0]["start"], "end": aligned[-1]["end"]})
    segments: list[dict[str, Any]] = []
    for match in re.finditer(r".+?(?:[.!?]+(?:\s+|$)|\n+|$)", text[:count], re.S):
        segment_text = match.group(0).strip()
        if not segment_text:
            continue
        begin = match.start() + len(match.group(0)) - len(match.group(0).lstrip())
        finish = match.end() - len(match.group(0)) + len(match.group(0).rstrip())
        aligned = character_alignment[max(0, begin) : min(count, finish)]
        if aligned:
            segments.append({"text": segment_text, "start": aligned[0]["start"], "end": aligned[-1]["end"]})
    duration = max((item["end"] for item in character_alignment), default=0.0)
    return character_alignment, words, duration, warnings


def generate_narration(
    text: str,
    voice_id: str | None = None,
    voice: str | None = None,
    style: str = "explainer",
    output_format: str = DEFAULT_FORMAT,
    model: str = DEFAULT_MODEL,
    title: str = "",
    force_regenerate: bool = False,
) -> dict[str, Any]:
    script = (text or "").strip()
    if not script:
        raise ValueError("Narration text is required.")
    if len(script) > MAX_TEXT_LENGTH:
        raise ValueError(f"Narration text exceeds the configured {MAX_TEXT_LENGTH:,}-character limit.")
    if style not in STYLE_SETTINGS:
        raise ValueError(f"Unsupported narration style {style!r}. Use one of: {', '.join(STYLE_SETTINGS)}.")
    selected_voice, voice_name = _voice_id(voice_id, voice)
    api_key = os.environ.get("ELEVEN_LABS_API_KEY", "").strip()
    if not api_key:
        raise NarrationError("ElevenLabs API configuration is missing.")
    identity = {
        "text": script,
        "voice_id": selected_voice,
        "model": model,
        "style": style,
        "output_format": output_format,
        "style_version": NARRATION_STYLE_VERSION,
    }
    if force_regenerate:
        identity["regeneration_nonce"] = str(time.time_ns())
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    payload = {
        "text": script,
        "model_id": model,
        "output_format": output_format,
        "voice_settings": STYLE_SETTINGS[style],
    }
    logger.info(
        "narration_request", extra={"text_length": len(script), "voice": voice_name, "model": model, "style": style}
    )
    try:
        response = requests.post(
            f"{ELEVENLABS_URL}/{selected_voice}/with-timestamps",
            params={"output_format": output_format},
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={key: value for key, value in payload.items() if key != "output_format"},
            timeout=90,
        )
    except requests.RequestException as exc:
        raise NarrationError("ElevenLabs request failed due to a network error.") from exc
    if response.status_code in {401, 403}:
        raise NarrationError("ElevenLabs authentication failed.")
    if response.status_code == 429:
        raise NarrationError("ElevenLabs rate limit or quota was reached.")
    if response.status_code >= 400:
        raise NarrationError(f"ElevenLabs generation failed with HTTP {response.status_code}.")
    try:
        provider = response.json()
        audio = base64.b64decode(provider["audio_base64"])
    except (ValueError, KeyError, TypeError) as exc:
        raise NarrationError("ElevenLabs returned a malformed timestamped audio response.") from exc
    characters, words, duration, warnings = _alignment_timings(script, provider.get("alignment"))
    cloud = upload_generated_asset(
        audio,
        asset_type="narration",
        digest=digest,
        source_property_ids=[],
        metadata={
            "asset_type": "narration",
            "voice_id": selected_voice,
            "model": model,
            "style": style,
            "style_version": NARRATION_STYLE_VERSION,
            "duration": str(duration),
        },
        content_type="audio/mpeg",
        resource_type="video",
    )
    result = {
        "success": True,
        "tool_name": "generate_narration",
        "asset_id": f"narration_{digest}",
        "asset_type": "narration",
        "cloudinary_public_id": cloud["cloudinary_public_id"],
        "audio_url": cloud["secure_url"],
        "secure_url": cloud["secure_url"],
        "resource_type": "video",
        "format": cloud.get("format") or output_format.split("_", 1)[0],
        "duration": duration or cloud.get("duration"),
        "original_script": script,
        "aligned_transcript": provider.get("normalized_alignment", {}).get("characters")
        and "".join(provider["normalized_alignment"]["characters"]),
        "voice_id": selected_voice,
        "voice": voice_name,
        "model": model,
        "style": style,
        "narration_style_version": NARRATION_STYLE_VERSION,
        "source_dataset": "elevenlabs_timestamped_tts",
        "source_hash": digest,
        "provenance": {
            "provider": "elevenlabs",
            "cloudinary_resource_type": "video",
            "style_version": NARRATION_STYLE_VERSION,
        },
        "cached": cloud["cached"],
        "character_alignment": characters,
        "word_timings": words,
        "segments": _segments_from_words(script, words),
        "warnings": warnings,
        "generated_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": title or f"Timestamped {style} narration generated from the approved script.",
    }
    logger.info(
        "narration_generated", extra={"asset_id": result["asset_id"], "duration": duration, "cached": cloud["cached"]}
    )
    return result


def _segments_from_words(text: str, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    cursor = 0
    for match in re.finditer(r".+?(?:[.!?]+(?:\s+|$)|\n+|$)", text, re.S):
        segment = match.group(0).strip()
        if not segment:
            continue
        token_count = len(re.findall(r"\S+", segment))
        relevant = words[cursor : cursor + token_count]
        if relevant:
            segments.append({"text": segment, "start": relevant[0]["start"], "end": relevant[-1]["end"]})
            cursor += len(relevant)
    return segments
