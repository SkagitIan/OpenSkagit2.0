# Phase 1 Codex Brief
## Civic Intelligence Platform — Prove the Loop

**Goal:** One parcel, one question, one real evidence-based answer pulled from live Skagit GIS.

**Exit criteria:** `POST /ask` with `"Tell me about parcel P48165"` returns a structured JSON response with real assessor and GIS data, a confidence score, and named evidence gaps. The frontend renders it in two panels.

**Rules that cannot be broken:**
- No Anthropic or OpenAI SDK in the frontend. `fetch()` only.
- The agent never calls a model directly. It calls an internal `/model` endpoint.
- No civic data is stored. The D1 database holds source metadata only.
- Every `/ask` call returns a `job_id`, even when resolved synchronously.
- All source queries go through the source catalog. Nothing hardcoded.

---

## Repository Structure

```
civic-agent/
  agent/
    main.py
    planner.py
    case_file.py
    analyst.py
    model.py
    adapters/
      arcgis.py
    catalog/
      sources.py
    tests/
      test_adapters.py
      test_planner.py
      test_case_file.py
      test_api.py
      fixtures/
        p48165_expected.json

  workers/
    arcgis-adapter/
      src/
        index.ts
      wrangler.toml
      package.json

  catalog/
    schema.sql
    seeds/
      skagit.yaml

  frontend/
    index.html
    app.js
    style.css

  railway.json
  requirements.txt
  .env.example
  README.md
```

---

## Ticket 1 — D1 Schema + Skagit Seed

**File:** `catalog/schema.sql`

Create these three tables. No others.

```sql
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  base_url TEXT NOT NULL,
  domains TEXT NOT NULL,
  supports TEXT NOT NULL,
  config TEXT,
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queries (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  query_params TEXT NOT NULL,
  result TEXT,
  status TEXT DEFAULT 'pending',
  error TEXT,
  duration_ms INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS case_files (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  question TEXT NOT NULL,
  entity TEXT,
  evidence TEXT NOT NULL,
  missing TEXT NOT NULL,
  confidence TEXT NOT NULL,
  answer TEXT,
  sources_queried TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
```

**File:** `catalog/seeds/skagit.yaml`

```yaml
sources:
  skagit_parcels:
    name: "Skagit County Parcels"
    type: arcgis_rest
    base_url: "https://gis.skagitcounty.net/arcgis/rest/services/Parcels/MapServer"
    domains:
      - parcels
      - assessor
      - ownership
    supports:
      - query_by_parcel
      - query_by_address
      - query_by_geometry
    config:
      layer_id: 0
      parcel_field: "PARCELID"
      owner_field: "OWNER"
      address_field: "SITEADDRESS"

  skagit_zoning:
    name: "Skagit County Zoning"
    type: arcgis_rest
    base_url: "https://gis.skagitcounty.net/arcgis/rest/services/Planning/MapServer"
    domains:
      - zoning
      - planning
      - land_use
    supports:
      - query_by_geometry
      - query_by_parcel
    config:
      layer_id: 0
      zone_field: "ZONE_CODE"
      description_field: "ZONE_DESC"

  skagit_flood:
    name: "Skagit County Flood Zones"
    type: arcgis_rest
    base_url: "https://gis.skagitcounty.net/arcgis/rest/services/FloodHazard/MapServer"
    domains:
      - flood
      - hazard
      - fema
    supports:
      - query_by_geometry
    config:
      layer_id: 0
      zone_field: "FLD_ZONE"
      description_field: "ZONE_SUBTY"
```

**Seed script:** `catalog/seeds/seed.py`

Write a script that reads `skagit.yaml` and inserts each source into the D1 `sources` table. It must be idempotent (upsert, not insert). Accept a `--env` flag for local vs production D1.

```python
# Usage:
# python catalog/seeds/seed.py --env local
# python catalog/seeds/seed.py --env production
```

---

## Ticket 2 — arcgis_adapter Cloudflare Worker

**Directory:** `workers/arcgis-adapter/`

This Worker is the only thing that touches ArcGIS REST APIs. The agent never calls ArcGIS directly.

**`wrangler.toml`:**

```toml
name = "arcgis-adapter"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
ALLOWED_ORIGINS = "https://your-frontend.pages.dev,http://localhost:3000"
```

**Interface — `src/index.ts`:**

The Worker accepts `POST` requests with this body:

```typescript
interface ArcGISRequest {
  base_url: string;
  layer_id: number;
  query_type: "by_attribute" | "by_geometry" | "by_parcel";
  params: {
    where?: string;        // for by_attribute
    geometry?: object;     // for by_geometry (GeoJSON)
    parcel_id?: string;    // for by_parcel
    out_fields?: string[]; // fields to return, default ["*"]
    return_count?: number; // max features, default 10
  };
}

interface ArcGISResponse {
  success: boolean;
  features: Feature[];
  count: number;
  source_url: string;
  error?: string;
}

interface Feature {
  attributes: Record<string, unknown>;
  geometry?: object;
}
```

**Worker logic:**

1. Validate the request body matches `ArcGISRequest`.
2. Build the ArcGIS REST query URL from `base_url`, `layer_id`, and `params`.
3. ArcGIS REST query endpoint pattern: `{base_url}/{layer_id}/query`
4. Required ArcGIS params: `f=json`, `outFields=*` (or specified fields), `returnGeometry=false` (unless geometry needed).
5. For `by_parcel`: build `where` clause as `{parcel_field} = '{parcel_id}'`.
6. For `by_attribute`: pass `where` directly.
7. For `by_geometry`: pass geometry with `spatialRel=esriSpatialRelIntersects`, `geometryType=esriGeometryPolygon`.
8. Fetch from ArcGIS, parse response, return normalized `ArcGISResponse`.
9. On ArcGIS error: return `{ success: false, features: [], count: 0, error: "..." }`. Never throw.
10. Set CORS headers for allowed origins.

**Error handling rules:**
- ArcGIS timeout (>10s): return structured error, do not hang.
- ArcGIS returns 200 but `error` field in body: surface that error.
- Network failure: return structured error.
- Never return a 500. Always return 200 with `success: false` and an `error` message.

---

## Ticket 3 — Agent: POST /ask Endpoint

**File:** `agent/main.py`

FastAPI app. Single endpoint for Phase 1. Must use `async` throughout.

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Civic Intelligence Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in Phase 5
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

@app.post("/ask")
async def ask(request: AskRequest) -> AskResponse:
    ...

@app.get("/job/{job_id}")
async def get_job(job_id: str) -> JobStatus:
    ...

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Request/response contracts:**

```python
from pydantic import BaseModel
from typing import Optional

class AskRequest(BaseModel):
    question: str
    context: Optional[dict] = {}
    # context example: {"county": "skagit", "state": "wa", "entity": "P48165"}

class EvidenceItem(BaseModel):
    source_id: str
    source_name: str
    data: dict
    retrieved_at: str

class AskResponse(BaseModel):
    job_id: str
    status: str              # "complete" | "pending" | "error"
    question: str
    answer: Optional[str]
    confidence: Optional[str]  # "high" | "medium" | "low"
    evidence: list[EvidenceItem]
    missing: list[str]
    sources_queried: list[str]
    case_file_id: Optional[str]
    error: Optional[str]

class JobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[AskResponse]
```

**Execution flow for `/ask`:**

```
1. Generate job_id (uuid4)
2. Call planner.create_plan(question, context)
3. For each step in plan:
   a. Identify source from catalog
   b. Call adapter (arcgis adapter in Phase 1)
   c. Collect evidence or record as missing
4. Call case_file.build(question, evidence, missing)
5. Call analyst.respond(question, case_file)
6. Save case_file to D1
7. Return AskResponse with job_id
```

In Phase 1 this runs synchronously. The async scaffolding is in place for Phase 2. Return `status: "complete"` immediately.

---

## Ticket 4 — Planner

**File:** `agent/planner.py`

The planner receives a question and returns a list of evidence-gathering steps. In Phase 1 it uses a simple Claude call. The plan is a JSON structure, not free text.

```python
import json
from agent.model import call_model
from agent.catalog.sources import get_sources_for_domains

PLANNER_SYSTEM = """You are a civic evidence planner. Given a question about a parcel, 
address, or civic entity, return a JSON plan listing the evidence needed and which 
source domains to query.

Return ONLY valid JSON. No explanation. No markdown.

Schema:
{
  "entity": "string — the parcel ID, address, or entity extracted from the question",
  "entity_type": "parcel | address | district | person | business",
  "steps": [
    {
      "step": 1,
      "domain": "string — one of: parcels, zoning, flood, assessor, ownership",
      "query_type": "by_parcel | by_address | by_geometry",
      "reason": "string — why this evidence matters for the question"
    }
  ],
  "ambiguous": false,
  "clarification_needed": null
}

If the question is ambiguous (no parcel ID, no address, unclear entity), 
set ambiguous to true and clarification_needed to a specific question to ask the user.

Available domains: parcels, zoning, flood, assessor, ownership, planning"""


async def create_plan(question: str, context: dict) -> dict:
    prompt = f"Question: {question}\nContext: {json.dumps(context)}"
    response = await call_model(
        system=PLANNER_SYSTEM,
        user=prompt,
        max_tokens=500
    )
    try:
        plan = json.loads(response)
        return plan
    except json.JSONDecodeError:
        # Fallback: minimal plan for parcel questions
        return _fallback_plan(question, context)


def _fallback_plan(question: str, context: dict) -> dict:
    entity = context.get("entity", "unknown")
    return {
        "entity": entity,
        "entity_type": "parcel",
        "steps": [
            {"step": 1, "domain": "parcels", "query_type": "by_parcel",
             "reason": "Get basic parcel facts"},
            {"step": 2, "domain": "zoning", "query_type": "by_parcel",
             "reason": "Get zoning designation"},
        ],
        "ambiguous": False,
        "clarification_needed": None
    }
```

---

## Ticket 5 — Model Abstraction

**File:** `agent/model.py`

The agent never imports `anthropic` directly anywhere except this file. Every other module calls `call_model()`.

```python
import os
import httpx
from typing import Optional

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


async def call_model(
    system: str,
    user: str,
    max_tokens: int = 1000,
    model: Optional[str] = None
) -> str:
    """
    Single entry point for all model calls.
    Returns the text content of the first response block.
    Raises RuntimeError on API failure.
    """
    api_key = os.environ["ANTHROPIC_API_KEY"]
    payload = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}]
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]
```

---

## Ticket 6 — ArcGIS Adapter (Python side)

**File:** `agent/adapters/arcgis.py`

This calls the Cloudflare arcgis-adapter Worker. It does not call ArcGIS directly.

```python
import os
import httpx
from typing import Optional

ARCGIS_WORKER_URL = os.environ.get("ARCGIS_WORKER_URL", "")


async def query(
    source: dict,
    query_type: str,
    params: dict
) -> dict:
    """
    Call the arcgis-adapter Cloudflare Worker.
    
    source: a row from the sources table
    query_type: "by_parcel" | "by_attribute" | "by_geometry"
    params: query-specific params (parcel_id, where, geometry, etc.)
    
    Returns normalized response dict.
    Never raises — returns error dict on failure.
    """
    config = source.get("config", {})
    
    payload = {
        "base_url": source["base_url"],
        "layer_id": config.get("layer_id", 0),
        "query_type": query_type,
        "params": params
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{ARCGIS_WORKER_URL}/query",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {
            "success": False,
            "features": [],
            "count": 0,
            "error": str(e),
            "source_url": source.get("base_url", "")
        }
```

---

## Ticket 7 — Case File Builder

**File:** `agent/case_file.py`

```python
import uuid
from datetime import datetime, timezone
from typing import Optional


def build(
    question: str,
    entity: Optional[str],
    evidence: list[dict],
    missing: list[str]
) -> dict:
    """
    Assemble a case file from collected evidence.
    Compute confidence based on evidence completeness.
    """
    cf_id = f"cf_{uuid.uuid4().hex[:12]}"
    confidence = _compute_confidence(evidence, missing)
    
    return {
        "id": cf_id,
        "question": question,
        "entity": entity,
        "evidence": evidence,
        "missing": missing,
        "confidence": confidence,
        "sources_queried": [e["source_id"] for e in evidence],
        "created_at": datetime.now(timezone.utc).isoformat()
    }


def _compute_confidence(evidence: list[dict], missing: list[str]) -> str:
    """
    high   — evidence found, no missing critical items
    medium — evidence found, some gaps
    low    — minimal evidence, significant gaps
    """
    if not evidence:
        return "low"
    
    evidence_count = len(evidence)
    missing_count = len(missing)
    
    if evidence_count >= 2 and missing_count == 0:
        return "high"
    elif evidence_count >= 1 and missing_count <= 2:
        return "medium"
    else:
        return "low"
```

---

## Ticket 8 — Analyst

**File:** `agent/analyst.py`

Takes the case file and produces a human-readable answer. The answer must cite sources.

```python
import json
from agent.model import call_model

ANALYST_SYSTEM = """You are a civic intelligence analyst. You receive a case file 
containing evidence gathered from live public sources about a parcel or civic entity.

Write a clear, factual answer to the question. Rules:
- Only state what the evidence supports. 
- If evidence is missing, say so explicitly.
- Cite your sources by name (e.g. "According to Skagit County Parcels...").
- Do not speculate beyond the evidence.
- Do not make recommendations. Describe what the data shows.
- Be concise. 3-6 sentences for simple questions. A short paragraph per major finding for complex ones.
- If confidence is low, say the answer is incomplete and explain what is missing."""


async def respond(question: str, case_file: dict) -> str:
    prompt = f"""Question: {question}

Case File:
{json.dumps(case_file, indent=2)}"""
    
    return await call_model(
        system=ANALYST_SYSTEM,
        user=prompt,
        max_tokens=600
    )
```

---

## Ticket 9 — Source Catalog

**File:** `agent/catalog/sources.py`

```python
import os
import sqlite3
import json
from typing import Optional

DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")


def get_source(source_id: str) -> Optional[dict]:
    """Fetch a single source by ID."""
    ...


def get_sources_for_domains(domains: list[str]) -> list[dict]:
    """
    Return all active sources that cover at least one of the given domains.
    domains: list of strings like ["parcels", "zoning", "flood"]
    """
    ...


def list_sources() -> list[dict]:
    """Return all active sources."""
    ...
```

Implementation notes:
- In Phase 1, use local sqlite for development and Cloudflare D1 binding for production.
- `domains` and `supports` are stored as JSON strings in D1. Deserialize on read.
- `config` is stored as JSON string. Deserialize on read.
- All functions return `dict` with deserialized fields, not raw sqlite rows.

---

## Ticket 10 — Frontend

**File:** `frontend/index.html`

Single HTML file. No framework. No build step. No external SDKs.

**Layout:** Two panels side by side on desktop, tabs on mobile.

```
┌─────────────────────────────────────────────────────┐
│  Civic Intelligence                         [Skagit] │
├───────────────────────┬─────────────────────────────┤
│                       │                             │
│   CONVERSATION        │   CASE FILE                 │
│                       │                             │
│   [question history]  │   Entity: P48165            │
│                       │   Confidence: medium        │
│                       │                             │
│                       │   Evidence                  │
│                       │   ┌─────────────────────┐  │
│                       │   │ Skagit Parcels       │  │
│                       │   │ Owner: John Smith    │  │
│                       │   │ Area: 1.2 acres      │  │
│                       │   └─────────────────────┘  │
│                       │                             │
│                       │   Missing                   │
│                       │   - Flood zone data         │
│                       │                             │
│   [text input] [Ask]  │   [Export] [Share]          │
└───────────────────────┴─────────────────────────────┘
```

**`frontend/app.js` — required functions:**

```javascript
const API_BASE = window.ENV_API_BASE || 'http://localhost:8000';

async function ask(question) {
  // POST to API_BASE/ask
  // Poll GET API_BASE/job/{job_id} until status === "complete"
  // No SDK. fetch() only.
  // Returns AskResponse
}

function renderConversation(history) {
  // Render question/answer history in left panel
  // Each item: question in user style, answer in agent style
}

function renderCaseFile(response) {
  // Render right panel from AskResponse:
  // - entity + confidence badge
  // - evidence cards (one per source)
  // - missing items in red/muted
  // - sources with names
}

function renderEvidenceCard(item) {
  // One card per EvidenceItem
  // Show source name, key fields from item.data
  // Collapsible for raw data
}

function showConfidence(level) {
  // "high" → green badge
  // "medium" → amber badge  
  // "low" → red badge
}
```

**Polling pattern (implement exactly this):**

```javascript
async function pollJob(jobId, maxAttempts = 20, intervalMs = 1000) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(`${API_BASE}/job/${jobId}`);
    const data = await response.json();
    if (data.status === 'complete' || data.status === 'error') {
      return data;
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  throw new Error('Job timed out');
}
```

**Loading state:** While polling, show a spinner in the right panel with the text "Gathering evidence..." — not in the left panel. The left panel shows the question immediately.

**No external fonts, no CDN calls, no framework.** System font stack only in Phase 1.

---

## Ticket 11 — Test Suite

**Directory:** `agent/tests/`

**File:** `agent/tests/test_adapters.py`

```python
import pytest
import respx
import httpx
from agent.adapters.arcgis import query

MOCK_ARCGIS_RESPONSE = {
    "success": True,
    "features": [
        {
            "attributes": {
                "PARCELID": "P48165",
                "OWNER": "TEST OWNER",
                "SITEADDRESS": "123 MAIN ST",
                "ACRES": 1.2
            }
        }
    ],
    "count": 1,
    "source_url": "https://gis.skagitcounty.net/..."
}

@respx.mock
@pytest.mark.asyncio
async def test_arcgis_query_by_parcel():
    respx.post("http://localhost:8787/query").mock(
        return_value=httpx.Response(200, json=MOCK_ARCGIS_RESPONSE)
    )
    source = {
        "id": "skagit_parcels",
        "base_url": "https://gis.skagitcounty.net/arcgis/rest/services/Parcels/MapServer",
        "config": {"layer_id": 0, "parcel_field": "PARCELID"}
    }
    result = await query(source, "by_parcel", {"parcel_id": "P48165"})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["features"][0]["attributes"]["PARCELID"] == "P48165"


@respx.mock
@pytest.mark.asyncio
async def test_arcgis_query_handles_timeout():
    respx.post("http://localhost:8787/query").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    source = {
        "id": "skagit_parcels",
        "base_url": "https://gis.skagitcounty.net/arcgis/rest/services/Parcels/MapServer",
        "config": {"layer_id": 0}
    }
    result = await query(source, "by_parcel", {"parcel_id": "P48165"})
    assert result["success"] is False
    assert "error" in result
    # Must not raise
```

**File:** `agent/tests/test_planner.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from agent.planner import create_plan

MOCK_PLAN_RESPONSE = """{
  "entity": "P48165",
  "entity_type": "parcel",
  "steps": [
    {"step": 1, "domain": "parcels", "query_type": "by_parcel", 
     "reason": "Get basic parcel facts"},
    {"step": 2, "domain": "zoning", "query_type": "by_parcel",
     "reason": "Get zoning designation"}
  ],
  "ambiguous": false,
  "clarification_needed": null
}"""

@pytest.mark.asyncio
async def test_planner_parcel_question():
    with patch("agent.planner.call_model", new=AsyncMock(return_value=MOCK_PLAN_RESPONSE)):
        plan = await create_plan(
            "Tell me about parcel P48165",
            {"county": "skagit"}
        )
    assert plan["entity"] == "P48165"
    assert plan["ambiguous"] is False
    assert len(plan["steps"]) >= 1
    assert plan["steps"][0]["domain"] in ["parcels", "assessor", "zoning", "flood"]


@pytest.mark.asyncio
async def test_planner_handles_malformed_json():
    with patch("agent.planner.call_model", new=AsyncMock(return_value="not json")):
        plan = await create_plan("Tell me about parcel P48165", {})
    # Must not raise. Must return fallback plan.
    assert "steps" in plan
    assert "entity_type" in plan
```

**File:** `agent/tests/test_case_file.py`

```python
from agent.case_file import build

def test_case_file_build_with_evidence():
    evidence = [
        {"source_id": "skagit_parcels", "source_name": "Skagit Parcels",
         "data": {"PARCELID": "P48165", "OWNER": "TEST"}, "retrieved_at": "2025-01-01T00:00:00Z"},
        {"source_id": "skagit_zoning", "source_name": "Skagit Zoning",
         "data": {"ZONE_CODE": "RR-5"}, "retrieved_at": "2025-01-01T00:00:00Z"}
    ]
    cf = build("Tell me about parcel P48165", "P48165", evidence, [])
    
    assert cf["id"].startswith("cf_")
    assert cf["confidence"] == "high"
    assert len(cf["evidence"]) == 2
    assert len(cf["missing"]) == 0
    assert cf["entity"] == "P48165"


def test_case_file_low_confidence_when_no_evidence():
    cf = build("Tell me about parcel P48165", "P48165", [], ["parcels", "zoning"])
    assert cf["confidence"] == "low"


def test_case_file_medium_confidence_with_gaps():
    evidence = [
        {"source_id": "skagit_parcels", "source_name": "Skagit Parcels",
         "data": {"PARCELID": "P48165"}, "retrieved_at": "2025-01-01T00:00:00Z"}
    ]
    cf = build("Tell me about parcel P48165", "P48165", evidence, ["zoning", "flood"])
    assert cf["confidence"] == "medium"
```

**File:** `agent/tests/test_api.py`

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from agent.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ask_returns_job_id():
    mock_response = {
        "job_id": "test-job-id",
        "status": "complete",
        "question": "Tell me about parcel P48165",
        "answer": "P48165 is a 1.2 acre parcel...",
        "confidence": "medium",
        "evidence": [],
        "missing": [],
        "sources_queried": [],
        "case_file_id": "cf_abc123",
        "error": None
    }
    with patch("agent.main.run_ask", new=AsyncMock(return_value=mock_response)):
        response = client.post("/ask", json={
            "question": "Tell me about parcel P48165",
            "context": {"county": "skagit"}
        })
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ["complete", "pending"]


def test_ask_requires_question():
    response = client.post("/ask", json={"context": {}})
    assert response.status_code == 422
```

**File:** `agent/tests/fixtures/p48165_expected.json`

This is the golden fixture. It defines what a correct response for P48165 must contain. You will fill in real values after running against live Skagit GIS for the first time.

```json
{
  "question": "Tell me about parcel P48165",
  "entity": "P48165",
  "required_sources": ["skagit_parcels"],
  "required_evidence_fields": ["PARCELID", "OWNER"],
  "confidence_min": "medium",
  "answer_must_contain": ["P48165"],
  "answer_must_not_contain": ["I don't know", "unable to", "no information"]
}
```

Add a test that loads this fixture and validates the live response against it. This test is the Phase 1 exit criteria made executable.

---

## Environment Variables

**File:** `.env.example`

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Cloudflare Workers
ARCGIS_WORKER_URL=http://localhost:8787

# D1 (local dev uses sqlite file)
D1_LOCAL_PATH=catalog/local.db

# Production D1 (set by Railway)
D1_ACCOUNT_ID=
D1_DATABASE_ID=
D1_API_TOKEN=
```

---

## `requirements.txt`

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
pydantic>=2.7.0
python-dotenv>=1.0.0
pytest>=8.2.0
pytest-asyncio>=0.23.0
respx>=0.21.0
pyyaml>=6.0.1
```

---

## `railway.json`

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn agent.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 10,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

---

## Running Order for Codex

Execute tickets in this order. Each ticket should pass its tests before moving to the next.

```
1. D1 schema + Skagit seed YAML
2. arcgis_adapter Worker (deploy to Cloudflare, verify /query returns data)
3. model.py abstraction
4. catalog/sources.py
5. adapters/arcgis.py (Python side calling the Worker)
6. case_file.py + tests
7. planner.py + tests
8. analyst.py
9. main.py wiring it all together + API tests
10. frontend two-panel UI
11. Golden fixture test for P48165
```

Do not proceed to Phase 2 until the golden fixture test passes against live Skagit GIS data.

---

## Definition of Done — Phase 1

- [ ] `pytest` passes with zero failures
- [ ] `POST /ask` with `"Tell me about parcel P48165"` returns real data from live Skagit GIS
- [ ] Response includes `PARCELID`, `OWNER`, and at least one additional field
- [ ] `confidence` is `"medium"` or `"high"` 
- [ ] `answer` cites at least one source by name
- [ ] `answer` does not contain "I don't know" or "unable to"
- [ ] Frontend renders the response in two panels
- [ ] Frontend polls correctly and shows "Gathering evidence..." during query
- [ ] arcgis_adapter Worker handles timeout gracefully (returns structured error, no crash)
- [ ] Golden fixture test passes
- [ ] `.env.example` is complete and README has setup instructions
