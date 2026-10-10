#!/usr/bin/env python3
"""What this watch sees, and does not see, on each chain: one record per chain built from the files the run just wrote, no RPC.
A reader of a score should know that on some chains the Safe events are not read, the timelock queues are not watched, or the
independent reader cannot classify the admin. watch/coverage.json says it per chain, with the blind spots in words.

    python3 scripts/coverage.py --watch watch --out watch/coverage.json
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, PENDING_CHAIN, norm  # noqa: E402


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001 -- a missing file is a blind spot, reported below


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--out", default="watch/coverage.json"); a = ap.parse_args(); W = a.watch
    so, sc, po, tvl = load(os.path.join(W, "second_opinion.json")), load(os.path.join(W, "safe_changes.json")), load(os.path.join(W, "pending_ops.json")), load(os.path.join(W, "tvl.json"))
    held = (load(os.path.join(W, "held_assets.json")) or {}).get("by_target", {})   # since 2026-10-10: a vault DefiLlama lists no protocol for still has a money figure, what it holds by its own account
    pz, sr, sa, ap = (load(os.path.join(W, n)) for n in ("pause_state.json", "side_roles.json", "safe_activity.json", "admin_probe.json"))   # since 2026-10-10: what each state mechanism actually sees (None = the file is missing: not read this run)
    def per_chain(d, keyed):
        """{chain: count} of the non-stale records of a state file keyed <chain>:<something>; None when the file is missing."""
        if d is None: return None
        out = {}
        for k, v in (d.get(keyed) or {}).items():
            if not (v or {}).get("stale"): out[str(k).split(":", 1)[0]] = out.get(str(k).split(":", 1)[0], 0) + 1
        return out
    n_pause, n_roles, n_safes, n_probe = per_chain(pz, "by_target"), per_chain(sr, "by_target"), per_chain(sa, "by_safe"), per_chain(ap, "by_target")
    chains = {}
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5]) or ("solana" if (load(f) or {}).get("kind") == "solana" else None)
        if not key: continue
        d = load(f) or {}; ts = d.get("targets", [])
        c = chains.setdefault(key, {"oracle": d.get("name"), "targets": 0, "independent_read": {"readable": 0, "unreadable": 0, "native": 0}, "proxies_fingerprinted": 0, "safes": 0, "safes_modules_read": 0, "timelocks_in_admin_path": 0,
                                    "timelock_queues_watched": 0, "safe_events": None, "tvl_matched": 0, "held_read": 0, "pause_answered": None, "roles_read": None, "admin_safes_nonce_read": None, "admin_role_probed": None, "blind_spots": []})
        c["targets"] += len(ts)
        c["tvl_matched"] += sum(1 for t in ts if (tvl or {}).get("matched", {}).get(key + ":" + norm(t["target"]).lower()))
        c["held_read"] += sum(1 for t in ts if not (tvl or {}).get("matched", {}).get(key + ":" + norm(t["target"]).lower()) and (held.get(key + ":" + norm(t["target"]).lower()) or {}).get("held_usd") is not None)   # tvl_match.py writes its keys lowercase, base58 included (norm keeps base58 case; evaluate_rules lowercases too)
    for r in (so or {}).get("results", []):
        c = chains.get(r.get("chain"))
        if not c or r.get("oracle_self"): continue
        k = r.get("kind")
        c["independent_read"]["unreadable" if k == "unreadable" else "native" if k == "native" else "readable"] += 1
        if r.get("impl") or r.get("deployed_slot"): c["proxies_fingerprinted"] += 1   # EVM: the implementation slot; Solana: the ProgramData deployment slot (since 2026-10-10)
        if k == "safe": c["safes"] += 1; c["safes_modules_read"] += 1 if r.get("modules") is not None else 0
        if k == "timelock": c["timelocks_in_admin_path"] += 1
    for tl in (po or {}).get("results", []):
        c = chains.get(PENDING_CHAIN.get(tl.get("chain"), tl.get("chain")))
        if c: c["timelock_queues_watched"] += 1
    for r in (sc or {}).get("results", []):
        c = chains.get(r.get("ecosystem"))
        if c: c["safe_events"] = {"safes": r.get("safes"), "days": r.get("days_read", (sc or {}).get("days")), "status": "ok" if not r.get("status") or str(r["status"]).startswith("ok") else "unread", "why": None if not r.get("status") or str(r["status"]).startswith("ok") else str(r["status"])[:160]}
    for key, c in chains.items():
        if n_pause is not None: c["pause_answered"] = n_pause.get(key, 0)
        if n_roles is not None: c["roles_read"] = n_roles.get(key, 0)
        if n_safes is not None: c["admin_safes_nonce_read"] = n_safes.get(key, 0)
        if n_probe is not None: c["admin_role_probed"] = n_probe.get(key, 0)
        ir = c["independent_read"]; b = c["blind_spots"]
        if ir["unreadable"]: b.append("%d contract(s) where no admin slot, owner() or admin() answers: the independent reader cannot classify their admin" % ir["unreadable"])
        if key != "solana" and c["targets"]:
            if c["pause_answered"] is None: b.append("pause state not read this run (watch/pause_state.json missing): a paused contract is not seen")
            elif c["pause_answered"] < c["targets"]: b.append("paused() or isPaused() answered by %d of %d contracts: a pause on the other %d is not seen, and 'nothing paused' says nothing about them" % (c["pause_answered"], c["targets"], c["targets"] - c["pause_answered"]))
            if c["roles_read"] is None: b.append("secondary roles not read this run (watch/side_roles.json missing)")
            elif c["roles_read"] < c["targets"]: b.append("no pauser, guardian or curator getter answers on %d of %d contracts: a change of those hands is not seen there" % (c["targets"] - c["roles_read"], c["targets"]))
        if c["safes"]:
            if c["admin_safes_nonce_read"] is None: b.append("admin Safe activity not read this run (watch/safe_activity.json missing): a Safe waking up is not seen")
            elif c["admin_safes_nonce_read"] < 1: b.append("no admin Safe nonce read although %d contract(s) have a Safe in their admin path: a Safe waking up is not seen" % c["safes"])
        if ir["unreadable"] and c["admin_role_probed"]: b.append("of the unreadable contracts, %d are AccessControl contracts asked who holds the admin role among the holders already known: a yes proves one holder, never the full list" % c["admin_role_probed"])
        if ir["native"]: b.append("%d native identifier(s) (no code at the address): outside the independent reader's reach, scored by the methodology alone" % ir["native"])
        if c["safes"] and c["safes_modules_read"] < c["safes"]: b.append("modules not read on %d of %d admin Safes this run" % (c["safes"] - c["safes_modules_read"], c["safes"]))
        if c["timelocks_in_admin_path"] and not c["timelock_queues_watched"]: b.append("%d timelock(s) in admin paths but no timelock queue watched on this chain: queued operations are not seen before they execute" % c["timelocks_in_admin_path"])
        if c["safe_events"] is None: b.append("Safe signer, threshold, module and guard events not scanned on this chain" if key != "solana" else "Squads changes read by the independent reader only (no event scan)")
        elif c["safe_events"]["status"] == "unread": b.append("Safe events not read this run (%s)" % (c["safe_events"]["why"] or "RPC"))
        if c["targets"] and c["tvl_matched"] + c["held_read"] < c["targets"]: b.append("no money figure for %d of %d contracts (no DefiLlama protocol, no totalAssets() answered): money at risk not computed for them" % (c["targets"] - c["tvl_matched"] - c["held_read"], c["targets"]))
        if key == "solana" and c["proxies_fingerprinted"] < c["targets"]: b.append("%d program(s) without a deployment slot read (not upgradeable, or ProgramData not answered): an upgrade there is not seen" % (c["targets"] - c["proxies_fingerprinted"]))
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "chains": chains,
           "what": "what the watch sees per chain, from the files of this run: targets, the independent reader's reach (readable / unreadable / native), proxies fingerprinted (an upgrade is seen), admin Safes and those whose modules were read, timelocks in admin paths and timelock queues watched, Safe event scan status, TVL matched; blind_spots in words. Written by scripts/coverage.py after every run"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    print("coverage: %d chain(s), %d blind spot(s) in all" % (len(chains), sum(len(c["blind_spots"]) for c in chains.values())))
    for key, c in chains.items():
        for b in c["blind_spots"]: print("  %s: %s" % (key, b))


if __name__ == "__main__":
    main()
