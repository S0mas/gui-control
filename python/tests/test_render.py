from gui_control.render import render_candidates, render_compact_tree, render_tree

CONTENT = ("text", "placeholderText", "checked", "title")


def _node(node_type, children=(), role="item", object_name=None, props=None, **extra):
    node = {"type": node_type, "role": role, "rect": {"x": 1, "y": 2, "width": 3, "height": 4}}
    if object_name:
        node["objectName"] = object_name
    if props:
        node["props"] = props
    node["children"] = list(children)
    node.update(extra)
    return node


def _compact(tree, keep_types=frozenset()):
    return render_compact_tree(tree, CONTENT, keep_types)


def test_containers_disappear_and_their_children_move_up():
    label = _node("Label", role="text", props={"text": "Overview", "color": "#fff"})
    button = _node("Button", [_node("Rect", role="container")], role="button", object_name="ok", props={"text": "OK"})
    layout = _node("Column", [_node("Item", [button, label], role="container")], role="container", object_name="column")
    tree = _node("Root", [_node("SettingsView", [layout])], role="container")
    assert _compact(tree) == [
        "SettingsView (1,2 3x4)",
        '  Button #ok (1,2 3x4)  text="OK"',
        '  Label (1,2 3x4)  text="Overview"',
    ]


def test_every_role_other_than_container_and_item_is_shown():
    tree = _node("Root", [_node("List", role="scrollable"), _node("Picture", role="image"), _node("Sheet", role="popup")], role="container")
    assert _compact(tree) == ["List (1,2 3x4)", "Picture (1,2 3x4)", "Sheet (1,2 3x4)"]


def test_plain_items_need_a_name_content_or_view_suffix():
    tree = _node(
        "Root",
        [_node("Gauge"), _node("Gauge", object_name="speed"), _node("Gauge", props={"checked": True}), _node("MainView")],
        role="container",
    )
    assert _compact(tree) == ["Gauge #speed (1,2 3x4)", "Gauge (1,2 3x4)  checked=true", "MainView (1,2 3x4)"]


def test_container_with_content_is_shown():
    assert _compact(_node("Item", role="container", props={"checked": True})) == ["Item (1,2 3x4)  checked=true"]


def test_keep_types_adds_application_widgets():
    tree = _node("Root", [_node("Gauge")], role="container")
    assert _compact(tree) == []
    assert _compact(tree, frozenset({"Gauge"})) == ["Gauge (1,2 3x4)"]


def test_only_backend_content_props_are_shown():
    node = _node("Label", role="text", props={"text": "a", "color": "#000", "wrap": True})
    assert render_compact_tree(node, ("text",)) == ['Label (1,2 3x4)  text="a"']
    assert render_compact_tree(node) == ["Label (1,2 3x4)"]


def test_items_repeating_the_text_of_their_owner_are_left_out():
    button = _node(
        "Button",
        [_node("IconLabel", [_node("Text", role="text", object_name="label", props={"text": "OK"})], props={"text": "OK"})],
        role="button",
        object_name="ok",
        props={"text": "OK", "checked": False},
    )
    field = _node("TextField", [_node("Placeholder", role="text", props={"text": "Name"})], role="input", props={"placeholderText": "Name"})
    assert _compact([button, field]) == [
        'Button #ok (1,2 3x4)  text="OK" checked=false',
        'TextField (1,2 3x4)  placeholderText="Name"',
    ]


def test_flags_truncation_and_long_text():
    tree = _node(
        "MainView",
        [_node("Item", [_node("Text", role="text", props={"text": "x" * 60})], role="container", truncatedChildren=3)],
        visible=False,
        enabled=False,
    )
    assert _compact(tree) == [
        "MainView (1,2 3x4) [hidden, disabled]",
        "  … 3 more child items",
        f'  Text (1,2 3x4)  text="{"x" * 47}…"',
    ]


def test_raw_render_shows_every_item_and_prop():
    assert render_tree([_node("Item", [_node("Rect", props={"color": "#000"})], role="container")]) == [
        "Item (1,2 3x4)",
        '  Rect (1,2 3x4)  color="#000"',
    ]


def test_candidates_show_type_name_rect_and_text():
    assert render_candidates([{"type": "Button", "objectName": "ok", "rect": {}, "text": "OK"}, "raw"]) == [
        '  Button #ok (0,0 0x0)  text="OK"',
        "  raw",
    ]
