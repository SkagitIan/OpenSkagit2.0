# Codex Prompt — Civic Intelligence Platform Phase 5

---

Phase 4 is complete and verified. You are building Phase 5 — the final phase.

**Do not modify any Phase 1–4 file unless the brief explicitly says to.** All 26 existing tests must continue passing.

Read `phase-5-codex-brief.md` completely before writing any code.

## What Phase 5 means

Every previous phase built the engine. Phase 5 makes it a product someone else can own. When this phase is done, a county IT manager can clone the repo, follow `docs/self-hosting.md`, and run their own branded instance — without calling you, without modifying core code, and without understanding how the agent works internally.

Every decision in this phase is made with that person in mind.

## What Phase 5 adds

API key auth on all endpoints. Audit log on every query. PDF export. Tenant white-label config. Admin dashboard. Public source registry. Self-hosting documentation. Political access risk checklist.

## Hard rules — all carry forward

1. Frontend uses `fetch()` only.
2. Only `agent/model.py` calls the Anthropic API.
3. No civic data stored. D1 holds source metadata, jobs, case files, audit log, and API keys.
4. Workers return structured errors, never crash.
5. Notification failure never affects the `/ask` response.
6. Audit failure never affects the `/ask` response.

## Phase 5 specific rules

7. **Auth is additive, not breaking.** The dev key seeded by `seed.py` must work immediately after the schema migration. Tests that call `/ask` must pass a valid key. Update existing tests to include `headers={"X-API-Key": "dev-admin-key-change-in-production"}` wherever needed.

8. **`/health` and `/config` have no auth.** Monitoring tools and the frontend need these before auth is established.

9. **Audit log never raises.** Wrap every DB write in `try/except`. A broken audit trail must not affect the answer or the response.

10. **PDF uses fpdf2 only.** No system dependencies (no wkhtmltopdf, no puppeteer, no weasyprint). `fpdf2` is pure Python and installs cleanly on Railway.

11. **Registry is documentation, not code.** The `registry/` directory is a standalone artifact — copied source YAMLs with schema docs. It does not affect the running system.

12. **Docs are written for a non-developer.** `docs/county-deployment.md` assumes the reader knows how to use a browser and follow instructions, not how to write Python.

## Build order — follow exactly

**Step 1 — Schema migration**

Add `api_keys` and `audit_log` tables to `catalog/schema.sql`. Add `seed_default_api_key()` to `catalog/seeds/seed.py`. Apply:

```bash
python catalog/seeds/seed.py --env local
sqlite3 catalog/local.db ".tables"
# Should show: api_keys, audit_log, case_files, jobs, queries, sources
sqlite3 catalog/local.db "SELECT id, name, role FROM api_keys;"
# Should show: key_dev_admin | Dev Admin | admin
```

**Step 2 — Tenant config**

Create `config/tenant.yaml` and `agent/config.py`. Write `agent/tests/test_config.py` and run it:

```bash
python -m pytest agent/tests/test_config.py -v
```

**Step 3 — Auth**

Implement `agent/auth.py` with `require_reader`, `require_writer`, `require_admin` FastAPI dependencies.

Write `agent/tests/test_auth.py`. Before adding auth to any endpoint, run the existing full test suite to confirm baseline:

```bash
python -m pytest agent/tests/ -v
```

Then add auth dependencies to the endpoints listed in the brief. After adding auth, update any existing test that calls a protected endpoint to include the dev key header. Run the full suite again — all 26 prior tests must still pass.

**Step 4 — Audit log**

Implement `agent/audit.py`. Write `agent/tests/test_audit.py`.

Add `audit.log_query(...)` to the `/ask` execution flow in `main.py`, after saving the case file, before firing the notification. Pass the `api_key_id` from the auth dependency and the client IP from `Request`.

Verify audit entries appear after a test query:

```bash
sqlite3 catalog/local.db "SELECT question, confidence, duration_ms FROM audit_log LIMIT 5;"
```

**Step 5 — PDF**

Add `fpdf2>=2.7.9` to `requirements.txt`. Install it:

```bash
pip install fpdf2
```

Implement `agent/pdf.py`. Write `agent/tests/test_pdf.py`.

Verify the PDF is valid:

```bash
python -c "
from agent.pdf import build_pdf
pdf = build_pdf({'id':'cf_test','entity':'P48165','question':'test',
  'confidence':'medium','answer':'Test answer.','evidence':[],
  'missing':[],'sources_queried':[],'created_at':'2025-01-01'})
print(f'PDF size: {len(pdf)} bytes')
print(f'Header: {pdf[:4]}')
assert pdf[:4] == b'%PDF', 'Not a valid PDF'
print('PDF valid')
"
```

Update `/export/{id}` in `main.py` to handle `format=pdf`.

**Step 6 — Admin endpoints**

Add `/admin/stats`, `/admin/sources`, `/admin/audit`, `/admin/keys`, and `/config` to `main.py`. All admin endpoints use `require_admin`. `/config` has no auth.

Test each manually:

```bash
# Stats
curl -H "X-API-Key: dev-admin-key-change-in-production" \
  http://localhost:8000/admin/stats

# Config (no auth)
curl http://localhost:8000/config
```

**Step 7 — Frontend**

Three frontend changes:

1. Replace all `fetch(API_BASE + path)` with `apiFetch(path)` using the key from localStorage
2. Add API key modal on first load
3. Add admin panel that loads on admin key detection

After frontend changes, open `frontend/index.html` in a browser with no API key in localStorage. The key modal should appear. Enter `dev-admin-key-change-in-production`. The main interface should load. The Admin link should appear in the header.

**Step 8 — Registry**

Create the `registry/` directory structure. Copy source YAMLs. Write `README.md`, `CONTRIBUTING.md`, `SCHEMA.md`.

The registry does not connect to any code. It is a documentation artifact.

**Step 9 — Docs**

Write all three docs files:

- `docs/self-hosting.md` — 10 steps, developer-audience
- `docs/county-deployment.md` — non-technical, county IT audience
- `docs/political-access-checklist.md` — full checklist from brief

**Step 10 — Full test run**

```bash
python -m pytest agent/tests/ -v
```

Expected: 26 prior tests pass (with updated headers where needed), 13+ new tests pass, 3 skipped. Zero failures.

## Updating existing tests for auth

After adding auth to endpoints, existing tests that call `/ask`, `/case/`, `/cases`, `/export/`, or `/job/` will return 401. Update them to include the dev key:

```python
# Before
response = client.post("/ask", json={...})

# After
response = client.post(
    "/ask",
    json={...},
    headers={"X-API-Key": "dev-admin-key-change-in-production"}
)
```

Do this for every affected test in `test_api.py` and any other test file that calls protected endpoints. Do not change the assertion logic — only add the header.

## Verifying the county handoff story

After completing all steps, do a full walkthrough as if you were the county IT manager receiving this repo for the first time:

1. Clone the repo to a fresh directory
2. Follow `docs/self-hosting.md` from Step 1
3. Confirm the platform is running with a test query
4. Change `config/tenant.yaml` to a fictional county name
5. Restart the agent
6. Confirm `GET /config` returns the new name
7. Confirm the frontend shows the new name after reload

If any step in `docs/self-hosting.md` fails or is unclear during this walkthrough, fix the docs. The docs are done when a non-developer can follow them without assistance.

## Definition of done

- [ ] `python -m pytest agent/tests/ -v` — 39+ tests pass (26 prior + 13 new), 3 skipped
- [ ] `POST /ask` without key returns 401
- [ ] `POST /ask` with dev key returns 200 and creates an audit log entry
- [ ] `GET /admin/stats` returns `total_queries`, `by_confidence`, `top_entities`
- [ ] `GET /export/{id}?format=pdf` returns bytes starting with `%PDF`
- [ ] `GET /config` returns display name without auth header
- [ ] Tenant name change in `config/tenant.yaml` reflected in `/config` after restart
- [ ] Frontend API key modal appears with empty localStorage
- [ ] Admin panel visible and functional with admin key
- [ ] `registry/` contains 5 source YAML files and 3 doc files
- [ ] `docs/self-hosting.md` has all 10 steps and is accurate
- [ ] `docs/political-access-checklist.md` exists and is complete
- [ ] County walkthrough completed successfully (see Verifying section above)
- [ ] `fpdf2` is the only new dependency added to requirements.txt
- [ ] No Phase 1–4 test regressions
