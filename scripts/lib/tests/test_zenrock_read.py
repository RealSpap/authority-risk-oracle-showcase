"""
Unit tests for `chains/zcash/scripts/zenrock_read.py` -- Zenrock's own
`zrchain` custody chain reader behind the `zenZEC` MPC keyring target
(`chains/zcash/scorers.py::score_zenzec_mpc_keyring()`, added 2026-09-19).

Found 2026-09-19 while sweeping every ecosystem's scorer dependencies for
test coverage: this module had ZERO tests of any kind, direct or
indirect -- a real gap, and arguably a MORE bug-prone one than the
already-tested Hyperliquid HyperEVM decode helpers, since this file is a
hand-rolled protobuf reader (varint + length-delimited wire types only,
no protobuf runtime) written from scratch against zrchain's own `.pb.go`
source, guarding real custodied value (~$494K in zenZEC per the scorer's
own docstring). The module's own docstring flags this explicitly: "A
future zrchain proto change would need this file re-checked."

No network access: every test either (a) round-trips through the
module's OWN encode helpers (`_field_bytes`/`_field_varint`, the true
inverse of `_decode_tlv`) to build synthetic-but-correctly-shaped request/
response bytes, or (b) cross-checks against an independently-written
reference computation for the cryptographic primitives (hash160,
Base58Check), the same "two independent paths, not one library trusting
itself" discipline `test_bridge2_hyperevm.py` already established for
Hyperliquid's own manual ABI decode.
"""
import hashlib
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    ecosystem_dir = os.path.dirname(file_path)
    if ecosystem_dir not in sys.path:
        sys.path.insert(0, ecosystem_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


zr = _load_module("aro_test_zcash_zenrock_read", "chains/zcash/scripts/zenrock_read.py")


class TestVarint(unittest.TestCase):
    """Known-answer tests, computed independently (a plain protobuf varint
    is base-128 continuation-bit encoding, standard and checkable by hand,
    not this project's own invention)."""

    def test_known_encodings(self):
        cases = {
            0: "00",
            1: "01",
            127: "7f",        # largest 1-byte value (no continuation bit)
            128: "8001",      # smallest 2-byte value
            300: "ac02",
            16384: "808001",  # smallest 3-byte value (2^14)
            123456789: "959aef3a",
        }
        for value, expected_hex in cases.items():
            self.assertEqual(zr._varint(value).hex(), expected_hex)

    def test_read_varint_inverts_varint_for_every_known_case(self):
        for value in [0, 1, 127, 128, 300, 16384, 123456789]:
            encoded = zr._varint(value)
            decoded, consumed = zr._read_varint(encoded, 0)
            self.assertEqual(decoded, value)
            self.assertEqual(consumed, len(encoded))

    def test_read_varint_respects_start_offset(self):
        # Real usage always reads varints out of a larger buffer at a
        # moving cursor position, never from a fresh buffer at index 0.
        buf = b"\xff\xff" + zr._varint(300)
        decoded, consumed = zr._read_varint(buf, 2)
        self.assertEqual(decoded, 300)
        self.assertEqual(consumed, 4)


class TestFieldEncodeHelpers(unittest.TestCase):
    def test_field_varint_matches_hand_built_key_byte(self):
        # field 6 (party_threshold), wire type 0 (varint) -> key = 6<<3|0 = 48 = 0x30
        encoded = zr._field_varint(6, 5)
        self.assertEqual(encoded[0], 0x30)
        self.assertEqual(encoded, bytes([0x30]) + zr._varint(5))

    def test_field_bytes_matches_hand_built_key_byte_and_length_prefix(self):
        # field 1, wire type 2 (length-delimited) -> key = 1<<3|2 = 10 = 0x0a
        payload = b"hello"
        encoded = zr._field_bytes(1, payload)
        self.assertEqual(encoded[0], 0x0A)
        self.assertEqual(encoded, bytes([0x0A]) + zr._varint(len(payload)) + payload)


class TestDecodeTlv(unittest.TestCase):
    """`_decode_tlv` is the core parser every response-decoding function in
    this module depends on -- exercised here via its own inverse
    (`_field_bytes`/`_field_varint`), a legitimate round trip since those
    two helpers implement the encoding side of the identical wire format,
    not a copy of the decode logic under test."""

    def test_single_varint_field(self):
        blob = zr._field_varint(6, 42)
        self.assertEqual(zr._decode_tlv(blob), [(6, 42)])

    def test_single_bytes_field(self):
        blob = zr._field_bytes(3, b"zrchain")
        self.assertEqual(zr._decode_tlv(blob), [(3, b"zrchain")])

    def test_multiple_fields_in_order(self):
        blob = zr._field_bytes(1, b"addr") + zr._field_varint(6, 3) + zr._field_bytes(2, b"creator")
        self.assertEqual(
            zr._decode_tlv(blob),
            [(1, b"addr"), (6, 3), (2, b"creator")],
        )

    def test_repeated_field_appears_once_per_occurrence_not_collapsed(self):
        # The module's own get_key_by_id() docstring calls out the exact
        # regression this guards: collapsing repeated fields into a dict()
        # keeps only the LAST occurrence and silently drops the rest.
        blob = zr._field_bytes(2, b"wallet-mainnet") + zr._field_bytes(2, b"wallet-regtest")
        self.assertEqual(
            zr._decode_tlv(blob),
            [(2, b"wallet-mainnet"), (2, b"wallet-regtest")],
        )

    def test_unhandled_wire_type_raises(self):
        # Wire type 1 (64-bit fixed) is real protobuf but genuinely never
        # used by anything this module reads -- key byte for field 1, wire
        # type 1: (1<<3)|1 = 9.
        blob = bytes([0x09]) + b"\x00" * 8
        with self.assertRaises(ValueError):
            zr._decode_tlv(blob)

    def test_empty_buffer_decodes_to_empty_list(self):
        self.assertEqual(zr._decode_tlv(b""), [])


class TestHash160(unittest.TestCase):
    def test_matches_independently_chained_sha256_then_ripemd160(self):
        for payload in [b"", b"abc", bytes(range(33))]:
            expected = hashlib.new("ripemd160", hashlib.sha256(payload).digest()).digest()
            self.assertEqual(zr._hash160(payload), expected)

    def test_output_is_20_bytes(self):
        self.assertEqual(len(zr._hash160(b"anything")), 20)


class TestB58Encode(unittest.TestCase):
    def _reference_b58decode(self, s):
        """Independent reference decoder (the inverse of the module's own
        algorithm, written fresh here rather than imported) -- round-
        tripping through this is a real correctness check, not a tautology,
        since a directional bug in `_b58encode` (wrong alphabet index,
        wrong byte order) would break the round trip."""
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        n = 0
        n_ones = 0
        for c in s:
            if c == "1" and n == 0:
                n_ones += 1
            n = n * 58 + alphabet.index(c)
        body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
        return b"\x00" * n_ones + body

    def test_round_trips_arbitrary_payloads(self):
        for payload in [b"\x00", b"\x00\x00\x01", bytes(range(25)), bytes([0xFF] * 25)]:
            encoded = zr._b58encode(payload)
            self.assertEqual(self._reference_b58decode(encoded), payload)

    def test_empty_bytes_encodes_to_empty_string(self):
        self.assertEqual(zr._b58encode(b""), "")

    def test_leading_zero_bytes_become_leading_1_characters(self):
        # Standard Base58Check convention (same as Bitcoin/Zcash addresses):
        # each leading 0x00 byte maps to a leading '1', since plain
        # base-256-to-base-58 conversion would otherwise drop them (0 in
        # any base is still 0).
        encoded = zr._b58encode(b"\x00\x00" + b"\x01")
        self.assertTrue(encoded.startswith("11"))

    def test_alphabet_excludes_visually_ambiguous_characters(self):
        # Bitcoin-style Base58 deliberately omits 0, O, I, l -- confirm the
        # module's own alphabet constant (inlined in _b58encode) still does,
        # by checking a wide range of encoded outputs never contains them.
        ambiguous = set("0OIl")
        for payload in [bytes(range(i, i + 20)) for i in range(0, 200, 20)]:
            encoded = zr._b58encode(payload)
            self.assertFalse(ambiguous & set(encoded), f"{encoded!r} contains an ambiguous character")


class TestZcashMainnetP2pkhAddress(unittest.TestCase):
    def test_known_answer_vector(self):
        # Independently computed (separate script, not this module) for a
        # fixed synthetic 33-byte compressed-pubkey-shaped input -- see
        # this test file's own derivation notes in the commit that added
        # it. Locks in the full chain: hash160 -> version-prefix -> double-
        # SHA256 checksum -> Base58Check, matching zrchain's own
        # `wallet_zcash.go` algorithm this function re-derives.
        pubkey = bytes([0x02]) + bytes(range(1, 33))
        self.assertEqual(zr.zcash_mainnet_p2pkh_address(pubkey), "t1N9mwrrhJbfpiZgM8mR2hNRjxbUKcdHN1u")

    def test_uses_zcash_version_bytes_not_bitcoins(self):
        # Zcash's mainnet P2PKH version is 2 bytes (0x1C, 0xB8); Bitcoin's
        # is 1 byte (0x00) -- a real, easy-to-transpose distinction this
        # module's own docstring calls out explicitly. Confirm the payload
        # actually being checksummed/encoded starts with Zcash's prefix.
        pubkey = bytes([0x03]) + bytes(range(32, 0, -1))
        h = zr._hash160(pubkey)
        expected_payload = bytes([0x1C, 0xB8]) + h
        checksum = hashlib.sha256(hashlib.sha256(expected_payload).digest()).digest()[:4]
        expected_addr = zr._b58encode(expected_payload + checksum)
        self.assertEqual(zr.zcash_mainnet_p2pkh_address(pubkey), expected_addr)

    def test_different_pubkeys_produce_different_addresses(self):
        addr_a = zr.zcash_mainnet_p2pkh_address(bytes([0x02]) + bytes(range(1, 33)))
        addr_b = zr.zcash_mainnet_p2pkh_address(bytes([0x02]) + bytes(range(2, 34)))
        self.assertNotEqual(addr_a, addr_b)


class TestGetKeyring(unittest.TestCase):
    """Exercises get_keyring() end-to-end against a synthetic ABCI response
    built from the module's own encode helpers, matching the real field
    layout documented in get_keyring()'s own docstring (address=1,
    creator=2, description=3, admins=4 repeated, parties=5 repeated,
    party_threshold=6, key_req_fee=7, sig_req_fee=8, is_active=9)."""

    def _wire(self, response_bytes, height=9534552):
        orig = zr.abci_query
        zr.abci_query = lambda path, data=b"", host=zr.RPC_HOST, tries=3: (response_bytes, height)
        self.addCleanup(lambda: setattr(zr, "abci_query", orig))

    def _build_keyring_response(self, address="keyring1abc", creator="zrchain1creator",
                                 admins=("zrchain1admin1",), parties=("zrchain1p1", "zrchain1p2", "zrchain1p3"),
                                 party_threshold=2, is_active=True):
        keyring_fields = b"".join([
            zr._field_bytes(1, address.encode()),
            zr._field_bytes(2, creator.encode()),
        ])
        for a in admins:
            keyring_fields += zr._field_bytes(4, a.encode())
        for p in parties:
            keyring_fields += zr._field_bytes(5, p.encode())
        keyring_fields += zr._field_varint(6, party_threshold)
        if is_active:
            keyring_fields += zr._field_varint(9, 1)
        # QueryKeyringByAddressResponse wraps the Keyring in field 1
        return zr._field_bytes(1, keyring_fields)

    def test_parses_all_scalar_and_repeated_fields(self):
        self._wire(self._build_keyring_response())
        result = zr.get_keyring("keyring1abc")
        self.assertEqual(result["address"], "keyring1abc")
        self.assertEqual(result["creator"], "zrchain1creator")
        self.assertEqual(result["admins"], ["zrchain1admin1"])
        self.assertEqual(result["parties"], ["zrchain1p1", "zrchain1p2", "zrchain1p3"])
        self.assertEqual(result["party_threshold"], 2)
        self.assertTrue(result["is_active"])
        self.assertEqual(result["height"], 9534552)

    def test_three_of_three_parties_and_threshold_two_round_trips(self):
        self._wire(self._build_keyring_response(parties=("p1", "p2", "p3"), party_threshold=2))
        result = zr.get_keyring("keyring1abc")
        self.assertEqual(len(result["parties"]), 3)
        self.assertEqual(result["party_threshold"], 2)

    def test_omitted_proto3_defaults_fall_back_to_documented_zero_values(self):
        # party_threshold and is_active are proto3-omitted on the wire when
        # zero/false -- get_keyring() must default them, not KeyError.
        keyring_fields = zr._field_bytes(1, b"keyring1sparse")
        self._wire(zr._field_bytes(1, keyring_fields))
        result = zr.get_keyring("keyring1sparse")
        self.assertEqual(result["party_threshold"], 0)
        self.assertFalse(result["is_active"])
        self.assertEqual(result["admins"], [])
        self.assertEqual(result["parties"], [])

    def test_missing_wrapper_field_raises_rather_than_returning_empty_dict(self):
        self._wire(b"")  # no field 1 at all
        with self.assertRaises(RuntimeError):
            zr.get_keyring("keyring1abc")


class TestGetKeyById(unittest.TestCase):
    """Exercises get_key_by_id() -- the docstring's own most important
    regression target: `wallets` (field 2) is REPEATED at the top level
    and must never collapse through a plain dict(), or every wallet but
    the last is silently dropped."""

    def _wire(self, response_bytes, height=9534552):
        orig = zr.abci_query
        zr.abci_query = lambda path, data=b"", host=zr.RPC_HOST, tries=3: (response_bytes, height)
        self.addCleanup(lambda: setattr(zr, "abci_query", orig))

    def _key_response_field(self, key_id=387, workspace="zrchain1ws", keyring="keyring1abc",
                             key_type="KEY_TYPE_BITCOIN_SECP256K1", pubkey=None):
        fields = b"".join([
            zr._field_varint(1, key_id),
            zr._field_bytes(2, workspace.encode()),
            zr._field_bytes(3, keyring.encode()),
            zr._field_bytes(4, key_type.encode()),
        ])
        if pubkey is not None:
            fields += zr._field_bytes(5, pubkey)
        return zr._field_bytes(1, fields)

    def _wallet_response_field(self, address, wtype):
        wallet_fields = zr._field_bytes(1, address.encode()) + zr._field_bytes(2, wtype.encode())
        return zr._field_bytes(2, wallet_fields)

    def test_multiple_wallets_all_survive_not_just_the_last(self):
        pubkey = bytes([0x02]) + bytes(range(1, 33))
        blob = (
            self._key_response_field(pubkey=pubkey)
            + self._wallet_response_field("t1MainnetAddr", "Zcash")
            + self._wallet_response_field("tmRegtestAddr", "Zcash Regtest")
        )
        self._wire(blob)
        result = zr.get_key_by_id(387)
        self.assertEqual(result["wallets"], {"Zcash": "t1MainnetAddr", "Zcash Regtest": "tmRegtestAddr"})

    def test_scalar_key_fields_parsed(self):
        self._wire(self._key_response_field(key_id=388, workspace="ws2", keyring="kr2"))
        result = zr.get_key_by_id(388)
        self.assertEqual(result["id"], 388)
        self.assertEqual(result["workspace_addr"], "ws2")
        self.assertEqual(result["keyring_addr"], "kr2")
        self.assertEqual(result["key_type"], "KEY_TYPE_BITCOIN_SECP256K1")

    def test_bitcoin_secp256k1_key_gets_rederived_zcash_address(self):
        pubkey = bytes([0x02]) + bytes(range(1, 33))
        self._wire(self._key_response_field(pubkey=pubkey))
        result = zr.get_key_by_id(387)
        self.assertEqual(result["zcash_mainnet_address_rederived"], zr.zcash_mainnet_p2pkh_address(pubkey))

    def test_non_bitcoin_key_type_does_not_attempt_rederivation(self):
        pubkey = bytes(32)
        self._wire(self._key_response_field(key_type="KEY_TYPE_ED25519", pubkey=pubkey))
        result = zr.get_key_by_id(387)
        self.assertNotIn("zcash_mainnet_address_rederived", result)

    def test_no_pubkey_present_does_not_attempt_rederivation(self):
        self._wire(self._key_response_field(pubkey=None))
        result = zr.get_key_by_id(387)
        self.assertNotIn("zcash_mainnet_address_rederived", result)


class TestGetDctAssetParams(unittest.TestCase):
    def _wire(self, response_bytes, height=9534552):
        orig = zr.abci_query
        zr.abci_query = lambda path, data=b"", host=zr.RPC_HOST, tries=3: (response_bytes, height)
        self.addCleanup(lambda: setattr(zr, "abci_query", orig))

    def _asset_params_field(self, asset_enum, deposit_keyring=None, rewards_key_id=None,
                             change_address_key_ids=None, proxy_address=None,
                             solana_signer_key_id=None, solana_mint_address=None):
        fields = zr._field_varint(1, asset_enum)
        if deposit_keyring is not None:
            fields += zr._field_bytes(2, deposit_keyring.encode())
        if rewards_key_id is not None:
            fields += zr._field_varint(7, rewards_key_id)
        if change_address_key_ids is not None:
            packed = b"".join(zr._varint(v) for v in change_address_key_ids)
            fields += zr._field_bytes(8, packed)
        if proxy_address is not None:
            fields += zr._field_bytes(9, proxy_address.encode())
        if solana_signer_key_id is not None or solana_mint_address is not None:
            sol = b""
            if solana_signer_key_id is not None:
                sol += zr._field_varint(1, solana_signer_key_id)
            if solana_mint_address is not None:
                sol += zr._field_bytes(5, solana_mint_address.encode())
            fields += zr._field_bytes(12, sol)
        return fields

    def _params_response(self, *asset_params_blobs):
        # Params{ repeated AssetParams assets = 1 } serializes as one
        # `_field_bytes(1, blob)` per entry, concatenated -- NOT wrapped in
        # an extra outer field, since "repeated" fields don't get their own
        # length-delimited container the way a single nested message does.
        # QueryParamsResponse{ Params params = 1 } then wraps THAT once.
        assets = b"".join(zr._field_bytes(1, blob) for blob in asset_params_blobs)
        return zr._field_bytes(1, assets)

    def test_finds_matching_asset_among_several(self):
        other = self._asset_params_field(asset_enum=1, deposit_keyring="keyring1other")
        zenzec = self._asset_params_field(
            asset_enum=2, deposit_keyring="keyring1zenzec", rewards_key_id=387,
            change_address_key_ids=[388, 389], proxy_address="zrchain1proxy",
            solana_signer_key_id=42, solana_mint_address="So1anaMintAddr11111111111111111111111",
        )
        self._wire(self._params_response(other, zenzec))
        result = zr.get_dct_asset_params(2)
        self.assertEqual(result["asset"], 2)
        self.assertEqual(result["deposit_keyring_addr"], "keyring1zenzec")
        self.assertEqual(result["rewards_deposit_key_id"], 387)
        self.assertEqual(result["change_address_key_ids"], [388, 389])
        self.assertEqual(result["proxy_address"], "zrchain1proxy")
        self.assertEqual(result["solana_signer_key_id"], 42)
        self.assertEqual(result["solana_mint_address"], "So1anaMintAddr11111111111111111111111")

    def test_packed_repeated_varint_decodes_every_id(self):
        zenzec = self._asset_params_field(asset_enum=2, change_address_key_ids=[1, 300, 16384])
        self._wire(self._params_response(zenzec))
        result = zr.get_dct_asset_params(2)
        self.assertEqual(result["change_address_key_ids"], [1, 300, 16384])

    def test_asset_not_found_raises(self):
        other = self._asset_params_field(asset_enum=1)
        self._wire(self._params_response(other))
        with self.assertRaises(RuntimeError):
            zr.get_dct_asset_params(2)

    def test_omitted_optional_fields_absent_not_defaulted(self):
        # The module's own docstring: absent proto3 fields (e.g. no
        # StakerKeyId today) must stay ABSENT, not silently defaulted to a
        # misleadingly-specific 0 -- confirmed here for the fields this
        # decoder actually implements.
        bare = self._asset_params_field(asset_enum=2)
        self._wire(self._params_response(bare))
        result = zr.get_dct_asset_params(2)
        self.assertNotIn("deposit_keyring_addr", result)
        self.assertNotIn("rewards_deposit_key_id", result)
        self.assertNotIn("proxy_address", result)


if __name__ == "__main__":
    unittest.main()
