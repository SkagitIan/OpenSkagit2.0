from urllib.parse import urlparse
import os

from django.conf import settings
from django.test import SimpleTestCase


class IsolatedEnvironmentSettingsTests(SimpleTestCase):
    def test_automated_tests_use_only_suppressed_local_postgis_settings(self):
        self.assertEqual(settings.OPENSKAGIT_ENVIRONMENT, "test")
        self.assertIn(settings.DATABASES["default"]["HOST"], {"127.0.0.1", "localhost", "::1", "postgis", "postgres"})
        self.assertIn("test", settings.DATABASES["default"]["NAME"].lower())
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(settings.EMAIL_BACKEND, "django.core.mail.backends.locmem.EmailBackend")
        self.assertEqual(settings.BUDGET_PDF_STORAGE, "local")
        self.assertEqual(settings.RESEND_API_KEY, "")
        self.assertIn(urlparse(settings.OPENSKAGIT_PUBLIC_ORIGIN).hostname, {"127.0.0.1", "localhost", "::1"})
        self.assertEqual(os.environ.get("OPENSKAGIT_ENABLE_LIVE_TOOLS"), "false")
        self.assertNotIn("OPENAI_API_KEY", os.environ)
        self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
