# Codex Prompt — Civic Intelligence Platform Phase 2

---

Phase 1 is complete and verified. You are building Phase 2 on top of it.

**Do not modify any Phase 1 file unless the brief explicitly says to.** Phase 1 tests must continue passing throughout this build.

Read `phase-2-codex-brief.md` completely before writing any code.

## What Phase 2 adds

Multi-source routing across all Skagit county systems and federal financial sources. Concurrent evidence gathering. Saved, shareable, exportable case files. Async job queue scaffold. Tool registry placeholder.

## Hard rules carried forward from Phase 1

All Phase 1 rules still apply without exception:

1. Frontend uses `fetch()` only. No SDKs.
2. Only `agent/model.py` imports or calls the Anthropic API.
3. No civic data stored. D1 holds source metadata and case file records only.
4. Every `/ask` returns a `job_id`.
5. Workers never crash. All errors return `{ "success": false, "error": "..." }` with HTTP 200.
6. Python adapters call Workers, not external APIs directly — except `federal.py` which calls USASpending and SAM.gov directly (those are stable public JSON APIs with no CORS constraint server-side).

## New hard rules for Phase 2

7. **Concurrent steps must not cancel on partial failure.** Use `asyncio.gather(*tasks, return_exceptions=True)`. A flood query timeout must not abort a parcels query.
8. **Source discovery before implementation.** Before writing `skagit_web.yaml`, fetch the actual Skagit County Treasurer and Auditor search pages to find real form endpoints and field names. If an endpoint cannot be confirmed, set `config.endpoint: ""` and `status: "needs_manual_config"`. Do not fabricate URLs.
9. **FEMA NFHL requires no new Worker.** It speaks ArcGIS REST. Add it to the source catalog. The existing arcgis_adapter handles it.
10. **Tool registry is a schema document, not an implementation.** `catalog/tools/tool_registry.yaml` gets schema comments and `tools: []`. No tool Workers are built in Phase 2.

## Build order — follow exactly

**Step 1 — Source discovery**

Before writing any catalog YAML, attempt to fetch the Skagit County Treasurer search page:

```
https://www.skagitcounty.net/Departments/Treasurer
```

Inspect the HTML for `<form>` elements. Record:
- The form `action` attribute (the POST endpoint)
- The `<input name="">` values for parcel number and owner name fields

Do the same for the Auditor search page. Write what you find into `catalog/seeds/skagit_web.yaml`. If a page is unreachable or has no parseable form, mark the source `status: "needs_manual_config"` and continue. Do not block on this.

**Step 2 — Catalog seeds**
- Write `catalog/seeds/skagit_web.yaml` with discovered endpoints
- Write `catalog/seeds/federal.yaml` with FEMA, USASpending, SAM entries
- Update `catalog/seeds/seed.py` to also seed these new files

**Step 3 — web-adapter Worker**
- Create `workers/web-adapter/` with the interface from the brief
- Implement `form_post`, `query_string`, `json_post` request types
- Implement `parseHtmlTable()` — find first `<table>`, headers from first `<tr>`, rows as objects
- Test locally with `wrangler dev` on port 8788

**Step 4 — Python adapters**
- `agent/adapters/web.py` — calls web-adapter Worker
- `agent/adapters/federal.py` — calls USASpending and SAM.gov directly

**Step 5 — Jobs scaffold**
- `agent/jobs.py` — in-memory store, `create_job`, `get_job`, `complete_job`, `fail_job`, `run_job`

**Step 6 — Dispatcher + tests**
- `agent/dispatcher.py` — routes plan steps by source type
- `agent/tests/test_dispatcher.py` — all three tests from the brief

**Step 7 — Export + tests**
- `agent/export.py` — `to_json` and `to_markdown`
- `agent/tests/test_export.py` — all three tests

**Step 8 — main.py updates**
- Add `/job/{job_id}`, `/case/{id}`, `/export/{id}`, `/cases` endpoints
- Update `/ask` to use `jobs.run_job` and concurrent `asyncio.gather` dispatch
- Do not break any Phase 1 endpoint or test

**Step 9 — Updated planner**
- Add new domains to the system prompt
- Add multi-source guidance for investment/development questions

**Step 10 — Tool registry**
- Create `catalog/tools/tool_registry.yaml` with full schema comments and `tools: []`

**Step 11 — Frontend updates**
- Add share button (copy `/case/{id}` link to clipboard)
- Add export button (fetch markdown, trigger browser download)
- Add history panel (fetch `/cases`, render recent questions, click to load)

**Step 12 — Golden fixture**
- Create `agent/tests/fixtures/p48165_land_flip_expected.json`
- Write a live golden test behind `RUN_LIVE_GOLDEN=1`

## After each step

Run all tests before moving on:

```bash
pytest agent/tests/ -v
```

Phase 1 tests must stay green throughout. Any Phase 1 regression is a blocker.

## Handling unreachable county web sources

If the Skagit Treasurer or Auditor endpoints cannot be reached or parsed during source discovery:

1. Set `config.endpoint: ""` in the YAML
2. Add `status: "needs_manual_config"` to that source entry
3. The `web.py` adapter already handles missing endpoints gracefully — it returns a structured error without crashing
4. Continue building. The system degrades gracefully when a source has no endpoint configured.
5. Add a note in the README under "Sources requiring manual configuration"

Do not skip building the web-adapter Worker just because a specific endpoint is unknown. The Worker is needed for any future web source including ones with confirmed endpoints.

## Concurrent execution — verify this explicitly

After completing Step 8, write a quick manual test in the Python shell:

```python
import asyncio
from agent.dispatcher import execute_step

async def test_concurrent():
    steps = [
        {"step": 1, "domain": "parcels", "query_type": "by_parcel",
         "reason": "Get parcel", "entity": "P48165", "entity_type": "parcel"},
        {"step": 2, "domain": "zoning", "query_type": "by_parcel",
         "reason": "Get zoning", "entity": "P48165", "entity_type": "parcel"},
    ]
    results = await asyncio.gather(*[execute_step(s) for s in steps],
                                   return_exceptions=True)
    for r in results:
        print(r.get("source_id"), r.get("success"), r.get("count"))

asyncio.run(test_concurrent())
```

Both results should print. Neither should block on the other.

## Definition of done

- [ ] `pytest agent/tests/ -v` passes with zero failures
- [ ] All Phase 1 tests still pass
- [ ] `POST /ask` with `"Is P48165 a good land flip?"` returns evidence from at least 2 live sources
- [ ] Missing domains named explicitly in response
- [ ] `GET /case/{id}` retrieves the saved case file
- [ ] `GET /export/{id}?format=markdown` returns downloadable Markdown
- [ ] `GET /cases` returns history
- [ ] Frontend share, export, and history working
- [ ] FEMA NFHL query confirmed routing through existing arcgis_adapter
- [ ] `catalog/tools/tool_registry.yaml` exists with schema and empty tools list
- [ ] `RUN_LIVE_GOLDEN=1 pytest` passes for land flip fixture
- [ ] No Phase 1 file was modified except `agent/planner.py` and `agent/main.py`
