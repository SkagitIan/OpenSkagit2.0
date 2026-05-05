interface Env {
  ALLOWED_ORIGINS?: string;
}

interface WebRequest {
  source_id: string;
  endpoint: string;
  method: "GET" | "POST";
  query_type: "form_post" | "query_string" | "json_post";
  params: Record<string, string>;
  response_format: "html_table" | "asmx_html_table" | "json" | "xml";
  extract_fields?: string[];
  aggregate_mode?: "count_by_status";
  status_filter?: string;
  follow_pagination?: boolean;
  max_pages?: number;
}

interface WebResponse {
  success: boolean;
  records: Record<string, unknown>[];
  count: number;
  source_url: string;
  source_urls?: string[];
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

    const firstUrl = target.toString();
    const response = await fetchWithTimeout(firstUrl, init, 15000);
    const raw = await response.text();
    const raw_excerpt = raw.slice(0, 500);

    if (!response.ok) {
      return {
        success: false,
        records: [],
        count: 0,
        source_url: firstUrl,
        raw_excerpt,
        error: `HTTP ${response.status}`,
      };
    }

    const sourceUrls = [firstUrl];
    let records = parseRecords(raw, payload.response_format);
    if (payload.follow_pagination && payload.response_format === "html_table") {
      const maxPages = Math.max(1, Math.min(payload.max_pages ?? 50, 100));
      const seen = new Set(sourceUrls);
      let nextUrls = extractPaginationUrls(raw, firstUrl);
      while (nextUrls.length > 0 && sourceUrls.length < maxPages) {
        const next = nextUrls.find((url) => !seen.has(url));
        if (!next) break;
        seen.add(next);
        const pageResponse = await fetchWithTimeout(next, { method: "GET" }, 15000);
        const pageRaw = await pageResponse.text();
        sourceUrls.push(next);
        if (!pageResponse.ok) break;
        records = records.concat(parseRecords(pageRaw, payload.response_format));
        nextUrls = extractPaginationUrls(pageRaw, next);
      }
    }

    if (payload.aggregate_mode === "count_by_status") {
      const filtered = filterByStatus(records, payload.status_filter);
      const summary = {
        aggregate_mode: payload.aggregate_mode,
        status_filter: payload.status_filter || "",
        total_count: filtered.length,
        records_scanned: records.length,
        source_pages: sourceUrls.length,
      };
      return {
        success: true,
        records: [summary],
        count: filtered.length,
        source_url: firstUrl,
        source_urls: sourceUrls,
        raw_excerpt,
      };
    }

    return {
      success: true,
      records,
      count: records.length,
      source_url: firstUrl,
      source_urls: sourceUrls,
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
  if (format === "asmx_html_table") {
    // Skagit County ASP.NET web services return {"d": "<HTML fragment>"}.
    // Unwrap the JSON envelope, then parse all HTML tables inside.
    try {
      const envelope = JSON.parse(raw);
      const html = typeof envelope?.d === "string" ? envelope.d : raw;
      return parseAllHtmlTables(html);
    } catch {
      return parseAllHtmlTables(raw);
    }
  }
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

/**
 * Parse all <table> blocks from an HTML fragment and merge their rows into a
 * single flat record list. Each table that has a header row produces typed
 * records; label/value two-column tables are collapsed into a single object.
 * Used for ASMX responses that embed multiple data sections in one HTML blob.
 */
export function parseAllHtmlTables(html: string): Record<string, unknown>[] {
  const tables = [...html.matchAll(/<table\b[\s\S]*?<\/table>/gi)].map((m) => m[0]);
  if (tables.length === 0) return [];

  const all: Record<string, unknown>[] = [];

  for (const table of tables) {
    const rows = [...table.matchAll(/<tr\b[\s\S]*?<\/tr>/gi)].map((m) => m[0]);
    if (rows.length === 0) continue;

    const headerCells = parseCells(rows[0]);
    const dataRows = rows.slice(1).filter((r) => parseCells(r).some((v) => v));

    // Two-column label/value tables (e.g. property summary sidebar) → single record
    if (headerCells.length === 0 || (headerCells.length === 2 && dataRows.length > 2)) {
      const record: Record<string, unknown> = {};
      for (const row of rows) {
        const cells = parseCells(row);
        if (cells.length === 2 && cells[0]) {
          record[cells[0]] = cells[1] ?? "";
        }
      }
      if (Object.keys(record).length > 0) all.push(record);
      continue;
    }

    // Standard header + data rows
    if (dataRows.length === 0) continue;
    const headers = headerCells.map((v, i) => v || `column_${i + 1}`);
    for (const row of dataRows) {
      const values = parseCells(row);
      const record: Record<string, unknown> = {};
      headers.forEach((h, i) => {
        record[h] = values[i] ?? "";
      });
      all.push(record);
    }
  }

  return all;
}

function parseCells(row: string): string[] {
  return [...row.matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/gi)].map((match) =>
    stripHtml(match[1]),
  );
}

function extractPaginationUrls(html: string, currentUrl: string): string[] {
  const urls: string[] = [];
  for (const match of html.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>/gi)) {
    const href = decodeHtml(match[1]);
    if (!/[?&]page=\d+/i.test(href)) continue;
    try {
      urls.push(new URL(href, currentUrl).toString());
    } catch {
      // Ignore malformed links from public web systems.
    }
  }
  return [...new Set(urls)].sort((left, right) => {
    return pageNumber(left) - pageNumber(right);
  });
}

function pageNumber(url: string): number {
  return Number(new URL(url).searchParams.get("page") || "1");
}

function filterByStatus(records: Record<string, unknown>[], statusFilter?: string): Record<string, unknown>[] {
  if (!statusFilter) return records;
  const normalizedFilter = statusFilter.toLowerCase();
  const statusKeys = ["status", "permit status", "main status"];
  const filtered = records.filter((record) => {
    const value = statusKeys
      .map((key) => recordValue(record, key))
      .find((candidate) => candidate);
    if (!value) return false;
    const normalizedValue = value.toLowerCase();
    if (normalizedFilter === "active") {
      return ["active", "open", "issued", "pending", "review"].some((term) =>
        normalizedValue.includes(term),
      );
    }
    return normalizedValue.includes(normalizedFilter);
  });
  return filtered.length > 0 ? filtered : records;
}

function recordValue(record: Record<string, unknown>, wantedKey: string): string {
  for (const [key, value] of Object.entries(record)) {
    if (key.toLowerCase() === wantedKey) return String(value ?? "").trim();
  }
  return "";
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

function decodeHtml(value: string): string {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'");
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
