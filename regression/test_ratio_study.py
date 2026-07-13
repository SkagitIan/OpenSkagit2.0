"""
Tests for regression/ratio_study.py -- all pure pandas/numpy, no database.
"""

from __future__ import annotations

import pandas as pd
from django.test import SimpleTestCase

from regression import ratio_study


class RatioMetricsTests(SimpleTestCase):
    def test_perfect_predictions_give_ratio_one_and_zero_dispersion(self):
        actual = pd.Series([100_000.0, 200_000.0, 300_000.0, 400_000.0, 500_000.0])
        predicted = actual.copy()

        metrics = ratio_study.compute_ratio_metrics(predicted, actual)

        self.assertEqual(metrics["sale_count"], 5)
        self.assertAlmostEqual(metrics["median_ratio"], 1.0)
        self.assertAlmostEqual(metrics["mean_ratio"], 1.0)
        self.assertAlmostEqual(metrics["weighted_mean_ratio"], 1.0)
        self.assertAlmostEqual(metrics["cod"], 0.0)
        self.assertAlmostEqual(metrics["prd"], 1.0)
        self.assertAlmostEqual(metrics["rmse"], 0.0)
        self.assertAlmostEqual(metrics["pct_within_10"], 100.0)

    def test_systematic_overprediction_shows_in_ratio_and_prd(self):
        actual = pd.Series([100_000.0] * 10)
        predicted = actual * 1.05  # every prediction 5% high -- clear of the 10% boundary

        metrics = ratio_study.compute_ratio_metrics(predicted, actual)

        self.assertAlmostEqual(metrics["median_ratio"], 1.05)
        self.assertAlmostEqual(metrics["mean_ape"], 5.0)
        self.assertAlmostEqual(metrics["pct_within_10"], 100.0)
        self.assertAlmostEqual(metrics["pct_within_15"], 100.0)

    def test_empty_input_returns_zero_count(self):
        metrics = ratio_study.compute_ratio_metrics(pd.Series([], dtype=float), pd.Series([], dtype=float))
        self.assertEqual(metrics, {"sale_count": 0})

    def test_zero_or_negative_actual_excluded_from_metrics(self):
        actual = pd.Series([100_000.0, 0.0, -5000.0, 200_000.0])
        predicted = pd.Series([100_000.0, 50_000.0, 10_000.0, 200_000.0])

        metrics = ratio_study.compute_ratio_metrics(predicted, actual)

        self.assertEqual(metrics["sale_count"], 2)

    def test_sample_band_thresholds(self):
        self.assertEqual(ratio_study.sample_band(30), ratio_study.SAMPLE_BAND_NORMAL)
        self.assertEqual(ratio_study.sample_band(29), ratio_study.SAMPLE_BAND_PROVISIONAL)
        self.assertEqual(ratio_study.sample_band(15), ratio_study.SAMPLE_BAND_PROVISIONAL)
        self.assertEqual(ratio_study.sample_band(14), ratio_study.SAMPLE_BAND_INSUFFICIENT)
        self.assertEqual(ratio_study.sample_band(0), ratio_study.SAMPLE_BAND_INSUFFICIENT)


class PrepareFeaturesTests(SimpleTestCase):
    def _minimal_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "sale_year": [2020, 2021],
                "sale_price": [200_000.0, 900_000.0],
                "primary_actual_year_built": [1990.0, None],
                "primary_effective_year_built": [1990.0, 2000.0],
                "has_garage": [True, None],
                "has_fireplace": [None, True],
                "has_basement": [False, False],
                "distance_to_mount_vernon_miles": [1.0, 10.0],
                "distance_to_burlington_miles": [5.0, 2.0],
                "distance_to_sedro_woolley_miles": [8.0, 3.0],
                "distance_to_anacortes_miles": [15.0, 20.0],
                "distance_to_la_conner_miles": [3.0, 12.0],
            }
        )

    def test_age_at_sale_uses_actual_then_effective_year_built(self):
        result = ratio_study.prepare_features(self._minimal_df())
        self.assertEqual(result.loc[0, "age_at_sale"], 30)  # 2020 - 1990
        self.assertEqual(result.loc[1, "age_at_sale"], 21)  # falls back to effective 2000 -> 2021-2000

    def test_boolean_flags_filled_and_cast_to_int(self):
        result = ratio_study.prepare_features(self._minimal_df())
        self.assertEqual(result.loc[1, "has_garage"], 0)
        self.assertEqual(result.loc[0, "has_fireplace"], 0)

    def test_nearest_city_distance_is_min_of_anchors(self):
        result = ratio_study.prepare_features(self._minimal_df())
        self.assertAlmostEqual(result.loc[0, "distance_to_nearest_city_miles"], 1.0)
        self.assertAlmostEqual(result.loc[1, "distance_to_nearest_city_miles"], 2.0)


class GroupedRatioReportTests(SimpleTestCase):
    def test_groups_report_independently_with_sample_band(self):
        test_df = pd.DataFrame(
            {
                "sale_price": [100_000.0] * 40 + [200_000.0] * 10,
                "neighborhood_code": ["A"] * 40 + ["B"] * 10,
            }
        )
        predicted = test_df["sale_price"] * 1.0

        result = ratio_study.grouped_ratio_report(test_df, predicted, "neighborhood_code")

        a_row = result[result["group"] == "A"].iloc[0]
        b_row = result[result["group"] == "B"].iloc[0]
        self.assertEqual(a_row["sale_count"], 40)
        self.assertEqual(a_row["sample_band"], ratio_study.SAMPLE_BAND_NORMAL)
        self.assertEqual(b_row["sale_count"], 10)
        self.assertEqual(b_row["sample_band"], ratio_study.SAMPLE_BAND_INSUFFICIENT)


class BaselineModelTests(SimpleTestCase):
    def test_assessed_value_baseline_falls_back_to_market_value(self):
        test_df = pd.DataFrame({"assessed_value": [100_000.0, None], "total_market_value": [110_000.0, 220_000.0]})
        predicted = ratio_study.predict_assessed_value(None, test_df)
        self.assertEqual(list(predicted), [100_000.0, 220_000.0])

    def test_price_per_sqft_uses_train_medians_only(self):
        train_df = pd.DataFrame(
            {
                "sale_price": [200_000.0, 220_000.0, 400_000.0],
                "primary_living_area": [1000.0, 1100.0, 2000.0],
                "neighborhood_code": ["A", "A", "B"],
            }
        )
        test_df = pd.DataFrame({"neighborhood_code": ["A", "C"], "primary_living_area": [1000.0, 500.0]})

        predicted = ratio_study.predict_price_per_sqft(train_df, test_df)

        # Neighborhood A train median $/sqft = median(200, 200) = 200 -> 200 * 1000 = 200,000
        self.assertAlmostEqual(predicted.iloc[0], 200_000.0, delta=1.0)
        # Unseen neighborhood C falls back to the overall train median $/sqft (200/sqft) * 500 sqft.
        self.assertAlmostEqual(predicted.iloc[1], 100_000.0, delta=1.0)
