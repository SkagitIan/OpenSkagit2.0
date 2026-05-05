interface Env {
  ALLOWED_ORIGINS?: string;
}

type QueryType = "by_attribute" | "by_geometry" | "by_parcel";

interface ArcGISRequest {
  base_url: string;
  layer_id: number;
  parcel_field?: string;
  in_sr?: number;
  server_type?: "MapServer" | "ImageServer";
  query_type: QueryType;
  params: {
    where?: string;
    geometry?: Record<string, unknown>;
    parcel_id?: string;
    out_fields?: string[];
    return_count?: number;
    return_geometry?: boolean;
  };
}

interface Feature {
  attributes: Record<string, unknown>;
  geometry?: Record<string, unknown>;
}

interface ArcGISResponse {
  success: boolean;
  features: Feature[];
  count: number;
  source_url: string;
  error?: string;
}

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cors = corsHeaders(request, env);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    if (new URL(request.url).pathname !== "/query" || request.method !== "POST") {
      return json({ success: false, features: [], count: 0, source_url: "", error: "Not found" }, cors);
    }
    try {
      const body = await request.json();
      const parsed = validate(body);
      if (typeof parsed === "string") {
        return json({ success: false, features: [], count: 0, source_url: "", error: parsed }, cors);
      }
      const sourceUrl = buildUrl(parsed);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort("ArcGIS timeout"), 10000);
      try {
        const response = await fetch(sourceUrl, {
          signal: controller.signal,
          headers: { "user-agent": "Mozilla/5.0 OpenSkagitPhase3" },
        });
        const data = await response.json() as any;
        if (data?.error) {
          return json(failure(sourceUrl, formatArcGisError(data.error)), cors);
        }
        const features = normalizeFeatures(parsed, data);
        return json({ success: true, features, count: features.length, source_url: sourceUrl.toString() }, cors);
      } catch (error) {
        return json(failure(sourceUrl, error instanceof Error ? error.message : String(error)), cors);
      } finally {
        clearTimeout(timer);
      }
    } catch (error) {
      return json({ success: false, features: [], count: 0, source_url: "", error: error instanceof Error ? error.message : String(error) }, cors);
    }
  },
};

function validate(value: any): ArcGISRequest | string {
  if (!value || typeof value !== "object") return "Request body must be an object";
  if (typeof value.base_url !== "string" || !value.base_url.startsWith("http")) return "base_url is required";
  if (!Number.isInteger(value.layer_id)) return "layer_id must be an integer";
  if (value.server_type && !["MapServer", "ImageServer"].includes(value.server_type)) return "server_type is invalid";
  if (!["by_attribute", "by_geometry", "by_parcel"].includes(value.query_type)) return "query_type is invalid";
  if (!value.params || typeof value.params !== "object") return "params is required";
  if (value.query_type === "by_attribute" && typeof value.params.where !== "string") return "where is required";
  if (value.query_type === "by_geometry" && typeof value.params.geometry !== "object") return "geometry is required";
  if (value.query_type === "by_parcel" && typeof value.params.parcel_id !== "string") return "parcel_id is required";
  return value as ArcGISRequest;
}

function buildUrl(req: ArcGISRequest): URL {
  const base = req.base_url.replace(/\/$/, "");
  if (req.server_type === "ImageServer") {
    return buildImageServerUrl(base, req);
  }
  const url = new URL(`${base}/${req.layer_id}/query`);
  const outFields = req.params.out_fields?.length ? req.params.out_fields.join(",") : "*";
  url.searchParams.set("f", "json");
  url.searchParams.set("outFields", outFields);
  url.searchParams.set("returnGeometry", req.params.return_geometry ? "true" : "false");
  url.searchParams.set("resultRecordCount", String(req.params.return_count ?? 10));
  if (req.query_type === "by_parcel") {
    const field = req.parcel_field || "PARCELID";
    url.searchParams.set("where", `${field} = '${sqlEscape(req.params.parcel_id || "")}'`);
  } else if (req.query_type === "by_attribute") {
    url.searchParams.set("where", req.params.where || "1=1");
  } else {
    url.searchParams.set("where", "1=1");
    url.searchParams.set("geometry", JSON.stringify(req.params.geometry));
    url.searchParams.set("spatialRel", "esriSpatialRelIntersects");
    url.searchParams.set("geometryType", "esriGeometryPolygon");
    url.searchParams.set("inSR", String(req.in_sr || 102748));
  }
  return url;
}

function buildImageServerUrl(base: string, req: ArcGISRequest): URL {
  const url = new URL(`${base}/identify`);
  url.searchParams.set("f", "json");
  url.searchParams.set("geometry", JSON.stringify(pointFromGeometry(req.params.geometry)));
  url.searchParams.set("geometryType", "esriGeometryPoint");
  url.searchParams.set("returnGeometry", "false");
  url.searchParams.set("returnCatalogItems", "false");
  url.searchParams.set("inSR", String(req.in_sr || 4326));
  return url;
}

function pointFromGeometry(geometry: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!geometry) return {};
  if (typeof geometry.x === "number" && typeof geometry.y === "number") return geometry;
  const rings = geometry.rings;
  if (Array.isArray(rings) && Array.isArray(rings[0]) && Array.isArray(rings[0][0])) {
    const points = rings[0] as number[][];
    const totals = points.reduce((acc, point) => ({ x: acc.x + point[0], y: acc.y + point[1] }), { x: 0, y: 0 });
    return { x: totals.x / points.length, y: totals.y / points.length };
  }
  return geometry;
}

function normalizeFeatures(req: ArcGISRequest, data: any): Feature[] {
  if (req.server_type === "ImageServer") {
    const value = data?.value ?? data?.properties?.value;
    return value === undefined ? [] : [{ attributes: { value } }];
  }
  return Array.isArray(data?.features) ? data.features : [];
}

function failure(url: URL, error: string): ArcGISResponse {
  return { success: false, features: [], count: 0, source_url: url.toString(), error };
}

function formatArcGisError(error: any): string {
  const message = error?.message || "ArcGIS error";
  const details = Array.isArray(error?.details) ? `: ${error.details.join("; ")}` : "";
  return `${message}${details}`;
}

function sqlEscape(value: string): string {
  return value.replaceAll("'", "''").toUpperCase();
}

function corsHeaders(request: Request, env: Env): HeadersInit {
  const origin = request.headers.get("origin") || "*";
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((item) => item.trim()).filter(Boolean);
  return {
    ...JSON_HEADERS,
    "access-control-allow-origin": allowed.includes(origin) ? origin : "*",
    "access-control-allow-methods": "POST,OPTIONS",
    "access-control-allow-headers": "content-type",
  };
}

function json(data: unknown, headers: HeadersInit): Response {
  return new Response(JSON.stringify(data), { status: 200, headers });
}
