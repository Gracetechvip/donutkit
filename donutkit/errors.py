"""SDK 的错误类型。

三种失败来源各自的形状不同，所以分开，并且都把原始信息留全（调用方通常需要
`code` 来做分支，而不是解析字符串）：

* `DonutError`  —— 本地 REST API。状态码 + body；body 里可能是
  `{"code": "PROFILE_RUNNING"}`（api_server.rs:1545 `manager_error_response`
  把 manager 层的 coded error 原样透出），也可能是空 body（例如 402 付费闸门）。
* `SyncError`   —— 自建 donut-sync。状态码 + body（`{"error": ...}` 或纯文本）。
* `CdpError`    —— Chrome DevTools Protocol。协议错误里可能带引擎自己的话，
  例如 `Browser automation requires a paid Donut Browser plan.`（免费计划的实测结果）。
"""

from __future__ import annotations

from typing import Optional


class DonutError(RuntimeError):
    """本地 REST API 调用失败。"""

    def __init__(
        self,
        status: int,
        message: str,
        method: str = "",
        path: str = "",
        code: Optional[str] = None,
    ):
        self.status = status
        self.message = message
        self.method = method
        self.path = path
        self.code = code
        detail = f"{method} {path} -> HTTP {status}".strip()
        if code:
            detail += f" [{code}]"
        if message:
            detail += f": {message[:500]}"
        super().__init__(detail)

    @property
    def is_plan_gate(self) -> bool:
        """402：该动作需要 browserAutomation / cloudBackup 等付费能力。"""
        return self.status == 402

    @property
    def is_terms_gate(self) -> bool:
        """403：Wayfern 条款还没接受（api_server.rs:1128）。"""
        return self.status == 403

    @property
    def is_rate_limited(self) -> bool:
        """429：自动化限流或指纹生成配额。"""
        return self.status == 429

    @property
    def is_unauthorized(self) -> bool:
        return self.status == 401


class SyncError(RuntimeError):
    """自建 donut-sync 调用失败。"""

    def __init__(self, status: int, method: str, path: str, body: str = ""):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:300]}")

    @property
    def not_found(self) -> bool:
        return self.status == 404


class CdpError(RuntimeError):
    """CDP 命令失败（协议错误、连接断开、或引擎明确拒绝）。"""

    def __init__(self, message: str, method: Optional[str] = None, code: Optional[int] = None):
        self.message = message
        self.method = method
        self.code = code
        text = f"{method}: {message}" if method else message
        super().__init__(text)

    @property
    def is_plan_gate(self) -> bool:
        """引擎侧的付费闸门（实测原话：`… requires a paid Donut Browser plan.`）。"""
        lowered = self.message.lower()
        return "paid donut browser plan" in lowered or "requires a donut browser plan" in lowered
