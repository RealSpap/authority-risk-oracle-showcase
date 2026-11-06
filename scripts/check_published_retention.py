#!/usr/bin/env python3
"""Does the published output keep the Watch's own rule? No queued operation that has been executable for more than FRESH_READY_DAYS days may be listed (lib/fresh_ops.py).
This reads two FINAL files, not the rule: watch/pending_ops.json (results[].pending and the results[].recent rows still queued) and watch/alerts.json (active[].evidence[]). A rebuilt writer or a changed constant that lets one through THERE fails here.
NOT read: the calendar (.ics), the per-target feeds, review_queue, the digest, the warning ledger: they are written from the same lists, but this check does not prove them.
A date that is present and is not a positive number (0, negative, text, boolean) counts as unreadable and fails: it is the opposite of a reading, not "no time given".

    python3 scripts/check_published_retention.py [--dir watch]        exit 0 = none listed, 1 = at least one listed (printed), 2 = a file could not be read (never a pass)
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.fresh_ops import due_at, FRESH_READY_DAYS  # noqa: E402


def _bad_due(op, now):
    """None = fine; a number = days past the limit; "unreadable" = the row names a date that is not a usable number (never a pass)."""
    if not isinstance(op, dict): return None
    due = due_at(op)
    for k in ("ready_at", "eta"):
        if k in op and op[k] is not None and (isinstance(op[k], bool) or not isinstance(op[k], (int, float)) or op[k] <= 0): return "unreadable"
    if due is None: return None
    return round((now - due) / 86400, 1) if now - due > FRESH_READY_DAYS * 86400 else None


def listed_too_long(pending_ops, alerts, now):
    bad = []
    for rec in pending_ops.get("results") or []:
        if not isinstance(rec, dict): continue
        rows = [("pending", op) for op in rec.get("pending") or []] + [("recent", op) for op in rec.get("recent") or [] if isinstance(op, dict) and op.get("still_queued")]
        for where, op in rows:
            d = _bad_due(op, now)
            if d is not None: bad.append(("pending_ops.json/" + where, rec.get("address") or rec.get("name"), op.get("id") if isinstance(op, dict) else None, d))
    for a in (alerts.get("active") or []):
        if not isinstance(a, dict): continue
        for op in a.get("evidence") or []:
            d = _bad_due(op, now)
            if d is not None: bad.append(("alerts.json/evidence", a.get("target"), a.get("title") or a.get("rule"), d))
    return bad


def counts(pending_ops, alerts):
    """How many rows were actually read: (pending, recent still queued, evidence). A check that read 0 rows prints the same verdict as one that read 500, so the numbers are printed."""
    recs = [r for r in pending_ops.get("results") or [] if isinstance(r, dict)]
    return (sum(len(r.get("pending") or []) for r in recs), sum(1 for r in recs for o in r.get("recent") or [] if isinstance(o, dict) and o.get("still_queued")),
            sum(len(x.get("evidence") or []) for x in alerts.get("active") or [] if isinstance(x, dict)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", default="watch"); a = ap.parse_args()
    try: po, al = (json.load(open(os.path.join(a.dir, f), encoding="utf-8")) for f in ("pending_ops.json", "alerts.json"))
    except Exception as e:  # noqa: BLE001 -- an unreadable file is not a pass
        print("UNREAD: %s" % str(e)[:160]); return 2
    if not isinstance(po, dict) or not isinstance(al, dict) or not isinstance(po.get("results"), list): print("UNREAD: unexpected shape"); return 2
    bad = listed_too_long(po, al, time.time())
    for b in bad: print("LISTED TOO LONG / UNREADABLE DATE: %s %s %s (%s)" % b)
    print("read: %d pending, %d recent still queued, %d evidence" % counts(po, al))   # 0 is legitimate (an empty queue); the numbers say what the verdict rests on
    print("%d operation(s) listed past the limit" % len(bad)); return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
