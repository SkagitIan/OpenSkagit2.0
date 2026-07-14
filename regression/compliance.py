"""
Compliance thresholds and the coefficient-producing model ladder used by
``run_neighborhood_compliance_loop``.

The thresholds below are the reference ranges IAAO's Standard on Ratio
Studies commonly cites for single-family residential. Clearing them here
means a fitted model's metrics land in those numeric ranges -- it is not a
claim of formal IAAO compliance certification, same framing already used in
the existing baseline ratio-study reports.

Every model in the ladder produces plain linear coefficients (no tree-based
models) so a passing result can be exported as
``predicted_price = intercept + sum(coef_i * feature_i)`` without needing
scikit-learn at prediction time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Lasso, Ridge
from sklearn.model_selection import train_test_split

from .ratio_study import FEATURE_COLUMNS, RANDOM_SEED, compute_ratio_metrics

COD_RANGE = (5.0, 15.0)
PRD_RANGE = (0.98, 1.03)
PRB_RANGE = (-0.05, 0.05)

RIDGE_ALPHA_GRID = [0.1, 1.0, 10.0, 100.0]
# Deliberately small and unscaled, matching this codebase's existing
# unscaled-feature convention (ridge_regression in ratio_study.py also runs
# on raw feature units) -- a documented simplification, not an oversight.
LASSO_ALPHA = 0.001

ATTEMPT_RIDGE = "mechanical_ridge"
ATTEMPT_RIDGE_GRID = "mechanical_ridge_grid"
ATTEMPT_LASSO = "mechanical_lasso"

MECHANICAL_LADDER_ORDER = [ATTEMPT_RIDGE, ATTEMPT_RIDGE_GRID, ATTEMPT_LASSO]


def metrics_pass(metrics: dict) -> bool:
    """
    COD/PRD/PRB all within the IAAO reference ranges above. Sample size is a
    separate status tier (compliant/provisional/dropped), not checked here.
    """
    cod = metrics.get("cod")
    prd = metrics.get("prd")
    prb = metrics.get("prb")
    if cod is None or prd is None or prb is None:
        return False
    if pd.isna(cod) or pd.isna(prd) or pd.isna(prb):
        return False
    if not (COD_RANGE[0] <= cod <= COD_RANGE[1]):
        return False
    if not (PRD_RANGE[0] <= prd <= PRD_RANGE[1]):
        return False
    if not (PRB_RANGE[0] <= prb <= PRB_RANGE[1]):
        return False
    return True


def _fit_predict(model, train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str]):
    imputer = SimpleImputer(strategy="median")
    x_train = imputer.fit_transform(train_df[feature_columns])
    x_test = imputer.transform(test_df[feature_columns])
    model.fit(x_train, train_df["log_sale_price"])
    predicted_log_price = model.predict(x_test)
    predicted = pd.Series(np.exp(predicted_log_price), index=test_df.index)
    feature_medians = {col: float(val) for col, val in zip(feature_columns, imputer.statistics_)}
    coefficients = {col: float(coef) for col, coef in zip(feature_columns, model.coef_)}
    coefficients["intercept"] = float(model.intercept_)
    return predicted, coefficients, feature_medians


def _attempt_result(attempt_kind: str, predicted: pd.Series, test_df: pd.DataFrame, coefficients: dict, feature_medians: dict) -> dict:
    metrics = compute_ratio_metrics(predicted, test_df["sale_price"])
    return {
        "attempt_kind": attempt_kind,
        "metrics": metrics,
        "coefficients": coefficients,
        "feature_medians": feature_medians,
        "passed": metrics_pass(metrics),
        # In-memory only -- not part of the JSON `metrics` blob that gets
        # persisted, but useful for the AI-guided step to inspect misses
        # (see ratio_study.top_prediction_misses) without refitting.
        "predicted": predicted,
    }


def attempt_ridge(train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str] | None = None, alpha: float = 1.0) -> dict:
    feature_columns = feature_columns or FEATURE_COLUMNS
    predicted, coefficients, feature_medians = _fit_predict(
        Ridge(alpha=alpha, random_state=RANDOM_SEED), train_df, test_df, feature_columns
    )
    return _attempt_result(ATTEMPT_RIDGE, predicted, test_df, coefficients, feature_medians)


def attempt_ridge_grid(train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str] | None = None) -> dict:
    """
    Pick the ridge alpha with the lowest RMSE on a held-out slice of train
    (not full k-fold CV -- kept simple, matching how the countywide baseline
    was kept deliberately simple).
    """
    feature_columns = feature_columns or FEATURE_COLUMNS
    validation_train, validation_holdout = train_test_split(train_df, test_size=0.2, random_state=RANDOM_SEED)

    best_alpha = RIDGE_ALPHA_GRID[0]
    best_rmse = np.inf
    for alpha in RIDGE_ALPHA_GRID:
        try:
            predicted, _, _ = _fit_predict(Ridge(alpha=alpha, random_state=RANDOM_SEED), validation_train, validation_holdout, feature_columns)
        except ValueError:
            continue
        rmse = float(np.sqrt(((predicted - validation_holdout["sale_price"]) ** 2).mean()))
        if rmse < best_rmse:
            best_rmse = rmse
            best_alpha = alpha

    predicted, coefficients, feature_medians = _fit_predict(
        Ridge(alpha=best_alpha, random_state=RANDOM_SEED), train_df, test_df, feature_columns
    )
    result = _attempt_result(ATTEMPT_RIDGE_GRID, predicted, test_df, coefficients, feature_medians)
    result["metrics"]["ridge_alpha"] = best_alpha
    return result


def attempt_lasso(train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str] | None = None, alpha: float = LASSO_ALPHA) -> dict:
    feature_columns = feature_columns or FEATURE_COLUMNS
    predicted, coefficients, feature_medians = _fit_predict(
        Lasso(alpha=alpha, random_state=RANDOM_SEED, max_iter=10_000), train_df, test_df, feature_columns
    )
    return _attempt_result(ATTEMPT_LASSO, predicted, test_df, coefficients, feature_medians)


ATTEMPT_FUNCTIONS = {
    ATTEMPT_RIDGE: attempt_ridge,
    ATTEMPT_RIDGE_GRID: attempt_ridge_grid,
    ATTEMPT_LASSO: attempt_lasso,
}


def run_mechanical_ladder(train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str] | None = None) -> list[dict]:
    """
    Try ridge, then ridge-grid, then lasso, in order, stopping at the first
    pass. Returns every attempt made (1-3 results) so each can be logged as
    its own SFRSegmentExperiment row, pass or fail.
    """
    results = []
    for attempt_kind in MECHANICAL_LADDER_ORDER:
        result = ATTEMPT_FUNCTIONS[attempt_kind](train_df, test_df, feature_columns=feature_columns)
        results.append(result)
        if result["passed"]:
            break
    return results
