#!/usr/bin/env python3
"""Check the hash chain of watch/events.jsonl: from the first chained line on, every line's `prev` must equal the sha256 of the
previous line's exact text, and `seq` must grow by one. Anyone can run it on the published file; the dashboard does the same
in the browser. Exit 0 when the chain holds, 1 when a link is broken (the first broken line is named), 2 when the file is missing.

    python3 scripts/verify_chain.py [--events watch/events.jsonl] [--json watch/chain.json]
"""
import argparse, hashlib, json, os, sys


def check(path):
    if not os.path.exists(path):
        return {"ok": False, "reason": "no events file", "lines": 0, "chained": 0, "unchained": 0}
    lines = [l.rstrip("\n") for l in open(path) if l.strip()]
    unchained = chained = 0
    prev_text, prev_seq, first_chained, last_utc = None, None, None, None
    for i, text in enumerate(lines, 1):
        try: e = json.loads(text)
        except ValueError: e = {}   # not JSON: a line from before the chain is kept (its text is still what the next link commits to); after the chain started it is a line somebody inserted
        if "prev" not in e:
            if chained:   # a legacy line after the chain started is a line somebody inserted
                return {"ok": False, "reason": "line %d has no link but comes after chained lines" % i, "lines": len(lines), "chained": chained, "unchained": unchained}
            unchained += 1; prev_text = text; continue
        expect = hashlib.sha256(prev_text.encode()).hexdigest() if prev_text is not None else ""   # the first chained line commits to the last line before the chain, when there is one
        if e["prev"] != expect:
            return {"ok": False, "reason": "line %d (seq %s): prev does not match the previous line" % (i, e.get("seq")), "lines": len(lines), "chained": chained, "unchained": unchained}
        if prev_seq is not None and e.get("seq") != prev_seq + 1:
            return {"ok": False, "reason": "line %d: seq %s after %s" % (i, e.get("seq"), prev_seq), "lines": len(lines), "chained": chained, "unchained": unchained}
        if first_chained is None: first_chained = e.get("run_utc")
        chained += 1; prev_seq = e.get("seq"); prev_text = text; last_utc = e.get("run_utc")
    return {"ok": True, "lines": len(lines), "chained": chained, "unchained": unchained, "first_chained_utc": first_chained, "last_utc": last_utc,
            "head": hashlib.sha256(prev_text.encode()).hexdigest() if prev_text is not None else None}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--events", default="watch/events.jsonl"); ap.add_argument("--json", default=None)
    a = ap.parse_args()
    r = check(a.events)
    r["what"] = "sha256 chain over watch/events.jsonl: prev = sha256(previous line), seq += 1; verified at every run and by the dashboard"
    if a.json:
        tmp = a.json + ".tmp"; json.dump(r, open(tmp, "w"), indent=1); os.replace(tmp, a.json)
    print(("chain intact: %d chained line(s), %d before the chain, head %s" % (r["chained"], r["unchained"], (r.get("head") or "")[:16])) if r["ok"] else "CHAIN BROKEN: " + r["reason"])
    sys.exit(0 if r["ok"] else (2 if r.get("reason") == "no events file" else 1))


if __name__ == "__main__":
    main()
