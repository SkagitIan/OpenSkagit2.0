# OpenSkagit Budget Agent

The `budgets` app turns official local-government budget PDFs into reviewed, page-cited public data, and lets citizens have a real, cross-document conversation about it. SAO FIT remains useful for historical reported actuals; it is not treated as the current adopted budget.

## Public behavior

- `/budgets/` shows jurisdiction/year controls, reviewed headline totals, an explorable fund/department/category/account breakdown table, source pages, a streaming chat thread, and sample questions.
- `/budgets/compare/` is a dedicated side-by-side comparison view across jurisdictions, with per-capita columns and cited cells, usable with zero JavaScript.
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

## Population data for per-capita comparisons

`BudgetJurisdiction` carries `population`, `population_source`, `population_source_year`, and `population_source_url` so the agent and the comparison view can frame large numbers per resident instead of only reciting them. `data/jurisdiction_population.json` is the source fixture (currently 2020 Decennial Census counts for the county and its incorporated places); load or refresh it with:

```powershell
python manage.py load_jurisdiction_population --dry-run
python manage.py load_jurisdiction_population
```

Every per-capita figure returned by `budget_compare_per_capita` cites the population source and vintage alongside the dollar figure. Refresh the fixture with newer OFM postcensal estimates as they become available and bump `source_year`.

## Full-text search and reading tools

`BudgetDocumentPage` text is searched with Postgres full-text search (`SearchVector`/`SearchQuery`/`SearchRank`/`SearchHeadline`, `websearch_to_tsquery` semantics so phrases in quotes and `-exclusions` work, with English stemming). Matches are filtered on the `@@` match operator rather than `rank > 0`, because Postgres's `ts_rank` returns a tiny nonzero epsilon (not exactly zero) even for non-matching rows.

- `budget_search_documents(jurisdiction, query, year)` searches one jurisdiction's document and returns page-numbered, ranked snippets.
- `budget_search_all_documents(query, year)` searches every published jurisdiction's document at once and groups ranked results by jurisdiction -- this is what makes cross-document questions like "what does Anacortes say about the water utility" or "who spends the most on police" possible without picking a jurisdiction first.
- `budget_read_pages(jurisdiction, start_page, end_page, year)` returns the full text of up to 5 consecutive pages (capped server-side) with page numbers and the official source URL, so the agent can search for a candidate page and then actually read it before summarizing or quoting -- the previous `search_budget_document` tool only ever returned ~600-character snippets, which was the ceiling on answer quality.

## Analytical tools

- Every `budget_get_breakdown` row carries `percent_of_side_total`, computed against the reviewed side total (not just the sum of the rows returned), so one number can always be anchored to "X% of the total."
- `budget_compare_per_capita(jurisdictions, year, side)` divides reviewed totals by population and cites the population source/vintage per jurisdiction; `per_capita` is `null` where population isn't on file rather than guessed.
- `calculate(expression)` safely evaluates a short arithmetic expression (numbers and `+ - * / // % **` only, parsed and walked with `ast` -- never `eval()` of arbitrary Python) so the agent does arithmetic on cited figures instead of doing it mentally and risking an uncited, possibly wrong number.

## Accuracy evals

`data/budget_evals_2026.json` contains source-backed known-answer cases covering exact values, breakdown labels and percent-of-total, per-capita comparisons, cross-document and single-document search, page reading, official PDF pages, and safe refusal for jurisdictions with no located source (Hamilton, Lyman) across multiple tools (`summary`, `search`, `per_capita`). Case `type` values: `summary`, `breakdown`, `percent_of_total`, `per_capita`, `search`, `search_all`, `read_pages`, `unavailable` (with an optional `check: summary|search|per_capita`).

```powershell
python manage.py eval_budgets
python manage.py eval_budgets --json
```

The optional live layer sends the same questions through the configured budget agent and requires the expected number, source URL, and page citation (cases without a `question` field, such as the search/read-pages cases, are deterministic-only):

```powershell
python manage.py eval_budgets --live-chat
python manage.py eval_budgets --live-chat --case county-general-fund-spending
```

## Conversation UI

The `/budgets/` chat is a real, threaded conversation, not a one-shot POST-and-reload form:

- JavaScript progressively enhances the existing `<form>`: it intercepts submit, appends the question to an on-page thread, and streams the answer back over Server-Sent Events (`POST /budgets/ask/stream/`) instead of reloading the page. With JavaScript disabled, the same form still posts to `/budgets/ask/` and renders a full-page answer -- every capability works without JS, just without streaming.
- While the agent works, lightweight activity status lines appear ("Searching the Burlington budget for 'water utility'...", "Reading Anacortes pages 11-11...") derived from the tool being called and its arguments.
- When a tool returns a table-shaped result (a breakdown, a comparison, a per-capita comparison, a trend, or search matches), it's rendered as a real HTML table inline in the chat with a source line underneath -- not prose-ified numbers.
- Follow-up suggestion chips are generated from the shape of the last structured result (e.g. a breakdown offers "show that as a table" / "what about per resident?"; a per-capita comparison offers "show the raw totals instead") and replace the static six sample questions once a conversation starts.
- Conversation continuity (`previous_response_id`) is tracked client-side and echoed back on each turn, rather than stored in the Django session: `StreamingHttpResponse` bodies are only actually consumed by the WSGI server *after* `SessionMiddleware` has already saved the session, so session writes made while streaming would silently be lost.

`budgets/agent.py` exposes both a synchronous entry point (`answer_budget_turn`, used by the non-JS form and `eval_budgets`) and a streaming one (`stream_budget_turn`, used by the SSE view). Both share the same tool set and instructions. The streaming path bridges the `openai-agents` SDK's async `Runner.run_streamed` to a plain synchronous generator via a background thread and a queue, so the existing sync Django/WSGI deployment (gunicorn) doesn't need an ASGI stack to stream.

Exceptions from a failed agent run are logged server-side with `logger.exception(...)` (full traceback, question, jurisdiction, year) and never shown to the citizen, who instead sees a generic "temporarily unavailable" message -- answer-quality failures are diagnosable from the logs without ever leaking internals to the page.

## Explorable tables without the chat

A citizen who ignores the chat entirely can still get full value from the page:

- The breakdown table (`static/budgets/budgets.js`) is client-side sortable by clicking any column header, has a text filter, shows the top 10 rows with a "Show all" toggle for the rest, and has a "Download CSV" button -- all client-side, no extra request, appropriate at the current data scale.
- A grouping toggle (fund / department / category / account) re-requests the page with `?group_by=...` -- a plain link, so it works with zero JavaScript.
- `/budgets/compare/` is a dedicated comparison view: pick any set of jurisdictions and a side (revenue/expenditure/fund balance), get a sortable, CSV-exportable table with total and per-capita columns. It's a plain `GET` form, so it's bookmarkable and works without JS too.
- Every amount with a page citation links to `{official PDF URL}#page=N`.

## Read-only tools

The same service layer powers the dedicated web agent, general Ask Agent, and authenticated MCP. The budget chat agent (`budgets/agent.py`) has the full set below; MCP and the general Ask Agent (`openskagit_tools`) currently expose only the original six (population/search/analytical tools are additive and not yet mirrored there):

- `budget_list_jurisdictions`
- `budget_get_summary`
- `budget_get_breakdown` (rows include `percent_of_side_total`)
- `budget_get_trend`
- `budget_compare_jurisdictions`
- `budget_compare_per_capita` *(budget chat agent only)*
- `budget_search_documents` (Postgres full-text search)
- `budget_search_all_documents` *(budget chat agent only)*
- `budget_read_pages` *(budget chat agent only)*
- `calculate` *(budget chat agent only)*

Tool results identify jurisdiction, fiscal year, document status, official URL, and page evidence where applicable. The public agent never receives import controls or unrestricted access to draft tables.

## Verification

```powershell
python manage.py makemigrations budgets --check --dry-run
python manage.py check
python manage.py test budgets.tests openskagit_tools.tests tests.test_ask_agent_sql_safety
python manage.py eval_budgets
```
