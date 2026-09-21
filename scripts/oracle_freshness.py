#!/usr/bin/env python3
"""Read how fresh every tracked target is on every deployed testnet oracle, and say which ones
turn stale (older than `maxStaleness`, 9 days on every deployment) and when.

Why this exists: `AuthorityRiskOracle` has no removal function and `isStale()` is the only signal a
consumer gets, so an oracle nobody re-pushes silently turns "stale" for every target nine days after
its last `updateScores()`. On 2026-09-20 the Ethereum L1 index 3 (a retired Ethena minter) was left
to go stale on purpose, and Base had not been re-pushed since 2026-09-19. Run this before a judging
window or a deadline to know which oracles need a re-push and by when. Strictly read-only: plain
eth_call (and, for the native Solana program, plain `getAccountInfo` / `getProgramAccounts`, see
`solana_oracle_reader.py`), no key, no transaction. The Solana Registry carries the same 9-day
`max_staleness_seconds`.

    python3 scripts/oracle_freshness.py [--warn-hours 48]

Exit code 1 if any target is already stale or turns stale within --warn-hours, or if an oracle
could not be read (never reported as fresh by omission).
"""
import argparse
import datetime
import sys
import time

from web3 import Web3

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from live_target_counts import ORACLES  # noqa: E402
import solana_oracle_reader  # noqa: E402

FRESHNESS_ABI = [
    {"name": "trackedTargetsCount", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "trackedTargets", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
    {"name": "maxStaleness", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint64"}]},
    {"name": "getScore", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "tuple", "components": [
        {"name": "adminKeyScore", "type": "uint8"}, {"name": "multisigScore", "type": "uint8"}, {"name": "timelockScore", "type": "uint8"},
        {"name": "oracleAuthorityScore", "type": "uint8"}, {"name": "crossExposureScore", "type": "uint8"}, {"name": "compositeScore", "type": "uint8"},
        {"name": "lastUpdated", "type": "uint64"}, {"name": "methodologyHash", "type": "bytes32"}]}]},
]


def read_freshness(oracles=ORACLES, web3_cls=Web3, pause=0.0):
    """Returns [(name, info_or_None, error_or_None)] where info is
    {"count", "max_staleness", "updated": [(index, address, lastUpdated)]}. An unreadable oracle is
    reported with its error, never dropped."""
    out = []
    for name, address, rpc in oracles:
        try:
            w3 = web3_cls(web3_cls.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
            addr = web3_cls.to_checksum_address(address)
            code = w3.eth.get_code(addr)
            if not code or len(code) == 0:
                out.append((name, None, "no bytecode at oracle address"))
                continue
            c = w3.eth.contract(address=addr, abi=FRESHNESS_ABI)
            count = int(c.functions.trackedTargetsCount().call())
            max_staleness = int(c.functions.maxStaleness().call())
            updated = []
            for i in range(count):
                t = c.functions.trackedTargets(i).call()
                s = c.functions.getScore(t).call()
                updated.append((i, t, int(s[6])))
                if pause:
                    time.sleep(pause)
            out.append((name, {"count": count, "max_staleness": max_staleness, "updated": updated}, None))
        except Exception as e:  # noqa: BLE001 -- report per-oracle, keep going
            out.append((name, None, f"{type(e).__name__}: {e}"))
    return out


def read_freshness_solana(reader=solana_oracle_reader.read_oracle, name="Solana (Devnet)"):
    """Same return shape as `read_freshness()` for the native Solana program, so `summarize()` and the
    printing below need no special case. An unreadable oracle is reported with its error, never dropped."""
    try:
        o = reader()
        updated = [(i, s["target"], int(s["lastUpdated"])) for i, s in enumerate(o["scores"])]
        return [(name, {"count": len(o["tracked"]), "max_staleness": int(o["max_staleness"]), "updated": updated}, None)]
    except Exception as e:  # noqa: BLE001 -- report, keep going
        return [(name, None, f"{type(e).__name__}: {e}")]


def summarize(info, now, warn_seconds):
    """Pure: from one oracle's info and the current time, the freshness facts a person acts on."""
    ms = info["max_staleness"]
    rows = []
    for i, addr, last in info["updated"]:
        remaining = last + ms - now  # seconds until this entry turns stale (negative = already stale)
        rows.append({"index": i, "address": addr, "last_updated": last, "seconds_to_stale": remaining})
    stale = [r for r in rows if r["seconds_to_stale"] <= 0]
    soon = [r for r in rows if 0 < r["seconds_to_stale"] <= warn_seconds]
    oldest = min(rows, key=lambda r: r["last_updated"]) if rows else None
    return {"rows": rows, "stale": stale, "soon": soon, "oldest": oldest, "count": info["count"], "max_staleness": ms}


def _fmt(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _oracle_line(name, s):
    o = s["oldest"]
    if not o:
        return f"  {name:<24} {s['count']:>3} targets, nothing tracked yet"
    stale_at = _fmt(o["last_updated"] + s["max_staleness"])
    hours = o["seconds_to_stale"] / 3600
    status = f"STALE since {stale_at}" if hours <= 0 else f"turns stale in {hours:.1f} h ({stale_at})"
    return f"  {name:<24} {s['count']:>3} targets, oldest update {_fmt(o['last_updated'])}, first entry {status}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn-hours", type=float, default=48.0)
    args = ap.parse_args(argv)
    now = int(time.time())
    warn = int(args.warn_hours * 3600)
    problem = False
    for name, info, err in read_freshness(pause=0.1) + read_freshness_solana():
        if err:
            print(f"  {name:<24} UNREADABLE -- {err}")
            problem = True
            continue
        s = summarize(info, now, warn)
        print(_oracle_line(name, s))
        for r in s["stale"]:
            print(f"      already stale: index {r['index']} {r['address']}")
            problem = True
        for r in s["soon"]:
            print(f"      stale within {args.warn_hours:g} h: index {r['index']} {r['address']} ({_fmt(r['last_updated'] + s['max_staleness'])})")
            problem = True
    print("\nRe-push any oracle listed above before its first entry turns stale; a retired target is left to go stale on purpose." if problem
          else "\nEvery tracked target on every oracle is fresh beyond the warning window.")
    sys.exit(1 if problem else 0)


if __name__ == "__main__":
    main()
