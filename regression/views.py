from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import ai_reasoning, background, compliance_runner
from .models import (
    ModelImprovementSummary,
    ModelLandSummary,
    ModelSFRSalesDataset,
    ModelSFRSalesExclusion,
    SFRComplianceLoopRun,
    SFRDatasetBuildRun,
    SFRRatioStudyRun,
    SFRSegmentModel,
)


@staff_member_required
def dashboard(request):
    latest_build = SFRDatasetBuildRun.objects.order_by("-started_at").first()
    recent_builds = list(SFRDatasetBuildRun.objects.order_by("-started_at")[:5])

    latest_ratio_study = SFRRatioStudyRun.objects.filter(status=SFRRatioStudyRun.STATUS_SUCCESS).order_by("-started_at").first()
    recent_ratio_studies = list(SFRRatioStudyRun.objects.order_by("-started_at")[:5])

    exclusion_breakdown = list(
        ModelSFRSalesExclusion.objects.values("exclusion_reason").annotate(count=Count("id")).order_by("-count")
    )

    context = {
        "latest_build": latest_build,
        "recent_builds": recent_builds,
        "latest_ratio_study": latest_ratio_study,
        "recent_ratio_studies": recent_ratio_studies,
        "dataset_count": ModelSFRSalesDataset.objects.count(),
        "exclusion_count": ModelSFRSalesExclusion.objects.count(),
        "land_summary_count": ModelLandSummary.objects.count(),
        "improvement_summary_count": ModelImprovementSummary.objects.count(),
        "exclusion_breakdown": exclusion_breakdown,
        "sample_rows": ModelSFRSalesDataset.objects.order_by("-sale_date")[:15],
        "model_comparison": latest_ratio_study.model_comparison if latest_ratio_study else [],
    }
    return render(request, "regression/dashboard.html", context)


@staff_member_required
def neighborhoods(request):
    running = background.is_run_in_progress()
    recent_loop_runs = list(SFRComplianceLoopRun.objects.order_by("-started_at")[:5])
    segments = SFRSegmentModel.objects.order_by("-sample_count")

    context = {
        "running": running,
        "recent_loop_runs": recent_loop_runs,
        "segments": segments,
        "recent_years": compliance_runner.DEFAULT_RECENT_YEARS,
        "ai_model": ai_reasoning.AI_MODEL,
        "ai_max_rounds": ai_reasoning.MAX_AI_ROUNDS,
    }
    return render(request, "regression/neighborhoods.html", context)


@staff_member_required
@require_POST
def run_all_neighborhoods(request):
    run = background.start_compliance_loop_run()
    if run is None:
        messages.warning(request, "A compliance loop run is already in progress -- wait for it to finish before starting another.")
    else:
        messages.success(request, "Started a whole-county compliance loop run in the background. This page will refresh automatically.")
    return redirect(reverse("regression:neighborhoods"))


@staff_member_required
@require_POST
def run_one_neighborhood(request):
    segment_value = request.POST.get("segment_value", "")
    if not segment_value:
        messages.error(request, "No neighborhood specified.")
        return redirect(reverse("regression:neighborhoods"))
    run = background.start_compliance_loop_run(segment_scope=segment_value)
    if run is None:
        messages.warning(request, "A compliance loop run is already in progress -- wait for it to finish before starting another.")
    else:
        messages.success(request, f"Started a run for {segment_value} in the background. This page will refresh automatically.")
    return redirect(reverse("regression:neighborhoods"))
