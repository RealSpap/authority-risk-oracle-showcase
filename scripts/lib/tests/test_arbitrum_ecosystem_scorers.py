"""
Unit tests for chains/arbitrum-ecosystem/scorers.py's scoring-decision
logic -- previously ZERO coverage, closing the same 2026-09-18
test-coverage audit's next-ranked gap after Zcash and Base (Arbitrum is
Base's closest sibling: same shared `web3_utils.py` primitives, same
"root -> Safe/Timelock/role chain -> admin/multisig/timelock branches"
shape, same missing test layer on top of already-tested plumbing).

Same approach as `test_base_ecosystem_scorers.py`: monkeypatch the
read-primitive names this file imports directly (`read_address_getter`,
`call_raw`, `safe_owners_and_threshold`, `is_eoa`) with small
dict-dispatch fakes, rather than mocking Web3.py's contract-call
machinery. Two of the five scorers here (GMX, the Security Council Safe)
compute a real `Web3.keccak(...)` role hash inline rather than reading it
-- those hashes are recomputed independently in this test file (not
copy-pasted) and used as the exact dispatch keys the fakes are queried
with, so the tests exercise the real hashing path too, not just a
stand-in.
"""
import importlib.util
import os
import sys
import unittest

from eth_abi import encode
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
scorers = _load_module("aro_test_arbitrum_ecosystem_scorers", "chains/arbitrum-ecosystem/scorers.py")


# ADDED 2026-10-04: these tests pin the composite logic on a fake chain the price-path engine cannot walk. The engine is
# replaced here by a stub returning 100; scripts/lib/tests/test_price_authority_wiring.py checks that each consumer scorer
# really puts the engine's value into oracleAuthorityScore.
_PA_NAMES = ("for_aave", "for_comet", "for_morpho_v1")
_PA_ORIG = {}


def setUpModule():
    for n in _PA_NAMES:
        _PA_ORIG[n] = getattr(scorers.price_authority, n)
        setattr(scorers.price_authority, n, lambda *a, **k: 100)


def tearDownModule():
    for n, f in _PA_ORIG.items():
        setattr(scorers.price_authority, n, f)


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}       # (address, function_name) -> value-or-None
        self.call_raw_results = {}      # (address, function_name, args-tuple) -> value-or-None
        self.safe_results = {}          # address -> (owners, threshold) or None
        self.eoa_results = {}           # address -> bool, default True
        self.slots = {}                 # (address, slot) -> address-or-None  (ADDED 2026-09-19)
        self.modules = {}               # safe address -> list of module addresses, default [] (ADDED 2026-09-21)
        self.guards = {}                # safe address -> guard address, default the zero address

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def is_eoa(self, w3, address):
        return self.eoa_results.get(address, True)

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slots.get((address, slot))

    def get_w3(self, rpc_url):
        # Uniswap's scorer opens its own L1 w3; the fakes above ignore w3
        # entirely, so a sentinel is enough (no network in unit tests).
        return FakeW3()

    def read_modules(self, w3, address, retries=4):
        return self.modules.get(address, [])

    def read_guard(self, w3, address, retries=4):
        return self.guards.get(address, "0x" + "0" * 40)


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "safe_owners_and_threshold", "is_eoa", "read_slot_as_address", "get_w3", "read_modules", "read_guard"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


class FakeW3:
    """None of these 5 scorers call w3.eth.* directly (unlike Base's
    Uniswap scorer) -- score_camelot_ammv3_factory calls
    w3.to_checksum_address(...) though (inside its EOA-check dict
    comprehension's own f-string, and is_eoa itself is faked above), so a
    trivial passthrough covers it."""
    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


def _owners(n, start=1):
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


ADDR_A = RealWeb3.to_checksum_address("0x" + "aa" * 20)
ADDR_B = RealWeb3.to_checksum_address("0x" + "bb" * 20)
ADDR_C = RealWeb3.to_checksum_address("0x" + "cc" * 20)
ADDR_D = RealWeb3.to_checksum_address("0x" + "dd" * 20)


# --------------------------------------------------------------------- _composite
class TestComposite(unittest.TestCase):
    def test_weights_and_round_half_up(self):
        self.assertEqual(scorers._composite(65, 65, 0), 46)

    def test_half_boundary_rounds_up(self):
        self.assertEqual(scorers._composite(0, 0, 5), 2)  # 0.3*5+0.5=2.0 -> floor 2


# --------------------------------------------------------------------- GMX V2 RoleStore
# REWRITTEN 2026-09-19 alongside the scorer CORRECTION (rotation audit index
# 0): the scorer now resolves ROLE_ADMIN -> TimelockConfig -> live
# ConfigTimelockController and scores the WEAKEST TIMELOCK_ADMIN initiator,
# instead of trusting one hardcoded controller and one Safe.
class TestScoreGmxV2RoleStore(unittest.TestCase):
    TARGET = "0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72"
    DAO_TL = RealWeb3.to_checksum_address("0x" + "d1" * 20)
    CTL = RealWeb3.to_checksum_address("0x" + "c7" * 20)
    TCONF = RealWeb3.to_checksum_address("0x" + "e7" * 20)
    SAFE = ADDR_A
    EOA = ADDR_B

    @staticmethod
    def _role(name):  # GMX Role.sol pattern, recomputed independently of the scorer
        return RealWeb3.keccak(encode(["string"], [name]))

    def _wire(self, fake, timelock_admins=None, dao_delay=86400, ctl_delay=86400, veto=True, safe_threshold=5, safe_n=8):
        members = {
            "ROLE_ADMIN": [self.DAO_TL, self.CTL, self.TCONF],
            "TIMELOCK_ADMIN": timelock_admins if timelock_admins is not None else [self.SAFE, self.EOA],
            "TIMELOCK_MULTISIG": [self.SAFE],
        }
        for name, m in members.items():
            fake.call_raw_results[(self.TARGET, "getRoleMembers", (self._role(name), 0, 50))] = m
        fake.address_getters[(self.TCONF, "timelockController")] = self.CTL
        fake.call_raw_results[(self.CTL, "getMinDelay", ())] = ctl_delay
        fake.call_raw_results[(self.DAO_TL, "getMinDelay", ())] = dao_delay
        fake.safe_results[self.SAFE] = (_owners(safe_n), safe_threshold)
        fake.eoa_results[self.EOA] = True
        fake.call_raw_results[(self.CTL, "hasRole", (RealWeb3.keccak(text="CANCELLER_ROLE"), self.SAFE))] = veto

    def test_live_shape_bare_eoa_initiator_sets_the_score(self):
        # The 2026-09-19 live shape: 5-of-8 Safe AND a bare EOA both hold
        # TIMELOCK_ADMIN -- the EOA is the weakest initiator.
        fake = FakeHelpers()
        self._wire(fake)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (10, 0, 60))
        self.assertEqual(r["compositeScore"], 22)

    def test_safe_only_initiators_keep_the_old_strong_score(self):
        # Same path with the EOA removed reproduces the previously published
        # 65/90/60 -> 71: the correction is driven by the EOA, not by a
        # formula change.
        fake = FakeHelpers()
        self._wire(fake, timelock_admins=[self.SAFE])
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 90, 60, 71))

    def test_weakest_safe_wins_over_stronger_safe(self):
        fake = FakeHelpers()
        weak = ADDR_C
        self._wire(fake, timelock_admins=[self.SAFE, weak])
        fake.safe_results[weak] = (_owners(3, start=50), 2)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r["adminKeyScore"], 50)
        self.assertEqual(r["multisigScore"], 35)

    def test_unresolved_contract_initiator_scores_as_unknown(self):
        fake = FakeHelpers()
        odd = ADDR_D
        self._wire(fake, timelock_admins=[self.SAFE, odd])
        fake.eoa_results[odd] = False  # has code, not a Safe
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (20, 0))

    def test_zero_delay_role_admin_is_a_bypass(self):
        fake = FakeHelpers()
        self._wire(fake, dao_delay=0)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r["timelockScore"], 0)

    def test_missing_veto_caps_timelock(self):
        fake = FakeHelpers()
        self._wire(fake, veto=False)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r["timelockScore"], 50)

    def test_controller_unresolved_is_conservative(self):
        fake = FakeHelpers()
        self._wire(fake)
        fake.address_getters[(self.TCONF, "timelockController")] = None
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    # ---- ADDED 2026-09-21: symmetry with the V1 Vault (tracked index 9) on crossExposureScore ----
    V1_VAULT = "0x489ee077994B6658eAfA855C308275EAd8097C4A"
    V2_TIMELOCK = "0x2Dd99f39f58445CDDC57AA5E0DB2C367335BBD44"  # the live ConfigTimelockController, a ROLE_ADMIN of this RoleStore
    V1_GOV = RealWeb3.to_checksum_address("0x" + "a9" * 20)
    V1_TOKEN_MANAGER = RealWeb3.to_checksum_address("0x" + "b8" * 20)

    def _wire_real_v2_timelock(self, fake, tm_roles):
        self._wire(fake)
        members = {"ROLE_ADMIN": [self.DAO_TL, self.V2_TIMELOCK, self.TCONF], "TIMELOCK_ADMIN": [self.SAFE, self.EOA], "TIMELOCK_MULTISIG": [self.SAFE]}
        for name, m in members.items():
            fake.call_raw_results[(self.TARGET, "getRoleMembers", (self._role(name), 0, 50))] = m
        fake.address_getters[(self.TCONF, "timelockController")] = self.V2_TIMELOCK
        fake.call_raw_results[(self.V2_TIMELOCK, "getMinDelay", ())] = 86400
        fake.call_raw_results[(self.V2_TIMELOCK, "hasRole", (RealWeb3.keccak(text="CANCELLER_ROLE"), self.SAFE))] = True
        fake.address_getters[(self.V1_VAULT, "gov")] = self.V1_GOV
        fake.address_getters[(self.V1_GOV, "tokenManager")] = self.V1_TOKEN_MANAGER
        for role, held in tm_roles.items():
            fake.call_raw_results[(self.V2_TIMELOCK, "hasRole", (RealWeb3.keccak(text=role), self.V1_TOKEN_MANAGER))] = held

    def test_v1_token_manager_holding_a_role_on_the_v2_timelock_folds_cross_exposure_to_80(self):
        # The relation "one committee reaches two tracked targets" is symmetric: score_gmx_v1_vault reads 80 for it,
        # so the RoleStore must too. Composite is untouched.
        fake = FakeHelpers()
        self._wire_real_v2_timelock(fake, {"PROPOSER_ROLE": True, "EXECUTOR_ROLE": True, "CANCELLER_ROLE": True})
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["crossExposureScore"], r["compositeScore"]), (80, 22))
        self.assertTrue(any("crossExposureScore = 80" in n and "index 9" in n for n in r["notes"]))

    def test_no_role_held_by_the_v1_token_manager_keeps_cross_exposure_at_100_and_says_it_was_checked(self):
        fake = FakeHelpers()
        self._wire_real_v2_timelock(fake, {"PROPOSER_ROLE": False, "EXECUTOR_ROLE": False, "CANCELLER_ROLE": False})
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertTrue(any("holds no role on the GMX V2 timelock this run" in n for n in r["notes"]))

    def test_unread_v1_link_or_unread_roles_never_assert_the_overlap(self):
        # V1 gov unread -> nothing to compare; roles unread (None) -> not a clean result either.
        fake = FakeHelpers()
        self._wire_real_v2_timelock(fake, {})
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertIn(scorers._CROSS_EXPOSURE_NOTE, r["notes"])
        fake2 = FakeHelpers()
        self._wire(fake2)
        fake2.address_getters[(self.V1_VAULT, "gov")] = None
        _patch_helpers(self, fake2)
        r2 = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r2["crossExposureScore"], 100)
        self.assertIn(scorers._CROSS_EXPOSURE_NOTE, r2["notes"])

    # ---- ADDED 2026-09-20: the GMX DAO timelock's own proposer EOA (sweep section 4) ----
    DAO_EOA = RealWeb3.to_checksum_address("0xE7BfFf2aB721264887230037940490351700a068")
    DAO_GOVERNOR = RealWeb3.to_checksum_address("0x03e8f708e9C85EDCEaa6AD7Cd06824CeB82A7E68")

    def _wire_dao_holders(self, fake, eoa=("PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE"), governor=True, safe_cancels=False):
        fake.eoa_results[self.DAO_EOA] = True
        fake.eoa_results[self.DAO_GOVERNOR] = False
        for r in ("PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE"):
            fake.call_raw_results[(self.DAO_TL, "hasRole", (RealWeb3.keccak(text=r), self.DAO_EOA))] = r in eoa
            fake.call_raw_results[(self.DAO_TL, "hasRole", (RealWeb3.keccak(text=r), self.DAO_GOVERNOR))] = governor
        fake.call_raw_results[(self.DAO_TL, "hasRole", (RealWeb3.keccak(text="CANCELLER_ROLE"), self.SAFE))] = safe_cancels

    def test_dao_timelock_eoa_without_safe_veto_drops_the_veto_credit(self):
        fake = FakeHelpers()
        self._wire(fake)
        self._wire_dao_holders(fake)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (10, 0, 50, 19))
        text = " ".join(r["notes"])
        self.assertIn("NO veto from the RoleStore's Safe", text)
        self.assertIn(self.DAO_EOA, text)

    def test_dao_timelock_eoa_with_safe_cancel_keeps_the_veto_credit(self):
        fake = FakeHelpers()
        self._wire(fake)
        self._wire_dao_holders(fake, safe_cancels=True)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["timelockScore"], r["compositeScore"]), (60, 22))
        self.assertIn("veto window covers it", " ".join(r["notes"]))

    def test_dao_timelock_governor_only_changes_nothing(self):
        fake = FakeHelpers()
        self._wire(fake)
        self._wire_dao_holders(fake, eoa=())
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["timelockScore"], r["compositeScore"]), (60, 22))

    def test_dao_timelock_eoa_that_can_only_cancel_is_not_an_initiator(self):
        fake = FakeHelpers()
        self._wire(fake, timelock_admins=[self.SAFE])
        self._wire_dao_holders(fake, eoa=("CANCELLER_ROLE",))
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 90, 60, 71))

    def test_dao_timelock_eoa_makes_a_safe_only_initiator_set_bare_eoa_weak(self):
        # TIMELOCK_ADMIN is only the 5-of-8 Safe, yet a single key can still queue and execute on the DAO timelock.
        fake = FakeHelpers()
        self._wire(fake, timelock_admins=[self.SAFE])
        self._wire_dao_holders(fake)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (10, 0, 50))

    def test_dao_timelock_role_reads_unresolved_do_not_move_the_score_or_crash(self):
        fake = FakeHelpers()
        self._wire(fake)  # no hasRole wired on the DAO timelock: every read returns None
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (10, 0, 60, 22))

    def test_dao_timelock_with_zero_delay_is_not_consulted_for_holders(self):
        fake = FakeHelpers()
        self._wire(fake, dao_delay=0)
        self._wire_dao_holders(fake)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual(r["timelockScore"], 0)  # the zero-delay bypass rule already dominates

    def test_dao_holder_candidates_are_the_two_addresses_confirmed_on_2026_09_20(self):
        self.assertEqual([a.lower() for a in scorers._GMX_DAO_TIMELOCK_HOLDER_CANDIDATES],
                         [self.DAO_EOA.lower(), self.DAO_GOVERNOR.lower()])

    def test_hardcoded_old_controller_is_no_longer_consulted(self):
        # Regression guard for the CORRECTION: wiring ONLY the old
        # 0xC77E... controller (the pre-2026-09-19 hardcoded hop) must not
        # resolve the path any more.
        fake = FakeHelpers()
        old = "0xC77E6C0ca99E02660A23c00A860Dd5a8912DEaF5"
        fake.call_raw_results[(self.TARGET, "getRoleMembers", (self._role("TIMELOCK_MULTISIG"), 0, 50))] = [self.SAFE]
        fake.call_raw_results[(old, "getMinDelay", ())] = 86400
        fake.safe_results[self.SAFE] = (_owners(8), 5)
        _patch_helpers(self, fake)

        r = scorers.score_gmx_v2_rolestore(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))


# --------------------------------------------------------------------- Camelot
class TestScoreCamelotAmmv3Factory(unittest.TestCase):
    TARGET = "0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B"

    def test_threshold_2_of_3_scores_medium(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(3), 2)
        _patch_helpers(self, fake)

        r = scorers.score_camelot_ammv3_factory(FakeW3())
        self.assertEqual(r["adminKeyScore"], 50)
        self.assertEqual(r["timelockScore"], 0)  # no TimelockController layer, ever

    def test_threshold_3_scores_strong(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(5), 3)
        _patch_helpers(self, fake)

        r = scorers.score_camelot_ammv3_factory(FakeW3())
        self.assertEqual(r["adminKeyScore"], 65)

    def test_threshold_1_scores_weak(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(1), 1)
        _patch_helpers(self, fake)

        r = scorers.score_camelot_ammv3_factory(FakeW3())
        self.assertEqual(r["adminKeyScore"], 10)

    def test_owner_not_a_safe_degrades(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = None
        _patch_helpers(self, fake)

        r = scorers.score_camelot_ammv3_factory(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))


# --------------------------------------------------------------------- Radiant
# REWRITTEN 2026-09-20 alongside the scorer CORRECTION (see
# data/finding_2026-09-20-unscored-role-sweep.md section 3): the scorer used to
# credit provider.owner() (a 72h TimelockController) as the only root, but the
# provider's getPoolAdmin() is a DIFFERENT 4-of-11 Safe that upgrades the token
# proxies through the configurator with no delay. The pre-existing tests below
# (timelock == pool admin, no bypass) keep their old expectations exactly; the
# bypass, unread and non-Safe branches are new.
_SAME_AS_OWNER = object()


class TestScoreRadiantLendingPool(unittest.TestCase):
    LENDING_POOL = "0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886"
    PROVIDER = "0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a"
    TIMELOCK = ADDR_A
    POOL_ADMIN = ADDR_B
    EMERGENCY = ADDR_C
    PROPOSER = RealWeb3.keccak(text="PROPOSER_ROLE")  # recomputed independently of the scorer
    CANCELLER = RealWeb3.keccak(text="CANCELLER_ROLE")
    EXECUTOR = RealWeb3.keccak(text="EXECUTOR_ROLE")

    def _wire(self, fake, live_pool=None, provider_owner=ADDR_A, delay=259200, pool_admin=_SAME_AS_OWNER):
        fake.address_getters[(self.PROVIDER, "getLendingPool")] = live_pool or self.LENDING_POOL
        fake.address_getters[(self.PROVIDER, "owner")] = provider_owner
        fake.address_getters[(self.PROVIDER, "getPoolAdmin")] = provider_owner if pool_admin is _SAME_AS_OWNER else pool_admin
        if provider_owner:
            fake.call_raw_results[(provider_owner, "getMinDelay", ())] = delay

    def _wire_safe_pool_admin(self, fake, threshold=4, n=11, executors=6, **kw):
        """Live 2026-09-20 shape by default: pool admin = a 4-of-11 Safe distinct from the
        timelock, holding PROPOSER and CANCELLER on it, 6 of its 11 owners holding EXECUTOR."""
        self._wire(fake, pool_admin=self.POOL_ADMIN, **kw)
        owners = _owners(n, start=100)
        fake.safe_results[self.POOL_ADMIN] = (owners, threshold)
        fake.call_raw_results[(self.TIMELOCK, "hasRole", (self.PROPOSER, self.POOL_ADMIN))] = True
        fake.call_raw_results[(self.TIMELOCK, "hasRole", (self.CANCELLER, self.POOL_ADMIN))] = True
        for i, o in enumerate(owners):
            fake.call_raw_results[(self.TIMELOCK, "hasRole", (self.EXECUTOR, o))] = i < executors
        return owners

    def _score(self, fake):
        _patch_helpers(self, fake)
        return scorers.score_radiant_lendingpool(FakeW3())

    # ---- ADDED 2026-09-21: the emergency-admin Safe's modules, read live, note only ----
    HYPERNATIVE_MODULES = [RealWeb3.to_checksum_address("0x4405f3b660eb53c4d1aC04546ef30A7A6bF91036"),
                           RealWeb3.to_checksum_address("0x28e24b1d5fEFC0e9c0F354e9d7411f5F44827EAb")]

    def _score_with_emergency_modules(self, modules):
        fake = FakeHelpers()
        self._wire(fake)
        fake.address_getters[(self.PROVIDER, "getEmergencyAdmin")] = self.EMERGENCY
        fake.safe_results[self.EMERGENCY] = (_owners(5, start=200), 1)
        fake.modules[self.EMERGENCY] = modules
        return self._score(fake)

    def test_the_two_hypernative_pause_modules_are_disclosed_on_the_emergency_safe_and_move_no_score(self):
        base = self._score_with_emergency_modules([])
        r = self._score_with_emergency_modules(self.HYPERNATIVE_MODULES)
        self.assertEqual(sum("HypernativeModule" in n for n in r["notes"]), 1)  # one note line naming both modules
        self.assertFalse(any(n.startswith("WARNING") for n in r["notes"]))
        vec = lambda x: tuple(x[k] for k in ("adminKeyScore", "multisigScore", "timelockScore", "crossExposureScore", "compositeScore"))
        self.assertEqual(vec(r), vec(base))

    def test_an_unknown_module_on_the_emergency_safe_is_a_warning(self):
        r = self._score_with_emergency_modules([RealWeb3.to_checksum_address("0x" + "9f" * 20)])
        self.assertTrue(any(n.startswith("WARNING") for n in r["notes"]))

    def test_no_emergency_safe_means_no_module_note(self):
        fake = FakeHelpers()
        self._wire(fake)
        r = self._score(fake)
        self.assertFalse(any("modules or guard" in n or "no module and no guard" in n for n in r["notes"]))

    # ---- no bypass: pool admin == timelock keeps the pre-2026-09-20 scoring exactly
    def test_confirmed_pool_and_real_delay_scores_strong(self):
        fake = FakeHelpers()
        self._wire(fake)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (55, 100, 55))
        self.assertEqual(r["compositeScore"], 69)  # the score published on-chain before the correction
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertEqual(r["target"], self.LENDING_POOL)

    def test_pool_admin_equal_to_timelock_is_case_insensitive(self):
        fake = FakeHelpers()
        self._wire(fake, pool_admin=self.TIMELOCK.lower())
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (55, 100, 55, 69))

    def test_live_pool_diverging_from_docs_address_degrades_admin_key(self):
        # REGRESSION-SHAPED TEST: the scorer's own docstring says it was
        # written specifically because the scouting pass found the
        # DefiLlama-Adapters address was NOT the live pool -- confirm a
        # live/expected mismatch is caught, not silently accepted.
        fake = FakeHelpers()
        self._wire(fake, live_pool=ADDR_D)  # diverges from the hardcoded expected LENDING_POOL
        r = self._score(fake)
        self.assertEqual(r["adminKeyScore"], 25)
        self.assertEqual(r["target"], ADDR_D)  # still reports the REAL live address, not the stale expectation

    def test_zero_delay_scores_timelock_zero_even_if_chain_closed(self):
        fake = FakeHelpers()
        self._wire(fake, delay=0)
        r = self._score(fake)
        self.assertEqual(r["timelockScore"], 0)

    # ---- bypass: pool admin is a different Safe, no timelock over the token-upgrade path
    def test_safe_pool_admin_4_of_11_bypasses_the_timelock(self):
        # The live 2026-09-20 shape: 4-of-11 Safe, published before this fix as 55/100/55 -> 69.
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 95, 0))
        self.assertEqual(r["compositeScore"], 55)
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertEqual(r["target"], self.LENDING_POOL)
        notes = " | ".join(r["notes"])
        self.assertIn("4-of-11", notes)
        self.assertIn("does not bind", notes)
        self.assertIn("PROPOSER_ROLE = True, CANCELLER_ROLE = True", notes)
        self.assertIn("6 of its 11 owners hold EXECUTOR_ROLE", notes)
        self.assertIn("checked live 2026-09-20", notes)  # the Radiant-specific cross-exposure note, not the generic one
        self.assertNotIn("$72", notes)  # the exposure figure moves and is deliberately not hardcoded

    def test_safe_pool_admin_threshold_3_is_the_strong_band_boundary(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake, threshold=3, n=5)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 55, 0))
        self.assertEqual(r["compositeScore"], 43)

    def test_safe_pool_admin_threshold_2_scores_medium(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake, threshold=2, n=3)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (50, 35, 0))
        self.assertEqual(r["compositeScore"], 31)

    def test_safe_pool_admin_threshold_1_scores_weak(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake, threshold=1, n=1)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (10, 15, 0))
        self.assertEqual(r["compositeScore"], 9)

    def test_safe_pool_admin_multisig_score_is_capped_at_100(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake, threshold=7, n=20)  # 7*15 + 13*5 = 170 -> 100
        r = self._score(fake)
        self.assertEqual(r["multisigScore"], 100)

    def test_safe_pool_admin_score_does_not_depend_on_the_timelock_delay_value(self):
        # The scored path (onlyPoolAdmin) has no delay whatever the provider-level delay is; a 0s
        # delay only changes the wording of the note about the provider-level path.
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake, delay=0)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 95, 0))
        self.assertIn("0s delay", " | ".join(r["notes"]))

    def test_safe_pool_admin_role_reads_are_disclosure_only(self):
        # Unread hasRole results (None) must not change the score, only the note.
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake)
        for k in [k for k in fake.call_raw_results if k[1] == "hasRole"]:
            del fake.call_raw_results[k]
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 95, 0))
        self.assertIn("(11 unread)", " | ".join(r["notes"]))

    def test_safe_pool_admin_with_diverging_live_pool_keeps_the_25_cap(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake, live_pool=ADDR_D)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (25, 95, 0))
        self.assertEqual(r["target"], ADDR_D)

    # ---- emergency admin: disclosed, never scored
    def test_emergency_admin_is_disclosed_but_not_scored(self):
        fake = FakeHelpers()
        owners = self._wire_safe_pool_admin(fake)
        fake.address_getters[(self.PROVIDER, "getEmergencyAdmin")] = self.EMERGENCY
        fake.safe_results[self.EMERGENCY] = (owners[:5], 1)  # 1-of-5, all five also owners of the pool-admin Safe
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 95, 0, 55))
        notes = " | ".join(r["notes"])
        self.assertIn("1-of-5 Safe", notes)
        self.assertIn("all of its owners are also owners of the pool-admin Safe", notes)
        self.assertIn("availability-only path, disclosed, not scored", notes)

    def test_emergency_admin_owner_overlap_is_not_claimed_when_it_is_not_a_subset(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake)
        fake.address_getters[(self.PROVIDER, "getEmergencyAdmin")] = self.EMERGENCY
        fake.safe_results[self.EMERGENCY] = (_owners(5, start=900), 1)
        r = self._score(fake)
        notes = " | ".join(r["notes"])
        self.assertIn("owner overlap with the pool-admin Safe not established", notes)
        self.assertNotIn("all of its owners are also owners", notes)

    def test_emergency_admin_unread_or_not_a_safe_does_not_change_the_score(self):
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake)
        r = self._score(fake)  # getEmergencyAdmin not wired -> unread
        self.assertEqual(r["compositeScore"], 55)
        self.assertIn("getEmergencyAdmin() unread", " | ".join(r["notes"]))

        fake2 = FakeHelpers()
        self._wire_safe_pool_admin(fake2)
        fake2.address_getters[(self.PROVIDER, "getEmergencyAdmin")] = self.EMERGENCY  # no safe_results entry -> not a Safe
        r2 = self._score(fake2)
        self.assertEqual(r2["compositeScore"], 55)
        self.assertIn("not resolvable as a Safe", " | ".join(r2["notes"]))

    # ---- unread / unresolved authority degrades conservatively, never keeps the timelock credit
    def test_pool_admin_unread_degrades_conservatively(self):
        fake = FakeHelpers()
        self._wire(fake, pool_admin=None)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertEqual(r["compositeScore"], 8)
        self.assertIn("getPoolAdmin() unread", " | ".join(r["notes"]))

    def test_pool_admin_not_a_safe_degrades_conservatively(self):
        fake = FakeHelpers()
        self._wire(fake, pool_admin=self.POOL_ADMIN)  # differs from the timelock, no safe_results entry
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertIn("NOT resolvable as a Gnosis Safe", " | ".join(r["notes"]))

    def test_no_provider_owner_falls_back_to_docs_address_and_degrades(self):
        # provider.owner() unread: the bypass test cannot be made, so the timelock credit is not kept.
        # (Before 2026-09-20 this case scored admin 25 / multisig 100 / timelock 0; multisig 100 on an
        # unread authority was the confident-looking half of that, now (20, 0, 0) like every unread root.)
        fake = FakeHelpers()
        self._wire(fake, provider_owner=None, pool_admin=self.POOL_ADMIN)
        fake.safe_results[self.POOL_ADMIN] = (_owners(11), 4)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertEqual(r["target"], self.LENDING_POOL)  # live_pool still resolved; only provider_owner missing
        self.assertIn("owner() unread", " | ".join(r["notes"]))

    def test_provider_owner_not_answering_get_min_delay_degrades_when_pool_admin_differs(self):
        # Different pool admin, but the provider-level path is unverified (owner is not confirmed as a
        # timelock, or a transient read failure): a bare-EOA owner there would beat the Safe as the weakest
        # path, so the 65/95/0 score is not kept.
        fake = FakeHelpers()
        self._wire_safe_pool_admin(fake)
        del fake.call_raw_results[(self.TIMELOCK, "getMinDelay", ())]
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertIn("did not answer getMinDelay()", " | ".join(r["notes"]))


# --------------------------------------------------------------------- Arbitrum Security Council
class TestScoreArbitrumSecurityCouncilSafe(unittest.TestCase):
    TARGET = "0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641"
    EXECUTOR = "0xCF57572261c7c2BCF21ffD220ea7d1a27D40A827"
    TIMELOCK = "0x34d45e99f7D8c45ed05B5cA72D54bbD1fb3F98f0"
    EXEC_ROLE = RealWeb3.keccak(text="EXECUTOR_ROLE")

    def _wire(self, fake, threshold=9, n=12, has_exec_role=True, delay=691200):
        fake.safe_results[self.TARGET] = (_owners(n), threshold)
        fake.call_raw_results[(self.EXECUTOR, "hasRole", (self.EXEC_ROLE, self.TARGET))] = has_exec_role
        fake.call_raw_results[(self.TIMELOCK, "getMinDelay", ())] = delay

    def test_9_of_12_scores_at_the_top_band(self):
        fake = FakeHelpers()
        self._wire(fake, threshold=9, n=12)
        _patch_helpers(self, fake)

        r = scorers.score_arbitrum_security_council_safe(FakeW3())
        self.assertEqual(r["adminKeyScore"], 55)
        self.assertEqual(r["timelockScore"], 40)

    def test_5_of_n_scores_middle_band(self):
        fake = FakeHelpers()
        self._wire(fake, threshold=5, n=9)
        _patch_helpers(self, fake)

        r = scorers.score_arbitrum_security_council_safe(FakeW3())
        self.assertEqual(r["adminKeyScore"], 45)

    def test_below_5_scores_bottom_band(self):
        fake = FakeHelpers()
        self._wire(fake, threshold=3, n=5)
        _patch_helpers(self, fake)

        r = scorers.score_arbitrum_security_council_safe(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)

    def test_target_itself_unresolvable_as_safe_degrades(self):
        fake = FakeHelpers()
        fake.safe_results[self.TARGET] = None
        _patch_helpers(self, fake)

        r = scorers.score_arbitrum_security_council_safe(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    # ---- ADDED 2026-09-21: modules and guard of the Safe, read live, note only ----
    def _score_with_modules(self, modules, guard=None):
        fake = FakeHelpers()
        self._wire(fake)
        fake.modules[self.TARGET] = modules
        if guard:
            fake.guards[self.TARGET] = guard
        _patch_helpers(self, fake)
        return scorers.score_arbitrum_security_council_safe(FakeW3())

    def test_the_upgrade_executor_module_is_disclosed_and_moves_no_score(self):
        base = self._score_with_modules([])
        r = self._score_with_modules([RealWeb3.to_checksum_address(self.EXECUTOR)])
        self.assertTrue(any("Arbitrum L2 UpgradeExecutor" in n for n in r["notes"]))
        self.assertFalse(any(n.startswith("WARNING") for n in r["notes"]))
        vec = lambda x: tuple(x[k] for k in ("adminKeyScore", "multisigScore", "timelockScore", "compositeScore"))
        self.assertEqual(vec(r), vec(base))

    def test_no_module_is_stated_as_such(self):
        r = self._score_with_modules([])
        self.assertTrue(any("no module and no guard" in n for n in r["notes"]))

    def test_an_unknown_module_is_a_warning_and_still_moves_no_score(self):
        r = self._score_with_modules([RealWeb3.to_checksum_address("0x" + "9f" * 20)])
        self.assertTrue(any(n.startswith("WARNING") and "NOT ANALYZED" in n for n in r["notes"]))
        self.assertEqual(r["adminKeyScore"], 55)  # a note, never a score input

    def test_an_unreadable_module_list_never_claims_a_clean_result(self):
        r = self._score_with_modules(None)
        self.assertTrue(any("could not be read" in n for n in r["notes"]))
        self.assertFalse(any("no module and no guard" in n for n in r["notes"]))


# --------------------------------------------------------------------- Aave V3 Arbitrum
class TestScoreAaveV3PoolArbitrum(unittest.TestCase):
    PROVIDER = "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"
    ACL_MANAGER = "0xa72636CbcAa8F5FF95B2cc47F3CDEe83F3294a0B"
    DEFAULT_ADMIN_ROLE = "0x0000000000000000000000000000000000000000000000000000000000000000"

    def _wire(self, fake, delay=86400, guardian_owners=None, guardian_threshold=5, acl_has_role=True):
        fake.address_getters[(self.PROVIDER, "owner")] = ADDR_A  # executor
        fake.call_raw_results[(self.PROVIDER, "getACLAdmin", ())] = ADDR_A
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B  # payloads_controller
        fake.address_getters[(ADDR_B, "owner")] = ADDR_A  # closes the loop
        fake.call_raw_results[(ADDR_B, "getExecutorSettingsByAccessControl", (1,))] = (ADDR_A, delay)
        fake.call_raw_results[(ADDR_B, "guardian", ())] = ADDR_C
        if guardian_owners is not None:
            fake.safe_results[ADDR_C] = (guardian_owners, guardian_threshold)
        fake.call_raw_results[(self.ACL_MANAGER, "hasRole", (self.DEFAULT_ADMIN_ROLE, ADDR_A))] = acl_has_role

    def test_closed_chain_with_acl_role_scores_strong(self):
        fake = FakeHelpers()
        self._wire(fake, guardian_owners=_owners(9), guardian_threshold=5)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_pool_arbitrum(FakeW3())
        self.assertEqual(r["adminKeyScore"], 65)
        self.assertEqual(r["timelockScore"], 50)
        self.assertEqual(r["crossExposureScore"], 100)

    def test_acl_role_missing_degrades_despite_closed_loop(self):
        fake = FakeHelpers()
        self._wire(fake, acl_has_role=False)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_pool_arbitrum(FakeW3())
        self.assertEqual(r["adminKeyScore"], 30)

    def test_guardian_committee_identical_to_base_flags_shared_exposure(self):
        # Exact owner set hardcoded INSIDE score_aave_v3_pool_arbitrum()
        # (local, not module-level -- confirmed by reading the real
        # function body) as the dated 2026-09-17 Base snapshot.
        base_owners = [
            "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
            "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
            "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
            "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
            "0x4C30E33758216aD0d676419c21CB8D014C68099f",
        ]
        fake = FakeHelpers()
        self._wire(fake, guardian_owners=base_owners, guardian_threshold=5)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_pool_arbitrum(FakeW3())
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertTrue(any("IDENTICAL to Base" in n for n in r["notes"]))

    def test_broken_loop_degrades_admin_key(self):
        fake = FakeHelpers()
        self._wire(fake)
        fake.address_getters[(ADDR_B, "owner")] = ADDR_D  # breaks the loop back to executor
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_pool_arbitrum(FakeW3())
        self.assertEqual(r["adminKeyScore"], 30)



# ===================================================================== ADDED 2026-09-19
# Tests for the 4 targets added in the 2026-09-19 maintenance run.
class TestScoreCompoundV3CometArbitrumUsdc(unittest.TestCase):
    TARGET = "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf"
    RECEIVER = "0x42480C37B249e33aABaf4c22B20235656bd38068"
    L1_TL = "0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"

    def _wire(self, fake, receiver=None, gov=None, local=None, admin_owner=None, delay=86400):
        fake.address_getters[(self.TARGET, "governor")] = ADDR_A
        fake.slots[(self.TARGET, scorers.EIP1967_ADMIN_SLOT)] = ADDR_B
        fake.address_getters[(ADDR_B, "owner")] = admin_owner or ADDR_A
        fake.call_raw_results[(ADDR_A, "delay", ())] = delay
        fake.address_getters[(ADDR_A, "admin")] = receiver or self.RECEIVER
        fake.address_getters[(receiver or self.RECEIVER, "govTimelock")] = gov or self.L1_TL
        fake.address_getters[(receiver or self.RECEIVER, "localTimelock")] = local or ADDR_A
        fake.address_getters[(self.TARGET, "pauseGuardian")] = ADDR_C
        fake.safe_results[ADDR_C] = (_owners(9), 5)

    def test_closed_chain_scores_like_base_sibling(self):
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())
        # UPDATED 2026-09-25 (d6dca5e): a resolved pauseGuardian Safe (any Safe, wired by default in
        # _wire above) now caps timelockScore at 60, not 65 -- matches L1's twin Comet scorer's own
        # already-existing cap for the identical bypass shape. adminKeyScore/multisigScore unaffected.
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (75, 100, 60, 78))

    def test_pause_guardian_committee_shared_with_l1_and_base_folds_cross_exposure_to_80(self):
        # ADDED 2026-09-20 (real finding): the same 9-signer 5-of-9 pauseGuardian committee sits on Ethereum L1 and Base.
        fake = FakeHelpers(); self._wire(fake)
        fake.safe_results[ADDR_C] = (sorted(RealWeb3.to_checksum_address(a) for a in scorers._KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20), 5)
        _patch_helpers(self, fake)
        r = scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertEqual(r["compositeScore"], 78)  # UPDATED 2026-09-25 (d6dca5e): timelockScore capped at 60, not 65; crossExposure is still not a composite input
        self.assertIn("IDENTICAL, as an exact set", " ".join(r["notes"]))

    def test_unrelated_or_unresolved_guardian_keeps_cross_exposure_100(self):
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        self.assertEqual(scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())["crossExposureScore"], 100)
        fake.safe_results[ADDR_C] = None
        self.assertEqual(scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())["crossExposureScore"], 100)

    def test_wrong_bridge_receiver_degrades(self):
        fake = FakeHelpers(); self._wire(fake, receiver=ADDR_D); _patch_helpers(self, fake)
        r = scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (35, 0))

    def test_proxy_admin_owned_elsewhere_degrades(self):
        fake = FakeHelpers(); self._wire(fake, admin_owner=ADDR_D); _patch_helpers(self, fake)
        r = scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 35)

    def test_wrong_l1_timelock_degrades(self):
        fake = FakeHelpers(); self._wire(fake, gov=ADDR_D); _patch_helpers(self, fake)
        r = scorers.score_compound_v3_comet_arbitrum_usdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 35)


class TestScorePendleV2Arbitrum(unittest.TestCase):
    ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
    MF = "0x49F2f7002669E0e4425Fa0203975625Ab4af3143"
    GP = "0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e"

    def _wire(self, fake, owners=None, threshold=3, gp_admin=True, mf_owner=None):
        fake.address_getters[(self.ROUTER, "owner")] = ADDR_A
        fake.slots[(self.MF, scorers.EIP1967_ADMIN_SLOT)] = ADDR_B
        fake.address_getters[(ADDR_B, "owner")] = ADDR_A
        fake.address_getters[(self.MF, "owner")] = mf_owner or self.GP
        fake.call_raw_results[(self.GP, "hasRole", (b"\x00" * 32, ADDR_A))] = gp_admin
        fake.safe_results[ADDR_A] = (owners or _owners(5), threshold)

    def test_known_shared_committee_scores_the_flat_cross_ecosystem_80(self):
        known = [RealWeb3.to_checksum_address(o) for o in scorers._PENDLE_GOV_OWNERS_2026_09_19]
        fake = FakeHelpers(); self._wire(fake, owners=known); _patch_helpers(self, fake)
        r = scorers.score_pendle_v2_arbitrum(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 55, 0, 43))
        # Shared with 2 tracked groups (Plasma + Robinhood) but flat 80 like every other ecosystem (convention of
        # 2026-09-20; the per-snapshot 60 was a disclosed deviation, closed 2026-09-21).
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertEqual(sum("IDENTICAL to the tracked" in n for n in r["notes"]), 2)

    def test_different_committee_keeps_cross_exposure_100(self):
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_pendle_v2_arbitrum(FakeW3())
        self.assertEqual(r["crossExposureScore"], 100)

    def test_governance_proxy_admin_missing_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, gp_admin=False); _patch_helpers(self, fake)
        r = scorers.score_pendle_v2_arbitrum(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_factory_owner_not_governance_proxy_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, mf_owner=ADDR_D); _patch_helpers(self, fake)
        r = scorers.score_pendle_v2_arbitrum(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)


class TestScoreFluidLiquidityArbitrum(unittest.TestCase):
    LIQ = "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"
    PROP = "0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e"
    EXEC = "0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"
    ZERO = "0x0000000000000000000000000000000000000000"

    def _wire(self, fake, signers=None, required=6, exec_threshold=3, zero_admin=False, delay=86400):
        fake.address_getters[(self.LIQ, "getAdmin")] = ADDR_A
        fake.slots[(self.LIQ, scorers.EIP1967_ADMIN_SLOT)] = ADDR_A
        fake.call_raw_results[(ADDR_A, "getMinDelay", ())] = delay
        k = lambda n: RealWeb3.keccak(text=n)
        fake.call_raw_results[(ADDR_A, "hasRole", (k("TIMELOCK_ADMIN_ROLE"), ADDR_A))] = True
        fake.call_raw_results[(ADDR_A, "hasRole", (k("TIMELOCK_ADMIN_ROLE"), self.ZERO))] = zero_admin
        fake.call_raw_results[(ADDR_A, "hasRole", (k("PROPOSER_ROLE"), self.PROP))] = True
        fake.call_raw_results[(ADDR_A, "hasRole", (k("EXECUTOR_ROLE"), self.EXEC))] = True
        fake.call_raw_results[(self.PROP, "requiredSigners", ())] = required
        fake.call_raw_results[(self.PROP, "signers", ())] = signers or _owners(12)
        fake.safe_results[self.EXEC] = (_owners(5, start=100), exec_threshold)

    def test_live_shape_with_known_committee(self):
        known = [RealWeb3.to_checksum_address(o) for o in scorers._FLUID_TEAM_SIGNERS_2026_09_19]
        fake = FakeHelpers(); self._wire(fake, signers=known); _patch_helpers(self, fake)
        r = scorers.score_fluid_liquidity_arbitrum(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 55, 55, 59))
        self.assertEqual(r["crossExposureScore"], 80)

    def test_weaker_executor_sets_multisig_ceiling(self):
        fake = FakeHelpers(); self._wire(fake, exec_threshold=2); _patch_helpers(self, fake)
        r = scorers.score_fluid_liquidity_arbitrum(FakeW3())
        self.assertEqual(r["adminKeyScore"], 50)
        self.assertEqual(r["multisigScore"], 45)  # 2*15 + 3*5, lower than the 6-of-12 proposer's 100

    def test_open_timelock_admin_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, zero_admin=True); _patch_helpers(self, fake)
        r = scorers.score_fluid_liquidity_arbitrum(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_zero_delay_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, delay=0); _patch_helpers(self, fake)
        r = scorers.score_fluid_liquidity_arbitrum(FakeW3())
        self.assertEqual(r["timelockScore"], 0)


class TestScoreUniswapV3FactoryArbitrum(unittest.TestCase):
    FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    L1_TL = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"

    def _wire(self, fake, owner=None, l1_ok=True):
        alias = scorers.arbitrum_l1_l2_alias(self.L1_TL)
        fake.address_getters[(self.FACTORY, "owner")] = ADDR_A
        fake.address_getters[(ADDR_A, "owner")] = owner or alias
        fake.address_getters[(ADDR_A, "feeSetter")] = alias
        fake.call_raw_results[(self.L1_TL, "delay", ())] = 172800 if l1_ok else None
        fake.call_raw_results[(self.L1_TL, "admin", ())] = ADDR_B
        fake.call_raw_results[(ADDR_B, "quorumVotes", ())] = 40_000_000 * 10**18

    def test_alias_and_l1_reconfirmed_scores_85(self):
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_uniswap_v3_factory_arbitrum(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (80, 100, 75, 85))

    def test_alias_recomputed_independently(self):
        # Arbitrum alias = L1 address + 0x1111000000000000000000000000000000001111 (mod 2^160)
        expected = RealWeb3.to_checksum_address(hex((int(self.L1_TL, 16) + 0x1111000000000000000000000000000000001111) % (1 << 160)))
        self.assertEqual(scorers.arbitrum_l1_l2_alias(self.L1_TL).lower(), expected.lower())

    def test_non_alias_owner_degrades_to_bare_eoa_equivalent(self):
        fake = FakeHelpers(); self._wire(fake, owner=ADDR_D); _patch_helpers(self, fake)
        r = scorers.score_uniswap_v3_factory_arbitrum(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (5, 0, 0))

    def test_failed_l1_read_degrades(self):
        fake = FakeHelpers(); self._wire(fake, l1_ok=False); _patch_helpers(self, fake)
        r = scorers.score_uniswap_v3_factory_arbitrum(FakeW3())
        self.assertEqual(r["adminKeyScore"], 5)

    def test_confirmed_shared_l1_timelock_root_folds_cross_exposure_to_80_and_leaves_the_composite(self):
        # 2026-09-20: one L1 Timelock roots 11 tracked Uniswap targets on 5 ecosystems, so the root confirmed live folds
        # to the flat cross-ecosystem 80. Composite ignores crossExposure: still 85.
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_uniswap_v3_factory_arbitrum(FakeW3())
        self.assertEqual((r["crossExposureScore"], r["compositeScore"]), (80, 85))
        self.assertIn(scorers._UNISWAP_SHARED_ROOT_NOTE, r["notes"])
        self.assertNotIn(scorers._CROSS_EXPOSURE_NOTE, r["notes"])

    def test_degraded_paths_never_assert_an_unverified_shared_root(self):
        for kwargs in ({"owner": ADDR_D}, {"l1_ok": False}):
            fake = FakeHelpers(); self._wire(fake, **kwargs); _patch_helpers(self, fake)
            r = scorers.score_uniswap_v3_factory_arbitrum(FakeW3())
            self.assertEqual(r["crossExposureScore"], 100, kwargs)
            self.assertNotIn(scorers._UNISWAP_SHARED_ROOT_NOTE, r["notes"], kwargs)
            self.assertIn(scorers._CROSS_EXPOSURE_NOTE, r["notes"], kwargs)


# ------------------------------------------------------- GMX V1 Vault (index 9)
# ADDED 2026-09-20 (maintenance run) with score_gmx_v1_vault(). The branch that
# matters is the instant admin-replacement path: Timelock.setAdmin(address) is
# onlyTokenManager in GMX's own Timelock.sol, so a SECOND committee can replace
# the admin with no delay. Both halves are tested: with the path (the live
# shape) and without it (tokenManager == admin, or not a Safe), so the penalty
# is exercised in both directions rather than only pinned to today's numbers.
class TestScoreGmxV1Vault(unittest.TestCase):
    TARGET = "0x489ee077994B6658eAfA855C308275EAd8097C4A"
    GOV = ADDR_A          # the GMX Timelock
    ADMIN_SAFE = ADDR_B   # Timelock.admin()
    TM_SAFE = ADDR_C      # Timelock.tokenManager()
    V2_TIMELOCK = "0x2Dd99f39f58445CDDC57AA5E0DB2C367335BBD44"

    _KEEP = object()   # "leave the default", so None can mean "unreadable"

    def _wire(self, fake, gov=_KEEP, buffer_s=86400, admin=_KEEP, token_manager=_KEEP,
              admin_safe=(4, 6), tm_safe=(5, 8), v2_roles=True, shared=2):
        gov = self.GOV if gov is self._KEEP else gov
        admin = self.ADMIN_SAFE if admin is self._KEEP else admin
        token_manager = self.TM_SAFE if token_manager is self._KEEP else token_manager
        fake.address_getters[(self.TARGET, "gov")] = gov
        fake.call_raw_results[(self.TARGET, "isSwapEnabled", ())] = False
        fake.call_raw_results[(self.TARGET, "isLeverageEnabled", ())] = False
        if gov:
            fake.call_raw_results[(gov, "buffer", ())] = buffer_s
            fake.address_getters[(gov, "admin")] = admin
            fake.address_getters[(gov, "tokenManager")] = token_manager
        admin_owner_count = admin_safe[1] if admin_safe else 0
        if admin_safe and admin:
            th, n = admin_safe
            fake.safe_results[admin] = (_owners(n, start=1), th)
        # When tokenManager IS the admin there is only one committee: do not
        # overwrite the admin Safe's own owner set with a second one.
        if tm_safe and token_manager and token_manager != admin:
            th, n = tm_safe
            # start so that exactly `shared` owner addresses are common with
            # the admin Safe's owners (which run 1..admin_owner_count).
            fake.safe_results[token_manager] = (_owners(n, start=max(1, admin_owner_count - shared + 1)), th)
        for role in ("PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE"):
            fake.call_raw_results[(self.V2_TIMELOCK, "hasRole", (RealWeb3.keccak(text=role), token_manager))] = v2_roles

    def test_live_shape_two_safes_with_instant_admin_swap(self):
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        # adminKey 55 (instant swap), multisig = weaker of 4-of-6 (70) and
        # 5-of-8 (90) = 70, timelock 60 - 15 = 45, cross 80 (shared committee).
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["crossExposureScore"], r["compositeScore"]),
            (55, 70, 45, 80, 57),
        )

    def test_no_instant_swap_when_token_manager_is_the_admin(self):
        fake = FakeHelpers()
        self._wire(fake, token_manager=self.ADMIN_SAFE)
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        # One committee only: no penalty on adminKey or timelock, and the
        # multisig score stays the admin Safe's own 4-of-6 = 70.
        self.assertEqual((r["adminKeyScore"], r["timelockScore"], r["multisigScore"]), (65, 60, 70))

    def test_token_manager_not_a_safe_leaves_admin_safe_alone(self):
        fake = FakeHelpers()
        self._wire(fake, tm_safe=None)
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"], r["multisigScore"]), (65, 60, 70))

    def test_weaker_token_manager_safe_drags_multisig_down(self):
        fake = FakeHelpers()
        self._wire(fake, tm_safe=(1, 3))          # 1-of-3 -> 15 + 2*5 = 25
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(r["multisigScore"], 25)

    def test_short_buffer_scores_lower_than_a_day(self):
        fake = FakeHelpers()
        self._wire(fake, buffer_s=3600)           # 1h -> 30, minus 15 for the swap
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(r["timelockScore"], 15)

    def test_no_buffer_scores_zero_timelock(self):
        fake = FakeHelpers()
        self._wire(fake, buffer_s=None)
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(r["timelockScore"], 0)

    def test_unreadable_gov_degrades_and_assumes_nothing(self):
        fake = FakeHelpers()
        self._wire(fake, gov=None)   # gov() unreadable this run
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["crossExposureScore"]), (20, 0, 0, 100))

    def test_admin_not_a_safe_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, admin_safe=None)
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_cross_exposure_stays_100_when_the_committee_holds_no_v2_role(self):
        fake = FakeHelpers()
        self._wire(fake, v2_roles=False)
        _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertTrue(any("no role held by the tokenManager Safe" in n for n in r["notes"]))

    def test_shared_signer_count_is_reported_not_guessed(self):
        fake = FakeHelpers(); self._wire(fake, shared=0); _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertTrue(any("signers shared between the 2 Safes: 0 of 6 / 8" in n for n in r["notes"]))

    def test_role_hashes_are_recomputed_here_not_copied(self):
        # The scorer hashes PROPOSER_ROLE/EXECUTOR_ROLE/CANCELLER_ROLE inline;
        # the fakes above are keyed on hashes recomputed in this file, so a
        # changed hashing path would miss the dispatch and drop cross to 100.
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(r["crossExposureScore"], 80)

    def test_wind_down_flags_are_disclosed_not_scored(self):
        fake = FakeHelpers(); self._wire(fake); _patch_helpers(self, fake)
        r = scorers.score_gmx_v1_vault(FakeW3())
        self.assertTrue(any("isSwapEnabled() = False" in n and "NOT empty" in n for n in r["notes"]))
        # Disclosure only: the same scores come out whatever the two flags say.
        fake2 = FakeHelpers(); self._wire(fake2)
        fake2.call_raw_results[(self.TARGET, "isSwapEnabled", ())] = True
        fake2.call_raw_results[(self.TARGET, "isLeverageEnabled", ())] = True
        _patch_helpers(self, fake2)
        r2 = scorers.score_gmx_v1_vault(FakeW3())
        self.assertEqual(r2["compositeScore"], r["compositeScore"])


class TestScoreAllIncludesNewTargetsAfterExistingOnes(unittest.TestCase):
    def test_order_preserves_testnet_indices_0_to_4(self):
        names = [f.__name__ for f in scorers.SIMPLE_SCORERS]
        self.assertEqual(names[:5], ["score_gmx_v2_rolestore", "score_camelot_ammv3_factory", "score_radiant_lendingpool",
                                     "score_arbitrum_security_council_safe", "score_aave_v3_pool_arbitrum"])
        self.assertEqual(names[5:9], ["score_compound_v3_comet_arbitrum_usdc", "score_pendle_v2_arbitrum",
                                      "score_fluid_liquidity_arbitrum", "score_uniswap_v3_factory_arbitrum"])
        # UPDATED 2026-09-25: the tenth target (score_gmx_v1_vault) is still appended right after the nine
        # already pushed to the testnet oracle, and the 3 targets added 2026-09-25 are appended LAST of all,
        # so indices 0-9 keep their meaning. Asserting the exact tail, not just a prefix, is the point.
        self.assertEqual(names[9:], ["score_gmx_v1_vault", "score_dolomite_margin_arbitrum",
                                     "score_usdai_bridge_adapter_arbitrum", "score_gains_network_diamond_arbitrum"])


# ------------------------------------------------------- Dolomite Margin (index 10)
# ADDED 2026-09-25: closes the gap the 2026-09-20 scouting note left open ("Scouted,
# traced, NOT scored") -- the DEFAULT_ADMIN_ROLE holder on DolomiteMargin.owner() is
# now confirmed as a real 2-of-3 Safe, and owner().secondsTimeLocked() = 300s.
class TestScoreDolomiteMarginArbitrum(unittest.TestCase):
    MARGIN = "0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072"
    OWNER = ADDR_A
    ADMIN_ROLE_HOLDER = "0xa75c21C5BE284122a87A37a76cc6C4DD3E55a1D4"
    _KEEP = object()

    def _wire(self, fake, owner=_KEEP, seconds_locked=300, has_role=True, safe=(2, 3)):
        owner = self.OWNER if owner is self._KEEP else owner
        fake.address_getters[(self.MARGIN, "owner")] = owner
        if owner:
            fake.call_raw_results[(owner, "secondsTimeLocked", ())] = seconds_locked
            fake.call_raw_results[(owner, "hasRole", (b"\x00" * 32, self.ADMIN_ROLE_HOLDER))] = has_role
        if safe and has_role:
            th, n = safe
            fake.safe_results[self.ADMIN_ROLE_HOLDER] = (_owners(n, start=1), th)

    def _score(self, fake):
        _patch_helpers(self, fake)
        return scorers.score_dolomite_margin_arbitrum(FakeW3())

    def test_live_shape_2_of_3_safe_with_300s_delay(self):
        fake = FakeHelpers(); self._wire(fake)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (50, 35, 30))
        self.assertEqual(r["compositeScore"], 40)
        self.assertEqual(r["target"], self.MARGIN)

    def test_a_day_or_longer_delay_would_score_the_full_band(self):
        # Regression guard: confirms the 30/60 split is keyed on the 86400s threshold, not hardcoded to 300.
        fake = FakeHelpers(); self._wire(fake, seconds_locked=86400)
        r = self._score(fake)
        self.assertEqual(r["timelockScore"], 60)

    def test_no_delay_read_scores_timelock_zero(self):
        fake = FakeHelpers(); self._wire(fake, seconds_locked=None)
        r = self._score(fake)
        self.assertEqual(r["timelockScore"], 0)

    def test_owner_unread_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, owner=None)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_admin_role_not_held_by_the_expected_safe_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, has_role=False)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_admin_role_holder_not_a_safe_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, safe=None)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_threshold_1_scores_weak(self):
        fake = FakeHelpers(); self._wire(fake, safe=(1, 3))
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (10, 25))  # 1*15 + 2*5

    def test_threshold_3_scores_strong(self):
        fake = FakeHelpers(); self._wire(fake, safe=(3, 5))
        r = self._score(fake)
        self.assertEqual(r["adminKeyScore"], 65)

    def test_does_not_reference_the_old_dead_pool_or_its_1day_delayed_multisig(self):
        # Regression guard for the correction this closes: the OLD DelayedMultiSig
        # (0xE412991F..., 86400s delay) governs a DIFFERENT, near-empty pool
        # (0x6a769862...) and must never appear in this scorer's source.
        import inspect
        src = inspect.getsource(scorers.score_dolomite_margin_arbitrum)
        self.assertNotIn("0xE412991Fb026df586C2f2F9EE06ACaD1A34f585B", src)
        self.assertNotIn("0x6a76986201E1906eb8d887Bb4Ad74b55888617af", src)


# ------------------------------------------------------- USD AI (index 11)
# ADDED 2026-09-25: closes the gap the 2026-09-19 "considered, not added" note left
# open -- the _bridgeAdapter's own owner() chain (a 3-of-3 Safe, no timelock) is now
# traced, so the mint/burn authority is scored instead of skipped.
class TestScoreUsdaiBridgeAdapterArbitrum(unittest.TestCase):
    ADAPTER = "0xffA10065Ce1d1C42FABc46e06B84Ed8FfEb4baE5"
    _KEEP = object()

    def _wire(self, fake, owner=_KEEP, safe=(3, 3)):
        owner = ADDR_A if owner is self._KEEP else owner
        fake.address_getters[(self.ADAPTER, "owner")] = owner
        if safe and owner:
            th, n = safe
            fake.safe_results[owner] = (_owners(n, start=1), th)

    def _score(self, fake):
        _patch_helpers(self, fake)
        return scorers.score_usdai_bridge_adapter_arbitrum(FakeW3())

    def test_live_shape_3_of_3_safe_no_timelock(self):
        fake = FakeHelpers(); self._wire(fake)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 45, 0))
        self.assertEqual(r["compositeScore"], 40)
        self.assertEqual(r["target"], self.ADAPTER)
        self.assertIn(scorers._USDAI_UPGRADE_TIMELOCK, " ".join(r["notes"]))

    def test_owner_unread_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, owner=None)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_owner_not_a_safe_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, safe=None)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_threshold_2_scores_medium(self):
        fake = FakeHelpers(); self._wire(fake, safe=(2, 3))
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (50, 35))

    def test_threshold_1_scores_weak(self):
        fake = FakeHelpers(); self._wire(fake, safe=(1, 3))
        r = self._score(fake)
        self.assertEqual(r["adminKeyScore"], 10)


# ------------------------------------------------------- Gains Network gTrade Diamond (index 12)
# ADDED 2026-09-25: closes the gap the 2026-09-20 scouting note left open ("Left for
# a next run rather than scored from one hop") -- the real weakest path is a 4th,
# previously-missed GOV_EMERGENCY_TIMELOCK holder set: a bare EOA can propose alone,
# only 10h stand between that and execution by the weaker of two Safes.
class TestScoreGainsNetworkDiamondArbitrum(unittest.TestCase):
    TIMELOCK = "0x893FCf48D56CE2e92AFB4a085941135243D5E75a"
    SAFE_4_7 = "0xc07EEd650aB255190CA9766162CfB47cFDf72f3a"
    SAFE_2_4 = "0xe8997C502fCD0729B462FCA19A50cF0DAEA0cAB5"
    EOA = RealWeb3.to_checksum_address("0x80Fd0AcCc8dA81b0852d2dCA17B5DdaB68f22253")

    def _wire(self, fake, delay=36000, proposers=None, executors=None, eoa_is_eoa=True):
        proposers = {self.SAFE_4_7, self.SAFE_2_4, self.EOA} if proposers is None else proposers
        executors = {self.SAFE_4_7, self.SAFE_2_4} if executors is None else executors
        fake.call_raw_results[(self.TIMELOCK, "getMinDelay", ())] = delay
        for a in (self.SAFE_4_7, self.SAFE_2_4, self.EOA):
            fake.call_raw_results[(self.TIMELOCK, "hasRole", (RealWeb3.keccak(text="PROPOSER_ROLE"), a))] = a in proposers
            fake.call_raw_results[(self.TIMELOCK, "hasRole", (RealWeb3.keccak(text="EXECUTOR_ROLE"), a))] = a in executors
        fake.safe_results[self.SAFE_4_7] = (_owners(7, start=1), 4)
        fake.safe_results[self.SAFE_2_4] = (_owners(4, start=100), 2)
        fake.eoa_results[self.EOA] = eoa_is_eoa

    def _score(self, fake):
        _patch_helpers(self, fake)
        return scorers.score_gains_network_diamond_arbitrum(FakeW3())

    def test_live_shape_bare_eoa_is_the_weakest_proposer(self):
        fake = FakeHelpers(); self._wire(fake)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (10, 0, 0))
        self.assertEqual(r["compositeScore"], 4)
        self.assertEqual(r["target"], scorers._GAINS_DIAMOND)
        notes = " | ".join(r["notes"])
        self.assertIn("36000s", notes)
        self.assertIn("10h", notes)

    def test_without_the_eoa_the_weaker_safe_sets_the_score(self):
        fake = FakeHelpers(); self._wire(fake, proposers={self.SAFE_4_7, self.SAFE_2_4})
        r = self._score(fake)
        # weakest PROPOSER initiator is the 2-of-4 Safe: 50/40 (2*15 + 2*5).
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (50, 40))

    def test_zero_delay_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, delay=0)
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_no_readable_proposer_is_conservative(self):
        fake = FakeHelpers(); self._wire(fake, proposers=set())
        r = self._score(fake)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_eoa_executor_membership_is_disclosed(self):
        fake = FakeHelpers(); self._wire(fake, executors={self.SAFE_4_7, self.SAFE_2_4, self.EOA})
        r = self._score(fake)
        self.assertTrue(any("single-key finish" in n and ": True" in n for n in r["notes"]))
        fake2 = FakeHelpers(); self._wire(fake2)
        r2 = self._score(fake2)
        self.assertTrue(any("single-key finish" in n and ": False" in n for n in r2["notes"]))

    def test_admin_safe_timelock_admin_role_is_disclosed_not_scored(self):
        fake = FakeHelpers(); self._wire(fake)
        r = self._score(fake)
        self.assertTrue(any("TIMELOCK_ADMIN_ROLE on all three" in n for n in r["notes"]))
        self.assertEqual(r["compositeScore"], 4)  # disclosure only, no score change


if __name__ == "__main__":
    unittest.main()
