import json
import base64
import struct
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from .video import VideoManifestError, _caption_chunks, prepare_video, render_prepared_video, validate_manifest


def manifest(**changes):
    value = {
        "episode_id": "audit-example",
        "project": "Audit example",
        "title": "A property story",
        "description": "Evidence-led test episode.",
        "aspect_ratio": "9:16",
        "narration": {
            "cloudinary_public_id": "openskagit/visuals/narration/direct/narration_hash",
            "secure_url": "https://audio.example/narration.mp3",
            "duration": 8.0,
            "segments": [{"text": "A property story with concise captions.", "start": 0.0, "end": 2.0}],
        },
        "captions": True,
        "scenes": [
            {"id": "intro", "duration": 4.0, "primary_asset": {"cloudinary_public_id": "visual/intro", "secure_url": "https://image.example/intro.png"}, "motion": "none"},
            {"id": "value", "duration": 4.0, "primary_asset": {"cloudinary_public_id": "visual/value", "secure_url": "https://image.example/value.png"}, "motion": "none", "transition": "cut", "provenance": ["fact_value"]},
        ],
    }
    value.update(changes)
    return value


class VideoManifestTests(SimpleTestCase):
    def test_timeline_and_rounding_adjustment(self):
        normalized = validate_manifest({**manifest(), "narration": {**manifest()["narration"], "duration": 8.1}})
        self.assertEqual(normalized["scenes"][-1]["end"], 8.1)
        self.assertTrue(normalized["warnings"])

    def test_rejects_carrier_and_non_deterministic_effects_up_front(self):
        with self.assertRaisesMessage(VideoManifestError, "carrier"):
            validate_manifest({**manifest(), "base_video": "samples/elephants"})
        animated = manifest()
        animated["scenes"][0]["motion"] = "slow_zoom_in"
        with self.assertRaisesMessage(VideoManifestError, "motion must be 'none'"):
            validate_manifest(animated)

    def test_rejects_material_timing_mismatch(self):
        with self.assertRaisesMessage(VideoManifestError, "differs from narration"):
            validate_manifest({**manifest(), "narration": {**manifest()["narration"], "duration": 20}})

    def test_caption_chunks_are_phrase_sized(self):
        chunks = _caption_chunks(manifest()["narration"])
        self.assertTrue(chunks)
        self.assertTrue(all(len(item["text"].split()) <= 6 for item in chunks))

    @patch("openskagit_tools.video._catalog_episode")
    @patch("openskagit_tools.video._download")
    def test_prepare_freezes_inputs_and_reuses_bundle(self, download, catalog):
        download.side_effect = lambda reference, target, image: Path(target).write_bytes(b"asset")
        with TemporaryDirectory() as directory:
            first = prepare_video(manifest(), root=directory)
            second = prepare_video(manifest(), root=directory)
            self.assertEqual(first["bundle_id"], second["bundle_id"])
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertTrue(Path(first["caption_path"]).exists())
            self.assertEqual(download.call_count, 3)
            self.assertEqual(json.loads((Path(first["directory"]) / "bundle.json").read_text())["status"], "prepared")
        self.assertEqual(catalog.call_count, 1)

    @patch("openskagit_tools.video.delivery_url", return_value="https://video.example/thumb.jpg")
    @patch("openskagit_tools.video.upload_generated_asset")
    @patch("openskagit_tools.video._inspect_video")
    @patch("openskagit_tools.video._run_ffmpeg")
    @patch("openskagit_tools.video._catalog_episode")
    def test_render_publishes_real_mp4_and_marks_catalog_ready(self, catalog, run, inspect, upload, _delivery):
        inspect.return_value = {"width": 1080, "height": 1920, "duration": 8.0, "audio_codec": "aac", "video_codec": "h264"}
        upload.return_value = {"cloudinary_public_id": "openskagit/visuals/videos/audit/video_hash", "secure_url": "https://video.example/final.mp4", "cached": False}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("scene_001.png", "scene_002.png", "narration.audio", "captions.ass"):
                (root / name).write_bytes(b"asset")
            prepared = validate_manifest(manifest())
            bundle = {"bundle_id": "hash", "episode_id": "audit-example", "directory": str(root), "manifest": prepared, "scenes": [{**prepared["scenes"][0], "local_path": str(root / "scene_001.png")}, {**prepared["scenes"][1], "local_path": str(root / "scene_002.png")}], "audio_path": str(root / "narration.audio")}
            run.side_effect = lambda command, cwd: (root / "final.mp4").write_bytes(b"real mp4 bytes")
            result = render_prepared_video(bundle)
            cached = render_prepared_video(bundle)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(cached["cached"])
        self.assertEqual(result["url"], "https://video.example/final.mp4")
        self.assertEqual(upload.call_count, 1)
        self.assertFalse(upload.call_args.kwargs["check_existing"])
        self.assertEqual(catalog.call_args.kwargs["status"], "ready")
        self.assertEqual(catalog.call_args.kwargs["video_url"], result["url"])

    @patch("openskagit_tools.video.delivery_url", return_value="https://video.example/thumb.jpg")
    @patch("openskagit_tools.video.upload_generated_asset", return_value={"cloudinary_public_id": "video/test", "secure_url": "https://video.example/test.mp4", "cached": False})
    @patch("openskagit_tools.video._catalog_episode")
    def test_real_ffmpeg_smoke_includes_audio_and_burned_captions(self, _catalog, _upload, _delivery):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "source.png"
            image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR4nGP4z8DAwMDAxMDAwMAAAA0AAf9X5dQAAAAASUVORK5CYII="))
            audio = root / "source.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(struct.pack("<h", 0) * 8000)
            tiny = manifest(
                narration={"local_path": str(audio), "duration": 1.0, "segments": [{"text": "A clear caption.", "start": 0.0, "end": 0.9}]},
                scenes=[{"id": "one", "duration": 1.0, "primary_asset": {"local_path": str(image)}}],
            )
            bundle = prepare_video(tiny, root=root / "renders")
            result = render_prepared_video(bundle)
            self.assertEqual(result["qa_results"]["audio_codec"], "aac")
            self.assertEqual((result["width"], result["height"]), (1080, 1920))
