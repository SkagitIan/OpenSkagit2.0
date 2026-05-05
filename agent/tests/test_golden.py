import json
import os
from pathlib import Path

import pytest

from agent.main import run_ask


@pytest.mark.asyncio
async def test_live_land_flip_golden():
    if os.environ.get("RUN_LIVE_GOLDEN") != "1":
        pytest.skip("Set RUN_LIVE_GOLDEN=1 to run live golden test")

    fixture = json.loads(
        Path("agent/tests/fixtures/p48165_land_flip_expected.json").read_text(encoding="utf-8")
    )
    result = await run_ask(fixture["question"], {"county": "skagit", "state": "wa"})

    assert result["case_file_id"]
    assert len(result["evidence"]) >= fixture["min_evidence_count"]
    assert set(fixture["required_sources"]).issubset(set(result["sources_queried"]))
    for text in fixture["answer_must_contain"]:
        assert text in result["answer"]
    for text in fixture["answer_must_not_contain"]:
        assert text not in result["answer"]


@pytest.mark.asyncio
async def test_live_wetlands_golden():
    if os.environ.get("RUN_LIVE_GOLDEN") != "1":
        pytest.skip("Set RUN_LIVE_GOLDEN=1 to run live golden test")

    fixture = json.loads(
        Path("agent/tests/fixtures/p48165_wetlands_expected.json").read_text(encoding="utf-8")
    )
    result = await run_ask(fixture["question"], {"county": "skagit", "state": "wa"})

    assert result["case_file_id"]
    assert len(result["evidence"]) >= fixture["min_evidence_count"]
    assert set(fixture["required_sources"]).issubset(set(result["sources_queried"]))
    for source_id in fixture["preferred_sources"]:
        assert source_id in result["sources_queried"] or "wetlands" in fixture["missing_domains_acceptable"]
    for text in fixture["answer_must_contain"]:
        assert text in result["answer"]
    for text in fixture["answer_must_not_contain"]:
        assert text.lower() not in result["answer"].lower()
