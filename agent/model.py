import os
from typing import Optional

import httpx


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


async def call_model(
    system: str,
    user: str,
    max_tokens: int = 1000,
    model: Optional[str] = None,
) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    payload = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Model API failed with {response.status_code}: {response.text}")
    data = response.json()
    return data["content"][0]["text"]
