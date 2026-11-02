import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from gui_control import cli
from gui_control.client import GuiClient
from gui_control.gui import Gui
from gui_control.targets import ObjectMap

REPOSITORY = Path(__file__).resolve().parents[2]
HOOK_LIBRARY = Path(os.environ.get("GUI_CONTROL_LIB", REPOSITORY / "build" / "libguicontrol.so"))
QML_RUNTIME = os.environ.get("GUI_CONTROL_QML") or shutil.which("qml")
DEMO = REPOSITORY / "examples" / "demo.qml"

pytestmark = pytest.mark.skipif(
    not HOOK_LIBRARY.is_file() or not QML_RUNTIME,
    reason="needs the built hook library and a qml runtime (set GUI_CONTROL_LIB / GUI_CONTROL_QML)",
)


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def demo():
    port = _free_port()
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", GUI_CONTROL_PORT=str(port))
    environment["LD_PRELOAD"] = str(HOOK_LIBRARY)
    application = subprocess.Popen(
        [QML_RUNTIME, str(DEMO)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    try:
        GuiClient(port=port).wait_ready(timeout=30)
        yield port
    finally:
        application.terminate()
        application.wait(timeout=10)


@pytest.fixture
def gui(demo):
    with Gui(GuiClient(port=demo), ObjectMap({})) as driver:
        yield driver


def test_window_is_reported(gui):
    window = gui.window()
    assert (window["width"], window["height"], window["title"]) == (480, 640, "gui-control demo")


def test_ping_reports_the_backend_its_ops_and_content_props(gui):
    window = gui.window()
    assert window["backend"] == "qtquick"
    assert {"tap", "tree", "screenshot", "wait"} <= set(window["ops"])
    assert "text" in window["content_props"]


def test_items_carry_roles(gui):
    roles = {target: gui.get(target)["role"] for target in ("incrementButton", "counterLabel", "nameField", "darkSwitch", "fruitList", "homePage")}
    assert roles == {
        "incrementButton": "button",
        "counterLabel": "text",
        "nameField": "input",
        "darkSwitch": "button",
        "fruitList": "scrollable",
        "homePage": "page",
    }


def test_role_selects_items(gui):
    assert gui.get("[role=scrollable][0]", "objectName") == "fruitList"
    assert gui.get("[role=input]", "objectName") == "nameField"


def test_tap_clicks_a_button(gui):
    before = gui.get("counterLabel", "count")
    outcome = gui.tap("Button[text=Increment]")
    assert outcome.unsettled is None
    assert gui.get("counterLabel", "count") == before + 1
    assert gui.get("counterLabel", "text") == f"Clicked {before + 1} times"


def test_set_and_invoke_reach_qml_properties_and_functions(gui):
    gui.set("counterLabel", "count", 7)
    assert gui.get("counterLabel", "text") == "Clicked 7 times"
    assert gui.invoke("counterLabel", "summary", ["n="]) == "n=7"


def test_typing_and_keys_go_to_the_focused_field(gui):
    gui.tap("nameField")
    gui.type_text("Ada")
    gui.key("backspace")
    assert gui.get("nameField", "text") == "Ad"


def test_switch_toggles(gui):
    checked = gui.get("darkSwitch", "checked")
    gui.tap("darkSwitch")
    assert gui.get("darkSwitch", "checked") is not checked


def test_stack_navigation_waits_for_the_transition(gui):
    gui.tap("detailsButton")
    gui.wait_for("detailsPage")
    gui.tap("backButton")
    gui.wait_for("detailsPage", present=False)
    assert gui.get("homePage", "title") == "Home"


def test_tap_scrolls_a_list_item_into_view(gui):
    outcome = gui.tap("ItemDelegate[text=Fruit 25]")
    assert outcome.scrolled


def test_scroll_down_moves_the_first_scrollable_item(gui):
    gui.set("fruitList", "contentY", 0)
    gui.scroll("down")
    assert gui.get("fruitList", "contentY") > 0


def test_screenshot_writes_a_png(gui, tmp_path):
    path = gui.shot(str(tmp_path / "demo.png"))
    assert Path(path).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_screen_shows_the_compact_tree(demo, capsys):
    assert cli.main(["--port", str(demo), "screen"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("window 'gui-control demo' 480x640\n")
    assert "#incrementButton" in out
    assert 'text="Increment"' in out


def test_cli_reports_a_missing_target_with_candidates(demo, capsys):
    assert cli.main(["--port", str(demo), "get", "Button[text=Nope]", "text"]) == 2
    err = capsys.readouterr().err
    assert "matched nothing" in err
    assert "status: OBJECT_NOT_FOUND" in err
    assert "#incrementButton" in err
