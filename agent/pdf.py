from datetime import datetime

from fpdf import FPDF

from agent.config import tenant


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "#1a5276").lstrip("#")
    if len(value) != 6:
        return (26, 82, 118)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (26, 82, 118)


class CaseFilePDF(FPDF):
    def header(self):
        t = tenant()
        r, g, b = _hex_to_rgb(t.get("branding", {}).get("primary_color", "#1a5276"))
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(r, g, b)
        self.cell(0, 10, t.get("display_name", "Civic Intelligence"), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "Civic Intelligence Case File", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        self.cell(0, 10, f"Page {self.page_no()} - Generated {generated}", align="C")


def build_pdf(case_file: dict) -> bytes:
    pdf = CaseFilePDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, f"Entity: {case_file.get('entity', 'Unknown')}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Question: {case_file.get('question', '')}", new_x="LMARGIN", new_y="NEXT")

    confidence = str(case_file.get("confidence", "unknown")).upper()
    color_map = {"HIGH": (39, 174, 96), "MEDIUM": (156, 101, 0), "LOW": (179, 38, 30)}
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*color_map.get(confidence, (100, 100, 100)))
    pdf.cell(0, 7, f"Confidence: {confidence}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    _section(pdf, "Answer")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, str(case_file.get("answer") or "No answer generated."), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    _section(pdf, "Evidence")
    evidence = case_file.get("evidence", [])
    if evidence:
        for item in evidence:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 7, item.get("source_name", item.get("source_id", "Unknown")), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            data = item.get("data", [])
            records = data if isinstance(data, list) else [data]
            for record in records[:3]:
                if isinstance(record, dict):
                    for key, value in list(record.items())[:8]:
                        pdf.multi_cell(0, 5, f"  {key}: {value}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, "No evidence returned.", new_x="LMARGIN", new_y="NEXT")

    missing = case_file.get("missing", [])
    if missing:
        _section(pdf, "Missing Evidence")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(179, 38, 30)
        for item in missing:
            pdf.multi_cell(0, 6, f"  - {item}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    _section(pdf, "Sources Queried")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    sources = case_file.get("sources_queried", [])
    if sources:
        for source_id in sources:
            pdf.cell(0, 5, f"  {source_id}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 5, "  None", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"Case file ID: {case_file.get('id', '')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Generated: {case_file.get('created_at', '')}", new_x="LMARGIN", new_y="NEXT")

    output = pdf.output(dest="S")
    return output if isinstance(output, bytes) else bytes(output)


def _section(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
