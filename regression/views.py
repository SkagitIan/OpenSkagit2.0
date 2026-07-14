from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render

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
    latest_loop_run = SFRComplianceLoopRun.objects.order_by("-started_at").first()
    segments = SFRSegmentModel.objects.order_by("-sample_count")

    context = {
        "latest_loop_run": latest_loop_run,
        "segments": segments,
    }
    return render(request, "regression/neighborhoods.html", context)
