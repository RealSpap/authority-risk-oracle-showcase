#!/usr/bin/env python3
"""Read every `ScoreUpdated` event of each EVM testnet oracle and list every
composite change, whether it was published under an unchanged
`methodologyHash`, and why it changed (a fix of our own scorer, or a real
change of the target's authority posture).

Why this exists (found 2026-09-30, `work/2026-09-30-feuille-de-route-titan.md`):
`methodologyHash` is keccak of a hand-typed label (`METHODOLOGY_VERSION` in
each push script), frozen at `-v1` on every chain but Robinhood Chain. Across
the 6 oracles read that day, 22 composite changes went out under an unchanged
hash: 17 were corrections of our own scorer, 5 were real posture changes. A
consumer reading the chain cannot tell the two apart. This script is the
off-chain half of the answer: the full dated history, each change joined with
its cause from `data/score_change_causes.json`. A change with no entry there
is printed as UNCLASSIFIED -- that is the signal to classify it, not an error.

Read-only: eth_getLogs and eth_getBlockByNumber only, no key, no transaction.
A block range no endpoint would serve is reported UNREAD, never counted as
"no events" -- the script then exits 1 (do not quote its totals). Monad and HyperEVM,
skipped unless --all, are named in the output but do not make it fail.

    python3 scripts/score_history.py              # the 6 oracles with a fast log source
    python3 scripts/score_history.py --all        # + Monad and HyperEVM (1000-block pages, slow)
    python3 scripts/score_history.py --json out.json
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from live_target_counts import ORACLES  # noqa: E402

TOPIC = "0x5a0247329a74b8a1a6ff65241c9e5db97b91c7802a8acbc2f6a9f43b57963eb7"  # ScoreUpdated(address,uint8,uint64,bytes32)
CAUSES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "score_change_causes.json")
# First oracle deployment was after this; a log search starts at the first block at or after it.
START_TS = int(datetime(2026, 9, 14, tzinfo=timezone.utc).timestamp())

# Endpoints that serve eth_getLogs over the whole range in one call (verified 2026-09-30:
# 107/55/50/52 events). Oracles not listed here are paginated on their own RPC.
TENDERLY = "https://gateway.tenderly.co/public/"
LOG_RPC = {
    "Ethereum L1 (Sepolia)": TENDERLY + "sepolia",
    "Arbitrum (Sepolia)": TENDERLY + "arbitrum-sepolia",
    "Base (Sepolia)": TENDERLY + "base-sepolia",
    "Plasma": TENDERLY + "plasma-testnet",
    "Monad": TENDERLY + "monad-testnet",
}
# ponytail: Monad (Tenderly caps at 1000 blocks) and HyperEVM (1000 + rate limit) need thousands
# of pages; opt-in with --all. Upgrade path: read the receipts of the known push transactions.
SLOW = {"Monad": 1000, "Hyperliquid (HyperEVM)": 1000}


def first_block_at(w3, ts):
    """Binary search on block timestamps (deployment-block search by getCode fails on pruned state)."""
    lo, hi = 0, w3.eth.block_number
    while lo < hi:
        mid = (lo + hi) // 2
        if w3.eth.get_block(mid)["timestamp"] >= ts:
            hi = mid
        else:
            lo = mid + 1
    return lo


def fetch_events(name, address, rpc, max_step=50_000):
    """Returns (events, unread_ranges). events: dicts sorted by (block, logIndex)."""
    w3 = Web3(Web3.HTTPProvider(LOG_RPC.get(name, rpc), request_kwargs={"timeout": 60}))
    flt = {"address": Web3.to_checksum_address(address), "topics": [TOPIC]}
    head = w3.eth.block_number
    try:
        logs, unread = w3.eth.get_logs({**flt, "fromBlock": 0, "toBlock": head}), []
    except Exception:  # noqa: BLE001 -- range refused: paginate instead
        logs, unread = [], []
        frm, step = first_block_at(Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 60})), START_TS), max_step
        while frm <= head:
            to = min(frm + step - 1, head)
            try:
                logs += w3.eth.get_logs({**flt, "fromBlock": frm, "toBlock": to})
                frm = to + 1
            except Exception as e:  # noqa: BLE001
                if step > 10:
                    step = max(10, step // 4)
                else:
                    unread.append((frm, to, f"{type(e).__name__}: {str(e)[:100]}"))
                    frm = to + 1
                time.sleep(0.3)
    events = []
    for lg in logs:
        data = bytes(lg["data"])
        events.append({
            "block": lg["blockNumber"], "logIndex": lg["logIndex"], "tx": lg["transactionHash"].hex(),
            "target": Web3.to_checksum_address(bytes(lg["topics"][1])[-20:]),
            "composite": data[31], "lastUpdated": int.from_bytes(data[32:64], "big"),
            "methodologyHash": "0x" + data[64:96].hex(),
        })
    events.sort(key=lambda e: (e["block"], e["logIndex"]))
    return events, unread


def composite_changes(events):
    """Every event whose composite differs from the previous event for the same target."""
    last, changes = {}, []
    for e in events:
        prev = last.get(e["target"])
        if prev is not None and prev["composite"] != e["composite"]:
            changes.append({"target": e["target"], "block": e["block"], "tx": e["tx"],
                            "date": datetime.fromtimestamp(e["lastUpdated"], timezone.utc).strftime("%Y-%m-%d"),
                            "from": prev["composite"], "to": e["composite"],
                            "sameHash": prev["methodologyHash"] == e["methodologyHash"]})
        last[e["target"]] = e
    return changes


def load_causes(path=CAUSES_PATH):
    with open(path) as f:
        rows = json.load(f)["changes"]
    return {(r["oracle"], r["target"].lower(), r["block"]): r for r in rows}


def classify(oracle, changes, causes):
    for c in changes:
        row = causes.get((oracle, c["target"].lower(), c["block"]))
        c["cause"] = row["cause"] if row else "UNCLASSIFIED"
        c["ref"] = row.get("ref", "") if row else ""
        c["label"] = row.get("label", "") if row else ""
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="also read Monad and HyperEVM (slow)")
    ap.add_argument("--json", help="write the full history to this path")
    args = ap.parse_args()
    causes = load_causes()
    report, incomplete, skipped = [], [], []
    for name, address, rpc in ORACLES:
        if name in SLOW and not args.all:
            print(f"\n== {name}: NOT READ (slow log source, use --all) -- not a zero")
            skipped.append(name)
            continue
        try:
            events, unread = fetch_events(name, address, rpc, SLOW.get(name, 50_000))
        except Exception as e:  # noqa: BLE001 -- reported, never dropped
            print(f"\n== {name}: UNREADABLE -- {type(e).__name__}: {str(e)[:120]}")
            incomplete.append(name)
            continue
        changes = classify(name, composite_changes(events), causes)
        hashes = sorted({e["methodologyHash"] for e in events})
        same = [c for c in changes if c["sameHash"]]
        print(f"\n== {name}: {len(events)} ScoreUpdated, {len({e['target'] for e in events})} targets, "
              f"{len(hashes)} methodologyHash, {len(changes)} composite changes, {len(same)} under an unchanged hash")
        for c in changes:
            print(f"  {c['date']} block {c['block']} {c['target']} {c['from']:>3} -> {c['to']:<3} "
                  f"{'same hash' if c['sameHash'] else 'NEW HASH '} {c['cause']:<12} {c['label']} {c['ref']}")
        for frm, to, err in unread:
            print(f"  UNREAD blocks {frm}-{to}: {err}")
        if unread:
            incomplete.append(name)
        report.append({"oracle": name, "address": address, "events": events, "changes": changes,
                       "methodologyHashes": hashes, "unread": unread})
    same = [c for r in report for c in r["changes"] if c["sameHash"]]
    tally = {k: sum(c["cause"] == k for c in same) for k in ("correction", "posture", "mixed", "UNCLASSIFIED")}
    print(f"\n{len(same)} composite changes published under an unchanged methodologyHash across "
          f"{len(report)} oracles: {tally}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    if skipped:
        print(f"Not read by default (use --all): {', '.join(skipped)} -- the totals above cover the other oracles only")
    if incomplete:
        print(f"INCOMPLETE -- could not read: {', '.join(incomplete)} (do not quote the totals above as complete)")
        sys.exit(1)


if __name__ == "__main__":
    main()
