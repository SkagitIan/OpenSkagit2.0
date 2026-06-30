from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from organize_codepublishing_title14 import clean_text, element_text


DEFAULT_INPUT = Path("data/LaConner (1).html")
DEFAULT_OUTPUT = Path("output/codepublishing/la_conner_title15")
LA_CONNER_SOURCE = "https://www.codepublishing.com/WA/LaConner/#!/LaConner15/LaConner15.html"


def section_id_from_heading(heading) -> str:
    link = heading.find("a", id=True)
    if link:
        text = element_text(link)
        if re.match(r"^\d{1,2}\.\d{2,3}\.\d{3}(?:\.\d+)?$", text):
            return text
    match = re.match(r"^(\d{1,2}\.\d{2,3}\.\d{3}(?:\.\d+)?)\b", element_text(heading))
    return match.group(1) if match else ""


def nearest_title(heading) -> str:
    previous = heading.find_previous("h1", class_="Title")
    return element_text(previous) if previous else ""


def nearest_chapter(heading) -> str:
    previous = heading.find_previous("h2", class_="CH")
    return element_text(previous) if previous else ""


def source_url(section: str) -> str:
    return f"{LA_CONNER_SOURCE}#{section}"


def iter_section_records(soup: BeautifulSoup) -> list[dict[str, Any]]:
    records = []
    for index, heading in enumerate(soup.select("h3.Cite")):
        section = section_id_from_heading(heading)
        if not section:
            continue
        parts = []
        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) in {"h1", "h2"}:
                break
            if getattr(sibling, "name", None) == "h3" and "Cite" in sibling.get("class", []):
                break
            if getattr(sibling, "name", None) in {"script", "style"}:
                continue
            text = element_text(sibling) if getattr(sibling, "get_text", None) else clean_text(str(sibling))
            if text:
                parts.append(text)
        chapter_title = nearest_chapter(heading)
        records.append(
            {
                "jurisdiction": "la_conner",
                "title": nearest_title(heading) or "Title 15 Uniform Development Code",
                "chapter_ref": ".".join(section.split(".")[:2]),
                "chapter_title": chapter_title,
                "section": section,
                "heading": element_text(heading),
                "text": "\n".join(parts),
                "source_url": source_url(section),
                "order": index,
            }
        )
    return records


def iter_table_records(soup: BeautifulSoup) -> list[dict[str, Any]]:
    records = []
    for index, table in enumerate(soup.find_all("table")):
        rows = []
        for tr in table.find_all("tr"):
            cells = [element_text(cell) for cell in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        section_heading = table.find_previous("h3", class_="Cite")
        section = section_id_from_heading(section_heading) if section_heading else ""
        records.append(
            {
                "jurisdiction": "la_conner",
                "title": nearest_title(table) or "Title 15 Uniform Development Code",
                "chapter_ref": ".".join(section.split(".")[:2]) if section else "",
                "chapter_title": nearest_chapter(table),
                "table_index": index,
                "caption": element_text(table.find("caption")) if table.find("caption") else "",
                "nearest_heading": element_text(section_heading) if section_heading else "",
                "rows": rows,
                "source_url": source_url(section) if section else LA_CONNER_SOURCE,
            }
        )
    return records


def organize(input_path: Path, out_dir: Path) -> dict[str, Any]:
    html = input_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    sections = iter_section_records(soup)
    tables = iter_table_records(soup)

    html_dir = out_dir / "html"
    text_dir = out_dir / "text"
    html_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, html_dir / "LaConner15.html")

    with (out_dir / "sections.jsonl").open("w", encoding="utf-8") as handle:
        for row in sections:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out_dir / "tables.json").write_text(json.dumps(tables, indent=2, ensure_ascii=False), encoding="utf-8")

    chapters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sections:
        chapters[row["chapter_ref"]].append(row)
    pages = []
    for chapter_ref, chapter_sections in sorted(chapters.items()):
        ref = f"{chapter_ref}.txt"
        text = "\n\n".join(f"{row['heading']}\n{row['text']}".strip() for row in chapter_sections)
        (text_dir / ref).write_text(text, encoding="utf-8")
        pages.append(
            {
                "ref": ref,
                "url": f"{LA_CONNER_SOURCE}#{chapter_ref}",
                "status": 200,
                "mode": "local-html-export",
                "chapter": chapter_sections[0]["chapter_title"] or chapter_ref,
                "text_length": len(text),
            }
        )

    corpus = {
        "jurisdiction": "la_conner",
        "jurisdiction_key": "la_conner",
        "title": "Title 15 Uniform Development Code",
        "source": LA_CONNER_SOURCE,
        "platform": "codepublishing-local-export",
        "source_html": str(input_path),
        "page_count": len(pages),
        "pages": pages,
    }
    (out_dir / "corpus.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    manifest = {
        "input_html": str(input_path),
        "output_dir": str(out_dir),
        "sections": len(sections),
        "documents": len(pages),
        "tables": len(tables),
        "sections_path": str(out_dir / "sections.jsonl"),
        "tables_path": str(out_dir / "tables.json"),
    }
    (out_dir / "organized_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Organize a local single-file Code Publishing HTML export.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(organize(args.input, args.out), indent=2))


if __name__ == "__main__":
    main()
