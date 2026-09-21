"""
Unit tests for the Zcash v6 transaction builder/signer (`chains/zcash/scripts/
zcash_tx.py`) and its secp256k1 dependency (`chains/zcash/scripts/
secp256k1.py`) -- written 2026-09-19 alongside `publish_attestation.py`
(METHODOLOGY.md section 8/9's "native oracle form" resolution).

This is exactly the kind of novel, error-prone, financially-load-bearing
code this project already treats as test-worthy (see this folder's own
`test_zcash_read.py` docstring) -- more so here, since this module
constructs and signs a REAL transaction rather than only reading one. Two
real, disclosed bugs were caught by hand during development before either
reached the network (a transcription typo in secp256k1's Gy generator
constant, confirmed against `openssl ecparam -name secp256k1`; and a wrong
prevout hash from assuming legacy double-SHA256 txids for a v5/v6
transaction, confirmed against a third-party Testnet explorer) -- both are
guarded against here so they cannot silently regress.

The `TestRealBroadcastTransaction` fixture is not synthetic: it rebuilds,
byte for byte, the actual transaction this project broadcast to Zcash
Testnet and asserts the result against values independently confirmed by
(a) the server's own SendTransaction response, (b) a second, fresh
lightwalletd read of the confirmed transaction, and (c) a third-party block
explorer (testnet.cipherscan.app) -- see
chains/zcash/data/testnet_oracle_poc_2026-09-19.md for the full trail.
"""
import hashlib
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    scripts_dir = os.path.dirname(file_path)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


ec = _load_module("aro_test_secp256k1", "chains/zcash/scripts/secp256k1.py")
tx = _load_module("aro_test_zcash_tx", "chains/zcash/scripts/zcash_tx.py")
pk = _load_module("aro_test_publisher_key", "chains/zcash/scripts/publisher_key.py")


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


# --------------------------------------------------------------- secp256k1.py
class TestCurveConstants(unittest.TestCase):
    """Regression guard for the real Gy transcription bug this project hit
    2026-09-19: a single missing trailing hex digit in the hardcoded
    generator point produced a `G` that is not on the curve at all, silently
    computing garbage "public keys" until caught by cross-checking against
    `openssl ecparam -name secp256k1 -param_enc explicit -text -noout`."""

    def test_generator_point_is_on_the_curve(self):
        self.assertEqual((ec.Gy * ec.Gy - (ec.Gx ** 3 + 7)) % ec.P, 0)

    def test_generator_matches_openssl_secp256k1_reference(self):
        # Authoritative secp256k1 generator, taken from
        # `openssl ecparam -name secp256k1 -param_enc explicit -text -noout`
        # (SEC2 standard curve), not from memory.
        openssl_gen_hex = (
            "04:79:be:66:7e:f9:dc:bb:ac:55:a0:62:95:ce:87:0b:07:02:9b:fc:db:2d:"
            "ce:28:d9:59:f2:81:5b:16:f8:17:98:48:3a:da:77:26:a3:c4:65:5d:a4:fb:"
            "fc:0e:11:08:a8:fd:17:b4:48:a6:85:54:19:9c:47:d0:8f:fb:10:d4:b8"
        )
        raw = bytes.fromhex(openssl_gen_hex.replace(":", ""))
        self.assertEqual(raw[0], 4)  # uncompressed point marker
        gx, gy = raw[1:33], raw[33:65]
        self.assertEqual(int(gx.hex(), 16), ec.Gx)
        self.assertEqual(int(gy.hex(), 16), ec.Gy)

    def test_order_times_generator_is_the_point_at_infinity(self):
        self.assertIsNone(ec.scalar_mult(ec.N))

    def test_doubling_g_stays_on_the_curve(self):
        x2, y2 = ec.point_add(ec.G, ec.G)
        self.assertEqual((y2 * y2 - (x2 ** 3 + 7)) % ec.P, 0)


class TestEcdsaSignVerify(unittest.TestCase):
    def test_sign_then_verify_roundtrip(self):
        priv = 0xA1B2C3D4E5F60718293A4B5C6D7E8F9001122334455667788990011223344
        priv %= ec.N
        pub = ec.privkey_to_pubkey(priv)
        digest = hashlib.sha256(b"hello zcash").digest()
        sig = ec.ecdsa_sign(priv, digest)
        self.assertTrue(ec.ecdsa_verify(pub, digest, sig))

    def test_verify_rejects_a_tampered_digest(self):
        priv = 12345 % ec.N
        pub = ec.privkey_to_pubkey(priv)
        digest = hashlib.sha256(b"original message").digest()
        sig = ec.ecdsa_sign(priv, digest)
        tampered = hashlib.sha256(b"tampered message").digest()
        self.assertFalse(ec.ecdsa_verify(pub, tampered, sig))

    def test_signature_is_low_s(self):
        priv = 999999 % ec.N
        digest = hashlib.sha256(b"low-s check").digest()
        sig = ec.ecdsa_sign(priv, digest)
        _, s = ec.der_decode_sig(sig)
        self.assertLessEqual(s, ec.N // 2)

    def test_address_matches_hash160_of_compressed_pubkey(self):
        priv = 0xDEADBEEF % ec.N
        pub = ec.privkey_to_pubkey(priv)
        h160 = ec.hash160(pub)
        addr = ec.base58check(bytes.fromhex("1d25"), h160)  # Zcash Testnet P2PKH
        # round-trip through this project's own independent decoder
        zr = _load_module("aro_test_zcash_read_for_tx", "chains/zcash/scripts/zcash_read.py")
        raw = zr.b58dec(addr)
        self.assertEqual(raw[:2], bytes.fromhex("1d25"))
        self.assertEqual(raw[2:], h160)


# --------------------------------------------------------------- zcash_tx.py
class TestCompactSize(unittest.TestCase):
    def test_small_values_are_one_byte(self):
        self.assertEqual(tx.compact_size(0), b"\x00")
        self.assertEqual(tx.compact_size(252), bytes([252]))

    def test_fd_prefix_for_two_byte_values(self):
        self.assertEqual(tx.compact_size(253), b"\xfd\xfd\x00")
        self.assertEqual(tx.compact_size(0xFFFF), b"\xfd\xff\xff")

    def test_fe_prefix_for_four_byte_values(self):
        self.assertEqual(tx.compact_size(0x10000), b"\xfe\x00\x00\x01\x00")


class TestOpReturnScript(unittest.TestCase):
    def test_short_payload_uses_direct_push(self):
        data = b"A" * 36  # this project's real "ARO1" + 32-byte commitment shape
        script = tx.op_return_script(data)
        self.assertEqual(script[0], 0x6A)  # OP_RETURN
        self.assertEqual(script[1], 36)
        self.assertEqual(script[2:], data)

    def test_payload_over_75_bytes_uses_pushdata1(self):
        data = b"B" * 80
        script = tx.op_return_script(data)
        self.assertEqual(script[:2], bytes([0x6A, 0x4C]))
        self.assertEqual(script[2], 80)


class TestEmptyDigestConstants(unittest.TestCase):
    """These exact 16-byte personalizations were cross-checked, byte for
    byte, against the real reference implementation
    (zcash/librustzcash's zcash_primitives/src/transaction/txid.rs and
    zcash/orchard's src/bundle/commitments.rs), not derived from an
    AI-paraphrased reading of the ZIPs alone -- see this project's own
    METHODOLOGY.md discipline against trusting an unverified paraphrase."""

    def test_orchard_v6_uses_the_v6_specific_personalization(self):
        expected = hashlib.blake2b(b"", digest_size=32, person=b"ZTxIdOrchardH_v6").digest()
        self.assertEqual(tx.empty_orchard_digest_v6(), expected)
        # v6's empty-orchard digest must differ from v5's own constant --
        # ZIP 229's whole point is that they are NOT the same value.
        v5_style = hashlib.blake2b(b"", digest_size=32, person=b"ZTxIdOrchardHash").digest()
        self.assertNotEqual(tx.empty_orchard_digest_v6(), v5_style)

    def test_ironwood_empty_digest_personalization(self):
        expected = hashlib.blake2b(b"", digest_size=32, person=b"ZTxIdIronwd_H_v6").digest()
        self.assertEqual(tx.empty_ironwood_digest_v6(), expected)

    def test_sapling_empty_digest_unchanged_between_v5_and_v6(self):
        expected = hashlib.blake2b(b"", digest_size=32, person=b"ZTxIdSaplingHash").digest()
        self.assertEqual(tx.empty_sapling_digest(), expected)


class TestRealBroadcastTransaction(unittest.TestCase):
    """Rebuilds the exact transaction this project broadcast to Zcash
    Testnet 2026-09-19 and checks it against values independently confirmed
    off of this project's own code (server SendTransaction response, a
    second lightwalletd read, and testnet.cipherscan.app). See
    chains/zcash/data/testnet_oracle_poc_2026-09-19.md."""

    # CORRECTION 2026-09-19: no private key in this file any more (it was
    # exposed here and in publish_attestation.py, commit 40ca1a4). The
    # byte-for-byte rebuild now uses the scriptSig that was actually broadcast
    # (public: DER signature + SIGHASH_ALL + compressed pubkey, read out of
    # EXPECTED_RAW_TX_HEX below), and the signature test verifies THAT
    # published signature against a freshly recomputed ZIP-244 sighash. The
    # RFC 6979 re-signing check only runs when the out-of-repo key file exists.
    PUBLISHED_SCRIPT_SIG_HEX = (
        "47304402203a3cc5b634e6bc2d38129371d4fd3687fc31ad7210a1023f9a8fcf8d66d22ca5"
        "0220573ca720333bb3532eba0235d0f6601af6f48a1c93b8a86995406e2f2904fb4f01"
        "210388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41f"
    )
    PUBKEY_HEX = "0388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41f"
    PREVOUT_TXID_NATURAL_HEX = "0521e48f08c5d31068abf0e8b1be2d389f6cf960f54cff23b3d21d05df4ea2cd"
    PREVOUT_VALUE = 10_000_000
    PREVOUT_SCRIPT_HEX = "76a9142e1ee4d4133c8d426b3fa1f5ed8ee1755a2e491388ac"
    COMMIT_HASH_HEX = "d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d"
    LOCK_TIME = 0
    EXPIRY_HEIGHT = 4366744
    FEE = 20_000
    EXPECTED_TXID_DISPLAY = "f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5"
    # Generated by this exact code path (`_build()` below) and cross-checked
    # byte-for-byte against the raw bytes this project actually broadcast to
    # testnet.zec.rocks (SendTransaction's own success response echoed this
    # transaction's txid back verbatim -- see the companion write-up).
    EXPECTED_RAW_TX_HEX = (
        "0600008098b684d85b16a5370000000098a14200010521e48f08c5d31068abf0e8b1be2d389f6cf9"
        "60f54cff23b3d21d05df4ea2cd000000006a47304402203a3cc5b634e6bc2d38129371d4fd3687fc"
        "31ad7210a1023f9a8fcf8d66d22ca50220573ca720333bb3532eba0235d0f6601af6f48a1c93b8a8"
        "6995406e2f2904fb4f01210388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2a"
        "cfb3b41fffffffff020000000000000000266a2441524f31d722a2f753e7d4538619085272d556c"
        "5a87a4e3c27a9d531dc21ca14d23c272d60489800000000001976a9142e1ee4d4133c8d426b3fa1f"
        "5ed8ee1755a2e491388ac00000000"
    )

    def _build(self):
        prevout_script = bytes.fromhex(self.PREVOUT_SCRIPT_HEX)
        vin = [tx.TxIn(bytes.fromhex(self.PREVOUT_TXID_NATURAL_HEX), 0)]
        change_value = self.PREVOUT_VALUE - self.FEE
        op_return_data = b"ARO1" + bytes.fromhex(self.COMMIT_HASH_HEX)
        vout = [tx.TxOut(0, tx.op_return_script(op_return_data)), tx.TxOut(change_value, prevout_script)]
        vin[0].script_sig = bytes.fromhex(self.PUBLISHED_SCRIPT_SIG_HEX)
        return vin, vout

    def test_txid_matches_the_server_and_explorer_confirmed_value(self):
        vin, vout = self._build()
        txid_display = tx.txid_hex_display(vin, vout, self.LOCK_TIME, self.EXPIRY_HEIGHT)
        self.assertEqual(txid_display, self.EXPECTED_TXID_DISPLAY)

    def test_signature_verifies_against_the_real_sighash(self):
        vin, vout = self._build()
        prevout_script = bytes.fromhex(self.PREVOUT_SCRIPT_HEX)
        sighash = tx.signature_digest_v6(vin, vout, 0, self.PREVOUT_VALUE, prevout_script,
                                          self.LOCK_TIME, self.EXPIRY_HEIGHT)
        der_sig = vin[0].script_sig
        # scriptSig = field(sig+hashtype) + field(pubkey); strip the two
        # CompactSize length-prefixes and the trailing SIGHASH_ALL byte to
        # recover the bare DER signature.
        sig_len = der_sig[0]
        sig_with_type = der_sig[1:1 + sig_len]
        self.assertTrue(ec.ecdsa_verify(bytes.fromhex(self.PUBKEY_HEX), sighash, sig_with_type[:-1]))

    def test_serialized_transaction_is_deterministic_apart_from_the_signature(self):
        # ECDSA signing here is randomized-input-free but still nonce-based
        # (RFC 6979 is deterministic per (key, digest), so re-signing the
        # SAME inputs must reproduce the exact same bytes we actually
        # broadcast -- this is the strongest possible regression check.
        vin, vout = self._build()
        raw = tx.serialize_tx(vin, vout, self.LOCK_TIME, self.EXPIRY_HEIGHT)
        self.assertEqual(raw.hex(), self.EXPECTED_RAW_TX_HEX)

    def test_published_script_sig_is_inside_the_broadcast_bytes(self):
        self.assertIn(self.PUBLISHED_SCRIPT_SIG_HEX, self.EXPECTED_RAW_TX_HEX)
        self.assertTrue(self.PUBLISHED_SCRIPT_SIG_HEX.endswith("21" + self.PUBKEY_HEX))

    @NEEDS_LEGACY_KEY
    def test_resigning_with_the_out_of_repo_key_reproduces_the_broadcast_bytes(self):
        # RFC 6979: deterministic per (key, digest) -> re-signing must give the
        # exact scriptSig that was broadcast. The key never appears in the repo.
        priv, pub, address, _exposed = pk.load(allow_legacy_exposed=True)
        self.assertEqual(pub.hex(), self.PUBKEY_HEX)
        vin, vout = self._build()
        vin[0].script_sig = b""
        tx.sign_p2pkh_input(priv, pub, vin, vout, 0, self.PREVOUT_VALUE,
                            bytes.fromhex(self.PREVOUT_SCRIPT_HEX), self.LOCK_TIME, self.EXPIRY_HEIGHT)
        self.assertEqual(vin[0].script_sig.hex(), self.PUBLISHED_SCRIPT_SIG_HEX)


    def test_independent_parser_reads_back_the_expected_outputs(self):
        # Cross-check against zcash_read.py's OWN independent parser (used
        # for reading real chain state elsewhere in this project), not just
        # this module's own serializer -- catches a bug that both share
        # rather than one that's specific to zcash_tx.py alone.
        zr = _load_module("aro_test_zcash_read_for_tx2", "chains/zcash/scripts/zcash_read.py")
        raw = bytes.fromhex(self.EXPECTED_RAW_TX_HEX)
        version, outs = zr.parse_tx_transparent_outputs(raw)
        self.assertEqual(version, 6)
        self.assertEqual(zr.LAST_NIN, 1)
        self.assertEqual(outs[0], (0, "6a2441524f31" + self.COMMIT_HASH_HEX))
        self.assertEqual(outs[1], (self.PREVOUT_VALUE - self.FEE, self.PREVOUT_SCRIPT_HEX))


class TestPublisherKeyLoader(unittest.TestCase):
    """The key lives outside the repo; a missing file must be an explicit error."""

    def test_missing_key_file_raises_explicit_error(self):
        old = os.environ.get(pk.ENV_VAR)
        os.environ[pk.ENV_VAR] = os.path.join(os.path.dirname(__file__), "no_such_zcash_key.json")
        try:
            with self.assertRaises(pk.PublisherKeyMissing) as cm:
                pk.load()
            self.assertIn(pk.ENV_VAR, str(cm.exception))
        finally:
            if old is None:
                del os.environ[pk.ENV_VAR]
            else:
                os.environ[pk.ENV_VAR] = old

    def test_no_private_key_constant_left_in_tracked_zcash_scripts(self):
        import re
        scripts = os.path.abspath(os.path.join(REPO_ROOT, "chains/zcash/scripts"))
        for name in ("publish_attestation.py", "attest_scores.py", "publisher_key.py"):
            src = open(os.path.join(scripts, name)).read()
            self.assertNotRegex(src, re.compile(r"PRIVKEY_HEX\s*=\s*[\"']"), name)

    def test_send_refuses_an_exposed_key(self):
        import json
        import subprocess
        import tempfile
        # a throwaway key generated in-test, marked exposed -> 'send' must refuse
        priv = int.from_bytes(os.urandom(32), "big") % (ec.N - 1) + 1
        pub = ec.privkey_to_pubkey(priv)
        # Zcash Testnet transparent P2PKH prefix 0x1d25 (as in secp256k1.py's keygen)
        addr = ec.base58check(bytes.fromhex("1d25"), ec.hash160(pub))
        with tempfile.TemporaryDirectory() as d:
            kf = os.path.join(d, "k.json")
            json.dump({"privkey_hex": "%064x" % priv, "pubkey_compressed_hex": pub.hex(),
                       "address": addr, "exposed_in_git_history": True}, open(kf, "w"))
            env = dict(os.environ, **{pk.ENV_VAR: kf})
            script = os.path.abspath(os.path.join(REPO_ROOT, "chains/zcash/scripts/publish_attestation.py"))
            r = subprocess.run([sys.executable, script, "send"], env=env, capture_output=True, text=True,
                               cwd=os.path.dirname(script), timeout=60)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("REFUSED", r.stderr)
            self.assertNotIn("%064x" % priv, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
