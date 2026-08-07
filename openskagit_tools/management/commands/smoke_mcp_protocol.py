from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from openskagit_tools.auth import READ_SCOPE
from openskagit_tools.models import McpOAuthClient
from openskagit_tools.registry import TOOL_CONTRACT_BY_NAME


class Command(BaseCommand):
    help = "Exercise OAuth discovery, authorization-code exchange, and MCP protocol with ephemeral credentials."

    def add_arguments(self, parser):
        parser.add_argument(
            "--origin",
            help="HTTPS release-candidate origin. Omit to exercise the in-process local ASGI application.",
        )

    def handle(self, *args, **options):
        remote_origin = (options.get("origin") or "").strip().rstrip("/")
        if remote_origin:
            railway_name = os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
            if (
                settings.OPENSKAGIT_ENVIRONMENT != "release-candidate"
                or not any(marker in railway_name for marker in ("rc", "candidate", "staging"))
                or urlparse(remote_origin).scheme != "https"
                or remote_origin != settings.OPENSKAGIT_PUBLIC_ORIGIN
            ):
                raise CommandError(
                    "Remote smoke requires the matching HTTPS origin in an explicitly named "
                    "Railway release-candidate environment."
                )
        elif settings.OPENSKAGIT_ENVIRONMENT not in {"development", "test"}:
            raise CommandError("In-process MCP protocol smoke is restricted to development and test environments.")

        redirect_uri = "http://127.0.0.1:8765/callback"
        client, client_secret = McpOAuthClient.issue(
            name="Phase 1 protocol smoke",
            redirect_uris=[redirect_uri],
            days=1,
        )
        try:
            report = asyncio.run(
                self._exercise(
                    client_id=client.client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                    remote_origin=remote_origin or None,
                )
            )
        finally:
            client.delete()

        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        self.stdout.write(self.style.SUCCESS("Authenticated MCP protocol smoke passed."))

    @asynccontextmanager
    async def _http_client(self, remote_origin: str | None):
        if remote_origin:
            async with httpx.AsyncClient(
                base_url=remote_origin,
                follow_redirects=False,
                timeout=30,
            ) as http:
                yield http
            return

        from config.asgi import application, mcp_application

        transport = httpx.ASGITransport(app=application)
        async with mcp_application.router.lifespan_context(mcp_application):
            async with httpx.AsyncClient(
                transport=transport,
                base_url=settings.OPENSKAGIT_PUBLIC_ORIGIN,
                follow_redirects=False,
            ) as http:
                yield http

    async def _exercise(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        remote_origin: str | None,
    ) -> dict:
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        )
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "openskagit-phase1-smoke", "version": "1.0"},
            },
        }
        protocol_headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }

        async with self._http_client(remote_origin) as http:
            oauth_discovery = await http.get("/.well-known/oauth-authorization-server")
            protected_discovery = await http.get("/.well-known/oauth-protected-resource/mcp/api/")
            unauthenticated = await http.post("/mcp/api/", json=initialize, headers=protocol_headers)
            authorization = await http.get(
                "/authorize",
                params={
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "scope": READ_SCOPE,
                    "state": "phase1-smoke",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            )
            if authorization.status_code not in {302, 303, 307}:
                raise CommandError(f"Authorization endpoint returned {authorization.status_code}, expected redirect.")
            code_values = parse_qs(urlparse(authorization.headers["location"]).query).get("code")
            if not code_values:
                raise CommandError("Authorization redirect did not contain a code.")

            token_response = await http.post(
                "/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code_values[0],
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code_verifier": verifier,
                },
            )
            if token_response.status_code != 200:
                raise CommandError(f"Token exchange returned {token_response.status_code}.")
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise CommandError("Token exchange did not return an access token.")

            authenticated_headers = {
                **protocol_headers,
                "authorization": f"Bearer {access_token}",
            }
            initialized = await http.post(
                "/mcp/api/",
                json=initialize,
                headers=authenticated_headers,
            )
            tools_response = await http.post(
                "/mcp/api/",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=authenticated_headers,
            )

        expected_statuses = {
            "oauth_discovery": (oauth_discovery.status_code, 200),
            "protected_resource_discovery": (protected_discovery.status_code, 200),
            "unauthenticated_mcp": (unauthenticated.status_code, 401),
            "authenticated_initialize": (initialized.status_code, 200),
            "authenticated_tools_list": (tools_response.status_code, 200),
        }
        failures = {
            name: {"actual": actual, "expected": expected}
            for name, (actual, expected) in expected_statuses.items()
            if actual != expected
        }
        if failures:
            raise CommandError(f"Protocol smoke status mismatch: {failures}")

        tool_names = {item["name"] for item in tools_response.json().get("result", {}).get("tools", [])}
        expected_tools = set(TOOL_CONTRACT_BY_NAME)
        if tool_names != expected_tools:
            raise CommandError(
                "Authenticated tools/list diverged from the registry: "
                f"missing={sorted(expected_tools - tool_names)}, extra={sorted(tool_names - expected_tools)}"
            )

        return {
            "origin": remote_origin or settings.OPENSKAGIT_PUBLIC_ORIGIN,
            "transport": "https" if remote_origin else "in-process-asgi",
            "oauth_discovery_status": oauth_discovery.status_code,
            "protected_resource_discovery_status": protected_discovery.status_code,
            "unauthenticated_mcp_status": unauthenticated.status_code,
            "authenticated_initialize_status": initialized.status_code,
            "authenticated_tools_list_status": tools_response.status_code,
            "tool_count": len(tool_names),
            "credentials_persisted": False,
        }
