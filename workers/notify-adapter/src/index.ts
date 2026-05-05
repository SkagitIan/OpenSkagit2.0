import { buildEmailHtml, buildEmailText, type CaseFilePayload } from "./template";

interface Env {
  RESEND_API_KEY?: string;
}

interface NotifyRequest {
  channels: {
    email?: {
      to: string;
      subject: string;
      body_html?: string;
      body_text?: string;
      case_file?: CaseFilePayload;
    };
    webhook?: {
      url: string;
      payload: Record<string, unknown>;
    };
  };
}

interface NotifyResponse {
  success: boolean;
  results: {
    email?: { sent: boolean; error?: string };
    webhook?: { sent: boolean; status?: number; error?: string };
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (request.method === "OPTIONS") return jsonResponse({}, 204);
      if (request.method !== "POST" || url.pathname !== "/notify") {
        return jsonResponse({ success: false, error: "Not found" }, 404);
      }

      const payload = await parseJson(request);
      const response = await dispatchNotify(payload, env);
      return jsonResponse(response, 200);
    } catch (error) {
      return jsonResponse(
        { success: false, results: {}, error: error instanceof Error ? error.message : String(error) },
        200
      );
    }
  }
};

async function dispatchNotify(payload: unknown, env: Env): Promise<NotifyResponse> {
  const body = payload as Partial<NotifyRequest>;
  const channels = body.channels ?? {};
  const results: NotifyResponse["results"] = {};

  if (channels.email) {
    const email = channels.email;
    if (!env.RESEND_API_KEY) {
      console.warn("RESEND_API_KEY not configured");
      results.email = { sent: false, error: "API key not configured" };
    } else {
      const html = email.body_html ?? (email.case_file ? buildEmailHtml(email.case_file) : "");
      const text = email.body_text ?? (email.case_file ? buildEmailText(email.case_file) : "");
      results.email = await sendEmail(email.to, email.subject, html, text, env.RESEND_API_KEY);
    }
  }

  if (channels.webhook) {
    results.webhook = await sendWebhook(channels.webhook.url, channels.webhook.payload);
  }

  return {
    success: Object.values(results).every((result) => result.sent),
    results
  };
}

async function sendEmail(
  to: string,
  subject: string,
  html: string,
  text: string,
  apiKey: string
): Promise<{ sent: boolean; error?: string }> {
  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        from: "Civic Intelligence <notifications@yourdomain.com>",
        to: [to],
        subject,
        html,
        text
      })
    });
    if (!response.ok) {
      return { sent: false, error: await response.text() };
    }
    return { sent: true };
  } catch (error) {
    return { sent: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function sendWebhook(
  url: string,
  payload: Record<string, unknown>
): Promise<{ sent: boolean; status?: number; error?: string }> {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10000)
    });
    return { sent: response.ok, status: response.status };
  } catch (error) {
    return { sent: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function parseJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    }
  });
}
