"""
TaxShift signup notification service.

Queue: called from assessor_sync's sync_assessor_data after each successful
       nightly run.
Send:  called from the send_taxshift_notifications management command
       (separate Railway cron, same convention as opportunity's
       send_notifications).
"""
from __future__ import annotations

import logging
from typing import IO

from django.conf import settings
from django.core.signing import TimestampSigner
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Queueing — called at end of each nightly sync run
# ---------------------------------------------------------------------------

def queue_taxshift_notifications(run_id: int, stdout: IO | None = None) -> int:
    """
    Inspect the completed sync run for changes that touch watched TaxShift
    parcels and queue a TaxShiftNotification row for each affected signup.
    Returns total rows created.
    """
    from assessor_sync.models import AssessorSyncChange, AuditorRecording
    from .models import TaxShiftNotification, TaxShiftSignup

    watched_qs = TaxShiftSignup.objects.filter(
        is_active=True, resolution_status=TaxShiftSignup.RESOLUTION_RESOLVED
    ).exclude(parcel_number="")
    parcel_to_signups: dict[str, list] = {}
    for signup in watched_qs:
        parcel_to_signups.setdefault(signup.parcel_number, []).append(signup)

    count = 0

    if parcel_to_signups:
        # 1. Assessor data changes
        for change in AssessorSyncChange.objects.filter(run_id=run_id).iterator():
            parcel_number = _extract_parcel_number(change)
            if not parcel_number or parcel_number not in parcel_to_signups:
                continue
            for signup in parcel_to_signups[parcel_number]:
                _, created = TaxShiftNotification.objects.get_or_create(
                    signup=signup,
                    parcel_number=parcel_number,
                    trigger_type=TaxShiftNotification.TRIGGER_ASSESSOR,
                    run_id=run_id,
                    defaults={
                        "payload": {
                            "table_name": change.table_name,
                            "change_type": change.change_type,
                            "changed_fields": change.changed_fields,
                        }
                    },
                )
                if created:
                    count += 1

        # 2. Auditor recordings first seen in this run
        for recording in AuditorRecording.objects.filter(first_seen_run_id=run_id).exclude(parcel_number="").iterator():
            if recording.parcel_number not in parcel_to_signups:
                continue
            for signup in parcel_to_signups[recording.parcel_number]:
                _, created = TaxShiftNotification.objects.get_or_create(
                    signup=signup,
                    parcel_number=recording.parcel_number,
                    trigger_type=TaxShiftNotification.TRIGGER_AUDITOR,
                    run_id=run_id,
                    defaults={
                        "payload": {
                            "recording_number": recording.recording_number,
                            "document_type": recording.document_type,
                            "signal_group": recording.signal_group,
                            "grantor": recording.grantor,
                            "grantee": recording.grantee,
                            "recorded_date": str(recording.recorded_date) if recording.recorded_date else "",
                            "pdf_url": recording.pdf_url,
                        }
                    },
                )
                if created:
                    count += 1

    _log(stdout, f"Queued {count} taxshift notification(s) for run {run_id}.")
    return count


def _extract_parcel_number(change) -> str:
    """Pull parcel_number from an AssessorSyncChange regardless of table."""
    if change.table_name == "assessor_rollup":
        return change.record_key
    row = change.new_row or change.old_row or {}
    return row.get("parcel_number", "") or ""


# ---------------------------------------------------------------------------
# Unsubscribe tokens
# ---------------------------------------------------------------------------

def unsubscribe_token(email: str) -> str:
    return TimestampSigner(salt="taxshift-unsubscribe").sign(email)


def email_from_token(token: str, max_age_seconds: int = 60 * 60 * 24 * 30) -> str:
    return TimestampSigner(salt="taxshift-unsubscribe").unsign(token, max_age=max_age_seconds)


# ---------------------------------------------------------------------------
# Verification tokens — separate salt from unsubscribe so a leaked/expired
# link of one kind can never be replayed against the other endpoint.
# ---------------------------------------------------------------------------

def verification_token(email: str) -> str:
    return TimestampSigner(salt="taxshift-verify").sign(email)


def email_from_verification_token(token: str, max_age_seconds: int = 60 * 60 * 24 * 7) -> str:
    return TimestampSigner(salt="taxshift-verify").unsign(token, max_age=max_age_seconds)


# ---------------------------------------------------------------------------
# Verification + snapshot-summary email — sent once, immediately after the
# baseline snapshot is captured (see taxtool.snapshot.resolve_and_snapshot,
# triggered from the tax_signup view's background thread, with the
# process_taxshift_signups worker as a safety net for anything missed).
# ---------------------------------------------------------------------------

def send_verification_email(signup) -> None:
    """Send the one-time verification + snapshot-summary email. Idempotent."""
    from django.urls import reverse

    from .models import TaxShiftEmailTemplate

    if signup.verification_email_sent_at:
        return

    site_url = getattr(settings, "SITE_URL", "https://openskagit.org")
    verify_url = f"{site_url}{reverse('tax_verify', args=[verification_token(signup.email)])}"
    unsubscribe_url = f"{site_url}{reverse('tax_unsubscribe', args=[unsubscribe_token(signup.email)])}"
    parcel_url = f"{site_url}{reverse('tax_parcel', args=[signup.parcel_number])}" if signup.parcel_number else ""

    context = {
        "signup": signup,
        "snapshot": _snapshot_summary(signup),
        "verify_url": verify_url,
        "unsubscribe_url": unsubscribe_url,
        "parcel_url": parcel_url,
        "site_url": site_url,
    }

    try:
        tmpl = TaxShiftEmailTemplate.objects.get(name=TaxShiftEmailTemplate.VERIFICATION)
        subject, html_body = _render_template(tmpl, context)
    except TaxShiftEmailTemplate.DoesNotExist:
        subject, html_body = _default_verification_email(context)

    _send_resend(signup.email, subject, html_body)
    signup.verification_email_sent_at = timezone.now()
    signup.save(update_fields=["verification_email_sent_at", "updated_at"])


def _snapshot_summary(signup) -> dict | None:
    """Pull together a human-readable snapshot for the verification email.
    Returns None if the signup hasn't resolved to a parcel yet."""
    if signup.resolution_status != signup.RESOLUTION_RESOLVED or not signup.parcel_number:
        return None

    from .queries import get_parcel

    parcel = get_parcel(signup.parcel_number)
    if not parcel:
        return None

    address_parts = [parcel.get("situs_street_number"), parcel.get("situs_street_name")]
    address = " ".join(part for part in address_parts if part).strip()
    if parcel.get("situs_city_state_zip"):
        address = ", ".join(part for part in [address, parcel["situs_city_state_zip"]] if part)

    return {
        "address": address,
        "owner_name": parcel.get("owner_name", ""),
        "total_taxes_fmt": _format_currency(parcel.get("total_taxes")),
        "assessed_value_fmt": _format_currency(parcel.get("assessed_value")),
        "recorded_doc_count": len(signup.recorded_docs_snapshot or []),
    }


def _format_currency(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Sending — called from send_taxshift_notifications management command
# ---------------------------------------------------------------------------

def send_pending_taxshift(stdout: IO | None = None) -> int:
    """
    Send unsent notification digests to active TaxShift signups.
    Marks notifications sent after a successful email.
    """
    from django.urls import reverse

    from .models import TaxShiftEmailTemplate, TaxShiftNotification, TaxShiftSignup

    site_url = getattr(settings, "SITE_URL", "https://openskagit.org")
    sent_count = 0

    signup_ids = (
        TaxShiftNotification.objects.filter(sent_at__isnull=True, signup__is_active=True)
        .values_list("signup_id", flat=True)
        .distinct()
    )

    for signup in TaxShiftSignup.objects.filter(pk__in=list(signup_ids)):
        pending = TaxShiftNotification.objects.filter(signup=signup, sent_at__isnull=True).order_by(
            "parcel_number", "trigger_type", "created_at"
        )
        if not pending.exists():
            continue

        changes = [
            {
                "parcel_number": notif.parcel_number,
                "parcel_url": f"{site_url}{reverse('tax_parcel', args=[notif.parcel_number])}",
                "trigger_label": notif.get_trigger_type_display(),
                "payload": notif.payload,
            }
            for notif in pending
        ]

        unsubscribe_url = f"{site_url}{reverse('tax_unsubscribe', args=[unsubscribe_token(signup.email)])}"
        context = {"signup": signup, "changes": changes, "site_url": site_url, "unsubscribe_url": unsubscribe_url}

        try:
            tmpl = TaxShiftEmailTemplate.objects.get(name=TaxShiftEmailTemplate.WATCHLIST_DIGEST)
            subject, html_body = _render_template(tmpl, context)
        except TaxShiftEmailTemplate.DoesNotExist:
            subject, html_body = _default_watchlist_email(context)

        try:
            _send_resend(signup.email, subject, html_body)
            pending.update(sent_at=timezone.now())
            sent_count += pending.count()
            _log(stdout, f"Sent taxshift digest to {signup.email} ({len(changes)} change(s)).")
        except Exception as exc:
            logger.error("Failed sending taxshift digest to %s: %s", signup.email, exc)
            _log(stdout, f"ERROR sending to {signup.email}: {exc}")

    return sent_count


# ---------------------------------------------------------------------------
# Resend delivery
# ---------------------------------------------------------------------------

def _send_resend(to_email: str, subject: str, html_body: str) -> None:
    import resend

    resend.api_key = settings.RESEND_API_KEY
    from_addr = getattr(settings, "RESEND_FROM_EMAIL", "OpenSkagit <notifications@openskagit.org>")
    resend.Emails.send({
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    })


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _render_template(tmpl, context: dict) -> tuple[str, str]:
    from django.template import Context, Template
    subject = Template(tmpl.subject).render(Context(context))
    html_body = Template(tmpl.body_html).render(Context(context))
    return subject, html_body


def _default_watchlist_email(context: dict) -> tuple[str, str]:
    changes = context["changes"]
    site_url = context["site_url"]
    unsubscribe_url = context["unsubscribe_url"]
    subject = f"TaxShift: {len(changes)} update(s) on your watched parcel"

    rows = ""
    for c in changes:
        p = c["payload"]
        if c["trigger_label"] == "Auditor recording":
            detail = f'{p.get("document_type", "")} — {p.get("grantor", "")} to {p.get("grantee", "")}'
            pdf = f'<br><a href="{p["pdf_url"]}" style="color:#00828A;">View document</a>' if p.get("pdf_url") else ""
        else:
            fields = p.get("changed_fields", {})
            detail = ", ".join(fields.keys()) if fields else p.get("change_type", "")
            pdf = ""
        rows += f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #dfe7ee;">
            <a href="{c['parcel_url']}" style="color:#00828A;font-weight:700;">{c['parcel_number']}</a>
          </td>
          <td style="padding:10px 0 10px 16px;border-bottom:1px solid #dfe7ee;color:#3D4D5C;">
            {c['trigger_label']}<br><span style="font-size:13px;color:#617082;">{detail}</span>{pdf}
          </td>
        </tr>"""

    html_body = f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f6f8f8;font-family:Inter,system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8f8;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #dfe7ee;border-radius:8px;overflow:hidden;">
        <tr><td style="background:#042C53;padding:20px 28px;">
          <span style="color:#fff;font-size:16px;font-weight:700;">OpenSkagit TaxShift</span>
        </td></tr>
        <tr><td style="padding:28px;">
          <p style="margin:0 0 6px;font-size:13px;color:#00828A;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Watchlist Update</p>
          <h1 style="margin:0 0 16px;font-size:22px;color:#042C53;">There's new activity on your watched parcel.</h1>
          <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
          <p style="margin:24px 0 0;font-size:13px;color:#617082;">
            Public-record screening signals only. Confirm documents before acting on any change.<br>
            <a href="{site_url}" style="color:#00828A;">View TaxShift</a> &middot;
            <a href="{unsubscribe_url}" style="color:#617082;">Unsubscribe</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return subject, html_body


def _default_verification_email(context: dict) -> tuple[str, str]:
    snapshot = context["snapshot"]
    verify_url = context["verify_url"]
    unsubscribe_url = context["unsubscribe_url"]
    parcel_url = context["parcel_url"]

    if snapshot:
        subject = f"Verify your email — {snapshot['address'] or 'your TaxShift snapshot'}"
        stat_rows = ""
        for label, value in (
            ("Owner of record", snapshot["owner_name"]),
            ("Current tax bill", snapshot["total_taxes_fmt"]),
            ("Assessed value", snapshot["assessed_value_fmt"]),
        ):
            if not value:
                continue
            stat_rows += f"""
            <tr>
              <td style="padding:6px 0;color:#617082;font-size:13px;">{label}</td>
              <td style="padding:6px 0;color:#042C53;font-weight:700;text-align:right;">{value}</td>
            </tr>"""
        docs_line = (
            f"<p style=\"margin:12px 0 0;font-size:13px;color:#617082;\">"
            f"{snapshot['recorded_doc_count']} recorded document(s) on file for this parcel.</p>"
            if snapshot["recorded_doc_count"]
            else ""
        )
        snapshot_block = f"""
          <div style="margin:20px 0;padding:20px;border:1px solid #dfe7ee;border-radius:8px;background:#f9fbfc;">
            <p style="margin:0 0 10px;font-size:13px;color:#00828A;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Your snapshot</p>
            <p style="margin:0 0 10px;font-size:15px;color:#042C53;font-weight:700;">{snapshot['address']}</p>
            <table width="100%" cellpadding="0" cellspacing="0">{stat_rows}</table>
            {docs_line}
            {f'<p style="margin:14px 0 0;"><a href="{parcel_url}" style="color:#00828A;font-size:13px;">View full report</a></p>' if parcel_url else ''}
          </div>"""
    else:
        subject = "Verify your email to activate TaxShift tracking"
        snapshot_block = """
          <p style="margin:20px 0;font-size:14px;color:#617082;">
            We're still matching the address you gave us to a parcel — verify your email now and
            we'll keep working on it in the background.
          </p>"""

    html_body = f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f6f8f8;font-family:Inter,system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8f8;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #dfe7ee;border-radius:8px;overflow:hidden;">
        <tr><td style="background:#042C53;padding:20px 28px;">
          <span style="color:#fff;font-size:16px;font-weight:700;">OpenSkagit TaxShift</span>
        </td></tr>
        <tr><td style="padding:28px;">
          <p style="margin:0 0 6px;font-size:13px;color:#00828A;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Verify your email</p>
          <h1 style="margin:0 0 12px;font-size:22px;color:#042C53;">One click to start tracking.</h1>
          <p style="margin:0;font-size:14px;color:#3D4D5C;line-height:1.55;">
            Confirm this is your inbox and we'll email you whenever the assessor or auditor
            records for this parcel change.
          </p>
          {snapshot_block}
          <table cellpadding="0" cellspacing="0"><tr><td style="border-radius:8px;background:#00828A;">
            <a href="{verify_url}" style="display:inline-block;padding:14px 28px;color:#fff;font-weight:700;font-size:15px;text-decoration:none;">Verify email &amp; start tracking</a>
          </td></tr></table>
          <p style="margin:24px 0 0;font-size:13px;color:#617082;">
            Didn't sign up for this? <a href="{unsubscribe_url}" style="color:#617082;">Unsubscribe</a> and we'll stop.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return subject, html_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(stdout: IO | None, message: str) -> None:
    if stdout:
        stdout.write(message)
    else:
        logger.info(message)
