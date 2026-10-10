#!/usr/bin/env python3
"""Decide whether this run opens an alarm issue: a new finding opens one, a standing state is a reminder at most once a day, an unchanged one is quiet.

The Alarm step's condition stays true as long as a finding stands: 12 unreviewed second-opinion disagreements, an overdue review item.
Without a gate the job opened a new private issue on every 6-hour run for the same state, four a day (seen 10/10 before the first run).

    python3 scripts/alarm_gate.py --watch watch --run-log watch/run.log [--write]      # prints mode=new|reminder|quiet|unrecognised

The findings are the ones the condition reads: ALARM lines of the run, unreviewed second-opinion disagreements, upgrades executed, a methodology
change, an overdue review item, a HIGH alert that appeared this run. They are identified, not counted: a finding that goes away and comes
back is new again. State: watch/alarm_state.json (the findings last seen, the time of the last notice). With --write the state is updated;
the workflow passes it only when an issue can really be opened (ISSUES_TOKEN set), so that a run without the secret stays "new" and prints
the alarm in its log, as before. A first run (no state) is "new"; no finding the gate reads is "unrecognised" and never quiet. REMINDER_HOURS = 24.
"""
import argparse, calendar, json, os, sys, time

REMINDER_HOURS = 24


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001 -- a missing or unreadable file is no finding


def findings(watch, run_log):
    f = set()
    try:
        for l in open(run_log):
            if l.strip().startswith("ALARM"): f.add("alarm:" + l.strip()[:160])
    except OSError: pass
    so = load(os.path.join(watch, "second_opinion.json")) or {}
    for d in so.get("disagreements") or []: f.add("disagree:%s:%s" % (d.get("chain"), str(d.get("target")).lower()))
    for u in so.get("upgrades") or []: f.add("upgrade:" + (("%s:%s" % (u.get("chain"), str(u.get("target")).lower())) if isinstance(u, dict) else str(u)))
    for c in (load(os.path.join(watch, "methodology.json")) or {}).get("changes") or []: f.add("methodology:%s:%s" % (c.get("oracle"), str(c.get("to"))[:12]))
    for i in (load(os.path.join(watch, "review_queue.json")) or {}).get("items") or []:
        if i.get("overdue"): f.add("overdue:%s:%s:%s:%s" % (i.get("source"), i.get("chain"), str(i.get("target")).lower(), str(i.get("text"))[:60]))
    for x in (load(os.path.join(watch, "alerts.json")) or {}).get("active") or []:
        if x.get("severity") == "high" and x.get("new"): f.add("high:%s|%s|%s" % (x.get("rule"), x.get("chain"), str(x.get("target")).lower()))
    return f


def decide(found, state, now):
    seen = set((state or {}).get("findings") or []); last = (state or {}).get("notified_utc")
    if not found: return "unrecognised"   # the Alarm step only runs when its condition holds: no finding the gate knows means a cause it does not read, and that must never be silenced
    if found - seen or not state: return "new"
    age = (now - calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ"))) / 3600 if last else 1e9   # last is UTC: timegm, never mktime (an hour off in summer time, seen in audit_public.py)
    return "reminder" if age >= REMINDER_HOURS else "quiet"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--run-log", default="watch/run.log"); ap.add_argument("--write", action="store_true"); a = ap.parse_args()
    path = os.path.join(a.watch, "alarm_state.json"); state = load(path); now = time.time(); found = findings(a.watch, a.run_log)
    mode = decide(found, state, now); stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    if a.write:
        rec = {"updated_utc": stamp, "notified_utc": stamp if mode in ("new", "reminder") else (state or {}).get("notified_utc"), "mode": mode, "findings": sorted(found),
               "what": "what the Alarm step last saw and when it last opened an issue (scripts/alarm_gate.py): a finding not in this list opens a new issue, a standing state a reminder once every %d hours" % REMINDER_HOURS}
        json.dump(rec, open(path + ".tmp", "w"), indent=1); os.replace(path + ".tmp", path)
    print("alarm gate: %d finding(s), %s%s" % (len(found), mode, "" if a.write else " (state not written)"), file=sys.stderr)
    print("mode=" + mode)


if __name__ == "__main__":
    main()
