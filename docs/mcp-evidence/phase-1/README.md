# Phase 1 Evidence Status

Date: 2026-08-01
Owner: Ian
Branch: railway-django-scratch

## Implemented

- Safe environment classification and fail-closed local/test PostGIS targeting.
- Separate Compose development/test PostGIS definitions and synthetic source bootstrap.
- Real local ASGI/Uvicorn commands.
- Development/test/release-candidate notification suppression and local storage.
- Separate liveness and readiness semantics.
- Pinned runtime and verification dependency locks plus update workflow.
- GitHub Actions workflow with disposable PostGIS, lint, secret scan, vulnerability audit, migrations, tests, authenticated protocol smoke, and build checks.
- On-demand Railway release-candidate manifest and runbook.
- Ephemeral OAuth authorization-code/PKCE smoke for local ASGI and candidate HTTPS.
- Release-candidate-only forced readiness failure hook for the traffic-rejection drill.

## Local evidence collected

- Ruff Phase 1 scope: passed.
- Secret scan Phase 1 scope: passed; candidate values are never printed.
- Python compileall: passed.
- MCP/settings/health/bootstrap/protocol unit suite: 35 tests passed.
- Actual Uvicorn/ASGI smoke: liveness 200, readiness 503 with database/migrations false and MCP registry true, unauthenticated MCP 401.
- Local disposable PostGIS migrations and full Django suite: blocked because Docker is not installed and the two running local PostgreSQL services require credentials not available to this session.
- Dependency vulnerability audit: tool installed and lock accepted; the external audit service timed out twice in this sandbox. CI remains configured to run the audit.

## External evidence still required

- Successful GitHub Actions run link/output.
- On-demand Railway release-candidate endpoint and discovery/protocol report.
- Readiness traffic-rejection confirmation from Railway.
- Previous-deployment restore and forward database-compatibility result.
- Clean Railway operator-session command transcript.
- Candidate stop/scale-down confirmation.
- Ian approval to change the shared production web lifecycle after the non-MCP product check.

## Gate status

Phase 1 exit gate: **not passed**.

No production manifest, production service, production credential, production database, or scheduled non-MCP process has been changed.
