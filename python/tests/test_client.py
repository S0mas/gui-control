import pytest

from fake_hook import FakeHook
from gui_control.client import ControlError, GuiClient, screenshot_path


def _answer(request):
    if request["op"] == "get":
        return {"ok": False, "error": f"selector '{request['selector']}' matched nothing", "candidates": [{"type": "Button"}]}
    if request["op"] == "tree":
        return {"ok": True, "tree": {"type": "Root"}}
    return {"ok": True, "echo": request}


def test_request_sends_op_and_payload_as_one_json_line():
    with FakeHook(_answer) as hook, GuiClient(port=hook.port) as client:
        client.tap(selector="#ok")
        client.tap(point=(10, 20))
        client.key("enter")
    assert hook.requests == [
        {"op": "tap", "selector": "#ok", "hidden": False},
        {"op": "tap", "x": 10, "y": 20, "hidden": False},
        {"op": "key", "key": "enter"},
    ]


def test_tree_leaves_the_property_choice_to_the_backend_unless_asked():
    with FakeHook(_answer) as hook, GuiClient(port=hook.port) as client:
        assert client.tree() == {"type": "Root"}
        client.tree(props=["text"])
        client.tree(all_props=True)
    assert "props" not in hook.requests[0]
    assert hook.requests[1]["props"] == ["text"]
    assert hook.requests[2]["all_props"] is True


def test_get_without_prop_asks_for_every_declared_property():
    with FakeHook(lambda request: {"ok": True, "item": {"type": "Button"}}) as hook, GuiClient(port=hook.port) as client:
        assert client.get("#ok") == {"type": "Button"}
    assert hook.requests[0]["props"] == "*"


def test_hook_failure_raises_with_candidates_and_response():
    with FakeHook(_answer) as hook, GuiClient(port=hook.port) as client:
        with pytest.raises(ControlError, match="matched nothing") as raised:
            client.get("#nope")
    assert raised.value.candidates == [{"type": "Button"}]
    assert raised.value.answered_by_hook


def test_unreachable_hook_is_a_control_error_without_response():
    client = GuiClient(port=1)
    with pytest.raises(ControlError, match="not reachable") as raised:
        client.ping()
    assert not raised.value.answered_by_hook


def test_target_needs_selector_or_point():
    with pytest.raises(ControlError, match="selector or a point"):
        GuiClient(port=1).tap()


def test_environment_sets_host_and_port(monkeypatch):
    monkeypatch.setenv("GUI_CONTROL_HOST", "10.0.0.2")
    monkeypatch.setenv("GUI_CONTROL_PORT", "7999")
    client = GuiClient()
    assert (client.host, client.port) == ("10.0.0.2", 7999)


def test_screenshot_path_is_absolute_and_uses_shot_dir_for_bare_names(monkeypatch, tmp_path):
    monkeypatch.delenv("GUI_CONTROL_SHOT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert screenshot_path("a.png") == str(tmp_path / "a.png")
    monkeypatch.setenv("GUI_CONTROL_SHOT_DIR", str(tmp_path / "shots"))
    assert screenshot_path("a.png") == str(tmp_path / "shots" / "a.png")
    assert (tmp_path / "shots").is_dir()
    assert screenshot_path("sub/b.png") == str(tmp_path / "sub" / "b.png")
