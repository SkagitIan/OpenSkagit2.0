from decimal import Decimal

from django.db import DatabaseError, connection


def _dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def search_parcels(q):
    """Return up to 8 active parcels matching address or parcel number."""
    q = q.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                parcel_number,
                situs_street_number,
                situs_street_name,
                situs_city_state_zip
            FROM skagit_parcels
            WHERE inactive_date IS NULL
              AND (
                    parcel_number ILIKE %s
                 OR situs_street_name ILIKE %s
                 OR CONCAT(situs_street_number, ' ', situs_street_name) ILIKE %s
              )
            ORDER BY situs_street_name, situs_street_number
            LIMIT 8
            """,
            [pattern, pattern, pattern],
        )
        return _dictfetchall(cursor)


def get_parcel(parcel_number):
    """Return a single active parcel record, or None."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                parcel_number,
                owner_name,
                situs_street_number,
                situs_street_name,
                situs_city_state_zip,
                total_taxes,
                levy_code,
                tax_year,
                assessed_value,
                taxable_value,
                tax_statement_taxable_value,
                total_market_value,
                exemptions,
                senior_exemption_adjustment
            FROM skagit_parcels
            WHERE parcel_number = %s
              AND inactive_date IS NULL
            LIMIT 1
            """,
            [parcel_number],
        )
        rows = _dictfetchall(cursor)
        return rows[0] if rows else None


def get_tax_summary(parcel_number, tax_year=None):
    """Return all levy rows for a parcel from v_parcel_tax_summary."""
    year_filter = "AND parcel_tax_year = %s" if tax_year else ""
    params = [parcel_number]
    if tax_year:
        params.append(str(tax_year))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                parcel_number,
                levy_code,
                parcel_tax_year,
                reporting_status,
                agency_name,
                mcag,
                sao_fit_url,
                total_tax,
                pct_of_bill
            FROM v_parcel_tax_summary
            WHERE parcel_number = %s
              {year_filter}
            ORDER BY total_tax DESC
            """,
            params,
        )
        return _dictfetchall(cursor)


def get_levy_code_median(levy_code):
    """Return the median total_taxes for active parcels in this levy code."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_taxes)
            FROM skagit_parcels
            WHERE levy_code = %s
              AND inactive_date IS NULL
              AND total_taxes IS NOT NULL
              AND total_taxes > 0
            """,
            [levy_code],
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None


def get_levy_code_effective_rate_median(levy_code):
    """Return median effective tax rate per $1,000 of assessed value in this levy code."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY total_taxes / NULLIF(assessed_value, 0) * 1000
            )
            FROM skagit_parcels
            WHERE levy_code = %s
              AND inactive_date IS NULL
              AND total_taxes IS NOT NULL
              AND total_taxes > 0
              AND assessed_value IS NOT NULL
              AND assessed_value > 0
            """,
            [levy_code],
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None


def get_county_median():
    """Return the median total_taxes across all active parcels."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_taxes)
            FROM skagit_parcels
            WHERE inactive_date IS NULL
              AND total_taxes IS NOT NULL
              AND total_taxes > 0
            """
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None


def get_county_effective_rate_median():
    """Return median effective tax rate per $1,000 of assessed value countywide."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY total_taxes / NULLIF(assessed_value, 0) * 1000
            )
            FROM skagit_parcels
            WHERE inactive_date IS NULL
              AND total_taxes IS NOT NULL
              AND total_taxes > 0
              AND assessed_value IS NOT NULL
              AND assessed_value > 0
            """
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None


def get_county_taxable_effective_rate_median():
    """Return median effective tax rate per $1,000 of taxable value countywide."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY total_taxes / NULLIF(taxable_value, 0) * 1000
            )
            FROM skagit_parcels
            WHERE inactive_date IS NULL
              AND total_taxes IS NOT NULL
              AND total_taxes > 0
              AND taxable_value IS NOT NULL
              AND taxable_value > 0
            """
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None


def get_parcel_history(parcel_number):
    """Return assessed-value/tax history rows, most recent first, excluding zero/null values."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tax_year, total_value, tax_amount, building_value, land_value
            FROM skagit_parcel_history
            WHERE parcel_number = %s
              AND tax_amount IS NOT NULL AND tax_amount > 0
              AND total_value IS NOT NULL AND total_value > 0
            ORDER BY tax_year DESC
            LIMIT 20
            """,
            [parcel_number],
        )
        return _dictfetchall(cursor)


VOTER_APPROVED_CATEGORIES = {"BOND", "DEBT", "M&O", "E&O", "SPECIAL", "EMS", "CP", "TRANS"}


def _is_voter_approved(row):
    category = str(row.get("category") or "").upper().strip()
    levy_name = str(row.get("levy_name") or "").upper()
    if category in VOTER_APPROVED_CATEGORIES:
        return True
    return any(token in levy_name for token in ("BOND", "ENRICHMENT", "TECH", "CAPITAL", "EMS"))


def _build_tax_shock_from_pair(levy_code, newer, older):
    """
    Build a rate/value explanation for one year-over-year pair.

    Parcel-history tax_year is the bill year. The levy-composition file is one
    label behind that bill year, so a 2025 history row uses 2024 composition.
    """
    newer_year = int(newer["tax_year"])
    older_year = int(older["tax_year"])
    composition_years = [newer_year - 1, older_year - 1]

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    lc.tax_year,
                    lc.levy_short,
                    lc.levy_name,
                    lc.category,
                    lc.rate,
                    x.reporting_status,
                    COALESCE(x.sao_legal_name, lc.levy_name) AS agency_name,
                    lh.district_name,
                    lh.district_levy
                FROM skagit_levy_composition lc
                LEFT JOIN skagit_levy_crosswalk x
                  ON x.levy_short = lc.levy_short
                LEFT JOIN v_skagit_levy_history_joined lh
                  ON lh.tax_year = lc.tax_year + 1
                 AND lh.levy_short = lc.levy_short
                WHERE lc.levy_code = %s
                  AND lc.tax_year IN (%s, %s)
                  AND lc.levy_short != 'X0002'
                """,
                [levy_code, composition_years[0], composition_years[1]],
            )
            component_rows = _dictfetchall(cursor)
    except DatabaseError:
        return None

    if not component_rows:
        return None

    components = {}
    for row in component_rows:
        item = components.setdefault(row["levy_short"], {
            "levy_short": row["levy_short"],
            "levy_name": row["levy_name"],
            "agency_name": row["agency_name"],
            "district_name": row["district_name"] or row["levy_name"],
            "category": row["category"],
            "reporting_status": row["reporting_status"],
            "old_rate": Decimal("0"),
            "new_rate": Decimal("0"),
            "old_district_levy": None,
            "new_district_levy": None,
            "is_voter_approved": _is_voter_approved(row),
        })
        rate = Decimal(str(row["rate"] or 0))
        if int(row["tax_year"]) == composition_years[0]:
            item["new_rate"] = rate
            item["new_district_levy"] = row["district_levy"]
        elif int(row["tax_year"]) == composition_years[1]:
            item["old_rate"] = rate
            item["old_district_levy"] = row["district_levy"]

    val_new = Decimal(str(newer["total_value"]))
    val_old = Decimal(str(older["total_value"]))
    tax_new = Decimal(str(newer["tax_amount"]))
    tax_old = Decimal(str(older["tax_amount"]))
    delta_tax = tax_new - tax_old

    value_effect = Decimal("0")
    voter_rate_effect = Decimal("0")
    other_rate_effect = Decimal("0")
    line_drivers = []

    for item in components.values():
        old_rate = item["old_rate"]
        new_rate = item["new_rate"]
        line_value_effect = (val_new - val_old) * (old_rate + new_rate) / Decimal("2") / Decimal("1000")
        line_rate_effect = (new_rate - old_rate) * (val_old + val_new) / Decimal("2") / Decimal("1000")
        value_effect += line_value_effect
        if item["is_voter_approved"]:
            voter_rate_effect += line_rate_effect
        else:
            other_rate_effect += line_rate_effect
        line_drivers.append({
            **item,
            "rate_delta": new_rate - old_rate,
            "rate_effect": line_rate_effect,
            "value_effect": line_value_effect,
        })

    if delta_tax == 0 or abs(delta_tax) < Decimal("25"):
        return None

    if delta_tax > 0:
        effects = [
            ("voter", voter_rate_effect if voter_rate_effect > 0 else Decimal("0")),
            ("value", value_effect if value_effect > 0 else Decimal("0")),
            ("other", other_rate_effect if other_rate_effect > 0 else Decimal("0")),
        ]
        top_lines = [line for line in line_drivers if line["rate_effect"] > 0]
    else:
        effects = [
            ("voter", abs(voter_rate_effect) if voter_rate_effect < 0 else Decimal("0")),
            ("value", abs(value_effect) if value_effect < 0 else Decimal("0")),
            ("other", abs(other_rate_effect) if other_rate_effect < 0 else Decimal("0")),
        ]
        top_lines = [line for line in line_drivers if line["rate_effect"] < 0]

    main_driver, main_effect = max(effects, key=lambda item: item[1])
    if main_effect <= 0:
        return None
    pct = min(100, round(float(main_effect / abs(delta_tax) * 100))) if delta_tax else 0
    top_lines = sorted(top_lines, key=lambda line: abs(line["rate_effect"]), reverse=True)[:3]

    return {
        "year_new": newer_year,
        "year_old": older_year,
        "composition_year_new": composition_years[0],
        "composition_year_old": composition_years[1],
        "tax_new": tax_new,
        "tax_old": tax_old,
        "delta_tax": delta_tax,
        "delta_positive": delta_tax > 0,
        "main_driver": main_driver,
        "main_driver_effect": main_effect,
        "main_driver_pct": pct,
        "value_effect": value_effect,
        "voter_rate_effect": voter_rate_effect,
        "other_rate_effect": other_rate_effect,
        "top_lines": top_lines,
        "estimated_from_current_levy_code": True,
    }


def get_tax_shock(parcel_number):
    """Return a compact explanation of the latest year-over-year parcel tax change."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.levy_code, h.tax_year, h.total_value, h.tax_amount
            FROM skagit_parcels p
            JOIN skagit_parcel_history h
              ON h.parcel_number = p.parcel_number
            WHERE p.parcel_number = %s
              AND p.inactive_date IS NULL
              AND p.levy_code IS NOT NULL
              AND h.tax_amount IS NOT NULL AND h.tax_amount > 0
              AND h.total_value IS NOT NULL AND h.total_value > 0
            ORDER BY h.tax_year DESC
            LIMIT 2
            """,
            [parcel_number],
        )
        history = _dictfetchall(cursor)

    if len(history) < 2:
        return None

    return _build_tax_shock_from_pair(history[0]["levy_code"], history[0], history[1])


def get_tax_shock_history(parcel_number, limit=7):
    """Return estimated levy/rate drivers for recent year-over-year history rows."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.levy_code, h.tax_year, h.total_value, h.tax_amount
            FROM skagit_parcels p
            JOIN skagit_parcel_history h
              ON h.parcel_number = p.parcel_number
            WHERE p.parcel_number = %s
              AND p.inactive_date IS NULL
              AND p.levy_code IS NOT NULL
              AND h.tax_amount IS NOT NULL AND h.tax_amount > 0
              AND h.total_value IS NOT NULL AND h.total_value > 0
            ORDER BY h.tax_year DESC
            LIMIT %s
            """,
            [parcel_number, limit + 1],
        )
        history = _dictfetchall(cursor)

    if len(history) < 2:
        return {}

    levy_code = history[0]["levy_code"]
    shocks = {}
    for index in range(min(limit, len(history) - 1)):
        shock = _build_tax_shock_from_pair(levy_code, history[index], history[index + 1])
        if shock:
            shocks[(shock["year_old"], shock["year_new"])] = shock
    return shocks
def get_agency_crosswalk(mcag):
    """Return the crosswalk row for a given MCAG (sao_legal_name, sao_fit_url)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT
                mcag,
                sao_legal_name,
                sao_fit_url
            FROM skagit_levy_crosswalk
            WHERE mcag = %s
            LIMIT 1
            """,
            [mcag],
        )
        rows = _dictfetchall(cursor)
        return rows[0] if rows else None


def get_county_total_for_mcag(mcag):
    """Return the county-wide total for a given MCAG from the pre-computed summary table."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(county_total, 0) FROM skagit_agency_totals WHERE mcag = %s",
            [mcag],
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def get_data_methodology_stats():
    """Return live, read-only provenance stats for the TaxShift methodology page."""
    stats = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*), min(tax_year), max(tax_year),
                       count(*) FILTER (WHERE total_taxes IS NOT NULL AND total_taxes > 0)
                FROM skagit_parcels
                WHERE inactive_date IS NULL
                """
            )
            row = cursor.fetchone()
            stats["active_parcels"] = row[0]
            stats["parcel_tax_year_min"] = row[1]
            stats["parcel_tax_year_max"] = row[2]
            stats["parcels_with_tax"] = row[3]

            cursor.execute(
                """
                SELECT min(tax_year), max(tax_year), count(*), count(DISTINCT parcel_number),
                       min(fetched_at), max(fetched_at)
                FROM skagit_parcel_history
                """
            )
            row = cursor.fetchone()
            stats["history_year_min"] = row[0]
            stats["history_year_max"] = row[1]
            stats["history_rows"] = row[2]
            stats["history_parcels"] = row[3]
            stats["history_fetched_min"] = row[4]
            stats["history_fetched_max"] = row[5]

            cursor.execute(
                """
                SELECT min(parcel_tax_year), max(parcel_tax_year), count(*), count(DISTINCT parcel_number)
                FROM v_parcel_tax_summary
                """
            )
            row = cursor.fetchone()
            stats["summary_year_min"] = row[0]
            stats["summary_year_max"] = row[1]
            stats["summary_rows"] = row[2]
            stats["summary_parcels"] = row[3]

            cursor.execute(
                """
                SELECT min(tax_year), max(tax_year), count(*), count(DISTINCT levy_code)
                FROM skagit_levy_composition
                """
            )
            row = cursor.fetchone()
            stats["levy_year_min"] = row[0]
            stats["levy_year_max"] = row[1]
            stats["levy_rows"] = row[2]
            stats["levy_codes"] = row[3]

            cursor.execute(
                """
                SELECT min(tax_year), max(tax_year), count(*), max(loaded_at)
                FROM skagit_levy_history
                """
            )
            row = cursor.fetchone()
            stats["dor_year_min"] = row[0]
            stats["dor_year_max"] = row[1]
            stats["dor_rows"] = row[2]
            stats["dor_loaded_at"] = row[3]

            cursor.execute("SELECT count(*) FROM skagit_agency_totals")
            stats["agency_total_rows"] = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT reporting_status, count(*)
                FROM v_parcel_tax_summary
                GROUP BY reporting_status
                ORDER BY reporting_status
                """
            )
            stats["reporting_statuses"] = [
                {"status": row[0], "count": row[1]}
                for row in cursor.fetchall()
            ]
    except DatabaseError:
        stats["error"] = True
    return stats
