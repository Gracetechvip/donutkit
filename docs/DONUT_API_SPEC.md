# Donut Browser 本地 REST API 规范

> 本文档由 `scripts` 级静态解析生成：所有 Method / Path / 参数 / 字段名均来自
> `src-tauri/src/api_server.rs` 的 `#[utoipa::path]` 属性与 `struct` 定义，
> 每一条都带源码行号。没有推测的端点或参数名。

> **运行中验证（2026-11-06）**：在真机 `Donut.app` + `127.0.0.1:10108` 上抓了一次它自己的
> `GET /openapi.json` 做逐条比对 —— **86 个 operation 与本文完全一致（双向零差异）**，
> 且 `CreateProfileRequest`(15/15)、`UpdateProfileRequest`(15/15)、`CreateProxyRequest`(3/3)、
> `ImportVpnRequest`(3/3)、`RunProfileResponse`(4/4) 的 JSON 字段名逐字段相符。

- 解析结果：**86 个 handler**，**58 条 path**
- 交叉验证：仓库自带的 `sdk/api-paths.json`（官方 SDK 的 operation 清单）声明了 85 个
  operation —— 本表 **85/85 全部存在**，且 `operation_id` 与 handler 函数名、Method、Path
  逐条一致；本表多出的 1 条是 `POST /v1/profiles/{id}/agent/hold`（`agent_hold_api`，
  api_server.rs:5670），SDK 那份清单还没同步它。**没有任何一条是推测出来的。**
- 源码版本：`donutbrowser` @ `main`（AGPL-3.0）
- 认证：所有 `/v1/*` 需要 `Authorization: Bearer <api_token>`（`auth_middleware`, api_server.rs:1301）

## 0. 通用约定

| 项 | 值 | 证据 |
|---|---|---|
| 监听地址 | `127.0.0.1:<api_port>`，默认 10108；端口被吞则退到随机 `10000+rand` | `api_server.rs:1511`、`api_server.rs:1077-1100` |
| 启动条件 | 设置项 `api_enabled = true`（应用启动时自动拉起） | `lib.rs:3480` |
| 认证 | `Authorization: Bearer <token>`，常量时间比较 | `api_server.rs:1301-1355` |
| 条款闸门 | Wayfern 条款未接受 → 所有 `/v1/*` 403 | `api_server.rs:1128-1136` |
| 限流 | 仅“自动化请求”计费，1 小时窗口，超限 429 + `Retry-After` | `api_server.rs:1379-1419`、`automation_rate_limiter.rs:8` |
| 付费闸门 | 自动化 handler 内 `can_use_browser_automation()` 为假 → 402 | `api_server.rs:3581` 等 8 处 |
| OpenAPI 自描述 | `GET /openapi.json`、`GET /v1/openapi.json`（无需 token） | `api_server.rs:1121-1125` |

## 1. 路由总表

| # | Method | Path | Handler | 源码行 | Body |
|---|---|---|---|---|---|
| 1 | `POST` | `/v1/profiles/{id}/agent/click` | `agent_click_api` | 5635 | `AgentClickRequest` |
| 2 | `POST` | `/v1/profiles/{id}/agent/extract` | `agent_extract_api` | 5737 | `ExtractionRequest` |
| 3 | `POST` | `/v1/profiles/{id}/agent/hold` | `agent_hold_api` | 5670 | `AgentHoldRequest` |
| 4 | `POST` | `/v1/profiles/{id}/agent/perceive` | `agent_perceive_api` | 5569 | `PerceptionRequest` |
| 5 | `POST` | `/v1/profiles/{id}/agent/pick` | `agent_pick_api` | 5768 | `AgentPickRequest` |
| 6 | `POST` | `/v1/profiles/{id}/agent/resolve-locator` | `agent_resolve_locator_api` | 5600 | `AgentResolveRequest` |
| 7 | `POST` | `/v1/profiles/{id}/agent/type` | `agent_type_api` | 5701 | `AgentTypeRequest` |
| 8 | `POST` | `/v1/browsers/download` | `download_browser_api` | 5355 | `DownloadBrowserRequest` |
| 9 | `GET` | `/v1/browsers/{browser}/versions` | `get_browser_versions` | 5399 | — |
| 10 | `GET` | `/v1/browsers/{browser}/versions/{version}/downloaded` | `check_browser_downloaded` | 5432 | — |
| 11 | `GET` | `/v1/cookie-bot/conflicts` | `get_cookie_bot_conflicts` | 4515 | — |
| 12 | `GET` | `/v1/cookie-bot/presets` | `list_cookie_bot_presets` | 4664 | — |
| 13 | `GET` | `/v1/cookie-bot/runs` | `list_cookie_bot_runs` | 4555 | — |
| 14 | `POST` | `/v1/cookie-bot/runs` | `start_cookie_bot_run` | 4592 | `StartCookieBotRunRequest` |
| 15 | `DELETE` | `/v1/cookie-bot/runs/{run_id}` | `cancel_cookie_bot_run` | 4632 | — |
| 16 | `GET` | `/v1/cookie-bot/schedules` | `list_cookie_bot_schedules` | 4340 | — |
| 17 | `DELETE` | `/v1/cookie-bot/schedules/{profile_id}` | `delete_cookie_bot_schedule` | 4484 | — |
| 18 | `GET` | `/v1/cookie-bot/schedules/{profile_id}` | `get_cookie_bot_schedule` | 4369 | — |
| 19 | `PUT` | `/v1/cookie-bot/schedules/{profile_id}` | `set_cookie_bot_schedule` | 4407 | `SetCookieBotScheduleRequest` |
| 20 | `GET` | `/v1/cookie-bot/usage` | `get_cookie_bot_usage` | 4690 | — |
| 21 | `POST` | `/v1/profiles/{id}/cookies/import` | `import_profile_cookies` | 5277 | `ImportCookiesRequest` |
| 22 | `GET` | `/v1/profiles/{id}/storage-state` | `export_storage_state` | 5205 | — |
| 23 | `POST` | `/v1/profiles/{id}/storage-state` | `import_storage_state` | 5244 | `ApiStorageState` |
| 24 | `GET` | `/v1/extension-groups` | `get_extension_groups` | 3403 | — |
| 25 | `POST` | `/v1/extension-groups` | `create_extension_group_api` | 3420 | `CreateExtensionGroupRequest` |
| 26 | `DELETE` | `/v1/extension-groups/{id}` | `delete_extension_group_api` | 3483 | — |
| 27 | `GET` | `/v1/extension-groups/{id}` | `get_extension_group_api` | 3440 | — |
| 28 | `PUT` | `/v1/extension-groups/{id}` | `update_extension_group_api` | 3461 | `UpdateExtensionGroupRequest` |
| 29 | `DELETE` | `/v1/extension-groups/{id}/extensions/{extension_id}` | `remove_extension_from_group_api` | 3529 | — |
| 30 | `POST` | `/v1/extension-groups/{id}/extensions/{extension_id}` | `add_extension_to_group_api` | 3506 | — |
| 31 | `GET` | `/v1/extensions` | `get_extensions` | 3255 | — |
| 32 | `POST` | `/v1/extensions` | `create_extension_api` | 3283 | `CreateExtensionRequest` |
| 33 | `DELETE` | `/v1/extensions/{id}` | `delete_extension_api` | 3382 | — |
| 34 | `GET` | `/v1/extensions/{id}` | `get_extension_api` | 3316 | — |
| 35 | `PUT` | `/v1/extensions/{id}` | `update_extension_api` | 3340 | `UpdateExtensionRequest` |
| 36 | `GET` | `/v1/groups` | `get_groups` | 2211 | — |
| 37 | `POST` | `/v1/groups` | `create_group` | 2287 | `CreateGroupRequest` |
| 38 | `DELETE` | `/v1/groups/{id}` | `delete_group` | 2362 | — |
| 39 | `GET` | `/v1/groups/{id}` | `get_group` | 2247 | — |
| 40 | `PUT` | `/v1/groups/{id}` | `update_group` | 2322 | `UpdateGroupRequest` |
| 41 | `GET` | `/v1/profiles` | `get_profiles` | 1653 | — |
| 42 | `POST` | `/v1/profiles` | `create_profile` | 1776 | `CreateProfileRequest` |
| 43 | `POST` | `/v1/profiles/batch/run` | `batch_run_profiles` | 4860 | `BatchRunRequest` |
| 44 | `POST` | `/v1/profiles/batch/stop` | `batch_stop_profiles` | 5051 | `BatchStopRequest` |
| 45 | `POST` | `/v1/profiles/bulk-edit` | `bulk_edit_profiles` | 2488 | `BulkEditRequest` |
| 46 | `POST` | `/v1/profiles/distribute-proxies` | `distribute_proxies` | 5023 | `DistributeProxiesRequest` |
| 47 | `POST` | `/v1/profiles/import` | `import_profiles_api` | 5154 | `ImportProfilesRequest` |
| 48 | `GET` | `/v1/profiles/import/detect` | `detect_import_profiles` | 5120 | — |
| 49 | `DELETE` | `/v1/profiles/{id}` | `delete_profile` | 2181 | — |
| 50 | `GET` | `/v1/profiles/{id}` | `get_profile` | 1681 | — |
| 51 | `PUT` | `/v1/profiles/{id}` | `update_profile` | 1985 | `UpdateProfileRequest` |
| 52 | `POST` | `/v1/profiles/{id}/cloud-sync` | `set_profile_cloud_sync` | 3757 | `SetCloudSyncRequest` |
| 53 | `GET` | `/v1/profiles/{id}/fingerprint` | `get_profile_fingerprint_api` | 1720 | — |
| 54 | `POST` | `/v1/profiles/{id}/kill` | `kill_profile` | 4791 | — |
| 55 | `POST` | `/v1/profiles/{id}/open-url` | `open_url_in_profile` | 4726 | `OpenUrlRequest` |
| 56 | `POST` | `/v1/profiles/{id}/run` | `run_profile` | 3552 | `RunProfileRequest` |
| 57 | `POST` | `/v1/profiles/{id}/run-remote` | `run_profile_remote` | 3679 | `RunRemoteRequest` |
| 58 | `DELETE` | `/v1/remote-sessions/{id}` | `stop_remote_session` | 3914 | — |
| 59 | `GET` | `/v1/proxies` | `get_proxies` | 2671 | — |
| 60 | `POST` | `/v1/proxies` | `create_proxy` | 2722 | `CreateProxyRequest` |
| 61 | `POST` | `/v1/proxies/import` | `import_proxies_api` | 2761 | `ImportProxiesRequest` |
| 62 | `DELETE` | `/v1/proxies/{id}` | `delete_proxy` | 2904 | — |
| 63 | `GET` | `/v1/proxies/{id}` | `get_proxy` | 2693 | — |
| 64 | `PUT` | `/v1/proxies/{id}` | `update_proxy` | 2826 | `UpdateProxyRequest` |
| 65 | `POST` | `/v1/proxies/{id}/rotate` | `rotate_proxy` | 2869 | — |
| 66 | `GET` | `/v1/remote-hours` | `get_remote_hours` | 4278 | — |
| 67 | `GET` | `/v1/remote-sessions` | `list_remote_sessions_api` | 4220 | — |
| 68 | `GET` | `/v1/remote-sessions/{id}` | `get_remote_session_api` | 4245 | — |
| 69 | `GET` | `/v1/remote-sessions/{id}/cdp` | `remote_session_cdp` | 4088 | — |
| 70 | `GET` | `/v1/statuses` | `get_statuses` | 2396 | — |
| 71 | `POST` | `/v1/statuses` | `create_status` | 2417 | `StatusRequest` |
| 72 | `DELETE` | `/v1/statuses/{id}` | `delete_status` | 2466 | — |
| 73 | `PUT` | `/v1/statuses/{id}` | `update_status` | 2439 | `StatusRequest` |
| 74 | `GET` | `/v1/tags` | `get_tags` | 2647 | — |
| 75 | `GET` | `/v1/templates` | `get_templates` | 2514 | — |
| 76 | `POST` | `/v1/templates` | `create_template` | 2530 | `TemplateRequest` |
| 77 | `DELETE` | `/v1/templates/{id}` | `delete_template` | 2582 | — |
| 78 | `PUT` | `/v1/templates/{id}` | `update_template` | 2554 | `TemplateRequest` |
| 79 | `POST` | `/v1/templates/{id}/profiles` | `create_profiles_from_template` | 2604 | `CreateFromTemplateRequest` |
| 80 | `GET` | `/v1/vpns` | `get_vpns` | 2951 | — |
| 81 | `POST` | `/v1/vpns` | `create_vpn` | 3067 | `CreateVpnRequest` |
| 82 | `POST` | `/v1/vpns/import` | `import_vpn` | 3035 | `ImportVpnRequest` |
| 83 | `DELETE` | `/v1/vpns/{id}` | `delete_vpn` | 3135 | — |
| 84 | `GET` | `/v1/vpns/{id}` | `get_vpn` | 2974 | — |
| 85 | `PUT` | `/v1/vpns/{id}` | `update_vpn` | 3100 | `UpdateVpnRequest` |
| 86 | `GET` | `/v1/vpns/{id}/export` | `export_vpn` | 3004 | — |

## 2. 按 tag 展开（含请求/响应结构）

### 2.1 `agent`

#### `POST /v1/profiles/{id}/agent/click`

`agent_click_api` — `src-tauri/src/api_server.rs:5635`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::mcp_server::AgentClickRequest`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The element was clicked; `navigated` says whether a page load followed | `crate::mcp_server::AgentClick` |
| 400 | Malformed request, no element matched, or several did (see resolve-locator) | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | The profile is not running | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

#### `POST /v1/profiles/{id}/agent/extract`

`agent_extract_api` — `src-tauri/src/api_server.rs:5737`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::wayfern_cdp::ExtractionRequest`

**`ExtractionRequest`** — `src-tauri/src/wayfern_cdp.rs:485`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `container` | `container` | `LocatorDescription` | Matches every row container; several matches are the expected case. |
| `field_map` | `field_map` | `Vec<ExtractionField>` | The columns. The browser calls this `fieldMap`; `fields` is accepted too. |
| `next_page` | `next_page` | `Option<LocatorDescription>` | The control clicked to advance a page. Absent means one page. |
| `max_pages` | `max_pages` | `Option<u64>` | Default 1, ceiling 200. |
| `max_rows` | `max_rows` | `Option<u64>` | Default 1000, ceiling 100000. |
| `max_bytes` | `max_bytes` | `Option<u64>` | Default 262144, ceiling 8388608. |
| `max_nodes` | `max_nodes` | `Option<u64>` | Node cap for each snapshot. Default 20000, ceiling 200000. |
| `time_budget_ms` | `time_budget_ms` | `Option<u64>` | Default 8000, ceiling 120000. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The rows read, and why reading stopped. A missing container is a result with `stopReason` no-container, not an error | `crate::wayfern_cdp::Extraction` |
| 400 | Malformed request, or the profile runs a Wayfern older than 152 (`code` WAYFERN_152_REQUIRED) | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | The profile is not running | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

**`Extraction`** — `src-tauri/src/wayfern_cdp.rs:563`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `rows` | `rows` | `Vec<ExtractionRow>` |  |
| `row_count` | `row_count` | `u64` |  |
| `page_count` | `page_count` | `u64` |  |
| `byte_size` | `byte_size` | `u64` | Byte length of the compact JSON serialization of `rows`. |
| `truncated` | `truncated` | `bool` |  |
| `stop_reason` | `stop_reason` | `String` | "complete", "no-container", "no-next", "page-cap", "row-cap", "byte-cap" or "time-budget". |
| `engine` | `engine` | `Engine` |  |

#### `POST /v1/profiles/{id}/agent/hold`

`agent_hold_api` — `src-tauri/src/api_server.rs:5670`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::mcp_server::AgentHoldRequest`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The element was pressed and held, then let go: for a press-and-hold check. The pointer moves a little while the button is down; `held_ms` is how long the button was down | `crate::mcp_server::AgentHold` |
| 400 | Malformed request, duration_ms out of 100 to 30000, no element matched, or several did | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | The profile is not running | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

#### `POST /v1/profiles/{id}/agent/perceive`

`agent_perceive_api` — `src-tauri/src/api_server.rs:5569`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::wayfern_cdp::PerceptionRequest`

**`PerceptionRequest`** — `src-tauri/src/wayfern_cdp.rs:322`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `max_bytes` | `max_bytes` | `Option<u64>` | Total byte cap across cursor pages. Default 1 MiB, ceiling 4 MiB. |
| `budget_ms` | `budget_ms` | `Option<u64>` | Capture budget in milliseconds. Default 5000, clamped to [100, 60000]. |
| `max_nodes` | `max_nodes` | `Option<u64>` | Per-frame node ceiling, counted in document order. Default 100000; 0 for no limit. With `viewport_only` it bounds the nodes returned instead. |
| `include_text` | `include_text` | `Option<bool>` | Include readable text. Default true. |
| `viewport_only` | `viewport_only` | `Option<bool>` | Drop nodes outside the viewport. Default false. |
| `text_order` | `text_order` | `Option<String>` | "reading" (default) or "visual". |
| `cursor` | `cursor` | `Option<String>` | Continue an earlier capture from the cursor it returned. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The page as the agent sees it: nodes, frames, text, stats, and a cursor when truncated. Node keys are the browser's own camelCase; `engine` says whether Wayfern 152 or the DOM fallback answered | `crate::wayfern_cdp::PerceptionPage` |
| 400 | Malformed request, or a cursor on a profile whose browser cannot paginate | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | The profile is not running | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

**`PerceptionPage`** — `src-tauri/src/wayfern_cdp.rs:453`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `snapshot_id` | `snapshot_id` | `String` |  |
| `nodes` | `nodes` | `Vec<PerceptionNode>` |  |
| `frames` | `frames` | `Vec<PerceptionFrame>` |  |
| `text` | `text` | `String` | Readable text for exactly the nodes returned. |
| `truncated` | `truncated` | `bool` |  |
| `stats` | `stats` | `PerceptionStats` |  |
| `cursor` | `cursor` | `Option<String>` |  |
| `engine` | `engine` | `Engine` |  |

#### `POST /v1/profiles/{id}/agent/pick`

`agent_pick_api` — `src-tauri/src/api_server.rs:5768`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::mcp_server::AgentPickRequest`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The user clicked an element; `locator` is the smallest description that resolves to it | `crate::wayfern_cdp::PickedElement` |
| 400 | Malformed request, or the profile runs a Wayfern older than 152 (`code` WAYFERN_152_REQUIRED) | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 408 | Nothing was picked within timeout_ms; the picker has been disarmed | — |
| 409 | The profile is not running, or the picker was cancelled (Escape, or a navigation) | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

**`PickedElement`** — `src-tauri/src/wayfern_cdp.rs:582`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `backend_node_id` | `backend_node_id` | `i64` |  |
| `locator` | `locator` | `LocatorDescription` | The smallest description that still resolves to this node. |
| `match_count` | `match_count` | `u64` | How many nodes `locator` matches; more than 1 when the page genuinely holds indistinguishable elements. |
| `node` | `node` | `LocatorCandidate` |  |
| `engine` | `engine` | `Engine` |  |

#### `POST /v1/profiles/{id}/agent/resolve-locator`

`agent_resolve_locator_api` — `src-tauri/src/api_server.rs:5600`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::mcp_server::AgentResolveRequest`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Exactly one element matched; `match` describes it | `crate::wayfern_cdp::LocatorResolution` |
| 400 | Malformed locator, no element matched (`code` LOCATOR_NO_MATCH), or several did (`code` LOCATOR_AMBIGUOUS, with `candidates`) | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | The profile is not running | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

**`LocatorResolution`** — `src-tauri/src/wayfern_cdp.rs:291`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `backend_node_id` | `backend_node_id` | `Option<i64>` |  |
| `match_count` | `match_count` | `u64` | Always 1: present so a caller can assert it rather than infer it. |
| `matched` | `matched` | `LocatorCandidate` |  |
| `locator` | `locator` | `LocatorDescription` | The canonical form of the locator that resolved. |
| `engine` | `engine` | `Engine` |  |

#### `POST /v1/profiles/{id}/agent/type`

`agent_type_api` — `src-tauri/src/api_server.rs:5701`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`crate::mcp_server::AgentTypeRequest`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The text was typed, and the field read back holds it (`verified`) | `crate::mcp_server::AgentTyping` |
| 400 | Malformed request, no element matched, several did, or the text would take longer than the typing budget (`code` TYPING_TOO_LONG) | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | The profile is not running, or the field did not take the focus or the text (`code` TYPE_NOT_APPLIED, `reason` not_focused or value) | — |
| 429 | Automation request rate limit exceeded | — |
| 502 | The browser did not answer as documented | — |
| 500 | Internal server error | — |

### 2.2 `browsers`

#### `POST /v1/browsers/download`

`download_browser_api` — `src-tauri/src/api_server.rs:5355`

请求体：`DownloadBrowserRequest`

**`DownloadBrowserRequest`** — `src-tauri/src/api_server.rs:427`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `browser` | `browser` | `String` |  |
| `version` | `version` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Browser downloaded (or already present) | `DownloadBrowserResponse` |
| 400 | Invalid browser or version not available for download | — |
| 401 | Unauthorized | — |
| 409 | This browser version is already being downloaded | — |
| 500 | Internal server error (e.g. network failure) | — |

**`DownloadBrowserResponse`** — `src-tauri/src/api_server.rs:433`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `browser` | `browser` | `String` |  |
| `version` | `version` | `String` |  |
| `status` | `status` | `String` |  |

#### `GET /v1/browsers/{browser}/versions`

`get_browser_versions` — `src-tauri/src/api_server.rs:5399`

路径/查询参数：

- `browser` (Path, `String`) — Browser name

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of available browser versions | `Vec<String>` |
| 400 | Unsupported browser | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `GET /v1/browsers/{browser}/versions/{version}/downloaded`

`check_browser_downloaded` — `src-tauri/src/api_server.rs:5432`

路径/查询参数：

- `browser` (Path, `String`) — Browser name
- `version` (Path, `String`) — Browser version

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Browser download status | `bool` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

### 2.3 `cookie-bot`

#### `GET /v1/cookie-bot/conflicts`

`get_cookie_bot_conflicts` — `src-tauri/src/api_server.rs:4515`

路径/查询参数：

- `profile_id` (Query, `String`) — Profile ID
- `run_at_minute` (Query, `Option<u16>`) — Proposed minute past local midnight
- `timezone` (Query, `Option<String>`) — Proposed IANA zone
- `days_mask` (Query, `Option<u8>`) — Proposed weekday bitmask, bit 0 = Monday

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Teammates enrolling the same profile | `crate::cookie_bot::CookieBotConflictCheck` |
| 400 | profile_id missing | — |
| 401 | Unauthorized | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `GET /v1/cookie-bot/presets`

`list_cookie_bot_presets` — `src-tauri/src/api_server.rs:4664`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Selectable presets | `crate::cookie_bot::CookieBotPresetList` |
| 401 | Unauthorized | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `GET /v1/cookie-bot/runs`

`list_cookie_bot_runs` — `src-tauri/src/api_server.rs:4555`

路径/查询参数：

- `profile_id` (Query, `Option<String>`) — Restrict to one profile
- `scope` (Query, `Option<String>`) — `mine` (default) or `team`
- `limit` (Query, `Option<u32>`) — Page size, 1..100 (default 30)
- `before` (Query, `Option<String>`) — Keyset cursor from a previous page's next_before

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | One page of runs, newest first | `crate::cookie_bot::CookieBotRunPage` |
| 400 | limit out of range or malformed cursor | — |
| 401 | Unauthorized | — |
| 403 | Not signed in, or scope=team from a non-member | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `POST /v1/cookie-bot/runs`

`start_cookie_bot_run` — `src-tauri/src/api_server.rs:4592`

请求体：`StartCookieBotRunRequest`

**`StartCookieBotRunRequest`** — `src-tauri/src/api_server.rs:550`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_id` | `profile_id` | `String` | Profile to warm. It must already have a schedule: the preset and the site list live there, so a run never carries a behaviour of its own. |
| `max_minutes` | `max_minutes` | `Option<u32>` | Overrides the schedule's own cap for this run only. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 202 | Run accepted; it keeps executing for minutes after this response | `crate::cookie_bot::CookieBotRunStarted` |
| 400 | A profile the bot cannot run | — |
| 401 | Unauthorized | — |
| 402 | Plan does not include the cookie bot, or the pooled hours are spent | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 404 | Profile not found, or not enrolled | — |
| 409 | A run or remote session already holds this profile | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | No host of that operating system has a free slot | — |
| 500 | Internal server error | — |

#### `DELETE /v1/cookie-bot/runs/{run_id}`

`cancel_cookie_bot_run` — `src-tauri/src/api_server.rs:4632`

路径/查询参数：

- `run_id` (Path, `String`) — Run ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The run, cancelled (or unchanged if it had already finished) | `crate::cookie_bot::CookieBotRun` |
| 401 | Unauthorized | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 404 | No such run for this account | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | The fleet could not be reached; the run is still live | — |
| 500 | Internal server error | — |

#### `GET /v1/cookie-bot/schedules`

`list_cookie_bot_schedules` — `src-tauri/src/api_server.rs:4340`

路径/查询参数：

- `scope` (Query, `Option<String>`) — `mine` (default) or `team`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Enrolled profiles | `crate::cookie_bot::CookieBotScheduleList` |
| 401 | Unauthorized | — |
| 402 | Plan does not include the cookie bot | — |
| 403 | Not signed in, or scope=team from a non-member | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `DELETE /v1/cookie-bot/schedules/{profile_id}`

`delete_cookie_bot_schedule` — `src-tauri/src/api_server.rs:4484`

路径/查询参数：

- `profile_id` (Path, `String`) — Profile ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Enrolment removed, or there was none | `crate::cookie_bot::CookieBotScheduleDeleted` |
| 401 | Unauthorized | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `GET /v1/cookie-bot/schedules/{profile_id}`

`get_cookie_bot_schedule` — `src-tauri/src/api_server.rs:4369`

路径/查询参数：

- `profile_id` (Path, `String`) — Profile ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The profile's enrolment | `crate::cookie_bot::CookieBotSchedule` |
| 401 | Unauthorized | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 404 | This profile is not enrolled | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `PUT /v1/cookie-bot/schedules/{profile_id}`

`set_cookie_bot_schedule` — `src-tauri/src/api_server.rs:4407`

路径/查询参数：

- `profile_id` (Path, `String`) — Profile ID

请求体：`SetCookieBotScheduleRequest`

**`SetCookieBotScheduleRequest`** — `src-tauri/src/api_server.rs:519`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_name` | `profile_name` | `Option<String>` | Defaults to the profile's local name. |
| `platform` | `platform` | `Option<String>` | `windows`, `macos` or `linux`: the OS of the host the bot runs the profile on, `linux` for a profile that runs on every OS, else the OS that created the profile. Defaults to that OS, and must match it when supplied. |
| `enabled` | `enabled` | `bool` | Whether the nightly run is armed. A disabled schedule keeps its settings. |
| `run_at_minute` | `run_at_minute` | `u16` | Minutes past local midnight the run is anchored to (0..1439). |
| `days_mask` | `days_mask` | `u8` | Bitmask of local weekdays, bit 0 = Monday (1..127). |
| `timezone` | `timezone` | `String` | IANA zone the run time is expressed in. |
| `preset` | `preset` | `String` | Server-issued preset id from `GET /v1/cookie-bot/presets`. |
| `max_minutes` | `max_minutes` | `u32` | Upper bound on one run, in minutes. |
| `sites` | `sites` | `Vec<String>` | Absolute http(s) URLs to browse. The bot visits only these. |
| `jitter_seconds` | `jitter_seconds` | `Option<u32>` | Random spread around the anchor time, in seconds. |
| `acknowledge_conflict` | `acknowledge_conflict` | `bool` | Write anyway when a teammate already enrols this profile. Without it, a colliding write is refused with 409 and the teammate's details. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Enrolment saved | `crate::cookie_bot::CookieBotScheduleSaved` |
| 400 | Invalid schedule, or a profile the bot cannot run | — |
| 401 | Unauthorized | — |
| 402 | Plan does not include the cookie bot | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 404 | Profile not found | — |
| 409 | A teammate already enrols this profile; retry with acknowledge_conflict | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `GET /v1/cookie-bot/usage`

`get_cookie_bot_usage` — `src-tauri/src/api_server.rs:4690`

路径/查询参数：

- `period` (Query, `Option<String>`) — `YYYY-MM`; defaults to the current UTC month

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Per-member and per-profile spend | `crate::cookie_bot::CookieBotUsage` |
| 400 | Malformed period | — |
| 401 | Unauthorized | — |
| 403 | Not signed in, or not a member of that team | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

### 2.4 `cookies`

#### `POST /v1/profiles/{id}/cookies/import`

`import_profile_cookies` — `src-tauri/src/api_server.rs:5277`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`ImportCookiesRequest`

**`ImportCookiesRequest`** — `src-tauri/src/api_server.rs:596`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `content` | `content` | `String` | Raw cookie file content. Format is auto-detected: a JSON array (Puppeteer / EditThisCookie style) or a Netscape `cookies.txt`. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Cookies imported successfully | `ImportCookiesResponse` |
| 400 | Invalid cookie file or unsupported browser | — |
| 401 | Unauthorized | — |
| 404 | Profile not found | — |
| 409 | Browser is running, the profile is password-protected, or a remote session owns it | — |
| 500 | Internal server error | — |

**`ImportCookiesResponse`** — `src-tauri/src/api_server.rs:603`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `cookies_imported` | `cookies_imported` | `usize` |  |
| `cookies_replaced` | `cookies_replaced` | `usize` |  |
| `errors` | `errors` | `Vec<String>` |  |

#### `GET /v1/profiles/{id}/storage-state`

`export_storage_state` — `src-tauri/src/api_server.rs:5205`

路径/查询参数：

- `id` (Path, `String`) — Profile ID
- `include_cookies` (Query, `Option<bool>`) — Also export the profile's cookies; false when left out
- `indexed_db` (Query, `Option<bool>`) — Also export each origin's IndexedDB (`origins[].indexedDB`). The profile must be closed; it opens headless for a moment and no request leaves the computer. False when left out

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Playwright storageState: each origin's Local Storage, and the cookies and IndexedDB when asked for. Readable while the browser runs unless IndexedDB is asked for; writes from the last seconds may not be on disk yet | `ApiStorageState` |
| 400 | The profile is ephemeral and keeps no Local Storage on disk, the IndexedDB is over 24 MiB, or the browser could not read it | — |
| 401 | Unauthorized | — |
| 404 | Profile not found | — |
| 409 | The profile is password-protected, IndexedDB was asked for while the browser runs, or a remote session owns it | — |
| 500 | Internal server error | — |

**`ApiStorageState`** — `src-tauri/src/api_server.rs:287`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `cookies` | `cookies` | `Vec<serde_json::Value>` | Playwright cookies (`name`, `value`, `domain`, `path`, `expires`, `httpOnly`, `secure`, `sameSite`). |
| `origins` | `origins` | `Vec<crate::local_storage::OriginStorage>` |  |

#### `POST /v1/profiles/{id}/storage-state`

`import_storage_state` — `src-tauri/src/api_server.rs:5244`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`ApiStorageState`

**`ApiStorageState`** — `src-tauri/src/api_server.rs:287`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `cookies` | `cookies` | `Vec<serde_json::Value>` | Playwright cookies (`name`, `value`, `domain`, `path`, `expires`, `httpOnly`, `secure`, `sameSite`). |
| `origins` | `origins` | `Vec<crate::local_storage::OriginStorage>` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Imported. An item replaces the one of the same name; the origin's other items stay | `crate::local_storage::StorageStateImport` |
| 400 | Not a storageState, an origin that is not http(s), more than 10 MiB for one origin, or an ephemeral profile | — |
| 401 | Unauthorized | — |
| 404 | Profile not found | — |
| 409 | The browser is running, the profile is password-protected, or a remote session owns it | — |
| 500 | Internal server error | — |

### 2.5 `extensions`

#### `GET /v1/extension-groups`

`get_extension_groups` — `src-tauri/src/api_server.rs:3403`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of extension groups | `Vec<crate::extension_manager::ExtensionGroup>` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `POST /v1/extension-groups`

`create_extension_group_api` — `src-tauri/src/api_server.rs:3420`

请求体：`CreateExtensionGroupRequest`

**`CreateExtensionGroupRequest`** — `src-tauri/src/api_server.rs:649`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 201 | Extension group created | `crate::extension_manager::ExtensionGroup` |
| 400 | Empty or duplicate name | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `DELETE /v1/extension-groups/{id}`

`delete_extension_group_api` — `src-tauri/src/api_server.rs:3483`

路径/查询参数：

- `id` (Path, `String`) — Extension Group ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Extension group deleted | — |
| 401 | Unauthorized | — |
| 404 | Extension group not found | — |
| 500 | Internal server error | — |

#### `GET /v1/extension-groups/{id}`

`get_extension_group_api` — `src-tauri/src/api_server.rs:3440`

路径/查询参数：

- `id` (Path, `String`) — Extension Group ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Extension group | `crate::extension_manager::ExtensionGroup` |
| 401 | Unauthorized | — |
| 404 | Extension group not found | — |
| 500 | Internal server error | — |

#### `PUT /v1/extension-groups/{id}`

`update_extension_group_api` — `src-tauri/src/api_server.rs:3461`

路径/查询参数：

- `id` (Path, `String`) — Extension Group ID

请求体：`UpdateExtensionGroupRequest`

**`UpdateExtensionGroupRequest`** — `src-tauri/src/api_server.rs:654`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `Option<String>` | New group name. |
| `extension_ids` | `extension_ids` | `Option<Vec<String>>` | Replaces the whole membership list. Omit to leave it untouched; use the `/extensions/{extension_id}` sub-routes to add or remove one member. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Extension group updated | `crate::extension_manager::ExtensionGroup` |
| 400 | Empty or duplicate name | — |
| 401 | Unauthorized | — |
| 404 | Extension group not found | — |
| 500 | Internal server error | — |

#### `DELETE /v1/extension-groups/{id}/extensions/{extension_id}`

`remove_extension_from_group_api` — `src-tauri/src/api_server.rs:3529`

路径/查询参数：

- `id` (Path, `String`) — Extension Group ID
- `extension_id` (Path, `String`) — Extension ID to remove

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Extension group with the extension removed | `crate::extension_manager::ExtensionGroup` |
| 401 | Unauthorized | — |
| 404 | Extension group not found | — |
| 500 | Internal server error | — |

#### `POST /v1/extension-groups/{id}/extensions/{extension_id}`

`add_extension_to_group_api` — `src-tauri/src/api_server.rs:3506`

路径/查询参数：

- `id` (Path, `String`) — Extension Group ID
- `extension_id` (Path, `String`) — Extension ID to add

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Extension group with the extension added | `crate::extension_manager::ExtensionGroup` |
| 401 | Unauthorized | — |
| 404 | Extension or extension group not found | — |
| 500 | Internal server error | — |

#### `GET /v1/extensions`

`get_extensions` — `src-tauri/src/api_server.rs:3255`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of extensions | `Vec<crate::extension_manager::Extension>` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `POST /v1/extensions`

`create_extension_api` — `src-tauri/src/api_server.rs:3283`

请求体：`CreateExtensionRequest`

**`CreateExtensionRequest`** — `src-tauri/src/api_server.rs:613`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `Option<String>` | Display name. Optional — the manifest's own name wins when it has one, and a blank name is only rejected when the manifest has none either. |
| `file_name` | `file_name` | `Option<String>` | Name of the uploaded file. Its suffix picks the type: `.crx` or `.zip`. |
| `file_data_base64` | `file_data_base64` | `Option<String>` | Payload bytes, standard base64. Only meaningful with `file_name`. |
| `source_path` | `source_path` | `Option<String>` | Path on this machine: a `.crx`/`.zip`, or an unpacked extension directory holding a top-level `manifest.json`. |
| `link` | `link` | `Option<bool>` | Load a `source_path` directory in place instead of copying it into the store, so edits to the folder apply on the next browser start. Directory sources only, and a linked extension never syncs. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 201 | Extension added | `crate::extension_manager::Extension` |
| 400 | No source, two sources, undecodable payload, unsupported file type, or an unreadable unpacked directory | — |
| 401 | Unauthorized | — |
| 404 | source_path does not exist | — |
| 500 | Internal server error | — |

#### `DELETE /v1/extensions/{id}`

`delete_extension_api` — `src-tauri/src/api_server.rs:3382`

路径/查询参数：

- `id` (Path, `String`) — Extension ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Extension deleted | — |
| 401 | Unauthorized | — |
| 404 | Extension not found | — |
| 500 | Internal server error | — |

#### `GET /v1/extensions/{id}`

`get_extension_api` — `src-tauri/src/api_server.rs:3316`

路径/查询参数：

- `id` (Path, `String`) — Extension ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Extension | `crate::extension_manager::Extension` |
| 401 | Unauthorized | — |
| 404 | Extension not found | — |
| 500 | Internal server error | — |

#### `PUT /v1/extensions/{id}`

`update_extension_api` — `src-tauri/src/api_server.rs:3340`

路径/查询参数：

- `id` (Path, `String`) — Extension ID

请求体：`UpdateExtensionRequest`

**`UpdateExtensionRequest`** — `src-tauri/src/api_server.rs:634`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `Option<String>` | New display name. |
| `file_name` | `file_name` | `Option<String>` | Name of the replacement upload. Its suffix picks the type: `.crx` or `.zip`. |
| `file_data_base64` | `file_data_base64` | `Option<String>` | Replacement payload bytes, standard base64. Only meaningful with `file_name`. |
| `source_path` | `source_path` | `Option<String>` | Path on this machine to re-import from: a `.crx`/`.zip`, or an unpacked extension directory. |
| `link` | `link` | `Option<bool>` | Load a `source_path` directory in place instead of copying it in. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Extension updated | `crate::extension_manager::Extension` |
| 400 | Nothing to change, two sources, undecodable payload, unsupported file type, or an unreadable unpacked directory | — |
| 401 | Unauthorized | — |
| 404 | Extension not found, or source_path does not exist | — |
| 500 | Internal server error | — |

### 2.6 `groups`

#### `GET /v1/groups`

`get_groups` — `src-tauri/src/api_server.rs:2211`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of all groups | `Vec<ApiGroupResponse>` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `POST /v1/groups`

`create_group` — `src-tauri/src/api_server.rs:2287`

请求体：`CreateGroupRequest`

**`CreateGroupRequest`** — `src-tauri/src/api_server.rs:242`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Group created successfully | `ApiGroupResponse` |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`ApiGroupResponse`** — `src-tauri/src/api_server.rs:235`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `profile_count` | `profile_count` | `usize` |  |

#### `DELETE /v1/groups/{id}`

`delete_group` — `src-tauri/src/api_server.rs:2362`

路径/查询参数：

- `id` (Path, `String`) — Group ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Group deleted successfully | — |
| 401 | Unauthorized | — |
| 404 | Group not found | — |
| 500 | Internal server error | — |

#### `GET /v1/groups/{id}`

`get_group` — `src-tauri/src/api_server.rs:2247`

路径/查询参数：

- `id` (Path, `String`) — Group ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Group details | `ApiGroupResponse` |
| 401 | Unauthorized | — |
| 404 | Group not found | — |
| 500 | Internal server error | — |

**`ApiGroupResponse`** — `src-tauri/src/api_server.rs:235`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `profile_count` | `profile_count` | `usize` |  |

#### `PUT /v1/groups/{id}`

`update_group` — `src-tauri/src/api_server.rs:2322`

路径/查询参数：

- `id` (Path, `String`) — Group ID

请求体：`UpdateGroupRequest`

**`UpdateGroupRequest`** — `src-tauri/src/api_server.rs:247`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Group updated successfully | `ApiGroupResponse` |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 404 | Group not found | — |
| 500 | Internal server error | — |

**`ApiGroupResponse`** — `src-tauri/src/api_server.rs:235`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `profile_count` | `profile_count` | `usize` |  |

### 2.7 `profiles`

#### `GET /v1/profiles`

`get_profiles` — `src-tauri/src/api_server.rs:1653`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of all profiles | `ApiProfilesResponse` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`ApiProfilesResponse`** — `src-tauri/src/api_server.rs:126`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profiles` | `profiles` | `Vec<ApiProfile>` |  |
| `total` | `total` | `usize` |  |

#### `POST /v1/profiles`

`create_profile` — `src-tauri/src/api_server.rs:1776`

请求体：`CreateProfileRequest`

**`CreateProfileRequest`** — `src-tauri/src/api_server.rs:145`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |
| `browser` | `browser` | `String` | Browser engine. Must be `"wayfern"` (anti-detect Chromium). Any other value (e.g. `"chromium"`) is rejected with 400. |
| `version` | `version` | `Option<String>` | Optional. Omit (or pass `"latest"`) to use the newest already-downloaded version of the chosen browser. A concrete version must already be downloaded; the create path does not fetch new versions. |
| `proxy_id` | `proxy_id` | `Option<String>` | Optional stored-proxy id. Omit it, send `null`, or send an empty string for a profile with no proxy. Mutually exclusive with `vpn_id`. |
| `vpn_id` | `vpn_id` | `Option<String>` | Optional stored-VPN id. Omit it, send `null`, or send an empty string for a profile with no VPN. Mutually exclusive with `proxy_id`. |
| `launch_hook` | `launch_hook` | `Option<String>` |  |
| `release_type` | `release_type` | `Option<String>` |  |
| `wayfern_config` | `wayfern_config` | `Option<serde_json::Value>` | Wayfern fingerprint/config. Send only when `browser` is `"wayfern"`. Omit it, or pass an empty object `{}`, to have a fresh fingerprint generated automatically at creation. Provide a `fingerprint` field to pin a specific one. |
| `group_id` | `group_id` | `Option<String>` |  |
| `tags` | `tags` | `Option<Vec<String>>` |  |
| `ephemeral` | `ephemeral` | `Option<bool>` | Keep the profile's browsing data in memory only, so nothing it browses reaches real disk. Defaults to false. |
| `temporary` | `temporary` | `Option<bool>` | A profile for one automation run: implies `ephemeral`, is destroyed when its browser stops, and is swept at startup if it outlived a crash. Defaults to false. |
| `dns_server` | `dns_server` | `Option<String>` | DNS server to resolve names with, through the profile's proxy or VPN: `https://host/path` (DNS over HTTPS), `tls://host[:port]` (DNS over TLS), `tcp://host[:port]` (plain DNS), or a bare `host[:port]`. A bare address of a well-known public resolver such as `1.1.1.1` uses its DNS over HTTPS endpoint. Omit it, send `null`, or send an empty string to let the proxy resolve names. Anything else is rejected with 400. |
| `status_id` | `status_id` | `Option<String>` | Optional status id from `/v1/statuses`. |
| `start_urls` | `start_urls` | `Option<Vec<String>>` | Optional start pages, at most 20 http(s) URLs. A bare host gets `https://`. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Profile created successfully | `ApiProfileResponse` |
| 400 | Invalid browser, invalid wayfern_config, invalid dns_server, or no downloaded version available | — |
| 401 | Unauthorized | — |
| 402 | Selected proxy requires payment, or a cross-OS fingerprint or custom launch arguments require Pro | — |
| 429 | Hourly profile generation limit reached; the body carries retryAfterSeconds | — |
| 500 | Internal server error | — |

**`ApiProfileResponse`** — `src-tauri/src/api_server.rs:132`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile` | `profile` | `ApiProfile` |  |

#### `POST /v1/profiles/batch/run`

`batch_run_profiles` — `src-tauri/src/api_server.rs:4860`

请求体：`BatchRunRequest`

**`BatchRunRequest`** — `src-tauri/src/api_server.rs:663`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_ids` | `profile_ids` | `Vec<String>` | Profile IDs to launch. |
| `url` | `url` | `Option<String>` | Optional URL to open in every launched profile. |
| `headless` | `headless` | `Option<bool>` | Launch headless. Defaults to false. |
| `delay_ms` | `delay_ms` | `Option<u32>` | Pause between the starts of two launches, in milliseconds (0 to 60000). Defaults to the app's bulk launch delay. |
| `concurrency` | `concurrency` | `Option<u32>` | How many profiles may be starting at the same time (1 to 20). Defaults to the app's bulk launch concurrency. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Batch launch completed; inspect per-profile results | `BatchRunResponse` |
| 400 | The url is not an http, https or about:blank address | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 429 | Automation request rate limit exceeded | — |
| 500 | Internal server error | — |

**`BatchRunResponse`** — `src-tauri/src/api_server.rs:718`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `results` | `results` | `Vec<BatchRunResult>` |  |

#### `POST /v1/profiles/batch/stop`

`batch_stop_profiles` — `src-tauri/src/api_server.rs:5051`

请求体：`BatchStopRequest`

**`BatchStopRequest`** — `src-tauri/src/api_server.rs:734`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_ids` | `profile_ids` | `Vec<String>` | Profile IDs to stop. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Batch stop completed; inspect per-profile results | `BatchStopResponse` |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 429 | Automation request rate limit exceeded | — |
| 500 | Internal server error | — |

**`BatchStopResponse`** — `src-tauri/src/api_server.rs:749`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `results` | `results` | `Vec<BatchStopResult>` |  |

#### `POST /v1/profiles/bulk-edit`

`bulk_edit_profiles` — `src-tauri/src/api_server.rs:2488`

请求体：`BulkEditRequest`

**`BulkEditRequest`** — `src-tauri/src/api_server.rs:252`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_ids` | `profile_ids` | `Vec<String>` |  |
| `patch` | `patch` | `crate::profile::patch::ProfilePatch` | Fields left out stay as they are; `null` clears a field that can be empty. `new_device: true` makes the next launch generate a new device. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Every profile was checked first, then the changed ones were saved | `BulkEditResponse` |
| 400 | A value is invalid (DNS_SERVER_INVALID, START_URL_INVALID, WEBRTC_MODE_INVALID, ...); nothing changed | — |
| 401 | Unauthorized | — |
| 404 | A profile, status, group or extension group does not exist; nothing changed | — |
| 409 | A listed profile is running; nothing changed | — |

**`BulkEditResponse`** — `src-tauri/src/api_server.rs:260`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `changed` | `changed` | `usize` | How many of the profiles actually changed. |

#### `POST /v1/profiles/distribute-proxies`

`distribute_proxies` — `src-tauri/src/api_server.rs:5023`

请求体：`DistributeProxiesRequest`

**`DistributeProxiesRequest`** — `src-tauri/src/api_server.rs:723`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `pairs` | `pairs` | `Vec<crate::proxy_distribution::ProxyPair>` | Profile/proxy pairs to apply, one proxy per profile. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Distribution completed; inspect per-profile results | `DistributeProxiesResponse` |
| 400 | No pairs were supplied | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`DistributeProxiesResponse`** — `src-tauri/src/api_server.rs:729`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `results` | `results` | `Vec<crate::proxy_distribution::ProxyAssignmentResult>` |  |

#### `POST /v1/profiles/import`

`import_profiles_api` — `src-tauri/src/api_server.rs:5154`

请求体：`ImportProfilesRequest`

**`ImportProfilesRequest`** — `src-tauri/src/api_server.rs:766`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `items` | `items` | `Vec<crate::profile_importer::ImportProfileItem>` | Profiles to import. Each item is isolated — one failure doesn't stop the rest. |
| `group_id` | `group_id` | `Option<String>` | Optional group to assign every imported profile to. |
| `duplicate_strategy` | `duplicate_strategy` | `Option<crate::profile_importer::DuplicateStrategy>` | How to handle an already-taken profile name: "skip" or "rename" (auto-suffix). Defaults to "rename". |
| `wayfern_config` | `wayfern_config` | `Option<serde_json::Value>` | Wayfern fingerprint/config applied to every imported profile. Omit to have fresh fingerprints generated automatically. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Batch import completed; inspect per-item results | `crate::profile_importer::ProfileImportBatchResult` |
| 400 | No items, or invalid input | — |
| 401 | Unauthorized | — |
| 402 | Fingerprint OS spoofing requires an active Pro subscription | — |
| 404 | Group not found | — |
| 500 | Internal server error | — |

#### `GET /v1/profiles/import/detect`

`detect_import_profiles` — `src-tauri/src/api_server.rs:5120`

路径/查询参数：

- `folder` (Query, `Option<String>`) — Optional folder to scan instead of the default browser locations. Accepts a single profile dir, a Chromium user-data dir, or a folder holding one profile dir per child.

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Detected importable profiles | `DetectedProfilesResponse` |
| 401 | Unauthorized | — |
| 404 | Folder not found | — |
| 500 | Internal server error | — |

**`DetectedProfilesResponse`** — `src-tauri/src/api_server.rs:754`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profiles` | `profiles` | `Vec<crate::profile_importer::DetectedProfile>` |  |
| `total` | `total` | `usize` |  |

#### `DELETE /v1/profiles/{id}`

`delete_profile` — `src-tauri/src/api_server.rs:2181`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Profile deleted successfully | — |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 404 | Profile not found | — |
| 500 | Internal server error | — |

#### `GET /v1/profiles/{id}`

`get_profile` — `src-tauri/src/api_server.rs:1681`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Profile details | `ApiProfileResponse` |
| 401 | Unauthorized | — |
| 404 | Profile not found | — |
| 500 | Internal server error | — |

**`ApiProfileResponse`** — `src-tauri/src/api_server.rs:132`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile` | `profile` | `ApiProfile` |  |

#### `PUT /v1/profiles/{id}`

`update_profile` — `src-tauri/src/api_server.rs:1985`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`UpdateProfileRequest`

**`UpdateProfileRequest`** — `src-tauri/src/api_server.rs:195`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `Option<String>` |  |
| `version` | `version` | `Option<String>` |  |
| `proxy_id` | `proxy_id` | `Option<String>` | Omitted or `null` leaves the proxy assignment unchanged; an empty string detaches it. Assigning a proxy clears any assigned VPN. |
| `vpn_id` | `vpn_id` | `Option<String>` | Omitted or `null` leaves the VPN assignment unchanged; an empty string detaches it. Assigning a VPN clears any assigned proxy. |
| `launch_hook` | `launch_hook` | `Option<String>` |  |
| `release_type` | `release_type` | `Option<String>` |  |
| `group_id` | `group_id` | `Option<String>` |  |
| `tags` | `tags` | `Option<Vec<String>>` |  |
| `extension_group_id` | `extension_group_id` | `Option<String>` |  |
| `proxy_bypass_rules` | `proxy_bypass_rules` | `Option<Vec<String>>` |  |
| `sync_mode` | `sync_mode` | `Option<String>` | One of "Disabled", "Regular", "Encrypted". |
| `clear_on_close` | `clear_on_close` | `Option<bool>` | Wipe browsing data (keeping extensions and bookmarks) when the browser exits. Rejected (400) for ephemeral or password-protected profiles. |
| `dns_server` | `dns_server` | `Option<String>` | Omitted or `null` leaves the DNS server unchanged; an empty string clears it, so the proxy resolves names again. Same formats as on create. Takes effect at the next launch. |
| `status_id` | `status_id` | `Option<String>` | Omitted or `null` leaves the status unchanged; an empty string clears it. |
| `start_urls` | `start_urls` | `Option<Vec<String>>` | Replaces the start pages; an empty list removes them. Omitted or `null` leaves them unchanged. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Profile updated successfully | `ApiProfileResponse` |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 404 | Profile not found | — |
| 500 | Internal server error | — |

**`ApiProfileResponse`** — `src-tauri/src/api_server.rs:132`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile` | `profile` | `ApiProfile` |  |

#### `POST /v1/profiles/{id}/cloud-sync`

`set_profile_cloud_sync` — `src-tauri/src/api_server.rs:3757`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`SetCloudSyncRequest`

**`SetCloudSyncRequest`** — `src-tauri/src/api_server.rs:465`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `mode` | `mode` | `String` | `Disabled`, `Regular`, or `Encrypted`.  `Encrypted` derives its key from a passphrase that never leaves this machine, so a profile in that mode can be synced but NOT run remotely — a remote host would download ciphertext it cannot decrypt. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Cloud sync mode updated | `SetCloudSyncResponse` |
| 400 | Invalid mode, or the profile cannot be synced | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with cloud backup required | — |
| 404 | Profile not found | — |
| 409 | Profile is running — stop it before enabling sync | — |
| 500 | Internal server error | — |

**`SetCloudSyncResponse`** — `src-tauri/src/api_server.rs:475`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_id` | `profile_id` | `String` |  |
| `mode` | `mode` | `String` |  |
| `remote_launchable` | `remote_launchable` | `bool` | Whether the profile can now be launched on a remote host. |
| `remote_blocked_reason` | `remote_blocked_reason` | `Option<String>` | Why not, when `remote_launchable` is false. |

#### `GET /v1/profiles/{id}/fingerprint`

`get_profile_fingerprint_api` — `src-tauri/src/api_server.rs:1720`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The device the profile presents | `ApiProfileFingerprintResponse` |
| 400 | The browser could not rebuild the device | — |
| 401 | Unauthorized | — |
| 402 | The profile's fingerprint OS needs a paid plan | — |
| 404 | Profile not found | — |
| 500 | Internal server error | — |
| 503 | The device could not be read right now; try again | — |

**`ApiProfileFingerprintResponse`** — `src-tauri/src/api_server.rs:137`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `fingerprint` | `fingerprint` | `Option<String>` | The device the profile presents, as a JSON-encoded object: the shape `wayfern_config.fingerprint` takes on create. `null` when there is none to show. |

#### `POST /v1/profiles/{id}/kill`

`kill_profile` — `src-tauri/src/api_server.rs:4791`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Browser stopped, locally or on the profile's remote session | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan required | — |
| 404 | Profile not found | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | The fleet could not be reached; the remote browser is still running | — |
| 500 | Internal server error | — |

#### `POST /v1/profiles/{id}/open-url`

`open_url_in_profile` — `src-tauri/src/api_server.rs:4726`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`OpenUrlRequest`

**`OpenUrlRequest`** — `src-tauri/src/api_server.rs:591`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `url` | `url` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | URL opened successfully, locally or on the profile's remote session | — |
| 400 | Cannot open URL with a cross-OS profile that is not running remotely, or the url is not an http, https or about:blank address | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | Profile is locked by another team member, or waiting for a finished remote session to be pulled back | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | The profile lock service could not be reached, or the profile's files could not be downloaded from sync before its first launch here | — |
| 500 | Internal server error | — |

#### `POST /v1/profiles/{id}/run`

`run_profile` — `src-tauri/src/api_server.rs:3552`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`RunProfileRequest`

**`RunProfileRequest`** — `src-tauri/src/api_server.rs:585`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `url` | `url` | `Option<String>` |  |
| `headless` | `headless` | `Option<bool>` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Profile launched successfully | `RunProfileResponse` |
| 400 | Cannot launch cross-OS profile, or the url is not an http, https or about:blank address | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | Profile is locked by another team member, open on another device of the account, running on the remote fleet, or waiting for a finished remote session to be pulled back | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | The profile lock service could not be reached, or the profile's files could not be downloaded from sync before its first launch here | — |
| 500 | Internal server error | — |

**`RunProfileResponse`** — `src-tauri/src/api_server.rs:448`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_id` | `profile_id` | `String` |  |
| `remote_debugging_port` | `remote_debugging_port` | `u16` |  |
| `headless` | `headless` | `bool` | The mode asked for. A browser that was already running keeps its own. |
| `attached` | `attached` | `bool` | True when the profile was already running and was taken over as it is, with no restart. |

#### `POST /v1/profiles/{id}/run-remote`

`run_profile_remote` — `src-tauri/src/api_server.rs:3679`

路径/查询参数：

- `id` (Path, `String`) — Profile ID

请求体：`RunRemoteRequest`

**`RunRemoteRequest`** — `src-tauri/src/api_server.rs:459`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `url` | `url` | `Option<String>` | Optional URL to open once the remote browser is up. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Remote session started | `RunRemoteResponse` |
| 400 | Profile does not have cloud sync enabled, or the url is not an http, https or about:blank address | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | Profile not found | — |
| 409 | Profile is locked by another session | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | No remote capacity for this operating system | — |
| 500 | Internal server error | — |

**`RunRemoteResponse`** — `src-tauri/src/api_server.rs:485`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profile_id` | `profile_id` | `String` |  |
| `session_id` | `session_id` | `String` | Remote session id, for polling or closing the session. |
| `platform` | `platform` | `String` | Operating system of the host the session was scheduled onto: `linux` for a profile that runs on every OS, else the OS that created the profile. |
| `status` | `status` | `String` |  |

#### `DELETE /v1/remote-sessions/{id}`

`stop_remote_session` — `src-tauri/src/api_server.rs:3914`

路径/查询参数：

- `id` (Path, `String`) — Remote session ID from run-remote

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Remote session stopped | `StopRemoteResponse` |
| 401 | Unauthorized | — |
| 404 | No such remote session | — |
| 429 | Automation request rate limit exceeded | — |
| 503 | The fleet could not be reached; the session is still running | — |
| 500 | Internal server error | — |

**`StopRemoteResponse`** — `src-tauri/src/api_server.rs:496`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `session_id` | `session_id` | `String` |  |
| `status` | `status` | `String` |  |
| `billed_seconds` | `billed_seconds` | `u64` | What the session actually cost, in seconds. |

### 2.8 `proxies`

#### `GET /v1/proxies`

`get_proxies` — `src-tauri/src/api_server.rs:2671`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of all proxies | `Vec<ApiProxyResponse>` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `POST /v1/proxies`

`create_proxy` — `src-tauri/src/api_server.rs:2722`

请求体：`CreateProxyRequest`

**`CreateProxyRequest`** — `src-tauri/src/api_server.rs:363`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |
| `proxy_settings` | `proxy_settings` | `ProxySettings` |  |
| `rotation_url` | `rotation_url` | `Option<String>` | Optional http(s) "change IP" link from the proxy provider. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Proxy created successfully | `ApiProxyResponse` |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`ApiProxyResponse`** — `src-tauri/src/api_server.rs:341`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `proxy_settings` | `proxy_settings` | `ProxySettings` |  |
| `rotation_url` | `rotation_url` | `Option<String>` | The provider's "change IP" link, or `null`. Call `POST /v1/proxies/{id}/rotate` to use it. |

#### `POST /v1/proxies/import`

`import_proxies_api` — `src-tauri/src/api_server.rs:2761`

请求体：`ImportProxiesRequest`

**`ImportProxiesRequest`** — `src-tauri/src/api_server.rs:781`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `format` | `format` | `String` | "txt" — one proxy per line (`host:port`, `host:port:user:pass`, or URL forms like `http://user:pass@host:port`). "json" — a Donut proxy export. |
| `content` | `content` | `String` | Raw proxy list / export content. |
| `name_prefix` | `name_prefix` | `Option<String>` | Name prefix for txt imports; proxies are named "{prefix} Proxy {n}". |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Import completed; inspect counts and per-proxy errors | `ImportProxiesResponse` |
| 400 | Invalid format or no valid proxies in content | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`ImportProxiesResponse`** — `src-tauri/src/api_server.rs:792`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `imported_count` | `imported_count` | `usize` |  |
| `skipped_count` | `skipped_count` | `usize` |  |
| `errors` | `errors` | `Vec<String>` |  |
| `proxies` | `proxies` | `Vec<ApiProxyResponse>` |  |

#### `DELETE /v1/proxies/{id}`

`delete_proxy` — `src-tauri/src/api_server.rs:2904`

路径/查询参数：

- `id` (Path, `String`) — Proxy ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Proxy deleted successfully | — |
| 400 | Bad request (e.g. cloud-managed proxy) | — |
| 401 | Unauthorized | — |
| 404 | Proxy not found | — |
| 500 | Internal server error | — |

#### `GET /v1/proxies/{id}`

`get_proxy` — `src-tauri/src/api_server.rs:2693`

路径/查询参数：

- `id` (Path, `String`) — Proxy ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Proxy details | `ApiProxyResponse` |
| 401 | Unauthorized | — |
| 404 | Proxy not found | — |
| 500 | Internal server error | — |

**`ApiProxyResponse`** — `src-tauri/src/api_server.rs:341`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `proxy_settings` | `proxy_settings` | `ProxySettings` |  |
| `rotation_url` | `rotation_url` | `Option<String>` | The provider's "change IP" link, or `null`. Call `POST /v1/proxies/{id}/rotate` to use it. |

#### `PUT /v1/proxies/{id}`

`update_proxy` — `src-tauri/src/api_server.rs:2826`

路径/查询参数：

- `id` (Path, `String`) — Proxy ID

请求体：`UpdateProxyRequest`

**`UpdateProxyRequest`** — `src-tauri/src/api_server.rs:373`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `Option<String>` |  |
| `proxy_settings` | `proxy_settings` | `Option<ProxySettings>` |  |
| `rotation_url` | `rotation_url` | `Option<String>` | Omitted or `null` leaves the "change IP" link unchanged; an empty string clears it. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Proxy updated successfully | `ApiProxyResponse` |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 404 | Proxy not found | — |
| 500 | Internal server error | — |

**`ApiProxyResponse`** — `src-tauri/src/api_server.rs:341`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `proxy_settings` | `proxy_settings` | `ProxySettings` |  |
| `rotation_url` | `rotation_url` | `Option<String>` | The provider's "change IP" link, or `null`. Call `POST /v1/proxies/{id}/rotate` to use it. |

#### `POST /v1/proxies/{id}/rotate`

`rotate_proxy` — `src-tauri/src/api_server.rs:2869`

路径/查询参数：

- `id` (Path, `String`) — Proxy ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | The provider accepted the IP change. Every profile behind the proxy moves to the new IP. | `crate::proxy_rotation::RotationResult` |
| 400 | The proxy has no change-IP link (PROXY_ROTATION_URL_MISSING) | — |
| 401 | Unauthorized | — |
| 404 | Proxy not found | — |
| 502 | The provider refused or did not answer (PROXY_ROTATION_FAILED, PROXY_ROTATION_TIMEOUT, PROXY_ROTATION_UNREACHABLE, SYSTEM_PROXY_UNREACHABLE) | — |

**`RotationResult`** — `src-tauri/src/proxy_rotation.rs:17`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `proxy_id` | `proxy_id` | `String` |  |
| `status` | `status` | `Option<u16>` | The provider's HTTP status, when it answered. |
| `elapsed_ms` | `elapsed_ms` | `u64` |  |
| `error` | `error` | `Option<String>` | A coded backend error when the IP change was not confirmed. |

### 2.9 `remote-sessions`

#### `GET /v1/remote-hours`

`get_remote_hours` — `src-tauri/src/api_server.rs:4278`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Pooled remote-hour budget and its breakdown | `crate::cookie_bot::RemoteHoursQuota` |
| 401 | Unauthorized | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `GET /v1/remote-sessions`

`list_remote_sessions_api` — `src-tauri/src/api_server.rs:4220`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Sessions owned by the signed-in account | `ApiRemoteSessionsResponse` |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

**`ApiRemoteSessionsResponse`** — `src-tauri/src/api_server.rs:509`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `sessions` | `sessions` | `Vec<crate::remote_session::RemoteSessionState>` |  |

#### `GET /v1/remote-sessions/{id}`

`get_remote_session_api` — `src-tauri/src/api_server.rs:4245`

路径/查询参数：

- `id` (Path, `String`) — Remote session ID from run-remote

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Current session state | `crate::remote_session::RemoteSessionState` |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 403 | This desktop is not signed in to Donut cloud | — |
| 404 | No such remote session | — |
| 503 | Donut cloud could not be reached | — |
| 500 | Internal server error | — |

#### `GET /v1/remote-sessions/{id}/cdp`

`remote_session_cdp` — `src-tauri/src/api_server.rs:4088`

路径/查询参数：

- `id` (Path, `String`) — Remote session ID from run-remote

| 状态 | 说明 | 响应体 |
|---|---|---|
| 101 | Switching Protocols; a browser-level CDP WebSocket follows | — |
| 401 | Unauthorized | — |
| 402 | Active paid plan with browser automation required | — |
| 404 | No such remote session, or it is not attachable yet | — |
| 502 | The relay could not be reached | — |
| 426 | Not a WebSocket upgrade request | — |

### 2.10 `statuses`

#### `GET /v1/statuses`

`get_statuses` — `src-tauri/src/api_server.rs:2396`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Every profile status, in their order | `Vec<ApiStatusResponse>` |
| 401 | Unauthorized | — |

#### `POST /v1/statuses`

`create_status` — `src-tauri/src/api_server.rs:2417`

请求体：`StatusRequest`

**`StatusRequest`** — `src-tauri/src/api_server.rs:333`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` | 1 to 40 characters, unique (case-insensitive). |
| `color` | `color` | `String` | `#rrggbb`. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Status created | `ApiStatusResponse` |
| 400 | Empty, too long or duplicate name, invalid color, or 100 statuses already | — |
| 401 | Unauthorized | — |

**`ApiStatusResponse`** — `src-tauri/src/api_server.rs:268`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `color` | `color` | `String` | `#rrggbb`. |

#### `DELETE /v1/statuses/{id}`

`delete_status` — `src-tauri/src/api_server.rs:2466`

路径/查询参数：

- `id` (Path, `String`) — Status ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Status deleted and taken off every profile that had it | — |
| 401 | Unauthorized | — |
| 404 | Status not found | — |

#### `PUT /v1/statuses/{id}`

`update_status` — `src-tauri/src/api_server.rs:2439`

路径/查询参数：

- `id` (Path, `String`) — Status ID

请求体：`StatusRequest`

**`StatusRequest`** — `src-tauri/src/api_server.rs:333`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` | 1 to 40 characters, unique (case-insensitive). |
| `color` | `color` | `String` | `#rrggbb`. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Status updated | `ApiStatusResponse` |
| 400 | Empty, too long or duplicate name, or invalid color | — |
| 401 | Unauthorized | — |
| 404 | Status not found | — |

**`ApiStatusResponse`** — `src-tauri/src/api_server.rs:268`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `color` | `color` | `String` | `#rrggbb`. |

### 2.11 `tags`

#### `GET /v1/tags`

`get_tags` — `src-tauri/src/api_server.rs:2647`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of all tags | `Vec<String>` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

### 2.12 `templates`

#### `GET /v1/templates`

`get_templates` — `src-tauri/src/api_server.rs:2514`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Every profile template, in their order | `Vec<crate::profile_templates::ProfileTemplate>` |
| 401 | Unauthorized | — |

#### `POST /v1/templates`

`create_template` — `src-tauri/src/api_server.rs:2530`

请求体：`TemplateRequest`

**`TemplateRequest`** — `src-tauri/src/api_server.rs:306`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` | 1 to 60 characters, unique (case-insensitive). |
| `settings` | `settings` | `crate::profile_templates::TemplateSettings` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Template created. Device fields in `wayfern_config` are dropped: every profile made from it gets its own device | `crate::profile_templates::ProfileTemplate` |
| 400 | Empty, too long or duplicate name, an invalid value, both a proxy and a VPN, or 100 templates already | — |
| 401 | Unauthorized | — |
| 404 | A status, group or extension group does not exist | — |

#### `DELETE /v1/templates/{id}`

`delete_template` — `src-tauri/src/api_server.rs:2582`

路径/查询参数：

- `id` (Path, `String`) — Template ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | Template deleted; profiles made from it keep their settings | — |
| 401 | Unauthorized | — |
| 404 | Template not found | — |

#### `PUT /v1/templates/{id}`

`update_template` — `src-tauri/src/api_server.rs:2554`

路径/查询参数：

- `id` (Path, `String`) — Template ID

请求体：`TemplateRequest`

**`TemplateRequest`** — `src-tauri/src/api_server.rs:306`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` | 1 to 60 characters, unique (case-insensitive). |
| `settings` | `settings` | `crate::profile_templates::TemplateSettings` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Template replaced | `crate::profile_templates::ProfileTemplate` |
| 400 | Empty, too long or duplicate name, an invalid value, or both a proxy and a VPN | — |
| 401 | Unauthorized | — |
| 404 | Template, status, group or extension group not found | — |

#### `POST /v1/templates/{id}/profiles`

`create_profiles_from_template` — `src-tauri/src/api_server.rs:2604`

路径/查询参数：

- `id` (Path, `String`) — Template ID

请求体：`CreateFromTemplateRequest`

**`CreateFromTemplateRequest`** — `src-tauri/src/api_server.rs:314`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `count` | `count` | `u32` | 1 to 100. |
| `name` | `name` | `Option<String>` | One profile takes this name; several take it followed by numbers that continue after the highest in use. Defaults to the template's name prefix, else its name. |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Profiles made with the newest downloaded Wayfern, each with its own device. When `error` is set, creation stopped early and `profiles` lists what was made | `ApiBulkCreateResponse` |
| 400 | Count outside 1 to 100, empty name, a name in use, or a proxy or VPN that does not work | — |
| 401 | Unauthorized | — |
| 402 | The template's fingerprint OS needs a paid plan | — |
| 404 | Template not found | — |
| 409 | Another bulk creation is running | — |
| 429 | The hourly profile allowance is used up; nothing was made | — |

**`ApiBulkCreateResponse`** — `src-tauri/src/api_server.rs:325`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `profiles` | `profiles` | `Vec<ApiProfile>` | The profiles made, in order. |
| `error` | `error` | `Option<String>` | Why creation stopped before `count` (an error code JSON), or `null`. |

### 2.13 `vpns`

#### `GET /v1/vpns`

`get_vpns` — `src-tauri/src/api_server.rs:2951`

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | List of all VPN configurations | `Vec<ApiVpnResponse>` |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

#### `POST /v1/vpns`

`create_vpn` — `src-tauri/src/api_server.rs:3067`

请求体：`CreateVpnRequest`

**`CreateVpnRequest`** — `src-tauri/src/api_server.rs:414`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |
| `vpn_type` | `vpn_type` | `String` | Must be "WireGuard" |
| `config_data` | `config_data` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | VPN configuration created successfully | `ApiVpnResponse` |
| 400 | Invalid VPN config or unknown vpn_type | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`ApiVpnResponse`** — `src-tauri/src/api_server.rs:384`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `vpn_type` | `vpn_type` | `String` | Always "WireGuard" |
| `created_at` | `created_at` | `i64` |  |
| `last_used` | `last_used` | `Option<i64>` |  |

#### `POST /v1/vpns/import`

`import_vpn` — `src-tauri/src/api_server.rs:3035`

请求体：`ImportVpnRequest`

**`ImportVpnRequest`** — `src-tauri/src/api_server.rs:404`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `content` | `content` | `String` | Raw WireGuard `.conf` file content |
| `filename` | `filename` | `String` | Original filename |
| `name` | `name` | `Option<String>` | Optional display name; defaults to filename-based name |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | VPN configuration imported successfully | `ApiVpnResponse` |
| 400 | Invalid or unrecognized VPN config | — |
| 401 | Unauthorized | — |
| 500 | Internal server error | — |

**`ApiVpnResponse`** — `src-tauri/src/api_server.rs:384`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `vpn_type` | `vpn_type` | `String` | Always "WireGuard" |
| `created_at` | `created_at` | `i64` |  |
| `last_used` | `last_used` | `Option<i64>` |  |

#### `DELETE /v1/vpns/{id}`

`delete_vpn` — `src-tauri/src/api_server.rs:3135`

路径/查询参数：

- `id` (Path, `String`) — VPN configuration ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 204 | VPN configuration deleted successfully | — |
| 401 | Unauthorized | — |
| 404 | VPN configuration not found | — |
| 500 | Internal server error | — |

#### `GET /v1/vpns/{id}`

`get_vpn` — `src-tauri/src/api_server.rs:2974`

路径/查询参数：

- `id` (Path, `String`) — VPN configuration ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | VPN configuration details | `ApiVpnResponse` |
| 401 | Unauthorized | — |
| 404 | VPN configuration not found | — |
| 500 | Internal server error | — |

**`ApiVpnResponse`** — `src-tauri/src/api_server.rs:384`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `vpn_type` | `vpn_type` | `String` | Always "WireGuard" |
| `created_at` | `created_at` | `i64` |  |
| `last_used` | `last_used` | `Option<i64>` |  |

#### `PUT /v1/vpns/{id}`

`update_vpn` — `src-tauri/src/api_server.rs:3100`

路径/查询参数：

- `id` (Path, `String`) — VPN configuration ID

请求体：`UpdateVpnRequest`

**`UpdateVpnRequest`** — `src-tauri/src/api_server.rs:422`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `name` | `name` | `String` |  |

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | VPN configuration updated successfully | `ApiVpnResponse` |
| 400 | Bad request | — |
| 401 | Unauthorized | — |
| 404 | VPN configuration not found | — |
| 500 | Internal server error | — |

**`ApiVpnResponse`** — `src-tauri/src/api_server.rs:384`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `vpn_type` | `vpn_type` | `String` | Always "WireGuard" |
| `created_at` | `created_at` | `i64` |  |
| `last_used` | `last_used` | `Option<i64>` |  |

#### `GET /v1/vpns/{id}/export`

`export_vpn` — `src-tauri/src/api_server.rs:3004`

路径/查询参数：

- `id` (Path, `String`) — VPN configuration ID

| 状态 | 说明 | 响应体 |
|---|---|---|
| 200 | Decrypted VPN configuration | `ApiVpnExportResponse` |
| 401 | Unauthorized | — |
| 404 | VPN configuration not found | — |
| 500 | Internal server error | — |

**`ApiVpnExportResponse`** — `src-tauri/src/api_server.rs:394`

| JSON field | Rust field | Type | Notes |
|---|---|---|---|
| `id` | `id` | `String` |  |
| `name` | `name` | `String` |  |
| `vpn_type` | `vpn_type` | `String` | Always "WireGuard" |
| `config_data` | `config_data` | `String` | Raw `.conf` file content (decrypted) |

## 3. 结构索引

| 结构 | 文件:行 | 字段数 |
|---|---|---|
| `ApiBulkCreateResponse` | `src-tauri/src/api_server.rs:325` | 2 |
| `ApiDoc` | `src-tauri/src/api_server.rs:1025` | 2 |
| `ApiGroupResponse` | `src-tauri/src/api_server.rs:235` | 3 |
| `ApiProfile` | `src-tauri/src/api_server.rs:34` | 26 |
| `ApiProfileFingerprintResponse` | `src-tauri/src/api_server.rs:137` | 1 |
| `ApiProfileResponse` | `src-tauri/src/api_server.rs:132` | 1 |
| `ApiProfilesResponse` | `src-tauri/src/api_server.rs:126` | 2 |
| `ApiProxyResponse` | `src-tauri/src/api_server.rs:341` | 4 |
| `ApiRemoteSessionsResponse` | `src-tauri/src/api_server.rs:509` | 1 |
| `ApiServer` | `src-tauri/src/api_server.rs:1045` | 3 |
| `ApiServerState` | `src-tauri/src/api_server.rs:230` | 1 |
| `ApiStatusResponse` | `src-tauri/src/api_server.rs:268` | 3 |
| `ApiStorageState` | `src-tauri/src/api_server.rs:287` | 2 |
| `ApiVpnExportResponse` | `src-tauri/src/api_server.rs:394` | 4 |
| `ApiVpnResponse` | `src-tauri/src/api_server.rs:384` | 5 |
| `BatchRunRequest` | `src-tauri/src/api_server.rs:663` | 5 |
| `BatchRunResponse` | `src-tauri/src/api_server.rs:718` | 1 |
| `BatchRunResult` | `src-tauri/src/api_server.rs:707` | 4 |
| `BatchStopRequest` | `src-tauri/src/api_server.rs:734` | 1 |
| `BatchStopResponse` | `src-tauri/src/api_server.rs:749` | 1 |
| `BatchStopResult` | `src-tauri/src/api_server.rs:740` | 3 |
| `BrowserProfile` | `src-tauri/src/profile/types.rs:24` | 33 |
| `BulkEditRequest` | `src-tauri/src/api_server.rs:252` | 2 |
| `BulkEditResponse` | `src-tauri/src/api_server.rs:260` | 1 |
| `CdpTarget` | `src-tauri/src/wayfern_manager.rs:1497` | 2 |
| `CookieBotConflictsQuery` | `src-tauri/src/api_server.rs:564` | 4 |
| `CookieBotRunsQuery` | `src-tauri/src/api_server.rs:572` | 4 |
| `CookieBotScopeQuery` | `src-tauri/src/api_server.rs:559` | 1 |
| `CookieBotUsageQuery` | `src-tauri/src/api_server.rs:580` | 1 |
| `CreateExtensionGroupRequest` | `src-tauri/src/api_server.rs:649` | 1 |
| `CreateExtensionRequest` | `src-tauri/src/api_server.rs:613` | 5 |
| `CreateFromTemplateRequest` | `src-tauri/src/api_server.rs:314` | 2 |
| `CreateGroupRequest` | `src-tauri/src/api_server.rs:242` | 1 |
| `CreateProfileRequest` | `src-tauri/src/api_server.rs:145` | 15 |
| `CreateProxyRequest` | `src-tauri/src/api_server.rs:363` | 3 |
| `CreateVpnRequest` | `src-tauri/src/api_server.rs:414` | 3 |
| `DetectImportQuery` | `src-tauri/src/api_server.rs:760` | 1 |
| `DetectedProfilesResponse` | `src-tauri/src/api_server.rs:754` | 2 |
| `DistributeProxiesRequest` | `src-tauri/src/api_server.rs:723` | 1 |
| `DistributeProxiesResponse` | `src-tauri/src/api_server.rs:729` | 1 |
| `DownloadBrowserRequest` | `src-tauri/src/api_server.rs:427` | 2 |
| `DownloadBrowserResponse` | `src-tauri/src/api_server.rs:433` | 3 |
| `Extraction` | `src-tauri/src/wayfern_cdp.rs:563` | 7 |
| `ExtractionField` | `src-tauri/src/wayfern_cdp.rs:471` | 4 |
| `ExtractionRequest` | `src-tauri/src/wayfern_cdp.rs:485` | 8 |
| `ExtractionRow` | `src-tauri/src/wayfern_cdp.rs:551` | 3 |
| `GeneratedFingerprint` | `src-tauri/src/wayfern_manager.rs:1439` | 4 |
| `GithubAsset` | `src-tauri/src/browser.rs:471` | 11 |
| `GithubRelease` | `src-tauri/src/browser.rs:439` | 15 |
| `Glide` | `src-tauri/src/wayfern_cdp.rs:1157` | 2 |
| `HeadlessWayfern` | `src-tauri/src/wayfern_manager.rs:1126` | 4 |
| `ImportCookiesRequest` | `src-tauri/src/api_server.rs:596` | 1 |
| `ImportCookiesResponse` | `src-tauri/src/api_server.rs:603` | 3 |
| `ImportProfilesRequest` | `src-tauri/src/api_server.rs:766` | 4 |
| `ImportProxiesRequest` | `src-tauri/src/api_server.rs:781` | 3 |
| `ImportProxiesResponse` | `src-tauri/src/api_server.rs:792` | 4 |
| `ImportVpnRequest` | `src-tauri/src/api_server.rs:404` | 3 |
| `Inscription` | `src-tauri/src/wayfern_cdp.rs:1174` | 3 |
| `LocatorAttribute` | `src-tauri/src/wayfern_cdp.rs:200` | 2 |
| `LocatorBounds` | `src-tauri/src/wayfern_cdp.rs:257` | 4 |
| `LocatorCandidate` | `src-tauri/src/wayfern_cdp.rs:271` | 9 |
| `LocatorDescription` | `src-tauri/src/wayfern_cdp.rs:212` | 6 |
| `LocatorResolution` | `src-tauri/src/wayfern_cdp.rs:291` | 5 |
| `OpenUrlRequest` | `src-tauri/src/api_server.rs:591` | 1 |
| `PerceptionFrame` | `src-tauri/src/wayfern_cdp.rs:420` | 4 |
| `PerceptionNode` | `src-tauri/src/wayfern_cdp.rs:383` | 19 |
| `PerceptionPage` | `src-tauri/src/wayfern_cdp.rs:453` | 8 |
| `PerceptionRequest` | `src-tauri/src/wayfern_cdp.rs:322` | 7 |
| `PerceptionStats` | `src-tauri/src/wayfern_cdp.rs:431` | 7 |
| `PickedElement` | `src-tauri/src/wayfern_cdp.rs:582` | 5 |
| `ProbeTransport` | `src-tauri/src/wayfern_manager.rs:1415` | 3 |
| `ProxySettings` | `src-tauri/src/browser.rs:6` | 6 |
| `ResolveOptions` | `src-tauri/src/wayfern_cdp.rs:306` | 3 |
| `RotationResult` | `src-tauri/src/proxy_rotation.rs:17` | 4 |
| `RunProfileRequest` | `src-tauri/src/api_server.rs:585` | 2 |
| `RunProfileResponse` | `src-tauri/src/api_server.rs:448` | 4 |
| `RunRemoteRequest` | `src-tauri/src/api_server.rs:459` | 1 |
| `RunRemoteResponse` | `src-tauri/src/api_server.rs:485` | 4 |
| `SetCloudSyncRequest` | `src-tauri/src/api_server.rs:465` | 1 |
| `SetCloudSyncResponse` | `src-tauri/src/api_server.rs:475` | 4 |
| `SetCookieBotScheduleRequest` | `src-tauri/src/api_server.rs:519` | 11 |
| `StartCookieBotRunRequest` | `src-tauri/src/api_server.rs:550` | 2 |
| `StatusRequest` | `src-tauri/src/api_server.rs:333` | 2 |
| `StopRemoteResponse` | `src-tauri/src/api_server.rs:496` | 3 |
| `StorageStateQuery` | `src-tauri/src/api_server.rs:298` | 2 |
| `Strike` | `src-tauri/src/wayfern_cdp.rs:1166` | 1 |
| `TemplateRequest` | `src-tauri/src/api_server.rs:306` | 2 |
| `ToastPayload` | `src-tauri/src/api_server.rs:440` | 4 |
| `UpdateExtensionGroupRequest` | `src-tauri/src/api_server.rs:654` | 2 |
| `UpdateExtensionRequest` | `src-tauri/src/api_server.rs:634` | 5 |
| `UpdateGroupRequest` | `src-tauri/src/api_server.rs:247` | 1 |
| `UpdateProfileRequest` | `src-tauri/src/api_server.rs:195` | 15 |
| `UpdateProxyRequest` | `src-tauri/src/api_server.rs:373` | 3 |
| `UpdateVpnRequest` | `src-tauri/src/api_server.rs:422` | 1 |
| `VellumPointer` | `src-tauri/src/wayfern_cdp.rs:1138` | 2 |
| `ViewportTarget` | `src-tauri/src/wayfern_cdp.rs:999` | 4 |
| `WayfernConfig` | `src-tauri/src/wayfern_manager.rs:17` | 23 |
| `WayfernInstance` | `src-tauri/src/wayfern_manager.rs:1475` | 5 |
| `WayfernLaunchResult` | `src-tauri/src/wayfern_manager.rs:1456` | 4 |
| `WayfernManager` | `src-tauri/src/wayfern_manager.rs:1491` | 2 |
| `WayfernManagerInner` | `src-tauri/src/wayfern_manager.rs:1487` | 1 |
| `WayfernSession` | `src-tauri/src/wayfern_cdp.rs:602` | 2 |
| `WorkArea` | `src-tauri/src/wayfern_manager.rs:645` | 2 |
| `had` | `src-tauri/src/api_server.rs:92` | 26 |

