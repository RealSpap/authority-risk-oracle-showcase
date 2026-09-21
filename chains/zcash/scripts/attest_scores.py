#!/usr/bin/env python3
"""Batch score attestation for Zcash: the native "contract that publishes the
scores" for a chain with no contract VM (METHODOLOGY.md section 9, "What is
deliberately NOT done here": the missing automation step between a
`scorers.py` re-run and an `OP_RETURN` anchor).

Where `publish_attestation.py` (the 2026-09-19 Testnet proof of concept)
anchored ONE hand-copied score (Zcash L1) with a commitment that also covered
a wall-clock timestamp and free-text notes, this module turns the WHOLE
`score_all()` output into one deterministic commitment:

  1. `canonical_record(r)` keeps only the authority data of one scored target
     (target id + the five sub-scores + composite + l1CappedComposite). Labels
     and `notes` are deliberately excluded: notes carry live balances and
     sample windows that legitimately move between runs, so hashing them would
     make the commitment change even when no score did.
  2. Each record is hashed into a leaf (BLAKE2b-256, personalization
     `AROzecLeaf___v1_`), leaves are sorted by target id and folded into a
     binary Merkle root (`AROzecNode___v1_`; an odd node is PROMOTED, never
     duplicated, so two different leaf lists can never share a root the way
     Bitcoin's duplicate-last-leaf rule allows). Any single target's score can
     later be proven against the anchored root with a log2(n) inclusion proof.
  3. The batch header {format, ecosystem, methodologyHashSha256, merkleRoot,
     targetCount} is hashed (`AROzecBatch__v1_`) into the 32-byte commitment.
     No timestamp inside: the commitment is a pure function of (scores,
     methodology), so an unchanged re-run re-derives the SAME commitment (no
     need to republish), and the publication time is the block's own time.
  4. `OP_RETURN` payload = b"ARO2" + commitment (36 bytes, same size as the
     "ARO1" proof of concept, so the same ZIP-317 fee class).
  5. `build_tx()` builds and signs (RFC 6979, deterministic) a fully
     transparent v6 Testnet transaction spending one P2PKH UTXO of the
     publisher address into [OP_RETURN, change]. It NEVER broadcasts: there is
     no send path in this module. Broadcasting is the deploy_testnet phase's
     job (`zcash_tx.send_transaction`).

Usage (from chains/zcash/scripts):
  python3 attest_scores.py snapshot OUT.json            # live score_all() -> raw snapshot
  python3 attest_scores.py bundle SNAPSHOT.json OUT.json  # snapshot -> attestation bundle (offline)
  python3 attest_scores.py plan-tx BUNDLE.json --expiry-height H [--utxo TXID:VOUT:VALUE]
                                                        # offline build+sign, prints raw tx, NO broadcast
  python3 attest_scores.py verify BUNDLE.json [--snapshot SNAPSHOT.json | --live]
                                                        # re-derive leaves/root/commitment, compare

TESTNET ONLY. The signing key is the zero-value Testnet publisher key, loaded
at run time from a file OUTSIDE this repo (publisher_key.py ->
keys/zcash-testnet.json or $ARO_ZCASH_TESTNET_KEY_FILE). Its address is the
only funded one this project controls on Zcash Testnet. The key used until
2026-09-19 was exposed in git history (commit 40ca1a4) and was rotated on the
evening of 2026-09-19 UTC; a plan built with a key file still marked exposed is
a rehearsal only, not a publishable ARO2 anchor.
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import secp256k1 as ec  # noqa: E402
import zcash_tx as tx  # noqa: E402
import zcash_read as zr  # noqa: E402
from zcash_retired_targets import retired_in_bundle  # noqa: E402

FORMAT = "aro-zcash-batch-v1"
MAGIC = b"ARO2"
PERS_LEAF = b"AROzecLeaf___v1_"
PERS_NODE = b"AROzecNode___v1_"
PERS_BATCH = b"AROzecBatch__v1_"
for _p in (PERS_LEAF, PERS_NODE, PERS_BATCH):
    assert len(_p) == 16, _p

SCORE_FIELDS = ("adminKeyScore", "multisigScore", "timelockScore",
                "oracleAuthorityScore", "crossExposureScore", "compositeScore")
METHODOLOGY_PATH = os.path.join(HERE, "..", "METHODOLOGY.md")

# The only funded UTXO this project controls on Zcash Testnet today: output 1
# (change, 9,925,000 zat) of the ARO2 six-live-targets transaction 462de12b...,
# block 4,371,248 (2026-09-20 19:23 UTC). It belongs to publisher_key.ADDRESS, so plans
# built with the current key file spend it. Chain of custody: the exposed key's
# address held 18791a4c...:1 (9,965,000 zat); the key rotation of 2026-09-19 (UTC
# evening; 2026-09-20 in Europe/Paris) swept it to the rotated address as
# d2b5a319...:0 (9,955,000 zat, fee 10,000), the re-anchor eeaa894c... (block 4,368,633)
# spent that output and left 9,940,000 zat as its change output 1, and the six-live anchor
# spent that one (fee 15,000). See data/publisher_key_exposure_2026-09-19.md and METHODOLOGY 9.8.
# Update this constant after every broadcast: publish_batch.utxo_preflight aborts when the
# address balance differs.
DEFAULT_UTXO = ("462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c", 1, 9_925_000)

# ZIP-317 constants (https://zips.z.cash/zip-0317, "Fee calculation").
MARGINAL_FEE = 5000
GRACE_ACTIONS = 2
P2PKH_STANDARD_INPUT_SIZE = 150
P2PKH_STANDARD_OUTPUT_SIZE = 34


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def blake(personal: bytes, data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32, person=personal).digest()


def methodology_hash(path: str = METHODOLOGY_PATH) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def canonical_record(r: dict) -> dict:
    rec = {"target": str(r["target"])}
    for k in SCORE_FIELDS:
        v = r[k]
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
            raise ValueError(f"{r['target']}: {k}={v!r} is not an int in [0,100]")
        rec[k] = v
    cap = r.get("l1CappedComposite")
    if cap is not None and (not isinstance(cap, int) or not 0 <= cap <= 100):
        raise ValueError(f"{r['target']}: l1CappedComposite={cap!r} invalid")
    rec["l1CappedComposite"] = cap  # None (JSON null) for targets it does not apply to
    return rec


def leaf_hash(rec: dict) -> bytes:
    return blake(PERS_LEAF, canonical_json(rec))


def merkle_root(leaves: list) -> bytes:
    if not leaves:
        raise ValueError("empty batch")
    level = list(leaves)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(blake(PERS_NODE, level[i] + level[i + 1]))
            else:
                nxt.append(level[i])  # promote, never duplicate
        level = nxt
    return level[0]


def merkle_proof(leaves: list, index: int) -> list:
    """[(sibling_hex, 'L'|'R'), ...] from leaf to root; promoted levels add nothing."""
    proof, level, idx = [], list(leaves), index
    while len(level) > 1:
        sib = idx ^ 1
        if sib < len(level):
            proof.append((level[sib].hex(), "L" if sib < idx else "R"))
        nxt = []
        for i in range(0, len(level), 2):
            nxt.append(blake(PERS_NODE, level[i] + level[i + 1]) if i + 1 < len(level) else level[i])
        level, idx = nxt, idx // 2
    return proof


def verify_proof(leaf: bytes, proof: list, root: bytes) -> bool:
    h = leaf
    for sib_hex, side in proof:
        sib = bytes.fromhex(sib_hex)
        h = blake(PERS_NODE, sib + h) if side == "L" else blake(PERS_NODE, h + sib)
    return h == root


def build_bundle(results: list, methodology_sha256: str) -> dict:
    records = sorted((canonical_record(r) for r in results), key=lambda x: x["target"])
    targets = [r["target"] for r in records]
    if len(set(targets)) != len(targets):
        raise ValueError(f"duplicate target ids in batch: {targets}")
    leaves = [leaf_hash(r) for r in records]
    root = merkle_root(leaves)
    header = {"format": FORMAT, "ecosystem": "zcash", "methodologyHashSha256": methodology_sha256,
              "merkleRoot": root.hex(), "targetCount": len(records)}
    commitment = blake(PERS_BATCH, canonical_json(header))
    labels = {str(r["target"]): r.get("label", "") for r in results}
    return {
        "header": header,
        "commitmentBlake2b256": commitment.hex(),
        "opReturnDataHex": (MAGIC + commitment).hex(),
        "records": [dict(rec, leafHash=lf.hex(), inclusionProof=merkle_proof(leaves, i),
                         label=labels.get(rec["target"], ""))
                    for i, (rec, lf) in enumerate(zip(records, leaves))],
    }


def rederive(bundle: dict) -> dict:
    """Recompute everything from the bundle's own records + header fields only."""
    recs = [{k: v for k, v in r.items() if k not in ("leafHash", "inclusionProof", "label")}
            for r in bundle["records"]]
    return build_bundle(recs, bundle["header"]["methodologyHashSha256"])


def zip317_fee(vin_sizes: list, vout_sizes: list) -> int:
    logical = max(math.ceil(sum(vin_sizes) / P2PKH_STANDARD_INPUT_SIZE),
                  math.ceil(sum(vout_sizes) / P2PKH_STANDARD_OUTPUT_SIZE))
    return MARGINAL_FEE * max(GRACE_ACTIONS, logical)


def _publisher(allow_legacy_exposed=False):
    # CORRECTION 2026-09-19: the key is loaded from a file OUTSIDE the repo
    # (publisher_key.py, keys/zcash-testnet.json); a missing file raises
    # publisher_key.PublisherKeyMissing with an explicit message.
    import publisher_key
    priv, pub, address, exposed = publisher_key.load(allow_legacy_exposed=allow_legacy_exposed)
    if exposed:
        print("WARNING: publisher key is marked exposed_in_git_history (commit 40ca1a4). "
              "This plan is a rehearsal only, not a publishable ARO2 anchor, until the key "
              "is rotated.", file=sys.stderr)
    return priv, pub, address


def build_tx(op_return_data: bytes, utxo, expiry_height: int, fee: int = None, lock_time: int = 0,
             allow_legacy_exposed: bool = False) -> dict:
    """Offline: build + sign, never broadcast. utxo = (txid_display_hex, vout, value_zat).
    allow_legacy_exposed exists ONLY for the test that rebuilds the ARO1 transaction with the
    exposed key; without it a key file holding that key is refused by identity."""
    priv, pub, address = _publisher(allow_legacy_exposed)
    txid_disp, vout_idx, value = utxo
    prev_script = bytes.fromhex(zr.transparent_output_script(address))
    op_script = tx.op_return_script(op_return_data)

    def assemble(fee_zat):
        vin = [tx.TxIn(bytes.fromhex(txid_disp)[::-1], vout_idx)]
        vout = [tx.TxOut(0, op_script), tx.TxOut(value - fee_zat, prev_script)]
        sighash, der = tx.sign_p2pkh_input(priv, pub, vin, vout, 0, value, prev_script, lock_time, expiry_height)
        return vin, vout, sighash, der

    vin, vout, _, _ = assemble(fee or 0)
    in_sizes = [len(i.outpoint()) + len(tx.field(i.script_sig)) + 4 for i in vin]
    out_sizes = [len(o.ser()) for o in vout]
    conventional = zip317_fee(in_sizes, out_sizes)
    fee = conventional if fee is None else fee
    if fee < conventional:
        raise ValueError(f"fee {fee} below ZIP-317 conventional fee {conventional}")
    if value - fee < 0:
        raise ValueError("UTXO too small for fee")
    vin, vout, sighash, der = assemble(fee)
    raw = tx.serialize_tx(vin, vout, lock_time, expiry_height)
    return {
        "network": "Zcash Testnet (branch 0x%08x)" % tx.TESTNET_BRANCH_ID,
        "publisherAddress": address, "spentUtxo": f"{txid_disp}:{vout_idx}", "spentValueZat": value,
        "feeZat": fee, "zip317ConventionalFeeZat": conventional, "changeZat": value - fee,
        "expiryHeight": expiry_height, "lockTime": lock_time,
        "sighashHex": sighash.hex(), "signatureDerHex": der.hex(),
        "predictedTxid": tx.txid_hex_display(vin, vout, lock_time, expiry_height),
        "rawTxHex": raw.hex(), "rawTxBytes": len(raw), "broadcast": False,
    }


def check_tx(raw_hex: str, op_return_data: bytes, publisher_address: str) -> None:
    """Independent read-back with zcash_read.py's own (separately written) parser."""
    ver, outs = zr.parse_tx_transparent_outputs(bytes.fromhex(raw_hex))
    assert ver == 6, ver
    assert outs[0] == (0, tx.op_return_script(op_return_data).hex()), outs[0]
    assert outs[1][1] == zr.transparent_output_script(publisher_address), outs[1]


def _live_results(include_retired=False):
    """A live score_all() run. `include_retired` adds targets retired from the live set (see zcash_retired_targets.py):
    True for all of them, or the set of ids, which only a commitment made BEFORE their retirement still contains."""
    sys.path.insert(0, os.path.join(HERE, ".."))
    from scorers import score_all
    return score_all(include_retired=include_retired)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("out")
    b = sub.add_parser("bundle"); b.add_argument("snapshot"); b.add_argument("out")
    p = sub.add_parser("plan-tx"); p.add_argument("bundle"); p.add_argument("--expiry-height", type=int, required=True)
    p.add_argument("--utxo", default=None, help="TXID:VOUT:VALUE_ZAT (default: the known publisher change UTXO)")
    p.add_argument("--fee", type=int, default=None); p.add_argument("--out", default=None)
    v = sub.add_parser("verify"); v.add_argument("bundle")
    g = v.add_mutually_exclusive_group(); g.add_argument("--snapshot"); g.add_argument("--live", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "snapshot":
        res = _live_results()
        with open(a.out, "w") as f:
            json.dump(res, f, indent=2, sort_keys=True, default=str)
        print(f"{len(res)} targets written to {a.out}")
    elif a.cmd == "bundle":
        with open(a.snapshot) as f:
            res = json.load(f)
        bundle = build_bundle(res, methodology_hash())
        with open(a.out, "w") as f:
            json.dump(bundle, f, indent=2, sort_keys=True)
            f.write("\n")
        print("commitment", bundle["commitmentBlake2b256"], "targets", bundle["header"]["targetCount"])
        print("OP_RETURN", bundle["opReturnDataHex"])
    elif a.cmd == "plan-tx":
        with open(a.bundle) as f:
            bundle = json.load(f)
        again = rederive(bundle)
        assert again["commitmentBlake2b256"] == bundle["commitmentBlake2b256"], "bundle does not re-derive"
        utxo = DEFAULT_UTXO
        if a.utxo:
            t, i, val = a.utxo.split(":"); utxo = (t, int(i), int(val))
        data = bytes.fromhex(bundle["opReturnDataHex"])
        plan = build_tx(data, utxo, a.expiry_height, a.fee)
        check_tx(plan["rawTxHex"], data, plan["publisherAddress"])
        plan["commitmentBlake2b256"] = bundle["commitmentBlake2b256"]
        out = json.dumps(plan, indent=2, sort_keys=True)
        print(out)
        if a.out:
            with open(a.out, "w") as f:
                f.write(out + "\n")
        print("(NOT broadcast -- this module has no send path)", file=sys.stderr)
    elif a.cmd == "verify":
        with open(a.bundle) as f:
            bundle = json.load(f)
        ok = True
        again = rederive(bundle)
        root = bytes.fromhex(bundle["header"]["merkleRoot"])
        for r in bundle["records"]:
            good = verify_proof(bytes.fromhex(r["leafHash"]), r["inclusionProof"], root)
            ok &= good
            print(f"  proof {'OK ' if good else 'BAD'} {r['target']} composite={r['compositeScore']}")
        self_ok = again["commitmentBlake2b256"] == bundle["commitmentBlake2b256"]
        print("self re-derivation:", "MATCH" if self_ok else "MISMATCH")
        ok &= self_ok
        mh = methodology_hash()
        if mh != bundle["header"]["methodologyHashSha256"]:
            print(f"note: METHODOLOGY.md now hashes to {mh} (bundle pinned "
                  f"{bundle['header']['methodologyHashSha256']}) -- scores compared under the bundle's pin")
        if a.snapshot or a.live:
            if a.live:
                # a bundle made before a target was retired still contains it: re-derive it with that target too
                res = _live_results(include_retired=retired_in_bundle(bundle))
            else:
                with open(a.snapshot) as f:
                    res = json.load(f)
            fresh = build_bundle(res, bundle["header"]["methodologyHashSha256"])
            same = fresh["commitmentBlake2b256"] == bundle["commitmentBlake2b256"]
            print("re-derivation from", "live score_all()" if a.live else a.snapshot, ":", "MATCH" if same else "MISMATCH")
            if not same:
                old = {r["target"]: r for r in bundle["records"]}
                for r in fresh["records"]:
                    o = old.get(r["target"])
                    diffs = {k: (o.get(k) if o else None, r[k]) for k in SCORE_FIELDS + ("l1CappedComposite",)
                             if not o or o.get(k) != r[k]}
                    if diffs:
                        print("   DRIFT", r["target"], diffs)
                for t in set(old) - {r["target"] for r in fresh["records"]}:
                    print("   MISSING in fresh run", t)
            ok &= same
        print("VERIFY", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
