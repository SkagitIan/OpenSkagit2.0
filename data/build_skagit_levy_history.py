"""
Build Skagit levy history from WA DOR All County Levy Detail workbooks.

The DOR files use a statewide taxing district code (TDCODE). Skagit County
rows use county prefix 29. This script filters those rows, maps TDCODE values
to the local levy_short keys already used by OpenSkagit, and writes a joined
CSV suitable for loading into Postgres.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


DOR_TDCODE_TO_LEVY_SHORT = {
    "290000000": "STSCH",
    "290000200": "STSCH2",
    "290100000": "COUNTYCE",
    "290101180": "CONFUT",
    "290200100": "CORD",
    "290200200": "CORDDIV",
    "290300100": "TANAGEN",
    "290300200": "TBURGEN",
    "290300300": "TCONGEN",
    "290300400": "THAMGEN",
    "290300500": "TLACGEN",
    "290300600": "TLYMGEN",
    "290300700": "TMTVGEN",
    "290300800": "TSEDGEN",
    "290300850": "TSEDBOND",
    "290401110": "SD01101",
    "290401120": "SD01102",
    "290410010": "SD10001",
    "290410020": "SD10002",
    "290410030": "SD10020",
    "290410110": "SD10101",
    "290410120": "SD10102",
    "290410130": "SD10120",
    "290410310": "SD10301",
    "290410320": "SD10302",
    "290410330": "SD10320",
    "290431110": "SD31101",
    "290431130": "SD31120",
    "290431710": "SD31701",
    "290431720": "SD31702",
    "290431730": "SD31720",
    "290432010": "SD32001",
    "290432020": "SD32002",
    "290432030": "SD32020",
    "290433010": "SD33001",
    "290433020": "SD33002",
    "290433030": "SD33003",
    "290433040": "SD33020",
    "290500000": "LIBLAC",
    "290500200": "LIBDAR",
    "290500300": "LIBUSP",
    "290500400": "LIBCEN",
    "290600140": "H0121",
    "290600200": "H0227",
    "290600240": "H0224",
    "290630400": "H30408",
    "290700100": "F0101",
    "290700200": "F0201",
    "290700300": "F0301",
    "290700400": "F0401",
    "290700500": "F0501",
    "290700600": "F0601",
    "290700700": "F0701",
    "290700800": "F0801",
    "290700900": "F0901",
    "290700940": "F0920",
    "290701000": "F1001",
    "290701100": "F1101",
    "290701200": "F1201",
    "290701300": "F1301",
    "290701400": "F1401",
    "290701500": "F1501",
    "290701600": "F1601",
    "290701640": "F1620",
    "290701700": "F1701",
    "290701900": "F1901",
    "290702400": "F2401",
    "290900180": "P0108",
    "290900280": "P0201",
    "290900281": "P0209",
    "291200180": "COMD1",
    "291202480": "F24EMS",
    "291300100": "FIDPK",
    "291400100": "CEM1",
    "291400200": "CEM2",
    "291400300": "CEM3",
    "291400400": "CEM4",
    "291400500": "CEM5",
    "291400600": "CEM6",
    "291900290": "P0209",
    "292800100": "SCRFA 1019",
}


OUTPUT_COLUMNS = [
    "history_id",
    "tax_year",
    "taxing_district_code",
    "county_code",
    "district_name",
    "levy_short",
    "locally_assessed_value",
    "levy_rate",
    "district_levy",
    "highest_prior_levy",
    "new_construction_assessed_value",
    "prior_year_levy_rate",
    "prior_year_state_assessed_property",
    "two_years_prior_state_assessed_property",
    "two_years_prior_annexation_assessed_value",
    "two_years_prior_annex_tax_due",
    "two_years_prior_refund_tax_due",
    "maximum_allowable_levy_101_calc",
    "levy_name_canonical",
    "entity_key",
    "mcag",
    "reporting_status",
    "parent_mcag",
    "sao_legal_name",
    "review_needed",
    "agency_common_name",
    "agency_type",
    "source_file",
]


def _col_to_idx(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + ord(ch.upper()) - 64
    return idx - 1


def _read_sheet_rows(path: Path) -> list[list[str | None]]:
    with zipfile.ZipFile(path) as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", SPREADSHEET_NS):
                text = "".join(t.text or "" for t in si.findall(".//a:t", SPREADSHEET_NS))
                shared_strings.append(text)

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        first_sheet = workbook.find("a:sheets/a:sheet", SPREADSHEET_NS)
        if first_sheet is None:
            return []
        rel_id = first_sheet.attrib[f"{{{REL_NS}}}id"]
        target = rel_targets[rel_id]
        if not target.startswith("xl/"):
            target = f"xl/{target}"

        worksheet = ET.fromstring(zf.read(target))
        output_rows = []
        for row in worksheet.findall("a:sheetData/a:row", SPREADSHEET_NS):
            values: list[str | None] = []
            for cell in row.findall("a:c", SPREADSHEET_NS):
                idx = _col_to_idx(cell.attrib.get("r", "A1"))
                while len(values) < idx:
                    values.append(None)

                value = None
                v = cell.find("a:v", SPREADSHEET_NS)
                if v is not None:
                    if cell.attrib.get("t") == "s":
                        value = shared_strings[int(v.text or "0")]
                    else:
                        value = v.text
                else:
                    inline = cell.find("a:is", SPREADSHEET_NS)
                    if inline is not None:
                        value = "".join(t.text or "" for t in inline.findall(".//a:t", SPREADSHEET_NS))
                values.append(value)
            output_rows.append(values)
        return output_rows


def _year_from_filename(path: Path) -> int:
    match = re.search(r"(20\d{2})", path.name)
    if not match:
        raise ValueError(f"Could not infer tax year from {path}")
    return int(match.group(1))


def _get(row: list[str | None], idx: int) -> str | None:
    if idx >= len(row):
        return None
    value = row[idx]
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _load_crosswalk() -> dict[str, dict[str, str]]:
    # Keep this builder dependency-free by reading the existing static crosswalk
    # from skagit_tax_load.py instead of importing pandas/sqlalchemy.
    path = Path(__file__).with_name("skagit_tax_load.py")
    if not path.exists():
        return {}
    script = path.read_text(encoding="utf-8")
    module = ast.parse(script)
    assignment = next(
        (
            node
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "CROSSWALK_ROWS" for target in node.targets)
        ),
        None,
    )
    if assignment is None:
        return {}
    rows = ast.literal_eval(assignment.value)

    keys = [
        "levy_short",
        "levy_name_canonical",
        "entity_key",
        "mcag",
        "reporting_status",
        "parent_mcag",
        "sao_legal_name",
        "review_needed",
    ]
    crosswalk = {}
    for row in rows:
        item = dict(zip(keys, row))
        for nullable in ("mcag", "parent_mcag"):
            if item[nullable] is None:
                item[nullable] = ""
        item["review_needed"] = str(item["review_needed"]).lower()
        crosswalk[item["levy_short"]] = item
    return crosswalk


def _load_agencies() -> dict[str, dict[str, str]]:
    path = Path(__file__).with_name("skagit_agencies.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(workbook_dir: Path, county_prefix: str = "29") -> list[dict[str, str]]:
    crosswalk = _load_crosswalk()
    agencies = _load_agencies()
    rows: list[dict[str, str]] = []

    for workbook in sorted(workbook_dir.glob("All_County_Levy_Detail_*.xlsx")):
        tax_year = _year_from_filename(workbook)
        for source_row in _read_sheet_rows(workbook):
            tdcode = _get(source_row, 0)
            if not tdcode or not re.fullmatch(r"\d{9}", tdcode):
                continue
            if not tdcode.startswith(county_prefix):
                continue

            levy_short = DOR_TDCODE_TO_LEVY_SHORT.get(tdcode, "")
            crosswalk_row = crosswalk.get(levy_short, {})
            effective_mcag = crosswalk_row.get("mcag") or crosswalk_row.get("parent_mcag") or ""
            agency = agencies.get(str(effective_mcag), {}) if effective_mcag else {}

            row = {
                "history_id": f"{tax_year}:{tdcode}",
                "tax_year": str(tax_year),
                "taxing_district_code": tdcode,
                "county_code": tdcode[:2],
                "district_name": _get(source_row, 1) or "",
                "levy_short": levy_short,
                "locally_assessed_value": _get(source_row, 2) or "",
                "levy_rate": _get(source_row, 3) or "",
                "district_levy": _get(source_row, 4) or "",
                "highest_prior_levy": _get(source_row, 5) or "",
                "new_construction_assessed_value": _get(source_row, 6) or "",
                "prior_year_levy_rate": _get(source_row, 7) or "",
                "prior_year_state_assessed_property": _get(source_row, 8) or "",
                "two_years_prior_state_assessed_property": _get(source_row, 9) or "",
                "two_years_prior_annexation_assessed_value": _get(source_row, 10) or "",
                "two_years_prior_annex_tax_due": _get(source_row, 11) or "",
                "two_years_prior_refund_tax_due": _get(source_row, 12) or "",
                "maximum_allowable_levy_101_calc": _get(source_row, 13) or "",
                "levy_name_canonical": crosswalk_row.get("levy_name_canonical", ""),
                "entity_key": crosswalk_row.get("entity_key", ""),
                "mcag": crosswalk_row.get("mcag", ""),
                "reporting_status": crosswalk_row.get("reporting_status", ""),
                "parent_mcag": crosswalk_row.get("parent_mcag", ""),
                "sao_legal_name": crosswalk_row.get("sao_legal_name", ""),
                "review_needed": crosswalk_row.get("review_needed", ""),
                "agency_common_name": agency.get("common_name", ""),
                "agency_type": agency.get("type", ""),
                "source_file": workbook.name,
            }
            rows.append(row)
    return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Skagit levy history CSV")
    parser.add_argument("--workbook-dir", default=".", help="Directory containing All_County_Levy_Detail_*.xlsx")
    parser.add_argument("--output", default="skagit_levy_history.csv", help="Output CSV path")
    args = parser.parse_args()

    workbook_dir = Path(args.workbook_dir)
    rows = build_rows(workbook_dir)
    write_csv(rows, Path(args.output))

    years = sorted({row["tax_year"] for row in rows})
    unmatched = [row for row in rows if not row["levy_short"]]
    print(f"Wrote {len(rows):,} Skagit levy history rows to {args.output}")
    print(f"Years: {', '.join(years) if years else 'none'}")
    print(f"Unmatched TDCODE rows: {len(unmatched)}")
    for row in unmatched[:20]:
        print(f"  {row['tax_year']} {row['taxing_district_code']} {row['district_name']}")


if __name__ == "__main__":
    main()
