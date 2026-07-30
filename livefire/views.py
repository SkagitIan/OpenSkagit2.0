from copy import copy
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import DayForm, ExpenseForm, MenuItemForm, QuoteRequestForm, ScenarioForm, SnapshotForm, StaffingForm, VendorQuoteForm
from .models import DayAssumption, Expense, MenuItem, QuoteRequest, Scenario, Snapshot, StaffingLine, VendorQuote
from .services import calculate, create_base_scenario, snapshot_data


def owned_scenario(request, pk):
    return get_object_or_404(Scenario, pk=pk, owner=request.user)

@login_required
def dashboard(request):
    scenarios = Scenario.objects.filter(owner=request.user, is_archived=False)
    scenario = scenarios.filter(pk=request.GET.get("scenario")).first() or scenarios.first()
    if not scenario:
        scenario = create_base_scenario(request.user)
        scenarios = Scenario.objects.filter(owner=request.user, is_archived=False)
    if request.method == "POST":
        form = ScenarioForm(request.POST, instance=scenario)
        if form.is_valid():
            scenario = form.save(); messages.success(request, "Assumptions updated.")
            if request.headers.get("HX-Request"): return render(request, "livefire/_forecast.html", {"scenario": scenario, "forecast": calculate(scenario)})
            return redirect(f"/livefire/?scenario={scenario.pk}")
    else: form = ScenarioForm(instance=scenario)
    return render(request, "livefire/dashboard.html", {"scenarios": scenarios, "scenario": scenario, "form": form, "forecast": calculate(scenario)})

@login_required
def scenario_create(request):
    form = ScenarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        scenario = form.save(commit=False); scenario.owner = request.user; scenario.save()
        for day, _ in DayAssumption.DAYS: DayAssumption.objects.create(scenario=scenario, day=day, traffic=scenario.traffic, capture_rate=scenario.capture_rate, hours=scenario.hours_per_day, max_transactions_per_hour=scenario.max_transactions_per_hour)
        return redirect(f"/livefire/?scenario={scenario.pk}")
    return render(request, "livefire/form.html", {"form": form, "title": "New scenario"})

@login_required
@require_POST
def scenario_clone(request, pk):
    original = owned_scenario(request, pk)
    with transaction.atomic():
        clone = copy(original); clone.pk = None; clone.name = f"{original.name} copy"; clone.save()
        for relation in (original.days.all(), original.menu_items.all(), original.staffing.all(), original.expenses.all()):
            for item in relation: item.pk = None; item.scenario = clone; item.save()
    return redirect(f"/livefire/?scenario={clone.pk}")

@login_required
@require_POST
def scenario_archive(request, pk):
    scenario = owned_scenario(request, pk); scenario.is_archived = True; scenario.save(update_fields=["is_archived"])
    return redirect("livefire:dashboard")

@login_required
def compare(request):
    ids = request.GET.getlist("scenario")[:3]
    scenarios = list(Scenario.objects.filter(owner=request.user, is_archived=False, pk__in=ids))
    return render(request, "livefire/compare.html", {"choices": Scenario.objects.filter(owner=request.user, is_archived=False), "results": [(s, calculate(s)) for s in scenarios]})

@login_required
def related_edit(request, scenario_pk, kind, pk=None):
    scenario = owned_scenario(request, scenario_pk)
    specs = {"day": (DayAssumption, DayForm), "menu": (MenuItem, MenuItemForm), "staff": (StaffingLine, StaffingForm), "expense": (Expense, ExpenseForm)}
    if kind not in specs: raise Http404
    model, form_class = specs[kind]; instance = get_object_or_404(model, pk=pk, scenario=scenario) if pk else None
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.scenario = scenario; obj.save(); return redirect(f"/livefire/?scenario={scenario.pk}")
    return render(request, "livefire/form.html", {"form": form, "title": f"{('Edit' if pk else 'Add')} {kind}"})

@login_required
def quotes(request):
    form = QuoteRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.owner = request.user; obj.save(); messages.success(request, "Secure vendor link created."); return redirect("livefire:quotes")
    requests = QuoteRequest.objects.filter(owner=request.user).prefetch_related("quotes")
    return render(request, "livefire/quotes.html", {"form": form, "requests": requests})

def vendor_quote(request, token):
    quote_request = get_object_or_404(QuoteRequest, token=token)
    if quote_request.expires_at and quote_request.expires_at < timezone.localdate(): raise Http404
    form = VendorQuoteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quote = form.save(commit=False); quote.request = quote_request; quote.save(); return render(request, "livefire/vendor_thanks.html")
    return render(request, "livefire/vendor_quote.html", {"form": form, "quote_request": quote_request})

@login_required
@require_POST
def prefer_quote(request, pk):
    quote = get_object_or_404(VendorQuote, pk=pk, request__owner=request.user)
    quote.request.quotes.update(preferred=False); quote.preferred = True; quote.save(update_fields=["preferred"])
    return redirect("livefire:quotes")

@login_required
def publish(request, pk):
    scenario = owned_scenario(request, pk); form = SnapshotForm(request.POST or None, initial={"title": scenario.name})
    if request.method == "POST" and form.is_valid():
        snapshot = Snapshot.objects.create(scenario=scenario, title=form.cleaned_data["title"], visible_sections=form.cleaned_data["visible_sections"], data=snapshot_data(scenario))
        return redirect("livefire:shared", token=snapshot.token)
    return render(request, "livefire/form.html", {"form": form, "title": "Publish snapshot"})

def shared(request, token):
    snapshot = get_object_or_404(Snapshot, token=token)
    return render(request, "livefire/shared.html", {"snapshot": snapshot, "report": snapshot.data, "sections": snapshot.visible_sections})
