from parcelbook_ai.schema_guide import get_parcel_search_semantic_guide


def test_schema_guide_contains_required_semantics():
    guide = get_parcel_search_semantic_guide()
    assert guide
    assert "primary_building_living_area" in guide
    assert "do not use zoning_code_short or zoning_label as a legal determination" in guide
