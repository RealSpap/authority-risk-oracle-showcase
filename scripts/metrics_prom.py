#!/usr/bin/env python3
"""The run in the Prometheus text format, watch/metrics.prom: what a monitor needs without parsing nine JSON files.

    python3 scripts/metrics_prom.py --watch watch

A Prometheus (or Grafana Agent, or VictoriaMetrics) can scrape the raw file over HTTPS; the alert that matters most is the Watch stopping:

    time() - aro_run_timestamp_seconds > 8 * 3600       # a run every 6 hours: two missed runs

Other alerts: aro_status{state="alarm"} == 1, aro_alerts_active{severity="high"} > 0, aro_oracle_read == 0, aro_safes_woke > 0.

A source file that is missing or unreadable gives NO series, never a zero: an unread state is not a healthy one, and a gauge at 0 would
say "nothing paused" when nothing was asked. Read-only over the files the run just wrote; written after status.json, so it is not in the signed manifest
(like status.json it is derived: recompute it from the signed files).
"""
import argparse, calendar, glob, json, os, time


def load(path):
    try: return json.load(open(path))
    except Exception: return None  # noqa: BLE001 -- a missing or unreadable source is a missing series, not a zero


def esc(v):
    """A label value in the exposition format: backslash, double quote and newline are escaped."""
    return str(v).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def utc_s(t):
    try: return calendar.timegm(time.strptime(t, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError): return None


class Out:
    def __init__(self): self.lines, self.seen = [], set()

    def gauge(self, name, help_, samples):
        """samples: [(labels dict, value)]; nothing is written for an empty list, and a metric is declared once."""
        samples = [(l, v) for l, v in samples if v is not None]
        if not samples: return
        if name not in self.seen: self.seen.add(name); self.lines += ["# HELP %s %s" % (name, help_), "# TYPE %s gauge" % name]
        for l, v in samples:
            lab = ("{" + ",".join('%s="%s"' % (k, esc(x)) for k, x in sorted(l.items())) + "}") if l else ""
            self.lines.append("%s%s %s" % (name, lab, ("%d" % v) if isinstance(v, (int, bool)) else repr(round(float(v), 6))))


def build(W):
    o = Out(); latest, status, alerts = (load(os.path.join(W, f)) for f in ("latest.json", "status.json", "alerts.json"))
    so, pause, safe = (load(os.path.join(W, f)) for f in ("second_opinion.json", "pause_state.json", "safe_activity.json"))
    if latest:
        o.gauge("aro_run_timestamp_seconds", "UTC time of the last Watch run (Unix seconds)", [({}, utc_s(latest.get("run_utc")))])
        oracles = [x for x in latest.get("oracles") or [] if x.get("name")]
        o.gauge("aro_oracle_read", "1 when the oracle was read at the last run, 0 when it was not (its targets are then unknown, not zero)", [({"oracle": x["name"]}, 1 if x.get("read_ok") else 0) for x in oracles])
        o.gauge("aro_oracle_targets", "Targets the oracle tracks", [({"oracle": x["name"]}, x.get("targets")) for x in oracles if x.get("read_ok")])
        o.gauge("aro_oracle_stale_targets", "Targets of the oracle whose score is older than its maxStaleness", [({"oracle": x["name"]}, x.get("stale")) for x in oracles if x.get("read_ok")])
        o.gauge("aro_targets", "Targets tracked across the oracles that were read", [({}, latest.get("total_targets"))])
        o.gauge("aro_targets_stale", "Targets whose score is stale", [({}, latest.get("stale_total"))])
    if status and status.get("state") in ("ok", "degraded", "alarm"):
        o.gauge("aro_status", "The run's health, one series per state, 1 for the current one", [({"state": s}, 1 if status["state"] == s else 0) for s in ("ok", "degraded", "alarm")])
        ck = status.get("checks") or {}
        o.gauge("aro_chain_ok", "1 when the hash-chained event log verifies", [({}, None if ck.get("chain_ok") is None else (1 if ck["chain_ok"] else 0))])
        o.gauge("aro_signed", "1 when the run carries a valid Ed25519 signature", [({}, None if ck.get("signed") is None else (1 if ck["signed"] else 0))])
    if alerts is not None and isinstance(alerts.get("active"), list):
        n = {"high": 0, "medium": 0, "info": 0}
        for a in alerts["active"]: n[a.get("severity") if a.get("severity") in n else "info"] += 1
        o.gauge("aro_alerts_active", "Alerts firing now, by severity", [({"severity": k}, v) for k, v in n.items()])
    if so:
        o.gauge("aro_second_opinion", "Targets by verdict of the independent reader", [({"result": k}, so.get(k)) for k in ("agree", "disagree", "unreadable", "native")])
    if pause and isinstance(pause.get("paused"), list):
        o.gauge("aro_contracts_paused", "Tracked contracts that answer paused() true now", [({}, len(pause["paused"]))])
    if safe:
        o.gauge("aro_safes", "Safes that administer a tracked contract", [({}, safe.get("safes"))])
        o.gauge("aro_safes_woke", "Admin Safes that executed after 14 days or more observed idle, at the last run", [({}, len(safe["woke"]) if isinstance(safe.get("woke"), list) else None)])
        o.gauge("aro_safes_never_executed", "Admin Safes still at nonce 0", [({}, len(safe["never_executed"]) if isinstance(safe.get("never_executed"), list) else None)])
    score, stale = [], []
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = load(f); slug = os.path.basename(f)[:-5]
        for t in (d or {}).get("targets") or []:
            if isinstance(t.get("compositeScore"), (int, float)): score.append(({"chain": slug, "target": str(t.get("target"))}, t["compositeScore"])); stale.append(({"chain": slug, "target": str(t.get("target"))}, 1 if t.get("stale") else 0))
    o.gauge("aro_target_score", "Composite score of a tracked contract, 0 to 100, from the oracle's last push", score)
    o.gauge("aro_target_stale", "1 when the score is stale", stale)
    return "\n".join(o.lines) + "\n" if o.lines else ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); a = ap.parse_args()
    text = build(a.watch)
    if not text: print("metrics.prom: no source file readable, nothing written (an empty file would read as a healthy one)"); return
    p = os.path.join(a.watch, "metrics.prom"); open(p + ".tmp", "w").write(text); os.replace(p + ".tmp", p)
    print("metrics.prom: %d series" % sum(1 for l in text.split("\n") if l and not l.startswith("#")))


if __name__ == "__main__":
    main()
