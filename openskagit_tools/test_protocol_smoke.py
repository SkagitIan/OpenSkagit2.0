from unittest.mock import patch

from django.core.management import CommandError
from django.test import SimpleTestCase, override_settings

from openskagit_tools.management.commands.smoke_mcp_protocol import Command


class LocalMcpProtocolCommandTests(SimpleTestCase):
    @override_settings(OPENSKAGIT_ENVIRONMENT="production")
    def test_rejects_production(self):
        with self.assertRaisesMessage(CommandError, "restricted"):
            Command().handle(origin=None)

    @override_settings(OPENSKAGIT_ENVIRONMENT="development")
    @patch("openskagit_tools.management.commands.smoke_mcp_protocol.asyncio.run")
    @patch("openskagit_tools.management.commands.smoke_mcp_protocol.McpOAuthClient.issue")
    def test_removes_ephemeral_oauth_client(self, issue, run):
        client = issue.return_value[0]
        issue.return_value = (client, "not-printed-secret")

        def finish_coroutine(coroutine):
            coroutine.close()
            return {"credentials_persisted": False}

        run.side_effect = finish_coroutine

        Command().handle(origin=None)

        client.delete.assert_called_once_with()
