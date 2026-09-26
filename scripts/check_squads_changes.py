#!/usr/bin/env python3
"""Has any Squads v4 multisig the Solana scorers rely on changed (members, permissions, threshold, time lock, config authority)?

Reads every `*_MS = "<address>"` constant in chains/solana/scorers.py (so the watch list follows the scorers, never a copy), reads each multisig's live
state with sol_read.read_squads(), and diffs it against data/squads_snapshot.json. A multisig that is not Squads v4 (Jupiter Aggregator's is v3) or could
not be read is reported, never treated as unchanged.

    python3 scripts/check_squads_changes.py            # compare; exit 1 if anything changed or could not be read
    python3 scripts/check_squads_changes.py --update   # write the current state as the new snapshot after reviewing the changes

Why: on 2026-09-26 Jupiter Lend's program-upgrade multisig (4-of-7) removed a member at 08:41 UTC, 82 minutes after that day's re-push, so the published
multisigScore (83) stopped matching the live scorer (87). Nothing signalled it until a verifier's read-back failed. Read-only (getAccountInfo), no key.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "chains", "solana", "scripts"))
import sol_read  # noqa: E402
from lib.squads_watch import diff, multisig_constants, shape  # noqa: E402

SCORERS = os.path.join(ROOT, "chains", "solana", "scorers.py")
SNAPSHOT = os.path.join(ROOT, "data", "squads_snapshot.json")
URL = "https://api.mainnet-beta.solana.com"
SQUADS_V4_PROGRAM = "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"
SQUADS_V3_PROGRAM = "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu"


def live():
    """{address: {"names": [...], "shape": {...}} | {"names": [...], "problem": "..."}} for every multisig constant."""
    with open(SCORERS) as f:
        consts = multisig_constants(f.read())
    out = {}
    for addr, names in sorted(consts.items()):
        try:
            owner = sol_read.acct(URL, addr)["owner"]
            if owner == SQUADS_V3_PROGRAM:
                out[addr] = {"names": names, "unsupported": "Squads v3: not diffed by this tool (its state needs an authority index)"}
            elif owner != SQUADS_V4_PROGRAM:
                out[addr] = {"names": names, "problem": f"not a Squads multisig (owner {owner})"}
            else:
                out[addr] = {"names": names, "shape": shape(sol_read.read_squads(URL, addr))}
        except Exception as e:  # noqa: BLE001 -- reported, never counted as unchanged
            out[addr] = {"names": names, "problem": f"unread: {type(e).__name__}: {str(e)[:100]}"}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    now = live()
    old = {}
    if os.path.exists(SNAPSHOT):
        with open(SNAPSHOT) as f:
            old = json.load(f).get("multisigs", {})
    changed = new = problems = unsupported = 0
    for addr, cur in now.items():
        label = f"{addr} ({', '.join(cur['names'])})"
        if "unsupported" in cur:
            unsupported += 1
            print(f"  [v3, not diffed] {label}: {cur['unsupported']}")
            continue
        if "problem" in cur:
            problems += 1
            print(f"  [UNREAD] {label}: {cur['problem']}")
            continue
        prev = old.get(addr, {}).get("shape")
        if prev is None:
            new += 1
            print(f"  [NEW] {label}: {cur['shape']['threshold']}-of-{len(cur['shape']['members'])}, time lock {cur['shape']['time_lock_s']}s")
            continue
        changes = diff(prev, cur["shape"])
        if changes:
            changed += 1
            print(f"  [CHANGED] {label}: " + "; ".join(changes))
    gone = [a for a in old if a not in now]
    for a in gone:
        print(f"  [NO LONGER WATCHED] {a} ({', '.join(old[a].get('names', []))})")
    print(f"{len(now)} multisigs read, {changed} changed, {new} new, {problems} unread, {unsupported} Squads v3 not diffed" + (f", snapshot of {json.load(open(SNAPSHOT)).get('read')}" if os.path.exists(SNAPSHOT) else ", no snapshot yet"))
    if args.update:
        import time
        keep = {a: c for a, c in now.items() if "shape" in c}
        with open(SNAPSHOT, "w") as f:
            json.dump({"read": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "multisigs": {a: {"names": c["names"], "shape": c["shape"]} for a, c in keep.items()}}, f, indent=1, sort_keys=True)
        print(f"snapshot written: {len(keep)} multisigs")
    sys.exit(1 if changed or problems else 0)


if __name__ == "__main__":
    main()
