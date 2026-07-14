"""
Tests for regression/compliance.py -- all pure pandas/numpy/sklearn, no
database.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from regression import compliance
from regression.ratio_study import FEATURE_COLUMNS


class MetricsPassTests(SimpleTestCase):
    def test_all_in_range_passes(self):
        self.assertTrue(compliance.metrics_pass({"cod": 10.0, "prd": 1.0, "prb": 0.0}))

    def test_cod_out_of_range_fails(self):
        self.assertFalse(compliance.metrics_pass({"cod": 20.0, "prd": 1.0, "prb": 0.0}))

    def test_prd_out_of_range_fails(self):
        self.assertFalse(compliance.metrics_pass({"cod": 10.0, "prd": 1.10, "prb": 0.0}))

    def test_prb_out_of_range_fails(self):
        self.assertFalse(compliance.metrics_pass({"cod": 10.0, "prd": 1.0, "prb": 0.10}))

    def test_boundary_values_pass(self):
        self.assertTrue(compliance.metrics_pass({"cod": 5.0, "prd": 0.98, "prb": -0.05}))
        self.assertTrue(compliance.metrics_pass({"cod": 15.0, "prd": 1.03, "prb": 0.05}))

    def test_missing_metric_fails(self):
        self.assertFalse(compliance.metrics_pass({"cod": 10.0, "prd": 1.0}))
        self.assertFalse(compliance.metrics_pass({}))

    def test_none_prb_fails(self):
        # _compute_prb returns None for very small/degenerate test sets.
        self.assertFalse(compliance.metrics_pass({"cod": 10.0, "prd": 1.0, "prb": None}))

    def test_nan_metric_fails(self):
        self.assertFalse(compliance.metrics_pass({"cod": float("nan"), "prd": 1.0, "prb": 0.0}))


def _synthetic_segment(n: int, seed: int = 0) -> pd.DataFrame:
    """A segment-sized frame with a real linear relationship so a ridge/lasso
    fit can actually pass metrics_pass, for the ladder-stops-at-first-pass test."""
    rng = np.random.default_rng(seed)
    living_area = rng.uniform(900, 3000, n)
    land_acres = rng.uniform(0.1, 2.0, n)
    age = rng.uniform(0, 80, n)
    log_price = 10.5 + 0.0006 * living_area - 0.01 * age + rng.normal(0, 0.02, n)

    df = pd.DataFrame(
        {
            "primary_living_area": living_area,
            "total_land_acres": land_acres,
            "age_at_sale": age,
            "has_garage": rng.integers(0, 2, n),
            "has_fireplace": rng.integers(0, 2, n),
            "has_basement": rng.integers(0, 2, n),
            "distance_to_nearest_road_miles": rng.uniform(0, 2, n),
            "distance_to_nearest_city_miles": rng.uniform(0, 20, n),
        }
    )
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0
    df["log_sale_price"] = log_price
    df["sale_price"] = np.exp(log_price)
    return df


class RunMechanicalLadderTests(SimpleTestCase):
    def test_stops_at_first_pass(self):
        train_df = _synthetic_segment(120, seed=1)
        test_df = _synthetic_segment(40, seed=2)

        results = compliance.run_mechanical_ladder(train_df, test_df)

        self.assertGreaterEqual(len(results), 1)
        # Whichever attempt is last, if any passed it must be the last one logged.
        if any(r["passed"] for r in results):
            self.assertTrue(results[-1]["passed"])

    def test_every_attempt_has_coefficients_and_metrics(self):
        train_df = _synthetic_segment(120, seed=3)
        test_df = _synthetic_segment(40, seed=4)

        results = compliance.run_mechanical_ladder(train_df, test_df)

        for result in results:
            self.assertIn("intercept", result["coefficients"])
            self.assertIn("sale_count", result["metrics"])
            self.assertEqual(result["metrics"]["sale_count"], 40)

    def test_custom_feature_columns_respected(self):
        train_df = _synthetic_segment(120, seed=5)
        test_df = _synthetic_segment(40, seed=6)
        reduced_features = ["primary_living_area", "age_at_sale"]

        result = compliance.attempt_ridge(train_df, test_df, feature_columns=reduced_features)

        self.assertEqual(set(result["feature_medians"].keys()), set(reduced_features))
        self.assertEqual(set(result["coefficients"].keys()) - {"intercept"}, set(reduced_features))
