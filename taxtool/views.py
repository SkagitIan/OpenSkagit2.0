import logging
import threading

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import HttpResponse
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from core.views import CITY_PAGES
from .models import ParcelSearchCache, TaxShiftSignup

from .queries import (
    search_parcels,
    get_parcel,
    get_agency_crosswalk,
    get_county_total_for_mcag,
    get_parcel_history,
    get_data_methodology_stats,
)
from .og_images import render_parcel_og_image
from .report import build_tax_report_context
from .utils import (
    format_currency,
    format_amount_short,
    format_delta_currency,
    format_delta_pct,
    compute_yoy_breakdown,
    get_agency_info,
    build_display_history,
)

logger = logging.getLogger(__name__)


def _taxshift_context(**extra):
    context = {
        "city_pages": CITY_PAGES,
        "taxshift_turnstile_site_key": getattr(settings, "TAXSHIFT_TURNSTILE_SITE_KEY", ""),
    }
    context.update(extra)
    return context


def _verify_turnstile(request):
    if request.user.is_authenticated:
        return True, ""

    site_key = getattr(settings, "TAXSHIFT_TURNSTILE_SITE_KEY", "")
    secret_key = getattr(settings, "TAXSHIFT_TURNSTILE_SECRET_KEY", "")
    if not site_key and not secret_key:
        return True, ""
    if not site_key or not secret_key:
        return False, "CAPTCHA is not fully configured yet."

    token = request.POST.get("cf-turnstile-response", "")
    if not token:
        return False, "Complete the CAPTCHA and try again."

    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": secret_key,
                "response": token,
                "remoteip": request.META.get("REMOTE_ADDR", ""),
            },
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        logger.exception("TaxShift Turnstile verification request failed")
        return False, "CAPTCHA verification failed. Try again in a moment."

    if not payload.get("success"):
        logger.warning("TaxShift Turnstile rejected signup: %s", payload.get("error-codes"))
        return False, "CAPTCHA verification failed. Try again."
    return True, ""


def _signup_error_response(request, message):
    status = 200 if request.headers.get("HX-Request") else 400
    return render(request, "taxtool/_signup_result.html", {
        "success": False,
        "message": message,
    }, status=status)


def _ensure_user_for_signup(signup):
    user = signup.user
    if not user:
        user, created = User.objects.get_or_create(username=signup.email, defaults={"email": signup.email})
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        signup.user = user
        signup.save(update_fields=["user", "updated_at"])
    return user

def cache_searched_parcels(parcels, query="", source="search_result"):
    """Persist a lightweight cache of parcels users searched or opened."""
    for parcel in parcels:
        parcel_number = (parcel.get("parcel_number") or "").strip()
        if not parcel_number:
            continue
        defaults = {
            "situs_street_number": str(parcel.get("situs_street_number") or "")[:32],
            "situs_street_name": str(parcel.get("situs_street_name") or "")[:160],
            "situs_city_state_zip": str(parcel.get("situs_city_state_zip") or "")[:160],
            "last_query": query[:255],
            "last_source": source[:40],
        }
        cache, created = ParcelSearchCache.objects.update_or_create(
            parcel_number=parcel_number,
            defaults=defaults,
        )
        if created:
            ParcelSearchCache.objects.filter(pk=cache.pk).update(hit_count=1)
        else:
            ParcelSearchCache.objects.filter(pk=cache.pk).update(hit_count=F("hit_count") + 1)


def tax_parcel_og_image(request, parcel_id):
    image = render_parcel_og_image(parcel_id)
    response = HttpResponse(image, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    return response

def tax_home(request):
    return render(request, "taxtool/base.html", _taxshift_context())


def tax_data_sources(request):
    stats = get_data_methodology_stats()
    for key in (
        "active_parcels",
        "parcels_with_tax",
        "history_rows",
        "history_parcels",
        "summary_rows",
        "summary_parcels",
        "levy_rows",
        "levy_codes",
        "dor_rows",
        "agency_total_rows",
    ):
        if key in stats and stats[key] is not None:
            stats[f"{key}_fmt"] = f"{int(stats[key]):,}"
    return render(request, "taxtool/data_sources.html", _taxshift_context(stats=stats))


def tax_faq(request):
    return render(request, "taxtool/faq.html", _taxshift_context())



def tax_contact(request):
    context = _taxshift_context()

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()
        errors = []

        if not name:
            errors.append("Enter your name.")
        try:
            validate_email(email)
        except ValidationError:
            errors.append("Enter a valid email address.")
        if not message:
            errors.append("Enter a message.")

        context.update({
            "form_data": {
                "name": name,
                "email": email,
                "subject": subject,
                "message": message,
            },
            "errors": errors,
        })

        if not errors:
            email_subject = subject or "TaxShift contact form message"
            body = (
                f"Name: {name}\n"
                f"Email: {email}\n"
                f"Subject: {email_subject}\n\n"
                f"{message}"
            )
            send_mail(
                subject=f"[TaxShift] {email_subject}",
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=["ian@openskagit.com"],
                fail_silently=False,
            )
            context = _taxshift_context(success=True)

    return render(request, "taxtool/contact.html", context)

def tax_search(request):
    q = request.GET.get("q", "").strip()
    mode = request.GET.get("mode", "").strip()
    parcels = search_parcels(q) if len(q) >= 2 else []
    if parcels:
        cache_searched_parcels(parcels, query=q, source="search_result")
    template_name = "taxtool/_signup_suggestions.html" if mode == "signup" else "taxtool/_suggestions.html"
    return render(request, template_name, {"parcels": parcels, "q": q})


def _process_signup_async(signup_pk: int) -> None:
    """Resolve + snapshot + verification email, run off the request thread so
    the signup form can respond immediately with the modal."""
    from django.db import connections

    from .notifications import send_verification_email
    from .snapshot import resolve_and_snapshot

    try:
        signup = TaxShiftSignup.objects.get(pk=signup_pk)
        resolve_and_snapshot(signup)
        send_verification_email(signup)
    except Exception:
        logger.exception("Immediate TaxShift signup processing failed for signup %s", signup_pk)
    finally:
        connections.close_all()


@require_POST
def tax_signup(request):
    email = request.POST.get("email", "").strip().lower()
    address_or_parcel = request.POST.get("address_or_parcel", "").strip()
    parcel_number = request.POST.get("parcel_number", "").strip().upper()
    requires_parcel = request.POST.get("requires_parcel") == "1"
    source = request.POST.get("source", "").strip() or ("parcel_detail" if parcel_number else "taxshift_home")

    if request.user.is_authenticated and not email:
        email = (request.user.email or request.user.username or "").strip().lower()

    try:
        validate_email(email)
    except ValidationError:
        return _signup_error_response(request, "Enter a valid email address.")

    if requires_parcel and not parcel_number:
        return _signup_error_response(request, "Select a parcel from the autocomplete results.")

    if parcel_number:
        parcel = get_parcel(parcel_number)
        if not parcel:
            return _signup_error_response(request, "We could not find that parcel anymore. Search again and retry.")
        parcel_number = parcel["parcel_number"]
        if not address_or_parcel:
            address_parts = [parcel.get("situs_street_number"), parcel.get("situs_street_name")]
            address = " ".join(part for part in address_parts if part).strip()
            if parcel.get("situs_city_state_zip"):
                address = f"{address}, {parcel['situs_city_state_zip']}".strip(", ")
            address_or_parcel = f"{address} / Parcel {parcel_number}".strip()

    if source != "parcel_detail":
        captcha_ok, captcha_message = _verify_turnstile(request)
        if not captcha_ok:
            return _signup_error_response(request, captcha_message)

    signup_defaults = {
        "address_or_parcel": address_or_parcel[:255],
        "source": source,
        "resolution_status": TaxShiftSignup.RESOLUTION_PENDING,
        "is_active": True,
        "unsubscribed_at": None,
        "verification_email_sent_at": None,
    }
    if parcel_number:
        signup_defaults["parcel_number"] = parcel_number

    signup, _created = TaxShiftSignup.objects.update_or_create(
        email=email,
        defaults=signup_defaults,
    )
    threading.Thread(target=_process_signup_async, args=(signup.pk,), daemon=True).start()

    return render(request, "taxtool/_signup_result.html", {
        "success": True,
        "show_modal": True,
        "email": email,
    })


def tax_verify(request, token):
    from django.contrib.auth import login
    from django.core.signing import BadSignature, SignatureExpired
    from django.utils import timezone

    from .notifications import email_from_verification_token

    try:
        email = email_from_verification_token(token)
    except SignatureExpired:
        return render(request, "taxtool/verify_result.html", {
            "success": False,
            "message": "This verification link has expired. Sign up again on taxshift.co to get a new one.",
        }, status=400)
    except BadSignature:
        return render(request, "taxtool/verify_result.html", {
            "success": False,
            "message": "This verification link is invalid.",
        }, status=400)

    signup = TaxShiftSignup.objects.filter(email=email).first()
    if not signup:
        return render(request, "taxtool/verify_result.html", {
            "success": False,
            "message": "We couldn't find that signup anymore.",
        }, status=404)

    user = _ensure_user_for_signup(signup)

    signup.is_verified = True
    signup.verified_at = timezone.now()
    signup.user = user
    signup.save(update_fields=["is_verified", "verified_at", "user", "updated_at"])

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    return render(request, "taxtool/verify_result.html", {"success": True, "signup": signup})


@require_http_methods(["GET", "POST"])
def tax_login(request):
    context = _taxshift_context()

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        context["email"] = email
        try:
            validate_email(email)
        except ValidationError:
            context["errors"] = ["Enter a valid email address."]
            return render(request, "taxtool/login.html", context, status=400)

        signup = TaxShiftSignup.objects.filter(email=email, is_verified=True).first()
        if signup:
            _ensure_user_for_signup(signup)
            try:
                from .notifications import send_login_email

                send_login_email(signup)
            except Exception:
                logger.exception("TaxShift login email failed for %s", email)
                context["errors"] = ["We could not send a login link just now. Try again in a moment."]
                return render(request, "taxtool/login.html", context, status=500)

        context["success"] = True
        return render(request, "taxtool/login.html", context)

    return render(request, "taxtool/login.html", context)


def tax_login_token(request, token):
    from django.contrib.auth import login
    from django.core.signing import BadSignature, SignatureExpired

    from .notifications import email_from_login_token

    try:
        email = email_from_login_token(token)
    except SignatureExpired:
        return render(request, "taxtool/login.html", _taxshift_context(
            errors=["That login link has expired. Request a new link to continue."]
        ), status=400)
    except BadSignature:
        return render(request, "taxtool/login.html", _taxshift_context(
            errors=["That login link is invalid. Request a new link to continue."]
        ), status=400)

    signup = TaxShiftSignup.objects.filter(email=email, is_verified=True).first()
    if not signup:
        return render(request, "taxtool/login.html", _taxshift_context(
            errors=["We could not find a verified TaxShift account for that link."]
        ), status=404)

    user = _ensure_user_for_signup(signup)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("tax_account")


@login_required(login_url="tax_login")
@require_http_methods(["GET", "POST"])
def tax_account(request):
    if request.user.email:
        TaxShiftSignup.objects.filter(
            email__iexact=request.user.email,
            is_verified=True,
            user__isnull=True,
        ).update(user=request.user)

    signups = TaxShiftSignup.objects.filter(user=request.user, is_verified=True).order_by("-updated_at")

    if request.method == "POST":
        signup = get_object_or_404(signups, pk=request.POST.get("signup_id"))
        wants_notifications = request.POST.get("is_active") == "on"
        signup.is_active = wants_notifications
        if wants_notifications:
            signup.unsubscribed_at = None
        else:
            from django.utils import timezone

            signup.unsubscribed_at = timezone.now()
        signup.save(update_fields=["is_active", "unsubscribed_at", "updated_at"])
        messages.success(request, "Notification preferences updated.")
        return redirect("tax_account")

    return render(request, "taxtool/account.html", _taxshift_context(signups=signups))


def tax_privacy(request):
    return render(request, "taxtool/privacy.html", _taxshift_context())


def tax_terms(request):
    return render(request, "taxtool/terms.html", _taxshift_context())

def tax_unsubscribe(request, token):
    from django.core.signing import BadSignature, SignatureExpired
    from django.utils import timezone

    from .notifications import email_from_token

    try:
        email = email_from_token(token)
    except (BadSignature, SignatureExpired):
        return render(request, "taxtool/_signup_result.html", {
            "success": False,
            "message": "This unsubscribe link is invalid or has expired.",
        }, status=400)

    updated = TaxShiftSignup.objects.filter(email=email).update(
        is_active=False, unsubscribed_at=timezone.now()
    )
    message = (
        "You're unsubscribed and won't receive further TaxShift updates."
        if updated
        else "That email address wasn't found on the TaxShift list."
    )
    return render(request, "taxtool/_signup_result.html", {"success": True, "message": message})


def tax_parcel(request, parcel_number):
    template_name = "taxtool/_bill.html" if request.headers.get("HX-Request") else "taxtool/parcel_page.html"
    context = build_tax_report_context(parcel_number, city_pages=CITY_PAGES)
    context["taxshift_turnstile_site_key"] = getattr(settings, "TAXSHIFT_TURNSTILE_SITE_KEY", "")
    parcel = context.get("parcel")
    if parcel:
        cache_searched_parcels([parcel], query=parcel_number, source="parcel_detail")
        context["parcel_is_tracked"] = _user_tracks_parcel(request.user, parcel["parcel_number"])

    return render(request, template_name, context)


def _user_tracks_parcel(user, parcel_number):
    if not user.is_authenticated:
        return False

    filters = Q(user=user)
    if user.email:
        filters |= Q(email__iexact=user.email)
    return TaxShiftSignup.objects.filter(
        filters,
        parcel_number=parcel_number,
        is_verified=True,
    ).exists()


def tax_yoy(request, parcel_number):
    parcel = get_parcel(parcel_number)
    if not parcel:
        return render(request, "taxtool/_yoy.html", {"error": "Parcel not found.", "parcel_number": parcel_number})

    history = build_display_history(parcel, get_parcel_history(parcel_number))
    if not history:
        return render(request, "taxtool/_yoy.html", {"parcel": parcel, "no_history": True})

    breakdowns = compute_yoy_breakdown(history)

    latest_ctx = None
    if breakdowns:
        b = breakdowns[0]
        rate_delta = b["rate_b"] - b["rate_a"]
        rate_delta_sign = "+" if rate_delta >= 0 else "-"
        latest_ctx = {
            "year_b": b["year_b"],
            "year_a": b["year_a"],
            "tax_b_fmt": format_currency(b["tax_b"]),
            "tax_a_fmt": format_currency(b["tax_a"]),
            "delta_fmt": format_delta_currency(b["delta_tax"]),
            "delta_pct_fmt": format_delta_pct(b["delta_pct"]),
            "delta_positive": b["delta_tax"] >= 0,
            "val_b_fmt": format_currency(b["val_b"]),
            "val_a_fmt": format_currency(b["val_a"]),
            "delta_val_fmt": format_delta_currency(b["delta_val"]),
            "delta_val_pct_fmt": format_delta_pct(b["delta_val_pct"]),
            "rate_a_fmt": f"{b['rate_a']:.2f}",
            "rate_b_fmt": f"{b['rate_b']:.2f}",
            "rate_delta_fmt": f"{rate_delta_sign}{abs(rate_delta):.2f} per $1,000",
            "value_effect_fmt": format_delta_currency(b["value_effect"]),
            "value_effect_positive": b["value_effect"] >= 0,
            "rate_effect_fmt": format_delta_currency(b["rate_effect"]),
            "rate_effect_positive": b["rate_effect"] >= 0,
        }

    history_rows = []
    for i, row in enumerate(history):
        bd = breakdowns[i] if i < len(breakdowns) else None
        history_rows.append({
            "tax_year": row["tax_year"],
            "total_value_fmt": format_currency(row["total_value"]),
            "tax_amount_fmt": format_currency(row["tax_amount"]),
            "delta_fmt": format_delta_currency(bd["delta_tax"]) if bd else "",
            "delta_pct_fmt": format_delta_pct(bd["delta_pct"]) if bd else "",
            "delta_positive": bd["delta_tax"] >= 0 if bd else None,
        })

    return render(request, "taxtool/_yoy.html", {
        "parcel": parcel,
        "latest": latest_ctx,
        "history_rows": history_rows,
    })


def tax_agency(request, mcag):
    # Pull user's tax amount for this agency from query param (passed by template)
    your_amount_raw = request.GET.get("your_amount")
    your_amount_fmt = format_currency(your_amount_raw) if your_amount_raw else None

    info = get_agency_info(mcag)
    crosswalk = get_agency_crosswalk(mcag)

    if not info and not crosswalk:
        return render(request, "taxtool/_agency.html", {
            "error": f"No data found for agency {mcag}.",
            "mcag": mcag,
        })

    common_name = (info or {}).get("common_name") or (crosswalk or {}).get("sao_legal_name", "Unknown Agency")
    blurb = (info or {}).get("blurb")
    budget = (info or {}).get("budget")
    sao_fit_url = (info or {}).get("sao_fit_url") or (crosswalk or {}).get("sao_fit_url")
    data_year = (info or {}).get("data_year")

    county_total = get_county_total_for_mcag(mcag)
    county_total_fmt = format_currency(county_total)

    top_expenditures = []
    if budget:
        top_expenditures = (budget.get("top_expenditures") or [])[:3]
        for exp in top_expenditures:
            exp["amount_fmt"] = format_amount_short(exp.get("amount"))

    return render(request, "taxtool/_agency.html", {
        "mcag": mcag,
        "common_name": common_name,
        "blurb": blurb,
        "budget": budget,
        "sao_fit_url": sao_fit_url,
        "data_year": data_year,
        "county_total_fmt": county_total_fmt,
        "your_amount_fmt": your_amount_fmt,
        "top_expenditures": top_expenditures,
        "revenue_fmt": format_amount_short((budget or {}).get("total_revenue")),
        "spent_fmt": format_amount_short((budget or {}).get("total_expenditure")),
        "surplus_fmt": format_amount_short((budget or {}).get("surplus_deficit")),
        "surplus_positive": ((budget or {}).get("surplus_deficit") or 0) >= 0,
        "property_tax_pct": (budget or {}).get("property_tax_pct_of_revenue"),
    })


@staff_member_required
def tax_staff_dashboard(request):
    from .dashboard import build_dashboard_context

    return render(request, "taxtool/staff_dashboard.html", build_dashboard_context())
