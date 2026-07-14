"""
Per-neighborhood try-then-drop orchestration for run_neighborhood_compliance_loop.

For every neighborhood, independent of every other neighborhood:

1. Always attempt the mechanical ladder once (compliance.run_mechanical_ladder),
   regardless of sample size -- this is the "try" in "try then drop."
2. If it passes: status is `compliant` (sample_count >= 30) or `provisional`
   (15 <= sample_count < 30). Done.
3. If it doesn't pass and sample_count < 15: drop immediately. No AI call is
   spent on a segment with no realistic path to a trustworthy fit.
4. If it doesn't pass and sample_count >= 15: hand off to a bounded AI-guided
   loop (ai_reasoning.py, up to MAX_AI_ROUNDS rounds). Drop if still failing
   after that, with the AI's own rationale as the recommendation.

No segment is ever merged into a city or countywide model -- a dropped
neighborhood is dropped, not rolled up into something broader.
"""

from __future__ import annotations

import logging

import pandas as pd
from sklearn.model_selection import train_test_split

from . import ai_reasoning, compliance
from .ratio_study import FEATURE_COLUMNS, RANDOM_SEED, TEST_SIZE

logger = logging.getLogger(__name__)

STATUS_COMPLIANT = "compliant"
STATUS_PROVISIONAL = "provisional"
STATUS_DROPPED = "dropped"

MIN_SAMPLE_TO_ATTEMPT_AI = 15
MIN_TOTAL_SAMPLE_TO_SPLIT = 5
COMPLIANT_SAMPLE_THRESHOLD = 30


def run_segment(segment_value: str, segment_df: pd.DataFrame) -> dict:
    """
    Run the full try-then-drop loop for one neighborhood's recent-window sales.

    Returns a dict with: segment_value, status, sample_count, model_name,
    coefficients, feature_medians, metrics, recommendation, attempts_made,
    and `experiments` -- a list of per-attempt dicts ready to become
    SFRSegmentExperiment rows.
    """
    sample_count = len(segment_df)
    experiments: list[dict] = []

    if sample_count < MIN_TOTAL_SAMPLE_TO_SPLIT:
        return _dropped_result(
            segment_value,
            sample_count,
            experiments,
            recommendation=f"Insufficient sample (n={sample_count}), too few sales to fit or evaluate a model.",
        )

    train_df, test_df = train_test_split(segment_df, test_size=TEST_SIZE, random_state=RANDOM_SEED)
    feature_columns = list(FEATURE_COLUMNS)

    try:
        ladder_results = compliance.run_mechanical_ladder(train_df, test_df, feature_columns=feature_columns)
    except Exception:
        logger.exception("Mechanical ladder failed to fit for segment %s", segment_value)
        return _dropped_result(
            segment_value, sample_count, experiments,
            recommendation="Model fitting failed (numerical error) -- see server logs.",
        )

    for i, result in enumerate(ladder_results, start=1):
        experiments.append(_experiment_row(result, attempt_number=i, train_count=len(train_df), test_count=len(test_df)))

    best = ladder_results[-1]
    if best["passed"]:
        return _passed_result(segment_value, sample_count, best, experiments, model_label=best["attempt_kind"])

    if sample_count < MIN_SAMPLE_TO_ATTEMPT_AI:
        return _dropped_result(
            segment_value,
            sample_count,
            experiments,
            recommendation=f"Insufficient sample (n={sample_count}, minimum {MIN_SAMPLE_TO_ATTEMPT_AI} to attempt further tuning).",
        )

    return _run_ai_guided_rounds(segment_value, sample_count, train_df, test_df, feature_columns, ladder_results, experiments)


def _run_ai_guided_rounds(
    segment_value: str,
    sample_count: int,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    ladder_results: list[dict],
    experiments: list[dict],
) -> dict:
    prior_ai_rounds: list[dict] = []
    current_train, current_test, current_features = train_df, test_df, feature_columns
    last_rationale = ""

    for round_number in range(1, ai_reasoning.MAX_AI_ROUNDS + 1):
        context = ai_reasoning.build_segment_context(
            segment_value=segment_value,
            sample_count=sample_count,
            train_df=current_train,
            test_df=current_test,
            feature_columns=current_features,
            ladder_results=ladder_results,
            prior_ai_rounds=prior_ai_rounds,
        )
        try:
            adjustment = ai_reasoning.propose_adjustment(context)
        except Exception:
            logger.exception("AI-guided round %d failed for segment %s", round_number, segment_value)
            last_rationale = f"AI reasoning unavailable after {round_number - 1} round(s); stopped without a pass."
            break

        prior_ai_rounds.append(adjustment)
        last_rationale = adjustment.get("rationale", "")

        if adjustment.get("action") == ai_reasoning.ACTION_DROP:
            break

        current_features, current_train, current_test, extra_alpha = ai_reasoning.apply_adjustment(
            adjustment, current_features, current_train, current_test
        )

        try:
            if extra_alpha is not None:
                round_attempts = [compliance.attempt_ridge(current_train, current_test, feature_columns=current_features, alpha=extra_alpha)]
            else:
                round_attempts = compliance.run_mechanical_ladder(current_train, current_test, feature_columns=current_features)
        except Exception:
            logger.exception("AI-guided refit failed for segment %s (round %d)", segment_value, round_number)
            last_rationale = f"AI-proposed adjustment could not be fit (round {round_number}); stopped."
            break

        passed_attempt = None
        for attempt in round_attempts:
            experiments.append(_experiment_row(
                attempt,
                attempt_number=len(experiments) + 1,
                train_count=len(current_train),
                test_count=len(current_test),
                is_ai_guided=True,
                ai_rationale=last_rationale,
            ))
            if attempt["passed"]:
                passed_attempt = attempt
                break

        if passed_attempt is not None:
            return _passed_result(
                segment_value, sample_count, passed_attempt, experiments,
                model_label=f"ai_guided_round_{round_number}:{passed_attempt['attempt_kind']}",
                ai_calls_made=len(prior_ai_rounds),
            )

    recommendation = last_rationale or f"No adjustment cleared thresholds after {len(prior_ai_rounds)} AI-guided round(s)."
    return _dropped_result(segment_value, sample_count, experiments, recommendation=recommendation, ai_calls_made=len(prior_ai_rounds))


def _experiment_row(result: dict, attempt_number: int, train_count: int, test_count: int, is_ai_guided: bool = False, ai_rationale: str = "") -> dict:
    return {
        "attempt_kind": "ai_guided" if is_ai_guided else result["attempt_kind"],
        "attempt_number": attempt_number,
        "train_count": train_count,
        "test_count": test_count,
        "metrics": result["metrics"],
        "passed": result["passed"],
        "coefficients": result["coefficients"],
        "ai_rationale": ai_rationale,
    }


def _passed_result(segment_value: str, sample_count: int, result: dict, experiments: list[dict], model_label: str, ai_calls_made: int = 0) -> dict:
    status = STATUS_COMPLIANT if sample_count >= COMPLIANT_SAMPLE_THRESHOLD else STATUS_PROVISIONAL
    band_note = "" if status == STATUS_COMPLIANT else f" (provisional -- n={sample_count})"
    return {
        "segment_value": segment_value,
        "status": status,
        "sample_count": sample_count,
        "model_name": model_label,
        "coefficients": result["coefficients"],
        "feature_medians": result["feature_medians"],
        "metrics": result["metrics"],
        "recommendation": f"{model_label} -- passes all thresholds{band_note}.",
        "attempts_made": len(experiments),
        "ai_calls_made": ai_calls_made,
        "experiments": experiments,
    }


def _dropped_result(segment_value: str, sample_count: int, experiments: list[dict], recommendation: str, ai_calls_made: int = 0) -> dict:
    return {
        "segment_value": segment_value,
        "status": STATUS_DROPPED,
        "sample_count": sample_count,
        "model_name": "",
        "coefficients": None,
        "feature_medians": None,
        "metrics": experiments[-1]["metrics"] if experiments else {},
        "recommendation": recommendation,
        "attempts_made": len(experiments),
        "ai_calls_made": ai_calls_made,
        "experiments": experiments,
    }
