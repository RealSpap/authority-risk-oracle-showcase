#!/usr/bin/env python3
"""Rotation audit, ethereum-l1, index 2 (run 2026-09-21).

READ-ONLY, ZERO DEPENDENCIES. Anyone can run this file as is,
from anywhere:

    python3 audit_rotation_index2.py

No `pip install`, no `cast`/foundry, no import from the repo, no access to
keys/. Standard library only: keccak-256 is reimplemented here (the
4 function selectors are RECOMPUTED, never hardcoded) and the calls
go through urllib. That is the point: the exit code of this script must carry
the proof by itself, with no prepared environment.

What it establishes:
  1. a correct local keccak-256 (2 known test vectors), otherwise exit 2;
  2. which target is trackedTargets(2) on the deployed Sepolia oracle, read on
     TWO independent Sepolia RPCs (the target is not assumed, it is read);
  3. the PUBLISHED score for that target, via getScore(address) on those 2 RPCs;
  4. the MakerDAO/Sky authority FACTS, re-read from scratch on FOUR independent
     mainnet RPCs (delay/authority/hat/done + the spell's description/eta);
  5. the comparison between the published score and five constants VERIFIED against
     those facts, not five values re-derived from a formula that would vary
     with what is read. msig and oracle are the literals 100 (this target
     is neither a Gnosis Safe nor a price signer, never verified
     otherwise); admin and timelock become 75 and 70 as soon as hat()/done()
     and delay() are readable (the verified numeric fact is elsewhere, in the
     `faits` list below: delay() == 172800 s). Three of the five dimensions
     therefore cannot diverge as long as the read succeeds; only cross
     is a formula that really varies with what the script finds
     on-chain (number of other tracked targets rooted in Sky). Any
     divergence, on any of the five -> exit 1.

Exit codes (this is what makes the claim replayable):
    0 = full match, no divergence
    1 = at least one divergence between the verified constants and the published score
    2 = an indispensable on-chain read is impossible (dead RPCs, wrong address)
        - verification impossible, above all not a silent success

Built-in checks:
    AUDIT_FAULT_INJECT=1   forces adminKey to 76 -> MUST exit 1 (proves that 0 has teeth)
    AUDIT_FAKE_PAUSE=0x..  replaces MCD_PAUSE with a forged address -> MUST exit 2
"""
import json
import os
import sys
import urllib.request

ORACLE_SEPOLIA = "0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906"
MCD_PAUSE = "0xbE286431454714F511008713973d3B053A2d38f3"
ROTATION_INDEX = 2

SEPOLIA_RPCS = [
    "https://ethereum-sepolia-rpc.publicnode.com",   # Allnodes
    "https://sepolia.gateway.tenderly.co",           # Tenderly
    "https://1rpc.io/sepolia",                       # Automata
]
MAINNET_RPCS = [
    "https://ethereum-rpc.publicnode.com",           # Allnodes
    "https://eth.drpc.org",                          # dRPC
    "https://1rpc.io/eth",                           # Automata
    "https://eth-pokt.nodies.app",                   # Nodies / Pocket
]

divergences = []
unreadable = []


# --------------------------------------------------------------------------
# keccak-256 (FIPS-202 Keccak, padding 0x01, NOT the 0x06 padding of hashlib's
# SHA3-256). Reimplemented here so that the selectors are derived and not
# copied: a wrong selector would make the self-test below fail.
# --------------------------------------------------------------------------
_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_MASK = (1 << 64) - 1


def _rol(x, n):
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(a):
    for rnd in range(24):
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        a[0][0] ^= _RC[rnd]
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(block[i * 8:(i + 1) * 8], "little")
            a[i % 5][i // 5] ^= lane
        a = _keccak_f(a)
    out = bytearray()
    for i in range(4):  # 32 bytes = 4 lanes of the first row of the rate
        out += a[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out)


def selector(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()[:8]


def keccak_self_test():
    """Without this test, a broken keccak would produce wrong selectors and hence
    empty reads, and the script would lie silently. Public vectors."""
    vecteurs = [
        (b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
        (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"),
    ]
    for msg, attendu in vecteurs:
        got = keccak256(msg).hex()
        if got != attendu:
            print(f"KECCAK BROKEN on {msg!r}: {got} != {attendu}")
            return False
    # reference ERC-20 selector, publicly known
    if selector("transfer(address,uint256)") != "0xa9059cbb":
        print("KECCAK BROKEN: unexpected selector for transfer(address,uint256)")
        return False
    print(f"  keccak-256 self-test OK (3 vectors); selectors derived, not hardcoded")
    return True


# --------------------------------------------------------------------------
# JSON-RPC
# --------------------------------------------------------------------------
def rpc(url, method, params, retries=3):
    """One JSON-RPC call. `retries` covers the chunked-response cutoffs
    (http.client.IncompleteRead) seen on large eth_getCode payloads; an EVM
    revert, by contrast, is raised immediately as a RuntimeError."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    derniere = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"content-type": "application/json", "user-agent": "curl/8.7.1",
                         "connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read())
            if "error" in payload:
                raise RuntimeError(f"{url}: {payload['error']}")
            return payload["result"]
        except RuntimeError:
            raise
        except Exception as exc:
            derniere = exc
    raise RuntimeError(f"{url}: {derniere}")


def eth_call(url, to, data):
    return rpc(url, "eth_call", [{"to": to, "data": data}, "latest"])


def call_all(urls, to, sig, argdata="", label=None, sonde_negative=False):
    """Same call on ALL the RPCs. Requires unanimity: an RPC that diverges is
    a divergence, a call unreadable everywhere is an impossible read.

    `sonde_negative=True` marks a call that is EXPECTED not to answer
    (here getThreshold() on a contract that is not a Gnosis Safe). A negative
    probe with no answer is the normal result: it is not counted as an
    impossible read and writes no error word to the output, otherwise
    the claims journal would carry a false failure signal on every run.
    """
    label = label or f"{to} {sig}"
    data = selector(sig) + argdata
    vues = {}
    for url in urls:
        try:
            vues[url] = eth_call(url, to, data)
        except Exception as exc:  # dead RPC, rate limit, revert (expected or not)
            vues[url] = f"NO RESPONSE: {type(exc).__name__}"
    ok = {u: v for u, v in vues.items() if not str(v).startswith("NO RESPONSE") and v not in ("0x", None)}
    if not ok:
        if sonde_negative:
            print(f"    negative probe {label}: no response on the {len(urls)} RPCs, expected result")
        else:
            unreadable.append(f"{label}: unreadable on the {len(urls)} RPCs -> {list(vues.values())[:2]}")
        return None, 0
    distinctes = set(ok.values())
    if len(distinctes) != 1:
        divergences.append(f"{label}: RPCs disagree {ok}")
    return sorted(distinctes)[0], len(ok)


def as_addr(word):
    return None if word is None else "0x" + word[-40:]


def as_uint(word):
    return None if word is None else int(word, 16)


def as_bool(word):
    return None if word is None else bool(int(word, 16))


def as_string(word):
    """ABI decoding of a `string` returned alone."""
    if word is None:
        return None
    raw = bytes.fromhex(word[2:])
    off = int.from_bytes(raw[0:32], "big")
    ln = int.from_bytes(raw[off:off + 32], "big")
    return raw[off + 32:off + 32 + ln].decode("utf-8", "replace")


def pad_addr(addr):
    return addr.lower().replace("0x", "").rjust(64, "0")


def composite(admin, msig, timelock):
    """METHODOLOGY.md, Aggregation section: floor(.4a + .3m + .3t + .5),
    in exact integer arithmetic (same formula as the repo's _composite)."""
    return (4 * admin + 3 * msig + 3 * timelock + 5) // 10


# --------------------------------------------------------------------------
def main():
    global divergences, unreadable
    print("=" * 78)
    print("ROTATION AUDIT ethereum-l1 - index", ROTATION_INDEX, "- 2026-09-21")
    print("=" * 78)

    if not keccak_self_test():
        sys.exit(2)

    # --- 1. Which target IS index 2? read on-chain, not assumed ------------
    idx_word, n_sep = call_all(
        SEPOLIA_RPCS, ORACLE_SEPOLIA, "trackedTargets(uint256)",
        hex(ROTATION_INDEX)[2:].rjust(64, "0"), label="trackedTargets(2)",
    )
    if idx_word is None:
        print("\nIMPOSSIBLE to read trackedTargets(2) on the Sepolia oracle.")
        for u in unreadable:
            print(" -", u)
        sys.exit(2)
    target = as_addr(idx_word)
    print(f"\n[1] trackedTargets({ROTATION_INDEX}) = {target}   ({n_sep} Sepolia RPCs agree)")
    if target.lower() != MCD_PAUSE.lower():
        divergences.append(
            f"index {ROTATION_INDEX} is no longer MCD_PAUSE ({MCD_PAUSE}) but {target}: "
            "the rotation does not cover the expected target"
        )

    # --- 2. PUBLISHED score on-chain ---------------------------------------------
    score_word, _ = call_all(
        SEPOLIA_RPCS, ORACLE_SEPOLIA, "getScore(address)", pad_addr(target), label="getScore(target)",
    )
    if score_word is None:
        print("\nIMPOSSIBLE to read getScore() on the Sepolia oracle.")
        sys.exit(2)
    raw = bytes.fromhex(score_word[2:])
    mots = [int.from_bytes(raw[i * 32:(i + 1) * 32], "big") for i in range(7)]
    onchain = {"admin": mots[0], "msig": mots[1], "timelock": mots[2],
               "oracle": mots[3], "cross": mots[4], "composite": mots[5]}
    last_updated = mots[6]
    print(f"[2] PUBLISHED score = {onchain}  lastUpdated={last_updated}")

    # --- 3. Re-derivation from scratch on 4 mainnet RPCs ------------------------
    pause = os.environ.get("AUDIT_FAKE_PAUSE", MCD_PAUSE)
    if pause.lower() != MCD_PAUSE.lower():
        print(f"!! AUDIT_FAKE_PAUSE active: MCD_PAUSE replaced by {pause} (exit 2 expected)")

    delay_w, n_main = call_all(MAINNET_RPCS, pause, "delay()", label="MCD_PAUSE.delay()")
    auth_w, _ = call_all(MAINNET_RPCS, pause, "authority()", label="MCD_PAUSE.authority()")
    delay_s, authority = as_uint(delay_w), as_addr(auth_w)
    if delay_s is None or authority is None:
        print("\n[3] MCD_PAUSE.delay()/authority() unreadable - derivation IMPOSSIBLE.")
        for u in unreadable:
            print(" -", u)
        sys.exit(2)
    print(f"[3] MCD_PAUSE.delay()     = {delay_s} s ({delay_s / 86400:g} d)   ({n_main} mainnet RPCs agree)")
    print(f"    MCD_PAUSE.authority() = {authority}  (DSChief / MCD_ADM)")

    hat_w, _ = call_all(MAINNET_RPCS, authority, "hat()", label="DSChief.hat()")
    hat = as_addr(hat_w)
    if hat is None:
        print("    DSChief.hat() unreadable - derivation IMPOSSIBLE.")
        sys.exit(2)
    done_w, _ = call_all(MAINNET_RPCS, hat, "done()", label="hat().done()")
    done = as_bool(done_w)
    desc_w, _ = call_all(MAINNET_RPCS, hat, "description()", label="hat().description()")
    eta_w, _ = call_all(MAINNET_RPCS, hat, "eta()", label="hat().eta()")
    description = as_string(desc_w)
    eta = as_uint(eta_w)
    print(f"    DSChief.hat()         = {hat}  (latest executive spell)")
    print(f"    hat().done()          = {done}")
    print(f"    hat().eta()           = {eta}")
    print(f"    hat().description()   = {str(description)[:90]}")

    # Independent cross-check of the code: the hat must be a CONTRACT, not a bare EOA.
    # eth_getCode returns ~9 kB here and the chunked response is sometimes cut by a
    # network intermediary, on any of the 4 RPCs. When NONE returns the
    # code, it is not a divergence: we fall back on weaker but sufficient
    # evidence, already obtained above: a bare EOA cannot answer
    # done()/description()/eta(), it would return 0x.
    code_lens = set()
    for url in MAINNET_RPCS:
        try:
            code_lens.add(len(rpc(url, "eth_getCode", [hat, "latest"])))
        except Exception:
            pass
    if code_lens:
        print(f"    eth_getCode(hat)      = {sorted(code_lens)} hex chars ({len(code_lens)} distinct value(s))")
        contrat = max(code_lens) > 4
        base_contrat = "eth_getCode"
    else:
        print("    eth_getCode(hat)      = not returned by the 4 RPCs this pass (chunked response cut)")
        contrat = done is not None and bool(description)
        base_contrat = "answers to done()/description(), which a bare EOA cannot produce"
    if len(code_lens) > 1:
        divergences.append(f"eth_getCode(hat) differs between RPCs: {sorted(code_lens)}")

    # --- 3bis. crossExposureScore DERIVED, not assumed --------------------------
    # METHODOLOGY.md convention: 100 - 20 per OTHER tracked target sharing the same
    # signing root. Here the root is Sky governance: MCD_PAUSE itself,
    # its MCD_PAUSE_PROXY, and any proxy whose ward is MCD_PAUSE_PROXY.
    MCD_PAUSE_PROXY = "0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB"
    racine_sky = {MCD_PAUSE.lower(), MCD_PAUSE_PROXY.lower(), authority.lower()}

    n_word, _ = call_all(SEPOLIA_RPCS, ORACLE_SEPOLIA, "trackedTargetsCount()", label="trackedTargetsCount()")
    n_tracked = as_uint(n_word) or 0
    print(f"\n[3bis] trackedTargetsCount() = {n_tracked} - looking for the OTHER targets rooted in Sky")
    partages = []
    for i in range(n_tracked):
        if i == ROTATION_INDEX:
            continue
        w, _ = call_all(SEPOLIA_RPCS[:1], ORACLE_SEPOLIA, "trackedTargets(uint256)",
                        hex(i)[2:].rjust(64, "0"), label=f"trackedTargets({i})")
        other = as_addr(w)
        if other is None:
            continue
        rpc_m = MAINNET_RPCS[0]
        racines = set()
        for sig in ("owner()", "authority()"):
            try:
                r = as_addr(eth_call(rpc_m, other, selector(sig)))
                if r and int(r, 16):
                    racines.add(r.lower())
            except Exception:
                pass
        lie = bool(racines & racine_sky)
        if not lie:
            # 2nd hop: does the owning proxy have MCD_PAUSE_PROXY as a ward?
            for r in list(racines):
                try:
                    w2 = eth_call(rpc_m, r, selector("wards(address)") + pad_addr(MCD_PAUSE_PROXY))
                    if w2 and int(w2, 16) == 1:
                        lie = True
                except Exception:
                    pass
        if lie:
            partages.append((i, other))
            print(f"       index {i} {other} -> rooted in the same Sky governance")
    cross_derive = max(0, 100 - 20 * len(partages))
    print(f"       {len(partages)} other tracked target(s) share the Sky root -> derived crossExposure = {cross_derive}")

    # --- 4. Facts that the published score ASSUMES (METHODOLOGY.md + scorer) --------
    # adminKey 75  = real, active MKR/SKY governance: hat() AND hat().done() readable.
    # msig     100 = not applicable, DSChief/DSPause is not a Gnosis Safe (no getThreshold()).
    # timelock  70 = real 2-day delay confirmed, capped below 100 (no proof of the absence
    #                of an emergency bypass verified this pass).
    # oracle   100 = not applicable (this target signs no price).
    # cross    = 100 - 20 per other tracked target sharing the Sky root (derived in [3bis]).
    thr_w, _ = call_all(MAINNET_RPCS, pause, "getThreshold()",
                        label="MCD_PAUSE.getThreshold()", sonde_negative=True)
    faits = [
        (f"MCD_PAUSE.delay() = 172800 s (2 days)", delay_s == 172800),
        ("authority() resolves to a non-zero DSChief", authority is not None and int(authority, 16) != 0),
        ("DSChief.hat() readable (governance not dormant)", hat is not None and int(hat, 16) != 0),
        ("hat().done() = True (spell already executed, expected form)", done is True),
        (f"hat() is a CONTRACT, not a bare EOA (basis: {base_contrat})", contrat),
        ("the spell carries a readable description()", bool(description)),
        ("MCD_PAUSE is NOT a Gnosis Safe (getThreshold() does not answer)", thr_w is None),
    ]
    print("\n[4] facts expected by the published score:")
    for label, ok in faits:
        print(f"    [{'OK   ' if ok else 'MISMATCH'}] {label}")
        if not ok:
            divergences.append(f"expected fact FALSE: {label}")

    # --- 5. Derivation and comparison -----------------------------------------
    admin = 75 if (hat is not None and done is not None) else 20
    msig = 100
    timelock = 70 if delay_s is not None else 0
    if os.environ.get("AUDIT_FAULT_INJECT") == "1":
        admin = 76
        print("\n!! AUDIT_FAULT_INJECT=1: adminKey forced to 76, a divergence is expected")
    derive = {"admin": admin, "msig": msig, "timelock": timelock,
              "oracle": 100, "cross": cross_derive}
    derive["composite"] = composite(admin, msig, timelock)

    for k in ("admin", "msig", "timelock", "oracle", "cross", "composite"):
        if derive[k] != onchain[k]:
            divergences.append(f"{k}: derived={derive[k]} != published on-chain={onchain[k]}")
    recompute = composite(onchain["admin"], onchain["msig"], onchain["timelock"])
    if recompute != onchain["composite"]:
        divergences.append(f"published composite inconsistent with its own dimensions: {recompute} != {onchain['composite']}")

    print(f"\n[5] live derived   = {derive}")
    print(f"    published on-chain= {onchain}")

    if unreadable:
        print("\nIMPOSSIBLE READS:")
        for u in unreadable:
            print(" -", u)
    if divergences:
        print("\nDIVERGENCES:")
        for d in divergences:
            print(" -", d)
        sys.exit(1)
    print("\nNO DIVERGENCE: the constants verified against the facts collected live on")
    print(f"4 mainnet RPCs exactly reproduce the published score for index {ROTATION_INDEX} "
          f"(composite {onchain['composite']}).")
    sys.exit(0)


if __name__ == "__main__":
    main()
