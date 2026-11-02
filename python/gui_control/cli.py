import argparse
import json
import re
import sys
from datetime import datetime

from . import render
from .client import ControlError, GuiClient
from .gui import SETTLE_QUIET_MS, SETTLE_TIMEOUT_MS, Gui
from .targets import ObjectMap, ObjectMapLocationUnset, propose

TARGETED_COMMANDS = ("tap", "long-press", "swipe", "scroll", "get", "set", "invoke", "wait")
NOT_FOUND_PATTERN = re.compile(r"matched nothing|still absent")
AMBIGUOUS_PATTERN = re.compile(r"matched \d+ items")
NOT_FOUND_HINT = (
    "hint: plain text is not a selector; match visible text with Type[text=...] (e.g. Button[text=OK]), "
    'an @name from `gui-control map list`, or a point "x,y"'
)


def value_of(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def window_line(window):
    if not window.get("window"):
        return "no QQuickWindow yet"
    return f"window '{window.get('title', '')}' {window.get('width')}x{window.get('height')}"


def outcome_line(verb, target, outcome):
    line = f"{verb} {target}"
    if outcome.scrolled:
        line += " (scrolled into view)"
    if outcome.unsettled:
        line += f" (ui not settled: {outcome.unsettled})"
    return line


def cmd_ping(args, gui):
    print(f"hook up on {gui.client.host}:{gui.client.port}, {window_line(gui.window())}")
    return 0


def cmd_screen(args, gui):
    props = "all" if args.all_props else (args.props.split(",") if args.props else None)
    tree = gui.screen(args.target, depth=args.depth, props=props, hidden=args.hidden, all_props=args.all_props)
    if args.json:
        print(json.dumps(tree, indent=2))
        return 0
    if isinstance(tree, list) and not tree:
        print("no matches")
        return 1
    print(window_line(gui.window()))
    keep = render.keep_types_from_environment() | frozenset(args.keep.split(",") if args.keep else ())
    lines = render.render_tree(tree) if args.raw else render.render_compact_tree(tree, keep)
    print("\n".join(lines))
    return 0


def cmd_tap(args, gui):
    print(outcome_line("tapped", args.target, gui.tap(args.target, hidden=args.hidden)))
    return 0


def cmd_long_press(args, gui):
    outcome = gui.long_press(args.target, duration=args.duration, hidden=args.hidden)
    print(outcome_line("long-pressed", args.target, outcome))
    return 0


def cmd_swipe(args, gui):
    outcome = gui.swipe(args.target, args.to, duration=args.duration, hidden=args.hidden)
    print(outcome_line("swiped", f"{args.target} -> {args.to}", outcome))
    return 0


def cmd_scroll(args, gui):
    if args.direction == "to":
        if not args.target:
            raise ControlError("scroll to needs a target")
        rect, scrolled = gui.scroll_to(args.target, hidden=args.hidden)
        state = "scrolled into view" if scrolled else "already in view"
        print(f"{args.target} {state} at {rect.get('x', 0):.0f},{rect.get('y', 0):.0f}")
        return 0
    outcome = gui.scroll(args.direction, args.target, hidden=args.hidden)
    print(outcome_line("scrolled", f"{args.direction} in {args.target or 'QQuickListView'}", outcome))
    return 0


def cmd_type(args, gui):
    gui.type_text(args.text)
    print(f"typed {len(args.text)} characters")
    return 0


def cmd_key(args, gui):
    gui.key(args.name)
    print(f"pressed {args.name}")
    return 0


def cmd_get(args, gui):
    result = gui.get(args.target, args.prop, hidden=args.hidden)
    if args.prop or args.json:
        print(json.dumps(result, indent=None if args.prop else 2))
    else:
        print("\n".join(render.render(result)))
    return 0


def cmd_set(args, gui):
    value = value_of(args.value)
    gui.set(args.target, args.prop, value, hidden=args.hidden)
    print(f"{args.target}.{args.prop} = {json.dumps(value)}")
    return 0


def cmd_invoke(args, gui):
    print(json.dumps(gui.invoke(args.target, args.method, [value_of(arg) for arg in args.args], hidden=args.hidden)))
    return 0


def cmd_shot(args, gui):
    print(gui.shot(args.path or f"shot-{datetime.now():%Y%m%d-%H%M%S}.png"))
    return 0


def cmd_wait(args, gui):
    if args.mode == "settled":
        gui.wait_settled(quiet=args.quiet, timeout=args.timeout)
        print("settled")
        return 0
    if not args.target:
        raise ControlError(f"wait {args.mode} needs a target")
    if args.mode == "signal":
        if not args.signal:
            raise ControlError("wait signal needs --signal <name>")
        gui.wait_signal(args.target, args.signal, timeout=args.timeout, hidden=args.hidden)
        print(f"{args.signal} fired")
        return 0
    gui.wait_for(args.target, present=args.mode == "appears", timeout=args.timeout, hidden=args.hidden)
    print(f"{args.target} {args.mode}")
    return 0


def cmd_map(args, gui):
    object_map = gui.object_map
    if args.action == "list":
        object_map.require_location()
        if not object_map.entries:
            print(f"no object map entries in {object_map.path}")
            return 1
        for name in object_map.names():
            print(f"{name:40s} {object_map.selector_for(name)}")
        return 0
    if args.action == "add":
        object_map.add(args.name, args.selector, args.note)
        object_map.save()
        print(f"{args.name} -> {args.selector}  ({object_map.path})")
        return 0
    tree = gui.screen(args.target, depth=args.depth)
    if isinstance(tree, list):
        tree = {"type": "matches", "children": tree}
    for proposal in propose(tree):
        if args.named_only and not (proposal["text"] or proposal["name"]):
            continue
        text = f'  text="{proposal["text"]}"' if proposal["text"] else ""
        print(f"{proposal['name']:40s} {proposal['selector']}{text}")
    return 0


def common_parser(suppress):
    common = argparse.ArgumentParser(add_help=False)

    def default(value):
        return argparse.SUPPRESS if suppress else value

    common.add_argument("--host", default=default(None), help="hook host (default $GUI_CONTROL_HOST or 127.0.0.1)")
    common.add_argument("--port", type=int, default=default(None), help="hook port (default $GUI_CONTROL_PORT or 7801)")
    common.add_argument("--map", default=default(None), help="object map file (default $GUI_CONTROL_OBJECTMAP)")
    common.add_argument("--hidden", action="store_true", default=default(False), help="consider items that are not visible")
    common.add_argument("--json", action="store_true", default=default(False), help="machine-readable output where supported")
    common.add_argument("--no-settle", action="store_true", default=default(False), help="do not wait for the UI to settle after an action")
    return common


def build_parser():
    parser = argparse.ArgumentParser(
        prog="gui-control",
        description="Drive and inspect a running Qt Quick application that has libguicontrol.so loaded.",
        parents=[common_parser(False)],
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<verb>")
    parents = [common_parser(True)]

    def verb(name, func, help_text):
        command = sub.add_parser(name, help=help_text, parents=parents)
        command.set_defaults(func=func)
        return command

    verb("ping", cmd_ping, "is the hook up; window size and title")

    screen = verb("screen", cmd_screen, "compact item tree of the window (structure and values)")
    screen.add_argument("target", nargs="?", help="selector or object map name to scope the dump")
    screen.add_argument("--depth", type=int, default=None)
    screen.add_argument("--raw", action="store_true", help="every item with geometry and flags")
    screen.add_argument("--props", help="comma separated property whitelist")
    screen.add_argument("--all-props", action="store_true", help="include the properties every QQuickItem has")
    screen.add_argument("--keep", help="comma separated extra item types the compact view always shows")

    for name, func, help_text in (
        ("tap", cmd_tap, "click an item or point (scrolls it into view first)"),
        ("long-press", cmd_long_press, "press and hold an item or point"),
    ):
        command = verb(name, func, help_text)
        command.add_argument("target", help="object map name, selector, or 'x,y'")
        if name == "long-press":
            command.add_argument("--duration", type=int, default=0, help="ms; default is the platform press-and-hold time")

    swipe = verb("swipe", cmd_swipe, "drag from an item or point to a point")
    swipe.add_argument("target")
    swipe.add_argument("to", help="destination as 'x,y'")
    swipe.add_argument("--duration", type=int, default=300)

    scroll = verb("scroll", cmd_scroll, "scroll a list: down|up [container], or `to <target>` to bring an item into view")
    scroll.add_argument("direction", choices=["down", "up", "to"])
    scroll.add_argument("target", nargs="?", help="container to scroll (default QQuickListView), or the item for `to`")

    verb("type", cmd_type, "type text into the focused item").add_argument("text")
    verb("key", cmd_key, "press a named key (enter, escape, backspace, tab, up, down, ...)").add_argument("name")

    get = verb("get", cmd_get, "read a property, or dump one item with its subtree")
    get.add_argument("target")
    get.add_argument("prop", nargs="?")

    set_command = verb("set", cmd_set, "write a property (value as JSON)")
    set_command.add_argument("target")
    set_command.add_argument("prop")
    set_command.add_argument("value")

    invoke = verb("invoke", cmd_invoke, "call a method on an item (max 3 args, each as JSON)")
    invoke.add_argument("target")
    invoke.add_argument("method")
    invoke.add_argument("args", nargs="*")

    shot = verb("shot", cmd_shot, "save a PNG of the window (bare name lands in $GUI_CONTROL_SHOT_DIR when set)")
    shot.add_argument("path", nargs="?")

    wait = verb("wait", cmd_wait, "wait for the UI to settle, an item to appear/disappear, or a signal")
    wait.add_argument("mode", choices=["settled", "appears", "disappears", "signal"])
    wait.add_argument("target", nargs="?")
    wait.add_argument("--signal")
    wait.add_argument("--quiet", type=int, default=SETTLE_QUIET_MS)
    wait.add_argument("--timeout", type=int, default=SETTLE_TIMEOUT_MS)

    object_map = verb("map", cmd_map, "inspect or extend the object map of @names")
    map_actions = object_map.add_subparsers(dest="action", required=True)
    map_actions.add_parser("list")
    add = map_actions.add_parser("add")
    add.add_argument("name")
    add.add_argument("selector")
    add.add_argument("--note")
    generate = map_actions.add_parser("generate")
    generate.add_argument("target", nargs="?")
    generate.add_argument("--depth", type=int, default=12)
    generate.add_argument("--named-only", action="store_true")
    return parser


def classify(command, error):
    if command not in TARGETED_COMMANDS:
        return None
    message = str(error)
    if AMBIGUOUS_PATTERN.search(message):
        return "AMBIGUOUS"
    if NOT_FOUND_PATTERN.search(message) or error.candidates:
        return "OBJECT_NOT_FOUND"
    return None


def report_target_failure(status, error, gui):
    print(f"status: {status}", file=sys.stderr)
    if status == "OBJECT_NOT_FOUND":
        print(NOT_FOUND_HINT, file=sys.stderr)
    print("candidates:", file=sys.stderr)
    if error.candidates:
        print("\n".join(render.render_candidates(error.candidates)), file=sys.stderr)
    try:
        print(window_line(gui.window()), file=sys.stderr)
        print("\n".join(render.render_compact_tree(gui.screen(), render.keep_types_from_environment())), file=sys.stderr)
    except (ControlError, OSError):
        return


def run(args, gui):
    try:
        return args.func(args, gui)
    except ControlError as error:
        print(f"error: {error}", file=sys.stderr)
        status = classify(args.command, error)
        if status:
            report_target_failure(status, error, gui)
        elif error.candidates:
            print("candidates:", file=sys.stderr)
            print("\n".join(render.render_candidates(error.candidates)), file=sys.stderr)
        return 2
    except (KeyError, ObjectMapLocationUnset) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: connection failed or timed out: {error}", file=sys.stderr)
        return 2


def main(argv=None):
    args = build_parser().parse_args(argv)
    gui = Gui(GuiClient(args.host, args.port), ObjectMap.load(args.map), settle=not args.no_settle)
    try:
        return run(args, gui)
    finally:
        gui.close()


if __name__ == "__main__":
    sys.exit(main())
