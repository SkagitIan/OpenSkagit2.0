"""HTML rendering for the baseline ratio-study report."""

from __future__ import annotations

import html as html_module

METRIC_COLUMNS = [
    "sale_count",
    "sample_band",
    "median_ratio",
    "mean_ratio",
    "weighted_mean_ratio",
    "cod",
    "prd",
    "prb",
    "median_ape",
    "mean_ape",
    "rmse",
    "pct_within_10",
    "pct_within_15",
    "pct_within_20",
]


def _esc(value) -> str:
    return html_module.escape("" if value is None else str(value))


def _fmt(value, key: str = "") -> str:
    if value is None or (isinstance(value, float) and (value != value)):
        return ""
    if key in {"cod", "mean_ape", "median_ape", "pct_within_10", "pct_within_15", "pct_within_20"}:
        return f"{value:.1f}%"
    if key in {"median_ratio", "mean_ratio", "weighted_mean_ratio", "prd", "prb"}:
        return f"{value:.4f}"
    if key == "rmse":
        return f"${value:,.0f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "<p><em>No rows.</em></p>"
    head = "".join(f"<th>{_esc(col)}</th>" for col in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{_esc(_fmt(row.get(col), col))}</td>" for col in columns)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_ratio_study_html(
    *,
    model_comparison: list[dict],
    countywide: dict[str, dict],
    group_tables: dict[str, list[dict]],
    exclusion_summary: list[dict],
    temporal_leakage_warning: str,
    prb_formula_note: str,
    top_misses: dict[str, dict],
    notes: list[str],
    window_note: str = "",
) -> str:
    def esc(value) -> str:
        return html_module.escape(str(value))

    countywide_rows = []
    for model_name, metrics in countywide.items():
        row = {"model": model_name, **metrics}
        countywide_rows.append(row)

    group_sections = []
    for group_col, rows in group_tables.items():
        group_sections.append(
            f"<h3>By {esc(group_col)}</h3>{_table(rows, ['group'] + METRIC_COLUMNS)}"
        )

    miss_sections = []
    for model_name, misses in top_misses.items():
        miss_sections.append(f"<h3>{esc(model_name)} -- most underpredicted</h3>")
        miss_sections.append(_table(misses["underpredicted"], ["saleid", "parcel_number", "sale_date", "sale_price", "predicted", "ratio"]))
        miss_sections.append(f"<h3>{esc(model_name)} -- most overpredicted</h3>")
        miss_sections.append(_table(misses["overpredicted"], ["saleid", "parcel_number", "sale_date", "sale_price", "predicted", "ratio"]))

    notes_html = "".join(f"<li>{esc(note)}</li>" for note in notes)

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>SFR Baseline Ratio Study</title>
<style>
body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 2rem auto; max-width: 1000px; color: #1a1a1a; }}
h1 {{ font-size: 1.6rem; }}
h2 {{ font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
h3 {{ font-size: 1rem; margin-top: 1.2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.2rem; font-size: 0.8rem; }}
th, td {{ border: 1px solid #ddd; padding: 4px 7px; text-align: left; }}
th {{ background: #f4f4f4; }}
.warning {{ background: #fff3cd; border: 1px solid #ffe69c; padding: 12px 16px; border-radius: 6px; }}
.note {{ background: #e7f1ff; border: 1px solid #b6d4fe; padding: 12px 16px; border-radius: 6px; font-size: 0.85rem; }}
</style></head>
<body>
<h1>SFR Baseline Ratio Study</h1>
<div class="warning"><strong>Temporal leakage warning:</strong> {esc(temporal_leakage_warning)}</div>
<p class="note">{esc(prb_formula_note)}</p>
<p class="note"><strong>Study population:</strong> {esc(window_note)}. Comparing current assessed values/model
predictions against sale prices from many decades ago captures market appreciation, not model quality -- on this
data, assessed/sale-price ratios run 40x+ for 1960s sales and only settle near 1.0 in the last few years. See
notes below.</p>
<p><strong>This is a baseline report only. No IAAO compliance claim is made.</strong></p>

<h2>Model comparison (test set, 20% holdout, seed=42)</h2>
{_table(countywide_rows, ["model"] + METRIC_COLUMNS)}

<h2>Countywide test-set results</h2>
{_table(countywide_rows, ["model"] + METRIC_COLUMNS)}

<h2>Group results</h2>
{"".join(group_sections)}

<h2>Exclusion summary</h2>
{_table(exclusion_summary, ["value", "count"])}

<h2>Top under/over-predicted sales</h2>
{"".join(miss_sections)}

<h2>Notes for next modeling iteration</h2>
<ul>{notes_html}</ul>

</body></html>
"""
