import os

KEEP_TYPES_VARIABLE = "GUI_CONTROL_KEEP_TYPES"

COMPACT_CONTENT_PROPS = ("text", "displayText", "placeholderText", "value", "checked", "currentValue", "title")

COMPACT_TYPES = frozenset({
    "QQuickText",
    "QQuickTextInput",
    "QQuickTextEdit",
    "QQuickImage",
    "QQuickListView",
    "QQuickGridView",
    "QQuickPathView",
    "QQuickStackView",
    "QQuickSwipeView",
})

COMPACT_TYPE_MARKERS = ("Popup", "Dialog", "Drawer", "Overlay")

GENERIC_CONTAINER_TYPES = (
    "QQuickItem",
    "QQuickRootItem",
    "QQuickContentItem",
    "QQuickControl",
    "QQuickLoader",
    "QQuickRectangle",
    "QQuickMouseArea",
    "QQuickRow",
    "QQuickColumn",
    "QQuickGrid",
    "QQuickFlow",
)
GENERIC_CONTAINER_MARKERS = ("Layout", "Repeater")


def keep_types_from_environment():
    configured = os.environ.get(KEEP_TYPES_VARIABLE, "")
    return frozenset(name.strip() for name in configured.split(",") if name.strip())


def _rect(node):
    rect = node.get("rect") or {}
    return "{:.0f},{:.0f} {:.0f}x{:.0f}".format(
        rect.get("x", 0), rect.get("y", 0), rect.get("width", 0), rect.get("height", 0)
    )


def _props(props, max_len=48):
    parts = []
    for name, value in props.items():
        if isinstance(value, str):
            if len(value) > max_len:
                value = value[: max_len - 1] + "…"
            parts.append(f'{name}="{value}"')
        elif isinstance(value, bool):
            parts.append(f"{name}={'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            parts.append(f"{name}={value:g}" if isinstance(value, float) else f"{name}={value}")
    return " ".join(parts)


def _flags(node):
    flags = []
    if node.get("visible") is False:
        flags.append("hidden")
    if node.get("enabled") is False:
        flags.append("disabled")
    if "opacity" in node:
        flags.append(f"opacity={node['opacity']:g}")
    if node.get("clip"):
        flags.append("clip")
    return f" [{', '.join(flags)}]" if flags else ""


def _head(node, indent, props):
    name = node.get("type", "?")
    if node.get("objectName"):
        name += f" #{node['objectName']}"
    line = f"{'  ' * indent}{name} ({_rect(node)}){_flags(node)}"
    rendered = _props(props)
    return f"{line}  {rendered}" if rendered else line


def _truncation(node, indent):
    if node.get("truncatedChildren"):
        return [f"{'  ' * indent}… {node['truncatedChildren']} more child items"]
    return []


def render(node, indent=0, lines=None):
    lines = [] if lines is None else lines
    lines.append(_head(node, indent, node.get("props") or {}))
    lines.extend(_truncation(node, indent + 1))
    for child in node.get("children") or []:
        render(child, indent + 1, lines)
    return lines


def render_tree(tree):
    if not isinstance(tree, list):
        return render(tree)
    lines = []
    for node in tree:
        render(node, 0, lines)
    return lines


def render_candidates(candidates):
    lines = []
    for candidate in candidates:
        if isinstance(candidate, str):
            lines.append(f"  {candidate}")
            continue
        name = candidate.get("type", "?")
        if candidate.get("objectName"):
            name += f" #{candidate['objectName']}"
        text = candidate.get("text")
        suffix = f'  text="{text}"' if text else ""
        lines.append(f"  {name} ({_rect(candidate)}){suffix}")
    return lines


def _is_generic_container(node_type):
    return node_type in GENERIC_CONTAINER_TYPES or any(marker in node_type for marker in GENERIC_CONTAINER_MARKERS)


def is_compact_node(node, keep_types=frozenset()):
    props = node.get("props") or {}
    if any(key in props for key in COMPACT_CONTENT_PROPS):
        return True
    node_type = node.get("type", "")
    if node.get("objectName") and not _is_generic_container(node_type):
        return True
    if node_type in COMPACT_TYPES or node_type in keep_types or node_type.endswith("View"):
        return True
    return any(marker in node_type for marker in COMPACT_TYPE_MARKERS)


def _content_values(node):
    props = node.get("props") or {}
    return frozenset(repr(props[key]) for key in COMPACT_CONTENT_PROPS if key in props)


def render_compact(node, indent=0, lines=None, keep_types=frozenset(), values_shown_above=frozenset()):
    lines = [] if lines is None else lines
    child_indent = indent
    values = _content_values(node)
    repeats_its_owner = bool(values) and values <= values_shown_above

    if is_compact_node(node, keep_types) and not repeats_its_owner:
        props = node.get("props") or {}
        lines.append(_head(node, indent, {key: props[key] for key in COMPACT_CONTENT_PROPS if key in props}))
        child_indent = indent + 1
        values_shown_above = values

    lines.extend(_truncation(node, child_indent))
    for child in node.get("children") or []:
        render_compact(child, child_indent, lines, keep_types, values_shown_above)
    return lines


def render_compact_tree(tree, keep_types=frozenset()):
    if not isinstance(tree, list):
        return render_compact(tree, keep_types=keep_types)
    lines = []
    for node in tree:
        render_compact(node, 0, lines, keep_types)
    return lines
