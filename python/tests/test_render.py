from gui_control.render import render, render_candidates, render_compact, render_compact_tree


def _node(node_type, children=(), object_name=None, props=None, **extra):
    node = {"type": node_type, "rect": {"x": 1, "y": 2, "width": 3, "height": 4}}
    if object_name:
        node["objectName"] = object_name
    if props:
        node["props"] = props
    node["children"] = list(children)
    node.update(extra)
    return node


def _page_tree():
    label = _node("Label", props={"text": "Overview", "color": "#fff"})
    button = _node(
        "Button",
        [_node("QQuickRectangle", props={"color": "#000"})],
        object_name="okButton",
        props={"text": "OK"},
    )
    layout = _node("QQuickColumnLayout", [_node("QQuickItem", [button, label])])
    return _node("QQuickRootItem", [_node("SettingsView", [layout])])


def test_compact_promotes_kept_descendants_to_nearest_kept_ancestor():
    assert render_compact(_page_tree()) == [
        "SettingsView (1,2 3x4)",
        '  Button #okButton (1,2 3x4)  text="OK"',
        '  Label (1,2 3x4)  text="Overview"',
    ]


def test_compact_keeps_flags_truncation_and_long_text():
    tree = _node(
        "MainView",
        [_node("QQuickItem", [_node("QQuickText", props={"text": "x" * 60})], truncatedChildren=3)],
        visible=False,
        enabled=False,
    )
    lines = render_compact(tree)
    assert lines[0] == "MainView (1,2 3x4) [hidden, disabled]"
    assert lines[1] == "  … 3 more child items"
    assert lines[2] == f'  QQuickText (1,2 3x4)  text="{"x" * 47}…"'


def test_compact_keeps_nodes_by_content_props_and_popup_markers():
    tree = _node(
        "QQuickItem",
        [_node("QQuickItem", props={"checked": True}), _node("QQuickPopupItem"), _node("QQuickRepeater")],
    )
    assert render_compact(tree) == ["QQuickItem (1,2 3x4)  checked=true", "QQuickPopupItem (1,2 3x4)"]


def test_object_name_on_generic_container_does_not_keep_it():
    tree = _node("QQuickRowLayout", [_node("Label", props={"text": "a"})], object_name="row")
    assert render_compact(tree) == ['Label (1,2 3x4)  text="a"']


def test_items_repeating_the_text_of_their_owner_are_left_out():
    tree = _node(
        "Button",
        [_node("QQuickIconLabel", [_node("QQuickMnemonicLabel", object_name="label", props={"text": "OK"})], props={"text": "OK"})],
        object_name="okButton",
        props={"text": "OK", "checked": False},
    )
    field = _node("TextField", [_node("QQuickPlaceholderText", props={"text": "Name"})], props={"placeholderText": "Name"})
    assert render_compact_tree([tree, field]) == [
        'Button #okButton (1,2 3x4)  text="OK" checked=false',
        'TextField (1,2 3x4)  placeholderText="Name"',
    ]


def test_qt_internal_containers_with_object_names_are_left_out():
    tree = _node("QQuickRootItem", [_node("QQuickContentItem", [_node("Label", props={"text": "a"})], object_name="Page")], object_name="ApplicationWindow")
    assert render_compact(tree) == ['Label (1,2 3x4)  text="a"']


def test_keep_types_adds_application_widgets():
    tree = _node("QQuickItem", [_node("Gauge")])
    assert render_compact_tree(tree) == []
    assert render_compact_tree(tree, frozenset({"Gauge"})) == ["Gauge (1,2 3x4)"]


def test_compact_tree_handles_match_lists():
    assert render_compact_tree([_node("QQuickListView"), _node("QQuickItem")]) == ["QQuickListView (1,2 3x4)"]


def test_raw_render_shows_every_item_and_prop():
    assert render(_node("QQuickItem", [_node("Rect", props={"color": "#000"})])) == [
        "QQuickItem (1,2 3x4)",
        '  Rect (1,2 3x4)  color="#000"',
    ]


def test_candidates_show_type_name_rect_and_text():
    assert render_candidates([{"type": "Button", "objectName": "ok", "rect": {}, "text": "OK"}, "raw"]) == [
        '  Button #ok (0,0 0x0)  text="OK"',
        "  raw",
    ]
