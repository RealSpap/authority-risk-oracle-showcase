#!/usr/bin/env python3
"""Non-circular cross-check: which admin keys does DeFiScan v2 list, with value behind them, that this repository never
mentions? (read-only, public JSON, no key, no RPC)

Why: every check in this repo reads the chain through our own code, so a key our scorers never looked at stays invisible
to all of them. DeFiScan v2 (deficollective, defiscan.info) publishes, per reviewed protocol, every admin it found, its
type and the capital it can reach. Diffing that list against every address this repository mentions is a second source
we did not write. Found on its first run (2026-09-30): the third bare key of wBETH (the proxy admin of its only, unlimited
minter), since added to data/finding_2026-09-26-wbeth-and-ssv-authority.md.

For each protocol in https://defiscan.info/data/index.json, reads its compiled-review.json and classifies each admin
against the repository (scripts/, chains/, data/, src/, api/): FULL (the address appears), PREFIX (an abbreviated
"0x1234abcd..." form appears), ABSENT. It then lists the ABSENT admins that are live keys (EOA, multisig, timelock,
upgradeable or unknown contract; not DeFiScan's immutable internal contracts, revoked roles or tokens), largest reachable
value first. DeFiScan's own figures are quoted as DeFiScan's, not re-read on chain here: re-read an entry before
writing anything about it. A review can be months old (compiledAt is printed).

    python3 scripts/check_registry_diff_defiscan.py
    python3 scripts/check_registry_diff_defiscan.py --all        # also immutable/internal admins
"""
import argparse
import json
import os
import re
import sys
import urllib.request

BASE = "https://www.defiscan.info/data"  # defiscan.info answers 308, which urllib on Python 3.9 does not follow
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
CORPUS_DIRS = ("scripts", "chains", "data", "src", "api")
LIVE_TYPES = {"EOA", "EOAPermissioned", "Multisig", "Timelock", "Upgradeable", "Unknown", "Contract"}
SELF_OUTPUT = "registry_diff_defiscan"  # never count this tool's own output as "known"


def fetch(url):
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def repo_corpus(root=REPO, dirs=CORPUS_DIRS):
    """Lower-cased text of every file under the given repo dirs (build output and this tool's own output skipped)."""
    parts = []
    for d in dirs:
        for dirpath, dirnames, files in os.walk(os.path.join(root, d)):
            dirnames[:] = [x for x in dirnames if x not in ("out", "cache", "target", "node_modules", ".git")]
            for f in files:
                if SELF_OUTPUT in f:
                    continue
                p = os.path.join(dirpath, f)
                if os.path.getsize(p) < 20_000_000:
                    with open(p, errors="ignore") as fh:
                        parts.append(fh.read().lower())
    return "\n".join(parts)


def classify(address, corpus, full):
    """FULL / PREFIX / ABSENT for one admin address ("eth:0x..." or "0x...")."""
    a = address.split(":")[-1].lower()
    if a in full:
        return "FULL"
    if re.search(re.escape(a[:10]) + r"(\.\.\.|…|[^0-9a-f])", corpus):
        return "PREFIX"
    return "ABSENT"


def rows_for(review, slug, corpus, full):
    out = []
    for a in review.get("admins", []):
        out.append({"protocol": slug, "address": a["address"], "name": a.get("name"), "adminType": a.get("adminType"),
                    "reachableTokenValue": a.get("totalReachableTokenValue") or 0, "reachableCapital": a.get("totalReachableCapital") or 0,
                    "status": classify(a["address"], corpus, full)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="also list DeFiScan's immutable/internal admins, revoked roles and tokens")
    ap.add_argument("--json", help="write every row here (outside data/ is fine; a name containing 'registry_diff_defiscan' is never read back)")
    args = ap.parse_args()
    try:
        index = fetch(f"{BASE}/index.json")
    except Exception as e:  # noqa: BLE001 -- reported, never an empty registry
        raise SystemExit(f"DeFiScan index not read ({type(e).__name__}: {e}): no conclusion possible")
    corpus = repo_corpus()
    full = set(re.findall(r"0x[0-9a-f]{40}", corpus))
    rows, unread = [], []
    for p in index["protocols"]:
        try:
            review = fetch(f"{BASE}/{p['slug']}/compiled-review.json")
        except Exception as e:  # noqa: BLE001
            unread.append(f"{p['slug']} ({type(e).__name__})")
            continue
        print(f"  {p['slug']:<24} {p.get('chain', ''):<9} compiled {str(review.get('compiledAt'))[:10]}, {len(review.get('admins', []))} admins")
        rows += rows_for(review, p["slug"], corpus, full)
    counts = {s: sum(r["status"] == s for r in rows) for s in ("FULL", "PREFIX", "ABSENT")}
    print(f"\n{len(rows)} admins in {len(index['protocols']) - len(unread)} DeFiScan reviews, against {len(full)} addresses in this repo: {counts}")
    tracked = {r["protocol"] for r in rows if r["status"] != "ABSENT"}
    show = [r for r in rows if r["status"] == "ABSENT" and (args.all or r["adminType"] in LIVE_TYPES)]
    show.sort(key=lambda r: -max(r["reachableTokenValue"], r["reachableCapital"]))
    print(f"\nABSENT {'admins' if args.all else 'live keys'} (never mentioned in this repo), largest DeFiScan reachable value first"
          f" (* = a protocol this repo already covers in part):")
    for r in show:
        v = max(r["reachableTokenValue"], r["reachableCapital"])
        print(f"  {'*' if r['protocol'] in tracked else ' '} {r['protocol']:<22} {r['adminType']:<15} ${v / 1e6:10,.1f}M  {r['address']}  {str(r['name'])[:48]}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=1)
    if unread:
        print(f"\nUNREAD reviews: {', '.join(unread)} -- not counted, do not quote the totals as complete")
        sys.exit(1)


if __name__ == "__main__":
    main()
