from __future__ import annotations

import os
from urllib.parse import urlparse

import django
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from .auth import READ_SCOPE, StaticBearerTokenVerifier  # noqa: E402
from .handlers import HANDLERS  # noqa: E402
from .registry import TOOL_CONTRACTS, TOOL_CONTRACT_BY_NAME  # noqa: E402
from .telemetry import instrument_tool  # noqa: E402

INSTRUCTIONS = """
Read-only OpenSkagit parcel, GIS, Census/soils, and zoning tools.
Use parcel tools for live county property facts, GIS tools for spatial screening,
and zoning tools for cited planning context. Zoning and GIS outputs are not legal,
permitting, engineering, appraisal, or entitlement determinations.
""".strip()


def _register_tools(server: FastMCP, *, caller_class: str) -> FastMCP:
    if set(HANDLERS) != set(TOOL_CONTRACT_BY_NAME):
        missing_handlers = sorted(set(TOOL_CONTRACT_BY_NAME) - set(HANDLERS))
        missing_contracts = sorted(set(HANDLERS) - set(TOOL_CONTRACT_BY_NAME))
        raise RuntimeError(
            f"Unified tool registry mismatch: missing_handlers={missing_handlers}, "
            f"missing_contracts={missing_contracts}"
        )
    for contract in TOOL_CONTRACTS:
        server.add_tool(
            instrument_tool(HANDLERS[contract.name], tool_name=contract.name, caller_class=caller_class),
            name=contract.name,
            description=contract.description,
            structured_output=True,
        )
    return server


def build_stdio_server() -> FastMCP:
    return _register_tools(
        FastMCP(
            "OpenSkagit Unified MCP",
            instructions=INSTRUCTIONS,
            json_response=True,
            stateless_http=True,
        ),
        caller_class="mcp-stdio",
    )


def _validated_public_url(value: str) -> str:
    public_url = value.strip().rstrip("/")
    if not public_url:
        raise RuntimeError("OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL is required for HTTP transport.")
    parsed = urlparse(public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL must be an absolute HTTP(S) URL.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError("OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL must contain only the public origin.")
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not loopback:
        raise RuntimeError("Remote MCP requires HTTPS unless the public URL is loopback-only.")
    return public_url


def build_http_server_from_env() -> FastMCP:
    token = os.environ.get("OPENSKAGIT_UNIFIED_MCP_TOKEN", "")
    if not token.strip():
        raise RuntimeError("OPENSKAGIT_UNIFIED_MCP_TOKEN is required for HTTP transport.")
    public_url = _validated_public_url(os.environ.get("OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL", ""))
    host = os.environ.get("OPENSKAGIT_UNIFIED_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.environ.get("PORT") or os.environ.get("OPENSKAGIT_UNIFIED_MCP_PORT", "8000"))
    except ValueError as exc:
        raise RuntimeError("Unified MCP port must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Unified MCP port must be between 1 and 65535.")

    verifier = StaticBearerTokenVerifier(token)
    auth = AuthSettings(
        issuer_url=f"{public_url}/",
        resource_server_url=f"{public_url}/mcp",
        required_scopes=[READ_SCOPE],
    )
    return _register_tools(
        FastMCP(
            "OpenSkagit Unified MCP",
            instructions=INSTRUCTIONS,
            host=host,
            port=port,
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            token_verifier=verifier,
            auth=auth,
        ),
        caller_class="mcp-http-bearer",
    )


def build_oauth_http_server(
    *,
    public_origin: str,
    provider,
    host: str = "127.0.0.1",
    port: int = 8000,
    endpoint_path: str = "/mcp/api/",
) -> FastMCP:
    origin = _validated_public_url(public_origin)
    if not endpoint_path.startswith("/"):
        raise RuntimeError("MCP endpoint path must start with '/'.")
    auth = AuthSettings(
        issuer_url=f"{origin}/",
        service_documentation_url=f"{origin}/mcp/",
        resource_server_url=f"{origin}{endpoint_path}",
        required_scopes=[READ_SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=False,
            valid_scopes=[READ_SCOPE],
            default_scopes=[READ_SCOPE],
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    return _register_tools(
        FastMCP(
            "OpenSkagit Unified MCP",
            instructions=INSTRUCTIONS,
            host=host,
            port=port,
            streamable_http_path=endpoint_path,
            json_response=True,
            stateless_http=True,
            transport_security=TransportSecuritySettings(
                allowed_hosts=[urlparse(origin).netloc],
                allowed_origins=[origin],
            ),
            auth_server_provider=provider,
            auth=auth,
        ),
        caller_class="mcp-http-oauth",
    )

mcp = build_stdio_server()


def run() -> None:
    transport = os.environ.get("OPENSKAGIT_UNIFIED_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    if transport == "streamable-http":
        build_http_server_from_env().run(transport="streamable-http")
        return
    raise RuntimeError("Unified MCP transport must be 'stdio' or 'streamable-http'.")


if __name__ == "__main__":
    run()
