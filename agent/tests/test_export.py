import json

from agent.export import to_json, to_markdown


SAMPLE_CASE_FILE = {
    "id": "cf_test123",
    "question": "Tell me about parcel P48165",
    "entity": "P48165",
    "evidence": [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit County Parcels",
            "data": {"PARCELID": "P48165", "OWNER": "SWANSON EARLINE"},
            "count": 1,
        }
    ],
    "missing": ["flood"],
    "confidence": "medium",
    "answer": "Parcel P48165 is owned by SWANSON EARLINE.",
    "sources_queried": ["skagit_parcels"],
    "created_at": "2025-01-01T00:00:00Z",
}


def test_to_json_is_valid():
    output = to_json(SAMPLE_CASE_FILE)
    parsed = json.loads(output)
    assert parsed["id"] == "cf_test123"


def test_to_markdown_contains_key_fields():
    output = to_markdown(SAMPLE_CASE_FILE)
    assert "P48165" in output
    assert "SWANSON EARLINE" in output
    assert "medium" in output.lower()
    assert "Missing Evidence" in output
    assert "flood" in output


def test_to_markdown_caps_evidence_records():
    big_cf = {**SAMPLE_CASE_FILE}
    big_cf["evidence"] = [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit Parcels",
            "data": [{"PARCELID": f"P{i}"} for i in range(100)],
            "count": 100,
        }
    ]
    output = to_markdown(big_cf)
    assert output.count("P1") == 1
