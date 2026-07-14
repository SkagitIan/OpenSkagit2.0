"""HTML rendering for the per-neighborhood compliance loop summary report."""

from __future__ import annotations

import html as html_module

STATUS_COLORS = {
    "compliant": "#1a7f37",
    "provisional": "#9a6700",
    "dropped": "#cf222e",
}


def _esc(value) -> str:
    return html_module.escape("" if value is None else str(value))


def _fmt(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    if isinstance(value, float):
        return f"{value:,.3f}"
    return str(value)


def _status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#666")
    return f'<span style="color:{color}; font-weight:600;">{_esc(status)}</span>'


def render_compliance_loop_summary_html(segment_results: list[dict], window_note: str, ai_model: str) -> str:
    rows = []
    for result in sorted(segment_results, key=lambda r: (-r["sample_count"])):
        metrics = result.get("metrics") or {}
        rows.append(
            "<tr>"
            f"<td>{_esc(result['segment_value'])}</td>"
            f"<td>{_esc(result['sample_count'])}</td>"
            f"<td>{_fmt(metrics.get('median_ratio'))}</td>"
            f"<td>{_fmt(metrics.get('cod'))}</td>"
            f"<td>{_fmt(metrics.get('prd'))}</td>"
            f"<td>{_fmt(metrics.get('prb'))}</td>"
            f"<td>{_status_badge(result['status'])}</td>"
            f"<td>{_esc(result['recommendation'])}</td>"
            "</tr>"
        )

    counts = {status: sum(1 for r in segment_results if r["status"] == status) for status in ("compliant", "provisional", "dropped")}

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Neighborhood Compliance Loop Summary</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem;">
<h1>Neighborhood Compliance Loop Summary</h1>
<p>Study population: {_esc(window_note)}. AI-guided rounds use <code>{_esc(ai_model)}</code>.
Not an IAAO compliance certification -- "compliant"/"provisional" mean the fitted model's COD/PRD/PRB
cleared the commonly-cited IAAO reference ranges for the given sample size.</p>
<p><strong>{counts['compliant']}</strong> compliant, <strong>{counts['provisional']}</strong> provisional,
<strong>{counts['dropped']}</strong> dropped, out of {len(segment_results)} neighborhoods attempted.</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%;">
<thead><tr>
<th>Neighborhood</th><th>n</th><th>Median ratio</th><th>COD</th><th>PRD</th><th>PRB</th><th>Status</th><th>Recommendation</th>
</tr></thead>
<tbody>
{"".join(rows) if rows else '<tr><td colspan="8"><em>No segments attempted.</em></td></tr>'}
</tbody>
</table>
</body></html>
"""
