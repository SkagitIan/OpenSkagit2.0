interface Env {
  ALLOWED_ORIGINS?: string;
}

interface WebRequest {
  source_id: string;
  endpoint: string;
  method: "GET" | "POST";
  query_type: "form_post" | "query_string" | "json_post";
  params: Record<string, string>;
  response_format: "html_table" | "json" | "xml";
  extract_fields?: string[];
}

interface WebResponse {
  success: boolean;
  records: Record<string, unknown>[];
  count: number;
  source_url: string;
  raw_excerpt?: string;
  error?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cors = corsHeaders(request, env);
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    const url = new URL(request.url);
    if (url.pathname !== "/query") {
      return jsonResponse({ success: false, error: "Not found" }, cors);
    }

    try {
      const payload = (await request.json()) as WebRequest;
      const result = await handleQuery(payload);
      return jsonResponse(result, cors);
    } catch (error) {
      return jsonResponse(
        {
          success: false,
          records: [],
          count: 0,
          source_url: "",
          error: error instanceof Error ? error.message : String(error),
        },
        cors,
      );
    }
  },
};

async function handleQuery(payload: WebRequest): Promise<WebResponse> {
  try {
    const target = new URL(payload.endpoint);
    const init: RequestInit = { method: payload.method };

    if (payload.query_type === "query_string") {
      for (const [key, value] of Object.entries(payload.params || {})) {
        target.searchParams.set(key, value);
      }
      init.method = "GET";
    } else if (payload.query_type === "form_post") {
      init.method = "POST";
      init.headers = { "content-type": "application/x-www-form-urlencoded" };
      init.body = new URLSearchParams(payload.params || {}).toString();
    } else if (payload.query_type === "json_post") {
      init.method = "POST";
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(payload.params || {});
    }

    const response = await fetchWithTimeout(target.toString(), init, 15000);
    const raw = await response.text();
    const raw_excerpt = raw.slice(0, 500);

    if (!response.ok) {
      return {
        success: false,
        records: [],
        count: 0,
        source_url: target.toString(),
        raw_excerpt,
        error: `HTTP ${response.status}`,
      };
    }

    const records = parseRecords(raw, payload.response_format);
    return {
      success: true,
      records,
      count: records.length,
      source_url: target.toString(),
      raw_excerpt,
    };
  } catch (error) {
    return {
      success: false,
      records: [],
      count: 0,
      source_url: payload.endpoint,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function parseRecords(raw: string, format: WebRequest["response_format"]): Record<string, unknown>[] {
  if (format === "json") {
    const data = JSON.parse(raw);
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.records)) return data.records;
    if (Array.isArray(data.results)) return data.results;
    return [data];
  }
  if (format === "html_table") return parseHtmlTable(raw);
  return [];
}

export function parseHtmlTable(html: string): Record<string, unknown>[] {
  const table = html.match(/<table\b[\s\S]*?<\/table>/i)?.[0];
  if (!table) return [];

  const rows = [...table.matchAll(/<tr\b[\s\S]*?<\/tr>/gi)].map((match) => match[0]);
  if (rows.length < 2) return [];

  const headers = parseCells(rows[0]).map((value, index) => value || `column_${index + 1}`);
  return rows.slice(1).map((row) => {
    const values = parseCells(row);
    const record: Record<string, unknown> = {};
    headers.forEach((header, index) => {
      record[header] = values[index] ?? "";
    });
    return record;
  });
}

function parseCells(row: string): string[] {
  return [...row.matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/gi)].map((match) =>
    stripHtml(match[1]),
  );
}

function stripHtml(value: string): string {
  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function corsHeaders(request: Request, env: Env): HeadersInit {
  const origin = request.headers.get("origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((item) => item.trim());
  const allowOrigin = allowed.includes(origin) ? origin : "*";
  return {
    "access-control-allow-origin": allowOrigin,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type",
  };
}

function jsonResponse(data: unknown, headers: HeadersInit): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { ...headers, "content-type": "application/json" },
  });
}
