"""
Unit tests for the new HyperEVM-side byte-decoding logic added 2026-09-17
(`chains/hyperliquid/scripts/methodology_test.py`: `_selector`,
`read_safe_hyperevm`, `read_access_control_role_members`,
`_safe_rooted_scores_hyperevm`) -- the first HyperEVM-native target this
project scores (Kinetiq's `HIP3StakingManager`), and the first Hyperliquid
addition this pass to get dedicated unit tests, since this specific
code (manual ABI array decoding, keccak-based selector computation) is
meaningfully more bug-prone than the API-field-reading code the rest of
this ecosystem's ecosystem file relies on (itself covered by
`methodology_test.py`'s own live dry-run discipline, not pytest-style
tests).

`evm()` is monkeypatched with real responses fetched live from
`https://rpc.hyperliquid.xyz/evm` on 2026-09-17 (see `chains/hyperliquid/
data/methodology_test_2026-09-17-kinetiq-staking-manager.md` for the full
derivation), frozen so this suite doesn't depend on network access or
mutable on-chain state.
"""
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


mt = _load_module("aro_test_hyperliquid_methodology_test", "chains/hyperliquid/scripts/methodology_test.py")

SAFE = "0x18a82c968b992d28d4d812920eb7b4305306f8f1"
PROXY = "0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec"

OWNERS_RESPONSE = (
    "0x0000000000000000000000000000000000000000000000000000000000000020"
    "0000000000000000000000000000000000000000000000000000000000000008"
    "000000000000000000000000806e5f088a12a86bf1984378a824c224d29c7503"
    "00000000000000000000000099ed257a514d81a62c3195934d4e63a1c2c3946a"
    "00000000000000000000000007c78968a1be7151ad62a6b95e11321a8a4f77cd"
    "000000000000000000000000f0b3a9bff7b733bbf6b9fdca20cc954de5e8aa77"
    "000000000000000000000000fcaddd4395fbc10fb6fa024a427561c1841a0849"
    "000000000000000000000000dc1c4b5d08528a25a96ba036ddd6496fa2fb6947"
    "0000000000000000000000009bd23f6e1012d490faee8c81d3bad9d4e4f71624"
    "00000000000000000000000064cbed11afe88631b7b6c12d8b50e59e8e07f42e"
)
THRESHOLD_RESPONSE = "0x" + "0" * 63 + "4"
# Realistic (address[], address) ABI encoding for getModulesPaginated:
# word0 = offset to the dynamic array, relative to the start of the
# return data (0x40 = 64 bytes, i.e. right after the 2 head words --
# a real Solidity ABI encoder's actual value for this exact return
# shape); word1 = the static `next` cursor address (0x0 here, unused by
# read_safe_hyperevm); word2 = array length (0, i.e. zero modules); no
# further words needed since a zero-length array has no elements. An
# earlier version of this fixture used word0=4 -- a nonsensical offset
# for this shape, harmless only because read_safe_hyperevm's own
# decoding assumes the fixed layout and never actually follows the
# offset word, but not representative of what a real eth_call response
# looks like.
MODULES_RESPONSE = "0x" + ("%064x" % 0x40) + ("0" * 64) + ("0" * 64)
GUARD_RESPONSE = "0x" + "0" * 64
ROLE_COUNT_RESPONSE_1 = "0x" + "0" * 63 + "1"
ROLE_COUNT_RESPONSE_0 = "0x" + "0" * 64
ROLE_MEMBER_RESPONSE = "0x" + "0" * 24 + SAFE[2:]


class TestSelector(unittest.TestCase):
    """Regression test for the exact bug this project's own docstring
    (methodology_test.py::_selector) says was caught during derivation:
    HexBytes.hex() does NOT include a "0x" prefix in this project's web3.py
    version, so slicing [2:10] silently produced every selector shifted by
    one byte."""

    def test_known_selectors_match_ethereum_standard_values(self):
        self.assertEqual(mt._selector("getOwners()"), "0xa0e67e2b")
        self.assertEqual(mt._selector("getThreshold()"), "0xe75235b8")
        self.assertEqual(mt._selector("owner()"), "0x8da5cb5b")
        self.assertEqual(mt._selector("getModulesPaginated(address,uint256)"), "0xcc2f8452")

    def test_selector_is_exactly_four_bytes(self):
        sel = mt._selector("anyFunction()")
        self.assertEqual(len(sel), 10)  # "0x" + 8 hex chars = 4 bytes


class TestReadSafeHyperEVM(unittest.TestCase):
    def setUp(self):
        self._orig_evm = mt.evm

        def fake_evm(method, params):
            if method == "eth_call":
                data = params[0]["data"]
                if data.startswith("0xa0e67e2b"):
                    return OWNERS_RESPONSE
                if data.startswith("0xe75235b8"):
                    return THRESHOLD_RESPONSE
                if data.startswith("0xcc2f8452"):
                    return MODULES_RESPONSE
                raise AssertionError(f"unexpected eth_call data: {data}")
            if method == "eth_getStorageAt":
                return GUARD_RESPONSE
            raise AssertionError(f"unexpected method: {method}")

        mt.evm = fake_evm

    def tearDown(self):
        mt.evm = self._orig_evm

    def test_decodes_eight_owners_and_threshold_four(self):
        safe = mt.read_safe_hyperevm(SAFE)
        self.assertEqual(safe["threshold"], 4)
        self.assertEqual(len(safe["owners"]), 8)
        self.assertIn("0x806e5f088a12a86bf1984378a824c224d29c7503", safe["owners"])

    def test_no_modules_no_guard(self):
        safe = mt.read_safe_hyperevm(SAFE)
        self.assertEqual(safe["modules"], [])
        self.assertEqual(int(safe["guard"], 16), 0)


class TestReadAccessControlRoleMembers(unittest.TestCase):
    def test_single_member_role(self):
        orig_eth_call = mt._eth_call
        try:
            def fake_eth_call(to, data):
                if data.startswith(mt._selector("getRoleMemberCount(bytes32)")):
                    return ROLE_COUNT_RESPONSE_1
                if data.startswith(mt._selector("getRoleMember(bytes32,uint256)")):
                    return ROLE_MEMBER_RESPONSE
                raise AssertionError(f"unexpected call: {data}")
            mt._eth_call = fake_eth_call
            members = mt.read_access_control_role_members(PROXY, "0x" + "0" * 64)
            self.assertEqual(members, [SAFE])
        finally:
            mt._eth_call = orig_eth_call

    def test_zero_member_role_returns_empty_list(self):
        orig_eth_call = mt._eth_call
        try:
            mt._eth_call = lambda to, data: ROLE_COUNT_RESPONSE_0
            members = mt.read_access_control_role_members(PROXY, "0x" + "1" * 64)
            self.assertEqual(members, [])
        finally:
            mt._eth_call = orig_eth_call


class TestSafeRootedScoresHyperEVM(unittest.TestCase):
    """Mirrors scripts/lib/scorers.py::_safe_rooted_scores's already-
    calibrated numbers exactly -- this is a reuse, not a new formula, and
    this test locks that reuse in place."""

    def test_four_of_eight_matches_kinetiq_live_result(self):
        admin, multisig, timelock = mt._safe_rooted_scores_hyperevm(4, 8)
        self.assertEqual((admin, multisig, timelock), (65, 80, 0))
        self.assertEqual(mt.composite(admin, multisig, timelock), 50)

    def test_threshold_one_scores_as_weak(self):
        admin, multisig, timelock = mt._safe_rooted_scores_hyperevm(1, 5)
        self.assertEqual(admin, 10)

    def test_threshold_two_is_between_one_and_three_plus(self):
        admin_1, _, _ = mt._safe_rooted_scores_hyperevm(1, 5)
        admin_2, _, _ = mt._safe_rooted_scores_hyperevm(2, 5)
        admin_3, _, _ = mt._safe_rooted_scores_hyperevm(3, 5)
        self.assertLess(admin_1, admin_2)
        self.assertLess(admin_2, admin_3)

    def test_multisig_capped_at_100(self):
        _, multisig, _ = mt._safe_rooted_scores_hyperevm(10, 20)
        self.assertEqual(multisig, 100)


class TestAddressFromHex(unittest.TestCase):
    """Regression tests for the adversarial-review finding fixed 2026-09-17:
    `"0x" + raw[-40:]` on a too-short `raw` (e.g. "0x", a no-code address's
    real eth_call return value) used to silently produce a malformed
    "0x0x..." string rather than failing at the actual point of the bad
    read."""

    def test_extracts_address_from_a_full_32_byte_word(self):
        word = "0x" + "0" * 24 + SAFE[2:]
        self.assertEqual(mt._address_from_hex(word, "test"), SAFE)

    def test_raises_on_no_code_response(self):
        with self.assertRaises(mt.HyperEvmReadError):
            mt._address_from_hex("0x", "test context")

    def test_raises_on_truncated_response(self):
        with self.assertRaises(mt.HyperEvmReadError):
            mt._address_from_hex("0x1234", "test context")

    def test_error_message_names_the_context(self):
        try:
            mt._address_from_hex("0x", "proxy EIP-1967 admin slot")
        except mt.HyperEvmReadError as e:
            self.assertIn("proxy EIP-1967 admin slot", str(e))
        else:
            self.fail("expected HyperEvmReadError")


class TestReadSafeHyperEvmValidation(unittest.TestCase):
    """Regression tests for the adversarial-review finding fixed 2026-09-17:
    read_safe_hyperevm previously had no shape/threshold validation and
    could silently decode a non-Safe response into a self-contradictory
    result (e.g. "5-of-0") with no warning."""

    def _patch_evm(self, owners_response, threshold_response, modules_response=MODULES_RESPONSE, guard_response=GUARD_RESPONSE):
        def fake_evm(method, params):
            if method == "eth_call":
                data = params[0]["data"]
                if data.startswith("0xa0e67e2b"):
                    return owners_response
                if data.startswith("0xe75235b8"):
                    return threshold_response
                if data.startswith("0xcc2f8452"):
                    return modules_response
                raise AssertionError(f"unexpected eth_call data: {data}")
            if method == "eth_getStorageAt":
                return guard_response
            raise AssertionError(f"unexpected method: {method}")
        return fake_evm

    def test_raises_on_response_too_short_for_a_real_array_encoding(self):
        orig_evm = mt.evm
        try:
            mt.evm = self._patch_evm("0x" + "0" * 62, THRESHOLD_RESPONSE)
            with self.assertRaises(mt.HyperEvmReadError):
                mt.read_safe_hyperevm(SAFE)
        finally:
            mt.evm = orig_evm

    def test_raises_on_zero_threshold(self):
        orig_evm = mt.evm
        try:
            mt.evm = self._patch_evm(OWNERS_RESPONSE, "0x" + "0" * 64)
            with self.assertRaises(mt.HyperEvmReadError):
                mt.read_safe_hyperevm(SAFE)
        finally:
            mt.evm = orig_evm

    def test_raises_on_threshold_exceeding_owner_count(self):
        orig_evm = mt.evm
        try:
            # 8 owners in OWNERS_RESPONSE, threshold=9 is structurally impossible
            mt.evm = self._patch_evm(OWNERS_RESPONSE, "0x" + "0" * 63 + "9")
            with self.assertRaises(mt.HyperEvmReadError):
                mt.read_safe_hyperevm(SAFE)
        finally:
            mt.evm = orig_evm

    def test_valid_safe_still_decodes_cleanly(self):
        orig_evm = mt.evm
        try:
            mt.evm = self._patch_evm(OWNERS_RESPONSE, THRESHOLD_RESPONSE)
            safe = mt.read_safe_hyperevm(SAFE)
            self.assertEqual(safe["threshold"], 4)
            self.assertEqual(len(safe["owners"]), 8)
            self.assertFalse(safe["modulesPageMayBeTruncated"])
        finally:
            mt.evm = orig_evm


class TestClassifyAuthorityHolder(unittest.TestCase):
    """Regression tests for the most severe adversarial-review finding
    fixed 2026-09-17: the original score_kinetiq_staking_manager() checked
    only DEFAULT_ADMIN_ROLE and its docstring wrongly generalized that
    every other role "has zero current holders" -- never actually checked.
    Live re-verification found OPERATOR_ROLE held by a bare EOA and
    TREASURY_ROLE by a separate Safe. _classify_authority_holder is the
    piece that must tell these apart correctly."""

    OPERATOR_EOA = "0x4459872f33d7e3b61238a6edc7611463c25d82fa"

    def test_bare_eoa_scores_as_weak_single_key(self):
        orig_evm = mt.evm
        try:
            mt.evm = lambda method, params: "0x"  # eth_getCode of a bare EOA
            scores, info_ = mt._classify_authority_holder(self.OPERATOR_EOA)
            self.assertEqual(scores, (10, 0, 0))
            self.assertEqual(info_["kind"], "bare EOA")
        finally:
            mt.evm = orig_evm

    def test_gnosis_safe_scores_via_safe_rooted_scores(self):
        orig_evm = mt.evm
        try:
            def fake_evm(method, params):
                if method == "eth_getCode":
                    return "0x6080604052"  # has code -> not a bare EOA
                if method == "eth_call":
                    data = params[0]["data"]
                    if data.startswith("0xa0e67e2b"):
                        return OWNERS_RESPONSE
                    if data.startswith("0xe75235b8"):
                        return THRESHOLD_RESPONSE
                    if data.startswith("0xcc2f8452"):
                        return MODULES_RESPONSE
                    raise AssertionError(f"unexpected eth_call data: {data}")
                if method == "eth_getStorageAt":
                    return GUARD_RESPONSE
                raise AssertionError(f"unexpected method: {method}")
            mt.evm = fake_evm
            scores, info_ = mt._classify_authority_holder(SAFE)
            self.assertEqual(scores, (65, 80, 0))
            self.assertEqual(info_["kind"], "Gnosis Safe")
            self.assertEqual(info_["threshold"], 4)
        finally:
            mt.evm = orig_evm

    def test_unresolvable_contract_degrades_conservatively_not_crashes(self):
        # Has code, but getOwners() returns garbage too short to be a real
        # (address[]) ABI encoding -- must degrade to 20/0/0, matching
        # scripts/lib/scorers.py::_safe_rooted_entry's own fallback
        # convention, not raise out of score_kinetiq_staking_manager().
        orig_evm = mt.evm
        try:
            def fake_evm(method, params):
                if method == "eth_getCode":
                    return "0x6080604052"
                if method == "eth_call":
                    return "0x" + "0" * 62  # too short to be a real array encoding
                if method == "eth_getStorageAt":
                    return GUARD_RESPONSE
                raise AssertionError(f"unexpected method: {method}")
            mt.evm = fake_evm
            scores, info_ = mt._classify_authority_holder("0x" + "ab" * 20)
            self.assertEqual(scores, (20, 0, 0))
            self.assertEqual(info_["kind"], "unresolved (not a decodable Safe)")
        finally:
            mt.evm = orig_evm


if __name__ == "__main__":
    unittest.main()
