"""
Unit tests for chains/ethereum-l1/scorers.py's scoring-decision logic --
previously ZERO coverage, closing the 2026-09-18 test-coverage audit's
next-ranked gap after Zcash, Base-ecosystem, and Arbitrum-ecosystem.

`_apply_cross_exposure`'s within-L1 `_rootGroup` grouping is NOT re-tested
here -- it already has dedicated coverage in test_cross_ecosystem_fixes.py's
TestEthereumL1ApplyCrossExposure. This file covers the 7 SIMPLE_SCORERS
functions' own admin_key/multisig/timelock_score branch logic instead.
ADDED 2026-09-20: it also covers the cross-ecosystem fold (the internal
`_crossEcosystem` flag that score_aave_v3_pool() and score_morpho_blue_l1()
set and that `_apply_cross_exposure` turns into crossExposureScore = 80).

Same FakeHelpers/FakeW3 monkeypatch approach as
test_base_ecosystem_scorers.py / test_arbitrum_ecosystem_scorers.py, adapted
to this file's specific primitive surface: it imports ONLY `call_raw`,
`cross_checked`, `safe_owners_and_threshold`, `safe_score` from
web3_utils.py (no `read_address_getter`, no `read_slot_as_address`, no
`is_eoa` -- every address-returning getter here routes through `call_raw`
with an `_ADDR_GETTER(name)` ABI fragment instead). `cross_checked` is new
in this file (score_aave_v3_pool's PROTOCOL_GUARDIAN emergency-admin check,
the only call site of it in this project so far) -- faked here by simply
invoking the wrapped fn once against a FakeW3, since the fake call_raw it
delegates to doesn't care which w3 instance it's handed; a separate
`cross_checked_raises` hook lets a test exercise the `except RuntimeError`
branch that real disagreement across RPCs would hit.

Every 4-byte function selector this file hardcodes (setPeer, setDelegate,
the 3 disableX selectors, the 2 setAssetXCustodian selectors) is
independently recomputed here via `Web3.keccak(text=...)[:4]` rather than
copy-pasted from scorers.py, matching this project's "never trust a
hand-typed hex value" discipline applied to the tests themselves.
"""
import importlib.util
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    mod_dir = os.path.dirname(file_path)
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
scorers = _load_module("aro_test_ethereum_l1_scorers", "chains/ethereum-l1/scorers.py")


class FakeHelpers:
    def __init__(self):
        self.call_raw_results = {}   # (address, function_name, args-tuple) -> value-or-None
        self.safe_results = {}       # address -> (owners, threshold) or None
        self.cross_checked_raises = None  # set to an Exception instance to force the except branch
        # ADDED 2026-09-22 for score_aave_v3_horizon_pool()'s live role-holder replay (get_w3 +
        # _replay_role_holders, see chains/ethereum-l1/scorers.py). Default behaviour (both left
        # None/unset) is "the live replay exactly matches the known/disclosed holder sets" -- the
        # quiet, nothing-new outcome -- so every EXISTING test in test_aave_horizon_scorer.py that
        # predates this feature and never configures either of these keeps its old, unaffected
        # result without having to know this replay happens at all.
        self.replay_role_holders_result = None  # dict {role_name: set(addr)} or None (see get_w3 default below)
        self.replay_role_holders_raises = None  # set to an Exception instance to force the except branch

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def cross_checked(self, rpc_urls, fn, *args):
        if self.cross_checked_raises is not None:
            raise self.cross_checked_raises
        return fn(FakeW3(), *args)

    def get_w3(self, rpc_url):
        return FakeW3()  # never dereferenced directly -- only ever handed straight to the also-faked _replay_role_holders below

    def _replay_role_holders(self, w3, contract_address, role_names, start_block):
        if self.replay_role_holders_raises is not None:
            raise self.replay_role_holders_raises
        if self.replay_role_holders_result is not None:
            return self.replay_role_holders_result
        return {
            "POOL_ADMIN": set(scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN),
            "EMERGENCY_ADMIN": set(scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN),
            "RISK_ADMIN": set(scorers._HORIZON_KNOWN_RISK_ADMIN),
            "ASSET_LISTING_ADMIN": set(scorers._HORIZON_KNOWN_ASSET_LISTING_ADMIN),
        }


def _patch_helpers(test_case, fake):
    names = ["call_raw", "safe_owners_and_threshold", "cross_checked", "get_w3", "_replay_role_holders"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


class FakeW3:
    """score_uniswap_v3_factory calls w3.eth.get_code(...)/w3.to_checksum_address(...)
    directly (the one scorer in this file that does, to confirm the fee
    adapter isn't a bare EOA) -- get_code's return isn't used in any scoring
    branch (informational note only), so any non-empty bytes value works.
    Several other scorers call w3.to_checksum_address(...) inline before
    passing an address as a call_raw *arg (hasRole/isWhitelisted callers) --
    delegated to the real implementation so those checksums are genuine."""
    guard_slot_value = bytes(12) + bytes.fromhex("74abe7805541c28f31953b3cDA9711Dc96278D29")

    class eth:
        @staticmethod
        def get_code(addr):
            return b"\x60\x80\x60\x40"

        @staticmethod
        def get_storage_at(addr, slot):
            return FakeW3.guard_slot_value

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


def _owners(n, start=1):
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


ADAPTER = RealWeb3.to_checksum_address("0x" + "a1" * 20)
TIMELOCK_UNI = RealWeb3.to_checksum_address("0x" + "71" * 20)
GOVERNOR = RealWeb3.to_checksum_address("0x" + "60" * 20)
UNI_TOKEN = "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"

EXECUTOR = RealWeb3.to_checksum_address("0x" + "e1" * 20)
PAYLOADS_CONTROLLER = RealWeb3.to_checksum_address("0x" + "cc" * 20)
ACL_MANAGER = "0xc2aaCf6553D20d1e9d78E365AAba8032af9c85b0"
PROTOCOL_GUARDIAN = "0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30"
PROVIDER = "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"

PAUSE = "0xbE286431454714F511008713973d3B053A2d38f3"
DSCHIEF = RealWeb3.to_checksum_address("0x" + "d5" * 20)
HAT = RealWeb3.to_checksum_address("0x" + "17" * 20)

MINTING = "0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3"
ETHENA_SAFE = "0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862"
ETHENA_SAFE_CHECKSUM = RealWeb3.to_checksum_address(ETHENA_SAFE)
STAKED = "0x9D39A5DE30e57443BfF2A8307A4256c8797A3497"
DEFAULT_ADMIN_ROLE = b"\x00" * 32

USDTB_TARGET = "0xC139190F447e929f090Edeb554D95AbB8b18aC1c"
USDTB_ADMIN_EOA = "0xd93826BB299765c87D13AeBa2A7E5d9B27A03956"
USDTB_ADMIN_EOA_CHECKSUM = RealWeb3.to_checksum_address(USDTB_ADMIN_EOA)
USDTB_PROXY_ADMIN = "0x3C405F68d5C6eCE868e5646cAC926679839aCd68"

USDTB_PSM = "0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728"
USDTB_PSM_CHECKSUM = RealWeb3.to_checksum_address(USDTB_PSM)
ETHENA_TIMELOCK = "0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94"

DISABLE_SWAP_SEL = RealWeb3.keccak(text="disableSwap()")[:4]
DISABLE_COLLATERAL_SEL = RealWeb3.keccak(text="disableCollateral(address)")[:4]
DISABLE_BENEFACTOR_SEL = RealWeb3.keccak(text="disableBenefactor(address)")[:4]
SET_SEND_CUSTODIAN_SEL = RealWeb3.keccak(text="setAssetSendCustodian(address)")[:4]
SET_RECEIVE_CUSTODIAN_SEL = RealWeb3.keccak(text="setAssetReceiveCustodian(address)")[:4]
SET_PEER_SEL = RealWeb3.keccak(text="setPeer(uint32,bytes32)")[:4]
SET_DELEGATE_SEL = RealWeb3.keccak(text="setDelegate(address)")[:4]

# Sanity check: these must match the literal hex scorers.py hardcodes, since
# every test below relies on this independent recomputation to produce the
# exact same dispatch keys the real code calls call_raw() with.
assert DISABLE_SWAP_SEL == bytes.fromhex("fd5b9026")
assert DISABLE_COLLATERAL_SEL == bytes.fromhex("75c038b7")
assert DISABLE_BENEFACTOR_SEL == bytes.fromhex("9c621790")
assert SET_SEND_CUSTODIAN_SEL == bytes.fromhex("28cb6982")
assert SET_RECEIVE_CUSTODIAN_SEL == bytes.fromhex("cd0b89ca")
assert SET_PEER_SEL == bytes.fromhex("3400288b")
assert SET_DELEGATE_SEL == bytes.fromhex("ca5eb5e1")

OFT_ADAPTERS = [
    ("USDe OFTAdapter (LayerZero)", "0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34"),
    ("sUSDe OFTAdapter (LayerZero)", "0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2"),
    ("ENA OFTAdapter (LayerZero)", "0x58538E6A46E07434d7E7375BC268D3cB839C0133"),
]


# --------------------------------------------------------------------- _composite
class TestComposite(unittest.TestCase):
    def test_weights_and_round_half_up(self):
        self.assertEqual(scorers._composite(80, 100, 75), 85)

    def test_half_boundary_rounds_up(self):
        self.assertEqual(scorers._composite(0, 0, 5), 2)  # 0.3*5+0.5=2.0 -> floor 2


# --------------------------------------------------------------------- Uniswap V3 Factory
class TestScoreUniswapV3Factory(unittest.TestCase):
    FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

    def _base_fake(self):
        fake = FakeHelpers()
        fake.call_raw_results[(self.FACTORY, "owner", ())] = ADAPTER
        fake.call_raw_results[(ADAPTER, "owner", ())] = TIMELOCK_UNI
        return fake

    def test_all_resolve_confirmed_dao(self):
        fake = self._base_fake()
        fake.call_raw_results[(TIMELOCK_UNI, "delay", ())] = 172800
        fake.call_raw_results[(TIMELOCK_UNI, "admin", ())] = GOVERNOR
        fake.call_raw_results[(GOVERNOR, "quorumVotes", ())] = 40_000_000 * 10**18
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 80)
        self.assertEqual(result["timelockScore"], 75)
        self.assertEqual(result["multisigScore"], 100)
        self.assertEqual(result["compositeScore"], 85)
        self.assertEqual(result["_rootGroup"], "uniswap-l1-governance")

    def test_confirmed_real_timelock_claims_the_cross_ecosystem_shared_root(self):
        # 2026-09-20: the Uniswap L1 Timelock roots tracked targets on 4 other ecosystems. Claimed only when this run
        # read the REAL Timelock address and a live GovernorBravo quorum behind it.
        tl = scorers.UNISWAP_TIMELOCK
        fake = FakeHelpers()
        fake.call_raw_results[(self.FACTORY, "owner", ())] = ADAPTER
        fake.call_raw_results[(ADAPTER, "owner", ())] = tl
        fake.call_raw_results[(tl, "delay", ())] = 172800
        fake.call_raw_results[(tl, "admin", ())] = GOVERNOR
        fake.call_raw_results[(GOVERNOR, "quorumVotes", ())] = 40_000_000 * 10**18
        _patch_helpers(self, fake)
        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertIs(result["_crossEcosystem"], True)
        self.assertIn(scorers._UNISWAP_SHARED_ROOT_NOTE, result["notes"])

    def test_a_look_alike_timelock_or_unread_quorum_does_not_claim_it(self):
        fake = self._base_fake()  # TIMELOCK_UNI is a placeholder address, not the real Timelock
        fake.call_raw_results[(TIMELOCK_UNI, "delay", ())] = 172800
        fake.call_raw_results[(TIMELOCK_UNI, "admin", ())] = GOVERNOR
        fake.call_raw_results[(GOVERNOR, "quorumVotes", ())] = 40_000_000 * 10**18
        _patch_helpers(self, fake)
        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertIs(result["_crossEcosystem"], False)
        self.assertNotIn(scorers._UNISWAP_SHARED_ROOT_NOTE, result["notes"])

    def test_quorum_unresolved_degrades_admin_key_only(self):
        fake = self._base_fake()
        fake.call_raw_results[(TIMELOCK_UNI, "delay", ())] = 172800
        fake.call_raw_results[(TIMELOCK_UNI, "admin", ())] = GOVERNOR
        # quorumVotes() deliberately absent from the dispatch table -> None
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 20)
        self.assertEqual(result["timelockScore"], 75)  # delay still resolved -- independent branches
        self.assertTrue(any("quorumVotes() unread" in n for n in result["notes"]))

    def test_delay_unresolved_degrades_timelock_only(self):
        fake = self._base_fake()
        fake.call_raw_results[(TIMELOCK_UNI, "admin", ())] = GOVERNOR
        fake.call_raw_results[(GOVERNOR, "quorumVotes", ())] = 40_000_000 * 10**18
        # delay() deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 80)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("Timelock.delay() unread" in n for n in result["notes"]))

    def test_proposal_count_none_skips_proposals_loop_without_crashing(self):
        # proposalCount() unresolved -> the `if proposal_count:` guard must
        # skip the per-proposal call_raw loop entirely rather than calling
        # call_raw(..., "proposals", pid) with no dispatch entry and crashing
        # on an unexpected key lookup.
        fake = self._base_fake()
        fake.call_raw_results[(TIMELOCK_UNI, "delay", ())] = 172800
        fake.call_raw_results[(TIMELOCK_UNI, "admin", ())] = GOVERNOR
        fake.call_raw_results[(GOVERNOR, "quorumVotes", ())] = 40_000_000 * 10**18
        # proposalCount() absent -> None -> falsy
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual(result["compositeScore"], 85)  # unaffected -- disclosed-only data


# --------------------------------------------------------------------- Aave V3 Pool
class TestScoreAaveV3Pool(unittest.TestCase):
    def _base_fake(self):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(EXECUTOR, "owner", ())] = PAYLOADS_CONTROLLER
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (EXECUTOR,))] = False
        return fake

    def test_all_resolve_confirmed_guardian_safe(self):
        fake = self._base_fake()
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = EXECUTOR
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (PROTOCOL_GUARDIAN,))] = True
        fake.safe_results[PROTOCOL_GUARDIAN] = (_owners(7), 4)
        _patch_helpers(self, fake)

        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertEqual(result["adminKeyScore"], 78)
        self.assertEqual(result["timelockScore"], 55)
        self.assertEqual(result["multisigScore"], 100)
        self.assertEqual(result["_rootGroup"], "aave-l1-governance")

    def test_settings_unresolved_degrades_timelock_only(self):
        fake = self._base_fake()
        # getExecutorSettingsByAccessControl(1) absent -> None
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = EXECUTOR
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (PROTOCOL_GUARDIAN,))] = True
        fake.safe_results[PROTOCOL_GUARDIAN] = (_owners(7), 4)
        _patch_helpers(self, fake)

        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertEqual(result["timelockScore"], 0)
        self.assertEqual(result["adminKeyScore"], 78)  # independent branch, unaffected

    def test_cross_rpc_disagreement_degrades_admin_key(self):
        # This scorer's only cross_checked() call site in the whole project --
        # simulate the two RPCs disagreeing (the real helper raises
        # RuntimeError on any mismatch) and confirm the except branch
        # degrades adminKeyScore instead of propagating the exception.
        fake = self._base_fake()
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = EXECUTOR
        fake.safe_results[PROTOCOL_GUARDIAN] = (_owners(7), 4)
        fake.cross_checked_raises = RuntimeError("RPC disagreement for isEmergencyAdmin")
        _patch_helpers(self, fake)

        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertEqual(result["adminKeyScore"], 20)
        self.assertTrue(any("cross-RPC check FAILED" in n for n in result["notes"]))

    def test_guardian_threshold_unresolved_degrades_admin_key_despite_true_flag(self):
        # is_emergency_admin_guardian True but the Safe's owners/threshold
        # never resolved -- adminKeyScore must still degrade (both halves of
        # the `and` are required, not just the boolean flag).
        fake = self._base_fake()
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = EXECUTOR
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (PROTOCOL_GUARDIAN,))] = True
        # safe_results[PROTOCOL_GUARDIAN] deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertEqual(result["adminKeyScore"], 20)


class TestAaveV3PayloadsGuardianCommitteeNote(unittest.TestCase):
    """PayloadsController.guardian() used to be only logged, never resolved; it is a
    5-of-9 Safe whose owners are identical to the Aave guardian committee on
    Arbitrum/Base/Plasma/Monad. The scorer annotates that in its notes and, since
    2026-09-20, also flags it for the crossExposureScore fold (see
    TestAaveV3CrossEcosystemFold); adminKey/multisig/timelock never move."""
    GUARDIAN_SAFE = "0xCe52ab41C40575B072A18C9700091Ccbe4A06710"

    def _fake(self, guardian_safe_result):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(EXECUTOR, "owner", ())] = PAYLOADS_CONTROLLER
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (EXECUTOR,))] = False
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = self.GUARDIAN_SAFE
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (PROTOCOL_GUARDIAN,))] = True
        fake.safe_results[PROTOCOL_GUARDIAN] = (_owners(7), 4)
        if guardian_safe_result is not None:
            fake.safe_results[self.GUARDIAN_SAFE] = guardian_safe_result
        return fake

    def test_identical_committee_is_noted_and_no_score_moves(self):
        known = sorted(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        _patch_helpers(self, self._fake((known, 5)))
        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertTrue(any("IDENTICAL to the Aave guardian committee" in n for n in result["notes"]))
        self.assertTrue(any("5-of-9" in n for n in result["notes"]))
        # the three composite inputs are exactly what they were before this note existed
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (78, 100, 55))

    def test_case_differences_in_owner_addresses_still_match(self):
        from web3 import Web3 as _Web3
        checksummed = [_Web3.to_checksum_address(o) for o in scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17]
        _patch_helpers(self, self._fake((checksummed, 5)))
        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertTrue(any("IDENTICAL to the Aave guardian committee" in n for n in result["notes"]))

    def test_different_committee_is_not_flagged(self):
        _patch_helpers(self, self._fake((_owners(9), 5)))
        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertFalse(any("IDENTICAL" in n for n in result["notes"]))
        self.assertTrue(any("5-of-9" in n for n in result["notes"]))

    def test_one_owner_changed_is_not_identical(self):
        owners = sorted(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        owners[0] = "0x" + "ab" * 20
        _patch_helpers(self, self._fake((owners, 5)))
        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertFalse(any("IDENTICAL" in n for n in result["notes"]))

    def test_unresolved_guardian_safe_notes_skip_and_does_not_crash(self):
        _patch_helpers(self, self._fake(None))
        result = scorers.score_aave_v3_pool(FakeW3())
        self.assertTrue(any("committee comparison skipped" in n for n in result["notes"]))
        self.assertEqual(result["adminKeyScore"], 78)


# --------------------------------------------------------------------- Aave V3 cross-ecosystem fold
class TestAaveV3CrossEcosystemFold(unittest.TestCase):
    """ADDED 2026-09-20: crossExposureScore now folds cross-ecosystem overlaps.
    score_aave_v3_pool() sets the internal `_crossEcosystem` flag when EITHER
    PayloadsController.guardian()'s Safe owners == the 9-signer committee (a)
    OR PROTOCOL_GUARDIAN's Safe owners == the 7-signer committee (b)."""
    GUARDIAN_SAFE = "0xCe52ab41C40575B072A18C9700091Ccbe4A06710"

    def _fake(self, payloads_guardian_safe, protocol_guardian_safe):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(EXECUTOR, "owner", ())] = PAYLOADS_CONTROLLER
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (EXECUTOR,))] = False
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = self.GUARDIAN_SAFE
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (PROTOCOL_GUARDIAN,))] = True
        if payloads_guardian_safe is not None:
            fake.safe_results[self.GUARDIAN_SAFE] = payloads_guardian_safe
        if protocol_guardian_safe is not None:
            fake.safe_results[PROTOCOL_GUARDIAN] = protocol_guardian_safe
        return fake

    def _run(self, payloads_guardian_safe, protocol_guardian_safe):
        _patch_helpers(self, self._fake(payloads_guardian_safe, protocol_guardian_safe))
        return scorers.score_aave_v3_pool(FakeW3())

    def _final(self, result):
        results = [result]
        scorers._apply_cross_exposure(results)
        return results[0]

    KNOWN_9 = sorted(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
    KNOWN_7 = sorted(scorers._KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20)

    def test_protocol_guardian_snapshot_is_seven_lowercase_addresses_disjoint_from_the_nine(self):
        self.assertEqual(len(self.KNOWN_7), 7)
        self.assertTrue(all(a == a.lower() and a.startswith("0x") and len(a) == 42 for a in self.KNOWN_7))
        self.assertTrue(scorers._KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20.isdisjoint(
            scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17))

    def test_branch_a_payloads_guardian_committee_match_folds_to_80(self):
        result = self._run((self.KNOWN_9, 5), (_owners(7), 4))
        self.assertIs(result["_crossEcosystem"], True)
        final = self._final(result)
        self.assertEqual(final["crossExposureScore"], 80)
        self.assertTrue(any("real finding" in n and "crossExposureScore 80" in n for n in final["notes"]))
        self.assertTrue(any("same 9 signers" in n and "folded into crossExposureScore" in n for n in final["notes"]))
        self.assertFalse(any("not folded" in n for n in final["notes"]))

    def test_branch_a_alone_does_not_emit_the_protocol_guardian_note(self):
        result = self._run((self.KNOWN_9, 5), (_owners(7), 4))
        self.assertFalse(any("PROTOCOL_GUARDIAN owner set is IDENTICAL" in n for n in result["notes"]))

    def test_branch_b_protocol_guardian_committee_match_folds_to_80(self):
        result = self._run((_owners(9), 5), (self.KNOWN_7, 4))
        self.assertIs(result["_crossEcosystem"], True)
        final = self._final(result)
        self.assertEqual(final["crossExposureScore"], 80)
        self.assertTrue(any("PROTOCOL_GUARDIAN owner set is IDENTICAL" in n and "same 7 signers" in n for n in final["notes"]))
        self.assertFalse(any("IDENTICAL to the Aave guardian committee" in n for n in final["notes"]))

    def test_branch_b_checksummed_owner_addresses_still_match(self):
        checksummed = [RealWeb3.to_checksum_address(o) for o in self.KNOWN_7]
        result = self._run((_owners(9), 5), (checksummed, 4))
        self.assertIs(result["_crossEcosystem"], True)

    def test_both_branches_match_is_still_a_single_flat_80(self):
        result = self._run((self.KNOWN_9, 5), (self.KNOWN_7, 4))
        self.assertIs(result["_crossEcosystem"], True)
        self.assertEqual(self._final(result)["crossExposureScore"], 80)

    def test_no_match_on_either_seat_stays_100(self):
        result = self._run((_owners(9), 5), (_owners(7), 4))
        self.assertIs(result["_crossEcosystem"], False)
        final = self._final(result)
        self.assertEqual(final["crossExposureScore"], 100)
        self.assertFalse(any("real finding" in n for n in final["notes"]))

    def test_branch_b_one_owner_changed_is_not_identical(self):
        owners = list(self.KNOWN_7)
        owners[0] = "0x" + "ab" * 20
        result = self._run((_owners(9), 5), (owners, 4))
        self.assertIs(result["_crossEcosystem"], False)
        self.assertEqual(self._final(result)["crossExposureScore"], 100)

    def test_branch_b_subset_of_the_seven_is_not_identical(self):
        result = self._run((_owners(9), 5), (self.KNOWN_7[:6], 4))
        self.assertIs(result["_crossEcosystem"], False)

    def test_branch_b_safe_unread_degrades_without_a_match(self):
        result = self._run((_owners(9), 5), None)
        self.assertIs(result["_crossEcosystem"], False)
        self.assertEqual(result["adminKeyScore"], 20)  # existing conservative degrade, unchanged
        self.assertEqual(self._final(result)["crossExposureScore"], 100)

    def test_branch_a_unread_does_not_stop_branch_b(self):
        result = self._run(None, (self.KNOWN_7, 4))
        self.assertIs(result["_crossEcosystem"], True)
        self.assertEqual(self._final(result)["crossExposureScore"], 80)

    def test_fold_never_changes_the_composite_inputs(self):
        matched = self._run((self.KNOWN_9, 5), (self.KNOWN_7, 4))
        _patch_helpers(self, self._fake((_owners(9), 5), (_owners(7), 4)))
        plain = scorers.score_aave_v3_pool(FakeW3())
        for k in ("adminKeyScore", "multisigScore", "timelockScore", "compositeScore"):
            self.assertEqual(matched[k], plain[k], k)
        self.assertEqual((matched["adminKeyScore"], matched["multisigScore"], matched["timelockScore"]), (78, 100, 55))


# --------------------------------------------------------------------- Morpho Blue L1 cross-ecosystem fold
class TestMorphoBlueL1CrossEcosystemFold(unittest.TestCase):
    MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
    MORPHO_SAFE = RealWeb3.to_checksum_address("0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa")

    def _run(self, safe_result):
        fake = FakeHelpers()
        fake.call_raw_results[(self.MORPHO, "owner", ())] = self.MORPHO_SAFE
        if safe_result is not None:
            fake.safe_results[self.MORPHO_SAFE] = safe_result
        _patch_helpers(self, fake)
        return scorers.score_morpho_blue_l1(FakeW3())

    def _final(self, result):
        results = [result]
        scorers._apply_cross_exposure(results)
        return results[0]

    def test_identical_committee_folds_to_80(self):
        result = self._run((sorted(scorers._KNOWN_MORPHO_COMMITTEE_2026_09_19), 5))
        self.assertIs(result["_crossEcosystem"], True)
        final = self._final(result)
        self.assertEqual(final["crossExposureScore"], 80)
        self.assertTrue(any("IDENTICAL" in n and "folded into crossExposureScore" in n for n in final["notes"]))
        self.assertTrue(any("real finding" in n for n in final["notes"]))
        self.assertFalse(any("not folded" in n for n in final["notes"]))

    def test_fold_leaves_the_composite_inputs_at_their_pre_existing_values(self):
        final = self._final(self._run((sorted(scorers._KNOWN_MORPHO_COMMITTEE_2026_09_19), 5)))
        self.assertEqual((final["adminKeyScore"], final["multisigScore"], final["timelockScore"], final["compositeScore"]), (65, 95, 0, 55))

    def test_lowercase_owner_addresses_still_match(self):
        owners = [o.lower() for o in scorers._KNOWN_MORPHO_COMMITTEE_2026_09_19]
        result = self._run((owners, 5))
        self.assertIs(result["_crossEcosystem"], True)

    def test_different_committee_stays_100(self):
        result = self._run((_owners(9), 5))
        self.assertIs(result["_crossEcosystem"], False)
        final = self._final(result)
        self.assertEqual(final["crossExposureScore"], 100)
        self.assertFalse(any("IDENTICAL" in n for n in final["notes"]))

    def test_one_owner_changed_stays_100(self):
        owners = sorted(scorers._KNOWN_MORPHO_COMMITTEE_2026_09_19)
        owners[0] = RealWeb3.to_checksum_address("0x" + "ab" * 20)
        result = self._run((owners, 5))
        self.assertIs(result["_crossEcosystem"], False)
        self.assertEqual(self._final(result)["crossExposureScore"], 100)

    def test_owner_not_a_safe_degrades_and_does_not_fold(self):
        result = self._run(None)
        self.assertIs(result["_crossEcosystem"], False)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))
        self.assertEqual(self._final(result)["crossExposureScore"], 100)


# --------------------------------------------------------------------- _apply_cross_exposure cross-ecosystem fold
class TestApplyCrossExposureCrossEcosystemFold(unittest.TestCase):
    """ADDED 2026-09-20. The within-L1 `_rootGroup` ladder itself is covered in
    test_cross_ecosystem_fixes.py; this covers only what the `_crossEcosystem`
    flag adds on top of it."""

    def _entry(self, label, group, cross=None):
        e = {"label": label, "compositeScore": 50, "notes": [], "_rootGroup": group}
        if cross is not None:
            e["_crossEcosystem"] = cross
        return e

    def test_identical_committee_flag_gives_80_and_a_real_finding_note(self):
        results = [self._entry("A", "solo-a", cross=True)]
        scorers._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 80)
        self.assertTrue(any("real finding" in n and "80" in n for n in results[0]["notes"]))

    def test_no_flag_key_at_all_stays_100(self):
        results = [self._entry("A", "solo-a")]
        scorers._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 100)
        self.assertFalse(any("real finding" in n for n in results[0]["notes"]))

    def test_flag_false_stays_100_and_is_still_stripped(self):
        results = [self._entry("A", "solo-a", cross=False)]
        scorers._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 100)
        self.assertNotIn("_crossEcosystem", results[0])

    def test_lower_within_l1_value_is_not_raised(self):
        # 5 targets in one root group -> within-L1 20; the flag must NOT raise it to 80
        results = [self._entry(f"T{i}", "shared", cross=(i == 0)) for i in range(5)]
        scorers._apply_cross_exposure(results)
        for r in results:
            self.assertEqual(r["crossExposureScore"], 20)
        self.assertTrue(any("stays 20" in n for n in results[0]["notes"]))
        self.assertFalse(any("real finding" in n for n in results[1]["notes"]))

    def test_flag_on_a_two_way_group_is_already_80_and_stays_80(self):
        results = [self._entry("A", "shared", cross=True), self._entry("B", "shared")]
        scorers._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 80)
        self.assertEqual(results[1]["crossExposureScore"], 80)

    def test_flag_only_moves_the_flagged_target(self):
        results = [self._entry("A", "solo-a", cross=True), self._entry("B", "solo-b")]
        scorers._apply_cross_exposure(results)
        self.assertEqual([r["crossExposureScore"] for r in results], [80, 100])

    def test_internal_keys_do_not_leak(self):
        results = [self._entry("A", "solo-a", cross=True), self._entry("B", "solo-b", cross=False), self._entry("C", "solo-c")]
        scorers._apply_cross_exposure(results)
        for r in results:
            self.assertNotIn("_crossEcosystem", r)
            self.assertNotIn("_rootGroup", r)
            self.assertEqual([k for k in r if k.startswith("_")], [])

    def test_score_all_returns_80_for_aave_and_morpho_and_leaks_no_internal_key(self):
        from unittest import mock
        fake = FakeHelpers()
        guardian_safe = "0xCe52ab41C40575B072A18C9700091Ccbe4A06710"
        morpho = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
        morpho_safe = RealWeb3.to_checksum_address("0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa")
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(EXECUTOR, "owner", ())] = PAYLOADS_CONTROLLER
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (EXECUTOR,))] = False
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = guardian_safe
        fake.call_raw_results[(ACL_MANAGER, "isEmergencyAdmin", (PROTOCOL_GUARDIAN,))] = True
        fake.safe_results[guardian_safe] = (_owners(9), 5)
        fake.safe_results[PROTOCOL_GUARDIAN] = (sorted(scorers._KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20), 4)
        fake.call_raw_results[(morpho, "owner", ())] = morpho_safe
        fake.safe_results[morpho_safe] = (sorted(scorers._KNOWN_MORPHO_COMMITTEE_2026_09_19), 5)
        _patch_helpers(self, fake)
        with mock.patch.object(scorers, "SIMPLE_SCORERS", [scorers.score_aave_v3_pool, scorers.score_morpho_blue_l1]):
            results = scorers.score_all(FakeW3())
        self.assertEqual([r["crossExposureScore"] for r in results], [80, 80])
        for r in results:
            self.assertEqual([k for k in r if k.startswith("_")], [])


# --------------------------------------------------------------------- MakerDAO / Sky Pause
class TestScoreMakerdaoSkyPause(unittest.TestCase):
    def test_all_resolve_confirmed(self):
        fake = FakeHelpers()
        fake.call_raw_results[(PAUSE, "delay", ())] = 172800
        fake.call_raw_results[(PAUSE, "authority", ())] = DSCHIEF
        fake.call_raw_results[(DSCHIEF, "hat", ())] = HAT
        fake.call_raw_results[(HAT, "done", ())] = True
        _patch_helpers(self, fake)

        result = scorers.score_makerdao_sky_pause(FakeW3())
        self.assertEqual(result["adminKeyScore"], 75)
        self.assertEqual(result["timelockScore"], 70)
        self.assertEqual(result["_rootGroup"], "makerdao-sky-governance")

    def test_done_false_still_counts_as_resolved_not_degraded(self):
        # done()=False means the most recent spell hasn't executed yet -- a
        # fact about governance activity, not an unresolved read. The gate is
        # `done is not None`, not truthiness -- confirm False doesn't
        # accidentally trip the degrade branch the way None should.
        fake = FakeHelpers()
        fake.call_raw_results[(PAUSE, "delay", ())] = 172800
        fake.call_raw_results[(PAUSE, "authority", ())] = DSCHIEF
        fake.call_raw_results[(DSCHIEF, "hat", ())] = HAT
        fake.call_raw_results[(HAT, "done", ())] = False
        _patch_helpers(self, fake)

        result = scorers.score_makerdao_sky_pause(FakeW3())
        self.assertEqual(result["adminKeyScore"], 75)

    def test_hat_unresolved_degrades_admin_key(self):
        fake = FakeHelpers()
        fake.call_raw_results[(PAUSE, "delay", ())] = 172800
        fake.call_raw_results[(PAUSE, "authority", ())] = DSCHIEF
        # hat() absent -> None -> done() is never meaningfully reached (HAT is None,
        # so call_raw_results.get((None, "done", ())) also misses -> None too)
        _patch_helpers(self, fake)

        result = scorers.score_makerdao_sky_pause(FakeW3())
        self.assertEqual(result["adminKeyScore"], 20)
        self.assertEqual(result["timelockScore"], 70)  # independent branch, unaffected


# --------------------------------------------------------------------- Ethena EthenaMinting
class TestScoreEthenaMinting(unittest.TestCase):
    """REWRITTEN 2026-09-20: score_ethena_minting() now scores the LIVE minter
    (USDe.minter()), not the retired 0x2CC440b7... it scored before. Every selector and
    role hash below is recomputed here with keccak from its signature, and cross-checked
    against the hex values the independent authority map listed."""

    LIVE = "0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3"
    RETIRED = "0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3"
    USDE = "0x4c9EDD5852cd905f086C759E8383e09bff1E68B3"
    TL = "0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94"
    SAFE_CS = ETHENA_SAFE_CHECKSUM
    REDIRECT = (
        "grantRole(bytes32,address)", "transferAdmin(address)", "addCustodianAddress(address)",
        "addSupportedAsset(address,(uint8,bool,uint128,uint128))", "setTokenType(address,uint8)",
        "setStablesDeltaLimit(uint128)",
    )
    INSTANT = ("revokeRole(bytes32,address)", "addWhitelistedBenefactor(address)", "removeWhitelistedBenefactor(address)")
    GATED = ("disableMintRedeem()", "removeMinterRole(address)", "removeRedeemerRole(address)", "removeCollateralManagerRole(address)")

    @staticmethod
    def _sel(sig):
        return RealWeb3.keccak(text=sig)[:4]

    @staticmethod
    def _role(name):
        return bytes(RealWeb3.keccak(text=name))

    def _fake(self, owners=10, threshold=5):
        f = FakeHelpers()
        cs = RealWeb3.to_checksum_address
        f.call_raw_results[(self.USDE, "minter", ())] = self.LIVE
        f.call_raw_results[(self.USDE, "owner", ())] = self.TL
        f.call_raw_results[(self.LIVE, "hasRole", (DEFAULT_ADMIN_ROLE, cs(self.TL)))] = True
        f.call_raw_results[(self.LIVE, "hasRole", (DEFAULT_ADMIN_ROLE, self.SAFE_CS))] = False
        f.call_raw_results[(self.TL, "getMinDelay", ())] = 86400
        f.call_raw_results[(self.TL, "hasRole", (self._role("PROPOSER_ROLE"), self.SAFE_CS))] = True
        f.safe_results[ETHENA_SAFE] = (_owners(owners), threshold)
        for sig in self.REDIRECT:
            f.call_raw_results[(self.TL, "isWhitelisted", (cs(self.LIVE), self._sel(sig)))] = False
        f.call_raw_results[(self.TL, "isWhitelisted", (cs(self.USDE), self._sel("setMinter(address)")))] = False
        for sig in self.INSTANT + self.GATED:
            f.call_raw_results[(self.TL, "isWhitelisted", (cs(self.LIVE), self._sel(sig)))] = True
        f.call_raw_results[(self.LIVE, "hasRole", (self._role("GATEKEEPER_ROLE"), cs(self.TL)))] = False
        f.call_raw_results[(self.LIVE, "hasRole", (self._role("COLLATERAL_MANAGER_ROLE"), self.SAFE_CS))] = True
        for g in scorers._ETHENA_GATEKEEPERS:
            f.call_raw_results[(self.LIVE, "hasRole", (self._role("GATEKEEPER_ROLE"), cs(g)))] = True
        return f

    def _run(self, fake):
        _patch_helpers(self, fake)
        return scorers.score_ethena_minting(FakeW3())

    def test_target_is_the_live_minter_not_the_retired_contract(self):
        result = self._run(self._fake())
        self.assertEqual(result["target"], self.LIVE)
        self.assertNotEqual(result["target"].lower(), self.RETIRED.lower())
        self.assertEqual(result["_rootGroup"], "ethena-safe-0x3b0aaf6e")

    def test_clean_case_safe_plus_24h_timelock_matches_the_psm_convention(self):
        result = self._run(self._fake())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (65, 100, 55))
        self.assertEqual(result["compositeScore"], 73)

    def test_multisig_formula_uncapped_case_matches_hand_derivation(self):
        # 2-of-3 -> 2*15 + 1*5 = 35: proves the formula is applied, not pinned at the cap.
        result = self._run(self._fake(owners=3, threshold=2))
        self.assertEqual(result["multisigScore"], 35)

    def test_any_redirect_class_selector_being_whitelisted_drops_admin_and_timelock(self):
        cs = RealWeb3.to_checksum_address
        for sig in self.REDIRECT:
            with self.subTest(sig=sig):
                f = self._fake()
                f.call_raw_results[(self.TL, "isWhitelisted", (cs(self.LIVE), self._sel(sig)))] = True
                result = self._run(f)
                self.assertEqual((result["adminKeyScore"], result["timelockScore"]), (30, 0))

    def test_usde_setminter_whitelisted_drops_admin_and_timelock(self):
        f = self._fake()
        f.call_raw_results[(self.TL, "isWhitelisted", (RealWeb3.to_checksum_address(self.USDE), self._sel("setMinter(address)")))] = True
        result = self._run(f)
        self.assertEqual((result["adminKeyScore"], result["timelockScore"]), (30, 0))

    def test_usde_not_owned_by_the_timelock_drops_admin_and_timelock(self):
        f = self._fake()
        f.call_raw_results[(self.USDE, "owner", ())] = self.SAFE_CS
        result = self._run(f)
        self.assertEqual((result["adminKeyScore"], result["timelockScore"]), (30, 0))

    def test_instant_lanes_and_dead_gatekeeper_entries_are_disclosed_not_scored(self):
        result = self._run(self._fake())
        text = " ".join(result["notes"])
        for sig in self.INSTANT:
            self.assertIn(sig, text)
        self.assertIn("DEAD", text)
        self.assertIn("COLLATERAL_MANAGER_ROLE", text)
        self.assertIn("4 of 4 known bare-EOA GATEKEEPER_ROLE holders", text)
        self.assertEqual(result["timelockScore"], 55)  # the disclosures do not move the number

    def test_gatekeeper_entries_not_called_dead_when_the_timelock_role_read_fails(self):
        f = self._fake()
        del f.call_raw_results[(self.LIVE, "hasRole", (self._role("GATEKEEPER_ROLE"), RealWeb3.to_checksum_address(self.TL)))]
        text = " ".join(self._run(f)["notes"])
        self.assertIn("NOT proven dead", text)

    def test_safe_guard_is_read_from_the_guard_slot_and_disclosed(self):
        text = " ".join(self._run(self._fake())["notes"])
        self.assertIn("EthenaSafeGuard", text)
        self.assertIn("Matches: True", text)

    def test_a_different_or_unreadable_guard_never_moves_the_score(self):
        original = FakeW3.guard_slot_value
        self.addCleanup(lambda: setattr(FakeW3, "guard_slot_value", original))
        FakeW3.guard_slot_value = bytes(32)  # guard removed (zero address)
        result = self._run(self._fake())
        self.assertIn("Matches: False", " ".join(result["notes"]))
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (65, 100, 55))

    def test_guard_slot_constant_is_the_safe_guard_manager_slot(self):
        self.assertEqual(scorers._SAFE_GUARD_SLOT, "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8")

    def test_note_says_the_old_contract_is_retired(self):
        text = " ".join(self._run(self._fake())["notes"])
        self.assertIn(self.RETIRED, text)
        self.assertIn("RETIRED TARGET", text)

    def test_usde_minter_repointed_elsewhere_degrades(self):
        f = self._fake()
        f.call_raw_results[(self.USDE, "minter", ())] = self.RETIRED
        result = self._run(f)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("NO LONGER this contract" in n for n in result["notes"]))

    def test_each_unread_guard_degrades_to_20_20_0(self):
        cs = RealWeb3.to_checksum_address
        keys = {
            "usde.minter": (self.USDE, "minter", ()),
            "usde.owner": (self.USDE, "owner", ()),
            "timelock admin": (self.LIVE, "hasRole", (DEFAULT_ADMIN_ROLE, cs(self.TL))),
            "delay": (self.TL, "getMinDelay", ()),
            "proposer": (self.TL, "hasRole", (self._role("PROPOSER_ROLE"), self.SAFE_CS)),
            "redirect read": (self.TL, "isWhitelisted", (cs(self.LIVE), self._sel(self.REDIRECT[2]))),
            "setMinter read": (self.TL, "isWhitelisted", (cs(self.USDE), self._sel("setMinter(address)"))),
        }
        for label, key in keys.items():
            with self.subTest(unread=label):
                f = self._fake()
                del f.call_raw_results[key]
                result = self._run(f)
                self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))

    def test_safe_unread_degrades(self):
        f = self._fake()
        f.safe_results[ETHENA_SAFE] = None
        result = self._run(f)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))

    def test_safe_not_the_timelock_proposer_degrades_instead_of_scoring_the_wrong_root(self):
        f = self._fake()
        f.call_raw_results[(self.TL, "hasRole", (self._role("PROPOSER_ROLE"), self.SAFE_CS))] = False
        result = self._run(f)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))

    def test_safe_as_direct_admin_again_reverts_to_the_no_delay_shape(self):
        f = self._fake()
        f.call_raw_results[(self.LIVE, "hasRole", (DEFAULT_ADMIN_ROLE, RealWeb3.to_checksum_address(self.TL)))] = False
        f.call_raw_results[(self.LIVE, "hasRole", (DEFAULT_ADMIN_ROLE, self.SAFE_CS))] = True
        result = self._run(f)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (55, 100, 0))

    def test_zero_delay_gives_no_timelock_credit(self):
        f = self._fake()
        f.call_raw_results[(self.TL, "getMinDelay", ())] = 0
        result = self._run(f)
        self.assertEqual(result["timelockScore"], 0)

    def test_constants_and_selectors_match_the_independently_listed_values(self):
        self.assertEqual(scorers._ETHENA_MINTING, self.LIVE)
        self.assertEqual(scorers._ETHENA_MINTING_RETIRED, self.RETIRED)
        self.assertEqual(scorers._USDE, self.USDE)
        self.assertEqual(scorers._ETHENA_TIMELOCK, self.TL)
        # hex values as listed by the 2026-09-20 authority map, a second derivation of the same selectors
        listed = {
            "grantRole(bytes32,address)": "2f2ff15d", "transferAdmin(address)": "75829def", "addCustodianAddress(address)": "4be7a64b",
            "addSupportedAsset(address,(uint8,bool,uint128,uint128))": "7cfbc42f", "setTokenType(address,uint8)": "dfcf8528",
            "setStablesDeltaLimit(uint128)": "af4eca35", "setMinter(address)": "fca3b5aa", "revokeRole(bytes32,address)": "d547741f",
            "addWhitelistedBenefactor(address)": "16255c43", "removeWhitelistedBenefactor(address)": "8db940e0",
            "disableMintRedeem()": "c5ff38bd", "removeMinterRole(address)": "54f1e126", "removeRedeemerRole(address)": "532c3f82",
            "removeCollateralManagerRole(address)": "7274c25c",
        }
        for sig, hexval in listed.items():
            self.assertEqual(scorers._selector(sig).hex(), hexval, sig)
        self.assertEqual(scorers._selector_role("GATEKEEPER_ROLE").hex(), "3c63e605be3290ab6b04cfc46c6e1516e626d43236b034f09d7ede1d017beb0c")
        self.assertEqual(scorers._selector_role("PROPOSER_ROLE").hex(), "b09aa5aeb3702cfd50b6b62bc4532604938f21248a27a1d5ca736082b6819cc1")
        self.assertEqual(tuple(scorers._ETHENA_REDIRECT_SIGNATURES), self.REDIRECT)


# --------------------------------------------------------------------- USDtb
class TestScoreUsdtb(unittest.TestCase):
    def test_all_resolve_confirmed_bare_eoa(self):
        fake = FakeHelpers()
        fake.call_raw_results[(USDTB_TARGET, "hasRole", (DEFAULT_ADMIN_ROLE, USDTB_ADMIN_EOA_CHECKSUM))] = True
        fake.call_raw_results[(USDTB_PROXY_ADMIN, "owner", ())] = USDTB_ADMIN_EOA
        _patch_helpers(self, fake)

        result = scorers.score_usdtb(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertEqual(result["multisigScore"], 0)
        self.assertEqual(result["timelockScore"], 0)
        self.assertEqual(result["_rootGroup"], "usdtb-bare-eoa-0xd93826bb")

    def test_proxy_admin_owner_case_difference_still_matches(self):
        # proxy_admin_matches compares via .lower() -- confirm a
        # differently-cased return value for the same address still counts
        # as a match rather than falsely degrading on a case mismatch.
        fake = FakeHelpers()
        fake.call_raw_results[(USDTB_TARGET, "hasRole", (DEFAULT_ADMIN_ROLE, USDTB_ADMIN_EOA_CHECKSUM))] = True
        fake.call_raw_results[(USDTB_PROXY_ADMIN, "owner", ())] = USDTB_ADMIN_EOA.upper().replace("0X", "0x")
        _patch_helpers(self, fake)

        result = scorers.score_usdtb(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)

    def test_proxy_admin_owner_genuine_mismatch_degrades(self):
        fake = FakeHelpers()
        fake.call_raw_results[(USDTB_TARGET, "hasRole", (DEFAULT_ADMIN_ROLE, USDTB_ADMIN_EOA_CHECKSUM))] = True
        fake.call_raw_results[(USDTB_PROXY_ADMIN, "owner", ())] = RealWeb3.to_checksum_address("0x" + "99" * 20)
        _patch_helpers(self, fake)

        result = scorers.score_usdtb(FakeW3())
        self.assertEqual(result["adminKeyScore"], 20)

    def test_proxy_admin_owner_unresolved_degrades(self):
        fake = FakeHelpers()
        fake.call_raw_results[(USDTB_TARGET, "hasRole", (DEFAULT_ADMIN_ROLE, USDTB_ADMIN_EOA_CHECKSUM))] = True
        # proxy_admin.owner() absent -> None -> bool(None) is False
        _patch_helpers(self, fake)

        result = scorers.score_usdtb(FakeW3())
        self.assertEqual(result["adminKeyScore"], 20)


# --------------------------------------------------------------------- USDtb PSM
class TestScoreUsdtbPsm(unittest.TestCase):
    def _base_fake(self, disable_results=(True, True, True), custodian_results=(False, False)):
        fake = FakeHelpers()
        fake.call_raw_results[(ETHENA_TIMELOCK, "getMinDelay", ())] = 86400
        fake.safe_results[ETHENA_SAFE] = (_owners(10), 5)
        for sel, val in zip((DISABLE_SWAP_SEL, DISABLE_COLLATERAL_SEL, DISABLE_BENEFACTOR_SEL), disable_results):
            fake.call_raw_results[(ETHENA_TIMELOCK, "isWhitelisted", (USDTB_PSM_CHECKSUM, sel))] = val
        for sel, val in zip((SET_SEND_CUSTODIAN_SEL, SET_RECEIVE_CUSTODIAN_SEL), custodian_results):
            fake.call_raw_results[(ETHENA_TIMELOCK, "isWhitelisted", (USDTB_PSM_CHECKSUM, sel))] = val
        return fake

    def test_clean_case_freeze_bypassed_custodian_delayed(self):
        fake = self._base_fake()
        _patch_helpers(self, fake)

        result = scorers.score_usdtb_psm(FakeW3())
        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["timelockScore"], 55)
        self.assertEqual(result["multisigScore"], 100)  # 5-of-10 -> 5*15+5*5=100
        self.assertEqual(result["_rootGroup"], "ethena-safe-0x3b0aaf6e")

    def test_custodian_selector_whitelisted_degrades_despite_resolved_calls(self):
        # The economically-critical fund-redirect path becoming bypassable
        # (unexpectedly whitelisted) must drop both adminKeyScore and
        # timelockScore, even though every call still resolved cleanly --
        # this is the scenario the docstring calls "genuinely nuanced," not
        # an unresolved-read case.
        fake = self._base_fake(custodian_results=(True, False))
        _patch_helpers(self, fake)

        result = scorers.score_usdtb_psm(FakeW3())
        self.assertEqual(result["adminKeyScore"], 30)
        self.assertEqual(result["timelockScore"], 0)

    def test_scoring_depends_only_on_custodian_delay_not_freeze_bypass(self):
        # freeze_bypass_confirmed (the disable_selectors outcome) feeds a
        # note but does NOT gate admin_key/timelock_score in the actual code
        # -- only custodian_genuinely_delayed does. Confirm that stays true:
        # even with the freeze path NOT bypassed as expected, scores are
        # unaffected as long as calls_resolved and custodian delay hold.
        fake = self._base_fake(disable_results=(False, False, False))
        _patch_helpers(self, fake)

        result = scorers.score_usdtb_psm(FakeW3())
        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["timelockScore"], 55)

    def test_delay_unresolved_degrades_all_three_scores(self):
        fake = self._base_fake()
        del fake.call_raw_results[(ETHENA_TIMELOCK, "getMinDelay", ())]
        _patch_helpers(self, fake)

        result = scorers.score_usdtb_psm(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))


# --------------------------------------------------------------------- Ethena LayerZero OFTAdapters
class TestScoreEthenaLayerzeroOft(unittest.TestCase):
    def _register_adapter(self, fake, adapter, owner=ETHENA_TIMELOCK, endpoint="0x1a44076050125825900e736c501f859c50fE728c",
                           peer_bypassed=True, delegate_delayed=False):
        checksummed = RealWeb3.to_checksum_address(adapter)
        fake.call_raw_results[(adapter, "owner", ())] = owner
        fake.call_raw_results[(adapter, "endpoint", ())] = endpoint
        fake.call_raw_results[(ETHENA_TIMELOCK, "isWhitelisted", (checksummed, SET_PEER_SEL))] = peer_bypassed
        fake.call_raw_results[(ETHENA_TIMELOCK, "isWhitelisted", (checksummed, SET_DELEGATE_SEL))] = delegate_delayed

    def test_returns_a_list_of_three_all_confirmed(self):
        fake = FakeHelpers()
        for _, addr in OFT_ADAPTERS:
            self._register_adapter(fake, addr)
        _patch_helpers(self, fake)

        results = scorers.score_ethena_layerzero_oft(FakeW3())
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r["adminKeyScore"], 55)
            self.assertEqual(r["multisigScore"], 100)
            self.assertEqual(r["timelockScore"], 15)
            self.assertEqual(r["_rootGroup"], "ethena-safe-0x3b0aaf6e")
        self.assertEqual({r["target"] for r in results}, {addr for _, addr in OFT_ADAPTERS})

    def test_owner_mismatch_degrades_that_adapter_only(self):
        fake = FakeHelpers()
        label0, addr0 = OFT_ADAPTERS[0]
        self._register_adapter(fake, addr0, owner=RealWeb3.to_checksum_address("0x" + "99" * 20))
        for _, addr in OFT_ADAPTERS[1:]:
            self._register_adapter(fake, addr)
        _patch_helpers(self, fake)

        results = scorers.score_ethena_layerzero_oft(FakeW3())
        mismatched = next(r for r in results if r["target"] == addr0)
        others = [r for r in results if r["target"] != addr0]
        self.assertEqual((mismatched["adminKeyScore"], mismatched["multisigScore"], mismatched["timelockScore"]), (20, 20, 0))
        for r in others:
            self.assertEqual(r["timelockScore"], 15)

    def test_delegate_not_genuinely_delayed_zeroes_timelock_but_keeps_admin_key(self):
        fake = FakeHelpers()
        label0, addr0 = OFT_ADAPTERS[0]
        self._register_adapter(fake, addr0, delegate_delayed=True)  # unexpectedly whitelisted -> not genuinely delayed
        for _, addr in OFT_ADAPTERS[1:]:
            self._register_adapter(fake, addr)
        _patch_helpers(self, fake)

        results = scorers.score_ethena_layerzero_oft(FakeW3())
        affected = next(r for r in results if r["target"] == addr0)
        self.assertEqual(affected["adminKeyScore"], 55)  # owner_matches still holds
        self.assertEqual(affected["timelockScore"], 0)

    def test_exception_on_one_adapter_is_isolated_regression(self):
        # Regression test for the FIXED 2026-09-17 bug documented right above
        # this loop's try/except: one adapter raising used to propagate out
        # of the WHOLE function, dropping all 3 targets, not just the bad
        # one. Force a raise for exactly one adapter's call_raw and confirm
        # the other two still score normally.
        fake = FakeHelpers()
        label0, addr0 = OFT_ADAPTERS[0]
        for _, addr in OFT_ADAPTERS[1:]:
            self._register_adapter(fake, addr)

        original_call_raw = fake.call_raw

        def call_raw_raising_for_addr0(w3, address, abi_fragment, function_name, *args, retries=4):
            if address == addr0:
                raise ConnectionError("simulated transient RPC failure surviving all retries")
            return original_call_raw(w3, address, abi_fragment, function_name, *args, retries=retries)

        fake.call_raw = call_raw_raising_for_addr0
        _patch_helpers(self, fake)

        results = scorers.score_ethena_layerzero_oft(FakeW3())
        self.assertEqual(len(results), 3)  # all 3 targets still present, none dropped
        failed = next(r for r in results if r["target"] == addr0)
        healthy = [r for r in results if r["target"] != addr0]
        self.assertEqual((failed["adminKeyScore"], failed["multisigScore"], failed["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("raised" in n for n in failed["notes"]))
        for r in healthy:
            self.assertEqual(r["timelockScore"], 15)


# --------------------------------------------------------------------- SIMPLE_SCORERS sanity
class TestSimpleScorersList(unittest.TestCase):
    # UPDATED 2026-09-19: 7 -> 12 entries (5 targets added by the ethereum-l1
    # maintenance run; their own branch tests live in
    # chains/ethereum-l1/tests/test_new_targets_2026_09_19.py).
    # UPDATED 2026-09-20 (later): 16 -> 17 entries (score_aave_v3_horizon_pool, appended last; its own tests live in
    # scripts/lib/tests/test_aave_horizon_scorer.py).
    # UPDATED 2026-09-20: 12 -> 16 entries (Lido stETH, EigenLayer
    # StrategyManager, Curve Stableswap-NG factory, Rocket Pool RocketStorage;
    # branch tests in chains/ethereum-l1/tests/test_new_targets_2026_09_20.py).
    # UPDATED 2026-09-25: 17 -> 18 entries (score_convex_finance_booster, appended last; its own tests
    # live in chains/ethereum-l1/tests/test_new_targets_2026_09_25.py).
    # This guard is deliberately an exact count AND an exact name set: it is the
    # one shared-file line an ecosystem worker has to touch when it adds a
    # target, which is exactly what makes an accidental addition visible.
    def test_eighteen_entries_matching_module_functions(self):
        self.assertEqual(len(scorers.SIMPLE_SCORERS), 18)
        names = {fn.__name__ for fn in scorers.SIMPLE_SCORERS}
        self.assertEqual(names, {
            "score_uniswap_v3_factory", "score_aave_v3_pool", "score_makerdao_sky_pause",
            "score_ethena_minting", "score_usdtb", "score_usdtb_psm", "score_ethena_layerzero_oft",
            "score_compound_v3_cusdc", "score_sparklend_pool", "score_uniswap_v4_pool_manager",
            "score_morpho_blue_l1", "score_wbtc",
            "score_lido_steth", "score_eigenlayer_strategy_manager",
            "score_curve_stableswap_ng_factory", "score_rocketpool_storage",
            "score_aave_v3_horizon_pool", "score_convex_finance_booster",
        })


if __name__ == "__main__":
    unittest.main()
