from agent.pdf import build_pdf


SAMPLE_CASE_FILE = {
    "id": "cf_test123",
    "entity": "P48165",
    "question": "Tell me about parcel P48165",
    "confidence": "medium",
    "answer": "Parcel P48165 is a 6.5 acre parcel owned by SWANSON EARLINE.",
    "evidence": [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit County Parcels",
            "data": [{"PARCELID": "P48165", "OWNER": "SWANSON EARLINE", "Acres": 6.5}],
            "count": 1,
        }
    ],
    "missing": ["flood"],
    "sources_queried": ["skagit_parcels"],
    "created_at": "2025-01-01T00:00:00Z",
}


def test_build_pdf_returns_bytes():
    result = build_pdf(SAMPLE_CASE_FILE)
    assert isinstance(result, bytes)
    assert len(result) > 1000


def test_build_pdf_starts_with_pdf_header():
    result = build_pdf(SAMPLE_CASE_FILE)
    assert result[:4] == b"%PDF"


def test_build_pdf_handles_empty_evidence():
    cf = {**SAMPLE_CASE_FILE, "evidence": [], "missing": []}
    result = build_pdf(cf)
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"


def test_build_pdf_handles_long_answer():
    cf = {**SAMPLE_CASE_FILE, "answer": "A" * 2000}
    result = build_pdf(cf)
    assert isinstance(result, bytes)
