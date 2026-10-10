#!/usr/bin/env python3
"""Do the published files agree with each other? From the repository alone: no site, no network.

    python3 scripts/consistency.py                  # prints what disagrees, exit code 1 if anything does
    python3 scripts/consistency.py --watch watch --json

Every watch file is produced by its own script, from the score files (watch/scores/). A script that keys its records differently, a file left over from a contract that is no longer
tracked, or a run that stopped half-way leaves files that no longer describe the same set of contracts, and each file is valid on its own (the schemas pass, the signature holds). This
checks the invariants BETWEEN files:
  - latest.json says as many targets as the score files hold, oracle by oracle; history.jsonl's last line says the same total;
  - every contract named by tvl.json, held_assets.json, pause_state.json, side_roles.json, impl_sources.json, second_opinion.json, safe_activity.json (governed contracts), alerts.json and
    risk_by_cause.json is one of the tracked contracts (a name nobody tracks is a leftover, or a key written in another case);
  - risk_by_cause.json counts the tracked contracts, and every contract it lists under a cause is tracked.
A file that is not there is skipped and said so (an old checkout has fewer files), never counted as agreeing. Standard library only.
"""
import argparse, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, LABEL, norm  # noqa: E402


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001


def tracked_of(W):
    """({chain key:address: score-file slug}, {score-file slug: number of targets})."""
    ka, per = {}, {}
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        slug = os.path.basename(f)[:-5]; d = load(f) or {}; key = WATCH_SLUGS.get(slug) or ("solana" if d.get("kind") == "solana" else None); ts = d.get("targets") or []; per[slug] = len(ts)
        if key:
            for t in ts: ka[key + ":" + norm(t.get("target")).lower()] = slug
    return ka, per


def check(W):
    """(findings, skipped files, checks run): findings is a list of {"file", "what"}."""
    tracked, per = tracked_of(W); out, skipped, ran = [], [], 0
    def add(file, what): out.append({"file": file, "what": what})
    def names(file, keys, label="contract"):
        """Every key must be a tracked contract (compared in lower case: the files key their records so)."""
        nonlocal ran; ran += 1; bad = sorted(k for k in keys if str(k).lower() not in tracked)
        if bad: add(file, "%d %s(s) that no score file tracks, e.g. %s" % (len(bad), label, ", ".join(bad[:3])))
    if not tracked: return [{"file": "scores/", "what": "no tracked contract: nothing to compare the other files with"}], skipped, 0
    latest = load(os.path.join(W, "latest.json"))
    if latest is None: skipped.append("latest.json")
    else:
        ran += 1
        if latest.get("total_targets") != sum(per.values()): add("latest.json", "total_targets is %s, the score files hold %d" % (latest.get("total_targets"), sum(per.values())))
        for o in latest.get("oracles") or []:
            if o.get("read_ok") and o.get("slug") in per and o.get("targets") != per[o["slug"]]: add("latest.json", "oracle %s says %s targets, its score file holds %d" % (o["slug"], o.get("targets"), per[o["slug"]]))
    if len(tracked) != sum(per.values()): add("scores/", "%d distinct contracts for %d target entries: a contract is listed twice, or a chain slug is not known to the watch" % (len(tracked), sum(per.values())))
    h = None
    try: h = [json.loads(l) for l in open(os.path.join(W, "history.jsonl")) if l.strip()][-1]
    except Exception: skipped.append("history.jsonl")  # noqa: BLE001
    if h is not None:
        ran += 1
        if h.get("targets") != sum(per.values()): add("history.jsonl", "its last line says %s targets, the score files hold %d" % (h.get("targets"), sum(per.values())))
        if latest and h.get("run_utc") != latest.get("run_utc"): add("history.jsonl", "its last line is the run %s, latest.json is the run %s" % (h.get("run_utc"), latest.get("run_utc")))
    for fname, getter in (("tvl.json", lambda d: d.get("matched") or {}), ("held_assets.json", lambda d: d.get("by_target") or {}), ("pause_state.json", lambda d: d.get("by_target") or {}), ("side_roles.json", lambda d: d.get("by_target") or {}),
                          ("impl_sources.json", lambda d: d.get("by_target") or {})):
        d = load(os.path.join(W, fname))
        if d is None: skipped.append(fname); continue
        names(fname, getter(d))
    so = load(os.path.join(W, "second_opinion.json"))
    if so is None: skipped.append("second_opinion.json")
    else: names("second_opinion.json", [r["chain"] + ":" + norm(r["target"]) for r in so.get("results", []) if not r.get("oracle_self")])
    sa = load(os.path.join(W, "safe_activity.json"))
    if sa is None: skipped.append("safe_activity.json")
    else: names("safe_activity.json", {g for v in (sa.get("by_safe") or {}).values() for g in (v.get("governs") or [])}, "governed contract")
    al = load(os.path.join(W, "alerts.json"))
    if al is None: skipped.append("alerts.json")
    else:
        inv = {v: k for k, v in LABEL.items()}; keys = []
        for x in al.get("active", []):
            ck = inv.get(str(x.get("chain")).split(" (")[0]) or inv.get(x.get("chain"))
            keys.append((ck or str(x.get("chain"))) + ":" + norm(x.get("target")))
        names("alerts.json", keys, "alerting contract")
    rc = load(os.path.join(W, "risk_by_cause.json"))
    if rc is None: skipped.append("risk_by_cause.json")
    else:
        ran += 1
        if rc.get("contracts") != len(tracked): add("risk_by_cause.json", "it counts %s contracts, the score files track %d" % (rc.get("contracts"), len(tracked)))
        names("risk_by_cause.json", {t for v in (rc.get("causes") or {}).values() for t in v.get("targets") or []}, "contract listed under a cause")
    return out, skipped, ran


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    f, skipped, ran = check(a.watch)
    if a.json: print(json.dumps({"findings": f, "skipped": skipped, "checks": ran}, indent=1))
    else:
        print("consistency: %d check(s), %d disagreement(s)%s" % (ran, len(f), (", not checked (file missing): " + ", ".join(skipped)) if skipped else ""))
        for x in f: print("  %s: %s" % (x["file"], x["what"]))
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
