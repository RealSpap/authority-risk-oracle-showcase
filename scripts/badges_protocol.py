#!/usr/bin/env python3
"""A shields.io endpoint badge per PROTOCOL, so a protocol can show in its own README how it stands: watch/badge/protocol/<defillama-slug>.json.

    python3 scripts/badges_protocol.py --watch watch --out watch/badge/protocol

    ![authority risk](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/badge/protocol/morpho-blue.json)

The badge says the WEAKEST tracked deployment of the protocol (the one an attacker would pick) and how many contracts that covers, with the colour bands of the per-contract badges
(watch/badge/<oracle>/<address>.json): "weakest 55/100, 4 contracts". A weakest deployment whose score is stale says so. It is the oracle's reading of who can act and how fast on a
testnet-deployed score set, not an audit and not a rating of the protocol's code. Written only when the content changes, so a run with nothing new commits nothing. A slug that is not a
plain DefiLlama slug is skipped (a file name is never built from an unchecked string).
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from find import table  # noqa: E402
from brief import protocols  # noqa: E402

SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}$")


def color(v): return "red" if v < 20 else "orange" if v < 40 else "yellow" if v < 60 else "green" if v < 80 else "brightgreen"   # the bands of watch_run.py's per-contract badges


def badge(rows):
    """The badge document of one protocol's rows, or None when none of them has a score."""
    scored = [r for r in rows if r.get("score") is not None]
    if not scored: return None
    w = min(scored, key=lambda r: (r["score"], r["chain"], r["target"]))   # ties: the same contract every run
    return {"schemaVersion": 1, "label": "authority risk", "message": "weakest %d/100%s, %d contract%s" % (w["score"], " (stale)" if w.get("stale") else "", len(rows), "" if len(rows) == 1 else "s"), "color": color(w["score"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--out", default="watch/badge/protocol"); a = ap.parse_args()
    ps = protocols(table(a.watch)); os.makedirs(a.out, exist_ok=True); written = skipped = same = 0
    for slug, p in sorted(ps.items()):
        b = badge(p["rows"])
        if not b or not SLUG.match(slug): skipped += 1; continue
        path = os.path.join(a.out, slug + ".json")
        try: old = json.load(open(path))
        except Exception: old = None  # noqa: BLE001
        if old == b: same += 1; continue
        tmp = path + ".tmp"
        with open(tmp, "w") as f: json.dump(b, f)
        os.replace(tmp, path); written += 1
    print("badges_protocol: %d protocol badge(s) written, %d unchanged, %d skipped (no score or not a plain slug)" % (written, same, skipped))


if __name__ == "__main__":
    main()
