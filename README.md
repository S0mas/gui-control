# gui-control

Drive and inspect a running GUI application from the outside: read its item tree, tap, swipe, type,
read and write properties, take screenshots and wait for the UI to settle. The application needs no
code changes.

gui-control has two halves joined by a small JSON protocol:

- A **backend** runs inside the application process, answers the protocol on a local TCP port and
  knows the GUI technology. This repository ships the backend for **Qt Quick**: `libguicontrol.so`,
  preloaded into the application.
- The **client** (a Python library and the `gui-control` command line) speaks only the protocol. It
  contains no knowledge of any GUI technology, so scripts, tests and AI agents work the same against
  any backend.

![The client chain (agent or test, gui-control CLI, Gui, GuiClient) sends one JSON line per request over TCP to ControlServer inside the application process and reads one JSON line back. ControlServer, Scene and Actions form libguicontrol.so, the Qt Quick backend: Scene reads the application's QQuickWindow item tree, Actions sends input events to it. A backend for another GUI technology could answer the same requests; it is not built yet.](docs/diagrams/structure.svg)

## How it works

- `libguicontrol.so` is loaded into the application with `LD_PRELOAD`. The application's source and
  build stay unchanged.
- When the `QGuiApplication` starts, the library opens a TCP server inside the process (port 7801 on
  127.0.0.1 by default). In a process without a GUI it does nothing.
- Each request is one line of JSON, and so is each reply. The server runs on the GUI thread, so every
  command sees the same live object tree the application renders.
- **Reading:** the backend walks the item tree of the first visible window and returns each item's
  type, role, `objectName`, window rectangle, visibility and properties.
- **Roles:** the backend sorts every item into a role such as `button`, `input`, `text` or
  `scrollable`. The client decides what to show and what to scroll from roles alone, never from type
  names.
- **Finding:** items are addressed with a small selector language: type, `#objectName`,
  `[property=value]`, `[role=…]`, `[index]` and nesting (`/`).
- **Acting:** taps, long presses and swipes are real mouse events sent to the window at the item's
  centre, so they take the same path as a user's input. An item outside a scrollable area's viewport
  is scrolled into view first. Text and keys go to the focused item as key events.
- **Direct access:** any property can be read or written, and methods can be called.
- **Screenshots:** the window grabs itself, so screenshots work headless with
  `QT_QPA_PLATFORM=offscreen`.
- **Waiting:** until no frame has been rendered for a quiet period, until a page transition has
  finished, until an item appears or disappears, or until a signal fires.

One `gui-control tap` uses four kinds of request. The client checks that the target can be tapped,
the backend turns the selector into a point and sends real mouse events, and the client waits until
the screen has settled:

![Sequence of gui-control tap '#save': the client resolves the target and pings for the window size, repeats get until the item is visible, enabled and on screen (scrolling it into view when needed), then sends tap. ControlServer matches the selector, scrolls the item into view and sends a mouse press and release at its centre to the QQuickWindow, where the button emits clicked(). The client then sends wait settled, and ControlServer replies once any StackView transition has finished and no frame has been rendered for 300 ms, at most 8 s.](docs/diagrams/tap-sequence.svg)

## Requirements

- Linux (the Qt Quick backend is injected with `LD_PRELOAD`).
- Qt 6 with Core, Gui, Quick and Network. Build the backend against the same Qt installation the
  application runs with.
- CMake 3.21 or newer and a C++20 compiler.
- Python 3.9 or newer for the client. It needs nothing beyond the standard library.

## Build the Qt Quick backend

```sh
cmake -S . -B build -DCMAKE_PREFIX_PATH=$HOME/Qt/6.8.1/gcc_64
cmake --build build
```

The build writes `build/libguicontrol.so` and `build/gui-control-launch`.

## Start an application with the backend

```sh
bin/gui-control-run ./my-qt-quick-app --its-arguments
bin/gui-control-run qml examples/demo.qml
QT_QPA_PLATFORM=offscreen GUI_CONTROL_PORT=7900 bin/gui-control-run ./my-qt-quick-app
```

`gui-control-run` puts the library in front of `LD_PRELOAD` and starts the command. The application
logs `[gui-control] listening on 127.0.0.1:7801` once the server is up.

When a wrapper you do not control starts the application (a dynamic loader, an SDK run script) and
would reset `LD_PRELOAD`, put `build/gui-control-launch` where the application binary would go, and
set `GUI_CONTROL_TARGET` to the real binary and `GUI_CONTROL_LIB` to the library. The launcher sets
`LD_PRELOAD` at the last moment and replaces itself with the target, keeping any loader prefix on the
command line.

![Start-up: gui-control-run puts libguicontrol.so first in LD_PRELOAD and execs the application, or gui-control-launch takes the application's place under a wrapper script and execs GUI_CONTROL_TARGET. The dynamic loader maps the application and the library, the application constructs QGuiApplication, and Qt runs the library's startup function. In a GUI application ControlServer listens on 127.0.0.1:7801; without a QGuiApplication or with GUI_CONTROL_ENABLED=0 the library does nothing.](docs/diagrams/startup.svg)

## Command line

Install with `pip install -e python`, or run `bin/gui-control` from the checkout without installing.

```text
gui-control ping                               is the backend up; which one, its ops, window title and size
gui-control screen                             compact item tree: types, objectNames, rects, text and values
gui-control screen --raw                       every item with every reported property
gui-control screen '#settingsPage'             only the subtree under a selector
gui-control tap '#okButton'                    tap an item (waits until it is enabled and on screen)
gui-control tap 'Button[text=Save]'            tap by visible text
gui-control tap 240,320                        tap a window coordinate
gui-control long-press '#item' --duration 1500
gui-control swipe '#list' 240,100              drag from an item to a point
gui-control scroll down                        scroll the first scrollable item by 60% of its height
gui-control scroll down '#list'                scroll a given item
gui-control scroll to 'ItemDelegate[text=Row 12]'
gui-control type 'hello'                       type into the focused item
gui-control key enter                          enter, escape, backspace, delete, tab, space, arrows, home, end, back
gui-control get '#slider' value                read one property (JSON)
gui-control get '#slider'                      dump one item with its subtree and every declared property
gui-control set '#slider' value 42             write a property (value parsed as JSON)
gui-control invoke '#model' reload             call a method (at most 3 JSON arguments)
gui-control shot screen.png                    PNG of the window
gui-control wait settled                       no new frame for 300 ms
gui-control wait appears '#dialog' --timeout 5000
gui-control wait signal '#button' --signal clicked
```

Options that apply to every verb: `--host`, `--port`, `--map <file>`, `--hidden` (also match items
that are not visible), `--json`, and `--no-settle`. After every tap, long press, swipe or scroll the
command waits until the UI has settled. When the UI keeps animating it prints the action with
`(ui not settled: …)` rather than failing.

When a target matches nothing or several items, the command exits with status 2 and prints the status
(`OBJECT_NOT_FOUND` or `AMBIGUOUS`), the closest candidates and the current screen on stderr.

### The compact screen view

`screen` shows only the items worth reading, decided by role:

- An item that carries a content property is shown. The backend names its content properties in the
  `ping` reply; for Qt Quick they are `text`, `displayText`, `placeholderText`, `value`, `checked`,
  `currentValue` and `title`. Only these properties are printed.
- A `container` is left out, and its children move up a level.
- Every other role (`page`, `scrollable`, `popup`, `button`, `input`, `text`, `image`) is shown.
- A plain `item` is shown when it has an `objectName` or its type ends in `View`.
- An item that only repeats the content of the item it sits in, such as the label inside a button, is
  left out.
- Types named with `--keep Gauge,Tile` or `GUI_CONTROL_KEEP_TYPES=Gauge,Tile` are always shown.

Each line reads `Type #objectName (x,y wxh) [flags]  prop=value …`. Flags are `hidden`, `disabled`,
`opacity=` and `clip`.

![An excerpt of the demo application's item tree with each item's role. Container items are left out and their children move up; ButtonPanel, a plain item without a name or content, is left out; QQuickIconLabel and QQuickMnemonicLabel repeat the button's text and are left out; StackView, Page, Label, Button and QQuickListView are kept. Below it, the real gui-control screen output for the demo application.](docs/diagrams/screen-roles.svg)

## Selectors

| Form | Example | Matches |
| --- | --- | --- |
| type | `Button` | items of that type |
| objectName | `#saveButton` | items with that `objectName` |
| both | `Button#saveButton` | type and `objectName` |
| predicate | `Button[text=Save]` | property equals value (compared as text) |
| role | `[role=scrollable]` | items the backend gave that role |
| index | `Button[2]` | the third match of that segment |
| predicate and index | `Label[text=Total][1]` | the second label whose text is Total |
| nesting | `SettingsPage/Switch[0]` | a descendant at any depth of an earlier match |
| map name | `@save` | the selector stored under that name in the object map |
| point | `240,320` | a window coordinate (tap, long press, swipe) |
| bare word | `saveButton` | a map name if there is one, else lowercase start → `#saveButton`, uppercase start → type |

`[role=…]` always matches the role, even when an item also has a property called `role`.

In the Qt Quick backend the type is the class name of the item's meta object up to the first `_`. A
QML component defined in `Gauge.qml` therefore shows as `Gauge`, and a built-in item shows its C++
class, such as `QQuickText` or `QQuickListView`.

## Object map

An object map gives stable names to selectors, so scripts do not break when a layout changes. It is a
JSON file named by `--map` or `GUI_CONTROL_OBJECTMAP`:

```json
{"names": {"save": "Button[text=Save]", "volume": {"selector": "#volumeSlider", "note": "settings page"}}}
```

```text
gui-control map generate                       propose a name and a unique selector for every item on screen
gui-control map add save 'Button[text=Save]'
gui-control map list
gui-control tap @save
```

## Python

```python
from gui_control import Gui

with Gui.connect(port=7801) as gui:
    gui.tap("Button[text=Increment]")
    assert gui.get("#counterLabel", "text") == "Clicked 1 times"
    gui.set("#volumeSlider", "value", 30)
    gui.wait_for("#detailsPage")
    gui.shot("/tmp/details.png")
```

`Gui` resolves targets through the object map, waits until a target is interactable, and settles after
each action. `GuiClient` is the raw protocol, with one method per command.

## Protocol

The protocol is the contract between client and backend. A backend for another GUI technology
implements the same commands, node format and roles; the client then works with it unchanged.

Send one JSON object per line and read one JSON object per line back. Every reply has `ok`. A failure
carries `error` and, when a selector did not resolve to one item, `candidates`.

| op | Request fields | Reply |
| --- | --- | --- |
| `ping` | | `backend`, `ops`, `content_props`, `window`, `width`, `height`, `title` |
| `tree` | `selector`, `depth`, `hidden`, `props`, `all_props` | `tree`, or `matches` and `count` with a selector |
| `tap` | `selector`, or `x` and `y` | `scrolled` when the item had to be scrolled into view |
| `long_press` | as `tap`, plus `duration` in ms | as `tap` |
| `swipe` | as `tap`, plus `to_x`, `to_y`, `duration` | as `tap` |
| `scroll` | `selector` | `scrolled`, `rect` |
| `type` | `text` | |
| `key` | `key` | |
| `get` | `selector`, `prop`, or `props` without `prop` | `value`, or `item` without `prop` |
| `set` | `selector`, `prop`, `value` | |
| `invoke` | `selector`, `method`, `args` (at most 3) | `result` |
| `screenshot` | `path` (written by the application process) | `path` |
| `wait` | `mode` (`settled`, `appears`, `disappears`, and optionally `transition`, `signal`), `selector`, `signal`, `quiet`, `timeout` | |

Every op that takes a selector also accepts `hidden` to match items that are not visible.

`ping` names the backend and lists the ops it supports, so a client can check before it uses an op
that not every backend offers, such as `invoke` or `wait signal`.

Choosing properties in `tree` and `get`:

- `props` left out: the backend's default set of useful properties.
- `props: ["text", "value"]`: exactly those.
- `props: "*"`: every property the item's type declares beyond the generic base item.
- `all_props: true`: every property, including the ones every item has.

### Nodes

```json
{"type": "Button", "role": "button", "objectName": "save",
 "rect": {"x": 16, "y": 42, "width": 80, "height": 24},
 "visible": false, "enabled": false, "opacity": 0.5, "clip": true, "z": 1,
 "props": {"text": "Save", "checked": false},
 "children": [...], "truncatedChildren": 3}
```

`type`, `role` and `rect` (window coordinates) are always present. The flags appear only when they
differ from the default (visible, enabled, opaque, not clipping, stacking order 0). `truncatedChildren` counts the
children left out by `depth`.

### Roles

| Role | Meaning | Qt Quick backend |
| --- | --- | --- |
| `container` | layout only, carries nothing to read or touch | plain `Item`, `Rectangle`, `Loader`, `MouseArea`, `Repeater`, layouts, positioners, Qt's internal content items |
| `page` | a screen, or a stack or pager of screens | `StackView`, `SwipeView`, `Page` |
| `scrollable` | content that scrolls | everything based on `Flickable`, `PathView` |
| `popup` | a popup, dialog, drawer or menu | the item of a `Popup` |
| `button` | something to press or toggle | everything based on `AbstractButton` |
| `input` | something that takes a value | text fields and areas, sliders, spin boxes, combo boxes, dials, tumblers |
| `text` | read-only text | everything based on `Text` |
| `image` | a picture or icon | everything based on `Image` |
| `item` | anything else | QML components of the application itself, and other types |

## Environment variables

| Variable | Read by | Meaning |
| --- | --- | --- |
| `GUI_CONTROL_PORT` | backend, client | TCP port (default 7801) |
| `GUI_CONTROL_BIND` | backend | address the server listens on (default 127.0.0.1) |
| `GUI_CONTROL_HOST` | client | address the client connects to (default 127.0.0.1) |
| `GUI_CONTROL_ENABLED` | backend | `0` keeps the library loaded but switched off |
| `GUI_CONTROL_BLINKING_CARET` | backend | `1` keeps the text cursor blinking; it is off by default so screenshots are stable |
| `GUI_CONTROL_LIB` | `gui-control-run`, `gui-control-launch` | path of `libguicontrol.so` |
| `GUI_CONTROL_TARGET` | `gui-control-launch` | the real application binary |
| `GUI_CONTROL_OBJECTMAP` | client | object map file |
| `GUI_CONTROL_SHOT_DIR` | client | directory for screenshots given as a bare file name |
| `GUI_CONTROL_KEEP_TYPES` | client | extra item types the compact view always shows |

## Tests

```sh
cd python && python3 -m pytest
```

The end-to-end tests start `examples/demo.qml` headless with the backend preloaded. They run when
`build/libguicontrol.so` exists (or `GUI_CONTROL_LIB` names it) and a `qml` runtime from the same Qt
is on `PATH` (or `GUI_CONTROL_QML` names it). Otherwise they are skipped.

## Limits

- The only backend so far is Qt Quick. Qt Widgets applications are not reachable.
- Only the first visible window is driven.
- In the Qt Quick backend `invoke` passes and returns `QVariant`, so a C++ method must take `QVariant`
  arguments and return a `QVariant`. QML functions work as they are.
- The server has no authentication. Keep it bound to 127.0.0.1 unless the network is trusted.
