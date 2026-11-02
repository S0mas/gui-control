import json
import os
import re
from collections import Counter
from pathlib import Path

MAP_FILE_VARIABLE = "GUI_CONTROL_OBJECTMAP"

BARE_OBJECT_NAME_PATTERN = re.compile(r"^[a-z][A-Za-z0-9_]*$")
POINT_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class ObjectMapLocationUnset(RuntimeError):
    def __init__(self):
        super().__init__(f"no object map: set ${MAP_FILE_VARIABLE} or pass --map")


class ObjectMap:
    def __init__(self, entries=None, path=None):
        self.entries = entries or {}
        self.path = path

    @classmethod
    def load(cls, path=None):
        path = path or os.environ.get(MAP_FILE_VARIABLE)
        if not path:
            return cls({}, None)
        path = Path(path).expanduser()
        if not path.exists():
            return cls({}, path)
        with open(path) as handle:
            data = json.load(handle)
        return cls(data.get("names", data), path)

    def require_location(self):
        if self.path is None:
            raise ObjectMapLocationUnset()

    def save(self):
        self.require_location()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as handle:
            json.dump({"names": self.entries}, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def selector_for(self, name):
        entry = self.entries.get(name)
        if entry is None:
            return None
        return entry["selector"] if isinstance(entry, dict) else entry

    def add(self, name, selector, note=None):
        self.entries[name] = {"selector": selector, "note": note} if note else selector

    def names(self):
        return sorted(self.entries)


def resolve(target, object_map=None):
    point = POINT_PATTERN.match(target or "")
    if point:
        return "point", (float(point.group(1)), float(point.group(2)))

    if target.startswith("@"):
        name = target[1:]
        if object_map is None:
            raise KeyError(f"'{target}' needs an object map")
        object_map.require_location()
        selector = object_map.selector_for(name)
        if selector is None:
            known = ", ".join(object_map.names()) or "none"
            raise KeyError(f"'{name}' is not in the object map (known: {known})")
        return "selector", selector

    if object_map is not None:
        selector = object_map.selector_for(target)
        if selector is not None:
            return "selector", selector

    if BARE_OBJECT_NAME_PATTERN.match(target):
        return "selector", f"#{target}"
    return "selector", target


def _walk(node, out):
    out.append(node)
    for child in node.get("children") or []:
        _walk(child, out)
    return out


def propose(tree):
    nodes = _walk(tree, [])
    types = Counter(node.get("type", "?") for node in nodes)
    object_names = Counter(node.get("objectName") for node in nodes if node.get("objectName"))

    proposals = []
    for index, node in enumerate(nodes):
        node_type = node.get("type", "?")
        object_name = node.get("objectName")
        text = (node.get("props") or {}).get("text")

        if object_name and object_names[object_name] == 1:
            selector = f"#{object_name}"
        elif types[node_type] == 1:
            selector = node_type
        elif text and isinstance(text, str):
            same = [
                other
                for other in nodes
                if other.get("type") == node_type and (other.get("props") or {}).get("text") == text
            ]
            selector = f"{node_type}[text={text}]" if len(same) == 1 else None
        else:
            selector = None

        if selector is None:
            same_type = [other for other in nodes if other.get("type") == node_type]
            position = next(order for order, other in enumerate(same_type) if other is node)
            selector = f"{node_type}[{position}]"

        suggested = object_name or (
            _slug(text) if isinstance(text, str) and text else f"{_lower_first(node_type)}{index}"
        )
        proposals.append({"name": suggested, "selector": selector, "type": node_type, "text": text})
    return proposals


def _slug(text):
    cleaned = re.sub(r"[^0-9a-zA-Z]+", " ", text).strip().split()
    if not cleaned:
        return "item"
    head = cleaned[0].lower()
    return head + "".join(word.capitalize() for word in cleaned[1:])


def _lower_first(text):
    return text[:1].lower() + text[1:] if text else text
