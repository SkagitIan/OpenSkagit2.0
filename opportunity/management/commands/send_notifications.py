from django.core.management.base import BaseCommand

from opportunity.notifications import send_pending_brief, send_pending_watchlist


class Command(BaseCommand):
    help = "Send pending Parcel Book notifications via Resend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cadence",
            choices=["daily", "weekly"],
            default="daily",
            help="Send watchlist digests for users with this cadence (default: daily).",
        )
        parser.add_argument(
            "--skip-watchlist",
            action="store_true",
            help="Skip watchlist digests; only send the brief if --brief is set.",
        )
        parser.add_argument(
            "--brief",
            action="store_true",
            help="Also send the daily brief to subscribed users.",
        )

    def handle(self, *args, **options):
        if not options["skip_watchlist"]:
            cadence = options["cadence"]
            sent = send_pending_watchlist(cadence, stdout=self.stdout)
            self.stdout.write(self.style.SUCCESS(f"Watchlist ({cadence}): {sent} notification(s) sent."))

        if options["brief"]:
            sent = send_pending_brief(stdout=self.stdout)
            self.stdout.write(self.style.SUCCESS(f"Brief: {sent} user(s) notified."))
