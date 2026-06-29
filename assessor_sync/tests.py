import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from assessor_sync.auditor import build_search_payload, parse_recordings
from assessor_sync.management.commands.sync_assessor_data import _changed_fields
from opportunity.services import build_sync_narrative_prompt, fallback_sync_narrative


class AuditorRecordingParserTests(SimpleTestCase):
    def _har_results_html(self):
        har_path = Path(settings.BASE_DIR) / "data" / "auditor.harfile.har"
        if not har_path.exists():
            self.skipTest(f"Missing auditor HAR fixture: {har_path}")
        har = json.loads(har_path.read_text(encoding="utf-8"))
        for entry in har["log"]["entries"]:
            request = entry.get("request", {})
            if request.get("method") == "POST" and "Search/Recording/Results.aspx" in request.get("url", ""):
                return entry["response"]["content"]["text"]
        self.fail("No recording results response found in auditor HAR.")

    def test_parse_recordings_from_har(self):
        rows = parse_recordings(self._har_results_html())

        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first.recording_number, "202606220039")
        self.assertEqual(first.recorded_date.isoformat(), "2026-06-22")
        self.assertEqual(first.document_type, "Transfer on Death Deed")
        self.assertEqual(first.signal_group, "transfer")
        self.assertEqual(first.grantor, "WYMOND DARLENE O")
        self.assertIn("WYMOND WILLIAM J", first.grantee)
        self.assertEqual(first.parcel_number, "P109600")
        self.assertIn("/Search/Property/?rt=details&id=P109600", first.assessor_url)
        self.assertTrue(first.pdf_url.endswith("/202606220039.pdf"))
        self.assertIn("TRACT 7", first.legal)

    def test_build_search_payload_uses_county_fields(self):
        html = self._har_results_html()
        rows = parse_recordings(html)
        payload = build_search_payload(
            '<input name="__VIEWSTATE" value="abc"><input name="__EVENTVALIDATION" value="xyz">',
            rows[0].document_type,
            rows[0].recorded_date,
            rows[0].recorded_date,
        )

        self.assertEqual(payload["ctl00$content$ddlDocumentType"], "Transfer on Death Deed")
        self.assertEqual(payload["ctl00$content$txtStartDate"], "6/22/2026")
        self.assertEqual(payload["ctl00$content$txtEndDate"], "6/22/2026")
        self.assertEqual(payload["ctl00$content$ddlSortBy"], "DateRecorded")
        self.assertEqual(payload["ctl00$content$btnSearchRecording"], "Search")

    def test_change_detection_ignores_whitespace_only_changes(self):
        old = {"recording_number": "202606220039", "legal": "TRACT 7  CLEAR LAKE", "recorded_date": "2026-06-22"}
        new = {"recording_number": "202606220039", "legal": "TRACT 7 CLEAR LAKE", "recorded_date": "2026-06-22"}

        self.assertEqual(_changed_fields(old, new), {})
        self.assertIn("legal", _changed_fields(old, new | {"legal": "DIFFERENT"}))

    def test_sync_narrative_prompt_and_fallback_include_auditor_summary(self):
        summary = {
            "files_changed": 1,
            "tables": {"sales": {"inserted": 2, "updated": 3, "applied_rows": 5}},
            "auditor": {"enabled": True, "inserted": 4, "updated": 1, "errors": 0},
        }

        prompt = build_sync_narrative_prompt("## New Auditor Recordings", summary)
        fallback = fallback_sync_narrative(summary)

        self.assertIn("Auditor sync summary JSON", prompt)
        self.assertIn("4 new filing", fallback["narrative"])
        self.assertEqual(len(fallback["bullets"]), 3)
