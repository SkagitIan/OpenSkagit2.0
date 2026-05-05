import os

import httpx


NOTIFY_WORKER_URL = os.environ.get("NOTIFY_WORKER_URL", "http://localhost:8789")


async def dispatch(case_file: dict, notify_config: dict) -> dict:
    """
    Build a NotifyRequest and call the notify-adapter Worker.
    Returns a result dict and never raises.
    """
    on_confidence = notify_config.get("on_confidence")
    if on_confidence and case_file.get("confidence") not in on_confidence:
        return {
            "skipped": True,
            "reason": f"Confidence '{case_file.get('confidence')}' not in filter {on_confidence}",
        }

    channels = {}

    if notify_config.get("email"):
        subject = notify_config.get("subject") or (
            f"Case File: {case_file.get('entity', 'Civic Query')} - "
            f"{case_file.get('confidence', '').upper()} confidence"
        )
        channels["email"] = {
            "to": notify_config["email"],
            "subject": subject,
            "case_file": case_file,
        }

    if notify_config.get("webhook"):
        channels["webhook"] = {
            "url": notify_config["webhook"],
            "payload": {
                "event": "case_file_complete",
                "case_file_id": case_file.get("id"),
                "entity": case_file.get("entity"),
                "question": case_file.get("question"),
                "confidence": case_file.get("confidence"),
                "answer": case_file.get("answer"),
                "sources_queried": case_file.get("sources_queried", []),
                "missing": case_file.get("missing", []),
                "created_at": case_file.get("created_at"),
            },
        }

    if not channels:
        return {"skipped": True, "reason": "No channels configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{NOTIFY_WORKER_URL}/notify", json={"channels": channels})
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def dispatch_background(case_file: dict, notify_config: dict) -> None:
    """Fire-and-forget wrapper for asyncio.create_task()."""
    try:
        await dispatch(case_file, notify_config)
    except Exception:
        pass
