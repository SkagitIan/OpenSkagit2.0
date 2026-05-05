from unittest.mock import AsyncMock, patch

import pytest

from agent.notifier import dispatch


SAMPLE_CASE_FILE = {
    "id": "cf_test123",
    "entity": "P48165",
    "question": "Tell me about parcel P48165",
    "confidence": "medium",
    "answer": "Parcel P48165 is owned by SWANSON EARLINE.",
    "sources_queried": ["skagit_parcels"],
    "missing": [],
    "created_at": "2025-01-01T00:00:00Z",
}


@pytest.mark.asyncio
async def test_dispatch_skips_on_confidence_filter():
    result = await dispatch(
        case_file={**SAMPLE_CASE_FILE, "confidence": "low"},
        notify_config={
            "email": "test@example.com",
            "on_confidence": ["high", "medium"],
        },
    )
    assert result.get("skipped") is True
    assert "confidence" in result.get("reason", "").lower()


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_channels():
    result = await dispatch(case_file=SAMPLE_CASE_FILE, notify_config={})
    assert result.get("skipped") is True


@pytest.mark.asyncio
async def test_dispatch_calls_worker_with_email():
    mock_response = {"success": True, "results": {"email": {"sent": True}}}
    with patch("agent.notifier.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=type(
                "R",
                (),
                {
                    "raise_for_status": lambda self: None,
                    "json": lambda self: mock_response,
                },
            )()
        )
        result = await dispatch(
            case_file=SAMPLE_CASE_FILE,
            notify_config={"email": "planner@skagitcounty.gov"},
        )
    assert result.get("success") is True


@pytest.mark.asyncio
async def test_dispatch_survives_worker_failure():
    with patch("agent.notifier.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("Worker unreachable")
        )
        result = await dispatch(
            case_file=SAMPLE_CASE_FILE,
            notify_config={"email": "test@example.com"},
        )
    assert result.get("success") is False
    assert "error" in result
