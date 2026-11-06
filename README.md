# donutkit

A zero-dependency Python SDK for three things you can actually do with
[Donut Browser](https://github.com/zhom/donutbrowser):

1. **its local REST API** (`http://127.0.0.1:10108`) — profiles, proxies, VPNs,
   groups, storage-state import/export;
2. **a self-hosted `donut-sync` server** — the object-store protocol the app
   speaks, plus an inventory layer that the app itself is missing;
3. **Wayfern's Chrome DevTools Protocol endpoint** — DOM reads, screenshots and
   raw input, implemented over a hand-rolled WebSocket (no `websockets`, no
   `playwright`).

Everything here was written against a real, running Donut install, and every
claim below is marked with how it was checked. No part of this project tries to
defeat the app's paid-plan checks; it documents them instead
(see [Capability boundaries](#capability-boundaries)).

- Standard library only — `python3` 3.9+ runs it as-is, no `pip install` needed for the source tree.
- ~1.7k lines across `client.py` (REST), `sync.py` (object store + inventory), `cdp.py` (WebSocket/CDP), `cli.py`.
- Ships an API reference (`docs/DONUT_API_SPEC.md`, 2200 lines, cross-checked 86/86 against the app's own `/openapi.json`) and a findings report (`docs/RUNTIME_FINDINGS.md`).

---

## Install

```bash
git clone https://github.com/Gracetechvip/donutkit
cd donutkit
pip install -e .          # optional: gives you the `donutkit` entry point
python3 tests/test_client.py   # 22 offline contract checks, no Donut needed
```

Or just run it from the checkout — `python3 -m donutkit ...` works without installing.

## Configuration

| Variable | Used by | Meaning |
|---|---|---|
| `DONUT_API_TOKEN` | `DonutClient` | token from Donut → Settings → API (stored app-side in `api_token.dat`) |
| `DONUT_API_HOST` / `DONUT_API_PORT` | `DonutClient` | defaults `127.0.0.1` / `10108` |
| `DONUT_SYNC_URL` | `SyncServer` | your `donut-sync` base URL, e.g. `http://127.0.0.1:12342` |
| `SYNC_TOKEN` | `SyncServer` | shared secret; must equal the server's `SYNC_TOKEN` |

The app side needs `api_enabled = true` and a token for the first group, and
`sync_server_url` + `sync_source = "self_hosted"` for the second.

---

## Three usage groups

### 1. Local API

```python
from donutkit import DonutClient, DonutError

api = DonutClient()                     # reads DONUT_API_TOKEN
print(api.ping())                       # True

for p in api.list_profiles():
    print(p["id"], p["name"], p["is_running"], p.get("sync_mode"))

profile = api.create_profile("store-de", proxy_id="<proxy-id>")
api.bulk_edit([profile["id"]], {"tags": ["eu"]})
api.set_cloud_sync(profile["id"], "Regular")      # works on a free plan

try:
    api.run_and_wait_cdp(profile["id"], url="https://example.com")
except DonutError as exc:
    print(exc.status, exc.is_plan_gate)  # 402 True on a free plan
```

Covered surface: `list/get/create/update/delete_profile`, `bulk_edit`,
`get_fingerprint`, `list/create/update/delete_proxy`, `rotate_proxy`,
`realign_after_rotation`, `list/import/export/delete_vpn`, groups/tags/statuses,
`export_storage_state` / `import_storage_state` / `import_cookies`,
`browser_versions`, `set_cloud_sync`, `run_profile`, `kill_profile`,
`batch_run`, `batch_stop`.

### 2. Self-hosted sync server

Bring the server up (S3-compatible storage, optional TLS in front):

```bash
cp deploy/donut-sync.env.example deploy/.env    # then edit tokens
docker compose -f deploy/docker-compose.sync.yml up -d
curl -s localhost:12342/readyz                  # {"ok":true,...,"s3":true}
```

Then talk to it:

```python
from donutkit import SyncServer, Inventory

sync = SyncServer.from_env()            # DONUT_SYNC_URL + SYNC_TOKEN
print(sync.health()["status"], sync.ready()["s3"])

inv = Inventory(sync)
index = inv.build()                     # profiles + objects + sha256 + sizes
inv.publish()                           # write the index object
print(inv.verify())                     # compare index against live store
```

**Why `Inventory` exists:** the app's `sync/client.rs` has no "list remote
profiles" call, so after pointing a *second* machine at your server it downloads
nothing until something tells it which profile ids to fetch. `Inventory`
rebuilds that list from the object keys and writes
`data/profiles/<id>/metadata.json`, after which the app's own engine fetches the
rest. Measured on a blank device: `downloaded=4`, byte-identical.

```python
inv.restore("~/Library/Application Support/Donut Browser",
            settings_from="<a device that already works>",   # seeds vault.key / sync_token.dat
            dry_run=True)
```

### 3. Wayfern CDP

```python
from donutkit import cdp

if cdp.available(60991):
    with cdp.session(60991) as s:
        print(s.text()[:200])            # DOM.getOuterHTML → plain text
        s.screenshot("page.png")         # Page.captureScreenshot
        s.navigate("https://example.com")
        s.click(320, 240)                # Input.dispatchMouseEvent
        print(s.cookies())               # Network.getAllCookies
        print(s.capabilities())          # per-method OK / engine's refusal text
```

`CdpSession` speaks the protocol over a raw socket WebSocket client, so it works
where installing Playwright is inconvenient. `session.capabilities()` probes each
method and reports either `"OK"` or the engine's exact error string — useful
because what works depends on the plan (below).

### CLI

All three groups are exposed:

```bash
python3 -m donutkit api ping
python3 -m donutkit api list
python3 -m donutkit api run <profile-id> --url https://example.com
python3 -m donutkit sync health | verify | list | restore --root <dir> --dry-run
python3 -m donutkit cdp --port 60991 html --chars 500
python3 -m donutkit cdp --port 60991 caps
```

---

## Capability boundaries

Measured on a **free plan** (`browserAutomation = false`). The engine's refusals
are the feature here: the SDK surfaces them as typed errors instead of letting
you discover them halfway through a run.

| Area | Free plan | Evidence |
|---|---|---|
| Profile CRUD, bulk edit, groups, tags, statuses | ✅ works | create 3.2 s, rename, delete (`mode=erased`), 404 read-back |
| Proxy CRUD, `rotation_url`, Change-IP, fingerprint realign | ✅ works | 4 socks5 with auth; `bulk-edit {new_device:true}` |
| VPN import/export/list | ✅ works | list returns wireguard peers |
| Storage-state / cookie import & export | ✅ works | export 117 cookies / 14 origins; import verified |
| Turning on cloud sync (`set_cloud_sync`) | ✅ works | despite an outdated 402 comment in the source |
| Self-hosted sync upload/download/delete | ✅ works | `uploaded=614`, `downloaded=1` sha256 match |
| Server-side at-rest encryption | ✅ works on `nightly-*` builds | `verify-at-rest`: `complete=true plaintext=0`; the `:latest` tag (v0.36.0) does not read `SYNC_AT_REST_KEY` |
| CDP: `DOM.*`, `Page.navigate/captureScreenshot`, `Network.*`, `Input.*`, `Emulation.*` | ✅ works | 1.9 KB HTML, 46 KB PNG, cookies |
| `POST /v1/profiles/{id}/run` (launch browser via the app) | ⛔ **402** | `api_server.rs:3581`, empty body, ~10 ms |
| CDP `Runtime.evaluate` | ⛔ refused | `Browser automation requires a paid Donut Browser plan.` |
| `Wayfern.getFingerprint` / `getIdentity` | ⛔ refused / id only | `Custom fingerprints require a Donut Browser plan that includes them.` |

Full tables, including the four gotchas that cost the most time, are in
[`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) and
[`docs/RUNTIME_FINDINGS.md`](docs/RUNTIME_FINDINGS.md).

Two findings worth repeating because they silently corrupt measurements:

- **Egress-IP checks must run inside the browser stack.** A request issued from
  the Node side (`context.request`) reports the host's own IP even when the
  profile's proxy is active. Use `page.goto` + `DOM.getOuterHTML`.
- **Disabling sync does not clean up.** `snapshots/` (775 objects / 45 MB) and
  `.rclone_temp_put_*` multi-part leftovers (invisible to `ListObjectsV2`) stay
  behind. `donutkit sync prune` and the server's `migrate-at-rest` are the
  intended levers.

---

## Repository layout

```
donutkit/          client.py  sync.py  cdp.py  cli.py  errors.py
docs/              DONUT_API_SPEC.md   RUNTIME_FINDINGS.md   CAPABILITIES.md
deploy/            docker-compose.sync.yml   donut-sync.env.example   Caddyfile
examples/          quickstart.py
tests/             test_client.py           (offline, stub HTTP server)
```

## Verification

- `python3 tests/test_client.py` → **22 checks, all PASS**, no Donut install required.
- API reference (`docs/DONUT_API_SPEC.md`) checked endpoint-by-endpoint against a
  live `/openapi.json`: **86/86 operations**, 7 request/response structs field-by-field.
- Every ✅/⛔ row above was reproduced against a running app; the CDP numbers are
  from a live Wayfern target (`html 1989 B`, `png 46330 B`).

## License and attribution

AGPL-3.0 — see [LICENSE](LICENSE). The endpoint names and documented behaviour
are derived from the Donut Browser source, which is AGPL-3.0; this repository is
released under the same terms.

This project is **not affiliated with or endorsed by the Donut Browser authors**.
"Donut Browser" and "Wayfern" are used descriptively. Nothing here bypasses
licensing or plan checks — blocked features are reported, not circumvented.

---

## 中文说明

一句话：这是一个**纯标准库**的 Donut Browser 工具包，封装了三块能力——本地
REST API、自建 `donut-sync` 服务器、Wayfern 的 CDP；所有结论都在真机上复现过，
文档里每条能力都标了「✅ 可用 / ⛔ 被付费闸门挡住」以及验证方式。

**安装**：`git clone` 后直接 `python3 -m donutkit ...` 就能用；`pip install -e .`
只是额外提供 `donutkit` 命令。

**免费账户能做到什么**：profile / 代理 / VPN / 分组标签 / cookie 导入导出 /
开关同步全部可用；CDP 的 `DOM.*`、导航、截图、`Network.*`、原始鼠标键盘输入可用。
做不到的是「通过 App 启动浏览器」（`POST /v1/profiles/{id}/run` 返回 402）和
在页面里执行 JS（`Runtime.evaluate` 被引擎拒绝）。

**为什么要 `Inventory`**：App 的同步客户端没有「列远端 profile」的方法，换一台新
机器指向自建服务器时它不知道要下载什么。`Inventory` 从对象键重建清单并落
`metadata.json`，之后交给 App 自己的同步引擎，实测 `downloaded=4` 且逐字节一致。

**脱敏说明**：仓库内不含任何真实 token、同步密钥、profile UUID、代理地址或账号
信息；`deploy/donut-sync.env.example` 只是占位模板，真实配置走环境变量或
`deploy/.env`（已被 `.gitignore` 排除）。

本项目**与 Donut Browser 官方无关**，不代表其立场；不做任何绕过付费授权的改动。
