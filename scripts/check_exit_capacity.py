#!/usr/bin/env python3
"""A vault's timelock next to its actual exit capacity -- for the 9 Morpho V1 vaults this oracle tracks.
See scripts/lib/exit_capacity.py's own docstring for why and its precedent (l1CappedComposite). Live read
from Morpho's public API (an indexer, not trusted for values -- a sizing at one instant, not a forecast;
liquidity moves with utilisation). Nothing is sent, no key.

    python3 scripts/check_exit_capacity.py

Exit status 1 if any tracked vault's API row could not be read this run, 0 otherwise.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
sys.path.insert(0, os.path.dirname(__file__))
from lib.controller_concentration import MORPHO_API, TRACKED_MORPHO_VAULTS  # noqa: E402
from lib.exit_capacity import DAY, exit_band, exit_share, is_thin_behind_a_short_delay, timelock_bucket  # noqa: E402


def fetch_rows(vaults):
    """{(ecosystem, label): {tvl, liq, inkind, timelock_seconds} or None} -- best-effort live read by
    vault address. A vault this API does not return (delisted, or a genuine API hiccup) is None, not 0.0
    -- an unread row must never look like a 0% exit-capacity finding."""
    addrs = [v[3] for v in vaults]
    query = (
        "{ vaults(first: 50, where: { address_in: %s }) { items { address state { totalAssetsUsd timelock } liquidity { usd } } } "
        "vaultV2s(first: 50, where: { address_in: %s }) { items { address totalAssetsUsd liquidityUsd forceDeallocatableLiquidityUsd timelocks { functionName duration } } } }"
    ) % (json.dumps(addrs), json.dumps(addrs))
    try:
        req = urllib.request.Request(MORPHO_API, data=json.dumps({"query": query}).encode(), headers={"content-type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=30))["data"]
    except Exception as e:
        print(f"  [WARN] Morpho API unreachable this run ({type(e).__name__}: {e}) -- every row below is unread")
        data = {"vaults": {"items": []}, "vaultV2s": {"items": []}}

    by_addr = {}
    for v in data.get("vaults", {}).get("items", []):
        s = v.get("state") or {}
        by_addr[v["address"].lower()] = {
            "tvl": s.get("totalAssetsUsd") or 0.0, "liq": (v.get("liquidity") or {}).get("usd") or 0.0,
            "inkind": 0.0, "timelock": s.get("timelock"),
        }
    for v in data.get("vaultV2s", {}).get("items", []):
        tl = {t["functionName"]: t["duration"] for t in (v.get("timelocks") or [])}
        by_addr[v["address"].lower()] = {
            "tvl": v.get("totalAssetsUsd") or 0.0, "liq": v.get("liquidityUsd") or 0.0,
            "inkind": v.get("forceDeallocatableLiquidityUsd") or 0.0, "timelock": tl.get("addAdapter"),
        }

    out = {}
    for eco, _rpc, label, vault, _roles in vaults:
        out[(eco, label)] = by_addr.get(vault.lower())
    return out


def main():
    rows = fetch_rows(TRACKED_MORPHO_VAULTS)
    unread = [k for k, v in rows.items() if v is None]

    total_tvl = sum(r["tvl"] for r in rows.values() if r)
    print(f"{len(TRACKED_MORPHO_VAULTS)} tracked Morpho V1 vaults, ${total_tvl/1e6:.1f}M total TVL (Morpho API, live)\n")

    thin = []
    for (eco, label), r in sorted(rows.items(), key=lambda kv: -(kv[1]["tvl"] if kv[1] else 0)):
        if r is None:
            print(f"  [UNREAD] {eco}/{label}")
            continue
        share = exit_share(r["tvl"], r["liq"], r["inkind"])
        band = exit_band(share)
        tl_label = timelock_bucket(r["timelock"])
        flag = ""
        if is_thin_behind_a_short_delay(r["timelock"], share):
            flag = "  <-- timelock <=3d AND exit capacity <20%: the delay's real protection window is shorter than its own duration"
            thin.append((eco, label, r["tvl"], share))
        share_pct = "?" if share is None else f"{100*share:.1f}%"
        print(f"  {eco:12s} {label:55s} ${r['tvl']/1e6:8.1f}M  exit {share_pct:>6s} ({band:6s})  timelock {tl_label}{flag}")

    print(f"\n-> {len(thin)} of {len(TRACKED_MORPHO_VAULTS)} tracked vaults sit behind a timelock of ~3 days or less with exit capacity under 20% of deposits")
    for eco, label, tvl, share in thin:
        print(f"     {eco}/{label}: ${tvl/1e6:.1f}M, exit {100*share:.1f}%")

    if unread:
        print(f"\n[INCOMPLETE] {len(unread)} vault(s) could not be read this run: {unread} -- re-run before trusting the totals")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
