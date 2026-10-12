#!/usr/bin/env python3
"""The warning ledger: how much notice the watch really gave before a queued change applied, and every time it did not (12/10/2026).

    python3 scripts/warning_ledger.py --watch watch --out watch/warning_ledger.json

Every run reads the timelock and Squads queues the watch already publishes (watch/pending_ops.json) and keeps one entry per queued operation, with the run that FIRST saw it:
  warned     the operation was still queued, not yet executable, when the watch first saw it: `notice_hours` = time between that run and the moment it could apply;
  seen_without_notice   still queued but already executable (or without a time in the queue file) at the first sighting: seen in time to be told, with no lead time to count;
  missed     the operation was queued AFTER the ledger started and was already applied (or cancelled) when the watch first saw it: it went through between two runs, faster than the cadence;
  baseline   already applied when the very first run of the ledger saw it: history from before the watch existed, never counted as a miss and never as a warning.
The summary counts them, with the shortest and the median notice. A watch that only ever reports successes is an advertisement; this file keeps the misses next to the warnings, and it grows with every run
(a young ledger is small: the summary says since when it counts). No RPC: it reads the files of the run. Standard library only.
"""
import argparse, calendar, json, os, sys, time

KEEP = 2000


def iso(t): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
def secs(s): return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))


def ops_of(po):
    """(key, op, queued_now) for every operation of the queue file; the key is chain:timelock:id."""
    for r in (po or {}).get("results", []):
        if not isinstance(r, dict) or r.get("status") != "ok": continue
        for kind in ("pending", "recent"):
            for o in r.get(kind, []) or []:
                if not isinstance(o, dict) or not o.get("id"): continue
                yield "%s:%s:%s" % (r.get("chain"), str(r.get("address", r.get("name"))).lower(), o["id"]), r, o, (kind == "pending") or bool(o.get("still_queued"))


def due_at(r, o):
    """When the operation can apply, in unix seconds, or None when the file does not say."""
    for k in ("eta", "ready_at"):
        if isinstance(o.get(k), (int, float)): return int(o[k])
    if isinstance(o.get("queued_at"), (int, float)) and isinstance(o.get("delay") or r.get("delay"), (int, float)): return int(o["queued_at"] + (o.get("delay") or r.get("delay")))
    return None


def update(prev, po, now):
    """The new ledger from the previous one (None on the first run) and the queue file, at unix time `now`."""
    led = prev if isinstance(prev, dict) and isinstance(prev.get("entries"), dict) else {"started_utc": iso(now), "entries": {}}
    first_run = prev is None                                                  # only the very first run: what is already applied then is history, not a miss
    started = secs(led["started_utc"]); E = led["entries"]; seen = set()
    for key, r, o, queued in ops_of(po):
        seen.add(key); d = due_at(r, o); q = o.get("queued_at") or o.get("approved_at")
        if key not in E:
            if queued:                                                        # warned only when the time left is known and positive: an operation already executable, or without a time, gave no notice to count
                nh = round((d - now) / 3600, 1) if d and d > now else None
                E[key] = {"outcome": "warned" if nh is not None else "seen_without_notice", "first_seen_utc": iso(now), "due_utc": iso(d) if d else None, "notice_hours": nh, "state": "queued"}
            elif first_run or not isinstance(q, (int, float)) or q < started: E[key] = {"outcome": "baseline", "first_seen_utc": iso(now), "state": "resolved"}
            else: E[key] = {"outcome": "missed", "first_seen_utc": iso(now), "queued_utc": iso(q), "state": "resolved"}
            E[key].update({"chain": r.get("chain"), "timelock": r.get("name"), "what": o.get("decoded") or o.get("signature")})
        elif E[key]["state"] == "queued" and not queued:
            E[key]["state"] = "resolved"; E[key]["resolved_seen_utc"] = iso(now)
    for key, e in E.items():                                                  # a queued operation that left both lists was applied, cancelled or fell out of the window: said, not guessed
        if e["state"] == "queued" and key not in seen: e["state"] = "resolved"; e["resolved_seen_utc"] = iso(now); e["left_the_files"] = True
    if len(E) > KEEP: led["entries"] = dict(sorted(E.items(), key=lambda kv: kv[1]["first_seen_utc"])[-KEEP:])
    led["updated_utc"] = iso(now); led["summary"] = summarize(led["entries"], led["started_utc"]); return led


def summarize(E, since):
    w = sorted(e["notice_hours"] for e in E.values() if e["outcome"] == "warned" and e.get("notice_hours") is not None)
    c = lambda o: sum(1 for e in E.values() if e["outcome"] == o)
    med = (w[len(w) // 2] if len(w) % 2 else (w[len(w) // 2 - 1] + w[len(w) // 2]) / 2) if w else None
    return {"since_utc": since, "warned": c("warned"), "seen_without_notice": c("seen_without_notice"), "missed": c("missed"), "baseline": c("baseline"), "warned_with_a_known_notice": len(w), "shortest_notice_hours": w[0] if w else None,
            "median_notice_hours": round(med, 1) if med is not None else None, "note": "warned: seen while queued and not yet executable (the notice is real); seen_without_notice: still queued but already executable when first seen; missed: queued after the ledger started and already applied when first seen (faster than the 6-hour cadence); baseline: applied before the ledger started, counted as neither."}


def main(argv=None, out=print, now=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--out"); a = ap.parse_args(argv)
    def rj(p):
        try:
            with open(p, encoding="utf-8") as f: return json.load(f)
        except (OSError, ValueError): return None
    po = rj(os.path.join(a.watch, "pending_ops.json"))
    if not isinstance(po, dict) or "results" not in po: out("warning_ledger: watch/pending_ops.json could not be read: the ledger is left as it was"); return 1
    path = a.out or os.path.join(a.watch, "warning_ledger.json"); prev = rj(path)
    if os.path.exists(path) and prev is None: out("warning_ledger: the existing ledger is unreadable: not overwritten"); return 1
    latest = rj(os.path.join(a.watch, "latest.json")) or {}
    t = now if now is not None else (secs(latest["run_utc"]) if isinstance(latest.get("run_utc"), str) else int(time.time()))
    led = update(prev, po, t); tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(led, f, indent=1)
    os.replace(tmp, path); s = led["summary"]
    out("warning ledger: %d warned (median notice %s h), %d seen without notice, %d missed, %d baseline, since %s" % (s["warned"], s["median_notice_hours"], s["seen_without_notice"], s["missed"], s["baseline"], s["since_utc"])); return 0


def selftest():
    T0 = 1_790_000_000; H = 3600
    def q(i, queued, **kw): return {"id": i, "queued_at": T0 - 100, "still_queued": queued, "decoded": "authority change", **kw}
    po = lambda pending=(), recent=(): {"results": [{"chain": "ethereum", "address": "0xAA", "name": "TL", "status": "ok", "pending": list(pending), "recent": list(recent), "delay": 2 * H}]}
    # first run: an applied operation from before the watch is baseline; a queued one is warned with its notice
    l1 = update(None, po(recent=[q("a", False), q("b", True, eta=T0 + 30 * H)]), T0)
    assert l1["entries"]["ethereum:0xaa:a"]["outcome"] == "baseline" and l1["entries"]["ethereum:0xaa:b"]["outcome"] == "warned" and l1["entries"]["ethereum:0xaa:b"]["notice_hours"] == 30.0
    # next run: b applied (resolved, still a warning); c queued and applied between two runs (missed); d seen queued without a time (notice stays null, not 0)
    l2 = update(l1, po(recent=[q("a", False), q("b", False), q("c", False, queued_at=T0 + H)]), T0 + 6 * H)
    E = l2["entries"]; assert E["ethereum:0xaa:b"]["state"] == "resolved" and E["ethereum:0xaa:b"]["outcome"] == "warned" and E["ethereum:0xaa:c"]["outcome"] == "missed"
    l3 = update(l2, po(recent=[q("d", True, queued_at=T0 + 7 * H)]), T0 + 12 * H)
    assert l3["entries"]["ethereum:0xaa:d"]["notice_hours"] is None and l3["entries"]["ethereum:0xaa:d"]["outcome"] == "seen_without_notice" and l3["summary"]["warned"] == 1 and l3["summary"]["seen_without_notice"] == 1 and l3["summary"]["missed"] == 1 and l3["summary"]["baseline"] == 1
    assert l3["summary"]["median_notice_hours"] == 30.0 and l3["summary"]["warned_with_a_known_notice"] == 1
    # an operation that leaves both lists is resolved and flagged, not guessed as applied
    assert l3["entries"]["ethereum:0xaa:d"]["state"] == "queued"; l4 = update(l3, po(), T0 + 18 * H); assert l4["entries"]["ethereum:0xaa:d"]["left_the_files"] is True
    # an unreadable queue file or an unreadable previous ledger never rewrites the ledger
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        log = []; assert main(["--watch", d], out=log.append) == 1
        json.dump(po(), open(os.path.join(d, "pending_ops.json"), "w")); open(os.path.join(d, "warning_ledger.json"), "w").write("{broken"); assert main(["--watch", d], out=log.append) == 1
        assert open(os.path.join(d, "warning_ledger.json")).read() == "{broken"
        os.remove(os.path.join(d, "warning_ledger.json")); assert main(["--watch", d], out=log.append, now=T0) == 0 and "0 warned" in log[-1]
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest(); sys.exit(0)
    sys.exit(main())
