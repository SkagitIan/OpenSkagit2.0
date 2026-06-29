import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


DATA_DIR = Path(settings.BASE_DIR) / "data"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from build_skagit_levy_history import OUTPUT_COLUMNS, build_rows  # noqa: E402


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skagit_levy_history (
    history_id                                  TEXT        PRIMARY KEY,
    tax_year                                    INT         NOT NULL,
    taxing_district_code                        TEXT        NOT NULL,
    county_code                                 TEXT        NOT NULL,
    district_name                               TEXT        NOT NULL,
    levy_short                                  TEXT,
    locally_assessed_value                      NUMERIC,
    levy_rate                                   NUMERIC(16,8),
    district_levy                               NUMERIC,
    highest_prior_levy                          NUMERIC,
    new_construction_assessed_value             NUMERIC,
    prior_year_levy_rate                        NUMERIC(16,8),
    prior_year_state_assessed_property          NUMERIC,
    two_years_prior_state_assessed_property     NUMERIC,
    two_years_prior_annexation_assessed_value   NUMERIC,
    two_years_prior_annex_tax_due               NUMERIC,
    two_years_prior_refund_tax_due              NUMERIC,
    maximum_allowable_levy_101_calc             NUMERIC,
    levy_name_canonical                         TEXT,
    entity_key                                  TEXT,
    mcag                                        TEXT,
    reporting_status                            TEXT,
    parent_mcag                                 TEXT,
    sao_legal_name                              TEXT,
    review_needed                               BOOLEAN     DEFAULT FALSE,
    agency_common_name                          TEXT,
    agency_type                                 TEXT,
    source_file                                 TEXT,
    loaded_at                                   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tax_year, taxing_district_code)
)
"""


INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_skagit_levy_history_year ON skagit_levy_history (tax_year)",
    "CREATE INDEX IF NOT EXISTS idx_skagit_levy_history_levy_short ON skagit_levy_history (levy_short)",
    "CREATE INDEX IF NOT EXISTS idx_skagit_levy_history_mcag ON skagit_levy_history (mcag)",
]


CREATE_JOINED_VIEW_SQL = """
CREATE VIEW v_skagit_levy_history_joined AS
SELECT
    h.history_id,
    h.tax_year,
    h.taxing_district_code,
    h.county_code,
    h.district_name,
    h.levy_short,
    h.locally_assessed_value,
    h.levy_rate,
    h.district_levy,
    h.highest_prior_levy,
    h.new_construction_assessed_value,
    h.prior_year_levy_rate,
    h.prior_year_state_assessed_property,
    h.two_years_prior_state_assessed_property,
    h.two_years_prior_annexation_assessed_value,
    h.two_years_prior_annex_tax_due,
    h.two_years_prior_refund_tax_due,
    h.maximum_allowable_levy_101_calc,
    COALESCE(x.levy_name_canonical, h.levy_name_canonical) AS levy_name_canonical,
    COALESCE(x.entity_key, h.entity_key)                   AS entity_key,
    COALESCE(x.mcag, h.mcag)                               AS mcag,
    COALESCE(x.parent_mcag, h.parent_mcag)                 AS parent_mcag,
    COALESCE(x.mcag, x.parent_mcag, h.mcag, h.parent_mcag) AS effective_mcag,
    COALESCE(x.reporting_status, h.reporting_status)       AS reporting_status,
    COALESCE(x.sao_legal_name, h.sao_legal_name)           AS sao_legal_name,
    COALESCE(x.sao_fit_url,
        CASE WHEN h.mcag IS NOT NULL AND h.mcag != ''
             THEN 'https://portal.sao.wa.gov/FIT/ReportsByEntity?mcag=' || h.mcag
             ELSE NULL
        END
    )                                                      AS sao_fit_url,
    COALESCE(x.review_needed, h.review_needed)             AS review_needed,
    h.agency_common_name,
    h.agency_type,
    h.source_file,
    h.loaded_at
FROM skagit_levy_history h
LEFT JOIN skagit_levy_crosswalk x
    ON x.levy_short = h.levy_short
"""


CREATE_AGENCY_VIEW_SQL = """
CREATE VIEW v_skagit_agency_levy_history AS
SELECT
    tax_year::TEXT || ':' || COALESCE(entity_key, effective_mcag, 'unknown') AS history_id,
    tax_year,
    entity_key,
    effective_mcag,
    COALESCE(NULLIF(MAX(agency_common_name), ''), MAX(sao_legal_name)) AS agency_name,
    CASE
        WHEN BOOL_OR(reporting_status = 'state_levy') THEN 'state_levy'
        WHEN BOOL_OR(reporting_status = 'reports_independently') THEN 'reports_independently'
        ELSE MIN(reporting_status)
    END AS reporting_status,
    MAX(agency_type) AS agency_type,
    COUNT(*) AS levy_line_count,
    SUM(district_levy) AS district_levy,
    BOOL_OR(review_needed) AS review_needed
FROM v_skagit_levy_history_joined
GROUP BY tax_year, entity_key, effective_mcag
"""


NUMERIC_COLUMNS = {
    "tax_year",
    "locally_assessed_value",
    "levy_rate",
    "district_levy",
    "highest_prior_levy",
    "new_construction_assessed_value",
    "prior_year_levy_rate",
    "prior_year_state_assessed_property",
    "two_years_prior_state_assessed_property",
    "two_years_prior_annexation_assessed_value",
    "two_years_prior_annex_tax_due",
    "two_years_prior_refund_tax_due",
    "maximum_allowable_levy_101_calc",
}


def clean_value(column, value):
    if value == "":
        return None if column in NUMERIC_COLUMNS else ""
    if column == "review_needed":
        return str(value).lower() == "true"
    return value


class Command(BaseCommand):
    help = "Create and load Skagit historical levy rows from DOR All County Levy Detail workbooks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--workbook-dir",
            default=str(DATA_DIR),
            help="Directory containing All_County_Levy_Detail_*.xlsx files",
        )

    def handle(self, *args, **options):
        workbook_dir = Path(options["workbook_dir"])
        rows = build_rows(workbook_dir)
        if not rows:
            self.stdout.write(self.style.WARNING(f"No Skagit levy rows found in {workbook_dir}"))
            return

        insert_columns = [column for column in OUTPUT_COLUMNS if column != "loaded_at"]
        placeholders = ", ".join(["%s"] * len(insert_columns))
        column_sql = ", ".join(insert_columns)
        insert_sql = f"INSERT INTO skagit_levy_history ({column_sql}) VALUES ({placeholders})"
        values = [
            tuple(clean_value(column, row.get(column, "")) for column in insert_columns)
            for row in rows
        ]

        with connection.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
            for sql in INDEX_SQL:
                cursor.execute(sql)
            cursor.execute("DROP VIEW IF EXISTS v_skagit_agency_levy_history")
            cursor.execute("DROP VIEW IF EXISTS v_skagit_levy_history_joined")
            cursor.execute("DELETE FROM skagit_levy_history")
            cursor.executemany(insert_sql, values)
            cursor.execute(CREATE_JOINED_VIEW_SQL)
            cursor.execute(CREATE_AGENCY_VIEW_SQL)

        years = sorted({row["tax_year"] for row in rows})
        unmatched = sum(1 for row in rows if not row["levy_short"])
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows):,} rows into skagit_levy_history"))
        self.stdout.write(f"Years: {', '.join(years)}")
        self.stdout.write(f"Unmatched TDCODE rows: {unmatched}")
