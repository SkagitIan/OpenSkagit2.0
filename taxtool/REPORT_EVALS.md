# TaxShift Report Data Evals

Run the report-data evals with:

```powershell
.\.venv\Scripts\python manage.py evaluate_taxshift_report_data
```

Useful variants:

```powershell
.\.venv\Scripts\python manage.py evaluate_taxshift_report_data --sample-size 50
.\.venv\Scripts\python manage.py evaluate_taxshift_report_data --recent 25
.\.venv\Scripts\python manage.py evaluate_taxshift_report_data --parcel P53931 --parcel P23134
.\.venv\Scripts\python manage.py evaluate_taxshift_report_data --sample-size 100 --format json --output taxshift-evals.json
.\.venv\Scripts\python manage.py evaluate_taxshift_report_data --sample-size 100 --fail-level warning
```

The command evaluates the same report payload used by the user-facing parcel page. It can run against explicit parcels, recently searched/opened parcels from `ParcelSearchCache`, or a deterministic active-parcel sample.

## What It Checks

- The displayed bill matches `skagit_parcels.total_taxes`.
- Displayed agency groups sum back to the bill after reconciliation.
- Agency percentages are coherent, non-negative, and labeled.
- Large source drift between levy summary totals and the authoritative bill is flagged as a warning.
- Current-year history is merged and sorted newest first.
- Chart point and polyline counts match the displayed history rows.
- Effective-rate comparison math matches bill divided by assessed or taxable value.
- Year-over-year value/rate decomposition reconstructs the displayed bill change.
- Tax-shock percentage fields stay in sane ranges.

Errors indicate the report is likely showing incorrect or incomplete data. Warnings indicate the displayed report can still be coherent, but the underlying sources deserve review.
