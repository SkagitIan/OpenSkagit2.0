from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pypdf import PdfReader


DEFAULT_INPUT = Path(
    "data/Environmental Regulations - Land Use Decisions - Buildings and Construction - "
    "Land Divisions and Adjustments - Comprehensive Zoning Ordinance - Shoreline Master Program (1).pdf"
)
DEFAULT_OUTPUT = Path("output/pdf/burlington_code")
SOURCE_BASE = "https://ecode360.com/BU4372"


def clean_line(line: str) -> str:
    line = line.replace("\u00a0", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def is_noise(line: str) -> bool:
    if not line:
        return True
    if line in {"City of Burlington, WA", "BURLINGTON CODE", "COMPREHENSIVE ZONING ORDINANCE"}:
        return True
    if line.startswith("Downloaded from https://ecode360.com/BU4372"):
        return True
    return bool(re.match(r"^§\s+\d+[A-Z]?\.\d+\.\d+\s+(BURLINGTON CODE|COMPREHENSIVE ZONING ORDINANCE)\s+§", line))


def extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text(extraction_mode="layout") or ""
        lines = [clean_line(line) for line in text.splitlines()]
        pages.append({"page": index, "text": "\n".join(line for line in lines if not is_noise(line))})
    return pages


def section_heading(line: str) -> tuple[str, str] | None:
    match = re.match(r"^§\s+(\d+[A-Z]?\.\d+\.\d+)\.\s+(.+?)\s*$", line)
    if not match:
        return None
    heading = clean_line(match.group(2)).rstrip(".")
    return match.group(1), heading


def chapter_heading(line: str) -> str | None:
    match = re.match(r"^CHAPTER\s+(\d+[A-Z]?\.\d+)\s*$", line)
    return match.group(1) if match else None


def title_for_section(section: str) -> str:
    if section.startswith("14A."):
        return "Title 14A Land Use Decisions"
    title = section.split(".", 1)[0]
    return {
        "14": "Title 14 Environmental Regulations",
        "15": "Title 15 Buildings and Construction",
        "16": "Title 16 Land Divisions and Adjustments",
        "17": "Title 17 Comprehensive Zoning Ordinance",
        "18": "Title 18 Shoreline Master Program",
    }.get(title, "Burlington Municipal Code")


def section_url(section: str) -> str:
    return f"{SOURCE_BASE}/{section}"


def chapter_url(chapter: str) -> str:
    return f"{SOURCE_BASE}/{chapter}"


def organize(pdf_path: Path, out_dir: Path) -> dict[str, Any]:
    pages = extract_pages(pdf_path)
    sections_by_id: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    current_chapter = ""
    current_chapter_title = ""
    pending_chapter = ""

    def finish_current() -> None:
        nonlocal current
        if not current:
            return
        text = "\n".join(current.pop("_lines")).strip()
        current["text"] = text
        existing = sections_by_id.get(current["section"])
        if existing is None or len(text) > len(existing.get("text", "")):
            sections_by_id[current["section"]] = current
        current = None

    for page in pages:
        for raw_line in page["text"].splitlines():
            line = clean_line(raw_line)
            if not line:
                continue
            chapter = chapter_heading(line)
            if chapter:
                pending_chapter = chapter
                continue
            if pending_chapter and not line.startswith("§"):
                current_chapter = pending_chapter
                current_chapter_title = f"Chapter {pending_chapter} {line.title()}"
                pending_chapter = ""
                continue
            heading = section_heading(line)
            if heading:
                finish_current()
                section, label = heading
                chapter_ref = ".".join(section.split(".")[:2])
                if current_chapter != chapter_ref:
                    current_chapter = chapter_ref
                    current_chapter_title = f"Chapter {chapter_ref}"
                current = {
                    "jurisdiction": "burlington",
                    "title": title_for_section(section),
                    "chapter_ref": chapter_ref,
                    "chapter_title": current_chapter_title,
                    "section": section,
                    "heading": f"{section} {label}.",
                    "source_url": section_url(section),
                    "order": page["page"] * 1000,
                    "_lines": [],
                }
                continue
            if current:
                current["_lines"].append(line)
    finish_current()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "text").mkdir(parents=True, exist_ok=True)
    sections = sorted(sections_by_id.values(), key=lambda row: natural_section_key(row["section"]))
    with (out_dir / "sections.jsonl").open("w", encoding="utf-8") as handle:
        for index, section in enumerate(sections):
            section["order"] = index
            handle.write(json.dumps(section, ensure_ascii=False) + "\n")

    chapters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in sections:
        chapters[section["chapter_ref"]].append(section)
    pages_meta = []
    for chapter_ref, chapter_sections in sorted(chapters.items(), key=lambda item: natural_section_key(item[0] + ".000")):
        ref = f"{chapter_ref}.txt"
        text = "\n\n".join(f"{row['heading']}\n{row['text']}".strip() for row in chapter_sections)
        (out_dir / "text" / ref).write_text(text, encoding="utf-8")
        pages_meta.append(
            {
                "ref": ref,
                "url": chapter_url(chapter_ref),
                "status": 200,
                "mode": "pdf",
                "chapter": chapter_sections[0]["chapter_title"],
                "text_length": len(text),
            }
        )

    (out_dir / "tables.json").write_text("[]\n", encoding="utf-8")
    corpus = {
        "jurisdiction": "burlington",
        "jurisdiction_key": "burlington",
        "title": "Burlington Municipal Code zoning and land-use PDF",
        "source": SOURCE_BASE,
        "platform": "ecode360-pdf",
        "source_pdf": str(pdf_path),
        "page_count": len(pages_meta),
        "pages": pages_meta,
    }
    (out_dir / "corpus.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    manifest = {
        "input_pdf": str(pdf_path),
        "output_dir": str(out_dir),
        "sections": len(sections),
        "documents": len(pages_meta),
        "tables": 0,
        "sections_path": str(out_dir / "sections.jsonl"),
        "tables_path": str(out_dir / "tables.json"),
    }
    (out_dir / "organized_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def natural_section_key(section: str) -> tuple[Any, ...]:
    parts = re.split(r"([0-9]+)", section)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Organize Burlington eCode360 PDF into zoning corpus files.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(organize(args.input, args.out), indent=2))


if __name__ == "__main__":
    main()
