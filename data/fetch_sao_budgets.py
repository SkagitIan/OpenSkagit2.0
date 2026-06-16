"""
fetch_sao_budgets.py
====================
Fetches financial data from the SAO FIT public API for every MCAG in
skagit_agencies.json and updates the budget field in-place.

Also fixes sao_fit_url to use the correct portal URL format.

API base: https://portal.sao.wa.gov/FIT/api  (public OData, no auth)
Snapshot 32 = current annual filing snapshot (2024 data).
"""

import json
import time
import urllib.parse
from pathlib import Path
import urllib.request

BASE    = "https://portal.sao.wa.gov/FIT/api"
SNAP    = 32          # current snapshot ID from HAR
TARGET_YEAR = 2024    # prefer this year, fall back to most recent available

AGENCIES_JSON = Path("data/skagit_agencies.json")


def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ERROR fetching {url[:80]}: {e}")
                return None
            time.sleep(2)


def odata_url(path, filter_str):
    return f"{BASE}/{path}?$filter={urllib.parse.quote(filter_str)}"


def get_account_descriptors():
    """Fetch BARS account id→name mapping from Snapshots detail."""
    print("Fetching account descriptors...")
    data = get(f"{BASE}/Snapshots({SNAP})?$expand=Detail")
    if not data:
        return {}
    descriptors = data.get("detail", {}).get("accountDescriptors", [])
    mapping = {d["id"]: d["name"] for d in descriptors}
    print(f"  {len(mapping)} account descriptors loaded")
    return mapping


def get_latest_year(mcag):
    """Return the most recent year with filed data for this MCAG."""
    f = f"mcag eq '{mcag}' and year le {TARGET_YEAR}"
    url = odata_url(f"Snapshots({SNAP})/FilingStatuses", f) + "&$orderby=year%20desc"
    data = get(url)
    if not data:
        return None
    rows = data.get("value", data) if isinstance(data, dict) else data
    # Filter to years that actually have data (not noDataAvailable, not missing)
    filed = [r for r in rows if r.get("dateSubmitted") and not r.get("noDataAvailable")]
    if not filed:
        return None
    return max(r["year"] for r in filed)


def get_financials(mcag, year):
    """
    Returns dict with:
      total_revenue, total_expenditure, surplus_deficit,
      property_tax_pct_of_revenue, top_expenditures
    or None if no data.
    """
    # ── totals: revenue (fsSectionId=20) and expenditure (fsSectionId=30) ──
    totals_f = (
        f"subAccountId eq null and elementId eq null and subElementId eq null "
        f"and fundCategoryId eq null and fundTypeId eq null and fund eq null "
        f"and expenditureObjectId eq null "
        f"and fsSectionId in (20,30) "
        f"and mcag eq '{mcag}' "
        f"and basicAccountId eq null "
        f"and {year} le year and year le {year}"
    )
    totals_data = get(odata_url(f"Snapshots({SNAP})/schedule1AggregationsByGovt", totals_f))
    if not totals_data:
        return None
    totals_rows = totals_data.get("value", totals_data) if isinstance(totals_data, dict) else totals_data
    if not totals_rows:
        return None

    total_revenue     = sum(r["totalAmount"] for r in totals_rows if r["fsSectionId"] == 20)
    total_expenditure = sum(r["totalAmount"] for r in totals_rows if r["fsSectionId"] == 30)
    if total_revenue == 0 and total_expenditure == 0:
        return None

    # ── revenue breakdown: get property tax % ──
    rev_f = (
        f"fsSectionId in (20) and basicAccountId ne null "
        f"and subAccountId eq null and elementId eq null and subElementId eq null "
        f"and fund eq null and expenditureObjectId eq null "
        f"and fundCategoryId eq null and fundTypeId eq null "
        f"and mcag eq '{mcag}' "
        f"and {year} le year and year le {year}"
    )
    rev_data = get(odata_url(f"Snapshots({SNAP})/schedule1AggregationsByGovt", rev_f))
    tax_revenue = 0
    if rev_data:
        rev_rows = rev_data.get("value", rev_data) if isinstance(rev_data, dict) else rev_data
        # basicAccountId=6 is "Taxes" (includes property tax)
        tax_revenue = sum(r["totalAmount"] for r in rev_rows if r.get("basicAccountId") == 6)

    property_tax_pct = round(100 * tax_revenue / total_revenue, 1) if total_revenue else None

    # ── expenditure breakdown: top categories ──
    exp_f = (
        f"fsSectionId in (30) and basicAccountId ne null "
        f"and subAccountId eq null and elementId eq null and subElementId eq null "
        f"and fund eq null and expenditureObjectId eq null "
        f"and fundCategoryId eq null and fundTypeId eq null "
        f"and mcag eq '{mcag}' "
        f"and {year} le year and year le {year}"
    )
    exp_data = get(odata_url(f"Snapshots({SNAP})/schedule1AggregationsByGovt", exp_f))
    top_expenditures = []
    if exp_data:
        exp_rows = exp_data.get("value", exp_data) if isinstance(exp_data, dict) else exp_data
        exp_rows.sort(key=lambda r: r["totalAmount"], reverse=True)
        for r in exp_rows[:3]:
            acct_id = r.get("basicAccountId")
            name = ACCOUNT_NAMES.get(acct_id, f"Account {acct_id}")
            top_expenditures.append({"name": name, "amount": r["totalAmount"]})

    return {
        "total_revenue":            round(total_revenue, 2),
        "total_expenditure":        round(total_expenditure, 2),
        "surplus_deficit":          round(total_revenue - total_expenditure, 2),
        "property_tax_pct_of_revenue": property_tax_pct,
        "top_expenditures":         top_expenditures,
    }


def fix_url(mcag):
    return f"https://portal.sao.wa.gov/FIT/explore/government/{mcag}"


# ── main ────────────────────────────────────────────────────────────────────

agencies = json.loads(AGENCIES_JSON.read_text(encoding="utf-8"))

ACCOUNT_NAMES = get_account_descriptors()

total = len(agencies)
updated = 0
no_data = 0

for i, (mcag, entry) in enumerate(agencies.items(), 1):
    name = entry.get("common_name", mcag)
    print(f"[{i}/{total}] {mcag} {name}")

    # Always fix the URL
    entry["sao_fit_url"] = fix_url(mcag)

    # Skip if already has budget data from CSV (school districts)
    if entry.get("budget") and entry["budget"].get("total_revenue"):
        # Just fix URL, keep existing budget
        print(f"  -> keeping existing budget data, URL fixed")
        continue

    # Find latest year with filed data
    year = get_latest_year(mcag)
    if not year:
        print(f"  -> no filed data found")
        no_data += 1
        time.sleep(0.3)
        continue

    print(f"  -> fetching {year} data...")
    budget = get_financials(mcag, year)
    time.sleep(0.4)  # be polite to the API

    if budget:
        entry["budget"]    = budget
        entry["data_year"] = year
        updated += 1
        rev = budget["total_revenue"]
        exp = budget["total_expenditure"]
        top = [x["name"] for x in budget.get("top_expenditures", [])]
        print(f"  -> rev=${rev:,.0f} exp=${exp:,.0f} top={top}")
    else:
        print(f"  -> API returned no financial rows")
        no_data += 1

# Write updated JSON
AGENCIES_JSON.write_text(
    json.dumps(agencies, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print()
print(f"Done. Updated: {updated}, No data: {no_data}, URL-fixed: {total}")
print(f"Written to {AGENCIES_JSON}")
