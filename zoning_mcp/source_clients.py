from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .seed_data import JURISDICTIONS, SOURCE_URLS


@dataclass(frozen=True)
class CodeMatch:
    chapter: str
    section: str
    text: str
    source_url: str


class CodePublishingClient:
    def __init__(self, timeout: float = 20):
        self.timeout = timeout
        self.headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 OpenSkagit/0.1",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
        }

    def fetch_text(self, url: str) -> str:
        response = requests.get(url, timeout=self.timeout, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))

    def discover_links(self, jurisdiction: str, limit: int = 40) -> list[tuple[str, str]]:
        config = JURISDICTIONS.get(jurisdiction)
        if not config:
            return []
        base_url = config["source_url"]
        response = requests.get(base_url, timeout=self.timeout, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        links: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"])
            label = anchor.get_text(" ", strip=True)
            lowered = f"{label} {href}".lower()
            if "zon" not in lowered and "development" not in lowered and "title" not in lowered:
                continue
            links.append((label or href, urljoin(base_url, href)))
            if len(links) >= limit:
                break
        return links

    def search(self, jurisdiction: str, query: str, limit: int = 8) -> list[CodeMatch]:
        terms = [term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) >= 3]
        if not terms:
            return []
        matches: list[CodeMatch] = []
        for title, url in self._candidate_urls(jurisdiction):
            try:
                text = self.fetch_text(url)
            except requests.RequestException:
                continue
            for snippet in self._snippets(text, terms):
                matches.append(CodeMatch(title, self._section_label(snippet), snippet, url))
                if len(matches) >= limit:
                    return matches
        return matches

    def _candidate_urls(self, jurisdiction: str) -> list[tuple[str, str]]:
        if jurisdiction == "skagit_county":
            return [("SCC 14.11", SOURCE_URLS["skagit_county_14_11"]), ("SCC 14.12", SOURCE_URLS["skagit_county_14_12"])]
        links = self.discover_links(jurisdiction)
        zoning_links = [(label, url) for label, url in links if "zon" in f"{label} {url}".lower()]
        return zoning_links[:6] or links[:6]

    def _snippets(self, text: str, terms: Iterable[str]) -> list[str]:
        chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
        scored: list[tuple[int, str]] = []
        for chunk in chunks:
            score = sum(1 for term in terms if term in chunk.lower())
            if score:
                scored.append((score, re.sub(r"\s+", " ", chunk)[:1200]))
        scored.sort(key=lambda item: (-item[0], len(item[1])))
        return [chunk for _, chunk in scored[:12]]

    def _section_label(self, text: str) -> str:
        match = re.search(r"\b\d{1,2}\.\d{2,3}\.\d{3}\b", text)
        return match.group(0) if match else ""
