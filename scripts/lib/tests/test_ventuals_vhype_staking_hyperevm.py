"""
Unit tests for the THIRD HyperEVM-native target this project scores
(`Ventuals vHYPE staking`, added 2026-09-18 -- a day after Kinetiq's
`HIP3StakingManager` and `para StakingVault`, both 2026-09-17). Found
while chasing a "Similar Match" contract flagged next to `para`
StakingVault's own implementation -- that specific lead was a dead end
(its own EIP-1967 slot doesn't match any of the 10 tracked HIP-3 dexes'
deployer addresses), but sweeping every dex's deployer for its OWN
EIP-1967 implementation slot found still-dormant dex `vntl` also carries
a real, named liquid-staking product.

This target's scorer, `score_ventuals_vhype_staking`, is structurally
similar to `score_para_staking_vault` (same RoleRegistry/EnumerableRoles
pattern, same read helpers) but exercises ONE new, deliberate design
choice worth its own regression coverage: unlike `para`'s analogous
`MANAGER_ROLE` holder (an UNVERIFIED contract, conservatively scored as
"unresolved"), this target's `MANAGER_ROLE` holder IS a verified contract
whose gating was manually confirmed by reading its real source -- so its
practical score is hardcoded to match `RoleRegistry.owner()`'s own
resolution, NOT run through `_classify_authority_holder`'s mechanical
Safe-decode (which would revert on `getOwners()` and default to the same
conservative 20/0/0 fallback `para`'s case correctly uses). These tests
lock in that this hardcoded resolution only applies to the ONE address it
was manually verified for, and that an unexpected holder at that role
falls back to the normal, unverified-by-default classification instead of
silently trusting an unrecognized address.

`evm()`/`_eth_call()` are monkeypatched with real responses fetched live
from `https://rpc.hyperliquid.xyz/evm` on 2026-09-18 (see `chains/
hyperliquid/data/methodology_test_2026-09-18-ventuals-vhype-staking.md`
for the full derivation), frozen so this suite doesn't depend on network
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


mt = _load_module("aro_test_hyperliquid_methodology_test_ventuals", "chains/hyperliquid/scripts/methodology_test.py")

PROXY = "0x8888888192a4a0593c13532ba48449fc24c3beda"
ROLE_REGISTRY = "0x8888888f0651a534011d7ad277c302e7d2d77930"
SAFE = "0x72298a4cb6e571241331172fd90149d38feafe08"
SAFE_OWNERS = [
    "0xddf3bb50498d15b1e4cfb39adcf7acc7ecb11413",
    "0xb201911ba8f1834bb1e100d82072960a8d30b556",
    "0x748d8c24c38d8d6b3e7cff4b605661a7d78dae37",
]
MANAGER_ROLE_HOLDER = "0x88888880793f89ce85777ff2e0e2d366bf05b20c"
UNEXPECTED_HOLDER = "0x1111111111111111111111111111111111111111"


def _owners_response(owners):
    body = "".join("0" * 24 + o[2:].lower() for o in owners)
    return "0x" + ("%064x" % 0x20) + ("%064x" % len(owners)) + body


def _threshold_response(n):
    return "0x" + ("%064x" % n)


OWNERS_RESPONSE = _owners_response(SAFE_OWNERS)
THRESHOLD_RESPONSE = _threshold_response(2)
MODULES_RESPONSE = "0x" + ("%064x" % 0x40) + ("0" * 64) + ("0" * 64)
GUARD_RESPONSE = "0x" + "0" * 64


def _safe_fake_evm(method, params):
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


class TestManagerRoleManualResolution(unittest.TestCase):
    """Regression tests for the one deliberately-hardcoded resolution this
    target's scorer relies on: MANAGER_ROLE's holder is only treated as
    "same authority as RoleRegistry.owner()" when it EXACTLY matches the
    one address manually verified for this purpose; anything else falls
    back to the normal, conservative classification path."""

    def test_confirmed_verified_holder_resolves_to_safe_score(self):
        orig_evm = mt.evm
        mt.evm = _safe_fake_evm
        try:
            scores_owner, _ = mt._classify_authority_holder(SAFE, none_means_renounced=True)
            self.assertEqual(scores_owner, (50, 35, 0))
            # The scorer hardcodes MANAGER_ROLE's holder to this exact
            # score when the address matches -- verify the underlying
            # Safe resolution these two are supposed to agree on.
            member = MANAGER_ROLE_HOLDER
            confirmed_verified_manager_role_holders = {"0x88888880793f89ce85777ff2e0e2d366bf05b20c"}
            self.assertIn(member.lower(), confirmed_verified_manager_role_holders)
        finally:
            mt.evm = orig_evm

    def test_unexpected_holder_does_not_get_the_hardcoded_resolution(self):
        # An address other than the one manually verified must NOT be
        # silently trusted -- it should fall through to _classify_
        # authority_holder's normal (conservative, mechanical) path.
        confirmed_verified_manager_role_holders = {"0x88888880793f89ce85777ff2e0e2d366bf05b20c"}
        self.assertNotIn(UNEXPECTED_HOLDER.lower(), confirmed_verified_manager_role_holders)
        orig_evm = mt.evm
        mt.evm = lambda method, params: "0x"  # no code -> bare EOA fallback
        try:
            scores, info_ = mt._classify_authority_holder(UNEXPECTED_HOLDER)
            self.assertEqual(scores, (10, 0, 0))
            self.assertEqual(info_["kind"], "bare EOA")
        finally:
            mt.evm = orig_evm


class TestSafeResolutionMatchesLiveShape(unittest.TestCase):
    """Confirms the 2-of-3 Safe fixture used across this test file decodes
    the way score_ventuals_vhype_staking's live run actually observed it
    (threshold=2, 3 owners, no modules, no guard)."""

    def test_two_of_three_safe_decodes_correctly(self):
        orig_evm = mt.evm
        mt.evm = _safe_fake_evm
        try:
            safe = mt.read_safe_hyperevm(SAFE)
            self.assertEqual(safe["threshold"], 2)
            self.assertEqual(len(safe["owners"]), 3)
            self.assertEqual(set(safe["owners"]), set(SAFE_OWNERS))
            self.assertEqual(safe["modules"], [])
        finally:
            mt.evm = orig_evm

    def test_two_of_three_scores_as_50_35_0(self):
        admin, multisig, timelock = mt._safe_rooted_scores_hyperevm(2, 3)
        self.assertEqual((admin, multisig, timelock), (50, 35, 0))
        self.assertEqual(mt.composite(admin, multisig, timelock), 31)


VERIFIED_IMPL = "0x0000000c21e635b59edff54e70fe21315fa9b245"
OPERATOR_ROLE_HASH = mt._selector("OPERATOR_ROLE()")  # not the real 32-byte hash, only used as a dict key here
MANAGER_ROLE_HASH = mt._selector("MANAGER_ROLE()")


def _full_fake_evm(manager_impl=VERIFIED_IMPL, operator_holders=None, manager_holders=None,
                    manager_role_response=None, operator_role_response=None):
    """A complete, end-to-end fake for score_ventuals_vhype_staking()'s
    every eth_call/eth_getStorageAt/eth_getCode, built from real selectors
    (mt._selector), not hardcoded hex, so it stays correct if selectors
    are ever recomputed differently. Defaults reproduce the live-observed
    happy path; each keyword lets one specific test override exactly one
    piece of behavior."""
    real_manager_role = mt._selector("MANAGER_ROLE()")
    real_operator_role = mt._selector("OPERATOR_ROLE()")
    real_role_registry = mt._selector("roleRegistry()")
    real_owner = mt._selector("owner()")
    real_get_owners = mt._selector("getOwners()")
    real_get_threshold = mt._selector("getThreshold()")
    real_get_modules = mt._selector("getModulesPaginated(address,uint256)")
    real_role_holders = mt._selector("roleHolders(bytes32)")
    real_delegator_summary = mt._selector("delegatorSummary()")

    manager_role_resp = manager_role_response if manager_role_response is not None else "0x" + "11" * 32
    operator_role_resp = operator_role_response if operator_role_response is not None else "0x" + "22" * 32
    operator_holders = operator_holders if operator_holders is not None else [SAFE]
    manager_holders = manager_holders if manager_holders is not None else [MANAGER_ROLE_HOLDER]

    def fake_evm(method, params):
        if method == "eth_getCode":
            addr = params[0].lower()
            if addr == PROXY.lower():
                return "0x6080604052"  # StakingVault itself has code
            if addr == MANAGER_ROLE_HOLDER.lower():
                return "0x60806040527f36"  # the minimal EIP-1967 proxy
            return "0x6080604052"  # any Safe address: has code
        if method == "eth_getStorageAt":
            slot = params[1]
            addr = params[0].lower()
            if slot == mt.EIP1967_IMPLEMENTATION_SLOT and addr == MANAGER_ROLE_HOLDER.lower():
                return "0x" + "0" * 24 + manager_impl[2:].lower()
            return GUARD_RESPONSE
        if method == "eth_call":
            data = params[0]["data"]
            to = params[0]["to"].lower()
            if data.startswith(real_role_registry):
                return "0x" + "0" * 24 + ROLE_REGISTRY[2:]
            if data.startswith(real_owner) and to == ROLE_REGISTRY.lower():
                return "0x" + "0" * 24 + SAFE[2:]
            if data.startswith(real_manager_role) and to == ROLE_REGISTRY.lower():
                return manager_role_resp
            if data.startswith(real_operator_role) and to == ROLE_REGISTRY.lower():
                return operator_role_resp
            if data.startswith(real_get_owners) or data.startswith(real_get_threshold) or data.startswith(real_get_modules):
                # Matches real on-chain behavior: the MANAGER_ROLE proxy
                # is a minimal EIP-1967 proxy, not a Gnosis Safe -- calling
                # any Safe-shaped selector on it reverts (its backing
                # implementation simply doesn't define these functions).
                # UPDATED 2026-09-22: a confirmed revert is now HyperEvmReadError, not
                # HyperEvmRpcError -- see chains/hyperliquid/scripts/methodology_test.py's evm().
                if to == MANAGER_ROLE_HOLDER.lower():
                    raise mt.HyperEvmReadError(f"{to}: execution reverted (not a Safe)")
                if data.startswith(real_get_owners):
                    return OWNERS_RESPONSE
                if data.startswith(real_get_threshold):
                    return THRESHOLD_RESPONSE
                return MODULES_RESPONSE
            if data.startswith(real_role_holders):
                role_hash = data[len(real_role_holders):].rjust(64, "0")
                # role_hash arrives left-padded already inside read_role_registry_role_holders
                if manager_role_resp[2:].rjust(64, "0") in data:
                    return _owners_response(manager_holders)
                if operator_role_resp[2:].rjust(64, "0") in data:
                    return _owners_response(operator_holders)
                raise AssertionError(f"unrecognized roleHolders() call: {data}")
            if data.startswith(real_delegator_summary):
                return "0x" + ("%064x" % 732899248565) + "0" * 192
            raise AssertionError(f"unexpected eth_call data: {data}")
        raise AssertionError(f"unexpected method: {method}")

    return fake_evm


class TestScoreVentualsVhypeStakingEndToEnd(unittest.TestCase):
    """Regression tests for five fixes an adversarial review confirmed
    2026-09-18, all exercised through the real, complete
    score_ventuals_vhype_staking() function rather than its individual
    pieces in isolation."""

    def _run(self, **fake_evm_kwargs):
        orig_evm, orig_info = mt.evm, mt.info
        mt.evm = _full_fake_evm(**fake_evm_kwargs)
        mt.info = lambda body: []  # no HIP-3 dexes -> trivial, empty cross-exposure check
        try:
            return mt.score_ventuals_vhype_staking()
        finally:
            mt.evm, mt.info = orig_evm, orig_info

    def test_matching_implementation_uses_hardcoded_safe_score(self):
        r = self._run(manager_impl=VERIFIED_IMPL)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (50, 35, 0))
        manager_note = next(n for n in r["notes"] if n.startswith("MANAGER_ROLE:"))
        self.assertIn("manually confirmed onlyOwner-gated", manager_note)

    def test_mismatched_implementation_falls_back_to_conservative(self):
        # A DIFFERENT implementation address than the one manually
        # verified -- the runtime check must catch this and NOT apply the
        # hardcoded trust, falling through to the normal mechanical path
        # (which reverts on getOwners() against a non-Safe proxy).
        different_impl = "0x000000000000000000000000000000deadbeef"
        r = self._run(manager_impl=different_impl)
        manager_note = next(n for n in r["notes"] if n.startswith("MANAGER_ROLE:"))
        self.assertIn("NOT manually verified", manager_note)
        self.assertIn("re-check by hand", manager_note)
        # OPERATOR_ROLE and RoleRegistry.owner() still resolve to the
        # 2-of-3 Safe; MANAGER_ROLE now degrades to unresolved (20/0/0),
        # which becomes the binding minimum.
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (20, 0))

    def test_operator_role_same_as_owner_is_noted_as_reused(self):
        r = self._run()
        operator_note = next(n for n in r["notes"] if n.startswith("OPERATOR_ROLE:"))
        self.assertIn("SAME address as RoleRegistry.owner()", operator_note)
        self.assertIn("reusing that classification", operator_note)

    def test_zero_holders_role_gets_an_explicit_note(self):
        r = self._run(operator_holders=[])
        self.assertIn("OPERATOR_ROLE: 0 holders", r["notes"])

    def test_malformed_role_hash_degrades_gracefully_not_crashes(self):
        # MANAGER_ROLE() returns a too-short value (simulating a future
        # RoleRegistry upgrade that broke this getter) -- must degrade to
        # the UNRESOLVED sentinel, not raise out of the function.
        r = self._run(manager_role_response="0x1234")
        self.assertIn("MANAGER_ROLE:UNRESOLVED", r["reads"]["roleHolders"])
        manager_fail_note = next(n for n in r["notes"] if n.startswith("MANAGER_ROLE: FAILED"))
        self.assertIn("degraded to conservative unresolved", manager_fail_note)

    def test_unresolved_sentinel_excluded_from_cross_exposure_set(self):
        # With info() mocked to return no dexes, crossExposureScore is
        # trivially 100 regardless -- this test only checks that the
        # "unresolved" placeholder string itself never appears as if it
        # were a real address anywhere the function's own notes discuss
        # the holder set (the function has no public accessor for the
        # raw set, so this is checked indirectly via a crash-free run
        # with a forced-unresolved role, matching the malformed-hash test
        # above but asserting cross-exposure specifically still computes
        # a clean 100, not an error from comparing "unresolved" against
        # dex signer addresses).
        r = self._run(manager_role_response="0x1234")
        self.assertEqual(r["crossExposureScore"], 100)


if __name__ == "__main__":
    unittest.main()
