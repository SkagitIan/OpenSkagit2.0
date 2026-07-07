from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from .report import build_tax_report_context

WIDTH = 1200
HEIGHT = 630
BG = "#eef6f7"
INK = "#07192f"
MUTED = "#52677f"
TEAL = "#13aebc"
TEAL_DARK = "#0d7e89"
GREEN = "#4eb72f"
RED = "#c5251f"
CARD = "#ffffff"
LINE = "#d2e5ea"


def _font(size, bold=False):
    candidates = []
    if bold:
        candidates.extend([
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ])
    candidates.extend([
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ])
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


FONT_BRAND = _font(34, True)
FONT_KICKER = _font(23, True)
FONT_H1 = _font(48, True)
FONT_ADDRESS = _font(43, True)
FONT_H2 = _font(40, True)
FONT_BODY = _font(27)
FONT_BODY_BOLD = _font(27, True)
FONT_SMALL = _font(22)
FONT_MONO = _font(28, True)


def _text_size(draw, text, font):
    box = draw.textbbox((0, 0), str(text), font=font)
    return box[2] - box[0], box[3] - box[1]


def _fit_text(draw, text, font, max_width):
    text = str(text or "").strip()
    if not text:
        return ""
    if _text_size(draw, text, font)[0] <= max_width:
        return text
    ellipsis = "..."
    while text and _text_size(draw, text + ellipsis, font)[0] > max_width:
        text = text[:-1].rstrip()
    return text + ellipsis if text else ellipsis


def _wrap_text(draw, text, font, max_width, max_lines=2):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = _fit_text(draw, lines[-1], font, max_width)
    return lines


def _format_address(parcel):
    street = " ".join(str(parcel.get(key) or "").strip() for key in ("situs_street_number", "situs_street_name")).strip()
    city = str(parcel.get("situs_city_state_zip") or "").strip()
    return ", ".join(part for part in [street, city] if part) or "Skagit County, WA"


def _driver_rows(context):
    rows = []
    tax_shock = context.get("tax_shock") or {}
    if tax_shock.get("top_line_name") and tax_shock.get("top_line_effect_fmt"):
        rows.append((tax_shock["top_line_name"], tax_shock["top_line_effect_fmt"]))
    if tax_shock.get("value_effect_fmt"):
        rows.append(("Property value", tax_shock["value_effect_fmt"]))
    if tax_shock.get("voter_effect_fmt"):
        rows.append(("Voter-approved levies", tax_shock["voter_effect_fmt"]))
    if tax_shock.get("other_effect_fmt"):
        rows.append(("Regular levy rates", tax_shock["other_effect_fmt"]))

    seen = {name for name, _value in rows}
    for group in context.get("grouped") or []:
        name = str(group.get("label") or group.get("name") or "Taxing district").title()
        if name in seen:
            continue
        rows.append((name, group.get("total_fmt") or ""))
        seen.add(name)
        if len(rows) >= 3:
            break
    return rows[:3]


def _draw_logo(draw):
    draw.rounded_rectangle((70, 58, 116, 104), radius=12, fill=TEAL)
    draw.polygon([(80, 83), (93, 70), (106, 83)], outline="white", fill=None)
    draw.line((86, 82, 86, 96, 101, 96, 101, 82), fill="white", width=4)
    draw.text((132, 64), "TaxShift.co", font=FONT_BRAND, fill=INK)


def render_parcel_og_image(parcel_id):
    context = build_tax_report_context(parcel_id)
    parcel = context.get("parcel")
    if not parcel:
        return render_error_og_image(parcel_id)

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((40, 36, 1160, 594), radius=28, fill=CARD, outline=LINE, width=2)
    draw.rectangle((40, 36, 1160, 148), fill="#e8fbfd")
    draw.rounded_rectangle((40, 36, 1160, 594), radius=28, outline=LINE, width=2)
    _draw_logo(draw)

    parcel_number = str(parcel.get("parcel_number") or parcel_id).upper()
    address = _format_address(parcel)
    draw.rounded_rectangle((846, 66, 1096, 116), radius=16, fill="#f4fbfc", outline="#a7dbe3", width=2)
    draw.text((875, 78), f"Parcel {parcel_number}", font=FONT_MONO, fill=TEAL_DARK)

    y = 178
    for line in _wrap_text(draw, address.upper(), FONT_ADDRESS, 545, max_lines=3):
        draw.text((86, y), line, font=FONT_ADDRESS, fill=INK)
        y += 50

    latest = context.get("latest_change") or {}
    tax_year = latest.get("year_new") or parcel.get("tax_year") or "Current"
    delta = latest.get("delta_fmt") or context.get("total_fmt") or "$0"
    pct = latest.get("delta_pct_fmt") or ""
    change_color = GREEN if not latest or latest.get("delta_positive", True) else TEAL_DARK
    if latest.get("delta_positive"):
        change_color = RED

    draw.text((86, 356), f"{tax_year} Tax Shift", font=FONT_KICKER, fill=MUTED)
    draw.text((86, 394), delta, font=FONT_H2, fill=change_color)
    if pct:
        draw.text((250, 405), f"/ {pct}", font=FONT_BODY_BOLD, fill=change_color)

    reason = latest.get("main_reason_heading") or (context.get("tax_shock") or {}).get("driver_label") or "Property tax report"
    draw.rounded_rectangle((78, 486, 588, 542), radius=16, fill="#f6fbfb", outline=LINE, width=2)
    draw.text((104, 502), _fit_text(draw, "Main reason: " + reason, FONT_SMALL, 438), font=FONT_SMALL, fill=INK)

    draw.text((680, 192), "Main drivers", font=FONT_KICKER, fill=MUTED)
    driver_y = 242
    for name, value in _driver_rows(context):
        draw.rounded_rectangle((660, driver_y, 1088, driver_y + 74), radius=14, fill="#f8fbfc", outline=LINE, width=1)
        draw.text((684, driver_y + 20), _fit_text(draw, name, FONT_SMALL, 250), font=FONT_SMALL, fill=INK)
        value_color = RED if str(value).startswith("+") else TEAL_DARK
        value_text = _fit_text(draw, value, FONT_SMALL, 112)
        value_w, _ = _text_size(draw, value_text, FONT_SMALL)
        draw.text((1062 - value_w, driver_y + 20), value_text, font=FONT_SMALL, fill=value_color)
        driver_y += 88

    draw.line((86, 560, 1114, 560), fill=LINE, width=2)
    draw.text((86, 574), "Public assessor, levy, and tax-history data for Skagit County", font=FONT_SMALL, fill=MUTED)
    return _png_bytes(image)


def render_error_og_image(parcel_id):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((60, 70, 1140, 560), radius=28, fill=CARD, outline=LINE, width=2)
    _draw_logo(draw)
    draw.text((86, 220), "Parcel tax report", font=FONT_H1, fill=INK)
    draw.text((86, 298), f"Parcel {parcel_id}", font=FONT_H2, fill=TEAL_DARK)
    draw.text((86, 380), "TaxShift could not find this parcel.", font=FONT_BODY, fill=MUTED)
    return _png_bytes(image)


def render_home_og_image():
    image = Image.new("RGB", (WIDTH, HEIGHT), "#e9f7f8")
    draw = ImageDraw.Draw(image)
    _draw_logo(draw)

    draw.rounded_rectangle((680, 86, 1085, 500), radius=26, fill="#d9f1f4", outline="#b5dce2", width=2)
    for x, y, w, h in [(720, 140, 95, 60), (842, 126, 120, 74), (740, 236, 150, 88), (920, 252, 100, 70), (780, 378, 230, 74)]:
        draw.rounded_rectangle((x, y, x + w, y + h), radius=9, fill="#ffffff", outline="#9ed0d8", width=2)
    draw.line((700, 210, 1060, 210), fill="#94cfd8", width=5)
    draw.line((840, 108, 840, 480), fill="#94cfd8", width=5)
    draw.line((700, 356, 1060, 330), fill="#94cfd8", width=5)

    card_specs = [
        (650, 410, "P90623", "+$248", RED),
        (910, 92, "P123456", "-$84", TEAL_DARK),
        (952, 412, "P77401", "+$112", RED),
    ]
    for x, y, parcel, delta, color in card_specs:
        draw.rounded_rectangle((x, y, x + 170, y + 88), radius=16, fill="#ffffff", outline=LINE, width=2)
        draw.text((x + 18, y + 18), parcel, font=FONT_SMALL, fill=INK)
        draw.text((x + 18, y + 48), delta, font=FONT_BODY_BOLD, fill=color)

    headline = "Track how property taxes shift across Skagit County."
    y = 190
    for line in _wrap_text(draw, headline, FONT_H1, 520, max_lines=3):
        draw.text((78, y), line, font=FONT_H1, fill=INK)
        y += 64
    draw.text((82, y + 16), "Plain-English parcel tax snapshots from public data.", font=FONT_BODY, fill=MUTED)
    draw.rounded_rectangle((82, 500, 390, 556), radius=16, fill=TEAL)
    draw.text((112, 514), "taxshift.co", font=FONT_BODY_BOLD, fill="white")
    return _png_bytes(image)


def save_home_og_image(path=None):
    path = Path(path or settings.BASE_DIR / "static" / "images" / "og-home.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_home_og_image())
    return path


def _png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
