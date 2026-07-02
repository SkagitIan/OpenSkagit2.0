"""Structured output models for ParcelBook agent answers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ParcelResult(BaseModel):
    parcel_number: str
    address: str | None = None
    owner_name: str | None = None
    parcel_data: dict[str, Any] = Field(default_factory=dict)
    parcel_match_reason: str
    zoning_summary: str | None = None
    zoning_status: str | None = None
    caveats: list[str] = Field(default_factory=list)


class ParcelAgentAnswer(BaseModel):
    interpreted_intent: str
    mode: str
    sql_used: str | None = None
    zoning_was_used: bool = False
    row_count: int = 0
    results: list[ParcelResult] = Field(default_factory=list)
    general_caveats: list[str] = Field(default_factory=list)
