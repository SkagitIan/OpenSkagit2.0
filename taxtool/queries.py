from django.db import connection


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
                assessed_value,
                taxable_value
            FROM skagit_parcels
            WHERE parcel_number = %s
              AND inactive_date IS NULL
            LIMIT 1
            """,
            [parcel_number],
        )
        rows = _dictfetchall(cursor)
        return rows[0] if rows else None


def get_tax_summary(parcel_number):
    """Return all levy rows for a parcel from v_parcel_tax_summary."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                parcel_number,
                levy_code,
                reporting_status,
                agency_name,
                mcag,
                sao_fit_url,
                total_tax,
                pct_of_bill
            FROM v_parcel_tax_summary
            WHERE parcel_number = %s
            ORDER BY total_tax DESC
            """,
            [parcel_number],
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
