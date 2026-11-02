import os

KEEP_TYPES_VARIABLE = "GUI_CONTROL_KEEP_TYPES"

CONTAINER_ROLE = "container"
GENERIC_ITEM_ROLE = "item"
VIEW_TYPE_SUFFIX = "View"


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


def _render(node, indent, lines):
    lines.append(_head(node, indent, node.get("props") or {}))
    lines.extend(_truncation(node, indent + 1))
    for child in node.get("children") or []:
        _render(child, indent + 1, lines)


def render_tree(tree):
    lines = []
    for node in tree if isinstance(tree, list) else [tree]:
        _render(node, 0, lines)
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


def _content(node, content_props):
    props = node.get("props") or {}
    return {key: props[key] for key in content_props if key in props}


def is_compact_node(node, content_props=(), keep_types=frozenset()):
    node_type = node.get("type", "")
    if node_type in keep_types or _content(node, content_props):
        return True
    role = node.get("role", GENERIC_ITEM_ROLE)
    if role == CONTAINER_ROLE:
        return False
    if role != GENERIC_ITEM_ROLE:
        return True
    return bool(node.get("objectName")) or node_type.endswith(VIEW_TYPE_SUFFIX)


def _render_compact(node, indent, lines, content_props, keep_types, values_shown_above):
    content = _content(node, content_props)
    values = frozenset(repr(value) for value in content.values())
    repeats_its_owner = bool(values) and values <= values_shown_above
    child_indent = indent

    if is_compact_node(node, content_props, keep_types) and not repeats_its_owner:
        lines.append(_head(node, indent, content))
        child_indent = indent + 1
        values_shown_above = values

    lines.extend(_truncation(node, child_indent))
    for child in node.get("children") or []:
        _render_compact(child, child_indent, lines, content_props, keep_types, values_shown_above)


def render_compact_tree(tree, content_props=(), keep_types=frozenset()):
    lines = []
    for node in tree if isinstance(tree, list) else [tree]:
        _render_compact(node, 0, lines, tuple(content_props), keep_types, frozenset())
    return lines
