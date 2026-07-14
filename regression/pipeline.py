"""
Pipeline logic for the first SFR sales modeling dataset.

Two stages:
1. Rebuild the one-row-per-parcel summaries (``model_land_summary``,
   ``model_improvement_summary``) with set-based SQL aggregation -- never a
   Python loop over land/improvement rows.
2. Join sales to those summaries plus parcel/geo/zoning data, classify every
   sale as included or excluded with pandas (vectorized boolean masks), and
   hand back two DataFrames ready to load into
   ``model_sfr_sales_dataset`` / ``model_sfr_sales_exclusions``.

This module never writes to a source table (``sales``, ``land``,
``improvements``, ``skagit_parcels``, ``assessor_rollup``,
``parcel_geo_static_features``, ``parcel_primary_zoning``) -- only to this
app's own derived tables, via the command that calls these functions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Core detached-SFR land-use codes. See docs/sfr_modeling_dataset_plan.md for
# why 112/113 (secondary detached unit) and 190 (vacation/cabin) are tracked
# separately instead of folded into "included" or a generic "excluded".
CORE_SFR_LAND_USE_CODES = {"110", "111"}
SECONDARY_UNIT_LAND_USE_CODES = {"112", "113"}
VACATION_CABIN_LAND_USE_CODE = "190"
MOBILE_MANUFACTURED_LAND_USE_CODES = {"150", "180", "181", "182", "185"}
CONDO_LAND_USE_CODES = {"140", "500", "970"}
MULTIFAMILY_LAND_USE_CODES = {"120", "130"}
HOTEL_LODGING_LAND_USE_CODES = {"160", "170"}

ATTACHED_OR_CONDO_BUILDINGSTYLES = {
    "TOWNHOUSE - ATTACHED SFR UNITS",
    "CONDO",
    "DOUBLE WIDE",
}

GARAGE_TYPE_CODES = ("AGAR", "DGAR", "GBI", "CARP")
BASEMENT_TYPE_CODES = ("BMF", "BMU", "BMG", "GBI")
FIREPLACE_TYPE_CODES = ("OFP",)

VALID_SALE_TYPE = "VALID SALE"


def _fetch_df(cursor, sql: str, params: tuple = ()) -> pd.DataFrame:
    cursor.execute(sql, params)
    columns = [col.name for col in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)


def _clean_value(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts, NaN/NaT -> None and numpy scalars -> native Python types."""
    return [{key: _clean_value(value) for key, value in row.items()} for row in df.to_dict("records")]


# ----------------------------------------------------------------------
# Land summary
# ----------------------------------------------------------------------

_LAND_SUMMARY_SQL = """
SELECT
    agg.parcelnumber AS parcel_number,
    agg.land_segment_count,
    agg.total_land_acres,
    agg.total_land_market_value,
    agg.has_open_space_value,
    agg.max_land_segment_acres,
    agg.max_land_segment_value,
    primary_seg.land_type AS primary_land_type,
    primary_seg.appr_meth AS primary_appr_method
FROM (
    SELECT
        parcelnumber,
        COUNT(*) AS land_segment_count,
        SUM(size_acres_num) AS total_land_acres,
        SUM(market_value_num) AS total_land_market_value,
        bool_or(
            open_space_val IS NOT NULL
            AND trim(open_space_val) <> ''
            AND trim(open_space_val) <> '0'
        ) AS has_open_space_value,
        MAX(size_acres_num) AS max_land_segment_acres,
        MAX(market_value_num) AS max_land_segment_value
    FROM land
    WHERE parcelnumber IS NOT NULL AND parcelnumber <> ''
    GROUP BY parcelnumber
) agg
JOIN LATERAL (
    SELECT land_type, appr_meth
    FROM land l2
    WHERE l2.parcelnumber = agg.parcelnumber
    ORDER BY l2.size_acres_num DESC NULLS LAST, l2.market_value_num DESC NULLS LAST, l2.id
    LIMIT 1
) primary_seg ON true
"""


def fetch_land_summary(cursor) -> pd.DataFrame:
    """One row per parcel_number, aggregated from the one-to-many ``land`` table."""
    return _fetch_df(cursor, _LAND_SUMMARY_SQL)


# ----------------------------------------------------------------------
# Improvement summary
# ----------------------------------------------------------------------

_IMPROVEMENT_SUMMARY_SQL = """
SELECT
    agg.parcelnumber AS parcel_number,
    agg.improvement_row_count,
    agg.building_count,
    agg.total_improvement_value,
    agg.total_living_area,
    agg.has_garage,
    agg.has_fireplace,
    agg.has_basement,
    primary_imp.imprv_id AS primary_imprv_id,
    primary_imp.living_area_num AS primary_living_area,
    primary_imp.building_style AS primary_building_style,
    trim(primary_imp.condition_cd) AS primary_condition_cd,
    primary_imp.condition_description AS primary_condition_description,
    trim(primary_imp.imprv_det_type_cd) AS primary_imprv_det_type_cd,
    trim(primary_imp.imprv_det_class_cd) AS primary_imprv_det_class_cd,
    primary_imp.imprv_det_type_description AS primary_imprv_det_type_description,
    primary_imp.imprv_det_class_description AS primary_imprv_det_class_description,
    primary_imp.actual_year_built AS primary_actual_year_built,
    primary_imp.effective_yr_blt AS primary_effective_year_built,
    NULLIF(trim(primary_imp.bedrooms), '') AS bedrooms,
    NULLIF(trim(primary_imp.rooms), '') AS rooms
FROM (
    SELECT
        parcelnumber,
        COUNT(*) AS improvement_row_count,
        COUNT(*) FILTER (WHERE living_area_num > 0) AS building_count,
        SUM(imprv_val_num) AS total_improvement_value,
        SUM(living_area_num) FILTER (WHERE living_area_num > 0) AS total_living_area,
        bool_or(trim(imprv_det_type_cd) = ANY(%(garage_codes)s)) AS has_garage,
        bool_or(trim(imprv_det_type_cd) = ANY(%(fireplace_codes)s)) AS has_fireplace,
        bool_or(trim(imprv_det_type_cd) = ANY(%(basement_codes)s)) AS has_basement
    FROM improvements
    WHERE parcelnumber IS NOT NULL AND parcelnumber <> ''
    GROUP BY parcelnumber
) agg
JOIN LATERAL (
    SELECT *
    FROM improvements i2
    WHERE i2.parcelnumber = agg.parcelnumber
    ORDER BY
        (COALESCE(i2.living_area_num, 0) > 0) DESC,
        i2.living_area_num DESC NULLS LAST,
        i2.imprv_val_num DESC NULLS LAST,
        i2.imprv_id
    LIMIT 1
) primary_imp ON true
"""


def fetch_improvement_summary(cursor) -> pd.DataFrame:
    """One row per parcel_number, aggregated from the one-to-many ``improvements`` table."""
    df = _fetch_df(
        cursor,
        _IMPROVEMENT_SUMMARY_SQL,
        {
            "garage_codes": list(GARAGE_TYPE_CODES),
            "fireplace_codes": list(FIREPLACE_TYPE_CODES),
            "basement_codes": list(BASEMENT_TYPE_CODES),
        },
    )
    # actual_year_built/effective_yr_blt are text on `improvements`; coerce safely
    # rather than risk a SQL cast error on blank/garbage values.
    df["primary_actual_year_built"] = pd.to_numeric(df["primary_actual_year_built"], errors="coerce")
    df["primary_effective_year_built"] = pd.to_numeric(df["primary_effective_year_built"], errors="coerce")
    return df


# ----------------------------------------------------------------------
# Diagnostic report of distinct values (run before hard-coding SFR rules)
# ----------------------------------------------------------------------

def fetch_sfr_classification_diagnostic(cursor) -> dict:
    """Distinct value counts on valid, priced sales -- the evidence behind the rules above."""
    diagnostics = {}
    queries = {
        "sale_type": "SELECT sale_type, count(*) c FROM sales GROUP BY sale_type ORDER BY c DESC",
        "deed_type": "SELECT deed_type, count(*) c FROM sales GROUP BY deed_type ORDER BY c DESC LIMIT 25",
        "land_use_on_valid_sales": """
            SELECT p.land_use, count(*) c
            FROM sales s JOIN skagit_parcels p ON p.parcel_number = s.parcel_number
            WHERE s.sale_type = 'VALID SALE' AND s.sale_price_num > 0
            GROUP BY p.land_use ORDER BY c DESC LIMIT 40
        """,
        "proptype_on_valid_sales": """
            SELECT p.proptype, count(*) c
            FROM sales s JOIN skagit_parcels p ON p.parcel_number = s.parcel_number
            WHERE s.sale_type = 'VALID SALE' AND s.sale_price_num > 0
            GROUP BY p.proptype ORDER BY c DESC
        """,
        "buildingstyle_on_core_sfr": """
            SELECT p.buildingstyle, count(*) c
            FROM sales s JOIN skagit_parcels p ON p.parcel_number = s.parcel_number
            WHERE s.sale_type = 'VALID SALE' AND s.sale_price_num > 0
              AND split_part(ltrim(COALESCE(p.land_use,''),'('),')',1) IN ('110','111')
            GROUP BY p.buildingstyle ORDER BY c DESC LIMIT 20
        """,
        "exemptions_on_core_sfr": """
            SELECT p.exemptions, count(*) c
            FROM sales s JOIN skagit_parcels p ON p.parcel_number = s.parcel_number
            WHERE s.sale_type = 'VALID SALE' AND s.sale_price_num > 0
              AND split_part(ltrim(COALESCE(p.land_use,''),'('),')',1) IN ('110','111')
              AND p.exemptions IS NOT NULL AND trim(p.exemptions) <> ''
            GROUP BY p.exemptions ORDER BY c DESC LIMIT 20
        """,
    }
    for key, sql in queries.items():
        cursor.execute(sql)
        diagnostics[key] = [{"value": row[0], "count": row[1]} for row in cursor.fetchall()]
    return diagnostics


# ----------------------------------------------------------------------
# Sales join (one wide row per sale, before classification)
# ----------------------------------------------------------------------

_SALES_JOIN_SQL = """
WITH active_parcel AS (
    SELECT DISTINCT ON (parcel_number) *
    FROM skagit_parcels
    ORDER BY parcel_number, (inactive_date IS NULL) DESC, tax_year DESC NULLS LAST
),
rollup_desc AS (
    SELECT DISTINCT ON (parcel_number)
        parcel_number, neighborhood_description, land_use_description
    FROM assessor_rollup
    ORDER BY parcel_number, (inactive_date = '') DESC
)
SELECT
    s.saleid,
    s.parcel_number,
    s.sale_price_num,
    s.sale_date_iso,
    s.deed_type,
    s.sale_type,
    s.reval_area,
    s.recording_number,
    s.excise_number,

    p.neighborhood_code,
    rd.neighborhood_description,
    p.land_use,
    rd.land_use_description,
    p.proptype,
    p.buildingstyle,
    p.tax_year,
    p.appraisal_year,
    p.assessed_value::float8 AS assessed_value,
    p.total_market_value::float8 AS total_market_value,
    p.building_value::float8 AS building_value,
    p.acres::float8 AS acres,
    p.inactive_date,
    p.exemptions,

    ls.land_segment_count,
    ls.total_land_acres,
    ls.total_land_market_value,
    ls.primary_land_type,
    ls.has_open_space_value,

    ims.improvement_row_count,
    ims.building_count,
    ims.total_improvement_value,
    ims.total_living_area,
    ims.primary_living_area,
    ims.primary_building_style,
    ims.primary_condition_cd,
    ims.primary_condition_description,
    ims.primary_actual_year_built,
    ims.primary_effective_year_built,
    ims.primary_imprv_det_type_cd,
    ims.primary_imprv_det_class_cd,
    ims.bedrooms,
    ims.rooms,
    ims.has_garage,
    ims.has_fireplace,
    ims.has_basement,

    g.x, g.y, g.lat, g.lon, g.point_source, g.city_name, g.comp_plan_designation,
    g.school_district, g.fire_district, g.voting_precinct, g.historical_area_flag,
    g.distance_to_nearest_road_miles, g.distance_to_mount_vernon_miles,
    g.distance_to_burlington_miles, g.distance_to_sedro_woolley_miles,
    g.distance_to_anacortes_miles, g.distance_to_la_conner_miles,
    g.distance_to_nearest_public_place_miles, g.distance_to_nearest_tide_gate_miles,
    g.feature_status,

    z.zone_id AS primary_zoning_code,
    z.zone_name AS primary_zoning_description,
    z.percent_of_parcel AS primary_zoning_overlap_percent,
    z.waza_general AS zoning_general_category
FROM sales s
LEFT JOIN active_parcel p ON p.parcel_number = s.parcel_number
LEFT JOIN rollup_desc rd ON rd.parcel_number = s.parcel_number
LEFT JOIN model_land_summary ls ON ls.parcel_number = s.parcel_number
LEFT JOIN model_improvement_summary ims ON ims.parcel_number = s.parcel_number
LEFT JOIN parcel_geo_static_features g ON g.parcel_number = s.parcel_number
LEFT JOIN parcel_primary_zoning z ON z.parcel_id = s.parcel_number
"""


_EXACT_DUPLICATE_SALE_COLUMNS = ["saleid", "parcel_number", "sale_price_num", "sale_date_iso", "recording_number", "deed_type", "sale_type"]


def fetch_sales_join(cursor) -> pd.DataFrame:
    """
    One wide row per sale, left-joined to every parcel-level source. No sale is
    dropped by the join itself.

    ``sales.saleid`` is not unique in the source table -- ~1,760 groups of
    exact-duplicate rows exist even among valid, priced sales (an apparent
    import artifact, not a multi-parcel-sale pattern). Exact duplicates on the
    core sale-identity columns are collapsed to one row here so the same real
    transaction is never counted twice.
    """
    df = _fetch_df(cursor, _SALES_JOIN_SQL)
    return df.drop_duplicates(subset=_EXACT_DUPLICATE_SALE_COLUMNS, keep="first")


def _land_use_code(land_use: pd.Series) -> pd.Series:
    """Extract the numeric code from '(111) HOUSEHOLD, SFR, INSIDE CITY' -> '111'."""
    return land_use.fillna("").str.extract(r"\((\d+)\)", expand=False)


def classify_sales(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split the joined sales frame into (included, excluded), each sale getting
    exactly one exclusion reason -- the first applicable rule, checked in the
    priority order below (matching the order in the milestone brief).
    """
    df = df.copy()
    df["land_use_code"] = _land_use_code(df["land_use"])
    buildingstyle_upper = df["primary_building_style"].fillna("").str.upper()
    parcel_buildingstyle_upper = df["buildingstyle"].fillna("").str.upper()

    reason = pd.Series(np.nan, index=df.index, dtype=object)
    detail = pd.Series("", index=df.index, dtype=object)

    def apply_rule(mask: pd.Series, reason_code: str, detail_series: pd.Series | None = None) -> None:
        target = mask & reason.isna()
        reason.loc[target] = reason_code
        if detail_series is not None:
            detail.loc[target] = detail_series.loc[target].astype(str)

    # Sale-record data quality first.
    apply_rule(df["sale_price_num"].isna(), "missing_sale_price")
    apply_rule(df["sale_price_num"] <= 0, "non_positive_sale_price", df["sale_price_num"])
    apply_rule(~df["sale_date_iso"].fillna("").str.match(r"^\d{4}-\d{2}-\d{2}$"), "missing_sale_date")
    apply_rule(df["land_use"].isna(), "missing_parcel_match")
    apply_rule(df["inactive_date"].notna(), "inactive_parcel")
    apply_rule(df["sale_type"].fillna("") != VALID_SALE_TYPE, "non_arms_length_sale_type", df["sale_type"])
    apply_rule(df["proptype"].fillna("") != "R", "wrong_proptype", df["proptype"])

    # Asset-class rules -- checked before `exempt_parcel` so that flag doesn't
    # "steal" the reason from what is really a commercial/ag/vacant exclusion.
    apply_rule(
        df["land_use_code"].isin(MOBILE_MANUFACTURED_LAND_USE_CODES),
        "mobile_or_manufactured_home",
        df["land_use"],
    )
    apply_rule(df["land_use_code"].isin(CONDO_LAND_USE_CODES), "condo", df["land_use"])
    apply_rule(df["land_use_code"].isin(MULTIFAMILY_LAND_USE_CODES), "multifamily_or_duplex_plus", df["land_use"])
    apply_rule(df["land_use_code"].isin(SECONDARY_UNIT_LAND_USE_CODES), "secondary_detached_unit_present", df["land_use"])
    apply_rule(df["land_use_code"] == VACATION_CABIN_LAND_USE_CODE, "vacation_cabin_use", df["land_use"])
    apply_rule(df["land_use_code"].isin(HOTEL_LODGING_LAND_USE_CODES), "hotel_or_institutional_lodging", df["land_use"])
    apply_rule(
        df["land_use_code"].notna() & ~df["land_use_code"].isin(CORE_SFR_LAND_USE_CODES) & (df["land_use_code"] < "200"),
        "non_sfr_residential_land_use",
        df["land_use"],
    )
    apply_rule(df["land_use_code"].between("900", "999"), "vacant_or_undeveloped_land", df["land_use"])
    apply_rule(df["land_use_code"].between("700", "899"), "agricultural_or_recreation_only", df["land_use"])
    apply_rule(df["land_use_code"] >= "200", "commercial_or_industrial", df["land_use"])
    apply_rule(
        buildingstyle_upper.isin(ATTACHED_OR_CONDO_BUILDINGSTYLES) | parcel_buildingstyle_upper.isin(ATTACHED_OR_CONDO_BUILDINGSTYLES),
        "attached_or_condo_buildingstyle",
        df["primary_building_style"],
    )

    # Only reached by parcels that already look like genuine detached SFR --
    # so this is the true "SFR home carries an institutional exemption" count.
    apply_rule(df["exemptions"].fillna("").str.strip() != "", "exempt_parcel", df["exemptions"])

    apply_rule(df["improvement_row_count"].isna(), "no_usable_improvement_summary")
    apply_rule(df["primary_living_area"].isna() | (df["primary_living_area"] <= 0), "no_usable_living_area")
    apply_rule(
        df["primary_actual_year_built"].isna() & df["primary_effective_year_built"].isna(),
        "no_usable_year_built",
    )

    df["exclusion_reason"] = reason
    df["exclusion_detail"] = detail

    included = df[df["exclusion_reason"].isna()].copy()
    excluded = df[df["exclusion_reason"].notna()].copy()
    return included, excluded


def build_dataset_frame(included: pd.DataFrame) -> pd.DataFrame:
    """Shape the included sales into the final model_sfr_sales_dataset columns."""
    out = pd.DataFrame(index=included.index)
    sale_date = pd.to_datetime(included["sale_date_iso"], errors="coerce")

    out["saleid"] = included["saleid"]
    out["parcel_number"] = included["parcel_number"]
    out["sale_date"] = sale_date.dt.date
    out["sale_year"] = sale_date.dt.year.astype("Int64")
    out["sale_month"] = sale_date.dt.month.astype("Int64")
    out["sale_price"] = included["sale_price_num"].astype(float)
    out["log_sale_price"] = np.log(out["sale_price"])
    out["deed_type"] = included["deed_type"]
    out["sale_type"] = included["sale_type"]
    out["reval_area"] = included["reval_area"]
    out["recording_number"] = included["recording_number"]
    out["excise_number"] = included["excise_number"]

    out["neighborhood_code"] = included["neighborhood_code"]
    out["neighborhood_description"] = included["neighborhood_description"]
    out["land_use_code"] = included["land_use_code"]
    out["land_use_description"] = included["land_use_description"]
    out["proptype"] = included["proptype"]
    out["tax_year"] = included["tax_year"]
    out["appraisal_year"] = included["appraisal_year"]
    out["assessed_value"] = included["assessed_value"]
    out["total_market_value"] = included["total_market_value"]
    out["building_value"] = included["building_value"]
    out["acres"] = included["acres"]

    out["land_segment_count"] = included["land_segment_count"].astype("Int64")
    out["total_land_acres"] = included["total_land_acres"]
    out["total_land_market_value"] = included["total_land_market_value"]
    out["primary_land_type"] = included["primary_land_type"]
    out["has_open_space_value"] = included["has_open_space_value"]

    out["improvement_row_count"] = included["improvement_row_count"].astype("Int64")
    out["building_count"] = included["building_count"].astype("Int64")
    out["total_improvement_value"] = included["total_improvement_value"]
    out["total_living_area"] = included["total_living_area"]
    out["primary_living_area"] = included["primary_living_area"]
    out["primary_building_style"] = included["primary_building_style"]
    out["primary_condition_cd"] = included["primary_condition_cd"]
    out["primary_condition_description"] = included["primary_condition_description"]
    out["primary_actual_year_built"] = included["primary_actual_year_built"]
    out["primary_effective_year_built"] = included["primary_effective_year_built"]
    out["primary_imprv_det_type_cd"] = included["primary_imprv_det_type_cd"]
    out["primary_imprv_det_class_cd"] = included["primary_imprv_det_class_cd"]
    out["bedrooms"] = included["bedrooms"]
    out["rooms"] = included["rooms"]
    out["has_garage"] = included["has_garage"]
    out["has_fireplace"] = included["has_fireplace"]
    out["has_basement"] = included["has_basement"]

    out["x"] = included["x"]
    out["y"] = included["y"]
    out["lat"] = included["lat"]
    out["lon"] = included["lon"]
    out["point_source"] = included["point_source"]
    out["city_name"] = included["city_name"]
    out["comp_plan_designation"] = included["comp_plan_designation"]
    out["school_district"] = included["school_district"]
    out["fire_district"] = included["fire_district"]
    out["voting_precinct"] = included["voting_precinct"]
    out["historical_area_flag"] = included["historical_area_flag"]
    out["distance_to_nearest_road_miles"] = included["distance_to_nearest_road_miles"]
    out["distance_to_mount_vernon_miles"] = included["distance_to_mount_vernon_miles"]
    out["distance_to_burlington_miles"] = included["distance_to_burlington_miles"]
    out["distance_to_sedro_woolley_miles"] = included["distance_to_sedro_woolley_miles"]
    out["distance_to_anacortes_miles"] = included["distance_to_anacortes_miles"]
    out["distance_to_la_conner_miles"] = included["distance_to_la_conner_miles"]
    out["distance_to_nearest_public_place_miles"] = included["distance_to_nearest_public_place_miles"]
    out["distance_to_nearest_tide_gate_miles"] = included["distance_to_nearest_tide_gate_miles"]
    out["feature_status"] = included["feature_status"]

    out["primary_zoning_code"] = included["primary_zoning_code"]
    out["primary_zoning_description"] = included["primary_zoning_description"]
    out["primary_zoning_overlap_percent"] = included["primary_zoning_overlap_percent"]
    out["zoning_general_category"] = included["zoning_general_category"]

    return out


def build_exclusion_frame(excluded: pd.DataFrame) -> pd.DataFrame:
    """Shape the excluded sales into the model_sfr_sales_exclusions columns."""
    out = pd.DataFrame(index=excluded.index)
    out["saleid"] = excluded["saleid"]
    out["parcel_number"] = excluded["parcel_number"]
    out["sale_date_iso"] = excluded["sale_date_iso"]
    out["sale_price_num"] = excluded["sale_price_num"]
    out["exclusion_reason"] = excluded["exclusion_reason"]
    out["details"] = excluded["exclusion_detail"]
    return out
