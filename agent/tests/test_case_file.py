from agent.case_file import build


def test_case_file_build_with_evidence():
    evidence = [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit Parcels",
            "data": {"PARCELID": "P48165", "OWNER": "TEST"},
            "retrieved_at": "2025-01-01T00:00:00Z",
        },
        {
            "source_id": "skagit_zoning",
            "source_name": "Skagit Zoning",
            "data": {"ZONE_CODE": "RR-5"},
            "retrieved_at": "2025-01-01T00:00:00Z",
        },
    ]
    cf = build("Tell me about parcel P48165", "P48165", evidence, [])
    assert cf["id"].startswith("cf_")
    assert cf["confidence"] == "high"
    assert len(cf["evidence"]) == 2
    assert len(cf["missing"]) == 0
    assert cf["entity"] == "P48165"


def test_case_file_low_confidence_when_no_evidence():
    cf = build("Tell me about parcel P48165", "P48165", [], ["parcels", "zoning"])
    assert cf["confidence"] == "low"


def test_case_file_medium_confidence_with_gaps():
    evidence = [
        {
            "source_id": "skagit_parcels",
            "source_name": "Skagit Parcels",
            "data": {"PARCELID": "P48165"},
            "retrieved_at": "2025-01-01T00:00:00Z",
        }
    ]
    cf = build("Tell me about parcel P48165", "P48165", evidence, ["zoning", "flood"])
    assert cf["confidence"] == "medium"
