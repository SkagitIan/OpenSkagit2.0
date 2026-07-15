import os

from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

from openskagit_tools.mcp_server import build_oauth_http_server  # noqa: E402
from openskagit_tools.oauth_provider import DjangoOAuthProvider  # noqa: E402

mcp_server = build_oauth_http_server(
    public_origin=settings.OPENSKAGIT_PUBLIC_ORIGIN,
    provider=DjangoOAuthProvider(),
)
mcp_application = mcp_server.streamable_http_app()

MCP_EXACT_PATHS = {
    "/authorize",
    "/token",
    "/revoke",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource/mcp/api/",
}


async def application(scope, receive, send):
    """Route MCP/OAuth traffic to FastMCP and all other traffic to Django."""
    if scope["type"] == "lifespan":
        await mcp_application(scope, receive, send)
        return

    path = scope.get("path", "")
    if scope["type"] == "http" and (path.startswith("/mcp/api/") or path in MCP_EXACT_PATHS):
        await mcp_application(scope, receive, send)
        return

    await django_application(scope, receive, send)
