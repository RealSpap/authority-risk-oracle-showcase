"""Build, sign and broadcast a fully-transparent Zcash v6 (NU6.3/ZIP 229)
transaction, from scratch, over the same lightwalletd gRPC-over-curl transport
`zcash_read.py` already uses. No third-party deps.

Written 2026-09-19 for METHODOLOGY.md section 8's open "native oracle form"
question -- see `publish_attestation.py` in this folder for the actual use
(one P2PKH input, one OP_RETURN commitment output, one P2PKH change output).

TESTNET ONLY. This module signs whatever private key it is given; it is used
here exclusively with a freshly generated, zero-value Zcash Testnet key (see
`secp256k1.py`'s module docstring). It must never be pointed at a Mainnet
key or a Mainnet consensus branch id.

Every constant below is cited to a primary source, not guessed:
  - v6 header encoding (fOverwintered bit + version), field order through
    tx_out, and the empty-sapling/orchard/ironwood serialization (three
    trailing zero compactSizes, nothing else) -- ZIP 225
    (https://zips.z.cash/zip-0225) and ZIP 229 (https://zips.z.cash/zip-0229),
    read directly from `zcash/zips`' raw source, 2026-09-19.
  - nVersionGroupId for v6 = 0xD884B698 -- ZIP 229, same read.
  - The ZIP-244 digest tree (header/transparent/sapling/orchard digests,
    T.2a/b/c prevouts/sequence/outputs, and the S.2 per-input signature
    digest) -- ZIP 244 (https://zips.z.cash/zip-0244), read directly.
  - The v6 addition of a 5th `ironwood_digest_v6` child and the v6-specific
    personalization strings ("ZTxIdOrchardH_v6", "ZTxIdIronwd_H_v6", etc.,
    used unconditionally for every v6 tx, empty or not) -- ZIP 229, cross-
    checked byte-for-byte against the reference implementation's own source:
    `zcash/librustzcash`'s `zcash_primitives/src/transaction/txid.rs`
    (`to_hash_v6`) and `zcash/orchard`'s `src/bundle/commitments.rs`
    (`ZCASH_ORCHARD_V6_HASH_PERSONALIZATION`, `ZCASH_IRONWOOD_HASH_PERSONALIZATION`),
    both fetched 2026-09-19. This project's own discipline (METHODOLOGY.md,
    "never trust ... an AI-summarized paraphrase") applied to itself: an
    LLM-paraphrased read of these ZIPs was cross-checked against the raw
    ZIP source text and then against the actual reference-implementation
    source before any of it was trusted enough to sign a real transaction.
"""
import hashlib
import os
import struct
import subprocess
import tempfile

import secp256k1 as ec
from zcash_read import grpc, field_bytes as _pf, decode

TESTNET_BRANCH_ID = 0x37A5165B          # NU6.3, confirmed live via GetLightdInfo (zcash_read.py)
V6_HEADER = 0x80000006                  # fOverwintered=1, version=6
V6_VERSION_GROUP_ID = 0xD884B698        # ZIP 229
SIGHASH_ALL = 0x01


def compact_size(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def field(b: bytes) -> bytes:
    """CompactSize-length-prefixed byte field, as ZIP-244 calls a 'field encoding'."""
    return compact_size(len(b)) + b


def blake2b_p(personal16: bytes, data: bytes) -> bytes:
    assert len(personal16) == 16, personal16
    return hashlib.blake2b(data, digest_size=32, person=personal16).digest()


class TxOut:
    def __init__(self, value_zat: int, script_pubkey: bytes):
        self.value = value_zat
        self.script = script_pubkey

    def ser(self) -> bytes:
        return struct.pack("<q", self.value) + field(self.script)


class TxIn:
    def __init__(self, prevout_hash_natural: bytes, prevout_index: int, sequence: int = 0xFFFFFFFF):
        assert len(prevout_hash_natural) == 32
        self.prevout_hash = prevout_hash_natural
        self.prevout_index = prevout_index
        self.sequence = sequence
        self.script_sig = b""  # filled in after signing

    def outpoint(self) -> bytes:
        return self.prevout_hash + struct.pack("<I", self.prevout_index)


def op_return_script(data: bytes) -> bytes:
    assert len(data) <= 220, "keep well under standard OP_RETURN relay limits"
    if len(data) <= 75:
        push = bytes([len(data)]) + data
    else:
        push = b"\x4c" + bytes([len(data)]) + data  # OP_PUSHDATA1
    return b"\x6a" + push  # OP_RETURN <push data>


# ---- ZIP-244 digest tree (v6 / ZIP 229), transparent-only case ----

PERS_HEADERS = b"ZTxIdHeadersHash"
PERS_TRANSPARENT = b"ZTxIdTranspaHash"
PERS_PREVOUTS = b"ZTxIdPrevoutHash"
PERS_SEQUENCE = b"ZTxIdSequencHash"
PERS_OUTPUTS = b"ZTxIdOutputsHash"
PERS_SAPLING = b"ZTxIdSaplingHash"           # unchanged v5/v6 (verified against librustzcash)
PERS_ORCHARD_V6 = b"ZTxIdOrchardH_v6"        # v6-specific (verified against zcash/orchard source)
PERS_IRONWOOD_V6 = b"ZTxIdIronwd_H_v6"       # v6-specific, added by ZIP 229
PERS_TXIN = b"Zcash___TxInHash"              # 3 underscores
PERS_AMOUNTS = b"ZTxTrAmountsHash"
PERS_SCRIPTS = b"ZTxTrScriptsHash"


def header_digest(lock_time: int, expiry_height: int, branch_id: int = TESTNET_BRANCH_ID) -> bytes:
    data = (struct.pack("<I", V6_HEADER) + struct.pack("<I", V6_VERSION_GROUP_ID) +
            struct.pack("<I", branch_id) + struct.pack("<I", lock_time) +
            struct.pack("<I", expiry_height))
    return blake2b_p(PERS_HEADERS, data)


def prevouts_digest(vin) -> bytes:
    return blake2b_p(PERS_PREVOUTS, b"".join(i.outpoint() for i in vin))


def sequence_digest(vin) -> bytes:
    return blake2b_p(PERS_SEQUENCE, b"".join(struct.pack("<I", i.sequence) for i in vin))


def outputs_digest(vout) -> bytes:
    return blake2b_p(PERS_OUTPUTS, b"".join(o.ser() for o in vout))


def transparent_digest(vin, vout) -> bytes:
    if not vin and not vout:
        return blake2b_p(PERS_TRANSPARENT, b"")
    data = prevouts_digest(vin) + sequence_digest(vin) + outputs_digest(vout)
    return blake2b_p(PERS_TRANSPARENT, data)


def empty_sapling_digest() -> bytes:
    return blake2b_p(PERS_SAPLING, b"")


def empty_orchard_digest_v6() -> bytes:
    return blake2b_p(PERS_ORCHARD_V6, b"")


def empty_ironwood_digest_v6() -> bytes:
    return blake2b_p(PERS_IRONWOOD_V6, b"")


def top_combine_v6(header_d, transparent_d, sapling_d, orchard_d, ironwood_d, branch_id=TESTNET_BRANCH_ID) -> bytes:
    personal = b"ZcashTxHash_" + struct.pack("<I", branch_id)
    data = header_d + transparent_d + sapling_d + orchard_d + ironwood_d
    return blake2b_p(personal, data)


def txid_v6(vin, vout, lock_time, expiry_height, branch_id=TESTNET_BRANCH_ID) -> bytes:
    """ZIP-244 txid_digest, extended per ZIP 229 (T.1..T.4 plus ironwood as 5th child).
    Deliberately does NOT depend on scriptSig contents (ZIP-244's malleability fix):
    only prevout/sequence/output data is hashed for T.2."""
    hd = header_digest(lock_time, expiry_height, branch_id)
    td = transparent_digest(vin, vout)
    return top_combine_v6(hd, td, empty_sapling_digest(), empty_orchard_digest_v6(),
                           empty_ironwood_digest_v6(), branch_id)


def transparent_sig_digest_all(vin, vout, input_index, prevout_value, prevout_script, branch_id=TESTNET_BRANCH_ID) -> bytes:
    """ZIP-244 section S.2, SIGHASH_ALL, non-coinbase, transparent inputs present."""
    hash_type = SIGHASH_ALL
    prevouts_sig = prevouts_digest(vin)             # ANYONECANPAY not set -> identical to T.2a
    amounts_sig = blake2b_p(PERS_AMOUNTS, struct.pack("<q", prevout_value))
    scripts_sig = blake2b_p(PERS_SCRIPTS, field(prevout_script))
    sequence_sig = sequence_digest(vin)              # identical to T.2b (SIGHASH_ALL doesn't blank sequence)
    outputs_sig = outputs_digest(vout)               # identical to T.2c (SIGHASH_ALL commits to all outputs)
    txin_this = vin[input_index]
    txin_sig = blake2b_p(PERS_TXIN, txin_this.outpoint() + struct.pack("<q", prevout_value) +
                          field(prevout_script) + struct.pack("<I", txin_this.sequence))
    data = (bytes([hash_type]) + prevouts_sig + amounts_sig + scripts_sig +
            sequence_sig + outputs_sig + txin_sig)
    return blake2b_p(PERS_TRANSPARENT, data)


def signature_digest_v6(vin, vout, input_index, prevout_value, prevout_script, lock_time,
                         expiry_height, branch_id=TESTNET_BRANCH_ID) -> bytes:
    hd = header_digest(lock_time, expiry_height, branch_id)
    tsd = transparent_sig_digest_all(vin, vout, input_index, prevout_value, prevout_script, branch_id)
    return top_combine_v6(hd, tsd, empty_sapling_digest(), empty_orchard_digest_v6(),
                           empty_ironwood_digest_v6(), branch_id)


def serialize_tx(vin, vout, lock_time, expiry_height, branch_id=TESTNET_BRANCH_ID) -> bytes:
    out = (struct.pack("<I", V6_HEADER) + struct.pack("<I", V6_VERSION_GROUP_ID) +
           struct.pack("<I", branch_id) + struct.pack("<I", lock_time) +
           struct.pack("<I", expiry_height))
    out += compact_size(len(vin))
    for i in vin:
        out += i.outpoint() + field(i.script_sig) + struct.pack("<I", i.sequence)
    out += compact_size(len(vout))
    for o in vout:
        out += o.ser()
    out += compact_size(0)  # nSpendsSapling
    out += compact_size(0)  # nOutputsSapling
    out += compact_size(0)  # nActionsOrchard
    out += compact_size(0)  # nActionsIronwood (ZIP 229; always present, even at 0)
    return out


def sign_p2pkh_input(privkey_int, pubkey_compressed, vin, vout, input_index, prevout_value,
                      prevout_script, lock_time, expiry_height, branch_id=TESTNET_BRANCH_ID):
    """Fills vin[input_index].script_sig with a standard <sig><pubkey> P2PKH scriptSig."""
    sighash = signature_digest_v6(vin, vout, input_index, prevout_value, prevout_script,
                                   lock_time, expiry_height, branch_id)
    der_sig = ec.ecdsa_sign(privkey_int, sighash)
    assert ec.ecdsa_verify(pubkey_compressed, sighash, der_sig), "self-check: signature must verify before use"
    sig_with_type = der_sig + bytes([SIGHASH_ALL])
    vin[input_index].script_sig = field(sig_with_type) + field(pubkey_compressed)
    return sighash, der_sig


def send_transaction(host: str, raw_tx: bytes):
    """lightwalletd `SendTransaction` RPC: RawTransaction{bytes data=1} ->
    SendResponse{int32 errorCode=1; string errorMessage=2}."""
    msg = _pf(1, raw_tx)
    resp = grpc(host, "SendTransaction", msg)
    if not resp:
        return None, "(no response frame from server)"
    fields = dict(decode(resp[0]))
    code = fields.get(1, 0)
    err_msg = fields.get(2, b"")
    if isinstance(err_msg, bytes):
        err_msg = err_msg.decode(errors="replace")
    return code, err_msg


def txid_hex_display(vin, vout, lock_time, expiry_height, branch_id=TESTNET_BRANCH_ID) -> str:
    return txid_v6(vin, vout, lock_time, expiry_height, branch_id)[::-1].hex()
