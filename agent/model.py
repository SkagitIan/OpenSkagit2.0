import os
from typing import Optional

import httpx


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_PLANNER_MODEL = "claude-opus-4-20250514"


def _resolve_model(model: Optional[str], env_var: str, default: str) -> str:
    return model or os.environ.get(env_var, default)


async def call_model(
    system: str,
    user: str,
    max_tokens: int = 1000,
    model: Optional[str] = None,
) -> str:
    resolved = _resolve_model(model, "ANALYST_MODEL", DEFAULT_MODEL)
    if resolved.startswith("google/"):
        return await _gemini_text(system, user, max_tokens, resolved[7:])
    if resolved.startswith("openai/"):
        return await _openai_text(system, user, max_tokens, resolved[7:])
    return await _anthropic_text(system, user, max_tokens, resolved)


async def call_model_with_tools(
    system: str,
    user: str,
    tools: list[dict],
    max_tokens: int = 2000,
    model: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """Call a model with tool definitions for structured output.

    Returns (tool_input, text). ``tool_input`` is populated when the model
    invokes a tool; ``text`` is populated when it responds in plain prose.
    """
    resolved = _resolve_model(model, "PLANNER_MODEL", DEFAULT_PLANNER_MODEL)
    if resolved.startswith("google/"):
        return await _gemini_with_tools(system, user, tools, max_tokens, resolved[7:])
    if resolved.startswith("openai/"):
        return await _openai_with_tools(system, user, tools, max_tokens, resolved[7:])
    return await _anthropic_with_tools(system, user, tools, max_tokens, resolved)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

async def _anthropic_text(system: str, user: str, max_tokens: int, model: str) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
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
        raise RuntimeError(f"Anthropic API error {response.status_code}: {response.text}")
    data = response.json()
    return data["content"][0]["text"]


async def _anthropic_with_tools(
    system: str, user: str, tools: list[dict], max_tokens: int, model: str
) -> tuple[Optional[dict], Optional[str]]:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    anthropic_tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in tools
    ]
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": anthropic_tools,
        "tool_choice": {"type": "any"},  # force a tool call
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
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
        raise RuntimeError(f"Anthropic API error {response.status_code}: {response.text}")
    data = response.json()
    text_parts = []
    for block in data.get("content", []):
        if block.get("type") == "tool_use":
            return block.get("input"), None
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    return None, "\n".join(text_parts) or None


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

async def _gemini_text(system: str, user: str, max_tokens: int, model: str) -> str:
    api_key = os.environ["GOOGLE_API_KEY"]
    url = GEMINI_API_URL.format(model=model) + f"?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generation_config": {"max_output_tokens": max_tokens},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


async def _gemini_with_tools(
    system: str, user: str, tools: list[dict], max_tokens: int, model: str
) -> tuple[Optional[dict], Optional[str]]:
    api_key = os.environ["GOOGLE_API_KEY"]
    url = GEMINI_API_URL.format(model=model) + f"?key={api_key}"
    declarations = [
        {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
        for t in tools
    ]
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "tools": [{"function_declarations": declarations}],
        "tool_config": {"function_calling_config": {"mode": "ANY"}},
        "generation_config": {"max_output_tokens": max_tokens},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        if "functionCall" in part:
            return part["functionCall"].get("args"), None
        if "text" in part:
            return None, part["text"]
    return None, None


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

async def _openai_text(system: str, user: str, max_tokens: int, model: str) -> str:
    api_key = os.environ["OPENAI_API_KEY"]
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {response.status_code}: {response.text}")
    data = response.json()
    return data["choices"][0]["message"]["content"]


async def _openai_with_tools(
    system: str, user: str, tools: list[dict], max_tokens: int, model: str
) -> tuple[Optional[dict], Optional[str]]:
    import json as _json
    api_key = os.environ["OPENAI_API_KEY"]
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "tools": openai_tools,
        "tool_choice": "required",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {response.status_code}: {response.text}")
    data = response.json()
    message = data["choices"][0]["message"]
    calls = message.get("tool_calls", [])
    if calls:
        return _json.loads(calls[0]["function"]["arguments"]), None
    return None, message.get("content")
