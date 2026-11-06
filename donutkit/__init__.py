"""donutkit — Donut Browser 本地 API / 自建同步 / Wayfern CDP 的统一 SDK。

三个子模块对应三块**已在本机真机验证过**的能力：

    from donutkit import DonutClient, SyncServer, Inventory, cdp

    # 1) 本地 REST API（127.0.0.1:10108）
    api = DonutClient()
    run = api.run_profile(profile_id, url="https://example.com")   # 免费计划会 402

    # 2) 自建 donut-sync 服务器（对象存储协议 + profile 清单）
    sync = SyncServer.from_env()
    Inventory(sync).publish()

    # 3) Wayfern 的 CDP（DOM / 截图 / 输入可用；Runtime.evaluate 需付费计划）
    with cdp.session(60991) as s:
        print(s.html()[:200])

每条能力的可行性都带着实测证据，见同目录的 CAPABILITIES.md 与 RUNTIME_FINDINGS.md。
"""

from .errors import CdpError, DonutError, SyncError
from .client import Donut, DonutClient, RunResult
from .sync import Inventory, SyncServer
from . import cdp

__version__ = "0.1.0"
__all__ = [
    "DonutClient",
    "Donut",
    "RunResult",
    "SyncServer",
    "Inventory",
    "cdp",
    "DonutError",
    "SyncError",
    "CdpError",
    "__version__",
]
