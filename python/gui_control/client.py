import json
import os
import socket
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7801
HOST_VARIABLE = "GUI_CONTROL_HOST"
PORT_VARIABLE = "GUI_CONTROL_PORT"
SHOT_DIR_VARIABLE = "GUI_CONTROL_SHOT_DIR"

DECLARED_PROPS = "*"


class ControlError(RuntimeError):
    def __init__(self, message, candidates=None, response=None):
        super().__init__(message)
        self.candidates = candidates or []
        self.response = response or {}

    @property
    def answered_by_hook(self):
        return bool(self.response)


def default_host():
    return os.environ.get(HOST_VARIABLE, DEFAULT_HOST)


def default_port():
    return int(os.environ.get(PORT_VARIABLE, DEFAULT_PORT))


def screenshot_path(path):
    path = os.path.expanduser(path)
    directory = os.environ.get(SHOT_DIR_VARIABLE)
    if directory and not os.path.dirname(path):
        directory = os.path.expanduser(directory)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, path)
    return os.path.abspath(path)


class GuiClient:
    def __init__(self, host=None, port=None, timeout=30.0):
        self.host = host or default_host()
        self.port = port or default_port()
        self.timeout = timeout
        self._socket = None
        self._buffer = b""

    def connect(self):
        if self._socket is not None:
            return
        try:
            self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as error:
            raise ControlError(
                f"gui-control hook not reachable on {self.host}:{self.port} ({error}). "
                "Is the application running with its gui-control backend loaded?"
            ) from error

    def wait_ready(self, timeout=60.0, interval=0.2):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                self.connect()
                answer = self.ping()
                if answer.get("window"):
                    return answer
                last = "no window yet"
            except (ControlError, OSError) as error:
                last = error
                self.close()
            time.sleep(interval)
        raise ControlError(f"gui-control hook not ready within {timeout:.0f}s ({last})")

    def close(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None
            self._buffer = b""

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def request(self, op, **payload):
        self.connect()
        message = dict(payload)
        message["op"] = op

        timeout = payload.get("timeout")
        self._socket.settimeout(timeout / 1000.0 + 10.0 if timeout else self.timeout)
        self._socket.sendall(json.dumps(message).encode() + b"\n")

        while b"\n" not in self._buffer:
            chunk = self._socket.recv(65536)
            if not chunk:
                self.close()
                raise ControlError("gui-control hook closed the connection")
            self._buffer += chunk

        line, self._buffer = self._buffer.split(b"\n", 1)
        response = json.loads(line.decode())

        if not response.get("ok", False):
            raise ControlError(response.get("error", "unknown error"), response.get("candidates"), response)
        return response

    def ping(self):
        return self.request("ping")

    def tree(self, selector=None, depth=None, props=None, hidden=False, all_props=False):
        payload = {"hidden": hidden, "all_props": all_props}
        if selector:
            payload["selector"] = selector
        if depth is not None:
            payload["depth"] = depth
        if props is not None:
            payload["props"] = props
        response = self.request("tree", **payload)
        return response.get("tree") if "tree" in response else response.get("matches")

    def tap(self, selector=None, point=None, hidden=False):
        return self.request("tap", **_target(selector, point, hidden))

    def long_press(self, selector=None, point=None, duration=0, hidden=False):
        return self.request("long_press", duration=duration, **_target(selector, point, hidden))

    def swipe(self, to_x, to_y, selector=None, point=None, duration=0, hidden=False):
        return self.request("swipe", to_x=to_x, to_y=to_y, duration=duration, **_target(selector, point, hidden))

    def type_text(self, text):
        return self.request("type", text=text)

    def key(self, name):
        return self.request("key", key=name)

    def get(self, selector, prop=None, hidden=False):
        payload = {"selector": selector, "hidden": hidden}
        if prop:
            payload["prop"] = prop
        else:
            payload["props"] = DECLARED_PROPS
        response = self.request("get", **payload)
        return response.get("value", response.get("item"))

    def set(self, selector, prop, value, hidden=False):
        return self.request("set", selector=selector, prop=prop, value=value, hidden=hidden)

    def invoke(self, selector, method, args=None, hidden=False):
        return self.request("invoke", selector=selector, method=method, args=args or [], hidden=hidden).get("result")

    def scroll(self, selector, hidden=False):
        return self.request("scroll", selector=selector, hidden=hidden)

    def screenshot(self, path):
        return self.request("screenshot", path=screenshot_path(path))["path"]

    def wait_settled(self, quiet=300, timeout=5000):
        return self.request("wait", mode="settled", quiet=quiet, timeout=timeout)

    def wait_transition(self, timeout=5000):
        return self.request("wait", mode="transition", timeout=timeout)

    def wait_for(self, selector, present=True, timeout=5000, hidden=False):
        mode = "appears" if present else "disappears"
        return self.request("wait", mode=mode, selector=selector, timeout=timeout, hidden=hidden)

    def wait_signal(self, selector, signal, timeout=5000, hidden=False):
        return self.request("wait", mode="signal", selector=selector, signal=signal, timeout=timeout, hidden=hidden)


def _target(selector, point, hidden):
    if point is not None:
        return {"x": point[0], "y": point[1], "hidden": hidden}
    if not selector:
        raise ControlError("a selector or a point is required")
    return {"selector": selector, "hidden": hidden}
