# Phase 4 Codex Brief
## Civic Intelligence Platform — Tool Layer + Notifications

**Builds on:** Phase 3 verified and passing.

**Goal:** Activate the tool registry with the first real registered tool — a notification dispatcher that sends completed case files to email addresses or webhook endpoints. Complete the async job queue. Prove that tools registered in `tool_registry.yaml` are dispatched without touching the core agent.

**Exit criteria:** `POST /ask` with a `notify` config sends a formatted email or webhook POST after the case file is complete. The notification fires without blocking the response. A second tool can be added to the registry without modifying `main.py`, `planner.py`, or the dispatcher.

---

## What changes in Phase 4

```
New Worker
  workers/notify-adapter/       ← email (Resend) + webhook dispatch

New agent modules
  agent/notifier.py             ← post-answer notification orchestration
  agent/tools/registry.py       ← tool registry loader and dispatcher

Modified files
  agent/main.py                 ← add notify config to AskRequest, fire notifier
  agent/jobs.py                 ← upgrade in-memory store to sqlite-backed queue
  catalog/tools/tool_registry.yaml  ← first real tool entry: notify

New frontend features
  Notification config panel     ← email input + webhook input, optional
  Job progress states           ← pending / running / complete / failed

New tests
  agent/tests/test_notifier.py
  agent/tests/test_tool_registry.py
```

---

## Notification Design

### How it fits in the flow

```
POST /ask (with optional notify config)
  ↓
planner → dispatcher → case file → analyst answer → save
  ↓
IF notify config present:
  notifier.dispatch(case_file, notify_config)   ← fire and forget
  ↓
Return AskResponse immediately
Notification sends in background
```

The notification is **fire-and-forget**. It does not block the response. The user gets their answer in normal response time. The notification may arrive 1–3 seconds later.

### Request contract addition

```python
class NotifyConfig(BaseModel):
    email: Optional[str] = None           # recipient email address
    webhook: Optional[str] = None         # any HTTPS URL
    subject: Optional[str] = None         # email subject override
    on_confidence: Optional[list[str]] = None
    # ["high", "medium", "low"] — only notify if confidence matches
    # None means always notify

class AskRequest(BaseModel):
    question: str
    context: Optional[dict] = {}
    notify: Optional[NotifyConfig] = None  # NEW
```

### Notification filtering

If `on_confidence` is set, only send the notification if `case_file.confidence` is in that list.

```python
# Example: only notify on high or medium confidence answers
notify: {
  "email": "planner@skagitcounty.gov",
  "on_confidence": ["high", "medium"]
}
```

If the answer comes back `low` confidence, the notification is skipped. The response still returns normally.

---

## Ticket 1 — notify-adapter Cloudflare Worker

**Directory:** `workers/notify-adapter/`

This Worker handles outbound notifications. It accepts a POST from the Python agent and dispatches to email or webhook (or both).

**`wrangler.toml`:**

```toml
name = "notify-adapter"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
ALLOWED_ORIGINS = "http://localhost:8000"

[secrets]
# RESEND_API_KEY — set via: wrangler secret put RESEND_API_KEY
```

**Interface — `src/index.ts`:**

```typescript
interface NotifyRequest {
  channels: {
    email?: {
      to: string;
      subject: string;
      body_html: string;
      body_text: string;
    };
    webhook?: {
      url: string;
      payload: Record<string, unknown>;
    };
  };
}

interface NotifyResponse {
  success: boolean;
  results: {
    email?: { sent: boolean; error?: string };
    webhook?: { sent: boolean; status?: number; error?: string };
  };
}
```

**Email via Resend:**

Resend (resend.com) is the email provider. Free tier: 3,000 emails/month, 100/day. No domain verification needed for development sends.

```typescript
async function sendEmail(
  to: string,
  subject: string,
  html: string,
  text: string,
  apiKey: string
): Promise<{ sent: boolean; error?: string }> {
  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        from: "Civic Intelligence <notifications@yourdomain.com>",
        to: [to],
        subject,
        html,
        text
      })
    });
    if (!response.ok) {
      const err = await response.text();
      return { sent: false, error: err };
    }
    return { sent: true };
  } catch (e) {
    return { sent: false, error: String(e) };
  }
}
```

**Webhook dispatch:**

```typescript
async function sendWebhook(
  url: string,
  payload: Record<string, unknown>
): Promise<{ sent: boolean; status?: number; error?: string }> {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10000)
    });
    return { sent: response.ok, status: response.status };
  } catch (e) {
    return { sent: false, error: String(e) };
  }
}
```

**Worker rules:**
- Never throw. All errors return structured results with `sent: false`.
- Both channels are independent. Email failure does not abort webhook.
- Timeout for webhook: 10 seconds.
- Resend API key read from `RESEND_API_KEY` secret, not env var.
- If `RESEND_API_KEY` is not set, log a warning and skip email with `sent: false, error: "API key not configured"`.

---

## Ticket 2 — Email Template

**File:** `workers/notify-adapter/src/template.ts`

Generate the HTML and plain text email from a case file object. Keep it clean and readable — this may go to a county planner or a property owner.

```typescript
export function buildEmailHtml(caseFile: CaseFilePayload): string {
  const confidenceBadge = {
    high: "🟢 High",
    medium: "🟡 Medium",
    low: "🔴 Low"
  }[caseFile.confidence] ?? caseFile.confidence;

  return `
    <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="border-bottom: 1px solid #eee; padding-bottom: 8px;">
        Civic Intelligence Case File
      </h2>
      <p><strong>Entity:</strong> ${escapeHtml(caseFile.entity ?? "Unknown")}</p>
      <p><strong>Question:</strong> ${escapeHtml(caseFile.question)}</p>
      <p><strong>Confidence:</strong> ${confidenceBadge}</p>
      <hr style="border: none; border-top: 1px solid #eee;" />
      <h3>Answer</h3>
      <p>${escapeHtml(caseFile.answer ?? "No answer generated.")}</p>
      <h3>Sources Queried</h3>
      <ul>
        ${(caseFile.sources_queried ?? []).map(s => `<li>${escapeHtml(s)}</li>`).join("")}
      </ul>
      ${caseFile.missing?.length ? `
        <h3>Missing Evidence</h3>
        <ul style="color: #888;">
          ${caseFile.missing.map(m => `<li>${escapeHtml(m)}</li>`).join("")}
        </ul>
      ` : ""}
      <hr style="border: none; border-top: 1px solid #eee;" />
      <p style="font-size: 12px; color: #999;">
        Case file ID: ${escapeHtml(caseFile.id)}<br/>
        Generated: ${escapeHtml(caseFile.created_at)}
      </p>
    </div>
  `;
}

export function buildEmailText(caseFile: CaseFilePayload): string {
  // Plain text version for email clients that don't render HTML
  const lines = [
    "CIVIC INTELLIGENCE CASE FILE",
    "============================",
    `Entity: ${caseFile.entity ?? "Unknown"}`,
    `Question: ${caseFile.question}`,
    `Confidence: ${caseFile.confidence}`,
    "",
    "ANSWER",
    caseFile.answer ?? "No answer generated.",
    "",
    "SOURCES QUERIED",
    ...(caseFile.sources_queried ?? []).map(s => `- ${s}`),
  ];
  if (caseFile.missing?.length) {
    lines.push("", "MISSING EVIDENCE");
    caseFile.missing.forEach(m => lines.push(`- ${m}`));
  }
  lines.push("", `Case file ID: ${caseFile.id}`);
  return lines.join("\n");
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
```

---

## Ticket 3 — notifier.py

**File:** `agent/notifier.py`

Python side of the notification system. Calls the notify-adapter Worker.

```python
import os
import asyncio
import httpx
import json
from typing import Optional

NOTIFY_WORKER_URL = os.environ.get("NOTIFY_WORKER_URL", "http://localhost:8789")


async def dispatch(
    case_file: dict,
    notify_config: dict
) -> dict:
    """
    Fire-and-forget notification dispatcher.
    Builds the NotifyRequest and calls the notify-adapter Worker.
    Returns result dict. Never raises.
    """
    # Confidence filter
    on_confidence = notify_config.get("on_confidence")
    if on_confidence and case_file.get("confidence") not in on_confidence:
        return {
            "skipped": True,
            "reason": f"Confidence '{case_file.get('confidence')}' not in filter {on_confidence}"
        }

    channels = {}

    if notify_config.get("email"):
        subject = (
            notify_config.get("subject")
            or f"Case File: {case_file.get('entity', 'Civic Query')} — {case_file.get('confidence', '').upper()} confidence"
        )
        channels["email"] = {
            "to": notify_config["email"],
            "subject": subject,
            # body_html and body_text are rendered by the Worker's template
            # Pass the full case file and let the Worker build the email
            "case_file": case_file
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
                "created_at": case_file.get("created_at")
            }
        }

    if not channels:
        return {"skipped": True, "reason": "No channels configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{NOTIFY_WORKER_URL}/notify",
                json={"channels": channels}
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        # Never let notification failure affect the answer
        return {"success": False, "error": str(e)}


async def dispatch_background(case_file: dict, notify_config: dict) -> None:
    """
    Fire-and-forget wrapper for use with asyncio.create_task().
    Swallows all errors — notification must never crash the agent.
    """
    try:
        await dispatch(case_file, notify_config)
    except Exception:
        pass
```

---

## Ticket 4 — Tool Registry Loader

**File:** `agent/tools/registry.py`

Load and query the tool registry YAML at startup. In Phase 4 the notification tool is the only registered tool. This module makes the registry queryable by the planner and dispatcher.

```python
import yaml
import os
from typing import Optional
from functools import lru_cache

REGISTRY_PATH = os.environ.get(
    "TOOL_REGISTRY_PATH",
    "catalog/tools/tool_registry.yaml"
)


@lru_cache(maxsize=1)
def load_registry() -> dict:
    """Load and cache the tool registry. Call reload_registry() to bust cache."""
    with open(REGISTRY_PATH, "r") as f:
        return yaml.safe_load(f)


def reload_registry() -> None:
    """Bust the cache. Call after registry file changes in development."""
    load_registry.cache_clear()


def get_tool(tool_id: str) -> Optional[dict]:
    """Return a tool definition by ID, or None if not found."""
    registry = load_registry()
    for tool in registry.get("tools", []):
        if tool["id"] == tool_id:
            return tool
    return None


def find_tools_by_trigger(question: str) -> list[dict]:
    """
    Return all tools whose trigger keywords appear in the question.
    Case-insensitive substring match.
    """
    question_lower = question.lower()
    registry = load_registry()
    matches = []
    for tool in registry.get("tools", []):
        for trigger in tool.get("triggers", []):
            if trigger.lower() in question_lower:
                matches.append(tool)
                break
    return matches


def list_tools() -> list[dict]:
    """Return all registered tools."""
    return load_registry().get("tools", [])
```

---

## Ticket 5 — Updated tool_registry.yaml

**File:** `catalog/tools/tool_registry.yaml` (replace placeholder with first real entry)

```yaml
tools:
  - id: notify
    name: "Case File Notification"
    type: notification
    runtime: async
    worker_url_env: NOTIFY_WORKER_URL
    triggers:
      - "notify"
      - "send to"
      - "email me"
      - "alert me"
      - "send results to"
      - "forward to"
    input_domains: []
    output_format: notification_receipt
    description: >
      Sends a completed case file to an email address or webhook endpoint.
      Fires after the answer is generated. Does not affect the answer content.
      Supports confidence filtering: only notify if confidence meets a threshold.
    channels_supported:
      - email
      - webhook
    config:
      email_provider: resend
      email_from: "Civic Intelligence <notifications@yourdomain.com>"
      webhook_timeout_seconds: 10

# Schema reference for future tools:
#
# - id: string
#   name: string
#   type: notification | analysis | report | dashboard
#   runtime: sync | async
#   worker_url_env: string       env var holding the Worker URL
#   triggers: [string]           keywords that route to this tool
#   input_domains: [string]      source domains this tool needs
#   output_format: string        what it produces
#   description: string
```

---

## Ticket 6 — Updated main.py

Modify the `/ask` execution flow to:

1. Accept `notify` in `AskRequest`
2. Fire the notifier after the case file is complete
3. Use `asyncio.create_task()` so notification is fire-and-forget

```python
# In the ask_task() closure, after saving the case file:

if request.notify:
    asyncio.create_task(
        notifier.dispatch_background(
            case_file=saved_case_file,
            notify_config=request.notify.model_dump(exclude_none=True)
        )
    )
```

The response is returned before the notification completes. The notification result is not included in `AskResponse`. If the caller wants to know if the notification was sent, that is a future feature.

Also add a new endpoint for notification status (Phase 5 will use this for watch lists — scaffold now):

```python
@app.get("/notify/status/{job_id}")
async def notify_status(job_id: str):
    """
    Placeholder for notification delivery status.
    Returns 404 in Phase 4. Will be implemented in Phase 5.
    """
    return JSONResponse(
        status_code=404,
        content={"detail": "Notification status not yet implemented"}
    )
```

---

## Ticket 7 — Async Job Queue: Upgrade from In-Memory to SQLite

**File:** `agent/jobs.py` (replace Phase 2 in-memory store)

Phase 2 used a Python dict. That means jobs disappear on Railway restart. Upgrade to sqlite-backed storage using the existing D1 connection.

Add a `jobs` table to `catalog/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT DEFAULT 'pending',
  result TEXT,
  error TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  completed_at TEXT
);
```

Update `agent/jobs.py` to read/write from this table instead of `_jobs` dict. The external interface (`create_job`, `get_job`, `complete_job`, `fail_job`, `run_job`) does not change. Only the storage backend changes.

This means jobs survive Railway restarts and the `/job/{job_id}` poll endpoint works correctly even after a deploy.

---

## Ticket 8 — Frontend: Notification Config Panel

**File:** `frontend/app.js` and `frontend/index.html` (modify existing)

Add a collapsible notification section below the question input. Collapsed by default — don't clutter the main interface.

```
┌──────────────────────────────────────────┐
│  Ask a question about a parcel...        │
│  [                              ] [Ask]  │
│                                          │
│  ▸ Notify when complete (optional)       │
└──────────────────────────────────────────┘
```

When expanded:

```
┌──────────────────────────────────────────┐
│  ▾ Notify when complete (optional)       │
│                                          │
│  Email   [                             ] │
│  Webhook [                             ] │
│                                          │
│  Only notify if confidence is:          │
│  ☑ High  ☑ Medium  ☐ Low               │
└──────────────────────────────────────────┘
```

Include the `notify` config in the `/ask` POST body only if at least one channel (email or webhook) is filled in. If both are empty, omit the `notify` field entirely.

```javascript
function buildNotifyConfig() {
  const email = document.getElementById('notify-email').value.trim();
  const webhook = document.getElementById('notify-webhook').value.trim();
  
  if (!email && !webhook) return null;
  
  const config = {};
  if (email) config.email = email;
  if (webhook) config.webhook = webhook;
  
  const confidence = [];
  if (document.getElementById('conf-high').checked) confidence.push('high');
  if (document.getElementById('conf-medium').checked) confidence.push('medium');
  if (document.getElementById('conf-low').checked) confidence.push('low');
  if (confidence.length > 0 && confidence.length < 3) {
    config.on_confidence = confidence;
  }
  
  return config;
}
```

Add a small notification status indicator in the right panel after a response:

```
[Case file saved]  [Copy link]  [Export]  [📧 Notification sent]
```

The "Notification sent" indicator appears after the response arrives if `notify` was configured. In Phase 4 it's optimistic (shows immediately). Phase 5 can make it accurate with the status endpoint.

---

## Ticket 9 — Updated .env.example

```bash
# Notify Worker
NOTIFY_WORKER_URL=http://localhost:8789

# Resend API key (free tier at resend.com — 3,000 emails/month)
RESEND_API_KEY=re_...

# Jobs SQLite (already in Phase 1 .env, confirm it's there)
D1_LOCAL_PATH=catalog/local.db
```

Add `NOTIFY_WORKER_URL` and `RESEND_API_KEY` to Railway environment variables section of README.

---

## Ticket 10 — Test Suite

**File:** `agent/tests/test_notifier.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from agent.notifier import dispatch

SAMPLE_CASE_FILE = {
    "id": "cf_test123",
    "entity": "P48165",
    "question": "Tell me about parcel P48165",
    "confidence": "medium",
    "answer": "Parcel P48165 is owned by SWANSON EARLINE.",
    "sources_queried": ["skagit_parcels"],
    "missing": [],
    "created_at": "2025-01-01T00:00:00Z"
}


@pytest.mark.asyncio
async def test_dispatch_skips_on_confidence_filter():
    result = await dispatch(
        case_file={**SAMPLE_CASE_FILE, "confidence": "low"},
        notify_config={
            "email": "test@example.com",
            "on_confidence": ["high", "medium"]
        }
    )
    assert result.get("skipped") is True
    assert "confidence" in result.get("reason", "").lower()


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_channels():
    result = await dispatch(
        case_file=SAMPLE_CASE_FILE,
        notify_config={}
    )
    assert result.get("skipped") is True


@pytest.mark.asyncio
async def test_dispatch_calls_worker_with_email():
    mock_response = {"success": True, "results": {"email": {"sent": True}}}
    with patch("agent.notifier.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=type("R", (), {
                "raise_for_status": lambda self: None,
                "json": lambda self: mock_response
            })()
        )
        result = await dispatch(
            case_file=SAMPLE_CASE_FILE,
            notify_config={"email": "planner@skagitcounty.gov"}
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
            notify_config={"email": "test@example.com"}
        )
    assert result.get("success") is False
    assert "error" in result
    # Must not raise
```

**File:** `agent/tests/test_tool_registry.py`

```python
from agent.tools.registry import (
    load_registry, get_tool, find_tools_by_trigger, list_tools
)


def test_registry_loads():
    registry = load_registry()
    assert "tools" in registry
    assert isinstance(registry["tools"], list)


def test_notify_tool_registered():
    tool = get_tool("notify")
    assert tool is not None
    assert tool["id"] == "notify"
    assert "email" in tool.get("channels_supported", [])


def test_find_tools_by_trigger_email():
    tools = find_tools_by_trigger("notify me by email when this is done")
    ids = [t["id"] for t in tools]
    assert "notify" in ids


def test_find_tools_by_trigger_no_match():
    tools = find_tools_by_trigger("what is the zoning for P48165")
    assert tools == []


def test_list_tools_returns_list():
    tools = list_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 1
```

---

## Running Order for Codex

```
1.  catalog/schema.sql — add jobs table
2.  agent/jobs.py — upgrade to sqlite backend
3.  workers/notify-adapter/ — Worker + template
4.  agent/notifier.py
5.  agent/tools/registry.py
6.  catalog/tools/tool_registry.yaml — add notify tool entry
7.  agent/main.py — add notify to AskRequest, fire notifier post-answer,
                    add /notify/status scaffold, add /job/{id} sqlite lookup
8.  agent/tests/test_notifier.py
9.  agent/tests/test_tool_registry.py
10. frontend — notification config panel + status indicator
11. .env.example + README updates
```

---

## Definition of Done — Phase 4

- [ ] `python -m pytest agent/tests/ -v` — all prior tests pass, 8 new tests pass
- [ ] `POST /ask` with `notify.email` sends a formatted email via Resend (requires `RESEND_API_KEY`)
- [ ] `POST /ask` with `notify.webhook` POSTs the case file JSON to the target URL
- [ ] Notification fires after the response is returned (fire-and-forget confirmed)
- [ ] `notify.on_confidence: ["high"]` correctly skips notification on `medium` or `low` answers
- [ ] Worker failure does not affect the `/ask` response or cause an error
- [ ] `GET /job/{job_id}` returns correct status after Railway restart (sqlite-backed)
- [ ] `catalog/tools/tool_registry.yaml` has the `notify` tool registered with all required fields
- [ ] `agent/tools/registry.py` loads and queries the registry without file I/O on repeated calls (lru_cache)
- [ ] Frontend notification panel renders and submits correctly
- [ ] A second tool can be added to `tool_registry.yaml` and found by `find_tools_by_trigger()` without modifying any Python files
- [ ] `npm run typecheck` passes in `workers/notify-adapter/`
- [ ] README documents `RESEND_API_KEY` setup and free tier limits
