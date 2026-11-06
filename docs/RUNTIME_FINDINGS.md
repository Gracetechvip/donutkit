# 真机实测记录：本地 API + Wayfern CDP 的能力边界

全部数据来自 2026-11-06 在 macOS 上对**运行中的** `Donut.app`（Wayfern `156.0.8078.80`）与
`127.0.0.1:10108` 的实测。账户当时是 `plan: free`（`entitlements.browserAutomation = false`）。

## 1. HTTP API 层

| 操作 | 结果 | 证据 |
|---|---|---|
| `GET /openapi.json` | 200 | 与 `DONUT_API_SPEC.md` 的 86 个 operation **逐条一致** |
| 无 token 访问 `/v1/profiles` | **401** | `auth_middleware` 生效 |
| `GET /v1/profiles` / `proxies` / `groups` / `tags` / `statuses` / `browsers` | 200，返回真数据 | 3 profile、4 个 socks5 代理（带账密）、1 分组、wayfern 156/156/155 |
| `POST /v1/profiles`（无代理、宿主 OS） | **200**，3.2s | 日志：`Headless browser started purpose=generation` → `Fingerprint generated ... identity=true geolocation=applied` |
| `POST /v1/profiles/bulk-edit` | 200 `changed=1` | `ProfilePatch` 的 `tags_add` 生效 |
| `PUT /v1/profiles/{id}` | 200 | 改名成功 |
| `DELETE /v1/profiles/{id}` | 200，之后 `GET` 404 | 日志：`Profile deleted ... mode=erased` |
| `GET /v1/profiles/{id}/storage-state` | 200 | 真返回 **117 cookies / 14 origins** |
| `GET /v1/profiles/{id}/fingerprint` | **200 但 `fingerprint: null`** | 日志显示它起了 headless 引擎（`purpose=fingerprint_view, elapsed_ms=4347`），该 profile 是 identity 型 + 免费计划 → 没有可展示设备 |
| `POST /v1/profiles/{id}/run` | **402**，10ms，空 body | 与 `api_server.rs:3581` 的 `PAYMENT_REQUIRED, String::new()` 完全对应 |

结论：**CRUD 与数据读取在免费计划下完全可用；只有"启动/驱动浏览器"那条线被 402 挡住。**

## 2. 引擎/CDP 层（关键发现）

连上真机正在跑的 profile（`cdp_port=60991`，proxy worker 在 `60988`）后逐个方法试探：

| CDP 方法 | 结果 |
|---|---|
| `Target.getTargets` | OK |
| `DOM.getDocument` / `DOM.getOuterHTML` | **OK** |
| `Page.navigate` / `Page.getNavigationHistory` | OK |
| `Page.captureScreenshot` | OK |
| `Network.enable` / `Network.getAllCookies` / `Storage.getCookies` | OK |
| `Input.insertText` / `Input.dispatchMouseEvent` | OK |
| `Emulation.setUserAgentOverride` | OK |
| **`Runtime.evaluate`** | **DENY — `Browser automation requires a paid Donut Browser plan.`** |
| **`Wayfern.getFingerprint`** | **DENY — `Custom fingerprints require a Donut Browser plan that includes them.`** |
| `Wayfern.getIdentity` | OK，但 `identity` 是空对象 `{}`，只给 `identityId` |

两个闸门是**独立**的：一个管"自动化"（脚本执行），一个管"指纹编辑"（读设备）。

由此产生的连锁反应（都是同一个根因）：

- `page.evaluate(...)` → `Execution context was destroyed`
- `locator.fill()` / `locator.inputValue()` / `page.screenshot()` → 30s 超时
- `wayfern` 的 `wfp.move` / `wfp.scroll` / `wfp.typeText` → **仍然可用**（走 Input 域），但**没法校验输入值**（读 value 要 evaluate）

## 3. 出口 IP：必须用浏览器栈测

同一个 profile、同一时刻，两种测法给出完全不同的答案：

| 测法 | 结果 | 为什么 |
|---|---|---|
| `context.request.get("https://www.cloudflare.com/cdn-cgi/trace")` | 本机 IPv6（HK） | `connectOverCDP` 下 Playwright 的 APIRequestContext 走 **Node** 网络栈，**绕过浏览器代理** |
| `page.goto(trace)` + `DOM.getOuterHTML` 读正文 | **`<exit-ip>` / BR / GRU** | 走浏览器自己的网络栈 → profile 的 SOCKS5 代理 |

`wayfern_demo.mjs` 因此改成后者。任何"验证代理是否生效"的脚本都别用 `page.request` / `context.request`。

## 4. 指纹位置对齐：真机证据

三个 profile 的 `metadata.json` 全是 identity 型（`identity_id` 有值、`fingerprint: null`），
`location` 里存的就是**出口**的时区/语言/坐标：

```
profile-A  → America/Sao_Paulo  pt-BR  (-23.54, -46.63)   出口 `<exit-ip>` (BR/GRU)
profile-B  → America/Los_Angeles en-US (37.33, -121.89)
profile-C  → America/Los_Angeles en-US (34.05, -118.24)
```

实测 `Wayfern.getIdentity` 在免费计划下拿不到设备字段，所以"页面侧读到 timezone 是否等于
America/Sao_Paulo"这一步需要 Pro（有了 `Runtime.evaluate` 才能读 `Intl`）。间接旁证：该 profile
里某站点的界面语言是 **葡萄牙语**（`Caixa de entrada`），与 `pt-BR` 一致。

## 5. 付费后能多做什么

| 能力 | 免费 | Pro |
|---|---|---|
| REST 建/改/删/读 profile、代理、VPN、cookie 导入导出 | ✅ | ✅ |
| `POST /v1/profiles/{id}/run` + CDP 端口 | ❌ 402 | ✅ |
| CDP `Runtime.evaluate`（=> Playwright `evaluate/fill/screenshot`、wayfern 校验） | ❌ | ✅ |
| `Wayfern.getFingerprint` / `getIdentity` 带完整设备 | ❌ | ✅ |
| 拟人化 `move/scroll/typeText`（Input 域） | ✅（无法校验结果） | ✅ |
| 远端机队 / cookie-bot / 远端 MCP | ❌ | ✅ |

---

# 6. 自建 Sync Server × 真机 App：对接实测（2026-11-06）

目标：把 `docker-compose.sync.yml` 起的自建 `donut-sync` 与这台机器上的 `Donut.app`
真正接起来（登出/共享 token 语义），验证上传、下载、删除、加密四条路径。

## 6.1 拓扑与接线

| 项 | 实际值 |
|---|---|
| 同步服务 | `docker compose -f docker-compose.sync.yml up -d`（默认不带 caddy），`127.0.0.1:12342` |
| 对象存储 | 同 compose 里的 rclone S3，`127.0.0.1:9000`（`S3_PUBLIC_ENDPOINT` 必须与设备可达地址一致） |
| 客户端设置 | `sync_server_url = http://127.0.0.1:12342`、`sync_source = self_hosted`、`SYNC_TOKEN` 封在 `settings/sync_token.dat`（`DBSYN`） |
| 账户状态 | 仍处于登录态（`plan: free`）。源码允许登录态选用共享 token 服务器，条件是非 team seat 且 token 存在 —— `sync/account_server.rs:121-126`、`resolve()` |

App 日志的落地证据（此前每次都失败，接线后第一次成功）：

```
[11:13:15][sync::subscription] Sync subscription started     ← 连上了自建服务器的 SSE
[11:13:15][sync]              Sync scheduler started
```

## 6.2 四条路径的结果

| 路径 | 结果 |
|---|---|
| **首同步（元数据）** | `Profile synced uploaded=0 ... bytes_up=0`（新 profile 还没有浏览器数据） |
| **上传（有数据）** | `uploaded=4 bytes_up=20756`；对象落在 `profiles/<id>/{metadata.json,manifest.json,files/...}` |
| **下载** | 删掉本地 `Local Storage/leveldb/000003.log` → 重启 → `downloaded=1 bytes_down=219`，sha256 与删除前**逐字节一致** |
| **删除** | `mode=trashed sync_delete=queued` → `Profile deleted from cloud objects=6` → `Remote profile deleted`；服务器上该 profile 目录消失 |
| **还原点** | 服务器侧自动建快照：`Snapshot created kind=auto files=4 bytes=23147`，键前缀 `snapshots/profiles/<id>/<UTC stamp>/` |
| **代理/分组** | 桶里出现 `proxies/` 前缀，说明绑定的代理配置随 profile 一起同步 |

另两个 profile（profile-B / profile-C）本来就是 `sync_mode: Regular`（此前指向 Donut 云、被 403 拒绝），
接线后启动即整包上传：`uploaded=614 ... bytes_up=29208234` 与 `uploaded=145 ... bytes_up=15565189`，
各自还生成了服务器侧快照。**这意味着它们真实的浏览器数据（约 44 MB）现在躺在本机 docker 卷
`donut-sync_s3-data` 里**；不想同步就对单个 profile 调 `POST /v1/profiles/{id}/cloud-sync {"mode":"Disabled"}`
（会同时删远端副本）。

## 6.3 at-rest 加密：能用，但别指望它"立刻"生效

`verify-at-rest` 在 44 MB 上传完之后的实测输出：

```
Verify done complete=false objects=1543 stored_bytes=90017101 \
  plaintext=1530 plaintext_bytes=89972052 \
  sealed[k1]=13 sealed[k1]_bytes=45049 unknown_key=0 invalid=0 forged_marker=0 internal=8
```

即：**1530 个对象仍是明文**，只有 13 个被封（`DSAR` 头 + key id）。

原因在源码里，不是配置错：

- `Donut.app` 0.36.0 的同步客户端走**预签名直传**（对象直接进存储），`donut-sync` 只能在事后补封：
  `DirectUploads` 收键 → `PASS_EVERY=120s` 一轮 → 每小时一次 backstop，且首次 backstop 只回看
  `FIRST_BACKSTOP_MS = 2h`（`donut-sync/src/sealer.rs:32-37`）。
- 只有服务端返回 `transfer` 且客户端使用它（新版 App）时才是**入库即加密**。

因此大批量首传之后要跑一次迁移，`verify-at-rest` 才会 `complete=true`：

```bash
docker compose -f docker-compose.sync.yml exec -T donut-sync donut-sync migrate-at-rest
docker compose -f docker-compose.sync.yml exec -T donut-sync donut-sync verify-at-rest --sample 20
```

已加密的对象客户端是透明读的（服务端解封），对 App 无感。

## 6.4 命令速查

```bash
# 起 / 停
docker compose -f docker-compose.sync.yml up -d
docker compose -f docker-compose.sync.yml down          # 加 -v 连数据卷一起删

# 健康
curl -s http://127.0.0.1:12342/health
curl -s http://127.0.0.1:12342/readyz

# 不做 HTTP，直接数对象
docker compose -f docker-compose.sync.yml exec -T s3 sh -c \
  'echo "objects=$(find /data/donut-sync -type f | wc -l)"'

# 校验/迁移静态加密
docker compose -f docker-compose.sync.yml exec -T donut-sync donut-sync verify-at-rest
docker compose -f docker-compose.sync.yml exec -T donut-sync donut-sync migrate-at-rest

# 让某个 profile 停止同步（同时清远端）
curl -X POST http://127.0.0.1:10108/v1/profiles/<id>/cloud-sync \
  -H "Authorization: Bearer $DONUT_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"mode":"Disabled"}'
```

---

# 7. 多设备验证：A 机上传 → B 机收下（2026-11-06）

## 7.1 怎么模拟第二台设备

App 支持把全部状态挪到一个独立根目录（`app_dirs.rs:73-95`：`DONUTBROWSER_DATA_ROOT=<root>`
→ `<root>/{data,cache,logs}`），所以第二台设备不需要第二台机器：

1. 在 A 上新建设备无关的测试 profile，导入一个探针 cookie + 一条 localStorage，开启同步 →
   `Profile synced ... uploaded=4 bytes_up=20750`，远端得到
   `profiles/<id>/{metadata.json,manifest.json,files/profile/Default/{Cookies,Local Storage/leveldb/*}}`
2. 建 B 的根目录，只放三样东西：
   - `data/settings/app_settings.json`（复制 A 的再改：`api_enabled=false`、`sync_source=self_hosted`、同一个 `sync_server_url`）
   - `data/settings/vault.key`（B 自己新生成的 32 字节）+ 用**B 的** vault key 封出来的 `sync_token.dat`（`DBSYN`）
   - `data/profiles/<同一个 UUID>/metadata.json`，**不放任何浏览器文件**
   - 不放 `cloud_auth_state.json`，于是 B 是登出态 → `resolve()` 走 `SelfHosted`
3. 因为带 `tauri-plugin-single-instance`，先退出 A，再启动 B：
   ```bash
   DONUTBROWSER_DATA_ROOT=/tmp/device-b /Applications/Donut.app/Contents/MacOS/donutbrowser
   ```

## 7.2 结果（B 的日志原文）

```
[sync::subscription] Sync subscription started
[sync::scheduler]    Initial sync queued profiles=1
[sync::engine]       Proxy downloaded proxy=<proxy-id>  (共 4 个代理)
[sync::manifest]     Local manifest empty, recovering from remote files=4
[sync::engine]       Profile synced profile=<profile-id> uploaded=0 downloaded=4 \
                     deleted_local=0 deleted_remote=0 bytes_up=0 bytes_down=20750
```

校验：

```
profile/Default/Cookies                        A=B  sha256 51105fb13ed36778…
profile/Default/Local Storage/leveldb/000003.log    A=B  ecf8a82f27d3131b…
profile/Default/Local Storage/leveldb/MANIFEST-…    A=B  f9d31b278e215eb0…
B 的 Cookies 里存在探针值 from-device-A-42
```

**结论：数据面完全对等**——文件逐字节一致，import 的 cookie 真的到了 B；连 profile 绑定的代理配置也一起下发。

## 7.3 但"档案清单"不会同步（产品边界，不是配置问题）

`sync/client.rs` 没有任何"列出远端 profile"的方法，调度器只按**本地** profile 列表逐个
`sync_profile`。所以自建 sync 搬运的是**单个 profile 的数据**，不是"这台账号有哪些 profile"：

- 云端/团队模式下，清单来自 Donut 账号服务，所以新设备登录后能看到全部 profile；
- 纯自建 + 共享 token 时没有这个服务，**B 必须先有同 UUID 的 `metadata.json`**（手工拷贝、
  或你自己的分发流程），数据才会跟着下来。

要真正做到"新设备零手工恢复"，得自己在服务端加一层清单，或继续用账号侧 inventory。

## 7.4 关闭同步的清理语义（实测）

对两个真实 profile 关闭同步后，服务端留下：

| 残留 | 数量 | 说明 |
|---|---|---|
| `tombstones/profiles/<id>.json` | 1/个 | 防复活标记，**应当保留** |
| `proxies/*.json` | 4 | 代理配置，**可复用** |
| `snapshots/**`（自动还原点） | 775 个 / 45 MB | 关闭同步**不会删**，需要手动清 |
| `profiles/**/.rclone_temp_put_*` | 31 个 | rclone 原子写的临时对象；服务端 `ListObjectsV2` 看不见它们，`delete-prefix` 也就删不到 |

实测清理顺序与结果：

```bash
TOK=$(grep '^SYNC_TOKEN=' .env | cut -d= -f2)
# 1) 删自动还原点（这条走服务端 API，能真正删掉）
curl -X POST http://127.0.0.1:12342/v1/objects/delete-prefix \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"prefix":"snapshots/","tombstoneKey":""}'      # → {"deletedCount":775}

# 2) 清 rclone 临时对象（只能在卷上删）
docker compose -f docker-compose.sync.yml exec -T s3 \
  sh -c 'find /data/donut-sync -name ".rclone_temp_put_*" -delete'

# 3) 把剩下的小对象也封起来，然后校验
docker compose -f docker-compose.sync.yml exec -T donut-sync donut-sync migrate-at-rest
docker compose -f docker-compose.sync.yml exec -T donut-sync donut-sync verify-at-rest
```

最终状态：`objects=9 sealed[k1]=9 plaintext=0 complete=true`，卷内 516 KB（4 个代理 + 4 个
tombstone + 1 个桶清单 + 内部状态），**profile 数据与 45 MB 快照均已清空**。

---

# 8. 补上「profile 清单」：`donutkit.Inventory`（2026-11-06 实测）

第 7 节说明了自建 sync 的空白：客户端只按本地 profile 列表同步，没有远端清单。
`donutkit.Inventory` 补的正是这一层——**不动 App、不改服务端**，只在同一个桶里维护一个
`_inventory/profiles.json`，并提供一条命令把清单落到空白设备上。

## 8.1 它能做什么

| 命令 | 作用 | 用到的接口 |
|---|---|---|
| `publish` | 扫 `profiles/` 前缀，读每个 `metadata.json` 取名字/时间戳，写索引对象 | `list` / `stat` / `presign-download` / `presign-upload` |
| `list` | 打印索引（`--json` 出原始 JSON） | `presign-download` |
| `restore --root R [--settings-from S]` | 把索引里的 profile 落成 `R/data/profiles/<id>/metadata.json`，并可选铺好 `vault.key` / `sync_token.dat` / 最小 `app_settings.json` | `presign-download` |
| `prune` | 移除远端已不存在的条目 | `list` |
| `verify` | 索引 vs 远端对象数的一致性检查（退出码 2 表示不一致） | `list` |

索引结构（`_inventory/profiles.json`）：

```json
{"version":1,"generated_at":"...","server":"http://127.0.0.1:12342",
 "profiles":[{"id":"…","name":"…","files":4,"bytes":20732,
              "metadata_key":"profiles/…/metadata.json",
              "manifest_key":"profiles/…/manifest.json",
              "updated_at":1793936291,"last_sync":1793936291,
              "browser":"wayfern","version":"156.0.8078.81","host_os":"macos"}]}
```

## 8.2 端到端实测（空白设备 → 一条命令 → 数据到位）

```
$ python3 -m donutkit sync publish
已写入 _inventory/profiles.json（1 个 profile）
  <profile-id>  inventory-probe  files=4  bytes=20.2KB
$ python3 -m donutkit sync verify
verify: OK

$ python3 -m donutkit sync restore --root /tmp/device-c \
      --settings-from "$HOME/Library/Application Support/DonutBrowser"
settings 已铺到 /tmp/device-c/data/settings：vault.key, sync_token.dat, app_settings.json
  wrote  <profile-id> inventory-probe → …/metadata.json（1567B）
restore: 写入 1 个，跳过 0 个。

# 空白设备上唯一的文件就是上面这些；之后启动 App：
$ DONUTBROWSER_DATA_ROOT=/tmp/device-c /Applications/Donut.app/Contents/MacOS/donutbrowser
[sync::scheduler] Initial sync queued profiles=1
[sync::engine]    Proxy downloaded proxy=…（4 个）
[sync::manifest]  Local manifest empty, recovering from remote files=4
[sync::engine]    Profile synced … uploaded=0 downloaded=4 bytes_down=20732
```

三个数据文件 sha256 与主设备**逐字节一致**，`inv_probe` cookie 出现在新设备的 Cookies 里，
profile 名字读回为 `inventory-probe`。**没有手工拷贝任何 profile 目录。**

## 8.3 边界与注意事项

- **只搬清单、不搬文件**：`restore` 写完 `metadata.json` 就结束，真正的数据由 App 自己的
  同步引擎下载（这样版本演进、加密、租约、冲突处理都还是官方实现）。
- **一次只能跑一个 App 实例**：`tauri-plugin-single-instance` 会抢占，恢复前先退出主设备。
- **`--settings-from` 复制的是 `vault.key` + `sync_token.dat`**（stdlib 实现，无需 argon2）。
  想让新设备用**自己**的 vault key，就用 `mint_token.py` 那套封一个（需要 argon2-cffi +
  cryptography，kit 里已有 venv 方案），或者干脆在 App 的 Integrations 页重新生成 token。
- **新设备默认 `api_enabled=false`**，避免与主设备抢 10108；要远程控制它再打开。
- 索引本身也会被 `migrate-at-rest` 一起加密封存（实测 `sealed[k1]=11`，无明文残留）。
- `restore --dry-run` 可以先看会写什么；`--only <id>` 只恢复指定 profile。

## 8.4 收尾状态（实测）

```
_inventory   files=1     ← 空索引（0 个 profile），机制留档
profiles     files=0
proxies      files=4
tombstones   files=5     ← 防复活标记
snapshots    files=0
verify-at-rest: complete=true plaintext=0 sealed[k1]=11   （卷内 540 KB）
```
