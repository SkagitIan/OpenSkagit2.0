from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from openskagit_tools.models import CLAUDE_REDIRECT_URIS, McpAccessRequest, McpOAuthClient


class Command(BaseCommand):
    help = "Approve an MCP access request and issue OAuth client credentials once."

    def add_arguments(self, parser):
        parser.add_argument("request_id", type=int)
        parser.add_argument("--name", default="Claude connector")
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--redirect-uri", action="append", dest="redirect_uris")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            access_request = McpAccessRequest.objects.select_for_update().get(pk=options["request_id"])
        except McpAccessRequest.DoesNotExist as exc:
            raise CommandError("Access request not found.") from exc
        if access_request.status == McpAccessRequest.STATUS_DECLINED:
            raise CommandError("Declined requests cannot be approved without changing their status first.")
        client, raw_secret = McpOAuthClient.issue(
            name=options["name"],
            access_request=access_request,
            redirect_uris=options["redirect_uris"] or list(CLAUDE_REDIRECT_URIS),
            days=options["days"],
        )
        access_request.status = McpAccessRequest.STATUS_APPROVED
        access_request.reviewed_at = timezone.now()
        access_request.save(update_fields=["status", "reviewed_at"])
        self.stdout.write(self.style.SUCCESS("OAuth client issued. The secret is shown once."))
        self.stdout.write(f"MCP URL: https://openskagit.com/mcp/api/")
        self.stdout.write(f"Client ID: {client.client_id}")
        self.stdout.write(f"Client secret: {raw_secret}")
        self.stdout.write("Store the secret securely; it cannot be recovered from admin output.")
