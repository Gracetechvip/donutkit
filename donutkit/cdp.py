"""Wayfern 的 Chrome DevTools Protocol 客户端（纯标准库，无第三方依赖）。

三层：

1. **发现**：`GET /json/version`、`GET /json/list`（HTTP，10 行就够）。
2. **WebSocket**：一个最小 RFC 6455 客户端（掩码、分片、ping/pong、close），
   足以跑 CDP。Playwright 能做的事这里不做，所以也不需要它。
3. **便利方法**：`html()` / `screenshot()` / `navigate()` / `insert_text()` /
   `mouse_move()` / `click()` / `evaluate()`。

免费计划的实测边界（RUNTIME_FINDINGS.md 第 2 节）：`DOM.*`、`Page.navigate`、
`Page.captureScreenshot`、`Network.*`、`Input.*`、`Emulation.*` 都可用；
**`Runtime.evaluate` 会被引擎拒绝**——`Browser automation requires a paid Donut
Browser plan.`，`Wayfern.getFingerprint` 同样被拒。`CdpError.is_plan_gate` 用来区分
这种情况，不要当成网络错误重试。
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .errors import CdpError

OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


# ------------------------------------------------------------------ 发现（HTTP）
def version(port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """`GET /json/version` —— 服务端拿它判活（wayfern_manager.rs:2159）。"""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def targets(port: int, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """`GET /json/list` —— 每个 target 都有 `type`/`url`/`webSocketDebuggerUrl`。"""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def pages(port: int, url_contains: Optional[str] = None) -> List[Dict[str, Any]]:
    found = [t for t in targets(port) if t.get("type") == "page"]
    if url_contains:
        found = [t for t in found if url_contains in (t.get("url") or "")]
    return found


def browser_ws_url(port: int) -> str:
    return version(port)["webSocketDebuggerUrl"]


def page_ws_url(port: int, url_contains: Optional[str] = None) -> str:
    found = pages(port, url_contains)
    if not found:
        raise CdpError(f"没有匹配的 page target（port={port}）")
    return found[0]["webSocketDebuggerUrl"]


def available(port: int) -> bool:
    try:
        version(port)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------- WebSocket
class _WebSocket:
    """最小 WebSocket 客户端。只做 CDP 需要的那部分，同步阻塞。"""

    def __init__(self, url: str, timeout: float = 30.0):
        parsed = urlparse(url)
        if parsed.scheme not in ("ws", "wss"):
            raise CdpError(f"不是 ws/wss 地址：{url}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        raw = socket.create_connection((host, port), timeout=timeout)
        if parsed.scheme == "wss":
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=host)
        self.sock = raw
        self.sock.settimeout(timeout)
        self._buffer = b""
        self._handshake(host, port, path)

    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CdpError("WebSocket 握手被对端关闭")
            header += chunk
        head, _, rest = header.partition(b"\r\n\r\n")
        self._buffer = rest
        status_line = head.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status_line:
            raise CdpError(f"WebSocket 握手失败：{status_line}")

    # -- 帧 ---------------------------------------------------------------
    def send_text(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x80 | OP_TEXT])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read_exact(self, n: int) -> bytes:
        while len(self._buffer) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buffer)))
            if not chunk:
                raise CdpError("WebSocket 连接已断开")
            self._buffer += chunk
        out, self._buffer = self._buffer[:n], self._buffer[n:]
        return out

    def _send_control(self, opcode: int, payload: bytes = b"") -> None:
        header = bytearray([0x80 | opcode])
        header.append(0x80 | len(payload))
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv_message(self) -> str:
        """读一条完整消息（处理分片与控制帧）。"""
        fragments: List[bytes] = []
        while True:
            b1, b2 = self._read_exact(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", self._read_exact(2))
            elif length == 127:
                (length,) = struct.unpack("!Q", self._read_exact(8))
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == OP_PING:
                self._send_control(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                raise CdpError("服务端关闭了 WebSocket")
            fragments.append(payload)
            if fin:
                return b"".join(fragments).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self._send_control(OP_CLOSE, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ------------------------------------------------------------------------ 会话
class CdpSession:
    """一条 CDP 会话（默认连着某个 page target）。

        with CdpSession(60991) as s:
            s.navigate("https://example.com")
            print(s.html()[:200])

    也可以用 `s.send("Network.enable")` 直接发原始命令（错误会变成 `CdpError`）。
    """

    def __init__(self, port: int, url_contains: Optional[str] = None, *, browser: bool = False,
                 timeout: float = 30.0):
        self.port = port
        self.browser = browser
        url = browser_ws_url(port) if browser else page_ws_url(port, url_contains)
        self.ws_url = url
        self._ws = _WebSocket(url, timeout=timeout)
        self._next_id = 0
        self.events: List[Dict[str, Any]] = []

    # -- 协议 -------------------------------------------------------------
    def send(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        """发一条 CDP 命令，返回 `result`；`error` 变成 `CdpError`。"""
        self._next_id += 1
        message_id = self._next_id
        self._ws.send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            raw = self._ws.recv_message()
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if message.get("id") != message_id:
                if "method" in message:
                    self.events.append(message)  # 事件留着，别丢
                continue
            error = message.get("error")
            if error:
                raise CdpError(
                    error.get("message") or str(error), method=method, code=error.get("code")
                )
            return message.get("result")

    # -- 便利方法 ---------------------------------------------------------
    def navigate(self, url: str, wait: bool = True) -> Dict[str, Any]:
        """`Page.navigate`。免费计划可用（实测）。"""
        if wait:
            self.send("Page.enable")
        return self.send("Page.navigate", {"url": url})

    def html(self) -> str:
        """整个文档的 outerHTML（`DOM.getDocument` + `DOM.getOuterHTML`）。

        不需要 `Runtime.evaluate`，所以免费计划也能读——实测用它读到了 Cloudflare
        trace 的纯文本正文。
        """
        doc = self.send("DOM.getDocument", {"depth": -1, "pierce": False})
        return self.send("DOM.getOuterHTML", {"nodeId": doc["root"]["nodeId"]})["outerHTML"]

    def text(self) -> str:
        """去掉标签后的文本（粗粒度，够读纯文本页面）。"""
        import re

        return re.sub(r"<[^>]+>", " ", self.html())

    def screenshot(self, path: Optional[str] = None, fmt: str = "png") -> bytes:
        """`Page.captureScreenshot`；给了 `path` 就顺手落盘。"""
        data = self.send("Page.captureScreenshot", {"format": fmt})["data"]
        raw = base64.b64decode(data)
        if path:
            with open(path, "wb") as fh:
                fh.write(raw)
        return raw

    def evaluate(self, expression: str, await_promise: bool = False) -> Any:
        """`Runtime.evaluate` —— **免费计划会被引擎拒绝**（`CdpError.is_plan_gate`）。"""
        result = self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
        )
        if result.get("exceptionDetails"):
            raise CdpError(str(result["exceptionDetails"]), method="Runtime.evaluate")
        return (result.get("result") or {}).get("value")

    def mouse_move(self, x: float, y: float) -> None:
        self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})

    def click(self, x: float, y: float, button: str = "left") -> None:
        self.mouse_move(x, y)
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": 1})

    def insert_text(self, text: str) -> None:
        """`Input.insertText` —— 不经过键盘事件，但能进输入框（免费计划可用）。"""
        self.send("Input.insertText", {"text": text})

    def key(self, key: str, code: str = "", key_code: int = 0) -> None:
        self.send(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": key, "code": code or key, "windowsVirtualKeyCode": key_code},
        )
        self.send(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": key, "code": code or key, "windowsVirtualKeyCode": key_code},
        )

    def cookies(self) -> List[Dict[str, Any]]:
        """`Network.getAllCookies`（免费计划可用）。"""
        return self.send("Network.getAllCookies").get("cookies") or []

    def capabilities(self) -> Dict[str, str]:
        """探一遍各域是否被套餐闸住，返回 `{方法: "OK" 或引擎原话}`。"""
        matrix: Dict[str, str] = {}
        for method, params in (
            ("DOM.getDocument", {"depth": 1}),
            ("Page.captureScreenshot", {"format": "png"}),
            ("Runtime.evaluate", {"expression": "1+1", "returnByValue": True}),
            ("Network.getAllCookies", {}),
            ("Wayfern.getIdentity", {}),
            ("Wayfern.getFingerprint", {}),
        ):
            try:
                self.send(method, params)
                matrix[method] = "OK"
            except CdpError as exc:
                matrix[method] = exc.message
        return matrix

    # -- 生命周期 ---------------------------------------------------------
    def close(self) -> None:
        self._ws.close()

    def __enter__(self) -> "CdpSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def session(port: int, url_contains: Optional[str] = None, **kwargs: Any) -> CdpSession:
    """`CdpSession` 的工厂；`with cdp.session(60991) as s:` 这样用。"""
    return CdpSession(port, url_contains, **kwargs)
