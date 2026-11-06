"""donutkit 的命令行入口。

    python3 -m donutkit <group> <command> [...]

三组：
    api      本地 REST API（profiles / proxies / vpns / run / kill / fingerprint …）
    sync     自建 donut-sync（health / list / publish / verify / prune / restore / get）
    cdp      Wayfern 的 CDP（info / html / text / shot / caps / eval）

旧的 `donut_controller.py` 与 `sync_index.py` 保留为兼容壳，转发到这里。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional

from . import cdp as cdpmod
from .client import DonutClient
from .errors import CdpError, DonutError, SyncError
from .sync import Inventory, SyncServer, human_bytes


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


# --------------------------------------------------------------------------- api
def cmd_api(args: argparse.Namespace) -> int:
    api = DonutClient(token=args.token, port=args.port)

    if args.cmd == "ping":
        _print({"base_url": api.base_url, "alive": api.ping()})
    elif args.cmd == "list":
        _print([
            {
                "id": p["id"],
                "name": p["name"],
                "is_running": p["is_running"],
                "proxy_id": p.get("proxy_id"),
                "vpn_id": p.get("vpn_id"),
                "sync_mode": p.get("sync_mode"),
                "tags": p.get("tags"),
            }
            for p in api.list_profiles()
        ])
    elif args.cmd == "get":
        _print(api.get_profile(args.profile_id))
    elif args.cmd == "create":
        config: dict = {}
        if args.os:
            config["os"] = args.os
        profile = api.create_profile(
            args.name,
            proxy_id=args.proxy_id,
            vpn_id=args.vpn_id,
            group_id=args.group_id,
            wayfern_config=config or None,
        )
        _print({"id": profile["id"], "name": profile["name"], "version": profile["version"]})
    elif args.cmd == "delete":
        api.delete_profile(args.profile_id)
        _print({"deleted": args.profile_id})
    elif args.cmd == "fingerprint":
        _print(api.get_fingerprint(args.profile_id))
    elif args.cmd == "run":
        run = api.run_and_wait_cdp(args.profile_id, url=args.url)
        _print({
            "profile_id": run.profile_id,
            "port": run.port,
            "attached": run.attached,
            "cdp_http_url": run.cdp_http_url,
            "browser_ws_url": run.browser_ws_url,
            "page_ws_url": run.page_ws_url(),
        })
    elif args.cmd == "kill":
        api.kill_profile(args.profile_id)
        _print({"killed": args.profile_id})
    elif args.cmd == "proxies":
        _print(api.list_proxies())
    elif args.cmd == "add-proxy":
        _print(api.create_proxy(
            args.name, args.host, args.port, proxy_type=args.type,
            username=args.username, password=args.password, rotation_url=args.rotation_url,
        ))
    elif args.cmd == "rotate":
        if args.realign:
            _print(api.realign_after_rotation(args.proxy_id, args.realign))
        else:
            _print(api.rotate_proxy(args.proxy_id))
    elif args.cmd == "vpns":
        _print(api.list_vpns())
    elif args.cmd == "sync-mode":
        _print(api.set_cloud_sync(args.profile_id, args.mode))
    else:  # pragma: no cover
        raise SystemExit(f"未知命令 {args.cmd}")
    return 0


# -------------------------------------------------------------------------- sync
def cmd_sync(args: argparse.Namespace) -> int:
    server = SyncServer(server=args.server, token=args.token)
    inventory = Inventory(server, index_key=args.index_key)

    if args.cmd == "health":
        _print({"health": server.health(), "ready": server.ready()})
    elif args.cmd == "list":
        try:
            index = inventory.load()
        except SyncError as exc:
            if exc.not_found:
                print(f"没有索引（{inventory.index_key}），先跑 sync publish")
                return 1
            raise
        if args.json:
            _print(index)
        else:
            print(f"索引 {inventory.index_key}  generated_at={index.get('generated_at')}")
            print(f"{'id':38} {'name':24} {'files':>6} {'bytes':>9}")
            for p in index.get("profiles") or []:
                print(f"{p['id']:38} {(p.get('name') or '?')[:24]:24} {p['files']:>6} {human_bytes(p['bytes']):>9}")
    elif args.cmd == "objects":
        rows = server.list(args.prefix)
        if args.json:
            _print(rows)
        else:
            total = sum(int(r.get("size") or 0) for r in rows)
            print(f"{len(rows)} object(s) under {args.prefix!r}, {human_bytes(total)}")
            for r in rows[: args.limit]:
                print(f"  {human_bytes(int(r.get('size') or 0)):>9}  {r['key']}")
    elif args.cmd == "publish":
        index = inventory.publish()
        print(f"已写入 {inventory.index_key}（{len(index['profiles'])} 个 profile）")
        for p in index["profiles"]:
            print(f"  {p['id']}  {(p.get('name') or '?'):24} files={p['files']:<4} bytes={human_bytes(p['bytes'])}")
    elif args.cmd == "verify":
        result = inventory.verify()
        for problem in result["problems"]:
            print(f"  {problem}")
        print("verify: OK" if result["ok"] else f"verify: {len(result['problems'])} 处不一致")
        return 0 if result["ok"] else 2
    elif args.cmd == "prune":
        result = inventory.prune()
        print(f"prune: 保留 {result['kept']} 条，移除 {result['dropped']} 条")
    elif args.cmd == "restore":
        result = inventory.restore(
            args.root,
            only=args.only,
            force=args.force,
            dry_run=args.dry_run,
            settings_from=args.settings_from,
        )
        if result["seeded"]:
            print(f"settings 已铺到 {result['root']}/data/settings：{', '.join(result['seeded'])}")
        for pid in result["restored"]:
            print(f"  {'would' if result['dry_run'] else 'wrote'}  {pid}")
        for pid in result["skipped"]:
            print(f"  skip   {pid}（本地已有 metadata.json）")
        print(f"restore: 写入 {len(result['restored'])} 个，跳过 {len(result['skipped'])} 个")
        if result["restored"] and not result["dry_run"]:
            print(
                "\n下一步：启动那台设备的 App，让它按正常流程把文件拉下来\n"
                f"  DONUTBROWSER_DATA_ROOT={result['root']} "
                "/Applications/Donut.app/Contents/MacOS/donutbrowser"
            )
    elif args.cmd == "get":
        sys.stdout.buffer.write(server.get(args.key))
    elif args.cmd == "delete-prefix":
        if not args.yes:
            print(f"将删除 prefix={args.prefix!r} 下所有对象。加 --yes 确认。")
            return 1
        print(f"deleted {server.delete_prefix(args.prefix)} object(s)")
    else:  # pragma: no cover
        raise SystemExit(f"未知命令 {args.cmd}")
    return 0


# --------------------------------------------------------------------------- cdp
def cmd_cdp(args: argparse.Namespace) -> int:
    if args.cmd == "info":
        _print({
            "version": cdpmod.version(args.port),
            "pages": [
                {"url": t.get("url"), "title": t.get("title"), "type": t.get("type")}
                for t in cdpmod.targets(args.port)
                if t.get("type") == "page"
            ],
        })
        return 0
    with cdpmod.session(args.port, args.match) as session:
        if args.cmd == "html":
            print(session.html()[: args.chars])
        elif args.cmd == "text":
            print(session.text().strip()[: args.chars])
        elif args.cmd == "shot":
            raw = session.screenshot(args.out)
            print(f"{len(raw)} bytes → {args.out}")
        elif args.cmd == "caps":
            _print(session.capabilities())
        elif args.cmd == "eval":
            _print(session.evaluate(args.expression))
        elif args.cmd == "cookies":
            _print(session.cookies())
        else:  # pragma: no cover
            raise SystemExit(f"未知命令 {args.cmd}")
    return 0


# -------------------------------------------------------------------------- 组装
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="donutkit", description="Donut Browser 三件套 SDK 的 CLI")
    sub = parser.add_subparsers(dest="group", required=True)

    # -- api
    api = sub.add_parser("api", help="本地 REST API")
    api.add_argument("--token", default=None, help="或 DONUT_API_TOKEN")
    api.add_argument("--port", type=int, default=None)
    api_sub = api.add_subparsers(dest="cmd", required=True)
    api_sub.add_parser("ping")
    api_sub.add_parser("list")
    api_sub.add_parser("proxies")
    api_sub.add_parser("vpns")
    p = api_sub.add_parser("get"); p.add_argument("profile_id")
    p = api_sub.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--proxy-id", default=None)
    p.add_argument("--vpn-id", default=None)
    p.add_argument("--group-id", default=None)
    p.add_argument("--os", default=None, help="windows/macos/linux/android/ios")
    p = api_sub.add_parser("delete"); p.add_argument("profile_id")
    p = api_sub.add_parser("fingerprint"); p.add_argument("profile_id")
    p = api_sub.add_parser("run"); p.add_argument("profile_id"); p.add_argument("--url", default=None)
    p = api_sub.add_parser("kill"); p.add_argument("profile_id")
    p = api_sub.add_parser("add-proxy")
    p.add_argument("--name", required=True)
    p.add_argument("--type", default="socks5")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--rotation-url", default=None)
    p = api_sub.add_parser("rotate")
    p.add_argument("--proxy-id", required=True)
    p.add_argument("--realign", action="append", default=[])
    p = api_sub.add_parser("sync-mode")
    p.add_argument("--profile-id", required=True)
    p.add_argument("--mode", required=True, choices=["Disabled", "Regular", "Encrypted"])

    # -- sync
    sync = sub.add_parser("sync", help="自建 donut-sync")
    sync.add_argument("--server", default=None)
    sync.add_argument("--token", default=None)
    sync.add_argument("--index-key", default=None)
    sync_sub = sync.add_subparsers(dest="cmd", required=True)
    sync_sub.add_parser("health")
    p = sync_sub.add_parser("list"); p.add_argument("--json", action="store_true")
    p = sync_sub.add_parser("objects")
    p.add_argument("--prefix", default="")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--json", action="store_true")
    sync_sub.add_parser("publish")
    sync_sub.add_parser("verify")
    sync_sub.add_parser("prune")
    p = sync_sub.add_parser("restore")
    p.add_argument("--root", required=True)
    p.add_argument("--only", action="append", default=[])
    p.add_argument("--settings-from", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = sync_sub.add_parser("get"); p.add_argument("key")
    p = sync_sub.add_parser("delete-prefix"); p.add_argument("prefix"); p.add_argument("--yes", action="store_true")

    # -- cdp
    cdp = sub.add_parser("cdp", help="Wayfern 的 CDP")
    cdp.add_argument("--port", type=int, required=True)
    cdp.add_argument("--match", default=None, help="只挑 URL 含该子串的 page")
    cdp_sub = cdp.add_subparsers(dest="cmd", required=True)
    cdp_sub.add_parser("info")
    p = cdp_sub.add_parser("html"); p.add_argument("--chars", type=int, default=2000)
    p = cdp_sub.add_parser("text"); p.add_argument("--chars", type=int, default=2000)
    p = cdp_sub.add_parser("shot"); p.add_argument("--out", default="shot.png")
    cdp_sub.add_parser("caps")
    cdp_sub.add_parser("cookies")
    p = cdp_sub.add_parser("eval"); p.add_argument("expression")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # sync 组的默认值留给 from_env 决定
    if args.group == "sync":
        if args.server is None or args.token is None:
            from_env = SyncServer.from_env()
            args.server = args.server or from_env.server
            args.token = args.token or from_env.token
        if args.index_key is None:
            args.index_key = "_inventory/profiles.json"

    try:
        handlers = {"api": cmd_api, "sync": cmd_sync, "cdp": cmd_cdp}
        return handlers[args.group](args)
    except DonutError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        if exc.is_plan_gate:
            print("提示：402 = 该动作需要付费能力（browserAutomation / cloudBackup）。", file=sys.stderr)
        elif exc.is_terms_gate:
            print("提示：403 通常是 Wayfern 条款还没接受。", file=sys.stderr)
        elif exc.is_rate_limited:
            print("提示：429 = 自动化/生成配额，等 Retry-After。", file=sys.stderr)
        return 2
    except SyncError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except CdpError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        if exc.is_plan_gate:
            print("提示：引擎侧付费闸门，换付费计划或改用非 Runtime.evaluate 的路径。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
