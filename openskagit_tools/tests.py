from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
import httpx

django.setup()

from django.test import SimpleTestCase

from openskagit_tools.auth import READ_SCOPE, StaticBearerTokenVerifier
from openskagit_tools.contracts import CONTRACT_VERSION, result_envelope
from openskagit_tools.handlers import HANDLERS
from openskagit_tools.forms import McpAccessRequestForm
from openskagit_tools.mcp_server import build_http_server_from_env, build_oauth_http_server, mcp, run
from openskagit_tools.models import McpOAuthClient
from openskagit_tools.oauth_provider import DjangoOAuthProvider
from openskagit_tools.registry import TOOL_CONTRACTS, TOOL_CONTRACT_BY_NAME, get_tool_contract
from openskagit_tools.telemetry import instrument_tool
from openskagit_tools.management.commands.audit_legacy_d1 import _comparable, _embedded_assessor

TEST_TOKEN = "test-token-with-at-least-thirty-two-characters"


class UnifiedToolContractTests(SimpleTestCase):
    def test_legacy_d1_audit_finds_misplaced_assessor_json(self):
        payload = {"days_since_last_sale": json.dumps({"assessor": {"Assessed Value": "9,600"}})}

        assessor, field = _embedded_assessor(payload)

        self.assertEqual(field, "days_since_last_sale")
        self.assertEqual(assessor["Assessed Value"], "9,600")
        self.assertEqual(_comparable("9,600.00"), "9600")

    def test_registry_is_unique_read_only_and_has_handlers(self):
        self.assertEqual(len(TOOL_CONTRACTS), len(TOOL_CONTRACT_BY_NAME))
        self.assertEqual(set(TOOL_CONTRACT_BY_NAME), set(HANDLERS))
        self.assertTrue(all(contract.read_only for contract in TOOL_CONTRACTS))
        self.assertTrue(all(contract.contract_version == CONTRACT_VERSION for contract in TOOL_CONTRACTS))
        self.assertEqual({contract.domain for contract in TOOL_CONTRACTS}, {"parcel", "gis", "context", "zoning", "budget"})

    def test_fastmcp_publishes_exactly_the_contract_registry(self):
        tools = asyncio.run(mcp.list_tools())
        self.assertEqual({tool.name for tool in tools}, set(TOOL_CONTRACT_BY_NAME))

    def test_result_envelope_distinguishes_retrieval_from_data_freshness(self):
        contract = get_tool_contract("parcel_get_summary")
        result = result_envelope({"parcel_id": "P123"}, contract=contract)

        self.assertEqual(set(result), {"data", "sources", "freshness", "warnings", "errors"})
        self.assertEqual(result["data"]["parcel_id"], "P123")
        self.assertEqual(result["sources"][0]["source_id"], "skagit_property_onestop")
        self.assertTrue(result["sources"][0]["retrieved_at"].endswith("Z"))
        self.assertEqual(result["freshness"], {"as_of": None, "status": "unknown"})

    def test_unknown_tool_contract_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "Unknown OpenSkagit tool"):
            get_tool_contract("not_a_tool")

    @patch("openskagit_tools.telemetry.McpToolCall.objects.create")
    def test_tool_telemetry_records_no_arguments_or_response_body(self, create_call):
        def example(parcel_id: str) -> dict:
            return {"freshness": {"as_of": "2020-2024", "status": "unknown"}, "errors": []}

        result = asyncio.run(
            instrument_tool(example, tool_name="context_get_census", caller_class="mcp-http-oauth")("P123")
        )

        self.assertEqual(result["errors"], [])
        fields = create_call.call_args.kwargs
        self.assertEqual(fields["tool_name"], "context_get_census")
        self.assertEqual(fields["freshness_as_of"], "2020-2024")
        self.assertNotIn("parcel_id", fields)
        self.assertNotIn("result", fields)

    @patch.dict(
        os.environ,
        {
            "OPENSKAGIT_UNIFIED_MCP_TRANSPORT": "streamable-http",
            "OPENSKAGIT_UNIFIED_MCP_TOKEN": "",
            "OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL": "http://127.0.0.1:8000",
        },
    )
    def test_remote_transport_requires_token(self):
        with self.assertRaisesMessage(RuntimeError, "TOKEN is required"):
            run()

    @patch("openskagit_tools.handlers.assessor_services.get_parcel_details")
    def test_parcel_handler_delegates_and_wraps(self, get_parcel_details):
        get_parcel_details.return_value = {"parcel_id": "P123", "owner": "Example"}

        result = HANDLERS["parcel_get_summary"]("P123")

        get_parcel_details.assert_called_once_with("P123")
        self.assertEqual(result["data"]["owner"], "Example")
        self.assertEqual(result["errors"], [])

    @patch("openskagit_tools.handlers.assessor_services.search_parcels")
    def test_parcel_search_uses_canonical_postgis_service(self, search_parcels):
        search_parcels.return_value = {"query": "P123", "count": 1, "results": [{"parcel_id": "P123"}]}

        result = HANDLERS["parcel_search"]("P123", 5)

        search_parcels.assert_called_once_with("P123", 5)
        self.assertEqual(result["data"]["results"][0]["parcel_id"], "P123")

    @patch("assessor_mcp.services.connection")
    def test_postgis_parcel_search_normalizes_exact_id_and_shapes_results(self, db_connection):
        db_cursor = db_connection.cursor.return_value.__enter__.return_value
        db_cursor.fetchall.return_value = [
            ("P123", "123 MAIN ST", "MOUNT VERNON WA 98273", "(111) HOUSEHOLD", 100000, -122.3, 48.4, 1)
        ]

        from assessor_mcp.services import search_parcels

        result = search_parcels("123", limit=5)

        self.assertEqual(result["normalized_query"], "123")
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["results"][0]["parcel_id"], "P123")
        self.assertIn("P123", db_cursor.execute.call_args.args[1])

    def test_postgis_parcel_search_rejects_punctuation_only(self):
        from assessor_mcp.services import search_parcels

        with self.assertRaisesMessage(ValueError, "letters or numbers"):
            search_parcels("---")

    @patch("openskagit_tools.handlers.budget_services.budget_get_summary")
    def test_budget_handler_delegates_and_wraps_reviewed_service(self, get_summary):
        get_summary.return_value = {"document": {"fiscal_year": 2026, "status": "adopted"}, "totals": {"expenditure": 10}}

        result = HANDLERS["budget_get_summary"]("anacortes", 2026)

        get_summary.assert_called_once_with("anacortes", 2026)
        self.assertEqual(result["data"]["document"]["status"], "adopted")
        self.assertEqual(result["freshness"]["as_of"], "2026")
    @patch("openskagit_tools.handlers.gis_services.get_parcel_overlays")
    def test_gis_handler_preserves_partial_errors_as_warnings(self, get_parcel_overlays):
        get_parcel_overlays.return_value = {
            "parcel": "P123",
            "overlays": [
                {"layer": "zoning", "status": "ok"},
                {"layer": "wetlands", "status": "query_error"},
            ],
        }

        result = HANDLERS["gis_get_overlays"]("P123", bundles="core")

        get_parcel_overlays.assert_called_once_with("P123", "core", None, True)
        self.assertIn("wetlands", result["warnings"][0])

    @patch("openskagit_tools.handlers.zoning_services.build_parcel_feasibility_report")
    def test_zoning_feasibility_always_carries_screening_warning(self, build_report):
        build_report.return_value = {"parcel": {"parcel_id": "P123"}, "citations": []}

        result = HANDLERS["zoning_build_feasibility"]("P123", "ADU")

        build_report.assert_called_once_with("P123", "ADU")
        self.assertIn("not a legal", result["warnings"][0])

    @patch("openskagit_tools.handlers.context_services.get_census_context")
    def test_census_handler_uses_canonical_context_service(self, get_census_context):
        get_census_context.return_value = {
            "status": "ok",
            "parcel": "P123",
            "note": "Area-level estimate.",
            "acs": {},
        }

        result = HANDLERS["context_get_census"]("P123")

        get_census_context.assert_called_once_with("P123")
        self.assertEqual(result["data"]["parcel"], "P123")
        self.assertIn("Area-level", result["warnings"][0])

    @patch("openskagit_tools.handlers.context_services.get_soils_context")
    def test_soils_handler_exposes_upstream_failure_in_common_envelope(self, get_soils_context):
        get_soils_context.return_value = {
            "status": "error",
            "parcel": "P123",
            "error": "NRCS unavailable",
        }

        result = HANDLERS["context_get_soils"]("P123")

        self.assertEqual(result["errors"][0]["code"], "upstream_context_error")
        self.assertIn("NRCS unavailable", result["errors"][0]["message"])


class UnifiedMcpAuthenticationTests(SimpleTestCase):
    def test_static_verifier_accepts_only_configured_token(self):
        verifier = StaticBearerTokenVerifier(TEST_TOKEN)

        accepted = asyncio.run(verifier.verify_token(TEST_TOKEN))
        rejected = asyncio.run(verifier.verify_token("wrong-token"))

        self.assertIsNotNone(accepted)
        self.assertEqual(accepted.scopes, [READ_SCOPE])
        self.assertIsNone(rejected)

    def test_static_verifier_rejects_short_secrets(self):
        with self.assertRaisesMessage(ValueError, "at least 32"):
            StaticBearerTokenVerifier("short")

    @patch.dict(
        os.environ,
        {
            "OPENSKAGIT_UNIFIED_MCP_TOKEN": TEST_TOKEN,
            "OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL": "http://public.example.test",
        },
    )
    def test_http_server_rejects_insecure_non_loopback_url(self):
        with self.assertRaisesMessage(RuntimeError, "requires HTTPS"):
            build_http_server_from_env()

    @patch.dict(
        os.environ,
        {
            "OPENSKAGIT_UNIFIED_MCP_TOKEN": TEST_TOKEN,
            "OPENSKAGIT_UNIFIED_MCP_PUBLIC_URL": "http://127.0.0.1:8000",
            "OPENSKAGIT_UNIFIED_MCP_HOST": "127.0.0.1",
            "OPENSKAGIT_UNIFIED_MCP_PORT": "8000",
        },
    )
    def test_http_endpoint_requires_valid_bearer_token(self):
        server = build_http_server_from_env()
        app = server.streamable_http_app()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }

        async def exercise_endpoint():
            transport = httpx.ASGITransport(app=app)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
                    missing = await client.post("/mcp", json=payload, headers=headers)
                    invalid = await client.post(
                        "/mcp",
                        json=payload,
                        headers={**headers, "authorization": "Bearer wrong"},
                    )
                    valid = await client.post(
                        "/mcp",
                        json=payload,
                        headers={**headers, "authorization": f"Bearer {TEST_TOKEN}"},
                    )
            return missing, invalid, valid

        missing, invalid, valid = asyncio.run(exercise_endpoint())
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["result"]["serverInfo"]["name"], "OpenSkagit Unified MCP")

class PublicMcpCatalogTests(SimpleTestCase):
    def test_access_form_requires_responsible_use_agreement(self):
        form = McpAccessRequestForm(
            {
                "name": "Agent User",
                "email": "agent@example.com",
                "organization": "",
                "agent_client": "Claude",
                "intended_use": "Parcel research",
                "expected_volume": "low",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("agreed_to_terms", form.errors)

    def test_oauth_client_secret_is_encrypted_at_rest(self):
        client = McpOAuthClient(name="Test", client_id="test", redirect_uris=[])
        client.set_client_secret("top-secret")

        self.assertNotIn("top-secret", client.encrypted_client_secret)
        self.assertEqual(client.get_client_secret(), "top-secret")

    def test_catalog_page_uses_registry_and_connector_url(self):
        response = self.client.get("/mcp/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://openskagit.com/mcp/api/")
        self.assertContains(response, f"{len(TOOL_CONTRACTS)} read-only tools")
        self.assertContains(response, "parcel_get_summary")

    def test_oauth_server_exposes_discovery_and_protocol_routes(self):
        server = build_oauth_http_server(
            public_origin="https://openskagit.com",
            provider=DjangoOAuthProvider(),
        )
        app = server.streamable_http_app()
        paths = {route.path for route in app.routes}

        self.assertIn("/.well-known/oauth-authorization-server", paths)
        self.assertIn("/.well-known/oauth-protected-resource/mcp/api/", paths)
        self.assertIn("/authorize", paths)
        self.assertIn("/token", paths)
        self.assertIn("/mcp/api/", paths)
        self.assertEqual(server.settings.transport_security.allowed_hosts, ["openskagit.com"])
