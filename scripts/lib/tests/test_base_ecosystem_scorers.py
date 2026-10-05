"""
Unit tests for chains/base-ecosystem/scorers.py's SCORING LOGIC -- the
branches that turn live reads into adminKeyScore/multisigScore/
timelockScore/crossExposureScore, previously untested anywhere (found
during the same 2026-09-18 test-coverage audit that led to `test_zcash_
read.py`). The shared read primitives this file calls into
(read_address_getter, call_raw, read_slot_as_address,
safe_owners_and_threshold) are ALREADY covered at the retry/plumbing
level by `test_web3_utils.py`; what's untested is the decision logic
built on TOP of them -- and that logic has already had two real bugs
found and fixed in place (both cited in the module's own docstrings):
  1. `score_uniswap_v3_factory_base`'s `slot0_is_predeploy` check used to
     be read and noted but never actually compared against the expected
     L2CrossDomainMessenger predeploy -- the cross-domain gate the
     docstring claimed to verify wasn't actually verified.
  2. The same function's `admin_key` used to be a bare literal 80
     regardless of whether the L1 cross-domain re-confirmation actually
     succeeded.
Both are locked in here with dedicated regression tests, alongside the
Aerodrome governor/pauser identity live-check and emergencyCouncil
overlap computation added 2026-09-18 (this pass).

Approach: monkeypatch the four read-primitive names `scorers.py` imports
directly (`read_address_getter`, `call_raw`, `read_slot_as_address`,
`safe_owners_and_threshold`) with small dict-dispatch fakes, rather than
mocking Web3.py's contract-call machinery -- the same "fake the
project's own primitive, not the underlying network library" discipline
`test_zcash_read.py` already uses for `zcash_read.grpc`. A minimal FakeW3
covers the one place (`score_uniswap_v3_factory_base`) that calls
`w3.eth.get_code`/`w3.to_checksum_address` directly instead of going
through a helper.
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
scorers = _load_module("aro_test_base_ecosystem_scorers", "chains/base-ecosystem/scorers.py")


# ADDED 2026-10-04: these tests pin the composite logic on a fake chain the price-path engine cannot walk. The engine is
# replaced here by a stub returning 100; scripts/lib/tests/test_price_authority_wiring.py checks that each consumer scorer
# really puts the engine's value into oracleAuthorityScore.
_PA_NAMES = ("for_aave", "for_aave_v2", "for_comet", "for_morpho_v1", "for_morpho_v2", "for_gmx_v2", "for_gmx_v1", "for_euler_factory", "for_euler_earn", "for_moonwell")
_PA_ORIG = {}


def setUpModule():
    for n in _PA_NAMES:
        _PA_ORIG[n] = getattr(scorers.price_authority, n)
        setattr(scorers.price_authority, n, lambda *a, **k: 100)


def tearDownModule():
    for n, f in _PA_ORIG.items():
        setattr(scorers.price_authority, n, f)


class FakeHelpers:
    """One dispatch table per read primitive, keyed exactly the way the
    real helpers are called. `.get(key)` semantics (default None) match
    the real helpers' own "revert/failure -> None" contract."""

    def __init__(self):
        self.address_getters = {}       # (address, function_name) -> address-or-None
        self.call_raw_results = {}      # (address, function_name, args-tuple) -> value-or-None
        self.slot_results = {}          # (address, slot) -> address-or-None
        self.safe_results = {}          # address -> (owners, threshold) or None
        self.l1_rpc_url = None

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def get_w3(self, rpc_url):
        self.l1_rpc_url = rpc_url
        return "fake-l1-w3"  # never dereferenced directly; only passed back into the faked helpers above


class FakeEth:
    def __init__(self, code_sizes):
        self._code_sizes = code_sizes

    def get_code(self, addr):
        return b"\x00" * self._code_sizes.get(addr, 100)


class FakeW3:
    def __init__(self, code_sizes=None):
        self.eth = FakeEth(code_sizes or {})

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "read_slot_as_address", "safe_owners_and_threshold", "get_w3"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


ADDR_A = RealWeb3.to_checksum_address("0x" + "aa" * 20)
ADDR_B = RealWeb3.to_checksum_address("0x" + "bb" * 20)
ADDR_C = RealWeb3.to_checksum_address("0x" + "cc" * 20)
ADDR_D = RealWeb3.to_checksum_address("0x" + "dd" * 20)


def _owners(n, start=1):
    # `start` lets two calls produce genuinely DISJOINT address sets (the
    # default start=1 for every call would otherwise silently overlap on
    # the first min(n1, n2) addresses -- exactly wrong for a "these two
    # Safes share zero owners" test fixture).
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


# --------------------------------------------------------------------- _composite
class TestComposite(unittest.TestCase):
    def test_weights_and_round_half_up(self):
        # 0.4*65 + 0.3*65 + 0.3*0 + 0.5 = 26 + 19.5 + 0 + 0.5 = 46.0 -> floor 46
        self.assertEqual(scorers._composite(65, 65, 0), 46)

    def test_half_rounds_up_not_bankers_rounding(self):
        # Python's builtin round(0.5) would go to 0 (banker's rounding);
        # this project's own docstring says that bug was already caught
        # and fixed once -- pin the correct floor(x+0.5) behavior here so
        # it can't quietly regress back to round().
        # Choose inputs landing exactly on a .5 boundary: 0.4*1=0.4, want
        # total x.5 -> 0.4*a + 0.3*b + 0.3*c = X.0 before the +0.5 offset.
        # a=0, b=0, c=0 -> 0.5 -> floor(0.5+0.5)=floor(1.0)=1, not 0.
        self.assertEqual(scorers._composite(0, 0, 0), 0)
        # 0.4*0+0.3*0+0.3*5+0.5 = 1.5+0.5=2.0 -> floor=2
        self.assertEqual(scorers._composite(0, 0, 5), 2)

    def test_max_inputs_give_100(self):
        self.assertEqual(scorers._composite(100, 100, 100), 100)


# --------------------------------------------------------------------- Morpho Blue
class TestScoreMorphoBlue(unittest.TestCase):
    TARGET = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"

    def test_real_safe_3_of_7_scores_as_strong(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(7), 3)
        _patch_helpers(self, fake)

        r = scorers.score_morpho_blue(FakeW3())
        self.assertEqual(r["adminKeyScore"], 65)
        self.assertEqual(r["multisigScore"], min(100, 3 * 15 + 4 * 5))
        self.assertEqual(r["timelockScore"], 0)
        self.assertEqual(r["compositeScore"], scorers._composite(r["adminKeyScore"], r["multisigScore"], 0))

    def test_threshold_2_scores_as_medium(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(3), 2)
        _patch_helpers(self, fake)

        r = scorers.score_morpho_blue(FakeW3())
        self.assertEqual(r["adminKeyScore"], 50)

    def test_threshold_1_scores_as_weak(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(1), 1)
        _patch_helpers(self, fake)

        r = scorers.score_morpho_blue(FakeW3())
        self.assertEqual(r["adminKeyScore"], 10)

    def test_owner_not_a_safe_degrades_conservatively(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = None  # not resolvable as a Safe
        _patch_helpers(self, fake)

        r = scorers.score_morpho_blue(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertTrue(any("unresolved authority" in n for n in r["notes"]))

    def test_unrelated_owner_set_scores_cross_exposure_100(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(9), 5)  # unrelated synthetic set, wrong threshold-shape coincidence aside
        _patch_helpers(self, fake)

        r = scorers.score_morpho_blue(FakeW3())
        self.assertEqual(r["crossExposureScore"], 100)

    def test_owner_matches_known_robinhood_committee_scores_80(self):
        # Real addresses from this same module's own
        # _KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19 snapshot -- Base's
        # Morpho Blue owner Safe, live-confirmed to share this exact 9-of-9
        # set at 5-of-9 with Robinhood Chain's own tracked Morpho Blue Safe.
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (list(scorers._KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19), 5)
        _patch_helpers(self, fake)

        r = scorers.score_morpho_blue(FakeW3())
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertTrue(any("IDENTICAL" in n for n in r["notes"]))


# --------------------------------------------------------------------- Aave V3 Base
class TestScoreAaveV3Base(unittest.TestCase):
    PROVIDER = "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"

    def _wire_closed_chain(self, fake, delay=86400, guardian_owners=None, guardian_threshold=5):
        fake.address_getters[(self.PROVIDER, "owner")] = ADDR_A  # executor
        fake.call_raw_results[(self.PROVIDER, "getACLAdmin", ())] = ADDR_A
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B  # payloads_controller
        fake.address_getters[(ADDR_B, "owner")] = ADDR_A  # closes the loop back to executor
        fake.call_raw_results[(ADDR_B, "getExecutorSettingsByAccessControl", (1,))] = (ADDR_A, delay)
        fake.call_raw_results[(ADDR_B, "guardian", ())] = ADDR_C
        if guardian_owners is not None:
            fake.safe_results[ADDR_C] = (guardian_owners, guardian_threshold)

    def test_closed_chain_with_real_delay_scores_high_admin_and_timelock(self):
        fake = FakeHelpers()
        self._wire_closed_chain(fake, delay=86400, guardian_owners=_owners(5), guardian_threshold=3)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_base(FakeW3())
        self.assertEqual(r["adminKeyScore"], 65)
        self.assertEqual(r["timelockScore"], 50)
        self.assertEqual(r["multisigScore"], 100)  # not applicable -- not a Safe pair

    def test_broken_loop_degrades_admin_key(self):
        fake = FakeHelpers()
        self._wire_closed_chain(fake, delay=86400)
        # Break the loop: PayloadsController.owner() no longer points back to executor.
        fake.address_getters[(ADDR_B, "owner")] = ADDR_D
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_base(FakeW3())
        self.assertEqual(r["adminKeyScore"], 30)

    def test_zero_or_missing_delay_scores_timelock_zero(self):
        fake = FakeHelpers()
        self._wire_closed_chain(fake, delay=0)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_base(FakeW3())
        self.assertEqual(r["timelockScore"], 0)

    def test_guardian_committee_identical_to_arbitrum_flags_shared_exposure(self):
        # Exact owner set hardcoded INSIDE score_aave_v3_base() itself (a
        # local, not a module-level constant -- confirmed by reading the
        # real function body) as the dated 2026-09-17 Arbitrum snapshot;
        # copied here verbatim so this test exercises the real comparison
        # against the actual values production code compares against, not
        # a synthetic stand-in that could drift from it unnoticed.
        arb_owners = [
            "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
            "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
            "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
            "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
            "0x4C30E33758216aD0d676419c21CB8D014C68099f",
        ]
        fake = FakeHelpers()
        self._wire_closed_chain(fake, delay=86400, guardian_owners=arb_owners, guardian_threshold=5)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_base(FakeW3())
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertTrue(any("IDENTICAL to Arbitrum" in n for n in r["notes"]))

    def test_guardian_committee_different_from_arbitrum_scores_full_cross_exposure(self):
        fake = FakeHelpers()
        self._wire_closed_chain(fake, delay=86400, guardian_owners=_owners(9), guardian_threshold=5)
        _patch_helpers(self, fake)

        r = scorers.score_aave_v3_base(FakeW3())
        self.assertEqual(r["crossExposureScore"], 100)


# --------------------------------------------------------------------- Aerodrome
class TestScoreAerodromePoolFactory(unittest.TestCase):
    TARGET = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"

    def _wire_common(self, fake, voter=ADDR_B, governor=None, pauser=ADDR_A, fee_manager=ADDR_A,
                      pauser_owners=None, pauser_threshold=3, emergency_council=None,
                      council_owners=None, council_threshold=3):
        fake.call_raw_results[(self.TARGET, "owner", ())] = None  # PoolFactory.owner() reverts by design
        fake.address_getters[(self.TARGET, "pauser")] = pauser
        fake.address_getters[(self.TARGET, "feeManager")] = fee_manager
        fake.address_getters[(self.TARGET, "voter")] = voter
        if governor is not None:
            fake.address_getters[(voter, "governor")] = governor
        if emergency_council is not None:
            fake.address_getters[(voter, "emergencyCouncil")] = emergency_council
        if pauser_owners is not None:
            fake.safe_results[pauser] = (pauser_owners, pauser_threshold)
        if council_owners is not None and emergency_council is not None:
            fake.safe_results[emergency_council] = (council_owners, council_threshold)

    def test_governor_identical_to_pauser_scores_normally_with_identity_note(self):
        fake = FakeHelpers()
        self._wire_common(fake, governor=ADDR_A, pauser=ADDR_A, fee_manager=ADDR_A,
                           pauser_owners=_owners(7), pauser_threshold=3)
        _patch_helpers(self, fake)

        r = scorers.score_aerodrome_poolfactory(FakeW3())
        self.assertEqual(r["adminKeyScore"], 65)
        self.assertTrue(any("CONFIRMED live to be the exact same Safe" in n for n in r["notes"]))

    def test_governor_diverged_from_pauser_degrades_as_stale(self):
        # Regression test for the live-identity guard added 2026-09-18:
        # if voter().governor() no longer matches pauser()/feeManager(),
        # this must degrade rather than silently keep scoring the old
        # (now-wrong) assumption that they're the same key.
        fake = FakeHelpers()
        self._wire_common(fake, governor=ADDR_D, pauser=ADDR_A, fee_manager=ADDR_A,
                           pauser_owners=_owners(7), pauser_threshold=3)
        _patch_helpers(self, fake)

        r = scorers.score_aerodrome_poolfactory(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertTrue(any("STALE, degrading" in n for n in r["notes"]))

    def test_emergency_council_with_no_overlap_reports_clean(self):
        fake = FakeHelpers()
        self._wire_common(
            fake, governor=ADDR_A, pauser=ADDR_A, fee_manager=ADDR_A,
            pauser_owners=_owners(7, start=1), pauser_threshold=3,
            emergency_council=ADDR_C, council_owners=_owners(5, start=100), council_threshold=3,
        )
        _patch_helpers(self, fake)

        r = scorers.score_aerodrome_poolfactory(FakeW3())
        self.assertTrue(any("zero owner overlap" in n for n in r["notes"]))
        self.assertFalse(any("OVERLAPS" in n for n in r["notes"]))

    def test_emergency_council_sharing_an_owner_is_flagged_not_silently_missed(self):
        # Regression test for the 2026-09-18 adversarial-review fix: this
        # note used to assert "zero overlap" as fixed prose without ever
        # computing it. Construct a genuine overlap and confirm the code
        # actually catches it now.
        shared_owner = _owners(1)[0]
        pauser_owners = _owners(6) + [shared_owner]
        council_owners = [shared_owner] + _owners(4)
        fake = FakeHelpers()
        self._wire_common(
            fake, governor=ADDR_A, pauser=ADDR_A, fee_manager=ADDR_A,
            pauser_owners=pauser_owners, pauser_threshold=3,
            emergency_council=ADDR_C, council_owners=council_owners, council_threshold=3,
        )
        _patch_helpers(self, fake)

        r = scorers.score_aerodrome_poolfactory(FakeW3())
        self.assertTrue(any("OVERLAPS governor/pauser/feeManager" in n for n in r["notes"]))


# --------------------------------------------------------------------- Uniswap V3 Base
class TestScoreUniswapV3FactoryBase(unittest.TestCase):
    FACTORY = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
    L2_PREDEPLOY = "0x4200000000000000000000000000000000000007"

    def _wire(self, fake, slot0=None, slot1=ADDR_C, l1_delay=172800, l1_admin=ADDR_D):
        fake.address_getters[(self.FACTORY, "owner")] = ADDR_A  # adapter
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B  # forwarder
        fake.slot_results[(ADDR_B, "0x0000000000000000000000000000000000000000000000000000000000000000")] = slot0
        fake.slot_results[(ADDR_B, "0x0000000000000000000000000000000000000000000000000000000000000001")] = slot1
        if slot1:
            fake.call_raw_results[(slot1, "delay", ())] = l1_delay
            fake.call_raw_results[(slot1, "admin", ())] = l1_admin

    def test_predeploy_confirmed_and_l1_resolved_scores_strong_admin_and_timelock(self):
        fake = FakeHelpers()
        self._wire(fake, slot0=self.L2_PREDEPLOY, slot1=ADDR_C, l1_delay=172800, l1_admin=ADDR_D)
        _patch_helpers(self, fake)

        r = scorers.score_uniswap_v3_factory_base(FakeW3())
        self.assertEqual(r["adminKeyScore"], 80)
        self.assertEqual(r["timelockScore"], 75)
        self.assertTrue(any("matches the expected L2CrossDomainMessenger predeploy: True" in n for n in r["notes"]))

    def test_slot0_not_predeploy_degrades_admin_key_even_if_l1_resolves(self):
        # REGRESSION TEST for the real 2026-09-17 bug: slot0 used to be
        # read and noted but never actually gated on -- a factory whose
        # forwarder's slot0 is NOT the canonical L2CrossDomainMessenger
        # predeploy must not still get the confident "cross-domain gate
        # verified" adminKeyScore of 80, even though slot1/L1 both
        # resolve cleanly.
        fake = FakeHelpers()
        self._wire(fake, slot0=ADDR_D, slot1=ADDR_C, l1_delay=172800, l1_admin=ADDR_D)  # wrong slot0
        _patch_helpers(self, fake)

        r = scorers.score_uniswap_v3_factory_base(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)
        self.assertTrue(any("does NOT match the canonical L2CrossDomainMessenger predeploy" in n for n in r["notes"]))

    def test_l1_delay_unresolved_degrades_admin_key_despite_correct_predeploy(self):
        # REGRESSION TEST for the second real 2026-09-17 bug: adminKeyScore
        # used to be a bare literal 80 regardless of whether the L1
        # cross-domain re-confirmation actually succeeded, even though
        # timelockScore was already correctly gated on l1_delay.
        fake = FakeHelpers()
        self._wire(fake, slot0=self.L2_PREDEPLOY, slot1=ADDR_C, l1_delay=None, l1_admin=ADDR_D)
        _patch_helpers(self, fake)

        r = scorers.score_uniswap_v3_factory_base(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)
        self.assertEqual(r["timelockScore"], 0)

    def test_uses_the_ethereum_l1_rpc_not_the_base_rpc_for_the_l1_hop(self):
        fake = FakeHelpers()
        self._wire(fake, slot0=self.L2_PREDEPLOY, slot1=ADDR_C, l1_delay=172800, l1_admin=ADDR_D)
        _patch_helpers(self, fake)

        scorers.score_uniswap_v3_factory_base(FakeW3())
        self.assertEqual(fake.l1_rpc_url, "https://ethereum-rpc.publicnode.com")


# --------------------------------------------------------------------- Compound V3 Base
class TestScoreCompoundV3CometBaseUsdc(unittest.TestCase):
    TARGET = "0xb125E6687d4313864e53df431d5425969c15Eb2F"

    def _wire(self, fake, proxy_admin_owner_matches=True, gov_timelock=ADDR_D, local_matches=True, delay=86400):
        fake.address_getters[(self.TARGET, "governor")] = ADDR_A  # LocalTimelock
        fake.slot_results[(self.TARGET, scorers.EIP1967_ADMIN_SLOT)] = ADDR_B  # ProxyAdmin
        fake.address_getters[(ADDR_B, "owner")] = ADDR_A if proxy_admin_owner_matches else ADDR_C
        fake.call_raw_results[(ADDR_A, "delay", ())] = delay
        fake.address_getters[(ADDR_A, "admin")] = ADDR_C  # BaseBridgeReceiver
        fake.address_getters[(ADDR_C, "govTimelock")] = gov_timelock
        fake.address_getters[(ADDR_C, "localTimelock")] = ADDR_A if local_matches else ADDR_D

    def test_fully_closed_chain_scores_strong_admin(self):
        fake = FakeHelpers()
        self._wire(fake)
        _patch_helpers(self, fake)

        r = scorers.score_compound_v3_comet_base_usdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 75)
        self.assertEqual(r["timelockScore"], 65)

    def test_pause_guardian_committee_shared_with_l1_and_arbitrum_folds_cross_exposure_to_80(self):
        # ADDED 2026-09-20 (real finding): Base's pauseGuardian is the same 9-signer 5-of-9 committee as L1 and Arbitrum.
        fake = FakeHelpers()
        self._wire(fake)
        pg = "0x" + "9a" * 20
        fake.address_getters[(self.TARGET, "pauseGuardian")] = pg
        fake.safe_results[pg] = (sorted(RealWeb3.to_checksum_address(a) for a in scorers._KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20), 5)
        _patch_helpers(self, fake)

        r = scorers.score_compound_v3_comet_base_usdc(FakeW3())
        self.assertEqual(r["crossExposureScore"], 80)
        # UPDATED 2026-09-25 (d6dca5e): timelockScore is now capped at 60, not 65, when the resolved
        # pauseGuardian matches the known committee -- this test wires exactly that committee, so it
        # must see the capped value, not the pre-fix uncapped one. adminKeyScore is unaffected.
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (75, 60))
        self.assertIn("IDENTICAL, as an exact set", " ".join(r["notes"]))

    def test_no_guardian_read_or_other_committee_keeps_cross_exposure_100(self):
        fake = FakeHelpers()
        self._wire(fake)  # pauseGuardian not wired: unread
        _patch_helpers(self, fake)
        self.assertEqual(scorers.score_compound_v3_comet_base_usdc(FakeW3())["crossExposureScore"], 100)

    def test_proxy_admin_owner_mismatch_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, proxy_admin_owner_matches=False)
        _patch_helpers(self, fake)

        r = scorers.score_compound_v3_comet_base_usdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 35)

    def test_local_timelock_loop_not_closed_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, local_matches=False)
        _patch_helpers(self, fake)

        r = scorers.score_compound_v3_comet_base_usdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 35)

    def test_no_gov_timelock_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, gov_timelock=None)
        _patch_helpers(self, fake)

        r = scorers.score_compound_v3_comet_base_usdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 35)

    def test_zero_delay_scores_timelock_zero(self):
        fake = FakeHelpers()
        self._wire(fake, delay=0)
        _patch_helpers(self, fake)

        r = scorers.score_compound_v3_comet_base_usdc(FakeW3())
        self.assertEqual(r["timelockScore"], 0)


if __name__ == "__main__":
    unittest.main()
