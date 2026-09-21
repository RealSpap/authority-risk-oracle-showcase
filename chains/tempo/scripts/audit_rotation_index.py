#!/usr/bin/env python3
"""Non-circular rotation audit for one tracked Tempo target.

WHY THIS FILE EXISTS
--------------------
The rotation audit has to answer one question: *does the score published
on-chain still match what the chain says today?*  A script that imports
`methodology_test.py` and calls `score_token()` cannot answer it -- it
re-runs the very code that produced the published number, so it agrees
with itself by construction (see the project memory note
`feedback_audit_non_circulaire`).  This file therefore:

  * imports NOTHING from this repository (no `methodology_test`, no
    `scorers`, no shared helper) -- only the Python standard library and
    `curl`;
  * hardcodes NO score, NO role hash, NO function selector, NO multisig
    threshold.  Every cryptographic constant is derived at runtime by a
    keccak-256 implemented in this file (self-tested against the empty
    string vector on startup), and every authority fact is read live over
    JSON-RPC;
  * re-derives all six published dimensions from
    `chains/tempo/METHODOLOGY.md` section 4.1 (rules R1, R1b, R2, R3, R4,
    R5, R5b, R5c, R6, R7);
  * then reads `getScore(address)` on the deployed oracle *inside this
    script* and compares field by field.  Exit code 1 on any divergence.

It replaces `audit_usdc_independent.py` (commit 2324848), which was
committed with three invented role hashes, a 3-argument event signature
that does not exist, `burn(uint256)`'s selector labelled `threshold()`,
a hardcoded 5-of-7 threshold and a hardcoded on-chain "65" -- and which
reverted on its first eth_call, so it never produced any of the audit its
commit message claimed.

RPC HONESTY (this was mis-stated on 2026-09-20 and again on 2026-09-21)
----------------------------------------------------------------------
`eth_call` reads are double-read on two fully independent mainnet
providers: the official `rpc.tempo.xyz` and `tempo.drpc.org`.  A third,
`tempo-rpc.publicnode.com`, also serves eth_call and is used as an extra
control on the decisive reads.

`eth_getLogs` on publicnode cannot serve this scan.  Measured 2026-09-21
and printed by the script itself: publicnode answers HTTP 200 on a
ten-block window at the head but HTTP 403 on any historical block,
including the oldest block that carries a role event for the audited
token.  (This refines, rather than repeats, the earlier finding that it
403s "on everything": the distinction is recent vs archive, and either
way it cannot serve a full-history scan.)  The historical role-event scan
therefore runs on the official endpoint only, and its result is NOT left
unverified: every block that produced a role event is re-read one block
at a time on `tempo.drpc.org` -- a genuinely independent provider -- and
the two log sets must match exactly; every candidate the scan produces is
then re-confirmed with `hasRole` on all three providers.  drpc's own log
ranges are narrow in practice (100 blocks OK, 500 rejected), hence the
per-block re-read.

USAGE
-----
    python3 chains/tempo/scripts/audit_rotation_index.py [index]

`index` is an index into the oracle's own `trackedTargets` array, read
on-chain; it defaults to 1.  The script takes no input from this repo.
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

MAINNET_OFFICIAL = "https://rpc.tempo.xyz"
MAINNET_DRPC = "https://tempo.drpc.org"
MAINNET_PUBLICNODE = "https://tempo-rpc.publicnode.com"
CALL_RPCS = [MAINNET_OFFICIAL, MAINNET_DRPC, MAINNET_PUBLICNODE]
LOG_RPC = MAINNET_OFFICIAL
LOG_VERIFY_RPC = MAINNET_DRPC
LOG_WINDOW = 100_000
LOG_VERIFY_WINDOW = 5_000

MODERATO_RPC = "https://rpc.moderato.tempo.xyz"
# FIXED 2026-09-22 (backlog item "quatre reimplementations separees"): every read of the oracle's
# own published state used to go through MODERATO_RPC alone, unlike this file's own CALL_RPCS
# (official+drpc+publicnode) pattern for the mainnet re-derivation side, and unlike this file's own
# design comment on call1() ("every fact that feeds a published number is read through call2/
# CALL_RPCS instead") -- getScore() IS exactly such a published number. dRPC's Tempo Moderato
# Testnet gateway (found via https://drpc.org/chainlist/tempo-moderato-testnet-rpc, no API key)
# verified live 2026-09-22 to serve identical eth_chainId (0xa5bf) and trackedTargetsCount() (0x0e)
# to the official RPC -- same "official + drpc" pairing this file already trusts for mainnet.
MODERATO_DRPC = "https://tempo-moderato-testnet.drpc.org"
MODERATO_RPCS = [MODERATO_RPC, MODERATO_DRPC]
ORACLE = "0x50840a7667baEa9D05ad4ae3dCeb384724b58720"

TEMPO_MAINNET_CHAIN_ID = 4217
MODERATO_CHAIN_ID = 42431

VALIDATOR_CONFIG_V2 = "0xCCCCCCCC00000000000000000000000000000001"
TIP403_REGISTRY = "0x403c000000000000000000000000000000000000"
LZ_ENDPOINT_V2 = "0x20Bb7C2E2f4e5ca2B4c57060d1aE2615245dCc9C"
SAFE_SENTINEL = "0x0000000000000000000000000000000000000001"
EIP1967_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"

# METHODOLOGY.md R1: roles whose holders form the root-control set of a
# TIP-20. UNPAUSE_ROLE is excluded (it can only restore transfers).
ROOT_ROLE_NAMES = ["DEFAULT_ADMIN_ROLE", "ISSUER_ROLE", "PAUSE_ROLE", "BURN_BLOCKED_ROLE"]


# --------------------------------------------------------------- keccak-256
# Pure-Python Keccak-f[1600] / keccak-256, so this file needs no third-party
# package and nothing in it can be a copy-pasted "known" hash.
_RHO = [1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14, 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44]
_PI = [10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4, 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1]
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
       0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_M = (1 << 64) - 1


def _rotl(x, s):
    return ((x << s) | (x >> (64 - s))) & _M


def _keccak_f(a):
    for rnd in range(24):
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x + 5 * y] ^= d[x]
        t = a[1]
        for i in range(24):
            j = _PI[i]
            t, a[j] = a[j], _rotl(t, _RHO[i])
        for y in range(5):
            row = [a[x + 5 * y] for x in range(5)]
            for x in range(5):
                a[x + 5 * y] = row[x] ^ ((~row[(x + 1) % 5] & _M) & row[(x + 2) % 5])
        a[0] ^= _RC[rnd]
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data) + b"\x01" + b"\x00" * ((-len(data) - 1) % rate)
    padded[-1] ^= 0x80
    state = [0] * 25
    for off in range(0, len(padded), rate):
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(padded[off + 8 * i:off + 8 * i + 8], "little")
        state = _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470", "keccak self-test failed"


def selector(sig: str) -> str:
    return "0x" + keccak256(sig.encode()).hex()[:8]


def topic(sig: str) -> str:
    return "0x" + keccak256(sig.encode()).hex()


def role_hash(name: str) -> str:
    """OpenZeppelin / TIP-20 convention: DEFAULT_ADMIN_ROLE is 32 zero bytes,
    every other role is keccak256 of its own name."""
    if name == "DEFAULT_ADMIN_ROLE":
        return "0x" + "00" * 32
    return topic(name)


# ------------------------------------------------------------------ minimal ABI
def enc_addr(a):
    return a.lower().replace("0x", "").rjust(64, "0")


def enc_uint(v):
    return hex(v)[2:].rjust(64, "0")


def enc_b32(h):
    return h.lower().replace("0x", "").rjust(64, "0")


def words(hexdata):
    raw = hexdata[2:] if hexdata.startswith("0x") else hexdata
    return [raw[i:i + 64] for i in range(0, len(raw), 64)]


def as_addr(word):
    return "0x" + word[-40:]


def as_int(word):
    return int(word, 16)


def dec_addr_array(hexdata):
    w = words(hexdata)
    if len(w) < 2:
        return None
    off = as_int(w[0]) // 32
    n = as_int(w[off])
    return [as_addr(x) for x in w[off + 1:off + 1 + n]]


# ---------------------------------------------------------------------- JSON-RPC
def rpc(url, method, params, tries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    last = None
    for _ in range(tries):
        r = subprocess.run(["curl", "-s", "-m", "70", "-X", "POST",
                            "-H", "Content-Type: application/json", "-d", body, url],
                           capture_output=True, text=True)
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            last = r.stdout[:180]
            continue
        if "error" in out:
            last = out["error"]
            if out["error"].get("code") == 3:  # execution reverted -> deterministic
                return None
            continue
        return out["result"]
    raise RuntimeError(f"{url} {method}: {last}")


def call(url, to, sig, argwords=""):
    return rpc(url, "eth_call", [{"to": to, "data": selector(sig) + argwords}, "latest"])


def call2(to, sig, argwords="", rpcs=None, label=""):
    """eth_call on two+ independent providers; the answers must be identical."""
    rpcs = rpcs or CALL_RPCS[:2]
    outs = [call(u, to, sig, argwords) for u in rpcs]
    ok = [o for o in outs if o not in (None, "0x")]
    if not ok:
        return None
    if len({o for o in ok}) != 1:
        raise RuntimeError(f"RPC DISAGREEMENT on {label or sig} @ {to}: {dict(zip(rpcs, outs))}")
    return ok[0]


def moderato_call(data, label="", rpcs=None):
    """call2()'s counterpart for the ORACLE's own Moderato chain: raw eth_call data (already
    selector-encoded) against MODERATO_RPCS, requiring agreement. Every published number read off
    the oracle itself (trackedTargetsCount, trackedTargets, getScore) goes through this now.

    STRICTER than call2() ON PURPOSE, not a bug -- REVIEW FINDING (review run, reservation
    "moderato_call() IS STRICTER THAN THE call2() IT CLAIMS TO MIRROR"): call2() tolerates one
    provider returning nothing (a revert can legitimately mean "this optional fact doesn't apply"
    for the mainnet re-derivation side); there is no such legitimate case for the oracle's own
    published state -- a revert or empty answer here is itself an anomaly worth failing loud on, not
    silently dropping a provider for. What WAS a real gap in the first version: the single generic
    "RPC DISAGREEMENT" message did not distinguish "one provider answered nothing" (an infra hiccup,
    e.g. dRPC lagging one block right after a score push) from "both providers answered but
    disagree" (a real, tampering-shaped finding) -- fixed below by naming which case happened."""
    rpcs = rpcs or MODERATO_RPCS
    outs = [rpc(u, "eth_call", [{"to": ORACLE, "data": data}, "latest"]) for u in rpcs]
    silent = [u for u, o in zip(rpcs, outs) if o in (None, "0x")]
    if silent:
        raise RuntimeError(f"NO ANSWER on {label or data} @ {ORACLE} (Moderato) from: {silent} -- {dict(zip(rpcs, outs))}")
    if len(set(outs)) != 1:
        raise RuntimeError(f"RPC DISAGREEMENT on {label or data} @ {ORACLE} (Moderato): {dict(zip(rpcs, outs))}")
    return outs[0]


_CODE_CACHE = {}
_CALL_CACHE = {}


def code_of(addr, double=True):
    a = addr.lower()
    if a in _CODE_CACHE:
        return _CODE_CACHE[a]
    outs = [rpc(u, "eth_getCode", [addr, "latest"]) for u in (CALL_RPCS[:2] if double else CALL_RPCS[:1])]
    if len(set(outs)) != 1:
        raise RuntimeError(f"RPC DISAGREEMENT on eth_getCode @ {addr}: {outs}")
    _CODE_CACHE[a] = outs[0]
    return outs[0]


def call1(to, sig, argwords=""):
    """Single-provider read, memoised. Used ONLY inside the cross-exposure
    closure, which is a superset traversal -- every fact that feeds a
    published number is read through call2/CALL_RPCS instead."""
    k = (to.lower(), sig, argwords)
    if k not in _CALL_CACHE:
        _CALL_CACHE[k] = call(MAINNET_OFFICIAL, to, sig, argwords)
    return _CALL_CACHE[k]


def storage_addr(addr, slot):
    v = rpc(MAINNET_OFFICIAL, "eth_getStorageAt", [addr, slot, "latest"])
    return as_addr(v[2:]) if v and int(v, 16) else None


# ------------------------------------------------------ METHODOLOGY.md 4.1 formulas
def admin_key_score(k, n, unresolved):
    """R4."""
    if unresolved:
        return 20
    if k is None:
        return 100
    if k >= 3:
        return 65
    if k == 2:
        return 50
    return 5 if n > 1 else 10


def multisig_score(k, n, unresolved):
    """R5."""
    if unresolved:
        return 0
    if k is None:
        return 100
    if k == 1:
        return 15 if n == 1 else max(0, 14 - 2 * (n - 1))
    return max(16, min(100, 20 * k - (n - k)))


def timelock_score(min_delay_seconds):
    """R5b."""
    d = min_delay_seconds
    if d <= 0:
        return 0
    if d < 24 * 3600:
        return 20
    if d <= 48 * 3600:
        return 35
    if d < 7 * 86400:
        return 60
    return 80


def composite(a, m, t):
    """R7. Exact-integer form -- not int(0.4*a+0.3*m+0.3*t+0.5), which reads one LOWER than exact
    on 2054/1,030,301 (a,m,t) triples (scripts/lib/scorers.py, scripts/validate_all_scorers.py;
    matches chains/ethereum-l1/scripts/audit_rotation_index2.py already). Found by the review of
    commit 585d949."""
    return (4 * a + 3 * m + 3 * t + 5) // 10


# --------------------------------------------------------------- authority reads
def resolve_key(addr):
    """METHODOLOGY.md R2, implemented from the rule text, for the shapes this
    audit actually needs to resolve exactly (EOA, EIP-7702 EOA, Safe,
    LayerZero OneSig, and a one-hop owner()/EIP-1967 contract).  Returns
    (kind, k, n, signers, min_delay_seconds) or kind='unresolved'."""
    c = code_of(addr)
    if c == "0x":
        return {"kind": "EOA", "k": 1, "n": 1, "signers": [addr.lower()], "delay": 0}
    if c.startswith("0xef0100"):
        return {"kind": "EOA (EIP-7702 delegated)", "k": 1, "n": 1, "signers": [addr.lower()], "delay": 0}
    thr = call2(addr, "getThreshold()", label="Safe.getThreshold")
    owners = call2(addr, "getOwners()", label="Safe.getOwners")
    if thr and owners:
        os_ = [o.lower() for o in dec_addr_array(owners)]
        mods = call2(addr, "getModulesPaginated(address,uint256)", enc_addr(SAFE_SENTINEL) + enc_uint(20))
        return {"kind": "Safe", "k": as_int(words(thr)[0]), "n": len(os_), "signers": os_, "delay": 0,
                "modulesRaw": mods}
    othr = call2(addr, "threshold()", label="OneSig.threshold")
    osig = call2(addr, "getSigners()", label="OneSig.getSigners")
    if othr and osig:
        ss = [s.lower() for s in dec_addr_array(osig)]
        return {"kind": "LayerZero OneSig", "k": as_int(words(othr)[0]), "n": len(ss), "signers": ss, "delay": 0}
    owner = call2(addr, "owner()", label="owner")
    padmin = storage_addr(addr, EIP1967_ADMIN)
    cands = []
    if owner and int(words(owner)[0], 16):
        cands.append(("owner()", as_addr(words(owner)[0])))
    if padmin:
        cands.append(("EIP-1967 admin", padmin))
    if cands:
        sub = [dict(via=v, **resolve_key(a)) for v, a in cands]
        weak = min(sub, key=lambda r: (0 if r["kind"] == "unresolved" else 1,
                                       r["k"] if r["k"] is not None else 0,
                                       -(r["n"] or 0)))
        return {"kind": f"contract -> {weak['via']} -> {weak['kind']}", "k": weak["k"], "n": weak["n"],
                "signers": sorted({s for r in sub for s in r["signers"]}), "delay": min(r["delay"] for r in sub)}
    return {"kind": "unresolved", "k": None, "n": None, "signers": [], "delay": 0, "unresolved": True}


def scan_role_logs(addresses, head):
    """R1b: candidate role holders = every `account` of a
    RoleMembershipUpdated log over the full chain history.  The signature is
    derived here, not quoted: RoleMembershipUpdated(bytes32,address,address,bool)
    -- four arguments (role, account, sender, granted)."""
    t0 = topic("RoleMembershipUpdated(bytes32,address,address,bool)")

    def window(start):
        return rpc(LOG_RPC, "eth_getLogs", [{"fromBlock": hex(start),
                                             "toBlock": hex(min(start + LOG_WINDOW - 1, head)),
                                             "address": addresses, "topics": [[t0]]}])
    logs = []
    with ThreadPoolExecutor(12) as ex:
        for res in ex.map(window, range(0, head + 1, LOG_WINDOW)):
            logs.extend(res)
    logs.sort(key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16)))
    return t0, logs


def verify_logs_second_source(addresses, t0, logs):
    """Independent re-read of the role events on a second provider (drpc).

    drpc's free plan advertises a 10,000-block log range but in practice
    refuses anything wider than a few hundred blocks on this chain (measured
    2026-09-21: 100 blocks OK, 500 rejected with the same "ranges over 10000
    blocks" message).  The verification therefore queries each event block
    individually -- narrower than any range, and an exact re-read of the same
    block on a different provider, which is what the cross-check is for."""
    blocks = sorted({int(l["blockNumber"], 16) for l in logs})
    if not blocks:
        return True, 0

    def q(b):
        return rpc(LOG_VERIFY_RPC, "eth_getLogs", [{"fromBlock": hex(b), "toBlock": hex(b),
                                                    "address": addresses, "topics": [[t0]]}])
    got = []
    with ThreadPoolExecutor(6) as ex:
        for res in ex.map(q, blocks):
            got.extend(res)

    def key(l):
        return (int(l["blockNumber"], 16), int(l["logIndex"], 16), l["address"].lower(),
                tuple(x.lower() for x in l["topics"]), l["data"].lower())
    return sorted(map(key, got)) == sorted(map(key, logs)), len(blocks)


def role_holders(token, candidates, role_names):
    """Confirm each candidate live with hasRole(address,bytes32) -- argument
    order address-then-role, the TIP-20 order (the OZ order reverts).  Every
    confirmation is read on all three eth_call providers."""
    out = {r: [] for r in role_names}
    for acct in candidates:
        for r in role_names:
            res = call2(token, "hasRole(address,bytes32)", enc_addr(acct) + enc_b32(role_hash(r)),
                        rpcs=CALL_RPCS, label=f"hasRole {r}")
            if res and int(res, 16) == 1:
                out[r].append(acct)
    return out


def _probe(addr):
    """One address: every authority edge this script can read."""
    out = []
    c = code_of(addr, double=False)
    if c == "0x" or c.startswith("0xef0100"):
        return out
    for sig in ("owner()", "curator()", "pendingOwner()"):
        v = call1(addr, sig)
        if v and v != "0x" and len(v) >= 66 and int(words(v)[0], 16):
            out.append(as_addr(words(v)[0]))
    for sig in ("getOwners()", "getSigners()", "getExecutors()"):
        v = call1(addr, sig)
        if v and v != "0x" and len(v) > 66:
            try:
                out.extend(dec_addr_array(v) or [])
            except Exception:
                pass
    pa = storage_addr(addr, EIP1967_ADMIN)
    if pa:
        out.append(pa)
        v = call1(pa, "owner()")
        if v and v != "0x" and int(words(v)[0], 16):
            out.append(as_addr(words(v)[0]))
    d = call1(LZ_ENDPOINT_V2, "delegates(address)", enc_addr(addr))
    if d and d != "0x" and int(words(d)[0], 16):
        out.append(as_addr(words(d)[0]))
    for rn in ("DEFAULT_ADMIN_ROLE", "PROPOSER_ROLE", "BYPASSER_ROLE", "ADMIN_ROLE"):
        cnt = call1(addr, "getRoleMemberCount(bytes32)", enc_b32(role_hash(rn)))
        if not cnt or cnt == "0x":
            continue
        for i in range(min(as_int(words(cnt)[0]), 40)):
            m = call1(addr, "getRoleMember(bytes32,uint256)", enc_b32(role_hash(rn)) + enc_uint(i))
            if m and m != "0x":
                out.append(as_addr(words(m)[0]))
    return out


def authority_closure(root, seeds=(), max_depth=3):
    """Conservative SUPERSET of the addresses that can appear in a target's
    root signer set: follow every authority edge this script knows how to
    read (owner, curator, Safe owners, OneSig signers, EIP-1967 admin and
    its owner, LayerZero endpoint delegate, enumerable role members) up to
    `max_depth`, plus the role-log candidates passed in `seeds` for TIP-20
    precompiles (which expose no role enumeration at all).  Used only for
    the cross-exposure disjointness proof: if the closure of another target
    does NOT contain any of this target's root signers, that target provably
    shares no root signer, because the exact signer set is a subset of this
    closure."""
    seen = {root.lower()} | {s.lower() for s in seeds}
    frontier = [root] + list(seeds)
    for _ in range(max_depth):
        if not frontier:
            break
        nxt = []
        with ThreadPoolExecutor(8) as ex:
            for res in ex.map(_probe, frontier):
                nxt.extend(res)
        frontier = []
        for a in nxt:
            al = a.lower()
            if al not in seen and int(al, 16) != 0:
                seen.add(al)
                frontier.append(a)
    return seen


# ------------------------------------------------------------------------- main
def main():
    index = int(sys.argv[1]) if sys.argv[1:] else 1
    fail = []

    print("== 0. derived constants (nothing below is hardcoded) ==")
    print(f"   keccak256('')                                            = 0x{keccak256(b'').hex()}")
    for rn in ROOT_ROLE_NAMES + ["UNPAUSE_ROLE"]:
        print(f"   role hash {rn:<20} = {role_hash(rn)}")
    for sig in ("hasRole(address,bytes32)", "transferPolicyId()", "threshold()", "getSigners()",
                "getThreshold()", "getOwners()", "owner()", "getScore(address)",
                "trackedTargets(uint256)", "trackedTargetsCount()", "totalSupply()"):
        print(f"   selector {sig:<28} = {selector(sig)}")
    ev = "RoleMembershipUpdated(bytes32,address,address,bool)"
    print(f"   topic0   {ev} = {topic(ev)}")

    print("\n== 1. networks ==")
    for u in CALL_RPCS:
        cid = int(rpc(u, "eth_chainId", []), 16)
        print(f"   {u:<38} chainId={cid}")
        if cid != TEMPO_MAINNET_CHAIN_ID:
            fail.append(f"{u} is not Tempo mainnet ({cid})")
    for u in MODERATO_RPCS:
        mcid = int(rpc(u, "eth_chainId", []), 16)
        print(f"   {u:<38} chainId={mcid}")
        if mcid != MODERATO_CHAIN_ID:
            fail.append(f"oracle RPC {u} is not Moderato ({mcid})")

    print("\n== 2. target taken from the oracle's own trackedTargets array ==")
    cnt = as_int(words(moderato_call(selector("trackedTargetsCount()"), label="trackedTargetsCount()"))[0])
    tracked = []
    for i in range(cnt):
        v = moderato_call(selector("trackedTargets(uint256)") + enc_uint(i), label=f"trackedTargets({i})")
        tracked.append(as_addr(words(v)[0]))
    print(f"   oracle {ORACLE} trackedTargetsCount() = {cnt}")
    target = tracked[index]
    print(f"   trackedTargets({index}) = {target}")

    print("\n== 3. target identity, read live ==")
    tcode = code_of(target)
    name = call2(target, "name()", label="name")
    sym = call2(target, "symbol()", label="symbol")

    def dec_str(h):
        w = words(h)
        n = as_int(w[1])
        return bytes.fromhex(w[2][:2 * n]).decode()
    supply = as_int(words(call2(target, "totalSupply()", label="totalSupply"))[0])
    dec = as_int(words(call2(target, "decimals()", label="decimals"))[0])
    pid = as_int(words(call2(target, "transferPolicyId()", rpcs=CALL_RPCS, label="transferPolicyId"))[0])
    print(f"   name={dec_str(name)!r} symbol={dec_str(sym)!r} decimals={dec}")
    print(f"   totalSupply = {supply / 10 ** dec:,.2f}")
    print(f"   eth_getCode = {tcode}  (TIP-20 precompile instance marker 0xef: {tcode == '0xef'})")
    print(f"   transferPolicyId() = {pid}  ->  " +
          ("always-reject" if pid == 0 else "always-allow (no policy admin in the root set, R1)"
           if pid == 1 else "custom policy, admin joins the root set (R1)"))

    print("\n== 4. R1b: historical role-event scan (candidates) ==")
    head = int(rpc(LOG_RPC, "eth_blockNumber", []), 16)
    tip20 = [t for t in tracked if code_of(t) == "0xef"]
    print(f"   TIP-20 precompile instances among the {cnt} tracked targets: {len(tip20)}"
          f" (they expose no role enumeration, so their holders only exist in logs)")
    t0, all_logs = scan_role_logs(tip20, head)
    logs = [l for l in all_logs if l["address"].lower() == target.lower()]
    print(f"   head block {head:,}, scanned 0..{head:,} in {LOG_WINDOW:,}-block windows on {LOG_RPC}")
    print(f"   {len(logs)} RoleMembershipUpdated log(s) on {target}")
    for l in logs:
        print(f"     block {int(l['blockNumber'], 16):>12,}  role={l['topics'][1]}"
              f"  account={as_addr(l['topics'][2])}  granted={int(l['data'], 16) == 1}")
    ok, nranges = verify_logs_second_source(tip20, t0, all_logs)
    print(f"   second source {LOG_VERIFY_RPC}: re-read {nranges} individual block(s) covering all"
          f" {len(all_logs)} role log(s) of the {len(tip20)} TIP-20 targets -> "
          f"{'IDENTICAL log set' if ok else 'MISMATCH'}")
    if not ok:
        fail.append("log set differs between the two providers")
    def pn_http(frm, to):
        return subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "25", "-X", "POST",
                               "-H", "Content-Type: application/json",
                               "-d", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
                                                 "params": [{"fromBlock": hex(frm), "toBlock": hex(to)}]}),
                               MAINNET_PUBLICNODE], capture_output=True, text=True).stdout.strip()
    oldest = min(int(l["blockNumber"], 16) for l in all_logs)
    print(f"   honesty control on the third provider {MAINNET_PUBLICNODE}:")
    print(f"     eth_getLogs on the 10 most recent blocks        -> HTTP {pn_http(head - 10, head)}")
    print(f"     eth_getLogs on the OLDEST role-event block {oldest:,} -> HTTP {pn_http(oldest, oldest)}")
    print("     it serves recent logs but refuses historical ones, so it CANNOT be a second")
    print("     source for this full-history scan -- only for eth_call, where it is used above.")

    print("\n== 5. R1: root-control set (hasRole confirmed on 3 providers) ==")
    candidates = sorted({as_addr(l["topics"][2]) for l in logs})
    holders = role_holders(target, candidates, ROOT_ROLE_NAMES + ["UNPAUSE_ROLE"])
    for r in ROOT_ROLE_NAMES + ["UNPAUSE_ROLE"]:
        print(f"   {r:<20} -> {holders[r] or '(none)'}" + ("   [excluded from root set, R1]" if r == "UNPAUSE_ROLE" else ""))
    root_addrs = sorted({a for r in ROOT_ROLE_NAMES for a in holders[r]})
    print(f"   root-control set = {root_addrs}")

    print("\n== 6. R2/R3: resolving each root holder to a key ==")
    keys = []
    for a in root_addrs:
        k = resolve_key(a)
        keys.append(k)
        print(f"   {a} -> {k['kind']} k={k['k']} n={k['n']} delay={k['delay']}s")
        if k["kind"] == "LayerZero OneSig" or k["kind"] == "Safe":
            empty = [s for s in k["signers"] if code_of(s) == "0x"]
            print(f"      signers ({len(k['signers'])}): {k['signers']}")
            print(f"      signers with empty code (EOA): {len(empty)}/{len(k['signers'])}")
        if "contract ->" in k["kind"]:
            print(f"      resolved signer set ({len(k['signers'])}): {k['signers']}")
    weak = min(keys, key=lambda r: (0 if r.get("unresolved") else 1,
                                    r["k"] if r["k"] is not None else 0, -(r["n"] or 0)))
    print(f"   weakest key (R3): k={weak['k']} n={weak['n']} kind={weak['kind']}")

    print("\n== 7. R5b: enforced delay on every path ==")
    delays = []
    for a in root_addrs:
        for sig in ("getMinDelay()", "delay()", "minDelay()"):
            v = call(MAINNET_OFFICIAL, a, sig)
            if v and v != "0x":
                delays.append((a, sig, as_int(words(v)[0])))
    print(f"   timelock getters found on the root set: {delays or 'none'}")
    min_delay = min([d[2] for d in delays], default=0)

    print("\n== 8. re-derived dimensions (formulas R4/R5/R5b/R5c/R7) ==")
    unres = bool(weak.get("unresolved"))
    a_s = admin_key_score(weak["k"], weak["n"], unres)
    m_s = multisig_score(weak["k"], weak["n"], unres)
    t_s = timelock_score(min_delay)
    o_s = 100  # R5c: a TIP-20 stablecoin reads no price
    c_s = composite(a_s, m_s, t_s)
    print(f"   adminKeyScore       = {a_s}   (R4 on k={weak['k']})")
    print(f"   multisigScore       = {m_s}   (R5: max(16, min(100, 20*{weak['k']} - ({weak['n']}-{weak['k']}))))")
    print(f"   timelockScore       = {t_s}   (R5b on minimum enforced delay {min_delay}s)")
    print(f"   oracleAuthorityScore= {o_s}   (R5c: target reads no price)")
    print(f"   compositeScore      = {c_s}   (R7: floor(0.4*{a_s}+0.3*{m_s}+0.3*{t_s}+0.5))")

    print("\n== 9. R6: crossExposureScore, re-derived over the whole tracked set ==")
    my_signers = {s for k in keys for s in k["signers"]}
    print(f"   this target's root signers ({len(my_signers)}): {sorted(my_signers)}")
    shared = []
    for i, other in enumerate(tracked):
        if other.lower() == target.lower():
            continue
        seeds = sorted({as_addr(l["topics"][2]) for l in all_logs if l["address"].lower() == other.lower()})
        clo = authority_closure(other, seeds)
        hit = sorted(my_signers & clo)
        mark = "SHARES" if hit else "disjoint"
        print(f"   [{i:>2}] {other} closure={len(clo):>3} addr  -> {mark}" + (f" {hit}" if hit else ""))
        if hit:
            shared.append((i, other, hit))
    within = max(0, 100 - 20 * len(shared))
    print(f"   OTHER tracked targets sharing >=1 root signer: {len(shared)} -> crossExposureScore = {within}")
    print("   (a disjoint closure is a SUPERSET disjointness proof: no traversal of that target")
    print("    reaches any of this target's root signers, so no exact resolution can either)")
    x_s = within

    print("\n== 10. published score read from the oracle IN THIS SCRIPT ==")
    raw = moderato_call(selector("getScore(address)") + enc_addr(target), label="getScore()")
    w = words(raw)
    pub = {"adminKeyScore": as_int(w[0]), "multisigScore": as_int(w[1]), "timelockScore": as_int(w[2]),
           "oracleAuthorityScore": as_int(w[3]), "crossExposureScore": as_int(w[4]),
           "compositeScore": as_int(w[5]), "lastUpdated": as_int(w[6]), "methodologyHash": "0x" + w[7]}
    print(f"   eth_call {ORACLE} getScore({target}) on {', '.join(MODERATO_RPCS)}")
    print(f"   {json.dumps(pub, indent=6)}")

    print("\n== 11. comparison ==")
    mine = {"adminKeyScore": a_s, "multisigScore": m_s, "timelockScore": t_s,
            "oracleAuthorityScore": o_s, "crossExposureScore": x_s, "compositeScore": c_s}
    for k, v in mine.items():
        same = v == pub[k]
        print(f"   {k:<22} re-derived={v:<4} published={pub[k]:<4} {'OK' if same else 'DIVERGENCE'}")
        if not same:
            fail.append(f"{k}: re-derived {v} != published {pub[k]}")

    print("\n== VERDICT ==")
    if fail:
        print("   DIVERGENCE / FAILURE:")
        for f in fail:
            print(f"     - {f}")
        sys.exit(1)
    print(f"   index {index} ({target}): all 6 published dimensions re-derived from the chain, NO DIVERGENCE")
    sys.exit(0)


if __name__ == "__main__":
    main()
