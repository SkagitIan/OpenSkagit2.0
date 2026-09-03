from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from .visualizations import ASPECTS, generate_infographic


class VisualizationValidationTests(SimpleTestCase):
    def test_all_aspects_have_consistent_dimensions(self):
        for aspect, (width, height) in ASPECTS.items():
            with (
                patch("openskagit_tools.visualizations.default_storage.exists", return_value=True),
                patch("openskagit_tools.visualizations.default_storage.url", return_value="/media/example.svg"),
                patch(
                    "openskagit_tools.visualizations.upload_generated_asset",
                    return_value={
                        "cloudinary_public_id": "p",
                        "secure_url": "https://example.test/p",
                        "source_url": "https://example.test/p",
                        "cached": False,
                    },
                ),
                patch("openskagit_tools.visualizations.transformed_url", return_value="https://example.test/p.png"),
            ):
                result = generate_infographic("big_number", "Observed difference", [48000], aspect_ratio=aspect)
            self.assertEqual((result["width"], result["height"]), (width, height))
            self.assertEqual(result["aspect_ratio"], aspect)

    def test_infographic_rejects_mismatched_labels(self):
        with self.assertRaisesMessage(ValueError, "same length"):
            generate_infographic("bar", "Values", [1, 2], ["Only one"])

    def test_infographic_rejects_unknown_type(self):
        with self.assertRaisesMessage(ValueError, "Unsupported infographic type"):
            generate_infographic("scatter", "Values", [1])

    def test_vertical_bars_fit_inside_right_inset(self):
        with patch("openskagit_tools.visualizations._store", side_effect=lambda tool, payload, svg, width, height, source_ids, warnings: {"svg": svg}):
            result = generate_infographic("bar", "Assessment", [195100, 453500], ["Land", "Total"], aspect_ratio="9:16", presentation_mode="video_scene")
        self.assertIn('width="540"', result["svg"])
        self.assertIn('x="330"', result["svg"])

    def test_vertical_visuals_use_neutral_series_branding(self):
        with patch("openskagit_tools.visualizations._store", side_effect=lambda tool, payload, svg, width, height, source_ids, warnings: {"svg": svg}):
            result = generate_infographic("big_number", "Assessment total", [453500], aspect_ratio="9:16", presentation_mode="video_scene")
        self.assertIn("HOME VALUE BRIEF", result["svg"])
        self.assertNotIn("OPENSKAGIT", result["svg"])

    def test_infographic_preserves_provenance_metadata(self):
        with (
            patch("openskagit_tools.visualizations.default_storage.exists", return_value=True),
            patch("openskagit_tools.visualizations.default_storage.url", return_value="/media/example.svg"),
            patch(
                "openskagit_tools.visualizations.upload_generated_asset",
                return_value={
                    "cloudinary_public_id": "p",
                    "secure_url": "https://example.test/p",
                    "source_url": "https://example.test/p",
                    "cached": False,
                },
            ),
            patch("openskagit_tools.visualizations.transformed_url", return_value="https://example.test/p.png"),
        ):
            result = generate_infographic(
                "value_breakdown",
                "Value",
                [1, 2],
                ["Land", "House"],
                property_ids=["P123"],
                source_references=["assessed_value"],
            )
        self.assertEqual(result["source_property_ids"], ["P123"])
        self.assertEqual(result["fields_used"], ["assessed_value"])

    def test_video_scene_mode_uses_the_same_real_vertical_canvas_without_dense_footer(self):
        with (
            patch("openskagit_tools.visualizations.default_storage.exists", return_value=True),
            patch("openskagit_tools.visualizations.default_storage.url", return_value="/media/example.svg"),
            patch("openskagit_tools.visualizations.upload_generated_asset", return_value={"cloudinary_public_id": "p", "secure_url": "https://example.test/p", "cached": False}),
            patch("openskagit_tools.visualizations.transformed_url", return_value="https://example.test/p.png"),
            patch("openskagit_tools.visualizations._store", side_effect=lambda tool, payload, svg, width, height, source_ids, warnings: {"svg": svg, "payload": payload, "width": width, "height": height}),
        ):
            result = generate_infographic("value_breakdown", "Land versus building", [2, 3], ["Land", "Building"], aspect_ratio="9:16", presentation_mode="video_scene")
        self.assertEqual((result["width"], result["height"]), (1080, 1920))
        self.assertEqual(result["payload"]["presentation_mode"], "video_scene")
        self.assertNotIn("READ THE RECORD IN PARTS", result["svg"])
