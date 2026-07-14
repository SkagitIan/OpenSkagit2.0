"""
Tests for the deterministic parts of regression/ai_reasoning.py --
apply_adjustment(), _feature_summary_stats(), build_segment_context().

propose_adjustment() itself (the live Claude API call) is not unit tested
here -- it requires network access and a real ANTHROPIC_API_KEY, verified
live instead, same approach used for the SQL aggregation functions in
regression/pipeline.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from regression import ai_reasoning
from regression.ratio_study import FEATURE_COLUMNS


def _sample_train_df(n: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({col: rng.uniform(0, 10, n) for col in FEATURE_COLUMNS})
    df["sale_price"] = rng.uniform(100_000, 900_000, n)
    return df


class ApplyAdjustmentTests(SimpleTestCase):
    def test_feature_addition_appends_known_column(self):
        base_features = ["primary_living_area"]
        adjustment = {"action": "adjust_features", "feature_additions": ["total_land_acres"], "feature_removals": []}
        columns, train, test, alpha = ai_reasoning.apply_adjustment(adjustment, base_features, _sample_train_df(), _sample_train_df())
        self.assertIn("total_land_acres", columns)
        self.assertIn("primary_living_area", columns)

    def test_unknown_feature_addition_ignored(self):
        base_features = ["primary_living_area"]
        adjustment = {"action": "adjust_features", "feature_additions": ["not_a_real_column"], "feature_removals": []}
        columns, train, test, alpha = ai_reasoning.apply_adjustment(adjustment, base_features, _sample_train_df(), _sample_train_df())
        self.assertNotIn("not_a_real_column", columns)

    def test_feature_removal_drops_column(self):
        base_features = ["primary_living_area", "total_land_acres"]
        adjustment = {"action": "adjust_features", "feature_additions": [], "feature_removals": ["total_land_acres"]}
        columns, train, test, alpha = ai_reasoning.apply_adjustment(adjustment, base_features, _sample_train_df(), _sample_train_df())
        self.assertEqual(columns, ["primary_living_area"])

    def test_removing_every_feature_falls_back_to_original(self):
        base_features = ["primary_living_area"]
        adjustment = {"action": "adjust_features", "feature_additions": [], "feature_removals": ["primary_living_area"]}
        columns, train, test, alpha = ai_reasoning.apply_adjustment(adjustment, base_features, _sample_train_df(), _sample_train_df())
        self.assertEqual(columns, base_features)

    def test_outlier_trim_removes_extreme_prices(self):
        train_df = pd.DataFrame({"sale_price": [100_000.0] * 18 + [5_000_000.0, 10_000_000.0]})
        for col in FEATURE_COLUMNS:
            train_df[col] = 1.0
        adjustment = {
            "action": "exclude_outliers",
            "feature_additions": [],
            "feature_removals": [],
            "outlier_exclude_above_percentile": 90,
        }
        columns, adjusted_train, test, alpha = ai_reasoning.apply_adjustment(adjustment, FEATURE_COLUMNS, train_df, train_df)
        self.assertLess(len(adjusted_train), len(train_df))
        self.assertNotIn(10_000_000.0, adjusted_train["sale_price"].values)

    def test_outlier_trim_that_would_remove_almost_everything_is_ignored(self):
        train_df = pd.DataFrame({"sale_price": [100_000.0] * 4 + [5_000_000.0]})
        for col in FEATURE_COLUMNS:
            train_df[col] = 1.0
        adjustment = {
            "action": "exclude_outliers",
            "feature_additions": [],
            "feature_removals": [],
            "outlier_exclude_below_percentile": 99,
        }
        columns, adjusted_train, test, alpha = ai_reasoning.apply_adjustment(adjustment, FEATURE_COLUMNS, train_df, train_df)
        # trimming to <5 rows is rejected -- falls back to the untrimmed frame
        self.assertEqual(len(adjusted_train), len(train_df))

    def test_ridge_alpha_passed_through(self):
        adjustment = {"action": "try_alpha", "feature_additions": [], "feature_removals": [], "ridge_alpha": 250.0}
        columns, train, test, alpha = ai_reasoning.apply_adjustment(adjustment, FEATURE_COLUMNS, _sample_train_df(), _sample_train_df())
        self.assertEqual(alpha, 250.0)


class FeatureSummaryStatsTests(SimpleTestCase):
    def test_reports_mean_std_and_missing_pct(self):
        df = pd.DataFrame({"primary_living_area": [1000.0, 2000.0, None]})
        stats = ai_reasoning._feature_summary_stats(df, ["primary_living_area"])
        self.assertAlmostEqual(stats["primary_living_area"]["mean"], 1500.0)
        self.assertAlmostEqual(stats["primary_living_area"]["pct_missing"], 33.3, places=1)

    def test_all_missing_column_reports_none_mean(self):
        df = pd.DataFrame({"primary_living_area": [None, None]})
        stats = ai_reasoning._feature_summary_stats(df, ["primary_living_area"])
        self.assertIsNone(stats["primary_living_area"]["mean"])
        self.assertEqual(stats["primary_living_area"]["pct_missing"], 100.0)


class BuildSegmentContextTests(SimpleTestCase):
    def test_context_is_json_shaped_and_includes_prior_rounds(self):
        train_df = _sample_train_df()
        test_df = train_df.copy()
        test_df["saleid"] = "S1"
        test_df["parcel_number"] = "P1"
        test_df["sale_date"] = "2024-01-01"
        ladder_results = [{"attempt_kind": "mechanical_ridge", "metrics": {"cod": 20.0}, "passed": False, "predicted": test_df["sale_price"]}]

        context = ai_reasoning.build_segment_context(
            segment_value="100",
            sample_count=18,
            train_df=train_df,
            test_df=test_df,
            feature_columns=FEATURE_COLUMNS,
            ladder_results=ladder_results,
            prior_ai_rounds=[{"action": "try_alpha", "ridge_alpha": 5.0}],
        )

        self.assertEqual(context["segment_value"], "100")
        self.assertEqual(context["sample_count"], 18)
        self.assertEqual(len(context["prior_ai_rounds_this_segment"]), 1)
        self.assertIn("mechanical_ladder_attempts", context)
