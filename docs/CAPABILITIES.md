# 现在能实现什么（以及哪些做不了）

一句话：**在这台机器上，一个免费版 Donut 账号 + 一套自建同步服务器 + 一条纯标准库的
SDK，已经覆盖「profile 批量管理 / 代理与 VPN / 数据同步与多设备恢复 / 浏览器 DOM 读取」，
唯一缺的是「程序化启动浏览器并把脚本注入页面」——那两件事被引擎的付费闸门挡着。**

下面的每一项都标了验证方式；带 ✅ 的在本机真机跑过，不是"应该可以"。

---

## 1. 本地 REST API（`127.0.0.1:10108`）

### 免费可用的部分 ✅

| 能力 | 端点 / 方法 | 实测 |
|---|---|---|
| 列/读/建/改/删 profile | `DonutClient.list_profiles/get_profile/create_profile/update_profile/delete_profile` | ✅ 建号 3.2s、改名、删除（`mode=erased`）、404 读回 |
| 批量打补丁（标签/分组/状态/新设备…） | `bulk_edit(ids, patch)` | ✅ `changed=1` |
| 读指纹配置 | `get_fingerprint(id)` | ✅ 200（identity 型 profile 返回 `null`，见 §4） |
| 代理 CRUD + Change-IP | `create_proxy/update_proxy/rotate_proxy` | ✅ 4 个 socks5 带账密；`rotation_url` 字段在 |
| 轮换后重建指纹 | `realign_after_rotation(proxy_id, ids)` | ✅ 走 `bulk-edit {new_device:true}`，下次启动按新出口生成 |
| WireGuard 隧道 | `import_vpn/export_vpn/list_vpns` | ✅ 列表可用（单 peer 校验在 `vpn/storage.rs:421`） |
| 分组/标签/状态/模板 | `list_groups/create_group/list_tags/list_statuses` | ✅ 1 个分组、空标签 |
| cookie / localStorage 导入导出 | `export_storage_state/import_storage_state/import_cookies` | ✅ 导出 117 cookies / 14 origins；导入 1 cookie 生效 |
| 浏览器版本与下载 | `browser_versions/browser_downloaded/download_browser` | ✅ wayfern 156/156/155 |
| 开关同步 | `set_cloud_sync(id, "Regular")` | ✅ **免费也能开**（源码里那个 402 注释是过时的） |

### 需要付费（`browserAutomation`）的部分 ⛔

`run_profile` / `kill_profile` / `open_url` / `batch_run` / `batch_stop` /
`agent/*`（perceive/resolve-locator/click/hold/type/extract/pick）——
全部在 handler 里 402（`api_server.rs:3581` 等 8 处），实测 10ms 返回空 body。

## 2. 自建同步服务器（`donut-sync`）

| 能力 | 怎么用 | 实测 |
|---|---|---|
| 一键起服务 | `docker compose -f docker-compose.sync.yml up -d`（默认不需要域名/TLS） | ✅ `/health`、`/readyz s3:true` |
| 客户端接线 | `sync_server_url` + `sync_source=self_hosted` + 共享 `SYNC_TOKEN` | ✅ 登录态也生效（非 team seat 即可） |
| 上传 / 下载 / 删除 | App 自身同步 | ✅ `uploaded=614`、`downloaded=1`（sha256 一致）、`Remote profile deleted` |
| 还原点 | 服务端自动建快照 | ✅ `Snapshot created kind=auto files=4` |
| 服务端静态加密 | `SYNC_AT_REST_KEY` + `migrate-at-rest` / `verify-at-rest` | ✅ `complete=true plaintext=0 sealed[k1]=11` |
| profile 清单 + 新设备恢复 | `donutkit.Inventory` | ✅ 空白设备 `restore` 后 App `downloaded=4`，逐字节一致 |

## 3. Wayfern 的 CDP

| 能力 | 方法 | 实测 |
|---|---|---|
| 发现 | `cdp.version / targets / pages` | ✅ |
| 导航 | `session.navigate(url)` | ✅ |
| 读 DOM（**不需要 JS**） | `session.html()` / `text()` | ✅ 1.9 KB HTML、纯文本正文 |
| 截图 | `session.screenshot(path)` | ✅ 46 KB PNG |
| cookie | `session.cookies()`（`Network.getAllCookies`） | ✅ |
| 原始输入 | `mouse_move / click / insert_text / key` | ✅ |
| 能力探测 | `session.capabilities()` | ✅ 返回 `{方法: "OK" 或引擎原话}` |
| **脚本执行** | `session.evaluate(expr)` | ⛔ 免费 Wayfern 拒绝；普通 Chromium 正常（2） |
| **读设备指纹** | `Wayfern.getFingerprint` / `getIdentity` | ⛔ 拒绝 / 只给 id；付费才有设备字段 |

## 4. 四个必须知道的边界（都是实测）

1. **`run` 402 ⇒ 拿不到 CDP 端口**，除非 GUI 手点启动（GUI 路径不查套餐）。免费账号即使
   手点启动，`Runtime.evaluate` 仍被引擎拒绝，所以 Playwright 的 `evaluate/fill/screenshot`
   会以 "Execution context was destroyed" 或超时的形式失败。
2. **出口 IP 只能用浏览器栈测**：`context.request` 走 Node 网络栈（实测读到本机 HK IPv6），
   `page.goto` + `DOM.getOuterHTML` 才是真出口（实测 BR/GRU）。
3. **`GET /profiles/{id}/fingerprint` 对 identity 型 profile 返回 `null`**（免费计划下引擎不给
   设备字段），这不是 bug。
4. **自建 sync 不搬"profile 清单"**：客户端只按本地列表同步，所以新设备要先有同 UUID 的
   `metadata.json` —— 已由 `Inventory.restore` 补上（§2 最后一行）。

## 5. 架构与数据流

```
                     ┌──────────────────────────────┐
  donutkit.DonutClient│ 127.0.0.1:10108  (axum)     │──► ProfileManager / PROXY_MANAGER
                     └──────────────────────────────┘        │
                                                             ├─► donut-proxy  worker (SOCKS5, 127.0.0.1:R)
  donutkit.cdp  ────► ws://127.0.0.1:<debug port> ──► Wayfern 内核 ◄──┴─(浏览器只用本地 SOCKS5)
                                                             │
  donutkit.SyncServer ──► donut-sync:12342 ──► S3(rclone:9000) ──► 本地卷 donut-sync_s3-data
        └─ Inventory(_inventory/profiles.json)  ← 清单；restore → 新设备 data root
```

## 6. SDK 一览（`donutkit/`）

```python
from donutkit import DonutClient, SyncServer, Inventory, cdp

api = DonutClient()                       # token 取 DONUT_API_TOKEN
p   = api.create_profile("Store DE", proxy_id=px["id"])   # 建号即对齐出口 tz/lang
api.bulk_edit([p["id"]], {"tags_add": ["de"]})
api.realign_after_rotation(px["id"], [p["id"]])           # 换 IP 后重建设备

sync = SyncServer.from_env()              # 读 kit 的 .env
inv  = Inventory(sync); inv.publish(); inv.verify()
inv.restore(root="/tmp/device-c", settings_from="~/Library/Application Support/DonutBrowser")

with cdp.session(port) as s:              # 免费计划：DOM/截图/输入可用
    s.navigate("https://example.com"); print(s.text()[:200])
```

CLI（`python3 -m donutkit ...`）：

```
api   ping|list|get|create|delete|fingerprint|run|kill|proxies|add-proxy|rotate|vpns|sync-mode
sync  health|list|objects|publish|verify|prune|restore|get|delete-prefix
cdp   --port N info|html|text|shot|caps|cookies|eval
```

以上命令全部由 `donutkit` 一个包提供，无第三方依赖（22 项离线断言与真机命令都复跑通过）。

## 7. 验证方式汇总

| 层 | 证据 |
|---|---|
| API 契约 | 运行中 App 的 `/openapi.json` 与 `DONUT_API_SPEC.md` **86/86 逐条一致**（字段名 7 个结构体逐字段相符） |
| 客户端行为 | 22 项 mock 断言（请求体、响应解包、402/429/400+code、CDP 解析）全 PASS |
| 同步 | 真机上传/下载/删除/还原点/at-rest/多设备，sha256 一致 |
| CDP | 真浏览器：HTML 1989B、PNG 46330B、`evaluate` 返回 2、capabilities 矩阵 |
| 限制 | 免费账号的 402、`Runtime.evaluate` 拒绝、出口测法差异，都是真机复现的 |
