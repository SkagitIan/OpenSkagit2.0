from __future__ import annotations

import json
import sys
from pathlib import Path

from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import default_settings


INCLUDED_SUFFIXES = {
    ".env",
    ".example",
    ".html",
    ".in",
    ".json",
    ".lock",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SCAN_ROOTS = (
    Path(".env.example"),
    Path("compose.yaml"),
    Path("config"),
    Path("openskagit_tools"),
    Path("scripts"),
    Path(".github"),
)


def candidate_files() -> list[str]:
    candidates: list[str] = []
    for root in SCAN_ROOTS:
        paths = [root] if root.is_file() else root.rglob("*") if root.exists() else []
        for path in paths:
            if not path.is_file():
                continue
            if path.name == ".env.example" or path.suffix.lower() in INCLUDED_SUFFIXES:
                if path.stat().st_size <= 500_000:
                    candidates.append(str(path))
    return sorted(set(candidates))


def main() -> int:
    secrets = SecretsCollection()
    with default_settings():
        for filename in candidate_files():
            secrets.scan_file(filename)

    findings = secrets.json().get("results", {})
    if not findings:
        print("Secret scan passed: no unallowlisted high-confidence findings.")
        return 0

    sanitized = {
        filename: [
            {
                "line_number": item.get("line_number"),
                "type": item.get("type"),
            }
            for item in items
        ]
        for filename, items in findings.items()
    }
    print(json.dumps(sanitized, indent=2, sort_keys=True))
    print("Secret scan failed. Remove the secret or add an allowlist pragma only for a reviewed placeholder.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
