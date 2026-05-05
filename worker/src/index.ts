export interface Env {
  SKAGIT_PROPERTY_SERVICE: string;
  SKAGIT_PROPERTY_SALES_BASE?: string;
  SKAGIT_ADDRESS_LAYER?: string;
  MCP_BEARER_TOKEN?: string;
  ASSETS: { fetch(request: Request): Promise<Response> | Response };
}

type PageType = "Details" | "Improvements" | "Land" | "Sales" | "History" | "Taxes" | "Permits";
const PAGE_TYPES: PageType[] = ["Details", "Improvements", "Land", "Sales", "History", "Taxes", "Permits"];

type DossierPages = Record<string, unknown>;

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
      "access-control-allow-headers": "content-type",
    },
  });
}

function estimateTokens(payload: unknown) {
  const estimated_chars = JSON.stringify(payload).length;
  return {
    estimated_tokens: Math.ceil(estimated_chars / 4),
    estimated_chars,
    token_estimate_method: "chars_div_4",
  };
}

function withResponseMeta<T extends Record<string, unknown>>(payload: T) {
  const cleanPayload = { ...payload };
  delete (cleanPayload as Record<string, unknown>).meta;
  return { meta: estimateTokens(cleanPayload), ...cleanPayload };
}

function mcpJson(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "access-control-allow-headers": "content-type, authorization, mcp-session-id",
    },
  });
}

function mcpError(id: unknown, code: number, message: string, data?: unknown) {
  return { jsonrpc: "2.0", id: id ?? null, error: data === undefined ? { code, message } : { code, message, data } };
}

function mcpResult(id: unknown, result: unknown) {
  return { jsonrpc: "2.0", id, result };
}

function mcpToolText(data: unknown) {
  return {
    content: [{
      type: "text",
      text: JSON.stringify(data, null, 2),
    }],
  };
}

function requireMcpAuth(request: Request, env: Env) {
  if (!env.MCP_BEARER_TOKEN) return null;
  const header = request.headers.get("authorization") || "";
  if (header === `Bearer ${env.MCP_BEARER_TOKEN}`) return null;
  return mcpJson({ error: "Unauthorized MCP request" }, 401);
}

const MCP_TOOLS = [
  {
    name: "search_parcels",
    description: "Search Skagit County parcels by address text or parcel number. Use this before parcel-specific tools when the user gives an address instead of a parcel ID.",
    inputSchema: {
      type: "object",
      properties: {
        q: { type: "string", description: "Address text or parcel number, for example '813 Cultus Mountain' or 'P96023'." },
      },
      required: ["q"],
    },
  },
  {
    name: "get_property_context",
    description: "Default full-context property research packet for one Skagit County parcel. Includes assessor details, taxes, value history, transfers, comps, census, soils, and GIS overlays. This can be large.",
    inputSchema: {
      type: "object",
      properties: {
        parcel: { type: "string", description: "Parcel ID such as P96023." },
        raw: { type: "boolean", description: "Include raw county page payloads. Default false." },
        bundles: { type: "string", description: "Optional comma-separated GIS bundles. Defaults to all bundles: core,development,utilities_services,state_federal." },
        layers: { type: "string", description: "Optional comma-separated explicit GIS layer keys." },
      },
      required: ["parcel"],
    },
  },
  {
    name: "get_property_summary",
    description: "Parsed assessor/property packet for one parcel without GIS overlays. Includes taxes, value history, transfers, comps, census, soils, related parcels, value trends, and agent flags.",
    inputSchema: {
      type: "object",
      properties: {
        parcel: { type: "string", description: "Parcel ID such as P96023." },
        raw: { type: "boolean", description: "Include raw county page payloads. Default false." },
      },
      required: ["parcel"],
    },
  },
  {
    name: "get_gis_overlays",
    description: "Get GIS overlays intersecting a parcel. Use for zoning, critical areas, utilities/services, and state/federal environmental/public-land context.",
    inputSchema: {
      type: "object",
      properties: {
        parcel: { type: "string", description: "Parcel ID such as P96023." },
        bundles: { type: "string", description: "Optional comma-separated bundles: core, development, utilities_services, state_federal." },
        layers: { type: "string", description: "Optional comma-separated specific layer keys." },
      },
      required: ["parcel"],
    },
  },
  {
    name: "get_census_context",
    description: "Get Census ACS area-level context matched by parcel centroid. These are area estimates, not parcel-level facts.",
    inputSchema: {
      type: "object",
      properties: {
        parcel: { type: "string", description: "Parcel ID such as P96023." },
      },
      required: ["parcel"],
    },
  },
  {
    name: "get_soils_context",
    description: "Get NRCS SSURGO soil map units intersecting the parcel polygon, including drainage, flooding, hydrologic group, and farmland class where available.",
    inputSchema: {
      type: "object",
      properties: {
        parcel: { type: "string", description: "Parcel ID such as P96023." },
      },
      required: ["parcel"],
    },
  },
  {
    name: "list_gis_layers",
    description: "List available GIS overlay bundles and layer keys.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
];

async function callMcpTool(env: Env, name: string, args: any) {
  if (name === "search_parcels") {
    return searchAddress(env, cleanSearch(args?.q || null));
  }
  if (name === "get_property_context") {
    const parcel = cleanParcel(args?.parcel || null);
    const [property, gis] = await Promise.all([
      propertyDossier(env, parcel, Boolean(args?.raw)),
      parcelOverlays(parcel, parseLayerKeys(args?.layers || null, args?.bundles || null)),
    ]);
    return withResponseMeta({ parcel, property, gis });
  }
  if (name === "get_property_summary") {
    const parcel = cleanParcel(args?.parcel || null);
    return withResponseMeta({ parcel, ...(await propertyDossier(env, parcel, Boolean(args?.raw))) });
  }
  if (name === "get_gis_overlays") {
    const parcel = cleanParcel(args?.parcel || null);
    return parcelOverlays(parcel, parseLayerKeys(args?.layers || null, args?.bundles || null));
  }
  if (name === "get_census_context") {
    const parcel = cleanParcel(args?.parcel || null);
    return withResponseMeta({ parcel, census: await parcelCensus(parcel) });
  }
  if (name === "get_soils_context") {
    const parcel = cleanParcel(args?.parcel || null);
    return withResponseMeta({ parcel, soils: await parcelSoils(parcel) });
  }
  if (name === "list_gis_layers") {
    return layerList();
  }
  throw new Error(`Unknown MCP tool: ${name}`);
}

async function handleMcpMessage(message: any, env: Env) {
  const id = message?.id;
  const method = message?.method;
  if (!method) return mcpError(id, -32600, "Invalid JSON-RPC request");

  if (method === "initialize") {
    return mcpResult(id, {
      protocolVersion: "2025-06-18",
      capabilities: { tools: {} },
      serverInfo: { name: "openskagit-property-agent", version: "0.1.0" },
      instructions: "Read-only Skagit County property research tools. Use get_property_context as the default full parcel context call. Do not use reval area as neighborhood.",
    });
  }
  if (method === "ping") return mcpResult(id, {});
  if (method === "tools/list") return mcpResult(id, { tools: MCP_TOOLS });
  if (method === "resources/list") return mcpResult(id, { resources: [] });
  if (method === "prompts/list") return mcpResult(id, { prompts: [] });
  if (method === "tools/call") {
    const toolName = message?.params?.name;
    const args = message?.params?.arguments || {};
    const data = await callMcpTool(env, toolName, args);
    return mcpResult(id, mcpToolText(data));
  }
  return mcpError(id, -32601, `Method not found: ${method}`);
}

async function handleMcp(request: Request, env: Env) {
  const authError = requireMcpAuth(request, env);
  if (authError) return authError;

  if (request.method === "GET") {
    return mcpJson({
      name: "openskagit-property-agent",
      transport: "streamable-http-json-rpc",
      endpoint: "/mcp",
      tools: MCP_TOOLS.map((tool) => tool.name),
      note: "POST JSON-RPC MCP messages to this URL. Set MCP_BEARER_TOKEN as a Worker secret to require Authorization: Bearer <token>.",
    });
  }

  if (request.method !== "POST") return mcpJson({ error: "MCP endpoint expects POST JSON-RPC messages" }, 405);

  let payload: any;
  try {
    payload = await request.json();
  } catch {
    return mcpJson(mcpError(null, -32700, "Parse error"));
  }

  try {
    if (Array.isArray(payload)) {
      const responses = await Promise.all(payload.filter((message) => message?.id !== undefined).map((message) => handleMcpMessage(message, env)));
      return responses.length ? mcpJson(responses) : new Response(null, { status: 202 });
    }
    if (payload?.id === undefined) {
      await handleMcpMessage(payload, env);
      return new Response(null, { status: 202 });
    }
    return mcpJson(await handleMcpMessage(payload, env));
  } catch (err) {
    return mcpJson(mcpError(payload?.id, -32000, err instanceof Error ? err.message : String(err)));
  }
}

function openApiSchema(origin: string) {
  const parcelParam = {
    name: "parcel",
    in: "query",
    required: true,
    description: "Skagit County parcel number, for example P96023. Parcel numbers start with P followed by digits.",
    schema: { type: "string", pattern: "^P\\d{1,10}$" },
  };
  const rawParam = {
    name: "raw",
    in: "query",
    required: false,
    description: "Set to 1 only when the user explicitly needs raw county HTML/service responses. Defaults to parsed agent-ready output.",
    schema: { type: "string", enum: ["0", "1"], default: "0" },
  };
  const bundlesParam = {
    name: "bundles",
    in: "query",
    required: false,
    description: "Comma-separated GIS overlay bundles. Defaults to core,development,utilities_services,state_federal.",
    schema: {
      type: "string",
    },
  };
  const layersParam = {
    name: "layers",
    in: "query",
    required: false,
    description: "Comma-separated specific GIS layer keys. Prefer bundles unless the user asks for a specific overlay.",
    schema: { type: "string" },
  };
  const jsonResponse = {
    "200": {
      description: "JSON response. Most property/context responses include a top-level meta token estimate.",
      content: {
        "application/json": {
          schema: {
            type: "object",
            properties: {
              meta: {
                type: "object",
                properties: {
                  estimated_tokens: { type: "integer" },
                  estimated_chars: { type: "integer" },
                  token_estimate_method: { type: "string" },
                },
              },
              parcel: { type: "string" },
              query: { type: "string" },
              count: { type: "integer" },
              results: { type: "array", items: { type: "object", properties: {} } },
              summary: { type: "object", properties: {} },
              property: { type: "object", properties: {} },
              gis: { type: "object", properties: {} },
              census: { type: "object", properties: {} },
              soils: { type: "object", properties: {} },
              layer: { type: "string" },
              layers: { type: "array", items: { type: "object", properties: {} } },
              bundles: { type: "object", properties: {} },
              data: { type: "object", properties: {} },
            },
            additionalProperties: true,
          },
        },
      },
    },
    "400": {
      description: "Invalid request or upstream lookup error.",
      content: {
        "application/json": {
          schema: {
            type: "object",
            properties: { error: { type: "string" } },
          },
        },
      },
    },
  };

  return {
    openapi: "3.1.0",
    info: {
      title: "OpenSkagit Property Agent API",
      version: "0.2.0",
      description: [
        "Read-only property research API for Skagit County parcels.",
        "Use getPropertyContext for a full agent-ready packet with assessor data, sales/transfers, comps, census, and GIS overlays.",
        "Use getPropertySummary for assessor/property details without GIS overlays.",
        "Neighborhood and reval area are different concepts; do not use reval area for neighborhood grouping or comparable selection.",
        "Census values are area-level estimates matched by parcel centroid, not parcel-level facts.",
      ].join(" "),
    },
    servers: [{ url: origin }],
    paths: {
      "/api/search": {
        get: {
          operationId: "searchParcels",
          summary: "Search parcel records by address or parcel number",
          description: "Find candidate Skagit County parcels by address text or parcel number before requesting full property context.",
          parameters: [{
            name: "q",
            in: "query",
            required: true,
            description: "Address text or parcel number. Use this before parcel-specific calls when the user gives an address.",
            schema: { type: "string", minLength: 2, maxLength: 120 },
          }],
          responses: jsonResponse,
        },
      },
      "/api/property": {
        get: {
          operationId: "getPropertySummary",
          summary: "Get parsed property assessor context for one parcel",
          description: "Returns parsed assessor details, value history, taxes, sales/transfers, related parcels, value trends, agent flags, comps, and census context. Does not include GIS overlays.",
          parameters: [parcelParam, rawParam],
          responses: jsonResponse,
        },
      },
      "/api/context": {
        get: {
          operationId: "getPropertyContext",
          summary: "Get full agent-ready property context packet",
          description: "Best default call for appraisal/research questions. Returns property summary plus GIS overlays. The response can be large; check meta.estimated_tokens before deciding whether to ask for follow-up narrowing.",
          parameters: [parcelParam, rawParam, bundlesParam, layersParam],
          responses: jsonResponse,
        },
      },
      "/api/census": {
        get: {
          operationId: "getCensusContext",
          summary: "Get Census ACS context for one parcel",
          description: "Returns Census geographies and ACS 5-year area estimates matched by parcel centroid. Treat as area-level context, not parcel-level measurement.",
          parameters: [parcelParam],
          responses: jsonResponse,
        },
      },
      "/api/soils": {
        get: {
          operationId: "getSoilsContext",
          summary: "Get NRCS SSURGO soil map unit context for one parcel",
          description: "Returns NRCS Soil Data Access SSURGO map units intersecting the parcel polygon, including drainage class, flooding frequency, hydrologic group, and farmland classification where available.",
          parameters: [parcelParam],
          responses: jsonResponse,
        },
      },
      "/api/gis/parcel-overlays": {
        get: {
          operationId: "getParcelGisOverlays",
          summary: "Get GIS overlays intersecting one parcel",
          description: "Returns parcel geometry and selected overlay layers such as zoning, environmental constraints, service districts, utilities, water systems, and flood context.",
          parameters: [parcelParam, bundlesParam, layersParam],
          responses: jsonResponse,
        },
      },
      "/api/gis/layers": {
        get: {
          operationId: "listGisLayers",
          summary: "List available GIS overlay bundles and layers",
          description: "Use this to discover valid GIS bundle and layer keys for parcel overlay calls.",
          responses: jsonResponse,
        },
      },
      "/api/gis/metadata": {
        get: {
          operationId: "getGisLayerMetadata",
          summary: "Get metadata for one configured GIS layer",
          description: "Returns fields and service metadata for a configured GIS layer key.",
          parameters: [{
            name: "layer",
            in: "query",
            required: true,
            description: "GIS layer key from listGisLayers, for example zoning, fema_flood, school_district, or group_a_water_systems.",
            schema: { type: "string" },
          }],
          responses: jsonResponse,
        },
      },
      "/api/tax-detail": {
        get: {
          operationId: "getTaxStatementDetail",
          summary: "Get one tax statement year for a parcel",
          description: "Returns county tax statement details for one parcel and year. Use getPropertySummary first when a full parsed tax history is needed.",
          parameters: [
            parcelParam,
            {
              name: "year",
              in: "query",
              required: true,
              description: "Tax statement year, for example 2025.",
              schema: { type: "string", pattern: "^20\\d{2}$" },
            },
          ],
          responses: jsonResponse,
        },
      },
    },
  };
}


function cleanSearch(value: string | null) {
  const q = (value || "").trim();
  if (q.length < 2) throw new Error("Search needs at least 2 characters");
  if (q.length > 120) throw new Error("Search is too long");
  return q;
}

function sqlLiteral(value: string) {
  return value.replace(/'/g, "''").toUpperCase();
}

function addressLabel(a: Record<string, unknown>) {
  return String(a.FullAddressCSZ || a.FullAddress || a.GeneralAddressCSZ || a.GeneralAddress || "").trim();
}

async function searchAddress(env: Env, q: string) {
  const addressLayer = env.SKAGIT_ADDRESS_LAYER || "https://gis.skagitcountywa.gov/arcgis/rest/services/Assessor/PropertyMap/MapServer/3";
  const query = sqlLiteral(q);
  const isParcel = /^P\d{1,10}$/i.test(q);
  const where = isParcel
    ? `UPPER(ParcelID) = '${query}'`
    : `UPPER(FullAddressCSZ) LIKE '%${query}%' OR UPPER(FullAddress) LIKE '%${query}%' OR UPPER(GeneralAddressCSZ) LIKE '%${query}%' OR UPPER(GeneralAddress) LIKE '%${query}%'`;

  const params = new URLSearchParams({
    f: "json",
    where,
    outFields: "ParcelID,FullAddressCSZ,FullAddress,GeneralAddressCSZ,GeneralAddress,Latitude,Longitude,Mncplty,Post_Comm,Post_Code",
    returnGeometry: "false",
    orderByFields: "FullAddress ASC",
    resultRecordCount: "10",
  });

  const res = await fetch(`${addressLayer}/query?${params}`, {
    headers: { "accept": "application/json", "user-agent": "OpenSkagit research tool" },
  });
  const data = await res.json() as any;
  if (!res.ok || data.error) return { error: data.error || `Address search failed: ${res.status}`, raw: data };

  const seen = new Set<string>();
  const results = (data.features || [])
    .map((feature: any) => feature.attributes || {})
    .map((a: Record<string, unknown>) => ({
      label: addressLabel(a),
      parcel: String(a.ParcelID || "").trim(),
      latitude: typeof a.Latitude === "number" ? a.Latitude : null,
      longitude: typeof a.Longitude === "number" ? a.Longitude : null,
      city: String(a.Post_Comm || a.Mncplty || "").trim() || null,
      zip: String(a.Post_Code || "").trim() || null,
    }))
    .filter((r: any) => r.label && r.parcel)
    .filter((r: any) => {
      const key = `${r.parcel}|${r.label}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

  return { query: q, count: results.length, results };
}


type GisLayerKey =
  | "parcel"
  | "zoning"
  | "uga"
  | "npdes"
  | "wria"
  | "watershed_basin"
  | "surface_water_limited_stream"
  | "stream_buffer"
  | "wellhead_protection"
  | "big_lake_water_mitigation"
  | "alluvial_fans"
  | "slope_stability"
  | "landslide_areas"
  | "aerial_interpreted_wetlands"
  | "skagit_wetlands"
  | "hydric_soils"
  | "fema_bfe"
  | "fema_floodway"
  | "fema_flood"
  | "fema_panels"
  | "landfill_influence"
  | "fire_district"
  | "school_district"
  | "sewer_district"
  | "dike_district"
  | "drainage_district"
  | "road_maintenance_district"
  | "group_a_water_systems"
  | "group_a_b_wells"
  | "mtca_cleanup_sites"
  | "ust_facilities"
  | "wdfw_priority_habitats"
  | "fema_nfhl_zones"
  | "fema_nfhl_panels"
  | "dnr_natural_heritage_current"
  | "dnr_managed_lands"
  | "tribal_lands"
  | "forest_practices"
  | "epa_superfund";

type GisLayerConfig = { key: GisLayerKey; label: string; url: string; outFields: string; notes: string; };
type ArcGisField = { name: string; type?: string; alias?: string };
type ArcGisLayerMetadata = {
  id?: number;
  name?: string;
  type?: string;
  geometryType?: string;
  fields?: ArcGisField[];
  capabilities?: string;
  maxRecordCount?: number;
  error?: unknown;
};

const CRITICAL_AREAS = "https://gis.skagitcountywa.gov/arcgis/rest/services/Geocortex/CriticalAreas/MapServer";
const DISTRICTS = "https://gis.skagitcountywa.gov/arcgis/rest/services/Districts";
const HEALTH = "https://gis.skagitcountywa.gov/arcgis/rest/services/Health";
const WA_ECOLOGY_TCP = "https://gis.ecology.wa.gov/serverext/rest/services/TCP/Neighborhood/MapServer";
const WDFW_PHS = "https://geodataservices.wdfw.wa.gov/arcgis/rest/services/PHSOnTheWeb/PHSOnTheWebPublic/MapServer";
const FEMA_NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer";
const WA_DNR_NATURAL_HERITAGE = "https://gis.dnr.wa.gov/site2/rest/services/Natural_Heritage/Public_Element_Occurrences/MapServer";
const WA_DNR_MANAGED_LANDS = "https://gis.dnr.wa.gov/site3/rest/services/Public_Boundaries/WADNR_PUBLIC_Managed_Lands/MapServer";
const WA_DNR_NON_DNR_PUBLIC_LANDS = "https://gis.dnr.wa.gov/site3/rest/services/Public_Boundaries/WADNR_PUBLIC_Major_Public_Lands_NonDNR/MapServer";
const WA_DNR_FOREST_PRACTICES = "https://gis.dnr.wa.gov/site2/rest/services/Public_Forest_Practices/WADNR_PUBLIC_FP_Applications/FeatureServer";

const GIS_LAYERS: Record<GisLayerKey, GisLayerConfig> = {
  parcel: { key: "parcel", label: "Assessor Tax Parcel", url: "https://gis.skagitcountywa.gov/arcgis/rest/services/Assessor/PropertyMap/MapServer/5", outFields: "PARCELID,OwnerName,SitusStName,Acres,PropType,LivingArea,GeneralTaxes,SaleDate,CityDistrict,FireDistrict", notes: "Base parcel polygon used to drive spatial overlay checks." },
  zoning: { key: "zoning", label: "Comprehensive Plan / Zoning", url: "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/ComprehensivePlanWebMap/MapServer/14", outFields: "ZONING_CODE,ZONING_LABEL,LUD,LUD_ZONING,FEAT_TYPE,ACRES,FEDERAL", notes: "Primary planning/zoning context layer." },
  uga: { key: "uga", label: "Urban Growth Area", url: "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/ComprehensivePlanWebMap/MapServer/4", outFields: "OBJECTID,GlobalID", notes: "Whether the parcel intersects a UGA area." },
  npdes: { key: "npdes", label: "NPDES Permit Area", url: "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/ComprehensivePlanWebMap/MapServer/3", outFields: "OBJECTID,GlobalID", notes: "Stormwater/NPDES permit area context." },
  wria: { key: "wria", label: "WRIA", url: `${CRITICAL_AREAS}/18`, outFields: "WRIA_ID,WRIA_NM,WRIA_NR,WRIA_AREA_", notes: "Water Resource Inventory Area." },
  watershed_basin: { key: "watershed_basin", label: "Skagit Watershed Basin", url: `${CRITICAL_AREAS}/17`, outFields: "Basin_NM,SBasin_NM,SYMBOL", notes: "Watershed basin/subbasin context." },
  surface_water_limited_stream: { key: "surface_water_limited_stream", label: "Surface Water Source Limited Stream", url: `${CRITICAL_AREAS}/20`, outFields: "Name,TYPE,WRIA_STRM_NO", notes: "Nearby/intersecting source-limited stream lines." },
  stream_buffer: { key: "stream_buffer", label: "Stream Buffer", url: `${CRITICAL_AREAS}/21`, outFields: "INSIDE,LOW_BUFF_,LOW_BUFF_ID", notes: "Low-flow stream buffer polygon context." },
  wellhead_protection: { key: "wellhead_protection", label: "Wellhead Protection Area", url: `${CRITICAL_AREAS}/3`, outFields: "TYPE,OBJECTID,GlobalID", notes: "Wellhead protection overlay." },
  big_lake_water_mitigation: { key: "big_lake_water_mitigation", label: "Big Lake Water Mitigation Area", url: "https://gis.skagitcountywa.gov/arcgis/rest/services/Planning/SkagitCountyBigLakeWaterMitigationProgramWebMap/MapServer/7", outFields: "BASIN_NM,SUBBASIN_N,Mit_Area,Reserv,Acreage,SqMi,PermPerMi", notes: "Big Lake water mitigation eligibility/context layer." },
  alluvial_fans: { key: "alluvial_fans", label: "Alluvial Fans", url: `${CRITICAL_AREAS}/24`, outFields: "TYPE,OBJECTID", notes: "Geo-hazard/deposition fan context for development risk." },
  slope_stability: { key: "slope_stability", label: "Slope Stability", url: `${CRITICAL_AREAS}/25`, outFields: "SLP_CLASS,OBJECTID", notes: "Slope stability class for geologic/development risk." },
  landslide_areas: { key: "landslide_areas", label: "Landslide Areas", url: `${CRITICAL_AREAS}/26`, outFields: "MGMT_ZONE,OBJECTID", notes: "Mapped landslide area context." },
  aerial_interpreted_wetlands: { key: "aerial_interpreted_wetlands", label: "Aerial Interpreted Wetlands", url: `${CRITICAL_AREAS}/29`, outFields: "INREC,OBJECTID", notes: "Aerial-interpreted wetland overlay." },
  skagit_wetlands: { key: "skagit_wetlands", label: "Skagit Wetlands", url: `${CRITICAL_AREAS}/30`, outFields: "FWS_CODE,OBJECTID", notes: "Wetland inventory overlay." },
  hydric_soils: { key: "hydric_soils", label: "Hydric Soils", url: `${CRITICAL_AREAS}/31`, outFields: "FM_CODE,OBJECTID", notes: "Hydric soil indicator used as wetland/development risk signal." },
  fema_bfe: { key: "fema_bfe", label: "FEMA Base Flood Elevation", url: `${CRITICAL_AREAS}/33`, outFields: "BFE,OBJECTID", notes: "Base flood elevation line context." },
  fema_floodway: { key: "fema_floodway", label: "FEMA Floodway", url: `${CRITICAL_AREAS}/34`, outFields: "FLOODWAY,OBJECTID", notes: "Regulatory floodway context." },
  fema_flood: { key: "fema_flood", label: "FEMA Flood Zone", url: `${CRITICAL_AREAS}/35`, outFields: "ZONE_,FLOODWAY,SFHA,FIRM_PANEL,COMMUNITY,OBJECTID", notes: "FEMA Q3 floodplain/flood zone context." },
  fema_panels: { key: "fema_panels", label: "FEMA Panels", url: `${CRITICAL_AREAS}/36`, outFields: "FIRM_PANEL,OBJECTID", notes: "FIRM panel reference layer." },
  landfill_influence: { key: "landfill_influence", label: "Potential Landfill Influence", url: `${CRITICAL_AREAS}/40`, outFields: "Name,Status,Landfill_ID,OBJECTID", notes: "Area of potential closed/abandoned landfill influence." },
  fire_district: { key: "fire_district", label: "Fire District", url: `${DISTRICTS}/FireDistrictsWebMap/MapServer/4`, outFields: "DISTRICT,OBJECTID,GlobalID", notes: "Unincorporated fire district service context." },
  school_district: { key: "school_district", label: "School District", url: `${DISTRICTS}/SchoolDistrictsWebMap/MapServer/5`, outFields: "NAME,DIST_NUM,COUNTY,OBJECTID,GlobalID", notes: "School district overlay for appraisal and public-service context." },
  sewer_district: { key: "sewer_district", label: "Sewer District", url: `${DISTRICTS}/SkagitCountySewerDistrictsWebMap/MapServer/7`, outFields: "ACRES,OBJECTID,PERIMETER,SEW_DIST_,SEW_DIST_ID,BNDRY,RISK,SEWER_DIST,PERCENT_,GlobalID", notes: "Sewer district area overlay." },
  dike_district: { key: "dike_district", label: "Dike District Assessment Parcels", url: `${DISTRICTS}/SkagitCountyDikeDistrictAssessmentAreas/MapServer/8`, outFields: "PARCELID,OBJECTID,Code_Description,GlobalID", notes: "Properties paying into dike district assessments; districts are defined by assessment rolls." },
  drainage_district: { key: "drainage_district", label: "Drainage District Assessment Parcels", url: `${DISTRICTS}/SkagitCountyDrainDistrictAssessmentAreas/MapServer/7`, outFields: "CityDistrict,OwnerName,PARCELID,PARCELTYPE,SitusStName,Acres,DistrictTy,FireDistrict,GeneralTaxes,OBJECTID", notes: "Generalized drainage district assessment parcel overlay." },
  road_maintenance_district: { key: "road_maintenance_district", label: "Road Maintenance District", url: "https://gis.skagitcountywa.gov/arcgis/rest/services/TransportationUtilities/StormwaterMap/MapServer/15", outFields: "DIST_NO,OBJECTID", notes: "Skagit County Public Works road maintenance district context." },
  group_a_water_systems: { key: "group_a_water_systems", label: "Group A Public Water System Area", url: `${HEALTH}/GroupAWaterSystemsMap/MapServer/7`, outFields: "Water_System_Name,PWS_ID,OBJECTID", notes: "Group A public drinking water system service-area overlay." },
  group_a_b_wells: { key: "group_a_b_wells", label: "Group A and B Wells", url: `${HEALTH}/GroupAandBWells/MapServer/0`, outFields: "PARCEL,PWSNAME,SOURCETYPE,TYPE,OBJECTID,OBJECTID_1,DOHPWSID,DOHSOURCEI,GROUP_,WPHA,DOETAG,QTRSECTION,SECTION,TOWNSHIP,RANGE,X,Y", notes: "Group A source/well locations from the county Group A and B wells service." },
  mtca_cleanup_sites: { key: "mtca_cleanup_sites", label: "WA Ecology MTCA Cleanup Sites", url: `${WA_ECOLOGY_TCP}/0`, outFields: "*", notes: "Washington Ecology Toxics Cleanup Program contaminated cleanup sites and cleanup actions." },
  ust_facilities: { key: "ust_facilities", label: "WA Ecology Underground Storage Tank Facilities", url: `${WA_ECOLOGY_TCP}/5`, outFields: "*", notes: "Washington Ecology underground storage tank facility context." },
  wdfw_priority_habitats: { key: "wdfw_priority_habitats", label: "WDFW Priority Habitats and Species Polygons", url: `${WDFW_PHS}/3`, outFields: "*", notes: "WDFW PHS public polygon habitat/species context; sensitive locations may be generalized under WDFW policy." },
  fema_nfhl_zones: { key: "fema_nfhl_zones", label: "FEMA NFHL Flood Hazard Zones", url: `${FEMA_NFHL}/28`, outFields: "*", notes: "Current FEMA National Flood Hazard Layer flood hazard zones for comparison with county Q3 flood data." },
  fema_nfhl_panels: { key: "fema_nfhl_panels", label: "FEMA NFHL FIRM Panels", url: `${FEMA_NFHL}/3`, outFields: "*", notes: "Current FEMA NFHL FIRM panel metadata and effective map context." },
  dnr_natural_heritage_current: { key: "dnr_natural_heritage_current", label: "WA DNR Natural Heritage Current Element Occurrences", url: `${WA_DNR_NATURAL_HERITAGE}/0`, outFields: "*", notes: "Washington Natural Heritage Program current rare plant, ecosystem, and natural community element occurrences." },
  dnr_managed_lands: { key: "dnr_managed_lands", label: "WA DNR Managed Surface Lands", url: `${WA_DNR_MANAGED_LANDS}/1`, outFields: "*", notes: "DNR-managed surface lands including state trust land context." },
  tribal_lands: { key: "tribal_lands", label: "Tribal Lands", url: `${WA_DNR_NON_DNR_PUBLIC_LANDS}/2`, outFields: "*", notes: "Tribal land administrative boundaries from WA DNR Non-DNR Major Public Lands." },
  forest_practices: { key: "forest_practices", label: "WA DNR Forest Practices Applications", url: `${WA_DNR_FOREST_PRACTICES}/0`, outFields: "*", notes: "Washington DNR forest practices application context, including active/recent timber harvest and forestry applications where available." },
  epa_superfund: { key: "epa_superfund", label: "EPA Superfund Site Boundaries", url: "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0", outFields: "*", notes: "EPA public Superfund/NPL site boundary context." },
};

type GisBundleKey = "core" | "development" | "utilities_services" | "state_federal";

const GIS_BUNDLES: Record<GisBundleKey, GisLayerKey[]> = {
  core: ["zoning", "uga", "npdes", "wria", "watershed_basin", "surface_water_limited_stream", "stream_buffer", "wellhead_protection", "big_lake_water_mitigation"],
  development: ["alluvial_fans", "slope_stability", "landslide_areas", "aerial_interpreted_wetlands", "skagit_wetlands", "hydric_soils", "fema_bfe", "fema_floodway", "fema_flood", "fema_panels", "landfill_influence"],
  utilities_services: ["fire_district", "school_district", "sewer_district", "dike_district", "drainage_district", "road_maintenance_district", "group_a_water_systems", "group_a_b_wells"],
  state_federal: ["mtca_cleanup_sites", "ust_facilities", "wdfw_priority_habitats", "fema_nfhl_zones", "fema_nfhl_panels", "dnr_natural_heritage_current", "dnr_managed_lands", "tribal_lands", "forest_practices", "epa_superfund"],
};

const DEFAULT_BUNDLES: GisBundleKey[] = ["core", "development", "utilities_services", "state_federal"];
const DEFAULT_OVERLAY_LAYERS: GisLayerKey[] = [...GIS_BUNDLES.core, ...GIS_BUNDLES.development, ...GIS_BUNDLES.utilities_services, ...GIS_BUNDLES.state_federal];

function layerList() {
  return {
    default_bundles: DEFAULT_BUNDLES,
    bundles: GIS_BUNDLES,
    layers: Object.values(GIS_LAYERS).map(({ key, label, url, outFields, notes }) => ({ key, label, url, outFields, notes })),
  };
}

function getLayer(key: string | null) {
  const layer = GIS_LAYERS[(key || "") as GisLayerKey];
  if (!layer) throw new Error(`Unknown GIS layer. Use one of: ${Object.keys(GIS_LAYERS).join(", ")}`);
  return layer;
}

function parseLayerKeys(value: string | null, bundleValue: string | null = null) {
  const keys: GisLayerKey[] = [];
  const addKey = (key: GisLayerKey) => { if (!keys.includes(key)) keys.push(key); };

  if (bundleValue) {
    for (const raw of bundleValue.split(",")) {
      const bundle = raw.trim() as GisBundleKey;
      if (!GIS_BUNDLES[bundle]) throw new Error(`Unknown GIS bundle. Use one of: ${Object.keys(GIS_BUNDLES).join(", ")}`);
      GIS_BUNDLES[bundle].forEach(addKey);
    }
  }

  if (value) value.split(",").map((x) => getLayer(x.trim()).key).forEach(addKey);
  if (!keys.length) DEFAULT_OVERLAY_LAYERS.forEach(addKey);
  return keys;
}

async function arcgisRequest(layer: GisLayerConfig, params: Record<string, string>) {
  const body = new URLSearchParams({ f: "json", ...params });
  const res = await fetch(`${layer.url}/query`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded;charset=UTF-8", "accept": "application/json", "user-agent": "OpenSkagit research tool" },
    body,
  });
  const data = await res.json() as any;
  if (!res.ok || data.error) return { error: data.error || `ArcGIS query failed: ${res.status}`, layer: layer.key, raw: data };
  return data;
}

function trimFeature(feature: any, includeGeometry = false) {
  return { attributes: feature?.attributes || {}, ...(includeGeometry ? { geometry: feature?.geometry || null } : {}) };
}

async function getParcelGis(parcel: string, includeGeometry = true) {
  const layer = GIS_LAYERS.parcel;
  const data = await arcgisRequest(layer, {
    where: `PARCELID = '${sqlLiteral(parcel)}'`,
    outFields: layer.outFields,
    returnGeometry: includeGeometry ? "true" : "false",
    outSR: "4326",
    resultRecordCount: "1",
  }) as any;
  if (data.error) return data;
  const feature = data.features?.[0];
  if (!feature) throw new Error(`No parcel geometry found for ${parcel}`);
  return trimFeature(feature, includeGeometry);
}

async function queryGisLayerFromUrl(url: URL) {
  const layer = getLayer(url.searchParams.get("layer"));
  const count = Math.min(Number(url.searchParams.get("limit") || "10") || 10, 50);
  const where = url.searchParams.get("where") || "1=1";
  const returnGeometry = url.searchParams.get("geometry") === "1";
  const outFields = url.searchParams.get("outFields") || layer.outFields;
  const geometry = url.searchParams.get("arcgisGeometry");
  const params: Record<string, string> = { where, outFields, returnGeometry: returnGeometry ? "true" : "false", outSR: "4326", resultRecordCount: String(count) };
  if (geometry) {
    params.geometry = geometry;
    params.geometryType = url.searchParams.get("geometryType") || "esriGeometryPolygon";
    params.inSR = url.searchParams.get("inSR") || "4326";
    params.spatialRel = url.searchParams.get("spatialRel") || "esriSpatialRelIntersects";
  }
  const data = await arcgisRequest(layer, params) as any;
  if (data.error) return data;
  return { layer: layer.key, label: layer.label, count: data.features?.length || 0, exceededTransferLimit: Boolean(data.exceededTransferLimit), features: (data.features || []).map((f: any) => trimFeature(f, returnGeometry)) };
}

async function fetchLayerMetadata(layer: GisLayerConfig): Promise<ArcGisLayerMetadata> {
  const res = await fetch(`${layer.url}?f=json`, { headers: { "accept": "application/json", "user-agent": "OpenSkagit research tool" } });
  const data = await res.json() as ArcGisLayerMetadata;
  if (!res.ok || (data as any).error) return { error: (data as any).error || `Metadata fetch failed: ${res.status}` };
  return data;
}

function compactMetadata(metadata: ArcGisLayerMetadata) {
  return {
    id: metadata.id,
    name: metadata.name,
    type: metadata.type,
    geometryType: metadata.geometryType || null,
    capabilities: metadata.capabilities || null,
    maxRecordCount: metadata.maxRecordCount || null,
    fields: (metadata.fields || []).map((f) => ({ name: f.name, type: f.type, alias: f.alias })),
  };
}

function existingOutFields(layer: GisLayerConfig, metadata: ArcGisLayerMetadata) {
  if (layer.outFields.split(",").map((x) => x.trim()).includes("*")) return "*";
  const fields = new Set((metadata.fields || []).map((f) => f.name.toUpperCase()));
  const requested = layer.outFields.split(",").map((x) => x.trim()).filter(Boolean);
  const valid = requested.filter((name) => fields.has(name.toUpperCase()));
  if (valid.length) return valid.join(",");
  if (fields.has("OBJECTID")) return "OBJECTID";
  if (metadata.fields?.[0]?.name) return metadata.fields[0].name;
  return "*";
}

async function gisLayerMetadata(key: string | null) {
  const layer = getLayer(key);
  const metadata = await fetchLayerMetadata(layer);
  return { layer: layer.key, label: layer.label, configured_url: layer.url, configured_outFields: layer.outFields, metadata: compactMetadata(metadata) };
}

async function queryOverlayLayer(layer: GisLayerConfig, geometryText: string) {
  const metadata = await fetchLayerMetadata(layer);
  const metadataDebug = compactMetadata(metadata);

  if ((metadata as any).error) {
    return { layer: layer.key, label: layer.label, status: "metadata_error", error: (metadata as any).error, metadata_debug: metadataDebug, features: [] };
  }

  if (!metadata.geometryType) {
    return { layer: layer.key, label: layer.label, status: "skipped_non_spatial", reason: "Layer has no geometryType and cannot be intersected with a parcel polygon.", metadata_debug: metadataDebug, features: [] };
  }

  const baseParams = {
    geometry: geometryText,
    geometryType: "esriGeometryPolygon",
    inSR: "4326",
    spatialRel: "esriSpatialRelIntersects",
    returnGeometry: "false",
    resultRecordCount: "25",
  };

  const safeOutFields = existingOutFields(layer, metadata);
  const first = await arcgisRequest(layer, { ...baseParams, outFields: safeOutFields }) as any;

  let data = first;
  let retried_with_all_fields = false;
  if (first.error) {
    retried_with_all_fields = true;
    data = await arcgisRequest(layer, { ...baseParams, outFields: "*" }) as any;
  }

  if (data.error) {
    return {
      layer: layer.key,
      label: layer.label,
      status: "query_error",
      error: data.error,
      configured_outFields: layer.outFields,
      attempted_outFields: safeOutFields,
      retried_with_all_fields,
      metadata_debug: metadataDebug,
      features: [],
    };
  }

  return {
    layer: layer.key,
    label: layer.label,
    status: "ok",
    count: data.features?.length || 0,
    exceededTransferLimit: Boolean(data.exceededTransferLimit),
    outFields_used: safeOutFields,
    retried_with_all_fields,
    metadata: { name: metadata.name, geometryType: metadata.geometryType },
    features: (data.features || []).map((f: any) => trimFeature(f, false)),
  };
}

async function parcelOverlays(parcel: string, layerKeys: GisLayerKey[] = DEFAULT_OVERLAY_LAYERS) {
  const parcelFeature = await getParcelGis(parcel, true) as any;
  const geometry = parcelFeature.geometry;
  if (!geometry) throw new Error(`No parcel geometry returned for ${parcel}`);
  const geometryText = JSON.stringify({ ...geometry, spatialReference: { wkid: 4326 } });
  const overlays = await Promise.all(layerKeys.map((key) => queryOverlayLayer(GIS_LAYERS[key], geometryText)));
  return { parcel, parcel_gis: { attributes: parcelFeature.attributes, geometry: parcelFeature.geometry }, overlays };
}

type CensusGeo = { name?: string; geoid?: string; state?: string; county?: string; tract?: string; block?: string; place?: string; zcta?: string; countySubdivision?: string };

const ACS_YEAR = "2024";
const ACS_VARIABLES: Record<string, string> = {
  B01003_001E: "total_population",
  B01002_001E: "median_age",
  B11001_001E: "households",
  B19013_001E: "median_household_income",
  B17001_001E: "poverty_universe",
  B17001_002E: "below_poverty",
  B25001_001E: "housing_units",
  B25002_002E: "occupied_housing_units",
  B25002_003E: "vacant_housing_units",
  B25003_002E: "owner_occupied_units",
  B25003_003E: "renter_occupied_units",
  B25077_001E: "median_owner_occupied_home_value",
  B25064_001E: "median_gross_rent",
  B15003_001E: "education_25_plus_total",
  B15003_022E: "bachelors_degree",
  B15003_023E: "masters_degree",
  B15003_024E: "professional_degree",
  B15003_025E: "doctorate_degree",
  B08012_001E: "workers_commute_total",
  B08013_001E: "aggregate_commute_minutes",
  B02001_001E: "race_total",
  B02001_002E: "white_alone",
  B02001_003E: "black_alone",
  B02001_004E: "american_indian_alaska_native_alone",
  B02001_005E: "asian_alone",
  B02001_006E: "native_hawaiian_pacific_islander_alone",
  B02001_007E: "some_other_race_alone",
  B02001_008E: "two_or_more_races",
  B03003_003E: "hispanic_or_latino",
  B25034_001E: "year_built_total",
  B25034_002E: "built_2020_or_later",
  B25034_003E: "built_2010_to_2019",
  B25034_004E: "built_2000_to_2009",
  B25034_005E: "built_1990_to_1999",
  B25034_006E: "built_1980_to_1989",
  B25034_007E: "built_1970_to_1979",
  B25034_008E: "built_1960_to_1969",
  B25034_009E: "built_1950_to_1959",
  B25034_010E: "built_1940_to_1949",
  B25034_011E: "built_1939_or_earlier",
};

function centroidOfGeometry(geometry: any) {
  const rings = geometry?.rings;
  if (!Array.isArray(rings) || !rings.length) return null;
  let xSum = 0;
  let ySum = 0;
  let count = 0;
  for (const ring of rings) {
    if (!Array.isArray(ring)) continue;
    for (const point of ring) {
      if (Array.isArray(point) && typeof point[0] === "number" && typeof point[1] === "number") {
        xSum += point[0];
        ySum += point[1];
        count += 1;
      }
    }
  }
  return count ? { longitude: xSum / count, latitude: ySum / count } : null;
}

function firstCensusGeo(geographies: any, names: string[]) {
  for (const name of names) {
    const item = geographies?.[name]?.[0];
    if (item) return item;
  }
  return null;
}

function normalizeCensusGeo(item: any): CensusGeo | null {
  if (!item) return null;
  return {
    name: item.NAME || item.BASENAME || null,
    geoid: item.GEOID || item.GEOIDFQ || null,
    state: item.STATE || null,
    county: item.COUNTY || null,
    tract: item.TRACT || null,
    block: item.BLOCK || null,
    place: item.PLACE || null,
    zcta: item.ZCTA5 || item.ZCTA || null,
    countySubdivision: item.COUSUB || null,
  };
}

async function censusGeographies(longitude: number, latitude: number) {
  const params = new URLSearchParams({
    x: String(longitude),
    y: String(latitude),
    benchmark: "Public_AR_Current",
    vintage: "Current_Current",
    format: "json",
  });
  const res = await fetch(`https://geocoding.geo.census.gov/geocoder/geographies/coordinates?${params}`, {
    headers: { "accept": "application/json", "user-agent": "OpenSkagit research tool" },
  });
  const data = await res.json() as any;
  if (!res.ok || data.errors?.length) return { error: data.errors || `Census geocoder failed: ${res.status}`, raw: data };
  const geos = data.result?.geographies || {};
  const block = normalizeCensusGeo(firstCensusGeo(geos, ["2020 Census Blocks", "Census Blocks"]));
  const blockGroup = normalizeCensusGeo(firstCensusGeo(geos, ["2020 Census Block Groups", "Census Block Groups", "Block Groups"]))
    || (block?.state && block.county && block.tract && block.block
      ? { name: `${block.tract} Block Group ${block.block[0]}`, geoid: `${block.state}${block.county}${block.tract}${block.block[0]}`, state: block.state, county: block.county, tract: block.tract, block: block.block[0] }
      : null);
  return {
    raw: geos,
    block,
    block_group: blockGroup,
    tract: normalizeCensusGeo(firstCensusGeo(geos, ["Census Tracts"])),
    place: normalizeCensusGeo(firstCensusGeo(geos, ["Incorporated Places", "Places"])),
    county_subdivision: normalizeCensusGeo(firstCensusGeo(geos, ["County Subdivisions"])),
    county: normalizeCensusGeo(firstCensusGeo(geos, ["Counties"])),
    zcta: normalizeCensusGeo(firstCensusGeo(geos, ["2020 ZIP Code Tabulation Areas", "ZIP Code Tabulation Areas"])),
  };
}

function censusNumber(value: string | undefined) {
  if (value === undefined || value === null || value === "" || value === "-666666666" || value === "-999999999") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function pct(part: number | null, total: number | null) {
  return part !== null && total ? Number(((part / total) * 100).toFixed(1)) : null;
}

function shapeAcsRecord(raw: Record<string, number | null>) {
  const college = (raw.bachelors_degree || 0) + (raw.masters_degree || 0) + (raw.professional_degree || 0) + (raw.doctorate_degree || 0);
  return {
    demographics: {
      total_population: raw.total_population,
      median_age: raw.median_age,
      race_ethnicity: {
        white_alone_pct: pct(raw.white_alone, raw.race_total),
        black_alone_pct: pct(raw.black_alone, raw.race_total),
        american_indian_alaska_native_alone_pct: pct(raw.american_indian_alaska_native_alone, raw.race_total),
        asian_alone_pct: pct(raw.asian_alone, raw.race_total),
        native_hawaiian_pacific_islander_alone_pct: pct(raw.native_hawaiian_pacific_islander_alone, raw.race_total),
        some_other_race_alone_pct: pct(raw.some_other_race_alone, raw.race_total),
        two_or_more_races_pct: pct(raw.two_or_more_races, raw.race_total),
        hispanic_or_latino_pct: pct(raw.hispanic_or_latino, raw.race_total),
      },
    },
    socioeconomic: {
      households: raw.households,
      median_household_income: raw.median_household_income,
      poverty_rate_pct: pct(raw.below_poverty, raw.poverty_universe),
      bachelors_or_higher_pct: pct(college, raw.education_25_plus_total),
    },
    housing: {
      housing_units: raw.housing_units,
      occupied_housing_units: raw.occupied_housing_units,
      vacancy_rate_pct: pct(raw.vacant_housing_units, raw.housing_units),
      owner_occupied_pct: pct(raw.owner_occupied_units, raw.occupied_housing_units),
      renter_occupied_pct: pct(raw.renter_occupied_units, raw.occupied_housing_units),
      median_owner_occupied_home_value: raw.median_owner_occupied_home_value,
      median_gross_rent: raw.median_gross_rent,
      year_built: {
        total: raw.year_built_total,
        built_2020_or_later: raw.built_2020_or_later,
        built_2010_to_2019: raw.built_2010_to_2019,
        built_2000_to_2009: raw.built_2000_to_2009,
        built_1990_to_1999: raw.built_1990_to_1999,
        built_1980_to_1989: raw.built_1980_to_1989,
        built_1970_to_1979: raw.built_1970_to_1979,
        built_1960_to_1969: raw.built_1960_to_1969,
        built_1950_to_1959: raw.built_1950_to_1959,
        built_1940_to_1949: raw.built_1940_to_1949,
        built_1939_or_earlier: raw.built_1939_or_earlier,
      },
    },
    commute: {
      workers: raw.workers_commute_total,
      mean_commute_minutes: raw.aggregate_commute_minutes !== null && raw.workers_commute_total ? Number((raw.aggregate_commute_minutes / raw.workers_commute_total).toFixed(1)) : null,
    },
    raw,
  };
}

async function acsQuery(geo: CensusGeo | null, level: "block_group" | "tract" | "place" | "county") {
  if (!geo?.state) return null;
  const vars = Object.keys(ACS_VARIABLES);
  const params = new URLSearchParams({ get: ["NAME", ...vars].join(",") });

  if (level === "block_group") {
    if (!geo.county || !geo.tract || !geo.geoid) return null;
    params.set("for", `block group:${geo.geoid.slice(-1)}`);
    params.set("in", `state:${geo.state} county:${geo.county} tract:${geo.tract}`);
  } else if (level === "tract") {
    if (!geo.county || !geo.tract) return null;
    params.set("for", `tract:${geo.tract}`);
    params.set("in", `state:${geo.state} county:${geo.county}`);
  } else if (level === "place") {
    if (!geo.place) return null;
    params.set("for", `place:${geo.place}`);
    params.set("in", `state:${geo.state}`);
  } else {
    if (!geo.county) return null;
    params.set("for", `county:${geo.county}`);
    params.set("in", `state:${geo.state}`);
  }

  const res = await fetch(`https://api.census.gov/data/${ACS_YEAR}/acs/acs5?${params}`, {
    headers: { "accept": "application/json", "user-agent": "OpenSkagit research tool" },
  });
  const data = await res.json() as string[][];
  if (!res.ok || !Array.isArray(data) || data.length < 2) return { error: `ACS ${level} query failed: ${res.status}`, raw: data };
  const headers = data[0];
  const values = data[1];
  const raw: Record<string, number | null> = {};
  vars.forEach((variable) => raw[ACS_VARIABLES[variable]] = censusNumber(values[headers.indexOf(variable)]));
  return { name: values[headers.indexOf("NAME")] || geo.name || null, geography: geo, ...shapeAcsRecord(raw) };
}

async function parcelCensus(parcel: string) {
  const parcelFeature = await getParcelGis(parcel, true) as any;
  const centroid = centroidOfGeometry(parcelFeature.geometry);
  if (!centroid) return { status: "error", error: `No parcel centroid available for ${parcel}` };
  const matched = await censusGeographies(centroid.longitude, centroid.latitude) as any;
  if (matched.error) return { status: "error", centroid, error: matched.error, raw: matched.raw };
  const [blockGroup, tract, place, county] = await Promise.all([
    acsQuery(matched.block_group, "block_group"),
    acsQuery(matched.tract, "tract"),
    acsQuery(matched.place, "place"),
    acsQuery(matched.county, "county"),
  ]);
  return {
    status: "ok",
    source: `US Census ACS ${ACS_YEAR} 5-year detailed tables`,
    note: "Census statistics are matched by parcel centroid to Census geographies; they are area-level estimates, not parcel-level measurements.",
    centroid,
    matched_geographies: {
      block: matched.block,
      block_group: matched.block_group,
      tract: matched.tract,
      place: matched.place,
      county_subdivision: matched.county_subdivision,
      county: matched.county,
      zcta: matched.zcta,
    },
    acs: {
      block_group: blockGroup,
      tract,
      place,
      county,
    },
  };
}

function parcelGeometryToWkt(geometry: any) {
  const rings = geometry?.rings;
  if (!Array.isArray(rings) || !rings.length) return null;
  const wktRings = rings
    .filter((ring) => Array.isArray(ring) && ring.length >= 4)
    .map((ring) => {
      const points = ring
        .filter((point: unknown) => Array.isArray(point) && typeof point[0] === "number" && typeof point[1] === "number")
        .map((point: number[]) => `${point[0]} ${point[1]}`);
      if (points.length && points[0] !== points[points.length - 1]) points.push(points[0]);
      return points.length >= 4 ? `(${points.join(",")})` : null;
    })
    .filter((ring): ring is string => Boolean(ring));
  return wktRings.length ? `POLYGON(${wktRings.join(",")})` : null;
}

function parseNrcsTable(data: any) {
  const table = data?.Table || data?.Table1 || data?.tables?.[0]?.rows || data;
  if (!Array.isArray(table) || !table.length) return [];
  const headers = Array.isArray(table[0]) ? table[0].map((header: unknown) => String(header)) : null;
  if (!headers) return table;
  return table.slice(1).map((row: unknown[]) => Object.fromEntries(headers.map((header: string, idx: number) => [header, row[idx] ?? null])));
}

async function parcelSoils(parcel: string) {
  const parcelFeature = await getParcelGis(parcel, true) as any;
  const wkt = parcelGeometryToWkt(parcelFeature.geometry);
  if (!wkt) return { status: "error", error: `No parcel polygon available for NRCS soils query for ${parcel}` };

  const query = `
    SELECT DISTINCT
      mu.mukey,
      mu.musym,
      mu.muname,
      mu.mukind,
      ma.drclassdcd,
      ma.flodfreqdcd,
      ma.niccdcd,
      ma.farmlndcl,
      ma.hydgrpdcd
    FROM mapunit mu
    LEFT JOIN muaggatt ma ON mu.mukey = ma.mukey
    WHERE mu.mukey IN (
      SELECT mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('${wkt}')
    )
    ORDER BY mu.musym
  `;
  const body = new URLSearchParams({
    SERVICE: "query",
    REQUEST: "query",
    FORMAT: "JSON+COLUMNNAME",
    QUERY: query,
  });
  const res = await fetch("https://sdmdataaccess.nrcs.usda.gov/Tabular/post.rest", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded", "accept": "application/json", "user-agent": "OpenSkagit research tool" },
    body,
  });
  const text = await res.text();
  let data: any = text;
  try {
    data = JSON.parse(text);
  } catch {
    // Keep raw text below for diagnostics.
  }
  if (!res.ok) return { status: "error", source: "NRCS Soil Data Access", error: `NRCS soils query failed: ${res.status}`, raw: typeof data === "string" ? data.slice(0, 1200) : data };
  const mapunits = parseNrcsTable(data);
  return {
    status: "ok",
    source: "NRCS Soil Data Access SSURGO",
    note: "Soil map units are intersected with the parcel polygon using NRCS SDA. Soil attributes are map-unit level and may not represent every point on the parcel.",
    mapunit_count: mapunits.length,
    mapunits,
  };
}

function cleanParcel(value: string | null) {
  const parcel = (value || "").trim().toUpperCase();
  if (!/^P\d{1,10}$/.test(parcel)) throw new Error("Use a parcel number like P45283");
  return parcel;
}

function htmlDecode(value: string) {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&#xA;/gi, "\n")
    .replace(/&#x9;/gi, "\t")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}

function stripTags(html: unknown) {
  if (typeof html !== "string") return "";
  return htmlDecode(html)
    .replace(/<br\s*\/?\s*>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function htmlText(html: unknown) {
  if (typeof html !== "string") return "";
  return htmlDecode(html)
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<\/tr>/gi, "\n")
    .replace(/<\/td>/gi, "\t")
    .replace(/<\/th>/gi, "\t")
    .replace(/<[^>]*>/g, " ")
    .replace(/[ \t\r]+/g, " ")
    .replace(/\n\s+/g, "\n")
    .replace(/\s+\n/g, "\n")
    .trim();
}

function compact(value?: string | null) {
  return value?.replace(/\s+/g, " ").trim() || null;
}

function money(value?: string | null) {
  const cleaned = value?.replace(/[^\d.-]/g, "") || "";
  return cleaned ? Number(cleaned) : null;
}

function numberValue(value?: string | null) {
  const match = value?.match(/[\d,.]+/);
  return match ? Number(match[0].replace(/,/g, "")) : null;
}

function firstMatch(text: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return compact(match[1]);
  }
  return null;
}

function absoluteSkagitUrl(path: string | null) {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  return `https://www.skagitcounty.net${path.startsWith("/") ? "" : "/"}${path}`;
}

function tableCells(rowHtml: string) {
  const cells: string[] = [];
  const re = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
  let match: RegExpExecArray | null;
  while ((match = re.exec(rowHtml))) {
    const cell = stripTags(match[1]);
    if (cell) cells.push(cell);
  }
  return cells;
}

function tableRows(html: unknown) {
  if (typeof html !== "string") return [] as string[][];
  const rows: string[][] = [];
  const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let match: RegExpExecArray | null;
  while ((match = trRe.exec(html))) {
    const cells = tableCells(match[1]);
    if (cells.length) rows.push(cells);
  }
  return rows;
}

function tagAttrs(tag: string) {
  const attrs: Record<string, string> = {};
  const re = /([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(tag))) attrs[match[1].toLowerCase()] = htmlDecode(match[2] ?? match[3] ?? match[4] ?? "");
  return attrs;
}

function formValues(html: string) {
  const values = new URLSearchParams();
  const inputRe = /<input\b[^>]*>/gi;
  let inputMatch: RegExpExecArray | null;
  while ((inputMatch = inputRe.exec(html))) {
    const attrs = tagAttrs(inputMatch[0]);
    const name = attrs.name;
    if (!name) continue;
    const type = (attrs.type || "text").toLowerCase();
    if ((type === "checkbox" || type === "radio") && !/\schecked(?:\s|=|>)/i.test(inputMatch[0])) continue;
    if (type === "submit" || type === "button" || type === "image") continue;
    values.append(name, attrs.value || "");
  }

  const selectRe = /<select\b([^>]*)>([\s\S]*?)<\/select>/gi;
  let selectMatch: RegExpExecArray | null;
  while ((selectMatch = selectRe.exec(html))) {
    const attrs = tagAttrs(selectMatch[1]);
    const name = attrs.name;
    if (!name) continue;
    const options = [...selectMatch[2].matchAll(/<option\b[^>]*>([\s\S]*?)<\/option>/gi)];
    const selected = options.find((option) => /\sselected(?:\s|=|>)/i.test(option[0])) || options[0];
    if (!selected) continue;
    const optionAttrs = tagAttrs(selected[0]);
    values.set(name, optionAttrs.value ?? stripTags(selected[1]));
  }

  return values;
}

function isLabel(value: string) {
  return /^[A-Za-z0-9 /*'().-]+:?$/.test(value) && value.length <= 55 && !/^\$?[\d,.]+$/.test(value);
}

function parseLabeledRows(html: unknown) {
  if (typeof html !== "string") return {} as Record<string, string>;
  const rows: Record<string, string> = {};
  const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let match: RegExpExecArray | null;

  while ((match = trRe.exec(html))) {
    const cells = tableCells(match[1]).filter((cell) => cell !== ":");
    if (cells.length < 2) continue;

    if (cells.length === 2 && isLabel(cells[0])) {
      rows[cells[0].replace(/:$/, "")] ||= cells[1];
      continue;
    }

    for (let i = 0; i < cells.length - 1; i += 2) {
      if (isLabel(cells[i])) rows[cells[i].replace(/:$/, "")] ||= cells[i + 1];
    }
  }

  return rows;
}

function getRowValue(html: unknown, label: string) {
  const rows = parseLabeledRows(html);
  return rows[label] || null;
}

function parseSales(html: unknown) {
  if (typeof html !== "string") return [];
  const blocks = html.split(/<strong>\s*SALE\s+NUMBER\s+\d+\s*<\/strong>/i).slice(1);
  return blocks
    .map((block) => {
      const rows = parseLabeledRows(block);
      return {
        date: rows["Sale Date"] || null,
        price: money(rows["Taxable Selling Price"]),
        deed_type: rows["Deed Type"] || null,
        seller: rows.Seller || null,
        buyer: rows.Buyer || null,
        auditor_file_number: rows["Auditor File Number"] || null,
        excise_number: rows["Excise Number"] || null,
        reval_area: rows["Reval Area"] || null,
        sale_parcels: rows["Sale Parcels"] || null,
      };
    })
    .filter((sale) => sale.date || sale.price || sale.deed_type || sale.seller || sale.buyer);
}

function parseValueHistory(html: unknown) {
  return tableRows(html)
    .filter((cells) => cells.length >= 7 && /^\d{4}$/.test(cells[0]) && /^\d{4}$/.test(cells[1]))
    .map((cells) => ({
      value_year: Number(cells[0]),
      tax_year: Number(cells[1]),
      building_market_value: money(cells[2]),
      land_market_value: money(cells[3]),
      market_total: money(cells[4]),
      land_assessed: money(cells[5]),
      assessed_total: money(cells[6]),
      tax: money(cells[7]),
    }));
}

function parseTaxYears(html: unknown) {
  if (typeof html !== "string") return [] as { year: number; label: string; current: boolean }[];
  const years: { year: number; label: string; current: boolean }[] = [];
  const optionRe = /<option[^>]*value=["']?(\d{4})["']?[^>]*>([\s\S]*?)<\/option>/gi;
  let match: RegExpExecArray | null;
  while ((match = optionRe.exec(html))) {
    const label = stripTags(match[2]);
    years.push({ year: Number(match[1]), label, current: /current/i.test(label) });
  }
  return years;
}

function parseInstallment(text: string, year: number, label: "first" | "second", dueLabel: string) {
  const re = new RegExp(`${year}\\s+${dueLabel}\\s+Installment\\s+DUE\\s+by\\s+([^:]+):\\s*(PAID:)?\\s*(\\$[\\d,.]+)`, "i");
  const match = text.match(re);
  return match ? { status: match[2] ? "paid" : "due", due_by: compact(match[1]), amount: money(match[3]) } : null;
}

function parseTaxStatement(html: unknown) {
  if (typeof html !== "string") return null;
  const text = htmlText(html);
  const year = Number(firstMatch(text, [/(\d{4})\s+Real Estate Tax Statement/i, /(\d{4})\s+Property Tax, Assessments, and Fees/i]));
  if (!year) return null;

  const rows = tableRows(html);
  const districts: { district: string; rate: number | null; amount: number | null }[] = [];
  const specialAssessments: { name: string; amount: number | null }[] = [];
  let mode: "none" | "districts" | "special" = "none";
  let total: number | null = null;

  for (const cells of rows) {
    const rowText = cells.join(" ");
    if (/Tax District/i.test(rowText) && /Rate/i.test(rowText) && /Amount/i.test(rowText)) {
      mode = "districts";
      continue;
    }
    if (/Special Assessment and Fees/i.test(rowText)) {
      mode = "special";
      continue;
    }
    if (/Property Tax, Assessments, and Fees Total/i.test(rowText)) {
      total = money(cells[cells.length - 1]);
      mode = "none";
      continue;
    }
    if (mode === "districts" && cells.length >= 3 && !/^\d{4}/.test(cells[0])) {
      districts.push({ district: cells[0], rate: numberValue(cells[1]), amount: money(cells[2]) });
    }
    if (mode === "special" && cells.length >= 2 && !/Property Tax/i.test(rowText)) {
      specialAssessments.push({ name: cells[0], amount: money(cells[cells.length - 1]) });
    }
  }

  const labeled = parseLabeledRows(html);
  const totalDueKey = Object.keys(labeled).find((key) => new RegExp(`^${year} Total Due$`, "i").test(key));
  const amountPaidKey = Object.keys(labeled).find((key) => new RegExp(`^${year} Amount Paid$`, "i").test(key));

  return {
    year,
    installments: {
      first: parseInstallment(text, year, "first", "First"),
      second: parseInstallment(text, year, "second", "Second"),
    },
    summary: {
      levy_code: labeled["Levy Code"] || null,
      levy_rate: labeled["Levy Rate"] || null,
      land_market_value: money(labeled["Land Market Value"]),
      building_market_value: money(labeled["Building Market Value"]),
      total_market_value: money(labeled["Total Market Value"]),
      taxable_value: money(labeled["Taxable Value"]),
      general_tax: money(labeled["General Tax"]),
      special_assessment_fees: money(labeled["Special Assessment/Fees"]),
      exemptions: money(labeled.Exemptions),
      total_due: money(totalDueKey ? labeled[totalDueKey] : null),
      amount_paid: money(amountPaidKey ? labeled[amountPaidKey] : null),
    },
    districts,
    special_assessments: specialAssessments,
    total_tax_assessments_fees: total,
  };
}

function parseComparableSales(html: unknown) {
  if (typeof html !== "string") return { status: "unavailable", subject: null, sales: [], rows: [] };
  const rows = tableRows(html).filter((cells) => cells.length >= 2);
  const header = rows.find((cells) => /^Features$/i.test(cells[0]));
  if (!header) return { status: "no_results", subject: null, sales: [], rows: [] };

  const labels = header.slice(1);
  const columns = labels.map((label) => ({ label, fields: {} as Record<string, string | number | null> }));

  for (const cells of rows) {
    const field = cells[0].trim();
    if (!field || /^Features$/i.test(field) || /recorded sales acquired/i.test(field)) continue;
    cells.slice(1).forEach((value, idx) => {
      if (columns[idx]) columns[idx].fields[field] = value || null;
    });
  }

  const photoHrefs = [...html.matchAll(/<a[^>]+href=['"]([^'"]*\/Assessor\/Images\/PublicImages\/[^'"]+\.jpg)['"][\s\S]*?<img/gi)]
    .map((match) => absoluteSkagitUrl(htmlDecode(match[1])));
  photoHrefs.forEach((href, idx) => {
    if (columns[idx]) columns[idx].fields.photo_url = href;
  });

  const normalize = (column: { label: string; fields: Record<string, string | number | null> }, idx: number) => {
    const f = column.fields;
    const parcelId = compact(String(f["Property ID"] || ""));
    return {
      role: idx === 0 ? "subject" : "sale",
      label: column.label,
      parcel: parcelId ? `P${parcelId.replace(/^P/i, "")}` : null,
      address: f.Address || null,
      city: f.City || null,
      neighborhood: f.Neighborhood || null,
      region: f.Region || null,
      market_value_or_sale_price: money(String(f["Market Value/Sale Price"] || "")),
      price_per_sq_ft: money(String(f["Price Per Sq Ft"] || "")),
      appraisal_year_or_sale_date: f["Appraisal Year/Sale Date"] || null,
      excise_number: f["Excise Number"] || null,
      year_built: numberValue(String(f["Year Built"] || "")),
      building_style: f["Building Style"] || null,
      building_quality: f["Building Quality"] || null,
      building_condition: f["Building Condition"] || null,
      above_grade_living_area: numberValue(String(f["Above Grade Living Area"] || "")),
      total_living_area: numberValue(String(f["Total Living Area"] || "")),
      basement_sq_ft: numberValue(String(f["Basement Sq Ft"] || "")),
      bedrooms: numberValue(String(f.Bedrooms || "")),
      bathrooms: f.Bathrooms || null,
      heat_type: f["Heat Type"] || null,
      fireplace: f.Fireplace || null,
      garage_carport_sq_ft: numberValue(String(f["Garage/Carport Sq Ft"] || "")),
      porch_sq_ft: numberValue(String(f["Porch Sq Ft"] || "")),
      acres: numberValue(String(f.Acres || "")),
      photo_url: f.photo_url || null,
      raw: f,
    };
  };

  const normalized = columns.map(normalize);
  return {
    status: "ok",
    source: "Skagit County PropertySales Comparable Sales",
    subject: normalized[0] || null,
    sales: normalized.slice(1),
    rows,
  };
}

function parseComparableSearchResults(html: unknown) {
  const rows = tableRows(html);
  let section: "subject" | "subject_sales" | "candidates" | null = null;
  let headers: string[] = [];
  const subject: Record<string, unknown>[] = [];
  const subjectSales: Record<string, unknown>[] = [];
  const candidates: Record<string, unknown>[] = [];

  const normalizeHeader = (header: string) => header
    .replace(/^PID\s*-\s*(Subject|Sales Subject|Sales Compare)$/i, "PID")
    .replace(/\s+/g, " ")
    .trim();

  const parseRow = (cells: string[]) => {
    const mapped: Record<string, string> = {};
    headers.forEach((header, idx) => mapped[normalizeHeader(header)] = cells[idx] || "");
    const pid = mapped.PID || cells.find((cell) => /^\d{3,10}$/.test(cell)) || "";
    return {
      parcel: pid ? `P${pid.replace(/^P/i, "")}` : null,
      address: mapped.Address || null,
      region: mapped.Region || null,
      neighborhood: mapped.Neighborhood || null,
      appraisal_year: numberValue(mapped["Appr Yr"]),
      sale_date: mapped["Sale Date"] || null,
      market_value: money(mapped["Market Value"]),
      sale_price: money(mapped["Sale Price"]),
      price_per_sq_ft: money(mapped["Price/SqFt"]),
      year_built: numberValue(mapped["Act Yr Blt"]),
      above_grade_living_area: numberValue(mapped.AGLA),
      finished_basement_area: numberValue(mapped["Fin Bsmnt Area"]),
      total_living_area: numberValue(mapped["Tot Living Area"]),
      unfinished_basement_area: numberValue(mapped["Unfin Bsmnt Area"]),
      acres: numberValue(mapped.Acres),
      bedrooms: numberValue(mapped.Bdrms),
      bathrooms: mapped.Bathrooms || null,
      building_style: mapped["Bldg Style"] || null,
      condition: mapped.Condition || null,
      quality: mapped.Quality || null,
      raw: mapped,
    };
  };

  for (const cells of rows) {
    const first = cells[0]?.trim() || "";
    if (/^PID\s*-\s*Subject$/i.test(first)) {
      section = "subject";
      headers = cells.map(normalizeHeader);
      continue;
    }
    if (/^PID\s*-\s*Sales Subject$/i.test(first)) {
      section = "subject_sales";
      headers = cells.map(normalizeHeader);
      continue;
    }
    if (/^PID\s*-\s*Sales Compare$/i.test(first)) {
      section = "candidates";
      headers = cells.map(normalizeHeader);
      continue;
    }
    if (!section || !headers.length) continue;
    if (!cells.some((cell) => /^\d{3,10}$/.test(cell))) continue;

    const parsed = parseRow(cells);
    if (section === "subject") subject.push(parsed);
    if (section === "subject_sales") subjectSales.push(parsed);
    if (section === "candidates") candidates.push(parsed);
  }

  const countText = typeof html === "string" ? firstMatch(htmlText(html), [/(\d+)\s+Sales Found/i]) : null;
  return {
    status: candidates.length || subject.length || subjectSales.length ? "ok" : "no_results",
    count: numberValue(countText),
    subject: subject[0] || null,
    subject_sales: subjectSales,
    candidates,
  };
}

function parseSegments(html: unknown) {
  if (typeof html !== "string") return [];
  const blocks = html.split(/<b>\s*Improvement\s+\d+\s*,\s*Segment\s+\d+\s*<\/b>/i).slice(1);
  return blocks
    .map((block) => {
      const rows = parseLabeledRows(block);
      return {
        description: rows.Description || null,
        quality_class: rows["Quality/Class"] || null,
        condition: rows.Condition || null,
        area: numberValue(rows.Area),
        foundation: rows.Foundation || null,
        exterior_wall: rows["Exterior Wall"] || null,
        roof_covering: rows["Roof Covering"] || null,
        floor_covering: rows["Floor Covering"] || null,
        plumbing: rows.Plumbing || null,
        heat_air_conditioning: rows["Heat-Air Conditioning"] || null,
        bedrooms: numberValue(rows.Bedrooms),
        year_built: numberValue(rows["Year Built"]),
      };
    })
    .filter((segment) => segment.description || segment.area || segment.year_built);
}

function parseHeaderGrid(html: unknown) {
  if (typeof html !== "string") return {} as Record<string, string>;
  const rowMatches = [...html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)].map((m) => tableCells(m[1]));
  for (let i = 0; i < rowMatches.length - 1; i++) {
    const headers = rowMatches[i];
    const values = rowMatches[i + 1];
    if (headers.includes("Parcel Number") && values.length >= headers.length) {
      const out: Record<string, string> = {};
      headers.forEach((header, idx) => out[header] = values[idx] || "");
      return out;
    }
  }
  return {};
}

function parseLegal(html: unknown) {
  if (typeof html !== "string") return null;
  const match = html.match(/<legal[^>]*>([\s\S]*?)<\/legal>/i);
  return match ? stripTags(match[1]) : null;
}

function parseSiteAddress(detailsHtml: unknown) {
  if (typeof detailsHtml !== "string") return null;
  const text = htmlText(detailsHtml);
  const block = firstMatch(text, [
    /Site Address\(es\)\s*\.?\s*\n([\s\S]*?)(?:\n\s*(?:Map Links|Current Legal Description|Owner Information|Property Information|Appraisal Information)\b)/i,
  ]);

  if (block) {
    const lines = block
      .split(/\n+/)
      .map((line) => compact(line.replace(/\(Jurisdiction,\s*State\)/i, "")))
      .filter((line): line is string => Boolean(line))
      .filter((line) => !/^(Site Address|Map Links|Zip Code Lookup)$/i.test(line));
    if (lines.length) return compact(lines.slice(0, 2).join(", "));
  }

  const siteAddress = firstMatch(text, [/Site Address\(es\)\s*\.?\s*\n([^\n]+)/i]);
  const cityState = firstMatch(text, [/Site Address\(es\)[\s\S]*?\n([^\n]*,\s*WA[^\n]*)/i]);
  const parsed = compact([siteAddress, cityState?.replace(/\(Jurisdiction,\s*State\)/i, "")].filter(Boolean).join(", "));
  return parsed || null;
}

function parseUtilities(detailRows: Record<string, string>, detailsHtml: unknown) {
  const candidates = [
    detailRows.Utilities,
    typeof detailsHtml === "string" ? firstMatch(htmlText(detailsHtml), [/Utilities\s*:?\s*\n([^\n]+)/i]) : null,
  ];
  const badValues = new Set([
    "ACRES",
    "LAND SEGMENT SIZE",
    "MARKET VALUE",
    "DESCRIPTION",
    "APPRAISAL METHOD",
    "LAND FRONT SIZE",
    "BUILDING STYLE",
  ]);

  for (const candidate of candidates) {
    const value = compact(candidate || "");
    if (!value) continue;
    const normalized = value.replace(/:$/, "").toUpperCase();
    if (badValues.has(normalized)) continue;
    if (/^\$?[\d,.]+(?:\s*(?:ACRES?|SQUARE FEET|SQ\.?\s*FT\.?))?$/i.test(value)) continue;
    return value;
  }
  return null;
}

function splitParcelList(value: unknown) {
  return String(value || "")
    .toUpperCase()
    .split(/[^A-Z0-9]+/)
    .map((part) => part.trim())
    .filter((part) => /^P\d{1,10}$/.test(part));
}

function relatedParcels(parcel: string, sales: any[]) {
  const subject = parcel.toUpperCase();
  const fromSales = new Set<string>();
  const saleEvents: { date: unknown; price: unknown; sale_parcels: unknown }[] = [];

  for (const sale of sales || []) {
    const parcels = splitParcelList(sale?.sale_parcels);
    const related = parcels.filter((pid) => pid !== subject);
    if (!related.length) continue;
    related.forEach((pid) => fromSales.add(pid));
    saleEvents.push({ date: sale.date || null, price: sale.price ?? null, sale_parcels: sale.sale_parcels || null });
  }

  return {
    from_sales: [...fromSales],
    likely_assemblage: fromSales.size > 0,
    sale_events: saleEvents,
  };
}

function percentChange(current: number | null | undefined, previous: number | null | undefined) {
  return typeof current === "number" && typeof previous === "number" && previous !== 0
    ? Number((((current - previous) / previous) * 100).toFixed(1))
    : null;
}

function currentTaxStatement(summary: any) {
  const statements = summary?.taxes?.statements_by_year || {};
  const years = Object.keys(statements).map((year) => Number(year)).filter(Number.isFinite).sort((a, b) => b - a);
  return years.length ? { year: years[0], statement: statements[String(years[0])] } : { year: null, statement: null };
}

function valueTrends(summary: any) {
  const history = [...(summary?.value_history || [])]
    .filter((row) => Number.isFinite(row?.tax_year))
    .sort((a, b) => Number(b.tax_year) - Number(a.tax_year));
  const latest = history[0] || null;
  const baseline = latest ? history.find((row) => Number(row.tax_year) <= Number(latest.tax_year) - 5) || history[4] || null : null;
  const { year: currentTaxYear, statement } = currentTaxStatement(summary);
  const currentAssessed = statement?.summary?.taxable_value ?? summary?.values?.taxable_value ?? latest?.assessed_total ?? null;
  const currentTax = statement?.total_tax_assessments_fees ?? summary?.taxes?.total_taxes ?? latest?.tax ?? null;
  const taxPerThousand = typeof currentTax === "number" && typeof currentAssessed === "number" && currentAssessed > 0
    ? Number(((currentTax / currentAssessed) * 1000).toFixed(2))
    : null;
  const years = history.map((row) => Number(row.tax_year)).filter(Number.isFinite);

  return {
    latest_value_year: latest?.value_year ?? null,
    latest_tax_year: latest?.tax_year ?? null,
    current_statement_tax_year: currentTaxYear,
    five_year_baseline_tax_year: baseline?.tax_year ?? null,
    land_value_change_5yr_pct: percentChange(latest?.land_market_value, baseline?.land_market_value),
    assessed_value_change_5yr_pct: percentChange(latest?.assessed_total, baseline?.assessed_total),
    tax_change_5yr_pct: percentChange(latest?.tax, baseline?.tax),
    current_tax_per_1000_assessed: taxPerThousand,
    building_value_present: Boolean((summary?.values?.building_market_value || 0) > 0 || (summary?.improvement_summary?.living_area || 0) > 0),
    history_span: years.length ? { first_tax_year: Math.min(...years), last_tax_year: Math.max(...years), years: years.length } : { first_tax_year: null, last_tax_year: null, years: 0 },
  };
}

function agentFlags(summary: any, comps: any, census: any, related: any, trends: any) {
  const flags: { severity: "info" | "warning" | "critical"; code: string; message: string; evidence?: unknown }[] = [];
  const add = (severity: "info" | "warning" | "critical", code: string, message: string, evidence?: unknown) => {
    flags.push(evidence === undefined ? { severity, code, message } : { severity, code, message, evidence });
  };

  if (!summary?.site_address) add("warning", "missing_site_address", "No site address was parsed for this parcel.");
  if (summary?.utilities === "Acres") add("warning", "bad_utilities_parse", "Utilities looked like table bleed-through instead of a real utility value.", summary.utilities);
  if (typeof summary?.acres === "number" && summary.acres < 0.05) add("warning", "tiny_parcel", "Parcel area is unusually small and may be part of an assemblage or remnant.", { acres: summary.acres });
  if (/UNDEVELOPED|VACANT/i.test(summary?.use_code || "") || trends?.building_value_present === false) {
    add("info", "vacant_or_unimproved", "Parcel appears vacant or unimproved from use code, building value, or living area.", {
      use_code: summary?.use_code || null,
      building_market_value: summary?.values?.building_market_value ?? null,
      living_area: summary?.improvement_summary?.living_area ?? null,
    });
  }
  if (related?.likely_assemblage) add("warning", "multi_parcel_sale_history", "Sale history references other parcels sold with the subject.", related);
  const searchResults = comps?.search_results;
  const hasComps = comps?.status === "ok" && ((searchResults?.candidates?.length || 0) > 0 || (searchResults?.subject_sales?.length || 0) > 0 || (comps?.comparables?.length || 0) > 0);
  if (!hasComps) add("warning", "comps_unavailable", "Comparable sales were not available as structured selected results.", { status: comps?.status || null, search_results_status: searchResults?.status || null });
  if (census?.status === "ok") add("info", "census_area_estimate", "Census values are area-level estimates matched by parcel centroid, not parcel-level facts.", census.note || null);
  if (/contact the city/i.test(summary?.zoning_note || "")) add("info", "incorporated_city_zoning_required", "County record indicates city zoning should be verified with the incorporated jurisdiction.", { jurisdiction: summary?.jurisdiction || null, zoning_note: summary?.zoning_note || null });

  return flags;
}

function parsePropertySummary(parcel: string, pages: DossierPages, taxDetailPages: Record<string, unknown> = {}) {
  const detailsHtml = pages.details;
  const improvementsHtml = pages.improvements;
  const landHtml = pages.land;
  const salesHtml = pages.sales;
  const historyHtml = pages.history;
  const taxesHtml = pages.taxes;

  const detailsText = htmlText(detailsHtml);
  const detailRows = parseLabeledRows(detailsHtml);
  const headerGrid = parseHeaderGrid(detailsHtml);
  const landRows = parseLabeledRows(landHtml);
  const sales = parseSales(salesHtml);
  const taxStatements = Object.fromEntries(
    [[String(parseTaxStatement(taxesHtml)?.year || ""), parseTaxStatement(taxesHtml)], ...Object.entries(taxDetailPages).map(([year, html]) => [year, parseTaxStatement(html)])]
      .filter(([year, statement]) => year && statement)
  );
  const segments = parseSegments(improvementsHtml);
  const mainSegment = segments.find((s) => s.description === "MAIN AREA") || segments[0];

  const sketchPath = typeof improvementsHtml === "string"
    ? firstMatch(improvementsHtml, [/HREF="([^"]*\/assessor\/images\/photos\/[^"]+\.jpg)"/i])
    : null;
  const photoPath = typeof detailsHtml === "string"
    ? firstMatch(detailsHtml, [/src=['"]([^'"]*\/Assessor\/Images\/PublicImages\/[^'"]+\.jpg)['"]/i])
    : null;

  const owner = firstMatch(detailsText, [/Owner Information\s*\n([^\n]+)/i]);
  const ownerMailing = firstMatch(detailsText, [/Owner Information\s*\n[^\n]+\n([^\n]+\n[^\n]+)/i]);

  return {
    parcel,
    xref_id: headerGrid.XrefID || null,
    owner,
    owner_mailing: ownerMailing,
    site_address: parseSiteAddress(detailsHtml),
    jurisdiction: detailRows.Jurisdiction || firstMatch(detailsText, [/Jurisdiction:\s*\n?([^\n]+)/i]),
    zoning_note: firstMatch(detailsText, [/Zoning Designation:\s*\n?([^\n]+)/i]),
    legal: parseLegal(detailsHtml),
    use_code: getRowValue(detailsHtml, "*Assessment Use Code") || firstMatch(detailsText, [/Assessment Use Code\s+([^\n]+)/i]),
    neighborhood: detailRows.Neighborhood || firstMatch(detailsText, [/Neighborhood\s+([^\n]+)/i]),
    levy_code: detailRows["Levy Code"] || null,
    school_district: detailRows["School District"] || null,
    utilities: parseUtilities(detailRows, detailsHtml),
    acres: numberValue(detailRows.Acres || landRows["Land Segment Size"]),
    values: {
      building_market_value: money(firstMatch(detailsText, [/Building Market Value\s+([$\d,.]+)/i])),
      land_market_value: money(firstMatch(detailsText, [/Land Market Value\s+\+?([$\d,.]+)/i])),
      total_market_value: money(firstMatch(detailsText, [/Total Market Value\s+([$\d,.]+)/i])),
      assessed_value: money(firstMatch(detailsText, [/Assessed Value\s+([$\d,.]+)/i])),
      taxable_value: money(firstMatch(detailsText, [/Taxable Value\s+([$\d,.]+)/i])),
    },
    taxes: {
      taxable_value_2026: money(firstMatch(detailsText, [/2026 Taxable Value\s+([$\d,.]+)/i])),
      general_taxes: money(firstMatch(detailsText, [/General Taxes\s+([$\d,.]+)/i])),
      special_assessments: money(firstMatch(detailsText, [/Special Assessments\/Fees\s+\+?([$\d,.]+)/i])),
      total_taxes: money(firstMatch(detailsText, [/Total Taxes\s+([$\d,.]+)/i])),
      available_statement_years: parseTaxYears(taxesHtml),
      statements_by_year: taxStatements,
    },
    value_history: parseValueHistory(historyHtml),
    improvement_summary: {
      building_style: detailRows["Building Style"] || null,
      year_built: numberValue(detailRows["Year Built"] || String(mainSegment?.year_built || "")),
      living_area: numberValue(detailRows["*Total Living Area"] || detailRows["Above Grade Living Area"] || String(mainSegment?.area || "")),
      above_grade_living_area: numberValue(detailRows["Above Grade Living Area"] || String(mainSegment?.area || "")),
      bedrooms: numberValue(detailRows.Bedrooms || String(mainSegment?.bedrooms || "")),
      bathrooms: detailRows.Bathrooms || mainSegment?.plumbing || null,
      garage_area: numberValue(detailRows["*Total Garage Area"]),
      foundation: detailRows.Foundation || mainSegment?.foundation || null,
      exterior_walls: detailRows["Exterior Walls"] || mainSegment?.exterior_wall || null,
      roof_covering: detailRows["Roof Covering"] || mainSegment?.roof_covering || null,
      heat_air_conditioning: detailRows["Heat/Air Conditioning"] || mainSegment?.heat_air_conditioning || null,
    },
    land: {
      acres: numberValue(landRows["Land Segment Size"]),
      square_feet: numberValue(firstMatch(htmlText(landHtml), [/Land Segment Size:\s*([\d,.]+) Square Feet/i])),
      frontage_feet: numberValue(landRows["Land Front Size"]),
      appraisal_method: landRows["Appraisal Method"] || null,
      description: landRows.Description || null,
      market_value: money(landRows["Market Value"]),
    },
    latest_sale: sales[0] || null,
    sales,
    transfers: sales,
    improvement_segments: segments,
    links: {
      photo_url: absoluteSkagitUrl(photoPath),
      sketch_url: absoluteSkagitUrl(sketchPath),
      imap_url: `https://www.skagitcounty.net/Maps/iMap/?pid=${parcel}`,
      recorded_documents_url: `https://www.skagitcounty.net/Search/Recording/results.aspx?PA=${parcel}&SC=DateRecorded&SO=DESC`,
      excise_affidavits_url: `https://www.skagitcounty.net/Search/DocByType/default.aspx?app=Excise+Affidavits&name=PNumber&value=${parcel}&sort=DateOfDocument%20DESC`,
    },
  };
}

async function postAsmx(base: string, method: string, body: Record<string, string>) {
  const res = await fetch(`${base}/${method}`, {
    method: "POST",
    headers: {
      "content-type": "application/json; charset=utf-8",
      "accept": "application/json, text/javascript, */*; q=0.01",
      "user-agent": "OpenSkagit research tool",
    },
    body: JSON.stringify(body),
  });

  const text = await res.text();
  if (!res.ok) return { ok: false, status: res.status, body: text.slice(0, 1200) };

  try {
    const parsed = JSON.parse(text);
    return parsed.d ?? parsed;
  } catch {
    return text;
  }
}

async function fillPage(env: Env, parcel: string, resultType: PageType) {
  return postAsmx(env.SKAGIT_PROPERTY_SERVICE, "fillPage", {
    sValue: parcel,
    ResultType: resultType,
  });
}

async function taxDetail(env: Env, parcel: string, year: string) {
  return postAsmx(env.SKAGIT_PROPERTY_SERVICE, "getTaxHistoryDetail", {
    sValue: parcel,
    sYear: year,
  });
}

function addCookies(cookieHeader: string, response: Response) {
  const setCookie = response.headers.get("set-cookie");
  if (!setCookie) return cookieHeader;
  const current = new Map(cookieHeader.split(";").map((part) => part.trim()).filter(Boolean).map((part) => {
    const idx = part.indexOf("=");
    return [part.slice(0, idx), part.slice(idx + 1)] as const;
  }));
  for (const raw of setCookie.split(/,(?=\s*[^;,=\s]+(?:=|$))/)) {
    const first = raw.split(";")[0]?.trim();
    const idx = first?.indexOf("=") ?? -1;
    if (first && idx > 0) current.set(first.slice(0, idx), first.slice(idx + 1));
  }
  return [...current.entries()].map(([key, value]) => `${key}=${value}`).join("; ");
}

async function fetchTextWithCookies(url: string, init: RequestInit = {}, cookieHeader = "") {
  const headers = new Headers(init.headers);
  headers.set("accept", headers.get("accept") || "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");
  headers.set("user-agent", headers.get("user-agent") || "OpenSkagit research tool");
  if (cookieHeader) headers.set("cookie", cookieHeader);
  const res = await fetch(url, { ...init, headers });
  const nextCookie = addCookies(cookieHeader, res);
  return { res, text: await res.text(), cookie: nextCookie };
}

function selectedResultsUrl(html: string, base: string) {
  const match = html.match(/(?:href|action)=["']([^"']*SelectedResults\.aspx\?wc=[^"']+)["']/i)
    || html.match(/window\.open\(["']([^"']*SelectedResults\.aspx\?wc=[^"']+)["']/i)
    || html.match(/(SelectedResults\.aspx\?wc=[^"'\s<>]+)/i);
  if (!match) return null;
  const path = match[1].startsWith("SelectedResults.aspx") ? match[1] : match[1];
  return new URL(htmlDecode(path), `${base}/`).toString();
}

async function propertyComps(env: Env, parcel: string) {
  const base = env.SKAGIT_PROPERTY_SALES_BASE || "https://www.skagitcounty.net/Search/PropertySales";
  try {
    const startUrl = `${base}?id=${encodeURIComponent(parcel)}`;
    const first = await fetchTextWithCookies(startUrl);
    if (!first.res.ok) return { status: "error", error: `PropertySales page failed: ${first.res.status}` };

    const form = formValues(first.text);
    form.set("ctl00$content$txtParcelNumber", parcel);
    form.set("ctl00$content$butGetSales", "FIND Sales");

    const posted = await fetchTextWithCookies(startUrl, {
      method: "POST",
      redirect: "manual",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "referer": startUrl,
      },
      body: form,
    }, first.cookie);

    const location = posted.res.headers.get("location");
    const resultsUrl = location ? new URL(location, startUrl).toString() : `${base}/Results.aspx`;
    const results = await fetchTextWithCookies(resultsUrl, { headers: { "referer": startUrl } }, posted.cookie);
    const searchResults = parseComparableSearchResults(results.text);

    const selectedUrl = selectedResultsUrl(results.text, base);
    if (!selectedUrl) {
      return {
        status: searchResults.status === "ok" ? "ok" : "no_selected_results",
        search_url: startUrl,
        results_url: resultsUrl,
        criteria: {
          neighborhood: form.get("ctl00$content$cboNeighborhood"),
          present_use: form.get("ctl00$content$cboPresentUse"),
          sale_type: form.get("ctl00$content$cboSaleType"),
          region: form.get("ctl00$content$region"),
        },
        search_results: searchResults,
        results_text: stripTags(results.text).slice(0, 4000),
      };
    }

    const selected = await fetchTextWithCookies(selectedUrl, { headers: { "referer": resultsUrl } }, results.cookie);
    const parsed = parseComparableSales(selected.text);
    return {
      ...parsed,
      search_url: startUrl,
      results_url: resultsUrl,
      selected_results_url: selectedUrl,
      search_results: searchResults,
      criteria: {
        neighborhood: form.get("ctl00$content$cboNeighborhood"),
        present_use: form.get("ctl00$content$cboPresentUse"),
        sale_type: form.get("ctl00$content$cboSaleType"),
        region: form.get("ctl00$content$region"),
        price_from: form.get("ctl00$content$txtPriceFrom"),
        price_to: form.get("ctl00$content$txtPriceTo"),
        living_area_from: form.get("ctl00$content$txtLivingAreaFrom"),
        living_area_to: form.get("ctl00$content$txtLivingAreaTo"),
        year_built_from: form.get("ctl00$content$txtYearBuiltFrom"),
        year_built_to: form.get("ctl00$content$txtYearBuiltTo"),
      },
    };
  } catch (err) {
    return { status: "error", error: err instanceof Error ? err.message : String(err) };
  }
}

async function propertyDossier(env: Env, parcel: string, includeRaw = false) {
  const [pages, comps, census, soils] = await Promise.all([
    Promise.all(PAGE_TYPES.map(async (type) => [type.toLowerCase(), await fillPage(env, parcel, type)] as const)),
    propertyComps(env, parcel),
    parcelCensus(parcel).catch((err) => ({ status: "error", error: err instanceof Error ? err.message : String(err) })),
    parcelSoils(parcel).catch((err) => ({ status: "error", source: "NRCS Soil Data Access SSURGO", error: err instanceof Error ? err.message : String(err) })),
  ]);
  const raw = Object.fromEntries(pages);
  const taxYears = parseTaxYears(raw.taxes).filter((item) => !item.current);
  const taxDetailEntries = await Promise.all(
    taxYears.map(async ({ year }) => [String(year), await taxDetail(env, parcel, String(year))] as const)
  );
  const taxDetails = Object.fromEntries(taxDetailEntries);
  const summary = parsePropertySummary(parcel, raw, taxDetails);
  const related_parcels = relatedParcels(parcel, summary.sales);
  const value_trends = valueTrends(summary);
  const summaryWithDerived = { ...summary, related_parcels, value_trends };
  const enrichedSummary = {
    ...summaryWithDerived,
    agent_flags: agentFlags(summaryWithDerived, comps, census, related_parcels, value_trends),
    comps,
    census,
    soils,
  };
  return includeRaw ? { summary: enrichedSummary, raw: { ...raw, tax_details: taxDetails } } : { summary: enrichedSummary };
}

export default {
  async fetch(request: Request, env: Env) {
    if (request.method === "OPTIONS") return json({ ok: true });

    const url = new URL(request.url);

    try {
      if (url.pathname === "/openapi.json") {
        return json(openApiSchema(url.origin));
      }

      if (url.pathname === "/mcp") {
        return handleMcp(request, env);
      }

      if (url.pathname === "/api/search") {
        const q = cleanSearch(url.searchParams.get("q"));
        return json(await searchAddress(env, q));
      }

      if (url.pathname === "/api/gis/layers") {
        return json(layerList());
      }

      if (url.pathname === "/api/gis/metadata") {
        return json(await gisLayerMetadata(url.searchParams.get("layer")));
      }

      if (url.pathname === "/api/gis/query") {
        return json(await queryGisLayerFromUrl(url));
      }

      if (url.pathname === "/api/gis/parcel") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        return json({ parcel, gis: await getParcelGis(parcel, url.searchParams.get("geometry") !== "0") });
      }

      if (url.pathname === "/api/gis/parcel-overlays") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        return json(await parcelOverlays(parcel, parseLayerKeys(url.searchParams.get("layers"), url.searchParams.get("bundles"))));
      }

      if (url.pathname === "/api/census") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        return json(withResponseMeta({ parcel, census: await parcelCensus(parcel) }));
      }

      if (url.pathname === "/api/soils") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        return json(withResponseMeta({ parcel, soils: await parcelSoils(parcel) }));
      }

      if (url.pathname === "/api/context") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        const [property, gis] = await Promise.all([
          propertyDossier(env, parcel, url.searchParams.get("raw") === "1"),
          parcelOverlays(parcel, parseLayerKeys(url.searchParams.get("layers"), url.searchParams.get("bundles"))),
        ]);
        return json(withResponseMeta({ parcel, property, gis }));
      }

      if (url.pathname === "/api/property") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        return json(withResponseMeta({
          parcel,
          ...(await propertyDossier(env, parcel, url.searchParams.get("raw") === "1")),
        }));
      }

      if (url.pathname === "/api/page") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        const type = url.searchParams.get("type") as PageType;
        if (!PAGE_TYPES.includes(type)) throw new Error(`type must be one of: ${PAGE_TYPES.join(", ")}`);
        return json({ parcel, type, data: await fillPage(env, parcel, type) });
      }

      if (url.pathname === "/api/tax-detail") {
        const parcel = cleanParcel(url.searchParams.get("parcel"));
        const year = url.searchParams.get("year") || new Date().getFullYear().toString();
        if (!/^20\d{2}$/.test(year)) throw new Error("Use a year like 2025");
        return json({ parcel, year, data: await taxDetail(env, parcel, year) });
      }

      return env.ASSETS.fetch(request);
    } catch (err) {
      return json({ error: err instanceof Error ? err.message : String(err) }, 400);
    }
  },
};
