"""
setup_taxtool.py
================
One-shot setup for the taxtool Django app.

1. Creates skagit_parcels, skagit_levy_composition, skagit_levy_crosswalk tables
2. Creates v_parcel_tax_detail and v_parcel_tax_summary views
3. Loads crosswalk (90 hand-coded rows)
4. Loads levy composition from 10yr_levy_mapping.csv
5. Populates skagit_parcels from assessor_rollup (already loaded)
6. Builds data/skagit_agencies.json from 2025schedule01.csv

Run from project root:
    python data/setup_taxtool.py
"""

import os, sys, re, json
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Load .env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not set in .env")
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

LEVY_CSV = DATA_DIR / "10yr_levy_mapping.csv"
SCHEDULE01_CSV = DATA_DIR / "2025schedule01.csv"
AGENCIES_JSON_OUT = DATA_DIR / "skagit_agencies.json"

# ---------------------------------------------------------------------------
# Crosswalk (90 rows, hand-maintained)
# ---------------------------------------------------------------------------

CROSSWALK_ROWS = [
    # (levy_short, levy_name_canonical, entity_key, mcag, reporting_status, parent_mcag, sao_legal_name, review_needed)
    ("STSCH",      "State School Fund",                       "WA_STATE_SCHOOL_1",   None,   "state_levy",            None,   "WA Dept of Revenue",                                            False),
    ("STSCH2",     "State Levy School Part 2",                "WA_STATE_SCHOOL_2",   None,   "state_levy",            None,   "WA Dept of Revenue",                                            False),
    ("STSCHREF",   "State School Refund Fund",                "WA_STATE_SCHOOL_REF", None,   "state_levy",            None,   "WA Dept of Revenue",                                            False),
    ("COUNTYCE",   "Current Expense",                         "SKAGIT_COUNTY",       "0158", "reports_independently", None,   "Skagit County",                                                 False),
    ("COUNTYMH",   "Mental Health/Dev Disability",            "SKAGIT_COUNTY",       "0158", "sub_levy",              "0158", "Skagit County",                                                 False),
    ("COUNTYVR",   "Veterans Relief",                         "SKAGIT_COUNTY",       "0158", "sub_levy",              "0158", "Skagit County",                                                 False),
    ("CONFUT",     "Conservation Futures",                    "SKAGIT_COUNTY",       "0158", "sub_levy",              "0158", "Skagit County",                                                 False),
    ("CORD",       "County Road",                             "SKAGIT_COUNTY",       "0158", "sub_levy",              "0158", "Skagit County",                                                 False),
    ("CORDDIV",    "Road Diversion Fund",                     "SKAGIT_COUNTY",       "0158", "sub_levy",              "0158", "Skagit County",                                                 False),
    ("COMD1",      "Medic I Services",                        "MEDIC1",              "2834", "reports_independently", None,   "Skagit County Emergency Medical Services Commission",           False),
    ("TANAGEN",    "Anacortes General",                       "ANACORTES",           "0628", "reports_independently", None,   "City of Anacortes",                                             False),
    ("TANALIB",    "Anacortes 2001 Library GO Bond",          "ANACORTES",           "0628", "sub_levy",              "0628", "City of Anacortes",                                             False),
    ("TBURGEN",    "Burlington General",                      "BURLINGTON",          "0633", "reports_independently", None,   "City of Burlington",                                            False),
    ("TCONGEN",    "Concrete General",                        "CONCRETE",            "0636", "reports_independently", None,   "Town of Concrete",                                              False),
    ("THAMGEN",    "Hamilton General",                        "HAMILTON",            "0638", "reports_independently", None,   "Town of Hamilton",                                              False),
    ("TLACGEN",    "La Conner General",                       "LACONNER",            "0640", "reports_independently", None,   "Town of La Conner",                                             False),
    ("TLACBOND",   "La Conner Bond",                          "LACONNER",            "0640", "sub_levy",              "0640", "Town of La Conner",                                             False),
    ("TLYMGEN",    "Lyman General",                           "LYMAN",               "0642", "reports_independently", None,   "Town of Lyman",                                                 False),
    ("TMTVGEN",    "Mount Vernon General",                    "MOUNT_VERNON",        "0644", "reports_independently", None,   "City of Mount Vernon",                                          False),
    ("TMTVBOND",   "Mount Vernon Bond",                       "MOUNT_VERNON",        "0644", "sub_levy",              "0644", "City of Mount Vernon",                                          False),
    ("TSEDGEN",    "Sedro-Woolley General",                   "SEDRO_WOOLLEY",       "0647", "reports_independently", None,   "City of Sedro-Woolley",                                         False),
    ("TSEDBOND",   "Sedro-Woolley Bond (Lid Lift)",           "SEDRO_WOOLLEY",       "0647", "sub_levy",              "0647", "City of Sedro-Woolley",                                         False),
    ("SD01101",    "Concrete SD #11 General",                 "CONCRETE_SD",         "2016", "reports_independently", None,   "Concrete School District No. 11",                               False),
    ("SD01102",    "Concrete SD #11 Capital Project",         "CONCRETE_SD",         "2016", "sub_levy",              "2016", "Concrete School District No. 11",                               False),
    ("SD10001",    "Burlington SD #100 General",              "BURLINGTON_SD",       "2014", "reports_independently", None,   "Burlington-Edison School District No. 100",                     False),
    ("SD10002",    "Burlington SD #100 Technology",           "BURLINGTON_SD",       "2014", "sub_levy",              "2014", "Burlington-Edison School District No. 100",                     False),
    ("SD10009",    "Burlington SD #100 General Supp",         "BURLINGTON_SD",       "2014", "sub_levy",              "2014", "Burlington-Edison School District No. 100",                     False),
    ("SD10020",    "Burlington SD #100 Debt Service",         "BURLINGTON_SD",       "2014", "sub_levy",              "2014", "Burlington-Edison School District No. 100",                     False),
    ("SD10101",    "Sedro-Woolley SD #101 General",           "SEDRO_SD",            "2015", "reports_independently", None,   "Sedro-Woolley School District No. 101",                         False),
    ("SD10102",    "Sedro-Woolley SD #101 Technology",        "SEDRO_SD",            "2015", "sub_levy",              "2015", "Sedro-Woolley School District No. 101",                         False),
    ("SD10120",    "Sedro-Woolley SD #101 Debt Service",      "SEDRO_SD",            "2015", "sub_levy",              "2015", "Sedro-Woolley School District No. 101",                         False),
    ("SD10301",    "Anacortes SD #103 General",               "ANACORTES_SD",        "2017", "reports_independently", None,   "Anacortes School District No. 103",                             False),
    ("SD10302",    "Anacortes SD #103 Technology",            "ANACORTES_SD",        "2017", "sub_levy",              "2017", "Anacortes School District No. 103",                             False),
    ("SD10320",    "Anacortes SD #103 Debt Service",          "ANACORTES_SD",        "2017", "sub_levy",              "2017", "Anacortes School District No. 103",                             False),
    ("SD31101",    "La Conner SD #311 General",               "LACONNER_SD",         "2018", "reports_independently", None,   "La Conner School District No. 311",                             False),
    ("SD31102",    "La Conner SD #311 Technology",            "LACONNER_SD",         "2018", "sub_levy",              "2018", "La Conner School District No. 311",                             False),
    ("SD31120",    "La Conner SD #311 Debt Service",          "LACONNER_SD",         "2018", "sub_levy",              "2018", "La Conner School District No. 311",                             False),
    ("SD31701",    "Conway SD #317 General",                  "CONWAY_SD",           "2019", "reports_independently", None,   "Conway School District No. 317",                                False),
    ("SD31702",    "Conway SD #317 Technology",               "CONWAY_SD",           "2019", "sub_levy",              "2019", "Conway School District No. 317",                                False),
    ("SD31720",    "Conway SD #317 Debt Service",             "CONWAY_SD",           "2019", "sub_levy",              "2019", "Conway School District No. 317",                                False),
    ("SD32001",    "Mt. Vernon SD #320 General",              "MOUNTVERNON_SD",      "2020", "reports_independently", None,   "Mount Vernon School District No. 320",                          False),
    ("SD32002",    "Mt. Vernon SD #320 Technology",           "MOUNTVERNON_SD",      "2020", "sub_levy",              "2020", "Mount Vernon School District No. 320",                          False),
    ("SD32020",    "Mt. Vernon SD #320 Debt Service",         "MOUNTVERNON_SD",      "2020", "sub_levy",              "2020", "Mount Vernon School District No. 320",                          False),
    ("SD33001",    "Darrington SD #330 General",              "DARRINGTON_SD",       "2037", "reports_independently", None,   "Darrington School District No. 330",                            False),
    ("SD33002",    "Darrington SD #330 Transportation",       "DARRINGTON_SD",       "2037", "sub_levy",              "2037", "Darrington School District No. 330",                            False),
    ("SD33003",    "Darrington SD #330 Capital Project",      "DARRINGTON_SD",       "2037", "sub_levy",              "2037", "Darrington School District No. 330",                            False),
    ("SD33020",    "Darrington SD #330 Bond Fund",            "DARRINGTON_SD",       "2037", "sub_levy",              "2037", "Darrington School District No. 330",                            False),
    ("LIBLAC",     "Library District #1 La Conner",           "LACONNER_LIB",        "0454", "reports_independently", None,   "La Conner Rural Partial County Library District",               False),
    ("LIBDAR",     "Darrington Rural Library",                "DARRINGTON_LIB",      "1143", "reports_independently", None,   "Darrington Rural Partial County Library District",              False),
    ("LIBUSP",     "Upper Skagit Library",                    "UPPER_SKAGIT_LIB",    "2922", "reports_independently", None,   "Upper Rural Skagit Library District",                           False),
    ("LIBCEN",     "Central Skagit Rural Library",            "CENTRAL_SKAGIT_LIB",  "3101", "reports_independently", None,   "Central Skagit Rural Partial - County Library District",        False),
    ("H0121",      "Hospital #1 2004 GO Bond",                "HOSP1",               "1487", "reports_independently", None,   "Skagit County Public Hospital District No. 1",                  False),
    ("H0224",      "Hospital Dist #2 2012 UTGO",              "HOSP2",               "1488", "sub_levy",              "1488", "Skagit County Public Hospital District No. 2",                  False),
    ("H0225",      "Hospital Dist #2 1996 UTGO",              "HOSP2",               "1488", "sub_levy",              "1488", "Skagit County Public Hospital District No. 2",                  False),
    ("H0227",      "Hospital Dist #2 1996 LTGO",              "HOSP2",               "1488", "reports_independently", None,   "Skagit County Public Hospital District No. 2",                  False),
    ("H30408",     "Hospital #304 Annual Tax Levy",           "HOSP304",             "1489", "reports_independently", None,   "Skagit County Public Hospital District No. 304",                False),
    ("F0101",      "Fire District 1",                         "FIRE1",               "1281", "reports_independently", None,   "Skagit County Fire Protection District No. 1",                  False),
    ("F0201",      "Fire District 2",                         "FIRE2",               "1282", "reports_independently", None,   "Skagit County Fire Protection District No. 2",                  False),
    ("F0301",      "Fire District 3",                         "FIRE3",               "1283", "reports_independently", None,   "Skagit County Fire Protection District No. 3",                  False),
    ("F0401",      "Fire District 4",                         "FIRE4",               "1284", "reports_independently", None,   "Skagit County Fire Protection District No. 4",                  False),
    ("F0470",      "Fire District 4 Pension Fund",            "FIRE4",               "1284", "sub_levy",              "1284", "Skagit County Fire Protection District No. 4",                  False),
    ("F0501",      "Fire District 5",                         "FIRE5",               "1285", "reports_independently", None,   "Skagit County Fire Protection District No. 5",                  False),
    ("F0601",      "Fire District 6",                         "FIRE6",               "1286", "reports_independently", None,   "Skagit County Fire Protection District No. 6",                  False),
    ("F0701",      "Fire District 7 (Lake Cavanaugh)",        "FIRE7",               "0366", "reports_independently", None,   "Skagit County Fire Protection District No. 7",                  False),
    ("F0801",      "Fire District 8",                         "FIRE8",               "1287", "reports_independently", None,   "Skagit County Fire Protection District No. 8",                  False),
    ("F0901",      "Fire District 9 (Big Lake)",              "FIRE9",               "1288", "reports_independently", None,   "Skagit County Fire Protection District No. 9",                  False),
    ("F0920",      "Fire District 9 Bond",                    "FIRE9",               "1288", "sub_levy",              "1288", "Skagit County Fire Protection District No. 9",                  False),
    ("F1001",      "Fire District 10",                        "FIRE10",              "2571", "reports_independently", None,   "Skagit County Fire Protection District No. 10",                 False),
    ("F1101",      "Fire District 11 (Mt. Erie)",             "FIRE11",              "2572", "reports_independently", None,   "Skagit County Fire Protection District No. 11",                 False),
    ("F1201",      "Fire District 12",                        "FIRE12",              "2573", "reports_independently", None,   "Skagit County Fire Protection District No. 12",                 False),
    ("F1301",      "Fire District 13",                        "FIRE13",              "2574", "reports_independently", None,   "Skagit County Fire District No. 13",                            False),
    ("F1401",      "Fire District 14",                        "FIRE14",              "2204", "reports_independently", None,   "Skagit County Fire Protection District No. 14",                 False),
    ("F1501",      "Fire District 15 (Lake McMurray)",        "FIRE15",              "2576", "reports_independently", None,   "Skagit County Fire Protection District No. 15",                 False),
    ("F1601",      "Fire District 16",                        "FIRE16",              "2205", "reports_independently", None,   "Skagit County Fire Protection District No. 16",                 False),
    ("F1620",      "Fire District 16 Bond",                   "FIRE16",              "2205", "sub_levy",              "2205", "Skagit County Fire Protection District No. 16",                 False),
    ("F1701",      "Fire District 17",                        "FIRE17",              "2578", "reports_independently", None,   "Skagit County Fire Protection District No. 17",                 False),
    ("F1901",      "Fire District 19",                        "FIRE19",              "2580", "reports_independently", None,   "Skagit County Fire Protection District No. 19",                 False),
    ("F2401",      "Fire District 24",                        "FIRE24",              None,   "needs_review",          None,   "UNKNOWN - verify vs SCRFA merger",                              True),
    ("F24EMS",     "Fire District 24 EMS Levy",               "FIRE24_EMS",          None,   "needs_review",          None,   "UNKNOWN - verify vs SCRFA merger",                              True),
    ("SCRFA 1019", "Regional Fire Authority 1",               "SCRFA",               "3293", "reports_independently", None,   "Skagit County Regional Fire Authority",                         False),
    ("P0108",      "Port 1 Anacortes",                        "PORT_ANACORTES",      "1756", "reports_independently", None,   "Port of Anacortes",                                             False),
    ("P0201",      "Port 2 Skagit General Fund",              "PORT_SKAGIT",         "1757", "reports_independently", None,   "Port of Skagit County",                                         False),
    ("P0209",      "Port 2 Skagit IDD",                       "PORT_SKAGIT",         "1757", "sub_levy",              "1757", "Port of Skagit County",                                         False),
    ("FIDPK",      "Fidalgo Park & Recreation District",      "FIDALGO_POOL",        None,   "needs_review",          None,   "UNKNOWN - verify MCAG",                                         True),
    ("CEM1",       "Cemetery District 1",                     "CEM1",                "0059", "reports_independently", None,   "Skagit County Cemetery District No. 1",                         False),
    ("CEM2",       "Cemetery District 2 (Fern Hill)",         "CEM2",                "0060", "reports_independently", None,   "Skagit County Cemetery District No. 2",                         False),
    ("CEM3",       "Cemetery District 3 (Edens)",             "CEM3",                "0061", "reports_independently", None,   "Skagit County Cemetery District No. 3",                         False),
    ("CEM4",       "Cemetery District 4",                     "CEM4",                "2470", "reports_independently", None,   "Skagit County Cemetery District No. 4",                         False),
    ("CEM5",       "Cemetery District 5 (Forest Park)",       "CEM5",                "0287", "reports_independently", None,   "Skagit County Cemetery District No. 5",                         False),
    ("CEM6",       "Cemetery District 6",                     "CEM6",                "2894", "reports_independently", None,   "Skagit County Cemetery District No. 6",                         False),
    ("X0002",      "DO NOT USE",                              "SKIP",                None,   "administrative",        None,   "Administrative placeholder",                                    False),
]

# All Skagit MCAGs with common names, types, and blurbs
SKAGIT_MCAGS = {
    "0158": {"entity_key": "SKAGIT_COUNTY",      "common_name": "Skagit County",                    "type": "county",   "blurb": "Provides county-wide services including courts, elections, roads, public health, sheriff, and social services."},
    "2834": {"entity_key": "MEDIC1",             "common_name": "Skagit County Medic 1",            "type": "ems",      "blurb": "Operates paramedic and advanced life support emergency medical services throughout Skagit County."},
    "0628": {"entity_key": "ANACORTES",          "common_name": "City of Anacortes",                "type": "city",     "blurb": "Provides city services to Anacortes residents including police, fire, parks, and utilities."},
    "0633": {"entity_key": "BURLINGTON",         "common_name": "City of Burlington",               "type": "city",     "blurb": "Provides city services to Burlington residents including police, streets, parks, and planning."},
    "0636": {"entity_key": "CONCRETE",           "common_name": "Town of Concrete",                 "type": "city",     "blurb": "Provides municipal services to the Town of Concrete including water, streets, and local government."},
    "0638": {"entity_key": "HAMILTON",           "common_name": "Town of Hamilton",                 "type": "city",     "blurb": "Provides municipal services to the small Town of Hamilton on the Skagit River."},
    "0640": {"entity_key": "LACONNER",           "common_name": "Town of La Conner",                "type": "city",     "blurb": "Provides municipal services to the Town of La Conner including planning, streets, and local government."},
    "0642": {"entity_key": "LYMAN",              "common_name": "Town of Lyman",                    "type": "city",     "blurb": "Provides municipal services to the small Town of Lyman."},
    "0644": {"entity_key": "MOUNT_VERNON",       "common_name": "City of Mount Vernon",             "type": "city",     "blurb": "Provides city services to Mount Vernon residents including police, fire, parks, planning, and streets."},
    "0647": {"entity_key": "SEDRO_WOOLLEY",      "common_name": "City of Sedro-Woolley",            "type": "city",     "blurb": "Provides city services to Sedro-Woolley residents including police, streets, parks, and planning."},
    "2014": {"entity_key": "BURLINGTON_SD",      "common_name": "Burlington-Edison Schools",        "type": "school",   "blurb": "Operates Burlington-Edison School District, serving students in Burlington and Edison."},
    "2015": {"entity_key": "SEDRO_SD",           "common_name": "Sedro-Woolley Schools",            "type": "school",   "blurb": "Operates Sedro-Woolley School District, serving students in Sedro-Woolley and surrounding communities."},
    "2016": {"entity_key": "CONCRETE_SD",        "common_name": "Concrete Schools",                 "type": "school",   "blurb": "Operates Concrete School District, serving students in Concrete and the upper Skagit Valley."},
    "2017": {"entity_key": "ANACORTES_SD",       "common_name": "Anacortes Schools",                "type": "school",   "blurb": "Operates Anacortes School District, serving students on Fidalgo Island."},
    "2018": {"entity_key": "LACONNER_SD",        "common_name": "La Conner Schools",                "type": "school",   "blurb": "Operates La Conner School District, serving students in La Conner and Swinomish area."},
    "2019": {"entity_key": "CONWAY_SD",          "common_name": "Conway Schools",                   "type": "school",   "blurb": "Operates Conway School District, serving students in the Conway and Fir Island area."},
    "2020": {"entity_key": "MOUNTVERNON_SD",     "common_name": "Mount Vernon Schools",             "type": "school",   "blurb": "Operates Mount Vernon School District, the largest district in Skagit County."},
    "2037": {"entity_key": "DARRINGTON_SD",      "common_name": "Darrington Schools",               "type": "school",   "blurb": "Operates Darrington School District, serving students in the Darrington community."},
    "0454": {"entity_key": "LACONNER_LIB",       "common_name": "La Conner Library",                "type": "library",  "blurb": "Provides public library services to La Conner and surrounding communities."},
    "1143": {"entity_key": "DARRINGTON_LIB",     "common_name": "Darrington Library",               "type": "library",  "blurb": "Provides public library services to Darrington and surrounding communities."},
    "2922": {"entity_key": "UPPER_SKAGIT_LIB",   "common_name": "Upper Skagit Library",             "type": "library",  "blurb": "Provides public library services to upper Skagit communities including Concrete and Rockport."},
    "3101": {"entity_key": "CENTRAL_SKAGIT_LIB", "common_name": "Central Skagit Library",           "type": "library",  "blurb": "Provides public library services to central Skagit County communities."},
    "1487": {"entity_key": "HOSP1",              "common_name": "Skagit Regional Health",           "type": "hospital", "blurb": "Operates Skagit Regional Health, the main hospital system serving Skagit County."},
    "1488": {"entity_key": "HOSP2",              "common_name": "Island Health",                    "type": "hospital", "blurb": "Operates Island Health (formerly Skagit County Public Hospital District No. 2), serving Anacortes and the islands."},
    "1489": {"entity_key": "HOSP304",            "common_name": "United General District 304",      "type": "hospital", "blurb": "Operates United General District 304, providing hospital services to upper Skagit communities."},
    "1281": {"entity_key": "FIRE1",              "common_name": "Fire District 1",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 1."},
    "1282": {"entity_key": "FIRE2",              "common_name": "Fire District 2",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 2."},
    "1283": {"entity_key": "FIRE3",              "common_name": "Fire District 3",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 3."},
    "1284": {"entity_key": "FIRE4",              "common_name": "Fire District 4",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 4."},
    "1285": {"entity_key": "FIRE5",              "common_name": "Fire District 5",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 5."},
    "1286": {"entity_key": "FIRE6",              "common_name": "Fire District 6",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 6."},
    "0366": {"entity_key": "FIRE7",              "common_name": "Fire District 7 (Lake Cavanaugh)", "type": "fire",     "blurb": "Provides fire protection for the Lake Cavanaugh area."},
    "1287": {"entity_key": "FIRE8",              "common_name": "Fire District 8",                  "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 8."},
    "1288": {"entity_key": "FIRE9",              "common_name": "Fire District 9 (Big Lake)",       "type": "fire",     "blurb": "Provides fire protection for the Big Lake area."},
    "2571": {"entity_key": "FIRE10",             "common_name": "Fire District 10",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 10."},
    "2572": {"entity_key": "FIRE11",             "common_name": "Fire District 11 (Mt. Erie)",      "type": "fire",     "blurb": "Provides fire protection for the Mt. Erie area."},
    "2573": {"entity_key": "FIRE12",             "common_name": "Fire District 12",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 12."},
    "2574": {"entity_key": "FIRE13",             "common_name": "Fire District 13",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 13."},
    "2204": {"entity_key": "FIRE14",             "common_name": "Fire District 14",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 14."},
    "2576": {"entity_key": "FIRE15",             "common_name": "Fire District 15 (Lake McMurray)", "type": "fire",     "blurb": "Provides fire protection for the Lake McMurray area."},
    "2205": {"entity_key": "FIRE16",             "common_name": "Fire District 16",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 16."},
    "2578": {"entity_key": "FIRE17",             "common_name": "Fire District 17",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 17."},
    "2580": {"entity_key": "FIRE19",             "common_name": "Fire District 19",                 "type": "fire",     "blurb": "Provides fire protection and emergency response services for Fire District 19."},
    "3293": {"entity_key": "SCRFA",              "common_name": "Skagit Regional Fire Authority",   "type": "fire",     "blurb": "A consolidated fire agency serving multiple districts in Skagit County."},
    "1756": {"entity_key": "PORT_ANACORTES",     "common_name": "Port of Anacortes",                "type": "port",     "blurb": "Operates the Port of Anacortes, including the oil refinery terminal, marina, and industrial properties."},
    "1757": {"entity_key": "PORT_SKAGIT",        "common_name": "Port of Skagit County",            "type": "port",     "blurb": "Operates the Port of Skagit County, supporting industrial, commercial, and agricultural uses."},
    "0059": {"entity_key": "CEM1",               "common_name": "Cemetery District 1",              "type": "cemetery", "blurb": "Maintains public cemeteries in Cemetery District 1."},
    "0060": {"entity_key": "CEM2",               "common_name": "Cemetery District 2 (Fern Hill)",  "type": "cemetery", "blurb": "Maintains public cemeteries in Cemetery District 2 (Fern Hill)."},
    "0061": {"entity_key": "CEM3",               "common_name": "Cemetery District 3 (Edens)",      "type": "cemetery", "blurb": "Maintains public cemeteries in Cemetery District 3 (Edens)."},
    "2470": {"entity_key": "CEM4",               "common_name": "Cemetery District 4",              "type": "cemetery", "blurb": "Maintains public cemeteries in Cemetery District 4."},
    "0287": {"entity_key": "CEM5",               "common_name": "Cemetery District 5 (Forest Park)","type": "cemetery", "blurb": "Maintains Forest Park Cemetery (Cemetery District 5)."},
    "2894": {"entity_key": "CEM6",               "common_name": "Cemetery District 6",              "type": "cemetery", "blurb": "Maintains public cemeteries in Cemetery District 6."},
}

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

DDL_TABLES = """
CREATE TABLE IF NOT EXISTS skagit_parcels (
    aid                         TEXT,
    parcel_number               TEXT,
    account_number              TEXT,
    legal_description           TEXT,
    situs_street_number         TEXT,
    situs_street_name           TEXT,
    situs_city_state_zip        TEXT,
    old_street_number           TEXT,
    old_street_name             TEXT,
    old_city_state_zip          TEXT,
    owner_name                  TEXT,
    owner_add_1                 TEXT,
    owner_add_2                 TEXT,
    owner_add_3                 TEXT,
    owner_city                  TEXT,
    owner_state                 TEXT,
    owner_zip                   TEXT,
    exemptions                  TEXT,
    neighborhood_code           TEXT,
    building_value              NUMERIC,
    land_use                    TEXT,
    impr_land_value             NUMERIC,
    unimpr_land_value           NUMERIC,
    timber_land_value           NUMERIC,
    assessed_value              NUMERIC,
    taxable_value               NUMERIC,
    total_market_value          NUMERIC,
    acres                       NUMERIC,
    sale_date                   DATE,
    sale_price                  NUMERIC,
    sale_deed_type              TEXT,
    total_taxes                 NUMERIC,
    year_built                  NUMERIC,
    living_area                 NUMERIC,
    tot_special_assessments     NUMERIC,
    general_taxes               NUMERIC,
    inactive_date               DATE,
    buildingstyle               TEXT,
    foundation                  TEXT,
    exterior_walls              TEXT,
    roof_covering               TEXT,
    roof_style                  TEXT,
    floor_covering              TEXT,
    floor_construction          TEXT,
    interior_finish             TEXT,
    plumbing                    TEXT,
    garagesqft                  NUMERIC,
    heat_air_cond               TEXT,
    fireplace                   TEXT,
    finishedbasement            NUMERIC,
    number_of_bedrooms          NUMERIC,
    eff_year_built              NUMERIC,
    unfinishedbasement          NUMERIC,
    fire_district               TEXT,
    school_district             TEXT,
    city_district               TEXT,
    unit                        TEXT,
    levy_code                   TEXT,
    current_use_adjustment      NUMERIC,
    tide_land_value             NUMERIC,
    senior_exemption_adjustment NUMERIC,
    township                    TEXT,
    range                       TEXT,
    section                     TEXT,
    quarter_section             TEXT,
    tax_year                    TEXT,
    appraisal_year              TEXT,
    utilities                   TEXT,
    tax_statement_taxable_value NUMERIC,
    proptype                    TEXT,
    hasseptic                   TEXT,
    loaded_at                   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skagit_parcels_parcel_number ON skagit_parcels (parcel_number);
CREATE INDEX IF NOT EXISTS idx_skagit_parcels_levy_code     ON skagit_parcels (levy_code);
CREATE INDEX IF NOT EXISTS idx_skagit_parcels_owner_name    ON skagit_parcels (owner_name);
CREATE INDEX IF NOT EXISTS idx_skagit_parcels_situs         ON skagit_parcels (situs_street_name, situs_street_number);

CREATE TABLE IF NOT EXISTS skagit_levy_composition (
    levy_code   TEXT        NOT NULL,
    tax_year    INT         NOT NULL,
    levy_short  TEXT        NOT NULL,
    levy_name   TEXT,
    rate        NUMERIC(12,6),
    category    TEXT,
    PRIMARY KEY (levy_code, tax_year, levy_short)
);

CREATE INDEX IF NOT EXISTS idx_levy_comp_year ON skagit_levy_composition (tax_year);

CREATE TABLE IF NOT EXISTS skagit_levy_crosswalk (
    levy_short          TEXT        PRIMARY KEY,
    levy_name_canonical TEXT,
    entity_key          TEXT        NOT NULL,
    mcag                TEXT,
    reporting_status    TEXT        NOT NULL,
    parent_mcag         TEXT,
    sao_legal_name      TEXT,
    review_needed       BOOLEAN     DEFAULT FALSE,
    sao_fit_url         TEXT        GENERATED ALWAYS AS (
        CASE WHEN mcag IS NOT NULL
             THEN 'https://portal.sao.wa.gov/FIT/ReportsByEntity?mcag=' || mcag
             ELSE NULL
        END
    ) STORED
);
"""

DDL_VIEWS = """
CREATE OR REPLACE VIEW v_parcel_tax_detail AS
SELECT
    p.parcel_number,
    p.levy_code,
    p.tax_year                                                      AS parcel_tax_year,
    lc.tax_year                                                     AS levy_year,
    lc.levy_short,
    lc.levy_name,
    lc.category,
    lc.rate,
    p.assessed_value,
    ROUND((lc.rate * p.assessed_value / 1000.0)::NUMERIC, 2)       AS tax_amount,
    x.entity_key,
    COALESCE(x.mcag, x.parent_mcag)                                AS effective_mcag,
    x.reporting_status,
    x.sao_legal_name,
    x.sao_fit_url,
    x.review_needed
FROM skagit_parcels p
JOIN skagit_levy_composition lc
    ON  lc.levy_code = p.levy_code
    AND lc.tax_year = (
        SELECT MAX(lc2.tax_year)
        FROM skagit_levy_composition lc2
        WHERE lc2.levy_code = p.levy_code
          AND lc2.tax_year <= COALESCE(p.tax_year::INT, EXTRACT(YEAR FROM NOW())::INT)
    )
JOIN skagit_levy_crosswalk x
    ON x.levy_short = lc.levy_short
WHERE lc.levy_short != 'X0002'
  AND x.reporting_status != 'administrative'
  AND p.inactive_date IS NULL;

CREATE OR REPLACE VIEW v_parcel_tax_summary AS
SELECT
    parcel_number,
    levy_code,
    parcel_tax_year,
    reporting_status,
    sao_legal_name                      AS agency_name,
    effective_mcag                      AS mcag,
    sao_fit_url,
    SUM(tax_amount)                     AS total_tax,
    ROUND(
        100.0 * SUM(tax_amount)
        / NULLIF(SUM(SUM(tax_amount)) OVER (PARTITION BY parcel_number), 0),
        1
    )                                   AS pct_of_bill
FROM v_parcel_tax_detail
GROUP BY
    parcel_number, levy_code, parcel_tax_year,
    reporting_status, sao_legal_name, effective_mcag, sao_fit_url
ORDER BY total_tax DESC;
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_levy_code(val):
    """Zero-pad numeric part to 4 digits, preserve alpha suffix (e.g. 905AG -> 0905AG)."""
    if not val:
        return val
    s = str(val).strip()
    m = re.match(r'^(\d+)([A-Za-z]*)$', s)
    if m:
        num, suffix = m.group(1), m.group(2).upper()
        return num.zfill(4) + suffix
    return s


def parse_amount(val):
    """Strip $ and commas from SAO FIT amount strings like '$3,835,822.20'."""
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Step 1: Create schema
# ---------------------------------------------------------------------------

def create_schema(engine):
    print("Creating tables and indexes...")
    with engine.begin() as conn:
        for stmt in DDL_TABLES.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    print("Creating views...")
    with engine.begin() as conn:
        for stmt in DDL_VIEWS.split(";\n\n"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    print("  Schema ready.")


# ---------------------------------------------------------------------------
# Step 2: Load crosswalk
# ---------------------------------------------------------------------------

def load_crosswalk(engine):
    print("Loading crosswalk (90 rows)...")
    cols = ["levy_short", "levy_name_canonical", "entity_key", "mcag",
            "reporting_status", "parent_mcag", "sao_legal_name", "review_needed"]
    df = pd.DataFrame(CROSSWALK_ROWS, columns=cols)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE skagit_levy_crosswalk"))
    df.to_sql("skagit_levy_crosswalk", engine, if_exists="append", index=False)
    print(f"  {len(df)} rows -> skagit_levy_crosswalk")


# ---------------------------------------------------------------------------
# Step 3: Load levy composition
# ---------------------------------------------------------------------------

def load_levy_composition(engine):
    print(f"Loading levy composition from {LEVY_CSV.name}...")
    df = pd.read_csv(LEVY_CSV, header=None, dtype=str)
    df.columns = ["levy_code", "tax_year", "levy_short", "levy_name", "rate", "category"]

    df = df[df["levy_code"].notna()].copy()
    df["levy_code"] = df["levy_code"].apply(normalize_levy_code)
    df["levy_short"] = df["levy_short"].str.strip()
    df["tax_year"] = pd.to_numeric(df["tax_year"], errors="coerce").astype("Int64")
    df["rate"] = pd.to_numeric(df["rate"], errors="coerce")
    df = df[df["levy_short"] != "X0002"].copy()

    # Drop duplicates on the primary key columns (CSV may have repeated rows)
    before = len(df)
    df = df.drop_duplicates(subset=["levy_code", "tax_year", "levy_short"], keep="last")
    if len(df) < before:
        print(f"  Dropped {before - len(df)} duplicate rows")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE skagit_levy_composition"))
    df.to_sql("skagit_levy_composition", engine, if_exists="append", index=False, chunksize=1000)
    print(f"  {len(df):,} rows -> skagit_levy_composition")
    print(f"  Years: {sorted(df['tax_year'].dropna().unique().tolist())}")
    print(f"  Unique levy codes: {df['levy_code'].nunique()}")


# ---------------------------------------------------------------------------
# Step 4: Populate skagit_parcels from assessor_rollup
# ---------------------------------------------------------------------------

def populate_parcels(engine):
    print("Populating skagit_parcels from assessor_rollup...")

    # Check assessor_rollup columns
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'assessor_rollup' ORDER BY ordinal_position"
        ))
        ar_cols = {row[0] for row in result.fetchall()}

    if not ar_cols:
        print("  ERROR: assessor_rollup table not found. Run import_assessor first.")
        return

    print(f"  assessor_rollup has {len(ar_cols)} columns")

    # Use _num variants for NUMERIC columns where available
    def col(name, cast=None, fallback=None):
        num = f"{name}_num"
        if num in ar_cols:
            src = f'"{num}"'
        elif name in ar_cols:
            src = f'"{name}"'
        elif fallback:
            src = fallback
        else:
            src = "NULL"
        if cast:
            return f"{src}::{cast}"
        return src

    # Levy code normalization in SQL: zero-pad numeric part to 4 chars
    levy_expr = """
        CASE
            WHEN levy_code ~ '^[0-9]+[A-Za-z]*$' THEN
                LPAD(regexp_replace(levy_code, '[^0-9]', '', 'g'), 4, '0')
                || upper(regexp_replace(levy_code, '^[0-9]+', ''))
            ELSE levy_code
        END
    """

    # inactive_date and sale_date are TEXT in assessor_rollup (import_assessor stores them as text)
    inactive_date_expr = 'NULLIF("inactive_date", \'\')::DATE' if "inactive_date" in ar_cols else "NULL"
    # sale_date_iso is the normalized ISO date added by import_assessor
    sale_date_expr = 'NULLIF("sale_date_iso", \'\')::DATE' if "sale_date_iso" in ar_cols else 'NULLIF("sale_date", \'\')::DATE' if "sale_date" in ar_cols else "NULL"

    insert_sql = f"""
        INSERT INTO skagit_parcels (
            aid, parcel_number, account_number, legal_description,
            situs_street_number, situs_street_name, situs_city_state_zip,
            old_street_number, old_street_name, old_city_state_zip,
            owner_name, owner_add_1, owner_add_2, owner_add_3,
            owner_city, owner_state, owner_zip,
            exemptions, neighborhood_code,
            building_value, land_use,
            impr_land_value, unimpr_land_value, timber_land_value,
            assessed_value, taxable_value, total_market_value, acres,
            sale_date, sale_price, sale_deed_type,
            total_taxes, year_built, living_area,
            tot_special_assessments, general_taxes,
            inactive_date,
            buildingstyle, foundation, exterior_walls,
            roof_covering, roof_style, floor_covering, floor_construction,
            interior_finish, plumbing, garagesqft, heat_air_cond,
            fireplace, finishedbasement, number_of_bedrooms, eff_year_built,
            unfinishedbasement,
            fire_district, school_district, city_district, unit,
            levy_code,
            current_use_adjustment, tide_land_value, senior_exemption_adjustment,
            township, range, section, quarter_section,
            tax_year, appraisal_year, utilities, tax_statement_taxable_value,
            proptype, hasseptic
        )
        SELECT
            "aid", "parcel_number", "account_number", "legal_description",
            "situs_street_number", "situs_street_name", "situs_city_state_zip",
            "old_street_number", "old_street_name", "old_city_state_zip",
            "owner_name", "owner_add_1", "owner_add_2", "owner_add_3",
            "owner_city", "owner_state", "owner_zip",
            "exemptions", "neighborhood_code",
            {col('building_value', 'NUMERIC')}, "land_use",
            {col('impr_land_value', 'NUMERIC')}, {col('unimpr_land_value', 'NUMERIC')}, {col('timber_land_value', 'NUMERIC')},
            {col('assessed_value', 'NUMERIC')}, {col('taxable_value', 'NUMERIC')}, {col('total_market_value', 'NUMERIC')}, {col('acres', 'NUMERIC')},
            {sale_date_expr}, {col('sale_price', 'NUMERIC')}, "sale_deed_type",
            NULLIF("total_taxes", '')::NUMERIC, NULLIF("year_built", '')::NUMERIC, NULLIF("living_area", '')::NUMERIC,
            NULLIF("tot_special_assessments", '')::NUMERIC, NULLIF("general_taxes", '')::NUMERIC,
            {inactive_date_expr},
            "buildingstyle", "foundation", "exterior_walls",
            "roof_covering", "roof_style", "floor_covering", "floor_construction",
            "interior_finish", "plumbing",
            NULLIF("garagesqft", '')::NUMERIC, "heat_air_cond",
            "fireplace",
            NULLIF("finishedbasement", '')::NUMERIC, NULLIF("number_of_bedrooms", '')::NUMERIC, NULLIF("eff_year_built", '')::NUMERIC,
            NULLIF("unfinishedbasement", '')::NUMERIC,
            "fire_district", "school_district", "city_district", "unit",
            {levy_expr},
            NULLIF("current_use_adjustment", '')::NUMERIC, NULLIF("tide_land_value", '')::NUMERIC, NULLIF("senior_exemption_adjustment", '')::NUMERIC,
            "township", "range", "section", "quarter_section",
            "tax_year", "appraisal_year", "utilities",
            NULLIF("tax_statement_taxable_value", '')::NUMERIC,
            "proptype", "hasseptic"
        FROM assessor_rollup
    """

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE skagit_parcels"))
        result = conn.execute(text(insert_sql))
        print(f"  {result.rowcount:,} rows -> skagit_parcels")

    # Quick check
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*), COUNT(CASE WHEN inactive_date IS NULL THEN 1 END) "
            "FROM skagit_parcels"
        )).fetchone()
        print(f"  Total: {row[0]:,}, Active (no inactive_date): {row[1]:,}")

        # Sample levy codes
        sample = conn.execute(text(
            "SELECT DISTINCT levy_code FROM skagit_parcels WHERE levy_code IS NOT NULL LIMIT 5"
        )).fetchall()
        print(f"  Sample levy codes: {[r[0] for r in sample]}")


# ---------------------------------------------------------------------------
# Step 5: Diagnostics
# ---------------------------------------------------------------------------

def run_diagnostics(engine):
    print("\n--- Diagnostics ---")
    with engine.connect() as conn:
        # Unmatched levy codes
        result = conn.execute(text("""
            SELECT DISTINCT p.levy_code
            FROM skagit_parcels p
            WHERE NOT EXISTS (
                SELECT 1 FROM skagit_levy_composition lc WHERE lc.levy_code = p.levy_code
            ) AND p.levy_code IS NOT NULL
            LIMIT 10
        """))
        unmatched = [r[0] for r in result.fetchall()]
        if unmatched:
            print(f"  Levy codes in parcels NOT in composition: {unmatched}")
        else:
            print("  All parcel levy codes found in composition OK")

        # Unmatched levy_shorts
        result = conn.execute(text("""
            SELECT DISTINCT lc.levy_short
            FROM skagit_levy_composition lc
            WHERE NOT EXISTS (
                SELECT 1 FROM skagit_levy_crosswalk x WHERE x.levy_short = lc.levy_short
            )
            LIMIT 10
        """))
        unmatched_shorts = [r[0] for r in result.fetchall()]
        if unmatched_shorts:
            print(f"  levy_shorts in composition NOT in crosswalk: {unmatched_shorts}")
        else:
            print("  All levy_shorts found in crosswalk OK")

        # Sample parcel breakdown
        sample_parcel = conn.execute(text("""
            SELECT parcel_number FROM skagit_parcels
            WHERE inactive_date IS NULL AND levy_code IS NOT NULL
            AND assessed_value > 0
            LIMIT 1
        """)).fetchone()

        if sample_parcel:
            pnum = sample_parcel[0]
            rows = conn.execute(text(f"""
                SELECT parcel_number, levy_short, levy_name, rate, tax_amount,
                       reporting_status, sao_legal_name, effective_mcag
                FROM v_parcel_tax_detail
                WHERE parcel_number = '{pnum}'
                ORDER BY tax_amount DESC
            """)).fetchall()
            if rows:
                total = sum(r[4] or 0 for r in rows)
                print(f"\n  Sample breakdown for parcel {pnum} (total ${total:.2f}):")
                for r in rows[:6]:
                    print(f"    {r[1]:12s} {r[5]:25s} ${r[4]:.2f}")
            else:
                print(f"  WARNING: No rows in v_parcel_tax_detail for parcel {pnum}")
                print("           This usually means levy_code normalization didn't match composition.")


# ---------------------------------------------------------------------------
# Step 6: Build skagit_agencies.json from 2025schedule01.csv
# ---------------------------------------------------------------------------

# BARSAccountName keyword -> expenditure category
EXP_CATEGORY_MAP = [
    ("Public Safety",          ["police", "fire", "emergency", "law enforcement", "jail", "corrections", "safety", "ems", "dispatch", "911"]),
    ("Teaching & Learning",    ["instruction", "teaching", "learning", "classroom", "curriculum", "special education", "early childhood"]),
    ("Support Services",       ["support services", "administration", "superintendent", "principal", "counseling", "library media", "technology", "food service", "transportation"]),
    ("Transportation",         ["road", "street", "highway", "bridge", "transportation", "traffic"]),
    ("General Government",     ["general government", "legislative", "judicial", "executive", "finance", "auditor", "treasurer", "assessor", "clerk", "human resources", "information"]),
    ("Health & Human Services",["health", "mental health", "social services", "veterans", "aging", "developmental"]),
    ("Parks & Recreation",     ["parks", "recreation", "culture", "library", "museum", "arts"]),
    ("Capital & Debt",         ["capital", "debt service", "bond", "construction", "facility", "infrastructure"]),
    ("Utilities & Environment",["water", "sewer", "solid waste", "utility", "environmental", "conservation"]),
    ("Airport & Port",         ["airport", "port", "marina", "aviation", "terminal", "industrial"]),
    ("Hospital & Medical",     ["hospital", "medical", "clinical", "patient", "nursing", "pharmacy"]),
]

def classify_expenditure(account_name):
    if pd.isna(account_name):
        return "Other"
    name_lower = str(account_name).lower()
    for category, keywords in EXP_CATEGORY_MAP:
        if any(kw in name_lower for kw in keywords):
            return category
    return "Other"


def build_agencies_json():
    if not SCHEDULE01_CSV.exists():
        print(f"  WARNING: {SCHEDULE01_CSV} not found. Skipping financial data. agencies.json will have budget=null.")
        return None

    print(f"\nBuilding agencies JSON from {SCHEDULE01_CSV.name}...")
    df = pd.read_csv(SCHEDULE01_CSV, dtype=str, low_memory=False)
    print(f"  Raw shape: {df.shape}")

    # Normalize column names
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(r'[\s/]+', '_', regex=True)
                  .str.replace(r'[^a-z0-9_]', '', regex=True))

    # Auto-detect columns
    def find_col(candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    col_mcag   = find_col(['mcag', 'entity_mcag', 'govt_mcag'])
    col_year   = find_col(['year', 'filing_year', 'fiscal_year', 'report_year'])
    col_amount = find_col(['amount', 'total_amount', 'dollar_amount'])
    col_fsumm  = find_col(['financialsummary', 'financial_summary', 'financialsummarysection'])
    col_bars   = find_col(['barsaccount', 'bars_account', 'bars', 'bars_code', 'barsaccountid'])
    col_bname  = find_col(['barsaccountname', 'bars_account_name', 'account_name'])

    print(f"  Columns: mcag={col_mcag}, year={col_year}, amount={col_amount}, "
          f"fsumm={col_fsumm}, bars={col_bars}, bname={col_bname}")

    if not col_mcag or not col_amount:
        print("  ERROR: Cannot identify required columns. Skipping.")
        return None

    # Normalize MCAG to 4-digit zero-padded
    df[col_mcag] = df[col_mcag].astype(str).str.strip().str.zfill(4)

    # Parse amounts
    df['_amount'] = df[col_amount].apply(parse_amount)

    # Filter to Skagit MCAGs
    skagit_df = df[df[col_mcag].isin(SKAGIT_MCAGS.keys())].copy()
    print(f"  Skagit rows: {len(skagit_df):,}")
    print(f"  MCAGs found: {sorted(skagit_df[col_mcag].unique())}")

    # Determine year
    if col_year:
        skagit_df[col_year] = pd.to_numeric(skagit_df[col_year], errors='coerce')
        year_counts = skagit_df.groupby(col_year)[col_mcag].nunique().sort_index(ascending=False)
        print(f"  Year coverage:\n{year_counts.to_string()}")
        use_year = int(year_counts.index[0])
        year_df = skagit_df[skagit_df[col_year] == use_year].copy()
    else:
        use_year = 2025
        year_df = skagit_df.copy()

    print(f"  Using year: {use_year}")

    # Classify rows as revenue or expenditure via FinancialSummary
    def classify_row(fsumm_val, bars_val):
        fsumm = str(fsumm_val).lower() if pd.notna(fsumm_val) else ""
        if "revenue" in fsumm:
            return "revenue"
        if "expenditure" in fsumm or "expense" in fsumm:
            return "expenditure"
        # Fallback: infer from BARS code prefix
        bars = str(bars_val).replace("id-", "").strip() if pd.notna(bars_val) else ""
        if bars.startswith("3"):
            return "revenue"
        if bars.startswith("5") or (len(bars) >= 2 and bars[0] == "0" and bars[1:3] in ["01","02","03","04","05","06","07","08","09"]):
            return "expenditure"
        return "other"

    year_df['_type'] = year_df.apply(
        lambda r: classify_row(r.get(col_fsumm), r.get(col_bars)), axis=1
    )

    # Check a sample of type values
    if col_fsumm:
        print(f"  FinancialSummary unique values (sample): {year_df[col_fsumm].value_counts().head(8).to_dict()}")

    print(f"  Row type distribution: {year_df['_type'].value_counts().to_dict()}")

    agencies_json = {}

    for mcag, meta in SKAGIT_MCAGS.items():
        agency_rows = year_df[year_df[col_mcag] == mcag]

        sao_fit_url = f"https://portal.sao.wa.gov/FIT/ReportsByEntity?mcag={mcag}"

        if agency_rows.empty:
            agencies_json[mcag] = {
                "mcag": mcag,
                "entity_key": meta["entity_key"],
                "common_name": meta["common_name"],
                "type": meta["type"],
                "blurb": meta["blurb"],
                "budget": None,
                "sao_fit_url": sao_fit_url,
                "data_year": None,
            }
            continue

        rev_rows = agency_rows[agency_rows['_type'] == 'revenue']
        exp_rows = agency_rows[agency_rows['_type'] == 'expenditure']

        total_revenue     = float(rev_rows['_amount'].sum())
        total_expenditure = float(exp_rows['_amount'].sum())
        surplus_deficit   = round(total_revenue - total_expenditure, 2)

        # Property tax % of revenue
        prop_tax_rev = 0.0
        if col_bname:
            pt_rows = rev_rows[rev_rows[col_bname].astype(str).str.lower().str.contains('property tax', na=False)]
            prop_tax_rev = float(pt_rows['_amount'].sum())
        if prop_tax_rev == 0.0 and col_bars:
            # Also try BARS code 311xxxx
            pt_bars = rev_rows[rev_rows[col_bars].astype(str).str.replace('id-','').str.startswith('311')]
            prop_tax_rev = float(pt_bars['_amount'].sum())

        prop_tax_pct = round(100 * prop_tax_rev / total_revenue, 1) if total_revenue > 0 else 0

        # Top 3 expenditure categories
        top_expenditures = []
        if not exp_rows.empty and col_bname:
            exp_copy = exp_rows.copy()
            exp_copy['_category'] = exp_copy[col_bname].apply(classify_expenditure)
            top_exp = (
                exp_copy.groupby('_category')['_amount']
                .sum()
                .reset_index()
                .sort_values('_amount', ascending=False)
                .head(3)
            )
            top_expenditures = [
                {"category": row['_category'], "amount": round(float(row['_amount']), 2)}
                for _, row in top_exp.iterrows()
                if row['_amount'] > 0
            ]

        agencies_json[mcag] = {
            "mcag": mcag,
            "entity_key": meta["entity_key"],
            "common_name": meta["common_name"],
            "type": meta["type"],
            "blurb": meta["blurb"],
            "budget": {
                "total_revenue":                round(total_revenue, 2),
                "total_expenditure":            round(total_expenditure, 2),
                "surplus_deficit":              surplus_deficit,
                "property_tax_revenue":         round(prop_tax_rev, 2),
                "property_tax_pct_of_revenue":  prop_tax_pct,
                "top_expenditures":             top_expenditures,
            },
            "sao_fit_url": sao_fit_url,
            "data_year": int(use_year),
        }

    ok  = sum(1 for v in agencies_json.values() if v["budget"])
    nil = sum(1 for v in agencies_json.values() if not v["budget"])
    print(f"  Built: {ok} agencies with budget data, {nil} with no data (budget=null)")

    # Sample record
    sample = agencies_json.get("0647") or next(iter(agencies_json.values()))
    print(f"\n  Sample ({sample['mcag']} — {sample['common_name']}):")
    if sample.get("budget"):
        b = sample["budget"]
        print(f"    Revenue: ${b['total_revenue']:,.0f}")
        print(f"    Spent:   ${b['total_expenditure']:,.0f}")
        print(f"    PropTax: {b['property_tax_pct_of_revenue']}% of revenue")
        print(f"    Top spending: {[e['category'] for e in b['top_expenditures']]}")

    return agencies_json


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    engine = create_engine(DATABASE_URL, echo=False)

    print("=" * 60)
    print("OpenSkagit taxtool setup")
    print("=" * 60)

    create_schema(engine)
    load_crosswalk(engine)
    load_levy_composition(engine)
    populate_parcels(engine)
    run_diagnostics(engine)

    agencies = build_agencies_json()
    if agencies:
        AGENCIES_JSON_OUT.write_text(json.dumps(agencies, indent=2))
        print(f"\nWrote {len(agencies)} agencies -> {AGENCIES_JSON_OUT}")
    else:
        print("\nSkipped agencies JSON (no schedule01 data).")

    print("\n" + "=" * 60)
    print("Setup complete. Test with:")
    print("  SELECT parcel_number, agency_name, total_tax, pct_of_bill")
    print("  FROM v_parcel_tax_summary")
    print("  WHERE parcel_number = (SELECT parcel_number FROM skagit_parcels")
    print("                         WHERE inactive_date IS NULL AND assessed_value > 0 LIMIT 1)")
    print("  ORDER BY total_tax DESC;")
    print("=" * 60)


if __name__ == "__main__":
    main()
