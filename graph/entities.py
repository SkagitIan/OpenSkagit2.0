"""Pure owner/entity resolution helpers for the internal graph.

This module does not access Django models, databases, or public-facing
serialization. Mailing keys are normalized matching keys, not display data.
"""
from __future__ import annotations
import hashlib
import re
import string
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

JUNK_MAILING_THRESHOLD = 25
_PUNCTUATION = str.maketrans({char: " " for char in string.punctuation if char != "&"})
_STREET_WORDS = {"STREET":"ST", "AVENUE":"AVE", "ROAD":"RD", "DRIVE":"DR", "LANE":"LN", "COURT":"CT", "BOULEVARD":"BLVD", "HIGHWAY":"HWY", "PARKWAY":"PKWY", "PLACE":"PL", "CIRCLE":"CIR", "TRAIL":"TRL", "TERRACE":"TER", "NORTH":"N", "SOUTH":"S", "EAST":"E", "WEST":"W"}
_ENTITY_SUFFIXES = ("LLC", "INC", "CORP", "CORPORATION", "LP", "PLLC")
_TRUST_WORDS = ("TRUST", "TTEE", "ESTATE", "LIVING TRUST")
_GOVERNMENT_PREFIXES = ("CITY OF ", "COUNTY OF ", "STATE OF ", "PORT OF ", "USA ", "DISTRICT OF ")

@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    canonical_name: str
    kind: str
    raw_names: tuple[str, ...]
    parcel_numbers: tuple[str, ...]

@dataclass(frozen=True)
class ResolvedOwnershipGroup:
    group_id: str
    member_entity_ids: tuple[str, ...]
    link_reason: str
    mailing_key: str

@dataclass(frozen=True)
class EntityResolution:
    entities: tuple[ResolvedEntity, ...]
    entity_parcels: tuple[tuple[str, str], ...]
    groups: tuple[ResolvedOwnershipGroup, ...]
    junk_mailing_keys: tuple[str, ...]
    unresolved_rows: int

def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()

def normalize_owner_name(raw: str) -> str:
    """Canonicalize common assessor owner-name variations."""
    original = _text(raw).upper()
    text = original.replace("&", " AND ")
    text = re.sub(r"\bET\s*(?:AL|UX)\b", " ", text)
    comma = "," in original
    if comma:
        head, tail = original.split(",", 1)
        surname = re.sub(r"[^A-Z0-9 ]", " ", head).split()
        given_text = tail
    else:
        tokens = re.sub(r"[^A-Z0-9 ]", " ", text).split()
        if not tokens:
            return ""
        surname, given_text = tokens[:1], " ".join(tokens[1:])
    given = re.sub(r"\bET\s*(?:AL|UX)\b", " ", given_text)
    given = re.sub(r"[^A-Z0-9 ]", " ", given).split()
    given = [token for token in given if token != "AND" and len(token) > 1]
    return " ".join(surname + sorted(set(given)))

def classify_entity(canonical: str) -> str:
    """Classify an already canonicalized owner name."""
    value = _text(canonical).upper()
    if any(value.endswith(suffix) or f" {suffix} " in f" {value} " for suffix in _ENTITY_SUFFIXES):
        return "llc"
    if any(word in value for word in _TRUST_WORDS):
        return "trust"
    if any(value.startswith(prefix) for prefix in _GOVERNMENT_PREFIXES):
        return "gov"
    words = value.split()
    return "person" if len(words) >= 2 and all(re.fullmatch(r"[A-Z][A-Z0-9'-]*", word) for word in words) else "unknown"

def normalize_mailing_address(add1, add2, add3, city, state, zip_code) -> str | None:
    """Return a normalized single-line mailing key or None when incomplete."""
    parts = [_text(value).upper() for value in (add1, add2, add3, city, state, zip_code)]
    if not parts[0] or not parts[3] or not parts[4] or not parts[5]:
        return None
    folded = []
    for part in parts:
        folded.extend(_STREET_WORDS.get(word, word) for word in re.sub(r"[^A-Z0-9 ]", " ", part).split())
    return " ".join(folded)

def _stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:48]

def cluster_entities(rows: Iterable[dict[str, Any]], mailing_threshold: int = JUNK_MAILING_THRESHOLD) -> EntityResolution:
    """Resolve owner rows into entities, parcel links, and mailing groups."""
    by_name, parcel_links = {}, set()
    mailing_entities, mailing_parcels = defaultdict(set), defaultdict(set)
    unresolved = 0
    for row in rows:
        raw_name, parcel = _text(row.get("owner_name")), _text(row.get("parcel_number"))
        canonical = normalize_owner_name(raw_name)
        if not canonical or not parcel:
            unresolved += 1
            continue
        entity_id = _stable_id("ent_", canonical)
        entry = by_name.setdefault(entity_id, {"canonical": canonical, "raw": set(), "parcels": set()})
        entry["raw"].add(raw_name)
        entry["parcels"].add(parcel)
        parcel_links.add((entity_id, parcel))
        mailing_key = normalize_mailing_address(row.get("owner_add_1"), row.get("owner_add_2"), row.get("owner_add_3"), row.get("owner_city"), row.get("owner_state"), row.get("owner_zip"))
        if mailing_key:
            mailing_entities[mailing_key].add(entity_id)
            mailing_parcels[mailing_key].add(parcel)
    entities = tuple(ResolvedEntity(entity_id, data["canonical"], classify_entity(data["canonical"]), tuple(sorted(data["raw"])), tuple(sorted(data["parcels"]))) for entity_id, data in sorted(by_name.items()))
    junk_keys = tuple(sorted(key for key, parcels in mailing_parcels.items() if len(parcels) > mailing_threshold))
    groups = []
    for key, members in sorted(mailing_entities.items()):
        if len(mailing_parcels[key]) > mailing_threshold or len(members) < 2:
            continue
        groups.append(ResolvedOwnershipGroup(_stable_id("grp_", key), tuple(sorted(members)), "shared_mailing_address", _stable_id("mail_", key)))
    return EntityResolution(entities, tuple(sorted(parcel_links)), tuple(groups), junk_keys, unresolved)