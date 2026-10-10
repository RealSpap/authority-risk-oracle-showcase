#!/usr/bin/env python3
"""One health record per run, for people and monitors that will not read nine files: watch/status.json and a shields.io
endpoint badge, watch/badge/integrity.json. Read-only over the files the run just wrote.

    python3 scripts/run_status.py --watch watch

state: "ok" when every oracle was read, the event-log chain verifies, the run is signed and nothing fired; "degraded" when an
oracle was not read, the run is unsigned, the chain could not be checked, a second-opinion disagreement or a public dispute waits for review;
"alarm" when the watch raised an alarm (a score drop, a stale target, an oracle not answering, a role change on an oracle) or
the chain is broken. The reasons are listed, so a monitor can alert on the state and a person can read why.
"""
import argparse, json, os, time


def load(path):
    try: return json.load(open(path))
    except Exception: return None  # noqa: BLE001 -- a missing or unreadable file is reported as such below


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); a = ap.parse_args()
    W = a.watch; latest, chain, sig, so, meth, dp, rq, rules_al = (load(os.path.join(W, f)) for f in ("latest.json", "chain.json", "signature.json", "second_opinion.json", "methodology.json", "disputes.json", "review_queue.json", "alerts.json"))
    reasons, state = [], "ok"
    def worse(s):
        nonlocal state
        if s == "alarm" or (s == "degraded" and state == "ok"): state = s
    if not latest: reasons.append("latest.json missing"); worse("alarm")
    else:
        if latest.get("alerts"): reasons.append("%d alarm(s) raised by the watch" % len(latest["alerts"])); worse("alarm")
        if latest.get("unread"): reasons.append("oracle(s) not read: " + ", ".join(latest["unread"])); worse("degraded")
        if latest.get("stale_total"): reasons.append("%d of %d targets stale on the oracles" % (latest["stale_total"], latest.get("total_targets", 0)))
    if chain is None: reasons.append("event-log chain not checked"); worse("degraded")
    elif not chain.get("ok"): reasons.append("event-log chain broken: " + str(chain.get("reason"))); worse("alarm")
    if sig is None: reasons.append("no signed manifest"); worse("degraded")
    elif not sig.get("signed"): reasons.append("run unsigned (no signing key set)"); worse("degraded")
    if so and so.get("upgrades"): reasons.append("%d upgrade(s) executed on tracked contracts since the previous run" % len(so["upgrades"])); worse("alarm")
    if so and so.get("disagree"): reasons.append("%d second-opinion disagreement(s) to review" % so["disagree"]); worse("degraded")
    if dp and dp.get("open"): reasons.append("%d public dispute(s) open, review pending" % dp["open"]); worse("degraded")
    hi_rules = [x for x in ((rules_al or {}).get("active") or []) if x.get("severity") == "high"]   # since 2026-10-10: a drain, a pause, a change ready to execute, an upgrade: the rules' own high alerts count in the state
    if hi_rules: reasons.append("%d high alert(s) from the rules firing now (%s)" % (len(hi_rules), "; ".join(sorted({str(x.get("rule"))[:60] for x in hi_rules})[:3]))); worse("degraded")
    if meth and meth.get("changes"): reasons.append("methodology changed on %d oracle(s): scores before this run are not comparable" % len(meth["changes"])); worse("degraded")
    if meth and meth.get("mixed"): reasons.append("methodology hashes mixed on %d oracle(s)" % len(meth["mixed"])); worse("degraded")
    rec = {"run_utc": (latest or {}).get("run_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "state": state, "reasons": reasons,
           "checks": {"oracles_read": (len(latest.get("oracles", [])) - len(latest.get("unread", []))) if latest else None, "oracles": len(latest.get("oracles", [])) if latest else None,
                      "targets": (latest or {}).get("total_targets"), "stale": (latest or {}).get("stale_total"), "alarms": len((latest or {}).get("alerts", [])),
                      "chain_ok": chain.get("ok") if chain else None, "chain_entries": chain.get("lines") if chain else None, "signed": bool(sig and sig.get("signed")),
                      "signing_key": (sig or {}).get("public_key"), "second_opinion": ({k: so.get(k) for k in ("agree", "disagree", "acknowledged", "unreadable", "native")} if so else None),
                      "methodology_mixed": len(meth.get("mixed", [])) if meth else None, "disputes_open": dp.get("open") if dp else None, "review_items": rq.get("total") if rq else None},   # the review queue is information for the maintainer, it does not change the state
           "what": "the run's health in one record: ok / degraded / alarm with the reasons; written by scripts/run_status.py after every Watch run"}
    tmp = os.path.join(W, "status.json.tmp"); json.dump(rec, open(tmp, "w"), indent=1); os.replace(tmp, os.path.join(W, "status.json"))
    os.makedirs(os.path.join(W, "badge"), exist_ok=True)
    parts = [("signed" if rec["checks"]["signed"] else "unsigned"), ("chain intact" if rec["checks"]["chain_ok"] else ("chain broken" if chain else "chain unchecked"))]
    if so: parts.append("2nd opinion %s" % ("%d to review" % so["disagree"] if so.get("disagree") else "agrees"))
    badge = {"schemaVersion": 1, "label": "watch integrity", "message": " · ".join(parts), "color": {"ok": "brightgreen", "degraded": "orange", "alarm": "red"}[state]}
    tmp = os.path.join(W, "badge", "integrity.json.tmp"); json.dump(badge, open(tmp, "w"), indent=1); os.replace(tmp, os.path.join(W, "badge", "integrity.json"))
    print("status: %s%s" % (state, (" (" + "; ".join(reasons) + ")") if reasons else ""))


if __name__ == "__main__":
    main()
