"""
Unit tests for `chains/zcash/scripts/attest_scores.py` -- the batch score
attestation (canonical records -> BLAKE2b Merkle root -> 32-byte commitment
-> "ARO2" OP_RETURN) and its offline, never-broadcast Testnet transaction
builder, added 2026-09-19 to close METHODOLOGY.md section 9.4's "no
automation from a scorers.py re-run to a new attestation" gap.

No network: `build_tx()` only needs the tip height the caller passes in.
Grounded in real data where it can be: the tx builder is checked against the
REAL ARO1 transaction already confirmed on Zcash Testnet (block 4,366,645),
and the ZIP-317 fee formula against the two real network verdicts on that
same transaction (10,000 zat rejected, 20,000 zat accepted).
"""
import copy
import importlib.util
import json
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
SCRIPTS = os.path.abspath(os.path.join(REPO_ROOT, "chains/zcash/scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.abspath(os.path.join(REPO_ROOT, rel)))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


at = _load("aro_test_attest_scores", "chains/zcash/scripts/attest_scores.py")
zr = _load("aro_test_zcash_read_for_attest", "chains/zcash/scripts/zcash_read.py")
pk = _load("aro_test_publisher_key_for_attest", "chains/zcash/scripts/publisher_key.py")
# build_tx() signs with the Testnet publisher key, which lives OUTSIDE the repo
# (publisher_key.py). Signing tests are skipped, not failed, when it is absent.
NEEDS_KEY = unittest.skipUnless(pk.key_available(), "out-of-repo Zcash Testnet key file absent")


def _legacy_key_loaded():
    if not pk.key_available():
        return False
    try:
        return pk.load(allow_legacy_exposed=True)[1].hex() == pk.LEGACY_EXPOSED_PUBKEY_HEX
    except (pk.PublisherKeyInvalid, KeyError, TypeError, ValueError) as e:
        # a key file that exists but cannot be used must fail loudly, not silently skip the historic checks
        raise RuntimeError(f"key file {pk.key_file_path()} exists but is unusable ({type(e).__name__})") from e


# Rebuilding a transaction the exposed 2026-09-19 key signed needs that key. It is no longer
# the active publisher key, so these checks run only when ARO_ZCASH_TESTNET_KEY_FILE points at
# the superseded key file; otherwise they are skipped (the public-bytes checks still run).
NEEDS_LEGACY_KEY = unittest.skipUnless(
    _legacy_key_loaded(), "needs the superseded (exposed) 2026-09-19 key file via ARO_ZCASH_TESTNET_KEY_FILE")

# The 7 targets exactly as data/scored_targets_2026-09-19.md publishes them.
PUBLISHED = [
    ("0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3", 20, 50, 35, 100, 100, 34, None),
    ("t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo", 50, 39, 0, 100, 100, 32, 32),
    ("t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow", 50, 39, 0, 100, 100, 32, 32),
    ("zec.omft.near", 5, 18, 0, 100, 100, 7, None),
    ("t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT", 65, 100, 0, 100, 100, 56, None),
    ("t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE", 65, 100, 0, 100, 100, 56, None),
    ("keyring1k6vc6vhp6e6l3rxalue9v4ux", 65, 60, 0, 100, 100, 44, None),
]
METH = "00" * 32


def results(notes="n"):
    out = []
    for t, a, m, tl, o, c, comp, cap in PUBLISHED:
        r = {"target": t, "label": "L-" + t, "adminKeyScore": a, "multisigScore": m, "timelockScore": tl,
             "oracleAuthorityScore": o, "crossExposureScore": c, "compositeScore": comp, "notes": [notes]}
        if cap is not None or t.startswith("t3"):
            r["l1CappedComposite"] = cap
        out.append(r)
    return out


class TestCommitmentDeterminism(unittest.TestCase):
    def test_same_scores_same_commitment_regardless_of_order_notes_labels(self):
        a = at.build_bundle(results("balance 1"), METH)
        shuffled = list(reversed(results("balance 2 -- live data moved")))
        for r in shuffled:
            r["label"] = "renamed"
        b = at.build_bundle(shuffled, METH)
        self.assertEqual(a["commitmentBlake2b256"], b["commitmentBlake2b256"])

    def test_any_single_score_change_changes_the_commitment(self):
        base = at.build_bundle(results(), METH)["commitmentBlake2b256"]
        for i in range(len(PUBLISHED)):
            for k in at.SCORE_FIELDS:
                rs = results()
                rs[i][k] = rs[i][k] - 1 if rs[i][k] > 0 else 1
                self.assertNotEqual(at.build_bundle(rs, METH)["commitmentBlake2b256"], base, (i, k))

    def test_l1_cap_and_methodology_hash_are_committed(self):
        base = at.build_bundle(results(), METH)["commitmentBlake2b256"]
        rs = results(); rs[1]["l1CappedComposite"] = 31
        self.assertNotEqual(at.build_bundle(rs, METH)["commitmentBlake2b256"], base)
        self.assertNotEqual(at.build_bundle(results(), "11" * 32)["commitmentBlake2b256"], base)

    def test_dropping_a_target_changes_the_commitment(self):
        base = at.build_bundle(results(), METH)["commitmentBlake2b256"]
        self.assertNotEqual(at.build_bundle(results()[:-1], METH)["commitmentBlake2b256"], base)

    def test_op_return_payload_is_magic_plus_commitment_36_bytes(self):
        b = at.build_bundle(results(), METH)
        data = bytes.fromhex(b["opReturnDataHex"])
        self.assertEqual(len(data), 36)
        self.assertEqual(data[:4], b"ARO2")
        self.assertEqual(data[4:].hex(), b["commitmentBlake2b256"])

    def test_bundle_rederives_from_its_own_json_roundtrip(self):
        b = json.loads(json.dumps(at.build_bundle(results(), METH)))
        self.assertEqual(at.rederive(b)["commitmentBlake2b256"], b["commitmentBlake2b256"])


class TestValidation(unittest.TestCase):
    def test_rejects_out_of_range_or_non_int_scores(self):
        for bad in (101, -1, 34.0, "34", True, None):
            rs = results(); rs[0]["compositeScore"] = bad
            with self.assertRaises((ValueError, KeyError), msg=repr(bad)):
                at.build_bundle(rs, METH)

    def test_rejects_duplicate_targets_and_empty_batches(self):
        with self.assertRaises(ValueError):
            at.build_bundle(results() + results()[:1], METH)
        with self.assertRaises(ValueError):
            at.build_bundle([], METH)


class TestMerkle(unittest.TestCase):
    def test_every_record_has_a_valid_inclusion_proof(self):
        for n in range(1, 8):
            b = at.build_bundle(results()[:n], METH)
            root = bytes.fromhex(b["header"]["merkleRoot"])
            for r in b["records"]:
                self.assertTrue(at.verify_proof(bytes.fromhex(r["leafHash"]), r["inclusionProof"], root), (n, r["target"]))

    def test_tampered_record_fails_its_proof(self):
        b = at.build_bundle(results(), METH)
        root = bytes.fromhex(b["header"]["merkleRoot"])
        rec = copy.deepcopy(b["records"][2])
        rec["compositeScore"] += 1
        clean = {k: v for k, v in rec.items() if k not in ("leafHash", "inclusionProof", "label")}
        self.assertFalse(at.verify_proof(at.leaf_hash(clean), rec["inclusionProof"], root))

    def test_odd_node_is_promoted_not_duplicated(self):
        # With duplication, [a,b,c] and [a,b,c,c] would share a root.
        leaves = [bytes([i]) * 32 for i in range(3)]
        self.assertNotEqual(at.merkle_root(leaves), at.merkle_root(leaves + leaves[-1:]))


class TestZip317Fee(unittest.TestCase):
    def test_real_aro1_tx_sizes_give_15000_consistent_with_both_network_verdicts(self):
        # Real ARO1 tx: 1 P2PKH input (147 bytes: 36 outpoint + 107 scriptSig field + 4 sequence), outputs 47 + 34 bytes.
        fee = at.zip317_fee([147], [47, 34])
        self.assertEqual(fee, 15000)
        self.assertLess(10000, fee)     # 10,000 zat was rejected by testnet.zec.rocks
        self.assertLessEqual(fee, 20000)  # 20,000 zat was accepted (block 4,366,645)

    def test_grace_actions_floor(self):
        self.assertEqual(at.zip317_fee([148], [34]), 10000)


class TestOfflineTxBuilder(unittest.TestCase):
    @NEEDS_LEGACY_KEY
    def test_reproduces_the_real_confirmed_aro1_transaction_byte_for_byte(self):
        data = b"ARO1" + bytes.fromhex("d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d")
        utxo = ("cda24edf051dd2b323ff4cf560f96c9f382dbeb1e8f0ab6810d3c5088fe42105", 0, 10_000_000)
        plan = at.build_tx(data, utxo, expiry_height=4366744, fee=20000, allow_legacy_exposed=True)
        self.assertEqual(plan["predictedTxid"], "f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5")
        self.assertFalse(plan["broadcast"])
        # ZIP-244 txids exclude scriptSigs, so also pin the full signed bytes
        # (the exact raw tx the network accepted, see test_zcash_tx.py).
        ref = _load("aro_test_zcash_tx_ref", "scripts/lib/tests/test_zcash_tx.py")
        self.assertEqual(plan["rawTxHex"], ref.TestRealBroadcastTransaction.EXPECTED_RAW_TX_HEX)

    @NEEDS_KEY
    def test_aro2_plan_is_well_formed_and_read_back_by_the_independent_parser(self):
        b = at.build_bundle(results(), METH)
        data = bytes.fromhex(b["opReturnDataHex"])
        plan = at.build_tx(data, at.DEFAULT_UTXO, expiry_height=4368100)
        at.check_tx(plan["rawTxHex"], data, plan["publisherAddress"])
        ver, outs = zr.parse_tx_transparent_outputs(bytes.fromhex(plan["rawTxHex"]))
        self.assertEqual(outs[0][1], "6a24" + b["opReturnDataHex"])
        self.assertEqual(plan["feeZat"], plan["zip317ConventionalFeeZat"])
        self.assertEqual(outs[1][0], at.DEFAULT_UTXO[2] - plan["feeZat"])

    @NEEDS_KEY
    def test_plan_is_deterministic(self):
        data = bytes.fromhex(at.build_bundle(results(), METH)["opReturnDataHex"])
        p1 = at.build_tx(data, at.DEFAULT_UTXO, expiry_height=4368100)
        p2 = at.build_tx(data, at.DEFAULT_UTXO, expiry_height=4368100)
        self.assertEqual(p1["rawTxHex"], p2["rawTxHex"])

    @NEEDS_KEY
    def test_underpaid_fee_is_refused(self):
        data = bytes.fromhex(at.build_bundle(results(), METH)["opReturnDataHex"])
        with self.assertRaises(ValueError):
            at.build_tx(data, at.DEFAULT_UTXO, expiry_height=4368100, fee=10000)

    def test_missing_key_file_is_an_explicit_error(self):
        old = os.environ.get(pk.ENV_VAR)
        os.environ[pk.ENV_VAR] = os.path.join(SCRIPTS, "no_such_zcash_key.json")
        try:
            data = bytes.fromhex(at.build_bundle(results(), METH)["opReturnDataHex"])
            with self.assertRaises(FileNotFoundError) as cm:
                at.build_tx(data, at.DEFAULT_UTXO, expiry_height=4368100)
            self.assertIn("not found", str(cm.exception))
        finally:
            if old is None:
                del os.environ[pk.ENV_VAR]
            else:
                os.environ[pk.ENV_VAR] = old

    def test_module_has_no_broadcast_path(self):
        src = open(os.path.join(SCRIPTS, "attest_scores.py")).read()
        self.assertNotIn("send_transaction(", src)


class TestCommittedBundle(unittest.TestCase):
    """The committed data/attestation_batch_2026-09-19.json must re-derive
    from its own records AND match the published 2026-09-19 score table."""

    def setUp(self):
        with open(os.path.join(REPO_ROOT, "chains/zcash/data/attestation_batch_2026-09-19.json")) as f:
            self.bundle = json.load(f)

    def test_self_rederivation(self):
        self.assertEqual(at.rederive(self.bundle)["commitmentBlake2b256"], self.bundle["commitmentBlake2b256"])

    def test_matches_published_table(self):
        fresh = at.build_bundle(results(), self.bundle["header"]["methodologyHashSha256"])
        self.assertEqual(fresh["commitmentBlake2b256"], self.bundle["commitmentBlake2b256"])


if __name__ == "__main__":
    unittest.main()
