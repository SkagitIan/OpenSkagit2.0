from parcelbook_ai.zoning_router import detect_zoning_need


def test_adu_candidates_are_parcel_first():
    result = detect_zoning_need("Find ADU candidates in Mount Vernon")
    assert result["needs_zoning"] is True
    assert result["mode"] == "parcel_first"
    assert result["proposed_use"] == "accessory dwelling unit"


def test_pure_parcel_search_is_none():
    assert detect_zoning_need("Find older houses on big lots")["needs_zoning"] is False


def test_restaurant_zoning_only():
    result = detect_zoning_need("Which zones allow restaurants?")
    assert result["mode"] == "zoning_only"
    assert result["proposed_use"] == "restaurant"


def test_restaurant_zoning_first():
    result = detect_zoning_need("Find parcels in zones where restaurants are allowed")
    assert result["mode"] == "zoning_first"
    assert result["proposed_use"] == "restaurant"
