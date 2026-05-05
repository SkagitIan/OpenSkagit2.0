# Civic Intelligence Platform Phase 1

Phase 1 proves the loop: a question about one Skagit parcel becomes a structured, cited answer with evidence from live GIS data.

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python catalog/seeds/seed.py --env local
```

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` if you want model-authored planning and answers. Without it, the API uses deterministic fallback planning and answer text for parcel questions.

## Run

Start the ArcGIS adapter:

```bash
cd workers/arcgis-adapter
npm install
npm run dev
```

Start the notify adapter for email and webhook delivery:

```bash
cd workers/notify-adapter
npm install
npm run dev
```

Start the agent:

```bash
uvicorn agent.main:app --reload --host 0.0.0.0 --port 8000
```

Open `frontend/index.html` in a browser. The frontend uses `fetch()` only and calls `http://localhost:8000` by default.

## Notifications

Phase 4 supports post-answer notifications through `workers/notify-adapter`. Webhooks can be tested with a free inspector URL from [webhook.site](https://webhook.site/).

Email delivery uses [Resend](https://resend.com/). Create a free API key in the Resend dashboard; the free tier covers 3,000 emails per month. For local Worker development, set the secret from `workers/notify-adapter`:

```bash
wrangler secret put RESEND_API_KEY
```

For Railway, add these environment variables in the service settings:

```bash
NOTIFY_WORKER_URL=http://localhost:8789
RESEND_API_KEY=re_...
```

The Worker currently sends from `Civic Intelligence <notifications@yourdomain.com>`. Production sends require changing that address to a Resend-verified domain.

## Test

```bash
pytest agent/tests/ -v
```

The live P48165 test is skipped unless `RUN_LIVE_GOLDEN=1` is set and the local Worker is running.

## Sources requiring manual configuration

The Skagit Auditor recorded-document search is an ASP.NET WebForms page. The search page and field names were discoverable, but a stable parcel-specific POST endpoint was not confirmed during Phase 2 source discovery, so `skagit_auditor` is seeded with `status: "needs_manual_config"` and an empty `config.endpoint`.

The Skagit Treasurer property search page posts to `/Search/Property/` and uses JavaScript plus hidden ASP.NET fields. The catalog records the confirmed form action and field names, but live use may require preserving viewstate fields from a fresh page load.

## Sources Pending Verification

The following sources are in the catalog but could not be verified during Phase 3 implementation. They will return structured errors gracefully until confirmed and updated.

| Source ID | Issue | Last checked |
|-----------|-------|--------------|
| federal_usgs_geology | `https://mrdata.usgs.gov/services/geo-us-2014/MapServer?f=json` returned non-JSON; FeatureServer variation also returned non-JSON. | 2026-05-05 |
| federal_fema_nfhl | Existing Phase 2 FEMA NFHL endpoint returned 404 during Phase 3 verification; source was not modified. | 2026-05-05 |
| skagit_flood | Existing Phase 2 FEMA NFHL alias returned 404 during Phase 3 verification; source was not modified. | 2026-05-05 |
