#!/usr/bin/env python3
"""Which tracked contracts will the page show WITHOUT a name? Run it after a watch run, before the site is published.

    python3 scripts/untitled.py --dashboard ../dashboard/index.html
    python3 scripts/untitled.py --dashboard path/to/index.html --json

A contract is named, in this order, by: the dashboard's written title for its (chain, registry index), the on-chain name()/symbol() in watch/names.json, the DefiLlama protocol it is matched to in
watch/tvl.json. A contract with none of the three shows as a short address, in the table, the podium, the map's tooltips and its share card. The 10/10 re-push added 11 targets (8 on Solana, 2 on
Ethereum L1, 1 on Hyperliquid): the dashboard source had titles for indices 0 to 17 on Solana, so the 8 new ones would have been nameless. Warns, never blocks (exit code 0); exit code 1 only when a file is missing.
Without --dashboard the written titles are unknown and every contract that has neither a name nor a match is listed."""
import argparse, glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from og_cards import WATCH_SLUGS, LABEL, norm, dashboard_titles  # noqa: E402


def untitled(scores_dir, names_path, tvl_path, titles):
    """[(chain label, index, address)] of the targets that no source names."""
    names = {k: v for k, v in (json.load(open(names_path)) if names_path and os.path.exists(names_path) else {}).items() if v}
    matched = (json.load(open(tvl_path)).get("matched") or {}) if tvl_path and os.path.exists(tvl_path) else {}
    out = []
    for f in sorted(glob.glob(os.path.join(scores_dir, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5])
        if not key: continue
        for i, t in enumerate(json.load(open(f)).get("targets", [])):
            addr = t["target"]; idx = t.get("index", i); ka = key + ":" + addr.lower(); m = matched.get(ka)
            if titles.get((key, idx)) or names.get(ka) or (m and m.get("scope") != "chain-total" and m.get("name")): continue
            out.append((LABEL.get(key, key), idx, norm(addr)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--names", default="watch/names.json"); ap.add_argument("--tvl", default="watch/tvl.json")
    ap.add_argument("--dashboard", default="dashboard/index.html"); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    if not os.path.isdir(a.scores): print("no scores folder at %s" % a.scores); return 1
    rows = untitled(a.scores, a.names, a.tvl, dashboard_titles(a.dashboard))
    total = sum(len(json.load(open(f)).get("targets", [])) for f in glob.glob(os.path.join(a.scores, "*.json")))
    if a.json: print(json.dumps({"targets": total, "untitled": [{"chain": c, "index": i, "target": t} for c, i, t in rows]}, indent=1)); return 0
    print("%d of %d tracked contracts have no name from any source (dashboard title, on-chain name, DefiLlama match)%s" % (len(rows), total, "" if os.path.exists(a.dashboard) else "; the dashboard file %s was not found, so its written titles are not counted" % a.dashboard))
    for c in sorted({r[0] for r in rows}): mine = [r for r in rows if r[0] == c]; print("  %-18s %2d: indices %s" % (c, len(mine), ", ".join(str(r[1]) for r in mine)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
