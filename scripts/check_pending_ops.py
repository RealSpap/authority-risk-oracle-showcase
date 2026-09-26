#!/usr/bin/env python3
"""What is queued right now behind the timelocks this oracle scores? (read-only, public RPC, no key)

A timelock's delay is a promise; the queue is the fact. For each watched timelock this reads the queue events of the last N days
(default 365, the queue of an OpenZeppelin controller has no expiry), asks the contract itself whether each operation is still
pending, and lists what will become executable and when: target, function selector (named through the public signature database
when reachable), value, time left. Also lists what was queued in the last 14 days and is no longer queued (executed or cancelled), so a
change that already went through is visible too. Two families: OpenZeppelin `TimelockController` and the Compound-style `Timelock` (Uniswap, Compound).

    python3 scripts/check_pending_ops.py
    python3 scripts/check_pending_ops.py --days 90 --recent-days 30 --show-expired --out data/pending_ops_2026-09-26.json

A Compound-style entry that stayed queued past `eta + GRACE_PERIOD` can never execute (the mapping is never cleaned): those are counted as
"expired" and hidden unless --show-expired, so the list stays what can still happen.

Each timelock reports how many queue events it emitted in the window and the date of the latest one. A timelock with none in a year is
"quiet or truncated" (a public RPC that refuses a range looks the same, so a refused range is UNREAD, never "nothing queued").
Disclosed only: no score reads this. Chains: Ethereum and Arbitrum through Tenderly's public gateway (full-history getLogs).
"""
import argparse
import json
import os
import sys
import time

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from lib import code_review  # noqa: E402
from lib.pending_ops import QUEUE_TOPICS, decode_scheduled, dedupe_ops, status  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402

TENDERLY = {"ethereum": "https://gateway.tenderly.co/public/mainnet", "arbitrum": "https://gateway.tenderly.co/public/arbitrum"}
CALL_RPC = {"ethereum": "https://ethereum-rpc.publicnode.com", "arbitrum": "https://arbitrum-one-rpc.publicnode.com"}

# (name, chain, address, family). Each was probed live 2026-09-26: getMinDelay() for oz, delay() and GRACE_PERIOD() for compound.
WATCHLIST = [
    ("Uniswap Governance Timelock", "ethereum", "0x1a9C8182C09F50c8318d769245bEA52c32BE35BC", "compound"),
    ("Compound Governance Timelock", "ethereum", "0x6d903f6003cca6255D85CcA4D3B5E5146dC33925", "compound"),
    ("Ethena Timelock", "ethereum", "0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94", "oz"),
    ("Arbitrum L1 Timelock", "ethereum", "0xE6841D92B0C345144506576eC13ECf5103aC7f49", "oz"),
    ("Arbitrum L2 Core Governor Timelock", "arbitrum", "0x34d45e99f7D8c45ed05B5cA72D54bbD1fb3F98f0", "oz"),
    ("Arbitrum L2 Treasury Timelock", "arbitrum", "0xbFc1FECa8B09A5c5D3EFfE7429eBE24b9c09EF58", "oz"),
]


def _call(w3, to, sig, arg=b""):
    return w3.eth.call({"to": Web3.to_checksum_address(to), "data": Web3.keccak(text=sig)[:4] + arg})


def _b32(hexstr):
    return bytes.fromhex(hexstr.removeprefix("0x"))


def check_timelock(name, chain, address, family, days, recent_days=14):
    out = {"name": name, "chain": chain, "address": address, "family": family, "status": "ok", "queued_events": None, "latest_queued": None, "pending": [], "recent": []}
    logs_w3, calls_w3 = get_w3(TENDERLY[chain]), get_w3(CALL_RPC[chain])
    try:
        head = logs_w3.eth.block_number
        if family == "oz":
            out["delay"] = int.from_bytes(_call(calls_w3, address, "getMinDelay()"), "big")
        else:
            out["delay"] = int.from_bytes(_call(calls_w3, address, "delay()"), "big")
            out["grace"] = int.from_bytes(_call(calls_w3, address, "GRACE_PERIOD()"), "big")
        block_time = 12 if chain == "ethereum" else 0.25
        start = max(0, head - int(days * 86400 / block_time * 1.15))
        raw = logs_w3.eth.get_logs({"address": Web3.to_checksum_address(address), "topics": [QUEUE_TOPICS[family]], "fromBlock": start, "toBlock": head})
        ops = [o for o in (decode_scheduled(family, lg) for lg in raw) if o]
        out["queued_events"] = len(ops)
        now = int(time.time())
        if ops:
            out["latest_queued"] = max(logs_w3.eth.get_block(o["block"])["timestamp"] for o in ops[-3:])
        recent_from = head - int(recent_days * 86400 / block_time)
        for op in dedupe_ops(ops):
            if family == "oz":
                still = bool(int.from_bytes(_call(calls_w3, address, "isOperationPending(bytes32)", _b32(op["id"])), "big"))
                ready = int.from_bytes(_call(calls_w3, address, "getTimestamp(bytes32)", _b32(op["id"])), "big") if still else None
                grace = None
            else:
                still = bool(int.from_bytes(_call(calls_w3, address, "queuedTransactions(bytes32)", _b32(op["id"])), "big"))
                ready, grace = op["eta"], out["grace"]
            if still:
                out["pending"].append({**op, "ready_at": ready, "state": status(now, ready, grace)})
            if op["block"] >= recent_from:
                out["recent"].append({**op, "still_queued": still, "queued_at": logs_w3.eth.get_block(op["block"])["timestamp"]})
    except Exception as e:  # noqa: BLE001 -- any unread part makes the whole timelock UNREAD, never "nothing pending"
        out["status"] = f"UNREAD ({type(e).__name__}: {str(e)[:120]})"
    return out


def fmt_left(seconds):
    return f"{abs(seconds) / 3600:.1f}h {'left' if seconds > 0 else 'ago'}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--recent-days", type=int, default=14)
    ap.add_argument("--show-expired", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    results = [check_timelock(*w, args.days, args.recent_days) for w in WATCHLIST]
    selectors = {p["selector"] for r in results for p in r["pending"] + r["recent"] if p["selector"] != "0x"}
    names = code_review.resolve_names(selectors) if selectors else {}
    now = int(time.time())
    def fn_of(p):
        return (names.get(p["selector"]) or [p.get("signature") or p["selector"]])[0] if p["selector"] != "0x" else (p.get("signature") or "(no data)")

    for r in results:
        latest = time.strftime("%Y-%m-%d", time.gmtime(r["latest_queued"])) if r["latest_queued"] else "none"
        live = [p for p in r["pending"] if p["state"] != "expired"]
        expired = len(r["pending"]) - len(live)
        print(f"{r['name']} ({r['chain']}, {r['family']}, delay {r.get('delay')}s): {r['status']}; {r['queued_events']} queue event(s) in {args.days}d, latest {latest}; "
              f"{len(live)} pending" + (f", {expired} expired (can never execute)" if expired else ""))
        for p in sorted(r["pending"], key=lambda p: p["ready_at"]):
            if p["state"] == "expired" and not args.show_expired:
                continue
            print(f"    {p['state']:8s} {fmt_left(p['ready_at'] - now):>12s}  {p['target']}  {fn_of(p)}  value {p['value']}  calls {p['calls']}  id {p['id']}")
        for p in sorted(r["recent"], key=lambda p: p["queued_at"]):
            when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(p["queued_at"]))
            print(f"    queued {when}Z  {'STILL QUEUED' if p['still_queued'] else 'gone (executed or cancelled)'}  {p['target']}  {fn_of(p)}")
    unread = [r["name"] for r in results if r["status"].startswith("UNREAD")]
    if unread:
        print(f"\nUNREAD (no conclusion): {unread}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"days": args.days, "results": results}, f, indent=1, default=str)


if __name__ == "__main__":
    main()
