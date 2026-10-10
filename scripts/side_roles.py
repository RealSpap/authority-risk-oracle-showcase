#!/usr/bin/env python3
"""The other hands on a contract: who holds its secondary roles, and did one change hands since the previous run. watch/side_roles.json.

The score and the independent reader look at the admin. A contract also has roles the admin handed out: a curator that decides what a
vault may do, a guardian, a pauser. 28 of the 161 tracked EVM contracts answer at least one of these getters on 10/10 (21 curator(),
7 guardian(), 4 pauseGuardian(), 3 pauser()); nothing said who held them. For each: the holder, and what it is (a plain key, a Safe
t-of-n, a timelock with its delay, another contract). A role changing hands, appearing or being cleared fires a medium alert.

    python3 scripts/side_roles.py --scores watch/scores --out watch/side_roles.json

The role is named by the getter that answered, never by what it is assumed to do: in a MetaMorpho vault guardian() can revoke a pending
change, in another protocol it may pause. A plain key is published shortened (0x1234...abcd), a Safe or a timelock whole in by_target (the job
redacts the file like the others: a Safe that also signs elsewhere is shortened, the index of who shares a key is never published), signers
of a Safe never (only the threshold and the count). The changes, which travel into the feeds and the alert texts, carry shortened addresses only. A call nobody answered keeps the previous role, marked stale; an answered zero address
is a role cleared. A MetaMorpho-style vault also announces a new guardian (pendingGuardian()) or a new delay (pendingTimelock()) before it applies: that
is an "announced" change with the time it applies, and a delay announced shorter than the current timelock() is flagged, because that is the owner
lowering the time users have to react (none was pending on 10/10; 10 vaults expose the getters). A holder that cannot be classified is "unread", never "plain key".
"""
import argparse, glob, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from second_opinion import MAINNET, rpc_batch, addr_of, short, delegation, is_plain  # noqa: E402
from evaluate_rules import WATCH_SLUGS  # noqa: E402

ROLES = {"pauser()": "0x9fd0506d", "guardian()": "0x452a9320", "curator()": "0xe66f53b7", "pauseGuardian()": "0x24a3d622",
         "emergencyGuardian()": "0xbc394350", "emergencyAdmin()": "0x70905dce", "getEmergencyAdmin()": "0xddcaa9ea"}   # keccak checked 10/10
SEL = {"getThreshold": "0xe75235b8", "getOwners": "0xa0e67e2b", "getMinDelay": "0xf27a0c92"}
PENDING = ("0x762c31ba", "0x7cc4d9a1", "0xd33219b4")   # pendingGuardian(), pendingTimelock(), timelock(): a MetaMorpho vault announces a new guardian or a new delay before it applies (keccak checked 10/10)


def classify(addr, code, thr, owners, delay):
    """What a role holder is, from four reads; None for a read nobody answered (never read as 'plain key')."""
    if code is None: return {"kind": "unread"}
    if is_plain(code): return dict({"kind": "eoa"}, **({"delegated_to": delegation(code)} if delegation(code) else {}))   # a plain key, with or without an EIP-7702 delegation
    if thr and len(thr) == 66 and int(thr, 16) > 0 and owners and len(owners) >= 130:
        return {"kind": "safe", "threshold": int(thr, 16), "owners": int(owners[66:130], 16)}
    if delay and len(delay) == 66 and int(delay, 16) > 0: return {"kind": "timelock", "delay_seconds": int(delay, 16)}
    return {"kind": "contract"}


def describe(rec):
    k = rec.get("kind")
    return {"eoa": "a plain key", "safe": "a Safe %s-of-%s" % (rec.get("threshold"), rec.get("owners")), "timelock": "a timelock of %s h" % ((rec.get("delay_seconds") or 0) // 3600),
            "contract": "a contract", "unread": "not read"}.get(k, str(k))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--out", default="watch/side_roles.json"); a = ap.parse_args()
    try: prev = json.load(open(a.out)); prev_by = prev.get("by_target") or {}
    except Exception: prev, prev_by = {}, {}  # noqa: BLE001
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); by_target, changes, asked, stale, unread = {}, [], 0, 0, []
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5]); url = MAINNET.get(key)
        if not url: continue
        ts = [t["target"] for t in json.load(open(f)).get("targets", [])]; asked += len(ts); names = list(ROLES)
        r = rpc_batch(url, [("eth_call", [{"to": t, "data": ROLES[n]}, "latest"]) for t in ts for n in names])
        if ts and all(x is None for x in r): unread.append(key)
        holders = {}   # (target, role) -> address | None (cleared) | "?" (not answered)
        for i, t in enumerate(ts):
            for j, n in enumerate(names):
                v = r[len(names) * i + j]
                if v is None: holders[(t, n)] = "?"
                elif v and len(v) == 66: holders[(t, n)] = addr_of(v) or None   # an answered zero address is a role cleared
        rp = rpc_batch(url, [("eth_call", [{"to": t, "data": d}, "latest"]) for t in ts for d in PENDING])   # a vault announces a change of guardian or of delay before it applies
        pending_raw = {t: rp[3 * i:3 * i + 3] for i, t in enumerate(ts)}
        pend_guardians = {t.lower(): addr_of(g[:66]) for t, (g, _tl, _cur) in pending_raw.items() if g and len(g) >= 130 and addr_of(g[:66])}
        addrs = sorted({h.lower() for h in holders.values() if h and h != "?"} | {a_.lower() for a_ in pend_guardians.values()})
        rr = rpc_batch(url, [c for h in addrs for c in (("eth_getCode", [h, "latest"]), ("eth_call", [{"to": h, "data": SEL["getThreshold"]}, "latest"]), ("eth_call", [{"to": h, "data": SEL["getOwners"]}, "latest"]), ("eth_call", [{"to": h, "data": SEL["getMinDelay"]}, "latest"]))]) if addrs else []
        kinds = {h: classify(h, *rr[4 * i:4 * i + 4]) for i, h in enumerate(addrs)}
        for t in ts:
            ka = key + ":" + t.lower(); roles, pv = {}, (prev_by.get(ka) or {}).get("roles") or {}
            for n in names:
                h = holders.get((t, n), "")
                if h == "?":   # nobody answered: the previous role stays, marked, and says nothing
                    if n in pv: roles[n] = dict(pv[n], stale=True); stale += 1
                    continue
                if h:
                    k = kinds.get(h.lower(), {"kind": "unread"}); shown = short(h) if k["kind"] == "eoa" else h
                    roles[n] = dict(k, holder=shown, self=(h.lower() == t.lower()) or None)
                    roles[n] = {x: y for x, y in roles[n].items() if y is not None}
                p = pv.get(n)
                if p and key + ":" + t.lower() in prev_by:   # also when the previous record is stale (kept from a run where nobody answered): its holder is the last one READ, so a handover that happened during the outage is told when the call answers again
                    if h and p.get("holder") != roles[n]["holder"] and short(str(p.get("holder"))) != short(roles[n]["holder"]):
                        changes.append({"target": ka, "role": n, "change": "changed", "from": short(p.get("holder")), "from_kind": p.get("kind"), "to": short(roles[n]["holder"]), "to_kind": roles[n]["kind"]})
                    elif not h: changes.append({"target": ka, "role": n, "change": "cleared", "from": short(p.get("holder")), "from_kind": p.get("kind"), "to": None, "to_kind": None})
                elif h and (t.lower() and key + ":" + t.lower() in prev_by) and not p:
                    changes.append({"target": ka, "role": n, "change": "added", "from": None, "from_kind": None, "to": short(roles[n]["holder"]), "to_kind": roles[n]["kind"]})
            g, tl, cur = pending_raw.get(t, (None, None, None)); pend, ppv = {}, (prev_by.get(ka) or {}).get("pending") or {}
            if g is None or tl is None:   # a call nobody answered: the previous announcement stays, marked, and says nothing
                if ppv: pend = {k_: dict(v_, stale=True) for k_, v_ in ppv.items()}; stale += 1
            else:
                ok_ts = lambda w: w == 0 or 1_500_000_000 <= w <= 4_200_000_000   # a validAt is a Unix time: any other second word is not this getter's shape (an (address, bool) pair, say)
                if len(g) >= 130 and (addr_of(g[:66]) or int(g[66:130], 16)) and ok_ts(int(g[66:130], 16)):
                    ga = addr_of(g[:66]); kg = kinds.get(ga.lower(), {"kind": "unread"}) if ga else {}
                    pend["guardian"] = {x: y for x, y in dict(kg, holder=(short(ga) if (ga and kg.get("kind") == "eoa") else ga), valid_at=int(g[66:130], 16)).items() if y is not None}
                if len(tl) >= 130 and (int(tl[2:66], 16) or int(tl[66:130], 16)) and ok_ts(int(tl[66:130], 16)):
                    secs = int(tl[2:66], 16); cur_s = int(cur, 16) if cur and len(cur) == 66 else None
                    pend["timelock"] = {x: y for x, y in {"seconds": secs, "current_seconds": cur_s, "valid_at": int(tl[66:130], 16), "shorter": True if (cur_s is not None and secs < cur_s) else None}.items() if y is not None}
                for k_, role in (("guardian", "pendingGuardian()"), ("timelock", "pendingTimelock()")):
                    new_, old_ = pend.get(k_), ppv.get(k_)
                    if new_ and not (old_ and not old_.get("stale") and all((short(old_.get(f_)) == short(new_.get(f_))) if f_ == "holder" else (old_.get(f_) == new_.get(f_)) for f_ in ("holder", "seconds", "valid_at"))):   # announced, or changed since the previous run (holders compared in short form: the job redacts the file in place, a Safe that signs elsewhere comes back shortened)
                        ch = {"target": ka, "role": role, "change": "announced", "valid_at": new_.get("valid_at")}
                        if k_ == "guardian": ch.update({"to": new_.get("holder"), "to_kind": new_.get("kind")})
                        else: ch.update({"from_seconds": new_.get("current_seconds"), "to_seconds": new_.get("seconds"), "shorter": new_.get("shorter")})
                        changes.append(ch)
            if roles or pend: by_target[ka] = dict({"roles": roles} if roles else {}, **({"pending": pend} if pend else {}))
    plain = sorted(k for k, v in by_target.items() if any(x.get("kind") == "eoa" and not x.get("stale") for x in (v.get("roles") or {}).values()))
    out = {"generated_utc": now, "asked": asked, "count": len(by_target), "pending": sorted(k for k, v in by_target.items() if any(not x.get("stale") for x in (v.get("pending") or {}).values())), "plain_key_roles": plain, "changes": changes, "stale": stale, "unread_chains": unread, "previous_run": prev.get("generated_utc"), "by_target": by_target,
           "what": "the secondary roles of the tracked EVM contracts (pauser, guardian, curator, pauseGuardian, emergencyGuardian, emergencyAdmin) named by the getter that answered, who holds each (plain key shortened, Safe as threshold and count, timelock with its delay, contract) and the changes since the previous run; a call nobody answered keeps the previous role marked stale; read by scripts/side_roles.py"}
    json.dump(out, open(a.out + ".tmp", "w"), indent=1); os.replace(a.out + ".tmp", a.out)
    for c in changes: print("ROLE CHANGE %s %s: %s%s" % (c["target"][:40], c["role"], c["change"], " (a SHORTER delay)" if c.get("shorter") else ""))
    print("side_roles.json: %d contract(s) with a secondary role, %d held by a plain key, %d change(s), %d kept stale%s" % (len(by_target), len(plain), len(changes), stale, (", chain(s) not read: " + ", ".join(unread)) if unread else ""))


if __name__ == "__main__":
    main()
