import json

import pytest

from gui_control.targets import ObjectMap, ObjectMapLocationUnset, propose, resolve


def test_points_and_raw_selectors_bypass_the_map():
    assert resolve("10,20", None) == ("point", (10.0, 20.0))
    assert resolve("Button[0]", ObjectMap({})) == ("selector", "Button[0]")


def test_lowercase_bare_word_means_object_name():
    assert resolve("okButton", ObjectMap({})) == ("selector", "#okButton")
    assert resolve("nope", None) == ("selector", "#nope")


def test_map_name_wins_over_bare_object_name():
    assert resolve("home", ObjectMap({"home": "HomePage"})) == ("selector", "HomePage")


def test_uppercase_and_structured_targets_stay_selectors():
    for target in ("Button", "#x", "a/b", "a[0]", "a=b", "a b", "a,b"):
        assert resolve(target, ObjectMap({})) == ("selector", target)


def test_at_name_needs_a_map_location():
    with pytest.raises(ObjectMapLocationUnset):
        resolve("@ok", ObjectMap({}))


def test_unknown_at_name_lists_known_ones(tmp_path):
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({"names": {"ok": "#okButton"}}))
    with pytest.raises(KeyError, match="known: ok"):
        resolve("@nope", ObjectMap.load(map_file))


def test_environment_names_the_map(monkeypatch, tmp_path):
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({"names": {"ok": {"selector": "#okButton", "note": "confirm"}}}))
    monkeypatch.setenv("GUI_CONTROL_OBJECTMAP", str(map_file))
    assert resolve("@ok", ObjectMap.load()) == ("selector", "#okButton")


def test_without_location_the_map_is_empty_and_cannot_be_saved(monkeypatch):
    monkeypatch.delenv("GUI_CONTROL_OBJECTMAP", raising=False)
    object_map = ObjectMap.load()
    assert object_map.entries == {}
    with pytest.raises(ObjectMapLocationUnset):
        object_map.save()


def test_add_and_save_round_trip(tmp_path):
    map_file = tmp_path / "nested" / "map.json"
    object_map = ObjectMap.load(map_file)
    object_map.add("ok", "#okButton", note="confirm")
    object_map.add("cancel", "Button[text=Cancel]")
    object_map.save()
    reloaded = ObjectMap.load(map_file)
    assert reloaded.names() == ["cancel", "ok"]
    assert reloaded.selector_for("ok") == "#okButton"
    assert reloaded.selector_for("cancel") == "Button[text=Cancel]"


def test_propose_prefers_unique_object_name_then_type_then_text_then_index():
    tree = {
        "type": "QQuickRootItem",
        "children": [
            {"type": "Button", "objectName": "okButton", "props": {"text": "OK"}},
            {"type": "Label", "props": {"text": "Hello world"}},
            {"type": "Label", "props": {"text": "Bye"}},
            {"type": "Label", "props": {"text": "Bye"}},
        ],
    }
    selectors = {proposal["selector"] for proposal in propose(tree)}
    assert "#okButton" in selectors
    assert "QQuickRootItem" in selectors
    assert "Label[text=Hello world]" in selectors
    assert {"Label[1]", "Label[2]"} <= selectors
    names = [proposal["name"] for proposal in propose(tree)]
    assert "helloWorld" in names
