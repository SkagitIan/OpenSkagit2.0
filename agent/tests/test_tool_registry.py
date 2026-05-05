from agent.tools.registry import find_tools_by_trigger, get_tool, list_tools, load_registry


def test_registry_loads():
    registry = load_registry()
    assert "tools" in registry
    assert isinstance(registry["tools"], list)


def test_notify_tool_registered():
    tool = get_tool("notify")
    assert tool is not None
    assert tool["id"] == "notify"
    assert "email" in tool.get("channels_supported", [])


def test_find_tools_by_trigger_email():
    tools = find_tools_by_trigger("notify me by email when this is done")
    ids = [tool["id"] for tool in tools]
    assert "notify" in ids


def test_find_tools_by_trigger_no_match():
    tools = find_tools_by_trigger("what is the zoning for P48165")
    assert tools == []


def test_list_tools_returns_list():
    tools = list_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 1
