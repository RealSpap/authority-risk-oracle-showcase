#!/usr/bin/env python3
"""Read every deployed EVM oracle and record what moved since the previous run (read-only, public RPC, no key).

For each oracle in `live_target_counts.ORACLES`: `trackedTargetsCount()`, every `trackedTargets(i)`, then `getScore(target)`
and `isStale(target)` for each. The result is written to `watch/scores/<oracle>.json`, compared with the previous file, and
summarised in `watch/latest.json` plus one line appended to `watch/history.jsonl`. When something needs a person,
`watch/alarm.md` is written and the exit code is 2.

Exit codes: 0 nothing to flag; 1 at least one oracle could not be read (its targets are unknown, not zero); 2 alarm
(a composite dropped by 10 points or more, a target turned stale, or an oracle that answered last time could not be read).

    python3 scripts/watch_run.py            # about 2 to 4 minutes
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from live_target_counts import ORACLES  # noqa: E402

WATCH = os.path.join(ROOT, "watch")
SEL_COUNT, SEL_TARGET, SEL_SCORE, SEL_STALE, SEL_MAX = "0x835e2172", "0x9481e5e0", "0xd47875d0", "0xf461f6e7", "0x87cf4696"
FIELDS = ["adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore"]
DROP_THRESHOLD = 10  # same threshold as scripts/lib/alerts.py
CHUNK = 20           # the Robinhood edge mishandles batch bodies above about 10 KB


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def rpc(url, calls, tries=3):
    """One JSON-RPC batch; returns a list of results in order. Raises on the last failed try."""
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]).encode()
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "watch_run/1"})
            with urllib.request.urlopen(req, timeout=40) as r:
                out = json.loads(r.read().decode())
            if not isinstance(out, list) or len(out) != len(calls):
                raise ValueError(f"malformed batch answer ({str(out)[:80]})")
            res = sorted(out, key=lambda x: x["id"])
            if any("error" in x for x in res):
                raise ValueError(str([x["error"] for x in res if "error" in x])[:160])
            return [x["result"] for x in res]
        except Exception as e:  # noqa: BLE001 -- retried, then reported
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def batched(url, calls):
    """Send `calls` in batches that the endpoint accepts: 20 at a time, then 5 with a pause, then one by one.
    Some testnet RPCs reject or rate-limit batches (HTTP 413, 'requests limited to 15/sec', 'batch too large')."""
    for size, pause in ((CHUNK, 0.0), (5, 1.0), (1, 0.25)):
        try:
            out = []
            for i in range(0, len(calls), size):
                out += rpc(url, calls[i:i + size], tries=2)
                time.sleep(pause)
            return out
        except Exception as e:  # noqa: BLE001 -- try a smaller batch before giving up
            last = e
    raise last


def call(oracle, data):
    return ("eth_call", [{"to": oracle, "data": data}, "latest"])


def pad(addr):
    return addr.lower().replace("0x", "").rjust(64, "0")


def read_oracle(name, oracle, url):
    block = int(rpc(url, [("eth_blockNumber", [])])[0], 16)
    count_hex, max_hex = rpc(url, [call(oracle, SEL_COUNT), call(oracle, SEL_MAX)])
    count, max_staleness = int(count_hex, 16), int(max_hex, 16)
    targets = ["0x" + r[-40:] for r in batched(url, [call(oracle, SEL_TARGET + f"{j:064x}") for j in range(count)])]
    rows = []
    if targets:
        res = batched(url, [call(oracle, SEL_SCORE + pad(t)) for t in targets] + [call(oracle, SEL_STALE + pad(t)) for t in targets])
        for t, s, st in zip(targets, res[:len(targets)], res[len(targets):]):
            words = [s[2 + 64 * k: 2 + 64 * (k + 1)] for k in range(8)]
            if len(s) < 2 + 64 * 8:
                raise ValueError(f"getScore returned {len(s)} chars for {t}")
            row = {"target": t, **{f: int(words[k], 16) for k, f in enumerate(FIELDS)},
                   "lastUpdated": int(words[6], 16), "methodologyHash": "0x" + words[7], "stale": int(st, 16) == 1}
            rows.append(row)
    return {"name": name, "oracle": oracle, "rpc": url, "block": block, "maxStaleness": max_staleness, "readAt": int(time.time()), "targets": rows}


def labels():
    try:
        d = json.load(open(os.path.join(ROOT, "api", "scores.json")))
        return {s["target"].lower(): s["label"] for s in d["scores"]}
    except Exception:  # noqa: BLE001
        return {}


def main():
    os.makedirs(os.path.join(WATCH, "scores"), exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    names = labels()
    summary, movers, alerts, unread = [], [], [], []
    prev_latest = {}
    try:
        prev_latest = json.load(open(os.path.join(WATCH, "latest.json")))
    except Exception:  # noqa: BLE001
        pass
    prev_ok = {o["slug"] for o in prev_latest.get("oracles", []) if o.get("read_ok")}

    for name, oracle, url in ORACLES:
        s = slug(name)
        path = os.path.join(WATCH, "scores", s + ".json")
        try:
            cur = read_oracle(name, oracle, url)
        except Exception as e:  # noqa: BLE001 -- an unread oracle is reported, never counted as empty
            err = f"{type(e).__name__}: {str(e)[:160]}"
            unread.append(name)
            summary.append({"name": name, "slug": s, "oracle": oracle, "read_ok": False, "error": err})
            if s in prev_ok:
                alerts.append(f"{name}: could not be read this run (it answered last time): {err}")
            continue
        prev = None
        try:
            prev = {t["target"]: t for t in json.load(open(path))["targets"]}
        except Exception:  # noqa: BLE001
            pass
        stale = [t for t in cur["targets"] if t["stale"]]
        for t in cur["targets"]:
            label = names.get(t["target"], t["target"][:6] + "…" + t["target"][-4:])
            p = prev.get(t["target"]) if prev else None
            if p is None:
                if prev is not None:
                    movers.append({"oracle": name, "target": t["target"], "label": label, "field": "new", "before": None, "after": t["compositeScore"]})
                    if t["compositeScore"] < 40:
                        alerts.append(f"{name}: new target {label} first published at composite {t['compositeScore']}")
                continue
            for f in FIELDS:
                if p.get(f) != t[f]:
                    movers.append({"oracle": name, "target": t["target"], "label": label, "field": f, "before": p.get(f), "after": t[f]})
            if p.get("compositeScore", 0) - t["compositeScore"] >= DROP_THRESHOLD:
                alerts.append(f"{name}: {label} composite {p['compositeScore']} -> {t['compositeScore']}")
            if t["stale"] and not p.get("stale"):
                alerts.append(f"{name}: {label} turned stale (last update {datetime.datetime.fromtimestamp(t['lastUpdated'], datetime.timezone.utc):%Y-%m-%d %H:%M} UTC)")
        last_push = max((t["lastUpdated"] for t in cur["targets"]), default=0)
        summary.append({"name": name, "slug": s, "oracle": oracle, "read_ok": True, "block": cur["block"], "targets": len(cur["targets"]),
                        "stale": len(stale), "lastUpdated": last_push, "maxStaleness": cur["maxStaleness"]})
        json.dump(cur, open(path, "w"), indent=1)

    latest = {
        "run_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "previous_run_utc": prev_latest.get("run_utc"),
        "oracles": summary, "total_targets": sum(o.get("targets", 0) for o in summary), "stale_total": sum(o.get("stale", 0) for o in summary),
        "movers": movers, "alerts": alerts, "unread": unread,
        "note": "EVM oracles only; the Solana program and the Zcash commitments are read by scripts/oracle_freshness.py. An oracle in `unread` has unknown targets, not zero.",
    }
    json.dump(latest, open(os.path.join(WATCH, "latest.json"), "w"), indent=1)
    with open(os.path.join(WATCH, "history.jsonl"), "a") as f:
        f.write(json.dumps({"run_utc": latest["run_utc"], "targets": latest["total_targets"], "stale": latest["stale_total"],
                            "movers": len(movers), "alerts": len(alerts), "unread": len(unread)}) + "\n")
    alarm = os.path.join(WATCH, "alarm.md")
    if alerts:
        with open(alarm, "w") as f:
            f.write(f"# Alarm, {latest['run_utc']}\n\n" + "".join(f"- {a}\n" for a in alerts)
                    + "\nRead-only watch of the deployed oracles (`scripts/watch_run.py`). Details: `watch/latest.json`.\n")
    elif os.path.exists(alarm):
        os.remove(alarm)
    print(f"{latest['total_targets']} targets read on {len(summary) - len(unread)} of {len(ORACLES)} EVM oracles, "
          f"{latest['stale_total']} stale, {len(movers)} moves, {len(alerts)} alerts, unread: {', '.join(unread) or 'none'}")
    for a in alerts:
        print("  ALARM", a)
    sys.exit(2 if alerts else 1 if unread else 0)


if __name__ == "__main__":
    main()
