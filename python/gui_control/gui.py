import time
from dataclasses import dataclass
from typing import Optional

from .client import ControlError, GuiClient
from .targets import ObjectMap, resolve

SETTLE_QUIET_MS = 300
SETTLE_TIMEOUT_MS = 8000
TARGET_POLL_SECONDS = 0.05
DEFAULT_SCROLL_CONTAINER = "[role=scrollable][0]"
SWIPE_NEAR_EDGE = 0.2
SWIPE_FAR_EDGE = 0.8


@dataclass
class ActionOutcome:
    scrolled: bool = False
    unsettled: Optional[str] = None


class Gui:
    def __init__(self, client=None, object_map=None, settle=True, quiet=SETTLE_QUIET_MS, timeout=SETTLE_TIMEOUT_MS):
        self.client = client or GuiClient()
        self.object_map = object_map if object_map is not None else ObjectMap.load()
        self.settles = settle
        self.quiet = quiet
        self.timeout = timeout

    @classmethod
    def connect(cls, host=None, port=None, map_path=None, **options):
        return cls(GuiClient(host, port), ObjectMap.load(map_path), **options)

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def selector(self, target):
        return resolve(target, self.object_map)[1]

    def _target(self, target):
        kind, value = resolve(target, self.object_map)
        return {"point": value} if kind == "point" else {"selector": value}

    def settle(self):
        if not self.settles:
            return None
        try:
            self.client.wait_settled(quiet=self.quiet, timeout=self.timeout)
        except ControlError as error:
            if not error.answered_by_hook:
                raise
            return str(error)
        return None

    def wait_until_interactable(self, target, hidden=False):
        selector = self.selector(target)
        window = self.client.ping()
        deadline = time.monotonic() + self.timeout / 1000
        reason = "absent"
        scrolled_into_view = False
        while time.monotonic() < deadline:
            try:
                item = self.client.get(selector, hidden=hidden)
            except ControlError as error:
                if "matched nothing" not in str(error):
                    raise
                reason = "absent"
            else:
                reason = _not_interactable_reason(item, window)
                if reason == "outside the window":
                    scrolled = self.client.scroll(selector, hidden=hidden)
                    scrolled_into_view = scrolled_into_view or bool(scrolled.get("scrolled"))
                    item["rect"] = scrolled.get("rect") or item.get("rect")
                    reason = _not_interactable_reason(item, window)
                if reason is None:
                    return scrolled_into_view
            time.sleep(TARGET_POLL_SECONDS)
        raise ControlError(f"{target} did not become interactable within {self.timeout} ms ({reason})")

    def screen(self, target=None, depth=None, props=None, hidden=False, all_props=False):
        selector = self.selector(target) if target else None
        return self.client.tree(selector=selector, depth=depth, props=props, hidden=hidden, all_props=all_props)

    def window(self):
        return self.client.ping()

    def tap(self, target, hidden=False):
        resolved = self._target(target)
        scrolled_before = "selector" in resolved and self.wait_until_interactable(target, hidden=hidden)
        response = self.client.tap(hidden=hidden, **resolved)
        return ActionOutcome(scrolled_before or bool(response.get("scrolled")), self.settle())

    def long_press(self, target, duration=0, hidden=False):
        resolved = self._target(target)
        scrolled_before = "selector" in resolved and self.wait_until_interactable(target, hidden=hidden)
        response = self.client.long_press(duration=duration, hidden=hidden, **resolved)
        return ActionOutcome(scrolled_before or bool(response.get("scrolled")), self.settle())

    def swipe(self, target, to, duration=300, hidden=False):
        kind, destination = resolve(to, self.object_map)
        if kind != "point":
            raise ControlError("swipe destination must be 'x,y'")
        response = self.client.swipe(
            to_x=destination[0], to_y=destination[1], duration=duration, hidden=hidden, **self._target(target)
        )
        return ActionOutcome(bool(response.get("scrolled")), self.settle())

    def scroll_to(self, target, hidden=False):
        response = self.client.scroll(self.selector(target), hidden=hidden)
        return response.get("rect") or {}, bool(response.get("scrolled"))

    def scroll(self, direction, container=None, hidden=False):
        selector = self.selector(container or DEFAULT_SCROLL_CONTAINER)
        rect = (self.client.get(selector, hidden=hidden) or {}).get("rect") or {}
        x = rect.get("x", 0) + rect.get("width", 0) / 2
        near = rect.get("y", 0) + rect.get("height", 0) * SWIPE_NEAR_EDGE
        far = rect.get("y", 0) + rect.get("height", 0) * SWIPE_FAR_EDGE
        start, end = ((x, far), (x, near)) if direction == "down" else ((x, near), (x, far))
        self.client.swipe(to_x=end[0], to_y=end[1], point=start, duration=300)
        return ActionOutcome(False, self.settle())

    def type_text(self, text):
        self.client.type_text(text)

    def key(self, name):
        self.client.key(name)

    def get(self, target, prop=None, hidden=False):
        return self.client.get(self.selector(target), prop, hidden=hidden)

    def set(self, target, prop, value, hidden=False):
        self.client.set(self.selector(target), prop, value, hidden=hidden)

    def invoke(self, target, method, args=(), hidden=False):
        return self.client.invoke(self.selector(target), method, list(args), hidden=hidden)

    def shot(self, path):
        return self.client.screenshot(path)

    def wait_settled(self, quiet=None, timeout=None):
        self.client.wait_settled(quiet=quiet or self.quiet, timeout=timeout or self.timeout)

    def wait_for(self, target, present=True, timeout=None, hidden=False):
        self.client.wait_for(self.selector(target), present=present, timeout=timeout or self.timeout, hidden=hidden)

    def wait_signal(self, target, signal, timeout=None, hidden=False):
        self.client.wait_signal(self.selector(target), signal, timeout=timeout or self.timeout, hidden=hidden)


def _not_interactable_reason(item, window):
    if item.get("visible", True) is False:
        return "not visible"
    if item.get("enabled", True) is False:
        return "disabled"
    if item.get("opacity", 1) <= 0:
        return "transparent"
    rect = item.get("rect") or {}
    width = rect.get("width", 0)
    height = rect.get("height", 0)
    if width <= 0 or height <= 0:
        return "empty geometry"
    center_x = rect.get("x", 0) + width / 2
    center_y = rect.get("y", 0) + height / 2
    if not 0 <= center_x < window.get("width", 0) or not 0 <= center_y < window.get("height", 0):
        return "outside the window"
    return None
