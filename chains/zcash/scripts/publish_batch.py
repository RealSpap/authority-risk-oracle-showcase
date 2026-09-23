#!/usr/bin/env python3
"""Sign and anchor the ARO2 batch attestation (the WHOLE `score_all()` output)
on Zcash TESTNET -- the deploy_testnet step that `attest_scores.py` deliberately
does not have (that module has no send path; a unit test pins that).

What it does, in order (every step aborts the run on failure, nothing is
"best effort"):
  1. Loads the batch bundle produced by `attest_scores.py bundle` and
     re-derives its leaves, Merkle root and commitment from its own records.
  2. Re-derives the same commitment from a FRESH live `score_all()` run under
     the bundle's pinned methodology hash. Any drift aborts: the anchored
     value must be what the live chains say at broadcast time.
  3. Loads the Testnet publisher key from OUTSIDE the repo (publisher_key.py,
     never printed) and REFUSES if the key file is marked
     `exposed_in_git_history` (same guard as `publish_attestation.py send`); the legacy exposed
     key is also refused by IDENTITY (publisher_key.load), whatever that flag says or omits.
  4. Preflight on the UTXO to spend: the publisher address balance must equal
     the UTXO value on two independent reads (lightwalletd and cipherscan).
  5. Signs the 32-byte commitment (ECDSA secp256k1, RFC 6979, low-S, DER),
     builds + signs the transparent v6 tx with the ZIP-317 conventional fee
     (`attest_scores.build_tx`), reads the raw bytes back with the independent
     parser, and predicts the txid BEFORE broadcasting.
  6. `send` only: SendTransaction, requires errorCode 0 and the predicted txid
     echoed back, then polls until a block contains the exact raw bytes, reads
     the block time from lightwalletd, and writes the published attestation
     file (bundle + signature + anchor record).

Usage (from chains/zcash/scripts):
  python3 publish_batch.py plan BUNDLE.json                # steps 1-5, NO broadcast
  python3 publish_batch.py send BUNDLE.json --out FILE.json  # steps 1-6, real Testnet broadcast
  python3 publish_batch.py finish BUNDLE.json --state PENDING.json --out FILE.json
                       # after an accepted broadcast that was not seen confirmed in time: keep waiting
                       # and write the record (needs no key; PENDING.json holds no secret)

TESTNET ONLY, by these barriers: HOST below is a Testnet lightwalletd, and every UTXO
this script spends exists only on Testnet. The consensus branch id 0x37A5165B in
zcash_tx.py is shared by Mainnet and Testnet (chains/zcash/METHODOLOGY.md section 2), so it
is NOT a network barrier. Nothing here makes a Mainnet write impossible in the absolute; it
makes it not happen through this script.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import attest_scores as at  # noqa: E402
import publisher_key  # noqa: E402
import secp256k1 as ec  # noqa: E402
import zcash_read as zr  # noqa: E402
import zcash_tx as tx  # noqa: E402

HOST = "testnet.zec.rocks:443"
CIPHERSCAN_API = "https://api.testnet.cipherscan.app/api"
ENVELOPE_FORMAT = "aro-zcash-attestation-v2"
EXPIRY_DELTA = 100           # blocks (same margin as the ARO1 run)
CONFIRM_TIMEOUT_S = 25 * 60  # Testnet blocks are ~75 s
POLL_S = 20


def _die(msg):
    sys.exit(msg)


def tip_height(host=HOST) -> int:
    return next(v for num, v in zr.decode(zr.grpc(host, "GetLightdInfo", b"")[0]) if num == 7)


def block_time(host, height) -> int:
    m = zr.grpc(host, "GetBlock", zr.field_varint(1, height))
    return next(v for num, v in zr.decode(m[0]) if num == 5)


def utc(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def cipherscan_balance(address):
    with urllib.request.urlopen(f"{CIPHERSCAN_API}/address/{address}", timeout=30) as r:
        return int(json.load(r)["balance"])


def load_bundle(path):
    with open(path) as f:
        bundle = json.load(f)
    again = at.rederive(bundle)
    if again["commitmentBlake2b256"] != bundle["commitmentBlake2b256"]:
        _die("bundle does not re-derive from its own records")
    root = bytes.fromhex(bundle["header"]["merkleRoot"])
    for r in bundle["records"]:
        if not at.verify_proof(bytes.fromhex(r["leafHash"]), r["inclusionProof"], root):
            _die(f"bad inclusion proof for {r['target']}")
    if bundle["opReturnDataHex"] != (at.MAGIC + bytes.fromhex(bundle["commitmentBlake2b256"])).hex():
        _die("opReturnDataHex is not ARO2 + commitment")
    return bundle


def live_check(bundle):
    fresh = at.build_bundle(at._live_results(include_retired=at.retired_in_bundle(bundle)), bundle["header"]["methodologyHashSha256"])
    if fresh["commitmentBlake2b256"] != bundle["commitmentBlake2b256"]:
        old = {r["target"]: r for r in bundle["records"]}
        for r in fresh["records"]:
            o = old.get(r["target"])
            diffs = {k: (o.get(k) if o else None, r[k]) for k in at.SCORE_FIELDS + ("l1CappedComposite",)
                     if not o or o.get(k) != r[k]}
            if diffs:
                print("DRIFT", r["target"], diffs, file=sys.stderr)
        _die("live score_all() no longer matches the bundle: regenerate the bundle, do not anchor stale scores")
    return len(fresh["records"])


def guard_key(refuse_exposed=True):
    """Returns (priv, pub, address). `send` refuses a key file marked exposed_in_git_history, like
    publish_attestation.py; `plan` (rehearsal) only warns."""
    try:
        priv, pub, address, exposed = publisher_key.load()
    except publisher_key.PublisherKeyExposed as e:
        _die(f"REFUSED: {e}")
    if exposed and refuse_exposed:
        _die("REFUSED: the publisher key file is marked exposed_in_git_history=true. A broadcast "
             "signed by it proves nothing about who published. Rotate to a fresh, never-committed "
             "key first (funding it is a manual action by Spap).")
    if exposed:
        print("WARNING: key file marked exposed_in_git_history: this plan is a rehearsal only.", file=sys.stderr)
    if pub.hex() != publisher_key.PUBKEY_HEX or address != publisher_key.ADDRESS:
        _die("key file is not the known ARO Testnet publisher key")
    return priv, pub, address


def utxo_preflight(address, utxo):
    _txid, _vout, value = utxo
    a = zr.taddr_balance(HOST, address)
    b = cipherscan_balance(address)
    if not (a == b == value):
        _die(f"UTXO preflight failed: expected balance {value} zat, lightwalletd says {a}, cipherscan says {b}")
    return a, b


def sign_commitment(priv, pub, commitment: bytes) -> bytes:
    sig = ec.ecdsa_sign(priv, commitment)
    assert ec.ecdsa_verify(pub, commitment, sig), "self-check: signature must verify"
    return sig


def find_confirmation(raw: bytes, address: str, start_height: int):
    """Height of the block containing exactly `raw`, or None."""
    end = tip_height() + 5
    rng = zr.field_bytes(1, zr.field_varint(1, start_height)) + zr.field_bytes(2, zr.field_varint(1, end))
    msg = zr.field_bytes(1, address.encode()) + zr.field_bytes(2, rng)
    for m in zr.grpc(HOST, "GetTaddressTxids", msg):
        f = dict(zr.decode(m))
        if f.get(1, b"") == raw and f.get(2, 0):
            return f[2]
    return None


def key_note(address):
    if address == publisher_key.LEGACY_EXPOSED_ADDRESS:
        return ("Zcash TESTNET-only throwaway key, zero value. Its private half was committed in "
                "clear in 40ca1a4 and stays readable in the private repo's history: a signature by "
                "it proves 'someone with access to that history', not a specific publisher "
                "(risk accepted by the maintainer, see chains/zcash/METHODOLOGY.md 9.6).")
    if address == publisher_key.ADDRESS:
        return ("Zcash TESTNET-only key, zero value, generated at rotation time (2026-09-19 evening UTC) "
                "with os.urandom and kept only in an "
                "out-of-repo key file: it was never written to a tracked file or a commit. It replaces the key "
                "committed in clear at 40ca1a4; its funds came from that key's address by one sweep "
                "transaction (chains/zcash/data/publisher_key_exposure_2026-09-19.md), not from a faucet.")
    return "Zcash TESTNET-only key, zero value, kept in an out-of-repo key file."



def build_record(bundle, sig, pub, address, publish_time, plan, anchor, reanchors=None):
    rec = json.loads(json.dumps(bundle))  # deep copy: header, commitment, opReturnDataHex, records
    rec.update({
        "format": ENVELOPE_FORMAT,
        "project": "authority-risk-oracle",
        "repo": "RealSpap/authority-risk-oracle (private)",
        "ecosystem": "zcash",
        "network": "Zcash Testnet (never Mainnet)",
        "magic": "ARO2",
        "publishedAtUtc": publish_time,
        "publishedAtNote": ("Informational only, NOT part of the commitment or the signature. The "
                            "trust-bearing timestamp is the block time in `anchor`."),
        "publisherPubkeyCompressed": pub.hex(),
        "publisherAddress_ZcashTestnet": address,
        "attestationSignatureDer": sig.hex(),
        "signedMessage": ("the 32 raw bytes of commitmentBlake2b256, used directly as the ECDSA secp256k1 message "
                          "digest (no SHA-256 or any other hashing on top), RFC 6979, low-S, DER"),
        "publisherKeyNote": key_note(address),
        "methodologyFile": "chains/zcash/METHODOLOGY.md",
        "methodologyPinnedAt": {
            "gitCommit": "9fe6270df6d2b524da48a4d8f3956065019ca4d1",
            "note": ("header.methodologyHashSha256 is the SHA-256 of METHODOLOGY.md as committed there "
                     "(`git show <commit>:chains/zcash/METHODOLOGY.md | sha256sum`); the file was edited "
                     "afterwards to document this very publication, so the CURRENT file hashes differently."),
        },
        "scoreComputedBy": "chains/zcash/scorers.py score_all()",
        "sourceDataFile": "chains/zcash/data/scored_targets_2026-09-19.md",
        "supersedesV1": False,
        "v1AttestationFile": "chains/zcash/data/testnet_attestation_2026-09-19.json",
        "v1Note": "The ARO1 attestation and its transaction are untouched and remain independently valid.",
        "anchor": anchor,
    })
    if reanchors:
        rec["reanchorsTxid"] = reanchors
        rec["reanchorNote"] = ("Same commitment and OP_RETURN payload as the ARO2 transaction named in "
                               "`reanchorsTxid`, republished from a different (rotated) publisher key.")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=("plan", "send", "finish"))
    ap.add_argument("bundle")
    ap.add_argument("--out", default=None)
    ap.add_argument("--utxo", default=None, help="TXID:VOUT:VALUE_ZAT (default: attest_scores.DEFAULT_UTXO)")
    ap.add_argument("--state", default=None, help="send/finish: pending-state file written right after an accepted broadcast")
    ap.add_argument("--skip-live", action="store_true", help="plan only: skip the fresh score_all() re-derivation")
    ap.add_argument("--reanchors", default=None, metavar="TXID",
                    help="send/finish: record that this republishes the commitment of an earlier ARO2 tx (its txid)")
    a = ap.parse_args(argv)
    if a.reanchors is not None and not (len(a.reanchors) == 64 and all(c in "0123456789abcdef" for c in a.reanchors)):
        _die("--reanchors must be a 64-character lowercase hex txid")

    bundle = load_bundle(a.bundle)
    print(f"bundle OK: {bundle['header']['targetCount']} targets, commitment {bundle['commitmentBlake2b256']}")

    if a.mode == "finish":
        if not a.state:
            _die("finish needs --state")
        with open(a.state) as f:
            st = json.load(f)
        return finish(a, bundle, st)

    if a.mode == "send" and a.skip_live:
        _die("--skip-live is only allowed in plan mode")
    # cheap refusals first (no network): key present, not marked exposed, is the known publisher key
    priv, pub, address = guard_key(refuse_exposed=(a.mode == "send"))
    if not a.skip_live:
        n = live_check(bundle)
        print(f"live score_all() re-derivation: MATCH ({n} targets)")
    utxo = at.DEFAULT_UTXO
    if a.utxo:
        t, i, v = a.utxo.split(":")
        utxo = (t, int(i), int(v))
    lw, cs = utxo_preflight(address, utxo)
    print(f"UTXO preflight: {utxo[0]}:{utxo[1]} = {utxo[2]} zat; lightwalletd {lw}, cipherscan {cs}")

    commitment = bytes.fromhex(bundle["commitmentBlake2b256"])
    sig = sign_commitment(priv, pub, commitment)
    tip = tip_height()
    expiry = tip + EXPIRY_DELTA
    data = bytes.fromhex(bundle["opReturnDataHex"])
    plan = at.build_tx(data, utxo, expiry)
    at.check_tx(plan["rawTxHex"], data, plan["publisherAddress"])
    print(f"tip {tip}, expiryHeight {expiry}, fee {plan['feeZat']} zat "
          f"(ZIP-317 conventional {plan['zip317ConventionalFeeZat']}), change {plan['changeZat']} zat")
    print("predicted txid:", plan["predictedTxid"])
    print("raw tx bytes:", plan["rawTxBytes"])
    if a.mode == "plan":
        print("(plan only -- NOT broadcast)")
        return 0

    publish_time = utc(time.time())
    raw = bytes.fromhex(plan["rawTxHex"])
    print("Broadcasting via", HOST, "...")
    code, msg = tx.send_transaction(HOST, raw)
    print("errorCode:", code, "errorMessage:", repr(msg))
    if code != 0 or plan["predictedTxid"] not in str(msg).lower():
        _die("broadcast was not accepted with the predicted txid: NOT recording anything")
    st = {"plan": plan, "signatureDer": sig.hex(), "publishedAtUtc": publish_time, "tipAtBuild": tip,
          "publisherAddress": address, "publisherPubkey": pub.hex()}
    if a.state:  # holds no secret: public tx, public signature
        with open(a.state, "w") as f:
            json.dump(st, f, indent=2, sort_keys=True)
    print("accepted; waiting for confirmation ...")
    return finish(a, bundle, st)


def finish(a, bundle, st):
    plan, raw = st["plan"], bytes.fromhex(st["plan"]["rawTxHex"])
    deadline = time.time() + CONFIRM_TIMEOUT_S
    height = None
    while time.time() < deadline:
        height = find_confirmation(raw, st["publisherAddress"], st["tipAtBuild"] - 2)
        if height:
            break
        time.sleep(POLL_S)
    if not height:
        _die(f"accepted but not confirmed within {CONFIRM_TIMEOUT_S}s: run `finish` later with --state "
             f"(txid {plan['predictedTxid']}, expiry height {plan['expiryHeight']})")
    return write_record(a, bundle, bytes.fromhex(st["signatureDer"]), bytes.fromhex(st["publisherPubkey"]),
                        st["publisherAddress"], st["publishedAtUtc"], plan, height)


def anchor_dict(plan, height):
    bt = block_time(HOST, height)
    return {
        "txid": plan["predictedTxid"], "blockHeight": height, "blockTimeUnix": bt, "blockTimeUtc": utc(bt),
        "network": "Zcash Testnet", "txVersion": 6, "feeZat": plan["feeZat"], "expiryHeight": plan["expiryHeight"],
        "spentUtxo": plan["spentUtxo"], "changeZat": plan["changeZat"], "rawTxBytes": plan["rawTxBytes"],
        "rawTxHex": plan["rawTxHex"],
        "explorer": "https://testnet.cipherscan.app/tx/" + plan["predictedTxid"],
    }


def write_record(a, bundle, sig, pub, address, publish_time, plan, height):
    anchor = anchor_dict(plan, height)
    rec = build_record(bundle, sig, pub, address, publish_time, plan, anchor, getattr(a, "reanchors", None))
    out = json.dumps(rec, indent=2, sort_keys=True) + "\n"
    if a.out:
        with open(a.out, "w") as f:
            f.write(out)
        print("record written to", a.out)
    print(f"CONFIRMED: txid {anchor['txid']} block {height} ({anchor['blockTimeUtc']})")
    return 0



if __name__ == "__main__":
    sys.exit(main())
