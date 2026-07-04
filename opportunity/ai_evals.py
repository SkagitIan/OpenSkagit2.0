from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from django.conf import settings

from .ai_search import (
    _fallback_search_plan,
    _has_bare_recreation_land_evidence,
    _has_dwelling_evidence,
    _intent_context,
    _json_safe,
    _zoning_mcp_context,
    apply_prompt_result_filters,
)
from .r2_search import (
    DuckDBR2OpportunityClient,
    R2GeneratedSearch,
    R2SearchError,
    code_reference_text,
    generate_r2_search,
    ontology_reference_text,
    run_generated_r2_search,
    schema_reference_text,
    validate_r2_search_sql,
    zoning_mcp_reference_text,
)
from .services import utility_labels


DEFAULT_CASES_PATH = Path("data") / "opportunity_ai_eval_cases.json"
DEFAULT_REPORT_DIR = Path("reports") / "opportunity_ai_evals"
DEFAULT_RESULT_LIMIT = 200
GENERATION_ATTEMPTS = 3


@dataclass(frozen=True)
class OpportunityEvalCase:
    id: str
    prompt: str
    notes: str = ""
    expected_min_result_count: int | None = None
    expected_max_result_count: int | None = None
    required_sql_patterns: list[str] = field(default_factory=list)
    forbidden_sql_patterns: list[str] = field(default_factory=list)
    required_parcels: list[str] = field(default_factory=list)
    forbidden_parcels: list[str] = field(default_factory=list)
    row_expectations: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalFailure:
    code: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


@dataclass
class EvalCaseResult:
    case: OpportunityEvalCase
    status: str
    failures: list[EvalFailure]
    generated: R2GeneratedSearch | None = None
    raw_rows: list[dict[str, Any]] = field(default_factory=list)
    hydrated_rows: list[dict[str, Any]] = field(default_factory=list)
    filtered_rows: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    repair_report: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        action_plan = build_action_plan(self)
        return {
            "id": self.case.id,
            "prompt": self.case.prompt,
            "status": self.status,
            "failures": [failure.as_dict() for failure in self.failures],
            "action_plan": action_plan,
            "next_action": action_plan[0] if action_plan else "",
            "generated_sql": self.generated.sql if self.generated else "",
            "generated_params": _json_safe(self.generated.params) if self.generated else [],
            "title": self.generated.title if self.generated else "",
            "criteria_summary": self.generated.criteria_summary if self.generated else "",
            "raw_row_count": len(self.raw_rows),
            "hydrated_row_count": len(self.hydrated_rows),
            "filtered_row_count": len(self.filtered_rows),
            "top_result_parcels": [row.get("parcel_number") for row in self.filtered_rows[:10]],
            "sample_rows": [_sample_row(row) for row in self.filtered_rows[:5]],
            "diagnostics": _json_safe(self.diagnostics),
            "repair_report": _json_safe(self.repair_report or {}),
        }


@dataclass
class EvalRunResult:
    cases: list[EvalCaseResult]
    report_path: str = ""

    @property
    def passed_count(self) -> int:
        return sum(1 for case in self.cases if case.status == "passed")

    @property
    def failed_count(self) -> int:
        return sum(1 for case in self.cases if case.status == "failed")

    @property
    def error_count(self) -> int:
        return sum(1 for case in self.cases if case.status == "error")

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": len(self.cases),
                "passed": self.passed_count,
                "failed": self.failed_count,
                "errors": self.error_count,
            },
            "report_path": self.report_path,
            "cases": [case.as_dict() for case in self.cases],
        }


Generator = Callable[..., R2GeneratedSearch]
Executor = Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]]


def default_eval_cases_path() -> Path:
    return Path(settings.BASE_DIR) / DEFAULT_CASES_PATH


def load_eval_cases(path: str | Path | None = None, *, case_ids: list[str] | None = None, limit: int | None = None) -> list[OpportunityEvalCase]:
    cases_path = Path(path) if path else default_eval_cases_path()
    if not cases_path.is_absolute():
        cases_path = Path(settings.BASE_DIR) / cases_path
    try:
        payload = json.loads(cases_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read eval cases from {cases_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Eval cases file is not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Eval cases file must contain a JSON list.")
    cases = [_case_from_payload(item, index) for index, item in enumerate(payload)]
    if case_ids:
        wanted = set(case_ids)
        cases = [case for case in cases if case.id in wanted]
        missing = sorted(wanted - {case.id for case in cases})
        if missing:
            raise ValueError(f"Unknown eval case id(s): {', '.join(missing)}")
    if limit is not None:
        cases = cases[: max(0, int(limit))]
    return cases


def run_opportunity_ai_evals(
    *,
    cases_path: str | Path | None = None,
    case_ids: list[str] | None = None,
    limit: int | None = None,
    model: str | None = None,
    repair_report: bool = False,
    generator: Generator = generate_r2_search,
    executor: Executor = run_generated_r2_search,
    r2_client: DuckDBR2OpportunityClient | None = None,
) -> EvalRunResult:
    cases = load_eval_cases(cases_path, case_ids=case_ids, limit=limit)
    model = model or _search_model()
    r2_client = r2_client or DuckDBR2OpportunityClient()
    results = [
        run_eval_case(case, model=model, generator=generator, executor=executor, r2_client=r2_client, repair_report=repair_report)
        for case in cases
    ]
    return EvalRunResult(results)


def run_eval_case(
    case: OpportunityEvalCase,
    *,
    model: str,
    generator: Generator = generate_r2_search,
    executor: Executor = run_generated_r2_search,
    r2_client: DuckDBR2OpportunityClient | None = None,
    repair_report: bool = False,
) -> EvalCaseResult:
    r2_client = r2_client or DuckDBR2OpportunityClient()
    generated: R2GeneratedSearch | None = None
    raw_rows: list[dict[str, Any]] = []
    hydrated_rows: list[dict[str, Any]] = []
    filtered_rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    failures: list[EvalFailure] = []

    extra_context = _eval_extra_context(case.prompt)
    generation_feedback = ""
    generation_attempts: list[dict[str, Any]] = []
    status = "error"

    for attempt in range(1, GENERATION_ATTEMPTS + 1):
        raw_rows = []
        hydrated_rows = []
        filtered_rows = []
        failures = []
        try:
            generated = generator(
                case.prompt,
                model=model,
                extra_context=extra_context,
                error_feedback=generation_feedback,
                r2_client=r2_client,
            )
            try:
                validate_r2_search_sql(generated.sql, generated.params)
            except R2SearchError as exc:
                failures.append(EvalFailure("sql_validation", str(exc)))

            if not failures:
                raw_rows, hydrated_rows, diagnostics = executor(generated, r2_client=r2_client, limit=DEFAULT_RESULT_LIMIT)
                filtered_rows = apply_prompt_result_filters(case.prompt, hydrated_rows)
                diagnostics = {
                    **diagnostics,
                    "eval_raw_row_count": len(raw_rows),
                    "eval_hydrated_row_count": len(hydrated_rows),
                    "eval_filtered_row_count": len(filtered_rows),
                }

            failures.extend(evaluate_sql(case, generated.sql if generated else ""))
            failures.extend(evaluate_rows(case, filtered_rows))
            if not failures:
                status = "passed"
                generation_attempts.append({"attempt": attempt, "status": "passed"})
                break

            status = "failed"
            generation_attempts.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "failures": [{"code": failure.code, "message": failure.message} for failure in failures],
                }
            )
            if attempt == GENERATION_ATTEMPTS or not _should_retry_eval_failures(failures):
                break
            generation_feedback = _eval_retry_feedback(failures)
        except Exception as exc:
            failures = [EvalFailure("eval_exception", f"{type(exc).__name__}: {exc}")]
            status = "error"
            generation_attempts.append({"attempt": attempt, "status": "error", "error": str(exc)})
            if attempt == GENERATION_ATTEMPTS:
                break
            generation_feedback = _eval_retry_feedback(failures)

    diagnostics = {**diagnostics, "generation_attempts": generation_attempts}

    result = EvalCaseResult(
        case=case,
        status=status,
        failures=failures,
        generated=generated,
        raw_rows=raw_rows,
        hydrated_rows=hydrated_rows,
        filtered_rows=filtered_rows,
        diagnostics=diagnostics,
    )
    if repair_report and failures:
        result.repair_report = generate_repair_report(result, model=model)
    return result


def _should_retry_eval_failures(failures: list[EvalFailure]) -> bool:
    retryable = {
        "sql_validation",
        "eval_exception",
        "required_sql_pattern",
        "forbidden_sql_pattern",
        "min_result_count",
        "row_low_quality",
        "row_utilities",
        "row_no_utilities",
        "row_no_exemptions",
        "row_dwelling",
        "row_bare_recreation",
        "row_place",
        "row_land_use_code",
        "row_forbidden_land_use_code",
        "row_zoning",
        "row_min_assessed_value",
        "row_max_assessed_value",
        "row_min_years_since_sale",
        "row_max_years_since_sale",
        "row_max_improvements",
        "row_min_numeric_field",
        "row_max_numeric_field",
        "row_required_text",
        "row_forbidden_text",
        "row_match_reasons",
        "row_geometry",
        "row_quality_code",
        "row_forbidden_quality_code",
    }
    return any(failure.code in retryable for failure in failures)


def _eval_retry_feedback(failures: list[EvalFailure]) -> str:
    lines = ["The previous attempt failed deterministic eval checks. Regenerate the SQL and fix these issues:"]
    for failure in failures[:8]:
        lines.append(f"- {failure.code}: {failure.message}")
    messages = " ".join(failure.message for failure in failures).lower()
    if "year_built" in messages or "building_value" in messages:
        lines.append(
            "Do not invent generic parcel_search columns like year_built or building_value. Use primary_actual_year_built, oldest_actual_year_built, assessor_building_value, primary_building_improvement_value, or total_improvement_value only when listed for the selected parquet file."
        )
    if "row_min_assessed_value" in messages or "row_max_assessed_value" in messages or "assessed_value" in messages:
        lines.append(
            "Apply assessed_value thresholds to the whole candidate set. If land-use families are joined with OR, wrap them in parentheses before adding AND ps.assessed_value filters."
        )
    if "row_utilities" in messages or "utilities" in messages:
        lines.append('For utility prompts, join assessor.parquet and select TRIM(a."Utilities") AS utilities; filtering on a."Utilities" without selecting it is not enough.')
    if "row_no_exemptions" in messages or "exemptions" in messages:
        lines.append('For no-exemptions prompts, join assessor.parquet and select TRIM(a."Exemptions") AS exemptions; derived/parcel_search.parquet does not have exemptions.')
    if "row_max_improvements" in messages or "improvement_building_count" in messages:
        lines.append("For no-improvement/unimproved prompts, filter COALESCE(ps.improvement_building_count, 0) = 0 and select ps.improvement_building_count.")
    if "years_since_last_valid_sale=none" in messages:
        lines.append("For no-valid-sale prompts, NULL years_since_last_valid_sale can be acceptable only when the eval allows missing sales; otherwise filter it out or select has_valid_sale evidence.")
    if "skagit" in messages or "min_result_count" in messages:
        lines.append("For prompts that say Skagit County, do not filter city_name or situs_city_state_zip for 'skagit'; the R2 dataset is already countywide.")
    if "could not convert string" in messages or "regexp_extract" in messages:
        lines.append("Do not CAST regexp_extract(land_use) directly. Use TRY_CAST(NULLIF(regexp_extract(COALESCE(ps.land_use, ''), '^\\\\((\\\\d+)\\\\)', 1), '') AS INTEGER), or compare extracted codes as text.")
    if "low-quality" in messages or "low quality" in messages or "row_low_quality" in messages:
        lines.append(
            "For low-quality dwelling prompts, use improvements.parquet.imprv_det_class_cd = 'MSL' and select quality_codes or match_reasons so the result explains the MSL evidence."
        )
    if "row_quality_code" in messages or "quality_codes=" in messages:
        lines.append(
            "For requested quality codes, filter the raw improvement class exactly: MSL=low, MSF=fair, MSA=average. "
            "Do not satisfy an average-quality prompt by only excluding MSL; require TRIM(i.imprv_det_class_cd) = 'MSA' and select quality_codes."
        )
    if "row_forbidden_text" in messages:
        lines.append(
            "For public/church/cemetery/school/moorage/condo exclusions, filter current owner_name, situs_address, and land_use fields. Do not rely only on land_use labels."
        )
    if "row_land_use_code" in messages and any(code in messages for code in ("110", "111", "112", "113")):
        lines.append(
            "For prompts that specifically say SFR, single-family, or single family homes, filter DOR land_use codes to 110, 111, 112, and 113 only. "
            "Do not include manufactured/mobile home codes 180 or 185 unless the prompt explicitly asks for mobile/manufactured homes."
        )
    if "primary_actual_year_built" in messages or "oldest_actual_year_built" in messages:
        lines.append(
            "For built-before prompts, use and select primary_actual_year_built or oldest_actual_year_built from a derived parcel/improvement parquet; do not alias assessor_year_built as year_built."
        )
    return "\n".join(lines)


def evaluate_sql(case: OpportunityEvalCase, sql: str) -> list[EvalFailure]:
    failures: list[EvalFailure] = []
    for pattern in case.required_sql_patterns:
        if not re.search(pattern, sql or "", re.IGNORECASE | re.DOTALL):
            failures.append(EvalFailure("required_sql_pattern", f"SQL did not match required pattern: {pattern}"))
    for pattern in case.forbidden_sql_patterns:
        if re.search(pattern, sql or "", re.IGNORECASE | re.DOTALL):
            failures.append(EvalFailure("forbidden_sql_pattern", f"SQL matched forbidden pattern: {pattern}"))
    return failures


def evaluate_rows(case: OpportunityEvalCase, rows: list[dict[str, Any]]) -> list[EvalFailure]:
    failures: list[EvalFailure] = []
    count = len(rows)
    if case.expected_min_result_count is not None and count < case.expected_min_result_count:
        failures.append(EvalFailure("min_result_count", f"Expected at least {case.expected_min_result_count} rows, got {count}."))
    if case.expected_max_result_count is not None and count > case.expected_max_result_count:
        failures.append(EvalFailure("max_result_count", f"Expected at most {case.expected_max_result_count} rows, got {count}."))

    parcels = {str(row.get("parcel_number") or "").upper() for row in rows}
    for parcel in case.required_parcels:
        if parcel.upper() not in parcels:
            failures.append(EvalFailure("required_parcel", f"Required parcel {parcel} was not returned."))
    for parcel in case.forbidden_parcels:
        if parcel.upper() in parcels:
            failures.append(EvalFailure("forbidden_parcel", f"Forbidden parcel {parcel} was returned."))

    expectations = case.row_expectations or {}
    row_failures = []
    for index, row in enumerate(rows):
        row_failures.extend(_evaluate_row(expectations, row, index))
        if len(row_failures) >= 10:
            row_failures.append(EvalFailure("row_failure_limit", "Stopped after 10 row-level failures."))
            break
    failures.extend(row_failures)
    return failures


def build_action_plan(result: EvalCaseResult) -> list[str]:
    if result.status == "passed":
        return ["No action needed. Keep this case in the regression suite."]

    actions: list[str] = []
    sql = result.generated.sql if result.generated else ""
    failure_codes = {failure.code for failure in result.failures}
    messages = " ".join(failure.message for failure in result.failures).lower()

    incomplete_cte = bool(re.match(r"(?is)^\s*with\b", sql or "")) and bool(re.search(r"(?is)\)\s*$", sql or ""))
    if incomplete_cte or 'syntax error at or near ")"' in messages:
        actions.append(
            "The model emitted a WITH/CTE block but no final SELECT. Keep the validator/generation guardrail that rejects incomplete CTEs, then rerun so the model produces SELECT ... FROM the CTE."
        )
    if "must read from allowed r2 parquet files" in messages:
        actions.append(
            "The model generated SQL without an approved read_parquet('r2://openskagit/...') source. Regenerate with explicit allowed parquet paths; low-quality dwelling searches should join parcel_search.parquet to improvements.parquet."
        )

    if "sql_validation" in failure_codes or "eval_exception" in failure_codes:
        actions.append("Fix the SQL-generation guardrail or schema contract named in the failure before rerunning the eval.")

    if "min_result_count" in failure_codes and not result.filtered_rows:
        if re.search(r"primary_building_style\s+LIKE\s+'%MSL%'", sql, re.IGNORECASE):
            actions.append(
                "The query is too narrow: it only checks primary_building_style for MSL. Update generation guidance to search low-quality evidence across condition_codes, improvement_detail_types, primary_building_style, and raw improvement class/code fields when needed."
            )
        elif "msl" in sql.lower() or "msf" in sql.lower() or "msa" in sql.lower():
            actions.append(
                "The query is using appraisal class/quality codes against condition_codes. Join improvements.parquet and filter TRIM(i.imprv_det_class_cd) = 'MSL' for low-quality dwellings; condition_codes are the separate L/F/A/G/VG condition family."
            )
        elif "low" in result.case.prompt.lower() or "quality" in result.case.prompt.lower():
            actions.append(
                "Verify whether matching low-quality records exist for this place/acreage band. If none exist, mark the eval as expected_min_result_count=0 or broaden the prompt/eval to fair-or-low quality."
            )
        else:
            actions.append("The generated SQL returned no accepted rows. Inspect hard WHERE filters and move uncertain criteria into score/match_reasons.")

    if "max_result_count" in failure_codes:
        actions.append(
            "The query returned more rows than the eval allows. Either add a deterministic LIMIT/order for this case or raise expected_max_result_count if the broader result set is acceptable."
        )

    if "required_sql_pattern" in failure_codes:
        actions.append("Add the required SQL construct from the eval case, or remove that expectation if it is not truly required.")
    if "forbidden_sql_pattern" in failure_codes:
        actions.append("Remove the forbidden SQL pattern from generation guidance and add/keep a validator regression for it.")
    if "row_place" in failure_codes:
        actions.append("Tighten place matching in SQL and keep app-level prompt-place filtering as a backstop.")
    if "row_utilities" in failure_codes:
        actions.append("Join assessor.parquet for a.\"Utilities\", filter non-empty utility tokens, and select TRIM(a.\"Utilities\") AS utilities so rows carry utility evidence.")
    if "row_no_utilities" in failure_codes:
        actions.append("For no-utilities prompts, join assessor.parquet, filter TRIM(COALESCE(a.\"Utilities\", '')) = '', and select it AS utilities for verification.")
    if "row_no_exemptions" in failure_codes:
        actions.append("For no-exemptions prompts, join assessor.parquet, filter TRIM(COALESCE(a.\"Exemptions\", '')) = '', and select it AS exemptions for verification.")
    if "row_dwelling" in failure_codes:
        actions.append("Require residential dwelling evidence using land-use code and improvement/detail signals before accepting rows.")
    if "row_bare_recreation" in failure_codes:
        actions.append("Use extracted land-use codes and existing bare/recreation app filters; avoid direct numeric comparisons to land_use labels.")
    if "row_low_quality" in failure_codes:
        actions.append("Return explicit low-quality evidence in selected columns or match_reasons so the row-level evaluator can verify it.")
    if "row_land_use_code" in failure_codes or "row_forbidden_land_use_code" in failure_codes:
        actions.append("Use regexp_extract(COALESCE(land_use, ''), '^\\\\((\\\\d+)\\\\)', 1) for DOR land-use code filters and select land_use/land_use_code evidence.")
    if "row_zoning" in failure_codes:
        actions.append("Tighten zoning or comprehensive-plan filters and select zoning_code_short/zoning_label so the row-level evaluator can verify zoning intent.")
    if "row_min_assessed_value" in failure_codes or "row_max_assessed_value" in failure_codes:
        actions.append("Apply the assessed-value threshold in SQL and select assessed_value for verification.")
    if "row_min_years_since_sale" in failure_codes or "row_max_years_since_sale" in failure_codes:
        actions.append("Use a sales-summary parquet with years_since_last_valid_sale and select that field for verification.")
    if "row_max_improvements" in failure_codes:
        actions.append("Apply the improvement_building_count threshold in SQL and select improvement_building_count for verification.")
    if "row_min_numeric_field" in failure_codes or "row_max_numeric_field" in failure_codes:
        actions.append("Apply the requested numeric threshold in SQL and select the evidence field so row-level evaluation can verify it.")
    if "row_required_text" in failure_codes or "row_forbidden_text" in failure_codes:
        actions.append("Tighten text/code evidence in SQL and select match_reasons or source fields that explain why each row belongs.")
    if "row_match_reasons" in failure_codes:
        actions.append("Select a concise match_reasons value explaining the evidence behind each returned row.")
    if "row_geometry" in failure_codes:
        actions.append("Require valid geometry/map evidence, such as has_geometry = TRUE with valid WGS84 gis_x/gis_y bounds.")
    if "row_quality_code" in failure_codes or "row_forbidden_quality_code" in failure_codes:
        actions.append("Join improvements.parquet, filter imprv_det_class_cd to the requested quality code, and select quality_codes for verification.")

    if not actions:
        actions.append(f"Inspect failures directly: {messages[:240]}")
    return _dedupe(actions)


def generate_repair_report(result: EvalCaseResult, *, model: str | None = None) -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "verdict": "not_run",
            "issues": ["OPENAI_API_KEY is not set; repair report was skipped."],
            "likely_layer": "",
            "suggested_tests": [],
            "patch_proposal": "",
        }
    try:
        from openai import OpenAI

        response = OpenAI(timeout=float(os.environ.get("OPPORTUNITY_EVAL_REPAIR_TIMEOUT", "75"))).responses.create(
            model=os.environ.get("OPPORTUNITY_EVAL_REPAIR_MODEL", model or _search_model()),
            instructions=_repair_instructions(),
            input=json.dumps(_repair_payload(result), indent=2, default=str),
            temperature=0.1,
            max_output_tokens=2200,
        )
        return _parse_repair_response(getattr(response, "output_text", "") or str(response))
    except Exception as exc:
        return {
            "verdict": "error",
            "issues": [f"{type(exc).__name__}: {exc}"],
            "likely_layer": "",
            "suggested_tests": [],
            "patch_proposal": "",
        }


def write_eval_report(result: EvalRunResult, *, output_dir: str | Path | None = None) -> Path:
    report_dir = Path(output_dir) if output_dir else Path(settings.BASE_DIR) / DEFAULT_REPORT_DIR
    if not report_dir.is_absolute():
        report_dir = Path(settings.BASE_DIR) / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"opportunity-ai-evals-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(result.as_dict(), indent=2, default=str), encoding="utf-8")
    result.report_path = str(path)
    return path


def _case_from_payload(payload: Any, index: int) -> OpportunityEvalCase:
    if not isinstance(payload, dict):
        raise ValueError(f"Eval case #{index + 1} must be an object.")
    required = ["id", "prompt"]
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise ValueError(f"Eval case #{index + 1} is missing required field(s): {', '.join(missing)}.")
    list_fields = ["required_sql_patterns", "forbidden_sql_patterns", "required_parcels", "forbidden_parcels"]
    for field_name in list_fields:
        value = payload.get(field_name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Eval case {payload['id']} field {field_name} must be a list of strings.")
    row_expectations = payload.get("row_expectations", {})
    if not isinstance(row_expectations, dict):
        raise ValueError(f"Eval case {payload['id']} row_expectations must be an object.")
    return OpportunityEvalCase(
        id=str(payload["id"]),
        prompt=str(payload["prompt"]),
        notes=str(payload.get("notes") or ""),
        expected_min_result_count=_optional_int(payload.get("expected_min_result_count")),
        expected_max_result_count=_optional_int(payload.get("expected_max_result_count")),
        required_sql_patterns=list(payload.get("required_sql_patterns", [])),
        forbidden_sql_patterns=list(payload.get("forbidden_sql_patterns", [])),
        required_parcels=list(payload.get("required_parcels", [])),
        forbidden_parcels=list(payload.get("forbidden_parcels", [])),
        row_expectations=row_expectations,
    )


def _evaluate_row(expectations: dict[str, Any], row: dict[str, Any], index: int) -> list[EvalFailure]:
    failures: list[EvalFailure] = []
    label = f"row {index + 1} parcel {row.get('parcel_number') or 'unknown'}"
    if terms := _string_list(expectations.get("place_terms")):
        if not _row_contains_any(row, terms):
            failures.append(EvalFailure("row_place", f"{label} did not match any expected place term: {', '.join(terms)}."))
    if terms := _string_list(expectations.get("forbidden_place_terms")):
        if _row_contains_any(row, terms):
            failures.append(EvalFailure("row_forbidden_place", f"{label} matched a forbidden place term: {', '.join(terms)}."))
    if expectations.get("min_acres") is not None:
        acres = _number(_row_value(row, "acres"))
        if acres is None or acres < float(expectations["min_acres"]):
            failures.append(EvalFailure("row_min_acres", f"{label} had acres={acres}, expected >= {expectations['min_acres']}."))
    if expectations.get("max_acres") is not None:
        acres = _number(_row_value(row, "acres"))
        if acres is None or acres > float(expectations["max_acres"]):
            failures.append(EvalFailure("row_max_acres", f"{label} had acres={acres}, expected <= {expectations['max_acres']}."))
    if expectations.get("max_improvement_building_count") is not None:
        count = _number(_row_value(row, "improvement_building_count"))
        if count is not None and count > float(expectations["max_improvement_building_count"]):
            failures.append(
                EvalFailure(
                    "row_max_improvements",
                    f"{label} had improvement_building_count={count}, expected <= {expectations['max_improvement_building_count']}.",
                )
            )
    if expectations.get("min_assessed_value") is not None:
        assessed = _number(_row_value(row, "assessed_value"))
        if assessed is None or assessed < float(expectations["min_assessed_value"]):
            failures.append(EvalFailure("row_min_assessed_value", f"{label} had assessed_value={assessed}, expected >= {expectations['min_assessed_value']}."))
    if expectations.get("max_assessed_value") is not None:
        assessed = _number(_row_value(row, "assessed_value"))
        if assessed is None or assessed > float(expectations["max_assessed_value"]):
            failures.append(EvalFailure("row_max_assessed_value", f"{label} had assessed_value={assessed}, expected <= {expectations['max_assessed_value']}."))
    if expectations.get("min_years_since_last_valid_sale") is not None:
        years = _number(_row_value(row, "years_since_last_valid_sale"))
        if years is None and expectations.get("allow_missing_sale_as_old"):
            pass
        elif years is None or years < float(expectations["min_years_since_last_valid_sale"]):
            failures.append(
                EvalFailure(
                    "row_min_years_since_sale",
                    f"{label} had years_since_last_valid_sale={years}, expected >= {expectations['min_years_since_last_valid_sale']}.",
                )
            )
    if expectations.get("max_years_since_last_valid_sale") is not None:
        years = _number(_row_value(row, "years_since_last_valid_sale"))
        if years is None or years > float(expectations["max_years_since_last_valid_sale"]):
            failures.append(
                EvalFailure(
                    "row_max_years_since_sale",
                    f"{label} had years_since_last_valid_sale={years}, expected <= {expectations['max_years_since_last_valid_sale']}.",
                )
            )
    for field, threshold in (expectations.get("min_numeric_fields") or {}).items():
        value = _number(_row_value(row, str(field)))
        if value is None or value < float(threshold):
            failures.append(EvalFailure("row_min_numeric_field", f"{label} had {field}={value}, expected >= {threshold}."))
    for field, threshold in (expectations.get("max_numeric_fields") or {}).items():
        value = _number(_row_value(row, str(field)))
        if value is None or value > float(threshold):
            failures.append(EvalFailure("row_max_numeric_field", f"{label} had {field}={value}, expected <= {threshold}."))
    land_use_code = _row_land_use_code(row)
    if codes := _string_list(expectations.get("expected_land_use_codes")):
        if land_use_code not in codes:
            failures.append(EvalFailure("row_land_use_code", f"{label} had land_use_code={land_use_code}, expected one of: {', '.join(codes)}."))
    if prefixes := _string_list(expectations.get("expected_land_use_code_prefixes")):
        if not land_use_code or not any(land_use_code.startswith(prefix) for prefix in prefixes):
            failures.append(EvalFailure("row_land_use_code", f"{label} had land_use_code={land_use_code}, expected prefix one of: {', '.join(prefixes)}."))
    if codes := _string_list(expectations.get("forbidden_land_use_codes")):
        if land_use_code in codes:
            failures.append(EvalFailure("row_forbidden_land_use_code", f"{label} had forbidden land_use_code={land_use_code}."))
    if prefixes := _string_list(expectations.get("forbidden_land_use_code_prefixes")):
        if land_use_code and any(land_use_code.startswith(prefix) for prefix in prefixes):
            failures.append(EvalFailure("row_forbidden_land_use_code", f"{label} had forbidden land_use_code={land_use_code}."))
    if terms := _string_list(expectations.get("zoning_terms")):
        if not _row_zoning_contains_any(row, terms):
            failures.append(EvalFailure("row_zoning", f"{label} did not match any expected zoning term: {', '.join(terms)}."))
    quality_codes = _row_quality_codes(row)
    if codes := _string_list(expectations.get("expected_quality_codes")):
        if not quality_codes.intersection({code.upper() for code in codes}):
            failures.append(EvalFailure("row_quality_code", f"{label} had quality_codes={sorted(quality_codes)}, expected one of: {', '.join(codes)}."))
    if codes := _string_list(expectations.get("forbidden_quality_codes")):
        forbidden = quality_codes.intersection({code.upper() for code in codes})
        if forbidden:
            failures.append(EvalFailure("row_forbidden_quality_code", f"{label} had forbidden quality_codes={sorted(forbidden)}."))
    for term in _string_list(expectations.get("required_text_terms")):
        if term.lower() not in _row_searchable_text(row):
            failures.append(EvalFailure("row_required_text", f"{label} did not include required text term: {term}."))
    for term in _string_list(expectations.get("forbidden_text_terms")):
        if term.lower() in _row_current_searchable_text(row):
            failures.append(EvalFailure("row_forbidden_text", f"{label} included forbidden text term: {term}."))
    if expectations.get("require_match_reasons") and not _row_has_match_reasons(row):
        failures.append(EvalFailure("row_match_reasons", f"{label} did not include match reasons."))
    if expectations.get("require_geometry") and not _row_has_geometry(row):
        failures.append(EvalFailure("row_geometry", f"{label} did not include valid map geometry."))
    if expectations.get("require_utilities") and not _row_has_utilities(row):
        failures.append(EvalFailure("row_utilities", f"{label} did not include utility evidence."))
    if expectations.get("require_no_utilities") and _row_has_utilities(row):
        failures.append(EvalFailure("row_no_utilities", f"{label} included utility evidence when none was expected."))
    if expectations.get("require_no_exemptions") and str(_row_value(row, "exemptions") or "").strip():
        failures.append(EvalFailure("row_no_exemptions", f"{label} included exemptions when none were expected."))
    if expectations.get("require_dwelling") and not _has_dwelling_evidence(row):
        failures.append(EvalFailure("row_dwelling", f"{label} did not include residential dwelling evidence."))
    if expectations.get("require_bare_recreation_land") and not _has_bare_recreation_land_evidence(row):
        failures.append(EvalFailure("row_bare_recreation", f"{label} did not include bare/recreation land evidence."))
    if expectations.get("require_low_quality_signal") and not _row_has_low_quality_signal(row):
        failures.append(EvalFailure("row_low_quality", f"{label} did not include low-quality improvement evidence."))
    return failures


def _row_has_utilities(row: dict[str, Any]) -> bool:
    value = _row_value(row, "utilities")
    if utility_labels(value):
        return True
    return bool(str(value or "").strip())


def _row_has_low_quality_signal(row: dict[str, Any]) -> bool:
    haystack = _row_text(
        row,
        [
            "quality_codes",
            "imprv_det_class_cd",
            "improvement_class_codes",
            "primary_building_style",
            "primary_construction_style",
            "match_reasons",
            "ai_match_reasons",
        ],
    )
    return bool(re.search(r"\b(MSL|LOW|SUB\s*STAN|CLASS\s*2)\b", haystack, re.IGNORECASE))


def _row_quality_codes(row: dict[str, Any]) -> set[str]:
    haystack = _row_text(
        row,
        [
            "quality_codes",
            "quality_code",
            "imprv_det_class_cd",
            "improvement_class_codes",
        ],
    )
    return {token.upper() for token in re.findall(r"\bMS(?:L|F|A|G|VG|E)\+?\b", haystack, re.IGNORECASE)}


def _row_land_use_code(row: dict[str, Any]) -> str:
    direct = str(_row_value(row, "land_use_code") or "").strip()
    if direct:
        return direct
    for key in ("land_use", "current_use"):
        value = str(_row_value(row, key) or "").strip()
        match = re.match(r"^\((\d+)\)", value)
        if match:
            return match.group(1)
    return ""


def _row_contains_any(row: dict[str, Any], terms: list[str]) -> bool:
    haystack = _row_text(
        row,
        [
            "location",
            "city",
            "situs_city_state_zip",
            "city_name",
        ],
    ).replace("-", " ")
    return any(term.lower().replace("-", " ") in haystack for term in terms)


def _row_zoning_contains_any(row: dict[str, Any], terms: list[str]) -> bool:
    haystack = _row_text(
        row,
        [
            "zoning",
            "zone_name",
            "zoning_code_short",
            "zoning_label",
            "zoning_code",
            "waza_general",
            "comp_plan_lud",
        ],
    ).replace("-", " ")
    return any(term.lower().replace("-", " ") in haystack for term in terms)


def _row_searchable_text(row: dict[str, Any]) -> str:
    parcel_data = row.get("parcel_data") if isinstance(row.get("parcel_data"), dict) else {}
    return _stringify({**parcel_data, **row}).lower()


def _row_current_searchable_text(row: dict[str, Any]) -> str:
    return _row_text(
        row,
        [
            "owner",
            "owner_name",
            "location",
            "address",
            "situs_address",
            "city",
            "city_name",
            "land_use",
            "current_use",
            "zoning",
            "zone_name",
            "zoning_label",
            "waza_general",
            "comp_plan_lud",
            "risk_flags",
            "signal_labels",
            "ai_match_reasons",
            "match_reasons",
        ],
    )


def _row_has_match_reasons(row: dict[str, Any]) -> bool:
    values = [
        row.get("match_reasons"),
        row.get("ai_match_reasons"),
        row.get("signal_labels"),
        _row_value(row, "match_reasons"),
    ]
    return any(bool(value) for value in values)


def _row_has_geometry(row: dict[str, Any]) -> bool:
    if row.get("map_url"):
        return True
    if _row_value(row, "has_geometry") is True:
        return True
    lat = _number(_row_value(row, "gis_y"))
    lng = _number(_row_value(row, "gis_x"))
    return lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180


def _row_text(row: dict[str, Any], keys: list[str]) -> str:
    parcel_data = row.get("parcel_data") if isinstance(row.get("parcel_data"), dict) else {}
    values = []
    for key in keys:
        values.append(row.get(key))
        values.append(parcel_data.get(key))
    return " ".join(_stringify(value) for value in values if value not in (None, "")).lower()


def _row_value(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    parcel_data = row.get("parcel_data") if isinstance(row.get("parcel_data"), dict) else {}
    return parcel_data.get(key)


def _sample_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "parcel_number": row.get("parcel_number"),
        "location": row.get("location"),
        "current_use": row.get("current_use"),
        "acres": row.get("acres"),
        "zoning": row.get("zoning"),
        "risk_flags": row.get("risk_flags"),
        "signal_labels": row.get("signal_labels"),
    }


def _eval_extra_context(prompt: str) -> str:
    plan = _fallback_search_plan(prompt)
    return "\n\n".join(
        [
            "Prompt-specific intent guidance:",
            _intent_context(prompt),
            "",
            "Zoning MCP advisory context:",
            _zoning_mcp_context(prompt, plan),
        ]
    )


def _repair_payload(result: EvalCaseResult) -> dict[str, Any]:
    return {
        "case": {
            "id": result.case.id,
            "prompt": result.case.prompt,
            "notes": result.case.notes,
            "row_expectations": result.case.row_expectations,
        },
        "generated_sql": result.generated.sql if result.generated else "",
        "diagnostics": result.diagnostics,
        "failures": [failure.as_dict() for failure in result.failures],
        "sample_rows": [_sample_row(row) for row in result.filtered_rows[:8]],
        "schema_excerpt": schema_reference_text()[:5000],
        "code_reference_excerpt": code_reference_text()[:4000],
        "ontology_excerpt": ontology_reference_text()[:6000],
        "zoning_mcp_excerpt": zoning_mcp_reference_text()[:7000],
    }


def _repair_instructions() -> str:
    return """
You are reviewing OpenSkagit Opportunity AI Search eval failures.
Return only compact JSON with keys: verdict, issues, likely_layer, suggested_tests, patch_proposal.
Do not claim a patch was applied. patch_proposal may be a unified-diff-style sketch or concise implementation notes.
Target only these layers: SQL-generation instructions, SQL validators, prompt/result filters, row hydration, eval expectations.
""".strip()


def _parse_repair_response(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(match.group(0)) if match else {}
    if not isinstance(parsed, dict):
        parsed = {}
    return {
        "verdict": str(parsed.get("verdict") or "unknown"),
        "issues": _string_list(parsed.get("issues")),
        "likely_layer": str(parsed.get("likely_layer") or ""),
        "suggested_tests": _string_list(parsed.get("suggested_tests")),
        "patch_proposal": str(parsed.get("patch_proposal") or ""),
    }


def _search_model() -> str:
    return os.environ.get("OPPORTUNITY_SEARCH_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _stringify(value: Any) -> str:
    if isinstance(value, list | tuple):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key}={val}" for key, val in value.items())
    return str(value)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped
