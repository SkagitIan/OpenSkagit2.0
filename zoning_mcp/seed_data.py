from __future__ import annotations

from dataclasses import dataclass

CODEPUBLISHING_BASE = "https://www.codepublishing.com"

JURISDICTIONS = {
    "skagit_county": {"display_name": "Skagit County", "code_source": "Code Publishing", "zoning_title": "Title 14 Unified Development Code", "source_url": f"{CODEPUBLISHING_BASE}/WA/SkagitCounty/", "extraction_status": "Rural mixed-use table extracted; other tables partial."},
    "mount_vernon": {"display_name": "Mount Vernon", "code_source": "Code Publishing", "zoning_title": "Title 17 Zoning", "source_url": f"{CODEPUBLISHING_BASE}/WA/MountVernon/", "extraction_status": "Source located; allowed-use extraction pending."},
    "burlington": {"display_name": "Burlington", "code_source": "eCode360 PDF", "zoning_title": "Title 17 Comprehensive Zoning Ordinance", "source_url": "https://ecode360.com/BU4372", "extraction_status": "Title 17 use sections extracted from Burlington eCode360 PDF."},
    "sedro_woolley": {"display_name": "Sedro-Woolley", "code_source": "Code Publishing", "zoning_title": "Title 17 Zoning", "source_url": f"{CODEPUBLISHING_BASE}/WA/SedroWoolley/", "extraction_status": "Major residential, commercial, central business, and industrial zones extracted."},
    "anacortes": {"display_name": "Anacortes", "code_source": "Code Publishing", "zoning_title": "Title 19 Unified Development Code", "source_url": f"{CODEPUBLISHING_BASE}/WA/Anacortes/", "extraction_status": "Residential table extracted."},
    "concrete": {"display_name": "Concrete", "code_source": "Code Publishing", "zoning_title": "Title 19 Development Regulations", "source_url": f"{CODEPUBLISHING_BASE}/WA/Concrete/", "extraction_status": "Major land-use table rows extracted."},
    "la_conner": {"display_name": "La Conner", "code_source": "Code Publishing", "zoning_title": "Title 15 Uniform Development Code", "source_url": f"{CODEPUBLISHING_BASE}/WA/LaConner/", "extraction_status": "Source located; extraction pending."},
}

SOURCE_URLS = {
    "skagit_county_14_11": f"{CODEPUBLISHING_BASE}/WA/SkagitCounty/html/SkagitCounty14/SkagitCounty1411.html",
    "skagit_county_14_12": f"{CODEPUBLISHING_BASE}/WA/SkagitCounty/html/SkagitCounty14/SkagitCounty1412.html",
}

ZONE_NAMES = {
    "skagit_county": {
        "RI": "Rural Intermediate",
        "RRV": "Rural Reserve",
        "RVR": "Rural Village Residential",
        "RC": "Rural Center",
        "RVC": "Rural Village Commercial",
        "RVC_ALGER": "Rural Village Commercial - Alger",
        "OSRSI": "Public Open Space of Regional/Statewide Importance",
        "RB": "Rural Business",
        "RFS": "Rural Freeway Service",
        "SSB": "Small Scale Business",
        "NRI": "Natural Resource Industrial",
        "RMI": "Rural Marine Industrial",
        "SRT": "Small Scale Recreation and Tourism",
    },
    "concrete": {
        "R": "Residential",
        "A": "Agriculture",
        "CL": "Commercial Limited",
        "TC": "Town Center",
        "I": "Industrial",
        "P": "Public Land",
        "OS": "Open Space",
    },
    "burlington": {
        "RD": "Residential Detached",
        "RA_1": "Residential Attached 1",
        "RA_2": "Residential Attached 2",
        "MUR_1": "Mixed Use Residential 1",
        "MUR_2": "Mixed Use Residential 2",
        "MUC_1": "Mixed Use Commercial 1",
        "MUC_2": "Mixed Use Commercial 2",
        "CI_1": "Commercial and Industrial 1",
        "CI_2": "Commercial and Industrial 2",
        "PC_1": "Parks and Conservation 1",
        "PC_2": "Parks and Conservation 2",
        "PFT_1": "Public Facilities and Transportation 1",
        "PFT_2": "Public Facilities and Transportation 2",
    },
}

USE_ALIASES = {
    "restaurant": ["cafe", "coffee shop", "coffee stand", "diner", "eating and drinking", "food service"],
    "small_retail_service_business": ["small retail", "shop", "boutique", "service business", "neighborhood retail"],
    "business_professional_office": ["office", "professional office", "business office", "real estate office"],
    "mini_storage": ["self storage", "storage units", "mini storage"],
    "accessory_dwelling_unit": ["adu", "accessory apartment", "mother in law unit", "detached accessory dwelling"],
    "single_family_residence": ["single family", "house", "home", "detached dwelling"],
    "middle_housing_2_to_4_units": ["duplex", "triplex", "fourplex", "middle housing"],
    "multifamily": ["multiunit", "multi-unit", "multiunit building", "multiunit buildings", "apartment", "apartments"],
    "contractor_yards": ["contractor yard", "contractor storage yard", "construction yard"],
    "contractor_yard": ["outdoor storage yard", "outdoor storage yards", "sales lot", "storage yard"],
    "outdoor_storage_yards_and_sales_lots": ["contractor yard", "contractor storage yard", "construction yard", "outdoor storage"],
}


@dataclass(frozen=True)
class SeedRule:
    jurisdiction: str
    source_table: str
    source_url: str
    use_category: str
    use_name: str
    normalized_use_key: str
    zones: dict[str, str]
    notes: str = ""


SKAGIT_RURAL_MIXED_USE_RULES = [
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Residential Uses", "Single-family residence", "single_family_residence", {"RI": "P", "RRV": "P", "RVR": "P", "RC": "X", "RVC": "X", "RVC_ALGER": "X", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Residential Uses", "Accessory dwelling unit", "accessory_dwelling_unit", {"RI": "P", "RRV": "P", "RVR": "P", "RC": "X", "RVC": "X", "RVC_ALGER": "X", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Residential Uses", "Middle housing (2-4 units)", "middle_housing_2_to_4_units", {"RI": "X", "RRV": "X", "RVR": "P", "RC": "X", "RVC": "X", "RVC_ALGER": "X", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Residential Uses", "Loft living quarters", "loft_living_quarters", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Business/professional office", "business_professional_office", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "X", "RVC": "P", "RVC_ALGER": "X", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Family day care provider", "family_day_care_provider", {"RI": "P", "RRV": "P", "RVR": "P", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Mini-storage", "mini_storage", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Outpatient medical and health care service", "outpatient_medical_health_care_service", {"RI": "X", "RRV": "X", "RVR": "HE", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Restaurant", "restaurant", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Small retail and service business", "small_retail_service_business", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Commercial/Retail Uses", "Small-scale production or manufacture", "small_scale_production_manufacture", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "X", "RVC": "AD", "RVC_ALGER": "AD", "OSRSI": "X"}),
    SeedRule("skagit_county", "Table 14.11.020-1", SOURCE_URLS["skagit_county_14_11"], "Storage, Transportation, and Utility Uses", "Vehicle fueling station", "vehicle_fueling_station", {"RI": "X", "RRV": "X", "RVR": "X", "RC": "P", "RVC": "P", "RVC_ALGER": "P", "OSRSI": "X"}),
]

SEED_RULES = SKAGIT_RURAL_MIXED_USE_RULES
