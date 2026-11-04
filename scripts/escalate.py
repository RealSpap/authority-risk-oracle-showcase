#!/usr/bin/env python3
"""Escalation of a standing alarm : when the alarm gate says `escalation`, the same state has stood for 72 hours or more, and it is said louder.

Until now an escalation only changed the title of the private issue. Two things change:
  - a new SEVERITY: the issue carries the label `escalation` next to `alarm` (the workflow does that), and the message below says "ESCALATION";
  - a new CHANNEL: the alert channels (Discord, the signed webhook, Telegram), which the alarm never used (it goes to a private issue), receive one short message with the
    number of findings, their kinds, and how long the oldest one has stood. Nothing private leaves: no target, no address, no text of a finding, only counts and kinds.

    python3 scripts/escalate.py --watch watch            # reads watch/alarm_state.json; prints the message; sends it to the channels whose secrets are set

The gate says `escalation` at every reminder period (24 hours) while the state stands; the channels are told at the FIRST escalation and then at every third one (`escalations` in alarm_state.json), so a public channel does not hear it daily.

Exit 0 when nothing had to be sent or at least one channel carried the message, 1 when every configured channel failed (the workflow does not stop for that).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from lib.reader_audit import configured_channels  # noqa: E402

PAGE = "https://realspap.github.io/oracle/"


def kinds_of(findings):
    """{kind: count} from the identifiers of the gate (`disagree:...`, `overdue:...`, `alarm:...`): the part before the first colon."""
    out = {}
    for f in findings or []:
        k = str(f).split(":", 1)[0]
        out[k] = out.get(k, 0) + 1
    return out


def message(state, now):
    """The text of the escalation, or None when the state holds no finding or no date to count from. Counts and kinds only."""
    state = state if isinstance(state, dict) else {}
    findings = state.get("findings") or []
    firsts = [v for k, v in (state.get("first_seen") or {}).items() if k in set(findings) and isinstance(v, str)]
    since = min(firsts) if firsts else (state.get("first_notified_utc") if isinstance(state.get("first_notified_utc"), str) else None)
    if not findings or not since:
        return None
    try:
        import calendar
        hours = int((now - calendar.timegm(time.strptime(since, "%Y-%m-%dT%H:%M:%SZ"))) // 3600)
    except ValueError:
        return None
    kinds = ", ".join("%d %s" % (n, k) for k, n in sorted(kinds_of(findings).items()))
    return ("Authority Risk Oracle: ESCALATION. The same state has stood for %d hours (since %s): %d finding(s) (%s). It was reported in a private issue and is still not resolved. %s"
            % (hours, since, len(findings), kinds, PAGE))


def send(text, env, post_json=None, post_signed=None, telegram=None):
    """{channel: bool} for every configured channel. The senders are injected so that a test can replace them."""
    if post_json is None or post_signed is None:
        import evaluate_rules as ev
        post_json, post_signed = post_json or ev.post_json, post_signed or ev.post_signed
    if telegram is None:
        import alerts
        telegram = alerts.send_telegram_alert
    res = {}
    chans = configured_channels(env)
    if "discord" in chans:
        res["discord"] = bool(post_json(env["DISCORD_WEBHOOK_URL"], {"content": text[:1900], "allowed_mentions": {"parse": []}}))
    if "webhook" in chans:
        res["webhook"] = bool(post_signed(env["ALERT_WEBHOOK_URL"], env.get("ALERT_WEBHOOK_SECRET", ""), {"event": "escalation", "version": 1, "sent_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "text": text, "page": PAGE}))
    if "telegram" in chans:
        try:
            res["telegram"] = bool(telegram(text))
        except Exception:  # noqa: BLE001 -- a sender must not stop the others
            res["telegram"] = False
    return res


def main(argv=None, env=None, **senders):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch")
    a = ap.parse_args(argv)
    env = os.environ if env is None else env
    try:
        with open(os.path.join(a.watch, "alarm_state.json"), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = None
    text = message(state, time.time())
    if text is None:
        print("escalate: no standing finding with a date: nothing sent")
        return 0
    n = (state or {}).get("escalations")
    if isinstance(n, int) and n > 1 and n % 3 != 0:      # the gate says `escalation` every 24 hours while the state stands: the public channels hear it at the first one and then every third day, not daily
        print("escalate: escalation %d of this state: already said, next notice on a multiple of 3 (nothing sent)" % n)
        return 0
    print(text)
    res = send(text, env, **senders)
    if not res:
        print("escalate: no alert channel is configured (no secret set): the message above is only in this log")
        return 0
    print("escalate: " + ", ".join("%s %s" % (c, "sent" if ok else "FAILED") for c, ok in sorted(res.items())))
    return 0 if any(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
