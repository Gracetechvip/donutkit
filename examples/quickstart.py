#!/usr/bin/env python3
"""Three short flows, each independent. Comment out what you cannot run.

    export DONUT_API_TOKEN=...          # Settings -> API in the Donut app
    python3 examples/quickstart.py

Nothing here needs a paid plan except the parts marked [paid]; those print the
engine's own refusal instead of crashing, so the script is safe on free plans.
"""
import os

from donutkit import DonutClient, DonutError, SyncServer


def flow_api() -> None:
    """Local REST API — profile / proxy management works on a free plan."""
    api = DonutClient()  # reads DONUT_API_TOKEN / DONUT_API_HOST / DONUT_API_PORT
    print("alive:", api.ping())

    for p in api.list_profiles():
        print(f"  {p['id'][:8]}…  {p['name']!r}  running={p['is_running']}  sync={p.get('sync_mode')}")

    # Create a profile bound to an existing proxy id.
    # profile = api.create_profile("demo-" + os.urandom(3).hex(), proxy_id="<proxy-id>")
    # api.set_cloud_sync(profile["id"], "Regular")   # free-plan friendly

    # [paid] Launching a browser returns 402 on a free plan.
    try:
        run = api.run_and_wait_cdp("<profile-id>", url="https://example.com")
        print("cdp:", run.cdp_http_url)
    except DonutError as exc:
        print("run refused:", exc.status, exc.message[:80])


def flow_sync() -> None:
    """Self-hosted donut-sync — inventory the objects held by the server."""
    sync = SyncServer.from_env()  # DONUT_SYNC_URL + SYNC_TOKEN
    print("health:", sync.health().get("status"), "ready:", sync.ready().get("s3"))

    from donutkit import Inventory

    inv = Inventory(sync)
    index = inv.build()
    print("profiles in index:", len(index["profiles"]), "objects:", len(index["objects"]))
    # inv.publish()                      # write the index object
    # inv.restore("~/Library/Application Support/Donut Browser", dry_run=True)


def flow_cdp() -> None:
    """Wayfern CDP — DOM reads and screenshots work without JavaScript."""
    from donutkit import cdp

    port = int(os.environ.get("CDP_PORT", "0"))
    if not port or not cdp.available(port):
        print("no CDP on port", port)
        return

    with cdp.session(port) as s:
        print("title:", s.text()[:80].replace("\n", " "))
        s.screenshot("/tmp/donutkit-shot.png")
        caps = s.capabilities()
        print("Runtime.evaluate:", caps.get("Runtime.evaluate"))


if __name__ == "__main__":
    which = os.environ.get("FLOW", "api")
    {"api": flow_api, "sync": flow_sync, "cdp": flow_cdp}[which]()
