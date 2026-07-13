"""
Report content for the SFR sales modeling dataset build.

Keeps "what to compute" (plain pandas, testable without Django/HTML) separate
from "how to render it" (HTML/Markdown strings), matching the split already
used in ``pipeline.py``.
"""

from __future__ import annotations

import html as html_module

TEMPORAL_LEAKAGE_WARNING = (
    "This prototype uses current parcel characteristics joined to historical sales. "
    "It may contain temporal leakage where a property changed after the sale date. "
    "Future versions should reconstruct sale-date characteristics or exclude sales "
    "with known post-sale physical changes."
)

DATASET_VERSION_LABEL = "prototype_current_characteristics"


def _describe(series) -> dict:
    described = series.dropna()
    if described.empty:
        return {"count": 0}
    quantiles = described.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    return {
        "count": int(described.count()),
        "min": float(described.min()),
        "p10": float(quantiles.loc[0.1]),
        "p25": float(quantiles.loc[0.25]),
        "median": float(quantiles.loc[0.5]),
        "p75": float(quantiles.loc[0.75]),
        "p90": float(quantiles.loc[0.9]),
        "max": float(described.max()),
        "mean": float(described.mean()),
    }


def _value_counts(series, top: int = 25) -> list[dict]:
    counts = series.fillna("(missing)").value_counts().head(top)
    return [{"value": str(value), "count": int(count)} for value, count in counts.items()]


def compute_dataset_summary(joined_df, included_df, excluded_df) -> dict:
    """All the numbers the dataset summary report needs, computed once."""
    total_loaded = len(joined_df)
    retained = len(included_df)

    summary = {
        "dataset_version": DATASET_VERSION_LABEL,
        "temporal_leakage_warning": TEMPORAL_LEAKAGE_WARNING,
        "total_sales_loaded": total_loaded,
        "retained_sfr_sales": retained,
        "retained_pct": (retained / total_loaded * 100) if total_loaded else 0.0,
        "excluded_by_reason": _value_counts(excluded_df["exclusion_reason"], top=50),
        "sales_by_year": sorted(
            _value_counts(included_df["sale_date"].astype(str).str.slice(0, 4), top=100),
            key=lambda row: row["value"],
        ),
        "sales_by_deed_type": _value_counts(included_df["deed_type"]),
        "sales_by_sale_type_all": _value_counts(joined_df["sale_type"]),
        "sales_by_neighborhood": _value_counts(included_df["neighborhood_code"], top=40),
        "sales_by_city": _value_counts(included_df["city_name"], top=20),
        "missing_geo_feature_count": int((included_df["feature_status"].fillna("") != "ok").sum()),
        "missing_living_area_count": int(joined_df["primary_living_area"].isna().sum()),
        "missing_year_built_count": int(
            (joined_df["primary_actual_year_built"].isna() & joined_df["primary_effective_year_built"].isna()).sum()
        ),
        "missing_land_data_count": int(joined_df["land_segment_count"].isna().sum()),
        "missing_improvement_data_count": int(joined_df["improvement_row_count"].isna().sum()),
        "sale_price_distribution": _describe(included_df["sale_price"]),
        "living_area_distribution": _describe(included_df["primary_living_area"]),
        "land_size_distribution": _describe(included_df["total_land_acres"]),
    }

    priced = included_df[included_df["primary_living_area"] > 0].copy()
    priced["price_per_sqft"] = priced["sale_price"] / priced["primary_living_area"]
    suspicious = priced.nsmallest(10, "price_per_sqft").to_dict("records") + priced.nlargest(10, "price_per_sqft").to_dict(
        "records"
    )
    summary["top_suspicious_rows"] = [
        {
            "saleid": row["saleid"],
            "parcel_number": row["parcel_number"],
            "sale_date": str(row["sale_date"]),
            "sale_price": row["sale_price"],
            "primary_living_area": row["primary_living_area"],
            "price_per_sqft": round(row["price_per_sqft"], 2),
        }
        for row in suspicious
    ]
    return summary


def render_dataset_summary_html(summary: dict) -> str:
    def esc(value) -> str:
        return html_module.escape(str(value))

    def table(rows: list[dict], columns: list[str]) -> str:
        if not rows:
            return "<p><em>No rows.</em></p>"
        head = "".join(f"<th>{esc(col)}</th>" for col in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(row.get(col, ''))}</td>" for col in columns) + "</tr>" for row in rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    def dist_table(dist: dict) -> str:
        if dist.get("count", 0) == 0:
            return "<p><em>No data.</em></p>"
        rows = [
            {"stat": key, "value": f"{dist[key]:,.1f}" if key != "count" else f"{dist[key]:,}"}
            for key in ["count", "min", "p10", "p25", "median", "p75", "p90", "max", "mean"]
        ]
        return table(rows, ["stat", "value"])

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>SFR Sales Dataset Summary</title>
<style>
body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 2rem auto; max-width: 900px; color: #1a1a1a; }}
h1 {{ font-size: 1.6rem; }}
h2 {{ font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; font-size: 0.85rem; }}
th, td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: left; }}
th {{ background: #f4f4f4; }}
.warning {{ background: #fff3cd; border: 1px solid #ffe69c; padding: 12px 16px; border-radius: 6px; }}
.badge {{ display: inline-block; background: #e2e3e5; padding: 2px 8px; border-radius: 4px; font-family: monospace; font-size: 0.8rem; }}
</style></head>
<body>
<h1>SFR Sales Dataset Summary</h1>
<p>Dataset version: <span class="badge">{esc(summary['dataset_version'])}</span></p>
<div class="warning"><strong>Temporal leakage warning:</strong> {esc(summary['temporal_leakage_warning'])}</div>

<h2>Overview</h2>
{table([
    {"metric": "Total sales loaded (post-dedup)", "value": f"{summary['total_sales_loaded']:,}"},
    {"metric": "Retained SFR sales", "value": f"{summary['retained_sfr_sales']:,}"},
    {"metric": "Retained %", "value": f"{summary['retained_pct']:.1f}%"},
    {"metric": "Missing geo feature (retained)", "value": f"{summary['missing_geo_feature_count']:,}"},
    {"metric": "Missing living area (all candidates)", "value": f"{summary['missing_living_area_count']:,}"},
    {"metric": "Missing year built (all candidates)", "value": f"{summary['missing_year_built_count']:,}"},
    {"metric": "Missing land data (all candidates)", "value": f"{summary['missing_land_data_count']:,}"},
    {"metric": "Missing improvement data (all candidates)", "value": f"{summary['missing_improvement_data_count']:,}"},
], ["metric", "value"])}

<h2>Excluded sales by reason</h2>
{table(summary['excluded_by_reason'], ["value", "count"])}

<h2>Retained sales by year</h2>
{table(summary['sales_by_year'], ["value", "count"])}

<h2>Retained sales by deed type</h2>
{table(summary['sales_by_deed_type'], ["value", "count"])}

<h2>All candidate sales by sale_type (before exclusion)</h2>
{table(summary['sales_by_sale_type_all'], ["value", "count"])}

<h2>Retained sales by neighborhood</h2>
{table(summary['sales_by_neighborhood'], ["value", "count"])}

<h2>Retained sales by city</h2>
{table(summary['sales_by_city'], ["value", "count"])}

<h2>Sale price distribution (retained)</h2>
{dist_table(summary['sale_price_distribution'])}

<h2>Living area distribution (retained)</h2>
{dist_table(summary['living_area_distribution'])}

<h2>Land size distribution, acres (retained)</h2>
{dist_table(summary['land_size_distribution'])}

<h2>Top suspicious rows (lowest/highest price per sqft)</h2>
{table(summary['top_suspicious_rows'], ["saleid", "parcel_number", "sale_date", "sale_price", "primary_living_area", "price_per_sqft"])}

</body></html>
"""


def render_dataset_summary_md(summary: dict) -> str:
    lines = [
        "# SFR Sales Dataset Summary",
        "",
        f"Dataset version: `{summary['dataset_version']}`",
        "",
        f"> **Temporal leakage warning:** {summary['temporal_leakage_warning']}",
        "",
        "## Overview",
        "",
        f"- Total sales loaded (post-dedup): {summary['total_sales_loaded']:,}",
        f"- Retained SFR sales: {summary['retained_sfr_sales']:,} ({summary['retained_pct']:.1f}%)",
        f"- Missing geo feature (retained): {summary['missing_geo_feature_count']:,}",
        f"- Missing living area (all candidates): {summary['missing_living_area_count']:,}",
        f"- Missing year built (all candidates): {summary['missing_year_built_count']:,}",
        f"- Missing land data (all candidates): {summary['missing_land_data_count']:,}",
        f"- Missing improvement data (all candidates): {summary['missing_improvement_data_count']:,}",
        "",
        "## Excluded sales by reason",
        "",
    ]
    for row in summary["excluded_by_reason"]:
        lines.append(f"- {row['value']}: {row['count']:,}")
    lines += ["", "## Retained sales by year", ""]
    for row in summary["sales_by_year"]:
        lines.append(f"- {row['value']}: {row['count']:,}")
    lines += ["", "## Sale price distribution (retained)", ""]
    dist = summary["sale_price_distribution"]
    if dist.get("count", 0):
        lines.append(
            f"- n={dist['count']:,}, min=${dist['min']:,.0f}, median=${dist['median']:,.0f}, "
            f"mean=${dist['mean']:,.0f}, max=${dist['max']:,.0f}"
        )
    return "\n".join(lines) + "\n"
