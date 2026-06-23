from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count, Sum
from django.shortcuts import render

from .models import TaxStatement, TaxStatementError, TaxStatementRun
from .services import LEAD_ORDER


ACTIONABLE_LEVELS = {"behind", "serious", "severe"}


def active_parcel_total():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM skagit_parcels WHERE inactive_date IS NULL")
        return cursor.fetchone()[0]


def fmt_money(value):
    if value is None:
        return "$0.00"
    return f"${Decimal(value):,.2f}"


@staff_member_required
def dashboard(request):
    selected_level = request.GET.get("level", "actionable")
    statements = TaxStatement.objects.filter(total_due__gt=0).order_by("parcel_number", "-tax_year")
    if selected_level == "actionable":
        statements = statements.filter(lead_level__in=ACTIONABLE_LEVELS)
    elif selected_level in LEAD_ORDER:
        statements = statements.filter(lead_level=selected_level)

    grouped = {}
    for statement in statements[:5000]:
        item = grouped.setdefault(
            statement.parcel_number,
            {
                "parcel_number": statement.parcel_number,
                "tax_account_number": statement.tax_account_number,
                "owner_name": statement.owner_name,
                "situs_address": statement.situs_address,
                "total_due": Decimal("0.00"),
                "years": [],
                "max_lead_level": statement.lead_level,
                "oldest_due_date": statement.oldest_due_date,
                "latest_fetch": statement.source_fetched_at,
            },
        )
        item["total_due"] += statement.total_due or Decimal("0.00")
        item["years"].append(statement)
        if LEAD_ORDER.get(statement.lead_level, 0) > LEAD_ORDER.get(item["max_lead_level"], 0):
            item["max_lead_level"] = statement.lead_level
        if statement.oldest_due_date and (
            item["oldest_due_date"] is None or statement.oldest_due_date < item["oldest_due_date"]
        ):
            item["oldest_due_date"] = statement.oldest_due_date
        if statement.source_fetched_at > item["latest_fetch"]:
            item["latest_fetch"] = statement.source_fetched_at

    leads = sorted(
        grouped.values(),
        key=lambda row: (LEAD_ORDER.get(row["max_lead_level"], 0), row["total_due"]),
        reverse=True,
    )[:200]
    for lead in leads:
        lead["total_due_fmt"] = fmt_money(lead["total_due"])
        lead["year_list"] = ", ".join(str(row.tax_year) for row in lead["years"])

    level_counts = {
        row["lead_level"]: row["count"]
        for row in TaxStatement.objects.values("lead_level").annotate(count=Count("id")).order_by("lead_level")
    }
    due_by_level = {
        row["lead_level"]: {
            "count": row["count"],
            "total_due": fmt_money(row["total_due"]),
        }
        for row in TaxStatement.objects.filter(total_due__gt=0)
        .values("lead_level")
        .annotate(count=Count("id"), total_due=Sum("total_due"))
        .order_by("lead_level")
    }
    year_stats = list(
        TaxStatement.objects.values("tax_year")
        .annotate(count=Count("id"), due_count=Count("id", filter=None), total_due=Sum("total_due"))
        .order_by("-tax_year")
    )
    for row in year_stats:
        row["total_due_fmt"] = fmt_money(row["total_due"])

    context = {
        "active_parcel_total": active_parcel_total(),
        "statement_total": TaxStatement.objects.count(),
        "parcel_coverage": TaxStatement.objects.values("parcel_number").distinct().count(),
        "level_counts": level_counts,
        "due_by_level": due_by_level,
        "year_stats": year_stats,
        "runs": TaxStatementRun.objects.all()[:10],
        "errors": TaxStatementError.objects.filter(resolved_at__isnull=True)[:25],
        "error_count": TaxStatementError.objects.filter(resolved_at__isnull=True).count(),
        "leads": leads,
        "selected_level": selected_level,
        "levels": [
            ("actionable", "Actionable"),
            ("one_late", "One late"),
            ("behind", "Behind"),
            ("serious", "Serious"),
            ("severe", "Severe"),
            ("watch", "Watch"),
        ],
    }
    return render(request, "tax_delinquency/dashboard.html", context)
