# OpenSkagit Budget Agent

The `budgets` app turns official local-government budget PDFs into reviewed, page-cited public data. SAO FIT remains useful for historical reported actuals; it is not treated as the current adopted budget.

## Public behavior

- `/budgets/` shows jurisdiction/year controls, reviewed headline totals, the best available fund/category breakdown, source pages, concise chat, and sample questions.
- Proposed, preliminary, adopted, and amended documents are stored separately. The latest reviewed adopted or amended document is the preferred public default.
- Draft imports are never returned by public services, the budget agent, or MCP.
- Revenue less expenditure is labeled as a difference, not automatically as a surplus or fund-balance change.

Initial jurisdiction coverage is Skagit County plus Anacortes, Burlington, Concrete, Hamilton, La Conner, Lyman, Mount Vernon, and Sedro-Woolley. `data/budget_sources.json` contains the first verified source records.

## Import and review

Import an official PDF into draft state:

```powershell
python manage.py import_budget_pdf --jurisdiction anacortes --year 2026 --status adopted --title "City of Anacortes 2026 Final Adopted Budget" --url "OFFICIAL_PDF_URL"
```

The importer saves the source hash, archived file, page text, page numbers, conservative amount candidates, warnings, and an import-run audit record. Pages without text are flagged for OCR. Large books should run as a Railway job or management command, never inside a web request.

## Cloudflare R2 archive

Budget PDFs use a dedicated Django storage alias. Local development defaults to `MEDIA_ROOT`; production uses the existing private Cloudflare R2 bucket when `BUDGET_PDF_STORAGE=r2` is set. Static files and any future non-budget uploads remain on their own storage aliases.

Required Railway variables are `BUDGET_PDF_STORAGE=r2`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and either `R2_BUDGET_BUCKET` or the existing `R2_BUCKET`. Object keys are content-addressed as `budgets/{jurisdiction}/{year}/{status}/{sha256}.pdf`. R2 URLs remain private and signed; citizens continue to receive the official jurisdiction URL.

Verify credentials without exposing them:

```powershell
python manage.py check_budget_r2
python manage.py check_budget_r2 --write-test
```

The write test creates one tiny object under `budgets/_healthchecks/`, verifies it, and immediately deletes it. The official Burlington book requires the default 200 MB import allowance. Override `BUDGET_MAX_PDF_MB` and `BUDGET_PDF_DOWNLOAD_TIMEOUT_SECONDS` only when an official source requires it.

Normalize reviewed rows with CSV:

```powershell
python manage.py import_budget_lines --document 1 --csv reviewed-lines.csv --replace
```

Required columns are `side` and `amount`. Optional columns are:

```text
amount_kind,page_number,fiscal_year,fund_code,fund_name,
department_code,department_name,account_code,account_name,category_name,
scope,is_total,display_order,source_note,raw_label
```

Valid sides are `revenue`, `expenditure`, and `fund_balance`. Page numbers must refer to the official PDF. Publish only after reconciliation:

```powershell
python manage.py publish_budget_document --document 1 --current
```

The publish command refuses documents without extracted pages, reviewed totals, or valid page citations. Raw extraction candidates can never satisfy the gate. Django admin provides inspection of documents, pages, candidates, reviewed rows, and import runs.

Import every primary verified source from the catalog as an unpublished draft:

```powershell
python manage.py import_budget_catalog --dry-run
python manage.py import_budget_catalog
```

Use `--jurisdiction anacortes` to limit a run and `--include-supporting` to archive Concrete's adoption/workshop packets. Current municipal coverage and missing-source blockers are recorded in `docs/budget-coverage.md`.


## Reviewed 2026 release

`data/budget_reviewed_2026.json` is the versioned human-review ledger for the seven available municipal-scope documents. It is bound to each imported PDF by SHA-256, reconciles complete breakdowns to cited totals, records permitted source rounding, and preserves review notes such as Concrete's conflicting printed total.

Validate without writing, load as a draft, or publish atomically:

```powershell
python manage.py load_reviewed_budgets --dry-run
python manage.py load_reviewed_budgets
python manage.py load_reviewed_budgets --publish
```

Published services read only rows where `reviewed=True`; top-level totals are separated from breakdown rows so they cannot be double-counted.

## Accuracy evals

`data/budget_evals_2026.json` contains source-backed known-answer cases. The default suite checks exact values, breakdown labels, official PDF pages, and safe refusal for missing sources:

```powershell
python manage.py eval_budgets
python manage.py eval_budgets --json
```

The optional live layer sends the same questions through the configured budget agent and requires the expected number, source URL, and page citation:

```powershell
python manage.py eval_budgets --live-chat
python manage.py eval_budgets --live-chat --case county-general-fund-spending
```
## Read-only tools

The same service layer powers the dedicated web agent, general Ask Agent, and authenticated MCP:

- `budget_list_jurisdictions`
- `budget_get_summary`
- `budget_get_breakdown`
- `budget_get_trend`
- `budget_compare_jurisdictions`
- `budget_search_documents`

Tool results identify jurisdiction, fiscal year, document status, official URL, and page evidence where applicable. The public agent never receives import controls or unrestricted access to draft tables.

## Verification

```powershell
python manage.py makemigrations budgets --check --dry-run
python manage.py check
python manage.py test budgets.tests openskagit_tools.tests tests.test_ask_agent_sql_safety
python manage.py eval_budgets
```
