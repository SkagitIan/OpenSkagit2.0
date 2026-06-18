from django.db import models


class AssessorRollup(models.Model):
    aid = models.TextField(blank=True, null=True)
    parcel_number = models.TextField(blank=True, null=True)
    account_number = models.TextField(blank=True, null=True)
    legal_description = models.TextField(blank=True, null=True)
    situs_street_number = models.TextField(blank=True, null=True)
    situs_street_name = models.TextField(blank=True, null=True)
    situs_city_state_zip = models.TextField(blank=True, null=True)
    old_street_number = models.TextField(blank=True, null=True)
    old_street_name = models.TextField(blank=True, null=True)
    old_city_state_zip = models.TextField(blank=True, null=True)
    owner_name = models.TextField(blank=True, null=True)
    owner_add_1 = models.TextField(blank=True, null=True)
    owner_add_2 = models.TextField(blank=True, null=True)
    owner_add_3 = models.TextField(blank=True, null=True)
    owner_city = models.TextField(blank=True, null=True)
    owner_state = models.TextField(blank=True, null=True)
    owner_zip = models.TextField(blank=True, null=True)
    exemptions = models.TextField(blank=True, null=True)
    neighborhood_code = models.TextField(blank=True, null=True)
    building_value = models.TextField(blank=True, null=True)
    land_use = models.TextField(blank=True, null=True)
    impr_land_value = models.TextField(blank=True, null=True)
    unimpr_land_value = models.TextField(blank=True, null=True)
    timber_land_value = models.TextField(blank=True, null=True)
    assessed_value = models.TextField(blank=True, null=True)
    taxable_value = models.TextField(blank=True, null=True)
    total_market_value = models.TextField(blank=True, null=True)
    acres = models.TextField(blank=True, null=True)
    sale_date = models.TextField(blank=True, null=True)
    sale_price = models.TextField(blank=True, null=True)
    sale_deed_type = models.TextField(blank=True, null=True)
    total_taxes = models.TextField(blank=True, null=True)
    year_built = models.TextField(blank=True, null=True)
    living_area = models.TextField(blank=True, null=True)
    tot_special_assessments = models.TextField(blank=True, null=True)
    general_taxes = models.TextField(blank=True, null=True)
    inactive_date = models.TextField(blank=True, null=True)
    buildingstyle = models.TextField(blank=True, null=True)
    foundation = models.TextField(blank=True, null=True)
    exterior_walls = models.TextField(blank=True, null=True)
    roof_covering = models.TextField(blank=True, null=True)
    roof_style = models.TextField(blank=True, null=True)
    floor_covering = models.TextField(blank=True, null=True)
    floor_construction = models.TextField(blank=True, null=True)
    interior_finish = models.TextField(blank=True, null=True)
    plumbing = models.TextField(blank=True, null=True)
    garagesqft = models.TextField(blank=True, null=True)
    heat_air_cond = models.TextField(blank=True, null=True)
    fireplace = models.TextField(blank=True, null=True)
    finishedbasement = models.TextField(blank=True, null=True)
    number_of_bedrooms = models.TextField(blank=True, null=True)
    eff_year_built = models.TextField(blank=True, null=True)
    unfinishedbasement = models.TextField(blank=True, null=True)
    fire_district = models.TextField(blank=True, null=True)
    school_district = models.TextField(blank=True, null=True)
    city_district = models.TextField(blank=True, null=True)
    unit = models.TextField(blank=True, null=True)
    levy_code = models.TextField(blank=True, null=True)
    current_use_adjustment = models.TextField(blank=True, null=True)
    tide_land_value = models.TextField(blank=True, null=True)
    senior_exemption_adjustment = models.TextField(blank=True, null=True)
    township = models.TextField(blank=True, null=True)
    range = models.TextField(blank=True, null=True)
    section = models.TextField(blank=True, null=True)
    quarter_section = models.TextField(blank=True, null=True)
    tax_year = models.TextField(blank=True, null=True)
    appraisal_year = models.TextField(blank=True, null=True)
    utilities = models.TextField(blank=True, null=True)
    tax_statement_taxable_value = models.TextField(blank=True, null=True)
    proptype = models.TextField(blank=True, null=True)
    hasseptic = models.TextField(blank=True, null=True)
    land_use_code = models.TextField(blank=True, null=True)
    land_use_description = models.TextField(blank=True, null=True)
    neighborhood_code_id = models.TextField(blank=True, null=True)
    neighborhood_description = models.TextField(blank=True, null=True)
    utilities_codes = models.TextField(blank=True, null=True)
    utilities_description = models.TextField(blank=True, null=True)
    assessed_value_num = models.FloatField(blank=True, null=True)
    taxable_value_num = models.FloatField(blank=True, null=True)
    total_market_value_num = models.FloatField(blank=True, null=True)
    acres_num = models.FloatField(blank=True, null=True)
    sale_price_num = models.FloatField(blank=True, null=True)
    sale_date_iso = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "assessor_rollup"


class SkagitParcel(models.Model):
    aid = models.TextField(blank=True, null=True)
    parcel_number = models.TextField(primary_key=True)
    account_number = models.TextField(blank=True, null=True)
    legal_description = models.TextField(blank=True, null=True)
    situs_street_number = models.TextField(blank=True, null=True)
    situs_street_name = models.TextField(blank=True, null=True)
    situs_city_state_zip = models.TextField(blank=True, null=True)
    owner_name = models.TextField(blank=True, null=True)
    owner_city = models.TextField(blank=True, null=True)
    owner_state = models.TextField(blank=True, null=True)
    owner_zip = models.TextField(blank=True, null=True)
    exemptions = models.TextField(blank=True, null=True)
    neighborhood_code = models.TextField(blank=True, null=True)
    building_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    land_use = models.TextField(blank=True, null=True)
    assessed_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    taxable_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    total_market_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    acres = models.DecimalField(max_digits=20, decimal_places=6, blank=True, null=True)
    sale_date = models.DateField(blank=True, null=True)
    sale_price = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    sale_deed_type = models.TextField(blank=True, null=True)
    total_taxes = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    year_built = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    living_area = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    general_taxes = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    inactive_date = models.DateField(blank=True, null=True)
    fire_district = models.TextField(blank=True, null=True)
    school_district = models.TextField(blank=True, null=True)
    city_district = models.TextField(blank=True, null=True)
    levy_code = models.TextField(blank=True, null=True)
    tax_year = models.TextField(blank=True, null=True)
    appraisal_year = models.TextField(blank=True, null=True)
    utilities = models.TextField(blank=True, null=True)
    proptype = models.TextField(blank=True, null=True)
    loaded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "skagit_parcels"

    def __str__(self):
        return self.parcel_number


class GisSkagitParcel(models.Model):
    objectid = models.BigIntegerField(primary_key=True)
    parcel_id = models.TextField(blank=True, null=True)
    situsstno = models.TextField(blank=True, null=True)
    situsstname = models.TextField(blank=True, null=True)
    situscsz = models.TextField(blank=True, null=True)
    ownername = models.TextField(blank=True, null=True)
    citydistrict = models.TextField(blank=True, null=True)
    landuse = models.TextField(blank=True, null=True)
    acres = models.FloatField(blank=True, null=True)
    taxyear = models.FloatField(blank=True, null=True)
    appraisalyear = models.FloatField(blank=True, null=True)
    inactivedate = models.FloatField(blank=True, null=True)
    geometry = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "gis_skagit_parcels"

    def __str__(self):
        return self.parcel_id or str(self.objectid)


class ParcelPrimaryZoning(models.Model):
    parcel_id = models.TextField(primary_key=True)
    citydistrict = models.TextField(blank=True, null=True)
    landuse = models.TextField(blank=True, null=True)
    acres = models.FloatField(blank=True, null=True)
    jurisdiction = models.TextField(blank=True, null=True)
    county = models.TextField(blank=True, null=True)
    zone_id = models.TextField(blank=True, null=True)
    zone_name = models.TextField(blank=True, null=True)
    waza_general = models.TextField(blank=True, null=True)
    waza_specific = models.TextField(blank=True, null=True)
    percent_of_parcel = models.FloatField(blank=True, null=True)
    overlap_area_sqft = models.FloatField(blank=True, null=True)
    parcel_area_sqft = models.FloatField(blank=True, null=True)
    reference_url = models.TextField(blank=True, null=True)
    waza_spatial_normalization_date = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "parcel_primary_zoning"

    def __str__(self):
        return self.parcel_id


class ParcelZoning(models.Model):
    parcel_id = models.TextField(primary_key=True)
    citydistrict = models.TextField(blank=True, null=True)
    landuse = models.TextField(blank=True, null=True)
    acres = models.FloatField(blank=True, null=True)
    zoning_objectid = models.BigIntegerField(blank=True, null=True)
    jurisdiction = models.TextField(blank=True, null=True)
    county = models.TextField(blank=True, null=True)
    zone_id = models.TextField(blank=True, null=True)
    zone_name = models.TextField(blank=True, null=True)
    waza_general = models.TextField(blank=True, null=True)
    waza_specific = models.TextField(blank=True, null=True)
    reference_url = models.TextField(blank=True, null=True)
    waza_spatial_normalization_date = models.TextField(blank=True, null=True)
    percent_of_parcel = models.FloatField(blank=True, null=True)
    overlap_area_sqft = models.FloatField(blank=True, null=True)
    parcel_area_sqft = models.FloatField(blank=True, null=True)
    rn = models.BigIntegerField(blank=True, null=True)
    is_primary = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "parcel_zoning"


class WazaZoningZone(models.Model):
    source_objectid = models.BigIntegerField(primary_key=True)
    jurisdiction = models.TextField(blank=True, null=True)
    county = models.TextField(blank=True, null=True)
    zone_id = models.TextField(blank=True, null=True)
    zone_name = models.TextField(blank=True, null=True)
    waza_general = models.TextField(blank=True, null=True)
    waza_specific = models.TextField(blank=True, null=True)
    reference_url = models.TextField(blank=True, null=True)
    waza_spatial_normalization_date = models.TextField(blank=True, null=True)
    geometry = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "waza_zoning_zones"


class OpenSkagitParcelZoning(models.Model):
    parcel_id = models.TextField(primary_key=True)
    citydistrict = models.TextField(blank=True, null=True)
    landuse = models.TextField(blank=True, null=True)
    acres = models.FloatField(blank=True, null=True)
    jurisdiction = models.TextField(blank=True, null=True)
    zone_id = models.TextField(blank=True, null=True)
    zone_name = models.TextField(blank=True, null=True)
    waza_general = models.TextField(blank=True, null=True)
    waza_specific = models.TextField(blank=True, null=True)
    percent_of_parcel = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "openskagit_parcel_zoning_view"


class ParcelTaxSummary(models.Model):
    parcel_number = models.TextField(primary_key=True)
    levy_code = models.TextField(blank=True, null=True)
    parcel_tax_year = models.TextField(blank=True, null=True)
    reporting_status = models.TextField(blank=True, null=True)
    agency_name = models.TextField(blank=True, null=True)
    mcag = models.TextField(blank=True, null=True)
    sao_fit_url = models.TextField(blank=True, null=True)
    total_tax = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    pct_of_bill = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "v_parcel_tax_summary"


class ParcelTaxDetail(models.Model):
    parcel_number = models.TextField(primary_key=True)
    levy_code = models.TextField(blank=True, null=True)
    parcel_tax_year = models.TextField(blank=True, null=True)
    levy_year = models.IntegerField(blank=True, null=True)
    levy_short = models.TextField(blank=True, null=True)
    levy_name = models.TextField(blank=True, null=True)
    category = models.TextField(blank=True, null=True)
    rate = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    assessed_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    tax_amount = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    entity_key = models.TextField(blank=True, null=True)
    effective_mcag = models.TextField(blank=True, null=True)
    reporting_status = models.TextField(blank=True, null=True)
    sao_legal_name = models.TextField(blank=True, null=True)
    sao_fit_url = models.TextField(blank=True, null=True)
    review_needed = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "v_parcel_tax_detail"


class SkagitLevyComposition(models.Model):
    levy_code = models.TextField(primary_key=True)
    tax_year = models.IntegerField()
    levy_short = models.TextField()
    levy_name = models.TextField(blank=True, null=True)
    rate = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    category = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "skagit_levy_composition"


class SkagitLevyCrosswalk(models.Model):
    levy_short = models.TextField(primary_key=True)
    levy_name_canonical = models.TextField(blank=True, null=True)
    entity_key = models.TextField()
    mcag = models.TextField(blank=True, null=True)
    reporting_status = models.TextField()
    parent_mcag = models.TextField(blank=True, null=True)
    sao_legal_name = models.TextField(blank=True, null=True)
    review_needed = models.BooleanField(blank=True, null=True)
    sao_fit_url = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "skagit_levy_crosswalk"


class SkagitAgencyTotal(models.Model):
    mcag = models.TextField(primary_key=True)
    county_total = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "skagit_agency_totals"


class SkagitParcelHistory(models.Model):
    parcel_number = models.TextField(primary_key=True)
    tax_year = models.IntegerField()
    value_year = models.IntegerField(blank=True, null=True)
    building_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    land_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    total_value = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    tax_amount = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    fetched_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "skagit_parcel_history"


class SkagitParcelHistoryStatus(models.Model):
    parcel_number = models.TextField(primary_key=True)
    status = models.TextField()
    fetched_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "skagit_parcel_history_status"


class Land(models.Model):
    parcelnumber = models.TextField(blank=True, null=True)
    prop_val_yr = models.TextField(blank=True, null=True)
    land_seg_id = models.TextField(blank=True, null=True)
    land_type = models.TextField(blank=True, null=True)
    appr_meth = models.TextField(blank=True, null=True)
    size_acres = models.TextField(blank=True, null=True)
    size_square_feet = models.TextField(blank=True, null=True)
    effective_front = models.TextField(blank=True, null=True)
    actual_front = models.TextField(blank=True, null=True)
    land_adj_factor = models.TextField(blank=True, null=True)
    adj_value = models.TextField(blank=True, null=True)
    mkt_unit_price = models.TextField(blank=True, null=True)
    market_value = models.TextField(blank=True, null=True)
    open_space_val = models.TextField(blank=True, null=True)
    open_space_use_code_desc = models.TextField(blank=True, null=True)
    ag_unit_price = models.TextField(blank=True, null=True)
    os_appr_meth = models.TextField(blank=True, null=True)
    land_seg_comment = models.TextField(blank=True, null=True)
    size_acres_num = models.FloatField(blank=True, null=True)
    market_value_num = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "land"


class Improvement(models.Model):
    parcelnumber = models.TextField(blank=True, null=True)
    imprv_id = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    building_style = models.TextField(blank=True, null=True)
    comment = models.TextField(blank=True, null=True)
    imprv_val = models.TextField(blank=True, null=True)
    new_const_year = models.TextField(blank=True, null=True)
    tot_living_area = models.TextField(blank=True, null=True)
    segment_id = models.TextField(blank=True, null=True)
    imprv_det_type_cd = models.TextField(blank=True, null=True)
    imprv_det_class_cd = models.TextField(blank=True, null=True)
    imprv_det_meth_cd = models.TextField(blank=True, null=True)
    condition_cd = models.TextField(blank=True, null=True)
    calc_area = models.TextField(blank=True, null=True)
    unit_price = models.TextField(blank=True, null=True)
    dep_pct = models.TextField(blank=True, null=True)
    imprv_det_val = models.TextField(blank=True, null=True)
    constructionstyle = models.TextField(blank=True, null=True)
    foundation = models.TextField(blank=True, null=True)
    exteriorwall = models.TextField(blank=True, null=True)
    roofcovering = models.TextField(blank=True, null=True)
    roofstyle = models.TextField(blank=True, null=True)
    flooring = models.TextField(blank=True, null=True)
    floorconstruction = models.TextField(blank=True, null=True)
    interiorfinish = models.TextField(blank=True, null=True)
    plumbing = models.TextField(blank=True, null=True)
    appliances = models.TextField(blank=True, null=True)
    heatingcooling = models.TextField(blank=True, null=True)
    fireplace = models.TextField(blank=True, null=True)
    rooms = models.TextField(blank=True, null=True)
    bedrooms = models.TextField(blank=True, null=True)
    effective_yr_blt = models.TextField(blank=True, null=True)
    actual_year_built = models.TextField(blank=True, null=True)
    sketchpath = models.TextField(blank=True, null=True)
    imprv_det_type_description = models.TextField(blank=True, null=True)
    imprv_det_class_description = models.TextField(blank=True, null=True)
    condition_description = models.TextField(blank=True, null=True)
    imprv_val_num = models.FloatField(blank=True, null=True)
    living_area_num = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "improvements"


class Sale(models.Model):
    saleid = models.TextField(blank=True, null=True)
    parcel_number = models.TextField(blank=True, null=True)
    account_number = models.TextField(blank=True, null=True)
    seller_name = models.TextField(blank=True, null=True)
    buyer_name = models.TextField(blank=True, null=True)
    sale_price = models.TextField(blank=True, null=True)
    sale_date = models.TextField(blank=True, null=True)
    sale_type = models.TextField(blank=True, null=True)
    recording_number = models.TextField(blank=True, null=True)
    deed_type = models.TextField(blank=True, null=True)
    deed_date = models.TextField(blank=True, null=True)
    reval_area = models.TextField(blank=True, null=True)
    excise_number = models.TextField(blank=True, null=True)
    sale_price_num = models.FloatField(blank=True, null=True)
    sale_date_iso = models.TextField(blank=True, null=True)
    deed_date_iso = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "sales"


class CodeDescription(models.Model):
    source_file = models.TextField()
    code = models.TextField()
    description = models.TextField()

    class Meta:
        managed = False
        db_table = "code_descriptions"


class CodeMapping(models.Model):
    category = models.TextField()
    code = models.TextField()
    description = models.TextField()
    source = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "code_mappings"


class PrimaryUseCode(models.Model):
    code = models.TextField(primary_key=True)
    description = models.TextField()
    source = models.TextField()

    class Meta:
        managed = False
        db_table = "primary_use_codes"
