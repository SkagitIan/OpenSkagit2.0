# Tax Delinquency Operations

## Staff Dashboard

The staff-only monitor is mounted at:

```text
/staff/tax-delinquency/
```

It requires `is_staff=True`. The default lead view excludes parcels with only one late installment. Those rows are still cached and visible through the `One late` tab.

Backfill and slow-check jobs only consider active residential parcels where `skagit_parcels.proptype = 'R'` and `assessed_value > 500`.

## Backfill On Railway

Create a Railway service that uses:

```text
railway.tax-delinquency-backfill.json
```

Default start command:

```bash
python manage.py migrate && python manage.py backfill_tax_statements --years 2023 2024 2025 2026 --delay ${TAX_DELINQUENCY_DELAY:-0.35}
```

Useful environment variables:

- `TAX_DELINQUENCY_DELAY`: seconds between county requests. Default `0.35`.
- `TAX_DELINQUENCY_TIMEOUT`: request timeout seconds. Default `20`.

For a small Railway smoke test:

```bash
python manage.py backfill_tax_statements --parcel P45283 --years 2025 2026 --delay 0
```

For a capped run:

```bash
python manage.py backfill_tax_statements --years 2023 2024 2025 2026 --limit 500 --delay 0.5
```

## Slow Checker On Railway

Create a separate Railway service that uses:

```text
railway.tax-delinquency-slow-check.json
```

Default start command:

```bash
python manage.py migrate && python manage.py slow_check_tax_statements --years 2023 2024 2025 2026 --cycle-hours ${TAX_DELINQUENCY_CYCLE_HOURS:-168} --start-after-hours ${TAX_DELINQUENCY_START_AFTER_HOURS:-168}
```

Defaults:

- waits one week before starting if enabled immediately.
- refreshes the full parcel/year universe over a seven-day cycle.
- skips statement rows fetched inside the current cycle.

Set `TAX_DELINQUENCY_START_AFTER_HOURS=0` if you enable the service after the backfill and want it to start immediately.

## Lead Logic

Rows are cached even when they are only mildly late. The dashboard promotes leads as follows:

- `clear`: no total due.
- `watch`: due amount exists but not yet delinquent by installment due date.
- `one_late`: one delinquent installment; retained but excluded from default actionable lead list.
- `behind`: two or more delinquent installments.
- `serious`: two or more delinquent installments plus a balance at least `$1,000` or a balance from two or more tax years ago.
- `severe`: two or more delinquent installments plus a balance at least `$5,000` or a balance from three or more tax years ago.

The actionable dashboard tab is intentionally limited to accounts with two or more delinquent installments.
