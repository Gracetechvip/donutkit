#!/usr/bin/env python3
"""Offline contract tests for :mod:`donutkit.client`.

Runs against a stub HTTP server that mimics the shapes of the real Donut local
API, so it needs no Donut install and no network access::

    python3 tests/test_client.py

Verified here:
  * ``Authorization: Bearer`` header is sent on every request
  * request bodies match ``CreateProfileRequest`` / ``CreateProxyRequest`` /
    ``RunProfileRequest`` (proxy XOR vpn is enforced client-side)
  * response envelopes are unwrapped (``{"profiles": [...]}``, ``{"profile": {...}}``)
  * 402 / 429 / 400 error mapping, including ``{"code": ...}`` extraction
  * CDP discovery (``/json/version``, ``/json/list``) and target filtering
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from donutkit import Donut, DonutError  # noqa: E402

TOKEN = "test-token"
SEEN = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else None

    def _auth_ok(self):
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def do_GET(self):
        SEEN.append(("GET", self.path, None))
        if self.path == "/openapi.json":
            return self._json(200, {"openapi": "3.1.0"})
        if self.path == "/v1/profiles":
            if not self._auth_ok():
                return self._json(401, {})
            return self._json(200, {"profiles": [{"id": "p1", "name": "Store DE", "is_running": False}], "total": 1})
        if self.path == "/v1/proxies":
            if not self._auth_ok():
                return self._json(401, {})
            return self._json(200, [{"id": "px1", "name": "socks", "proxy_settings": {"proxy_type": "socks5", "host": "1.2.3.4", "port": 1080, "username": None, "password": None, "vless_uri": None}, "rotation_url": "https://provider.invalid/rotate"}])
        if self.path.startswith("/v1/profiles/p1/fingerprint"):
            if not self._auth_ok():
                return self._json(401, {})
            return self._json(200, {"fingerprint": json.dumps({"timezone": "Europe/Berlin", "language": "de-DE"})})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read()
        SEEN.append(("POST", self.path, body))
        if not self._auth_ok():
            return self._json(401, {})
        if self.path == "/v1/profiles":
            # mirrors CreateProfileRequest required fields
            assert body["browser"] == "wayfern", body
            assert "name" in body
            return self._json(200, {"profile": {"id": "new1", "name": body["name"], "browser": body["browser"], "version": "152.0", "is_running": False}})
        if self.path == "/v1/profiles/p1/run":
            return self._json(200, {"profile_id": "p1", "remote_debugging_port": self.server.cdp_port, "headless": bool(body.get("headless")), "attached": False})
        if self.path == "/v1/profiles/p402/run":
            # real engine answers 402 with an empty body
            return self._json(402, "")
        if self.path == "/v1/profiles/prate/run":
            payload = json.dumps({"code": "RATE_LIMITED"}).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/v1/proxies":
            return self._json(200, {"id": "px2", "name": body["name"], "proxy_settings": body["proxy_settings"], "rotation_url": body.get("rotation_url")})
        if self.path == "/v1/proxies/px1/rotate":
            return self._json(200, {"proxy_id": "px1", "status": 200, "elapsed_ms": 412, "error": None})
        if self.path == "/v1/proxies/pxnorot/rotate":
            return self._json(400, {"code": "PROXY_ROTATION_URL_MISSING"})
        if self.path == "/v1/profiles/bulk-edit":
            return self._json(200, {"changed": len(body["profile_ids"])})
        if self.path == "/v1/profiles/p1/kill":
            return self._json(200, {})
        self._json(404, {"error": "not found"})


class CdpHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/json/version":
            return self._json(200, {"Browser": "Wayfern/152.0", "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/browser/abc"})
        if self.path == "/json/list":
            return self._json(200, [
                {"id": "1", "type": "page", "url": "https://example.com", "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/page/1"},
                {"id": "2", "type": "page", "url": "https://other.test", "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/page/2"},
            ])
        self._json(404, {})


def serve(handler, port=0):
    httpd = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    api_srv = serve(Handler)
    cdp_srv = serve(CdpHandler)
    api_srv.cdp_port = cdp_srv.server_address[1]
    api_port = api_srv.server_address[1]

    api = Donut(token=TOKEN, port=api_port)
    failures = []
    passed = 0

    def check(label, cond, detail=""):
        nonlocal passed
        print(("PASS " if cond else "FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
        if cond:
            passed += 1
        else:
            failures.append(label)

    check("ping", api.ping() is True)

    profiles = api.list_profiles()
    check("list_profiles unwraps .profiles", bool(profiles) and profiles[0]["id"] == "p1")

    prox = api.create_proxy("socks", "1.2.3.4", 1080, username="u", password="p", rotation_url="https://provider.invalid/rotate")
    body = [s for s in SEEN if s[1] == "/v1/proxies" and s[0] == "POST"][-1][2]
    check("create_proxy body shape",
          body["proxy_settings"] == {"proxy_type": "socks5", "host": "1.2.3.4", "port": 1080, "username": "u", "password": "p"}
          and body["rotation_url"] == "https://provider.invalid/rotate", str(body))
    check("create_proxy returns id", prox["id"] == "px2")

    created = api.create_profile("Store DE", proxy_id="px1", wayfern_config={"os": "windows"})
    body = [s for s in SEEN if s[1] == "/v1/profiles" and s[0] == "POST"][-1][2]
    check("create_profile body has browser/name/proxy/wayfern_config",
          body == {"name": "Store DE", "browser": "wayfern", "proxy_id": "px1", "wayfern_config": {"os": "windows"}}, str(body))
    check("create_profile unwraps .profile", created["id"] == "new1")

    try:
        api.create_profile("bad", proxy_id="a", vpn_id="b")
        check("proxy/vpn mutual exclusion raises locally", False)
    except ValueError:
        check("proxy/vpn mutual exclusion raises locally", True)

    run = api.run_profile("p1", url="https://example.com")
    body = [s for s in SEEN if s[1] == "/v1/profiles/p1/run"][-1][2]
    check("run_profile body", body == {"headless": False, "url": "https://example.com"}, str(body))
    check("RunResult port", run.port == cdp_srv.server_address[1])
    check("RunResult attached=false", run.attached is False)
    check("cdp_http_url", run.cdp_http_url == f"http://127.0.0.1:{cdp_srv.server_address[1]}")
    check("browser_ws_url from /json/version", run.browser_ws_url.endswith("/devtools/browser/abc"))
    check("page_ws_url picks first page", run.page_ws_url().endswith("/devtools/page/1"))
    check("page_ws_url filters by url", run.page_ws_url("other.test").endswith("/devtools/page/2"))

    fp = api.get_fingerprint("p1")
    check("get_fingerprint decodes json string", fp == {"timezone": "Europe/Berlin", "language": "de-DE"}, str(fp))

    try:
        api.run_profile("p402")
        check("402 surfaces as plan gate", False)
    except DonutError as exc:
        check("402 surfaces as plan gate", exc.status == 402 and exc.is_plan_gate)

    try:
        api.run_profile("prate")
        check("429 surfaces as rate limit", False)
    except DonutError as exc:
        check("429 surfaces as rate limit", exc.status == 429 and exc.is_rate_limited)

    try:
        api.rotate_proxy("pxnorot")
        check("400 + code extraction", False)
    except DonutError as exc:
        check("400 + code extraction", exc.status == 400 and exc.code == "PROXY_ROTATION_URL_MISSING", str(exc))

    rot = api.rotate_proxy("px1")
    check("rotate_proxy parses RotationResult", rot["status"] == 200 and rot["elapsed_ms"] == 412)

    realign = api.realign_after_rotation("px1", ["p1", "p2"])
    bulk = [s for s in SEEN if s[1] == "/v1/profiles/bulk-edit"][-1][2]
    check("realign sends new_device patch",
          bulk["patch"] == {"new_device": True} and realign["profiles_reset"] == 2, str(bulk))

    api.kill_profile("p1")
    check("kill_profile posts", any(s[1] == "/v1/profiles/p1/kill" for s in SEEN))

    try:
        api.update_profile("p1", wayfern_config={})
        check("update_profile rejects unknown field", False)
    except ValueError:
        check("update_profile rejects unknown field", True)

    api_srv.shutdown()
    cdp_srv.shutdown()
    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print(f"ALL {passed} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
