from __future__ import annotations

import os
import uuid

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify the configured Cloudflare R2 budget archive; optionally perform a reversible write test."

    def add_arguments(self, parser):
        parser.add_argument(
            "--write-test",
            action="store_true",
            help="Upload, verify, and immediately delete a tiny PDF under budgets/_healthchecks/.",
        )

    def handle(self, *args, **options):
        try:
            import boto3
        except ImportError as exc:
            raise CommandError("Install django-storages[boto3] before checking R2.") from exc

        account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
        access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        bucket = (os.environ.get("R2_BUDGET_BUCKET") or os.environ.get("R2_BUCKET") or "").strip()
        missing = [
            name
            for name, value in {
                "R2_ACCOUNT_ID": account_id,
                "R2_ACCESS_KEY_ID": access_key,
                "R2_SECRET_ACCESS_KEY": secret_key,
                "R2_BUDGET_BUCKET/R2_BUCKET": bucket,
            }.items()
            if not value
        ]
        if missing:
            raise CommandError("Missing R2 configuration: " + ", ".join(missing))

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        object_count = 0
        continuation_token = None
        try:
            while True:
                request = {"Bucket": bucket, "Prefix": "budgets/", "MaxKeys": 1000}
                if continuation_token:
                    request["ContinuationToken"] = continuation_token
                result = client.list_objects_v2(**request)
                object_count += int(result.get("KeyCount", len(result.get("Contents", []))))
                if not result.get("IsTruncated"):
                    break
                continuation_token = result.get("NextContinuationToken")
                if not continuation_token:
                    raise CommandError("R2 returned a truncated listing without a continuation token.")
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"R2 budget-prefix read check failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            f"R2 read check passed for bucket '{bucket}' (budget objects visible: {object_count})."
        ))

        if not options["write_test"]:
            return

        key = f"budgets/_healthchecks/{uuid.uuid4().hex}.pdf"
        payload = b"%PDF-1.4\n% OpenSkagit temporary R2 write check\n%%EOF\n"
        uploaded = False
        try:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=payload,
                ContentType="application/pdf",
                Metadata={"purpose": "temporary-budget-storage-healthcheck"},
            )
            uploaded = True
            head = client.head_object(Bucket=bucket, Key=key)
            if int(head.get("ContentLength", -1)) != len(payload):
                raise CommandError("R2 write check returned an unexpected object length.")
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"R2 budget-prefix write check failed: {exc}") from exc
        finally:
            if uploaded:
                try:
                    client.delete_object(Bucket=bucket, Key=key)
                except Exception as exc:
                    raise CommandError(f"R2 write passed but cleanup failed for '{key}': {exc}") from exc
        self.stdout.write(self.style.SUCCESS("R2 write/read/delete check passed; the temporary object was removed."))
