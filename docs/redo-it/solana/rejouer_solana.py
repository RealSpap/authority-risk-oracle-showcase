#!/usr/bin/env python3
"""Redo it, Solana: the score of the Exponent core program, from public reads only (no key, no account, no transaction, no library).
Python 3 standard library. Public Solana RPC: mainnet for the program and its multisig, devnet for the score account of the oracle.
  python3 rejouer_solana.py            prints each read, then VERDICT: MATCH only when the upgrade authority is the vault of the expected Squads multisig AND the recomputed scores equal the published ones.
  python3 rejouer_solana.py --selftest
Environment: SOL_MAINNET_RPC, SOL_DEVNET_RPC, EXPECTED_MULTISIG (to try a wrong one)."""
import base64, hashlib, json, os, struct, sys, time, urllib.request

MAINNET = os.environ.get("SOL_MAINNET_RPC", "https://api.mainnet-beta.solana.com"); DEVNET = os.environ.get("SOL_DEVNET_RPC", "https://api.devnet.solana.com")
ORACLE_PROGRAM = "5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W"          # Authority Risk Oracle, Solana devnet
TARGET = "ExponentnaRg3CQbW6dqQNZKXp7gtZ9DGMp1cwC4HAS7"                  # the target: the Exponent core program
MULTISIG = os.environ.get("EXPECTED_MULTISIG", "51smH7pBDKJDgmVnVks3gMWaPQFfmQ5s4Fc223yHcjuH")   # the Squads v4 multisig we expect (EXPONENT_MS in chains/solana/scorers.py)
SQUADS_V4 = "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
P = 2 ** 255 - 19; D = -121665 * pow(121666, P - 2, P) % P


def b58d(s):
    n = 0
    for c in s: n = n * 58 + A58.index(c)
    return b"\0" * (len(s) - len(s.lstrip("1"))) + (n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"")


def b58e(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def on_curve(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= P: return False
    u = (y * y - 1) % P; v = (D * y * y + 1) % P; x2 = u * pow(v, P - 2, P) % P
    return x2 == 0 or pow(x2, (P - 1) // 2, P) == 1


def pda(seeds, program):
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + b58d(program) + b"ProgramDerivedAddress").digest()
        if not on_curve(h): return b58e(h)
    raise ValueError("no PDA")


def rpc(url, method, params):
    for i in range(5):
        try:
            r = urllib.request.Request(url, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), {"content-type": "application/json", "user-agent": "curl/8.4.0"})
            d = json.load(urllib.request.urlopen(r, timeout=60))
            if "error" in d: raise RuntimeError(str(d["error"].get("message", ""))[:80])
            return d["result"]
        except RuntimeError: raise
        except Exception as e: err = e; time.sleep(1.5 * (i + 1))
    raise RuntimeError("RPC unreachable: %s" % str(err)[:60])


def account(url, addr, enc="base64"):
    v = rpc(url, "getAccountInfo", [addr, {"encoding": enc}])["value"]
    return v


def decode_score(data):
    if len(data) != 87 or data[:8] != hashlib.sha256(b"account:AuthorityScore").digest()[:8]: raise ValueError("not an AuthorityScore account")
    a, m, t, o, c, comp = data[40:46]; (last,) = struct.unpack_from("<q", data, 46)
    return {"target": b58e(data[8:40]), "admin": a, "multisig": m, "timelock": t, "oracleAuthority": o, "crossExposure": c, "composite": comp, "lastUpdated": last, "methodologyHash": "0x" + data[54:86].hex()}


def decode_squads_v4(data):
    """Squads v4 Multisig account: disc 8, create_key 32, config_authority 32, threshold u16, time_lock u32, transaction_index u64, stale_transaction_index u64, rent_collector Option<Pubkey>, bump u8, members Vec<{key 32, permissions u8}>."""
    if data[:8] != hashlib.sha256(b"account:Multisig").digest()[:8]: raise ValueError("not a Squads v4 Multisig account")
    o = 8 + 32; cfg = b58e(data[o:o + 32]); o += 32
    th, tl = struct.unpack_from("<HI", data, o); o += 6 + 16
    o += 1 + (32 if data[o] else 0); o += 1
    n = struct.unpack_from("<I", data, o)[0]; o += 4
    members = [(b58e(data[o + 33 * i:o + 33 * i + 32]), data[o + 33 * i + 32]) for i in range(n)]
    return {"threshold": th, "time_lock_s": tl, "config_authority": cfg, "members": members}


def rhu(x): return int(x + 0.5) if x >= 0 else -int(-x + 0.5)       # round half up, as _round_half_up in the scorer


def scores(threshold, voters, delay_s):
    """The scorer's rule for a program whose upgrade authority is a Squads v4 vault (chains/solana/scorers.py, _score_full_power_path and _delay_timelock_score)."""
    if threshold == 1: return 5, 0, 0
    multisig = min(100, rhu(15 * threshold + 40 * threshold / voters))
    h = 0 if delay_s == 0 else delay_s / 3600
    admin = (40 if h == 0 else 50 if h < 24 else 60) + min(20, 5 * (threshold - 1))
    timelock = 0 if h == 0 else (rhu(50 * h / 24) if h < 24 else min(80, 50 + min(30, rhu(10 * (h / 24 - 1)))))
    return admin, multisig, timelock


def composite(a, m, t): return (40 * a + 30 * m + 30 * t + 50) // 100


def selftest():
    assert b58e(b58d("11111111111111111111111111111111")) == "11111111111111111111111111111111"
    assert scores(3, 5, 36000) == (60, 69, 21), scores(3, 5, 36000)          # the values published for Exponent
    assert scores(4, 7, 0) == (55, 83, 0) and scores(1, 3, 0) == (5, 0, 0) and scores(3, 5, 86400)[2] == 50 and scores(3, 5, 86400 * 5)[2] == 80
    assert composite(60, 69, 21) == 51
    disc = hashlib.sha256(b"account:Multisig").digest()[:8]
    d = disc + b"\x11" * 32 + b"\x22" * 32 + struct.pack("<HI", 3, 36000) + struct.pack("<QQ", 7, 0) + b"\x00" + b"\x01" + struct.pack("<I", 2) + (bytes([1]) * 32 + b"\x07") + (bytes([2]) * 32 + b"\x04")
    m = decode_squads_v4(d); assert m["threshold"] == 3 and m["time_lock_s"] == 36000 and [x[1] for x in m["members"]] == [7, 4]
    print("selftest ok")


def main():
    if "--selftest" in sys.argv: return selftest()
    print("1. The published score (oracle account on devnet, PDA of seeds [\"score\", target]): admin, multisig, timelock, oracle-authority, cross-exposure, composite")
    sp = pda([b"score", b58d(TARGET)], ORACLE_PROGRAM); v = account(DEVNET, sp)
    if not v: print("   score account %s not found" % sp); print("VERDICT: NO MATCH (score account not read)"); return 1
    pub = decode_score(base64.b64decode(v["data"][0]))
    print("   account %s: %s" % (sp, [pub[k] for k in ("admin", "multisig", "timelock", "oracleAuthority", "crossExposure", "composite")]))
    print("2. The program and its upgrade authority (mainnet)")
    prog = account(MAINNET, TARGET, "jsonParsed"); pdata = prog["data"]["parsed"]["info"]["programData"]
    auth = account(MAINNET, pdata, "jsonParsed")["data"]["parsed"]["info"]["authority"]
    print("   program %s -> ProgramData %s -> upgrade authority = %s" % (TARGET, pdata, auth))
    print("3. Is that authority the vault 0 of the Squads v4 multisig %s ?" % MULTISIG)
    vault = pda([b"multisig", b58d(MULTISIG), b"vault", bytes([0])], SQUADS_V4)
    ok_vault = (vault == auth)
    print("   vault 0 re-derived offline = %s -> %s" % (vault, "same as the upgrade authority" if ok_vault else "DIFFERENT from the upgrade authority"))
    ms_acc = account(MAINNET, MULTISIG)
    if not ms_acc or ms_acc["owner"] != SQUADS_V4: print("   the multisig account is missing or not owned by Squads v4"); print("VERDICT: NO MATCH (multisig not read)"); return 1
    ms = decode_squads_v4(base64.b64decode(ms_acc["data"][0])); voters = sum(1 for _, p in ms["members"] if p & 2)
    print("   threshold = %d, members = %d (with the Vote permission: %d), time lock = %d s, config authority = %s" % (ms["threshold"], len(ms["members"]), voters, ms["time_lock_s"], ms["config_authority"]))
    print("4. The rule applied to what was read (chains/solana/scorers.py): multisig = min(100, round(15 t + 40 t / n)); admin = 40/50/60 + min(20, 5 (t - 1)) for a delay of 0 / under 24 h / 24 h or more; timelock = round(50 h / 24) under 24 h")
    if not ok_vault or ms["config_authority"] != "11111111111111111111111111111111":
        print("   not computed: the authority is not the vault of this multisig, or the multisig has a config authority"); print("VERDICT: NO MATCH (the read path does not hold)"); return 1
    a, m, t = scores(ms["threshold"], voters, ms["time_lock_s"]); comp = composite(a, m, t)
    print("   admin = %d, multisig = %d, timelock = %d -> composite = floor(0.4*%d + 0.3*%d + 0.3*%d + 0.5) = %d" % (a, m, t, a, m, t, comp))
    print("   Oracle-authority (%d) and cross-exposure (%d) are read from the oracle in step 1 and are not recomputed here." % (pub["oracleAuthority"], pub["crossExposure"]))
    if (a, m, t, comp) == (pub["admin"], pub["multisig"], pub["timelock"], pub["composite"]): print("VERDICT: MATCH (admin/multisig/timelock = %d %d %d, composite = %d, as published)" % (a, m, t, comp)); return 0
    print("VERDICT: NO MATCH (recomputed %s, published %s)" % ((a, m, t, comp), (pub["admin"], pub["multisig"], pub["timelock"], pub["composite"]))); return 1


if __name__ == "__main__":
    try: sys.exit(main() or 0)
    except RuntimeError as e: print("NOT READ: %s\nVERDICT: NO MATCH (a read failed; a failed read is never a match)" % e); sys.exit(2)
