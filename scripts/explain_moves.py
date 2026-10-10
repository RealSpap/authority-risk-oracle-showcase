#!/usr/bin/env python3
"""Why did a score move? Compares every target's five sub-scores with the previous run (kept in watch/prev/) and writes
watch/moves.json: one entry per target whose composite or any sub-score changed, with the axis, the old and new value and
a plain sentence. Then stores the current scores as the new previous. Read-only on the chain: it only reads the files
watch_run.py just wrote.

    python3 scripts/explain_moves.py --scores watch/scores --prev watch/prev --out watch/moves.json
"""
import argparse, glob, json, os, shutil, time

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


AXES = [("adminKeyScore", "admin key"), ("multisigScore", "multisig"), ("timelockScore", "timelock"), ("oracleAuthorityScore", "price feed"), ("crossExposureScore", "shared control")]


def norm(a):
    """An EVM address compares lowercase; a Solana program id is base58 and keeps its case."""
    a = str(a); return a.lower() if a.startswith("0x") else a

def sentence(axis, a, b):
    down = b < a
    if axis == "adminKeyScore": return "admin power moved to " + ("a smaller group or a bare key" if down else "a larger group") + " (%d → %d)" % (a, b)
    if axis == "multisigScore": return ("fewer" if down else "more") + " signatures are now required (%d → %d)" % (a, b)
    if axis == "timelockScore":
        if b == 0: return "the delay before changes apply was removed (%d → 0)" % a
        if a == 0: return "a delay before changes apply was added (0 → %d)" % b
        return "the delay before changes apply was " + ("shortened" if down else "lengthened") + " (%d → %d)" % (a, b)
    if axis == "oracleAuthorityScore": return "the price feed moved under " + ("fewer hands" if down else "more hands or a wider set") + " (%d → %d)" % (a, b)
    return ("a key is now shared with another tracked protocol" if down else "a shared key was removed") + " (%d → %d)" % (a, b)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--prev", default="watch/prev"); ap.add_argument("--out", default="watch/moves.json"); ap.add_argument("--keep", type=int, default=400)
    a = ap.parse_args()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    old = json.load(open(a.out)) if os.path.exists(a.out) else {"moves": []}
    moves, compared, first = [], 0, []
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        slug = os.path.basename(f)[:-5]; pf = os.path.join(a.prev, slug + ".json")
        cur = json.load(open(f))
        if not os.path.exists(pf): first.append(slug); continue
        prev = {norm(t["target"]): t for t in json.load(open(pf))["targets"]}
        for t in cur["targets"]:
            p = prev.get(norm(t["target"]))
            if not p: continue
            compared += 1
            changed = [(ax, int(p[ax]), int(t[ax])) for ax, _ in AXES if ax in p and ax in t and int(p[ax]) != int(t[ax])]
            if not changed and int(p["compositeScore"]) == int(t["compositeScore"]): continue
            moves.append({"run_utc": now, "oracle": slug, "target": t["target"], "composite": [int(p["compositeScore"]), int(t["compositeScore"])],
                          "methodology_changed": bool(p.get("methodologyHash") and t.get("methodologyHash") and p["methodologyHash"] != t["methodologyHash"]),   # the hash is tied to the code that pushed: when it changed with this move, part of the move may be a scorer update, not the target
                          "axes": [{"axis": ax, "label": dict(AXES)[ax], "from": x, "to": y, "why": sentence(ax, x, y)} for ax, x, y in changed],
                          "block": cur.get("block"), "lastUpdated": [p.get("lastUpdated"), t.get("lastUpdated")]})
    allm = (moves + [m for m in old.get("moves", []) if m.get("run_utc") != now])[: a.keep]
    _dump_json({"generated_utc": now, "compared": compared, "new_this_run": len(moves), "first_seen_oracles": first, "moves": allm}, a.out, indent=1)
    os.makedirs(a.prev, exist_ok=True)
    for f in glob.glob(os.path.join(a.scores, "*.json")): shutil.copy(f, os.path.join(a.prev, os.path.basename(f)))
    print(f"moves: {compared} targets compared, {len(moves)} moved this run, {len(first)} oracle(s) seen for the first time, {len(allm)} kept")

if __name__ == "__main__":
    main()
