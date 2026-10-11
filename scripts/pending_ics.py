#!/usr/bin/env python3
"""The timelock queue as a calendar feed (.ics): every operation queued behind a watched timelock becomes an event at the
moment it becomes executable, so anyone can subscribe from Google Calendar, Apple Calendar or Outlook and see governance
changes land on their own calendar. Built from watch/pending_ops.json, read-only.

    python3 scripts/pending_ics.py --pending watch/pending_ops.json --out watch/pending_ops.ics
"""
import argparse, json, os, sys, time
# function names for the selectors the watched timelocks queue most often (same table as the dashboard); the raw selector stays when unknown
SELNAMES = {"0x2f2ff15d": "grantRole", "0xd547741f": "revokeRole", "0x3659cfe6": "upgradeTo", "0x4f1ef286": "upgradeToAndCall", "0x99a88ec4": "upgrade", "0x9623609d": "upgradeAndCall", "0xf2fde38b": "transferOwnership", "0x8456cb59": "pause", "0x3f4ba83a": "unpause", "0x64d62353": "updateDelay", "0x6dbd9f90": "setConfig", "0x46f943e9": "setRateLimits", "0xadbab6c3": "setWithdrawExpiration", "0x87acd009": "setWithdrawCooldown", "0x4dd18bf5": "setPendingAdmin", "0x3dbb202b": "sendMessage", "0x01d5062a": "schedule", "0x9f3ce55a": "sendMessage"}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--pending", default="watch/pending_ops.json"); ap.add_argument("--out", default="watch/pending_ops.ics")
    a = ap.parse_args()
    d = json.load(open(a.pending)) if os.path.exists(a.pending) else {"results": []}
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Authority Risk Oracle//timelock queue//EN", "X-WR-CALNAME:Authority Risk Oracle: timelock queue", "X-WR-CALDESC:Operations queued behind the watched timelocks, at the time they become executable"]
    n = 0
    for t in d.get("results", []):
        if t.get("status") != "ok": continue
        for o in t.get("pending", []):
            at = o.get("ready_at")
            if not at or o.get("state") == "expired": continue   # past its grace window it can no longer run: no reminder (the digest leaves it out too)
            fn = (o.get("signature") or SELNAMES.get(str(o.get("selector") or "").lower()) or ("a call with no data" if o.get("selector") == "0x" else o.get("selector")) or "call").split("(")[0]   # the event's own signature, else the same small table the page uses, else the raw selector
            uid = (o.get("tx") or "") + "-" + str(o.get("index", 0)) + "@realspap.github.io"
            def ics(t): return str(t).replace("\\", "\\\\").replace("\n", " ").replace("\r", " ").replace(";", "\\;").replace(",", "\\,")[:200]
            lines += ["BEGIN:VEVENT", "UID:" + uid + "-" + str(o.get("id", ""))[:18], "DTSTAMP:" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
                      "DTSTART:" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(at)), "DTEND:" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(at + 1800)),
                      "SUMMARY:" + ics(t["name"] + ": " + fn + " becomes executable"),
                      "DESCRIPTION:" + fn + " on " + str(o.get("target")) + " (" + t.get("chain", "") + ")\\nqueued in tx " + str(o.get("tx")) + "\\nhttps://realspap.github.io/oracle/",
                      "URL:https://realspap.github.io/oracle/", "END:VEVENT"]
            n += 1
    lines.append("END:VCALENDAR")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w").write("\r\n".join(lines) + "\r\n")
    print(f"calendar: {n} queued operation(s)")

if __name__ == "__main__":
    sys.exit(main())
