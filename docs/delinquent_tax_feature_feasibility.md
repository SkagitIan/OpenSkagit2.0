# Delinquent Tax Feature Feasibility

## Summary

OpenSkagit can likely support a small public delinquent-tax account feature, but the provided HAR does not prove a countywide delinquent-account export or bulk API. It does reveal public Skagit County property-search endpoints that return tax statement HTML wrapped in JSON. Those statements include parcel ID, account/Xref ID, tax year, installment payment text, total due, amount paid, levy code, levy rate, taxable value, general tax, special assessments/fees, and official payment links.

The cleanest v1 is parcel/account lookup on demand, joined to OpenSkagit's existing parcel database by parcel number and account number, with cached normalized statement rows. A full delinquent roll should wait until we find an official export, delinquent list, or confirm acceptable usage with the county source.

## Current OpenSkagit Data

OpenSkagit is a Django app with these relevant apps and data surfaces:

- `core`: unmanaged models for assessor, parcel, GIS, levy, tax summary, parcel history, and land ledger tables.
- `taxtool`: parcel search, tax-bill explanation, levy composition, and parcel-history queries.
- `assessor_sync`: assessor source synchronization metadata.
- `land_ledger`: parcel-level land productivity outputs.

Relevant current tables/models:

- `skagit_parcels`: primary parcel table. Important fields include `parcel_number`, `account_number`, situs address fields, owner fields, `legal_description`, `levy_code`, `tax_year`, `total_taxes`, `general_taxes`, `taxable_value`, `assessed_value`, and `inactive_date`.
- `assessor_rollup`: broader imported assessor rollup, including `parcel_number`, `account_number`, owner/address/legal/tax/value fields.
- `gis_skagit_parcels`: parcel geometry and GIS attributes keyed by `parcel_id`.
- `skagit_parcel_history`: per-parcel historical assessed value and tax amount by tax year. It is populated from `https://www.skagitcounty.net/search/propertym/Webservice.asmx/fillPage` with `ResultType: history`.
- `v_parcel_tax_summary` and `v_parcel_tax_detail`: levy/tax allocation views, not payment-status or delinquency views.
- `skagit_levy_composition`, `skagit_levy_crosswalk`, and `skagit_levy_history`: levy rate and agency data.

Observed live database checks:

- `skagit_parcels` has parcel/account/tax fields but no `due`, `paid`, `balance`, `delinquent`, or payment status columns.
- For HAR parcel `P45283`, `skagit_parcels.account_number` is `351013-2-001-1815`, matching the HAR `Xref ID`.
- `skagit_parcels.tax_year` for `P45283` is `2026`, and `total_taxes` is `414.16`, matching the current tax statement total in the HAR.
- `skagit_parcel_history` stores historical tax amounts but rounds/normalizes some cents and does not store paid/due status.

## Useful HAR Endpoints

The HAR contains 18 entries, mostly public property-search calls. Useful endpoints:

| Purpose | Method | URL | Request body | Response |
| --- | --- | --- | --- | --- |
| Property details | POST | `https://www.skagitcounty.net/Search/Property/Webservice.asmx/fillPage` | `{ 'sValue': 'P45283','ResultType': 'Details' }` | `application/json`; `d` contains HTML |
| Property history | POST | same `fillPage` endpoint | `{ 'sValue': 'P45283','ResultType': 'History' }` | JSON-wrapped HTML table of value/tax history |
| Current tax statement | POST | same `fillPage` endpoint | `{ 'sValue': 'P45283','ResultType': 'Taxes' }` | JSON-wrapped HTML tax statement |
| Prior-year tax statement | POST | `https://www.skagitcounty.net/Search/Property/Webservice.asmx/getTaxHistoryDetail` | `{ 'sValue': 'P45283','sYear': '2025' }` | JSON-wrapped HTML tax statement |
| Prior-year tax statement | POST | same `getTaxHistoryDetail` endpoint | `{ 'sValue': 'P45283','sYear': '2024' }` | JSON-wrapped HTML tax statement |
| Prior-year tax statement | POST | same `getTaxHistoryDetail` endpoint | `{ 'sValue': 'P45283','sYear': '2023' }` | JSON-wrapped HTML tax statement |

The HAR did not show required authentication, private credentials, or special cookies for these calls. Code should still omit captured cookies and use only public request bodies and ordinary headers such as `Content-Type: application/json; charset=utf-8`.

## Available Tax Statement Fields

From `ResultType: Taxes` and `getTaxHistoryDetail`, the tax statement HTML exposes:

- `parcel_number`: displayed as `Parcel ID: P45283`.
- `tax_account_number`: displayed as `Xref ID: 351013-2-001-1815`; this matches OpenSkagit `skagit_parcels.account_number`.
- `tax_year`: statement heading, for example `2026 Real Estate Tax Statement`.
- `owner_name` and mailing address.
- `situs_address`.
- abbreviated legal description.
- available statement years in the year picker.
- installment labels, due dates, and paid/due amounts, for example first installment due April 30 and second installment due October 31.
- tax district line items with `rate` and `amount`.
- special assessment/fee line items.
- summary fields: `levy_code`, `levy_rate`, land market value, building market value, total market value, taxable value, general tax, special assessment/fees, total due, and amount paid.
- official payment link text and treasurer source context.

The captured example is not delinquent. It shows total due as zero and amount paid as the full statement amount for prior years/current captured statement. The payload structure strongly suggests delinquency can be inferred when `Total Due` is greater than zero or installment rows indicate unpaid/past-due amounts, but this should be verified with at least one known delinquent parcel before public launch.

## Missing Fields

Current OpenSkagit data does not appear to store:

- current balance due.
- amount paid.
- first/second installment paid or unpaid status.
- delinquency flag.
- penalties and interest as separate fields.
- payment dates.
- source fetch timestamp for tax statement balance data.
- raw official tax-statement payload for audit/debugging.

The HAR also does not clearly expose:

- a countywide delinquent account list.
- bulk export endpoint.
- separate penalty/interest fields.
- explicit legal delinquency status flag.
- rate-limit policy or terms of use.
- guaranteed freshness timestamp inside the returned HTML.

## Join Keys

Recommended joins:

- Primary: HAR `Parcel ID` -> `skagit_parcels.parcel_number`.
- Secondary: HAR `Xref ID` -> `skagit_parcels.account_number`.
- Address fallback: HAR site address -> `situs_street_number`, `situs_street_name`, and `situs_city_state_zip`.
- Legal fallback: abbreviated legal description is useful for display confirmation but should not be a primary join.
- Year: HAR statement year -> normalized delinquent-tax `tax_year`; existing `skagit_parcels.tax_year` stores the current roll year, and `skagit_parcel_history.tax_year` stores historical tax years.

The HAR source is account/parcel/year based. Payment state is embedded in a per-year tax statement rather than in OpenSkagit's current parcel tax allocation views.

## Risks

- Freshness: the webservice appears live and official, but the HAR does not expose a source timestamp. OpenSkagit should display `source_fetched_at`.
- Legality/terms: public endpoint access appears unauthenticated, but a full scrape should not proceed without confirming acceptable public-record reuse, robots/terms posture, and county expectations.
- Fragility: responses are HTML wrapped in JSON, so parser selectors may break if the county redesigns the page.
- Incomplete delinquency evidence: the HAR example is paid, not delinquent. Need a known delinquent parcel/account to confirm exact unpaid labels, penalties, and total-due behavior.
- Rate limits: no rate-limit headers or bulk API were discovered. Use on-demand lookup and caching, not aggressive crawling.
- Privacy/user expectation: owner mailing address appears in the official public page, but a citizen-facing feature should minimize owner details unless necessary.

## Simplest Defensible V1

Build a small lookup feature:

- Search by parcel number or situs address using existing `skagit_parcels` search.
- Fetch or read cached official tax statement data for the parcel.
- Show whether the parcel/account appears to have a positive `total_due`.
- Show delinquent or unpaid tax year(s), amount due when available, amount paid, and `source_fetched_at`.
- Link to the official Skagit County property/tax source.
- Include a clear disclaimer: OpenSkagit is informational only; Skagit County Treasurer/Assessor records control.

Do not build a countywide delinquency map or list until an official bulk source is found or approved.

## Recommended Minimal Data Model

Use one simple cache table before any heavier normalization:

```python
class DelinquentTaxAccount(models.Model):
    parcel_number = models.TextField(db_index=True)
    tax_account_number = models.TextField(blank=True, null=True, db_index=True)
    tax_year = models.IntegerField(db_index=True)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    penalties_interest = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    status = models.TextField(blank=True, null=True)
    source_url = models.TextField()
    source_fetched_at = models.DateTimeField()
    raw_data = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parcel_number", "tax_year"],
                name="uniq_delinquent_tax_account_parcel_year",
            )
        ]
```

`status` can start as `paid`, `unpaid`, `partially_paid`, or `unknown`, derived from total due and amount paid. Keep installment detail in `raw_data` until a real UI needs it.

## Proof Of Concept

A small management command is appropriate because the HAR source is clearly usable for one known parcel/year and does not require private credentials. The PoC should:

- POST one parcel to `fillPage` with `ResultType: Taxes`, or POST parcel/year to `getTaxHistoryDetail`.
- Parse the JSON `d` HTML with BeautifulSoup.
- Print normalized fields only.
- Avoid cookies and session headers.
- Avoid full scraping and scheduled jobs.

## Recommended Next Codex Task

Find or obtain one known delinquent Skagit parcel/account, run the PoC command against it, confirm how unpaid installments, penalties/interest, and `Total Due` appear, then add the minimal cache model and a parcel detail read-only display.
