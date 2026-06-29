from __future__ import annotations

from dataclasses import dataclass

CODEPUBLISHING_BASE = "https://www.codepublishing.com"

JURISDICTIONS = {
    "skagit_county": {"display_name": "Skagit County", "code_source": "Code Publishing", "zoning_title": "Title 14 Unified Development Code", "source_url": f"{CODEPUBLISHING_BASE}/WA/SkagitCounty/", "extraction_status": "Rural mixed-use table extracted; other tables partial."},
    "mount_vernon": {"display_name": "Mount Vernon", "code_source": "Code Publishing", "zoning_title": "Title 17 Zoning", "source_url": f"{CODEPUBLISHING_BASE}/WA/MountVernon/", "extraction_status": "Source located; allowed-use extraction pending."},
    "burlington": {"display_name": "Burlington", "code_source": "Code Publishing", "zoning_title": "Title 17 Zoning", "source_url": f"{CODEPUBLISHING_BASE}/WA/Burlington/", "extraction_status": "RA-1, MUR-1, and MUC-1 extracted."},
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
    }
}

USE_ALIASES = {
    "restaurant": ["cafe", "coffee shop", "coffee stand", "diner", "eating and drinking", "food service"],
    "small_retail_service_business": ["small retail", "shop", "boutique", "service business", "neighborhood retail"],
    "business_professional_office": ["office", "professional office", "business office", "real estate office"],
    "mini_storage": ["self storage", "storage units", "mini storage"],
    "accessory_dwelling_unit": ["adu", "accessory apartment", "mother in law unit", "detached accessory dwelling"],
    "single_family_residence": ["single family", "house", "home", "detached dwelling"],
    "middle_housing_2_to_4_units": ["duplex", "triplex", "fourplex", "middle housing"],
    "contractor_yards": ["contractor yard", "contractor storage yard", "construction yard"],
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
