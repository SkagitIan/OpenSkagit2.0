from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase
from unittest.mock import patch

from .house_content_engine import (
    EngineValidationError,
    EpisodeStore,
    FactLedger,
    Investigation,
    StoryPackage,
    binned_summary,
    build_production_manifest,
    derive_narration_cues,
    deduplicate_rows,
    group_summary,
    validate_fact_ledger,
    validate_public_artifact,
)


class HouseContentContractTests(SimpleTestCase):
    def test_typed_state_serializes_and_rejects_missing_fields(self):
        investigation = Investigation(
            id="acreage-value", question="How does acreage relate to value?", homeowner_concern="More land should mean more value.",
            hypothesis="The relationship is not proportional.", alternative_hypothesis="House size explains most of the difference.",
            variables=["acres", "sale_price"], geography="Washington", population="comparable residential sales", method="group comparison",
        )
        self.assertEqual(Investigation.model_validate_json(investigation.model_dump_json()).id, "acreage-value")
        with self.assertRaises(ValueError):
            Investigation.model_validate({"id": "missing"})

    def test_fact_gate_checks_script_references_and_display_value(self):
        ledger = FactLedger(facts=[{
            "fact_id": "fact_total", "classification": "CALCULATED_RESULT", "value": 453500, "unit": "USD",
            "display_text": "$453,500", "narration_text": "four hundred fifty-three thousand five hundred dollars",
            "source_reference": "assessment total", "confidence": "high", "approved_for_public_use": True,
        }])
        story = StoryPackage(
            question="What makes up an assessment?", story_promise="Follow the components.", central_reveal="The total has components.",
            hook="Look beneath the total.", master_script="The total has components.", script_fact_map={"The total has components.": ["fact_total"]},
        )
        validate_fact_ledger(ledger, story=story)
        with self.assertRaisesMessage(EngineValidationError, "unsupported fact ID"):
            validate_fact_ledger(ledger, story=story.model_copy(update={"script_fact_map": {"x": ["fact_missing"]}}))
        with self.assertRaisesMessage(EngineValidationError, "conflicts"):
            validate_fact_ledger(FactLedger(facts=[ledger.facts[0].model_copy(update={"display_text": "$453,501"})]))

    def test_privacy_allows_internal_records_but_rejects_public_artifacts(self):
        with self.assertRaises(EngineValidationError):
            validate_public_artifact({"title": "Example", "address": "123 Main Street"})
        with self.assertRaises(EngineValidationError):
            validate_public_artifact({"caption": "Parcel P90623"})
        validate_public_artifact({"title": "Generalized residential example", "value": "$453,500"})

    def test_episode_store_is_resumable(self):
        with TemporaryDirectory() as directory:
            store = EpisodeStore("episode-1", Path(directory))
            store.save("research", {"result": "reframe"})
            self.assertTrue(store.exists("research"))
            self.assertEqual(store.load("research")["result"], "reframe")

    def test_analytical_helpers_define_grain_and_medians(self):
        rows = [{"parcel_number": "P1", "group": "small", "acres": 0.2, "price": 100}, {"parcel_number": "P1", "group": "small", "acres": 0.2, "price": 999}, {"parcel_number": "P2", "group": "large", "acres": 2, "price": 300}]
        unique = deduplicate_rows(rows)
        self.assertEqual(len(unique), 2)
        self.assertEqual(group_summary(unique, group_field="group", metric="price")["small"]["median"], 100)
        self.assertEqual(binned_summary(unique, field="acres", metric="price", bins=[0, 1, 3])[0]["count"], 1)


    def test_mocked_mechanical_pipeline_reaches_production_inputs(self):
        story = StoryPackage(
            question="Does more land mean proportionally more value?", story_promise="Compare the components.",
            central_reveal="The relationship is not proportional.", hook="Let's find out.", master_script="The relationship is not proportional.",
            visual_beats=[{"id": "reveal", "duration": 4, "asset_id": "asset-1", "provenance": [{"fact_id": "fact_ratio"}]}],
            script_fact_map={"The relationship is not proportional.": ["fact_ratio"]},
        )
        ledger = FactLedger(facts=[{
            "fact_id": "fact_ratio", "classification": "ANALYSIS", "value": None, "display_text": "not proportional",
            "narration_text": "the relationship is not proportional", "source_reference": "cohort analysis",
            "confidence": "medium", "approved_for_public_use": True,
        }])
        validate_fact_ledger(ledger, story=story)
        manifest = build_production_manifest(
            story, {"cloudinary_public_id": "audio/example", "duration": 4, "segments": [{"text": "The relationship is not proportional.", "start": 0, "end": 4}]},
            [{"asset_id": "asset-1", "cloudinary_public_id": "visual/example"}], project="mock episode",
        )
        self.assertEqual(manifest["scenes"][0]["primary_asset"], "visual/example")
        self.assertEqual(manifest["narration"]["duration"], 4)

    def test_aligned_cues_drive_scene_onsets_and_hold_through_pause(self):
        story = StoryPackage(
            question="What changes?", story_promise="Follow the evidence.", central_reveal="The components differ.",
            hook="Let's find out.", master_script="Land rises. Building follows.",
            script_cues=[
                {"cue_id": "land", "text": "Land rises.", "fact_ids": ["fact_land"]},
                {"cue_id": "building", "text": "Building follows.", "fact_ids": ["fact_building"]},
            ],
            visual_beats=[
                {"id": "land", "cue_id": "land", "asset_id": "asset-land"},
                {"id": "building", "cue_id": "building", "asset_id": "asset-building"},
            ],
        )
        narration = {
            "cloudinary_public_id": "audio/example", "duration": 5,
            "word_timings": [
                {"word": "Land", "start": 0.5, "end": 0.8}, {"word": "rises.", "start": 0.8, "end": 1.1},
                {"word": "Building", "start": 3.0, "end": 3.4}, {"word": "follows.", "start": 3.4, "end": 3.8},
            ],
        }
        self.assertEqual(derive_narration_cues(story, narration)["building"]["start"], 3.0)
        manifest = build_production_manifest(
            story, narration,
            [{"asset_id": "asset-land", "cloudinary_public_id": "visual/land"}, {"asset_id": "asset-building", "cloudinary_public_id": "visual/building"}],
            project="aligned episode",
        )
        self.assertEqual(manifest["scenes"][0]["start"], 0.0)
        self.assertEqual(manifest["scenes"][0]["duration"], 3.0)
        self.assertEqual(manifest["scenes"][1]["start"], 3.0)
        self.assertEqual(manifest["scenes"][1]["duration"], 2.0)

    def test_aligned_narration_rejects_guessed_scene_timing(self):
        story = StoryPackage(
            question="What changes?", story_promise="Follow the evidence.", central_reveal="The answer changes.",
            hook="Let's find out.", master_script="The answer changes.",
            visual_beats=[{"id": "answer", "duration": 4, "asset_id": "asset-answer"}],
        )
        with self.assertRaisesMessage(EngineValidationError, "guessed scene timing is disabled"):
            build_production_manifest(
                story,
                {"cloudinary_public_id": "audio/example", "duration": 4, "word_timings": [{"word": "The", "start": 0, "end": 0.1}]},
                [{"asset_id": "asset-answer", "cloudinary_public_id": "visual/answer"}],
                project="aligned episode",
            )

    @patch("openskagit_tools.visualizations._store")
    @patch("openskagit_tools.visualizations._query_properties")
    def test_anonymized_card_suppresses_identity(self, query, store):
        query.return_value = ([{"parcel_number": "P90623", "address": "123 Main Street", "situs_city_state_zip": "Town, WA", "assessed_value": 100}], [])
        store.side_effect = lambda tool, payload, svg, width, height, source_ids, warnings: {"svg": svg, "payload": payload}
        from .visualizations import generate_property_card

        result = generate_property_card("P90623", identity_mode="anonymized")
        self.assertNotIn("123 Main Street", result["svg"])
        self.assertNotIn("P90623", result["payload"]["summary"])
