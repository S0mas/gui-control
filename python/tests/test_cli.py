from fake_hook import FakeHook
from gui_control import cli
from gui_control.client import ControlError

TREE = {
    "type": "QQuickRootItem",
    "rect": {"x": 0, "y": 0, "width": 400, "height": 300},
    "children": [{"type": "Button", "objectName": "okButton", "rect": {}, "props": {"text": "OK"}}],
}


def _answer(request):
    if request["op"] == "ping":
        return {"ok": True, "window": True, "width": 400, "height": 300, "title": "Demo"}
    if request["op"] == "tree":
        return {"ok": True, "tree": TREE}
    if request["op"] == "get":
        return {"ok": False, "error": f"selector '{request['selector']}' matched 2 items", "candidates": [{"type": "Button", "rect": {}}]}
    return {"ok": True}


def test_common_flags_work_before_and_after_the_verb():
    parser = cli.build_parser()
    assert parser.parse_args(["--port", "9", "screen"]).port == 9
    assert parser.parse_args(["screen", "--port", "9"]).port == 9
    assert parser.parse_args(["screen"]).port is None


def test_screen_prints_window_line_and_compact_tree(capsys):
    with FakeHook(_answer) as hook:
        assert cli.main(["--port", str(hook.port), "screen"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "window 'Demo' 400x300",
        'Button #okButton (0,0 0x0)  text="OK"',
    ]


def test_ambiguous_target_reports_status_candidates_and_screen(capsys):
    with FakeHook(_answer) as hook:
        assert cli.main(["--port", str(hook.port), "get", "Button", "text"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: selector 'Button' matched 2 items\nstatus: AMBIGUOUS\ncandidates:\n  Button (0,0 0x0)\n")
    assert "window 'Demo' 400x300" in err


def test_classify_only_targeted_commands():
    assert cli.classify("tap", ControlError("selector 'x' matched nothing")) == "OBJECT_NOT_FOUND"
    assert cli.classify("wait", ControlError("selector 'x' was still absent after 5 ms")) == "OBJECT_NOT_FOUND"
    assert cli.classify("get", ControlError("selector 'x' matched 4 items")) == "AMBIGUOUS"
    assert cli.classify("screen", ControlError("selector 'x' matched nothing")) is None
    assert cli.classify("tap", ControlError("hook closed the connection")) is None


def test_unreachable_hook_exits_2(capsys):
    assert cli.main(["--port", "1", "ping"]) == 2
    assert "not reachable" in capsys.readouterr().err


def test_set_parses_json_values():
    assert cli.value_of("5") == 5
    assert cli.value_of('"5"') == "5"
    assert cli.value_of("plain") == "plain"
