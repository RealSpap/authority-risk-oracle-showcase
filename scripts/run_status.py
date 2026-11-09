#!/usr/bin/env python3
"""One health record per run, for people and monitors that will not read nine files: watch/status.json and a shields.io
endpoint badge, watch/badge/integrity.json. Read-only over the files the run just wrote.

    python3 scripts/run_status.py --watch watch

state: "ok" when every oracle was read, the event-log chain verifies, the run is signed and nothing fired; "degraded" when an
oracle was not read, the run is unsigned, the chain could not be checked, a second-opinion disagreement or a public dispute waits for review;
"alarm" when the watch raised an alarm (a score drop, a stale target, an oracle not answering, a role change on an oracle) or
the chain is broken. The reasons are listed, so a monitor can alert on the state and a person can read why.
"""
import argparse, datetime, json, os, time
from watch_location import RAW  # noqa: E402
import run_id  # noqa: E402


SILENCE_H = 8   # a gap between two runs longer than this is added to the reasons (information, no change of state)
SAME_RUN_SECONDS = 600   # only when latest.json is missing: trend.py then wrote this run's line with the clock of its own step, a few minutes before this script reads the clock again


def _t(s):
    try: return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError): return None


def cadence(W, run_utc, same_run_seconds=0):
    """(runs in the 7 days up to and including this run, start of the run before it, hours between the two starts), read from trend.jsonl (one line per run, written before this step).
    None for what cannot be read, never 0: the cadence is a measure of the past, a page that wants to know whether the Watch is late now compares run_utc with its own clock.
    A line at most same_run_seconds before run_utc is this run's own line (it counts once, it is not the previous run); with latest.json the two times are equal and the value is 0."""
    now = _t(run_utc); seen = set()
    if now is None: return None, None, None
    try:
        for l in open(os.path.join(W, "trend.jsonl"), encoding="utf-8"):
            try: t = _t(json.loads(l).get("run_utc"))
            except (ValueError, AttributeError): t = None
            if t is not None and t < now and (now - t).total_seconds() > same_run_seconds: seen.add(t)
    except OSError: return None, None, None
    prev = max(seen, default=None); seen.add(now)
    return sum(1 for t in seen if t > now - datetime.timedelta(days=7)), prev, ((now - prev).total_seconds() / 3600 if prev else None)


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
        if latest.get("retired_total"): reasons.append("%d retired target(s) listed apart, not counted stale (information, no change of state; names in latest.json `retired`)" % latest["retired_total"])
    if chain is None: reasons.append("event-log chain not checked"); worse("degraded")
    elif not chain.get("ok"): reasons.append("event-log chain broken: " + str(chain.get("reason"))); worse("alarm")
    sig_status = "missing" if sig is None else ("signed" if sig.get("signed") else "unsigned")
    refused = False
    try: refused = "REFUSED TO SIGN" in open(os.path.join(W, "signature.txt"), encoding="utf-8", errors="replace").read() or open(os.path.join(W, "signature.txt"), encoding="utf-8", errors="replace").read().rstrip().rsplit("\n", 1)[-1].startswith("exit code")
    except OSError: pass
    older = bool(sig and latest and isinstance(sig.get("run_utc"), str) and isinstance(latest.get("run_utc"), str) and sig["run_utc"] < latest["run_utc"])   # the signature file is from an EARLIER run: this run was not signed
    if sig is not None and (refused or older): sig_status = "stale"   # N55bis: a refused signing leaves the previous signature.json in place; it must not be shown as "signed"
    try:
        import audit_public
        pinned_keys = [k.lower() for k in audit_public.PINNED_KEYS]
    except Exception:  # noqa: BLE001 -- the list of pinned keys could not be loaded: the badge then says the key was not checked
        pinned_keys = []
    key_state = "key not checked" if not pinned_keys else ("key pinned" if str((sig or {}).get("public_key", "")).lower() in pinned_keys else "key not pinned")   # "signed" is the file's own word; the pinned key is what makes it mean something
    if sig_status == "signed" and key_state != "key pinned": reasons.append("the run is signed but %s: a signature by a key nobody pinned proves nothing about who ran it" % key_state); worse("degraded")
    if sig_status == "missing": reasons.append("no signed manifest"); worse("degraded")
    elif sig_status == "unsigned": reasons.append("run unsigned (no signing key set)"); worse("degraded")
    elif sig_status == "stale": reasons.append("signature STALE: this run could not be signed (%s); signature.json is the one of an earlier run" % ("signing refused, see signature.txt" if refused else "its run time is older than latest.json")); worse("alarm")
    if so and so.get("upgrades"): reasons.append("%d upgrade(s) executed on tracked contracts since the previous run" % len(so["upgrades"])); worse("alarm")
    if so and so.get("disagree"): reasons.append("%d second-opinion disagreement(s) to review" % so["disagree"]); worse("degraded")
    if so and so.get("corroborated"): reasons.append("%d second-opinion disagreement(s) corroborated: the reader itself read and verified a second, weaker authority path on chain (listed in second_opinion.json under corroborated_disagreements with the facts read, recomputed at every run, not counted as a disagreement to review)" % so["corroborated"])   # information, not a state: it never makes the state worse
    if dp and dp.get("open"): reasons.append("%d public dispute(s) open, review pending" % dp["open"]); worse("degraded")
    hi_rules = [x for x in ((rules_al or {}).get("active") or []) if x.get("severity") == "high"]   # since 2026-10-10: a drain, a pause, a change ready to execute, an upgrade: the rules' own high alerts count in the state
    if hi_rules: reasons.append("%d high alert(s) from the rules firing now (%s)" % (len(hi_rules), "; ".join(sorted({str(x.get("rule"))[:100] for x in hi_rules})[:3]))); worse("degraded")
    if meth and meth.get("changes"): reasons.append("methodology changed on %d oracle(s): scores before this run are not comparable" % len(meth["changes"])); worse("degraded")
    if meth and meth.get("mixed"): reasons.append("methodology hashes mixed on %d oracle(s)" % len(meth["mixed"])); worse("degraded")
    if meth and meth.get("unregistered"): reasons.append("method hash not in registry on %d oracle(s): no version is shown for it (data/method_versions.json)" % len({o for u in meth["unregistered"] for o in u["oracles"]}))   # information: no change of state, a version is never invented
    rec = {"run_utc": (latest or {}).get("run_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "state": state, "reasons": reasons, "data_location": RAW,   # where every file of the Watch is served (the watch-data branch): a page or a monitor reads this, not a constant of its own
           "checks": {"oracles_read": (len(latest.get("oracles", [])) - len(latest.get("unread", []))) if latest else None, "oracles": len(latest.get("oracles", [])) if latest else None,
                      "targets": (latest or {}).get("total_targets"), "stale": (latest or {}).get("stale_total"), "retired": (latest or {}).get("retired_total"), "alarms": len((latest or {}).get("alerts", [])),
                      "chain_ok": chain.get("ok") if chain else None, "chain_entries": chain.get("lines") if chain else None, "signed": bool(sig and sig.get("signed")) and sig_status != "stale", "signature_status": sig_status,
                      "signing_key": (sig or {}).get("public_key"), "second_opinion": ({k: so.get(k) for k in ("agree", "disagree", "corroborated", "acknowledged", "unreadable", "native")} if so else None),
                      "methodology_mixed": len(meth.get("mixed", [])) if meth else None, "disputes_open": dp.get("open") if dp else None, "review_items": rq.get("total") if rq else None},   # the review queue is information for the maintainer, it does not change the state
           "what": "the run's health in one record: ok / degraded / alarm with the reasons; written by scripts/run_status.py after every Watch run"}
    ma = load(os.path.join(W, "main_activity.json"))   # since 2026-10-14: how old the last commit on main is (GitHub disables scheduled workflows after 60 days without repository activity)
    if ma:
        rec["main_last_commit_age_days"] = ma.get("main_last_commit_age_days")
        if ma.get("level") == "warn": reasons.append("main has had no commit for %s days: GitHub disables the scheduled Watch after 60 days without repository activity (information, no change of state)" % ma.get("main_last_commit_age_days"))
    n7, prev, gap = cadence(W, rec["run_utc"], 0 if (latest or {}).get("run_utc") else SAME_RUN_SECONDS)   # since 2026-11-08: what the Watch really did, so that no page has to write a count of runs by hand
    rec["runs_7d"] = n7; rec["previous_run_utc"] = prev.strftime("%Y-%m-%dT%H:%M:%SZ") if prev else None; rec["hours_since_previous_run"] = round(gap, 1) if gap is not None else None
    if gap is not None and gap > SILENCE_H: reasons.append("the Watch was silent for %.1f hours before this run (previous run %s, scheduled every 6 hours): information, no change of state" % (gap, rec["previous_run_utc"]))
    if run_id.current(): rec["run_id"] = run_id.current()
    tmp = os.path.join(W, "status.json.tmp"); json.dump(rec, open(tmp, "w"), indent=1); os.replace(tmp, os.path.join(W, "status.json"))
    os.makedirs(os.path.join(W, "badge"), exist_ok=True)
    parts = [("signature stale" if sig_status == "stale" else ("signed, " + key_state) if rec["checks"]["signed"] else "unsigned"), ("chain intact" if rec["checks"]["chain_ok"] else ("chain broken" if chain else "chain unchecked"))]
    if so: parts.append("2nd opinion: %d agree, %d to review, %d unread" % (so.get("agree") or 0, so.get("disagree") or 0, (so.get("unreadable") or 0) + (so.get("native") or 0)))   # the words say what was counted; "agrees" said more than the reader read
    badge = {"schemaVersion": 1, "label": "watch integrity", "message": " · ".join(parts), "color": {"ok": "brightgreen", "degraded": "orange", "alarm": "red"}[state]}
    tmp = os.path.join(W, "badge", "integrity.json.tmp"); json.dump(badge, open(tmp, "w"), indent=1); os.replace(tmp, os.path.join(W, "badge", "integrity.json"))
    print("status: %s%s" % (state, (" (" + "; ".join(reasons) + ")") if reasons else ""))


if __name__ == "__main__":
    main()
