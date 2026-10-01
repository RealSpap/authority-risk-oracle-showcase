#!/usr/bin/env python3
"""Read every `ScoreUpdated` event of each EVM testnet oracle and list every
composite change, whether it was published under an unchanged
`methodologyHash`, and why it changed (a fix of our own scorer, or a real
change of the target's authority posture).

Why this exists (found 2026-09-30, `work/2026-09-30-feuille-de-route-titan.md`):
`methodologyHash` is keccak of a hand-typed label (`METHODOLOGY_VERSION` in
each push script), frozen at `-v1` on every chain but Robinhood Chain. Across
the 6 oracles read that day, 22 composite changes went out under an unchanged
hash: 21 were corrections of our own scorer, 1 was mixed (a real Safe change that
also tripped a rule of ours), none a pure posture change (first classified 17/5,
corrected on 2026-10-01 after an independent review). A consumer reading the chain
cannot tell the two apart. This script is the
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
from live_target_counts import ORACLES, read_counts  # noqa: E402

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
KNOWN_UNREADABLE = {"Hyperliquid (HyperEVM)"}  # public RPC: "More than 3000 archived blocks queried in one day" (2026-10-01)


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
        pages, total = 0, head - frm + 1
        while frm <= head:
            to = min(frm + step - 1, head)
            try:
                logs += w3.eth.get_logs({**flt, "fromBlock": frm, "toBlock": to})
                frm = to + 1
                # Fixed 2026-10-01: the page size never grew back after an error, so one rate-limit on Monad left it at 10
                # blocks for good (a --all run was still going after 13 hours). It now doubles back up to max_step.
                step = min(max_step, step * 2)
                pages += 1
                if pages % 500 == 0:
                    print(f"   {name}: {100 * (frm - (head - total + 1)) / total:.0f}% read, {len(logs)} events so far", flush=True)
            except Exception as e:  # noqa: BLE001
                if "archived blocks queried" in str(e):
                    raise  # HyperEVM's daily archive quota: no page will pass today, let main() file the oracle as not read
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


API_PATH = os.path.join(os.path.dirname(__file__), "..", "api", "score_history.json")


def api_snapshot(report, skipped, failed):
    """What a consumer needs to tell our corrections from real posture changes: every composite change, dated, with its
    cause and reference, and the oracles not read. No raw events."""
    return {
        "about": "Every composite change published by the testnet oracles listed below, with its cause: correction = a fix of our own "
                 "scorer, posture = a real change of the target's authority, mixed = both in one push. Oracles in notRead were not read: "
                 "their changes are unknown, not zero. Every methodologyHash below is a hand-typed label from before 2026-09-30, which is "
                 "why corrections went out under an unchanged hash; pushes after that date carry a hash tied to the code "
                 "(scripts/lib/methodology.py).",
        "generatedAt": int(time.time()),
        "oracles": [{"oracle": r["oracle"], "address": r["address"], "events": len(r["events"]),
                     "targets": len({e["target"] for e in r["events"]}), "methodologyHashes": r["methodologyHashes"],
                     "changes": [{k: c[k] for k in ("date", "block", "tx", "target", "label", "from", "to", "sameHash", "cause", "ref")}
                                 for c in r["changes"]],
                     "unreadRanges": len(r["unread"])} for r in report],
        "notRead": sorted(set(skipped) | set(failed)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="also read Monad and HyperEVM (slow)")
    ap.add_argument("--json", help="write the full history to this path")
    ap.add_argument("--api", action="store_true", help="also write api/score_history.json, the classified changes a consumer can read")
    args = ap.parse_args()
    causes = load_causes()
    # incomplete = read with gaps, or failed without being a known-unreadable source: blocks the API file (its partial or
    # missing history would look complete). failed = a KNOWN_UNREADABLE oracle not read at all: absent from the report,
    # listed in notRead, does not block it. Split 2026-10-01: HyperEVM's public RPC refuses any archive read past a daily
    # quota, which kept every other oracle's history out of the API file; a one-off timeout elsewhere still blocks it.
    report, incomplete, skipped, failed = [], [], [], []
    tracked = {n: c for n, c, _ in read_counts([o for o in ORACLES if args.all or o[0] not in SLOW])}
    for name, address, rpc in ORACLES:
        if name in SLOW and not args.all:
            print(f"\n== {name}: NOT READ (slow log source, use --all) -- not a zero")
            skipped.append(name)
            continue
        try:
            events, unread = fetch_events(name, address, rpc, SLOW.get(name, 50_000))
        except Exception as e:  # noqa: BLE001 -- reported, never dropped
            print(f"\n== {name}: UNREADABLE -- {type(e).__name__}: {str(e)[:120]}")
            (failed if name in KNOWN_UNREADABLE else incomplete).append(name)
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
        # A log source can answer [] instead of an error past its limit: fewer targets in the events than the oracle
        # tracks means part of its history is missing (added 2026-10-01 after review).
        n_targets, n_tracked = len({e["target"] for e in events}), tracked.get(name)
        if n_tracked is None:
            print("  trackedTargetsCount() UNREAD: completeness not checked, so not published as complete")
        elif n_targets < n_tracked:
            print(f"  only {n_targets} targets in the events for {n_tracked} tracked: history INCOMPLETE")
        if unread or n_tracked is None or n_targets < n_tracked:
            incomplete.append(name)
        report.append({"oracle": name, "address": address, "events": events, "changes": changes,
                       "methodologyHashes": hashes, "unread": unread})
    same = [c for r in report for c in r["changes"] if c["sameHash"]]
    tally = {k: sum(c["cause"] == k for c in same) for k in ("correction", "posture", "mixed", "UNCLASSIFIED")}
    print(f"\n{len(same)} composite changes published under an unchanged methodologyHash across "
          f"{len(report)} oracles: {tally}")
    if args.api and incomplete:
        print(f"api/score_history.json NOT written: {', '.join(incomplete)} not fully read, the published file is kept as it was")
    elif args.api:
        with open(API_PATH, "w") as f:
            json.dump(api_snapshot(report, skipped, failed), f, indent=1)
        print(f"wrote {API_PATH}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    if skipped:
        print(f"Not read by default (use --all): {', '.join(skipped)} -- the totals above cover the other oracles only")
    if incomplete or failed:
        print(f"INCOMPLETE -- could not read: {', '.join(incomplete + failed)} (do not quote the totals above as complete)")
        sys.exit(1)


if __name__ == "__main__":
    main()
