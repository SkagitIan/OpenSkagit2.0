# Codex Prompt — Civic Intelligence Platform Phase 1

---

You are building Phase 1 of a civic intelligence agent. The full spec is in `phase-1-codex-brief.md`. Read it completely before writing a single line of code.

## What you are building

A system that accepts a natural language question about a public parcel, queries live Skagit County GIS data through a Cloudflare Worker, assembles an evidence case file, and returns a structured cited answer through a FastAPI endpoint. A two-panel frontend renders the result.

## Repository to create

```
civic-agent/
  agent/
  workers/arcgis-adapter/
  catalog/
  frontend/
```

## Tech stack — do not deviate

- **Agent:** Python, FastAPI, uvicorn, httpx, pydantic v2
- **Worker:** TypeScript, Cloudflare Workers, wrangler
- **Catalog:** sqlite locally, Cloudflare D1 in production
- **Frontend:** Vanilla HTML + JS + CSS. No framework. No build step.
- **Tests:** pytest, pytest-asyncio, respx

## Hard rules — treat these as immutable

1. The frontend never imports or calls the Anthropic or OpenAI SDK. Use `fetch()` only.
2. The agent never calls the Anthropic API directly except in `agent/model.py`. Every other module calls `call_model()` from that file.
3. No civic data is stored in the database. D1 holds source metadata only.
4. Every `/ask` response includes a `job_id` even when resolved synchronously.
5. The arcgis_adapter Worker never crashes. On any error — timeout, bad response, network failure — it returns `{ "success": false, "error": "..." }` with HTTP 200.
6. The Python arcgis adapter never calls ArcGIS REST directly. It calls the Cloudflare Worker.

## Build order — follow exactly

Work through tickets in this sequence. Do not skip ahead.

**Step 1 — Catalog schema and seed**
- Create `catalog/schema.sql` with the three tables defined in the brief (sources, queries, case_files)
- Create `catalog/seeds/skagit.yaml` with the three Skagit sources (parcels, zoning, flood)
- Create `catalog/seeds/seed.py` — idempotent upsert script, accepts `--env local|production`

**Step 2 — arcgis_adapter Cloudflare Worker**
- Create `workers/arcgis-adapter/` with `src/index.ts`, `wrangler.toml`, `package.json`
- Implement the full `ArcGISRequest` / `ArcGISResponse` interface from the brief
- Handle `by_parcel`, `by_attribute`, and `by_geometry` query types
- Implement timeout handling, ArcGIS error surfacing, and CORS headers
- Write a local test you can run with `wrangler dev`

**Step 3 — model.py**
- Create `agent/model.py` with `call_model()` exactly as specified
- Raw `httpx` POST to Anthropic API — no SDK
- Reads `ANTHROPIC_API_KEY` from environment
- Raises `RuntimeError` on non-200 responses

**Step 4 — catalog/sources.py**
- Implement `get_source()`, `get_sources_for_domains()`, `list_sources()`
- Use local sqlite path from `D1_LOCAL_PATH` env var
- Deserialize `domains`, `supports`, and `config` JSON fields on read
- All functions return plain dicts, not sqlite Row objects

**Step 5 — adapters/arcgis.py**
- Implement `query(source, query_type, params)` calling the Worker URL
- Reads `ARCGIS_WORKER_URL` from environment
- Never raises — returns error dict on any failure

**Step 6 — case_file.py**
- Implement `build()` and `_compute_confidence()` exactly as specified
- Confidence logic: high (2+ evidence, 0 missing), medium (1+ evidence, ≤2 missing), low (everything else)
- Write all three tests in `tests/test_case_file.py`

**Step 7 — planner.py**
- Implement `create_plan()` with the system prompt from the brief
- Implement `_fallback_plan()` for JSON parse failures
- Write both tests in `tests/test_planner.py`
- The planner must never raise on malformed model output

**Step 8 — analyst.py**
- Implement `respond()` with the system prompt from the brief
- Straightforward: takes question + case file dict, returns string answer

**Step 9 — main.py**
- Wire all components into the FastAPI app
- Implement the execution flow: planner → adapter dispatch → case file → analyst → save → return
- Implement `/ask`, `/job/{job_id}`, and `/health` endpoints
- Write all four tests in `tests/test_api.py`

**Step 10 — Frontend**
- Create `frontend/index.html`, `frontend/app.js`, `frontend/style.css`
- Two-panel layout: conversation left, case file right
- Implement `ask()`, `pollJob()`, `renderConversation()`, `renderCaseFile()`, `renderEvidenceCard()`, `showConfidence()` as specified
- Polling: 1 second interval, 20 attempt maximum, "Gathering evidence..." spinner in right panel while polling
- No external fonts, no CDN calls, system font stack only

**Step 11 — Golden fixture test**
- Create `tests/fixtures/p48165_expected.json` with the schema from the brief
- Write a test that loads this fixture and validates a response structure against it
- Leave `required_evidence_fields` as `["PARCELID", "OWNER"]` — will be updated after first live run

## Environment setup

- Create `.env.example` with all variables from the brief
- Create `requirements.txt` with exact packages and minimum versions from the brief
- Create `railway.json` exactly as specified

## After each step

Run the tests for that step before moving to the next. If a test fails, fix it before continuing. Do not accumulate failures.

```bash
# Run tests for a specific module
pytest agent/tests/test_case_file.py -v

# Run all tests
pytest agent/tests/ -v
```

## When you are uncertain about a GIS endpoint URL

The Skagit County ArcGIS REST base URLs in `skagit.yaml` may need verification. If a query returns zero features or an error, try inspecting the base URL in a browser with `/layers?f=json` appended to confirm the layer structure. Do not guess layer IDs — check.

## Definition of done

All of the following must be true before Phase 1 is complete:

- [ ] `pytest agent/tests/ -v` passes with zero failures
- [ ] arcgis_adapter Worker runs locally with `wrangler dev` and responds to a test POST
- [ ] `POST /ask` with body `{"question": "Tell me about parcel P48165", "context": {"county": "skagit"}}` returns a response with real data from live Skagit GIS
- [ ] Response `confidence` is `"medium"` or `"high"`
- [ ] Response `answer` cites at least one source by name and does not contain "I don't know" or "unable to"
- [ ] Frontend renders the response in two panels with evidence cards and confidence badge
- [ ] Worker returns structured error (not a crash) when given an unreachable URL
- [ ] No file other than `agent/model.py` contains an import of `anthropic`
- [ ] No file in `frontend/` contains a reference to `anthropic` or `openai`

Do not mark Phase 1 complete until every checkbox is checked.
