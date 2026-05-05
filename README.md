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

## Nightly Source Verification

The source verifier checks every active catalog source with a small real probe and records the run in the local SQLite catalog database. It is intended for nightly production monitoring, not mocked CI tests.

Run it locally:

```bash
python -m agent.source_verifier
```

Useful options:

```bash
python -m agent.source_verifier --json
python -m agent.source_verifier --source-ids skagit_parcels,skagit_zoning
python -m agent.source_verifier --alert-webhook https://example.com/webhook
```

Environment variables:

```bash
SOURCE_VERIFIER_CONCURRENCY=8
SOURCE_VERIFIER_TEST_PARCEL=P48165
SOURCE_VERIFIER_SOURCE_IDS=
SOURCE_VERIFIER_ALERT_WEBHOOK=
SOURCE_VERIFIER_ALERT_ON_WARNING=false
```

The verifier exits with code `1` when any source fails, so Railway will mark that cron execution as failed. Warnings, such as missing optional API keys or manually configured web forms, do not fail the run.

### Railway Cron Setup

Create a second Railway service from this same repository for the verifier. Keep the existing web/API service start command unchanged.

For the verifier service:

```bash
python -m agent.source_verifier
```

Set the Railway service type to Cron/Scheduled Job and use a nightly UTC schedule, for example:

```txt
0 10 * * *
```

Add the same required app variables as the API service, plus the verifier variables above. At minimum:

```bash
D1_LOCAL_PATH=/data/catalog.db
SOURCE_VERIFIER_CONCURRENCY=8
SOURCE_VERIFIER_TEST_PARCEL=P48165
```

Attach a Railway volume to the verifier service at `/data` if you want verification history to persist between runs. If the API service also needs to read the same verification tables, point both services at the same persistent database instead of each service's local filesystem.

Optional alerting:

```bash
SOURCE_VERIFIER_ALERT_WEBHOOK=https://your-alert-webhook
SOURCE_VERIFIER_ALERT_ON_WARNING=false
```

If you want authenticated sources verified, also set their API keys, for example `SAM_API_KEY`. Without those keys, authenticated sources are recorded as warnings rather than failures.

## Cloudflare D1 Persistence

Local development uses SQLite at `D1_LOCAL_PATH`. Production can use Cloudflare D1 through the D1 HTTP API by setting:

```bash
D1_ACCOUNT_ID=...
D1_DATABASE_ID=...
D1_API_TOKEN=...
```

Create and initialize the database with Wrangler:

```bash
npx wrangler d1 create openskagit
npx wrangler d1 execute openskagit --remote --file catalog/schema.sql
```

The app persists source metadata, jobs, case files, audit logs, source verification runs, planner output, and capped per-source query diagnostics. It does not mirror full civic source datasets into D1.

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
