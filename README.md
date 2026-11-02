# gui-control

Drive and inspect a running Qt Quick application from the outside: read its item tree, tap, swipe, type,
read and write properties, call QML functions, take screenshots and wait for the UI to settle. The
application needs no code changes. A small library is preloaded into its process and answers JSON
commands on a local TCP port. A Python client and a command line sit on top of it, so scripts, tests
and AI agents can drive the UI.

## How it works

- `libguicontrol.so` is loaded into the application with `LD_PRELOAD`. The application's source and
  build stay unchanged.
- When the `QGuiApplication` starts, the library opens a TCP server inside the process (port 7801 on
  127.0.0.1 by default). In a process without a GUI it does nothing.
- Each request is one line of JSON, and so is each reply. The server runs on the GUI thread, so every
  command sees the same live object tree the application renders.
- **Reading:** the server walks the `QQuickItem` tree of the first visible `QQuickWindow` and returns
  each item's QML type, `objectName`, scene rectangle, visibility and properties.
- **Finding:** items are addressed with a small selector language: type, `#objectName`,
  `[property=value]`, `[index]` and nesting (`/`).
- **Acting:** taps, long presses and swipes are real Qt mouse events sent to the window at the item's
  centre, so they take the same path as a user's input. An item that sits outside a `Flickable`'s
  viewport is scrolled into view first. Text and keys are sent as Qt key events to the focused item.
- **Direct access:** any property can be read or written, and any invokable method or QML function
  can be called.
- **Screenshots:** the window grabs itself (`QQuickWindow::grabWindow`), so screenshots work headless
  with `QT_QPA_PLATFORM=offscreen`.
- **Waiting:** until no frame has been rendered for a quiet period, until a `StackView` transition has
  finished, until an item appears or disappears, or until a signal fires.

## Requirements

- Linux (the hook is injected with `LD_PRELOAD`).
- Qt 6 with Core, Gui, Quick and Network. Build the hook against the same Qt installation the
  application runs with.
- CMake 3.21 or newer and a C++20 compiler.
- Python 3.9 or newer for the client. It needs nothing beyond the standard library.

## Build the hook

    cmake -S . -B build -DCMAKE_PREFIX_PATH=$HOME/Qt/6.8.1/gcc_64
    cmake --build build

The build writes `build/libguicontrol.so` and `build/gui-control-launch`.

## Start an application with the hook

    bin/gui-control-run ./my-qt-quick-app --its-arguments
    bin/gui-control-run qml examples/demo.qml
    QT_QPA_PLATFORM=offscreen GUI_CONTROL_PORT=7900 bin/gui-control-run ./my-qt-quick-app

`gui-control-run` puts the library in front of `LD_PRELOAD` and starts the command. The application
logs `[gui-control] listening on 127.0.0.1:7801` once the server is up.

When a wrapper you do not control starts the application (a dynamic loader, an SDK run script) and
would reset `LD_PRELOAD`, put `build/gui-control-launch` where the application binary would go, and
set `GUI_CONTROL_TARGET` to the real binary and `GUI_CONTROL_LIB` to the library. The launcher sets
`LD_PRELOAD` at the last moment and replaces itself with the target, keeping any loader prefix on the
command line.

## Command line

Install with `pip install -e python`, or run `bin/gui-control` from the checkout without installing.

    gui-control ping                               is the hook up; window title and size
    gui-control screen                             compact item tree: types, objectNames, rects, text and values
    gui-control screen --raw                       every item with every reported property
    gui-control screen '#settingsPage'             only the subtree under a selector
    gui-control tap '#okButton'                    tap an item (waits until it is enabled and on screen)
    gui-control tap 'Button[text=Save]'            tap by visible text
    gui-control tap 240,320                        tap a window coordinate
    gui-control long-press '#item' --duration 1500
    gui-control swipe '#list' 240,100              drag from an item to a point
    gui-control scroll down '#list'                scroll a list by 60% of its height
    gui-control scroll to 'ItemDelegate[text=Row 12]'
    gui-control type 'hello'                       type into the focused item
    gui-control key enter                          enter, escape, backspace, delete, tab, space, arrows, home, end, back
    gui-control get '#slider' value                read one property (JSON)
    gui-control get '#slider'                      dump one item with its subtree
    gui-control set '#slider' value 42             write a property (value parsed as JSON)
    gui-control invoke '#model' reload             call a method or QML function (at most 3 JSON arguments)
    gui-control shot screen.png                    PNG of the window
    gui-control wait settled                       no new frame for 300 ms
    gui-control wait appears '#dialog' --timeout 5000
    gui-control wait signal '#button' --signal clicked

Options that apply to every verb: `--host`, `--port`, `--map <file>`, `--hidden` (also match items
that are not visible), `--json`, and `--no-settle`. After every tap, long press, swipe or scroll the
command waits until the UI has settled. When the UI keeps animating it prints the action with
`(ui not settled: …)` rather than failing.

When a target matches nothing or several items, the command exits with status 2 and prints the status
(`OBJECT_NOT_FOUND` or `AMBIGUOUS`), the closest candidates and the current screen on stderr.

### The compact screen view

`screen` shows only the items worth reading. An item is kept when it has a content property (`text`,
`displayText`, `placeholderText`, `value`, `checked`, `currentValue`, `title`), when it has an
`objectName` and is not a plain container, when its type ends in `View`, when it is a popup, dialog,
drawer or overlay, or when its type is one of the Qt text, image and view types. Plain containers
(items, rectangles, mouse areas, layouts, positioners, repeaters, Qt's internal content items) are
left out, and their kept children move up a level. An item that only repeats the text of the item it
sits in, such as the label inside a button, is left out too. Add your application's own widget types with `--keep Gauge,Tile` or
`GUI_CONTROL_KEEP_TYPES=Gauge,Tile`.

Each line reads `Type #objectName (x,y wxh) [flags]  prop=value …`. Flags are `hidden`, `disabled`,
`opacity=` and `clip`.

## Selectors

| Form | Example | Matches |
|---|---|---|
| type | `Button` | items of that QML type |
| objectName | `#saveButton` | items with that `objectName` |
| both | `Button#saveButton` | type and `objectName` |
| predicate | `Button[text=Save]` | property equals value (compared as text) |
| index | `Button[2]` | the third match of that segment |
| predicate and index | `Label[text=Total][1]` | the second label whose text is Total |
| nesting | `SettingsPage/Switch[0]` | a descendant at any depth of an earlier match |
| map name | `@save` | the selector stored under that name in the object map |
| point | `240,320` | a window coordinate (tap, long press, swipe) |
| bare word | `saveButton` | a map name if there is one, else lowercase start → `#saveButton`, uppercase start → type |

The type is the class name of the item's meta object up to the first `_`. A QML component defined in
`Gauge.qml` therefore shows as `Gauge`, and a built-in item shows its C++ class, such as `QQuickText`
or `QQuickListView`.

## Object map

An object map gives stable names to selectors, so scripts do not break when a layout changes. It is a
JSON file named by `--map` or `GUI_CONTROL_OBJECTMAP`:

    {"names": {"save": "Button[text=Save]", "volume": {"selector": "#volumeSlider", "note": "settings page"}}}

    gui-control map generate                       propose a name and a unique selector for every item on screen
    gui-control map add save 'Button[text=Save]'
    gui-control map list
    gui-control tap @save

## Python

    from gui_control import Gui

    with Gui.connect(port=7801) as gui:
        gui.tap("Button[text=Increment]")
        assert gui.get("#counterLabel", "text") == "Clicked 1 times"
        gui.set("#volumeSlider", "value", 30)
        gui.wait_for("#detailsPage")
        gui.shot("/tmp/details.png")

`Gui` resolves targets through the object map, waits until a target is interactable, and settles after
each action. `GuiClient` is the raw protocol, with one method per command.

## Protocol

Send one JSON object per line and read one JSON object per line back. Every reply has `ok`. A failure
carries `error` and, when a selector did not resolve to one item, `candidates`.

| op | Request fields | Reply |
|---|---|---|
| `ping` | | `window`, `width`, `height`, `title` |
| `tree` | `selector`, `depth`, `hidden`, `props` (names), `all_props` | `tree`, or `matches` and `count` with a selector |
| `tap` | `selector`, or `x` and `y` | `scrolled` when the item had to be scrolled into view |
| `long_press` | as `tap`, plus `duration` in ms | as `tap` |
| `swipe` | as `tap`, plus `to_x`, `to_y`, `duration` | as `tap` |
| `scroll` | `selector` | `scrolled`, `rect` |
| `type` | `text` | |
| `key` | `key` | |
| `get` | `selector`, `prop` | `value`, or `item` without `prop` |
| `set` | `selector`, `prop`, `value` | |
| `invoke` | `selector`, `method`, `args` (at most 3) | `result` |
| `screenshot` | `path` (written by the application process) | `path` |
| `wait` | `mode` (`settled`, `transition`, `appears`, `disappears`, `signal`), `selector`, `signal`, `quiet`, `timeout` | |

Every op that takes a selector also accepts `hidden` to match items that are not visible.

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `GUI_CONTROL_PORT` | hook, client | TCP port (default 7801) |
| `GUI_CONTROL_BIND` | hook | address the server listens on (default 127.0.0.1) |
| `GUI_CONTROL_HOST` | client | address the client connects to (default 127.0.0.1) |
| `GUI_CONTROL_ENABLED` | hook | `0` keeps the hook loaded but switched off |
| `GUI_CONTROL_BLINKING_CARET` | hook | `1` keeps the text cursor blinking; it is off by default so screenshots are stable |
| `GUI_CONTROL_LIB` | `gui-control-run`, `gui-control-launch` | path of `libguicontrol.so` |
| `GUI_CONTROL_TARGET` | `gui-control-launch` | the real application binary |
| `GUI_CONTROL_OBJECTMAP` | client | object map file |
| `GUI_CONTROL_SHOT_DIR` | client | directory for screenshots given as a bare file name |
| `GUI_CONTROL_KEEP_TYPES` | client | extra item types the compact view always shows |

## Tests

    cd python && python3 -m pytest

The end-to-end tests start `examples/demo.qml` headless with the hook preloaded. They run when
`build/libguicontrol.so` exists (or `GUI_CONTROL_LIB` names it) and a `qml` runtime from the same Qt
is on `PATH` (or `GUI_CONTROL_QML` names it). Otherwise they are skipped.

## Limits

- Only Qt Quick windows. Qt Widgets are not reachable.
- Only the first visible `QQuickWindow` is driven.
- `invoke` passes and returns `QVariant`, so a C++ method must take `QVariant` arguments and return a
  `QVariant`. QML functions work as they are.
- The server has no authentication. Keep it bound to 127.0.0.1 unless the network is trusted.
