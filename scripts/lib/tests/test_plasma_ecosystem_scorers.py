"""
Unit tests for chains/plasma-ecosystem/scorers.py's scoring-decision logic.
Plasma is this project's newest ecosystem (added 2026-09-18, see
`data/finding_2026-09-18-competitive-positioning-cross-chain-overlap.md`
for why) -- previously zero test coverage.

Same approach as `test_arbitrum_ecosystem_scorers.py`/
`test_base_ecosystem_scorers.py`: monkeypatch the read-primitive names this
file imports directly (`read_address_getter`, `call_raw`,
`read_slot_as_address`, `safe_owners_and_threshold`) with small
dict-dispatch fakes, rather than mocking Web3.py's contract-call machinery.
Two scorers here also call `w3.eth.get_code`/`w3.eth.call` directly (the
validator-set self-ID raw-selector call, and every target's bytecode-size
note) -- faked via a small `FakeW3` below.
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
scorers = _load_module("aro_test_plasma_ecosystem_scorers", "chains/plasma-ecosystem/scorers.py")

# The price-authority walk (2026-10-04) reads many feeds on a real chain; it has its own offline test
# (scripts/lib/tests/test_price_authority.py), so the scorer bodies here see a fixed 100.
_PA_NAMES = ("for_aave", "for_aave_v2", "for_comet", "for_morpho_v1", "for_morpho_v2", "for_gmx_v2", "for_gmx_v1", "for_euler_factory", "for_euler_earn", "for_fluid")
_PA_ORIG = {}


def setUpModule():
    for n in _PA_NAMES:
        _PA_ORIG[n] = getattr(scorers.price_authority, n)
        setattr(scorers.price_authority, n, lambda *a, **k: 100)


def tearDownModule():
    for n, f in _PA_ORIG.items():
        setattr(scorers.price_authority, n, f)


def _addr(n):
    return RealWeb3.to_checksum_address("0x" + hex(n)[2:].zfill(40))


def _owners(n, start=1):
    return [_addr(i) for i in range(start, start + n)]


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}
        self.call_raw_results = {}
        self.safe_results = {}
        self.slot_results = {}
        self.code_sizes = {}       # address (lowercased) -> int
        self.raw_call_results = {}  # (to lowercased, data) -> bytes
        self.modules = {}           # safe address -> list of module addresses, default [] (ADDED 2026-09-21)
        self.guards = {}            # safe address -> guard address, default the zero address

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def read_modules(self, w3, address, retries=4):
        return self.modules.get(address, [])

    def read_guard(self, w3, address, retries=4):
        return self.guards.get(address, "0x" + "0" * 40)


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "safe_owners_and_threshold", "read_slot_as_address", "read_modules", "read_guard"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


class FakeEth:
    def __init__(self, fake):
        self.fake = fake

    def get_code(self, address):
        return b"\x00" * self.fake.code_sizes.get(address.lower(), 0)

    def call(self, tx):
        key = (tx["to"].lower(), tx["data"])
        return self.fake.raw_call_results.get(key, b"")


class FakeW3:
    def __init__(self, fake):
        self.eth = FakeEth(fake)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


AQUILA = "0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48"
AQUILA_SAFE = _addr(1)
PROVIDER = "0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9"
EXECUTOR = _addr(2)
PAYLOADS = _addr(3)
GUARDIAN = _addr(4)
ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
MARKET_FACTORY_V6 = "0x84A240Fa784E7F03CB99BA3716065961c5d0D531"
PENDLE_SAFE = _addr(5)
OFT = "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"
ETHENA_SAFE = _addr(6)
ETHENA_PENDING = _addr(7)

# The real, known Aave-guardian and Ethena-L1 committees this file's scorers
# compare against -- pulled directly from the module under test so a future
# change to those constants doesn't silently desync this test file from it.
KNOWN_AAVE_GUARDIAN = sorted(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
KNOWN_ETHENA_L1 = sorted(scorers._KNOWN_ETHENA_L1_SAFE_OWNERS_2026_09_18)
KNOWN_PENDLE_ROBINHOOD = sorted(scorers._KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20)
KNOWN_EULER_DAO = sorted(scorers._KNOWN_EULER_DAO_SIGNERS_2026_09_19)


class TestScoreValidatorSetAuthority(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def test_3_of_4_safe_no_timelock(self):
        self.fake.code_sizes[AQUILA.lower()] = 109
        self.fake.raw_call_results[(AQUILA.lower(), "0x54fd4d50")] = b"plasma-validator-set/v1".ljust(32, b"\x00")
        self.fake.call_raw_results[(AQUILA, "validatorCount", ())] = 10
        self.fake.address_getters[(AQUILA, "owner")] = AQUILA_SAFE
        self.fake.safe_results[AQUILA_SAFE] = (_owners(4), 3)
        self.fake.call_raw_results[(AQUILA_SAFE, "getMinDelay", ())] = None  # confirmed NOT a timelock

        result = scorers.score_validator_set_authority(self.w3)

        self.assertEqual(result["adminKeyScore"], 50)
        self.assertEqual(result["multisigScore"], 3 * 15 + 1 * 5)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("plasma-validator-set/v1" in n for n in result["notes"]))

    def test_owner_not_a_safe_degrades(self):
        self.fake.code_sizes[AQUILA.lower()] = 109
        self.fake.address_getters[(AQUILA, "owner")] = _addr(9)
        self.fake.safe_results[_addr(9)] = None

        result = scorers.score_validator_set_authority(self.w3)

        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))

    def test_self_id_raw_call_failure_is_none_not_a_crash(self):
        self.fake.code_sizes[AQUILA.lower()] = 109
        self.fake.address_getters[(AQUILA, "owner")] = AQUILA_SAFE
        self.fake.safe_results[AQUILA_SAFE] = (_owners(4), 3)
        # no raw_call_results entry -> FakeEth.call returns b"" -> decode of b"" is ""
        result = scorers.score_validator_set_authority(self.w3)
        self.assertIn("self-ID getter", " ".join(result["notes"]))


class TestScoreAaveV3PoolPlasma(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire_closed_chain(self, guardian_owners):
        self.fake.address_getters[(PROVIDER, "owner")] = EXECUTOR
        self.fake.address_getters[(EXECUTOR, "owner")] = PAYLOADS
        self.fake.address_getters[(PAYLOADS, "owner")] = EXECUTOR  # mutual pair, closes loop
        self.fake.call_raw_results[(PAYLOADS, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        self.fake.call_raw_results[(PAYLOADS, "guardian", ())] = GUARDIAN
        self.fake.safe_results[GUARDIAN] = (guardian_owners, 5)

    def test_shares_known_aave_guardian_committee_scores_80(self):
        self._wire_closed_chain(KNOWN_AAVE_GUARDIAN)
        result = scorers.score_aave_v3_pool_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 80)
        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["timelockScore"], 50)
        self.assertTrue(any("THIRD chain sharing this committee" in n for n in result["notes"]))

    def test_different_guardian_committee_scores_100_not_applicable(self):
        self._wire_closed_chain(_owners(9, start=100))
        result = scorers.score_aave_v3_pool_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertTrue(any("not computed this pass" in n for n in result["notes"]))

    def test_broken_mutual_pair_degrades_admin_key(self):
        self.fake.address_getters[(PROVIDER, "owner")] = EXECUTOR
        self.fake.address_getters[(EXECUTOR, "owner")] = PAYLOADS
        self.fake.address_getters[(PAYLOADS, "owner")] = _addr(77)  # does NOT close back to executor
        self.fake.call_raw_results[(PAYLOADS, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        self.fake.call_raw_results[(PAYLOADS, "guardian", ())] = GUARDIAN
        self.fake.safe_results[GUARDIAN] = (_owners(9, start=200), 5)

        result = scorers.score_aave_v3_pool_plasma(self.w3)
        self.assertEqual(result["adminKeyScore"], 30)

    def test_zero_delay_scores_timelock_zero(self):
        self._wire_closed_chain(_owners(9, start=300))
        self.fake.call_raw_results[(PAYLOADS, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 0)
        result = scorers.score_aave_v3_pool_plasma(self.w3)
        self.assertEqual(result["timelockScore"], 0)


class TestScorePendlePlasma(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)
        self.admin_slot = scorers._EIP1967_ADMIN_SLOT

    def test_two_paths_converge_on_3_of_5_safe(self):
        self.fake.address_getters[(ROUTER, "owner")] = PENDLE_SAFE
        self.fake.slot_results[(MARKET_FACTORY_V6, self.admin_slot)] = _addr(8)
        self.fake.address_getters[(_addr(8), "owner")] = PENDLE_SAFE
        self.fake.safe_results[PENDLE_SAFE] = (_owners(5), 3)

        result = scorers.score_pendle_plasma(self.w3)

        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["multisigScore"], 3 * 15 + 2 * 5)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("converging" in n for n in result["notes"]))

    def test_paths_disagree_still_scores_router_owner_but_flags_it(self):
        self.fake.address_getters[(ROUTER, "owner")] = PENDLE_SAFE
        self.fake.slot_results[(MARKET_FACTORY_V6, self.admin_slot)] = _addr(8)
        self.fake.address_getters[(_addr(8), "owner")] = _addr(99)  # disagrees
        self.fake.safe_results[PENDLE_SAFE] = (_owners(5), 3)

        result = scorers.score_pendle_plasma(self.w3)

        self.assertTrue(any("NOT independently confirmed to converge" in n for n in result["notes"]))

    def test_router_owner_unresolvable_degrades(self):
        self.fake.address_getters[(ROUTER, "owner")] = None
        self.fake.slot_results[(MARKET_FACTORY_V6, self.admin_slot)] = None
        result = scorers.score_pendle_plasma(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))

    def _wire_converging_safe(self, owners, threshold=3):
        self.fake.address_getters[(ROUTER, "owner")] = PENDLE_SAFE
        self.fake.slot_results[(MARKET_FACTORY_V6, self.admin_slot)] = _addr(8)
        self.fake.address_getters[(_addr(8), "owner")] = PENDLE_SAFE
        self.fake.safe_results[PENDLE_SAFE] = (owners, threshold)

    def test_shares_robinhood_pendle_committee_scores_80(self):
        # ADDED 2026-09-20: crossExposure fold, the identical Safe also owns Pendle on Robinhood Chain.
        self._wire_converging_safe(KNOWN_PENDLE_ROBINHOOD)

        result = scorers.score_pendle_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 80)
        # every other number is unchanged by the fold
        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["multisigScore"], 3 * 15 + 2 * 5)
        self.assertEqual(result["timelockScore"], 0)
        self.assertEqual(result["compositeScore"], 43)
        self.assertTrue(any("Real cross-chain finding, independently re-confirmed" in n for n in result["notes"]))
        self.assertFalse(any("not computed" in n for n in result["notes"]))

    def test_checksummed_owners_still_match_the_lowercased_snapshot(self):
        self._wire_converging_safe([RealWeb3.to_checksum_address(o) for o in KNOWN_PENDLE_ROBINHOOD])
        result = scorers.score_pendle_plasma(self.w3)
        self.assertEqual(result["crossExposureScore"], 80)

    def test_different_committee_scores_100_and_says_it_was_compared(self):
        self._wire_converging_safe(_owners(5, start=600))

        result = scorers.score_pendle_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertTrue(any("does NOT match exactly" in n for n in result["notes"]))
        self.assertFalse(any("Real cross-chain finding" in n for n in result["notes"]))

    def test_one_signer_rotated_out_loses_the_match(self):
        self._wire_converging_safe(KNOWN_PENDLE_ROBINHOOD[:4] + [_addr(601)])
        result = scorers.score_pendle_plasma(self.w3)
        self.assertEqual(result["crossExposureScore"], 100)

    def test_unread_safe_scores_100_with_not_computed_note(self):
        self.fake.address_getters[(ROUTER, "owner")] = PENDLE_SAFE
        self.fake.slot_results[(MARKET_FACTORY_V6, self.admin_slot)] = _addr(8)
        self.fake.address_getters[(_addr(8), "owner")] = PENDLE_SAFE
        self.fake.safe_results[PENDLE_SAFE] = None

        result = scorers.score_pendle_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))
        self.assertTrue(any("not computed" in n for n in result["notes"]))


class TestScoreEthenaUsdeOftPlasma(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def test_shares_known_ethereum_l1_ethena_committee_scores_80(self):
        self.fake.code_sizes[OFT.lower()] = 13639
        self.fake.address_getters[(OFT, "owner")] = ETHENA_SAFE
        self.fake.call_raw_results[(OFT, "pendingOwner", ())] = ETHENA_PENDING
        self.fake.safe_results[ETHENA_SAFE] = (KNOWN_ETHENA_L1, 5)
        self.fake.call_raw_results[(ETHENA_PENDING, "getMinDelay", ())] = 86400

        result = scorers.score_ethena_usde_oft_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 80)
        self.assertEqual(result["adminKeyScore"], 55)
        self.assertEqual(result["timelockScore"], 0)  # pending, not yet active
        self.assertTrue(any("SAME people control both Safes" in n for n in result["notes"]))

    def test_the_ethena_safe_guard_is_disclosed_as_a_positive_control_and_moves_no_score(self):
        # ADDED 2026-09-21: this Safe carries the same EthenaSafeGuard as the L1 Safe; note only.
        def run(guard):
            self.fake = FakeHelpers()
            _patch_helpers(self, self.fake)
            self.w3 = FakeW3(self.fake)
            self.fake.code_sizes[OFT.lower()] = 13639
            self.fake.address_getters[(OFT, "owner")] = ETHENA_SAFE
            self.fake.call_raw_results[(OFT, "pendingOwner", ())] = None
            self.fake.safe_results[ETHENA_SAFE] = (KNOWN_ETHENA_L1, 5)
            if guard:
                self.fake.guards[ETHENA_SAFE] = guard
            return scorers.score_ethena_usde_oft_plasma(self.w3)

        base = run(None)
        r = run(RealWeb3.to_checksum_address("0x74abe7805541c28f31953b3cDA9711Dc96278D29"))
        self.assertTrue(any("EthenaSafeGuard" in n and "positive control" in n for n in r["notes"]))
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
                         (base["adminKeyScore"], base["multisigScore"], base["timelockScore"], base["compositeScore"]))

    def test_different_committee_scores_100_not_applicable(self):
        self.fake.code_sizes[OFT.lower()] = 13639
        self.fake.address_getters[(OFT, "owner")] = ETHENA_SAFE
        self.fake.call_raw_results[(OFT, "pendingOwner", ())] = None
        self.fake.safe_results[ETHENA_SAFE] = (_owners(10, start=400), 5)

        result = scorers.score_ethena_usde_oft_plasma(self.w3)
        self.assertEqual(result["crossExposureScore"], 100)

    def test_owner_unresolvable_degrades(self):
        self.fake.code_sizes[OFT.lower()] = 13639
        self.fake.address_getters[(OFT, "owner")] = _addr(500)
        self.fake.call_raw_results[(OFT, "pendingOwner", ())] = None
        self.fake.safe_results[_addr(500)] = None

        result = scorers.score_ethena_usde_oft_plasma(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))

    # ADDED 2026-10-04: ownership moved to a TimelockController on 2026-09-29 (Plasma block 33749732). Documented live reads
    # of that day: getMinDelay 86400; the old owner Safe holds PROPOSER/EXECUTOR/CANCELLER/WHITELISTED_EXECUTOR;
    # isWhitelisted(OFT, setPeer) True, isWhitelisted(OFT, setDelegate) False; the Safe is 5-of-10 with the L1 owner set.
    # Expected values are Ethereum L1's convention for the same shape (score_ethena_layerzero_oft: 55/100/15), composite by
    # hand: (4*55 + 3*100 + 3*15 + 5) // 10 = 57.
    def _timelock_owner(self, peer=True, delegate=False, proposer=True):
        tl, safe = _addr(700), scorers._ETHENA_PLASMA_SAFE
        cs = RealWeb3.to_checksum_address
        self.fake.code_sizes[OFT.lower()] = 13639
        self.fake.address_getters[(OFT, "owner")] = tl
        self.fake.call_raw_results[(OFT, "pendingOwner", ())] = "0x" + "0" * 40
        self.fake.call_raw_results[(tl, "getMinDelay", ())] = 86400
        for role, held in (("PROPOSER_ROLE", proposer), ("EXECUTOR_ROLE", True), ("CANCELLER_ROLE", True), ("WHITELISTED_EXECUTOR_ROLE", True)):
            self.fake.call_raw_results[(tl, "hasRole", (RealWeb3.keccak(text=role), cs(safe)))] = held
        self.fake.call_raw_results[(tl, "isWhitelisted", (cs(OFT), bytes.fromhex("3400288b")))] = peer
        self.fake.call_raw_results[(tl, "isWhitelisted", (cs(OFT), bytes.fromhex("ca5eb5e1")))] = delegate
        self.fake.safe_results[safe] = (KNOWN_ETHENA_L1, 5)
        return scorers.score_ethena_usde_oft_plasma(self.w3)

    def test_owner_is_timelock_scores_like_the_l1_adapter(self):
        r = self._timelock_owner()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (55, 100, 15, 57))
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertTrue(any(n == "USDeOFT.pendingOwner() = none" for n in r["notes"]))

    def test_resolved_but_different_whitelist_shape_follows_l1(self):
        r = self._timelock_owner(delegate=True)  # setDelegate whitelisted too: resolved, so L1's rule gives timelock 0, not the floor
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (55, 100, 0))

    def test_timelock_shape_not_confirmed_degrades(self):
        for kw in ({"peer": None}, {"delegate": None}, {"proposer": False}):
            self.fake = FakeHelpers()
            _patch_helpers(self, self.fake)
            self.w3 = FakeW3(self.fake)
            r = self._timelock_owner(**kw)
            self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0), kw)


EULER_FACTORY = "0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3"
EULER_GOVERNOR = "0x939cA204c892932aA91810EeE50253a0427dd33D"
EULER_FACTORY_TIMELOCK = "0x1415c23e24786112a7f8d02a8366B6Ae4d082380"
EULER_ACEG = "0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c"
EULER_ADMIN_TIMELOCK = "0x61D942d4809482e6f761A326471053B343eE1921"
EULER_WILDCARD_TIMELOCK = "0xE468f1dA5B22b0d9A832De14a8f6158cD721b102"
EULER_DAO_SAFE = "0xfD30738fcB5eb5Ba418a84e672007912F991E539"
EULER_DEFAULT_ADMIN_ROLE = b"\x00" * 32
EULER_PROPOSER_ROLE = RealWeb3.keccak(text="PROPOSER_ROLE")


class TestEulerCrossExposureFold(unittest.TestCase):
    """ADDED 2026-09-20: the Euler DAO Safe (4-of-8) has the identical 8 signers as
    Monad's own Euler DAO Safe, so both Euler scorers fold crossExposureScore = 80
    when a fresh read of the Plasma DAO Safe equals the dated snapshot. Every other
    number is unchanged by the fold."""

    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire_factory_chain(self, dao_info):
        f = self.fake
        f.address_getters[(EULER_FACTORY, "upgradeAdmin")] = EULER_GOVERNOR
        f.call_raw_results[(EULER_GOVERNOR, "hasRole", (EULER_DEFAULT_ADMIN_ROLE, EULER_FACTORY_TIMELOCK))] = True
        f.call_raw_results[(EULER_FACTORY_TIMELOCK, "getMinDelay", ())] = 345600
        f.call_raw_results[(EULER_FACTORY_TIMELOCK, "hasRole", (EULER_PROPOSER_ROLE, EULER_DAO_SAFE))] = True
        f.safe_results[EULER_DAO_SAFE] = dao_info

    def _wire_aceg_chain(self, dao_info):
        f = self.fake
        f.call_raw_results[(EULER_ACEG, "hasRole", (EULER_DEFAULT_ADMIN_ROLE, EULER_ADMIN_TIMELOCK))] = True
        f.call_raw_results[(EULER_ADMIN_TIMELOCK, "getMinDelay", ())] = 172800
        f.call_raw_results[(EULER_WILDCARD_TIMELOCK, "getMinDelay", ())] = 172800
        f.call_raw_results[(EULER_ADMIN_TIMELOCK, "hasRole", (EULER_PROPOSER_ROLE, EULER_DAO_SAFE))] = True
        f.safe_results[EULER_DAO_SAFE] = dao_info

    def test_snapshot_is_the_8_lowercased_signers(self):
        self.assertEqual(len(KNOWN_EULER_DAO), 8)
        self.assertTrue(all(o == o.lower() for o in KNOWN_EULER_DAO))
        self.assertEqual(len(KNOWN_PENDLE_ROBINHOOD), 5)
        self.assertTrue(all(o == o.lower() for o in KNOWN_PENDLE_ROBINHOOD))

    # --- eVaultFactory ---

    def test_factory_shares_monad_euler_dao_committee_scores_80(self):
        self._wire_factory_chain((KNOWN_EULER_DAO, 4))

        result = scorers.score_euler_v2_evault_factory_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 80)
        self.assertEqual(result["adminKeyScore"], 70)
        self.assertEqual(result["multisigScore"], 4 * 15 + 4 * 5)
        self.assertEqual(result["timelockScore"], 68)
        self.assertEqual(result["compositeScore"], 72)
        self.assertTrue(any("Real cross-chain finding, independently re-confirmed" in n for n in result["notes"]))
        self.assertFalse(any("not computed" in n for n in result["notes"]))
        # the 2026-09-19 pause-guardian note is still emitted
        self.assertTrue(any("PAUSE_GUARDIAN_ROLE" in n for n in result["notes"]))

    def test_factory_different_dao_committee_scores_100(self):
        self._wire_factory_chain((_owners(8, start=700), 4))

        result = scorers.score_euler_v2_evault_factory_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertEqual(result["adminKeyScore"], 70)
        self.assertTrue(any("does NOT match exactly" in n for n in result["notes"]))
        self.assertFalse(any("Real cross-chain finding" in n for n in result["notes"]))

    def test_factory_unread_dao_safe_scores_100_with_not_computed_note(self):
        self._wire_factory_chain(None)

        result = scorers.score_euler_v2_evault_factory_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("not computed" in n for n in result["notes"]))

    # --- AccessControlEmergencyGovernor ---

    def test_aceg_shares_monad_euler_dao_committee_scores_80(self):
        self._wire_aceg_chain((KNOWN_EULER_DAO, 4))

        result = scorers.score_euler_v2_access_control_emergency_governor_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 80)
        self.assertEqual(result["adminKeyScore"], 68)
        self.assertEqual(result["multisigScore"], 4 * 15 + 4 * 5)
        self.assertEqual(result["timelockScore"], 55)
        self.assertEqual(result["compositeScore"], 68)
        self.assertTrue(any("Real cross-chain finding, independently re-confirmed" in n for n in result["notes"]))
        self.assertFalse(any("not computed" in n for n in result["notes"]))

    def test_aceg_different_dao_committee_scores_100(self):
        self._wire_aceg_chain((_owners(8, start=800), 4))

        result = scorers.score_euler_v2_access_control_emergency_governor_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertEqual(result["adminKeyScore"], 68)
        self.assertTrue(any("does NOT match exactly" in n for n in result["notes"]))
        self.assertFalse(any("Real cross-chain finding" in n for n in result["notes"]))

    def test_aceg_unread_dao_safe_scores_100_with_not_computed_note(self):
        self._wire_aceg_chain(None)

        result = scorers.score_euler_v2_access_control_emergency_governor_plasma(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("not computed" in n for n in result["notes"]))

    def test_a_signer_added_to_the_dao_safe_loses_the_match(self):
        self._wire_aceg_chain((KNOWN_EULER_DAO + [_addr(801)], 4))
        result = scorers.score_euler_v2_access_control_emergency_governor_plasma(self.w3)
        self.assertEqual(result["crossExposureScore"], 100)


SURGE = "0xA9C251f8304b1B3Fc2B9e8FCAE78D94eFF82Ac66"
HAVEN ="0x9c46EE1f01D2B551048f5Ff99a4659D98D04bED1"
TELOSC_SAFE = _addr(10)
USDT0_ASSET = _addr(11)

YZUSD = "0x6695c0f8706c5ace3bdf8995073179cca47926dc"
SYZUSD = "0xc8a8df9b210243c55d31c73090f06787ad0a1bf6"
YZPP = "0xebfc8c2fe73c431ef2a371aea9132110aab50dca"
YZUSD_TIMELOCK = _addr(12)


class TestScoreTelosConsiliumEulerEarnPlasma(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire(self, owner, curator, guardian="0x0000000000000000000000000000000000000000"):
        self.fake.address_getters[(SURGE, "owner")] = owner
        self.fake.address_getters[(SURGE, "curator")] = curator
        self.fake.address_getters[(SURGE, "guardian")] = guardian
        self.fake.address_getters[(SURGE, "asset")] = USDT0_ASSET
        self.fake.call_raw_results[(SURGE, "totalAssets", ())] = 99994647073267
        self.fake.call_raw_results[(SURGE, "timelock", ())] = 86400
        self.fake.address_getters[(HAVEN, "owner")] = owner
        self.fake.call_raw_results[(HAVEN, "totalAssets", ())] = 3393115462

    def test_2_of_5_safe_owner_equals_curator_scores_weak(self):
        self._wire(TELOSC_SAFE, TELOSC_SAFE)
        self.fake.safe_results[TELOSC_SAFE] = (_owners(5, start=900), 2)

        result = scorers.score_telos_consilium_euler_earn_plasma(self.w3)

        self.assertEqual(result["target"], SURGE)
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertEqual(result["multisigScore"], 2 * 15 + 3 * 5)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("owner==curator is a real Gnosis Safe: 2-of-5" in n for n in result["notes"]))
        self.assertTrue(any("Duplicate-authority check performed this pass" in n for n in result["notes"]))
        self.assertTrue(any("TelosC Haven" in n for n in result["notes"]))

    def test_owner_unresolvable_degrades(self):
        self._wire(_addr(901), _addr(901))
        self.fake.safe_results[_addr(901)] = None

        result = scorers.score_telos_consilium_euler_earn_plasma(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))


class TestScoreYuzuMoneyPlasma(unittest.TestCase):
    """REWRITTEN 2026-09-20: the placeholder (adminKey 20, "external admin unresolved") rested on an
    OpenZeppelin-4 role hash tested against an OpenZeppelin-5 timelock. The scorer now scores the traced chain."""

    T2 = scorers._YUZU_T2_2D
    T1 = scorers._YUZU_T1_12H
    S1 = RealWeb3.to_checksum_address(scorers._YUZU_S1)
    S2 = RealWeb3.to_checksum_address(scorers._YUZU_S2)
    PROXY_ADMIN = _addr(0x9AD)
    ZERO32 = b"\x00" * 32

    @staticmethod
    def _role(name):
        return bytes(RealWeb3.keccak(text=name))

    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire(self, s1=(3, 5), s2=(4, 5), pool_manager=True, t1_delay=43200, t2_delay=172800, t2_self_admin=True,
              t1_admin_on_token=True, t1_proposer=True, t2_proposer=True, proxy_admin_owner=None):
        f = self.fake
        f.code_sizes[scorers._YUZU_YZUSD.lower()] = 793
        for tok in (scorers._YUZU_YZUSD, scorers._YUZU_SYZUSD, scorers._YUZU_YZPP):
            f.address_getters[(tok, "owner")] = self.T2
        f.slot_results[(scorers._YUZU_YZUSD, scorers._EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        f.address_getters[(self.PROXY_ADMIN, "owner")] = proxy_admin_owner or self.T2
        f.call_raw_results[(self.T2, "getMinDelay", ())] = t2_delay
        f.call_raw_results[(self.T1, "getMinDelay", ())] = t1_delay
        f.call_raw_results[(self.T2, "hasRole", (self.ZERO32, self.T2))] = t2_self_admin
        f.call_raw_results[(self.T2, "hasRole", (self._role("PROPOSER_ROLE"), self.S2))] = t2_proposer
        f.call_raw_results[(self.T1, "hasRole", (self._role("PROPOSER_ROLE"), self.S1))] = t1_proposer
        f.call_raw_results[(scorers._YUZU_YZUSD, "hasRole", (self._role("ADMIN_ROLE"), self.T1))] = t1_admin_on_token
        f.call_raw_results[(scorers._YUZU_YZPP, "hasRole", (self._role("POOL_MANAGER_ROLE"), self.S1))] = pool_manager
        f.call_raw_results[(scorers._YUZU_YZPP, "hasRole", (self._role("DISTRIBUTOR_ROLE"), self.S1))] = pool_manager
        for tok in (scorers._YUZU_YZUSD, scorers._YUZU_SYZUSD, scorers._YUZU_YZPP):
            f.call_raw_results[(tok, "hasRole", (self._role("PAUSE_MANAGER_ROLE"), self.S1))] = True
        f.safe_results[scorers._YUZU_S1] = (_owners(s1[1]), s1[0]) if s1 else None
        f.safe_results[scorers._YUZU_S2] = (_owners(s2[1]), s2[0]) if s2 else None

    def test_live_shape_instant_pool_seat_decides(self):
        self._wire()
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual(r["target"], scorers._YUZU_YZUSD)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"], r["crossExposureScore"]), (65, 55, 0, 100, 100))
        self.assertEqual(r["compositeScore"], 43)
        text = " ".join(r["notes"])
        self.assertIn("INSTANT (no delay) seat", text)
        self.assertIn("Weakest fund-affecting path", text)

    def test_the_v3_implementation_note_is_dated_states_the_role_facts_and_moves_no_score(self):
        # ADDED 2026-09-21: the implementation changed within 30 days (found by the implementation watch); the note carries what the
        # verified V3 source and a role replay showed, and is note-only.
        self._wire()
        r = scorers.score_yuzu_money_plasma(self.w3)
        note = next(n for n in r["notes"] if n.startswith("Implementation changed within 30 days"))
        for fragment in ("YuzuUSDV3", "Routescan", "17 selectors added", "ten of the 18 roles", "NO holder", "MINTER_ROLE and REDEEMER_ROLE", "availability only"):
            self.assertIn(fragment, note)
        self.assertEqual(r["compositeScore"], 43)  # unchanged: the note is not a score input

    def test_the_oz4_role_hash_false_negative_is_gone(self):
        # The old scorer asked hasRole(TIMELOCK_ADMIN_ROLE, timelock); on OZ5 that is False even though the
        # timelock is its own admin. Wiring ONLY the OZ4 hash False must not make the score "unresolved".
        self._wire()
        oz4 = bytes.fromhex("5f58e3a2316349923ce3780f8d587db2d72378aed66a8261c916544fa6846ca5")
        self.fake.call_raw_results[(self.T2, "hasRole", (oz4, self.T2))] = False
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual(r["adminKeyScore"], 65)
        self.assertNotEqual(r["adminKeyScore"], 20)

    def test_threshold_two_and_one_safes_score_lower(self):
        for k, n, admin, multisig in ((2, 5, 50, 2 * 15 + 3 * 5), (1, 5, 10, 1 * 15 + 4 * 5)):
            with self.subTest(k=k):
                self._wire(s1=(k, n))
                r = scorers.score_yuzu_money_plasma(self.w3)
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (admin, multisig, 0))

    def test_without_the_instant_seat_the_12h_path_decides(self):
        self._wire(pool_manager=False)
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 55, 55, 59))
        self.assertIn("12h ADMIN_ROLE path decides", " ".join(r["notes"]))

    def test_only_the_2_day_path_when_the_12h_link_is_gone(self):
        self._wire(pool_manager=False, t1_admin_on_token=False)
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 65, 55))  # S2 is 4-of-5: 60 + 5
        self.assertIn("2-day upgrade path", " ".join(r["notes"]))

    def test_unresolved_proposer_safes_degrade(self):
        self._wire(pool_manager=False, s1=None, s2=None)
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_s1_not_a_safe_with_the_instant_seat_degrades_instead_of_falling_to_a_better_path(self):
        # S2 (4-of-5, the 2-day path) would score 65/65/55 if the unresolved S1 were skipped: it must not be.
        self._wire(s1=None)
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_a_failed_seat_read_is_not_taken_as_no_seat(self):
        for label, key in (
            ("pool manager", (scorers._YUZU_YZPP, "hasRole", (self._role("POOL_MANAGER_ROLE"), self.S1))),
            ("t1 admin on token", (scorers._YUZU_YZUSD, "hasRole", (self._role("ADMIN_ROLE"), self.T1))),
            ("t1 proposer", (self.T1, "hasRole", (self._role("PROPOSER_ROLE"), self.S1))),
            ("t2 proposer", (self.T2, "hasRole", (self._role("PROPOSER_ROLE"), self.S2))),
        ):
            with self.subTest(unread=label):
                self._wire()
                del self.fake.call_raw_results[key]
                r = scorers.score_yuzu_money_plasma(self.w3)
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_owner_not_the_expected_timelock_degrades(self):
        self._wire()
        for tok in (scorers._YUZU_YZUSD, scorers._YUZU_SYZUSD, scorers._YUZU_YZPP):
            self.fake.address_getters[(tok, "owner")] = _addr(902)
        self.fake.call_raw_results[(_addr(902), "getMinDelay", ())] = None
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_proxy_admin_not_owned_by_the_timelock_degrades(self):
        self._wire(proxy_admin_owner=_addr(903))
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_timelock_not_self_administered_degrades(self):
        self._wire(t2_self_admin=False)
        r = scorers.score_yuzu_money_plasma(self.w3)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_pause_and_custody_are_disclosed_but_not_scored(self):
        self._wire()
        text = " ".join(scorers.score_yuzu_money_plasma(self.w3)["notes"])
        self.assertIn("instant pause: availability-only, disclosed, not scored", text)
        self.assertIn("custody counterparty", text)

    def test_cross_exposure_note_names_the_registry_group(self):
        self._wire()
        text = " ".join(scorers.score_yuzu_money_plasma(self.w3)["notes"])
        self.assertIn("group 'yuzu'", text)

    def test_role_names_hash_to_the_values_confirmed_live(self):
        # ADMIN_ROLE, POOL_MANAGER_ROLE, PROPOSER_ROLE hashed here from their names, never hand-typed hex.
        self.assertEqual(scorers._yuzu_role("PROPOSER_ROLE").hex(), "b09aa5aeb3702cfd50b6b62bc4532604938f21248a27a1d5ca736082b6819cc1")
        self.assertEqual(len(scorers._yuzu_role("POOL_MANAGER_ROLE")), 32)


class TestScoreAllPlasma(unittest.TestCase):
    """Smoke test: score_all() runs every SIMPLE_SCORERS entry through
    safe_score()'s per-target isolation and returns a flat list -- does not
    re-verify each scorer's own decision logic (covered above/by the Euler
    and Fluid scorers' own existing dry-run/validate_all_scorers.py passes),
    just that a single failing scorer doesn't take down the whole batch."""

    def test_a_single_failing_scorer_does_not_crash_the_batch(self):
        class ExplodingW3:
            class eth:
                @staticmethod
                def get_code(addr):
                    raise RuntimeError("RPC down")

            @staticmethod
            def to_checksum_address(addr):
                return RealWeb3.to_checksum_address(addr)

        # score_all() must return a list (possibly with fewer than 7 targets
        # if every one of them independently fails against a dead w3), not
        # raise -- this is exactly what safe_score()'s per-target isolation
        # (already covered by scripts/lib/tests/test_web3_utils.py) exists
        # to guarantee; asserting the return type/no-crash here, not
        # re-deriving safe_score()'s own tested behavior.
        results = scorers.score_all(ExplodingW3())
        self.assertIsInstance(results, list)


class TestPauseGuardianNote(unittest.TestCase):
    """_pause_guardian_note(): PAUSE_GUARDIAN_ROLE on the eVaultFactory Governor was
    invisible to this scorer (it searched for role names the deployed contracts do
    not use). Two bare EOAs and the Labs Safe hold it; either EOA alone can call
    pause(eVaultFactory). Notes only, no score changes."""
    GOVERNOR = "0x939cA204c892932aA91810EeE50253a0427dd33D"
    SAFE = RealWeb3.to_checksum_address("0x9cC876dCb0e99cC040cf5F92880d0Ee9e320CA61")
    EOA_A = RealWeb3.to_checksum_address("0xff217004BdD3A6A592162380dc0E6BbF143291eB")
    EOA_B = RealWeb3.to_checksum_address("0xcC6451385685721778E7Bd80B54F8c92b484F601")

    def _wire(self, holders, count=None):
        fake = FakeHelpers()
        role = scorers._PAUSE_GUARDIAN_ROLE
        fake.call_raw_results[(self.GOVERNOR, "getRoleMemberCount", (role,))] = len(holders) if count is None else count
        for i, (addr, code_size) in enumerate(holders):
            fake.call_raw_results[(self.GOVERNOR, "getRoleMember", (role, i))] = addr
            fake.code_sizes[addr.lower()] = code_size
        _patch_helpers(self, fake)
        return FakeW3(fake)

    def test_role_hash_is_the_real_keccak_not_a_typed_constant(self):
        self.assertEqual(scorers._PAUSE_GUARDIAN_ROLE, RealWeb3.keccak(text="PAUSE_GUARDIAN_ROLE"))

    def test_lists_every_holder_and_counts_bare_eoas(self):
        w3 = self._wire([(self.SAFE, 171), (self.EOA_A, 0), (self.EOA_B, 0)])
        note = scorers._pause_guardian_note(w3, self.GOVERNOR)
        self.assertIn("3 holder(s)", note)
        self.assertIn(f"{self.SAFE} (contract)", note)
        self.assertIn(f"{self.EOA_A} (bare EOA)", note)
        self.assertIn(f"{self.EOA_B} (bare EOA)", note)
        self.assertIn("2 bare EOA(s)", note)
        self.assertIn("NOT scored", note)

    def test_unreadable_count_is_reported_not_guessed(self):
        fake = FakeHelpers()  # nothing registered -> call_raw returns None
        _patch_helpers(self, fake)
        note = scorers._pause_guardian_note(FakeW3(fake), self.GOVERNOR)
        self.assertIn("unread this run", note)

    def test_one_unreadable_member_does_not_hide_the_others(self):
        fake = FakeHelpers()
        role = scorers._PAUSE_GUARDIAN_ROLE
        fake.call_raw_results[(self.GOVERNOR, "getRoleMemberCount", (role,))] = 2
        fake.call_raw_results[(self.GOVERNOR, "getRoleMember", (role, 1))] = self.EOA_A
        fake.code_sizes[self.EOA_A.lower()] = 0
        _patch_helpers(self, fake)
        note = scorers._pause_guardian_note(FakeW3(fake), self.GOVERNOR)
        self.assertIn("<unread>", note)
        self.assertIn(f"{self.EOA_A} (bare EOA)", note)

    def test_member_loop_is_capped_at_ten(self):
        holders = [(RealWeb3.to_checksum_address("0x" + format(0x1000 + i, "040x")), 0) for i in range(25)]
        w3 = self._wire(holders)
        note = scorers._pause_guardian_note(w3, self.GOVERNOR)
        self.assertIn("25 holder(s)", note)  # the true count is still reported
        self.assertEqual(note.count("(bare EOA)"), 10)  # but only 10 members are read


if __name__ == "__main__":
    unittest.main()
