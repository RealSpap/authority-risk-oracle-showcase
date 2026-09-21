#!/usr/bin/env python3
"""Coinbase payout concentration over a block range, read-only via lightwalletd GetBlockRange.
Usage: miner_concentration.py <host:port> <start> <end>
Attributes each block to the script of its largest coinbase transparent output (miner payout),
excluding outputs to known funding-stream addresses (ZCG t3cFfPt1..., ZIP 271 t3ev37Q2...).

REFACTORED 2026-09-17 (closed a reuse gap): this used to run entirely at
module scope on import (sys.argv read directly, no __main__ guard, no
callable function) -- so nothing else in this project could import it
without crashing. Extracted into compute_concentration(), same logic, same
output, now safely importable by chains/zcash/scorers.py."""
import sys
import collections
import hashlib
import os

sys.path.insert(0, os.path.dirname(__file__))
from zcash_read import grpc, decode, field_bytes, field_varint, B58  # noqa: E402


def b58enc(b):
    chk = hashlib.sha256(hashlib.sha256(b).digest()).digest()[:4]
    n = int.from_bytes(b + chk, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return s


def addr(script):
    if script[:3] == bytes.fromhex("76a914") and len(script) == 25:
        return b58enc(bytes.fromhex("1cb8") + script[3:23])
    if script[:2] == bytes.fromhex("a914") and len(script) == 23:
        return b58enc(bytes.fromhex("1cbd") + script[2:22])
    return "script:" + script.hex()


EXCL = {"t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow", "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo"}


def compute_concentration(host, start, end, step=200):
    cnt = collections.Counter(); nblocks = 0
    for s in range(start, end + 1, step):
        e = min(end, s + step - 1)
        rng = field_bytes(1, field_varint(1, s)) + field_bytes(2, field_varint(1, e)) + field_varint(3, 1)
        for m in grpc(host, "GetBlockRange", rng):
            nblocks += 1
            txs = [v for n, v in decode(m) if n == 7]
            cb = decode(txs[0])
            outs = []
            for n, v in cb:
                if n == 8:
                    o = dict(decode(v)); outs.append((o.get(1, 0), addr(o.get(2, b""))))
            outs = [o for o in outs if o[1] not in EXCL]
            cnt[max(outs)[1] if outs else "shielded-or-none"] += 1
    ranked = cnt.most_common()
    cum = 0
    shares = []
    for a, c in ranked:
        cum += c
        shares.append({"address": a, "count": c, "pct": 100 * c / nblocks, "cumPct": 100 * cum / nblocks})

    def addresses_to_exceed(pct_threshold):
        # FIXED 2026-09-17 (closed a bug hunt finding): this returned the
        # enumerate() index (i+1) over ALL ranked buckets including the
        # skipped "shielded-or-none" one, overcounting the number of real
        # miner addresses needed whenever that excluded bucket ranked ahead
        # of the crossing point. Track real addresses counted, not the loop
        # index.
        run = 0
        real_count = 0
        for s in shares:
            if s["address"] == "shielded-or-none":
                continue
            run += s["count"]
            real_count += 1
            if 100 * run / nblocks > pct_threshold:
                return real_count
        return None

    return {
        "blocks": nblocks, "range": [start, end], "distinctPayoutAddresses": len(cnt),
        "shares": shares,
        "addressesToExceed50Pct": addresses_to_exceed(50),
        "addressesToExceed25Pct": addresses_to_exceed(25),
    }


if __name__ == "__main__":
    host, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    step = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    r = compute_concentration(host, start, end, step)
    print(f"blocks={r['blocks']} range={r['range'][0]}-{r['range'][1]} distinct_payout={r['distinctPayoutAddresses']}")
    for s in r["shares"][:8]:
        print(f"{s['address']} {s['count']} {s['pct']:.1f}% cum={s['cumPct']:.1f}%")
    print(f"addresses_to_exceed_50pct={r['addressesToExceed50Pct']} addresses_to_exceed_25pct={r['addressesToExceed25Pct']}")
