from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


DEFAULT_INPUT = Path("output/codepublishing/skagit_county_title14")


def clean_text(value: str) -> str:
    value = repair_mojibake(value)
    value = value.replace("Search Within This This section is included in your selections.", "")
    value = value.replace("Search Within This This chapter is included in your selections.", "")
    value = value.replace("Search Within This", "")
    value = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([,.;:])", r"\1", value)


def repair_mojibake(value: str) -> str:
    replacements = {
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "-",
        "â€”": "-",
        "â€¢": "*",
        "Â§": "§",
        "Â ": " ",
        "â‰¤": "<=",
        "â‰¥": ">=",
    }
    for bad, good in replacements.items():
        value = value.replace(bad, good)
    if "â" not in value and "Â" not in value:
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
    return repaired


def element_text(element) -> str:
    return clean_text(element.get_text(" ", strip=True))


def clean_heading(value: str) -> str:
    return clean_text(value.replace("Search Within This", "")).strip()


def chapter_title(soup: BeautifulSoup, fallback: str) -> str:
    heading = soup.select_one("h2.CH")
    if heading:
        return element_text(heading)
    chapter = soup.select_one("h1, .chunk-title, .breadcrumbs .active")
    if chapter:
        text = element_text(chapter)
        if text:
            return text
    page_title = soup.find("title")
    if page_title:
        text = element_text(page_title)
        if text:
            return text
    return fallback


def iter_section_records(ref: str, url: str, soup: BeautifulSoup, jurisdiction: str, title: str) -> list[dict[str, Any]]:
    main = soup.select_one("#mainContent") or soup.body or soup
    headings = main.select("h3.Cite[id]")
    if not headings:
        return iter_municipal_code_section_records(ref, url, soup, jurisdiction, title)
    records = []
    for index, heading in enumerate(headings):
        section_id = heading.get("id", "")
        if not re.match(r"^\d{1,2}\.\d{2}(\.\d{3})?$", section_id):
            continue
        parts = []
        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) == "h3" and "Cite" in sibling.get("class", []):
                break
            if getattr(sibling, "name", None) in {"script", "style"}:
                continue
            text = element_text(sibling) if getattr(sibling, "get_text", None) else clean_text(str(sibling))
            if text:
                parts.append(text)
        heading_text = element_text(heading)
        records.append(
            {
                "jurisdiction": jurisdiction,
                "title": title,
                "chapter_ref": ref,
                "chapter_title": chapter_title(soup, ref),
                "section": section_id,
                "heading": heading_text,
                "text": "\n\n".join(parts),
                "source_url": f"{url}#{section_id}",
                "order": index,
            }
        )
    return records


def iter_municipal_code_section_records(ref: str, url: str, soup: BeautifulSoup, jurisdiction: str, title: str) -> list[dict[str, Any]]:
    section_nodes = soup.select("article.type-Section[id][data-cite], section[id][data-cite]")
    records = []
    for index, node in enumerate(section_nodes):
        section_id = node.get("id", "")
        if not re.match(r"^\d{1,2}\.\d{2}\.\d{3}$", section_id):
            continue
        header = node.select_one(".inner-header, .header")
        heading = clean_heading(element_text(header)) if header else section_id
        section_text = element_text(node)
        if heading and section_text.startswith(heading):
            section_text = section_text[len(heading) :].strip()
        records.append(
            {
                "jurisdiction": jurisdiction,
                "title": title,
                "chapter_ref": ref,
                "chapter_title": chapter_title(soup, ref),
                "section": section_id,
                "heading": f"{section_id} {heading}".strip() if section_id not in heading else heading,
                "text": section_text,
                "source_url": municipal_section_url(url, section_id),
                "order": index,
            }
        )
    return records


def municipal_section_url(chapter_url: str, section_id: str) -> str:
    base = chapter_url.rsplit("/", 1)[0]
    return f"{base}/{section_id}"


def iter_table_records(ref: str, url: str, soup: BeautifulSoup, jurisdiction: str, title: str) -> list[dict[str, Any]]:
    records = []
    for index, table in enumerate(soup.find_all("table")):
        caption = table.find("caption")
        rows = []
        for tr in table.find_all("tr"):
            cells = [element_text(cell) for cell in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        nearest_heading = municipal_table_heading(table)
        previous = table.find_previous(["h2", "h3", "h4"])
        if previous:
            nearest_heading = nearest_heading or element_text(previous)
        source_url = url
        section = table.find_parent(["article", "section"], id=re.compile(r"^\d{1,2}\.\d{2}\.\d{3}$"))
        if section:
            source_url = municipal_section_url(url, section.get("id", ""))
        records.append(
            {
                "jurisdiction": jurisdiction,
                "title": title,
                "chapter_ref": ref,
                "chapter_title": chapter_title(soup, ref),
                "table_index": index,
                "caption": element_text(caption) if caption else "",
                "nearest_heading": nearest_heading or "",
                "rows": rows,
                "source_url": source_url,
            }
        )
    return records


def municipal_table_heading(table) -> str:
    section = table.find_parent(["article", "section"], id=re.compile(r"^\d{1,2}\.\d{2}\.\d{3}$"))
    if not section:
        return ""
    header = section.select_one(".inner-header, .header")
    return clean_heading(element_text(header)) if header else section.get("id", "")


def organize(input_dir: Path) -> dict[str, Any]:
    html_dir = input_dir / "html"
    corpus_path = input_dir / "corpus.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8")) if corpus_path.exists() else {}
    jurisdiction = corpus.get("jurisdiction_key") or corpus.get("jurisdiction") or "skagit_county"
    title = corpus.get("title") or "Title 14 Unified Development Code"
    page_urls = {page.get("ref"): page.get("url") for page in corpus.get("pages", []) if page.get("ref") and page.get("url")}
    sections_path = input_dir / "sections.jsonl"
    tables_path = input_dir / "tables.json"
    all_tables = []
    section_count = 0
    page_count = 0
    with sections_path.open("w", encoding="utf-8") as section_file:
        for html_path in sorted(html_dir.glob("*.html")):
            ref = html_path.name
            url = page_urls.get(ref) or f"https://www.codepublishing.com/WA/SkagitCounty/html/SkagitCounty14/{ref}"
            soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
            page_count += 1
            sections = iter_section_records(ref, url, soup, jurisdiction, title)
            for record in sections:
                section_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            section_count += len(sections)
            all_tables.extend(iter_table_records(ref, url, soup, jurisdiction, title))
    tables_path.write_text(json.dumps(all_tables, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "input_dir": str(input_dir),
        "jurisdiction": jurisdiction,
        "title": title,
        "pages": page_count,
        "sections": section_count,
        "tables": len(all_tables),
        "sections_path": str(sections_path),
        "tables_path": str(tables_path),
    }
    (input_dir / "organized_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Organize scraped Code Publishing Title 14 HTML into sections and tables.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    print(json.dumps(organize(args.input), indent=2))


if __name__ == "__main__":
    main()
