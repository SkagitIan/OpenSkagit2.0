from __future__ import annotations

import os

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

from openskagit_tools.mcp_server import build_stdio_server, validate_tool_registry


@never_cache
def liveness(_request):
    """Process-only signal: the Django ASGI application can answer HTTP."""
    return JsonResponse({"status": "alive"})


@never_cache
def readiness(_request):
    """Traffic-admission signal for database, migrations, and MCP construction."""
    checks = {
        "database": False,
        "migrations": False,
        "mcp_registry": False,
    }

    if (
        settings.OPENSKAGIT_ENVIRONMENT == "release-candidate"
        and os.getenv("OPENSKAGIT_FORCE_NOT_READY", "").lower() == "true"
    ):
        return JsonResponse(
            {"status": "not_ready", "checks": checks, "reason": "release_gate"},
            status=503,
        )

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        checks["migrations"] = not executor.migration_plan(targets)
    except Exception:
        # Keep health responses free of database addresses, SQL, and credentials.
        pass

    try:
        validate_tool_registry()
        build_stdio_server()
        checks["mcp_registry"] = True
    except Exception:
        pass

    ready = all(checks.values())
    return JsonResponse(
        {"status": "ready" if ready else "not_ready", "checks": checks},
        status=200 if ready else 503,
    )
