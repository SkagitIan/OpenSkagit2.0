"""
Staff dashboard data — signups, parcel searches, notification delivery,
and background-job health across the apps TaxShift depends on.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import ParcelSearchCache, TaxShiftNotification, TaxShiftSignup

# Runs older than this are stale enough that a missing/failed run is worth
# flagging even if the most recent row on file happens to say "success".
STALE_HOURS = {"assessor_sync": 36, "live_check": 36, "tax_statement": 24 * 9}


def build_dashboard_context() -> dict:
    now = timezone.now()

    return {
        "generated_at": now,
        "signups": _signup_section(now),
        "parcels": _parcel_section(),
        "notifications": _notification_section(),
        "jobs": _job_health_section(now),
    }


def _signup_section(now) -> dict:
    signups = TaxShiftSignup.objects.all()
    total = signups.count()

    by_status = {
        row["resolution_status"]: row["count"]
        for row in signups.values("resolution_status").annotate(count=Count("id"))
    }

    daily_counts = list(
        signups.filter(created_at__gte=now - timedelta(days=14))
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    max_daily = max((row["count"] for row in daily_counts), default=0)

    return {
        "total": total,
        "verified": signups.filter(is_verified=True).count(),
        "active": signups.filter(is_active=True).count(),
        "unsubscribed": signups.filter(is_active=False, unsubscribed_at__isnull=False).count(),
        "by_status": {
            "resolved": by_status.get(TaxShiftSignup.RESOLUTION_RESOLVED, 0),
            "pending": by_status.get(TaxShiftSignup.RESOLUTION_PENDING, 0),
            "unresolved": by_status.get(TaxShiftSignup.RESOLUTION_UNRESOLVED, 0),
            "ambiguous": by_status.get(TaxShiftSignup.RESOLUTION_AMBIGUOUS, 0),
        },
        "daily_counts": daily_counts,
        "max_daily": max_daily,
        "recent": signups.select_related("user").order_by("-created_at")[:25],
    }


def _parcel_section() -> dict:
    parcels = ParcelSearchCache.objects.all()
    return {
        "distinct_parcels": parcels.count(),
        "total_searches": parcels.aggregate(total=Sum("hit_count"))["total"] or 0,
        "top_searched": parcels.order_by("-hit_count")[:10],
        "recent": parcels.order_by("-last_seen_at")[:10],
    }


def _notification_section() -> dict:
    notifications = TaxShiftNotification.objects.all()
    by_trigger = {
        row["trigger_type"]: row["count"]
        for row in notifications.values("trigger_type").annotate(count=Count("id"))
    }
    return {
        "total": notifications.count(),
        "sent": notifications.filter(sent_at__isnull=False).count(),
        "pending": notifications.filter(sent_at__isnull=True).count(),
        "assessor_change": by_trigger.get(TaxShiftNotification.TRIGGER_ASSESSOR, 0),
        "auditor_recording": by_trigger.get(TaxShiftNotification.TRIGGER_AUDITOR, 0),
        "recent": notifications.select_related("signup").order_by("-created_at")[:15],
    }


def _job_health_section(now) -> dict:
    from assessor_sync.models import AssessorSyncRun, LiveCheckRun
    from tax_delinquency.models import TaxStatementRun

    assessor_runs = list(AssessorSyncRun.objects.order_by("-started_at")[:5])
    live_check_runs = list(LiveCheckRun.objects.order_by("-started_at")[:5])
    tax_statement_runs = list(TaxStatementRun.objects.order_by("-started_at")[:5])

    return {
        "assessor_sync": {
            "runs": assessor_runs,
            "healthy": _is_healthy(assessor_runs, "started_at", now, STALE_HOURS["assessor_sync"], ok_statuses={"success"}),
        },
        "live_check": {
            "runs": live_check_runs,
            "healthy": _is_healthy(live_check_runs, "started_at", now, STALE_HOURS["live_check"], ok_statuses={"success"}),
        },
        "tax_statement": {
            "runs": tax_statement_runs,
            "healthy": _is_healthy(tax_statement_runs, "started_at", now, STALE_HOURS["tax_statement"], ok_statuses={"success"}),
        },
    }


def _is_healthy(runs, timestamp_field, now, stale_hours, ok_statuses) -> bool:
    if not runs:
        return False
    latest = runs[0]
    if getattr(latest, timestamp_field) < now - timedelta(hours=stale_hours):
        return False
    return str(latest.status).lower() in ok_statuses
