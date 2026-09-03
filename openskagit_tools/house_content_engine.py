"""Deterministic contracts and safeguards for the House Content Engine.

Editorial choices remain in the skill.  This module only validates handoffs,
persists stage artifacts, and provides small, duplicate-safe analytical helpers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"
Classification = Literal["VERIFIED_FACT", "CALCULATED_RESULT", "ANALYSIS"]
EvidenceStrength = Literal["A", "B", "C", "D"]


class EngineValidationError(ValueError):
    """Raised when a deterministic handoff or public artifact is unsafe."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Investigation(StrictModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    homeowner_concern: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    alternative_hypothesis: str = Field(min_length=1)
    variables: list[str] = Field(min_length=1)
    controls: list[str] = Field(default_factory=list)
    geography: str = Field(min_length=1)
    population: str = Field(min_length=1)
    required_data: list[str] = Field(default_factory=list)
    method: str = Field(min_length=1)
    visuals: list[str] = Field(default_factory=list)
    discovery_score: float | None = Field(default=None, ge=-1, le=1)
    evidence_risks: list[str] = Field(default_factory=list)
    status: Literal["proposed", "active", "complete", "abandoned"] = "proposed"


class ResearchResult(StrictModel):
    research_question: str = Field(min_length=1)
    sample_description: str = Field(min_length=1)
    methodology: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)
    authoritative_context: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength
    storyworthiness: float = Field(ge=0, le=1)
    disposition: Literal["advance", "reframe", "abandon", "insufficient"]
    reproducibility: dict[str, Any] = Field(default_factory=dict)


class FactRecord(StrictModel):
    fact_id: str = Field(pattern=r"^fact_[A-Za-z0-9_-]+$")
    classification: Classification
    value: Any = None
    unit: str | None = None
    display_text: str = Field(min_length=1)
    narration_text: str = Field(min_length=1)
    source_property_ids: list[str] = Field(default_factory=list)
    source_field: str | None = None
    source_reference: str = Field(min_length=1)
    calculation: str | None = None
    confidence: Literal["high", "medium", "low"]
    limitations: str | None = None
    approved_for_public_use: bool = False


class FactLedger(StrictModel):
    facts: list[FactRecord] = Field(min_length=1)


class StoryPackage(StrictModel):
    question: str = Field(min_length=1)
    story_promise: str = Field(min_length=1)
    central_reveal: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    master_script: str = Field(min_length=1)
    short_scripts: list[str] = Field(default_factory=list)
    script_cues: list[dict[str, Any]] = Field(default_factory=list)
    visual_beats: list[dict[str, Any]] = Field(default_factory=list)
    script_fact_map: dict[str, list[str]] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)


class FinalProductionPackage(StrictModel):
    episode_id: str = Field(min_length=1)
    research_reference: str = Field(min_length=1)
    fact_ledger_reference: str = Field(min_length=1)
    story_reference: str = Field(min_length=1)
    visual_assets: list[dict[str, Any]] = Field(default_factory=list)
    narration_asset: dict[str, Any] | None = None
    captions: dict[str, Any] | None = None
    video_asset: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    final_qa_status: Literal["pending", "passed", "failed"] = "pending"


def _walk_strings(value: Any, path: str = "root"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")


_PRIVATE_KEY = re.compile(r"(?:parcel|owner|taxpayer|mailing|street|address|situs|account|property[_ -]?id)", re.I)
_PARCEL_ID = re.compile(r"\bP\d{4,}\b", re.I)
_STREET = re.compile(r"\b\d{1,6}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,5}\s+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|Blvd|Highway|Hwy)\b", re.I)


def validate_public_artifact(artifact: Any, *, privacy_exception_approved: bool = False) -> None:
    """Reject obvious property identity fields in public-facing artifacts."""
    if privacy_exception_approved:
        return
    issues: list[str] = []
    if isinstance(artifact, dict):
        for path, value in _walk_strings(artifact):
            key = path.rsplit(".", 1)[-1].split("[", 1)[0]
            if _PRIVATE_KEY.search(key):
                issues.append(f"{path}: private identity field")
            if _PARCEL_ID.search(value):
                issues.append(f"{path}: parcel identifier")
            if _STREET.search(value):
                issues.append(f"{path}: exact street address")
    else:
        for path, value in _walk_strings(artifact):
            if _PARCEL_ID.search(value) or _STREET.search(value):
                issues.append(f"{path}: property identity")
    if issues:
        raise EngineValidationError("Public artifact failed privacy validation: " + "; ".join(issues[:5]))


def validate_fact_ledger(ledger: FactLedger | dict[str, Any], *, story: StoryPackage | dict[str, Any] | None = None, production: dict[str, Any] | None = None) -> FactLedger:
    """Validate explicit fact lineage for scripts, graphics, and manifests."""
    parsed = ledger if isinstance(ledger, FactLedger) else FactLedger.model_validate(ledger)
    by_id = {fact.fact_id: fact for fact in parsed.facts}
    if len(by_id) != len(parsed.facts):
        raise EngineValidationError("Fact ledger contains duplicate fact IDs.")
    for fact in parsed.facts:
        if not fact.approved_for_public_use:
            continue
        if fact.source_property_ids:
            # IDs are valid internal lineage, but never valid public output.
            pass
        if isinstance(fact.value, (int, float)) and fact.display_text:
            numeric = re.sub(r"[^0-9.-]", "", fact.display_text)
            if numeric and abs(float(numeric) - float(fact.value)) > 0.01:
                raise EngineValidationError(f"{fact.fact_id} display_text conflicts with value.")
    if story is not None:
        story_model = story if isinstance(story, StoryPackage) else StoryPackage.model_validate(story)
        refs = {fact_id for values in story_model.script_fact_map.values() for fact_id in values}
        for fact_id in refs:
            if fact_id not in by_id:
                raise EngineValidationError(f"Story references unsupported fact ID {fact_id}.")
            if not by_id[fact_id].approved_for_public_use:
                raise EngineValidationError(f"Story references unapproved public fact {fact_id}.")
    if production is not None:
        for fact_id in _fact_ids_in(production):
            if fact_id not in by_id or not by_id[fact_id].approved_for_public_use:
                raise EngineValidationError(f"Production references unsupported or unapproved fact {fact_id}.")
        validate_public_artifact(production)
    return parsed


def _fact_ids_in(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "fact_id" and isinstance(item, str):
                yield item
            else:
                yield from _fact_ids_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _fact_ids_in(item)


class EpisodeStore:
    """Small JSON stage store; each write is atomic and resumable."""

    def __init__(self, episode_id: str, root: str | Path | None = None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", episode_id):
            raise ValueError("episode_id must be a safe slug")
        self.directory = Path(root or os.environ.get("HOUSE_CONTENT_EPISODES_DIR", "episodes")) / episode_id
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, stage: str, value: Any) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,49}", stage):
            raise ValueError("stage must be a safe lowercase name")
        payload = {"schema_version": SCHEMA_VERSION, "saved_at": datetime.now(timezone.utc).isoformat(), "data": _dump(value)}
        target = self.directory / f"{stage}.json"
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(target)
        return target

    def load(self, stage: str) -> Any:
        target = self.directory / f"{stage}.json"
        return json.loads(target.read_text(encoding="utf-8"))["data"]

    def exists(self, stage: str) -> bool:
        return (self.directory / f"{stage}.json").exists()


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in value]
    return value


def deduplicate_rows(rows: list[dict[str, Any]], *, unit: str = "parcel_number") -> list[dict[str, Any]]:
    """Keep one deterministic record per declared analytical unit."""
    seen: set[Any] = set()
    result = []
    for row in rows:
        key = row.get(unit)
        if key is None:
            continue
        if key not in seen:
            seen.add(key)
            result.append(dict(row))
    return result


def group_summary(rows: list[dict[str, Any]], *, group_field: str, metric: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        group = row.get(group_field)
        value = row.get(metric)
        if group in (None, "") or value in (None, ""):
            continue
        try:
            groups.setdefault(str(group), []).append(float(value))
        except (TypeError, ValueError):
            continue
    return {group: {"count": len(values), "median": median(values), "min": min(values), "max": max(values)} for group, values in groups.items()}


def binned_summary(rows: list[dict[str, Any]], *, field: str, metric: str, bins: list[float]) -> list[dict[str, Any]]:
    if len(bins) < 2 or bins != sorted(bins):
        raise ValueError("bins must contain at least two ascending boundaries")
    result = []
    for lower, upper in zip(bins, bins[1:]):
        values = []
        for row in rows:
            try:
                candidate, value = float(row[field]), float(row[metric])
            except (KeyError, TypeError, ValueError):
                continue
            if lower <= candidate < upper and value == value:
                values.append(value)
        result.append({"lower": lower, "upper": upper, "count": len(values), "median": median(values) if values else None})
    return result


def reproducibility_metadata(*, source_tool: str, filters: dict[str, Any], rows: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
    source_hash = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    specification = {"source_tool": source_tool, "filters": filters, "analysis": analysis}
    return {**specification, "source_hash": source_hash, "query_hash": hashlib.sha256(json.dumps(specification, sort_keys=True, default=str).encode()).hexdigest(), "result_count": len(rows)}


def _cue_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def derive_narration_cues(story: StoryPackage | dict[str, Any], narration: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map approved script cues to ElevenLabs word timing; never estimate timing."""
    story_model = story if isinstance(story, StoryPackage) else StoryPackage.model_validate(story)
    if not story_model.script_cues:
        return {}
    words = narration.get("word_timings") or []
    segments = narration.get("segments") or []
    timed_words = [(item, _cue_tokens(str(item.get("word", "")))) for item in words]
    timed_words = [(item, tokens) for item, tokens in timed_words if tokens]
    flattened = [tokens[0] for _, tokens in timed_words]
    result: dict[str, dict[str, Any]] = {}
    for cue in story_model.script_cues:
        cue_id = str(cue.get("cue_id", "")).strip()
        cue_text = str(cue.get("text", "")).strip()
        if not cue_id or not cue_text:
            raise EngineValidationError("Every script cue requires cue_id and text.")
        target = _cue_tokens(cue_text)
        match_start = None
        for index in range(len(flattened) - len(target) + 1):
            if flattened[index : index + len(target)] == target:
                match_start = index
                break
        if match_start is not None:
            matched = [timed_words[match_start + offset][0] for offset in range(len(target))]
            if cue_id in result:
                raise EngineValidationError(f"Duplicate script cue ID: {cue_id}.")
            result[cue_id] = {"cue_id": cue_id, "text": cue_text, "start": float(matched[0]["start"]), "end": float(matched[-1]["end"]), "fact_ids": cue.get("fact_ids", [])}
            continue
        normalized = " ".join(target)
        segment = next((item for item in segments if " ".join(_cue_tokens(str(item.get("text", "")))) == normalized), None)
        if segment:
            result[cue_id] = {"cue_id": cue_id, "text": cue_text, "start": float(segment["start"]), "end": float(segment["end"]), "fact_ids": cue.get("fact_ids", [])}
            continue
        raise EngineValidationError(f"Script cue {cue_id!r} could not be matched to ElevenLabs timing.")
    return result


def build_production_manifest(story: StoryPackage | dict[str, Any], narration: dict[str, Any], assets: list[dict[str, Any]], *, project: str, aspect_ratio: str = "9:16") -> dict[str, Any]:
    """Translate story beats, deriving scene timing from aligned narration cues."""
    story_model = story if isinstance(story, StoryPackage) else StoryPackage.model_validate(story)
    if not narration.get("cloudinary_public_id") or not narration.get("duration"):
        raise EngineValidationError("Narration asset with Cloudinary ID and duration is required.")
    if narration.get("word_timings") and not story_model.script_cues:
        raise EngineValidationError("Aligned narration requires story.script_cues; guessed scene timing is disabled.")
    asset_by_id = {item.get("asset_id") or item.get("cloudinary_public_id"): item for item in assets}
    timing_cues = derive_narration_cues(story_model, narration)
    scenes = []
    for index, beat in enumerate(story_model.visual_beats):
        asset_key = beat.get("asset_id") or beat.get("asset")
        if isinstance(asset_key, dict):
            asset_key = asset_key.get("asset_id") or asset_key.get("cloudinary_public_id")
        asset = asset_by_id.get(asset_key, {})
        asset_ref = asset.get("cloudinary_public_id") or beat.get("asset")
        if not asset_ref:
            raise EngineValidationError(f"Visual beat {index + 1} has no resolvable asset.")
        cue_ids = beat.get("cue_ids", [beat["cue_id"]] if beat.get("cue_id") else [])
        if timing_cues:
            if not cue_ids:
                raise EngineValidationError(f"Visual beat {index + 1} requires cue_ids when aligned narration is available.")
            missing = [cue_id for cue_id in cue_ids if cue_id not in timing_cues]
            if missing:
                raise EngineValidationError(f"Visual beat {index + 1} references unknown timing cues: {', '.join(missing)}.")
            start = min(timing_cues[cue_id]["start"] for cue_id in cue_ids)
            end = max(timing_cues[cue_id]["end"] for cue_id in cue_ids)
            duration = end - start
        else:
            start = None
            duration = beat.get("duration", 1)
        primary_asset = asset if asset.get("secure_url") or asset.get("png_url") or asset.get("local_path") else asset_ref
        scenes.append({"id": beat.get("id", f"beat-{index + 1}"), "scene_type": beat.get("scene_type", "DATA_FULL_FRAME"), "duration": duration, "primary_asset": primary_asset, "motion": beat.get("motion", "none"), "transition": beat.get("transition", "cut"), "overlays": beat.get("overlays", []), "provenance": beat.get("provenance", []), "cue_ids": cue_ids, **({"start": start} if start is not None else {})})
    if not scenes:
        raise EngineValidationError("Story must contain at least one visual beat.")
    if timing_cues:
        # A visual begins at its cue onset, then holds through pauses until the
        # next visual cue. This keeps the visual state synchronized without
        # leaving gaps between scenes.
        for index, scene in enumerate(scenes):
            cue_start = min(timing_cues[cue_id]["start"] for cue_id in scene["cue_ids"])
            start = 0.0 if index == 0 else cue_start
            end = min(
                (min(timing_cues[cue_id]["start"] for cue_id in scenes[index + 1]["cue_ids"]) if index + 1 < len(scenes) else float(narration["duration"])),
                float(narration["duration"]),
            )
            if end - start < 0.05:
                raise EngineValidationError(f"Visual beat {scene['id']!r} has no usable aligned duration.")
            scene["start"] = round(start, 3)
            scene["duration"] = round(end - start, 3)
    return {"episode_id": re.sub(r"[^a-z0-9_-]+", "-", project.lower()).strip("-"), "project": project, "title": story_model.question, "description": story_model.central_reveal, "aspect_ratio": aspect_ratio, "narration": narration, "captions": bool(narration.get("segments")), "scenes": scenes, "timing_cues": list(timing_cues.values())}
