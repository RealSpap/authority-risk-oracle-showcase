#!/usr/bin/env python3
"""Who holds the admin role of a contract whose holders cannot be listed? watch/admin_probe.json.

An AccessControl contract that does not enumerate its role members (no getRoleMember) keeps its holders in RoleGranted events, which public RPCs
cannot return over a long range. The independent reader calls such a target "unreadable". But a question that has a one-word answer can still be asked:
hasRole(DEFAULT_ADMIN_ROLE, X) for every contract the reader already knows as an admin elsewhere (Safes, timelocks, other contracts, in the same chain). A yes is
proof; a no proves nothing about holders nobody asked about, so this file never says "the admin is X", it says "X holds the admin role", and `complete` is always false.

    python3 scripts/admin_probe.py --second-opinion watch/second_opinion.json --out watch/admin_probe.json

Only an AccessControl-style contract is probed: hasRole(0, address(0)) must answer a boolean word, false. Plain keys are not candidates (the published file shortens them,
and a probe by shortened address is impossible). The Tempo precompiles order hasRole(account, role) the other way round and are left out. A call that goes unanswered is
counted, never read as a no: a target where no candidate answered gets no record.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from second_opinion import MAINNET, rpc_batch  # noqa: E402

HAS_ROLE = "0x91d14854"   # hasRole(bytes32,address), keccak checked 10/10
ZERO32 = "0" * 64
SKIP_CHAINS = {"tempo"}   # TIP-20: hasRole(account, role)


def word(addr): return str(addr)[2:].lower().rjust(64, "0")


def candidates(so):
    """{chain: {address: description}} from the independent read: the contract holders (Safe, timelock, other contract) and the Safes behind a bare-contract holder, whole addresses only."""
    out = {}
    def add(chain, addr, d):
        a = str(addr or "").lower()
        if len(a) == 42 and a.startswith("0x"): out.setdefault(chain, {}).setdefault(a, d)   # a shortened address (redaction) is not 42 characters
    for r in (so or {}).get("results", []):
        if r.get("chain") not in MAINNET or r.get("chain") in SKIP_CHAINS: continue
        if r.get("kind") in ("safe", "timelock", "contract"): add(r["chain"], r.get("holder"), {k: r.get(k) for k in ("kind", "threshold", "owners", "delay_seconds") if r.get(k) is not None})
        b = r.get("behind") or {}
        if b.get("kind") in ("safe", "timelock", "contract"): add(r["chain"], b.get("address"), {k: b.get(k) for k in ("kind", "threshold", "owners", "delay_seconds") if b.get(k) is not None})
    return out


def as_int(w):
    """A 32-byte hex word as an integer; anything else (None, a short answer, junk that is not hex) is None, never an exception."""
    if not isinstance(w, str) or len(w) != 66 or not w.startswith("0x"): return None
    try: return int(w, 16)
    except ValueError: return None


def is_access_control(w):
    """hasRole(0, address(0)) answers false as a 32-byte boolean word: the shape of an AccessControl, whatever ERC-165 says."""
    return as_int(w) == 0


def holds(w):
    return as_int(w) == 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--second-opinion", default="watch/second_opinion.json"); ap.add_argument("--out", default="watch/admin_probe.json"); a = ap.parse_args()
    try: so = json.load(open(a.second_opinion))
    except Exception: so = None  # noqa: BLE001 -- no independent read this run: nothing to probe
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); cands = candidates(so); by_target, unreadable = {}, 0
    for chain in sorted({r["chain"] for r in (so or {}).get("results", []) if r.get("kind") == "unreadable" and r.get("chain") in MAINNET and r.get("chain") not in SKIP_CHAINS}):
        ts = [r["target"] for r in so["results"] if r.get("chain") == chain and r.get("kind") == "unreadable"]; unreadable += len(ts); url = MAINNET[chain]
        shape = rpc_batch(url, [("eth_call", [{"to": t, "data": HAS_ROLE + ZERO32 + ZERO32}, "latest"]) for t in ts])
        cl = sorted(cands.get(chain, {}))
        for t, sh in zip(ts, shape):
            if not is_access_control(sh) or not cl: continue
            ans = rpc_batch(url, [("eth_call", [{"to": t, "data": HAS_ROLE + ZERO32 + word(c)}, "latest"]) for c in cl])
            answered = sum(1 for x in ans if as_int(x) in (0, 1))   # a word that is not a boolean is not an answer to hasRole
            if not answered: continue   # nobody answered: no record, never "no holder"
            held = [dict(holder=c, **cands[chain][c]) for c, x in zip(cl, ans) if holds(x)]
            by_target[chain + ":" + str(t).lower()] = {"role": "DEFAULT_ADMIN_ROLE", "method": "hasRole(DEFAULT_ADMIN_ROLE, known holder)", "probed": len(cl), "answered": answered, "holders": held, "complete": False}
    seen = sorted(k for k, v in by_target.items() if v["holders"])
    out = {"generated_utc": now, "unreadable_targets": unreadable, "probed_targets": len(by_target), "with_holder": seen, "by_target": by_target,
           "what": "for a contract whose role holders cannot be listed, the known contracts (Safes, timelocks, others read as an admin elsewhere, same chain) that hold DEFAULT_ADMIN_ROLE; a yes is proof, absence proves nothing, `complete` is always false; plain keys are not probed"}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out + ".tmp", "w"), indent=1); os.replace(a.out + ".tmp", a.out)
    for k in seen: print("ADMIN ROLE SEEN %s: %s" % (k[:48], ", ".join(h["holder"][:10] + "(" + str(h.get("kind")) + ")" for h in by_target[k]["holders"])))
    print("admin_probe.json: %d unreadable target(s), %d probed, %d with a known holder" % (unreadable, len(by_target), len(seen)))


if __name__ == "__main__":
    main()
