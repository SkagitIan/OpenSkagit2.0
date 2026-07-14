"""
Claude-powered reasoning step for the per-neighborhood compliance loop.

When the mechanical model ladder (regression/compliance.py) fails to clear
IAAO reference thresholds for a segment with a large enough sample to be
worth the extra attempts, this module asks Claude to propose ONE concrete,
bounded adjustment -- it never fits a model or writes/executes code itself.
The deterministic pipeline (regression/segment_loop.py) applies whatever
adjustment comes back and re-evaluates with the same ratio-study metrics
used everywhere else in this app.

Uses the Anthropic SDK directly (client.messages.create), not the OpenAI
integration already used elsewhere in this codebase (opportunity/ai_search.py)
-- a separate, new provider dependency for this specific reasoning step, per
explicit request. Requires ANTHROPIC_API_KEY and the `anthropic` package.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .ratio_study import FEATURE_COLUMNS, top_prediction_misses

AI_MODEL = os.environ.get("REGRESSION_AI_MODEL", "claude-sonnet-5")
MAX_AI_ROUNDS = int(os.environ.get("REGRESSION_AI_MAX_ROUNDS", "3"))

ACTION_ADJUST_FEATURES = "adjust_features"
ACTION_EXCLUDE_OUTLIERS = "exclude_outliers"
ACTION_TRY_ALPHA = "try_alpha"
ACTION_DROP = "drop"

# The AI's action space is fully enumerated and mechanically applied -- it
# never gets to write or execute arbitrary code, only pick among these.
_ADJUSTMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [ACTION_ADJUST_FEATURES, ACTION_EXCLUDE_OUTLIERS, ACTION_TRY_ALPHA, ACTION_DROP],
            "description": "Which single adjustment to try next, or 'drop' to stop and recommend dropping this segment.",
        },
        "feature_additions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Feature column names to add to the fit, from the provided available-features list. Empty if not applicable.",
        },
        "feature_removals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Feature column names to drop from the current fit. Empty if not applicable.",
        },
        "outlier_exclude_below_percentile": {
            "type": ["number", "null"],
            "description": "Drop training sales with sale_price below this percentile (0-100). Null if not applicable.",
        },
        "outlier_exclude_above_percentile": {
            "type": ["number", "null"],
            "description": "Drop training sales with sale_price above this percentile (0-100). Null if not applicable.",
        },
        "ridge_alpha": {
            "type": ["number", "null"],
            "description": "A specific ridge alpha value to try (outside the standard grid). Null if not applicable.",
        },
        "rationale": {
            "type": "string",
            "description": "One or two sentences explaining the reasoning behind this proposal, or why the segment should be dropped.",
        },
    },
    "required": [
        "action",
        "feature_additions",
        "feature_removals",
        "outlier_exclude_below_percentile",
        "outlier_exclude_above_percentile",
        "ridge_alpha",
        "rationale",
    ],
    "additionalProperties": False,
}


def _feature_summary_stats(df: pd.DataFrame, feature_columns: list[str]) -> dict:
    stats = {}
    for col in feature_columns:
        series = df[col]
        stats[col] = {
            "mean": None if series.dropna().empty else round(float(series.mean()), 3),
            "std": None if series.dropna().empty else round(float(series.std()), 3),
            "pct_missing": round(float(series.isna().mean() * 100), 1),
        }
    return stats


def build_segment_context(
    segment_value: str,
    sample_count: int,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    ladder_results: list[dict],
    prior_ai_rounds: list[dict],
) -> dict:
    """Assemble the JSON-able context sent to Claude for one segment's AI-guided round."""
    last_attempt = ladder_results[-1]
    misses = {}
    if last_attempt.get("predicted") is not None:
        try:
            misses = top_prediction_misses(test_df, last_attempt["predicted"], n=5)
        except KeyError:
            # top_prediction_misses expects saleid/parcel_number/sale_date --
            # supplementary context for the AI prompt, so skip rather than fail.
            misses = {}

    return {
        "segment_value": segment_value,
        "sample_count": sample_count,
        "available_features": FEATURE_COLUMNS,
        "current_feature_columns": feature_columns,
        "feature_summary_stats": _feature_summary_stats(train_df, feature_columns),
        "mechanical_ladder_attempts": [
            {"attempt_kind": r["attempt_kind"], "metrics": r["metrics"], "passed": r["passed"]}
            for r in ladder_results
        ],
        "top_prediction_misses": misses,
        "prior_ai_rounds_this_segment": prior_ai_rounds,
    }


def _prompt_for_context(context: dict) -> str:
    return f"""
You are reasoning about why a home-price ridge/lasso regression model failed to clear IAAO ratio-study
reference thresholds (COD in [5, 15], PRD in [0.98, 1.03], PRB in [-0.05, 0.05]) for one neighborhood
segment of a Skagit County, WA property assessment dataset.

Segment context (JSON):
{json.dumps(context, sort_keys=True, default=str)}

Propose exactly ONE adjustment to try next: add/remove features (only from `available_features`),
exclude price outliers by percentile, try a specific ridge alpha, or recommend dropping this segment if
you believe it has no realistic path to passing (e.g. sample too thin, repeated attempts already failed
for the same underlying reason, or the segment appears to be a genuine statistical edge case).

Do not propose the same adjustment as a prior round in `prior_ai_rounds_this_segment`. Be specific and
grounded in the actual metrics and feature stats provided -- do not guess generically.
""".strip()


def _anthropic_client():
    import anthropic

    return anthropic.Anthropic()


def propose_adjustment(context: dict) -> dict:
    """
    Calls Claude with the segment's context and returns one structured
    adjustment proposal. Raises on API failure -- callers should treat that
    as "AI unavailable this round" and fail safe (drop or stop early), never
    silently force a pass.
    """
    client = _anthropic_client()
    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=1500,
        output_config={"format": {"type": "json_schema", "schema": _ADJUSTMENT_SCHEMA}},
        messages=[{"role": "user", "content": _prompt_for_context(context)}],
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def apply_adjustment(
    adjustment: dict,
    feature_columns: list[str],
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[list[str], pd.DataFrame, pd.DataFrame, float | None]:
    """
    Mechanically applies an AI-proposed adjustment. Returns
    (adjusted_feature_columns, adjusted_train_df, adjusted_test_df, extra_ridge_alpha).
    Never executes anything the AI wrote -- only toggles from the fixed,
    known feature list, trims by percentile, or passes through a numeric
    alpha value.
    """
    columns = list(feature_columns)
    for col in adjustment.get("feature_additions") or []:
        if col in FEATURE_COLUMNS and col not in columns:
            columns.append(col)
    for col in adjustment.get("feature_removals") or []:
        if col in columns:
            columns.remove(col)
    if not columns:
        columns = list(feature_columns)

    adjusted_train = train_df
    low = adjustment.get("outlier_exclude_below_percentile")
    high = adjustment.get("outlier_exclude_above_percentile")
    if low is not None or high is not None:
        prices = train_df["sale_price"]
        lower_bound = prices.quantile(low / 100) if low is not None else -np.inf
        upper_bound = prices.quantile(high / 100) if high is not None else np.inf
        trimmed = train_df[(prices >= lower_bound) & (prices <= upper_bound)]
        if len(trimmed) >= 5:
            adjusted_train = trimmed

    ridge_alpha = adjustment.get("ridge_alpha")
    return columns, adjusted_train, test_df, ridge_alpha
