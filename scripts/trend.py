#!/usr/bin/env python3
"""One line per run, watch/trend.jsonl: the numbers the run measured, so that the next runs can say whether the tracked set is
improving. From the files of the run, no RPC. Appended, never rewritten (a line per run, like history.jsonl).

    python3 scripts/trend.py --watch watch --out watch/trend.jsonl
"""
import argparse, json, os, time


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001


def state_line(cov, pz, sa, ap):
    """How far the state mechanisms reach and what they found, one block per run (since 2026-10-10). A source that is missing leaves its keys out: absent is not zero,
    and a trend that drew a missing file as 0 would show coverage collapsing on the day a step failed."""
    out = {}
    chains = (cov or {}).get("chains") or {}
    for key, field in (("pause_answered", "pause_answered"), ("roles_read", "roles_read"), ("admin_safes_nonce_read", "admin_safes_nonce_read"), ("admin_role_probed", "admin_role_probed")):
        vals = [c.get(field) for c in chains.values() if c.get(field) is not None]
        if vals: out[key] = sum(vals)
    if pz and isinstance(pz.get("paused"), list): out["paused_now"] = len(pz["paused"])
    if sa:
        for k, f in (("admin_safes", "safes"),):
            if isinstance(sa.get(f), int): out[k] = sa[f]
        for k, f in (("safes_woke", "woke"), ("safes_never_executed", "never_executed")):
            if isinstance(sa.get(f), list): out[k] = len(sa[f])
    if ap and isinstance(ap.get("with_holder"), list): out["admin_role_holders_seen"] = len(ap["with_holder"])
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--out", default="watch/trend.jsonl"); a = ap.parse_args(); W = a.watch
    rbc, so, cov, isrc, rq, lat = (load(os.path.join(W, f)) for f in ("risk_by_cause.json", "second_opinion.json", "coverage.json", "impl_sources.json", "review_queue.json", "latest.json"))
    line = {"run_utc": (lat or {}).get("run_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "targets": (lat or {}).get("total_targets"), "stale": (lat or {}).get("stale_total")}
    if rbc: line["tracked_tvl_usd"] = rbc.get("tracked_tvl_usd"); line["causes"] = {k: {"contracts": v.get("contracts"), "tvl_usd": v.get("tvl_usd")} for k, v in (rbc.get("causes") or {}).items()}
    if so:
        line.update({"agree": so.get("agree"), "disagree": so.get("disagree"), "unreadable": so.get("unreadable"), "changed": len(so.get("changed") or []), "upgrades": len(so.get("upgrades") or [])})
        sc = so.get("signer_composition") or {}; line["signers"] = {"multisigs": sc.get("safes"), "signers": sc.get("signers"), "plain_keys": (sc.get("by_kind") or {}).get("eoa"), "keys_only": sc.get("safes_of_plain_keys_only"), "frozen_by_one_key": sc.get("safes_frozen_by_one_lost_key")}
    if cov: line["blind_spots"] = sum(len(c.get("blind_spots") or []) for c in (cov.get("chains") or {}).values())
    if isrc: line["verified_code"] = {"checked": isrc.get("checked"), "verified": isrc.get("verified")}
    st = state_line(cov, *(load(os.path.join(W, f)) for f in ("pause_state.json", "safe_activity.json", "admin_probe.json")))
    if st: line["state"] = st
    if rq: line["review_items"] = rq.get("total"); line["review_overdue"] = rq.get("overdue")
    with open(a.out, "a") as f: f.write(json.dumps(line) + "\n")
    n = sum(1 for _ in open(a.out))
    print("trend: line %d appended (%s)" % (n, line["run_utc"]))


if __name__ == "__main__":
    main()
