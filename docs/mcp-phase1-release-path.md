# MCP Phase 1 Release Path

Status: implemented locally; CI and Railway release-candidate evidence are still required before production startup changes.

## Safety model

The same Django ASGI application serves Django, OAuth discovery, and /mcp/api/:

    python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000

Development and test settings fail closed unless they use PostgreSQL/PostGIS on loopback or the Compose service. Development database names must contain dev; test database names must contain test. Test execution reads only OPENSKAGIT_TEST_DATABASE_URL. Local/test OAuth encryption uses OPENSKAGIT_LOCAL_SECRET_KEY, not SECRET_KEY.

Development, test, and release-candidate settings suppress Resend, use console/locmem email, use local document storage, and default live-source tools off outside production. A release candidate must have a new database and new SECRET_KEY; never copy production identity rows or credentials.

## Local setup

Prerequisites: Python 3.12 and Docker Desktop with Docker Compose.

    Copy-Item .env.example .env.local
    .\scripts\local-setup.ps1
    .\scripts\local-run.ps1

local-setup.ps1 installs the lock, starts postgis/postgis:16-3.4 on loopback port 55432, creates separate openskagit_dev and openskagit_test databases, creates the minimum unmanaged source relations in one transaction, inserts one synthetic text-keyed parcel, applies migrations, and runs Django checks.

Validate the complete local release path:

    .\scripts\local-test.ps1

That command bootstraps and migrates disposable test PostGIS, runs checks, performs OAuth discovery and an authorization-code/PKCE exchange through the real ASGI application, verifies unauthenticated rejection plus authenticated initialize and tools/list, removes the ephemeral OAuth client, then runs the Django suite.

Stop containers without deleting the database volume:

    .\scripts\local-stop.ps1

Do not add -v unless intentionally deleting local-only database state.

## Dependency updates

requirements.in and requirements-dev.in are the reviewed inputs. Runtime and verification environments install requirements.lock and requirements-dev.lock.

    .\scripts\update-locks.ps1
    .\scripts\local-test.ps1

Use -Upgrade only for an intentional dependency update. The Windows lock workflow preserves the pywin32 platform marker so Linux CI does not attempt to install it.

## CI

.github/workflows/mcp-ci.yml uses Python 3.12 and disposable PostGIS. It performs:

- pinned dependency installation and pip check;
- Ruff checks for the Phase 1 control plane;
- high-confidence secret scanning without printing candidate values;
- dependency vulnerability scanning against the runtime lock;
- source-schema bootstrap, forward migrations, migrate --check, and Django checks;
- authenticated OAuth/MCP protocol smoke through ASGI;
- the complete Django test suite with the disposable PostGIS database;
- static collection and bytecode compilation.

A successful GitHub run must be archived in docs/mcp-evidence/phase-1/ before the Railway gate.

## On-demand Railway release candidate

This step creates billable external resources and must be explicitly authorized before execution.

Create a new environment named with rc, candidate, or staging; create a new web service and a new PostGIS service inside it. Do not duplicate production database contents, identity rows, OAuth clients, Resend keys, R2 keys, upstream API keys, or SECRET_KEY.

Configure the web service to use railway.release-candidate.json and set:

    OPENSKAGIT_ENVIRONMENT=release-candidate
    OPENSKAGIT_ALLOW_RC_SAMPLE_BOOTSTRAP=true
    OPENSKAGIT_PUBLIC_ORIGIN=https://<candidate-domain>
    ALLOWED_HOSTS=<candidate-domain>
    CSRF_TRUSTED_ORIGINS=https://<candidate-domain>
    DATABASE_URL=<new candidate PostGIS private URL>
    SECRET_KEY=<new candidate-only random value>
    OPENSKAGIT_ENABLE_LIVE_TOOLS=false
    EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
    RESEND_API_KEY=
    BUDGET_PDF_STORAGE=local
    SENTRY_SEND_DEFAULT_PII=false

The candidate manifest collects static files during build, creates only synthetic source relations and data during pre-deploy, then applies migrations. The first pre-deploy marks an empty database with the Railway environment ID; later deploys require the same marker. A populated unmarked database or a marker from another environment is rejected. Web startup runs only Uvicorn/ASGI. Railway admits traffic only after /health/ready/ proves database access, no pending migrations, and MCP registry construction.

Deploy from a clean worktree after CI passes:

    railway up --environment <candidate-environment> --service <candidate-web> --detach
    railway logs --environment <candidate-environment> --service <candidate-web>

From a clean operator session, verify commands need no path workarounds:

    railway run --no-local --environment <candidate-environment> --service <candidate-web> python manage.py check
    railway run --no-local --environment <candidate-environment> --service <candidate-web> python manage.py migrate --check
    railway run --no-local --environment <candidate-environment> --service <candidate-web> python manage.py smoke_mcp_protocol --origin https://<candidate-domain>

The smoke command issues a one-day candidate-only OAuth client, completes OAuth/PKCE and authenticated MCP calls over HTTPS, reports statuses and tool count without secrets, and deletes the client.

## Traffic-rejection and rollback drill

1. Record the healthy candidate deployment ID, commit, readiness response, migration plan, and protocol report.
2. Set OPENSKAGIT_FORCE_NOT_READY=true only in the release-candidate environment and redeploy.
3. Confirm /health/live/ remains 200, /health/ready/ returns sanitized 503 with reason=release_gate, and Railway does not mark the deployment active.
4. Restore OPENSKAGIT_FORCE_NOT_READY=false.
5. In the Railway deployment UI, redeploy the recorded previous healthy deployment. The installed CLI has no rollback subcommand.
6. Run python manage.py migrate --check, readiness, and authenticated protocol smoke again.
7. Record results and stop or scale down the candidate resources.

Do not reverse migrations as part of this drill. If the previous application revision is not forward-compatible with the candidate database schema, the gate fails and production promotion stops.

## Production promotion boundary

The checked-in railway.json and compatibility Procfile retain their current deployed behavior until the candidate, rollback, and non-MCP product checks pass. After Ian approves the evidence, a separate change may:

- move production migrations into a pre-deploy command;
- remove source synchronization and materialized rebuilds from web boot;
- make Uvicorn/ASGI the only supported web entry point;
- point production Railway health checks to /health/ready/.

Tax backfill and slow-check processes are separate products and are not changed by this Phase 1 preparation.
