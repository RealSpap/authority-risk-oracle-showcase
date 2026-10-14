#!/usr/bin/env python3
"""How old is the last commit on main? GitHub disables the scheduled workflows of a public repository after 60 days without repository activity, and they run only on the default branch.

    python3 scripts/main_activity.py --out watch/main_activity.json
    python3 scripts/main_activity.py --out watch/main_activity.json --issue-repo OWNER/REPO --subject OWNER/REPO   # from day 45, one issue there (GH_TOKEN)

Since the state of the Watch moved to the watch-data branch, `main` receives no commit from the job: nobody can tell whether the commits of that branch count as activity, so the age of the last commit on main is measured and
said out loud. Under 45 days nothing happens besides the number in the file. From 45 days one issue labelled keep-schedule-alive is opened (or its title and text refreshed, never a second one; it needs a token that can write issues), and one Telegram message goes out through the
Watch's own sender (scripts/lib/alerts.py, the TELEGRAM_* secrets) at 45, 52 and 58 days, each tier once: the last tier notified is kept in the output file. When main has a recent commit again the issue gets a comment and is
closed, and the tiers start over. Read-only on the repository (git log, no secret). It never fails the run: whatever goes wrong is printed and the exit code is 0. Standard library only.
"""
import argparse, json, os, subprocess, sys, time

WARN_DAYS, DISABLE_DAYS = 45, 60
TIERS = (45, 52, 58)   # days at which the Telegram message goes out, once each
LABEL = "keep-schedule-alive"
TITLE = "Keep the schedule alive: main has had no commit for %d days"


def last_commit(repo_dir, ref):
    """Unix time of the last commit of ref, or None when it cannot be read."""
    r = subprocess.run(["git", "-C", repo_dir, "log", "-1", "--format=%ct", ref], capture_output=True, text=True)
    try: return int(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError: return None


def judge(ts, now):
    """(whole days, level): ok under 45 days, warn from 45, unknown when the commit date is missing or in the future."""
    if ts is None or ts - now > 3600: return None, "unknown"
    d = max(0, int((now - ts) // 86400))
    return d, "warn" if d >= WARN_DAYS else "ok"


def record(ts, now):
    d, level = judge(ts, now)
    return {"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "main_last_commit_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts is not None else None,
            "main_last_commit_age_days": d, "level": level, "warn_at_days": WARN_DAYS, "disabled_by_github_at_days": DISABLE_DAYS,
            "what": "age of the last commit on main: GitHub disables scheduled workflows after 60 days without repository activity; written by scripts/main_activity.py"}


def tier(days):
    """The highest tier reached (0 under 45 days or when the age is unknown)."""
    return max([x for x in TIERS if days is not None and days >= x], default=0)


def message(days):
    return "Keep the schedule alive: main has had no commit for %d days. Push any small change to main before day %d or GitHub will disable the scheduled Watch." % (days, DISABLE_DAYS)


def telegram_sender():
    """The Watch's own Telegram sender, or None when its secrets are not set. It never raises."""
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")): return None
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")); import alerts
        return alerts.send_telegram_alert
    except Exception: return None  # noqa: BLE001 -- no sender, no message; the run goes on


def previous_tier(path):
    try:
        v = json.load(open(path)).get("notified_tier")
        return v if isinstance(v, int) and not isinstance(v, bool) and v in (0,) + TIERS else 0
    except Exception: return 0  # noqa: BLE001 -- no earlier file, or one that cannot be read: nothing was notified


def notify(rec, notified, send):
    """(tier now remembered, sentence). A tier is remembered only once the message went out, so a failed send is tried again at the next run; a recent commit starts the tiers over."""
    d = rec["main_last_commit_age_days"]
    if rec["level"] == "ok": return 0, "no message needed"
    if rec["level"] != "warn": return notified, "age unknown, nothing sent"
    t = tier(d)
    if t <= notified: return notified, "message for day %d already sent" % notified
    if send is None: return notified, "no Telegram secrets, no message"
    try: ok = bool(send(message(d)))
    except Exception: ok = False  # noqa: BLE001 -- a broken sender never fails the run
    return (t, "Telegram message sent (tier %d)" % t) if ok else (notified, "Telegram message not delivered, will be tried again")


def body(days, subject):
    return ("The last commit on `main` of `%s` is %d days old. GitHub disables the scheduled workflows of a public repository after %d days without repository activity, and they run only on the default branch; "
            "the Watch is a scheduled workflow. To keep it running, push any small change to main before day %d or GitHub will disable the scheduled Watch (%d days left at the time of this text).\n\n"
            "The Watch refreshes this text on each run and closes the issue when `main` has a recent commit." % (subject, days, DISABLE_DAYS, DISABLE_DAYS, max(0, DISABLE_DAYS - days)))


def gh_cli(args):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


def sync_issue(gh, repo, rec, subject):
    """One issue, never two. gh(args) -> (returncode, stdout). Returns what was done: created / updated / closed / none."""
    rc, out = gh(["issue", "list", "--repo", repo, "--label", LABEL, "--state", "open", "--json", "number", "--limit", "20"])
    if rc != 0: raise RuntimeError("could not list the open issues of %s" % repo)
    nums = sorted(int(x["number"]) for x in json.loads(out or "[]"))
    d = rec["main_last_commit_age_days"]
    if rec["level"] == "warn":
        if nums:
            n = nums[0]; rc, _ = gh(["issue", "edit", str(n), "--repo", repo, "--title", TITLE % d, "--body", body(d, subject)])
            if rc != 0: raise RuntimeError("could not refresh issue %d" % n)
            return "updated"
        gh(["label", "create", LABEL, "--repo", repo, "--color", "FBCA04", "--description", "main has had no commit for 45 days or more: the scheduled Watch will be disabled at 60"])   # exists already: fine
        rc, _ = gh(["issue", "create", "--repo", repo, "--title", TITLE % d, "--body", body(d, subject), "--label", LABEL])
        if rc != 0: raise RuntimeError("could not open the issue in %s" % repo)
        return "created"
    if rec["level"] == "ok" and nums:
        for n in nums:
            gh(["issue", "comment", str(n), "--repo", repo, "--body", "`main` has a commit again (%d days old): closing." % d])
            gh(["issue", "close", str(n), "--repo", repo])
        return "closed"
    return "none"   # unknown age: an open issue is left as it is


def run(repo_dir, ref, out, issue_repo, subject, gh, now, send=None):
    rec = record(last_commit(repo_dir, ref), now)
    notified, said = notify(rec, previous_tier(out) if out else 0, send)
    rec["notified_tier"] = notified
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True); tmp = out + ".tmp"; json.dump(rec, open(tmp, "w"), indent=1); os.replace(tmp, out)
    d = rec["main_last_commit_age_days"]
    msg = {"ok": "main: last commit %s days ago" % d, "warn": "WARN main: last commit %s days ago, GitHub disables scheduled workflows at %d" % (d, DISABLE_DAYS), "unknown": "main: the age of the last commit is unknown"}[rec["level"]]
    action = "no issue requested"; msg += "; " + said
    if issue_repo and gh is not None:
        try: action = "issue " + sync_issue(gh, issue_repo, rec, subject or "this repository")
        except Exception as e:  # noqa: BLE001 -- never fail the run for this
            action = "issue not synced (%s)" % str(e)[:120]
    return rec, "%s; %s" % (msg, action)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-dir", default="."); ap.add_argument("--ref", default="HEAD"); ap.add_argument("--out"); ap.add_argument("--issue-repo"); ap.add_argument("--subject")
    a = ap.parse_args()
    try:
        has_token = bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        if a.issue_repo and not has_token: print("::warning::no token for the issue: only the number is written")
        rec, line = run(a.repo_dir, a.ref, a.out, a.issue_repo if has_token else None, a.subject, gh_cli, time.time(), telegram_sender())
        print(line)
    except Exception as e:  # noqa: BLE001 -- the check is advice, the Watch run must go on
        print("main_activity: %s" % str(e)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
