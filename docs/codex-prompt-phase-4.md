# Codex Prompt — Civic Intelligence Platform Phase 4

---

Phase 3 is complete and verified. You are building Phase 4 on top of it.

**Do not modify any Phase 1, 2, or 3 file unless the brief explicitly says to.** All existing tests must continue passing throughout this build.

Read `phase-4-codex-brief.md` completely before writing any code.

## What Phase 4 adds

The first real registered tool: a notification dispatcher that sends completed case files to email addresses or webhook URLs. The tool registry goes live. The async job queue upgrades from in-memory to sqlite. The frontend gains a notification config panel.

## The core design decision

The notification is **post-answer, fire-and-forget**. It does not change how the planner works. It does not affect the answer. It does not block the response. It fires after the case file is saved using `asyncio.create_task()`.

```
plan → gather evidence → build case file → generate answer → save
                                                              ↓
                                              asyncio.create_task(notify)
                                                              ↓
                                              return AskResponse immediately
```

The notification may arrive 1–3 seconds after the response. That is correct behavior.

## Hard rules — all carry forward

1. Frontend uses `fetch()` only. No SDKs.
2. Only `agent/model.py` calls the Anthropic API.
3. No civic data stored. D1 holds source metadata, case files, and now jobs.
4. Workers return structured errors, never crash.
5. Concurrent steps use `asyncio.gather(..., return_exceptions=True)`.
6. Notification failure must never affect the `/ask` response.

## Phase 4 specific rules

7. **The notify Worker never crashes.** Email failure and webhook failure are independent. If Resend returns an error, the webhook still fires. Return `{ success: false, results: { email: { sent: false, error: "..." } } }` — not a 500.

8. **Confidence filtering happens in Python, not the Worker.** The `on_confidence` filter is evaluated in `agent/notifier.py` before calling the Worker. If confidence does not match, the Worker is never called.

9. **The tool registry is the source of truth for tool capabilities.** The Python code reads `tool_registry.yaml` — it does not duplicate tool metadata. Adding a new tool means adding a YAML entry. No Python file changes required.

10. **Jobs must survive restarts.** Replace the in-memory dict in `agent/jobs.py` with sqlite. The external interface does not change — only the storage backend.

11. **Do not implement watch lists or subscriptions.** That is Phase 5. Scaffold the `/notify/status/{job_id}` endpoint returning 404 as a placeholder. Nothing more.

## Build order — follow exactly

**Step 1 — jobs table in schema**

Add the `jobs` table to `catalog/schema.sql`:

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

Run the seed script to apply it:
```bash
python catalog/seeds/seed.py --env local
```

**Step 2 — Upgrade agent/jobs.py to sqlite**

Replace the `_jobs = {}` dict with sqlite reads/writes. The function signatures `create_job`, `get_job`, `complete_job`, `fail_job`, `run_job` do not change. Only the storage backend changes.

After upgrading, verify by restarting the agent and confirming `/job/{id}` still returns results for jobs created before the restart.

**Step 3 — notify-adapter Worker**

Create `workers/notify-adapter/` with:
- `src/index.ts` — main Worker handling POST /notify
- `src/template.ts` — `buildEmailHtml()` and `buildEmailText()` functions
- `wrangler.toml` — name: notify-adapter, port 8789
- `package.json`

Email via Resend API (`https://api.resend.com/emails`). API key from `RESEND_API_KEY` secret.
Webhook via `fetch()` POST with 10-second timeout.
Both channels are independent. Both return structured results.

Run typecheck before moving on:
```bash
cd workers/notify-adapter && npm run typecheck
```

**Step 4 — agent/notifier.py**

Implement exactly as specified in the brief. Key behaviors:
- `dispatch()`: checks confidence filter, builds channels, calls Worker, returns result dict, never raises
- `dispatch_background()`: wraps `dispatch()` for `asyncio.create_task()`, swallows all exceptions

**Step 5 — agent/tools/registry.py**

Implement with `@lru_cache(maxsize=1)` on `load_registry()`. The cache means the YAML is read once at startup, not on every request. `reload_registry()` busts the cache for development.

**Step 6 — Update catalog/tools/tool_registry.yaml**

Replace `tools: []` with the `notify` tool entry from the brief. Preserve all schema comments below it.

**Step 7 — Update agent/main.py**

Three changes only:
1. Add `notify: Optional[NotifyConfig] = None` to `AskRequest`
2. After saving case file in `ask_task()`, add the `asyncio.create_task(notifier.dispatch_background(...))` call
3. Add `GET /notify/status/{job_id}` returning 404

Do not change any other endpoint. Do not change the planner call. Do not change the dispatcher call.

**Step 8 — Tests**

Write `agent/tests/test_notifier.py` — all four tests from the brief.
Write `agent/tests/test_tool_registry.py` — all five tests from the brief.

Run all tests:
```bash
python -m pytest agent/tests/ -v
```

All prior tests must pass. Eight new tests must pass.

**Step 9 — Frontend**

Add to `frontend/index.html` and `frontend/app.js`:
- Collapsible notification panel below the question input
- Email input, webhook input, confidence checkboxes (High/Medium checked by default, Low unchecked)
- `buildNotifyConfig()` function — returns null if both inputs are empty
- Include notify config in POST body only when non-null
- "Notification sent" indicator in right panel after response (optimistic)

**Step 10 — Environment and docs**

Add to `.env.example`:
```bash
NOTIFY_WORKER_URL=http://localhost:8789
RESEND_API_KEY=re_...
```

Update README with:
- How to get a free Resend API key (resend.com, free tier: 3,000 emails/month)
- How to set `RESEND_API_KEY` as Railway environment variable
- Note that `from` address in the Worker requires a verified domain for production sends

## Verifying fire-and-forget behavior

After completing Step 7, manually verify the notification is non-blocking:

```bash
# Start agent and notify Worker
# POST a request with a webhook URL pointing to a public echo service
# e.g., https://webhook.site (free, generates a test URL)

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Tell me about parcel P48165",
    "context": {"county": "skagit"},
    "notify": {
      "webhook": "https://webhook.site/your-test-id"
    }
  }'
```

The response should return in normal time (~3–5 seconds for live GIS query). The webhook.site dashboard should show the POST arriving 1–3 seconds after the response. If the response waits for the webhook, the fire-and-forget is broken — check `asyncio.create_task()` is being used, not `await`.

## Verifying the tool registry is code-change-free

After completing Step 6, verify that adding a hypothetical second tool to `tool_registry.yaml` is found by the registry without changing any Python:

```python
# In a Python shell:
from agent.tools.registry import reload_registry, find_tools_by_trigger

# Manually add a temp tool to tool_registry.yaml with trigger "test trigger phrase"
reload_registry()
tools = find_tools_by_trigger("this is a test trigger phrase query")
print(tools)  # Should find the temp tool
```

Remove the temp tool entry after verifying. This confirms the registry pattern is working correctly before Phase 5 adds real tools.

## Definition of done

- [ ] `python -m pytest agent/tests/ -v` — all prior tests pass, 8 new tests pass
- [ ] `npm run typecheck` passes in `workers/notify-adapter/`
- [ ] `GET /job/{job_id}` returns correct status after agent restart (sqlite confirmed)
- [ ] `POST /ask` with `notify.webhook` delivers to webhook.site within 3 seconds of response
- [ ] `POST /ask` with `notify.on_confidence: ["high"]` skips notification on `medium` answer
- [ ] Worker failure (e.g., wrong URL) does not affect `/ask` response
- [ ] `catalog/tools/tool_registry.yaml` has `notify` tool with all required fields
- [ ] Adding a second tool to YAML is found by `find_tools_by_trigger()` without Python changes
- [ ] Frontend notification panel renders, submits, and shows confirmation indicator
- [ ] `/notify/status/{job_id}` returns 404 (scaffold confirmed)
- [ ] `RESEND_API_KEY` documented in README with setup instructions
- [ ] No Phase 1, 2, or 3 test regressions
