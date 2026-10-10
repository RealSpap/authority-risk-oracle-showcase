#!/usr/bin/env python3
"""Two things a reader of a single score cannot see: the series of every composite score over time, rebuilt from the hash-chained
event log (every move the watch recorded, plus the current on-chain value), and the oracle's calibration: the authority actions
the watch itself observed (timelock operations queued or executed against a tracked contract, admin changes read independently)
set against the score the contract carried at that moment. If low scores never precede real actions, the score is decoration;
this file lets anyone check, with the counts as they are (small at first, growing with every run).

    python3 scripts/score_series.py --scores watch/scores --events watch/events.jsonl --pending watch/pending_ops.json --out watch/score_series.json

Output: `series` keyed <chain>:<address>, a list of {t, composite, from} oldest first (from: "push" the on-chain value and its push
time; "watch" a move the watch recorded at its run time; "first" the value the first recorded move started from, dated at that
move); `calibration`: the actions in the window, each with the score the contract had then and its band, totals per band.
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, PENDING_CHAIN, norm  # noqa: E402

BANDS = [(0, 19, "critical"), (20, 39, "weak"), (40, 59, "moderate"), (60, 79, "decent"), (80, 100, "strong")]   # the dashboard's bands


def band(s): return next(b[2] for b in BANDS if b[0] <= int(s) <= b[1])
def iso(ts): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--events", default="watch/events.jsonl"); ap.add_argument("--pending", default="watch/pending_ops.json")
    ap.add_argument("--out", default="watch/score_series.json"); ap.add_argument("--window", type=int, default=14, help="days of observed actions set against the scores"); a = ap.parse_args()
    series, label = {}, {}
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5])
        if not key: continue
        for t in json.load(open(f)).get("targets", []):
            ka = key + ":" + norm(t["target"]); series[ka] = [{"t": iso(t["lastUpdated"]), "composite": int(t["compositeScore"]), "from": "push"}] if t.get("lastUpdated") else []
    moves = {}
    if os.path.exists(a.events):
        for l in open(a.events):
            try: e = json.loads(l)
            except ValueError: continue
            if e.get("kind") != "move" or e.get("field") not in ("compositeScore", "new") or e.get("after") is None: continue
            ka = next((k for k in series if k.split(":", 1)[1] == norm(e.get("target")) and (e.get("oracle") or "").lower().startswith(k.split(":", 1)[0].replace("-", " ").split(" ")[0])), None)   # the watch names the oracle ("Ethereum L1 (Sepolia)"), the key is "ethereum-l1"
            if ka is None: continue
            moves.setdefault(ka, []).append(e)
    for ka, evs in moves.items():
        evs.sort(key=lambda e: e["run_utc"]); pts = []
        if evs[0].get("before") is not None: pts.append({"t": evs[0]["run_utc"], "composite": int(evs[0]["before"]), "from": "first"})
        pts += [{"t": e["run_utc"], "composite": int(e["after"]), "from": "watch"} for e in evs]
        cur = series[ka][-1] if series[ka] else None
        if cur and (not pts or pts[-1]["composite"] != cur["composite"] or cur["t"] > pts[-1]["t"]): pts.append(cur)
        series[ka] = sorted(pts, key=lambda p: p["t"])
    def score_at(ka, when_iso):
        pts = [p for p in series.get(ka, []) if p["t"] <= when_iso]
        return (pts[-1] if pts else (series[ka][0] if series.get(ka) else None))
    # calibration: the actions the watch observed, in the window, against tracked contracts
    now = time.time(); since = now - a.window * 86400; actions = []
    if os.path.exists(a.pending):
        for tl in json.load(open(a.pending)).get("results", []):
            ck = PENDING_CHAIN.get(tl.get("chain"), tl.get("chain"))
            for st in ("recent", "pending"):
                for op in tl.get(st, []):
                    ka = ck + ":" + norm(op.get("target")); when = op.get("executed_at") or op.get("queued_at")
                    if op.get("undecoded") or op.get("touches_governed") is False: continue   # not read, or decoded and aimed at another program or a transfer: not an authority action on the tracked program
                    if ka in series and when and int(when) >= since:
                        dk = op.get("decoded") or ""
                        actions.append({"kind": ("upgrade executed (Squads proposal)" if dk == "program upgrade" and op.get("executed_at") else ("Squads proposal " if tl.get("family") == "squads" else "timelock op ") + ("executed" if op.get("executed_at") else "queued") + ((" (%s)" % dk) if dk and tl.get("family") != "squads" else "")), "key": ka, "t": iso(when), "via": tl.get("name"), "tx": op.get("tx") or op.get("account")})
    if os.path.exists(a.events):
        for l in open(a.events):
            try: e = json.loads(l)
            except ValueError: continue
            if e.get("kind") == "upgraded" and e.get("oracle") and e.get("target"):
                ka = e["oracle"] + ":" + norm(e["target"])
                if ka in series and e["run_utc"] >= iso(since): actions.append({"kind": "upgrade executed", "key": ka, "t": e["run_utc"], "via": e.get("impl"), "tx": None})
            if e.get("kind") == "admin_change" and e.get("oracle") and e.get("target"):
                ka = e["oracle"] + ":" + norm(e["target"])
                if ka in series and e["run_utc"] >= iso(since): actions.append({"kind": "admin changed (independent read)", "key": ka, "t": e["run_utc"], "via": None, "tx": None})
    seen = set(); uniq = []
    for x in sorted(actions, key=lambda x: x["t"]):
        k = (x["kind"], x["key"], x["t"], x.get("tx"))
        if k not in seen: seen.add(k); uniq.append(x)
    by_band = {b[2]: 0 for b in BANDS}
    for x in uniq:
        p = score_at(x["key"], x["t"]); x["score_then"] = p["composite"] if p else None; x["band_then"] = band(p["composite"]) if p else None
        if p: by_band[x["band_then"]] += 1
    meth_changes = {}   # per chain key: the methodology changes the chained log recorded; points before one are not comparable with points after it
    if os.path.exists(a.events):
        for l in open(a.events):
            try: e = json.loads(l)
            except ValueError: continue
            if e.get("kind") == "methodology_changed" and e.get("chain"): meth_changes.setdefault(e["chain"], []).append({"t": e["run_utc"], "from": e.get("from"), "to": e.get("to")})
    n_moves = sum(len(v) for v in moves.values())
    out = {"run_utc": iso(now), "targets": len(series), "moves_recorded": n_moves, "series": series, "methodology_changes": meth_changes,
           "calibration": {"window_days": a.window, "actions": len(uniq), "under_40": by_band["critical"] + by_band["weak"], "by_band": by_band, "list": uniq[:200],
                           "read_as": "every authority action the watch observed in the window (a timelock operation queued or executed against a tracked contract, an admin change read independently) and the composite score the contract carried at that moment. Small counts prove little; the file grows with every run and the chained log keeps every move"},
           "what": "series: every composite score over time per tracked contract (from the on-chain value and the moves in the hash-chained events.jsonl); calibration: observed authority actions against the score at the time; written by scripts/score_series.py after every Watch run"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    print("score history: %d contract(s), %d move(s) recorded; calibration: %d action(s) in %d d, %d on contracts under 40 (%s)" % (len(series), n_moves, len(uniq), a.window, out["calibration"]["under_40"], ", ".join("%s %d" % kv for kv in by_band.items() if kv[1])))


if __name__ == "__main__":
    main()
