#!/usr/bin/env python3
"""Is the public Watch still running? A watchdog for a cron job, a launchd job or an uptime monitor.

    python3 scripts/watch_age.py                          # reads the published latest.json, prints its age
    python3 scripts/watch_age.py --max-hours 14 --json
    python3 scripts/watch_age.py --file watch/latest.json  # a local copy instead of the network

The Watch runs every 6 hours on GitHub; when the workflow stops (a disabled schedule after 60 days of inactivity, a revoked token, an Actions outage) nothing inside the repository can say so:
the files simply stop changing, and a dashboard that says "checked 11 min ago" is reading the last file there is. This reads the published `run_utc` and compares it with the clock.
Exit codes: 0 the last run is younger than --max-hours (default 14: two missed runs of slack); 1 it is older; 2 the age could NOT be established (no network, an unreadable file, a date that is
not a date, a date in the future): an unknown age is never reported as fresh. Standard library only.
"""
import argparse, calendar, json, os, sys, time, urllib.request

from watch_location import RAW  # noqa: E402  -- the state of the Watch lives on the watch-data branch

URL = RAW + "latest.json"


def parse_utc(t):
    try: return calendar.timegm(time.strptime(t, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError): return None


def judge(doc, now, max_hours):
    """(code, age in hours or None, sentence). 0 fresh, 1 stale, 2 unknown."""
    run = parse_utc((doc or {}).get("run_utc") if isinstance(doc, dict) else None)
    if run is None: return 2, None, "the published file has no readable run_utc: the age is unknown"
    age = (now - run) / 3600
    if age < -0.1: return 2, age, "the last run is dated %.1f hours in the future: the clock or the file is wrong, the age is unknown" % -age
    if age > max_hours: return 1, age, "the last run is %.1f hours old (limit %g): the Watch has stopped or is late" % (age, max_hours)
    return 0, age, "the last run is %.1f hours old (limit %g)" % (max(age, 0), max_hours)


def fetch(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "watch_age/1"}), timeout=timeout) as r: return json.loads(r.read().decode())


def main_note(status):
    """(NOTE or WARN, sentence) about the last commit on main from status.json, or None when the record carries no such field. NOTE under 45 days, WARN from 45; never changes the exit code."""
    d = status.get("main_last_commit_age_days") if isinstance(status, dict) else None
    if not isinstance(d, int) or isinstance(d, bool) or d < 0: return None
    if d >= 45: return "WARN", "main has had no commit for %d days: GitHub disables the scheduled Watch after 60 days without repository activity, push any small change to main" % d
    return "NOTE", "the last commit on main is %d days old (GitHub disables scheduled workflows after 60 days without repository activity)" % d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--url", default=URL); ap.add_argument("--file"); ap.add_argument("--max-hours", type=float, default=14); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    try: doc = json.load(open(a.file)) if a.file else fetch(a.url)
    except Exception as e:  # noqa: BLE001 -- any failure to read is "unknown", never "fresh"
        code, age, msg = 2, None, "could not read the published file (%s): the age is unknown" % str(e)[:100]
    else: code, age, msg = judge(doc, time.time(), a.max_hours)
    try: st = json.load(open(os.path.join(os.path.dirname(a.file) or ".", "status.json"))) if a.file else fetch(a.url.rsplit("/", 1)[0] + "/status.json", 10)
    except Exception: st = None  # noqa: BLE001 -- the note is advice: a missing status.json says nothing and changes nothing
    note = main_note(st)
    if a.json:
        out = {"status": {0: "fresh", 1: "stale", 2: "unknown"}[code], "age_hours": None if age is None else round(age, 2), "max_hours": a.max_hours, "message": msg}
        if note: out.update({"main_last_commit_age_days": st["main_last_commit_age_days"], "note_level": note[0], "note": note[1]})
        print(json.dumps(out))
    else:
        print(msg)
        if note: print("%s: %s" % note)
    return code


if __name__ == "__main__":
    sys.exit(main())
