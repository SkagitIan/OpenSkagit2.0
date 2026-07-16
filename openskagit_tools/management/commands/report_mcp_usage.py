from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone

from openskagit_tools.models import McpToolCall


class Command(BaseCommand):
    help = "Report secret-free MCP usage, latency, and failures for cutover decisions."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")
        since = timezone.now() - timedelta(days=days)
        rows = (
            McpToolCall.objects.filter(called_at__gte=since)
            .values("tool_name", "caller_class")
            .annotate(
                calls=Count("id"),
                failures=Count("id", filter=Q(outcome="error")),
                average_ms=Avg("duration_ms"),
                maximum_ms=Max("duration_ms"),
                last_called=Max("called_at"),
            )
            .order_by("tool_name", "caller_class")
        )
        self.stdout.write(f"OpenSkagit MCP usage: last {days} day(s)")
        if not rows:
            self.stdout.write("No tool calls recorded in this window.")
            return
        for row in rows:
            self.stdout.write(
                f"{row['tool_name']} [{row['caller_class']}]: calls={row['calls']} "
                f"failures={row['failures']} avg_ms={round(row['average_ms'] or 0)} "
                f"max_ms={row['maximum_ms']} last={row['last_called'].isoformat()}"
            )
