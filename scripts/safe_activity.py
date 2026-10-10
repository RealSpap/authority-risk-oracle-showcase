#!/usr/bin/env python3
"""Did a Safe that governs tracked contracts just wake up? watch/safe_activity.json.

A multisig that has not executed anything for weeks and suddenly does is the one thing a calm admin path does before an upgrade, a
parameter change or a key compromise. Nobody was watching it: the watch saw an admin change (the holder), a queued operation (the
timelock) and a role announced in advance, not the admin Safe itself moving. Each Safe that is the admin of a tracked contract (a holder or the owner
behind a bare-contract holder, read by second_opinion.py) is asked for nonce(): the number of transactions it has executed.

    python3 scripts/safe_activity.py --second-opinion watch/second_opinion.json --out watch/safe_activity.json

What the file can say is bounded by the runs it has seen: `idle_since` is the first run that read the current nonce, so "idle for 14 days"
means "observed unchanged for 14 days", and a cold start fires nothing. A Safe whose nonce moved after an idle stretch of `wake_days` or more is
listed under `woke` with the contracts it governs; a smaller move is a change without a wake (an active treasury moves every day). A Safe that does not
answer keeps its previous record, marked stale (a dead RPC is not an idle Safe), and a stale record never fires.
"""
import argparse, calendar, hashlib, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from second_opinion import MAINNET, rpc_batch, short  # noqa: E402

NONCE = "0xaffed0e0"   # nonce(), keccak checked 10/10
WAKE_DAYS = 14


def utc_s(t):
    try: return calendar.timegm(time.strptime(t, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError): return None


def parse_nonce(word):
    """A Safe nonce is a uint256 word; anything else (no getter, a revert, a short answer) is not this getter."""
    if not isinstance(word, str) or len(word) != 66: return None
    try: n = int(word, 16)
    except ValueError: return None
    return n if n < 2 ** 40 else None   # a counter of transactions; a larger word is another getter's answer


def step(pv, nonce, now_utc, wake_days=WAKE_DAYS):
    """(record, change) for one Safe: pv the previous record (or None), nonce the value read now. A stale previous record is compared like any other,
    a move during a gap in reading is still a move and its idle time is still known."""
    now_s = utc_s(now_utc)
    rec = {"nonce": nonce, "observed_since": (pv or {}).get("observed_since") or now_utc}
    if not pv or not isinstance(pv.get("nonce"), int):
        rec["idle_since"] = now_utc; return rec, None   # first read: nothing to compare with
    since = pv.get("idle_since") or pv.get("observed_since") or now_utc
    if nonce == pv["nonce"]:
        rec["idle_since"] = since
        if pv.get("last_moved"): rec["last_moved"] = pv["last_moved"]
        return rec, None
    rec["idle_since"] = now_utc; rec["last_moved"] = now_utc
    if nonce < pv["nonce"]: return rec, {"regressed": True, "delta": None, "idle_days": None, "woke": False}   # a nonce never goes down: the Safe was replaced, no wake claimed
    idle_s = max(0, now_s - (utc_s(since) or now_s))
    return rec, {"delta": nonce - pv["nonce"], "idle_days": int(idle_s / 86400 * 10) / 10, "woke": idle_s >= wake_days * 86400}


def safe_key(chain, addr):
    """The record's key: the chain and a hash of the Safe's address, never the address. The redaction step shortens, in place, every address of the signer index that is not
    a tracked target, and a Safe can sign elsewhere: a key made of the address would stop matching on the next run and the idle memory would restart from zero every time."""
    return chain + ":" + hashlib.sha256(addr.lower().encode()).hexdigest()[:16]


def safes_of(so):
    """{(chain, safe address): [governed targets]} from the independent reader: a Safe holder, and the Safe behind a bare-contract holder."""
    out = {}
    for r in (so or {}).get("results", []):
        if r.get("chain") not in MAINNET: continue
        tk = r["chain"] + ":" + str(r["target"]).lower()
        if r.get("kind") == "safe" and r.get("holder"): out.setdefault((r["chain"], str(r["holder"]).lower()), set()).add(tk)
        b = r.get("behind") or {}
        if b.get("kind") == "safe" and b.get("address"): out.setdefault((r["chain"], str(b["address"]).lower()), set()).add(tk)
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--second-opinion", default="watch/second_opinion.json"); ap.add_argument("--out", default="watch/safe_activity.json"); a = ap.parse_args()
    try: so = json.load(open(a.second_opinion))
    except Exception: so = None  # noqa: BLE001 -- no independent read this run: nothing to ask, previous file kept below
    try: prev = json.load(open(a.out)); prev_by = prev.get("by_safe") or {}
    except Exception: prev, prev_by = {}, {}  # noqa: BLE001
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); safes = safes_of(so); by_safe, changes, stale, unread = {}, [], 0, []
    for chain in sorted({c for c, _ in safes}):
        keys = sorted(s for c, s in safes if c == chain)
        r = rpc_batch(MAINNET[chain], [("eth_call", [{"to": s, "data": NONCE}, "latest"]) for s in keys])
        if all(x is None for x in r): unread.append(chain)
        for s, word in zip(keys, r):
            k = safe_key(chain, s); label = chain + ":" + short(s); gov = sorted(safes[(chain, s)]); n = parse_nonce(word); pv = prev_by.get(k)
            if n is None:
                if pv: by_safe[k] = dict(pv, stale=True, stale_since=pv.get("stale_since") or prev.get("generated_utc"), governs=gov, safe=label); stale += 1
                continue
            rec, ch = step(pv, n, now); rec["governs"] = gov; rec["safe"] = label; rec["never_executed"] = (n == 0); by_safe[k] = rec
            if ch: changes.append(dict(ch, safe=label, governs=gov, previous_run=prev.get("generated_utc")))
    woke = sorted(c["safe"] for c in changes if c.get("woke"))
    out = {"generated_utc": now, "wake_days": WAKE_DAYS, "safes": len(safes), "read": sum(1 for v in by_safe.values() if not v.get("stale")), "woke": woke, "changes": changes,
           "never_executed": sorted(v["safe"] for v in by_safe.values() if v.get("never_executed")), "stale": stale, "unread_chains": unread, "by_safe": by_safe,
           "what": "records are keyed by chain and a hash of the Safe address, labelled with the shortened address; the nonce (transactions executed) of every Safe that is the admin of a tracked contract, read by scripts/safe_activity.py; `idle_since` is the first run that read the current nonce, so idle time is observed time; `changes` lists the Safes whose nonce moved since the previous run, `woke` those that moved after wake_days or more unchanged, with the contracts they govern; `never_executed` lists the Safes still at nonce 0 (an admin path that has never been used); a Safe that does not answer keeps its record, marked stale"}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out + ".tmp", "w"), indent=1); os.replace(a.out + ".tmp", a.out)
    for c in changes:
        if c.get("woke"): print("SAFE WOKE %s: +%s after %s days idle, governs %d contract(s)" % (c["safe"][:48], c["delta"], c["idle_days"], len(c["governs"])))
    print("safe_activity.json: %d Safe(s), %d read, %d moved, %d woke, %d never executed, %d kept stale%s" % (len(safes), out["read"], len(changes), len(woke), len(out["never_executed"]), stale, (", chain(s) not read: " + ", ".join(unread)) if unread else ""))


if __name__ == "__main__":
    main()
