#!/usr/bin/env python3
"""Every score on the oracles carries the keccak256 of the methodology that produced it (methodologyHash). This writes the
registry of the hashes seen right now, watch/methodology.json: which oracles carry which hash, how many targets, whether an
oracle mixes two hashes (a push half done, or a target scored by an older method than its neighbours), and, since 2026-10-10,
whether an oracle's hash CHANGED since the previous run (watch/prev/, the scores as the previous run read them): a new
methodology changes every score at once and makes the series before it incomparable, so a change is a finding that travels
with the alarm, is appended to the hash-chained event log (kind methodology_changed) and is written to watch/methodology.md
for the alarm body. Read-only over watch/. Exit 0 always; a mix or a change is a finding, not a failure.

    python3 scripts/methodology_check.py --scores watch/scores --prev watch/prev --events watch/events.jsonl --out watch/methodology.json --md watch/methodology.md
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)


def dominant(d):
    seen = {}
    for t in d.get("targets", []):
        h = (t.get("methodologyHash") or "").lower()
        if not h or set(h[2:]) == {"0"}: h = "none"
        seen[h] = seen.get(h, 0) + 1
    return seen, (max(seen, key=seen.get) if seen else None)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--prev", default="watch/prev")
    ap.add_argument("--events", default="watch/events.jsonl"); ap.add_argument("--out", default="watch/methodology.json"); ap.add_argument("--md", default="watch/methodology.md")
    a = ap.parse_args(); now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    from evaluate_rules import WATCH_SLUGS
    hashes, mixed, changes = {}, [], []
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        try: d = json.load(open(f))
        except ValueError: continue
        slug = os.path.basename(f)[:-5]; seen, dom = dominant(d)
        for h, n in seen.items():
            hashes.setdefault(h, {"oracles": {}, "targets": 0}); hashes[h]["oracles"][slug] = n; hashes[h]["targets"] += n
        if len(seen) > 1: mixed.append({"oracle": slug, "hashes": seen})
        pf = os.path.join(a.prev, slug + ".json")
        if dom and dom != "none" and os.path.exists(pf):
            try: _, pdom = dominant(json.load(open(pf)))
            except ValueError: pdom = None
            if pdom and pdom != "none" and pdom != dom:
                changes.append({"oracle": slug, "name": d.get("name", slug), "chain": WATCH_SLUGS.get(slug), "from": pdom, "to": dom, "targets": seen[dom], "run_utc": now})
    if changes and a.events:
        from disputes import chain_append   # the same link rule as every writer of the log
        chain_append(a.events, [{"run_utc": now, "kind": "methodology_changed", "oracle": c["name"], "chain": c["chain"], "target": None, "label": None, "from": c["from"], "to": c["to"],
                                 "text": "methodology changed on %s: %s… -> %s… (%d target(s)); scores before this run are not comparable with scores after it" % (c["name"], c["from"][:10], c["to"][:10], c["targets"])} for c in changes])
    out = {"generated_utc": now, "hashes": hashes, "mixed": mixed, "changes": changes,
           "what": "methodologyHash as read on each oracle (keccak256 of the scoring code and its version, set at the push): one hash per oracle is the normal state; a mix means a push half done or a target scored by an older method; a change (against the previous run) means every score of that oracle was produced by a new method: compare across it with care, the chained log keeps the date"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    if a.md:
        if changes:
            open(a.md, "w").write("## Methodology changed, %s\n\n" % now + "".join("- **%s**: `%s` -> `%s` on %d target(s). Every score of this oracle now comes from a new method: the series before this run is not comparable with the series after it. Expected after a release of the scorer; otherwise a push by a key that should not hold the updater role.\n" % (c["name"], c["from"], c["to"], c["targets"]) for c in changes))
        elif os.path.exists(a.md): os.remove(a.md)
    print("%d methodology hash(es) over %d oracle(s), %d mixed, %d changed since the previous run" % (len(hashes), len({o for h in hashes.values() for o in h["oracles"]}), len(mixed), len(changes)))
    for m in mixed: print("  MIXED %s: %s" % (m["oracle"], m["hashes"]))
    for c in changes: print("  CHANGED %s: %s -> %s" % (c["oracle"], c["from"][:12], c["to"][:12]))


if __name__ == "__main__":
    main()
