"""
Unit tests for Zcash's hand-rolled decode primitives -- previously ZERO
test coverage anywhere in this project (found during a 2026-09-18 audit
of test-coverage gaps across ecosystems). `chains/zcash/scorers.py`
imports these functions directly and feeds their output straight into
the composite score (`find_multisig_spends`'s `m`/`n`/`pubkeys`,
`compute_concentration`'s `addressesToExceed50Pct`/`25Pct`) -- exactly
the kind of novel, error-prone, financially-load-bearing decode logic
this project already treats as test-worthy for Solana's `sol_read.py`
and Hyperliquid's `methodology_test.py`.

Covers three files, all pure functions except where noted (network calls
monkeypatched, not hit):
  - chains/zcash/scripts/zcash_read.py: a hand-rolled protobuf-ish
    varint/length-delimited decoder (grpc's wire format, not real
    protobuf but the same tag/varint scheme) and a base58check decoder.
  - chains/zcash/scripts/p2sh_spends.py: Bitcoin/Zcash script
    push-opcode parsing and CHECKMULTISIG redeem-script extraction.
  - chains/zcash/scripts/miner_concentration.py: a base58check ENCODER
    (round-tripped against zcash_read's decoder) and the
    `addresses_to_exceed` concentration-threshold logic, which has a
    real, previously-fixed bug (see its own 2026-09-17 comment: used to
    overcount past an excluded "shielded-or-none" bucket) -- locked in
    with a dedicated regression test here for the first time.

Real, known-good fixtures are used where practical (e.g. the ZIP 271
lockbox address `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo`, already cited
elsewhere in this project's own Zcash docs/code as a real mainnet
address) rather than arbitrary made-up strings, matching this project's
own `test_solend_governance.py`-style precedent of grounding fixtures in
real values where one is cheaply available.
"""
import hashlib
import importlib.util
import os
import struct
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


zr = _load_module("aro_test_zcash_read", "chains/zcash/scripts/zcash_read.py")
p2sh = _load_module("aro_test_p2sh_spends", "chains/zcash/scripts/p2sh_spends.py")
miner = _load_module("aro_test_miner_concentration", "chains/zcash/scripts/miner_concentration.py")

REAL_LOCKBOX_ADDR = "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo"  # ZIP 271, real mainnet address
REAL_ZCG_ADDR = "t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow"  # ZCG funding stream, real mainnet address


# --------------------------------------------------------------- zcash_read.py
class TestVarint(unittest.TestCase):
    def test_single_byte_roundtrip(self):
        for n in (0, 1, 42, 127):
            self.assertEqual(zr.read_varint(zr.varint(n), 0), (n, len(zr.varint(n))))

    def test_multi_byte_known_encoding(self):
        # 300 = 0b100101100 -> protobuf varint bytes [0xAC, 0x02] (well-known example)
        self.assertEqual(zr.varint(300), bytes([0xAC, 0x02]))
        self.assertEqual(zr.read_varint(bytes([0xAC, 0x02]), 0), (300, 2))

    def test_large_value_roundtrip(self):
        n = 123456789
        self.assertEqual(zr.read_varint(zr.varint(n), 0), (n, len(zr.varint(n))))

    def test_read_varint_respects_start_offset(self):
        buf = b"\xff\xff" + zr.varint(5)  # junk prefix, then a real varint
        self.assertEqual(zr.read_varint(buf, 2), (5, 3))


class TestFieldEncoders(unittest.TestCase):
    def test_field_varint_tag_and_value(self):
        # field 1, varint wire type (0): tag = (1<<3)|0 = 0x08
        encoded = zr.field_varint(1, 5)
        self.assertEqual(encoded[0], 0x08)
        self.assertEqual(zr.decode(encoded), [(1, 5)])

    def test_field_bytes_tag_length_and_payload(self):
        # field 2, length-delimited wire type (2): tag = (2<<3)|2 = 0x12
        encoded = zr.field_bytes(2, b"hello")
        self.assertEqual(encoded[0], 0x12)
        decoded = zr.decode(encoded)
        self.assertEqual(decoded, [(2, b"hello")])

    def test_field_number_above_15_uses_multi_byte_tag(self):
        # Field numbers >= 16 need a 2-byte varint tag -- regression guard
        # against an off-by-shift error in the (num << 3) | wiretype math.
        encoded = zr.field_varint(16, 7)
        self.assertEqual(zr.decode(encoded), [(16, 7)])


class TestDecode(unittest.TestCase):
    def test_mixed_wire_types_in_one_message(self):
        msg = zr.field_varint(1, 42) + zr.field_bytes(2, b"abc") + zr.field_varint(3, 999)
        self.assertEqual(zr.decode(msg), [(1, 42), (2, b"abc"), (3, 999)])

    def test_wire_type_1_is_8_bytes_fixed(self):
        # wire type 1 (64-bit fixed): tag = (5<<3)|1 = 0x29
        raw = bytes([0x29]) + struct.pack("<Q", 0xDEADBEEFCAFEBABE)
        self.assertEqual(zr.decode(raw), [(5, struct.pack("<Q", 0xDEADBEEFCAFEBABE))])

    def test_wire_type_5_is_4_bytes_fixed(self):
        # wire type 5 (32-bit fixed): tag = (5<<3)|5 = 0x2D
        raw = bytes([0x2D]) + struct.pack("<I", 0xCAFEBABE)
        self.assertEqual(zr.decode(raw), [(5, struct.pack("<I", 0xCAFEBABE))])

    def test_unsupported_wire_type_raises(self):
        # wire type 3 (deprecated "start group") -- tag = (1<<3)|3 = 0x0B
        with self.assertRaises(ValueError):
            zr.decode(bytes([0x0B]))

    def test_empty_message_decodes_to_empty_list(self):
        self.assertEqual(zr.decode(b""), [])


class TestB58Dec(unittest.TestCase):
    def test_real_lockbox_address_decodes_with_valid_checksum(self):
        # No exception means the internal sha256d checksum assertion passed.
        raw = zr.b58dec(REAL_LOCKBOX_ADDR)
        self.assertEqual(len(raw), 22)  # 2-byte version prefix + 20-byte hash160

    def test_real_zcg_address_decodes_with_valid_checksum(self):
        raw = zr.b58dec(REAL_ZCG_ADDR)
        self.assertEqual(len(raw), 22)

    def test_t3_prefix_is_the_p2sh_version_bytes(self):
        # Zcash t3... (P2SH) addresses use version prefix 0x1CBD, confirmed
        # against miner_concentration.py's own `addr()` encoder (which emits
        # exactly this prefix for a 0xa914...87 P2SH scriptPubKey).
        raw = zr.b58dec(REAL_LOCKBOX_ADDR)
        self.assertEqual(raw[:2], bytes.fromhex("1cbd"))

    def test_corrupted_checksum_raises(self):
        # Flip the last character (part of the checksum) -- must fail loudly,
        # never silently return a wrong hash160.
        corrupted = REAL_LOCKBOX_ADDR[:-1] + ("A" if REAL_LOCKBOX_ADDR[-1] != "A" else "B")
        with self.assertRaises(AssertionError):
            zr.b58dec(corrupted)

    def test_roundtrips_through_miner_concentration_encoder(self):
        # b58dec (zcash_read.py) and b58enc (miner_concentration.py) are
        # maintained in two different files -- confirm they're real inverses.
        raw = zr.b58dec(REAL_LOCKBOX_ADDR)
        self.assertEqual(miner.b58enc(raw), REAL_LOCKBOX_ADDR)  # b58dec already stripped the checksum


class TestParseTxTransparentOutputs(unittest.TestCase):
    def _build_v4_tx(self, outputs, inputs=None):
        """outputs: list of (value_zat, script_bytes). inputs: list of
        (script_sig_bytes,), each padded with a synthetic 36-byte outpoint
        and a fixed sequence number, matching the real wire format
        parse_tx_transparent_outputs expects (outpoint(36) + scriptSig +
        sequence(4))."""
        inputs = inputs or []
        header = struct.pack("<I", 0x80000004)  # overwintered bit set, version=4
        version_group_id = struct.pack("<I", 0x892F2085)  # real Sapling group id, value irrelevant to the parser
        buf = header + version_group_id
        buf += bytes([len(inputs)])  # CompactSize, small N
        for (script_sig,) in inputs:
            buf += b"\x00" * 36  # outpoint (txid(32) + index(4))
            buf += bytes([len(script_sig)]) + script_sig
            buf += b"\x00" * 4  # sequence
        buf += bytes([len(outputs)])
        for value, script in outputs:
            buf += struct.pack("<q", value)
            buf += bytes([len(script)]) + script
        return buf

    def test_simple_v4_tx_with_one_output(self):
        script = bytes.fromhex("76a914" + "11" * 20 + "88ac")  # P2PKH
        raw = self._build_v4_tx([(50000, script)])
        version, outs = p2sh.z.parse_tx_transparent_outputs(raw)
        self.assertEqual(version, 4)
        self.assertEqual(outs, [(50000, script.hex())])

    def test_multiple_outputs_preserve_order_and_values(self):
        s1 = bytes.fromhex("a914" + "22" * 20 + "87")
        s2 = bytes.fromhex("76a914" + "33" * 20 + "88ac")
        raw = self._build_v4_tx([(1000, s1), (2000, s2)])
        version, outs = p2sh.z.parse_tx_transparent_outputs(raw)
        self.assertEqual(outs, [(1000, s1.hex()), (2000, s2.hex())])

    def test_inputs_populate_last_scriptsigs_and_last_nin_globals(self):
        sig1 = bytes.fromhex("00" * 5)
        sig2 = bytes.fromhex("11" * 7)
        raw = self._build_v4_tx([(1, bytes.fromhex("51"))], inputs=[(sig1,), (sig2,)])
        p2sh.z.parse_tx_transparent_outputs(raw)
        self.assertEqual(p2sh.z.LAST_NIN, 2)
        self.assertEqual(p2sh.z.LAST_SCRIPTSIGS, [sig1, sig2])

    def test_v5_header_skips_extra_branch_id_locktime_expiry_fields(self):
        # v5 (and v6/ZIP-229) txs have branch_id(4)+lock_time(4)+expiry(4)
        # extra fields between version_group_id and the input count, which
        # a v4-only parser would misread as the CompactSize input count.
        header = struct.pack("<I", 0x80000005)  # version=5
        version_group_id = struct.pack("<I", 0x26A7270A)  # real NU5 group id
        extra = b"\x00" * 12  # branch_id + lock_time + expiry
        script = bytes.fromhex("6a")  # OP_RETURN, arbitrary
        body = bytes([0]) + bytes([1]) + struct.pack("<q", 777) + bytes([len(script)]) + script
        raw = header + version_group_id + extra + body
        version, outs = p2sh.z.parse_tx_transparent_outputs(raw)
        self.assertEqual(version, 5)
        self.assertEqual(outs, [(777, script.hex())])


# --------------------------------------------------------------- p2sh_spends.py
class TestPushes(unittest.TestCase):
    def test_direct_push_1_to_75_bytes(self):
        data = b"\xab" * 20
        script = bytes([len(data)]) + data
        self.assertEqual(p2sh.pushes(script), [data])

    def test_op_pushdata1(self):
        data = b"\xcd" * 100
        script = bytes([0x4c, len(data)]) + data
        self.assertEqual(p2sh.pushes(script), [data])

    def test_op_pushdata2(self):
        data = b"\xef" * 300
        script = bytes([0x4d]) + len(data).to_bytes(2, "little") + data
        self.assertEqual(p2sh.pushes(script), [data])

    def test_op_0_pushes_empty_bytes(self):
        self.assertEqual(p2sh.pushes(bytes([0x00])), [b""])

    def test_multiple_pushes_in_sequence(self):
        a, b = b"\x01\x02", b"\x03\x04\x05"
        script = bytes([len(a)]) + a + bytes([len(b)]) + b
        self.assertEqual(p2sh.pushes(script), [a, b])

    def test_empty_script_returns_empty_list(self):
        self.assertEqual(p2sh.pushes(b""), [])


def _hash160(data):
    return hashlib.new("ripemd160", hashlib.sha256(data).digest()).digest()


def _multisig_redeem_script(m, pubkeys, op=0xAE):
    """OP_m <pubkeys...> OP_n OP_CHECKMULTISIG(VERIFY) -- the exact shape
    find_multisig_spends looks for."""
    n = len(pubkeys)
    body = bytes([0x50 + m])
    for pk in pubkeys:
        body += bytes([len(pk)]) + pk
    body += bytes([0x50 + n, op])
    return body


def _grpc_frame_for_tx(raw_tx, height):
    """A single GetTaddressTxids response message: field 1 = raw tx bytes,
    field 2 = height (varint)."""
    return zr.field_bytes(1, raw_tx) + zr.field_varint(2, height)


def _push_script(data):
    """Frame `data` as a single scriptSig push, exactly as a real wallet
    would: a direct length byte for <= 75 bytes, OP_PUSHDATA1 (0x4c) for
    76-255 bytes -- a real 2-of-3 CHECKMULTISIG redeem script (1 + 3*34 +
    2 = 105 bytes) is already over the 75-byte direct-push limit, so
    `bytes([len(data)]) + data` alone would silently mis-encode it (byte
    value 105 = 0x69 isn't a push opcode `pushes()` recognizes at all)."""
    if len(data) <= 75:
        return bytes([len(data)]) + data
    if len(data) <= 255:
        return bytes([0x4c, len(data)]) + data
    return bytes([0x4d]) + len(data).to_bytes(2, "little") + data


class TestFindMultisigSpends(unittest.TestCase):
    def _tx_with_one_input_one_output(self, script_sig):
        header = struct.pack("<I", 0x80000004)
        version_group_id = struct.pack("<I", 0x892F2085)
        buf = header + version_group_id
        buf += bytes([1])  # 1 input
        buf += b"\x00" * 36
        buf += bytes([len(script_sig)]) + script_sig if len(script_sig) < 0xFD else b""
        buf += b"\x00" * 4
        buf += bytes([1])  # 1 output
        buf += struct.pack("<q", 100)
        buf += bytes([1]) + bytes([0x51])  # trivial output script
        return buf

    def test_recognizes_2_of_3_checkmultisig_and_extracts_pubkeys(self):
        pubkeys = [b"\x02" + bytes([i]) * 32 for i in range(3)]
        redeem = _multisig_redeem_script(2, pubkeys)
        addr_hash160 = _hash160(redeem)
        fake_addr = miner.b58enc(bytes.fromhex("1cbd") + addr_hash160)
        script_sig = _push_script(redeem)
        raw_tx = self._tx_with_one_input_one_output(script_sig)
        frame = _grpc_frame_for_tx(raw_tx, height=500)

        orig = p2sh.z.grpc
        p2sh.z.grpc = lambda host, method, msg: [frame]
        try:
            result = p2sh.find_multisig_spends("fake-host", fake_addr, 0, 1000)
        finally:
            p2sh.z.grpc = orig

        self.assertEqual(result["spendsFound"], 1)
        spend = result["spends"][0]
        self.assertEqual(spend["m"], 2)
        self.assertEqual(spend["n"], 3)
        self.assertEqual(spend["op"], "CHECKMULTISIG")
        self.assertEqual(set(spend["pubkeys"]), {pk.hex() for pk in pubkeys})
        self.assertEqual(spend["height"], 500)

    def test_checkmultisigverify_opcode_is_labeled_correctly(self):
        pubkeys = [b"\x03" + bytes([i]) * 32 for i in range(2)]
        redeem = _multisig_redeem_script(2, pubkeys, op=0xAF)
        addr_hash160 = _hash160(redeem)
        fake_addr = miner.b58enc(bytes.fromhex("1cbd") + addr_hash160)
        script_sig = _push_script(redeem)
        raw_tx = self._tx_with_one_input_one_output(script_sig)
        frame = _grpc_frame_for_tx(raw_tx, height=1)

        orig = p2sh.z.grpc
        p2sh.z.grpc = lambda host, method, msg: [frame]
        try:
            result = p2sh.find_multisig_spends("fake-host", fake_addr, 0, 10)
        finally:
            p2sh.z.grpc = orig

        self.assertEqual(result["spends"][0]["op"], "CHECKMULTISIGVERIFY")

    def test_non_multisig_redeem_script_falls_back_to_hex_dump(self):
        # A redeem script that hashes to the target address but doesn't
        # look like OP_m...OP_n OP_CHECKMULTISIG -- must still be reported
        # (not silently dropped), just without m/n/pubkeys.
        redeem = bytes([0x51, 0x93, 0x52])  # OP_1 OP_ADD OP_2 -- not multisig shape
        addr_hash160 = _hash160(redeem)
        fake_addr = miner.b58enc(bytes.fromhex("1cbd") + addr_hash160)
        script_sig = _push_script(redeem)
        raw_tx = self._tx_with_one_input_one_output(script_sig)
        frame = _grpc_frame_for_tx(raw_tx, height=2)

        orig = p2sh.z.grpc
        p2sh.z.grpc = lambda host, method, msg: [frame]
        try:
            result = p2sh.find_multisig_spends("fake-host", fake_addr, 0, 10)
        finally:
            p2sh.z.grpc = orig

        self.assertEqual(result["spendsFound"], 1)
        self.assertNotIn("m", result["spends"][0])
        self.assertEqual(result["spends"][0]["redeemScriptHex"], redeem.hex())

    def test_unrelated_spend_to_a_different_address_is_ignored(self):
        pubkeys = [b"\x02" + bytes([9]) * 32]
        redeem = _multisig_redeem_script(1, pubkeys)
        script_sig = _push_script(redeem)
        raw_tx = self._tx_with_one_input_one_output(script_sig)
        frame = _grpc_frame_for_tx(raw_tx, height=3)

        # Query for a COMPLETELY different address (does not match the
        # redeem script's own hash160) -- must find zero spends, not a
        # false positive.
        unrelated_addr = miner.b58enc(bytes.fromhex("1cbd") + b"\xff" * 20)

        orig = p2sh.z.grpc
        p2sh.z.grpc = lambda host, method, msg: [frame]
        try:
            result = p2sh.find_multisig_spends("fake-host", unrelated_addr, 0, 10)
        finally:
            p2sh.z.grpc = orig

        self.assertEqual(result["spendsFound"], 0)


# --------------------------------------------------------- miner_concentration.py
class TestB58Enc(unittest.TestCase):
    def test_roundtrips_real_lockbox_address(self):
        raw = zr.b58dec(REAL_LOCKBOX_ADDR)  # includes 4-byte checksum
        self.assertEqual(miner.b58enc(raw), REAL_LOCKBOX_ADDR)  # b58dec already stripped the checksum


class TestAddr(unittest.TestCase):
    def test_p2pkh_script_maps_to_t1_prefix(self):
        h160 = b"\xaa" * 20
        script = bytes.fromhex("76a914") + h160 + bytes.fromhex("88ac")
        result = miner.addr(script)
        self.assertTrue(result.startswith("t1"))
        # round-trip: decoding what we just encoded must recover the same hash160
        self.assertEqual(zr.b58dec(result)[2:], h160)

    def test_p2sh_script_maps_to_t3_prefix(self):
        h160 = b"\xbb" * 20
        script = bytes.fromhex("a914") + h160 + bytes.fromhex("87")
        result = miner.addr(script)
        self.assertTrue(result.startswith("t3"))
        self.assertEqual(zr.b58dec(result)[2:], h160)

    def test_unrecognized_script_falls_back_to_hex_label(self):
        script = bytes.fromhex("6a0448656c6c6f")  # OP_RETURN "Hello"
        result = miner.addr(script)
        self.assertEqual(result, "script:" + script.hex())

    def test_real_lockbox_address_hash160_matches_its_own_addr_encoding(self):
        # Cross-check against the REAL known-good address, not just a
        # synthetic one -- confirms the P2SH prefix (0x1cbd) is exactly
        # right, not just self-consistent between addr()/b58dec().
        h160 = zr.b58dec(REAL_LOCKBOX_ADDR)[2:22]
        script = bytes.fromhex("a914") + h160 + bytes.fromhex("87")
        self.assertEqual(miner.addr(script), REAL_LOCKBOX_ADDR)


def _fake_compact_block(coinbase_outputs):
    """A minimal CompactBlock-shaped protobuf message: field 7 = [a single
    tx message], and that tx message's field 8 = [repeated output
    messages, each {1: value, 2: script}] -- matching exactly what
    compute_concentration's own decode walk expects (`txs = [... n==7]`,
    `cb = decode(txs[0])`, `if n == 8: o = dict(decode(v))`)."""
    outs_encoded = b""
    for value, script in coinbase_outputs:
        out_msg = zr.field_varint(1, value) + zr.field_bytes(2, script)
        outs_encoded += zr.field_bytes(8, out_msg)
    cb_tx = outs_encoded
    return zr.field_bytes(7, cb_tx)


class TestComputeConcentration(unittest.TestCase):
    def _fake_grpc_blocks(self, blocks_outputs):
        """blocks_outputs: list of lists of (value, script) tuples, one
        list per block."""
        return [_fake_compact_block(outs) for outs in blocks_outputs]

    def test_attributes_each_block_to_its_largest_non_excluded_output(self):
        h160_a = b"\x01" * 20
        h160_b = b"\x02" * 20
        script_a = bytes.fromhex("76a914") + h160_a + bytes.fromhex("88ac")
        script_b = bytes.fromhex("76a914") + h160_b + bytes.fromhex("88ac")
        # Block 1: A gets the bigger payout -> attributed to A.
        # Block 2: B gets the bigger payout -> attributed to B.
        blocks = [
            [(1000, script_a), (500, script_b)],
            [(200, script_a), (900, script_b)],
        ]
        orig = miner.grpc
        miner.grpc = lambda host, method, msg: self._fake_grpc_blocks(blocks)
        try:
            result = miner.compute_concentration("fake-host", 0, 1, step=200)
        finally:
            miner.grpc = orig

        self.assertEqual(result["blocks"], 2)
        addr_a = miner.addr(script_a)
        addr_b = miner.addr(script_b)
        counts = {s["address"]: s["count"] for s in result["shares"]}
        self.assertEqual(counts.get(addr_a), 1)
        self.assertEqual(counts.get(addr_b), 1)

    def test_excluded_funding_stream_addresses_never_attributed(self):
        # A coinbase output to the REAL ZCG address, larger than a normal
        # miner payout -- must be excluded from concentration entirely,
        # falling back to "shielded-or-none" for that block.
        zcg_h160 = zr.b58dec(REAL_ZCG_ADDR)[2:22]
        zcg_script = bytes.fromhex("a914") + zcg_h160 + bytes.fromhex("87")
        blocks = [[(99999999, zcg_script)]]
        orig = miner.grpc
        miner.grpc = lambda host, method, msg: self._fake_grpc_blocks(blocks)
        try:
            result = miner.compute_concentration("fake-host", 0, 0, step=200)
        finally:
            miner.grpc = orig

        self.assertEqual(result["distinctPayoutAddresses"], 1)  # only "shielded-or-none"
        self.assertEqual(result["shares"][0]["address"], "shielded-or-none")

    def test_addresses_to_exceed_50pct_regression_shielded_bucket_ranked_first(self):
        # REGRESSION TEST for the real 2026-09-17 bug (see miner_
        # concentration.py's own comment on addresses_to_exceed): the
        # "shielded-or-none" bucket, when it ranks AHEAD of the 50%
        # crossing point, must NOT be counted toward the real-address
        # tally. Construct 10 blocks: 6 have no real (non-excluded)
        # coinbase output at all (-> "shielded-or-none", the LARGEST
        # bucket), and 4 are split 3/1 between two real addresses A and B
        # so A alone needs to be counted to cross 50% among A+B, but the
        # shielded bucket must not inflate that count.
        h160_a = b"\x0a" * 20
        h160_b = b"\x0b" * 20
        script_a = bytes.fromhex("76a914") + h160_a + bytes.fromhex("88ac")
        script_b = bytes.fromhex("76a914") + h160_b + bytes.fromhex("88ac")
        blocks = (
            [[]] * 6  # no coinbase outputs at all -> shielded-or-none, ranks FIRST (6 blocks)
            + [[(1, script_a)]] * 3  # A: 3 blocks
            + [[(1, script_b)]] * 1  # B: 1 block
        )
        orig = miner.grpc
        miner.grpc = lambda host, method, msg: self._fake_grpc_blocks(blocks)
        try:
            result = miner.compute_concentration("fake-host", 0, 9, step=200)
        finally:
            miner.grpc = orig

        self.assertEqual(result["blocks"], 10)
        # shielded-or-none (6/10=60%) ranks ahead of A (3/10=30%) in the
        # Counter.most_common() ordering -- the buggy version would have
        # returned addressesToExceed50Pct=2 (counting the shielded bucket
        # as "address #1"), the fixed version must return 1 (A alone,
        # since A's 30% doesn't exceed 50%... wait: real addresses' total
        # is only 4/10=40%, so 50% of ALL blocks can never be exceeded by
        # real addresses alone here) -- so the correct answer is None, and
        # a None result (not a wrong integer like 2) is itself the
        # regression signal for this exact scenario.
        self.assertIsNone(result["addressesToExceed50Pct"])
        # 25% IS exceeded by A alone (3/10=30% > 25%), after 1 real address.
        self.assertEqual(result["addressesToExceed25Pct"], 1)


# Added 2026-09-18 alongside transparent_output_script()/taddr_balance() --
# both extracted from chains/zcash/scripts/zcash_read.py's `tx`/`balance` CLI
# branches so chains/zcash/scorers.py's new score_maya_asgard_vault() (Maya
# Protocol's Asgard vaults, a `t1`/P2PKH target -- the exact case that
# exposed the P2SH-only matcher bug this fixes) can call them directly,
# same "close a reuse gap, add coverage" pattern as this file's other tests.
class TestTransparentOutputScript(unittest.TestCase):
    def test_t1_mainnet_address_gets_p2pkh_script(self):
        # Real Maya Protocol Asgard vault address (data/scouting_candidates_2026-09-18.md).
        script = zr.transparent_output_script("t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT")
        self.assertTrue(script.startswith("76a914"))
        self.assertTrue(script.endswith("88ac"))
        self.assertEqual(len(script), 50)  # 76a914 + 20-byte hash160 + 88ac

    def test_t3_mainnet_address_gets_p2sh_script(self):
        # Real ZIP 271 lockbox address -- must be unaffected by the P2PKH fix.
        script = zr.transparent_output_script(REAL_LOCKBOX_ADDR)
        self.assertTrue(script.startswith("a914"))
        self.assertTrue(script.endswith("87"))
        self.assertEqual(len(script), 46)  # a914 + 20-byte hash160 + 87

    def test_p2pkh_and_p2sh_scripts_share_the_same_hash160_for_the_same_bytes(self):
        # Same 20-byte payload, different version prefix -- scripts must
        # differ only in their template, not in the embedded hash.
        h160 = "00" * 20
        # Build a t1 and a t3 address from the same hash160 directly.
        import hashlib as _hashlib

        def _b58enc(b):
            chk = _hashlib.sha256(_hashlib.sha256(b).digest()).digest()[:4]
            n = int.from_bytes(b + chk, "big")
            s = ""
            while n:
                n, r = divmod(n, 58)
                s = zr.B58[r] + s
            return s

        raw = bytes.fromhex(h160)
        t1_addr = _b58enc(bytes.fromhex("1cb8") + raw)
        t3_addr = _b58enc(bytes.fromhex("1cbd") + raw)
        self.assertEqual(zr.transparent_output_script(t1_addr), "76a914" + h160 + "88ac")
        self.assertEqual(zr.transparent_output_script(t3_addr), "a914" + h160 + "87")

    def test_unrecognised_prefix_raises(self):
        # A well-formed base58check string whose 2-byte prefix isn't one of
        # Zcash's 4 known transparent-address prefixes must raise, not
        # silently guess a script shape.
        import hashlib as _hashlib

        def _b58enc(b):
            chk = _hashlib.sha256(_hashlib.sha256(b).digest()).digest()[:4]
            n = int.from_bytes(b + chk, "big")
            s = ""
            while n:
                n, r = divmod(n, 58)
                s = zr.B58[r] + s
            return s

        bogus_addr = _b58enc(b"\xff\xff" + b"\x00" * 20)
        with self.assertRaises(ValueError):
            zr.transparent_output_script(bogus_addr)


class TestTaddrBalance(unittest.TestCase):
    def test_sums_single_address_balance_from_mocked_grpc(self):
        frame = zr.field_varint(1, 220970943152)
        orig = zr.grpc
        zr.grpc = lambda host, method, msg: [frame]
        try:
            result = zr.taddr_balance("fake-host", "t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT")
        finally:
            zr.grpc = orig
        self.assertEqual(result, 220970943152)

    def test_passes_every_address_argument_as_its_own_field(self):
        # GetTaddressBalance takes a repeated `addresses` field (tag 1);
        # verify multiple addresses are each encoded, not just the first.
        captured = {}

        def fake_grpc(host, method, msg):
            captured["msg"] = msg
            return [zr.field_varint(1, 999)]

        orig = zr.grpc
        zr.grpc = fake_grpc
        try:
            zr.taddr_balance("fake-host", "addrA", "addrB")
        finally:
            zr.grpc = orig
        decoded = zr.decode(captured["msg"])
        self.assertEqual([v for num, v in decoded if num == 1], [b"addrA", b"addrB"])


if __name__ == "__main__":
    unittest.main()
