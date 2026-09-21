"""
Unit tests for the SECOND HyperEVM-native target this project scores
(`para StakingVault`, added 2026-09-17 same day as Kinetiq's
`HIP3StakingManager`) and for three general fixes to the SHARED HyperEVM
read helpers (`chains/hyperliquid/scripts/methodology_test.py`) this
target's own live investigation surfaced:

  1. `read_role_registry_role_holders` -- a NEW ABI read pattern (Solady
     `EnumerableRoles.roleHolders(uint256)`, wrapped by a project's own
     `RoleRegistry.roleHolders(bytes32)`) -- one call returns the full
     holder array directly, unlike OpenZeppelin's `AccessControlEnumerable`
     count-then-index-loop already covered by `test_kinetiq_hyperevm.py`.
  2. `HyperEvmRpcError` -- `evm()` previously did a bare `["result"]`
     lookup, crashing with an opaque `KeyError` on any RPC-level revert
     (a real, common case: calling `getOwners()` against a contract that
     simply isn't a Safe reverts, it doesn't return a malformed result).
  3. `_classify_authority_holder`'s new `none_means_renounced` parameter,
     ported from this project's own `none_means_renounced` convention on
     the Solana side (the same-day Drift Protocol correction).

Plus five further fixes an adversarial review of this same addition found
and confirmed via independent re-verification (fresh live RPC calls, not
just re-reading the claim) BEFORE any of it reached a commit:
  4. `_bytes_from_hex` -- `bytes.fromhex()` raises a bare, uncategorized
     `ValueError` on malformed hex, which slipped past every
     `except (HyperEvmReadError, HyperEvmRpcError)` clause in this file,
     including inside `read_safe_hyperevm` itself (present even after
     that function's OWN prior hardening pass, since that pass validated
     shape AFTER the conversion, not around the conversion).
  5. A role hash (`MANAGER_ROLE()`/`OPERATOR_ROLE()`) with no length
     check used to be spliced straight into `.rjust(64, "0")` -- a short
     or empty response would silently zero-pad into `bytes32(0)`, this
     project's own `DEFAULT_ADMIN_ROLE` sentinel elsewhere, querying a
     completely different, unintended role with no error at all.
  6. `score_para_staking_vault`'s per-role read (`read_role_registry_
     role_holders`) was unwrapped -- ANY single role failing to read used
     to crash the WHOLE target's score instead of degrading just that one
     role, unlike an individual unresolvable HOLDER, which `_classify_
     authority_holder` already degraded gracefully.
  7. `_classify_authority_holder`'s Gnosis Safe branch used to return only
     `len(safe["owners"])` (a count) in its `info_` dict, never the actual
     owner addresses -- so a cross-exposure check built from these `info_`
     dicts could never see an owner nested one level inside a Safe (a
     real case here: one of `para` StakingVault's `OPERATOR_ROLE` Safe's 3
     owners is the SAME address as the separate `RoleRegistry.owner()`
     Safe's own sole owner). Fixed by adding `ownerAddresses` alongside
     the existing count.

`evm()`/`_eth_call()` are monkeypatched with real responses fetched live
from `https://rpc.hyperliquid.xyz/evm` on 2026-09-17 (see `chains/
hyperliquid/data/methodology_test_2026-09-17-para-staking-vault.md` for
the full derivation), frozen so this suite doesn't depend on network
access or mutable on-chain state.
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


mt = _load_module("aro_test_hyperliquid_methodology_test_para", "chains/hyperliquid/scripts/methodology_test.py")

ROLE_REGISTRY = "0x8888888b418d2a2dec293fa30e1e202586f19fc0"
MANAGER_ROLE = "0x241ecf16d79d0f8dbfb92cbc07fe17840425976cf0667f022fe9877caa831b08"
OPERATOR_ROLE = "0x97667070c54ef182b0f5858b034beac1b6f3089aa2d3188bb1e8929f4fa9b929"
HOLDER_A = "0x8888888745a9155d012f0e546de03ff142b2f92c"
HOLDER_B = "0x5a24d40ef0b6856aefeefe65c332ce7cc7d9ba04"


class TestRoleHashConstants(unittest.TestCase):
    """A hand-typed 32-byte hex constant truncated by exactly one digit has
    now happened THREE times in this same investigation (the EIP-1967
    slot constants, twice, and MANAGER_ROLE, while drafting this very test
    file) -- always silently, since Python string slicing never raises on
    a too-short input. Recompute both role-hash constants from scratch
    here rather than trust the literals above, so a future edit that
    reintroduces the same one-digit truncation fails loudly."""

    def test_manager_role_matches_keccak256(self):
        from web3 import Web3
        self.assertEqual(MANAGER_ROLE, "0x" + Web3.keccak(text="MANAGER_ROLE").hex())
        self.assertEqual(len(MANAGER_ROLE), 66)  # "0x" + 64 hex chars = 32 bytes

    def test_operator_role_matches_keccak256(self):
        from web3 import Web3
        self.assertEqual(OPERATOR_ROLE, "0x" + Web3.keccak(text="OPERATOR_ROLE").hex())
        self.assertEqual(len(OPERATOR_ROLE), 66)


def _encode_address_array(addrs):
    """Real (address[]) ABI encoding for a plain `returns (address[]
    memory)`: an offset word (0x20 -- the array data starts right after
    this single head word, the standard encoding for one dynamic return
    value), then a length word, then one right-padded 32-byte word per
    address -- the exact shape `roleHolders(bytes32)` returns in one call.
    `read_role_registry_role_holders` reads the length from data[32:64]
    (i.e. it expects this leading offset word) exactly like
    `read_safe_hyperevm`'s own `getModulesPaginated` decode does -- this
    fixture originally omitted the offset word entirely, which surfaced
    as every test in this class raising HyperEvmReadError (the "length"
    it read was actually the first address's own bytes) -- fixed here,
    not in the function, which was correct against real live data."""
    body = "".join("0" * 24 + a[2:].lower() for a in addrs)
    return "0x" + ("%064x" % 0x20) + ("%064x" % len(addrs)) + body


class TestReadRoleRegistryRoleHolders(unittest.TestCase):
    def _patch(self, response):
        orig = mt.evm

        def fake_evm(method, params):
            if method == "eth_call":
                return response
            raise AssertionError(f"unexpected method: {method}")
        mt.evm = fake_evm
        return orig

    def test_single_holder(self):
        orig = self._patch(_encode_address_array([HOLDER_A]))
        try:
            holders = mt.read_role_registry_role_holders(ROLE_REGISTRY, MANAGER_ROLE)
            self.assertEqual(holders, [HOLDER_A])
        finally:
            mt.evm = orig

    def test_multiple_holders(self):
        orig = self._patch(_encode_address_array([HOLDER_A, HOLDER_B]))
        try:
            holders = mt.read_role_registry_role_holders(ROLE_REGISTRY, MANAGER_ROLE)
            self.assertEqual(holders, [HOLDER_A, HOLDER_B])
        finally:
            mt.evm = orig

    def test_zero_holders(self):
        orig = self._patch(_encode_address_array([]))
        try:
            holders = mt.read_role_registry_role_holders(ROLE_REGISTRY, MANAGER_ROLE)
            self.assertEqual(holders, [])
        finally:
            mt.evm = orig

    def test_raises_on_response_too_short(self):
        orig = self._patch("0x" + "0" * 62)
        try:
            with self.assertRaises(mt.HyperEvmReadError):
                mt.read_role_registry_role_holders(ROLE_REGISTRY, MANAGER_ROLE)
        finally:
            mt.evm = orig

    def test_raises_when_claimed_length_exceeds_actual_data(self):
        # offset word (0x20) + length word claiming 5 holders, but no
        # address words actually follow -- passes the first (>=64 bytes)
        # check, then must fail the second (enough bytes for 5 addresses).
        orig = self._patch("0x" + ("%064x" % 0x20) + ("%064x" % 5))
        try:
            with self.assertRaises(mt.HyperEvmReadError):
                mt.read_role_registry_role_holders(ROLE_REGISTRY, MANAGER_ROLE)
        finally:
            mt.evm = orig


class TestHyperEvmRpcError(unittest.TestCase):
    """Regression tests for the crash this project's own live investigation
    of para's MANAGER_ROLE holder surfaced: calling getOwners() against a
    contract that reverts (because it isn't a Safe at all) used to crash
    with a bare KeyError inside evm() instead of degrading the way every
    other malformed-response case already does."""

    def test_evm_raises_hyperevmreaderror_on_a_confirmed_revert(self):
        # UPDATED 2026-09-22: error code 3 ("execution reverted") is now classified as a confirmed
        # revert and raised as HyperEvmReadError, NOT HyperEvmRpcError -- see both classes' own
        # docstrings. Until this date evm() raised HyperEvmRpcError for every non-"result" response
        # regardless of code, so this exact JSON-RPC error object (code 3, a textbook revert) was
        # indistinguishable from a genuine RPC-level failure (rate limit, internal error) -- exactly
        # the "None for a revert same as for a network failure" ambiguity this project's web3_utils
        # module was fixed to close the same day, applied here to Hyperliquid's own zero-dependency
        # RPC layer (the one ecosystem that doesn't import web3_utils at all).
        orig_post = mt._post
        try:
            mt._post = lambda url, body: {"jsonrpc": "2.0", "id": 1, "error": {"code": 3, "message": "execution reverted"}}
            with self.assertRaises(mt.HyperEvmReadError):
                mt.evm("eth_call", [{"to": HOLDER_A, "data": "0xa0e67e2b"}, "latest"])
        finally:
            mt._post = orig_post

    def test_evm_raises_hyperevmrpcerror_on_a_genuine_rpc_failure_not_a_revert(self):
        # The case HyperEvmRpcError is narrowed TO since 2026-09-22: an error code that is NOT 3 --
        # e.g. -32005, the conventional "rate limit exceeded" JSON-RPC error code several public
        # providers this project depends on actually use -- is not a revert, and must not be
        # confused for one (a confirmed revert degrades gracefully at the 4 call sites that catch
        # HyperEvmReadError; this must propagate to score_all()'s SKIPPED isolation instead).
        orig_post = mt._post
        try:
            mt._post = lambda url, body: {"jsonrpc": "2.0", "id": 1, "error": {"code": -32005, "message": "call rate limit exhausted"}}
            with self.assertRaises(mt.HyperEvmRpcError):
                mt.evm("eth_call", [{"to": HOLDER_A, "data": "0xa0e67e2b"}, "latest"])
        finally:
            mt._post = orig_post

    def test_evm_still_returns_result_on_success(self):
        orig_post = mt._post
        try:
            mt._post = lambda url, body: {"jsonrpc": "2.0", "id": 1, "result": "0x1234"}
            self.assertEqual(mt.evm("eth_call", [{"to": HOLDER_A, "data": "0x"}, "latest"]), "0x1234")
        finally:
            mt._post = orig_post

    def test_classify_authority_holder_degrades_on_revert_instead_of_crashing(self):
        # Has code (so it's not a bare EOA), but every eth_call reverts --
        # simulating para's real MANAGER_ROLE holder, which delegates to an
        # implementation that simply doesn't implement getOwners().
        # UPDATED 2026-09-22: a confirmed revert now raises HyperEvmReadError, not HyperEvmRpcError
        # (see TestHyperEvmRpcError above) -- this scenario still degrades exactly the same way,
        # only the exception type simulating it changed.
        orig_evm = mt.evm

        def fake_evm(method, params):
            if method == "eth_getCode":
                return "0x60806040527f36"  # has code
            if method == "eth_call":
                raise mt.HyperEvmReadError("execution reverted")
            raise AssertionError(f"unexpected method: {method}")
        mt.evm = fake_evm
        try:
            scores, info_ = mt._classify_authority_holder(HOLDER_A)
            self.assertEqual(scores, (20, 0, 0))
            self.assertEqual(info_["kind"], "unresolved (not a decodable Safe)")
        finally:
            mt.evm = orig_evm

    def test_classify_authority_holder_propagates_a_genuine_rpc_failure_instead_of_degrading(self):
        # ADDED 2026-09-22: the counterpart to the test above -- a genuine RPC-level failure (not a
        # revert) must NOT degrade to (20, 0, 0) the way a confirmed revert does; it must propagate
        # so score_all()'s per-scorer SKIPPED isolation catches it, rather than silently retiring
        # this holder's contribution to its conservative floor under a rate limit.
        orig_evm = mt.evm

        def fake_evm(method, params):
            if method == "eth_getCode":
                return "0x60806040527f36"  # has code
            if method == "eth_call":
                raise mt.HyperEvmRpcError("call rate limit exhausted")
            raise AssertionError(f"unexpected method: {method}")
        mt.evm = fake_evm
        try:
            with self.assertRaises(mt.HyperEvmRpcError):
                mt._classify_authority_holder(HOLDER_A)
        finally:
            mt.evm = orig_evm


class TestNoneMeansRenounced(unittest.TestCase):
    """Regression tests for the gap ported from the same-day Solana Drift
    Protocol correction: an owner()-style slot reading the zero address
    means renounced (the SAFEST state, no one can ever act), not a weak
    bare key -- but ONLY when the caller explicitly says this address came
    from that kind of slot, never for an enumerated role-holder address."""

    def test_zero_address_scores_as_safest_when_flagged(self):
        scores, info_ = mt._classify_authority_holder(mt.ZERO_ADDRESS, none_means_renounced=True)
        self.assertEqual(scores, (100, 100, 100))
        self.assertIn("renounced", info_["kind"])

    def test_zero_address_without_flag_falls_through_to_bare_eoa(self):
        # Without none_means_renounced, the zero address is just another
        # address with no code -- scored as a bare EOA, not specially.
        orig_evm = mt.evm
        mt.evm = lambda method, params: "0x"  # eth_getCode of the zero address: no code
        try:
            scores, info_ = mt._classify_authority_holder(mt.ZERO_ADDRESS)
            self.assertEqual(scores, (10, 0, 0))
            self.assertEqual(info_["kind"], "bare EOA")
        finally:
            mt.evm = orig_evm

    def test_nonzero_address_unaffected_by_the_flag(self):
        orig_evm = mt.evm
        mt.evm = lambda method, params: "0x"  # no code -> bare EOA either way
        try:
            scores, info_ = mt._classify_authority_holder(HOLDER_A, none_means_renounced=True)
            self.assertEqual(scores, (10, 0, 0))
            self.assertEqual(info_["kind"], "bare EOA")
        finally:
            mt.evm = orig_evm


class TestBytesFromHex(unittest.TestCase):
    """Regression tests for the adversarial-review finding: bytes.fromhex()
    raises a bare, uncategorized ValueError on malformed hex, which used
    to slip past every except (HyperEvmReadError, HyperEvmRpcError) clause
    in this file, including inside read_safe_hyperevm itself."""

    def test_valid_hex_decodes_normally(self):
        self.assertEqual(mt._bytes_from_hex("0x0102", "test"), b"\x01\x02")

    def test_odd_length_hex_raises_hyperevmreaderror_not_valueerror(self):
        with self.assertRaises(mt.HyperEvmReadError):
            mt._bytes_from_hex("0x123", "test context")

    def test_non_hex_characters_raise_hyperevmreaderror_not_valueerror(self):
        with self.assertRaises(mt.HyperEvmReadError):
            mt._bytes_from_hex("0x12g4", "test context")

    def test_error_message_names_the_context(self):
        try:
            mt._bytes_from_hex("0x12g4", "proxy delegatorSummary()")
        except mt.HyperEvmReadError as e:
            self.assertIn("proxy delegatorSummary()", str(e))
        else:
            self.fail("expected HyperEvmReadError")


class TestRoleHashLengthValidation(unittest.TestCase):
    """Regression test for the adversarial-review finding: a role hash
    with no length check used to be spliced straight into
    `.rjust(64, "0")`, silently zero-padding a short/empty response into
    bytes32(0) -- this project's own DEFAULT_ADMIN_ROLE sentinel value
    elsewhere -- querying a completely different, unintended role with no
    error at all."""

    def test_raises_on_short_role_hash(self):
        with self.assertRaises(mt.HyperEvmReadError):
            mt.read_role_registry_role_holders(ROLE_REGISTRY, "0x1234")

    def test_raises_on_empty_role_hash(self):
        with self.assertRaises(mt.HyperEvmReadError):
            mt.read_role_registry_role_holders(ROLE_REGISTRY, "0x")

    def test_accepts_a_well_formed_role_hash(self):
        orig_evm = mt.evm
        mt.evm = lambda method, params: _encode_address_array([HOLDER_A])
        try:
            holders = mt.read_role_registry_role_holders(ROLE_REGISTRY, MANAGER_ROLE)
            self.assertEqual(holders, [HOLDER_A])
        finally:
            mt.evm = orig_evm


class TestClassifyAuthorityHolderExposesOwnerAddresses(unittest.TestCase):
    """Regression test for the adversarial-review finding: a Gnosis Safe
    classification used to return only len(safe["owners"]) (a count),
    never the actual owner addresses -- so a cross-exposure check built
    from these info_ dicts could never see an owner nested one level
    inside a Safe."""

    def test_gnosis_safe_branch_exposes_owner_addresses_list(self):
        orig_evm = mt.evm

        def fake_evm(method, params):
            if method == "eth_getCode":
                return "0x6080604052"  # has code -> not a bare EOA
            if method == "eth_call":
                data = params[0]["data"]
                if data.startswith("0xa0e67e2b"):
                    from scripts.lib.tests.test_kinetiq_hyperevm import OWNERS_RESPONSE
                    return OWNERS_RESPONSE
                if data.startswith("0xe75235b8"):
                    from scripts.lib.tests.test_kinetiq_hyperevm import THRESHOLD_RESPONSE
                    return THRESHOLD_RESPONSE
                if data.startswith("0xcc2f8452"):
                    from scripts.lib.tests.test_kinetiq_hyperevm import MODULES_RESPONSE
                    return MODULES_RESPONSE
                raise AssertionError(f"unexpected eth_call data: {data}")
            if method == "eth_getStorageAt":
                from scripts.lib.tests.test_kinetiq_hyperevm import GUARD_RESPONSE
                return GUARD_RESPONSE
            raise AssertionError(f"unexpected method: {method}")
        mt.evm = fake_evm
        try:
            scores, info_ = mt._classify_authority_holder("0x18a82c968b992d28d4d812920eb7b4305306f8f1")
            self.assertEqual(info_["kind"], "Gnosis Safe")
            self.assertIn("ownerAddresses", info_)
            self.assertEqual(len(info_["ownerAddresses"]), info_["owners"])
            self.assertIn("0x806e5f088a12a86bf1984378a824c224d29c7503", info_["ownerAddresses"])
        finally:
            mt.evm = orig_evm

    def test_bare_eoa_and_unresolved_have_no_owner_addresses_key(self):
        orig_evm = mt.evm
        mt.evm = lambda method, params: "0x"  # no code -> bare EOA
        try:
            _, info_ = mt._classify_authority_holder(HOLDER_A)
            self.assertNotIn("ownerAddresses", info_)
        finally:
            mt.evm = orig_evm


if __name__ == "__main__":
    unittest.main()
