"""
Unit tests for "batch A -- simple + safe-rooted family" of `scripts/lib/scorers.py`
(Robinhood Chain rotation-audit, 2026-09-18): score_curve_dex, score_ramses_clv2,
score_ekubo_core, score_chainlink_admin_safe, score_pancakeswap_v2_factory (all
standalone), plus the shared `_safe_rooted_scores` / `_safe_guard_and_modules` /
`_safe_rooted_entry` helper family and its four thin-wrapper callers
(score_pancakeswap_v3_factory, score_sushiswap_v3_factory,
score_symbiosis_portal, score_strato_bridge_router).

Same FakeHelpers/FakeW3 approach as test_robinhood_uniswap_family_scorers.py.
New wrinkle specific to this batch: score_ramses_clv2() calls
`_replay_role_holders()`, a plain module-level function DEFINED in scorers.py
itself (not imported from web3_utils, unlike every other faked name) that
does its own live `chain_w3.eth.get_logs`/`chain_w3.eth.block_number` calls.
It is faked the same way as the imported read-primitives -- monkeypatched on
the `scorers` module by name -- rather than given a real get_logs-capable
FakeW3, since it is itself just another read-primitive boundary from this
file's point of view (its own internal log-replay correctness is exercised
by whichever test file covers score_rollup_l1_authority(), not here).

Real-code finding worth flagging up front (see this file's final summary,
not fixed here per this project's own review-discipline split): every read
score_ramses_clv2() performs (team-Safe threshold, min delay, role-holder
sets) feeds ONLY the `notes` list -- `admin_key, multisig, timelock = 15, 5, 0`
is a hardcoded literal completely independent of any of those reads. That
contradicts this file's own module docstring ("re-derives the same facts
from the live chain instead of replaying hardcoded numbers"). Tests below
assert the code AS WRITTEN (constant score regardless of what resolves),
not the behavior the module docstring implies it should have.
"""
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

# scripts/lib/scorers.py uses a package-relative import (`from .web3_utils
# import ...`), unlike the per-ecosystem chains/*/scorers.py files -- it
# can't be loaded standalone via importlib.util.spec_from_file_location the
# way those are. Match test_scorers.py's own already-working approach
# instead: put `scripts` on sys.path so `lib` resolves as a real package.
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib import scorers  # noqa: E402


class FakeEth:
    def __init__(self, code_sizes=None):
        self._code_sizes = code_sizes or {}

    def get_code(self, addr):
        return b"\x00" * self._code_sizes.get(addr, 100)


class FakeW3:
    def __init__(self, code_sizes=None):
        self.eth = FakeEth(code_sizes)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}      # (address, function_name) -> address-or-None
        self.call_raw_results = {}     # (address, function_name, args-tuple) -> value-or-None
        self.slot_results = {}         # (address, slot) -> address-or-None
        self.safe_results = {}         # address -> (owners, threshold) or None
        self.eoa_results = {}          # address -> bool, default True
        self.l1_w3 = FakeW3()          # get_w3()'s return value
        self.role_holder_results = {}  # (contract_address, role_names-key, start_block) -> {role: set(...)}-or-None
        self.modules = {}              # safe address -> list of module addresses, default [] (ADDED 2026-09-21)
        self.guards = {}               # safe address -> guard address, default the zero address
        self.singletons = {}           # safe address -> singleton address

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def is_eoa(self, w3, address):
        return self.eoa_results.get(address, True)

    def get_w3(self, rpc_url):
        return self.l1_w3

    def _replay_role_holders(self, chain_w3, contract_address, role_names, start_block):
        key = (contract_address, role_names if isinstance(role_names, str) else tuple(role_names), start_block)
        return self.role_holder_results.get(key)

    def _read_safe_modules(self, w3, address, retries=4):
        return self.modules.get(address, [])

    def _read_safe_guard_addr(self, w3, address, retries=4):
        return self.guards.get(address, "0x" + "0" * 40)

    def _read_safe_singleton(self, w3, address, retries=4):
        return self.singletons.get(address, "0x41675C099F32341bf84BFc5382aF534df5C7461a")  # a published build by default


# _replay_role_holders is defined IN scorers.py (not imported from
# web3_utils), but it is still just another read-primitive boundary from
# score_ramses_clv2()'s point of view, so it is patched the same way as
# every name test_robinhood_uniswap_family_scorers.py already patches.
_PATCHED_NAMES = [
    "read_address_getter", "call_raw", "read_slot_as_address",
    "safe_owners_and_threshold", "is_eoa", "get_w3", "_replay_role_holders", "_read_safe_modules", "_read_safe_guard_addr", "_read_safe_singleton",
]


def _patch_helpers(test_case, fake):
    originals = {n: getattr(scorers, n) for n in _PATCHED_NAMES}
    for n in _PATCHED_NAMES:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in _PATCHED_NAMES])


def _owners(n, start=1):
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


ADDR_A = RealWeb3.to_checksum_address("0x" + "aa" * 20)
ADDR_B = RealWeb3.to_checksum_address("0x" + "bb" * 20)
ZERO_ADDR = RealWeb3.to_checksum_address("0x" + "00" * 20)


# ===================================================================== score_curve_dex
class TestScoreCurveDex(unittest.TestCase):
    FACTORY = "0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"
    FEE_RECEIVER = "0x193110Ce1542d7371e1515BD6A2E470fDefc310D"

    def test_same_key_confirmed_bare_eoa_scores_2(self):
        # "everything resolves, confirmed" happy path: both admin() and
        # owner() resolve to the SAME address, and it really is a bare EOA.
        fake = FakeHelpers()
        fake.call_raw_results[(self.FACTORY, "admin", ())] = ADDR_A
        fake.address_getters[(self.FEE_RECEIVER, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        _patch_helpers(self, fake)

        result = scorers.score_curve_dex(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (2, 0, 0))
        self.assertEqual(result["compositeScore"], scorers._composite(2, 0, 0))
        self.assertTrue(any("factory.admin() == fee-receiver.owner(): True" in n for n in result["notes"]))

    def test_different_keys_both_resolve_bare_eoa_scores_5(self):
        fake = FakeHelpers()
        fake.call_raw_results[(self.FACTORY, "admin", ())] = ADDR_A
        fake.address_getters[(self.FEE_RECEIVER, "owner")] = ADDR_B
        fake.eoa_results[ADDR_A] = True
        _patch_helpers(self, fake)

        result = scorers.score_curve_dex(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertTrue(any("factory.admin() == fee-receiver.owner(): False" in n for n in result["notes"]))

    def test_controller_is_a_real_contract_scores_40(self):
        fake = FakeHelpers()
        fake.call_raw_results[(self.FACTORY, "admin", ())] = ADDR_A
        fake.address_getters[(self.FEE_RECEIVER, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        _patch_helpers(self, fake)

        result = scorers.score_curve_dex(FakeW3())
        self.assertEqual(result["adminKeyScore"], 40)

    def test_both_reads_unresolved_degrades_without_crashing(self):
        # Degraded path: factory.admin() and fee-receiver.owner() both
        # revert/None -> controller is None -> controller_is_eoa is None.
        # `controller_is_eoa and same_key` and `5 if controller_is_eoa` both
        # short-circuit false, so this falls into the SAME conservative 40
        # branch as a confirmed real contract, not a crash.
        fake = FakeHelpers()
        _patch_helpers(self, fake)

        result = scorers.score_curve_dex(FakeW3())  # must not raise
        self.assertEqual(result["adminKeyScore"], 40)

    def test_partial_resolution_falls_back_to_fee_owner(self):
        # factory.admin() unresolved -> `controller = factory_admin or
        # fee_owner` must fall back to fee_owner, and same_key must be False
        # (short-circuited by `bool(factory_admin)`) without crashing on a
        # None comparison.
        fake = FakeHelpers()
        fake.address_getters[(self.FEE_RECEIVER, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        _patch_helpers(self, fake)

        result = scorers.score_curve_dex(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertTrue(any(f"controller {ADDR_A}" in n for n in result["notes"]))


# ===================================================================== score_meridian_exchangegateway
class TestScoreMeridianExchangeGateway(unittest.TestCase):
    # Same shape as score_curve_dex (two independent contracts checked for a
    # shared bare-EOA controller) -- new target found while auditing rotation
    # index 7, added in the same batch. Reuses that scorer's own branch
    # structure and formula, so these tests mirror TestScoreCurveDex's.
    EXCHANGE = "0xD540F47F214dC7D6D244E62A6aE7e06B586Ef44A"
    MER_USD = "0xad221259d4a1f2d7376dc1012c561bc86640f009"

    def test_same_key_confirmed_bare_eoa_scores_2(self):
        fake = FakeHelpers()
        fake.address_getters[(self.EXCHANGE, "owner")] = ADDR_A
        fake.address_getters[(self.MER_USD, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        _patch_helpers(self, fake)

        result = scorers.score_meridian_exchangegateway(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (2, 0, 0))
        self.assertEqual(result["compositeScore"], scorers._composite(2, 0, 0))
        self.assertEqual(result["target"], self.EXCHANGE)
        self.assertTrue(any("ExchangeGateway.owner() == merUSD.owner(): True" in n for n in result["notes"]))

    def test_different_keys_both_resolve_bare_eoa_scores_5(self):
        fake = FakeHelpers()
        fake.address_getters[(self.EXCHANGE, "owner")] = ADDR_A
        fake.address_getters[(self.MER_USD, "owner")] = ADDR_B
        fake.eoa_results[ADDR_A] = True
        _patch_helpers(self, fake)

        result = scorers.score_meridian_exchangegateway(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertTrue(any("ExchangeGateway.owner() == merUSD.owner(): False" in n for n in result["notes"]))

    def test_controller_is_a_real_contract_scores_40(self):
        fake = FakeHelpers()
        fake.address_getters[(self.EXCHANGE, "owner")] = ADDR_A
        fake.address_getters[(self.MER_USD, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        _patch_helpers(self, fake)

        result = scorers.score_meridian_exchangegateway(FakeW3())
        self.assertEqual(result["adminKeyScore"], 40)

    def test_both_reads_unresolved_degrades_without_crashing(self):
        fake = FakeHelpers()
        _patch_helpers(self, fake)

        result = scorers.score_meridian_exchangegateway(FakeW3())  # must not raise
        self.assertEqual(result["adminKeyScore"], 40)


# ===================================================================== score_ramses_clv2
class TestScoreRamsesClv2(unittest.TestCase):
    TEAM_MULTISIG = "0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A"
    TIMELOCK = "0xE41c07CcD69A0f19A2186f3Ad30409BD585436CE"
    ROLE_NAMES = ("PROPOSER_ROLE", "CANCELLER_ROLE", "EXECUTOR_ROLE")

    def _min_delay_key(self):
        return (self.TIMELOCK, "getMinDelay", ())

    def test_everything_resolves_confirmed_scores_constant_15_5_0_for_all_4_targets(self):
        fake = FakeHelpers()
        sole_signer = ADDR_A
        fake.safe_results[self.TEAM_MULTISIG] = ([sole_signer], 1)
        fake.eoa_results[sole_signer] = True
        fake.call_raw_results[self._min_delay_key()] = 0
        fake.role_holder_results[(self.TIMELOCK, self.ROLE_NAMES, 0)] = {
            "PROPOSER_ROLE": {ADDR_B}, "CANCELLER_ROLE": {ADDR_B}, "EXECUTOR_ROLE": {ADDR_B},
        }
        _patch_helpers(self, fake)

        results = scorers.score_ramses_clv2(FakeW3())
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (15, 5, 0))
            self.assertEqual(r["compositeScore"], scorers._composite(15, 5, 0))
        shared_notes = results[0]["notes"]
        self.assertTrue(any("Sole signer" in n and "bare EOA = True" in n for n in shared_notes))
        self.assertTrue(any("SAME single address" in n for n in shared_notes))

    def test_team_multisig_and_roles_unresolved_degrades_notes_but_score_stays_constant(self):
        # Degraded path: safe_owners_and_threshold() and the role replay both
        # come back unresolved (None / empty). This must not crash, and --
        # per the code as written, see module docstring above -- the score
        # stays the same fixed (15, 5, 0) regardless.
        fake = FakeHelpers()
        # TEAM_MULTISIG deliberately absent from safe_results -> None
        # min_delay deliberately absent -> None
        fake.role_holder_results[(self.TIMELOCK, self.ROLE_NAMES, 0)] = {
            "PROPOSER_ROLE": set(), "CANCELLER_ROLE": set(), "EXECUTOR_ROLE": set(),
        }
        _patch_helpers(self, fake)

        results = scorers.score_ramses_clv2(FakeW3())  # must not raise
        for r in results:
            self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (15, 5, 0))
        notes = results[0]["notes"]
        self.assertTrue(any("None-of-?" in n for n in notes))
        self.assertFalse(any("Sole signer" in n for n in notes))
        self.assertFalse(any("SAME single address" in n for n in notes))

    def test_roles_split_across_different_holders_omits_single_address_warning(self):
        fake = FakeHelpers()
        fake.safe_results[self.TEAM_MULTISIG] = (_owners(3), 2)  # not a 1-of-1 -> no "Sole signer" note either
        fake.call_raw_results[self._min_delay_key()] = 172800
        fake.role_holder_results[(self.TIMELOCK, self.ROLE_NAMES, 0)] = {
            "PROPOSER_ROLE": {ADDR_A}, "CANCELLER_ROLE": {ADDR_B}, "EXECUTOR_ROLE": {ADDR_A, ADDR_B},
        }
        _patch_helpers(self, fake)

        results = scorers.score_ramses_clv2(FakeW3())
        for r in results:
            self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (15, 5, 0))
        notes = results[0]["notes"]
        self.assertFalse(any("SAME single address" in n for n in notes))
        self.assertFalse(any("Sole signer" in n for n in notes))


# ===================================================================== score_ekubo_core
class TestScoreEkuboCore(unittest.TestCase):
    TARGET = "0x00000000000014aA86C5d3c41765bb24e11bd701"

    def test_owner_reverts_as_expected_scores_100_flat(self):
        fake = FakeHelpers()
        # (TARGET, "owner", ()) deliberately absent -> None ("reverted")
        _patch_helpers(self, fake)

        result = scorers.score_ekubo_core(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (100, 100, 100))
        self.assertEqual(result["compositeScore"], scorers._composite(100, 100, 100))
        self.assertTrue(any("reverted (expected)" in n for n in result["notes"]))

    def test_owner_unexpectedly_resolves_still_scores_100_flat(self):
        # If owner() ever stopped reverting (e.g. a hypothetical future
        # upgrade), the note would surface that live -- but the code as
        # written does not let this outcome change the score at all.
        fake = FakeHelpers()
        fake.call_raw_results[(self.TARGET, "owner", ())] = ADDR_A
        _patch_helpers(self, fake)

        result = scorers.score_ekubo_core(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (100, 100, 100))
        self.assertTrue(any(ADDR_A in n for n in result["notes"]))


# ===================================================================== score_chainlink_admin_safe
class TestScoreChainlinkAdminSafe(unittest.TestCase):
    TARGET = "0xEE27D5aE494300902D90454E8630a3f1c68C9c52"

    def test_safe_resolves_confirmed_multisig_uses_the_batch_9_convention(self):
        # CORRECTED 2026-09-21: was `threshold * 8` (32 for a 4-of-9, composite 36). Now the same formula as every
        # Safe-rooted target: 4*15 + 5*5 = 85, adminKey 65 (threshold >= 3), composite floor(26 + 25.5 + 0 + 0.5) = 52.
        fake = FakeHelpers()
        fake.safe_results[self.TARGET] = (_owners(9), 4)
        _patch_helpers(self, fake)

        result = scorers.score_chainlink_admin_safe(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (65, 85, 0))
        self.assertEqual(result["compositeScore"], 52)
        self.assertEqual(result["compositeScore"], scorers._composite(65, 85, 0))
        self.assertTrue(any("Confirmed live as owner() on 7 independently-sampled" in n for n in result["notes"]))

    def test_the_formula_is_the_shared_one_not_a_private_copy(self):
        for k, n in ((2, 3), (3, 5), (4, 9), (1, 1), (9, 12)):
            fake = FakeHelpers()
            fake.safe_results[self.TARGET] = (_owners(n), k)
            _patch_helpers(self, fake)
            result = scorers.score_chainlink_admin_safe(FakeW3())
            expected = scorers._safe_rooted_scores(k, n)
            self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected, (k, n))

    def test_safe_unresolved_degrades_to_the_unresolved_authority_floor_without_crashing(self):
        # CORRECTED 2026-09-21: an unresolved Safe used to keep adminKeyScore 65; it now degrades like every other
        # unresolved authority (20, 0, 0) and says so.
        fake = FakeHelpers()
        # TARGET deliberately absent from safe_results -> None
        _patch_helpers(self, fake)

        result = scorers.score_chainlink_admin_safe(FakeW3())  # must not raise
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))
        self.assertFalse(any("Confirmed live as owner()" in n for n in result["notes"]))
        self.assertTrue(any("NOT resolvable as a Gnosis Safe this run" in n for n in result["notes"]))

    def test_high_threshold_multisig_caps_at_100(self):
        fake = FakeHelpers()
        fake.safe_results[self.TARGET] = (_owners(20), 20)  # 20*15 = 300, must cap
        _patch_helpers(self, fake)

        result = scorers.score_chainlink_admin_safe(FakeW3())
        self.assertEqual(result["multisigScore"], 100)

    # ---- ADDED 2026-09-21: the Safe has a "Confirmed Transaction Module" enabled; read live, note only ----
    KNOWN_MODULE = RealWeb3.to_checksum_address("0xe5FB4576BBED29aC3846CcdE81e2201e72cC5316")

    def _score(self, modules, guard=None):
        fake = FakeHelpers()
        fake.safe_results[self.TARGET] = (_owners(9), 4)
        fake.modules[self.TARGET] = modules
        if guard:
            fake.guards[self.TARGET] = guard
        _patch_helpers(self, fake)
        return scorers.score_chainlink_admin_safe(FakeW3())

    def test_the_known_module_is_disclosed_with_what_was_found_and_moves_no_score(self):
        base = self._score([])
        r = self._score([self.KNOWN_MODULE])
        self.assertTrue(any("Confirmed Transaction Module 0.1.0" in n and "does not bypass the threshold" in n for n in r["notes"]))
        self.assertFalse(any(n.startswith("WARNING") for n in r["notes"]))
        vec = lambda x: tuple(x[k] for k in ("adminKeyScore", "multisigScore", "timelockScore", "compositeScore"))
        self.assertEqual(vec(r), vec(base))

    def test_a_new_unknown_module_is_a_warning_and_still_a_note_only(self):
        r = self._score([self.KNOWN_MODULE, RealWeb3.to_checksum_address("0x" + "9f" * 20)])
        self.assertTrue(any(n.startswith("WARNING") and "NOT ANALYZED" in n for n in r["notes"]))
        self.assertEqual(r["multisigScore"], 85)

    def test_the_odd_singleton_is_disclosed_with_the_source_diff_and_a_new_unknown_one_is_a_warning(self):
        odd = RealWeb3.to_checksum_address("0x113779dAF982b09f7A9dB64af132AA97496b3999")
        fake = FakeHelpers()
        fake.safe_results[self.TARGET] = (_owners(9), 4)
        fake.singletons[self.TARGET] = odd
        _patch_helpers(self, fake)
        r = scorers.score_chainlink_admin_safe(FakeW3())
        self.assertTrue(any("not a published Safe build" in n and "GuardManager.sol" in n for n in r["notes"]))
        self.assertFalse(any(n.startswith("WARNING") for n in r["notes"]))
        fake.singletons[self.TARGET] = RealWeb3.to_checksum_address("0x" + "9f" * 20)
        r2 = scorers.score_chainlink_admin_safe(FakeW3())
        self.assertTrue(any(n.startswith("WARNING (unanalyzed singleton") for n in r2["notes"]))
        self.assertEqual((r2["adminKeyScore"], r2["multisigScore"]), (65, 85))  # a note, never a score input

    def test_an_unresolved_safe_carries_no_module_note(self):
        fake = FakeHelpers()
        _patch_helpers(self, fake)
        r = scorers.score_chainlink_admin_safe(FakeW3())
        self.assertFalse(any("modules or guard" in n or "no module and no guard" in n or "Confirmed Transaction Module" in n for n in r["notes"]))


# ===================================================================== score_pancakeswap_v2_factory
class TestScorePancakeswapV2Factory(unittest.TestCase):
    FACTORY = "0x02a84c1b3BBD7401a5f7fa98a384EBC70bB5749E"

    def test_fee_to_setter_is_bare_eoa_scores_5(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "feeToSetter")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        _patch_helpers(self, fake)

        result = scorers.score_pancakeswap_v2_factory(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (5, 0, 0))
        self.assertEqual(result["compositeScore"], scorers._composite(5, 0, 0))

    def test_fee_to_setter_turns_out_to_be_a_safe_not_a_bare_eoa_warns(self):
        # The genuinely distinct 3-way branch this file's docstring flags:
        # a bare EOA / a real Safe / neither -- worth its own test since the
        # Safe branch fires a hand-written WARNING note not covered by the
        # heuristic.
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "feeToSetter")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.safe_results[ADDR_A] = (_owners(3), 2)
        _patch_helpers(self, fake)

        result = scorers.score_pancakeswap_v2_factory(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (40, 0, 0))
        self.assertTrue(any("WARNING: feeToSetter is actually a Safe (2-of-3)" in n for n in result["notes"]))

    def test_fee_to_setter_is_neither_eoa_nor_safe_scores_40_no_warning(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "feeToSetter")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        # ADDR_A deliberately absent from safe_results -> not a Safe either
        _patch_helpers(self, fake)

        result = scorers.score_pancakeswap_v2_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertFalse(any("WARNING" in n for n in result["notes"]))

    def test_fee_to_setter_unresolved_degrades_to_40_without_crashing(self):
        fake = FakeHelpers()
        # (FACTORY, "feeToSetter") deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_pancakeswap_v2_factory(FakeW3())  # must not raise
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertFalse(any("WARNING" in n for n in result["notes"]))


# ===================================================================== _safe_rooted_scores (pure logic -- no RPC)
class TestSafeRootedScores(unittest.TestCase):
    def test_threshold_ge_3_scores_admin_65(self):
        self.assertEqual(scorers._safe_rooted_scores(3, 3)[0], 65)
        self.assertEqual(scorers._safe_rooted_scores(7, 7)[0], 65)  # far above 3 -- still flat 65

    def test_threshold_eq_2_scores_admin_50(self):
        self.assertEqual(scorers._safe_rooted_scores(2, 5)[0], 50)

    def test_threshold_below_2_scores_admin_10(self):
        self.assertEqual(scorers._safe_rooted_scores(1, 1)[0], 10)
        self.assertEqual(scorers._safe_rooted_scores(0, 1)[0], 10)  # defensive: threshold 0 falls into the same else branch

    def test_shared_custody_and_upgrade_knocks_5_off_every_tier(self):
        self.assertEqual(scorers._safe_rooted_scores(3, 3, shared_custody_and_upgrade=True)[0], 60)
        self.assertEqual(scorers._safe_rooted_scores(2, 3, shared_custody_and_upgrade=True)[0], 45)
        self.assertEqual(scorers._safe_rooted_scores(1, 1, shared_custody_and_upgrade=True)[0], 5)

    def test_multisig_formula_15_per_required_plus_5_per_extra_owner(self):
        self.assertEqual(scorers._safe_rooted_scores(3, 3)[1], 45)        # 3*15 + 0
        self.assertEqual(scorers._safe_rooted_scores(3, 6)[1], 60)        # 3*15 + 3*5
        self.assertEqual(scorers._safe_rooted_scores(2, 10)[1], 70)       # 2*15 + 8*5

    def test_multisig_formula_caps_at_100(self):
        self.assertEqual(scorers._safe_rooted_scores(5, 30)[1], 100)      # 5*15 + 25*5 = 200 -> capped

    def test_timelock_is_always_zero(self):
        self.assertEqual(scorers._safe_rooted_scores(3, 3)[2], 0)
        self.assertEqual(scorers._safe_rooted_scores(1, 1, shared_custody_and_upgrade=True)[2], 0)


# ===================================================================== _safe_guard_and_modules
class TestSafeGuardAndModules(unittest.TestCase):
    SAFE = "0x" + "33" * 20
    MODULES_PAGE_START = "0x0000000000000000000000000000000000000001"
    MODULES_PAGE_COUNT = 10
    GUARD_SLOT = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"

    def _modules_key(self):
        return (self.SAFE, "getModulesPaginated", (self.MODULES_PAGE_START, self.MODULES_PAGE_COUNT))

    def test_no_modules_no_guard_returns_empty_list_and_zero_address(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._modules_key()] = ([], self.MODULES_PAGE_START)  # a real Safe's empty-page shape
        fake.slot_results[(self.SAFE, self.GUARD_SLOT)] = ZERO_ADDR
        _patch_helpers(self, fake)

        result = scorers._safe_guard_and_modules(FakeW3(), self.SAFE)
        self.assertEqual(result, ([], ZERO_ADDR))

    def test_modules_present_and_guard_set(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._modules_key()] = ([ADDR_A], self.MODULES_PAGE_START)
        fake.slot_results[(self.SAFE, self.GUARD_SLOT)] = ADDR_B
        _patch_helpers(self, fake)

        result = scorers._safe_guard_and_modules(FakeW3(), self.SAFE)
        self.assertEqual(result, ([ADDR_A], ADDR_B))

    def test_modules_call_reverts_returns_none_for_modules(self):
        fake = FakeHelpers()
        # modules call deliberately absent -> None (reverted / not a Safe)
        fake.slot_results[(self.SAFE, self.GUARD_SLOT)] = ZERO_ADDR
        _patch_helpers(self, fake)

        result = scorers._safe_guard_and_modules(FakeW3(), self.SAFE)
        self.assertEqual(result, (None, ZERO_ADDR))


# ===================================================================== _safe_rooted_entry (the real shared logic)
class TestSafeRootedEntry(unittest.TestCase):
    SAFE = "0x" + "44" * 20

    def test_safe_param_none_short_circuits_to_conservative_20_0_0(self):
        fake = FakeHelpers()
        _patch_helpers(self, fake)

        notes = []
        result = scorers._safe_rooted_entry(FakeW3(), "target", "label", None, notes)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))
        self.assertTrue(any("NOT resolvable" in n for n in notes))

    def test_safe_given_but_not_resolvable_as_a_safe_degrades_to_20_0_0(self):
        fake = FakeHelpers()
        # self.SAFE deliberately absent from safe_results -> None
        _patch_helpers(self, fake)

        notes = []
        result = scorers._safe_rooted_entry(FakeW3(), "target", "label", self.SAFE, notes)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))
        self.assertTrue(any(f"{self.SAFE}: NOT resolvable" in n for n in notes))

    def test_resolved_no_modules_no_guard_uses_safe_rooted_scores_table(self):
        fake = FakeHelpers()
        fake.safe_results[self.SAFE] = (_owners(3), 2)
        # no getModulesPaginated / guard-slot fixtures registered -> both None
        _patch_helpers(self, fake)

        notes = []
        result = scorers._safe_rooted_entry(FakeW3(), "target", "label", self.SAFE, notes)
        expected_admin, expected_multisig, expected_timelock = scorers._safe_rooted_scores(2, 3)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (expected_admin, expected_multisig, expected_timelock),
        )
        self.assertFalse(any("WARNING" in n for n in notes))

    def test_resolved_with_a_module_appends_warning(self):
        fake = FakeHelpers()
        fake.safe_results[self.SAFE] = (_owners(3), 2)
        fake.call_raw_results[(self.SAFE, "getModulesPaginated", ("0x0000000000000000000000000000000000000001", 10))] = ([ADDR_A], "0x0000000000000000000000000000000000000001")
        _patch_helpers(self, fake)

        notes = []
        scorers._safe_rooted_entry(FakeW3(), "target", "label", self.SAFE, notes)
        self.assertTrue(any("WARNING: Safe has a module or guard" in n for n in notes))

    def test_shared_custody_and_upgrade_flag_changes_admin_key_by_5(self):
        fake = FakeHelpers()
        fake.safe_results[self.SAFE] = (_owners(3), 3)  # threshold 3 -> base admin 65
        _patch_helpers(self, fake)

        without_flag = scorers._safe_rooted_entry(FakeW3(), "t", "l", self.SAFE, [], shared_custody_and_upgrade=False)
        with_flag = scorers._safe_rooted_entry(FakeW3(), "t", "l", self.SAFE, [], shared_custody_and_upgrade=True)
        self.assertEqual(without_flag["adminKeyScore"], 65)
        self.assertEqual(with_flag["adminKeyScore"], 60)
        self.assertEqual(without_flag["multisigScore"], with_flag["multisigScore"])  # only admin_key is affected


# ===================================================================== score_pancakeswap_v3_factory (light smoke)
class TestScorePancakeswapV3Factory(unittest.TestCase):
    FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
    WRAPPER = "0x" + "11" * 20
    SAFE = "0x" + "22" * 20

    def test_resolves_two_hop_owner_chain_and_matches_safe_rooted_entry(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = self.WRAPPER
        fake.address_getters[(self.WRAPPER, "owner")] = self.SAFE
        fake.safe_results[self.SAFE] = (_owners(6), 3)  # 3-of-6, per this scorer's own docstring
        _patch_helpers(self, fake)

        result = scorers.score_pancakeswap_v3_factory(FakeW3())
        expected_admin, expected_multisig, expected_timelock = scorers._safe_rooted_scores(3, 6)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (expected_admin, expected_multisig, expected_timelock),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(expected_admin, expected_multisig, expected_timelock))


# ===================================================================== score_sushiswap_v3_factory (light smoke)
class TestScoreSushiswapV3Factory(unittest.TestCase):
    FACTORY = "0xE51960f1B45f1C9FB6D166E6a884F866fC70433B"
    WRAPPER = "0x" + "33" * 20
    SAFE = "0x" + "44" * 20

    def test_resolves_two_hop_owner_chain_and_matches_safe_rooted_entry(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = self.WRAPPER
        fake.address_getters[(self.WRAPPER, "owner")] = self.SAFE
        fake.safe_results[self.SAFE] = (_owners(3), 2)  # 2-of-3, per this scorer's own docstring
        _patch_helpers(self, fake)

        result = scorers.score_sushiswap_v3_factory(FakeW3())
        expected_admin, expected_multisig, expected_timelock = scorers._safe_rooted_scores(2, 3)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (expected_admin, expected_multisig, expected_timelock),
        )


# ===================================================================== score_symbiosis_portal (light smoke)
class TestScoreSymbiosisPortal(unittest.TestCase):
    PORTAL = "0x292fC50e4eB66C3f6514b9E402dBc25961824D62"
    PROXY_ADMIN = "0x" + "55" * 20
    SAFE = "0x" + "66" * 20

    def test_resolves_proxy_admin_hop_and_matches_safe_rooted_entry(self):
        # This scorer's hop sequence is NOT read_address_getter chained
        # twice like PCS V3/SushiSwap V3 above -- it's an EIP-1967 admin
        # slot read followed by ProxyAdmin.owner().
        fake = FakeHelpers()
        fake.slot_results[(self.PORTAL, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.SAFE
        fake.address_getters[(self.PORTAL, "owner")] = self.SAFE  # portal_owner matches pa_owner -- no divergence
        fake.safe_results[self.SAFE] = (_owners(5), 3)  # 3-of-5, per this scorer's own docstring
        _patch_helpers(self, fake)

        result = scorers.score_symbiosis_portal(FakeW3())
        expected_admin, expected_multisig, expected_timelock = scorers._safe_rooted_scores(3, 5)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (expected_admin, expected_multisig, expected_timelock),
        )
        self.assertFalse(any("WARNING" in n for n in result["notes"]))

    def test_divergent_portal_owner_and_proxy_admin_owner_warns(self):
        # A distinct branch specific to this scorer among the 4 wrappers:
        # the upgrade authority (ProxyAdmin.owner()) and the business-logic
        # owner (Portal.owner()) are read and compared separately.
        fake = FakeHelpers()
        fake.slot_results[(self.PORTAL, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.SAFE
        fake.address_getters[(self.PORTAL, "owner")] = ADDR_A  # deliberately different from pa_owner
        fake.safe_results[self.SAFE] = (_owners(5), 3)
        _patch_helpers(self, fake)

        result = scorers.score_symbiosis_portal(FakeW3())
        self.assertTrue(any("upgrade authority and business-logic owner now DIFFER" in n for n in result["notes"]))
        # still scored on the upgrade authority (pa_owner -> self.SAFE), not the business-logic owner
        expected_admin, expected_multisig, _ = scorers._safe_rooted_scores(3, 5)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"]), (expected_admin, expected_multisig))


# ===================================================================== score_strato_bridge_router (light smoke)
class TestScoreStratoBridgeRouter(unittest.TestCase):
    ROUTER = "0x0dc846db6a4eC7b5a3e542F7db88049E9ADd2541"
    CUSTODY = "0x8c458F866e603335ef179A63a2528F357732f5d5"
    ALT_SAFE = "0x" + "77" * 20  # a different Safe address, NOT the hardcoded custody constant

    def test_router_owner_equals_custody_sets_shared_custody_flag_and_knocks_5_off(self):
        fake = FakeHelpers()
        fake.address_getters[(self.ROUTER, "owner")] = self.CUSTODY
        fake.safe_results[self.CUSTODY] = (_owners(3), 2)  # 2-of-3, per this scorer's own docstring
        _patch_helpers(self, fake)

        result = scorers.score_strato_bridge_router(FakeW3())
        base_admin, expected_multisig, _ = scorers._safe_rooted_scores(2, 3)
        self.assertEqual(result["adminKeyScore"], base_admin - 5)  # shared_custody_and_upgrade knocked 5 off
        self.assertEqual(result["multisigScore"], expected_multisig)
        self.assertTrue(any("equals custody Safe" in n and ": True" in n for n in result["notes"]))

    def test_router_owner_different_from_custody_does_not_set_the_flag(self):
        # Dedicated same-Safe-shape comparison: identical 2-of-3 threshold/
        # owner count as the test above, but router.owner() now resolves to
        # a DIFFERENT Safe than the hardcoded custody address, so `same` is
        # False and shared_custody_and_upgrade must NOT fire.
        fake = FakeHelpers()
        fake.address_getters[(self.ROUTER, "owner")] = self.ALT_SAFE
        fake.safe_results[self.ALT_SAFE] = (_owners(3), 2)  # same 2-of-3 shape as the custody case above
        _patch_helpers(self, fake)

        result = scorers.score_strato_bridge_router(FakeW3())
        base_admin, expected_multisig, _ = scorers._safe_rooted_scores(2, 3)
        self.assertEqual(result["adminKeyScore"], base_admin)  # NOT knocked down -- flag never set
        self.assertEqual(result["multisigScore"], expected_multisig)
        self.assertTrue(any("equals custody Safe" in n and ": False" in n for n in result["notes"]))


# ===================================================================== score_up_v3_factory (light smoke)
class TestScoreUpV3Factory(unittest.TestCase):
    """Rotation audit index 13 (2026-09-19) new-target search. Simplest of
    this file's `_safe_rooted_entry()` callers: a single `factory.owner()`
    read resolving DIRECTLY to the Safe -- no wrapper hop (PancakeSwap V3/
    SushiSwap V3), no EIP-1967 admin-slot hop (Symbiosis Portal), and no
    custody-address comparison (STRATO)."""

    FACTORY = "0x1ac9dB4a2608ba45D6127B1737949b51Bb54B7F3"
    SAFE = "0x" + "88" * 20

    def test_resolves_owner_directly_to_safe_and_matches_safe_rooted_entry(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = self.SAFE
        fake.safe_results[self.SAFE] = (_owners(4), 2)  # 2-of-4, per this scorer's own docstring
        _patch_helpers(self, fake)

        result = scorers.score_up_v3_factory(FakeW3())
        expected_admin, expected_multisig, expected_timelock = scorers._safe_rooted_scores(2, 4)
        self.assertEqual(result["target"], self.FACTORY)
        self.assertEqual(result["label"], "up v3 Factory (Robinhood Chain)")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (expected_admin, expected_multisig, expected_timelock),
        )
        self.assertEqual(
            result["compositeScore"],
            scorers._composite(expected_admin, expected_multisig, expected_timelock),
        )

    def test_owner_unresolved_as_safe_degrades_to_conservative_20_0_0(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = ADDR_A
        # ADDR_A deliberately absent from safe_results -> not resolvable as a Safe
        _patch_helpers(self, fake)

        result = scorers.score_up_v3_factory(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 0, 0),
        )
        self.assertTrue(any("NOT resolvable as a Gnosis Safe" in n for n in result["notes"]))


# ===================================================================== score_alandale_v3_factory
class TestScoreAlandaleV3Factory(unittest.TestCase):
    """Rotation audit index 14 (2026-09-19) new-target search. Same
    EIP-1967-admin-slot -> ProxyAdmin.owner() hop convention as
    `score_symbiosis_portal()` (scored on the upgrade authority, WARNING on
    divergence from the business-logic owner), but the fixture here is the
    real 3-of-5 shape found live for the Alandale V3 (Algebra) factory."""

    FACTORY = "0x16494A80E08Bcb9285D87b67149d7b01774D82F8"
    PROXY_ADMIN = "0x" + "77" * 20
    SAFE = "0x" + "99" * 20

    def test_upgrade_authority_and_owner_same_safe_matches_safe_rooted_scores(self):
        fake = FakeHelpers()
        fake.slot_results[(self.FACTORY, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.SAFE
        fake.address_getters[(self.FACTORY, "owner")] = self.SAFE
        fake.safe_results[self.SAFE] = (_owners(5), 3)  # 3-of-5, per this scorer's own docstring
        _patch_helpers(self, fake)

        result = scorers.score_alandale_v3_factory(FakeW3())
        expected_admin, expected_multisig, expected_timelock = scorers._safe_rooted_scores(3, 5)
        self.assertEqual((expected_admin, expected_multisig, expected_timelock), (65, 55, 0))
        self.assertEqual(result["target"], self.FACTORY)
        self.assertEqual(result["label"], "Alandale V3 Factory (Robinhood Chain)")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (65, 55, 0),
        )
        # hand-derived: floor(0.4*65 + 0.3*55 + 0.3*0 + 0.5) = floor(43.0) = 43
        self.assertEqual(result["compositeScore"], 43)
        self.assertFalse(any("WARNING" in n for n in result["notes"]))

    def test_divergent_owner_and_proxy_admin_owner_warns_and_scores_on_upgrade_authority(self):
        fake = FakeHelpers()
        fake.slot_results[(self.FACTORY, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.SAFE
        fake.address_getters[(self.FACTORY, "owner")] = ADDR_A  # deliberately different from pa_owner
        fake.safe_results[self.SAFE] = (_owners(5), 3)
        _patch_helpers(self, fake)

        result = scorers.score_alandale_v3_factory(FakeW3())
        self.assertTrue(any("upgrade authority and factory owner now DIFFER" in n for n in result["notes"]))
        expected_admin, expected_multisig, _ = scorers._safe_rooted_scores(3, 5)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"]), (expected_admin, expected_multisig))

    def test_proxy_admin_owner_unresolved_degrades_to_conservative_20_0_0(self):
        fake = FakeHelpers()
        fake.slot_results[(self.FACTORY, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        # PROXY_ADMIN.owner() deliberately absent from address_getters -> None
        fake.address_getters[(self.FACTORY, "owner")] = self.SAFE
        fake.safe_results[self.SAFE] = (_owners(5), 3)
        _patch_helpers(self, fake)

        result = scorers.score_alandale_v3_factory(FakeW3())
        # scored on the upgrade authority, which did not resolve -> never silently
        # falls back to the (stronger-looking) factory.owner() Safe
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 0, 0),
        )
        self.assertTrue(any("NOT resolvable as a Gnosis Safe" in n for n in result["notes"]))
        self.assertTrue(any("upgrade authority and factory owner now DIFFER" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
