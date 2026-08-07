import os
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from config.health import liveness, readiness


class HealthEndpointTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/health/ready/")

    @override_settings(OPENSKAGIT_ENVIRONMENT="release-candidate")
    @patch.dict(os.environ, {"OPENSKAGIT_FORCE_NOT_READY": "true"})
    def test_release_candidate_can_prove_traffic_rejection(self):
        response = readiness(self.request)

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content,
            {
                "status": "not_ready",
                "checks": {"database": False, "migrations": False, "mcp_registry": False},
                "reason": "release_gate",
            },
        )

    def test_liveness_does_not_depend_on_database(self):
        response = liveness(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "alive"})

    @patch("config.health.build_stdio_server")
    @patch("config.health.validate_tool_registry")
    @patch("config.health.MigrationExecutor")
    @patch("config.health.connection")
    def test_readiness_requires_database_migrations_and_registry(
        self,
        db_connection,
        executor_class,
        validate_registry,
        build_server,
    ):
        cursor = MagicMock()
        db_connection.cursor.return_value.__enter__.return_value = cursor
        executor_class.return_value.loader.graph.leaf_nodes.return_value = [("openskagit_tools", "0001_initial")]
        executor_class.return_value.migration_plan.return_value = []

        response = readiness(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "status": "ready",
                "checks": {"database": True, "migrations": True, "mcp_registry": True},
            },
        )
        cursor.execute.assert_called_once_with("SELECT 1")
        validate_registry.assert_called_once_with()
        build_server.assert_called_once_with()

    @patch("config.health.build_stdio_server")
    @patch("config.health.validate_tool_registry")
    @patch("config.health.connection")
    def test_readiness_sanitizes_database_failure(
        self,
        db_connection,
        validate_registry,
        build_server,
    ):
        db_connection.cursor.side_effect = RuntimeError("postgresql://user:secret@host/database")

        response = readiness(self.request)

        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"secret", response.content)
        self.assertJSONEqual(
            response.content,
            {
                "status": "not_ready",
                "checks": {"database": False, "migrations": False, "mcp_registry": True},
            },
        )
        validate_registry.assert_called_once_with()
        build_server.assert_called_once_with()

    @patch("config.health.build_stdio_server")
    @patch("config.health.validate_tool_registry")
    @patch("config.health.MigrationExecutor")
    @patch("config.health.connection")
    def test_readiness_rejects_unapplied_migrations(
        self,
        db_connection,
        executor_class,
        _validate_registry,
        _build_server,
    ):
        db_connection.cursor.return_value.__enter__.return_value = MagicMock()
        executor_class.return_value.loader.graph.leaf_nodes.return_value = [("core", "0007_drop_levy_area_map")]
        executor_class.return_value.migration_plan.return_value = [MagicMock()]

        response = readiness(self.request)

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content,
            {
                "status": "not_ready",
                "checks": {"database": True, "migrations": False, "mcp_registry": True},
            },
        )
