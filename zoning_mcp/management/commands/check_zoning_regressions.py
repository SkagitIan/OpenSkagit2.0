from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from zoning_mcp.models import Jurisdiction, Zone, ZoningCodeSection, ZoningUseRule
from zoning_mcp.services import (
    build_parcel_feasibility_report,
    lookup_use_status,
    normalize_jurisdiction,
    normalize_zone_code,
    resolve_parcel,
)


@dataclass(frozen=True)
class UseCase:
    jurisdiction: str
    zone: str
    proposed_use: str
    expected_status: str
    expected_match: str


USE_CASES = [
    UseCase("skagit_county", "RVC", "restaurant", "P", "Restaurant"),
    UseCase("skagit_county", "RVC", "office", "P", "office"),
    UseCase("skagit_county", "RC", "mini storage", "P", "Mini-storage"),
    UseCase("mount_vernon", "C-2", "restaurant", "P", "Eating and drinking"),
    UseCase("mount_vernon", "C-2", "office", "P", "Offices"),
    UseCase("mount_vernon", "C-2", "retail", "P", "Retail"),
    UseCase("sedro_woolley", "R-7", "duplex", "P", "duplex"),
    UseCase("sedro_woolley", "R-5", "single family", "P", "single-family"),
    UseCase("sedro_woolley", "UVMU", "restaurant", "P", "restaurants"),
    UseCase("concrete", "CL", "restaurant", "P", "Restaurants"),
    UseCase("concrete", "I", "restaurant", "C", "Restaurants"),
    UseCase("concrete", "R", "single family", "P", "Single-family"),
    UseCase("anacortes", "C", "restaurant", "P", "Restaurant/Bar"),
    UseCase("anacortes", "CBD", "restaurant", "P", "Restaurant/Bar"),
    UseCase("anacortes", "R2", "duplex", "P", "Duplex"),
    UseCase("anacortes", "R4", "multifamily", "P", "Multifamily"),
    UseCase("burlington", "MUC-1", "restaurant", "P", "Eating and drinking"),
    UseCase("burlington", "MUR-1", "multifamily", "P", "Multiunit"),
    UseCase("burlington", "CI-1", "contractor yard", "AC", "Outdoor storage"),
    UseCase("burlington", "RA-1", "duplex", "P", "Duplex"),
    UseCase("la_conner", "C", "restaurant", "P", "Food service"),
    UseCase("la_conner", "RD", "duplex", "P", "duplex"),
    UseCase("la_conner", "IND", "contractor yard", "P", "storage yards"),
    UseCase("la_conner", "PIND", "boat storage", "P", "boat storage"),
]


class Command(BaseCommand):
    help = "Run live zoning MCP regressions against imported code corpus and parcel zoning data."

    def add_arguments(self, parser):
        parser.add_argument("--parcel-samples", type=int, default=3, help="Parcel samples per jurisdiction with imported matching zone codes.")
        parser.add_argument("--json", action="store_true", help="Print machine-readable results.")

    def handle(self, *args, **options):
        results: dict[str, Any] = {"use_cases": [], "parcel_alignment": [], "feasibility_reports": []}
        failures: list[str] = []

        failures.extend(self._check_corpus_presence(results))
        failures.extend(self._check_use_cases(results))
        parcel_samples, parcel_failures = self._check_parcel_alignment(results, options["parcel_samples"])
        failures.extend(parcel_failures)
        failures.extend(self._check_feasibility_reports(results, parcel_samples))

        results["summary"] = {
            "use_cases": len(results["use_cases"]),
            "parcel_alignment_samples": len(results["parcel_alignment"]),
            "feasibility_reports": len(results["feasibility_reports"]),
            "failures": failures,
        }
        if options["json"]:
            self.stdout.write(json.dumps(results, indent=2, default=str))
        else:
            self.stdout.write(self.style.SUCCESS(f"Use-case checks: {len(results['use_cases'])}"))
            self.stdout.write(self.style.SUCCESS(f"Parcel alignment samples: {len(results['parcel_alignment'])}"))
            self.stdout.write(self.style.SUCCESS(f"Feasibility report checks: {len(results['feasibility_reports'])}"))
            if failures:
                for failure in failures:
                    self.stderr.write(self.style.ERROR(f"FAIL: {failure}"))
            else:
                self.stdout.write(self.style.SUCCESS("All zoning regressions passed."))
        if failures:
            raise CommandError(f"{len(failures)} zoning regression failure(s).")

    def _check_corpus_presence(self, results: dict[str, Any]) -> list[str]:
        failures = []
        expected = sorted({case.jurisdiction for case in USE_CASES})
        for key in expected:
            jurisdiction = Jurisdiction.objects.filter(key=key).first()
            section_count = ZoningCodeSection.objects.filter(jurisdiction=jurisdiction).count() if jurisdiction else 0
            rule_count = ZoningUseRule.objects.filter(jurisdiction=jurisdiction).count() if jurisdiction else 0
            results.setdefault("corpus", []).append({"jurisdiction": key, "sections": section_count, "rules": rule_count})
            if not jurisdiction:
                failures.append(f"{key}: jurisdiction row missing")
            if section_count <= 0:
                failures.append(f"{key}: no imported code sections")
            if rule_count <= 0:
                failures.append(f"{key}: no structured use rules")
        return failures

    def _check_use_cases(self, results: dict[str, Any]) -> list[str]:
        failures = []
        for case in USE_CASES:
            payload = lookup_use_status(case.jurisdiction, case.zone, case.proposed_use)
            ok = (
                payload.get("status") == case.expected_status
                and case.expected_match.lower() in payload.get("matched_use", "").lower()
                and bool(payload.get("source_url"))
            )
            results["use_cases"].append({"case": case.__dict__, "result": payload, "ok": ok})
            if not ok:
                failures.append(
                    f"{case.jurisdiction} {case.zone} {case.proposed_use}: expected {case.expected_status}/{case.expected_match}, "
                    f"got {payload.get('status')}/{payload.get('matched_use')}"
                )
        return failures

    def _check_parcel_alignment(self, results: dict[str, Any], samples_per_jurisdiction: int) -> tuple[list[dict[str, Any]], list[str]]:
        failures = []
        imported_zones = self._imported_zone_codes()
        selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT parcel_id, jurisdiction, zone_id, zone_name
                FROM parcel_primary_zoning
                WHERE parcel_id IS NOT NULL AND jurisdiction IS NOT NULL AND zone_id IS NOT NULL
                ORDER BY jurisdiction, zone_id, parcel_id
                """
            )
            columns = [column[0] for column in cursor.description]
            for raw in cursor.fetchall():
                row = dict(zip(columns, raw))
                jurisdiction = normalize_jurisdiction(row["jurisdiction"])
                zone_code = normalize_zone_code(row["zone_id"])
                if zone_code not in imported_zones.get(jurisdiction, set()):
                    continue
                if len(selected[jurisdiction]) >= samples_per_jurisdiction:
                    continue
                row["normalized_jurisdiction"] = jurisdiction
                row["normalized_zone"] = zone_code
                selected[jurisdiction].append(row)

        samples = [row for rows in selected.values() for row in rows]
        for row in samples:
            resolved = resolve_parcel(parcel_id=row["parcel_id"])
            ok = (
                resolved.get("found")
                and resolved.get("jurisdiction") == row["normalized_jurisdiction"]
                and resolved.get("zoning_code") == row["normalized_zone"]
            )
            result = {"sample": row, "resolved": resolved, "ok": ok}
            results["parcel_alignment"].append(result)
            if not ok:
                failures.append(
                    f"parcel {row['parcel_id']}: expected {row['normalized_jurisdiction']} {row['normalized_zone']}, "
                    f"got {resolved.get('jurisdiction')} {resolved.get('zoning_code')}"
                )
        missing = sorted(set(imported_zones) - set(selected))
        for jurisdiction in missing:
            results["parcel_alignment"].append({"jurisdiction": jurisdiction, "ok": True, "skipped": "No matching live parcel samples found."})
        return samples, failures

    def _check_feasibility_reports(self, results: dict[str, Any], parcel_samples: list[dict[str, Any]]) -> list[str]:
        failures = []
        by_jurisdiction: dict[str, dict[str, Any]] = {}
        for sample in parcel_samples:
            by_jurisdiction.setdefault(sample["normalized_jurisdiction"], sample)
        preferred_use = {
            "skagit_county": "restaurant",
            "mount_vernon": "restaurant",
            "sedro_woolley": "duplex",
            "concrete": "restaurant",
            "anacortes": "restaurant",
            "burlington": "restaurant",
            "la_conner": "restaurant",
        }
        for jurisdiction, sample in sorted(by_jurisdiction.items()):
            report = build_parcel_feasibility_report(sample["parcel_id"], preferred_use.get(jurisdiction, "restaurant"))
            ok = (
                report.get("found")
                and bool(report.get("summary"))
                and report.get("parcel", {}).get("jurisdiction") == jurisdiction
                and bool(report.get("zone_profile"))
                and bool(report.get("use_status"))
                and "development_standards" in report
                and "overlays" in report
                and bool(report.get("citations"))
            )
            results["feasibility_reports"].append(
                {
                    "jurisdiction": jurisdiction,
                    "parcel_id": sample["parcel_id"],
                    "proposed_use": preferred_use.get(jurisdiction, "restaurant"),
                    "summary": report.get("summary"),
                    "status": report.get("use_status", {}).get("status"),
                    "citation_count": len(report.get("citations", [])),
                    "ok": ok,
                }
            )
            if not ok:
                failures.append(f"parcel feasibility report failed for {jurisdiction} parcel {sample['parcel_id']}")
        return failures

    def _imported_zone_codes(self) -> dict[str, set[str]]:
        rows = Zone.objects.select_related("jurisdiction").values_list("jurisdiction__key", "zone_code")
        zones: dict[str, set[str]] = defaultdict(set)
        for jurisdiction, zone_code in rows:
            zones[jurisdiction].add(zone_code)
        return zones
