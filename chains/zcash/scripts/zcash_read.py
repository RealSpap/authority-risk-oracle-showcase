#!/usr/bin/env python3
"""Read-only Zcash mainnet reads over public lightwalletd gRPC (no deps, uses curl).

Usage:
  zcash_read.py info <host:port>                 -> decoded GetLightdInfo fields
  zcash_read.py balance <host:port> <taddr> ...  -> GetTaddressBalance valueZat
  zcash_read.py tx <host:port> <taddr> <start> <end> -> txids + transparent outputs to taddr per tx
"""
import subprocess, sys, struct, hashlib, tempfile, os

SVC = "cash.z.wallet.sdk.rpc.CompactTxStreamer"


def varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def field_bytes(num, data):
    return varint((num << 3) | 2) + varint(len(data)) + data


def field_varint(num, v):
    return varint(num << 3) + varint(v)


def grpc(host, method, msg):
    frame = b"\x00" + struct.pack(">I", len(msg)) + msg
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(frame)
        p = f.name
    try:
        out = subprocess.run(
            ["curl", "-s", "-m", "60", "--http2", "-H", "content-type: application/grpc",
             "-H", "te: trailers", "--data-binary", "@" + p,
             f"https://{host}/{SVC}/{method}"], capture_output=True, check=True).stdout
    finally:
        os.unlink(p)
    msgs, i = [], 0
    while i + 5 <= len(out):
        ln = struct.unpack(">I", out[i + 1:i + 5])[0]
        msgs.append(out[i + 5:i + 5 + ln])
        i += 5 + ln
    return msgs


def read_varint(b, i):
    shift = v = 0
    while True:
        c = b[i]; i += 1
        v |= (c & 0x7F) << shift; shift += 7
        if not c & 0x80:
            return v, i


def decode(b):
    i, res = 0, []
    while i < len(b):
        key, i = read_varint(b, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = read_varint(b, i)
        elif wt == 2:
            ln, i = read_varint(b, i)
            v = b[i:i + ln]; i += ln
        elif wt == 1:
            v = b[i:i + 8]; i += 8
        elif wt == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError(wt)
        res.append((num, v))
    return res


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes(26, "big")
    assert hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] == raw[-4:]
    return raw[:-4]  # 2-byte prefix + 20-byte hash


def parse_tx_transparent_outputs(raw):
    """Parse transparent vout of a v4/v5 Zcash tx; returns list of (value_zat, script_hex)."""
    i = 0
    header = struct.unpack("<I", raw[i:i + 4])[0]; i += 4
    version = header & 0x7FFFFFFF
    i += 4  # version group id
    if version >= 5:  # v5 and v6 (ZIP 229) share the same header layout
        i += 4 + 4 + 4  # branch id, lock_time, expiry
    def cs(i):
        c = raw[i]
        if c < 0xFD: return c, i + 1
        if c == 0xFD: return struct.unpack("<H", raw[i+1:i+3])[0], i + 3
        if c == 0xFE: return struct.unpack("<I", raw[i+1:i+5])[0], i + 5
        return struct.unpack("<Q", raw[i+1:i+9])[0], i + 9
    nin, i = cs(i)
    global LAST_NIN
    LAST_NIN = nin
    global LAST_SCRIPTSIGS
    LAST_SCRIPTSIGS = []
    for _ in range(nin):
        i += 36
        sl, i = cs(i); LAST_SCRIPTSIGS.append(raw[i:i + sl]); i += sl + 4
    nout, i = cs(i)
    outs = []
    for _ in range(nout):
        val = struct.unpack("<q", raw[i:i + 8])[0]; i += 8
        sl, i = cs(i)
        outs.append((val, raw[i:i + sl].hex())); i += sl
    return version, outs


def taddr_balance(host, *addrs):
    """GetTaddressBalance for one or more addresses, summed -- same call the
    `balance` CLI subcommand below already made inline. Extracted 2026-09-18
    (same reuse-gap fix already applied to p2sh_spends.py/miner_concentration.py
    on 2026-09-17) so scorers.py can call this directly instead of shelling
    out to this file as a subprocess for a live balance cross-check.

    FIXED 2026-09-19 (closed a bug hunt finding, hit live while checking
    Zenrock's zenZEC infrastructure keys, both of which genuinely hold 0
    ZEC): `valueZat` is proto3 field 1 of the response, which lightwalletd
    OMITS on the wire when the value is exactly 0 (proto3's own default-value
    convention -- the same reason `x/dct`'s AssetParams key IDs are absent
    rather than sent as an explicit 0 elsewhere in this project). The old
    `next(...)` with no default raised `StopIteration` for a real, correct
    zero balance -- indistinguishable from a communication failure to every
    caller, including `scorers.py`'s `score_maya_asgard_vault()`, which would
    have hit the exact same crash the day either Asgard vault's live balance
    happened to be exactly 0. A missing field now correctly means 0 zat, not
    an error."""
    msg = b"".join(field_bytes(1, a.encode()) for a in addrs)
    return next((v for num, v in decode(grpc(host, "GetTaddressBalance", msg)[0]) if num == 1), 0)


def transparent_output_script(addr: str) -> str:
    """The transparent output `scriptPubKey` hex a payment TO `addr` carries,
    selected from the address's own version-prefix byte. Extracted 2026-09-18
    (closed a tooling gap flagged in `data/scouting_candidates_2026-09-18.md`):
    the `tx` CLI subcommand below used to hardcode a P2SH-only matcher, so
    running it against a `t1` (P2PKH) address -- such as either Maya
    Protocol Asgard vault address -- silently returned `outputs_to_addr=0`
    on every real transaction in range, a false negative from a tooling gap,
    not evidence of no activity. Mainnet lead bytes from METHODOLOGY.md
    section 2: t1 (P2PKH) = 1CB8, t3 (P2SH) = 1CBD; Testnet tm (P2PKH) =
    1D25, t2 (P2SH) = 1CBA."""
    raw_addr = b58dec(addr)
    prefix, h160 = raw_addr[:2].hex(), raw_addr[2:].hex()
    if prefix in ("1cb8", "1d25"):
        return "76a914" + h160 + "88ac"  # OP_DUP OP_HASH160 <h160> OP_EQUALVERIFY OP_CHECKSIG
    if prefix in ("1cbd", "1cba"):
        return "a914" + h160 + "87"      # OP_HASH160 <h160> OP_EQUAL
    raise ValueError(f"unrecognised transparent address prefix {prefix} for {addr}")


def main():
    cmd, host = sys.argv[1], sys.argv[2]
    if cmd == "info":
        names = {1: "version", 2: "vendor", 4: "chainName", 5: "saplingActivationHeight",
                 6: "consensusBranchId", 7: "blockHeight", 12: "estimatedHeight",
                 14: "nodeSubversion"}
        for num, v in decode(grpc(host, "GetLightdInfo", b"")[0]):
            if num in names:
                print(f"{names[num]}={v.decode() if isinstance(v, bytes) else v}")
    elif cmd == "balance":
        print(f"valueZat={taddr_balance(host, *sys.argv[3:])}")
    elif cmd == "tx":
        addr, start, end = sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
        script = transparent_output_script(addr)
        rng = field_bytes(1, field_varint(1, start)) + field_bytes(2, field_varint(1, end))
        msg = field_bytes(1, addr.encode()) + field_bytes(2, rng)
        for m in grpc(host, "GetTaddressTxids", msg):
            f = dict(decode(m))
            raw, height = f.get(1, b""), f.get(2, 0)
            txid = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex() if raw else ""
            try:
                ver, outs = parse_tx_transparent_outputs(raw)
                to_addr = [v for v, s in outs if s == script]
                for sig in LAST_SCRIPTSIGS:
                    # redeem script is the last push; standard P2MS: OP_m <pubkeys> OP_n OP_CHECKMULTISIG
                    j = sig.find(bytes.fromhex("4c69")) if bytes.fromhex("4c69") in sig else -1
                    rs = sig[j + 2:j + 2 + 0x69] if j >= 0 else b""
                    if rs and rs[-1] == 0xAE and hashlib.new("ripemd160", hashlib.sha256(rs).digest()).hexdigest() == h160:
                        print(f"  spend_from_addr redeem_script m={rs[0]-0x50} n={rs[-2]-0x50} pubkeys={(len(rs)-3)//34}")
                print(f"height={height} v{ver} outputs_to_addr={len(to_addr)} sum_zat={sum(to_addr)} total_vin={LAST_NIN} total_vout={len(outs)} rawlen={len(raw)}")
            except Exception as e:
                print(f"height={height} parse_error={e} rawlen={len(raw)}")


if __name__ == "__main__":
    main()
