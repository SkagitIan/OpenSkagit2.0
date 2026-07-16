from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import McpAccessRequestForm
from .models import McpAccessRequest
from .registry import TOOL_CONTRACTS

DOMAIN_LABELS = {
    "parcel": "Parcel & assessor",
    "gis": "GIS & overlays",
    "context": "Census & soils",
    "zoning": "Zoning & feasibility",
}


def _client_ip(request) -> str | None:
    return (
        request.META.get("HTTP_CF_CONNECTING_IP")
        or (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",", 1)[0].strip())
        or request.META.get("REMOTE_ADDR")
        or None
    )


def _tool_groups():
    groups: OrderedDict[str, list] = OrderedDict()
    for contract in TOOL_CONTRACTS:
        groups.setdefault(contract.domain, []).append(contract)
    return [{"key": key, "label": DOMAIN_LABELS.get(key, key.title()), "tools": tools} for key, tools in groups.items()]


@require_http_methods(["GET", "POST"])
def mcp_catalog(request):
    submitted = False
    if request.method == "POST":
        form = McpAccessRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            recent = McpAccessRequest.objects.filter(
                email__iexact=email,
                created_at__gte=timezone.now() - timedelta(minutes=10),
            ).exists()
            if not recent:
                access_request = form.save(commit=False)
                access_request.email = email
                access_request.ip_address = _client_ip(request)
                access_request.user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
                access_request.save()
            submitted = True
            form = McpAccessRequestForm()
    else:
        form = McpAccessRequestForm()

    return render(
        request,
        "openskagit_tools/catalog.html",
        {
            "form": form,
            "submitted": submitted,
            "tool_groups": _tool_groups(),
            "tool_count": len(TOOL_CONTRACTS),
            "connector_url": getattr(
                settings,
                "OPENSKAGIT_MCP_CONNECTOR_URL",
                "https://openskagit.com/mcp/api/",
            ),
        },
    )
