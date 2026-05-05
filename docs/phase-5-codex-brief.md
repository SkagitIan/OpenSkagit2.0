# Phase 5 Codex Brief
## Civic Intelligence Platform — County Acquisition Readiness

**Builds on:** Phase 4 verified and passing. 26 tests passing, 3 skipped.

**Goal:** Make the platform handoffable. A county IT manager can follow the deployment docs, stand up a white-labeled instance pointing at their GIS, and operate it without touching core agent code. Every query is auditable. Every source is inspectable. Auth protects the API. PDF exports look professional.

**Exit criteria:** The platform runs with API key auth, logs every query to an audit trail, exports case files as real PDFs, reads its identity from a tenant config file, and ships with docs a county IT department can follow without calling you.

---

## What changes in Phase 5

```
New agent modules
  agent/auth.py                  ← API key middleware
  agent/audit.py                 ← audit log writer
  agent/pdf.py                   ← PDF export (fpdf2)
  agent/config.py                ← tenant config loader

Modified files
  agent/main.py                  ← auth on protected endpoints,
                                    audit logging on /ask,
                                    /export returns PDF option,
                                    /admin/* endpoints
  catalog/schema.sql             ← api_keys table, audit_log table
  frontend/index.html + app.js  ← admin panel, auth header, tenant branding

New config
  config/tenant.yaml             ← white-label identity + feature flags

New registry
  registry/
    README.md
    CONTRIBUTING.md
    SCHEMA.md
    sources/skagit/skagit.yaml
    sources/wa_state/wa_state.yaml
    sources/federal/federal_gis.yaml

New docs
  docs/self-hosting.md
  docs/county-deployment.md
  docs/political-access-checklist.md

New tests
  agent/tests/test_auth.py
  agent/tests/test_audit.py
  agent/tests/test_pdf.py
  agent/tests/test_config.py
```

---

## Ticket 1 — Schema Updates

**File:** `catalog/schema.sql` (add two tables)

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'reader',
  -- roles: 'reader' (POST /ask only)
  --        'writer' (ask + export + share)
  --        'admin'  (all endpoints including /admin/*)
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now')),
  last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  api_key_id TEXT,
  question TEXT NOT NULL,
  entity TEXT,
  sources_queried TEXT,        -- JSON array
  confidence TEXT,
  duration_ms INTEGER,
  ip_address TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity  ON audit_log(entity);
```

Run `python catalog/seeds/seed.py --env local` after adding these tables. The seed script must apply schema changes idempotently (it already uses `CREATE TABLE IF NOT EXISTS`).

**Seed a default admin key for local development:**

Add to `catalog/seeds/seed.py` — only if no admin key exists yet:

```python
import hashlib, secrets

def seed_default_api_key(conn):
    existing = conn.execute(
        "SELECT count(*) FROM api_keys WHERE role='admin'"
    ).fetchone()[0]
    if existing == 0:
        raw_key = "dev-admin-key-change-in-production"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn.execute(
            "INSERT INTO api_keys (id, key_hash, name, role) VALUES (?,?,?,?)",
            ("key_dev_admin", key_hash, "Dev Admin", "admin")
        )
        print(f"Seeded default admin key: {raw_key}")
        print("CHANGE THIS IN PRODUCTION")
```

---

## Ticket 2 — Tenant Config

**File:** `config/tenant.yaml`

```yaml
tenant:
  id: "skagit"
  name: "Skagit County"
  display_name: "Skagit County Civic Intelligence"
  tagline: "Ask questions about public parcels, permits, and records."
  primary_county: "skagit"
  state: "wa"
  contact_email: ""
  logo_url: ""              # URL to county logo, optional

  # Source overrides — a new county points their GIS here
  # without changing any source catalog code
  gis_overrides:
    base_domain: "gis.skagitcounty.net"
    # future: map source IDs to new base URLs for white-label

  features:
    notifications: true
    export: true
    history: true
    admin_panel: true
    public_registry: false   # set true when county opens to public

  branding:
    primary_color: "#1a5276"  # used in PDF header and frontend
    font: "system-ui"
```

**File:** `agent/config.py`

```python
import yaml
import os
from functools import lru_cache

CONFIG_PATH = os.environ.get("TENANT_CONFIG_PATH", "config/tenant.yaml")


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def tenant() -> dict:
    return load_config().get("tenant", {})


def feature_enabled(feature: str) -> bool:
    return load_config().get("tenant", {}).get("features", {}).get(feature, False)


def reload_config() -> None:
    load_config.cache_clear()
```

---

## Ticket 3 — API Key Auth

**File:** `agent/auth.py`

```python
import hashlib
import sqlite3
import os
from datetime import datetime, timezone
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_key(raw_key: str, required_role: str = "reader") -> dict:
    """
    Verify an API key and return the key record.
    Raises HTTPException 401 or 403 on failure.
    Role hierarchy: reader < writer < admin
    """
    if not raw_key:
        raise HTTPException(status_code=401, detail="API key required")

    key_hash = _hash_key(raw_key)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash=? AND active=1",
        (key_hash,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid API key")

    role_hierarchy = ["reader", "writer", "admin"]
    key_role = row["role"]
    if role_hierarchy.index(key_role) < role_hierarchy.index(required_role):
        conn.close()
        raise HTTPException(
            status_code=403,
            detail=f"Role '{key_role}' cannot access this endpoint"
        )

    # Update last_used_at
    conn.execute(
        "UPDATE api_keys SET last_used_at=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), row["id"])
    )
    conn.commit()
    conn.close()
    return dict(row)


def require_reader(api_key: str = Security(api_key_header)) -> dict:
    return verify_key(api_key, "reader")


def require_writer(api_key: str = Security(api_key_header)) -> dict:
    return verify_key(api_key, "writer")


def require_admin(api_key: str = Security(api_key_header)) -> dict:
    return verify_key(api_key, "admin")
```

**Endpoints protected by role:**

```
POST /ask             → require_reader
GET  /case/{id}       → require_reader
GET  /cases           → require_reader
GET  /export/{id}     → require_writer
GET  /job/{id}        → require_reader
GET  /admin/*         → require_admin
GET  /health          → no auth (monitoring tools need this)
```

---

## Ticket 4 — Audit Log

**File:** `agent/audit.py`

```python
import uuid
import sqlite3
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")


def log_query(
    job_id: str,
    api_key_id: str,
    question: str,
    entity: Optional[str],
    sources_queried: list[str],
    confidence: str,
    duration_ms: int,
    ip_address: Optional[str] = None
) -> None:
    """
    Write one audit log entry. Fire-and-forget — never raises.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO audit_log
               (id, job_id, api_key_id, question, entity,
                sources_queried, confidence, duration_ms, ip_address)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f"al_{uuid.uuid4().hex[:12]}",
                job_id,
                api_key_id,
                question,
                entity,
                json.dumps(sources_queried),
                confidence,
                duration_ms,
                ip_address
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Audit failure must never affect the response


def get_stats(days: int = 30) -> dict:
    """Return aggregate stats for the admin dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute(
        "SELECT count(*) as n FROM audit_log WHERE created_at > datetime('now', ?)",
        (f"-{days} days",)
    ).fetchone()["n"]

    by_confidence = conn.execute(
        """SELECT confidence, count(*) as n FROM audit_log
           WHERE created_at > datetime('now', ?)
           GROUP BY confidence""",
        (f"-{days} days",)
    ).fetchall()

    top_entities = conn.execute(
        """SELECT entity, count(*) as n FROM audit_log
           WHERE entity IS NOT NULL
           AND created_at > datetime('now', ?)
           GROUP BY entity ORDER BY n DESC LIMIT 10""",
        (f"-{days} days",)
    ).fetchall()

    avg_duration = conn.execute(
        """SELECT avg(duration_ms) as avg_ms FROM audit_log
           WHERE created_at > datetime('now', ?)""",
        (f"-{days} days",)
    ).fetchone()["avg_ms"]

    conn.close()
    return {
        "period_days": days,
        "total_queries": total,
        "by_confidence": {r["confidence"]: r["n"] for r in by_confidence},
        "top_entities": [{"entity": r["entity"], "count": r["n"]} for r in top_entities],
        "avg_duration_ms": round(avg_duration or 0, 1)
    }
```

**Where audit logging fires in main.py:**

```python
# In ask_task(), after saving case file, before firing notification:
import time

start_ms = time.monotonic()
# ... all the ask work ...
duration_ms = int((time.monotonic() - start_ms) * 1000)

audit.log_query(
    job_id=job_id,
    api_key_id=current_key["id"],   # from auth dependency
    question=request.question,
    entity=case_file.get("entity"),
    sources_queried=case_file.get("sources_queried", []),
    confidence=case_file.get("confidence", "unknown"),
    duration_ms=duration_ms,
    ip_address=client_ip   # from Request object
)
```

---

## Ticket 5 — PDF Export

**File:** `agent/pdf.py`

Use `fpdf2` — pure Python, no system dependencies, installs cleanly on Railway.

Add to `requirements.txt`:
```
fpdf2>=2.7.9
```

```python
from fpdf import FPDF
from datetime import datetime
from agent.config import tenant


class CaseFilePDF(FPDF):

    def header(self):
        t = tenant()
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(26, 82, 118)   # default primary, overridden by tenant
        self.cell(0, 10, t.get("display_name", "Civic Intelligence"), ln=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "Civic Intelligence Case File", ln=True)
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()} — Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", align="C")


def build_pdf(case_file: dict) -> bytes:
    """
    Generate a PDF case file and return bytes.
    Uses tenant config for branding.
    """
    pdf = CaseFilePDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Meta block
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, f"Entity: {case_file.get('entity', 'Unknown')}", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Question: {case_file.get('question', '')}")
    pdf.set_font("Helvetica", "B", 10)

    confidence = case_file.get("confidence", "unknown").upper()
    color_map = {"HIGH": (39, 174, 96), "MEDIUM": (243, 156, 18), "LOW": (231, 76, 60)}
    r, g, b = color_map.get(confidence, (100, 100, 100))
    pdf.set_text_color(r, g, b)
    pdf.cell(0, 7, f"Confidence: {confidence}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Answer
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Answer", ln=True)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, case_file.get("answer", "No answer generated."))
    pdf.ln(4)

    # Evidence
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Evidence", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    for item in case_file.get("evidence", []):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, item.get("source_name", item.get("source_id", "Unknown")), ln=True)
        pdf.set_font("Helvetica", "", 9)
        data = item.get("data", [])
        records = data if isinstance(data, list) else [data]
        for record in records[:3]:
            if isinstance(record, dict):
                for k, v in list(record.items())[:8]:
                    pdf.cell(0, 5, f"  {k}: {v}", ln=True)
        pdf.ln(2)

    # Missing evidence
    missing = case_file.get("missing", [])
    if missing:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Missing Evidence", ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(180, 50, 50)
        for item in missing:
            pdf.cell(0, 6, f"  \u2022 {item}", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    # Sources
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Sources Queried", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    for source_id in case_file.get("sources_queried", []):
        pdf.cell(0, 5, f"  {source_id}", ln=True)

    # Footer meta
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"Case file ID: {case_file.get('id', '')}", ln=True)
    pdf.cell(0, 5, f"Generated: {case_file.get('created_at', '')}", ln=True)

    return bytes(pdf.output())
```

**Update `/export/{id}` endpoint in main.py:**

```python
@app.get("/export/{case_file_id}")
async def export_case_file(
    case_file_id: str,
    format: str = "markdown",
    key: dict = Depends(require_writer)
):
    case_file = get_case_file_from_db(case_file_id)
    if not case_file:
        raise HTTPException(status_code=404, detail="Case file not found")

    if format == "pdf":
        pdf_bytes = pdf.build_pdf(case_file)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=case-{case_file_id}.pdf"
            }
        )
    elif format == "json":
        return JSONResponse(content=case_file)
    else:  # markdown
        md = export.to_markdown(case_file)
        return PlainTextResponse(content=md, headers={
            "Content-Disposition": f"attachment; filename=case-{case_file_id}.md"
        })
```

---

## Ticket 6 — Admin Endpoints

Add to `agent/main.py`. All require `require_admin`.

```python
@app.get("/admin/stats")
async def admin_stats(
    days: int = 30,
    key: dict = Depends(require_admin)
):
    """Query volume, confidence distribution, top entities, avg duration."""
    return audit.get_stats(days=days)


@app.get("/admin/sources")
async def admin_sources(key: dict = Depends(require_admin)):
    """
    Return all active sources with last-queried timestamp and query count.
    Joins audit_log with sources table.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sources = conn.execute(
        "SELECT id, name, type, active FROM sources WHERE active=1"
    ).fetchall()

    result = []
    for source in sources:
        # Count how many times this source appeared in queries
        stats = conn.execute(
            """SELECT count(*) as n, max(al.created_at) as last_used
               FROM audit_log al
               WHERE al.sources_queried LIKE ?""",
            (f'%"{source["id"]}"%',)
        ).fetchone()
        result.append({
            "id": source["id"],
            "name": source["name"],
            "type": source["type"],
            "active": bool(source["active"]),
            "query_count": stats["n"],
            "last_used": stats["last_used"]
        })
    conn.close()
    return {"sources": result}


@app.get("/admin/audit")
async def admin_audit(
    limit: int = 50,
    offset: int = 0,
    entity: Optional[str] = None,
    confidence: Optional[str] = None,
    key: dict = Depends(require_admin)
):
    """Paginated audit log with optional filters."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    where = ["1=1"]
    params: list = []
    if entity:
        where.append("entity = ?")
        params.append(entity)
    if confidence:
        where.append("confidence = ?")
        params.append(confidence)

    rows = conn.execute(
        f"""SELECT id, job_id, question, entity, confidence,
                   sources_queried, duration_ms, created_at
            FROM audit_log WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()

    total = conn.execute(
        f"SELECT count(*) as n FROM audit_log WHERE {' AND '.join(where)}",
        params
    ).fetchone()["n"]

    conn.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [dict(r) for r in rows]
    }


@app.post("/admin/keys")
async def create_api_key(
    body: CreateKeyRequest,
    key: dict = Depends(require_admin)
):
    """
    Create a new API key. Returns the raw key once — not stored.
    Caller must save it. After this endpoint returns, the raw key
    is unrecoverable.
    """
    import secrets, hashlib, uuid
    raw_key = f"civ_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO api_keys (id, key_hash, name, role) VALUES (?,?,?,?)",
        (f"key_{uuid.uuid4().hex[:12]}", key_hash, body.name, body.role)
    )
    conn.commit()
    conn.close()
    return {
        "key": raw_key,
        "name": body.name,
        "role": body.role,
        "warning": "Save this key now. It cannot be retrieved again."
    }
```

---

## Ticket 7 — Frontend: Auth Header + Admin Panel

**File:** `frontend/app.js` (modify existing)

**Auth header on all API calls:**

```javascript
const API_KEY = localStorage.getItem('civic_api_key') || '';

async function apiFetch(path, options = {}) {
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...(options.headers || {})
    }
  });
}
```

Replace all existing `fetch(API_BASE + ...)` calls with `apiFetch(...)`.

**API key entry on first load:**

If `localStorage.getItem('civic_api_key')` is empty, show a modal asking for the API key before the first query. Store it in localStorage. Add a "Change API key" link in the header.

```javascript
function checkAuth() {
  const key = localStorage.getItem('civic_api_key');
  if (!key) {
    showApiKeyModal();
  }
}

function showApiKeyModal() {
  // Simple modal: one input, one button
  // On submit: store key in localStorage, close modal
}
```

**Admin panel (visible only to admin keys):**

After a successful auth check, call `GET /admin/stats`. If it returns 200, show an "Admin" link in the header. If 403, hide it.

The admin panel is a simple page with three sections:

```
QUERY STATS (last 30 days)
  Total queries: N
  High confidence: N  Medium: N  Low: N
  Avg response time: N ms
  Top entities: [list]

SOURCE HEALTH
  [table: source name | type | query count | last used]

RECENT AUDIT LOG
  [table: time | entity | question | confidence | duration]
  [load more button]
```

No separate admin HTML file. Render it in a panel that replaces the main workspace, toggled by the Admin link.

**Tenant branding from config:**

On page load, call a new `GET /config` endpoint (see below) and use the response to:
- Set `document.title` to `tenant.display_name`
- Set the header text to `tenant.display_name`
- Set the tagline below the header to `tenant.tagline`

---

## Ticket 8 — Config Endpoint

Add to `agent/main.py` — no auth required, safe for public:

```python
@app.get("/config")
async def get_config():
    """Return safe public-facing tenant config. No secrets."""
    t = config.tenant()
    return {
        "display_name": t.get("display_name", "Civic Intelligence"),
        "tagline": t.get("tagline", ""),
        "primary_color": t.get("branding", {}).get("primary_color", "#1a5276"),
        "features": t.get("features", {})
    }
```

---

## Ticket 9 — Source Registry

Create a public registry structure that a county (or any contributor) can fork to add their own sources.

**Directory:** `registry/`

**`registry/README.md`:**

```markdown
# Civic Intelligence Source Registry

A community-maintained collection of source adapter configurations
for the Civic Intelligence Platform.

## How to use

Copy any source YAML from this registry into your local
`catalog/seeds/` directory and reseed:

    python catalog/seeds/seed.py --env local

## How to contribute

See CONTRIBUTING.md.

## Structure

sources/
  {county-or-agency}/
    {name}.yaml      — one YAML per source group
```

**`registry/CONTRIBUTING.md`:**

Document the source YAML schema. Copy it from `catalog/seeds/skagit.yaml` as a reference. Include:
- Required fields: `id`, `name`, `type`, `base_url`, `domains`, `supports`, `config`
- How to verify a source before submitting (reference `catalog/tools/verify_sources.py`)
- Pull request checklist: source reachable, spatial reference confirmed, at least one domain listed

**`registry/SCHEMA.md`:**

Document every field in the source schema with types, allowed values, and examples. This is the contract for community contributors.

**Copy existing seeds into registry:**

```
registry/sources/skagit/skagit.yaml          ← copy from catalog/seeds/skagit.yaml
registry/sources/skagit/skagit_web.yaml      ← copy from catalog/seeds/skagit_web.yaml
registry/sources/wa_state/wa_state.yaml      ← copy from catalog/seeds/wa_state.yaml
registry/sources/federal/federal_gis.yaml    ← copy from catalog/seeds/federal_gis.yaml
registry/sources/federal/federal_financial.yaml ← copy from catalog/seeds/federal.yaml
```

These are copies, not symlinks. The registry is a standalone artifact.

---

## Ticket 10 — Documentation

**File:** `docs/self-hosting.md`

Write step-by-step self-hosting instructions for a county IT manager. Cover:

1. Prerequisites (Python 3.11+, Node 18+, git, a Railway account, a Cloudflare account)
2. Clone and configure (`.env`, `config/tenant.yaml`)
3. Seed the database
4. Deploy Workers to Cloudflare (arcgis-adapter, web-adapter, notify-adapter)
5. Deploy agent to Railway
6. Deploy frontend to Cloudflare Pages
7. Create the first admin API key
8. Verify the deployment with `GET /health` and a test query
9. Point GIS sources at your county (edit `catalog/seeds/` YAMLs and reseed)
10. Set up Resend for email notifications (optional)

**File:** `docs/county-deployment.md`

A shorter, non-technical version of self-hosting.md written for a county IT manager who may not be a developer. Focus on:
- What they receive (the repo, deployment docs, a running instance)
- What infrastructure they control (their own Railway, their own Cloudflare)
- What data is and is not stored (source metadata only — no civic data copied)
- How to add their own departments as sources (point to registry/CONTRIBUTING.md)
- How to white-label (edit `config/tenant.yaml`)
- Who to call when something breaks (your contact info placeholder)

**File:** `docs/political-access-checklist.md`

This is the document Musk forced into scope. Before deploying for a county, work through this checklist:

```markdown
# Political Access Risk Checklist

Before deploying the Civic Intelligence Platform for a county,
assess each item below. Items marked HIGH risk require a conversation
with the relevant department head before go-live.

## GIS Portal Access
- [ ] Who controls access to the county ArcGIS portal?
- [ ] Is the GIS data portal publicly accessible or behind auth?
- [ ] Has the GIS department been informed about automated queries?
- [ ] Is there a rate limit on the GIS portal that could be triggered?
      HIGH RISK if: GIS department has not been informed

## Treasurer / Auditor Web Sources  
- [ ] Do the web adapter queries comply with the site's terms of use?
- [ ] Has the IT department been informed about automated form queries?
      HIGH RISK if: Web scraping is prohibited by site terms

## Data Sensitivity
- [ ] Does any query surface personally identifiable information (PII)?
- [ ] Is owner name data appropriate for the intended user base?
- [ ] Are there parcels with privacy flags (e.g., law enforcement addresses)?
      HIGH RISK if: PII is surfaced without appropriate access controls

## Auth and Access
- [ ] Who will receive admin API keys?
- [ ] Is the frontend publicly accessible or internal-only?
- [ ] Is Cloudflare Access needed to restrict frontend access?
      HIGH RISK if: Frontend is public and data is sensitive

## Federal Data
- [ ] Is USASpending data appropriate for the intended query types?
- [ ] Are SAM.gov contractor queries within intended use?

## Organizational
- [ ] Which department owns this deployment?
- [ ] Who approves changes to the source catalog?
- [ ] Is there a process for removing a source if it is discontinued?
- [ ] Is there a contact for residents who have questions about the data?
```

---

## Ticket 11 — Test Suite

**File:** `agent/tests/test_auth.py`

```python
import pytest
from fastapi.testclient import TestClient
from agent.main import app

client = TestClient(app)


def test_ask_requires_api_key():
    response = client.post("/ask", json={"question": "test"})
    assert response.status_code == 401


def test_ask_accepts_valid_reader_key():
    # Uses the dev-admin-key seeded in catalog/seeds/seed.py
    response = client.post(
        "/ask",
        json={"question": "Tell me about parcel P48165"},
        headers={"X-API-Key": "dev-admin-key-change-in-production"}
    )
    # 200 or may be a live data error — not 401 or 403
    assert response.status_code != 401
    assert response.status_code != 403


def test_admin_endpoint_requires_admin_key():
    response = client.get(
        "/admin/stats",
        headers={"X-API-Key": "dev-admin-key-change-in-production"}
    )
    assert response.status_code == 200


def test_health_requires_no_auth():
    response = client.get("/health")
    assert response.status_code == 200


def test_config_requires_no_auth():
    response = client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert "display_name" in data
```

**File:** `agent/tests/test_audit.py`

```python
import pytest
from agent.audit import log_query, get_stats


def test_log_query_does_not_raise():
    # Should succeed silently
    log_query(
        job_id="job_test123",
        api_key_id="key_test",
        question="Tell me about P48165",
        entity="P48165",
        sources_queried=["skagit_parcels"],
        confidence="medium",
        duration_ms=1234
    )


def test_log_query_handles_db_error_silently(monkeypatch):
    # Even if DB is broken, no exception should escape
    import agent.audit as audit_module
    original = audit_module.DB_PATH
    audit_module.DB_PATH = "/nonexistent/path/db.sqlite"
    try:
        log_query("j", "k", "q", None, [], "low", 0)
        # Must not raise
    finally:
        audit_module.DB_PATH = original


def test_get_stats_returns_expected_shape():
    stats = get_stats(days=30)
    assert "total_queries" in stats
    assert "by_confidence" in stats
    assert "top_entities" in stats
    assert isinstance(stats["top_entities"], list)
```

**File:** `agent/tests/test_pdf.py`

```python
from agent.pdf import build_pdf

SAMPLE_CASE_FILE = {
    "id": "cf_test123",
    "entity": "P48165",
    "question": "Tell me about parcel P48165",
    "confidence": "medium",
    "answer": "Parcel P48165 is a 6.5 acre parcel owned by SWANSON EARLINE.",
    "evidence": [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit County Parcels",
            "data": [{"PARCELID": "P48165", "OWNER": "SWANSON EARLINE", "Acres": 6.5}],
            "count": 1
        }
    ],
    "missing": ["flood"],
    "sources_queried": ["skagit_parcels"],
    "created_at": "2025-01-01T00:00:00Z"
}


def test_build_pdf_returns_bytes():
    result = build_pdf(SAMPLE_CASE_FILE)
    assert isinstance(result, bytes)
    assert len(result) > 1000  # non-trivial PDF


def test_build_pdf_starts_with_pdf_header():
    result = build_pdf(SAMPLE_CASE_FILE)
    assert result[:4] == b"%PDF"


def test_build_pdf_handles_empty_evidence():
    cf = {**SAMPLE_CASE_FILE, "evidence": [], "missing": []}
    result = build_pdf(cf)
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"


def test_build_pdf_handles_long_answer():
    cf = {**SAMPLE_CASE_FILE, "answer": "A" * 2000}
    result = build_pdf(cf)
    assert isinstance(result, bytes)
```

**File:** `agent/tests/test_config.py`

```python
from agent.config import tenant, feature_enabled


def test_tenant_returns_dict():
    t = tenant()
    assert isinstance(t, dict)
    assert "display_name" in t


def test_feature_enabled_returns_bool():
    result = feature_enabled("notifications")
    assert isinstance(result, bool)


def test_feature_missing_returns_false():
    result = feature_enabled("nonexistent_feature_xyz")
    assert result is False
```

---

## Running Order for Codex

```
1.  catalog/schema.sql — add api_keys and audit_log tables
2.  catalog/seeds/seed.py — add seed_default_api_key()
3.  python catalog/seeds/seed.py --env local — apply schema + seed dev key
4.  config/tenant.yaml
5.  agent/config.py
6.  agent/auth.py + agent/tests/test_auth.py
7.  agent/audit.py + agent/tests/test_audit.py
8.  requirements.txt — add fpdf2>=2.7.9
9.  agent/pdf.py + agent/tests/test_pdf.py
10. agent/tests/test_config.py
11. agent/main.py — add auth dependencies, audit logging, /export PDF,
                    /admin/* endpoints, /config endpoint
12. frontend — auth header, API key modal, admin panel, tenant branding
13. registry/ — structure, README, CONTRIBUTING, SCHEMA, source copies
14. docs/ — self-hosting.md, county-deployment.md, political-access-checklist.md
15. python -m pytest agent/tests/ -v — all tests passing
```

---

## Definition of Done — Phase 5

- [ ] `python -m pytest agent/tests/ -v` — all prior 26 tests pass, 13+ new tests pass
- [ ] `POST /ask` without `X-API-Key` returns 401
- [ ] `POST /ask` with dev key returns 200 and logs to `audit_log` table
- [ ] `GET /admin/stats` returns query counts and confidence breakdown
- [ ] `GET /admin/sources` returns all active sources with query counts
- [ ] `GET /export/{id}?format=pdf` returns a valid PDF (starts with `%PDF`)
- [ ] `GET /config` returns tenant display name without auth
- [ ] `config/tenant.yaml` change is reflected in `GET /config` response after restart
- [ ] Frontend shows API key modal on first load
- [ ] Frontend sets page title from tenant config
- [ ] Admin panel visible and functional for admin key
- [ ] `registry/` directory exists with all five source YAMLs copied
- [ ] `docs/self-hosting.md` contains all 10 steps
- [ ] `docs/political-access-checklist.md` exists with all checklist items
- [ ] `fpdf2` installs cleanly on a fresh `pip install -r requirements.txt`
- [ ] No prior test regressions
