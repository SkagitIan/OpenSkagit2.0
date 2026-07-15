from __future__ import annotations

from django.db import DatabaseError
from django.utils import timezone

from .ai_search import DEFAULT_RESULT_LIMIT
from .models import OpportunitySearch, PublicIntelligenceExample


PUBLIC_INTELLIGENCE_EXAMPLES = [
    {
        "slug": "large-homes-under-500k",
        "search_id": 35,
        "question": "Find homes over 3,000 square feet under $500k in Sedro-Woolley, La Conner, or Conway.",
        "source_context": ["Assessor", "improvements", "zoning"],
        "sort_order": 10,
    },
    {
        "slug": "senior-living-candidates",
        "search_id": 34,
        "question": "Find large homes or commercial buildings in Conway or La Conner that could be explored for senior living.",
        "source_context": ["Assessor", "improvements", "zoning"],
        "sort_order": 20,
    },
    {
        "slug": "low-quality-acre-homes",
        "search_id": 32,
        "question": "Find low-quality homes on 1-3 acre residential lots.",
        "source_context": ["Assessor", "improvements", "zoning"],
        "sort_order": 30,
    },
    {
        "slug": "sedro-low-quality-homes",
        "search_id": 26,
        "question": "Find low-quality residential dwellings on 1-3 acres around Sedro-Woolley.",
        "source_context": ["Assessor", "improvements", "zoning"],
        "sort_order": 40,
    },
    {
        "slug": "vacant-served-land",
        "search_id": 17,
        "question": "Find vacant 1-5 acre parcels with utility signals and moderate assessed value.",
        "source_context": ["Assessor", "land", "utilities"],
        "sort_order": 50,
    },
    {
        "slug": "multiunit-no-recent-sale",
        "search_id": 10,
        "question": "Find multi-unit buildings with no sale activity in the last 15 years.",
        "source_context": ["Assessor", "improvements", "sales"],
        "sort_order": 60,
    },
    {
        "slug": "recreation-utility-land",
        "search_id": 3,
        "question": "Find recreation or small bare-land parcels with utility signals under $200k assessed value.",
        "source_context": ["Assessor", "land", "utilities", "zoning"],
        "sort_order": 70,
    },
    {
        "slug": "sedro-vacant-parcels",
        "search_id": 8,
        "question": "Find vacant parcels in Sedro-Woolley.",
        "source_context": ["Assessor", "land use", "zoning"],
        "sort_order": 80,
    },
    {
        "slug": "adult-care-candidates",
        "search_id": 2,
        "question": "Find buildings in Conway that could be explored for an adult-care facility with up to five rooms.",
        "source_context": ["Assessor", "improvements", "zoning"],
        "sort_order": 90,
    },
    {
        "slug": "small-senior-community-set",
        "search_id": 11,
        "question": "Find low-quality homes on 1-3 acre parcels in Sedro-Woolley.",
        "source_context": ["Assessor", "improvements", "zoning"],
        "sort_order": 100,
    },
]


def sync_public_intelligence_examples() -> int:
    synced = 0
    for definition in PUBLIC_INTELLIGENCE_EXAMPLES:
        search = OpportunitySearch.objects.filter(
            pk=definition["search_id"],
            status=OpportunitySearch.STATUS_READY,
        ).first()
        if not search:
            continue
        count_is_capped = search.result_count >= DEFAULT_RESULT_LIMIT
        PublicIntelligenceExample.objects.update_or_create(
            slug=definition["slug"],
            defaults={
                "search": search,
                "question": definition["question"],
                "public_title": search.title or definition["question"],
                "source_context": definition["source_context"],
                "result_count": search.result_count,
                "count_is_capped": count_is_capped,
                "refreshed_at": search.updated_at or timezone.now(),
                "sort_order": definition["sort_order"],
                "is_active": True,
                "status": OpportunitySearch.STATUS_READY,
            },
        )
        synced += 1
    return synced


def public_home_examples(limit: int = 10) -> list[dict]:
    try:
        examples = PublicIntelligenceExample.objects.filter(
            is_active=True,
            status=OpportunitySearch.STATUS_READY,
        ).order_by("sort_order", "slug")[:limit]
        rows = list(examples)
    except DatabaseError:
        return []
    return [
        {
            "question": example.question,
            "count_label": example.count_label,
            "source_context": example.source_context,
            "refreshed_at": example.refreshed_at,
        }
        for example in rows
    ]
