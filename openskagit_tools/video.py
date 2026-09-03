"""Deterministic, carrier-free video production from an editorial manifest.

The public operation remains ``generate_video``. Internally it has two retryable
stages: prepare an immutable local bundle, then render, QA, upload, and catalog a
real MP4. Cloudinary is the delivery layer, not the compositor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .cloudinary_service import delivery_url, upload_generated_asset

logger = logging.getLogger(__name__)

VIDEO_RENDER_VERSION = os.environ.get("OPENSKAGIT_VIDEO_RENDER_VERSION", "3")
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
SCENE_TYPES = {"DATA_FULL_FRAME", "MEDIA_FULL_FRAME", "MEDIA_WITH_DATA_CARD", "SPLIT_COMPARE"}
PLACEMENTS = {"top", "center", "bottom"}
STYLES = {"headline", "value", "label", "callout"}
TIMING_TOLERANCE = float(os.environ.get("OPENSKAGIT_VIDEO_TIMING_TOLERANCE", "0.25"))
MAX_DOWNLOAD_BYTES = int(os.environ.get("OPENSKAGIT_VIDEO_MAX_INPUT_BYTES", str(150 * 1024 * 1024)))


class VideoManifestError(ValueError):
    """A safe, actionable production-manifest validation failure."""


class VideoRenderError(RuntimeError):
    """A safe local composition or technical-QA failure."""


def _number(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise VideoManifestError(f"{name} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VideoManifestError(f"{name} must be a number.") from exc
    if number < minimum:
        raise VideoManifestError(f"{name} must be at least {minimum}.")
    return number


def _asset_reference(reference: Any, name: str) -> dict[str, str]:
    if isinstance(reference, str):
        public_id, url, local_path = reference, "", ""
    elif isinstance(reference, dict):
        public_id = reference.get("cloudinary_public_id") or reference.get("public_id") or ""
        url = reference.get("secure_url") or reference.get("audio_url") or reference.get("png_url") or reference.get("url") or ""
        local_path = reference.get("local_path") or ""
    else:
        public_id = url = local_path = ""
    public_id, url, local_path = str(public_id).strip(), str(url).strip(), str(local_path).strip()
    if not public_id and not url and not local_path:
        raise VideoManifestError(f"{name} requires a Cloudinary public ID, URL, or local path.")
    if public_id and any(token in public_id for token in ("?", "&", "#", "\\", "%")):
        raise VideoManifestError(f"{name} contains unsupported asset-ID characters.")
    if url and not re.match(r"^https?://", url, re.I):
        raise VideoManifestError(f"{name} URL must use HTTP or HTTPS.")
    return {"public_id": public_id, "url": url, "local_path": local_path}


def _caption_chunks(narration: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for segment in narration.get("segments") or []:
        words = str(segment.get("text", "")).strip().split()
        if not words:
            continue
        start, end = float(segment.get("start", 0)), float(segment.get("end", 0))
        span = max(end - start, 0.05)
        for offset in range(0, len(words), 6):
            group = words[offset : offset + 6]
            chunks.append({"text": " ".join(group), "start": start + span * offset / len(words), "end": start + span * (offset + len(group)) / len(words)})
    return chunks


def _timestamp(seconds: float) -> str:
    millis = int(round(max(0, seconds) * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d},{milliseconds:03d}"


def _caption_text(narration: dict[str, Any]) -> str:
    lines: list[str] = []
    for index, chunk in enumerate(_caption_chunks(narration), 1):
        if chunk["end"] > chunk["start"]:
            lines.extend([str(index), f"{_timestamp(chunk['start'])} --> {_timestamp(chunk['end'])}", chunk["text"], ""])
    return "\n".join(lines)


def _ass_time(seconds: float) -> str:
    millis = int(round(max(0, seconds) * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours}:{minutes:02d}:{secs:02d}.{millis // 10:02d}"


def _ass_escape(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _ass_text(normalized: dict[str, Any], narration: dict[str, Any]) -> str:
    width, height = normalized["width"], normalized["height"]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Caption,Arial,48,&H00FFFFFF,&H00FFFFFF,&H001A3207,&HC0071A2D,-1,0,0,0,100,100,0,0,3,4,0,2,70,70,220,1",
        "Style: Overlay,Arial,58,&H00FFFFFF,&H00FFFFFF,&H00183238,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,5,80,80,80,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if normalized["captions"]:
        for chunk in _caption_chunks(narration):
            if chunk["end"] > chunk["start"]:
                lines.append(f"Dialogue: 0,{_ass_time(chunk['start'])},{_ass_time(chunk['end'])},Caption,,0,0,0,,{_ass_escape(chunk['text'])}")
    positions = {"top": rf"{{\an8\pos({width // 2},180)}}", "center": rf"{{\an5\pos({width // 2},{height // 2})}}", "bottom": rf"{{\an2\pos({width // 2},{height - 360})}}"}
    for scene in normalized["scenes"]:
        for overlay in scene["overlays"]:
            start = scene["start"] + overlay["start_offset"]
            end = start + overlay["duration"]
            text = positions[overlay["placement"]] + _ass_escape(overlay["text"])
            lines.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Overlay,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise VideoManifestError("manifest must be an object.")
    if manifest.get("base_video"):
        raise VideoManifestError("base_video/carrier assets are not used; scenes define the complete visual timeline.")
    if manifest.get("background_audio"):
        raise VideoManifestError("background_audio is not supported by the deterministic renderer yet.")
    aspect = manifest.get("aspect_ratio", "16:9")
    if aspect not in ASPECTS:
        raise VideoManifestError("aspect_ratio must be '16:9' or '9:16'.")
    width, height = ASPECTS[aspect]
    if manifest.get("width", width) != width or manifest.get("height", height) != height:
        raise VideoManifestError(f"{aspect} output dimensions must be {width}x{height}.")
    narration = manifest.get("narration")
    if not isinstance(narration, dict):
        raise VideoManifestError("manifest requires an existing narration result.")
    narration_ref = _asset_reference(narration, "narration")
    narration_duration = _number(narration.get("duration"), "narration.duration", minimum=0.01)
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise VideoManifestError("manifest requires at least one scene.")
    timeline: list[dict[str, Any]] = []
    cursor = 0.0
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise VideoManifestError(f"scene {index} must be an object.")
        scene_type = scene.get("scene_type", "DATA_FULL_FRAME")
        if scene_type not in SCENE_TYPES:
            raise VideoManifestError(f"scene {index}.scene_type is unsupported.")
        if scene.get("asset") is not None and scene.get("primary_asset") is not None:
            raise VideoManifestError(f"scene {index} must define one primary visual, not asset and primary_asset.")
        if any(scene.get(key) for key in ("background_video", "background_asset")):
            raise VideoManifestError(f"scene {index} cannot contain a background carrier asset.")
        if scene.get("motion", "none") != "none":
            raise VideoManifestError(f"scene {index}.motion must be 'none' for deterministic render version {VIDEO_RENDER_VERSION}.")
        if scene.get("transition", "cut") != "cut":
            raise VideoManifestError(f"scene {index}.transition must be 'cut' for deterministic render version {VIDEO_RENDER_VERSION}.")
        duration = _number(scene.get("duration"), f"scene {index}.duration", minimum=0.05)
        start = _number(scene.get("start", cursor), f"scene {index}.start")
        if abs(start - cursor) > TIMING_TOLERANCE:
            raise VideoManifestError(f"scene {index}.start is not contiguous with the previous scene.")
        reference = _asset_reference(scene.get("primary_asset") or scene.get("asset") or scene.get("asset_id"), f"scene {index}.primary_asset")
        overlays = scene.get("overlays", [])
        if not isinstance(overlays, list):
            raise VideoManifestError(f"scene {index}.overlays must be a list.")
        normalized_overlays = []
        for overlay_index, overlay in enumerate(overlays, 1):
            if not isinstance(overlay, dict) or not str(overlay.get("text", "")).strip():
                raise VideoManifestError(f"scene {index} overlay {overlay_index} requires text.")
            offset = _number(overlay.get("start_offset", 0), "overlay.start_offset")
            overlay_duration = _number(overlay.get("duration", duration - offset), "overlay.duration", minimum=0.01)
            if offset + overlay_duration > duration + TIMING_TOLERANCE:
                raise VideoManifestError(f"scene {index} overlay {overlay_index} exceeds scene duration.")
            placement, style = overlay.get("placement", "bottom"), overlay.get("style", "label")
            if placement not in PLACEMENTS or style not in STYLES:
                raise VideoManifestError(f"scene {index} overlay {overlay_index} has unsupported placement/style.")
            normalized_overlays.append({"text": str(overlay["text"]).strip(), "start_offset": offset, "duration": overlay_duration, "placement": placement, "style": style})
        timeline.append({"id": str(scene.get("id") or f"scene_{index:02d}"), "scene_type": scene_type, "asset": reference, "start": round(start, 3), "end": round(start + duration, 3), "duration": round(duration, 3), "motion": "none", "transition": "cut", "overlays": normalized_overlays, "provenance": scene.get("provenance", []), "cue_ids": scene.get("cue_ids", [])})
        cursor = start + duration
    difference = abs(cursor - narration_duration)
    warnings: list[str] = []
    if difference > TIMING_TOLERANCE:
        raise VideoManifestError(f"Scene total {cursor:.2f}s differs from narration duration {narration_duration:.2f}s by more than {TIMING_TOLERANCE:.2f}s.")
    if difference:
        timeline[-1]["duration"] = round(timeline[-1]["duration"] + narration_duration - cursor, 3)
        timeline[-1]["end"] = round(narration_duration, 3)
        warnings.append("Final scene duration was adjusted to match narration within the timing tolerance.")
    return {"episode_id": _slug(manifest.get("episode_id") or manifest.get("project") or manifest.get("title") or "house-video"), "project": str(manifest.get("project") or manifest.get("title") or "House video"), "title": str(manifest.get("title") or "House video"), "description": str(manifest.get("description") or ""), "aspect_ratio": aspect, "width": width, "height": height, "scenes": timeline, "narration": narration, "narration_ref": narration_ref, "narration_duration": narration_duration, "captions": bool(manifest.get("captions", True)), "metadata": manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}, "timing_cues": manifest.get("timing_cues", []), "render_version": VIDEO_RENDER_VERSION, "warnings": warnings}


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", str(value).lower()).strip("-")[:100] or "house-video"


def _render_root(root: str | Path | None = None) -> Path:
    return Path(root or os.environ.get("HOUSE_CONTENT_RENDER_ROOT", Path.cwd() / "output" / "house_content" / "renders"))


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")
    temporary.replace(path)


def _source_url(reference: dict[str, str], *, image: bool) -> str:
    if reference["url"]:
        return reference["url"]
    if image:
        return delivery_url(reference["public_id"], resource_type="image", transformation="f_png,q_auto", fmt="png")
    return delivery_url(reference["public_id"], resource_type="video")


def _download(reference: dict[str, str], target: Path, *, image: bool) -> None:
    if reference["local_path"]:
        source = Path(reference["local_path"])
        if not source.is_file():
            raise VideoRenderError(f"Prepared input does not exist: {source.name}.")
        shutil.copyfile(source, target)
        return
    try:
        with requests.get(_source_url(reference, image=image), stream=True, timeout=60) as response:
            if response.status_code >= 400:
                raise VideoRenderError(f"Could not retrieve a render input (HTTP {response.status_code}).")
            total = 0
            with target.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise VideoRenderError("A render input exceeded the configured size limit.")
                    handle.write(chunk)
    except requests.RequestException as exc:
        raise VideoRenderError("Could not retrieve a render input due to a network error.") from exc


def _catalog_episode(normalized: dict[str, Any], *, status: str, **changes: Any) -> None:
    from core.models import HouseContentEpisode
    defaults = {"title": normalized["title"], "description": normalized["description"], "status": status, "aspect_ratio": normalized["aspect_ratio"], "width": normalized["width"], "height": normalized["height"], "duration": normalized["narration_duration"], "manifest": normalized, "warnings": normalized["warnings"], "failure_reason": ""}
    defaults.update(changes)
    HouseContentEpisode.objects.update_or_create(episode_id=normalized["episode_id"], defaults=defaults)


def prepare_video(manifest: dict[str, Any], *, root: str | Path | None = None) -> dict[str, Any]:
    """Freeze remote inputs and timing into an immutable, retryable render bundle."""
    normalized = validate_manifest(manifest)
    identity = {key: value for key, value in normalized.items() if key != "warnings"}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20]
    directory = _render_root(root) / f"{normalized['episode_id']}_{digest}"
    bundle_path = directory / "bundle.json"
    if bundle_path.exists():
        cached = json.loads(bundle_path.read_text(encoding="utf-8"))
        cached["cached"] = True
        return cached
    directory.mkdir(parents=True, exist_ok=True)
    prepared_scenes = []
    for index, scene in enumerate(normalized["scenes"], 1):
        target = directory / f"scene_{index:03d}.png"
        _download(scene["asset"], target, image=True)
        prepared_scenes.append({**scene, "local_path": str(target.resolve())})
    audio_path = directory / "narration.audio"
    _download(normalized["narration_ref"], audio_path, image=False)
    (directory / "captions.srt").write_text(_caption_text(normalized["narration"]), encoding="utf-8")
    (directory / "captions.ass").write_text(_ass_text(normalized, normalized["narration"]), encoding="utf-8")
    bundle = {"bundle_id": digest, "episode_id": normalized["episode_id"], "directory": str(directory.resolve()), "manifest": normalized, "scenes": prepared_scenes, "audio_path": str(audio_path.resolve()), "caption_path": str((directory / "captions.ass").resolve()), "cached": False, "status": "prepared"}
    _write_json(bundle_path, bundle)
    _catalog_episode(normalized, status="prepared")
    return bundle


def _ffmpeg_executable() -> str:
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise VideoRenderError("FFmpeg is unavailable. Configure FFMPEG_BINARY or install imageio-ffmpeg.") from exc


def _run_ffmpeg(command: list[str], cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "")[-500:].replace("\n", " ").strip()
        raise VideoRenderError(f"FFmpeg composition failed: {detail}") from exc


def _inspect_video(path: Path) -> dict[str, Any]:
    try:
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
        metadata = next(reader)
        reader.close()
    except Exception as exc:
        raise VideoRenderError("The rendered MP4 could not be decoded for technical QA.") from exc
    width, height = metadata.get("size") or (None, None)
    return {"width": width, "height": height, "duration": float(metadata.get("duration") or 0), "audio_codec": metadata.get("audio_codec"), "video_codec": metadata.get("codec")}


def render_prepared_video(bundle: dict[str, Any]) -> dict[str, Any]:
    """Render, inspect, upload, and catalog one prepared bundle."""
    directory = Path(bundle["directory"])
    published_path = directory / "published.json"
    if published_path.exists():
        cached = json.loads(published_path.read_text(encoding="utf-8"))
        cached["cached"] = True
        _catalog_episode(
            bundle["manifest"], status="ready", cloudinary_public_id=cached["cloudinary_public_id"],
            video_url=cached["url"], thumbnail_url=cached.get("thumbnail_url", ""),
            duration=cached["duration"], qa_results=cached.get("qa_results", {}),
        )
        return cached
    normalized = bundle["manifest"]
    _catalog_episode(normalized, status="rendering")
    output = directory / "final.mp4"
    inputs: list[str] = []
    filters: list[str] = []
    for index, scene in enumerate(bundle["scenes"]):
        inputs.extend(["-loop", "1", "-t", str(scene["duration"]), "-i", scene["local_path"]])
        filters.append(f"[{index}:v]scale={normalized['width']}:{normalized['height']}:force_original_aspect_ratio=increase,crop={normalized['width']}:{normalized['height']},fps=30,trim=duration={scene['duration']},setpts=PTS-STARTPTS[v{index}]")
    audio_index = len(bundle["scenes"])
    inputs.extend(["-i", bundle["audio_path"]])
    filters.append("".join(f"[v{i}]" for i in range(len(bundle["scenes"]))) + f"concat=n={len(bundle['scenes'])}:v=1:a=0[sequence]")
    video_label = "sequence"
    if normalized["captions"] or any(scene["overlays"] for scene in bundle["scenes"]):
        filters.append("[sequence]ass=captions.ass[captioned]")
        video_label = "captioned"
    command = [_ffmpeg_executable(), "-y", *inputs, "-filter_complex", ";".join(filters), "-map", f"[{video_label}]", "-map", f"{audio_index}:a:0", "-t", str(normalized["narration_duration"]), "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    try:
        _run_ffmpeg(command, directory)
        qa = _inspect_video(output)
        if (qa["width"], qa["height"]) != (normalized["width"], normalized["height"]):
            raise VideoRenderError("Rendered dimensions failed technical QA.")
        if abs(qa["duration"] - normalized["narration_duration"]) > max(0.5, normalized["narration_duration"] * 0.01):
            raise VideoRenderError("Rendered duration failed technical QA.")
        if not qa["audio_codec"]:
            raise VideoRenderError("Rendered MP4 has no audio stream.")
        cloud = upload_generated_asset(output.read_bytes(), asset_type="video", digest=bundle["bundle_id"], source_property_ids=[normalized["episode_id"]], metadata={"asset_type": "video", "episode_id": normalized["episode_id"], "render_version": VIDEO_RENDER_VERSION}, content_type="video/mp4", resource_type="video", filename_extension="mp4", check_existing=False)
        thumbnail = delivery_url(cloud["cloudinary_public_id"], resource_type="video", transformation="so_0,c_fill,w_720,h_1280,f_jpg", fmt="jpg")
        result = {"success": True, "status": "ready", "asset_type": "video", "video_id": f"video_{bundle['bundle_id']}", "bundle_id": bundle["bundle_id"], "episode_id": normalized["episode_id"], "cloudinary_public_id": cloud["cloudinary_public_id"], "secure_url": cloud["secure_url"], "url": cloud["secure_url"], "thumbnail_url": thumbnail, "duration": qa["duration"], "width": qa["width"], "height": qa["height"], "aspect_ratio": normalized["aspect_ratio"], "format": "mp4", "narration_asset_id": normalized["narration_ref"]["public_id"], "scene_count": len(bundle["scenes"]), "scene_timeline": normalized["scenes"], "captions": {"enabled": normalized["captions"], "status": "burned_in" if normalized["captions"] else "disabled"}, "source_visual_asset_ids": [scene["asset"]["public_id"] for scene in normalized["scenes"]], "qa_results": qa, "provenance": {"project": normalized["project"], "render_version": VIDEO_RENDER_VERSION}, "cached": False, "warnings": normalized["warnings"], "generated_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "summary": f"Rendered, verified, and published a carrier-free {normalized['aspect_ratio']} MP4 with {len(bundle['scenes'])} scenes."}
        _catalog_episode(normalized, status="ready", cloudinary_public_id=cloud["cloudinary_public_id"], video_url=cloud["secure_url"], thumbnail_url=thumbnail, duration=qa["duration"], qa_results=qa)
        _write_json(published_path, result)
        return result
    except Exception as exc:
        _catalog_episode(normalized, status="failed", failure_reason=str(exc))
        raise


def generate_video(manifest: dict[str, Any]) -> dict[str, Any]:
    """One-action API: prepare deterministically, then render, QA, publish, and catalog."""
    return render_prepared_video(prepare_video(manifest))
