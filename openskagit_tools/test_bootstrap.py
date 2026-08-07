from unittest.mock import MagicMock, patch

from django.core.management import CommandError
from django.test import SimpleTestCase, override_settings

from openskagit_tools.management.commands.bootstrap_mcp_source_schema import Command


class BootstrapSourceSchemaTests(SimpleTestCase):
    def test_release_candidate_rejects_populated_unmarked_database(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (None, "django_migrations", "openskagit_tools_mcpoauthclient")

        with self.assertRaisesMessage(CommandError, "unmarked"):
            Command._verify_release_candidate_database(cursor, environment_id="rc-environment-id")

    @override_settings(OPENSKAGIT_ENVIRONMENT="production")
    def test_rejects_non_local_environment(self):
        with self.assertRaisesMessage(CommandError, "restricted"):
            Command().handle(with_sample=False)

    @override_settings(OPENSKAGIT_ENVIRONMENT="test")
    @patch("openskagit_tools.management.commands.bootstrap_mcp_source_schema.transaction.atomic")
    @patch("openskagit_tools.management.commands.bootstrap_mcp_source_schema.connection")
    def test_uses_transaction_and_verifies_relations(self, db_connection, atomic):
        cursor = MagicMock()
        db_connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = [
            ("assessor_rollup",),
            ("sales",),
            ("parcel_zoning",),
            ("v_parcel_tax_summary",),
            ("skagit_parcels",),
            ("gis_skagit_parcels",),
            ("parcel_primary_zoning",),
            ("waza_zoning_zones",),
        ]

        Command().handle(with_sample=True)

        atomic.assert_called_once_with()
        self.assertEqual(cursor.execute.call_count, 3)
