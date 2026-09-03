from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .views import house_content_review


class HouseContentReviewTests(SimpleTestCase):
    @patch("core.views.render")
    @patch("core.views.HouseContentEpisode.objects.filter")
    def test_ready_catalog_records_feed_staff_page(self, filtered, render):
        filtered.return_value = [SimpleNamespace(episode_id="ready-video", title="Ready video", description="Evidence-led.", duration=63, video_url="https://video.example/ready.mp4", thumbnail_url="https://video.example/thumb.jpg")]
        request = RequestFactory().get("/staff/house-content/")
        request.user = SimpleNamespace(is_active=True, is_staff=True)
        house_content_review(request)
        filtered.assert_called_once_with(status="ready")
        context = render.call_args.args[2]
        self.assertEqual(context["finished_videos"][0]["duration"], "1:03")
        self.assertEqual(context["finished_videos"][0]["url"], "https://video.example/ready.mp4")
