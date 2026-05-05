from agent.config import feature_enabled, tenant


def test_tenant_returns_dict():
    t = tenant()
    assert isinstance(t, dict)
    assert "display_name" in t


def test_feature_enabled_returns_bool():
    result = feature_enabled("notifications")
    assert isinstance(result, bool)


def test_feature_missing_returns_false():
    result = feature_enabled("nonexistent_feature_xyz")
    assert result is False
