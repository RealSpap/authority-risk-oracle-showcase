"""
Unit tests for the ARO2 whole-set publication on Zcash Testnet
(`chains/zcash/scripts/publish_batch.py`, `attest_scores.py`, and the published
`chains/zcash/data/testnet_attestation_v2_2026-09-19.json`), written 2026-09-19.

Two things are pinned here, both against REAL data and not against the code
that produced them:

1. The canonical serialization: literal byte strings for one record and for
   the batch header, hashed with `hashlib` directly (a second, deliberately
   naive implementation of the Merkle rule), so a silent change to key order,
   separators, personalization or the odd-node rule breaks a test instead of
   quietly producing a different commitment.
2. The commitment against the REAL confirmed transaction. The raw bytes below
   are the transaction broadcast to Zcash Testnet on 2026-09-19 (block
   4,368,539); they are the same bytes lightwalletd (testnet.zec.rocks) and
   testnet.cipherscan.app returned. The tests parse them with the project's
   independent parser, recompute the ZIP-244/229 txid and the input signature
   digest, check the OP_RETURN payload equals "ARO2" + the commitment that the
   file's records re-derive, and check the ECDSA signature over that
   commitment.

The ARO1 attestation (single L1 score) and its transaction must stay intact
and independently verifiable: `TestV1StillIntact` pins that.

No network. No private key in this file; the RFC 6979 re-signing check only
runs when the out-of-repo key file exists and is skipped otherwise.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPTS = os.path.join(REPO_ROOT, "chains/zcash/scripts")
DATA = os.path.join(REPO_ROOT, "chains/zcash/data")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO_ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ec = _load("aro_test_batch_secp256k1", "chains/zcash/scripts/secp256k1.py")
tx = _load("aro_test_batch_zcash_tx", "chains/zcash/scripts/zcash_tx.py")
zr = _load("aro_test_batch_zcash_read", "chains/zcash/scripts/zcash_read.py")
at = _load("aro_test_batch_attest_scores", "chains/zcash/scripts/attest_scores.py")
pk = _load("aro_test_batch_publisher_key", "chains/zcash/scripts/publisher_key.py")


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

# ---- the real, confirmed ARO2 transaction (Zcash Testnet, block 4,368,539) ----
TXID = "18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37"
BLOCK = 4368539
EXPIRY_HEIGHT = 4368638
FEE_ZAT = 15000
CHANGE_ZAT = 9_965_000
RAW_TX_HEX = (
    "0600008098b684d85b16a53700000000fea8420001e575d5d4f795ade5dd7a0ae307d3a59372656dab6c4bfa7"
    "92a1d389f090a78f0010000006b483045022100d2c37b91ff02975aef8ebec4805a9cac62ab25bc91c2f4b766"
    "393c2460b23f80022041bd33061d90ceeb62dde8674ac78f8fa5a7e55ea99a6b39363f983a9fe6256c01210388"
    "e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41fffffffff020000000000000000266a"
    "2441524f3274f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662c80d98000000000019"
    "76a9142e1ee4d4133c8d426b3fa1f5ed8ee1755a2e491388ac00000000"
)
COMMITMENT = "74f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662"
PUBKEY = "0388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41f"
ADDRESS = "tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo"
PUBLISHER_SCRIPT = "76a9142e1ee4d4133c8d426b3fa1f5ed8ee1755a2e491388ac"
SIGNATURE_DER = ("30440220553d06409f49e3df922ba5e2bee4e39e706cbd6fd01cb25b1dc3a8f203aad6c30220"
                 "6e511340897f78a2c56daa82ac312af5cfc7373b68fe249bdc0058bba4f8ec6a")
METHODOLOGY_PIN = "8a3a1042690bfda50555667496ab9510bc86fd2d250cdb6a56334600996f4bb5"
MERKLE_ROOT = "a323d59c09351e9cda29f27cab34ad2078568995b7e911bc40f1c0e3012c3c93"
# the ARO1 transaction that created the UTXO the ARO2 tx spent (its change output, index 1)
V1_TXID = "f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5"

# The 7 tracked Zcash targets, in canonical (sorted-by-target) order, with their published leaf hashes.
LEAVES = {
    "0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3": "5cf1bf5bb173f7fc11c7c03d1103ebf121981eff6630956472b27db2d864c12c",
    "keyring1k6vc6vhp6e6l3rxalue9v4ux": "14f29ce9df4577bd355dc45998685e230f95a9164a941655ddfc30fd37244e03",
    "t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT": "68b579707fd3e0da32e6f7371fa2d010d67fcd4317af9b05219c5303289897e4",
    "t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE": "d634d9813d91b3508f91ea4f72c6643f920fd64c75e3e2cdc0553f9b63bf754f",
    "t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow": "517cd168ee027743cdfe08e52f95cb9347dd73b047eb215f2034de80101b6de2",
    "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo": "947c434b53c737ffeb262f7735580991e8f81ea4703e29ce3ec6102ebd72bee0",
    "zec.omft.near": "318f930e70227d7ae441d0e95e4ab8da4646ad34f416baf5fcbc7750f5781eff",
}

# Literal canonical bytes (sorted keys, no whitespace, null for a non-applicable cap).
L1_RECORD_CANONICAL = (
    b'{"adminKeyScore":20,"compositeScore":34,"crossExposureScore":100,"l1CappedComposite":null,'
    b'"multisigScore":50,"oracleAuthorityScore":100,"target":"0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3",'
    b'"timelockScore":35}'
)
HEADER_CANONICAL = (
    b'{"ecosystem":"zcash","format":"aro-zcash-batch-v1","merkleRoot":"' + MERKLE_ROOT.encode() +
    b'","methodologyHashSha256":"' + METHODOLOGY_PIN.encode() + b'","targetCount":7}'
)


def _b2(person: bytes, data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32, person=person).digest()


def _naive_root(leaves):
    """Odd node PROMOTED (never duplicated): deliberately re-written here, not imported."""
    level = list(leaves)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            nxt.append(_b2(b"AROzecNode___v1_", level[i] + level[i + 1]) if i + 1 < len(level) else level[i])
        level = nxt
    return level[0]


def _v2():
    with open(os.path.join(DATA, "testnet_attestation_v2_2026-09-19.json")) as f:
        return json.load(f)


class TestCanonicalSerialization(unittest.TestCase):
    def test_l1_record_canonical_bytes_and_leaf_hash(self):
        rec = at.canonical_record({
            "target": "0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3", "label": "ignored", "notes": ["ignored"],
            "adminKeyScore": 20, "multisigScore": 50, "timelockScore": 35,
            "oracleAuthorityScore": 100, "crossExposureScore": 100, "compositeScore": 34,
        })
        self.assertEqual(at.canonical_json(rec), L1_RECORD_CANONICAL)
        self.assertEqual(_b2(b"AROzecLeaf___v1_", L1_RECORD_CANONICAL).hex(),
                         LEAVES["0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3"])

    def test_header_canonical_bytes_hash_to_the_anchored_commitment(self):
        self.assertEqual(_b2(b"AROzecBatch__v1_", HEADER_CANONICAL).hex(), COMMITMENT)

    def test_every_published_leaf_is_the_hash_of_its_record_canonical_bytes(self):
        for r in _v2()["records"]:
            rec = {k: r[k] for k in ("adminKeyScore", "compositeScore", "crossExposureScore", "l1CappedComposite",
                                     "multisigScore", "oracleAuthorityScore", "target", "timelockScore")}
            canon = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
            self.assertEqual(_b2(b"AROzecLeaf___v1_", canon).hex(), LEAVES[r["target"]], r["target"])
            self.assertEqual(r["leafHash"], LEAVES[r["target"]])

    def test_records_are_sorted_by_target_and_cover_exactly_the_seven_targets(self):
        targets = [r["target"] for r in _v2()["records"]]
        self.assertEqual(targets, sorted(targets))
        self.assertEqual(targets, sorted(LEAVES))
        self.assertEqual(_v2()["header"]["targetCount"], 7)

    def test_naive_merkle_root_matches_the_published_root(self):
        leaves = [bytes.fromhex(LEAVES[t]) for t in sorted(LEAVES)]
        self.assertEqual(_naive_root(leaves).hex(), MERKLE_ROOT)
        self.assertEqual(at.merkle_root(leaves).hex(), MERKLE_ROOT)

    def test_l1_cap_is_null_or_int_only_for_the_two_p2sh_targets(self):
        caps = {r["target"]: r["l1CappedComposite"] for r in _v2()["records"]}
        self.assertEqual({t: c for t, c in caps.items() if c is not None},
                         {"t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow": 32, "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo": 32})

    def test_v2_domain_separation_from_v1(self):
        # different magic, different personalizations: an ARO1 commit can never be read as an ARO2 root
        self.assertEqual(at.MAGIC, b"ARO2")
        self.assertNotEqual(at.MAGIC, b"ARO1")
        for p in (at.PERS_LEAF, at.PERS_NODE, at.PERS_BATCH):
            self.assertNotEqual(p, b"AuthRiskOracle_1")

    def test_file_rederives_from_its_own_records_to_the_commitment(self):
        d = _v2()
        self.assertEqual(at.rederive(d)["commitmentBlake2b256"], COMMITMENT)
        self.assertEqual(d["commitmentBlake2b256"], COMMITMENT)
        self.assertEqual(d["opReturnDataHex"], (b"ARO2" + bytes.fromhex(COMMITMENT)).hex())
        self.assertEqual(d["header"]["methodologyHashSha256"], METHODOLOGY_PIN)
        root = bytes.fromhex(d["header"]["merkleRoot"])
        for r in d["records"]:
            self.assertTrue(at.verify_proof(bytes.fromhex(r["leafHash"]), r["inclusionProof"], root), r["target"])


class TestRealBroadcastAro2Transaction(unittest.TestCase):
    """The raw bytes below are what the network accepted and mined."""

    def setUp(self):
        self.raw = bytes.fromhex(RAW_TX_HEX)
        self.version, self.outs = zr.parse_tx_transparent_outputs(self.raw)
        self.script_sig = zr.LAST_SCRIPTSIGS[0]

    def _vin_vout(self):
        # header(4)+vgid(4)+branch(4)+locktime(4)+expiry(4)=20, then nIn(1), then prevout hash(32) + index(4)
        prevout_hash = self.raw[21:53]
        prevout_index = int.from_bytes(self.raw[53:57], "little")
        vin = [tx.TxIn(prevout_hash, prevout_index)]
        vin[0].script_sig = self.script_sig
        vout = [tx.TxOut(v, bytes.fromhex(s)) for v, s in self.outs]
        return vin, vout, prevout_hash, prevout_index

    def test_parses_as_v6_with_one_input_and_the_two_expected_outputs(self):
        self.assertEqual(self.version, 6)
        self.assertEqual(zr.LAST_NIN, 1)
        self.assertEqual(len(self.raw), 255)
        self.assertEqual(self.outs[0], (0, "6a24" + "41524f32" + COMMITMENT))
        self.assertEqual(self.outs[1], (CHANGE_ZAT, PUBLISHER_SCRIPT))

    def test_op_return_payload_is_aro2_plus_the_commitment_the_file_rederives(self):
        payload = bytes.fromhex(self.outs[0][1])[2:]
        self.assertEqual(len(payload), 36)
        self.assertEqual(payload[:4], b"ARO2")
        self.assertEqual(payload[4:].hex(), COMMITMENT)
        self.assertEqual(payload[4:].hex(), at.rederive(_v2())["commitmentBlake2b256"])

    def test_txid_is_the_zip244_229_digest_of_these_bytes(self):
        vin, vout, _, _ = self._vin_vout()
        self.assertEqual(tx.txid_hex_display(vin, vout, 0, EXPIRY_HEIGHT), TXID)

    def test_input_signature_verifies_against_the_recomputed_sighash(self):
        vin, vout, _, _ = self._vin_vout()
        sighash = tx.signature_digest_v6(vin, vout, 0, 9_980_000, bytes.fromhex(PUBLISHER_SCRIPT), 0, EXPIRY_HEIGHT)
        sig_len = self.script_sig[0]
        sig_with_type = self.script_sig[1:1 + sig_len]
        self.assertEqual(sig_with_type[-1], tx.SIGHASH_ALL)
        self.assertTrue(ec.ecdsa_verify(bytes.fromhex(PUBKEY), sighash, sig_with_type[:-1]))
        self.assertTrue(self.script_sig.endswith(bytes([33]) + bytes.fromhex(PUBKEY)))

    def test_it_spends_the_change_output_of_the_untouched_aro1_transaction(self):
        _, _, prevout_hash, prevout_index = self._vin_vout()
        self.assertEqual(prevout_hash[::-1].hex(), V1_TXID)
        self.assertEqual(prevout_index, 1)

    def test_fee_is_the_zip317_conventional_fee_for_these_exact_sizes(self):
        vin, vout, _, _ = self._vin_vout()
        in_sizes = [len(i.outpoint()) + len(tx.field(i.script_sig)) + 4 for i in vin]
        out_sizes = [len(o.ser()) for o in vout]
        self.assertEqual(sum(v for v, _ in self.outs), 9_980_000 - FEE_ZAT)
        self.assertEqual(at.zip317_fee(in_sizes, out_sizes), FEE_ZAT)
        # 1 input of <=150 bytes (148: 72-byte DER signature this time, 147 for ARO1) and 81 output bytes
        # (47 + 34): max(ceil(148/150)=1, ceil(81/34)=3) = 3 logical actions x 5000
        self.assertEqual((sum(in_sizes), sum(out_sizes)), (148, 81))

    def test_change_goes_back_to_the_publisher_address(self):
        self.assertEqual(zr.transparent_output_script(ADDRESS), PUBLISHER_SCRIPT)
        self.assertEqual("76a914" + ec.hash160(bytes.fromhex(PUBKEY)).hex() + "88ac", PUBLISHER_SCRIPT)

    def test_file_anchor_record_matches_the_pinned_transaction(self):
        d = _v2()
        a = d["anchor"]
        self.assertEqual((a["txid"], a["blockHeight"], a["feeZat"], a["expiryHeight"], a["changeZat"]),
                         (TXID, BLOCK, FEE_ZAT, EXPIRY_HEIGHT, CHANGE_ZAT))
        self.assertEqual(a["rawTxHex"], RAW_TX_HEX)
        self.assertEqual(a["rawTxBytes"], 255)
        self.assertEqual(a["spentUtxo"], V1_TXID + ":1")
        self.assertEqual(d["publisherAddress_ZcashTestnet"], ADDRESS)
        self.assertEqual(d["publisherPubkeyCompressed"], PUBKEY)
        self.assertEqual(d["magic"], "ARO2")

    def test_ecdsa_signature_over_the_commitment_verifies_and_rejects_tampering(self):
        d = _v2()
        self.assertEqual(d["attestationSignatureDer"], SIGNATURE_DER)
        sig = bytes.fromhex(SIGNATURE_DER)
        commitment = bytes.fromhex(COMMITMENT)
        self.assertTrue(ec.ecdsa_verify(bytes.fromhex(PUBKEY), commitment, sig))
        tampered = bytes([commitment[0] ^ 1]) + commitment[1:]
        self.assertFalse(ec.ecdsa_verify(bytes.fromhex(PUBKEY), tampered, sig))

    @NEEDS_LEGACY_KEY
    def test_resigning_with_the_out_of_repo_key_reproduces_signature_and_script_sig(self):
        priv, pub, _addr, _exposed = pk.load(allow_legacy_exposed=True)
        self.assertEqual(pub.hex(), PUBKEY)
        self.assertEqual(ec.ecdsa_sign(priv, bytes.fromhex(COMMITMENT)).hex(), SIGNATURE_DER)  # RFC 6979
        vin, vout, _, _ = self._vin_vout()
        vin[0].script_sig = b""
        tx.sign_p2pkh_input(priv, pub, vin, vout, 0, 9_980_000, bytes.fromhex(PUBLISHER_SCRIPT), 0, EXPIRY_HEIGHT)
        self.assertEqual(vin[0].script_sig, self.script_sig)



class TestPublishBatchGuards(unittest.TestCase):
    """`send` must refuse before touching the network."""

    def _run(self, key_json, *args):
        script = os.path.join(SCRIPTS, "publish_batch.py")
        bundle = os.path.join(DATA, "attestation_batch_2026-09-19.json")
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ)
            if key_json is not None:
                kf = os.path.join(d, "k.json")
                with open(kf, "w") as f:
                    json.dump(key_json, f)
                env[pk.ENV_VAR] = kf
            return subprocess.run([sys.executable, script, *args[:1], bundle, *args[1:]], env=env,
                                  capture_output=True, text=True, cwd=SCRIPTS, timeout=60)

    def _throwaway(self, exposed):
        priv = int.from_bytes(os.urandom(32), "big") % (ec.N - 1) + 1
        pub = ec.privkey_to_pubkey(priv)
        addr = ec.base58check(bytes.fromhex("1d25"), ec.hash160(pub))
        return priv, {"privkey_hex": "%064x" % priv, "pubkey_compressed_hex": pub.hex(), "address": addr,
                      "exposed_in_git_history": exposed}

    def test_send_refuses_a_key_file_marked_exposed(self):
        priv, kj = self._throwaway(True)
        r = self._run(kj, "send")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REFUSED", r.stderr)
        self.assertNotIn("%064x" % priv, r.stdout + r.stderr)

    def test_send_refuses_a_key_that_is_not_the_known_publisher_key(self):
        priv, kj = self._throwaway(False)
        r = self._run(kj, "send")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not the known ARO Testnet publisher key", r.stderr)
        self.assertNotIn("%064x" % priv, r.stdout + r.stderr)

    def test_send_refuses_when_the_key_file_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, **{pk.ENV_VAR: os.path.join(d, "absent.json")})
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "publish_batch.py"), "send",
                                os.path.join(DATA, "attestation_batch_2026-09-19.json")],
                               env=env, capture_output=True, text=True, cwd=SCRIPTS, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stderr)

    def test_skip_live_is_refused_in_send_mode(self):
        r = self._run(None, "send", "--skip-live")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only allowed in plan mode", r.stderr)

    def test_broadcast_path_lives_only_in_publish_batch_not_in_attest_scores(self):
        with open(os.path.join(SCRIPTS, "publish_batch.py")) as f:
            self.assertIn("send_transaction(", f.read())
        with open(os.path.join(SCRIPTS, "attest_scores.py")) as f:
            self.assertNotIn("send_transaction(", f.read())


if __name__ == "__main__":
    unittest.main()
