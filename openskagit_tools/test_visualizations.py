from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from .visualizations import ASPECTS, generate_infographic


class VisualizationValidationTests(SimpleTestCase):
    def test_all_aspects_have_consistent_dimensions(self):
        for aspect, (width, height) in ASPECTS.items():
            with patch("openskagit_tools.visualizations.default_storage.exists", return_value=True), patch(
                "openskagit_tools.visualizations.default_storage.url", return_value="/media/example.svg"
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

    def test_infographic_preserves_provenance_metadata(self):
        with patch("openskagit_tools.visualizations.default_storage.exists", return_value=True), patch(
            "openskagit_tools.visualizations.default_storage.url", return_value="/media/example.svg"
        ):
            result = generate_infographic("value_breakdown", "Value", [1, 2], ["Land", "House"], property_ids=["P123"], source_references=["assessed_value"])
        self.assertEqual(result["source_property_ids"], ["P123"])
        self.assertEqual(result["fields_used"], ["assessed_value"])
