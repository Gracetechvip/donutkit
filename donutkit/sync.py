"""自建 donut-sync 服务器的客户端 + profile 清单（inventory）。

服务端接口取自 `donut-sync/src/http.rs`（`OBJECT_ROUTES` / `LEASE_ROUTES`）与
`sync.rs` 的 handler；认证是 `Authorization: Bearer <SYNC_TOKEN>`（`auth.rs:194-205`）。
本地 `_automation_kit/docker-compose.sync.yml` 起的那套已验证过上传/下载/删除/加密四条路径。

两个类：

* `SyncServer` —— 薄协议客户端：list/stat/get/put/delete/delete_prefix/ping。
* `Inventory` —— 建在协议之上的 profile 清单：publish/list/prune/verify/restore。
  Donut 客户端本身**没有**"列出远端 profile"的能力（`sync/client.rs` 里没有任何相关方法），
  所以自建场景下这一层必须由外部补上，新设备才能零手工恢复。
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from .errors import SyncError

DEFAULT_SERVER = "http://127.0.0.1:12342"
DEFAULT_INDEX_KEY = "_inventory/profiles.json"
PROFILE_PREFIX = "profiles/"
INDEX_VERSION = 1


class SyncServer:
    """donut-sync 的对象 API 客户端。

    `at_rest` 打开时，`presign-*` 返回的 `url` 指向服务端的 `/v1/transfer`
    （服务端解封后返回明文），所以调用方拿到的永远是明文对象。
    """

    def __init__(self, server: str = DEFAULT_SERVER, token: str = "", timeout: float = 60.0):
        if not token:
            raise SystemExit("缺少 SYNC_TOKEN：用参数、环境变量，或在 .env 里配置")
        self.server = server.rstrip("/")
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------ 构造
    @classmethod
    def from_env(cls, timeout: float = 60.0, env_file: Optional[str] = None) -> "SyncServer":
        """从环境变量 / `.env` 读 `SYNC_TOKEN`（以及可选的 `DONUT_SYNC_URL`）。

        `.env` 默认取本包所在目录的上一级（即 kit 根目录），也就是 compose 用的那个。
        """
        values: Dict[str, str] = {}
        if env_file is None:
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env_file = os.path.join(here, ".env")
        if env_file and os.path.isfile(env_file):
            for line in open(env_file, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
        server = os.environ.get("DONUT_SYNC_URL") or values.get("SYNC_PUBLIC_URL") or DEFAULT_SERVER
        token = os.environ.get("SYNC_TOKEN") or values.get("SYNC_TOKEN") or ""
        return cls(server=server, token=token, timeout=timeout)

    # -------------------------------------------------------------- plumbing
    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        req = urllib.request.Request(
            self.server + path,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise SyncError(exc.code, "POST", path, exc.read().decode("utf-8", "replace")) from None
        except urllib.error.URLError as exc:
            raise SyncError(0, "POST", path, f"connection failed: {exc.reason}") from None
        return json.loads(raw.decode()) if raw else None

    def _get(self, url: str) -> bytes:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise SyncError(exc.code, "GET", url.split("?")[0], exc.read().decode("utf-8", "replace")) from None

    def _put(self, url: str, body: bytes) -> None:
        req = urllib.request.Request(url, data=body, method="PUT", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            raise SyncError(exc.code, "PUT", url.split("?")[0], exc.read().decode("utf-8", "replace")) from None

    # ------------------------------------------------------------------- API
    def health(self) -> Dict[str, Any]:
        with urllib.request.urlopen(self.server + "/health", timeout=10) as resp:
            return json.loads(resp.read().decode())

    def ready(self) -> Dict[str, Any]:
        """`/readyz`：`{"status":"ready","s3":true,"storageEndpoint":…}`，503 时也返回 body。"""
        try:
            with urllib.request.urlopen(self.server + "/readyz", timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode())

    def ping(self) -> bool:
        try:
            return self.health().get("status") == "ok"
        except Exception:
            return False

    def list(self, prefix: str = "", max_keys: int = 1000) -> List[Dict[str, Any]]:
        """`POST /v1/objects/list` → 所有页拼起来的 `[{key,size,lastModified}]`。

        注意 rclone 后端的 `.rclone_temp_put_*` 临时对象不会出现在列表里（实测）。
        """
        out: List[Dict[str, Any]] = []
        token: Optional[str] = None
        while True:
            body: Dict[str, Any] = {"prefix": prefix, "maxKeys": max_keys}
            if token:
                body["continuationToken"] = token
            page = self._post("/v1/objects/list", body)
            out.extend(page.get("objects") or [])
            if not page.get("isTruncated"):
                return out
            token = page.get("nextContinuationToken")
            if not token:
                return out

    def stat(self, key: str) -> Dict[str, Any]:
        return self._post("/v1/objects/stat", {"key": key})

    def exists(self, key: str) -> bool:
        return bool(self.stat(key).get("exists"))

    def get(self, key: str, expires_in: int = 600) -> bytes:
        url = self._post("/v1/objects/presign-download", {"key": key, "expiresIn": expires_in})["url"]
        return self._get(url)

    def get_json(self, key: str) -> Any:
        return json.loads(self.get(key).decode())

    def put(self, key: str, body: bytes, expires_in: int = 600) -> None:
        url = self._post("/v1/objects/presign-upload", {"key": key, "expiresIn": expires_in})["url"]
        self._put(url, body)

    def put_json(self, key: str, value: Any) -> None:
        self.put(key, json.dumps(value, ensure_ascii=False, indent=1).encode())

    def delete(self, key: str) -> Any:
        return self._post("/v1/objects/delete", {"key": key})

    def delete_prefix(self, prefix: str, tombstone_key: str = "") -> int:
        """`POST /v1/objects/delete-prefix` —— 最高杀伤力的操作，返回删除数。

        `tombstone_key` 非空时会顺带写一条删除记录（客户端据此判断"远端被删过"）。
        共享 token 模式下空 prefix 是允许的（会清空整个桶），所以这里禁止空串。
        """
        if not prefix:
            raise ValueError("拒绝删除空 prefix：那会清空整个桶")
        result = self._post(
            "/v1/objects/delete-prefix", {"prefix": prefix, "tombstoneKey": tombstone_key}
        )
        return int(result.get("deletedCount") or 0)

    def snapshot_create(self, profile_id: str) -> Any:
        """`POST /v1/objects/snapshots/create` —— 服务端还原点（客户端同步时会自动建）。"""
        return self._post("/v1/objects/snapshots/create", {"key": PROFILE_PREFIX + profile_id})

    def snapshot_list(self, profile_id: str) -> Any:
        return self._post("/v1/objects/snapshots/list", {"key": PROFILE_PREFIX + profile_id})


class Inventory:
    """`_inventory/profiles.json`：远端 profile 清单，以及"把清单落到一台空白设备"。

    索引条目字段：`id, name, files, bytes, metadata_key, manifest_key, updated_at,
    last_sync, browser, version, host_os, metadata_modified`。
    """

    def __init__(self, server: SyncServer, index_key: str = DEFAULT_INDEX_KEY):
        self.server = server
        self.index_key = index_key

    # -------------------------------------------------------------- 远端扫描
    def scan(self) -> Dict[str, Dict[str, Any]]:
        """远端实际存在的 profile：`id → {files, bytes, metadata_key, manifest_key}`。"""
        found: Dict[str, Dict[str, Any]] = {}
        for obj in self.server.list(PROFILE_PREFIX):
            key = obj["key"]
            rest = key[len(PROFILE_PREFIX):]
            if "/" not in rest:
                continue
            pid, tail = rest.split("/", 1)
            entry = found.setdefault(
                pid, {"files": 0, "bytes": 0, "metadata_key": None, "manifest_key": None}
            )
            if tail == "metadata.json":
                entry["metadata_key"] = key
            elif tail == "manifest.json":
                entry["manifest_key"] = key
            elif tail.startswith("files/"):
                entry["files"] += 1
                entry["bytes"] += int(obj.get("size") or 0)
        return found

    def build(self) -> Dict[str, Any]:
        remote = self.scan()
        profiles: List[Dict[str, Any]] = []
        for pid, info in sorted(remote.items()):
            if not info["metadata_key"]:
                continue  # 没有 metadata 的目录不是可恢复的 profile
            entry: Dict[str, Any] = {
                "id": pid,
                "files": info["files"],
                "bytes": info["bytes"],
                "metadata_key": info["metadata_key"],
            }
            if info["manifest_key"]:
                entry["manifest_key"] = info["manifest_key"]
            try:
                stat = self.server.stat(info["metadata_key"])
                entry["metadata_size"] = stat.get("size")
                entry["metadata_modified"] = stat.get("lastModified")
            except SyncError:
                pass
            try:
                meta = json.loads(self.server.get(info["metadata_key"]).decode())
                for field in ("name", "browser", "version", "updated_at", "last_sync", "host_os", "sync_mode"):
                    if field in meta:
                        entry[field] = meta[field]
            except (SyncError, ValueError) as exc:
                entry["error"] = f"metadata unreadable: {exc}"
            profiles.append(entry)
        return {
            "version": INDEX_VERSION,
            "generated_at": _now(),
            "server": self.server.server,
            "profiles": profiles,
        }

    # ------------------------------------------------------------------ 索引
    def publish(self) -> Dict[str, Any]:
        index = self.build()
        self.server.put_json(self.index_key, index)
        return index

    def load(self) -> Dict[str, Any]:
        return self.server.get_json(self.index_key)

    def prune(self) -> Dict[str, Any]:
        """丢掉远端已不存在的条目（被 tombstone 掉的 profile）。"""
        index = self.load()
        remote = self.scan()
        keep = [p for p in index.get("profiles") or [] if p["id"] in remote]
        dropped = len(index.get("profiles") or []) - len(keep)
        index["profiles"] = keep
        index["generated_at"] = _now()
        self.server.put_json(self.index_key, index)
        return {"kept": len(keep), "dropped": dropped, "index": index}

    def verify(self) -> Dict[str, Any]:
        """索引 vs 远端对象数的一致性检查。"""
        index = self.load()
        remote = self.scan()
        problems: List[str] = []
        known = {p["id"] for p in index.get("profiles") or []}
        for p in index.get("profiles") or []:
            pid = p["id"]
            if pid not in remote:
                problems.append(f"MISSING {pid} ({p.get('name')}): 索引有、远端无")
            elif remote[pid]["files"] != p["files"]:
                problems.append(
                    f"DRIFT {pid}: 索引 {p['files']} 文件 vs 远端 {remote[pid]['files']}"
                )
        for pid, info in remote.items():
            if pid not in known and info["metadata_key"]:
                problems.append(f"ABSENT {pid}: 远端有、索引无（重新 publish 可补）")
        return {"ok": not problems, "problems": problems}

    # ---------------------------------------------------------------- 恢复
    def metadata_bytes(self, entry: Dict[str, Any]) -> bytes:
        return self.server.get(entry["metadata_key"])

    def restore(
        self,
        root: str,
        only: Optional[Iterable[str]] = None,
        force: bool = False,
        dry_run: bool = False,
        settings_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """把索引里的 profile 写成 `<root>/data/profiles/<id>/metadata.json`。

        之后由 App 自己的同步引擎下载文件（实测 `downloaded=N`、逐字节一致）。
        `settings_from` 给一个**已有设备**的数据目录时，会顺带铺好 `vault.key` /
        `sync_token.dat` / 最小 `app_settings.json`，于是这条命令就能 bootstrap 一台空白设备。
        """
        index = self.load()
        only_set = set(only or [])
        entries = [p for p in (index.get("profiles") or []) if not only_set or p["id"] in only_set]
        root = os.path.abspath(os.path.expanduser(root))
        profiles_dir = os.path.join(root, "data", "profiles")
        os.makedirs(profiles_dir, exist_ok=True)

        seeded: List[str] = []
        if settings_from:
            seeded = self._seed_settings(root, os.path.abspath(os.path.expanduser(settings_from)))

        restored, skipped = [], []
        for entry in entries:
            pid = entry["id"]
            dest_dir = os.path.join(profiles_dir, pid)
            dest = os.path.join(dest_dir, "metadata.json")
            if os.path.exists(dest) and not force:
                skipped.append(pid)
                continue
            if dry_run:
                restored.append(pid)
                continue
            body = self._metadata_verified(entry)
            os.makedirs(dest_dir, exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(body)
            restored.append(pid)
        return {"restored": restored, "skipped": skipped, "seeded": seeded, "root": root, "dry_run": dry_run}

    def _metadata_verified(self, entry: Dict[str, Any]) -> bytes:
        body = self.metadata_bytes(entry)
        json.loads(body.decode())  # 坏数据不要落到磁盘上
        return body

    def _seed_settings(self, root: str, source_root: str) -> List[str]:
        src = os.path.join(source_root, "settings")
        dst = os.path.join(root, "data", "settings")
        os.makedirs(dst, exist_ok=True)
        written: List[str] = []
        for name in ("vault.key", "sync_token.dat"):
            path = os.path.join(src, name)
            if not os.path.isfile(path):
                raise SystemExit(f"源 settings 里缺 {name}：{path}")
            target = os.path.join(dst, name)
            shutil.copyfile(path, target)
            os.chmod(target, 0o600)
            written.append(name)
        app = os.path.join(src, "app_settings.json")
        settings = json.load(open(app)) if os.path.isfile(app) else {}
        settings.update(
            {
                "api_enabled": False,
                "api_token": None,
                "api_port": settings.get("api_port") or 10108,
                "mcp_remote_enabled": False,
                "set_as_default_browser": False,
                "onboarding_completed": True,
                "sync_server_url": self.server.server,
                "sync_source": "self_hosted",
                "account_sync_server_url": None,
            }
        )
        json.dump(settings, open(os.path.join(dst, "app_settings.json"), "w"), indent=2, ensure_ascii=False)
        written.append("app_settings.json")
        return written


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_bytes(n: Optional[int]) -> str:
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n}B"
