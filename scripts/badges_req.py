#!/usr/bin/env python3
"""A shields.io endpoint badge per target saying how many of the six requirements its setup meets (same thresholds as the
dashboard): watch/badge/<oracle-slug>/<address>-req.json.

    python3 scripts/badges_req.py --scores watch/scores --out watch/badge
"""
import argparse, glob, json, os

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)



def norm(a):
    """An EVM address compares lowercase; a Solana program id is base58 and keeps its case."""
    a = str(a); return a.lower() if a.startswith("0x") else a

# the six requirements, in the order of the page: (what it asks, the sub-score it reads, the least that meets it). The page (module-all.js reqMet / REQ) and the static pages
# (appliquer_oracle_site.py _req) carry the same thresholds; a test reads all of them and fails if one drifts.
REQUIREMENTS = [("Admin power is not a bare key", "adminKeyScore", 50), ("At least a 3-of-5 multisig", "multisigScore", 55), ("A confirmed delay before changes apply, no bypass", "timelockScore", 60),
                ("Bypass paths of the delay checked and ruled out", "timelockScore", 75), ("Price feed not under one hand", "oracleAuthorityScore", 60), ("No key shared with another tracked protocol", "crossExposureScore", 100)]


def requirements(t):
    """[(what it asks, met, sub-score name, its value, the least that meets it)]; met is None when the sub-score is not in the record (not read is neither met nor failed)."""
    return [(label, None if t.get(f) is None else t[f] >= th, f, t.get(f), th) for label, f, th in REQUIREMENTS]


def met(t): return sum(1 for _l, ok, _f, _v, _th in requirements(t) if ok)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--out", default="watch/badge"); a = ap.parse_args(); n = 0
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        slug = os.path.basename(f)[:-5]; d = os.path.join(a.out, slug); os.makedirs(d, exist_ok=True)
        for t in json.load(open(f))["targets"]:
            k = met(t); _dump_json({"schemaVersion": 1, "label": "authority requirements", "message": f"{k} of 6", "color": "3fbf8f" if k >= 5 else "dfb13a" if k >= 3 else "e05d5d"}, os.path.join(d, norm(t["target"]) + "-req.json")); n += 1
    print(f"badges: {n} requirement badges written")

if __name__ == "__main__":
    main()
