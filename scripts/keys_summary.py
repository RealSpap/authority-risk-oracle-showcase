#!/usr/bin/env python3
"""From the signer index that who_controls.py builds (kept out of the repository: it is a map of who can reach what), keep only
numbers and the union of the groups the ten most connected signers sit on, without any address: watch/keys_summary.json.

    python3 scripts/keys_summary.py --index "$RUNNER_TEMP/who_controls.json" --out watch/keys_summary.json
"""
import argparse, json, os, time

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--index", required=True); ap.add_argument("--out", default="watch/keys_summary.json"); a = ap.parse_args()
    if not os.path.exists(a.index):
        print("keys: no signer index this run (who_controls did not finish); the previous summary is kept"); return
    idx = json.load(open(a.index))
    rows = sorted(({"n": len(g), "e": len({x[0] for x in g}), "g": g} for g in idx.values() if len(g) > 1), key=lambda r: (-r["e"], -r["n"]))[:10]
    groups = sorted({(x[0], x[1]) for r in rows for x in r["g"]})
    _dump_json({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "signers": len(idx), "signers_on_more_than_one_group": sum(1 for g in idx.values() if len(g) > 1),
               "top10": len(rows), "top10_groups": [list(g) for g in groups], "note": "no address here on purpose: the index itself is a targeting map and is not published"}, a.out, indent=1)
    print(f"keys: {len(idx)} signers, {len(rows)} most connected, {len(groups)} groups reachable by them")

if __name__ == "__main__":
    main()
