from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from zoning_mcp.models import Jurisdiction, Zone, ZoningCodeDocument, ZoningCodeSection, ZoningSourceTable, ZoningUseRule
from zoning_mcp.seed_data import JURISDICTIONS, ZONE_NAMES
from zoning_mcp.services import normalize_use_key, normalize_zone_code


DEFAULT_CORPUS_DIR = Path("output/codepublishing/skagit_county_title14")


@dataclass(frozen=True)
class ParsedUseRule:
    source_table: str
    source_url: str
    chapter_ref: str
    use_category: str
    use_name: str
    normalized_use_key: str
    zone_code: str
    status: str
    notes: str = ""


class Command(BaseCommand):
    help = "Import scraped Code Publishing Title 14 sections/tables and expand allowed-use tables into ZoningUseRule rows."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=Path, default=DEFAULT_CORPUS_DIR)
        parser.add_argument("--jurisdiction", default="skagit_county")
        parser.add_argument("--clear", action="store_true", help="Clear imported sections/tables and generated use rules first.")
        parser.add_argument("--no-rules", action="store_true", help="Import sections/tables but skip allowed-use rule parsing.")

    def handle(self, *args, **options):
        input_dir: Path = options["input"]
        jurisdiction_key = options["jurisdiction"]
        sections_path = input_dir / "sections.jsonl"
        tables_path = input_dir / "tables.json"
        corpus_path = input_dir / "corpus.json"
        if not sections_path.exists() or not tables_path.exists():
            raise CommandError(f"Expected sections.jsonl and tables.json under {input_dir}. Run the collector/organizer first.")

        with transaction.atomic():
            jurisdiction = self._ensure_jurisdiction(jurisdiction_key)
            if options["clear"]:
                ZoningCodeSection.objects.filter(jurisdiction=jurisdiction).delete()
                ZoningSourceTable.objects.filter(jurisdiction=jurisdiction).delete()
                ZoningCodeDocument.objects.filter(jurisdiction=jurisdiction).delete()
                ZoningUseRule.objects.filter(jurisdiction=jurisdiction).delete()

            if options["clear"]:
                section_count = self._bulk_import_sections(jurisdiction, sections_path)
                table_records = self._bulk_import_tables(jurisdiction, tables_path)
                document_count = self._bulk_import_documents(jurisdiction, input_dir, corpus_path)
                rule_count = 0 if options["no_rules"] else self._bulk_import_allowed_use_rules(jurisdiction, table_records, sections_path)
            else:
                section_count = self._import_sections(jurisdiction, sections_path)
                table_records = self._import_tables(jurisdiction, tables_path)
                document_count = self._import_documents(jurisdiction, input_dir, corpus_path)
                rule_count = 0 if options["no_rules"] else self._bulk_import_allowed_use_rules(jurisdiction, table_records, sections_path)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {section_count} sections, {len(table_records)} tables, {document_count} documents, "
                f"and {rule_count} allowed-use rules for {jurisdiction.key}."
            )
        )

    def _ensure_jurisdiction(self, key: str) -> Jurisdiction:
        data = JURISDICTIONS.get(key, {})
        jurisdiction, _ = Jurisdiction.objects.update_or_create(
            key=key,
            defaults={
                "display_name": data.get("display_name", key.replace("_", " ").title()),
                "code_source": data.get("code_source", "Code Publishing"),
                "zoning_title": data.get("zoning_title", "Title 14 Unified Development Code"),
                "source_url": data.get("source_url", ""),
                "extraction_status": data.get("extraction_status", "Imported from Code Publishing scrape."),
            },
        )
        return jurisdiction

    def _import_sections(self, jurisdiction: Jurisdiction, sections_path: Path) -> int:
        count = 0
        with sections_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                ZoningCodeSection.objects.update_or_create(
                    jurisdiction=jurisdiction,
                    source_url=row["source_url"],
                    defaults={
                        "title": row.get("title", ""),
                        "chapter_ref": row.get("chapter_ref", ""),
                        "chapter_title": row.get("chapter_title", ""),
                        "section": row.get("section", ""),
                        "heading": row.get("heading", ""),
                        "text": row.get("text", ""),
                        "order": row.get("order", 0) or 0,
                    },
                )
                count += 1
        return count

    def _bulk_import_sections(self, jurisdiction: Jurisdiction, sections_path: Path) -> int:
        objects = []
        with sections_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                objects.append(
                    ZoningCodeSection(
                        jurisdiction=jurisdiction,
                        source_url=row["source_url"],
                        title=row.get("title", ""),
                        chapter_ref=row.get("chapter_ref", ""),
                        chapter_title=row.get("chapter_title", ""),
                        section=row.get("section", ""),
                        heading=row.get("heading", ""),
                        text=row.get("text", ""),
                        order=row.get("order", 0) or 0,
                    )
                )
        ZoningCodeSection.objects.bulk_create(objects, batch_size=500)
        return len(objects)

    def _import_tables(self, jurisdiction: Jurisdiction, tables_path: Path) -> list[dict[str, Any]]:
        rows = json.loads(tables_path.read_text(encoding="utf-8"))
        for row in rows:
            ZoningSourceTable.objects.update_or_create(
                jurisdiction=jurisdiction,
                chapter_ref=row.get("chapter_ref", ""),
                table_index=row.get("table_index", 0) or 0,
                defaults={
                    "title": row.get("title", ""),
                    "chapter_title": row.get("chapter_title", ""),
                    "caption": row.get("caption", ""),
                    "nearest_heading": row.get("nearest_heading", ""),
                    "source_url": self._table_source_url(row),
                    "rows": row.get("rows", []),
                },
            )
        return rows

    def _bulk_import_tables(self, jurisdiction: Jurisdiction, tables_path: Path) -> list[dict[str, Any]]:
        rows = json.loads(tables_path.read_text(encoding="utf-8"))
        objects = [
            ZoningSourceTable(
                jurisdiction=jurisdiction,
                chapter_ref=row.get("chapter_ref", ""),
                table_index=row.get("table_index", 0) or 0,
                title=row.get("title", ""),
                chapter_title=row.get("chapter_title", ""),
                caption=row.get("caption", ""),
                nearest_heading=row.get("nearest_heading", ""),
                source_url=self._table_source_url(row),
                rows=row.get("rows", []),
            )
            for row in rows
        ]
        ZoningSourceTable.objects.bulk_create(objects, batch_size=200)
        return rows

    def _import_documents(self, jurisdiction: Jurisdiction, input_dir: Path, corpus_path: Path) -> int:
        count = 0
        pages = []
        if corpus_path.exists():
            pages = json.loads(corpus_path.read_text(encoding="utf-8")).get("pages", [])
        for page in pages:
            ref = page.get("ref")
            text_path = input_dir / "text" / str(ref).replace(".html", ".txt")
            if not ref or not text_path.exists():
                continue
            ZoningCodeDocument.objects.update_or_create(
                jurisdiction=jurisdiction,
                source_url=page.get("url", ""),
                defaults={
                    "title": page.get("chapter", ref),
                    "chapter": self._chapter_number(page.get("chapter", "")),
                    "text": text_path.read_text(encoding="utf-8"),
                },
            )
            count += 1
        return count

    def _bulk_import_documents(self, jurisdiction: Jurisdiction, input_dir: Path, corpus_path: Path) -> int:
        pages = []
        if corpus_path.exists():
            pages = json.loads(corpus_path.read_text(encoding="utf-8")).get("pages", [])
        objects = []
        for page in pages:
            ref = page.get("ref")
            text_path = input_dir / "text" / str(ref).replace(".html", ".txt")
            if not ref or not text_path.exists():
                continue
            objects.append(
                ZoningCodeDocument(
                    jurisdiction=jurisdiction,
                    source_url=page.get("url", ""),
                    title=page.get("chapter", ref),
                    chapter=self._chapter_number(page.get("chapter", "")),
                    text=text_path.read_text(encoding="utf-8"),
                )
            )
        ZoningCodeDocument.objects.bulk_create(objects, batch_size=100)
        return len(objects)

    def _import_allowed_use_rules(self, jurisdiction: Jurisdiction, tables: list[dict[str, Any]]) -> int:
        count = 0
        for table in tables:
            for parsed in self._parse_allowed_use_table(table):
                zone = self._ensure_zone(jurisdiction, parsed.zone_code)
                ZoningUseRule.objects.update_or_create(
                    jurisdiction=jurisdiction,
                    zone=zone,
                    normalized_use_key=parsed.normalized_use_key,
                    source_table=parsed.source_table,
                    defaults={
                        "use_category": self._truncate(parsed.use_category, 160),
                        "use_name": parsed.use_name,
                        "local_status": parsed.status,
                        "normalized_status": parsed.status,
                        "source_url": parsed.source_url,
                        "notes": parsed.notes,
                    },
                )
                count += 1
        return count

    def _bulk_import_allowed_use_rules(self, jurisdiction: Jurisdiction, tables: list[dict[str, Any]], sections_path: Path | None = None) -> int:
        parsed_rules = []
        zone_cache: dict[str, Zone] = {}
        for table in tables:
            parsed_rules.extend(self._parse_allowed_use_table(table))
            parsed_rules.extend(self._parse_mount_vernon_use_table(table) if jurisdiction.key == "mount_vernon" else [])
        if sections_path:
            parsed_rules.extend(self._parse_section_use_rules(jurisdiction, sections_path))
        parsed_rules = list(self._dedupe_rules(parsed_rules).values())
        for parsed in parsed_rules:
            if parsed.zone_code not in zone_cache:
                zone_cache[parsed.zone_code] = self._ensure_zone(jurisdiction, parsed.zone_code)
        objects = [
            ZoningUseRule(
                jurisdiction=jurisdiction,
                zone=zone_cache[parsed.zone_code],
                normalized_use_key=parsed.normalized_use_key,
                source_table=parsed.source_table,
                use_category=self._truncate(parsed.use_category, 160),
                use_name=parsed.use_name,
                local_status=parsed.status,
                normalized_status=parsed.status,
                source_url=parsed.source_url,
                notes=parsed.notes,
            )
            for parsed in parsed_rules
        ]
        ZoningUseRule.objects.bulk_create(objects, batch_size=1000)
        return len(objects)

    def _dedupe_rules(self, parsed_rules: list[ParsedUseRule]) -> dict[tuple[str, str, str], ParsedUseRule]:
        priority = {"P": 6, "AC": 5, "AD": 4, "CUP": 3, "C": 3, "HE": 2, "UNKNOWN": 1, "X": 0}
        deduped: dict[tuple[str, str, str], ParsedUseRule] = {}
        for rule in parsed_rules:
            key = (rule.zone_code, rule.normalized_use_key, rule.source_table)
            current = deduped.get(key)
            if current is None or priority.get(rule.status, 0) > priority.get(current.status, 0):
                deduped[key] = rule
        return deduped

    def _parse_allowed_use_table(self, table: dict[str, Any]) -> list[ParsedUseRule]:
        caption = table.get("caption", "")
        if "allowed" not in caption.lower() or "use" not in caption.lower():
            return []
        rows = table.get("rows") or []
        if not rows:
            return []
        header_index = self._header_index(rows)
        if header_index is None:
            return []
        headers = [normalize_zone_code(cell) for cell in rows[header_index][1:]]
        if not any(headers):
            return []

        category = ""
        parsed = []
        for row in rows[header_index + 1 :]:
            cells = [str(cell).strip() for cell in row]
            if not any(cells):
                continue
            if self._is_category_row(cells, len(headers) + 1):
                category = cells[0]
                continue
            use_name = self._truncate(cells[0], 240)
            if not use_name or self._looks_like_header(use_name):
                continue
            for index, zone_code in enumerate(headers):
                if not zone_code:
                    continue
                raw_status = cells[index + 1] if index + 1 < len(cells) else ""
                status, note = self._normalize_status(raw_status)
                parsed.append(
                    ParsedUseRule(
                        source_table=caption,
                        source_url=self._table_source_url(table),
                        chapter_ref=table.get("chapter_ref", ""),
                        use_category=self._truncate(category, 160),
                        use_name=use_name,
                        normalized_use_key=self._normalized_key(use_name),
                        zone_code=zone_code,
                        status=status,
                        notes=f"Generated from imported Code Publishing table. {note}".strip(),
                    )
                )
        return parsed

    def _parse_mount_vernon_use_table(self, table: dict[str, Any]) -> list[ParsedUseRule]:
        heading = table.get("nearest_heading", "")
        if "permitted uses" not in heading.lower() and "conditional uses" not in heading.lower():
            return []
        rows = table.get("rows") or []
        if not rows:
            return []
        header = rows[0]
        if len(header) < 3 or not any("subarea" in str(cell).lower() for cell in header):
            return []
        status = "CUP" if "conditional" in heading.lower() else "P"
        zones = [self._normalize_mount_vernon_zone_header(cell) for cell in header[2:]]
        parsed = []
        for row in rows[1:]:
            if len(row) < 3:
                continue
            use_name = self._truncate(str(row[1]).strip(), 240)
            if not use_name:
                continue
            for index, zone_code in enumerate(zones):
                if not zone_code:
                    continue
                cell = str(row[index + 2]).strip() if index + 2 < len(row) else ""
                if not cell or cell.lower().startswith("no"):
                    parsed_status = "X"
                elif cell.lower().startswith("yes") or "permitted" in cell.lower():
                    parsed_status = status
                else:
                    parsed_status = "UNKNOWN"
                parsed.append(
                    ParsedUseRule(
                        source_table=table.get("caption") or heading,
                        source_url=self._table_source_url(table),
                        chapter_ref=table.get("chapter_ref", ""),
                        use_category="",
                        use_name=use_name,
                        normalized_use_key=self._normalized_key(use_name),
                        zone_code=zone_code,
                        status=parsed_status,
                        notes="Generated from imported Mount Vernon use table.",
                    )
                )
        return parsed

    def _parse_section_use_rules(self, jurisdiction: Jurisdiction, sections_path: Path) -> list[ParsedUseRule]:
        if jurisdiction.key != "mount_vernon":
            return []
        parsed = []
        with sections_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                heading = row.get("heading", "")
                lower_heading = heading.lower()
                if "permitted uses" not in lower_heading and "conditional uses" not in lower_heading:
                    continue
                zone_code = self._zone_from_chapter_title(row.get("chapter_title", ""))
                if not zone_code:
                    continue
                status = "CUP" if "conditional" in lower_heading else "P"
                for category, use_name in self._uses_from_section_text(row.get("text", "")):
                    parsed.append(
                        ParsedUseRule(
                            source_table=heading,
                            source_url=row.get("source_url", ""),
                            chapter_ref=row.get("chapter_ref", ""),
                            use_category=self._truncate(category, 160),
                    use_name=self._truncate(use_name, 240),
                    normalized_use_key=self._normalized_key(use_name),
                            zone_code=zone_code,
                            status=status,
                            notes="Generated from imported Mount Vernon use section.",
                        )
                    )
        return parsed

    def _ensure_zone(self, jurisdiction: Jurisdiction, zone_code: str) -> Zone:
        zone_name = ZONE_NAMES.get(jurisdiction.key, {}).get(zone_code, "")
        zone, _ = Zone.objects.update_or_create(
            jurisdiction=jurisdiction,
            zone_code=zone_code,
            defaults={"zone_name": zone_name},
        )
        return zone

    def _header_index(self, rows: list[list[str]]) -> int | None:
        for index, row in enumerate(rows[:5]):
            normalized = [normalize_zone_code(cell) for cell in row]
            zone_like = sum(1 for cell in normalized[1:] if cell and len(cell) <= 20)
            if len(row) >= 3 and zone_like >= 2:
                return index
        return None

    def _is_category_row(self, cells: list[str], expected_width: int) -> bool:
        return bool(cells[0]) and "use" in cells[0].lower() and all(not cell for cell in cells[1:expected_width])

    def _looks_like_header(self, value: str) -> bool:
        lowered = value.lower()
        return lowered in {"use", "uses", "zone", "zones"} or lowered.startswith("table ")

    def _normalize_status(self, value: str) -> tuple[str, str]:
        raw = value.strip()
        if not raw:
            return "X", "Blank source cell; treated as not listed as allowed."
        token = re.sub(r"[^A-Za-z]+", "", raw).upper()
        aliases = {
            "P": "P",
            "AC": "AC",
            "AD": "AD",
            "HE": "HE",
            "C": "C",
            "CU": "CUP",
            "CUP": "CUP",
            "X": "X",
        }
        status = aliases.get(token, "UNKNOWN")
        note = "" if status != "UNKNOWN" else f"Unparsed source status: {raw}."
        return status, note

    def _normalize_mount_vernon_zone_header(self, value: str) -> str:
        text = re.sub(r"(?i)^subarea\s+", "", str(value).strip())
        return normalize_zone_code(text)

    def _zone_from_chapter_title(self, title: str) -> str:
        after_chapter = re.sub(r"^Chapter\s+\d+\.\d+\s+", "", title, flags=re.IGNORECASE).strip()
        match = re.match(r"([A-Z]+(?:-[A-Z0-9]+)?(?:,\s*\d+(?:\.\d+)?)?)", after_chapter)
        if not match:
            return ""
        return normalize_zone_code(match.group(1))

    def _uses_from_section_text(self, text: str) -> list[tuple[str, str]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        items: list[tuple[str, str, str]] = []
        current_letter = ""
        for line in lines:
            match = re.match(r"^([A-Z])\.\s+(.+)$", line)
            if match:
                current_letter = self._clean_use_name(match.group(2))
                items.append(("letter", "", current_letter))
                continue
            match = re.match(r"^(\d+)\.\s+(.+)$", line)
            if match:
                items.append(("number", current_letter, self._clean_use_name(match.group(2))))
        if any(kind == "number" for kind, _, _ in items):
            uses = [(category, value) for kind, category, value in items if kind == "number" and self._looks_like_use(value)]
            if uses:
                return uses
        return [("", value) for kind, _, value in items if kind == "letter" and self._looks_like_use(value)]

    def _clean_use_name(self, value: str) -> str:
        value = re.split(r";| provided,| subject to| according to| which meet| involving", value, maxsplit=1, flags=re.IGNORECASE)[0]
        value = re.sub(r"\s+", " ", value).strip(" .")
        return value

    def _truncate(self, value: str, length: int) -> str:
        return value if len(value) <= length else value[: length - 1].rstrip() + "…"

    def _normalized_key(self, value: str) -> str:
        return self._truncate(normalize_use_key(value), 180)

    def _looks_like_use(self, value: str) -> bool:
        lowered = value.lower()
        if len(value) < 3 or lowered.startswith("repealed"):
            return False
        if lowered.startswith(("the ", "all ", "adequate ", "individual ", "there shall", "a recreational", "no ")):
            return False
        return True

    def _table_source_url(self, table: dict[str, Any]) -> str:
        url = table.get("source_url", "")
        heading = table.get("nearest_heading", "")
        match = re.search(r"\b(14\.\d{2}\.\d{3})\b", heading)
        return f"{url}#{match.group(1)}" if match and "#" not in url else url

    def _chapter_number(self, chapter: str) -> str:
        match = re.search(r"\b(14\.\d{2})\b", chapter)
        return match.group(1) if match else ""
