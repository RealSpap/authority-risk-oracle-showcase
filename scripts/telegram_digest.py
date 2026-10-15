#!/usr/bin/env python3
"""A weekly summary for the public Telegram channel, built only from the files the watch publishes (12/10/2026).

    python3 scripts/telegram_digest.py --watch watch --dry-run      # print the message, send nothing
    python3 scripts/telegram_digest.py --watch watch                # send it (needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

Why: the channel only speaks when an alarm fires, so a quiet week looks like a dead channel. This says what the watch did, honestly: how many
oracles and contracts were read, what the signed event log recorded in the last 7 days (counted by kind, a re-scoring after a method change is not
a move of a contract and is said apart), and the alerts that are active right now with their rule. Nothing is invented: a number the files do not
give is left out, never written as 0. Exit 0 sent or printed; 1 the message could not be built; 3 not configured (nothing is sent, not an error).
Standard library only; the message stays under Telegram's 4096-character limit.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

PAGE = "https://realspap.github.io/oracle/"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError): return None


def read_events(path, since):
    """Events of the signed log newer than `since` (an ISO string compared as text: the log writes UTC ISO times). None when the log is unreadable."""
    try:
        with open(path, encoding="utf-8") as f: lines = [l for l in f if l.strip()]
    except OSError: return None
    out = []
    for l in lines:
        try: e = json.loads(l)
        except ValueError: continue
        if str(e.get("run_utc", "")) >= since: out.append(e)
    return out


def build(watch, now=None):
    """The message text, or None when the status file cannot be read (nothing is guessed)."""
    st = read_json(os.path.join(watch, "status.json"))
    if not isinstance(st, dict) or "checks" not in st: return None
    now = now if now is not None else time.time(); since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 7 * 86400)); day = time.strftime("%Y-%m-%d", time.gmtime(now))
    c = st["checks"]; lines = ["Weekly summary, %s (UTC)" % day, ""]
    if c.get("oracles") is not None and c.get("targets") is not None:
        read = c.get("oracles_read"); lines.append("The watch read %s of %s oracles and tracks %s contracts%s." % (read if read is not None else "?", c["oracles"], c["targets"], ", %s stale" % c["stale"] if c.get("stale") else ""))
    ev = read_events(os.path.join(watch, "events.jsonl"), since)
    if ev is None: lines.append("The event log could not be read: no count this week.")
    else:
        names = {"move": ("sub-score move", "sub-score moves"), "methodology_changed": ("method change", "method changes"), "alarm": ("alarm", "alarms"), "admin_change": ("admin change", "admin changes"), "upgraded": ("upgrade", "upgrades")}
        kinds = {}
        for e in ev: kinds[e.get("kind", "other")] = kinds.get(e.get("kind", "other"), 0) + 1
        label = lambda k, n: "%d %s" % (n, names.get(k, (k, k))[0 if n == 1 else 1])
        if not ev: lines.append("The signed event log recorded nothing new in the last 7 days: no score move, no alarm, no admin change.")
        else:
            lines.append("The signed event log recorded %d event%s in the last 7 days: %s." % (len(ev), "" if len(ev) == 1 else "s", ", ".join(label(k, n) for k, n in sorted(kinds.items(), key=lambda x: -x[1]))))
            if kinds.get("methodology_changed"): lines.append("A method change re-scores contracts: those sub-score moves are the formula changing, not the contracts.")
    wl = (read_json(os.path.join(watch, "warning_ledger.json")) or {}).get("summary")
    if isinstance(wl, dict) and (wl.get("warned") or wl.get("missed") or wl.get("seen_without_notice")):          # the misses are said next to the warnings, or the line is an advertisement
        lines.append("Warning ledger since %s: %d queued change(s) seen with real notice%s, %d seen already executable, %d went through between two runs." % (str(wl.get("since_utc"))[:10], wl.get("warned", 0), (" (median %s h)" % wl["median_notice_hours"]) if wl.get("median_notice_hours") is not None else "", wl.get("seen_without_notice", 0), wl.get("missed", 0)))
    al = read_json(os.path.join(watch, "alerts.json")); act = (al or {}).get("active") if isinstance(al, dict) else None
    if not isinstance(act, list): lines += ["", "The alerts file could not be read: no alert count this week (not the same as no alert)."]
    if isinstance(act, list):
        groups = {}
        for x in act: groups.setdefault((x.get("severity"), str(x.get("rule"))[:110]), []).append(str(x.get("chain")))
        hi = sum(1 for x in act if x.get("severity") == "high"); me = sum(1 for x in act if x.get("severity") == "medium")
        lines += ["", "Alerts active now: %d high, %d medium." % (hi, me)]
        order = sorted(groups.items(), key=lambda kv: (0 if kv[0][0] == "high" else 1, -len(kv[1])))
        for (sev, rule), chains in order[:5]: lines.append("- %s x%d (%s): %s" % (str(sev).upper(), len(chains), ", ".join(sorted(set(chains))), rule))
        if len(order) > 5: lines.append("... and %d more kinds of alert on the dashboard." % (len(order) - 5))
    lines += ["", "An alert means take a closer look, not that funds are at risk. Every alert, with its evidence: " + PAGE]
    return "\n".join(lines)[:4000]


def build_daily(watch, now=None):
    """One message a day for the public channel (prepared 12/10, used only when the repository variable TELEGRAM_MODE is "daily"): what moved in the last 24 hours, counted by kind, and how many alerts are active by severity.
    No protocol, no contract, no detail: the per-protocol detail is the offer behind the waitlist. None when the status file cannot be read."""
    st = read_json(os.path.join(watch, "status.json"))
    if not isinstance(st, dict) or "checks" not in st: return None
    now = now if now is not None else time.time(); since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 86400)); day = time.strftime("%Y-%m-%d", time.gmtime(now)); lines = ["Daily summary, %s (UTC)" % day, ""]
    ev = read_events(os.path.join(watch, "events.jsonl"), since)
    if ev is None: lines.append("The event log could not be read: no count today.")
    else:
        kinds = {}
        for e in ev: kinds[e.get("kind", "other")] = kinds.get(e.get("kind", "other"), 0) + 1
        names = {"move": "sub-score moves", "methodology_changed": "method changes", "alarm": "alarms", "admin_change": "admin changes", "upgraded": "upgrades"}
        lines.append("In the last 24 hours the signed event log recorded: %s." % (", ".join("%d %s" % (n, names.get(k, k)) for k, n in sorted(kinds.items(), key=lambda x: -x[1])) if kinds else "nothing new"))
    al = read_json(os.path.join(watch, "alerts.json")); act = (al or {}).get("active") if isinstance(al, dict) else None
    if isinstance(act, list):
        lines.append("Alerts active now: %d high, %d medium." % (sum(1 for x in act if x.get("severity") == "high"), sum(1 for x in act if x.get("severity") == "medium")))
    else: lines.append("The alerts file could not be read: no count today.")
    lines += ["", "Every alert, with its evidence: " + PAGE]
    return "\n".join(lines)[:3900]


def send(text, token, chat):
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "authority-risk-oracle-digest"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return 200 <= r.status < 300, ""
    except urllib.error.HTTPError as e: return False, "HTTP %d" % e.code
    except (urllib.error.URLError, OSError) as e: return False, type(e).__name__


def main(argv=None, out=print, now=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--daily", action="store_true", help="the daily summary (no protocol, no detail) instead of the weekly one")
    a = ap.parse_args(argv); text = build_daily(a.watch, now) if a.daily else build(a.watch, now)
    if text is None: out("telegram_digest: watch/status.json could not be read, no message built"); return 1
    if a.dry_run: out(text); return 0
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat: out("telegram_digest: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set: nothing sent"); return 3
    ok, why = send(text, tok, chat); out("telegram_digest: sent" if ok else "telegram_digest: NOT sent (%s)" % why); return 0 if ok else 1


def selftest():
    import tempfile
    now = time.mktime(time.strptime("2026-10-12T12:00:00", "%Y-%m-%dT%H:%M:%S")) - time.timezone
    with tempfile.TemporaryDirectory() as d:
        assert build(d, now) is None                                                                  # no status file: no message, not a message full of zeros
        json.dump({"checks": {"oracles": 9, "oracles_read": 9, "targets": 197, "stale": 4}}, open(os.path.join(d, "status.json"), "w"))
        t = build(d, now); assert "9 of 9 oracles" in t and "197 contracts, 4 stale" in t and "The event log could not be read" in t, t
        open(os.path.join(d, "events.jsonl"), "w").write(json.dumps({"run_utc": "2026-10-01T00:00:00Z", "kind": "move"}) + "\n" + json.dumps({"run_utc": "2026-10-11T06:00:00Z", "kind": "move"}) + "\n" + json.dumps({"run_utc": "2026-10-11T06:00:00Z", "kind": "alarm"}) + "\n")
        t = build(d, now); assert "recorded 2 events in the last 7 days" in t and "1 sub-score move" in t and "1 alarm" in t and "method change re-scores" not in t, t       # the event of 01/10 is outside the week
        open(os.path.join(d, "events.jsonl"), "a").write(json.dumps({"run_utc": "2026-10-11T07:00:00Z", "kind": "methodology_changed"}) + "\n")
        assert "method change re-scores contracts" in build(d, now)                                    # said apart: those moves are the formula changing
        open(os.path.join(d, "events.jsonl"), "w").write("")
        assert "recorded nothing new" in build(d, now)
        json.dump({"active": [{"severity": "high", "chain": "Solana", "rule": "a queued change is ready to execute now"}, {"severity": "medium", "chain": "Base", "rule": "r2"}] + [{"severity": "medium", "chain": "X", "rule": "r"}] * 6}, open(os.path.join(d, "alerts.json"), "w"))
        t = build(d, now); assert "1 high, 7 medium" in t and "- HIGH x1 (Solana)" in t and "- MEDIUM x6 (X)" in t and len(t) < 4096 and "—" not in t, t
        os.remove(os.path.join(d, "alerts.json")); assert "alerts file could not be read" in build(d, now)                          # an unreadable alerts file is said, not shown as a quiet week
        json.dump({"active": []}, open(os.path.join(d, "alerts.json"), "w"))
        json.dump({"summary": {"since_utc": "2026-10-12T00:00:00Z", "warned": 2, "missed": 1, "seen_without_notice": 0, "median_notice_hours": 30.0}}, open(os.path.join(d, "warning_ledger.json"), "w"))
        t = build(d, now); assert "2 queued change(s) seen with real notice (median 30.0 h)" in t and "1 went through between two runs" in t, t          # the miss is in the same line as the warnings
        log = []; assert main(["--watch", d, "--dry-run"], out=log.append, now=now) == 0 and "Weekly summary" in log[0]
        os.environ.pop("TELEGRAM_BOT_TOKEN", None); os.environ.pop("TELEGRAM_CHAT_ID", None)
        assert main(["--watch", d], out=log.append, now=now) == 3                                      # not configured: nothing sent, not a failure
        assert main(["--watch", os.path.join(d, "nope")], out=log.append) == 1
    with tempfile.TemporaryDirectory() as d:
        assert build_daily(d, now) is None
        json.dump({"checks": {"oracles": 9}}, open(os.path.join(d, "status.json"), "w"))
        open(os.path.join(d, "events.jsonl"), "w").write(json.dumps({"run_utc": "2026-10-11T20:00:00Z", "kind": "move", "target": "0xSECRET", "label": "Some Protocol"}) + "\n" + json.dumps({"run_utc": "2026-09-01T00:00:00Z", "kind": "alarm"}) + "\n")
        json.dump({"active": [{"severity": "high", "chain": "Base", "target": "0xabc", "title": "Some Protocol", "rule": "r"}, {"severity": "medium", "chain": "X", "target": "0xdef", "title": "Other", "rule": "r2"}]}, open(os.path.join(d, "alerts.json"), "w"))
        t = build_daily(d, now); assert "1 sub-score moves" in t and "Alerts active now: 1 high, 1 medium" in t, t       # the alarm of September is outside the last 24 hours
        assert "Some Protocol" not in t and "0xSECRET" not in t and "Base" not in t and "—" not in t                          # no protocol, no contract, no chain: the detail is the paid offer
        log = []; assert main(["--watch", d, "--daily", "--dry-run"], out=log.append, now=now) == 0 and "Daily summary" in log[0]
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest(); sys.exit(0)
    sys.exit(main())
