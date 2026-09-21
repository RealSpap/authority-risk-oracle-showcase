#!/usr/bin/env python3
"""List spends from a Zcash P2SH address and decode the revealed redeem script (read-only).
Pages GetTaddressTxids in windows; prints only transactions whose inputs reveal a redeem
script hashing to the address (generic m-of-n OP_CHECKMULTISIG or other script).
Usage: p2sh_spends.py <host:port> <t3addr> <start> <end> [window]

REFACTORED 2026-09-17 (closed a reuse gap): this used to run entirely at
module scope on import (sys.argv read directly, no __main__ guard, no
callable function) -- so nothing else in this project could import it
without crashing. Extracted into find_multisig_spends(), same logic, same
output, now safely importable by chains/zcash/scorers.py (needed to
live-decode a fund's current (m, n) threshold and full signer pubkeys)."""
import sys
import os
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zcash_read as z  # noqa: E402


def pushes(script):
    i, out = 0, []
    while i < len(script):
        op = script[i]; i += 1
        if 1 <= op <= 75:
            out.append(script[i:i + op]); i += op
        elif op == 0x4c:
            n = script[i]; out.append(script[i + 1:i + 1 + n]); i += 1 + n
        elif op == 0x4d:
            n = int.from_bytes(script[i:i + 2], "little"); out.append(script[i + 2:i + 2 + n]); i += 2 + n
        elif op == 0x00:
            out.append(b"")
    return out


def find_multisig_spends(host, addr, start, end, window=2000):
    h160 = z.b58dec(addr)[2:].hex()
    ntx = 0
    spends = []
    for s in range(start, end + 1, window):
        e = min(end, s + window - 1)
        rng = z.field_bytes(1, z.field_varint(1, s)) + z.field_bytes(2, z.field_varint(1, e))
        for m in z.grpc(host, "GetTaddressTxids", z.field_bytes(1, addr.encode()) + z.field_bytes(2, rng)):
            f = dict(z.decode(m)); raw, height = f.get(1, b""), f.get(2, 0)
            ntx += 1
            try:
                ver, outs = z.parse_tx_transparent_outputs(raw)
            except Exception as ex:
                spends.append({"height": height, "parseError": str(ex)}); continue
            for sig in z.LAST_SCRIPTSIGS:
                ps = pushes(sig)
                if not ps:
                    continue
                rs = ps[-1]
                if rs and hashlib.new("ripemd160", hashlib.sha256(rs).digest()).hexdigest() == h160:
                    k = 1 if 0x51 <= rs[0] <= 0x60 else -1
                    pks = []
                    while k > 0 and k < len(rs) and rs[k] == 0x21:
                        pks.append(rs[k + 1:k + 34].hex()); k += 34
                    if k > 0 and k + 1 < len(rs) and 0x51 <= rs[k] <= 0x60 and rs[k + 1] in (0xAE, 0xAF):
                        suffix = rs[k + 2:].hex()
                        spends.append({
                            "height": height, "m": rs[0] - 0x50, "n": rs[k] - 0x50,
                            "op": "CHECKMULTISIG" if rs[k + 1] == 0xAE else "CHECKMULTISIGVERIFY",
                            "pubkeys": pks, "suffix": suffix or None,
                            "vin": z.LAST_NIN, "transparentVout": len(outs),
                        })
                    else:
                        spends.append({"height": height, "redeemScriptHex": rs.hex()})
                    break
    return {"address": addr, "scannedTxs": ntx, "spendsFound": len(spends), "range": [start, end], "spends": spends}


if __name__ == "__main__":
    host, addr, start, end = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    win = int(sys.argv[5]) if len(sys.argv) > 5 else 2000
    r = find_multisig_spends(host, addr, start, end, win)
    for sp in r["spends"]:
        if "m" in sp:
            print(f"height={sp['height']} spend redeem_script m={sp['m']} n={sp['n']} op={sp['op']} "
                  f"pubkeys={len(sp['pubkeys'])} suffix={sp['suffix'] or '-'} vin={sp['vin']} "
                  f"transparent_vout={sp['transparentVout']} pk_prefixes={','.join(x[:10] for x in sp['pubkeys'])}")
        elif "redeemScriptHex" in sp:
            print(f"height={sp['height']} spend redeem_script_hex={sp['redeemScriptHex']}")
        else:
            print(f"height={sp['height']} parse_error={sp['parseError']}")
    print(f"scanned_txs={r['scannedTxs']} spends_found={r['spendsFound']} range={r['range'][0]}-{r['range'][1]}")
