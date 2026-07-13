"""
Baseline models and ratio-study metrics for the SFR sales dataset.

Four deliberately simple baseline models, all evaluated on the same fixed
80/20 train/test split (seed=42, no leakage -- every fitted statistic,
imputer, and regression is fit on train only and applied to test):

1. assessed_value       -- the existing assessed value (or total market value
                            if assessed value is missing), no fitting at all.
2. price_per_sqft       -- median $/sqft per neighborhood_code, learned on
                            train, applied to test's living area.
3. linear_regression    -- OLS on log(sale_price).
4. ridge_regression     -- Ridge on log(sale_price).

This is a baseline, not a compliance tool -- no IAAO conformance claim is
made anywhere in this module or its output.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import train_test_split

RANDOM_SEED = 42
TEST_SIZE = 0.2

FEATURE_COLUMNS = [
    "primary_living_area",
    "total_land_acres",
    "age_at_sale",
    "has_garage",
    "has_fireplace",
    "has_basement",
    "distance_to_nearest_road_miles",
    "distance_to_nearest_city_miles",
]

CITY_ANCHOR_COLUMNS = [
    "distance_to_mount_vernon_miles",
    "distance_to_burlington_miles",
    "distance_to_sedro_woolley_miles",
    "distance_to_anacortes_miles",
    "distance_to_la_conner_miles",
]

GROUP_COLUMNS = [
    "neighborhood_code",
    "city_name",
    "comp_plan_designation",
    "school_district",
    "sale_year",
    "sale_price_decile",
]

# IAAO ratio-study sample-size bands (brief's exact thresholds).
SAMPLE_BAND_NORMAL = "normal"
SAMPLE_BAND_PROVISIONAL = "provisional_low_sample"
SAMPLE_BAND_INSUFFICIENT = "insufficient_sample"


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer the small, simple feature set the two regressions use."""
    df = df.copy()
    year_built = df["primary_actual_year_built"].fillna(df["primary_effective_year_built"])
    df["age_at_sale"] = (df["sale_year"] - year_built).clip(lower=0)
    df["distance_to_nearest_city_miles"] = df[CITY_ANCHOR_COLUMNS].min(axis=1)
    for flag in ("has_garage", "has_fireplace", "has_basement"):
        df[flag] = df[flag].fillna(False).astype(int)
    df["sale_price_decile"] = pd.qcut(df["sale_price"], 10, labels=False, duplicates="drop")
    return df


def split_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fixed 80/20 split, fixed seed. Nothing about test rows informs train fitting downstream."""
    return train_test_split(df, test_size=TEST_SIZE, random_state=RANDOM_SEED)


# ----------------------------------------------------------------------
# Baseline models
# ----------------------------------------------------------------------

def predict_assessed_value(train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
    """Baseline 1: the existing assessed value (falls back to total market value)."""
    return test_df["assessed_value"].fillna(test_df["total_market_value"])


def predict_price_per_sqft(train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
    """Baseline 2: median $/sqft per neighborhood, learned on train only."""
    train = train_df[train_df["primary_living_area"] > 0].copy()
    train["price_per_sqft"] = train["sale_price"] / train["primary_living_area"]
    overall_median = train["price_per_sqft"].median()
    by_neighborhood = train.groupby("neighborhood_code")["price_per_sqft"].median()
    rate = test_df["neighborhood_code"].map(by_neighborhood).fillna(overall_median)
    return rate * test_df["primary_living_area"]


def _fit_predict_log_price(model, train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
    imputer = SimpleImputer(strategy="median")
    x_train = imputer.fit_transform(train_df[FEATURE_COLUMNS])
    x_test = imputer.transform(test_df[FEATURE_COLUMNS])
    model.fit(x_train, train_df["log_sale_price"])
    predicted_log_price = model.predict(x_test)
    return pd.Series(np.exp(predicted_log_price), index=test_df.index)


def predict_linear_regression(train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
    """Baseline 3: OLS on log(sale_price). No Duan smearing correction on the back-transform -- documented simplification for this first baseline."""
    return _fit_predict_log_price(LinearRegression(), train_df, test_df)


def predict_ridge_regression(train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
    """Baseline 4: Ridge (alpha=1.0) on log(sale_price)."""
    return _fit_predict_log_price(Ridge(alpha=1.0, random_state=RANDOM_SEED), train_df, test_df)


MODELS = {
    "assessed_value": predict_assessed_value,
    "price_per_sqft": predict_price_per_sqft,
    "linear_regression": predict_linear_regression,
    "ridge_regression": predict_ridge_regression,
}


# ----------------------------------------------------------------------
# Ratio-study metrics
# ----------------------------------------------------------------------

def sample_band(n: int) -> str:
    if n >= 30:
        return SAMPLE_BAND_NORMAL
    if n >= 15:
        return SAMPLE_BAND_PROVISIONAL
    return SAMPLE_BAND_INSUFFICIENT


def compute_ratio_metrics(predicted: pd.Series, actual: pd.Series) -> dict:
    """
    Standard ratio-study metrics. ratio = predicted / actual.

    PRB (Price-Related Bias) follows the IAAO Standard on Ratio Studies (2013)
    definition: regress (ratio - median_ratio) / median_ratio on
    log2[(predicted / median_ratio + actual) / 2]. The regression slope is
    PRB; IAAO's informal acceptable range is roughly [-0.05, 0.05]. This is a
    baseline implementation, not an IAAO-compliance claim.
    """
    valid = predicted.notna() & actual.notna() & (actual > 0)
    predicted = predicted[valid]
    actual = actual[valid]
    n = len(predicted)
    if n == 0:
        return {"sale_count": 0}

    ratio = predicted / actual
    median_ratio = float(ratio.median())
    mean_ratio = float(ratio.mean())
    weighted_mean_ratio = float(predicted.sum() / actual.sum())

    cod = float((ratio - median_ratio).abs().mean() / median_ratio * 100) if median_ratio else np.nan
    prd = float(mean_ratio / weighted_mean_ratio) if weighted_mean_ratio else np.nan

    prb = _compute_prb(ratio, predicted, actual, median_ratio)

    pct_error = (predicted - actual).abs() / actual
    rmse = float(np.sqrt(((predicted - actual) ** 2).mean()))

    return {
        "sale_count": n,
        "sample_band": sample_band(n),
        "median_ratio": median_ratio,
        "mean_ratio": mean_ratio,
        "weighted_mean_ratio": weighted_mean_ratio,
        "cod": cod,
        "prd": prd,
        "prb": prb,
        "median_ape": float(pct_error.median() * 100),
        "mean_ape": float(pct_error.mean() * 100),
        "rmse": rmse,
        "ratio_p10": float(ratio.quantile(0.10)),
        "ratio_p25": float(ratio.quantile(0.25)),
        "ratio_p75": float(ratio.quantile(0.75)),
        "ratio_p90": float(ratio.quantile(0.90)),
        "pct_within_10": float((pct_error <= 0.10).mean() * 100),
        "pct_within_15": float((pct_error <= 0.15).mean() * 100),
        "pct_within_20": float((pct_error <= 0.20).mean() * 100),
    }


def _compute_prb(ratio: pd.Series, predicted: pd.Series, actual: pd.Series, median_ratio: float) -> float | None:
    if median_ratio <= 0 or len(ratio) < 5:
        return None
    value_estimate = 0.5 * (predicted / median_ratio) + 0.5 * actual
    value_estimate = value_estimate[value_estimate > 0]
    if len(value_estimate) < 5:
        return None
    independent = np.log2(value_estimate.loc[value_estimate.index])
    dependent = ((ratio - median_ratio) / median_ratio).loc[value_estimate.index]
    x = independent.values
    y = dependent.values
    x_mean, y_mean = x.mean(), y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        return None
    slope = ((x - x_mean) * (y - y_mean)).sum() / denom
    return float(slope)


def grouped_ratio_report(test_df: pd.DataFrame, predicted: pd.Series, group_col: str) -> pd.DataFrame:
    """Ratio-study metrics for every value of ``group_col``, with sample-size banding."""
    rows = []
    frame = test_df.assign(_predicted=predicted)
    for group_value, group_frame in frame.groupby(group_col, dropna=False):
        metrics = compute_ratio_metrics(group_frame["_predicted"], group_frame["sale_price"])
        metrics["group"] = group_value
        rows.append(metrics)
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    columns = ["group"] + [col for col in result.columns if col != "group"]
    return result[columns].sort_values("sale_count", ascending=False)


def top_prediction_misses(test_df: pd.DataFrame, predicted: pd.Series, n: int = 15) -> dict:
    """The most under/over-predicted sales for a model, for the report's spot-check section."""
    frame = test_df.assign(predicted=predicted)
    frame = frame[frame["predicted"].notna() & (frame["sale_price"] > 0)]
    frame["ratio"] = frame["predicted"] / frame["sale_price"]
    columns = ["saleid", "parcel_number", "sale_date", "sale_price", "predicted", "ratio"]
    underpredicted = frame.nsmallest(n, "ratio")[columns].to_dict("records")
    overpredicted = frame.nlargest(n, "ratio")[columns].to_dict("records")
    return {"underpredicted": underpredicted, "overpredicted": overpredicted}
