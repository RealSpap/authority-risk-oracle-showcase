#!/usr/bin/env python3
"""What share of each ecosystem's DefiLlama TVL do the tracked targets cover, and which are the biggest untracked protocols? (read-only)

Number of targets is the wrong yardstick of growth: Robinhood Chain has 63 targets because it is a long tail of small protocols, another chain can be 50%
covered with 13. This measures value instead, and lists the largest unmatched protocols per chain: a ranked backlog of candidates (each still needs an
authority trace, a scorer and tests before it is a target; nothing here adds one).

    python3 scripts/check_tvl_coverage.py                       # labels from the live scorers (slow: about 15 minutes), cached
    python3 scripts/check_tvl_coverage.py --cache data/tracked_labels_2026-09-26.json --out data/tvl_coverage_2026-09-26.json

Labels: the live scorers of each EVM ecosystem through validate_all_scorers.run_ecosystem (a scorer that fails is UNREAD, never "no labels");
Robinhood Chain from api/scores.json (its own scan takes 25 minutes). TVL from DefiLlama
/protocols, CEX proof-of-reserves excluded. The match is by name and crude (scripts/lib/tvl_coverage.py explains where it errs); read the unmatched list, not only the percentage.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import validate_all_scorers as vas  # noqa: E402
from lib.tvl_coverage import coverage  # noqa: E402

CHAIN = {"robinhood-chain": "Robinhood Chain", "ethereum-l1": "Ethereum", "arbitrum": "Arbitrum", "base": "Base", "plasma": "Plasma",
         "monad": "Monad", "tempo": "Tempo", "hyperliquid": "Hyperliquid L1", "solana": "Solana"}


def fetch_protocols():
    r = subprocess.run(["curl", "-s", "-m", "120", "-A", "Mozilla/5.0", "https://api.llama.fi/protocols"], capture_output=True, text=True)
    return json.loads(r.stdout)


def labels_for(name):
    """(labels, source) or (None, reason)."""
    if name == "robinhood-chain":
        with open(os.path.join(ROOT, "api", "scores.json")) as f:
            return [s["label"] for s in json.load(f)["scores"]], "api/scores.json (published)"
    rep = vas.run_ecosystem(name, timeout=vas._ECOSYSTEM_TIMEOUT_DEFAULTS.get(name, 900))
    if rep.get("error") or not rep.get("entries"):
        return None, rep.get("error") or "scorer returned no entries"
    return [e.get("label") or "" for e in rep["entries"]], "live scorer"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache")
    ap.add_argument("--only")
    ap.add_argument("--out")
    args = ap.parse_args()
    cache = json.load(open(args.cache)) if args.cache and os.path.exists(args.cache) else {}
    protocols = fetch_protocols()
    results = []
    for name, chain in CHAIN.items():
        if args.only and name not in args.only.split(","):
            continue
        if name in cache:
            labels, src = cache[name], "cache"
        else:
            labels, src = labels_for(name)
            if labels is not None:
                cache[name] = labels
                if args.cache:  # written after each ecosystem: a later failure must not lose a 10-minute scorer run
                    with open(args.cache, "w") as f:
                        json.dump(cache, f, indent=1)
        if labels is None:
            print(f"{chain}: UNREAD ({src})")
            results.append({"ecosystem": name, "chain": chain, "status": f"UNREAD ({src})"})
            continue
        c = coverage(protocols, chain, labels)
        results.append({"ecosystem": name, "status": "ok", "labels": len(labels), "label_source": src, **c})
        print(f"{chain}: {len(labels)} tracked labels ({src}); DefiLlama ${c['total_usd']/1e6:,.0f}M over {c['protocols']} protocols, "
              f"{c['matched_count']} matched by name = {100*c['share']:.1f}% of value")
        for n, cat, tvl in c["largest_unmatched"]:
            print(f"    untracked: {n} [{cat}] ${tvl/1e6:,.1f}M")
    if args.cache:
        with open(args.cache, "w") as f:
            json.dump(cache, f, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1, default=str)


if __name__ == "__main__":
    main()
