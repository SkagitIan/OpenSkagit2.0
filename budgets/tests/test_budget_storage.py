from __future__ import annotations

import os
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.storage import storages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from budgets.models import BudgetDocument
from budgets.storage import budget_pdf_upload_to


R2_ENV = {
    "R2_ACCOUNT_ID": "test-account",
    "R2_ACCESS_KEY_ID": "test-key",
    "R2_SECRET_ACCESS_KEY": "test-secret",
    "R2_BUCKET": "openskagit",
    "R2_BUDGET_BUCKET": "",
}


class BudgetStorageTests(SimpleTestCase):
    def test_pdf_key_is_stable_and_scoped(self):
        document = SimpleNamespace(
            content_sha256="a" * 64,
            jurisdiction=SimpleNamespace(slug="anacortes"),
            fiscal_year=2026,
            status="adopted",
        )
        self.assertEqual(
            budget_pdf_upload_to(document, "untrusted name.pdf"),
            "budgets/anacortes/2026/adopted/" + "a" * 64 + ".pdf",
        )

    def test_model_uses_dedicated_budget_storage_alias(self):
        field = BudgetDocument._meta.get_field("local_file")
        self.assertIs(field.storage, storages["budget_pdfs"])

    @patch.dict(os.environ, R2_ENV, clear=False)
    @patch("boto3.client")
    def test_r2_write_check_cleans_up_exact_object(self, client_factory):
        client = client_factory.return_value
        client.list_objects_v2.return_value = {"KeyCount": 0}
        client.head_object.return_value = {"ContentLength": 53}

        with patch("budgets.management.commands.check_budget_r2.uuid.uuid4") as uuid4:
            uuid4.return_value.hex = "abc123"
            call_command("check_budget_r2", write_test=True)

        put = client.put_object.call_args.kwargs
        self.assertEqual(put["Bucket"], "openskagit")
        self.assertEqual(put["Key"], "budgets/_healthchecks/abc123.pdf")
        self.assertEqual(len(put["Body"]), 53)
        client.head_object.assert_called_once_with(Bucket="openskagit", Key=put["Key"])
        client.delete_object.assert_called_once_with(Bucket="openskagit", Key=put["Key"])

    @patch.dict(
        os.environ,
        {"R2_ACCOUNT_ID": "", "R2_ACCESS_KEY_ID": "", "R2_SECRET_ACCESS_KEY": "", "R2_BUCKET": "", "R2_BUDGET_BUCKET": ""},
        clear=False,
    )
    def test_r2_check_fails_without_credentials(self):
        with self.assertRaisesMessage(CommandError, "Missing R2 configuration"):
            call_command("check_budget_r2")
    def test_catalog_dry_run_selects_seven_primary_documents(self):
        output = StringIO()
        call_command("import_budget_catalog", dry_run=True, stdout=output)
        rendered = output.getvalue()
        self.assertIn("Dry run complete: 7 document(s) selected.", rendered)
        self.assertIn("anacortes 2026 adopted", rendered)
        self.assertNotIn("hamilton 2026", rendered)
        self.assertNotIn("lyman 2026", rendered)

    def test_catalog_reports_jurisdiction_without_verified_pdf(self):
        output = StringIO()
        call_command("import_budget_catalog", dry_run=True, jurisdictions=["hamilton"], stdout=output)
        self.assertIn("No importable verified PDF for: hamilton", output.getvalue())
