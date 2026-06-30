"""
Parcel watch notification service.

Queue: called from sync_assessor_data after each successful run.
Send:  called from the send_notifications management command (separate Railway cron).
"""
from __future__ import annotations

import logging
from typing import IO

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Queueing — called at end of each nightly sync run
# ---------------------------------------------------------------------------

def queue_watchlist_notifications(run_id: int, stdout: IO | None = None) -> int:
    """
    Inspect the completed sync run for changes that touch watched parcels and
    queue a ParcelWatchNotification row for each affected user/parcel pair.
    Also queues brief notifications for all brief subscribers.
    Returns total rows created.
    """
    from assessor_sync.models import AssessorSyncChange, AuditorRecording
    from .models import OpportunitySavedParcel, ParcelWatchNotification, UserNotificationPreference, ParcelBookSyncNarrative

    # Build parcel -> [user] map for all watched parcels
    watched_qs = OpportunitySavedParcel.objects.select_related("user").all()
    parcel_to_users: dict[str, list] = {}
    for item in watched_qs:
        parcel_to_users.setdefault(item.parcel_number, []).append(item.user)

    # Build set of user IDs with watchlist notifications enabled
    watchlist_user_ids = set(
        UserNotificationPreference.objects.filter(notify_watchlist=True).values_list("user_id", flat=True)
    )

    count = 0

    if parcel_to_users and watchlist_user_ids:
        # 1. Assessor data changes
        for change in AssessorSyncChange.objects.filter(run_id=run_id).iterator():
            parcel_number = _extract_parcel_number(change)
            if not parcel_number or parcel_number not in parcel_to_users:
                continue
            for user in parcel_to_users[parcel_number]:
                if user.pk not in watchlist_user_ids:
                    continue
                _, created = ParcelWatchNotification.objects.get_or_create(
                    user=user,
                    parcel_number=parcel_number,
                    trigger_type=ParcelWatchNotification.TRIGGER_ASSESSOR,
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
            if recording.parcel_number not in parcel_to_users:
                continue
            for user in parcel_to_users[recording.parcel_number]:
                if user.pk not in watchlist_user_ids:
                    continue
                _, created = ParcelWatchNotification.objects.get_or_create(
                    user=user,
                    parcel_number=recording.parcel_number,
                    trigger_type=ParcelWatchNotification.TRIGGER_AUDITOR,
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

    # 3. Brief notifications for all brief subscribers
    brief_pref_qs = UserNotificationPreference.objects.filter(notify_brief=True).select_related("user")
    if brief_pref_qs.exists():
        from assessor_sync.models import AssessorSyncReport
        report = AssessorSyncReport.objects.filter(run_id=run_id).first()
        if report:
            narrative = ParcelBookSyncNarrative.objects.filter(assessor_sync_report=report).first()
            if narrative:
                for pref in brief_pref_qs:
                    _, created = ParcelWatchNotification.objects.get_or_create(
                        user=pref.user,
                        parcel_number="",
                        trigger_type=ParcelWatchNotification.TRIGGER_BRIEF,
                        run_id=run_id,
                        defaults={"payload": {"narrative_id": narrative.pk}},
                    )
                    if created:
                        count += 1

    _log(stdout, f"Queued {count} parcel watch notification(s) for run {run_id}.")
    return count


def _extract_parcel_number(change) -> str:
    """Pull parcel_number from an AssessorSyncChange regardless of table."""
    if change.table_name == "assessor_rollup":
        return change.record_key
    row = change.new_row or change.old_row or {}
    return row.get("parcel_number", "") or ""


# ---------------------------------------------------------------------------
# Sending — called from send_notifications management command
# ---------------------------------------------------------------------------

def send_pending_watchlist(cadence: str, stdout: IO | None = None) -> int:
    """
    Send unsent watchlist digest notifications to users whose digest_cadence matches.
    Marks notifications sent after a successful email.
    """
    from .models import ParcelWatchNotification, UserNotificationPreference, EmailTemplate

    prefs = UserNotificationPreference.objects.filter(
        notify_watchlist=True, digest_cadence=cadence
    ).select_related("user")

    sent_count = 0
    site_url = getattr(settings, "SITE_URL", "https://openskagit.org/opportunity")

    for pref in prefs:
        user = pref.user
        if not user.email:
            continue

        pending = ParcelWatchNotification.objects.filter(
            user=user,
            sent_at__isnull=True,
            trigger_type__in=[ParcelWatchNotification.TRIGGER_ASSESSOR, ParcelWatchNotification.TRIGGER_AUDITOR],
        ).order_by("parcel_number", "trigger_type", "created_at")

        if not pending.exists():
            continue

        changes = []
        for notif in pending:
            changes.append({
                "parcel_number": notif.parcel_number,
                "parcel_url": f"{site_url}/parcels/{notif.parcel_number}/",
                "trigger_label": notif.get_trigger_type_display(),
                "payload": notif.payload,
            })

        context = {"user": user, "changes": changes, "site_url": site_url}

        try:
            tmpl = EmailTemplate.objects.get(name=EmailTemplate.WATCHLIST_DIGEST)
            subject, html_body = _render_template(tmpl, context)
        except EmailTemplate.DoesNotExist:
            subject, html_body = _default_watchlist_email(context)

        try:
            _send_resend(user.email, subject, html_body)
            pending.update(sent_at=timezone.now())
            sent_count += pending.count()
            _log(stdout, f"Sent watchlist digest to {user.email} ({len(changes)} change(s)).")
        except Exception as exc:
            logger.error("Failed sending watchlist digest to %s: %s", user.email, exc)
            _log(stdout, f"ERROR sending to {user.email}: {exc}")

    return sent_count


def send_pending_brief(stdout: IO | None = None) -> int:
    """
    Send queued daily brief notifications to subscribed users.
    """
    from .models import ParcelWatchNotification, EmailTemplate, ParcelBookSyncNarrative

    pending_qs = ParcelWatchNotification.objects.filter(
        trigger_type=ParcelWatchNotification.TRIGGER_BRIEF,
        sent_at__isnull=True,
    ).select_related("user").order_by("user_id", "-created_at")

    site_url = getattr(settings, "SITE_URL", "https://openskagit.org/opportunity")
    sent_count = 0

    # Group by user — take the most recent brief per user
    seen_users: set[int] = set()
    for notif in pending_qs:
        user = notif.user
        if not user.email or user.pk in seen_users:
            continue
        seen_users.add(user.pk)

        narrative = None
        narrative_id = notif.payload.get("narrative_id")
        if narrative_id:
            narrative = ParcelBookSyncNarrative.objects.filter(pk=narrative_id).first()

        context = {
            "user": user,
            "narrative": narrative,
            "site_url": site_url,
        }

        try:
            tmpl = EmailTemplate.objects.get(name=EmailTemplate.DAILY_BRIEF)
            subject, html_body = _render_template(tmpl, context)
        except EmailTemplate.DoesNotExist:
            subject, html_body = _default_brief_email(context)

        try:
            _send_resend(user.email, subject, html_body)
            # Mark all unsent brief notifications for this user as sent
            ParcelWatchNotification.objects.filter(
                user=user,
                trigger_type=ParcelWatchNotification.TRIGGER_BRIEF,
                sent_at__isnull=True,
            ).update(sent_at=timezone.now())
            sent_count += 1
            _log(stdout, f"Sent brief to {user.email}.")
        except Exception as exc:
            logger.error("Failed sending brief to %s: %s", user.email, exc)
            _log(stdout, f"ERROR sending brief to {user.email}: {exc}")

    return sent_count


# ---------------------------------------------------------------------------
# Resend delivery
# ---------------------------------------------------------------------------

def _send_resend(to_email: str, subject: str, html_body: str) -> None:
    import resend

    resend.api_key = settings.RESEND_API_KEY
    from_addr = getattr(settings, "RESEND_FROM_EMAIL", "Parcel Book <parcelbook@openskagit.org>")
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
    from django.template import Template, Context
    subject = Template(tmpl.subject).render(Context(context))
    html_body = Template(tmpl.body_html).render(Context(context))
    return subject, html_body


def _default_watchlist_email(context: dict) -> tuple[str, str]:
    user = context["user"]
    changes = context["changes"]
    site_url = context["site_url"]
    first_name = user.first_name or user.get_username()
    subject = f"Parcel Book: {len(changes)} update(s) on your watched parcels"

    rows = ""
    for c in changes:
        p = c["payload"]
        if c["trigger_label"] == "Auditor recording":
            detail = f'{p.get("document_type", "")} — {p.get("grantor", "")} to {p.get("grantee", "")}'
            pdf = f'<br><a href="{p["pdf_url"]}" style="color:#00828A;">View document</a>' if p.get("pdf_url") else ""
        else:
            ai_summary = p.get("ai_summary", "")
            if ai_summary:
                detail = ai_summary
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
          <span style="color:#fff;font-size:16px;font-weight:700;">OpenSkagit Parcel Book</span>
        </td></tr>
        <tr><td style="padding:28px;">
          <p style="margin:0 0 6px;font-size:13px;color:#00828A;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Watchlist Update</p>
          <h1 style="margin:0 0 16px;font-size:22px;color:#042C53;">Hi {first_name}, your watched parcels have activity.</h1>
          <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
          <p style="margin:24px 0 0;font-size:13px;color:#617082;">
            Public-record screening signals only. Confirm documents, title, and site conditions before acting on any lead.<br>
            <a href="{site_url}" style="color:#00828A;">View Parcel Book</a> &middot;
            <a href="{site_url}/settings/" style="color:#617082;">Notification settings</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return subject, html_body


def _default_brief_email(context: dict) -> tuple[str, str]:
    user = context["user"]
    narrative = context.get("narrative")
    site_url = context["site_url"]
    first_name = user.first_name or user.get_username()

    if narrative:
        subject = narrative.newsletter_subject or narrative.headline
        headline = narrative.headline
        dek = narrative.dek
        body_text = narrative.narrative
        bullets_html = ""
        for b in (narrative.bullets or []):
            bullets_html += f"<li style='margin-bottom:6px;'>{b}</li>"
        bullets_block = f"<ul style='padding-left:20px;color:#3D4D5C;'>{bullets_html}</ul>" if bullets_html else ""
    else:
        subject = "Your Parcel Book daily brief"
        headline = "Daily brief"
        dek = ""
        body_text = ""
        bullets_block = ""

    html_body = f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f6f8f8;font-family:Inter,system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8f8;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #dfe7ee;border-radius:8px;overflow:hidden;">
        <tr><td style="background:#042C53;padding:20px 28px;">
          <span style="color:#fff;font-size:16px;font-weight:700;">OpenSkagit Parcel Book</span>
        </td></tr>
        <tr><td style="padding:28px;">
          <p style="margin:0 0 6px;font-size:13px;color:#00828A;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Daily Brief</p>
          <h1 style="margin:0 0 8px;font-size:22px;color:#042C53;">{headline}</h1>
          {f'<p style="margin:0 0 16px;color:#617082;">{dek}</p>' if dek else ''}
          {bullets_block}
          {f'<p style="margin:16px 0;color:#3D4D5C;line-height:1.6;">{body_text}</p>' if body_text else ''}
          <p style="margin:24px 0 0;font-size:13px;color:#617082;">
            Hi {first_name} — this is your Parcel Book brief from OpenSkagit.<br>
            <a href="{site_url}" style="color:#00828A;">View Parcel Book</a> &middot;
            <a href="{site_url}/settings/" style="color:#617082;">Notification settings</a>
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
