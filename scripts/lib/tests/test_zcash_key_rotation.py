"""
Unit tests for the 2026-09-19/20 rotation of the Zcash Testnet publisher key
(`chains/zcash/scripts/publisher_key.py`, `publish_batch.py`, and the published
`chains/zcash/data/testnet_attestation_v2_reanchor_2026-09-20.json`).

The first publisher key was committed in clear at 40ca1a4 (see
`chains/zcash/data/publisher_key_exposure_2026-09-19.md`). It was rotated in two
real Testnet transactions, both pinned here as raw bytes that lightwalletd
(testnet.zec.rocks) and testnet.cipherscan.app returned, not as output of the code
that built them:

1. the SWEEP: the whole balance of the exposed key's address moved to the new
   publisher address, signed by the exposed key, no faucet involved;
2. the RE-ANCHOR: the same ARO2 commitment as the first anchor (18791a4c...),
   republished from the new address and signed by the new key.

No network. No private key in this file.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import traceback
import unittest
from unittest import mock

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


ec = _load("aro_test_rot_secp256k1", "chains/zcash/scripts/secp256k1.py")
tx = _load("aro_test_rot_zcash_tx", "chains/zcash/scripts/zcash_tx.py")
zr = _load("aro_test_rot_zcash_read", "chains/zcash/scripts/zcash_read.py")
at = _load("aro_test_rot_attest_scores", "chains/zcash/scripts/attest_scores.py")
pk = _load("aro_test_rot_publisher_key", "chains/zcash/scripts/publisher_key.py")
pb = _load("aro_test_rot_publish_batch", "chains/zcash/scripts/publish_batch.py")
# The scripts under test do `import publisher_key`, i.e. this shared module object, not `pk` above (a
# separately loaded copy): patch THIS one when a test needs to change what counts as the legacy key.
import publisher_key as pk_shared  # noqa: E402

# ---- the two keys (public values only) ----
OLD_PUBKEY = "0388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41f"
OLD_ADDRESS = "tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo"
OLD_SCRIPT = "76a9142e1ee4d4133c8d426b3fa1f5ed8ee1755a2e491388ac"
NEW_PUBKEY = "02e6a829db766cdf6488cfae3cd9588b1871317b625becdd5381c356923004a8cd"
NEW_ADDRESS = "tmCj66nwJY8xgNj3jwEyUMhLGmZzbHYiHY8"
NEW_SCRIPT = "76a914210c1452fa23b003f258d03dbfad4eb5e063eb7988ac"

# ---- the first ARO2 anchor, made by the exposed key ----
FIRST_ARO2_TXID = "18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37"
COMMITMENT = "74f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662"

# ---- the sweep (Testnet block 4,368,630) ----
SWEEP_TXID = "d2b5a31914bc66168f3f0ea8db2fd61ffffeb81fbcec4a2ea2f62de3d19d8074"
SWEEP_EXPIRY = 4368729
SWEEP_FEE = 10_000
SWEEP_IN_VALUE = 9_965_000
SWEEP_OUT_VALUE = 9_955_000
SWEEP_RAW_HEX = (
    "0600008098b684d85b16a5370000000059a942000137cc32fe2d7773d9b003db03e2a93ee4c67655cedcc1ef0a5d0ba0da4c1a79"
    "18010000006b483045022100d5d44eacf0a8b8a7b98a8b02174c3e7d42ed7e776f11078956243262da39b38f02201711cda6de8c"
    "603569d95e6d2661e59059aa812338a40da43316acb99693156201210388e6af60fe4d0fe63248e3953165f6f13dd57f733ed728"
    "3d68f12f2acfb3b41fffffffff01b8e69700000000001976a914210c1452fa23b003f258d03dbfad4eb5e063eb7988ac00000000"
)

# ---- the re-anchor (Testnet block 4,368,633, 2026-09-19T23:15:28Z) ----
REANCHOR_TXID = "eeaa894c3c46814f7228a7ecf2be84c0006c1154b5101688dd413d9a419689c0"
REANCHOR_BLOCK = 4368633
REANCHOR_EXPIRY = 4368732
REANCHOR_FEE = 15_000
REANCHOR_CHANGE = 9_940_000
REANCHOR_RAW_HEX = (
    "0600008098b684d85b16a537000000005ca942000174809dd1e32df6a22e4aecbc1fb8feff1fd62fdba80e3f8f1666bc1419a3b5"
    "d2000000006b483045022100b78a1461db30d256ececae36738faa4af79f9b89f79a5cb531bc411aded93cd702204753b0e80e4e"
    "eae7a4c8fbe9338597a0622ee00f09734e5a5fe643141d69680f012102e6a829db766cdf6488cfae3cd9588b1871317b625becdd"
    "5381c356923004a8cdffffffff020000000000000000266a2441524f3274f6ba041e253bb75e523e1b0d00422e44221c7a024075"
    "7cd1a40ad15d51366220ac9700000000001976a914210c1452fa23b003f258d03dbfad4eb5e063eb7988ac00000000"
)
REANCHOR_SIGNATURE_DER = (
    "304402205c1dbbc6e5467567e28f7e024ae9b1d6540a3bf0a9b478cc5c17e1ae28dffbc002201ad92e1f00a99dff5109027c04c9"
    "99ece0f18dafe6ba4ac39ca83eb1606c9dde"
)


def _record():
    with open(os.path.join(DATA, "testnet_attestation_v2_reanchor_2026-09-20.json")) as f:
        return json.load(f)


def _first_aro2():
    with open(os.path.join(DATA, "testnet_attestation_v2_2026-09-19.json")) as f:
        return json.load(f)


def _vin_vout(raw, outs, script_sig):
    # header(4)+vgid(4)+branch(4)+locktime(4)+expiry(4)=20, then nIn(1), then prevout hash(32) + index(4)
    prevout_hash = raw[21:53]
    prevout_index = int.from_bytes(raw[53:57], "little")
    vin = [tx.TxIn(prevout_hash, prevout_index)]
    vin[0].script_sig = script_sig
    vout = [tx.TxOut(v, bytes.fromhex(s)) for v, s in outs]
    return vin, vout, prevout_hash, prevout_index


def _verify_input_signature(raw, outs, script_sig, expiry, prevout_value, prevout_script_hex, pubkey_hex):
    vin, vout, _, _ = _vin_vout(raw, outs, script_sig)
    sighash = tx.signature_digest_v6(vin, vout, 0, prevout_value, bytes.fromhex(prevout_script_hex), 0, expiry)
    sig_with_type = script_sig[1:1 + script_sig[0]]
    return (sig_with_type[-1] == tx.SIGHASH_ALL
            and script_sig.endswith(bytes([33]) + bytes.fromhex(pubkey_hex))
            and ec.ecdsa_verify(bytes.fromhex(pubkey_hex), sighash, sig_with_type[:-1]))


class TestKeyConstants(unittest.TestCase):
    def test_current_publisher_constants_are_the_rotated_key(self):
        self.assertEqual((pk.PUBKEY_HEX, pk.ADDRESS), (NEW_PUBKEY, NEW_ADDRESS))
        self.assertEqual((pk.LEGACY_EXPOSED_PUBKEY_HEX, pk.LEGACY_EXPOSED_ADDRESS), (OLD_PUBKEY, OLD_ADDRESS))
        self.assertNotEqual(pk.PUBKEY_HEX, pk.LEGACY_EXPOSED_PUBKEY_HEX)
        self.assertNotEqual(pk.ADDRESS, pk.LEGACY_EXPOSED_ADDRESS)

    def test_each_address_is_the_p2pkh_of_its_own_public_key(self):
        for pub, addr, script in ((NEW_PUBKEY, NEW_ADDRESS, NEW_SCRIPT), (OLD_PUBKEY, OLD_ADDRESS, OLD_SCRIPT)):
            self.assertEqual(len(bytes.fromhex(pub)), 33)
            self.assertEqual(zr.transparent_output_script(addr), script)
            self.assertEqual("76a914" + ec.hash160(bytes.fromhex(pub)).hex() + "88ac", script)
            self.assertEqual(ec.base58check(bytes.fromhex("1d25"), ec.hash160(bytes.fromhex(pub))), addr)

    def test_default_utxo_is_the_unspent_change_of_the_latest_anchor_owned_by_the_current_publisher(self):
        # the sweep output (SWEEP_TXID:0) was spent by the re-anchor, and the re-anchor's change (REANCHOR_TXID:1) by the
        # six-live-target anchor of 2026-09-20 (block 4,371,248), so the live UTXO is that anchor's change
        with open(os.path.join(DATA, "testnet_attestation_v2_six_live_2026-09-20.json")) as f:
            six = json.load(f)["anchor"]
        self.assertEqual(at.DEFAULT_UTXO, (six["txid"], 1, six["changeZat"]))
        self.assertEqual(six["changeZat"], REANCHOR_CHANGE - six["feeZat"])
        raw6 = bytes.fromhex(six["rawTxHex"])
        self.assertEqual(raw6[21:53][::-1].hex(), REANCHOR_TXID)          # the six-live anchor spent the re-anchor's change
        # the amount and owner of that change are read from the transaction itself, not from the record's own fields, so a record
        # and a constant that were both wrong in the same way would still be caught
        _, outs6 = zr.parse_tx_transparent_outputs(raw6)
        self.assertEqual((outs6[1][0], outs6[1][1]), (at.DEFAULT_UTXO[2], NEW_SCRIPT))
        raw = bytes.fromhex(REANCHOR_RAW_HEX)
        self.assertEqual(raw[21:53][::-1].hex(), SWEEP_TXID)              # the re-anchor spent the sweep output
        self.assertNotIn(at.DEFAULT_UTXO[0], (SWEEP_TXID, REANCHOR_TXID))

    def test_aro1_module_stays_on_the_legacy_key(self):
        pa = _load("aro_test_rot_publish_attestation", "chains/zcash/scripts/publish_attestation.py")
        self.assertEqual((pa.PUBKEY_HEX, pa.ADDRESS), (OLD_PUBKEY, OLD_ADDRESS))


class TestBuildTxWithThrowawayKey(unittest.TestCase):
    """build_tx / sign_p2pkh_input exercised with a throwaway key file, so this coverage does not depend
    on any real key file being present."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.priv = int.from_bytes(os.urandom(32), "big") % (ec.N - 1) + 1
        self.pub = ec.privkey_to_pubkey(self.priv)
        self.addr = ec.base58check(bytes.fromhex("1d25"), ec.hash160(self.pub))
        kf = os.path.join(self.tmp.name, "k.json")
        with open(kf, "w") as f:
            json.dump({"privkey_hex": "%064x" % self.priv, "pubkey_compressed_hex": self.pub.hex(),
                       "address": self.addr, "exposed_in_git_history": False}, f)
        self.old_env = os.environ.get(pk.ENV_VAR)
        os.environ[pk.ENV_VAR] = kf

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop(pk.ENV_VAR, None)
        else:
            os.environ[pk.ENV_VAR] = self.old_env
        self.tmp.cleanup()

    def test_plan_pays_op_return_and_change_and_is_signed_by_the_loaded_key_only(self):
        data = bytes.fromhex("41524f32" + COMMITMENT)
        utxo = at.DEFAULT_UTXO
        plan = at.build_tx(data, utxo, expiry_height=REANCHOR_EXPIRY)
        raw = bytes.fromhex(plan["rawTxHex"])
        _ver, outs = zr.parse_tx_transparent_outputs(raw)
        script_sig = zr.LAST_SCRIPTSIGS[0]
        own_script = zr.transparent_output_script(self.addr)
        self.assertEqual(outs, [(0, "6a24" + data.hex()), (utxo[2] - plan["feeZat"], own_script)])
        self.assertEqual(plan["feeZat"], REANCHOR_FEE)
        args = (raw, outs, script_sig, REANCHOR_EXPIRY, utxo[2], own_script)
        self.assertTrue(_verify_input_signature(*args, self.pub.hex()))
        self.assertFalse(_verify_input_signature(*args, NEW_PUBKEY))
        self.assertFalse(plan["broadcast"])

    def test_plan_is_deterministic_and_predicted_txid_matches_its_own_bytes(self):
        data = bytes.fromhex("41524f32" + COMMITMENT)
        p1 = at.build_tx(data, at.DEFAULT_UTXO, expiry_height=REANCHOR_EXPIRY)
        p2 = at.build_tx(data, at.DEFAULT_UTXO, expiry_height=REANCHOR_EXPIRY)
        self.assertEqual(p1["rawTxHex"], p2["rawTxHex"])
        raw = bytes.fromhex(p1["rawTxHex"])
        _ver, outs = zr.parse_tx_transparent_outputs(raw)
        vin, vout, _, _ = _vin_vout(raw, outs, zr.LAST_SCRIPTSIGS[0])
        self.assertEqual(tx.txid_hex_display(vin, vout, 0, REANCHOR_EXPIRY), p1["predictedTxid"])

    def test_publish_batch_refuses_this_key_because_it_is_not_the_known_publisher(self):
        with self.assertRaises(SystemExit) as cm:
            pb.guard_key(refuse_exposed=True)
        self.assertIn("not the known ARO Testnet publisher key", str(cm.exception))


class TestMalformedKeyFileDoesNotLeak(unittest.TestCase):
    """A malformed privkey_hex is exactly what a half-pasted real key looks like: it must not be echoed by
    the exception, including the chained (`__context__`) one that a traceback prints."""

    def test_malformed_privkey_is_not_in_the_full_formatted_traceback(self):
        marker = "ZZ-half-pasted-SECRET-MARKER-0123456789"
        with tempfile.TemporaryDirectory() as d:
            kf = os.path.join(d, "k.json")
            with open(kf, "w") as f:
                json.dump({"privkey_hex": marker, "pubkey_compressed_hex": NEW_PUBKEY, "address": NEW_ADDRESS}, f)
            old = os.environ.get(pk_shared.ENV_VAR)
            os.environ[pk_shared.ENV_VAR] = kf
            try:
                with self.assertRaises(pk_shared.PublisherKeyInvalid) as cm:
                    pk_shared.load()
            finally:
                if old is None:
                    os.environ.pop(pk_shared.ENV_VAR, None)
                else:
                    os.environ[pk_shared.ENV_VAR] = old
        full = "".join(traceback.format_exception(type(cm.exception), cm.exception, cm.exception.__traceback__))
        self.assertNotIn(marker, full)
        self.assertNotIn(marker, str(cm.exception))


class TestLegacyKeyRefusedByIdentity(unittest.TestCase):
    """The exposed key is refused because of WHICH KEY IT IS, not because of a flag in an editable file.
    The real legacy private key is not used anywhere: a throwaway key is made to stand in for the legacy
    identity by patching the constant the code compares against."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        priv = int.from_bytes(os.urandom(32), "big") % (ec.N - 1) + 1
        self.pub = ec.privkey_to_pubkey(priv)
        self.addr = ec.base58check(bytes.fromhex("1d25"), ec.hash160(self.pub))
        self.priv = priv
        self.old_env = os.environ.get(pk_shared.ENV_VAR)
        self.patch = mock.patch.object(pk_shared, "LEGACY_EXPOSED_PUBKEY_HEX", self.pub.hex())
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        if self.old_env is None:
            os.environ.pop(pk_shared.ENV_VAR, None)
        else:
            os.environ[pk_shared.ENV_VAR] = self.old_env
        self.tmp.cleanup()

    def _key_file(self, **flag):
        d = {"privkey_hex": "%064x" % self.priv, "pubkey_compressed_hex": self.pub.hex(), "address": self.addr}
        d.update(flag)
        path = os.path.join(self.tmp.name, "k.json")
        with open(path, "w") as f:
            json.dump(d, f)
        os.environ[pk_shared.ENV_VAR] = path

    def _each_flag_state(self):
        for flag in ({"exposed_in_git_history": False}, {}, {"exposed_in_git_history": True}):
            self._key_file(**flag)
            yield flag

    def test_load_refuses_it_with_the_flag_false_absent_or_true(self):
        for flag in self._each_flag_state():
            with self.assertRaises(pk_shared.PublisherKeyExposed, msg=str(flag)):
                pk_shared.load()

    def test_load_returns_it_only_with_the_explicit_opt_in(self):
        self._key_file(exposed_in_git_history=False)
        priv, pub, addr, _ = pk_shared.load(allow_legacy_exposed=True)
        self.assertEqual((priv, pub.hex(), addr), (self.priv, self.pub.hex(), self.addr))

    def test_build_tx_refuses_it_and_only_signs_with_the_opt_in(self):
        self._key_file(exposed_in_git_history=False)
        data = bytes.fromhex("41524f32" + COMMITMENT)
        with self.assertRaises(pk_shared.PublisherKeyExposed):
            at.build_tx(data, at.DEFAULT_UTXO, expiry_height=REANCHOR_EXPIRY)
        with contextlib.redirect_stderr(io.StringIO()):
            plan = at.build_tx(data, at.DEFAULT_UTXO, expiry_height=REANCHOR_EXPIRY, allow_legacy_exposed=True)
        self.assertFalse(plan["broadcast"])

    def test_publish_batch_refuses_it_in_send_and_plan_with_any_flag(self):
        for flag in self._each_flag_state():
            for refuse_exposed in (True, False):
                with self.assertRaises(SystemExit) as cm:
                    pb.guard_key(refuse_exposed=refuse_exposed)
                self.assertIn("REFUSED", str(cm.exception), msg=str(flag))

    def test_publish_attestation_refuses_send_and_plan_before_any_network_call(self):
        pa = _load("aro_test_rot_publish_attestation_ident", "chains/zcash/scripts/publish_attestation.py")
        for flag in self._each_flag_state():
            for mode in ("send", "plan"):
                with mock.patch.object(sys, "argv", ["publish_attestation.py", mode]), \
                        mock.patch.object(pa.tx, "send_transaction", side_effect=AssertionError("must not broadcast")), \
                        mock.patch.object(pa.zr, "grpc", side_effect=AssertionError("must not touch the network")):
                    with self.assertRaises(SystemExit) as cm:
                        pa.main()
                self.assertIn("REFUSED", str(cm.exception), msg=f"{mode} {flag}")


class TestSweepTransaction(unittest.TestCase):
    """The raw bytes below are what the network accepted and mined."""

    def setUp(self):
        self.raw = bytes.fromhex(SWEEP_RAW_HEX)
        self.version, self.outs = zr.parse_tx_transparent_outputs(self.raw)
        self.script_sig = zr.LAST_SCRIPTSIGS[0]

    def test_one_input_one_output_paying_only_the_new_address(self):
        self.assertEqual((self.version, zr.LAST_NIN, len(self.raw)), (6, 1, 208))
        self.assertEqual(self.outs, [(SWEEP_OUT_VALUE, NEW_SCRIPT)])

    def test_it_spends_the_change_of_the_first_aro2_tx_and_leaves_the_old_address_empty(self):
        _, _, prevout_hash, prevout_index = _vin_vout(self.raw, self.outs, self.script_sig)
        self.assertEqual((prevout_hash[::-1].hex(), prevout_index), (FIRST_ARO2_TXID, 1))
        self.assertEqual(SWEEP_IN_VALUE - SWEEP_OUT_VALUE, SWEEP_FEE)

    def test_txid_is_the_zip244_229_digest_of_these_bytes(self):
        vin, vout, _, _ = _vin_vout(self.raw, self.outs, self.script_sig)
        self.assertEqual(tx.txid_hex_display(vin, vout, 0, SWEEP_EXPIRY), SWEEP_TXID)

    def test_input_is_signed_by_the_exposed_key_not_the_new_one(self):
        args = (self.raw, self.outs, self.script_sig, SWEEP_EXPIRY, SWEEP_IN_VALUE, OLD_SCRIPT)
        self.assertTrue(_verify_input_signature(*args, OLD_PUBKEY))
        self.assertFalse(_verify_input_signature(*args, NEW_PUBKEY))

    def test_fee_is_the_zip317_conventional_fee_for_these_exact_sizes(self):
        vin, vout, _, _ = _vin_vout(self.raw, self.outs, self.script_sig)
        in_sizes = [len(i.outpoint()) + len(tx.field(i.script_sig)) + 4 for i in vin]
        out_sizes = [len(o.ser()) for o in vout]
        self.assertEqual(at.zip317_fee(in_sizes, out_sizes), SWEEP_FEE)


class TestReanchorTransaction(unittest.TestCase):
    def setUp(self):
        self.raw = bytes.fromhex(REANCHOR_RAW_HEX)
        self.version, self.outs = zr.parse_tx_transparent_outputs(self.raw)
        self.script_sig = zr.LAST_SCRIPTSIGS[0]

    def test_outputs_are_the_aro2_payload_and_change_to_the_new_address(self):
        self.assertEqual((self.version, zr.LAST_NIN, len(self.raw)), (6, 1, 255))
        self.assertEqual(self.outs[0], (0, "6a24" + "41524f32" + COMMITMENT))
        self.assertEqual(self.outs[1], (REANCHOR_CHANGE, NEW_SCRIPT))

    def test_it_spends_the_sweep_output(self):
        _, _, prevout_hash, prevout_index = _vin_vout(self.raw, self.outs, self.script_sig)
        self.assertEqual((prevout_hash[::-1].hex(), prevout_index), (SWEEP_TXID, 0))
        self.assertEqual(SWEEP_OUT_VALUE - REANCHOR_FEE, REANCHOR_CHANGE)

    def test_txid_is_the_zip244_229_digest_of_these_bytes(self):
        vin, vout, _, _ = _vin_vout(self.raw, self.outs, self.script_sig)
        self.assertEqual(tx.txid_hex_display(vin, vout, 0, REANCHOR_EXPIRY), REANCHOR_TXID)

    def test_input_is_signed_by_the_new_key_not_the_exposed_one(self):
        args = (self.raw, self.outs, self.script_sig, REANCHOR_EXPIRY, SWEEP_OUT_VALUE, NEW_SCRIPT)
        self.assertTrue(_verify_input_signature(*args, NEW_PUBKEY))
        self.assertFalse(_verify_input_signature(*args, OLD_PUBKEY))

    def test_fee_is_the_zip317_conventional_fee_for_these_exact_sizes(self):
        vin, vout, _, _ = _vin_vout(self.raw, self.outs, self.script_sig)
        in_sizes = [len(i.outpoint()) + len(tx.field(i.script_sig)) + 4 for i in vin]
        out_sizes = [len(o.ser()) for o in vout]
        self.assertEqual(at.zip317_fee(in_sizes, out_sizes), REANCHOR_FEE)


class TestReanchorRecord(unittest.TestCase):
    def test_anchor_block_matches_the_pinned_transaction(self):
        d = _record()
        a = d["anchor"]
        self.assertEqual((a["txid"], a["blockHeight"], a["feeZat"], a["expiryHeight"], a["changeZat"]),
                         (REANCHOR_TXID, REANCHOR_BLOCK, REANCHOR_FEE, REANCHOR_EXPIRY, REANCHOR_CHANGE))
        self.assertEqual(a["rawTxHex"], REANCHOR_RAW_HEX)
        self.assertEqual(a["spentUtxo"], SWEEP_TXID + ":0")
        self.assertEqual((d["publisherAddress_ZcashTestnet"], d["publisherPubkeyCompressed"]),
                         (NEW_ADDRESS, NEW_PUBKEY))

    def test_it_republishes_the_exact_commitment_of_the_first_aro2_anchor(self):
        d, first = _record(), _first_aro2()
        self.assertEqual(d["reanchorsTxid"], FIRST_ARO2_TXID)
        self.assertEqual(first["anchor"]["txid"], FIRST_ARO2_TXID)
        for k in ("commitmentBlake2b256", "opReturnDataHex", "header", "records", "methodologyPinnedAt"):
            self.assertEqual(d[k], first[k], k)
        self.assertEqual(d["commitmentBlake2b256"], COMMITMENT)
        self.assertEqual(at.rederive(d)["commitmentBlake2b256"], COMMITMENT)

    def test_signature_over_the_commitment_is_by_the_new_key_only(self):
        d = _record()
        self.assertEqual(d["attestationSignatureDer"], REANCHOR_SIGNATURE_DER)
        sig, commitment = bytes.fromhex(REANCHOR_SIGNATURE_DER), bytes.fromhex(COMMITMENT)
        self.assertTrue(ec.ecdsa_verify(bytes.fromhex(NEW_PUBKEY), commitment, sig))
        self.assertFalse(ec.ecdsa_verify(bytes.fromhex(OLD_PUBKEY), commitment, sig))
        tampered = bytes([commitment[0] ^ 1]) + commitment[1:]
        self.assertFalse(ec.ecdsa_verify(bytes.fromhex(NEW_PUBKEY), tampered, sig))

    def test_key_note_matches_the_key_and_does_not_claim_exposure_for_the_new_one(self):
        d = _record()
        self.assertEqual(d["publisherKeyNote"], pb.key_note(NEW_ADDRESS))
        self.assertNotIn("committed in clear in 40ca1a4 and stays readable", pb.key_note(NEW_ADDRESS))
        self.assertIn("never written to a tracked file", pb.key_note(NEW_ADDRESS))
        self.assertIn("stays readable in the private repo's history", pb.key_note(OLD_ADDRESS))

    def test_the_first_aro2_record_is_untouched_and_still_names_the_exposed_key(self):
        first = _first_aro2()
        self.assertEqual((first["publisherAddress_ZcashTestnet"], first["publisherPubkeyCompressed"]),
                         (OLD_ADDRESS, OLD_PUBKEY))


if __name__ == "__main__":
    unittest.main()
