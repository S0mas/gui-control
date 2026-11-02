import pytest

from gui_control.client import ControlError
from gui_control.gui import Gui
from gui_control.targets import ObjectMap

WINDOW = {"ok": True, "window": True, "width": 400, "height": 300}


class FakeClient:
    def __init__(self, items=None, settle_error=None):
        self.items = items or {}
        self.settle_error = settle_error
        self.calls = []

    def ping(self):
        return WINDOW

    def get(self, selector, prop=None, hidden=False):
        self.calls.append(("get", selector))
        states = self.items.get(selector)
        if not states:
            raise ControlError(f"selector '{selector}' matched nothing", response={"ok": False})
        return dict(states.pop(0) if len(states) > 1 else states[0])

    def scroll(self, selector, hidden=False):
        self.calls.append(("scroll", selector))
        return {"ok": True, "scrolled": True, "rect": {"x": 10, "y": 10, "width": 20, "height": 20}}

    def tap(self, **target):
        self.calls.append(("tap", target))
        return {"ok": True}

    def swipe(self, **arguments):
        self.calls.append(("swipe", arguments))
        return {"ok": True}

    def wait_settled(self, quiet, timeout):
        self.calls.append(("settle", quiet, timeout))
        if self.settle_error:
            raise self.settle_error
        return {"ok": True}


def _item(x=10, y=10, **flags):
    return {"rect": {"x": x, "y": y, "width": 20, "height": 20}, **flags}


def test_tap_waits_until_the_item_is_enabled_then_settles():
    client = FakeClient({"#ok": [_item(enabled=False), _item()]})
    outcome = Gui(client, ObjectMap({})).tap("ok")
    assert [call[0] for call in client.calls] == ["get", "get", "tap", "settle"]
    assert client.calls[2] == ("tap", {"selector": "#ok", "hidden": False})
    assert outcome.unsettled is None


def test_tap_scrolls_an_item_outside_the_window_into_view():
    client = FakeClient({"#far": [_item(y=900)]})
    assert Gui(client, ObjectMap({})).tap("far").scrolled
    assert ("scroll", "#far") in client.calls


def test_tap_on_a_point_skips_the_interactable_wait():
    client = FakeClient()
    Gui(client, ObjectMap({})).tap("5,6")
    assert client.calls[0] == ("tap", {"point": (5.0, 6.0), "hidden": False})


def test_item_that_never_appears_fails_after_the_timeout():
    gui = Gui(FakeClient(), ObjectMap({}), timeout=100)
    with pytest.raises(ControlError, match="did not become interactable within 100 ms \\(absent\\)"):
        gui.tap("missing")


def test_unsettled_ui_is_reported_not_raised():
    client = FakeClient({"#ok": [_item()]}, ControlError("ui did not settle within 8000 ms", response={"ok": False}))
    assert Gui(client, ObjectMap({})).tap("ok").unsettled == "ui did not settle within 8000 ms"


def test_lost_connection_during_settle_is_raised():
    client = FakeClient({"#ok": [_item()]}, ControlError("gui-control hook closed the connection"))
    with pytest.raises(ControlError, match="closed"):
        Gui(client, ObjectMap({})).tap("ok")


def test_settle_can_be_switched_off():
    client = FakeClient({"#ok": [_item()]})
    Gui(client, ObjectMap({}), settle=False).tap("ok")
    assert "settle" not in [call[0] for call in client.calls]


def test_scroll_down_swipes_from_low_to_high_inside_the_container():
    client = FakeClient({"QQuickListView": [{"rect": {"x": 0, "y": 100, "width": 200, "height": 100}}]})
    Gui(client, ObjectMap({})).scroll("down")
    swipe = next(call[1] for call in client.calls if call[0] == "swipe")
    assert swipe["point"] == (100, 180)
    assert (swipe["to_x"], swipe["to_y"]) == (100, 120)


def test_swipe_destination_must_be_a_point():
    with pytest.raises(ControlError, match="x,y"):
        Gui(FakeClient(), ObjectMap({})).swipe("5,5", "Button")
