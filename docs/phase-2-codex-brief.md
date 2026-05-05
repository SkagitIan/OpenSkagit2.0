# Phase 2 Codex Brief
## Civic Intelligence Platform — Full Skagit + Federal Financial

**Builds on:** Phase 1 verified and passing. All Phase 1 modules remain unchanged unless explicitly noted.

**Goal:** A multi-source planner that routes across all Skagit county sources and federal financial sources, assembles evidence from several live systems, saves and exports case files, and scaffolds the async job queue for Phase 4 analysis tools.

**Exit criteria:** `POST /ask` with `"Is parcel P48165 a good land flip?"` returns a full multi-source memo drawing from assessor, GIS, treasurer, and auditor data — with gaps named explicitly — saved as a retrievable case file.

---

## What changes in Phase 2

```
New Workers
  workers/web-adapter/          ← Skagit Treasurer, Auditor, Permits
  (arcgis_adapter reused)       ← FEMA NFHL uses existing Worker

New agent modules
  agent/adapters/web.py         ← calls web-adapter Worker
  agent/adapters/federal.py     ← USASpending + SAM.gov REST APIs
  agent/dispatcher.py           ← routes plan steps to correct adapter
  agent/jobs.py                 ← async job queue scaffold
  agent/export.py               ← case file PDF + JSON export

Modified agent modules
  agent/planner.py              ← multi-source domain awareness
  agent/main.py                 ← /job polling, /case/{id}, /export/{id}

New catalog seeds
  catalog/seeds/skagit_web.yaml
  catalog/seeds/federal.yaml

New tools (scaffold only)
  catalog/tools/tool_registry.yaml  ← schema + placeholder entries

New frontend features
  Case file panel: share link, export button
  Job polling: progress states beyond spinner
  History: previously answered questions
```

---

## Ticket 1 — web-adapter Cloudflare Worker

**Directory:** `workers/web-adapter/`

This Worker handles county sources that are not ArcGIS REST. In Phase 2 that means Skagit Treasurer and Auditor, which expose query endpoints discoverable via their web interfaces.

**`wrangler.toml`:**

```toml
name = "web-adapter"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
ALLOWED_ORIGINS = "https://your-frontend.pages.dev,http://localhost:3000"
```

**Interface — `src/index.ts`:**

```typescript
interface WebRequest {
  source_id: string;
  endpoint: string;         // full URL to POST or GET
  method: "GET" | "POST";
  query_type: "form_post" | "query_string" | "json_post";
  params: Record<string, string>;
  response_format: "html_table" | "json" | "xml";
  extract_fields?: string[]; // field names to pull from response
}

interface WebResponse {
  success: boolean;
  records: Record<string, unknown>[];
  count: number;
  source_url: string;
  raw_excerpt?: string;   // first 500 chars of raw response for debugging
  error?: string;
}
```

**Worker logic:**

1. For `form_post`: send `params` as `application/x-www-form-urlencoded`.
2. For `query_string`: append `params` to the URL as query parameters, GET request.
3. For `json_post`: send `params` as `application/json` body.
4. For `response_format: "html_table"`: parse the HTML response, extract the first `<table>` found, convert rows to an array of objects using the first `<tr>` as headers.
5. For `response_format: "json"`: parse directly as JSON, return records array.
6. Timeout: 15 seconds. Return structured error, never throw.
7. Include `raw_excerpt` in all responses for debugging.
8. Set CORS headers for allowed origins.

**HTML table parser requirements:**

Write a standalone `parseHtmlTable(html: string): Record<string, unknown>[]` function. It must:
- Find the first `<table>` element in the HTML string.
- Use the first `<tr>` as column headers (strip HTML tags from header cells).
- Return one object per subsequent `<tr>`, keyed by header names.
- Strip all HTML tags from data cell values.
- Return `[]` (not an error) if no table is found.

---

## Ticket 2 — Skagit Web Source Catalog Entries

**File:** `catalog/seeds/skagit_web.yaml`

Research the Skagit County Treasurer and Auditor web portals to find their search endpoints. Use the pattern below. If a form POST endpoint is not discoverable, use `query_string` with known URL parameters.

```yaml
sources:
  skagit_treasurer:
    name: "Skagit County Treasurer"
    type: web
    base_url: "https://www.skagitcounty.net/Departments/Treasurer"
    domains:
      - taxes
      - levy
      - delinquency
      - assessments
    supports:
      - query_by_parcel
      - query_by_owner
    config:
      endpoint: ""           # fill in discovered search endpoint
      method: "POST"
      query_type: "form_post"
      response_format: "html_table"
      parcel_param: ""       # the form field name for parcel number
      owner_param: ""        # the form field name for owner name

  skagit_auditor:
    name: "Skagit County Auditor"
    type: web
    base_url: "https://www.skagitcounty.net/Departments/AuditorRecording"
    domains:
      - recorded_documents
      - ownership_history
      - easements
      - deeds
    supports:
      - query_by_parcel
      - query_by_name
      - query_by_date
    config:
      endpoint: ""
      method: "POST"
      query_type: "form_post"
      response_format: "html_table"
      parcel_param: ""
      name_param: ""
```

**Source discovery instructions for Codex:**

Use `fetch()` with browser-like headers to GET the Treasurer and Auditor search pages. Inspect the HTML for `<form>` elements — the `action` attribute gives you the endpoint, and `<input>` names give you the parameter names. Fill in the `config` fields from what you find. If a source cannot be discovered programmatically, leave `config.endpoint` as an empty string and add a `status: "needs_manual_config"` field — do not fabricate endpoints.

---

## Ticket 3 — Federal Source Catalog Entries

**File:** `catalog/seeds/federal.yaml`

FEMA NFHL uses the existing arcgis_adapter Worker. USASpending and SAM use their public REST APIs via the federal adapter.

```yaml
sources:
  federal_fema_nfhl:
    name: "FEMA National Flood Hazard Layer"
    type: arcgis_rest
    base_url: "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer"
    domains:
      - flood
      - flood_zone
      - fema
      - hazard
    supports:
      - query_by_geometry
      - query_by_attribute
    config:
      layer_id: 28           # SFHA / Flood Hazard Zones layer
      zone_field: "FLD_ZONE"
      description_field: "ZONE_SUBTY"
      note: "Supersedes skagit_flood for federal flood data"

  federal_usaspending:
    name: "USASpending.gov"
    type: rest_api
    base_url: "https://api.usaspending.gov/api/v2"
    domains:
      - federal_spending
      - contracts
      - grants
      - awards
    supports:
      - query_by_recipient
      - query_by_location
      - query_by_cfda
    config:
      awards_endpoint: "/search/spending_by_award/"
      geo_endpoint: "/search/spending_by_geography/"
      requires_auth: false

  federal_sam:
    name: "SAM.gov Entity Registry"
    type: rest_api
    base_url: "https://api.sam.gov/entity-information/v3"
    domains:
      - federal_contractors
      - entity_registration
      - business
    supports:
      - query_by_name
      - query_by_uei
      - query_by_cage
    config:
      entity_endpoint: "/entities"
      requires_auth: true
      auth_type: "api_key"
      auth_header: "X-Api-Key"
      note: "Requires SAM_API_KEY env var. Free registration at sam.gov."
```

Update `.env.example` to add `SAM_API_KEY=`.

---

## Ticket 4 — Federal Adapter (Python)

**File:** `agent/adapters/federal.py`

Handles USASpending and SAM.gov. These are public REST APIs called directly from the agent — no Worker needed because they are stable, well-documented JSON APIs with no CORS issues server-side.

```python
import os
import httpx
from typing import Optional

SAM_API_KEY = os.environ.get("SAM_API_KEY", "")

async def query_usaspending(
    endpoint: str,
    payload: dict
) -> dict:
    """
    POST to USASpending API endpoint.
    Returns normalized response with records list.
    Never raises.
    """
    base = "https://api.usaspending.gov/api/v2"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{base}{endpoint}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "records": data.get("results", []),
                "count": data.get("page_metadata", {}).get("total", 0),
                "source_url": f"{base}{endpoint}"
            }
    except Exception as e:
        return {"success": False, "records": [], "count": 0, "error": str(e)}


async def query_sam(
    params: dict
) -> dict:
    """
    GET SAM.gov entity registry.
    Returns normalized response with records list.
    Requires SAM_API_KEY in environment.
    Never raises.
    """
    if not SAM_API_KEY:
        return {
            "success": False,
            "records": [],
            "count": 0,
            "error": "SAM_API_KEY not configured"
        }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://api.sam.gov/entity-information/v3/entities",
                params={**params, "api_key": SAM_API_KEY}
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "records": data.get("entityData", []),
                "count": data.get("totalRecords", 0),
                "source_url": "https://api.sam.gov/entity-information/v3/entities"
            }
    except Exception as e:
        return {"success": False, "records": [], "count": 0, "error": str(e)}
```

---

## Ticket 5 — Web Adapter (Python)

**File:** `agent/adapters/web.py`

Calls the web-adapter Cloudflare Worker.

```python
import os
import httpx

WEB_WORKER_URL = os.environ.get("WEB_WORKER_URL", "http://localhost:8788")


async def query(
    source: dict,
    query_type: str,
    params: dict
) -> dict:
    """
    Call the web-adapter Cloudflare Worker.
    source: row from sources table with config deserialized
    query_type: "query_by_parcel" | "query_by_owner" | "query_by_name"
    params: {"parcel_id": "P48165"} or {"owner_name": "SMITH"}
    
    Builds the WebRequest from source config + params.
    Returns normalized response dict.
    Never raises.
    """
    config = source.get("config", {})
    
    # Map query_type to the right param key and value
    form_params = _build_form_params(config, query_type, params)
    
    if not config.get("endpoint"):
        return {
            "success": False,
            "records": [],
            "count": 0,
            "error": f"Source {source['id']} has no configured endpoint"
        }
    
    payload = {
        "source_id": source["id"],
        "endpoint": config["endpoint"],
        "method": config.get("method", "POST"),
        "query_type": config.get("query_type", "form_post"),
        "params": form_params,
        "response_format": config.get("response_format", "html_table"),
    }
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{WEB_WORKER_URL}/query",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"success": False, "records": [], "count": 0, "error": str(e)}


def _build_form_params(config: dict, query_type: str, params: dict) -> dict:
    """Map logical query params to source-specific form field names."""
    if query_type == "query_by_parcel":
        key = config.get("parcel_param", "parcel")
        return {key: params.get("parcel_id", "")}
    elif query_type == "query_by_owner":
        key = config.get("owner_param", "owner")
        return {key: params.get("owner_name", "")}
    elif query_type == "query_by_name":
        key = config.get("name_param", "name")
        return {key: params.get("name", "")}
    else:
        return params
```

Update `.env.example` to add `WEB_WORKER_URL=http://localhost:8788`.

---

## Ticket 6 — Dispatcher

**File:** `agent/dispatcher.py`

Routes each plan step to the correct adapter based on source type.

```python
from agent.catalog.sources import get_sources_for_domains, get_source
from agent.adapters import arcgis, web, federal


async def execute_step(step: dict) -> dict:
    """
    Execute one plan step. Returns an evidence item or error dict.
    
    step schema:
    {
      "step": 1,
      "domain": "parcels",
      "query_type": "by_parcel",
      "reason": "...",
      "entity": "P48165",
      "entity_type": "parcel"
    }
    """
    sources = get_sources_for_domains([step["domain"]])
    
    if not sources:
        return {
            "success": False,
            "domain": step["domain"],
            "error": f"No source registered for domain: {step['domain']}"
        }
    
    # Use first matching active source
    source = sources[0]
    source_type = source["type"]
    
    params = _build_params(step)
    
    if source_type == "arcgis_rest":
        result = await arcgis.query(
            source=source,
            query_type=step["query_type"].replace("by_", "by_"),
            params=params
        )
    elif source_type == "web":
        result = await web.query(
            source=source,
            query_type=f"query_{step['query_type']}",
            params=params
        )
    elif source_type == "rest_api":
        result = await _dispatch_rest_api(source, step, params)
    else:
        return {
            "success": False,
            "domain": step["domain"],
            "error": f"Unknown source type: {source_type}"
        }
    
    return {
        "source_id": source["id"],
        "source_name": source["name"],
        "domain": step["domain"],
        "success": result.get("success", False),
        "data": result.get("features", result.get("records", [])),
        "count": result.get("count", 0),
        "error": result.get("error"),
    }


async def _dispatch_rest_api(source: dict, step: dict, params: dict) -> dict:
    """Route rest_api sources to their specific implementations."""
    if source["id"] == "federal_usaspending":
        payload = _build_usaspending_payload(step, params)
        return await federal.query_usaspending(
            source["config"]["awards_endpoint"], payload
        )
    elif source["id"] == "federal_sam":
        return await federal.query_sam(params)
    else:
        return {
            "success": False,
            "records": [],
            "count": 0,
            "error": f"No handler for rest_api source: {source['id']}"
        }


def _build_params(step: dict) -> dict:
    """Build adapter params from a plan step."""
    entity = step.get("entity", "")
    entity_type = step.get("entity_type", "parcel")
    query_type = step.get("query_type", "by_parcel")
    
    if query_type == "by_parcel":
        return {"parcel_id": entity, "where": f"PARCELID = '{entity}'"}
    elif query_type == "by_address":
        return {"where": f"SITEADDRESS LIKE '%{entity}%'"}
    elif query_type == "by_owner":
        return {"owner_name": entity}
    else:
        return {"where": "1=1", "return_count": 5}


def _build_usaspending_payload(step: dict, params: dict) -> dict:
    """Build USASpending search payload from plan step."""
    return {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],
            "recipient_search_text": [params.get("parcel_id", "")]
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Description"],
        "page": 1,
        "limit": 10,
        "sort": "Award Amount",
        "order": "desc"
    }
```

---

## Ticket 7 — Async Job Queue Scaffold

**File:** `agent/jobs.py`

Phase 2 scaffold. Jobs run synchronously now but the interface is async-ready. Phase 4 plugs a real queue in here without changing anything upstream.

```python
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

# In-memory store for Phase 2 (Phase 4 replaces with persistent queue)
_jobs: dict[str, dict] = {}


def create_job() -> str:
    """Create a new job and return its ID."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "error": None
    }
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    """Fetch job status and result."""
    return _jobs.get(job_id)


def complete_job(job_id: str, result: dict) -> None:
    """Mark a job complete with its result."""
    if job_id in _jobs:
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = result
        _jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()


def fail_job(job_id: str, error: str) -> None:
    """Mark a job failed."""
    if job_id in _jobs:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = error


async def run_job(
    job_id: str,
    task: Callable[[], Awaitable[dict]]
) -> dict:
    """
    Run a task synchronously (Phase 2).
    In Phase 4, this becomes a background task dispatch.
    Always returns the result dict.
    """
    try:
        result = await task()
        complete_job(job_id, result)
        return result
    except Exception as e:
        fail_job(job_id, str(e))
        raise
```

---

## Ticket 8 — Case File Export

**File:** `agent/export.py`

```python
import json
from datetime import datetime

def to_json(case_file: dict) -> str:
    """
    Serialize a case file to formatted JSON string.
    Suitable for download as .json file.
    """
    return json.dumps(case_file, indent=2, default=str)


def to_markdown(case_file: dict) -> str:
    """
    Serialize a case file to Markdown string.
    Used as the basis for the PDF export and for sharing.
    """
    lines = []
    lines.append(f"# Civic Intelligence Case File")
    lines.append(f"\n**Entity:** {case_file.get('entity', 'Unknown')}")
    lines.append(f"**Question:** {case_file.get('question', '')}")
    lines.append(f"**Confidence:** {case_file.get('confidence', 'unknown').upper()}")
    lines.append(f"**Generated:** {case_file.get('created_at', '')}")
    lines.append(f"\n---\n")
    lines.append(f"## Answer\n")
    lines.append(case_file.get('answer', 'No answer generated.'))
    lines.append(f"\n## Evidence\n")
    
    for item in case_file.get('evidence', []):
        lines.append(f"### {item.get('source_name', item.get('source_id', 'Unknown'))}")
        data = item.get('data', [])
        if isinstance(data, list) and data:
            for record in data[:3]:  # cap at 3 records per source
                if isinstance(record, dict):
                    for k, v in record.items():
                        lines.append(f"- **{k}:** {v}")
        lines.append("")
    
    if case_file.get('missing'):
        lines.append(f"## Missing Evidence\n")
        for item in case_file['missing']:
            lines.append(f"- {item}")
    
    lines.append(f"\n## Sources Queried\n")
    for source_id in case_file.get('sources_queried', []):
        lines.append(f"- {source_id}")
    
    return "\n".join(lines)
```

No PDF library in Phase 2. The `/export/{id}` endpoint returns Markdown. PDF generation is a Phase 5 concern.

---

## Ticket 9 — Updated main.py

Add new endpoints to the existing FastAPI app. Do not remove any Phase 1 endpoints.

**New endpoints:**

```python
@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Poll job status.
    Returns: { job_id, status, result? }
    status: "pending" | "complete" | "error"
    """
    ...

@app.get("/case/{case_file_id}")
async def get_case_file(case_file_id: str):
    """
    Retrieve a saved case file by ID.
    Returns full AskResponse.
    """
    ...

@app.get("/export/{case_file_id}")
async def export_case_file(case_file_id: str, format: str = "markdown"):
    """
    Export a case file.
    format: "markdown" | "json"
    Returns: PlainTextResponse or JSONResponse
    """
    ...

@app.get("/cases")
async def list_cases(limit: int = 20, offset: int = 0):
    """
    List recent case files. For history panel in frontend.
    Returns: { cases: [{ id, entity, question, confidence, created_at }] }
    """
    ...
```

**Updated /ask execution flow:**

```
1.  Generate job_id via jobs.create_job()
2.  Define ask_task() as async closure:
    a. Call planner.create_plan(question, context)
    b. Execute each plan step via dispatcher.execute_step()
       - Run steps concurrently where possible (asyncio.gather)
       - Collect evidence items and missing domains
    c. Call case_file.build(question, entity, evidence, missing)
    d. Call analyst.respond(question, case_file)
    e. Add answer to case_file
    f. Save case_file to D1
    g. Return AskResponse
3.  Call jobs.run_job(job_id, ask_task)
4.  Return AskResponse with job_id immediately
```

**Concurrent step execution:**

Steps that query independent sources should run concurrently. Use `asyncio.gather()` for steps that share no dependency. A step for `parcels` and a step for `flood` can run in parallel. If one fails, the others continue — don't cancel on partial failure.

```python
tasks = [dispatcher.execute_step(step) for step in plan["steps"]]
results = await asyncio.gather(*tasks, return_exceptions=True)

evidence = []
missing = []
for step, result in zip(plan["steps"], results):
    if isinstance(result, Exception):
        missing.append(step["domain"])
    elif result.get("success") and result.get("count", 0) > 0:
        evidence.append(result)
    else:
        missing.append(step["domain"])
```

---

## Ticket 10 — Updated Planner

**File:** `agent/planner.py` (modify existing)

Update the system prompt to include the new domains. The planner logic is otherwise unchanged.

Add to the `Available domains` line in `PLANNER_SYSTEM`:

```
parcels, zoning, flood, assessor, ownership, planning,
taxes, levy, delinquency, recorded_documents, ownership_history,
easements, permits, federal_spending, federal_contractors
```

Add to the system prompt:

```
For investment or development questions, include taxes and recorded_documents steps.
For federal land or spending questions, include federal_spending steps.
Multi-source questions should produce 3-6 steps covering distinct domains.
```

---

## Ticket 11 — Tool Registry Schema (placeholder)

**File:** `catalog/tools/tool_registry.yaml`

Create the schema now. No tools are implemented in Phase 2. This is the contract that Phase 4 tools will conform to.

```yaml
# Tool Registry — Civic Intelligence Platform
# Each tool is a Cloudflare Worker registered here.
# The planner checks this registry before assembling a plan.
# If a tool matches the question's intent, it is dispatched instead of
# (or in addition to) the standard evidence assembly flow.

tools: []

# Tool schema reference:
#
# - id: string, unique snake_case identifier
#   name: string, human-readable
#   type: analysis | report | dashboard
#   runtime: sync | async
#   worker_url_env: string, env var name holding the Worker URL
#   triggers:
#     - list of keywords/phrases that route to this tool
#   input_domains:
#     - list of source domains this tool requires
#   output_format: case_file | report | dataset | chart_data
#   description: string
#
# Example (not active):
#
# - id: neighborhood_regression
#   name: "Neighborhood Regression Analysis"
#   type: analysis
#   runtime: async
#   worker_url_env: REGRESSION_WORKER_URL
#   triggers:
#     - "regression"
#     - "market analysis"
#     - "comp analysis"
#     - "price trends"
#   input_domains:
#     - parcels
#     - assessor
#     - recorded_documents
#   output_format: report
#   description: >
#     Batch-gathers parcels in a geographic area, pulls sales and assessor
#     data, runs linear regression on price per sqft over time, and
#     returns a structured report with charts.
```

---

## Ticket 12 — Updated Frontend

**File:** `frontend/app.js` (modify existing)

Add three capabilities to the existing frontend. Do not break Phase 1 behavior.

**1. Case file share link**

After a successful response, render a share button in the right panel. On click, copy `{API_BASE}/case/{case_file_id}` to clipboard and show a "Link copied" confirmation for 2 seconds.

```javascript
function renderShareButton(caseFileId) {
  const btn = document.createElement('button');
  btn.textContent = 'Copy link';
  btn.onclick = async () => {
    await navigator.clipboard.writeText(`${API_BASE}/case/${caseFileId}`);
    btn.textContent = 'Link copied';
    setTimeout(() => { btn.textContent = 'Copy link'; }, 2000);
  };
  return btn;
}
```

**2. Export button**

Add an export button next to the share button. On click, fetch `/export/{case_file_id}?format=markdown` and trigger a browser download.

```javascript
async function exportCaseFile(caseFileId) {
  const response = await fetch(`${API_BASE}/export/${caseFileId}?format=markdown`);
  const text = await response.text();
  const blob = new Blob([text], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `case-${caseFileId}.md`;
  a.click();
  URL.revokeObjectURL(url);
}
```

**3. Question history sidebar (collapsed by default on mobile)**

Add a history section at the bottom of the left panel. On load, fetch `GET /cases?limit=10` and render a list of previous questions. Clicking one re-renders its case file in the right panel by fetching `GET /case/{id}`.

```javascript
async function loadHistory() {
  const response = await fetch(`${API_BASE}/cases?limit=10`);
  const data = await response.json();
  renderHistory(data.cases);
}

function renderHistory(cases) {
  // Render list of { id, entity, question, confidence, created_at }
  // Each item: question text truncated to 60 chars + confidence badge
  // On click: fetch /case/{id} and call renderCaseFile()
}
```

---

## Ticket 13 — Test Suite Updates

**File:** `agent/tests/test_dispatcher.py` (new)

```python
import pytest
from unittest.mock import AsyncMock, patch
from agent.dispatcher import execute_step

MOCK_ARCGIS_SUCCESS = {
    "success": True,
    "features": [{"attributes": {"PARCELID": "P48165"}}],
    "count": 1,
    "source_url": "..."
}

@pytest.mark.asyncio
async def test_dispatcher_routes_arcgis():
    with patch("agent.dispatcher.arcgis.query", new=AsyncMock(return_value=MOCK_ARCGIS_SUCCESS)):
        with patch("agent.dispatcher.get_sources_for_domains", return_value=[{
            "id": "skagit_parcels",
            "name": "Skagit County Parcels",
            "type": "arcgis_rest",
            "base_url": "https://...",
            "config": {"layer_id": 0}
        }]):
            result = await execute_step({
                "step": 1,
                "domain": "parcels",
                "query_type": "by_parcel",
                "reason": "Get parcel facts",
                "entity": "P48165",
                "entity_type": "parcel"
            })
    assert result["success"] is True
    assert result["source_id"] == "skagit_parcels"
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_dispatcher_returns_error_for_unknown_domain():
    with patch("agent.dispatcher.get_sources_for_domains", return_value=[]):
        result = await execute_step({
            "step": 1,
            "domain": "nonexistent_domain",
            "query_type": "by_parcel",
            "reason": "...",
            "entity": "P48165",
            "entity_type": "parcel"
        })
    assert result["success"] is False
    assert "error" in result
    # Must not raise


@pytest.mark.asyncio
async def test_concurrent_steps_continue_on_partial_failure():
    # One step succeeds, one fails — both should complete
    call_count = 0
    async def mock_execute(step):
        nonlocal call_count
        call_count += 1
        if step["domain"] == "flood":
            raise Exception("Flood source timeout")
        return {"success": True, "source_id": "skagit_parcels",
                "domain": "parcels", "data": [], "count": 1}
    
    with patch("agent.dispatcher.execute_step", side_effect=mock_execute):
        import asyncio
        steps = [
            {"domain": "parcels", "query_type": "by_parcel", "entity": "P48165"},
            {"domain": "flood", "query_type": "by_geometry", "entity": "P48165"}
        ]
        results = await asyncio.gather(
            *[mock_execute(s) for s in steps],
            return_exceptions=True
        )
    assert call_count == 2  # Both steps ran
    assert not isinstance(results[0], Exception)  # parcels succeeded
    assert isinstance(results[1], Exception)       # flood failed gracefully
```

**File:** `agent/tests/test_export.py` (new)

```python
from agent.export import to_json, to_markdown
import json

SAMPLE_CASE_FILE = {
    "id": "cf_test123",
    "question": "Tell me about parcel P48165",
    "entity": "P48165",
    "evidence": [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit County Parcels",
            "data": [{"PARCELID": "P48165", "OWNER": "SWANSON EARLINE"}],
            "count": 1
        }
    ],
    "missing": ["flood"],
    "confidence": "medium",
    "answer": "Parcel P48165 is owned by SWANSON EARLINE.",
    "sources_queried": ["skagit_parcels"],
    "created_at": "2025-01-01T00:00:00Z"
}


def test_to_json_is_valid():
    output = to_json(SAMPLE_CASE_FILE)
    parsed = json.loads(output)
    assert parsed["id"] == "cf_test123"


def test_to_markdown_contains_key_fields():
    output = to_markdown(SAMPLE_CASE_FILE)
    assert "P48165" in output
    assert "SWANSON EARLINE" in output
    assert "medium" in output.lower()
    assert "Missing Evidence" in output
    assert "flood" in output


def test_to_markdown_caps_evidence_records():
    # Should not blow up on case files with many records
    big_cf = {**SAMPLE_CASE_FILE}
    big_cf["evidence"] = [{
        "source_id": "skagit_parcels",
        "source_name": "Skagit Parcels",
        "data": [{"PARCELID": f"P{i}"} for i in range(100)],
        "count": 100
    }]
    output = to_markdown(big_cf)
    # Should cap at 3 records per source, not dump all 100
    assert output.count("P1") == 1
```

**Update:** `agent/tests/fixtures/p48165_land_flip_expected.json`

Add a second golden fixture for the Phase 2 exit criteria question.

```json
{
  "question": "Is parcel P48165 a good land flip?",
  "entity": "P48165",
  "required_sources": ["skagit_parcels", "skagit_zoning"],
  "min_evidence_count": 2,
  "confidence_min": "medium",
  "answer_must_contain": ["P48165"],
  "answer_must_not_contain": ["I don't know", "unable to"],
  "missing_domains_acceptable": ["taxes", "recorded_documents", "flood"]
}
```

---

## Updated Environment Variables

**Additions to `.env.example`:**

```bash
# Web adapter Worker (Treasurer, Auditor, Permits)
WEB_WORKER_URL=http://localhost:8788

# SAM.gov (optional — free API key at sam.gov)
SAM_API_KEY=

# Federal FEMA — uses existing ARCGIS_WORKER_URL, no new var needed
```

---

## Updated `wrangler.toml` for arcgis-adapter

No changes needed. The existing arcgis_adapter Worker handles FEMA NFHL because FEMA uses ArcGIS REST. Add the FEMA base URL to Skagit.yaml and the existing Worker handles it.

---

## Running Order for Codex

```
1. catalog/seeds/skagit_web.yaml (source discovery required first)
2. catalog/seeds/federal.yaml
3. workers/web-adapter/ (new Worker)
4. agent/adapters/web.py
5. agent/adapters/federal.py
6. agent/jobs.py
7. agent/dispatcher.py + tests/test_dispatcher.py
8. agent/export.py + tests/test_export.py
9. agent/main.py (add new endpoints, update /ask flow)
10. catalog/tools/tool_registry.yaml
11. frontend share + export + history
12. Golden fixture: p48165_land_flip_expected.json + test
```

---

## Definition of Done — Phase 2

- [ ] `pytest agent/tests/ -v` passes with zero failures
- [ ] `POST /ask` with `"Is P48165 a good land flip?"` returns evidence from at least 2 sources
- [ ] Response includes evidence from `skagit_parcels` and at least one of: `skagit_zoning`, `skagit_treasurer`, `skagit_auditor`
- [ ] Missing domains are named explicitly in the response
- [ ] `GET /case/{id}` retrieves the saved case file
- [ ] `GET /export/{id}?format=markdown` returns a downloadable Markdown case file
- [ ] `GET /cases` returns recent case file history
- [ ] Frontend share button copies a working `/case/{id}` link
- [ ] Frontend export button downloads the Markdown file
- [ ] Frontend history section renders the 10 most recent questions
- [ ] FEMA NFHL query routes through existing arcgis_adapter with no code changes to that Worker
- [ ] Concurrent step execution confirmed: two parallel source queries complete independently
- [ ] `catalog/tools/tool_registry.yaml` exists with schema comments but empty `tools: []`
- [ ] `RUN_LIVE_GOLDEN=1 pytest agent/tests/test_golden.py -v` passes for the land flip fixture
