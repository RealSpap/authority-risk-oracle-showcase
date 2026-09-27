#!/usr/bin/env python3
"""How many of the targets this oracle publishes sit at or below the authority configuration of a documented incident? (read-only)

Reads every published score from the deployed oracles (8 EVM testnet oracles by eth_call, the Solana devnet program by getProgramAccounts), replays each incident of
lib/incident_exposure.INCIDENTS through the shared Safe-rooted convention, and counts the published targets whose composite is at or below it. An oracle that cannot be read is
listed as UNREAD and its targets are absent from the totals, never counted as zero.

This is EXPOSURE, not prediction: see data/research_2026-09-21-authority-incidents-evidence-table.md for why the second cannot be tested.

    python3 scripts/incident_exposure.py [--out data/incident_exposure_2026-09-26.json]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import check_posture_drift as drift  # noqa: E402
import solana_oracle_reader  # noqa: E402
from lib.incident_exposure import INCIDENTS, at_or_below, replay, summarize  # noqa: E402


def read_published(oracles=None, read=None, solana_read=None):
    """([row], [unread note]); a row carries the ecosystem, the target and the six score dimensions. The three arguments are for tests."""
    oracles = drift.ORACLES if oracles is None else oracles
    read = read or drift.published_scores
    solana_read = solana_read or solana_oracle_reader.read_oracle
    rows, unread = [], []
    for name, addr, rpc in oracles:
        try:
            got = read(addr, rpc)
        except Exception as e:  # noqa: BLE001
            got = None
            unread.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if got is None:
            unread.append(f"{name}: oracle did not answer")
            continue
        unread_targets = sum(1 for v in got.values() if v is None)
        if unread_targets:
            unread.append(f"{name}: {unread_targets} target(s) unread")
        rows += [{"ecosystem": name, "target": a, **v} for a, v in got.items() if v is not None]
    try:
        for s in solana_read()["scores"]:
            rows.append({"ecosystem": "Solana (devnet)", **s})
    except Exception as e:  # noqa: BLE001
        unread.append(f"Solana: {type(e).__name__}: {e}")
    return rows, unread


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out")
    args = ap.parse_args()
    rows, unread = read_published()
    s = summarize(rows)
    print(f"{s['targets']} published targets read; median composite {s['median_composite']}; {s['no_delay']} with no timelock score; {s['lowest_band']} in the lowest band (composite <= 10)")
    per = {}
    for r in rows:
        per.setdefault(r["ecosystem"], []).append(r)
    for eco, rs in per.items():
        e = summarize(rs)
        print(f"  {eco}: {e['targets']} targets, median {e['median_composite']}, no timelock {e['no_delay']}, lowest band {e['lowest_band']}")
    print("\nIncident configuration replayed through the Safe-rooted convention, and the published targets at or below it:")
    table = []
    for label, t, n in INCIDENTS:
        r = replay(t, n)
        k = at_or_below(rows, r["compositeScore"])
        table.append({"incident": label, "threshold": t, "owners": n, **r, "targets_at_or_below": k, "of": s["targets"]})
        print(f"  {label}: composite {r['compositeScore']} (admin {r['adminKeyScore']}, multisig {r['multisigScore']}, timelock {r['timelockScore']}) -> {k} of {s['targets']} published targets at or below")
    for u in unread:
        print(f"UNREAD: {u}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"summary": s, "unread": unread, "incidents": table, "rows": rows}, f, indent=1, default=str)
    sys.exit(1 if unread or not rows else 0)  # a partial read is a failure, never a smaller clean total


if __name__ == "__main__":
    main()
