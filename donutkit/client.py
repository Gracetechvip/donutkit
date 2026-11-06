"""Donut Browser 本地 REST API 客户端（`127.0.0.1:<api_port>`，默认 10108）。

端点与字段全部取自 `src-tauri/src/api_server.rs` 的 `#[utoipa::path]` 与 `struct` 定义；
已在真机 `Donut.app` v0.36.0 的 `/openapi.json` 上逐条比对过（86/86，字段名逐字段相符）。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .errors import DonutError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10108  # api_server.rs:1511 的默认端口；被占用时 App 会退到 10000+rand


class RunResult:
    """`POST /v1/profiles/{id}/run` 的响应 + CDP 端点解析。

    RunProfileResponse（api_server.rs:448）::

        {"profile_id": "…", "remote_debugging_port": 52114, "headless": false, "attached": false}

    注意响应里**没有** ws 地址：浏览器级 WebSocket 要去 `GET /json/version` 的
    `webSocketDebuggerUrl` 拿（见 `donutkit.cdp`）。
    """

    def __init__(self, payload: Dict[str, Any], api: "DonutClient"):
        self.raw = payload
        self.profile_id = payload["profile_id"]
        self.port = int(payload["remote_debugging_port"])
        self.headless = bool(payload.get("headless", False))
        self.attached = bool(payload.get("attached", False))
        self._api = api

    @property
    def cdp_http_url(self) -> str:
        """Playwright `chromium.connectOverCDP()` 要的 http 地址。

        Wayfern 以 `--remote-debugging-address=127.0.0.1 --remote-debugging-port=<port>`
        启动（wayfern_manager.rs:3106-3107）；服务端自己也用
        `http://127.0.0.1:{port}/json/version` 判活（wayfern_manager.rs:2159）。
        """
        return f"http://127.0.0.1:{self.port}"

    @property
    def browser_ws_url(self) -> str:
        return self._api.browser_ws_url(self.port)

    def page_ws_url(self, url_contains: Optional[str] = None) -> str:
        return self._api.page_ws_url(self.port, url_contains)

    def session(self, url_contains: Optional[str] = None):
        """直接在这个浏览器上开一个 CDP 会话（`donutkit.cdp.session`）。"""
        from . import cdp

        return cdp.session(self.port, url_contains=url_contains)

    def __repr__(self) -> str:
        return (
            f"RunResult(profile_id={self.profile_id!r}, port={self.port}, "
            f"headless={self.headless}, attached={self.attached})"
        )


class DonutClient:
    """本地 REST API 客户端。所有 `/v1/*` 都要 `Authorization: Bearer <api_token>`。"""

    def __init__(
        self,
        token: Optional[str] = None,
        host: str = DEFAULT_HOST,
        port: Optional[int] = None,
        timeout: float = 60.0,
    ):
        self.token = token or os.environ.get("DONUT_API_TOKEN", "")
        self.host = host or os.environ.get("DONUT_API_HOST", DEFAULT_HOST)
        self.port = int(port or os.environ.get("DONUT_API_PORT") or DEFAULT_PORT)
        self.timeout = timeout
        if not self.token:
            raise SystemExit(
                "缺少 API token：在 Donut 的 Settings → Local API 里复制，"
                "然后传 token= 或设 DONUT_API_TOKEN。"
            )

    @classmethod
    def from_env(cls, timeout: float = 60.0) -> "DonutClient":
        return cls(timeout=timeout)

    # ------------------------------------------------------------------ 基础
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Any] = None,
        query: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = self.base_url + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        data = None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:  # 4xx/5xx 仍带 body，必须读出来
            raw = exc.read()
            text = raw.decode("utf-8", "replace").strip()
            code = None
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    code = parsed.get("code")
            except ValueError:
                pass
            raise DonutError(exc.code, text, method, path, code) from None
        except urllib.error.URLError as exc:
            raise DonutError(0, f"连接失败：{exc.reason}", method, path) from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode())
        except ValueError:
            return raw.decode("utf-8", "replace")

    # --------------------------------------------------------------- 健康检查
    def openapi(self) -> Dict[str, Any]:
        """`GET /openapi.json`（api_server.rs:1121，不经过鉴权层）。"""
        with urllib.request.urlopen(self.base_url + "/openapi.json", timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def ping(self) -> bool:
        try:
            self.openapi()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- profiles
    def list_profiles(self) -> List[Dict[str, Any]]:
        """`GET /v1/profiles` → `{profiles, total}`（api_server.rs:1653）。"""
        return self.request("GET", "/v1/profiles")["profiles"]

    def get_profile(self, profile_id: str) -> Dict[str, Any]:
        return self.request("GET", f"/v1/profiles/{profile_id}")["profile"]

    def find_profile(self, name: str) -> Optional[Dict[str, Any]]:
        for profile in self.list_profiles():
            if profile.get("name") == name:
                return profile
        return None

    def create_profile(
        self,
        name: str,
        *,
        browser: str = "wayfern",
        version: Optional[str] = None,
        proxy_id: Optional[str] = None,
        vpn_id: Optional[str] = None,
        wayfern_config: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        ephemeral: Optional[bool] = None,
        temporary: Optional[bool] = None,
        dns_server: Optional[str] = None,
        status_id: Optional[str] = None,
        start_urls: Optional[Sequence[str]] = None,
        launch_hook: Optional[str] = None,
    ) -> Dict[str, Any]:
        """`POST /v1/profiles`（api_server.rs:1793，body=CreateProfileRequest:145）。

        指纹与出口对齐（源码事实，别想当然）：

        * `wayfern_config` 省略或 `{}` → 创建时生成新设备；生成过程**经这个 profile 的
          代理**探测出口，把出口的时区/语言/经纬度写进指纹（profile/manager.rs:498 →
          wayfern_manager.rs:2823-2835）。所以"建号时 tz/语言对齐出口"是自动的。
        * 给 `wayfern_config.fingerprint` → 钉死设备，不生成、也不会被出口覆盖。
        * `wayfern_config.os` 非宿主 OS 需要付费（否则 402）；`launch_args` 同理。
        * `proxy_id` 与 `vpn_id` 互斥。
        """
        if proxy_id and vpn_id:
            raise ValueError("proxy_id 与 vpn_id 互斥：一次只能给一个路由")
        body: Dict[str, Any] = {"name": name, "browser": browser}
        optional = {
            "version": version,
            "proxy_id": proxy_id,
            "vpn_id": vpn_id,
            "wayfern_config": wayfern_config,
            "group_id": group_id,
            "tags": list(tags) if tags is not None else None,
            "ephemeral": ephemeral,
            "temporary": temporary,
            "dns_server": dns_server,
            "status_id": status_id,
            "start_urls": list(start_urls) if start_urls is not None else None,
            "launch_hook": launch_hook,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        return self.request("POST", "/v1/profiles", body)["profile"]

    def create_profiles(self, specs: Iterable[Dict[str, Any]], *, delay: float = 0.0) -> List[Dict[str, Any]]:
        """批量创建：逐个失败不中断，返回成功的那些（失败打到 stderr）。"""
        created: List[Dict[str, Any]] = []
        for spec in specs:
            try:
                created.append(self.create_profile(**spec))
            except DonutError as exc:
                print(f"[create failed] {spec.get('name')}: {exc}", file=sys.stderr)
            if delay:
                time.sleep(delay)
        return created

    def update_profile(self, profile_id: str, **fields: Any) -> Dict[str, Any]:
        """`PUT /v1/profiles/{id}`（body=UpdateProfileRequest:195）。

        这里**没有** `wayfern_config`：改指纹/时区不走这个端点（见
        `realign_after_rotation`）。`proxy_id`/`vpn_id` 空串表示解除绑定。
        """
        allowed = {
            "name", "version", "proxy_id", "vpn_id", "launch_hook", "release_type",
            "group_id", "tags", "extension_group_id", "proxy_bypass_rules",
            "sync_mode", "clear_on_close", "dns_server", "status_id", "start_urls",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"UpdateProfileRequest 没有这些字段: {sorted(unknown)}")
        return self.request("PUT", f"/v1/profiles/{profile_id}", fields)["profile"]

    def delete_profile(self, profile_id: str) -> None:
        """`DELETE /v1/profiles/{id}`（api_server.rs:2181）。"""
        self.request("DELETE", f"/v1/profiles/{profile_id}")

    def bulk_edit(self, profile_ids: Sequence[str], patch: Dict[str, Any]) -> int:
        """`POST /v1/profiles/bulk-edit`（api_server.rs:2488，body=BulkEditRequest:259）。

        `patch` 是 `ProfilePatch`（profile/patch.rs:22，`deny_unknown_fields`）：
        `status_id, tags_add, tags_remove, note, group_id, extension_group_id,
        dns_blocklist, dns_server, proxy_bypass_rules, start_urls, launch_hook,
        clear_on_close, randomize_fingerprint_on_launch, webrtc_mode, block_images,
        block_webgl, restore_session, new_device`。返回实际改变的数量。
        """
        return self.request(
            "POST", "/v1/profiles/bulk-edit", {"profile_ids": list(profile_ids), "patch": patch}
        )["changed"]

    def get_fingerprint(self, profile_id: str) -> Optional[Any]:
        """`GET /v1/profiles/{id}/fingerprint`（api_server.rs:1740）。

        返回的 `fingerprint` 是 JSON 字符串（WayfernConfig.fingerprint 的存储形态），
        这里替你解成对象；`None` 表示没有可展示的设备（identity 型 profile + 免费计划
        的实测结果就是这样，见 RUNTIME_FINDINGS.md）。
        """
        payload = self.request("GET", f"/v1/profiles/{profile_id}/fingerprint")
        raw = payload.get("fingerprint")
        if raw is None:
            return None
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except ValueError:
                return raw
        return raw

    # ------------------------------------------------------------------ 启动
    def run_profile(self, profile_id: str, url: Optional[str] = None, headless: bool = False) -> RunResult:
        """`POST /v1/profiles/{id}/run`（api_server.rs:3575）。

        * 已在跑的 profile 会被**接管**（`attached=True`），端口是它现有的 DevTools 端口；
        * 否则服务端先 bind 一个空闲端口（api_server.rs:3647）再交给 Wayfern；
        * 402 = 没有 `browserAutomation`；409 = 被 team lock / 另一会话占用。
        """
        body: Dict[str, Any] = {"headless": headless}
        if url is not None:
            body["url"] = url
        return RunResult(self.request("POST", f"/v1/profiles/{profile_id}/run", body), self)

    def run_and_wait_cdp(self, profile_id: str, url: Optional[str] = None, timeout: float = 30.0) -> RunResult:
        """启动并等 `/json/version` 真的可用。"""
        run = self.run_profile(profile_id, url=url)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.request_cdp(run.port, "/json/version")
                return run
            except Exception:
                time.sleep(0.3)
        raise DonutError(0, f"CDP 在 {timeout}s 内没就绪", "GET", f"http://127.0.0.1:{run.port}/json/version")

    def kill_profile(self, profile_id: str) -> None:
        """`POST /v1/profiles/{id}/kill`（api_server.rs:4818，同样要 browserAutomation）。"""
        self.request("POST", f"/v1/profiles/{profile_id}/kill")

    def open_url(self, profile_id: str, url: str) -> None:
        self.request("POST", f"/v1/profiles/{profile_id}/open-url", {"url": url})

    def batch_run(
        self,
        profile_ids: Sequence[str],
        url: Optional[str] = None,
        headless: bool = False,
        delay_ms: Optional[int] = None,
        concurrency: Optional[int] = None,
    ) -> Dict[str, Any]:
        """`POST /v1/profiles/batch/run`（body=BatchRunRequest:663）。"""
        body: Dict[str, Any] = {"profile_ids": list(profile_ids), "headless": headless}
        if url is not None:
            body["url"] = url
        if delay_ms is not None:
            body["delay_ms"] = delay_ms
        if concurrency is not None:
            body["concurrency"] = concurrency
        return self.request("POST", "/v1/profiles/batch/run", body)

    def batch_stop(self, profile_ids: Sequence[str]) -> Dict[str, Any]:
        return self.request("POST", "/v1/profiles/batch/stop", {"profile_ids": list(profile_ids)})

    # ------------------------------------------------------------------ CDP
    def request_cdp(self, port: int, path: str) -> Any:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return json.loads(resp.read().decode())

    def browser_ws_url(self, port: int) -> str:
        return self.request_cdp(port, "/json/version")["webSocketDebuggerUrl"]

    def cdp_targets(self, port: int) -> List[Dict[str, Any]]:
        return self.request_cdp(port, "/json/list")

    def page_ws_url(self, port: int, url_contains: Optional[str] = None) -> str:
        pages = [t for t in self.cdp_targets(port) if t.get("type") == "page"]
        if url_contains:
            pages = [t for t in pages if url_contains in (t.get("url") or "")]
        if not pages:
            raise DonutError(0, "没有匹配的 page target", "GET", f"http://127.0.0.1:{port}/json/list")
        return pages[0]["webSocketDebuggerUrl"]

    # ---------------------------------------------------------------- proxies
    def list_proxies(self) -> List[Dict[str, Any]]:
        """`GET /v1/proxies` → 裸数组 `Vec<ApiProxyResponse>`（api_server.rs:2685）。

        每项 `{id, name, proxy_settings{proxy_type,host,port,username,password,vless_uri},
        rotation_url}`；`rotation_url` 就是 Change-IP 链接。
        """
        return self.request("GET", "/v1/proxies")

    def get_proxy(self, proxy_id: str) -> Dict[str, Any]:
        return self.request("GET", f"/v1/proxies/{proxy_id}")

    def create_proxy(
        self,
        name: str,
        host: str,
        port: int,
        *,
        proxy_type: str = "socks5",
        username: Optional[str] = None,
        password: Optional[str] = None,
        vless_uri: Optional[str] = None,
        rotation_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """`POST /v1/proxies`（body=CreateProxyRequest:363）。

        `proxy_type` ∈ `http|https|socks5|vless|vmess|trojan|hysteria2`；后四种把整条分享
        链接放 `vless_uri`（字段名是历史遗留）。带账密的代理，凭据不会进浏览器命令行——
        本地起一个 donut-proxy 进程，凭据走 `DONUT_PROXY_USERNAME/PASSWORD` 环境变量
        （proxy_manager.rs:2321/2324），浏览器只看到 `socks5://127.0.0.1:<本地端口>`。
        """
        settings: Dict[str, Any] = {"proxy_type": proxy_type, "host": host, "port": int(port)}
        if username is not None:
            settings["username"] = username
        if password is not None:
            settings["password"] = password
        if vless_uri is not None:
            settings["vless_uri"] = vless_uri
        body: Dict[str, Any] = {"name": name, "proxy_settings": settings}
        if rotation_url is not None:
            body["rotation_url"] = rotation_url
        return self.request("POST", "/v1/proxies", body)

    def update_proxy(self, proxy_id: str, **fields: Any) -> Dict[str, Any]:
        allowed = {"name", "proxy_settings", "rotation_url"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"UpdateProxyRequest 没有这些字段: {sorted(unknown)}")
        return self.request("PUT", f"/v1/proxies/{proxy_id}", fields)

    def rotate_proxy(self, proxy_id: str) -> Dict[str, Any]:
        """`POST /v1/proxies/{id}/rotate`（api_server.rs:2887）—— 触发 Change-IP。

        返回 `RotationResult{proxy_id,status,elapsed_ms,error}`（proxy_rotation.rs:17）。
        400 = 没登记 rotation_url；502 = 供应商拒了/超时/打不通。

        **轮换只换 IP**：已存指纹里的时区/语言不会跟着变，见
        `realign_after_rotation`。
        """
        return self.request("POST", f"/v1/proxies/{proxy_id}/rotate")

    def delete_proxy(self, proxy_id: str) -> None:
        self.request("DELETE", f"/v1/proxies/{proxy_id}")

    def realign_after_rotation(
        self, proxy_id: str, profile_ids: Sequence[str], *, wait_ms: int = 0
    ) -> Dict[str, Any]:
        """轮换 IP，并让这些 profile 下次启动时按新出口重建设备。

        为什么只能这么做（源码事实）：重写「已存指纹的位置」只有 Tauri 命令
        `match_profile_fingerprint_to_exit`（fingerprint_consistency.rs:481），它没有
        暴露到 `127.0.0.1:10108`；`UpdateProfileRequest`(:195) 没有 `wayfern_config`，
        `ProfilePatch`(:22) 也没有 location。可达路径是 `bulk_edit({"new_device": True})`
        —— 下次启动时 browser_runner 会重新 `generate_fingerprint_config`
        （browser_runner.rs:685），而生成过程经代理探出口再写 tz/lang
        （wayfern_manager.rs:2823-2835）。代价：整台设备被换掉 + 消耗一次生成配额。
        """
        result = self.rotate_proxy(proxy_id)
        if wait_ms:
            time.sleep(wait_ms / 1000.0)
        changed = self.bulk_edit(profile_ids, {"new_device": True})
        return {"rotation": result, "profiles_reset": changed}

    # ------------------------------------------------------------------- VPN
    def list_vpns(self) -> List[Dict[str, Any]]:
        return self.request("GET", "/v1/vpns")

    def import_vpn(self, content: str, filename: str, name: Optional[str] = None) -> Dict[str, Any]:
        """`POST /v1/vpns/import`（body=ImportVpnRequest:404）。

        `content` 是 WireGuard `.conf` 原文；上游只接受单 peer
        （vpn/storage.rs:421 `ensure_single_peer`）。启动时 Donut 会拉起
        `donut-proxy vpn-worker start --id --port --config-path`
        （vpn_worker_runner.rs:313-323），在 127.0.0.1 上开 SOCKS5，浏览器只看到它
        （browser_runner.rs:554）。
        """
        body: Dict[str, Any] = {"content": content, "filename": filename}
        if name is not None:
            body["name"] = name
        return self.request("POST", "/v1/vpns/import", body)

    def export_vpn(self, vpn_id: str) -> str:
        return self.request("GET", f"/v1/vpns/{vpn_id}/export")["config_data"]

    def delete_vpn(self, vpn_id: str) -> None:
        self.request("DELETE", f"/v1/vpns/{vpn_id}")

    # -------------------------------------------------------------- 其它常用
    def list_groups(self) -> List[Dict[str, Any]]:
        return self.request("GET", "/v1/groups")
    def create_group(self, name: str) -> Dict[str, Any]:
        return self.request("POST", "/v1/groups", {"name": name})

    def list_tags(self) -> Any:
        return self.request("GET", "/v1/tags")

    def list_statuses(self) -> List[Dict[str, Any]]:
        return self.request("GET", "/v1/statuses")

    def export_storage_state(
        self, profile_id: str, include_cookies: bool = True, indexed_db: bool = False
    ) -> Dict[str, Any]:
        """`GET /v1/profiles/{id}/storage-state`（api_server.rs:5205）—— 真机实测能拿到
        117 cookies / 14 origins 这样的实际数据。"""
        return self.request(
            "GET",
            f"/v1/profiles/{profile_id}/storage-state",
            query={"include_cookies": str(include_cookies).lower(), "indexed_db": str(indexed_db).lower()},
        )

    def import_storage_state(self, profile_id: str, state: Dict[str, Any]) -> Any:
        """`POST /v1/profiles/{id}/storage-state`（api_server.rs:5244）。"""
        return self.request("POST", f"/v1/profiles/{profile_id}/storage-state", state)

    def import_cookies(self, profile_id: str, content: str) -> Dict[str, Any]:
        """`POST /v1/profiles/{id}/cookies/import`（api_server.rs:5277）：JSON 数组或
        Netscape `cookies.txt`，自动识别。"""
        return self.request("POST", f"/v1/profiles/{profile_id}/cookies/import", {"content": content})

    def set_cloud_sync(self, profile_id: str, mode: str) -> Dict[str, Any]:
        """`POST /v1/profiles/{id}/cloud-sync`（api_server.rs:3784），mode ∈
        `Disabled|Regular|Encrypted`。实测免费计划也能开（文档里的 402 是过时注释）。"""
        return self.request("POST", f"/v1/profiles/{profile_id}/cloud-sync", {"mode": mode})

    def browser_versions(self, browser: str = "wayfern") -> Any:
        return self.request("GET", f"/v1/browsers/{browser}/versions")

    def browser_downloaded(self, version: str, browser: str = "wayfern") -> Any:
        return self.request("GET", f"/v1/browsers/{browser}/versions/{version}/downloaded")

    def download_browser(self, browser: str = "wayfern", version: Optional[str] = None) -> Any:
        body: Dict[str, Any] = {"browser": browser}
        if version is not None:
            body["version"] = version
        return self.request("POST", "/v1/browsers/download", body)


# 兼容旧脚本里的名字
Donut = DonutClient
