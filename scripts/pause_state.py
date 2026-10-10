#!/usr/bin/env python3
"""Is the contract paused, and did that change since the previous run? watch/pause_state.json.

A paused contract cannot be withdrawn from or traded against: either an incident is being contained (a guardian pulled the brake) or the
admin holds the users' funds hostage. Nobody was watching the state. 28 of the 161 EVM targets answer paused() (25) or isPaused() (3);
none was paused on 10/10. What matters is the move: running -> paused fires a high alert (evaluate_rules.py), paused -> running an info one.

    python3 scripts/pause_state.py --scores watch/scores --out watch/pause_state.json

A contract that does not answer (no such getter, a different return type) is absent, never "running". A contract that answered last run
and does not now keeps its previous record, marked stale (a dead RPC is not an unpaused contract); a stale record never fires.
"""
import argparse, glob, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from second_opinion import MAINNET, rpc_batch  # noqa: E402
from evaluate_rules import WATCH_SLUGS  # noqa: E402

SEL = {"paused()": "0x5c975abb", "isPaused()": "0xb187bd26"}   # keccak checked 10/10


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--out", default="watch/pause_state.json"); a = ap.parse_args()
    try: prev = json.load(open(a.out)); prev_by = prev.get("by_target") or {}
    except Exception: prev, prev_by = {}, {}  # noqa: BLE001
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); by_target, changes, asked, stale, unread = {}, [], 0, 0, []
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5]); url = MAINNET.get(key)
        if not url: continue
        ts = [t["target"] for t in json.load(open(f)).get("targets", [])]; asked += len(ts)
        r = rpc_batch(url, [("eth_call", [{"to": t, "data": s}, "latest"]) for t in ts for s in SEL.values()])
        if ts and all(x is None for x in r): unread.append(key)
        for i, t in enumerate(ts):
            ka = key + ":" + t.lower(); got = None
            for j, name in enumerate(SEL):
                v = r[2 * i + j]
                if v and len(v) == 66 and int(v, 16) in (0, 1): got = (name, bool(int(v, 16))); break   # a bool; any other word is not this getter
            pv = prev_by.get(ka)
            if got is None:
                # unanswered (None) or no getter (""): a contract that answered before keeps its record, stale
                if pv: by_target[ka] = dict(pv, stale=True, stale_since=pv.get("stale_since") or prev.get("generated_utc")); stale += 1
                continue
            rec = {"paused": got[1], "via": got[0], "since": (pv or {}).get("since") if (pv and pv.get("paused") == got[1]) else (now if pv else None)}
            if pv and pv.get("paused") != got[1]:   # also against a stale record: it holds the last state READ, so a pause that happened while the call went unanswered is still told (before 2026-10-10 it was not, and the alert rule fires on the change only)
                last_read = (pv.get("stale_since") or prev.get("generated_utc")) if pv.get("stale") else prev.get("generated_utc")   # stale_since = the run at which this state was last read
                rec["change"] = "paused" if got[1] else "unpaused"; rec["from"] = pv.get("paused"); rec["previous_run"] = last_read
                changes.append({"target": ka, "change": rec["change"], "since": last_read})
            by_target[ka] = rec
    paused = sorted(k for k, v in by_target.items() if v.get("paused") and not v.get("stale"))
    out = {"generated_utc": now, "asked": asked, "count": len(by_target), "paused": paused, "changes": changes, "stale": stale, "unread_chains": unread, "by_target": by_target,
           "what": "pause state of the tracked EVM contracts that expose paused() or isPaused(): `paused` lists the paused ones, `changes` the flips since the previous run (running to paused, paused to running); a contract without the getter is absent, not running; a record kept from the previous run for a call that went unanswered is marked stale and never fires; read by scripts/pause_state.py"}
    json.dump(out, open(a.out + ".tmp", "w"), indent=1); os.replace(a.out + ".tmp", a.out)
    for c in changes: print("PAUSE CHANGE %s: %s" % (c["target"][:44], c["change"]))
    print("pause_state.json: %d contract(s) answer, %d paused, %d change(s), %d kept stale%s" % (len(by_target), len(paused), len(changes), stale, (", chain(s) not read: " + ", ".join(unread)) if unread else ""))


if __name__ == "__main__":
    main()
