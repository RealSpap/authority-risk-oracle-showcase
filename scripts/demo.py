#!/usr/bin/env python3
"""See the watch react, offline, in a few seconds: four synthetic events on a copy of the real files, then the real scripts.

    python3 scripts/demo.py
    python3 scripts/demo.py --watch watch --rules rules.json --chain base --target 0xbbbb...

On the real data nothing fires today: nothing is paused, no Safe has woken, no balance has collapsed. A reader cannot see the alerts, the review queue or the dossier
react to anything. This copies watch/ to a temporary folder, writes four events into the state files of ONE contract (by default the tracked contract with the most money behind it)
and runs the actual scripts on the copy: evaluate_rules.py (the alerts), review_queue.py (what needs a person), dossier.py (the contract's page in words) and metrics_prom.py
(what a monitor would see). The events:

  1. the contract is paused now and was not at the previous run;
  2. its own delay is announced to drop from 7 days to zero, and a new guardian (a plain key) is announced;
  3. the Safe that administers it, idle for 41 days, executed three transactions;
  4. the balance it holds fell by 80 percent since the previous run.

NOTHING HERE HAPPENED. The events are invented, written only into a copy that is deleted when the command ends; the real files are never touched and nothing leaves the machine.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, LABEL, norm  # noqa: E402
from dossier import utf8_stdout  # noqa: E402


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001


def pick(W, chain=None, target=None):
    """(chain key, address) of the contract to play the events on: the one asked for, else the tracked EVM contract with the most TVL attached."""
    tvl = (load(os.path.join(W, "tvl.json")) or {}).get("matched") or {}
    tracked = set()
    for slug, key in WATCH_SLUGS.items():
        d = load(os.path.join(W, "scores", slug + ".json")) or {}
        for t in d.get("targets", []): tracked.add(key + ":" + norm(t["target"]))
    if chain and target:
        ka = chain + ":" + norm(target)
        return (chain, norm(target)) if ka in tracked else None
    best = max((k for k in tracked if (tvl.get(k) or {}).get("tvl")), key=lambda k: tvl[k]["tvl"], default=None)
    return tuple(best.split(":", 1)) if best else None


def inject(T, chain, addr, now=None):
    """Write the four events into the state files of the copy T. Returns the contract key."""
    now = int(now or time.time()); ka = chain + ":" + addr; prev_run = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 6 * 3600)); at = now + 2 * 86400
    json.dump({"generated_utc": prev_run, "paused": [ka], "changes": [{"target": ka, "change": "paused"}],
               "by_target": {ka: {"paused": True, "via": "paused()", "since": prev_run, "change": "paused", "from": False, "previous_run": prev_run}}}, open(os.path.join(T, "pause_state.json"), "w"))
    json.dump({"by_target": {ka: {"roles": {}, "pending": {"timelock": {"seconds": 0, "current_seconds": 604800, "valid_at": at, "shorter": True}, "guardian": {"kind": "eoa", "holder": "0x1234…abcd", "valid_at": at}}}},
               "changes": [{"target": ka, "role": "pendingTimelock()", "change": "announced", "from_seconds": 604800, "to_seconds": 0, "shorter": True, "valid_at": at},
                           {"target": ka, "role": "pendingGuardian()", "change": "announced", "to": "0x1234…abcd", "to_kind": "eoa", "valid_at": at}]}, open(os.path.join(T, "side_roles.json"), "w"))
    json.dump({"generated_utc": prev_run, "safes": 1, "woke": [chain + ":0xdeadbe…ef01"], "never_executed": [],
               "changes": [{"safe": chain + ":0xdead…ef01", "woke": True, "delta": 3, "idle_days": 41.0, "governs": [ka], "previous_run": prev_run}],
               "by_safe": {"demo": {"safe": chain + ":0xdead…ef01", "nonce": 112, "idle_since": prev_run, "last_moved": prev_run, "governs": [ka]}}}, open(os.path.join(T, "safe_activity.json"), "w"))
    json.dump({"by_target": {ka: {"symbol": "USDC", "prev_amount": 2_701_800_000.0, "amount": 540_360_000.0, "amount_change_pct": -80.0, "price_usd": 1.0, "held_usd": 540_360_000.0, "prev_at": prev_run}}}, open(os.path.join(T, "held_assets.json"), "w"))
    return ka


def run(cmd):
    # PYTHONUTF8: the Watch scripts write their files without naming an encoding (they run on a UTF-8 runner); on a Windows code page they would stop on '…'. The environment is set here, not in them.
    r = subprocess.run([sys.executable, "-W", "ignore"] + cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))   # an inherited PYTHONIOENCODING would win over PYTHONUTF8 for the standard streams
    return r.returncode, (r.stdout + r.stderr)


def play(W, rules, T, chain, addr):
    """Run the real scripts on the copy T. Returns {alerts, queue, dossier, metrics} as parsed data or text."""
    S = HERE; data = os.path.join(T, "data"); os.makedirs(data, exist_ok=True)
    def evaluate():
        rc, log = run([os.path.join(S, "evaluate_rules.py"), "--rules", rules, "--scores", os.path.join(T, "scores"), "--latest", os.path.join(T, "latest.json"), "--tvl", os.path.join(T, "tvl.json"),
                   "--pause", os.path.join(T, "pause_state.json"), "--side", os.path.join(T, "side_roles.json"), "--safe", os.path.join(T, "safe_activity.json"), "--held", os.path.join(T, "held_assets.json"),
                   "--pending", os.path.join(T, "pending_ops.json"), "--prev", os.path.join(T, "prev"), "--second-opinion", os.path.join(T, "second_opinion.json"), "--disputes", os.path.join(T, "disputes.json"), "--out", os.path.join(T, "alerts.json")])
        if rc: raise RuntimeError("evaluate_rules failed: " + log[-400:])
        return load(os.path.join(T, "alerts.json")) or {}
    before = {(x.get("rule"), str(x.get("target")).lower()) for x in evaluate().get("active", [])}   # what the real files already fire, before any invented event
    ka = inject(T, chain, addr); after = evaluate()
    rc, log = run([os.path.join(S, "review_queue.py"), "--watch", T, "--data", data, "--out", os.path.join(T, "review_queue.json"), "--md", os.path.join(T, "review_queue.md")])
    if rc: raise RuntimeError("review_queue failed: " + log[-400:])
    rc, dossier = run([os.path.join(S, "dossier.py"), chain, addr, "--watch", T])
    rc2, log2 = run([os.path.join(S, "metrics_prom.py"), "--watch", T])
    mine = [x for x in after.get("active", []) if (x.get("rule"), str(x.get("target")).lower()) not in before]
    return {"key": ka, "alerts": mine, "already": len(before), "queue": load(os.path.join(T, "review_queue.json")) or {}, "dossier": dossier if rc == 0 else "dossier failed:\n" + dossier, "metrics_rc": rc2,
            "metrics": open(os.path.join(T, "metrics.prom")).read() if os.path.exists(os.path.join(T, "metrics.prom")) else ""}


def report(res):
    out = ["SYNTHETIC EVENTS on a copy of the real files: nothing below happened, nothing was written to the real folder.", "", "Contract: %s" % res["key"], "", "== Alerts the invented events fire (evaluate_rules.py) =="]
    for x in sorted(res["alerts"], key=lambda x: {"high": 0, "medium": 1}.get(x.get("severity"), 2)): out.append("  [%s] %s" % (x.get("severity"), x.get("rule")))
    out.append("  (%d alert(s) the real files already fire are not listed: only what the invented events add)" % res["already"])
    out += ["", "== What needs a person (review_queue.py) =="]
    for x in res["queue"].get("items", []):
        if x.get("target") and str(x["target"]).lower() in res["key"]: out.append("  priority %s: %s: %s" % (x.get("priority"), x.get("kind"), x.get("text")))
    out += ["", "== What a monitor sees (metrics_prom.py) =="] + ["  " + l for l in res["metrics"].split("\n") if l.startswith("aro_alerts_active") or l.startswith("aro_contracts_paused") or l.startswith("aro_safes_woke")]
    out += ["", "== The contract's dossier (dossier.py), with the invented events in it =="] + ["  " + l for l in res["dossier"].split("\n")]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--rules", default="rules.json"); ap.add_argument("--chain"); ap.add_argument("--target"); a = ap.parse_args(); utf8_stdout()
    choice = pick(a.watch, a.chain, a.target)
    if not choice: print("no tracked contract to play the events on (--chain and --target must name a tracked one)"); sys.exit(2)
    T = tempfile.mkdtemp(prefix="aro-demo-")
    try:
        shutil.copytree(a.watch, T, dirs_exist_ok=True, ignore=shutil.ignore_patterns("who_controls.json", "*.txt", "*.log"))   # the signer index is never copied, even to a temporary folder
        print(report(play(a.watch, a.rules, T, *choice)))
    finally: shutil.rmtree(T, ignore_errors=True)


if __name__ == "__main__":
    main()
