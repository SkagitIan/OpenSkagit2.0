export interface CaseFilePayload {
  id: string;
  entity?: string;
  question: string;
  confidence: string;
  answer?: string;
  sources_queried?: string[];
  missing?: string[];
  created_at: string;
}

export function buildEmailHtml(caseFile: CaseFilePayload): string {
  const confidenceBadge = {
    high: "High",
    medium: "Medium",
    low: "Low"
  }[caseFile.confidence] ?? caseFile.confidence;

  return `
    <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="border-bottom: 1px solid #eee; padding-bottom: 8px;">
        Civic Intelligence Case File
      </h2>
      <p><strong>Entity:</strong> ${escapeHtml(caseFile.entity ?? "Unknown")}</p>
      <p><strong>Question:</strong> ${escapeHtml(caseFile.question)}</p>
      <p><strong>Confidence:</strong> ${escapeHtml(confidenceBadge)}</p>
      <hr style="border: none; border-top: 1px solid #eee;" />
      <h3>Answer</h3>
      <p>${escapeHtml(caseFile.answer ?? "No answer generated.")}</p>
      <h3>Sources Queried</h3>
      <ul>
        ${(caseFile.sources_queried ?? []).map((source) => `<li>${escapeHtml(source)}</li>`).join("")}
      </ul>
      ${caseFile.missing?.length ? `
        <h3>Missing Evidence</h3>
        <ul style="color: #888;">
          ${caseFile.missing.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      ` : ""}
      <hr style="border: none; border-top: 1px solid #eee;" />
      <p style="font-size: 12px; color: #999;">
        Case file ID: ${escapeHtml(caseFile.id)}<br/>
        Generated: ${escapeHtml(caseFile.created_at)}
      </p>
    </div>
  `;
}

export function buildEmailText(caseFile: CaseFilePayload): string {
  const lines = [
    "CIVIC INTELLIGENCE CASE FILE",
    "============================",
    `Entity: ${caseFile.entity ?? "Unknown"}`,
    `Question: ${caseFile.question}`,
    `Confidence: ${caseFile.confidence}`,
    "",
    "ANSWER",
    caseFile.answer ?? "No answer generated.",
    "",
    "SOURCES QUERIED",
    ...(caseFile.sources_queried ?? []).map((source) => `- ${source}`)
  ];
  if (caseFile.missing?.length) {
    lines.push("", "MISSING EVIDENCE");
    caseFile.missing.forEach((item) => lines.push(`- ${item}`));
  }
  lines.push("", `Case file ID: ${caseFile.id}`, `Generated: ${caseFile.created_at}`);
  return lines.join("\n");
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
