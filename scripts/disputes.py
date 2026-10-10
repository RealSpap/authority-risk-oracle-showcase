#!/usr/bin/env python3
"""Public disputes of a score: the registry data/disputes.json (kept by hand, one entry per dispute) is checked against the
tracked set and published as watch/disputes.json; every opening and every resolution is appended to the hash-chained event log,
so a dispute cannot be opened, closed or edited away quietly. Read-only over the chain (nothing is read on-chain here).

    python3 scripts/disputes.py --registry data/disputes.json --scores watch/scores --out watch/disputes.json --events watch/events.jsonl

An entry: id, chain (watch key), target, opened, issue, claim, status (open | upheld | revised | withdrawn), and for a resolved
one resolved and resolution. An entry that names a contract the oracles do not track, or lacks a field, is listed under
`invalid` with the reason and never counted. Exit 0 always: a bad entry is a published finding, not a failed run.
"""
import argparse, glob, hashlib, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, norm  # noqa: E402  -- the same slug -> chain-key map the rules use

STATES = ("open", "upheld", "revised", "withdrawn")
FIELDS = ("id", "chain", "target", "opened", "issue", "claim", "status")


def scrub(t):
    """A chained line is never rewritten, so a free text (claim, resolution) enters it with every address already shortened: a maintainer
    who quotes a signer in a resolution must not put it in the public log by accident. The tracked target stays whole in its own field."""
    return re.sub(r"0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}", lambda m: m.group(0)[:6] + "\u2026" + m.group(0)[-4:], str(t))


def chain_append(path, records):
    """Append records to the hash-chained log with the same link rule as the watch (seq, prev = sha256 of the previous line)."""
    last, seq = "", 0
    if os.path.exists(path):
        for l in open(path):
            if l.strip(): last, seq = l.rstrip("\n"), seq + 1
        if last and not open(path, "rb").read().endswith(b"\n"): open(path, "a").write("\n")
    prev = hashlib.sha256(last.encode()).hexdigest() if last else ""
    with open(path, "a") as f:
        for r in records:
            seq += 1; line = json.dumps({**r, "seq": seq, "prev": prev}); f.write(line + "\n"); prev = hashlib.sha256(line.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="data/disputes.json"); ap.add_argument("--scores", default="watch/scores")
    ap.add_argument("--out", default="watch/disputes.json"); ap.add_argument("--events", default="watch/events.jsonl"); a = ap.parse_args()
    reg = json.load(open(a.registry)) if os.path.exists(a.registry) else {"disputes": []}
    tracked = {}
    for f in glob.glob(os.path.join(a.scores, "*.json")):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5])
        if key:
            for t in json.load(open(f)).get("targets", []): tracked[key + ":" + norm(t["target"])] = t
    prev = json.load(open(a.out)) if os.path.exists(a.out) else {}
    prev_state = {d["id"]: d["status"] for d in prev.get("disputes", [])}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); valid, invalid, events = [], [], []
    for d in reg.get("disputes", []):
        missing = [k for k in FIELDS if not d.get(k)]
        why = ("missing " + ", ".join(missing)) if missing else ("unknown status " + str(d.get("status"))) if d.get("status") not in STATES else \
              ("not a tracked contract: " + str(d.get("chain")) + ":" + str(d.get("target"))) if (str(d.get("chain")) + ":" + norm(d.get("target"))) not in tracked else \
              ("resolved without resolved/resolution") if d["status"] != "open" and not (d.get("resolved") and d.get("resolution")) else None
        if why: invalid.append({"id": d.get("id"), "why": why}); continue
        ka = d["chain"] + ":" + norm(d["target"]); t = tracked[ka]
        rec = {k: d.get(k) for k in FIELDS + ("resolved", "resolution")}; rec["key"] = ka; rec["score_now"] = t.get("compositeScore")
        valid.append(rec)
        label = "%s %s" % (d["chain"], d["target"][:10])
        if d["id"] not in prev_state:
            events.append({"run_utc": now, "kind": "dispute_opened", "oracle": d["chain"], "target": d["target"], "label": None, "dispute": d["id"],
                           "text": "dispute %s opened on %s (score %s): %s" % (d["id"], label, t.get("compositeScore"), scrub(d["claim"])[:200])})
            if d["status"] != "open":   # an entry that arrives already resolved: both links, in order
                events.append({"run_utc": now, "kind": "dispute_resolved", "oracle": d["chain"], "target": d["target"], "label": None, "dispute": d["id"],
                               "text": "dispute %s %s on %s: %s" % (d["id"], d["status"], label, scrub(d["resolution"])[:200])})
        elif prev_state[d["id"]] != d["status"]:
            events.append({"run_utc": now, "kind": "dispute_resolved" if d["status"] != "open" else "dispute_reopened", "oracle": d["chain"], "target": d["target"], "label": None, "dispute": d["id"],
                           "text": "dispute %s %s on %s: %s" % (d["id"], d["status"], label, scrub(d.get("resolution") or d.get("claim"))[:200])})
    if events: chain_append(a.events, events)
    by_target = {}
    for d in valid: by_target.setdefault(d["key"], []).append({k: d[k] for k in ("id", "status", "opened", "resolved", "issue")})
    out = {"run_utc": now, "open": sum(d["status"] == "open" for d in valid), "resolved": sum(d["status"] != "open" for d in valid), "disputes": valid, "by_target": by_target, "invalid": invalid,
           "what": "public disputes of a published score, from data/disputes.json checked against the tracked set; each opening and resolution is a line of the hash-chained events.jsonl (kinds dispute_opened, dispute_resolved, dispute_reopened); by_target is keyed <chain>:<address>"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    print("disputes: %d open, %d resolved, %d invalid, %d event(s) appended to the chain" % (out["open"], out["resolved"], len(invalid), len(events)))
    for x in invalid: print("  INVALID %s: %s" % (x["id"], x["why"]))


if __name__ == "__main__":
    main()
