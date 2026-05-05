# Self-Hosting Guide

These 10 steps take a county from a fresh clone to a branded running instance. Commands assume you are in the repository root.

## 1. Install Prerequisites

Install Python 3.11 or newer, Node.js 18 or newer, git, SQLite command-line tools, a Railway account, and a Cloudflare account. On Windows, use PowerShell. Confirm the tools work:

```bash
python --version
node --version
git --version
sqlite3 --version
```

## 2. Clone and Configure

Clone the repository and enter it:

```bash
git clone <repo-url> OpenSkagit
cd OpenSkagit
```

Copy `.env.example` to `.env`, then fill in any adapter, Anthropic, Railway, Cloudflare, and notification settings your deployment uses. For a local smoke test, the seeded database and dev key are enough to verify auth, config, and the frontend.

Edit `config/tenant.yaml` for your county:

```yaml
tenant:
  display_name: "Example County Civic Intelligence"
  tagline: "Ask questions about public parcels and records."
  contact_email: "it@examplecounty.gov"
```

## 3. Seed the Database

Install Python dependencies and create the local database:

```bash
pip install -r requirements.txt
python catalog/seeds/seed.py --env local
```

Confirm the expected tables exist:

```bash
sqlite3 catalog/local.db ".tables"
sqlite3 catalog/local.db "SELECT id, name, role FROM api_keys;"
```

You should see `api_keys`, `audit_log`, `case_files`, `jobs`, `queries`, and `sources`. The local dev admin key is `dev-admin-key-change-in-production`. Replace it before production use.

## 4. Deploy Workers to Cloudflare

Deploy each adapter Worker from its directory. Use Cloudflare Wrangler from the worker project folders:

```bash
cd workers/arcgis-adapter
npm install
npx wrangler deploy
cd ../web-adapter
npm install
npx wrangler deploy
cd ../notify-adapter
npm install
npx wrangler deploy
cd ../..
```

Record each deployed Worker URL in `.env` or Railway environment variables so the agent can call them.

## 5. Deploy the Agent to Railway

Before deploying, run the agent locally so you know the clone works:

```bash
python -m uvicorn agent.main:app --host 127.0.0.1 --port 8000
```

Open a second terminal in the same repository and check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/config
```

When local health works, create a Railway project from this repository. Set the Railway start command to:

```bash
uvicorn agent.main:app --host 0.0.0.0 --port $PORT
```

Add the same environment variables from `.env` in Railway. Set `TENANT_CONFIG_PATH=config/tenant.yaml` unless you store tenant config elsewhere. After deploy, open:

```text
https://<your-railway-app>/health
```

It should return `{"status":"ok"}`.

## 6. Deploy the Frontend to Cloudflare Pages

Before deploying, preview the frontend locally while the agent is still running on port 8000:

```bash
cd frontend
python -m http.server 8020 --bind 127.0.0.1
```

Open `http://127.0.0.1:8020/index.html` in a browser. With empty browser localStorage, the API key modal should appear. Enter `dev-admin-key-change-in-production` for local testing. The header should show the `display_name` from `config/tenant.yaml`.

For production, create a Cloudflare Pages project that serves the `frontend/` directory. Set `window.ENV_API_BASE` to your Railway agent URL using your preferred Pages environment injection method. If you do not inject it, local preview defaults to `http://localhost:8000`.

For sensitive deployments, enable Cloudflare Access before sharing the frontend URL.

## 7. Create the First Admin API Key

The seed script creates a local development admin key. In production, create a named admin key and store it in your password manager:

```bash
curl -X POST "https://<your-agent>/admin/keys" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-admin-key-change-in-production" \
  -d "{\"name\":\"County IT Admin\",\"role\":\"admin\"}"
```

Save the returned `key`. It is only shown once. After confirming the new key works, disable or remove the dev key from the production database.

## 8. Verify Health and a Test Query

For local verification, use `http://127.0.0.1:8000`. For production, replace it with `https://<your-agent>`.

Check public config without an API key:

```bash
curl "http://127.0.0.1:8000/config"
```

Run a test query with your admin key:

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-admin-key>" \
  -d "{\"question\":\"Tell me about parcel P48165\",\"context\":{\"county\":\"skagit\",\"state\":\"wa\"}}"
```

Confirm an audit entry was created:

```bash
sqlite3 catalog/local.db "SELECT question, confidence, duration_ms FROM audit_log LIMIT 5;"
```

## 9. Point GIS Sources at Your County

Review `registry/SCHEMA.md` and copy the closest example from `registry/sources/` into `catalog/seeds/`. Edit the source IDs, names, `base_url`, domains, supported query modes, layer IDs, parcel field names, and spatial reference for your county.

Verify sources before launch:

```bash
python catalog/tools/verify_sources.py
python catalog/seeds/seed.py --env local
```

Work through `docs/political-access-checklist.md` before enabling a department-owned source.

## 10. Set Up Resend Notifications (Optional)

If email notifications are enabled, create a Resend account, verify the sender domain, and set notification environment variables in Railway and the notify Worker. Then keep this enabled in `config/tenant.yaml`:

```yaml
features:
  notifications: true
```

If the county is not ready for email notifications, set `notifications: false`. Notification failure never blocks a query response.

## County Walkthrough

Before handoff, test this guide in a fresh directory:

1. Clone the repo.
2. Follow steps 1 through 8.
3. Open the frontend with empty browser localStorage.
4. Enter the admin API key when prompted.
5. Run the test query.
6. Change `display_name` in `config/tenant.yaml` to a fictional county.
7. Restart the agent.
8. Open `/config` and confirm the new name appears.
9. Reload the frontend and confirm the new name appears in the header.

If any step fails or requires undocumented knowledge, fix this guide before deployment.
