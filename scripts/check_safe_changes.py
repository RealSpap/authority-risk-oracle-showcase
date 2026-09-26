#!/usr/bin/env python3
"""What changed on the Safes this oracle tracks in the last N days? (read-only, public RPC, no key)

Every Safe in the cross-ecosystem registry (scripts/lib/cross_ecosystem_overlap.py + signer_overlap.py, the same groups
scripts/who_controls.py indexes) emits an event when its signer set, threshold, modules, guard or singleton changes. This reads
those events for a recent window and ranks them (module or singleton change first, then owner/threshold, then guard).
It answers "what moved this week" before any score is recomputed; check_posture_drift.py answers it after.

    python3 scripts/check_safe_changes.py                       # last 30 days, every ecosystem
    python3 scripts/check_safe_changes.py --days 7 --only base,ethereum-l1 --out data/safe_changes_2026-09-26.json

Each ecosystem is checked against a CONTROL: the count of ExecutionSuccess events on the same Safes over the same window. An
ecosystem whose control returns nothing, or whose logs could not be fetched at all, is reported UNREAD, never as "no changes"
(a rate-limited or range-limited RPC otherwise looks exactly like a quiet month). Disclosed only: no score reads this.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from check_cross_ecosystem_overlap import REGISTRIES  # noqa: E402
from lib.safe_changes import TOPIC_TO_NAME, decode_event, rank  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402

# Full-history-capable free gateways (memory: reference-free-getlogs-sources); every other ecosystem uses its own public RPC.
LOG_RPC = {"ethereum-l1": "https://gateway.tenderly.co/public/mainnet", "base": "https://gateway.tenderly.co/public/base",
           "arbitrum": "https://gateway.tenderly.co/public/arbitrum"}
# Largest getLogs span a public endpoint accepts, measured 2026-09-26 (Base on Tenderly: 1,000 blocks; publicnode serves Base logs
# only near the head, 403 beyond). Pre-chunking to it avoids ~2x wasted calls from halving down; an ecosystem not listed is
# tried whole, then halved.
WINDOW = {"base": 1000, "hyperliquid": 1000}  # HyperEVM: "query exceeds max block range 1000"
# Monad's RPC answers 413 to a long address list; a smaller batch is accepted.
BATCH_BY_ECOSYSTEM = {"monad": 3}
# Seconds between calls where the public RPC rate-limits a long scan (HyperEVM answered 'rate limited' after a few hundred calls).
DELAY = {"hyperliquid": 0.25}
EXECUTION_SUCCESS = "0x" + Web3.keccak(text="ExecutionSuccess(bytes32,uint256)").hex().removeprefix("0x")
BATCH = 20
MIN_WINDOW = 1000


class LogsUnavailable(Exception):
    pass


class Budget:
    def __init__(self, calls):
        self.left = calls


def fetch_logs(w3, addresses, topics, start, end, budget, delay=0.0):
    """eth_getLogs over [start, end], halving the range when the RPC refuses it and backing off when it rate-limits. Raises
    LogsUnavailable rather than returning a short list: an unread range is never an empty one."""
    for attempt in range(4):
        if budget.left <= 0:
            raise LogsUnavailable("call budget exhausted")
        budget.left -= 1
        if delay:
            time.sleep(delay)
        try:
            return list(w3.eth.get_logs({"address": addresses, "topics": [topics], "fromBlock": start, "toBlock": end}))
        except Exception as e:  # noqa: BLE001 -- any refusal (range, rate, size) is handled below
            limited = "rate limit" in str(e).lower() or "429" in str(e) or "too many" in str(e).lower()
            if limited and attempt < 3:
                time.sleep(2 ** attempt)  # rate-limited: same range again after a pause, splitting would only add calls
                continue
            if limited or end - start + 1 <= MIN_WINDOW:
                raise LogsUnavailable(f"{type(e).__name__}: {str(e)[:100]}") from e
            mid = (start + end) // 2
            return fetch_logs(w3, addresses, topics, start, mid, budget, delay) + fetch_logs(w3, addresses, topics, mid + 1, end, budget, delay)


def block_at_or_after(w3, ts, head):
    """First block with timestamp >= ts. Starts from an estimate off the recent block time (a public RPC that prunes old
    history refuses a search from block 0), then bisects."""
    def stamp(n):
        for attempt in range(5):
            try:
                return w3.eth.get_block(n)["timestamp"]
            except Exception as e:  # noqa: BLE001 -- back off on a rate limit, re-raise anything else
                if attempt == 4 or not ("rate limit" in str(e).lower() or "429" in str(e)):
                    raise
                time.sleep(2 ** attempt)
    sample = min(5000, head)
    block_time = max((stamp(head) - stamp(head - sample)) / sample, 0.05)
    lo = max(0, head - int((stamp(head) - ts) / block_time * 1.3) - 1000)
    while lo > 0 and stamp(lo) >= ts:
        lo = max(0, lo - (head - lo) // 2 - 1000)
    hi = head
    while lo < hi:
        mid = (lo + hi) // 2
        if stamp(mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def check_ecosystem(eco, groups, days, calls):
    safes = defaultdict(list)  # safe (checksum) -> [group keys]
    for key, g in groups.items():
        for s in g.get("safes", []):
            safes[Web3.to_checksum_address(s)].append(key)
    if not safes:
        return {"ecosystem": eco, "safes": 0, "status": "no Safes in registry"}
    w3 = get_w3(LOG_RPC.get(eco, REGISTRIES[eco][0]))
    out = {"ecosystem": eco, "safes": len(safes), "events": [], "control": None, "status": "ok"}
    try:
        head = w3.eth.block_number
        start = block_at_or_after(w3, int(time.time()) - days * 86400, head)
    except Exception as e:  # noqa: BLE001 -- a pruned or unreachable RPC is UNREAD, not quiet
        out["status"] = f"UNREAD (cannot locate the window start: {type(e).__name__}: {str(e)[:100]})"
        return out
    out.update(fromBlock=start, toBlock=head)
    budget = Budget(calls)
    try:
        addrs = list(safes)
        size = BATCH_BY_ECOSYSTEM.get(eco, BATCH)
        batches = [addrs[i:i + size] for i in range(0, len(addrs), size)]
        step = WINDOW.get(eco, head - start + 1)
        spans = [(a, min(a + step - 1, head)) for a in range(start, head + 1, step)]
        control = 0
        for b in batches:  # one pass: management events and the ExecutionSuccess control together
            for lg in (lg for a, z in spans for lg in fetch_logs(w3, b, [EXECUTION_SUCCESS, *TOPIC_TO_NAME], a, z, budget, DELAY.get(eco, 0.0))):
                ev = decode_event(lg)
                if not ev:
                    control += 1
                    continue
                ev["safe"] = Web3.to_checksum_address(lg["address"])
                ev["groups"] = safes[ev["safe"]]
                ev["timestamp"] = w3.eth.get_block(ev["block"])["timestamp"]
                out["events"].append(ev)
        out["control"] = control
    except LogsUnavailable as e:
        out["status"] = f"UNREAD ({e})"
        return out
    if not out["control"]:
        out["status"] = "UNREAD (control returned 0 ExecutionSuccess events: the RPC may be truncating, not the Safes being idle)"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--only")
    ap.add_argument("--calls", type=int, default=1200, help="eth_getLogs call budget per ecosystem")
    ap.add_argument("--out")
    args = ap.parse_args()

    results = []
    for eco, (_, groups, _) in REGISTRIES.items():
        if args.only and eco not in args.only.split(","):
            continue
        r = check_ecosystem(eco, groups, args.days, args.calls)
        results.append(r)
        print(f"{eco}: {r['safes']} Safes, {r['status']}" + (f", control {r['control']} executions, {len(r['events'])} change event(s)" if r.get("control") is not None else ""))
    print()
    for r in results:
        if r.get("events"):
            print(f"=== {r['ecosystem']} ===")
            for e in rank(r["events"]):
                when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(e["timestamp"]))
                print(f"  {when}Z  {e['name']:18s} {e['value']}  safe {e['safe']} ({', '.join(e['groups'])})  tx {e['tx']}")
    unread = [r["ecosystem"] for r in results if r["status"].startswith("UNREAD")]
    if unread:
        print(f"\nUNREAD ecosystems (no conclusion drawn for them): {unread}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"days": args.days, "results": results}, f, indent=1, default=str)


if __name__ == "__main__":
    main()
