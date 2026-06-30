from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

GisLayerKey = Literal[
    "parcel",
    "zoning",
    "uga",
    "npdes",
    "wria",
    "watershed_basin",
    "surface_water_limited_stream",
    "stream_buffer",
    "wellhead_protection",
    "big_lake_water_mitigation",
    "alluvial_fans",
    "slope_stability",
    "landslide_areas",
    "aerial_interpreted_wetlands",
    "skagit_wetlands",
    "hydric_soils",
    "fema_bfe",
    "fema_floodway",
    "fema_flood",
    "fema_panels",
    "landfill_influence",
    "fire_district",
    "school_district",
    "sewer_district",
    "dike_district",
    "drainage_district",
    "road_maintenance_district",
    "group_a_water_systems",
    "group_a_b_wells",
    "mtca_cleanup_sites",
    "ust_facilities",
    "wdfw_priority_habitats",
    "fema_nfhl_zones",
    "fema_nfhl_panels",
    "dnr_natural_heritage_current",
    "dnr_managed_lands",
    "tribal_lands",
    "forest_practices",
    "epa_superfund",
]
GisBundleKey = Literal["core", "development", "utilities_services", "state_federal"]


@dataclass(frozen=True)
class GisLayerConfig:
    key: str
    label: str
    url: str
    out_fields: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        row = asdict(self)
        row["outFields"] = row.pop("out_fields")
        return row


CRITICAL_AREAS = "https://gis.skagitcountywa.gov/arcgis/rest/services/Geocortex/CriticalAreas/MapServer"
DISTRICTS = "https://gis.skagitcountywa.gov/arcgis/rest/services/Districts"
HEALTH = "https://gis.skagitcountywa.gov/arcgis/rest/services/Health"
WA_ECOLOGY_TCP = "https://gis.ecology.wa.gov/serverext/rest/services/TCP/Neighborhood/MapServer"
WDFW_PHS = "https://geodataservices.wdfw.wa.gov/arcgis/rest/services/PHSOnTheWeb/PHSOnTheWebPublic/MapServer"
FEMA_NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
WA_DNR_NATURAL_HERITAGE = "https://gis.dnr.wa.gov/site2/rest/services/Natural_Heritage/Public_Element_Occurrences/MapServer"
WA_DNR_MANAGED_LANDS = "https://gis.dnr.wa.gov/site3/rest/services/Public_Boundaries/WADNR_PUBLIC_Managed_Lands/MapServer"
WA_DNR_NON_DNR_PUBLIC_LANDS = "https://gis.dnr.wa.gov/site3/rest/services/Public_Boundaries/WADNR_PUBLIC_Major_Public_Lands_NonDNR/MapServer"
WA_DNR_FOREST_PRACTICES = "https://gis.dnr.wa.gov/site2/rest/services/Public_Forest_Practices/WADNR_PUBLIC_FP_Applications/FeatureServer"


GIS_LAYERS: dict[str, GisLayerConfig] = {
    "parcel": GisLayerConfig("parcel", "Assessor Tax Parcel", "https://gis.skagitcountywa.gov/arcgis/rest/services/Assessor/PropertyMap/MapServer/5", "PARCELID,OwnerName,SitusStName,Acres,PropType,LivingArea,GeneralTaxes,SaleDate,CityDistrict,FireDistrict", "Base parcel polygon used to drive spatial overlay checks."),
    "zoning": GisLayerConfig("zoning", "Comprehensive Plan / Zoning", "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/ComprehensivePlanWebMap/MapServer/14", "ZONING_CODE,ZONING_LABEL,LUD,LUD_ZONING,FEAT_TYPE,ACRES,FEDERAL", "Primary planning/zoning context layer."),
    "uga": GisLayerConfig("uga", "Urban Growth Area", "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/ComprehensivePlanWebMap/MapServer/4", "OBJECTID,GlobalID", "Whether the parcel intersects a UGA area."),
    "npdes": GisLayerConfig("npdes", "NPDES Permit Area", "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/ComprehensivePlanWebMap/MapServer/3", "OBJECTID,GlobalID", "Stormwater/NPDES permit area context."),
    "wria": GisLayerConfig("wria", "WRIA", f"{CRITICAL_AREAS}/18", "WRIA_ID,WRIA_NM,WRIA_NR,WRIA_AREA_", "Water Resource Inventory Area."),
    "watershed_basin": GisLayerConfig("watershed_basin", "Skagit Watershed Basin", f"{CRITICAL_AREAS}/17", "Basin_NM,SBasin_NM,SYMBOL", "Watershed basin/subbasin context."),
    "surface_water_limited_stream": GisLayerConfig("surface_water_limited_stream", "Surface Water Source Limited Stream", f"{CRITICAL_AREAS}/20", "Name,TYPE,WRIA_STRM_NO", "Nearby/intersecting source-limited stream lines."),
    "stream_buffer": GisLayerConfig("stream_buffer", "Stream Buffer", f"{CRITICAL_AREAS}/21", "INSIDE,LOW_BUFF_,LOW_BUFF_ID", "Low-flow stream buffer polygon context."),
    "wellhead_protection": GisLayerConfig("wellhead_protection", "Wellhead Protection Area", f"{CRITICAL_AREAS}/3", "TYPE,OBJECTID,GlobalID", "Wellhead protection overlay."),
    "big_lake_water_mitigation": GisLayerConfig("big_lake_water_mitigation", "Big Lake Water Mitigation Area", "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/SkagitCountyBigLakeWaterMitigationProgramWebMap/MapServer/7", "BASIN_NM,SUBBASIN_N,Mit_Area,Reserv,Acreage,SqMi,PermPerMi", "Big Lake water mitigation eligibility/context layer."),
    "alluvial_fans": GisLayerConfig("alluvial_fans", "Alluvial Fans", f"{CRITICAL_AREAS}/24", "TYPE,OBJECTID", "Geo-hazard/deposition fan context for development risk."),
    "slope_stability": GisLayerConfig("slope_stability", "Slope Stability", f"{CRITICAL_AREAS}/25", "SLP_CLASS,OBJECTID", "Slope stability class for geologic/development risk."),
    "landslide_areas": GisLayerConfig("landslide_areas", "Landslide Areas", f"{CRITICAL_AREAS}/26", "MGMT_ZONE,OBJECTID", "Mapped landslide area context."),
    "aerial_interpreted_wetlands": GisLayerConfig("aerial_interpreted_wetlands", "Aerial Interpreted Wetlands", f"{CRITICAL_AREAS}/29", "INREC,OBJECTID", "Aerial-interpreted wetland overlay."),
    "skagit_wetlands": GisLayerConfig("skagit_wetlands", "Skagit Wetlands", f"{CRITICAL_AREAS}/30", "FWS_CODE,OBJECTID", "Wetland inventory overlay."),
    "hydric_soils": GisLayerConfig("hydric_soils", "Hydric Soils", f"{CRITICAL_AREAS}/31", "FM_CODE,OBJECTID", "Hydric soil indicator used as wetland/development risk signal."),
    "fema_bfe": GisLayerConfig("fema_bfe", "FEMA Base Flood Elevation", f"{CRITICAL_AREAS}/33", "BFE,OBJECTID", "Base flood elevation line context."),
    "fema_floodway": GisLayerConfig("fema_floodway", "FEMA Floodway", f"{CRITICAL_AREAS}/34", "FLOODWAY,OBJECTID", "Regulatory floodway context."),
    "fema_flood": GisLayerConfig("fema_flood", "FEMA Flood Zone", f"{CRITICAL_AREAS}/35", "ZONE_,FLOODWAY,SFHA,FIRM_PANEL,COMMUNITY,OBJECTID", "FEMA Q3 floodplain/flood zone context."),
    "fema_panels": GisLayerConfig("fema_panels", "FEMA Panels", f"{CRITICAL_AREAS}/36", "FIRM_PANEL,OBJECTID", "FIRM panel reference layer."),
    "landfill_influence": GisLayerConfig("landfill_influence", "Potential Landfill Influence", f"{CRITICAL_AREAS}/40", "Name,Status,Landfill_ID,OBJECTID", "Area of potential closed/abandoned landfill influence."),
    "fire_district": GisLayerConfig("fire_district", "Fire District", f"{DISTRICTS}/FireDistrictsWebMap/MapServer/4", "DISTRICT,OBJECTID,GlobalID", "Unincorporated fire district service context."),
    "school_district": GisLayerConfig("school_district", "School District", f"{DISTRICTS}/SchoolDistrictsWebMap/MapServer/5", "NAME,DIST_NUM,COUNTY,OBJECTID,GlobalID", "School district overlay for appraisal and public-service context."),
    "sewer_district": GisLayerConfig("sewer_district", "Sewer District", f"{DISTRICTS}/SkagitCountySewerDistrictsWebMap/MapServer/7", "ACRES,OBJECTID,PERIMETER,SEW_DIST_,SEW_DIST_ID,BNDRY,RISK,SEWER_DIST,PERCENT_,GlobalID", "Sewer district area overlay."),
    "dike_district": GisLayerConfig("dike_district", "Dike District Assessment Parcels", f"{DISTRICTS}/SkagitCountyDikeDistrictAssessmentAreas/MapServer/8", "PARCELID,OBJECTID,Code_Description,GlobalID", "Properties paying into dike district assessments; districts are defined by assessment rolls."),
    "drainage_district": GisLayerConfig("drainage_district", "Drainage District Assessment Parcels", f"{DISTRICTS}/SkagitCountyDrainDistrictAssessmentAreas/MapServer/7", "CityDistrict,OwnerName,PARCELID,PARCELTYPE,SitusStName,Acres,DistrictTy,FireDistrict,GeneralTaxes,OBJECTID", "Generalized drainage district assessment parcel overlay."),
    "road_maintenance_district": GisLayerConfig("road_maintenance_district", "Road Maintenance District", "https://gis.skagitcountywa.gov/arcgis/rest/services/TransportationUtilities/StormwaterMap/MapServer/15", "DIST_NO,OBJECTID", "Skagit County Public Works road maintenance district context."),
    "group_a_water_systems": GisLayerConfig("group_a_water_systems", "Group A Public Water System Area", f"{HEALTH}/GroupAWaterSystemsMap/MapServer/7", "Water_System_Name,PWS_ID,OBJECTID", "Group A public drinking water system service-area overlay."),
    "group_a_b_wells": GisLayerConfig("group_a_b_wells", "Group A and B Wells", f"{HEALTH}/GroupAandBWells/MapServer/0", "PARCEL,PWSNAME,SOURCETYPE,TYPE,OBJECTID,OBJECTID_1,DOHPWSID,DOHSOURCEI,GROUP_,WPHA,DOETAG,QTRSECTION,SECTION,TOWNSHIP,RANGE,X,Y", "Group A source/well locations from the county Group A and B wells service."),
    "mtca_cleanup_sites": GisLayerConfig("mtca_cleanup_sites", "WA Ecology MTCA Cleanup Sites", f"{WA_ECOLOGY_TCP}/0", "*", "Washington Ecology Toxics Cleanup Program contaminated cleanup sites and cleanup actions."),
    "ust_facilities": GisLayerConfig("ust_facilities", "WA Ecology Underground Storage Tank Facilities", f"{WA_ECOLOGY_TCP}/5", "*", "Washington Ecology underground storage tank facility context."),
    "wdfw_priority_habitats": GisLayerConfig("wdfw_priority_habitats", "WDFW Priority Habitats and Species Polygons", f"{WDFW_PHS}/3", "*", "WDFW PHS public polygon habitat/species context; sensitive locations may be generalized under WDFW policy."),
    "fema_nfhl_zones": GisLayerConfig("fema_nfhl_zones", "FEMA NFHL Flood Hazard Zones", f"{FEMA_NFHL}/28", "*", "Current FEMA National Flood Hazard Layer flood hazard zones for comparison with county Q3 flood data."),
    "fema_nfhl_panels": GisLayerConfig("fema_nfhl_panels", "FEMA NFHL FIRM Panels", f"{FEMA_NFHL}/3", "*", "Current FEMA NFHL FIRM panel metadata and effective map context."),
    "dnr_natural_heritage_current": GisLayerConfig("dnr_natural_heritage_current", "WA DNR Natural Heritage Current Element Occurrences", f"{WA_DNR_NATURAL_HERITAGE}/0", "*", "Washington Natural Heritage Program current rare plant, ecosystem, and natural community element occurrences."),
    "dnr_managed_lands": GisLayerConfig("dnr_managed_lands", "WA DNR Managed Surface Lands", f"{WA_DNR_MANAGED_LANDS}/1", "*", "DNR-managed surface lands including state trust land context."),
    "tribal_lands": GisLayerConfig("tribal_lands", "Tribal Lands", f"{WA_DNR_NON_DNR_PUBLIC_LANDS}/2", "*", "Tribal land administrative boundaries from WA DNR Non-DNR Major Public Lands."),
    "forest_practices": GisLayerConfig("forest_practices", "WA DNR Forest Practices Applications", f"{WA_DNR_FOREST_PRACTICES}/0", "*", "Washington DNR forest practices application context, including active/recent timber harvest and forestry applications where available."),
    "epa_superfund": GisLayerConfig("epa_superfund", "EPA Superfund Site Boundaries", "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0", "*", "EPA public Superfund/NPL site boundary context."),
}

GIS_BUNDLES: dict[str, list[str]] = {
    "core": ["zoning", "uga", "npdes", "wria", "watershed_basin", "surface_water_limited_stream", "stream_buffer", "wellhead_protection", "big_lake_water_mitigation"],
    "development": ["alluvial_fans", "slope_stability", "landslide_areas", "aerial_interpreted_wetlands", "skagit_wetlands", "hydric_soils", "fema_bfe", "fema_floodway", "fema_flood", "fema_panels", "landfill_influence"],
    "utilities_services": ["fire_district", "school_district", "sewer_district", "dike_district", "drainage_district", "road_maintenance_district", "group_a_water_systems", "group_a_b_wells"],
    "state_federal": ["mtca_cleanup_sites", "ust_facilities", "wdfw_priority_habitats", "fema_nfhl_zones", "fema_nfhl_panels", "dnr_natural_heritage_current", "dnr_managed_lands", "tribal_lands", "forest_practices", "epa_superfund"],
}

DEFAULT_BUNDLES = ["core", "development", "utilities_services", "state_federal"]
DEFAULT_OVERLAY_LAYERS = [layer for bundle in DEFAULT_BUNDLES for layer in GIS_BUNDLES[bundle]]
