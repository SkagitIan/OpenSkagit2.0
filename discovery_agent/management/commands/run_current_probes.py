from __future__ import annotations

import json
import os
from getpass import getpass
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from discovery_agent.management.commands.discover_current_test import (
    SUPPORTED_PROBES,
    annotate_records,
    build_editor_prompt,
    build_probe_sql,
    build_qa_flags,
    fetch_columns,
    load_probe_catalog,
    parse_model_json,
    rows_for_sql,
    summarize_missing_columns,
)
from discovery_agent.models import CurrentDraft


ARTIFACT_TERMS = (
    "artifact",
    "tiny parcel",
    "under 0.05",
    "under 0.1",
    "zero acreage",
    "water area",
    "right-of-way",
    "common area",
)


def _score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _idea_text(idea: dict[str, Any]) -> str:
    parts = [
        idea.get("question", ""),
        idea.get("short_answer", ""),
        idea.get("why_it_matters", ""),
        idea.get("data_used", ""),
        " ".join(str(item) for item in idea.get("caveats", []) if item),
    ]
    return " ".join(str(part) for part in parts).lower()


def _artifact_based_reason(idea: dict[str, Any]) -> str:
    text = _idea_text(idea)
    if any(term in text for term in ARTIFACT_TERMS) and "data quality" not in text:
        return "Idea appears to rely on artifact-prone rows without framing the finding as data quality."
    return ""


def _idea_to_draft(
    *,
    probe: str,
    model: str,
    row_count: int,
    qa_flags: list[str],
    probe_metadata: dict[str, Any],
    idea: dict[str, Any],
    status: str,
    rejection_reason: str = "",
) -> CurrentDraft:
    return CurrentDraft(
        status=status,
        probe=probe,
        model=model,
        question=str(idea.get("question", "")).strip() or "(Untitled Current lead)",
        short_answer=str(idea.get("short_answer", "")).strip(),
        why_it_matters=str(idea.get("why_it_matters", "")).strip(),
        confidence=_score(idea.get("confidence")) or None,
        publish_score=_score(idea.get("publish_score")) or None,
        source_data=str(idea.get("data_used", "")).strip(),
        caveats=idea.get("caveats") if isinstance(idea.get("caveats"), list) else [],
        what_to_check_next=str(idea.get("what_to_check_next", "")).strip(),
        rejection_reason=rejection_reason,
        row_count=row_count,
        qa_flags=qa_flags,
        probe_metadata=probe_metadata,
        raw_payload=idea,
    )


class Command(BaseCommand):
    help = "Run OpenSkagit Current discovery probes and save draft/rejected Current items for staff review."

    def add_arguments(self, parser):
        parser.add_argument(
            "--probe",
            action="append",
            dest="probes",
            help="Probe to run. May be passed more than once. Defaults to every implemented v1 probe.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Rows per probe to send to the model. Default: 100.",
        )
        parser.add_argument(
            "--model",
            default="gpt-4.1-mini",
            help="OpenAI model for draft generation. Default: gpt-4.1-mini.",
        )
        parser.add_argument(
            "--min-publish-score",
            type=int,
            default=75,
            help="Minimum publish_score to save as a draft instead of rejected. Default: 75.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run probes and model calls, but do not save CurrentDraft rows.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable run results.",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"])
        if limit <= 0:
            raise CommandError("--limit must be greater than 0.")

        min_publish_score = int(options["min_publish_score"])
        probe_catalog = load_probe_catalog()
        requested_probes = options["probes"] or sorted(SUPPORTED_PROBES)
        unknown = [probe for probe in requested_probes if probe not in probe_catalog]
        if unknown:
            raise CommandError(f"Unknown probe(s): {', '.join(unknown)}")
        unsupported = [probe for probe in requested_probes if probe not in SUPPORTED_PROBES]
        if unsupported:
            raise CommandError(
                "Probe(s) are in the catalog but do not have v1 SQL yet: "
                + ", ".join(unsupported)
            )

        columns = fetch_columns()
        missing = summarize_missing_columns(columns)
        if missing:
            raise CommandError("Missing required PostGIS table/column(s): " + ", ".join(missing))

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            api_key = getpass("OpenAI API key: ").strip()
            if not api_key:
                raise CommandError("OPENAI_API_KEY is required.")
            os.environ["OPENAI_API_KEY"] = api_key

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise CommandError("The openai package is not installed. Run: pip install -r requirements.txt") from exc

        client = OpenAI()
        model = str(options["model"]).strip()
        run_results: list[dict[str, Any]] = []
        drafts_to_create: list[CurrentDraft] = []

        for probe in requested_probes:
            sql = build_probe_sql(probe, columns, limit)
            records = annotate_records(rows_for_sql(sql))
            if not records:
                run_results.append({"probe": probe, "row_count": 0, "created": 0, "rejected": 0, "status": "no_rows"})
                continue

            qa_flags = build_qa_flags(records)
            response = client.responses.create(
                model=model,
                input=build_editor_prompt(probe_catalog[probe], records),
                temperature=0.2,
            )
            parsed = parse_model_json(response.output_text)
            ideas = parsed.get("ideas", []) if isinstance(parsed, dict) else parsed
            rejected_ideas = parsed.get("rejected_ideas", []) if isinstance(parsed, dict) else []
            if not isinstance(ideas, list):
                ideas = []
            if not isinstance(rejected_ideas, list):
                rejected_ideas = []

            created_count = 0
            rejected_count = 0
            for idea in ideas:
                if not isinstance(idea, dict):
                    continue
                rejection_reason = _artifact_based_reason(idea)
                if not rejection_reason and _score(idea.get("publish_score")) < min_publish_score:
                    rejection_reason = f"publish_score below {min_publish_score}."
                status = CurrentDraft.Status.REJECTED if rejection_reason else CurrentDraft.Status.DRAFT
                drafts_to_create.append(
                    _idea_to_draft(
                        probe=probe,
                        model=model,
                        row_count=len(records),
                        qa_flags=qa_flags,
                        probe_metadata=probe_catalog[probe],
                        idea=idea,
                        status=status,
                        rejection_reason=rejection_reason,
                    )
                )
                if status == CurrentDraft.Status.DRAFT:
                    created_count += 1
                else:
                    rejected_count += 1

            for idea in rejected_ideas:
                if not isinstance(idea, dict):
                    continue
                normalized = {
                    "question": idea.get("question", ""),
                    "publish_score": 0,
                }
                drafts_to_create.append(
                    _idea_to_draft(
                        probe=probe,
                        model=model,
                        row_count=len(records),
                        qa_flags=qa_flags,
                        probe_metadata=probe_catalog[probe],
                        idea=normalized,
                        status=CurrentDraft.Status.REJECTED,
                        rejection_reason=str(idea.get("reason", "")).strip(),
                    )
                )
                rejected_count += 1

            run_results.append(
                {
                    "probe": probe,
                    "row_count": len(records),
                    "created": created_count,
                    "rejected": rejected_count,
                    "qa_flags": qa_flags,
                    "status": "ok",
                }
            )

        if not options["dry_run"] and drafts_to_create:
            with transaction.atomic():
                CurrentDraft.objects.bulk_create(drafts_to_create)

        payload = {
            "dry_run": bool(options["dry_run"]),
            "model": model,
            "probes": run_results,
            "draft_count": sum(item["created"] for item in run_results),
            "rejected_count": sum(item["rejected"] for item in run_results),
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, default=str))
            return

        action = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {payload['draft_count']} Current draft(s); "
                f"{payload['rejected_count']} rejected item(s)."
            )
        )
        for item in run_results:
            self.stdout.write(
                f"{item['probe']}: rows={item['row_count']} "
                f"drafts={item['created']} rejected={item['rejected']} status={item['status']}"
            )
