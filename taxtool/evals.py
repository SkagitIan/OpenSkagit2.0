from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db import connection

from .models import ParcelSearchCache
from .report import build_tax_report_context


ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass
class EvalFinding:
    severity: str
    check: str
    message: str
    expected: Any = None
    actual: Any = None


@dataclass
class ParcelEvalResult:
    parcel_number: str
    address: str = ""
    findings: list[EvalFinding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self):
        return sum(1 for finding in self.findings if finding.severity == ERROR)

    @property
    def warning_count(self):
        return sum(1 for finding in self.findings if finding.severity == WARNING)

    @property
    def passed(self):
        return self.error_count == 0


def select_eval_parcels(sample_size=25, seed="taxshift-evals-v1", recent=0, explicit=None, levy_code=None):
    """Return parcel numbers to evaluate: explicit, recent user-facing, then deterministic DB sample."""
    seen = set()
    parcel_numbers = []

    def add(parcel_number):
        parcel_number = str(parcel_number or "").strip()
        if parcel_number and parcel_number not in seen:
            parcel_numbers.append(parcel_number)
            seen.add(parcel_number)

    for parcel_number in explicit or []:
        add(parcel_number)

    if recent:
        recent_qs = ParcelSearchCache.objects.order_by("-last_seen_at").values_list("parcel_number", flat=True)[:recent]
        for parcel_number in recent_qs:
            add(parcel_number)

    if sample_size and sample_size > 0:
        target_count = len(parcel_numbers) + sample_size
        params = []
        levy_filter = ""
        if levy_code:
            levy_filter = "AND levy_code = %s"
            params.append(levy_code)
        params.extend([seed, sample_size + len(seen)])
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT parcel_number
                FROM skagit_parcels
                WHERE inactive_date IS NULL
                  AND total_taxes IS NOT NULL
                  AND total_taxes > 0
                  {levy_filter}
                ORDER BY md5(parcel_number || %s)
                LIMIT %s
                """,
                params,
            )
            for (parcel_number,) in cursor.fetchall():
                add(parcel_number)
                if len(parcel_numbers) >= target_count:
                    break

    return parcel_numbers


def evaluate_tax_report_parcel(parcel_number):
    context = build_tax_report_context(parcel_number)
    result = ParcelEvalResult(parcel_number=parcel_number)

    def add(severity, check, message, expected=None, actual=None):
        result.findings.append(EvalFinding(severity, check, message, expected, actual))

    if context.get("error"):
        add(ERROR, "parcel.exists", context["error"])
        return result

    parcel = context["parcel"]
    result.address = _format_address(parcel)
    data = context.get("report_data") or {}
    history = data.get("history") or []
    grouped = context.get("grouped") or []
    current_tax = _decimal(data.get("current_tax_amount"))
    parcel_total = _decimal(parcel.get("total_taxes"))

    result.metrics.update({
        "tax_year": parcel.get("tax_year"),
        "current_tax_amount": current_tax,
        "parcel_total_taxes": parcel_total,
        "agency_group_count": len(grouped),
        "summary_row_count": data.get("summary_row_count", 0),
        "history_count": len(history),
    })

    _check_bill_total(add, parcel_total, current_tax)
    _check_agency_allocation(add, result, context, data, grouped, current_tax)
    _check_history(add, result, parcel, context, data, history, current_tax)
    _check_comparison(add, result, context, data, current_tax)
    _check_yoy(add, context, data, history)
    _check_tax_shock(add, context)
    return result


def evaluate_tax_reports(parcel_numbers):
    return [evaluate_tax_report_parcel(parcel_number) for parcel_number in parcel_numbers]


def summarize_results(results):
    return {
        "parcel_count": len(results),
        "passed_count": sum(1 for result in results if result.passed),
        "error_count": sum(result.error_count for result in results),
        "warning_count": sum(result.warning_count for result in results),
    }


def render_text_report(results):
    summary = summarize_results(results)
    lines = [
        "TaxShift report data evals",
        f"Parcels: {summary['parcel_count']}  Passed: {summary['passed_count']}  Errors: {summary['error_count']}  Warnings: {summary['warning_count']}",
        "",
    ]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        label = f"{result.parcel_number} {result.address}".strip()
        lines.append(f"{status} {label}")
        for finding in result.findings:
            lines.append(f"  {finding.severity.upper()} {finding.check}: {finding.message}")
            if finding.expected is not None or finding.actual is not None:
                lines.append(f"    expected={_display(finding.expected)} actual={_display(finding.actual)}")
        if not result.findings:
            lines.append("  ok")
    return "\n".join(lines)


def render_markdown_report(results):
    summary = summarize_results(results)
    lines = [
        "# TaxShift Report Data Evals",
        "",
        f"- Parcels: {summary['parcel_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Errors: {summary['error_count']}",
        f"- Warnings: {summary['warning_count']}",
        "",
        "| Parcel | Status | Errors | Warnings |",
        "| --- | --- | ---: | ---: |",
    ]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        label = f"{result.parcel_number} {result.address}".strip()
        lines.append(f"| {label} | {status} | {result.error_count} | {result.warning_count} |")
    lines.append("")
    for result in results:
        if not result.findings:
            continue
        lines.append(f"## {result.parcel_number}")
        for finding in result.findings:
            lines.append(f"- **{finding.severity.upper()} {finding.check}:** {finding.message}")
    return "\n".join(lines)


def results_to_json(results):
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "summary": summarize_results(results),
        "results": results,
    }
    return json.dumps(payload, default=_json_default, indent=2)


def _check_bill_total(add, parcel_total, current_tax):
    if current_tax <= 0:
        add(ERROR, "bill.positive", "Displayed bill is missing or non-positive.", "> 0", current_tax)
    if not _close(parcel_total, current_tax, cents=Decimal("0.01")):
        add(
            ERROR,
            "bill.matches_authoritative_roll",
            "Displayed bill does not match skagit_parcels.total_taxes.",
            parcel_total,
            current_tax,
        )


def _check_agency_allocation(add, result, context, data, grouped, current_tax):
    summary_row_count = data.get("summary_row_count", 0)
    if current_tax > 0 and summary_row_count == 0:
        add(ERROR, "agency.summary_present", "No agency tax-summary rows are available for a positive bill.")
    if current_tax > 0 and not grouped:
        add(ERROR, "agency.groups_present", "No displayed agency groups are available for a positive bill.")

    group_total = sum(_decimal(group.get("total")) for group in grouped)
    result.metrics["agency_group_total"] = group_total
    if grouped and not _close(group_total, current_tax, cents=Decimal("0.02")):
        add(ERROR, "agency.groups_sum_to_bill", "Displayed agency groups do not sum to the displayed bill.", current_tax, group_total)

    pct_total = sum(_float(group.get("pct")) for group in grouped)
    result.metrics["agency_pct_total"] = round(pct_total, 3)
    if grouped and abs(pct_total - 100) > 0.7:
        add(WARNING, "agency.percent_total", "Agency percentages do not add up close to 100%.", "100 +/- 0.7", round(pct_total, 3))

    for index, group in enumerate(grouped):
        if _decimal(group.get("total")) < 0:
            add(ERROR, "agency.nonnegative", f"Agency group {index} has a negative amount.", ">= 0", group.get("total"))
        if not str(group.get("label") or "").strip():
            add(ERROR, "agency.label_present", f"Agency group {index} has no display label.")

    donut_groups = ((context.get("agency_donut") or {}).get("groups") or [])
    if len(donut_groups) != len(grouped):
        add(ERROR, "agency.donut_group_count", "Donut payload group count differs from displayed agency groups.", len(grouped), len(donut_groups))

    reconciliation = data.get("reconciliation") or {}
    target = _decimal(reconciliation.get("target_total"))
    source = _decimal(reconciliation.get("source_total"))
    difference = _decimal(reconciliation.get("difference"))
    if target > 0:
        drift_pct = abs(difference) / target * Decimal("100")
        result.metrics["agency_source_drift_pct"] = drift_pct
        if abs(difference) > Decimal("25") and drift_pct > Decimal("2"):
            add(
                WARNING,
                "agency.source_drift",
                "Levy-summary source total needed a large reconciliation adjustment.",
                "within $25 or 2%",
                {"source_total": source, "target_total": target, "difference": difference, "drift_pct": drift_pct},
            )


def _check_history(add, result, parcel, context, data, history, current_tax):
    if not history:
        add(WARNING, "history.present", "No history rows are available; YoY story and chart will be limited.")
        return

    years = []
    for row in history:
        try:
            years.append(int(row["tax_year"]))
        except (TypeError, ValueError, KeyError):
            add(ERROR, "history.year_valid", "A history row has an invalid tax_year.", actual=row)
    if years and years != sorted(years, reverse=True):
        add(ERROR, "history.sorted_desc", "History rows are not sorted newest first.", sorted(years, reverse=True), years)
    if len(years) != len(set(years)):
        add(ERROR, "history.unique_years", "History contains duplicate tax years.", actual=years)

    parcel_year = parcel.get("tax_year")
    if parcel_year and years and int(parcel_year) != years[0]:
        add(WARNING, "history.current_year_merged", "Current assessor roll year is not the first displayed history year.", parcel_year, years[0])
    if years and int(parcel_year or years[0]) == years[0] and not _close(_decimal(history[0].get("tax_amount")), current_tax, cents=Decimal("0.01")):
        add(ERROR, "history.current_tax_matches_bill", "Latest history row does not match the displayed bill.", current_tax, history[0].get("tax_amount"))

    story = context.get("history_story")
    if not story:
        add(ERROR, "history.story_present", "History rows exist but the chart/story payload is missing.")
        return
    points = story.get("tax_points") or []
    if len(points) != len(history):
        add(ERROR, "history.chart_point_count", "Chart point count does not match displayed history rows.", len(history), len(points))
    polyline_count = len(str(story.get("tax_polyline") or "").split())
    if polyline_count != len(points):
        add(ERROR, "history.polyline_point_count", "Chart polyline point count does not match chart points.", len(points), polyline_count)


def _check_comparison(add, result, context, data, current_tax):
    comparison = context.get("comparison") or {}
    your = comparison.get("your")
    use_taxable = bool(comparison.get("uses_taxable_value"))
    value = _decimal(data.get("current_taxable_value") if use_taxable else data.get("current_assessed_value"))
    result.metrics["comparison_basis"] = "taxable_value" if use_taxable else "assessed_value"
    if value <= 0:
        add(WARNING, "comparison.value_present", "Comparison rate cannot be evaluated because the value basis is missing.", "> 0", value)
        return
    expected_rate = float(current_tax / value * Decimal("1000"))
    if not your:
        add(ERROR, "comparison.your_rate_present", "Displayed comparison is missing the parcel's effective rate.", expected_rate, None)
        return
    actual_rate = _float(your.get("rate"))
    result.metrics["comparison_expected_rate"] = expected_rate
    result.metrics["comparison_actual_rate"] = actual_rate
    if abs(actual_rate - expected_rate) > 0.005:
        add(ERROR, "comparison.your_rate_math", "Displayed effective rate does not match bill divided by value basis.", expected_rate, actual_rate)


def _check_yoy(add, context, data, history):
    breakdowns = data.get("yoy_breakdowns") or []
    if len(history) >= 2 and not context.get("latest_change"):
        add(ERROR, "yoy.latest_change_present", "History has at least two years but latest change payload is missing.")
    if not breakdowns:
        return

    first = breakdowns[0]
    decomposed = _float(first.get("value_effect")) + _float(first.get("rate_effect"))
    delta = _float(first.get("delta_tax"))
    if abs(decomposed - delta) > 0.05:
        add(ERROR, "yoy.decomposition_sums", "Value effect plus rate effect does not reconstruct bill change.", delta, decomposed)

    latest = context.get("latest_change") or {}
    expected_reason = "assessed value changed" if abs(_float(first.get("value_effect"))) >= abs(_float(first.get("rate_effect"))) else "effective tax rate changed"
    actual_reason = latest.get("main_reason_label")
    if actual_reason and actual_reason != expected_reason:
        add(ERROR, "yoy.main_reason_matches_effects", "Main reason label does not match the larger YoY effect.", expected_reason, actual_reason)


def _check_tax_shock(add, context):
    tax_shock = context.get("tax_shock")
    if not tax_shock:
        return
    pct_keys = ["value_pct", "voter_pct", "other_pct", "main_driver_pct"]
    for key in pct_keys:
        pct = _float(tax_shock.get(key))
        if pct < 0 or pct > 100:
            add(ERROR, "tax_shock.percent_range", f"{key} is outside 0-100.", "0..100", pct)
    component_total = sum(_float(tax_shock.get(key)) for key in ["value_pct", "voter_pct", "other_pct"])
    if component_total > 101:
        add(WARNING, "tax_shock.component_percent_total", "Tax-shock component percentages add above 100%.", "<= 101", component_total)


def _format_address(parcel):
    street = " ".join(str(parcel.get(key) or "").strip() for key in ("situs_street_number", "situs_street_name")).strip()
    return ", ".join(part for part in [street, parcel.get("situs_city_state_zip")] if part)


def _decimal(value):
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _close(left, right, cents=Decimal("0.01")):
    return abs(_decimal(left) - _decimal(right)) <= cents


def _display(value):
    return json.dumps(_json_default(value), default=_json_default)


def _json_default(value):
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_default(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_default(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_default(item) for key, item in value.items()}
    return value
