from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .cloudinary_service import CloudinaryConfig, CloudinaryError, PRESETS, transformed_url, upload_generated_asset


class CloudinaryServiceTests(SimpleTestCase):
    @patch.dict(
        "os.environ",
        {"CLOUDINARY_CLOUD_NAME": "demo", "CLOUDINARY_API": "key", "CLOUDINARY_SECRET": "secret"},
        clear=False,
    )
    @patch("openskagit_tools.cloudinary_service.requests.get")
    @patch("openskagit_tools.cloudinary_service.requests.post")
    def test_uploads_svg_with_deterministic_public_id(self, post, get):
        get.return_value = Mock(status_code=404)
        post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "secure_url": "https://res.cloudinary.com/demo/image/upload/openskagit/visuals/maps/P123/map_hash.svg"
            },
        )
        result = upload_generated_asset(
            b"<svg/>", asset_type="map", digest="hash", source_property_ids=["P123"], metadata={"aspect_ratio": "16:9"}
        )
        self.assertEqual(result["cloudinary_public_id"], "openskagit/visuals/maps/P123/map_hash")
        self.assertFalse(result["cached"])
        self.assertEqual(post.call_args.kwargs["files"]["file"][2], "image/svg+xml")

    @patch.dict(
        "os.environ",
        {"CLOUDINARY_CLOUD_NAME": "demo", "CLOUDINARY_API": "key", "CLOUDINARY_SECRET": "secret"},
        clear=False,
    )
    @patch("openskagit_tools.cloudinary_service.requests.get")
    def test_existing_asset_is_reused(self, get):
        get.return_value = Mock(
            status_code=200, json=lambda: {"secure_url": "https://example.test/existing", "width": 1920, "height": 1080}
        )
        result = upload_generated_asset(
            b"svg", asset_type="infographic", digest="same", source_property_ids=[], metadata={}
        )
        self.assertTrue(result["cached"])

    @patch.dict(
        "os.environ",
        {"CLOUDINARY_CLOUD_NAME": "demo", "CLOUDINARY_API": "key", "CLOUDINARY_SECRET": "secret"},
        clear=False,
    )
    def test_transformation_presets_cover_required_sizes(self):
        for preset, size in PRESETS.items():
            url = transformed_url("openskagit/visuals/infographics/direct/x", preset, fmt="png")
            self.assertIn(f"w_{size['width']}", url)
            self.assertIn(f"h_{size['height']}", url)

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_credentials_are_clear(self):
        with self.assertRaisesMessage(CloudinaryError, "Cloudinary configuration is missing"):
            CloudinaryConfig.from_environment()
