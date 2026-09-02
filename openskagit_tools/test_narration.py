from __future__ import annotations

import base64
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .narration import _alignment_timings, generate_narration


class NarrationTests(SimpleTestCase):
    def test_alignment_derives_words_and_sentence_segments(self):
        text = "Sold for $685,000."
        alignment = {
            "characters": list(text),
            "character_start_times_seconds": [i * 0.1 for i in range(len(text))],
            "character_end_times_seconds": [(i + 1) * 0.1 for i in range(len(text))],
        }
        characters, words, duration, warnings = _alignment_timings(text, alignment)
        self.assertEqual(len(characters), len(text))
        self.assertEqual([item["word"] for item in words], ["Sold", "for", "$685,000."])
        self.assertEqual(words[-1]["start"], 0.9)
        self.assertEqual(words[-1]["end"], 1.8)
        self.assertEqual(duration, 1.8)
        self.assertFalse(warnings)

    def test_valid_generation_preserves_original_script_and_metadata(self):
        text = "Most homes tell a story."
        alignment = {
            "characters": list(text),
            "character_start_times_seconds": [0.0] * len(text),
            "character_end_times_seconds": [0.5] * len(text),
        }
        response = Mock(
            status_code=200, json=lambda: {"audio_base64": base64.b64encode(b"audio").decode(), "alignment": alignment}
        )
        cloud = {
            "cloudinary_public_id": "openskagit/visuals/narration/direct/narration_hash",
            "secure_url": "https://audio.example/narration.mp3",
            "cached": False,
            "format": "mp3",
        }
        with (
            patch.dict(
                "os.environ", {"ELEVEN_LABS_API_KEY": "test-key", "ELEVEN_LABS_DEFAULT_VOICE_ID": "voice_12345678"}
            ),
            patch("openskagit_tools.narration.requests.post", return_value=response),
            patch("openskagit_tools.narration.upload_generated_asset", return_value=cloud),
        ):
            result = generate_narration(text)
        self.assertEqual(result["original_script"], text)
        self.assertEqual(result["audio_url"], cloud["secure_url"])
        self.assertEqual(result["voice_id"], "voice_12345678")
        self.assertTrue(result["segments"])
        self.assertEqual(response.call_args.kwargs["params"]["output_format"], "mp3_44100_128")

    def test_empty_text_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "Narration text is required"):
            generate_narration(" ")
