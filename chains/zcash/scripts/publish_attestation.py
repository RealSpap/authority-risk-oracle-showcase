#!/usr/bin/env python3
"""Publish a real score attestation on Zcash Testnet: a transparent P2PKH-funded
transaction carrying one OP_RETURN output whose data is a compact commitment
(4-byte magic + 32-byte BLAKE2b-256 hash) to a full, signed, off-chain JSON
attestation of an ALREADY-COMPUTED score from this project's own scorers.py.

Resolves METHODOLOGY.md section 8's "Decide the native oracle form without
contracts" question -- see chains/zcash/METHODOLOGY.md section 9 for the
design writeup and chains/zcash/data/testnet_oracle_poc_2026-09-19.md for the
full attestation, receipt and verification steps this run produced.

TESTNET ONLY. Funded via https://zcashfaucet.jinolabs.xyz/ (a proof-of-work
gated, captcha-free, login-free public Zcash Testnet faucet that pays
transparent addresses on request -- confirmed live 2026-09-19). The signing
key is a fresh, zero-value Testnet-only secp256k1 key (see secp256k1.py); it
is never used for anything beyond this demonstration. It is loaded from a file
OUTSIDE this repo (publisher_key.py); it was exposed in git history (40ca1a4),
so `send` refuses to broadcast with it.

Usage:
  python3 publish_attestation.py plan     -> build+sign, print everything, do NOT broadcast
  python3 publish_attestation.py send     -> build+sign+broadcast for real
"""
import hashlib
import json
import sys
import time

import secp256k1 as ec
import zcash_tx as tx
import zcash_read as zr
import publisher_key

HOST = "testnet.zec.rocks:443"

# CORRECTION 2026-09-19: the private key is NO LONGER in this file. It was
# committed here in clear in 40ca1a4 and is still in git history, so it must be
# treated as compromised (see publisher_key.py). It is now loaded at run time
# from a key file outside the repository (keys/zcash-testnet.json in the
# pipeline folder, or $ARO_ZCASH_TESTNET_KEY_FILE); a missing file is an
# explicit error. Only public values stay here.
#
# ROTATED 2026-09-19 (UTC): ARO1 is a finished, historic publication made by the exposed
# key, spending a faucet UTXO that belongs to that key's address. These constants
# therefore stay on the LEGACY values. `build()` can no longer run at all: with a key
# file holding the legacy key, publisher_key.load() refuses it by identity (whatever the
# file's flag says); with any other key, the "not the ARO1 publisher key" assertion fails.
# Both are on purpose: this script must never sign or send again.
PUBKEY_HEX = publisher_key.LEGACY_EXPOSED_PUBKEY_HEX
ADDRESS = publisher_key.LEGACY_EXPOSED_ADDRESS

# CORRECTED 2026-09-19: the funding tx is a v6 (NU5+/ZIP-244) transaction, whose
# txid is a personalized BLAKE2b digest tree (see zcash_tx.py), NOT legacy
# double-SHA256. zcash_read.py's own `tx` CLI subcommand still computes txid via
# legacy double-SHA256 for its printed display -- correct for pre-v5 tx history,
# WRONG for any v5/v6 transaction (a real, disclosed gap in that tool, flagged
# here rather than silently worked around). The first build of this script used
# that legacy hash for PREVOUT_TXID_NATURAL_HEX, producing a well-formed but
# WRONG outpoint; testnet.zec.rocks correctly rejected the resulting tx with
# "could not find transparent input UTXO in the best chain or mempool" -- the
# consensus check working exactly as intended. Corrected here using the real
# txid independently confirmed on a third-party Zcash Testnet explorer
# (testnet.cipherscan.app, Zebra-backed) rather than re-deriving it by hand.
PREVOUT_TXID_DISPLAY = "cda24edf051dd2b323ff4cf560f96c9f382dbeb1e8f0ab6810d3c5088fe42105"
PREVOUT_TXID_NATURAL_HEX = bytes.fromhex(PREVOUT_TXID_DISPLAY)[::-1].hex()
PREVOUT_INDEX = 0
PREVOUT_VALUE = 10_000_000  # 0.1 TAZ, from the jinolabs faucet, block 4366628
PREVOUT_HEIGHT = 4366628

# ZIP-317 conventional fee = marginal_fee(5000) * max(grace_actions(2), logical_actions).
# contribution_Transparent = max(ceil(tx_in_total_size/150), ceil(tx_out_total_size/34))
# (ZIP-317 "Fee calculation" section, read from raw ZIP source 2026-09-19). Our
# 1-in/2-out tx with a 36-byte OP_RETURN payload has tx_out_total_size ~81 bytes
# -> ceil(81/34)=3 logical actions -> conventional fee 15000 zat. FIRST BROADCAST
# ATTEMPT paid only 10000 zat (assuming the flat ~10000 zat "minimal tx" figure
# quoted elsewhere in this project's own top-level METHODOLOGY.md reproduction
# notes, without re-deriving ZIP-317's actual size-based formula for THIS
# transaction's specific OP_RETURN size) and was rejected: "failed to verify
# ZIP-317 transaction rules ... Unpaid actions is higher than the limit".
# Corrected to comfortably clear 3 logical actions with margin to spare.
FEE = 20_000

MAGIC = b"ARO1"
COMMIT_PERSONAL = b"AuthRiskOracle_1"
assert len(COMMIT_PERSONAL) == 16

ATTESTATION = {
    "project": "authority-risk-oracle",
    "repo": "RealSpap/authority-risk-oracle (private)",
    "ecosystem": "zcash",
    "target": "L1",
    "targetId": "0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3",
    "label": "Zcash Mainnet consensus-rule-change authority",
    "scores": {
        "adminKeyScore": 20,
        "multisigScore": 50,
        "timelockScore": 35,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": 34,
    },
    "scoreComputedBy": "chains/zcash/scorers.py score_all() (score_l1())",
    "sourceDataFile": "chains/zcash/data/scored_targets_2026-09-19.md",
    "methodologyFile": "chains/zcash/METHODOLOGY.md",
    "methodologyHashSha256": "b9a0c7bba90c1e42acb2c6c6804c71c29f1bd52f4d9b3efe596cc49c6536dff0",
    "methodologyHashedAt": "2026-09-19, before this pass's section-8/9 edits",
    "publisherPubkeyCompressed": PUBKEY_HEX,
    "publisherAddress_ZcashTestnet": ADDRESS,
    "publisherKeyNote": (
        "Zcash TESTNET-only throwaway secp256k1 key, generated 2026-09-19 with "
        "os.urandom; no relationship to any real Zcash authority or Mainnet "
        "address; holds no value beyond faucet-issued TAZ."
    ),
    "note": (
        "Proof-of-concept publication for METHODOLOGY.md section 8's open "
        "'native oracle form' question. This score was independently computed "
        "by this project's own scorers.py before this attestation was built; "
        "this transaction does not compute, alter, or re-derive it -- it only "
        "publishes a signed, timestamped, on-chain-anchored record of an "
        "already-live-verified number."
    ),
}


def canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def build(publish_time_iso: str):
    priv, pub, address, _exposed = publisher_key.load()
    assert pub.hex() == PUBKEY_HEX and address == ADDRESS, "key file is not the ARO1 publisher key"
    attestation = dict(ATTESTATION)
    attestation["publishedAtUtc"] = publish_time_iso
    payload = canonical_json(attestation)
    commit_hash = hashlib.blake2b(payload, digest_size=32, person=COMMIT_PERSONAL).digest()

    sig = ec.ecdsa_sign(priv, commit_hash)
    assert ec.ecdsa_verify(bytes.fromhex(PUBKEY_HEX), commit_hash, sig)
    attestation["attestationSignatureDer"] = sig.hex()
    attestation["attestationCommitBlake2b256"] = commit_hash.hex()
    # re-serialize once more (now including the signature) for the file we publish;
    # the ON-CHAIN commitment above is over the PRE-signature payload, matching
    # a standard "sign the digest, then attach the signature" pattern -- anyone
    # verifying recomputes the commit hash from the file's own fields MINUS
    # attestationSignatureDer/attestationCommitBlake2b256, which the verification
    # steps in the companion write-up spell out explicitly.
    final_json = json.dumps(attestation, sort_keys=True, indent=2)

    op_return_data = MAGIC + commit_hash
    op_return_script = tx.op_return_script(op_return_data)

    prevout_script = bytes.fromhex(zr.transparent_output_script(ADDRESS))
    vin = [tx.TxIn(bytes.fromhex(PREVOUT_TXID_NATURAL_HEX), PREVOUT_INDEX)]
    change_value = PREVOUT_VALUE - FEE
    vout = [tx.TxOut(0, op_return_script), tx.TxOut(change_value, prevout_script)]

    info = dict(zr.decode(zr.grpc(HOST, "GetLightdInfo", b"")[0]))
    tip = next(v for num, v in zr.decode(zr.grpc(HOST, "GetLightdInfo", b"")[0]) if num == 7)
    expiry_height = tip + 100
    lock_time = 0

    sighash, der_sig = tx.sign_p2pkh_input(
        priv, pub, vin, vout, 0,
        PREVOUT_VALUE, prevout_script, lock_time, expiry_height,
    )
    raw = tx.serialize_tx(vin, vout, lock_time, expiry_height)
    txid_display = tx.txid_hex_display(vin, vout, lock_time, expiry_height)

    return {
        "attestation_json": final_json,
        "commit_hash_hex": commit_hash.hex(),
        "op_return_data_hex": op_return_data.hex(),
        "raw_tx_hex": raw.hex(),
        "raw_tx_bytes": raw,
        "txid_display": txid_display,
        "sighash_hex": sighash.hex(),
        "tip_at_build": tip,
        "expiry_height": expiry_height,
        "change_value": change_value,
    }


# Real, on-chain result of the run that produced this file's `git log` entry
# (see data/testnet_oracle_poc_2026-09-19.md for the full writeup and every
# verification step): publishedAtUtc "2026-09-19T03:34:31Z",
# attestationCommitBlake2b256 "d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d",
# txid "f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5",
# Testnet block 4366645, fee 20000 zat. Independently confirmed via a second
# lightwalletd read of the confirmed transaction's own OP_RETURN bytes AND via
# testnet.cipherscan.app (third-party, Zebra-backed explorer).


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode == "send":
        try:
            _p, _q, _a, exposed = publisher_key.load()
        except publisher_key.PublisherKeyExposed as e:
            sys.exit(f"REFUSED: {e}")
        if exposed:
            sys.exit("REFUSED: the publisher key file is marked exposed_in_git_history=true "
                     "(committed in clear in 40ca1a4). A broadcast signed by it proves nothing "
                     "about who published. Rotate to a fresh, never-committed key first "
                     "(funding it is a manual action by Spap).")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        result = build(now)
    except publisher_key.PublisherKeyExposed as e:
        sys.exit(f"REFUSED: {e}")
    print("=== Attestation JSON ===")
    print(result["attestation_json"])
    print()
    print("OP_RETURN data (hex):", result["op_return_data_hex"], f"({len(result['op_return_data_hex'])//2} bytes)")
    print("Commit hash:", result["commit_hash_hex"])
    print("Sighash signed:", result["sighash_hex"])
    print("Tip at build:", result["tip_at_build"], "expiryHeight:", result["expiry_height"])
    print("Change output value (zat):", result["change_value"])
    print("txid (display, pre-broadcast prediction):", result["txid_display"])
    print("Raw tx hex:", result["raw_tx_hex"])
    print("Raw tx length:", len(result["raw_tx_bytes"]), "bytes")

    if mode == "send":
        print()
        print("Broadcasting via", HOST, "SendTransaction ...")
        code, err = tx.send_transaction(HOST, result["raw_tx_bytes"])
        print("errorCode:", code, "errorMessage:", repr(err))
    else:
        print()
        print("(plan mode only -- not broadcast. Re-run with 'send' to broadcast for real.)")


if __name__ == "__main__":
    main()
