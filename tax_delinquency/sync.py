from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import connection
from django.utils import timezone

from .models import TaxStatement, TaxStatementError, TaxStatementRun
from .services import fetch_statement, parse_money


def default_years() -> list[int]:
    return list(range(2023, timezone.localdate().year + 1))


def active_parcel_count() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM skagit_parcels WHERE inactive_date IS NULL")
        return cursor.fetchone()[0]


def iter_active_parcels(limit: int | None = None, offset: int = 0, parcel_number: str | None = None):
    sql = """
        SELECT
            parcel_number,
            account_number,
            owner_name,
            CONCAT_WS(' ', situs_street_number, situs_street_name, situs_city_state_zip) AS situs_address
        FROM skagit_parcels
        WHERE inactive_date IS NULL
    """
    params = []
    if parcel_number:
        sql += " AND parcel_number = %s"
        params.append(parcel_number)
    sql += " ORDER BY parcel_number"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    if offset:
        sql += " OFFSET %s"
        params.append(offset)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        for row in cursor.fetchall():
            yield dict(zip(columns, row))


def should_skip_statement(parcel_number: str, tax_year: int, stale_after: timezone.datetime | None, force: bool) -> bool:
    if force or stale_after is None:
        return False
    return TaxStatement.objects.filter(
        parcel_number=parcel_number,
        tax_year=tax_year,
        source_fetched_at__gte=stale_after,
    ).exists()


def parse_decimal_field(value):
    if isinstance(value, Decimal) or value is None:
        return value
    return parse_money(str(value))


def save_statement(parsed: dict, parcel: dict, run: TaxStatementRun) -> TaxStatement:
    oldest_due_date = parsed.get("oldest_due_date") or None
    defaults = {
        "tax_account_number": parsed.get("tax_account_number") or parcel.get("account_number"),
        "owner_name": parcel.get("owner_name"),
        "situs_address": parcel.get("situs_address"),
        "levy_code": parsed.get("levy_code"),
        "general_tax": parse_decimal_field(parsed.get("general_tax")),
        "special_assessments_fees": parse_decimal_field(parsed.get("special_assessments_fees")),
        "total_due": parse_decimal_field(parsed.get("total_due")),
        "amount_paid": parse_decimal_field(parsed.get("amount_paid")),
        "status": parsed.get("status") or TaxStatement.Status.UNKNOWN,
        "lead_level": parsed.get("lead_level") or TaxStatement.LeadLevel.UNKNOWN,
        "delinquent_installment_count": parsed.get("delinquent_installment_count") or 0,
        "unpaid_installment_count": parsed.get("unpaid_installment_count") or 0,
        "oldest_due_date": date.fromisoformat(oldest_due_date) if oldest_due_date else None,
        "source_url": parsed["source_url"],
        "source_fetched_at": datetime.fromisoformat(parsed["source_fetched_at"]),
        "raw_data": parsed,
        "last_run": run,
    }
    statement, _ = TaxStatement.objects.update_or_create(
        parcel_number=parsed["parcel_number"],
        tax_year=parsed["tax_year"],
        defaults=defaults,
    )
    TaxStatementError.objects.filter(
        parcel_number=parsed["parcel_number"],
        tax_year=parsed["tax_year"],
        resolved_at__isnull=True,
    ).update(resolved_at=timezone.now())
    return statement


def record_error(run: TaxStatementRun, parcel_number: str, tax_year: int, source_url: str, exc: Exception):
    TaxStatementError.objects.create(
        run=run,
        parcel_number=parcel_number,
        tax_year=tax_year,
        source_url=source_url,
        error_type=exc.__class__.__name__,
        message=str(exc)[:2000],
    )


def sync_statements(
    *,
    run_type: str,
    years: list[int] | None = None,
    limit: int | None = None,
    offset: int = 0,
    parcel_number: str | None = None,
    delay: float = 0.35,
    stale_hours: float | None = None,
    force: bool = False,
    timeout: int = 20,
    stdout=None,
) -> TaxStatementRun:
    years = years or default_years()
    stale_after = timezone.now() - timedelta(hours=stale_hours) if stale_hours else None
    run = TaxStatementRun.objects.create(
        run_type=run_type,
        years=years,
        options={
            "limit": limit,
            "offset": offset,
            "parcel_number": parcel_number,
            "delay": delay,
            "stale_hours": stale_hours,
            "force": force,
            "timeout": timeout,
        },
    )

    try:
        for parcel in iter_active_parcels(limit=limit, offset=offset, parcel_number=parcel_number):
            run.parcels_considered += 1
            for tax_year in years:
                if should_skip_statement(parcel["parcel_number"], tax_year, stale_after, force):
                    run.statements_skipped += 1
                    continue
                run.statements_attempted += 1
                try:
                    parsed = fetch_statement(parcel["parcel_number"], tax_year, timeout=timeout)
                    save_statement(parsed, parcel, run)
                    run.statements_saved += 1
                except Exception as exc:
                    run.errors += 1
                    record_error(run, parcel["parcel_number"], tax_year, "", exc)
                    if stdout:
                        stdout.write(f"{parcel['parcel_number']} {tax_year} ERROR {exc}")
                if (run.statements_attempted + run.statements_skipped) % 100 == 0:
                    run.save()
                    if stdout:
                        stdout.write(
                            "progress "
                            f"parcels={run.parcels_considered} attempted={run.statements_attempted} "
                            f"saved={run.statements_saved} skipped={run.statements_skipped} errors={run.errors}"
                        )
                time.sleep(delay)
        run.status = TaxStatementRun.Status.SUCCESS
    except KeyboardInterrupt:
        run.status = TaxStatementRun.Status.STOPPED
        run.notes = "Interrupted."
    except Exception as exc:
        run.status = TaxStatementRun.Status.ERROR
        run.notes = str(exc)[:2000]
        raise
    finally:
        run.finished_at = timezone.now()
        run.save()
    return run
