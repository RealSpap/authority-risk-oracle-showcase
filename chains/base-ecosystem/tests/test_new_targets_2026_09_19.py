"""
Unit tests for the 4 Base targets added in the 2026-09-19 maintenance run
(Aerodrome Slipstream CLFactory, Uniswap V2 Factory, Uniswap V4 PoolManager,
Moonwell Comptroller) and for score_all()'s new intra-Base crossExposure
post-pass (_apply_intra_base_overlap).

Lives under chains/base-ecosystem/ (not scripts/lib/tests/) on purpose: the
pipeline's per-ecosystem agents must not edit the repo-root scripts/ tree.
Reuses the fakes (FakeHelpers, FakeW3, _patch_helpers) of the existing
scripts/lib/tests/test_base_ecosystem_scorers.py by importing that module,
so both files patch the SAME loaded scorers module.

Run from the repo root:
    python3 -m unittest discover -s chains/base-ecosystem/tests -v
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_spec = importlib.util.spec_from_file_location(
    "aro_base_existing_tests", os.path.join(REPO_ROOT, "scripts", "lib", "tests", "test_base_ecosystem_scorers.py")
)
base_tests = importlib.util.module_from_spec(_spec)
sys.modules["aro_base_existing_tests"] = base_tests
_spec.loader.exec_module(base_tests)

scorers = base_tests.scorers
FakeHelpers, FakeW3, _patch_helpers, _owners = base_tests.FakeHelpers, base_tests.FakeW3, base_tests._patch_helpers, base_tests._owners
ADDR_A, ADDR_B, ADDR_C, ADDR_D = base_tests.ADDR_A, base_tests.ADDR_B, base_tests.ADDR_C, base_tests.ADDR_D

SLOT0 = "0x" + "00" * 32
SLOT1 = "0x" + "00" * 31 + "01"
PREDEPLOY = "0x4200000000000000000000000000000000000007"


class TestSlipstreamCLFactory(unittest.TestCase):
    T = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"

    def _wire(self, fake, swap=ADDR_A, unstaked=ADDR_A, safe=(None, None)):
        fake.address_getters[(self.T, "owner")] = ADDR_A
        fake.address_getters[(self.T, "swapFeeManager")] = swap
        fake.address_getters[(self.T, "unstakedFeeManager")] = unstaked
        if safe[0] is not None:
            fake.safe_results[ADDR_A] = safe

    def test_one_3_of_7_safe_on_all_roles_scores_like_aerodrome_v1(self):
        fake = FakeHelpers()
        self._wire(fake, safe=(_owners(7), 3))
        _patch_helpers(self, fake)
        r = scorers.score_aerodrome_slipstream_clfactory(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 65, 0, 46))
        self.assertEqual(len(r["rootSafeOwners"]), 7)

    def test_fee_manager_on_a_different_key_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, swap=ADDR_B, safe=(_owners(7), 3))
        _patch_helpers(self, fake)
        r = scorers.score_aerodrome_slipstream_clfactory(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)
        self.assertEqual(r["rootSafeOwners"], [])

    def test_owner_not_a_safe_degrades(self):
        fake = FakeHelpers()
        self._wire(fake)
        _patch_helpers(self, fake)
        r = scorers.score_aerodrome_slipstream_clfactory(FakeW3())
        self.assertEqual(r["compositeScore"], scorers._composite(20, 0, 0))


class TestUniswapDirectForwarder(unittest.TestCase):
    V2 = "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"
    V4 = "0x498581fF718922c3f8e6A244956aF099B2652b2b"

    def _wire(self, fake, target, getter, slot0=PREDEPLOY, delay=172800):
        fake.address_getters[(target, getter)] = ADDR_B
        fake.slot_results[(ADDR_B, SLOT0)] = slot0
        fake.slot_results[(ADDR_B, SLOT1)] = ADDR_C
        fake.call_raw_results[(ADDR_C, "delay", ())] = delay
        fake.call_raw_results[(ADDR_C, "admin", ())] = ADDR_D

    def test_v2_resolved_scores_85_and_uses_l1_rpc(self):
        fake = FakeHelpers()
        self._wire(fake, self.V2, "feeToSetter")
        _patch_helpers(self, fake)
        r = scorers.score_uniswap_v2_factory_base(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"], r["compositeScore"]), (80, 75, 85))
        self.assertEqual(fake.l1_rpc_url, "https://ethereum-rpc.publicnode.com")

    def test_v4_resolved_scores_85(self):
        fake = FakeHelpers()
        self._wire(fake, self.V4, "owner")
        _patch_helpers(self, fake)
        r = scorers.score_uniswap_v4_poolmanager_base(FakeW3())
        self.assertEqual(r["compositeScore"], 85)

    def test_wrong_slot0_degrades_admin_and_timelock(self):
        fake = FakeHelpers()
        self._wire(fake, self.V4, "owner", slot0=ADDR_D)
        _patch_helpers(self, fake)
        r = scorers.score_uniswap_v4_poolmanager_base(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (20, 0))

    def test_l1_delay_unresolved_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, self.V2, "feeToSetter", delay=None)
        _patch_helpers(self, fake)
        r = scorers.score_uniswap_v2_factory_base(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (20, 0))


class TestMoonwellComptroller(unittest.TestCase):
    T = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
    SENDER = bytes(12) + bytes.fromhex("8769b70ac7c93af0e75de0d69877709b66d75838")

    def _wire(self, fake, senders, delay=86400):
        fake.address_getters[(self.T, "admin")] = ADDR_A
        fake.call_raw_results[(ADDR_A, "proposalDelay", ())] = delay
        fake.call_raw_results[(ADDR_A, "allTrustedSenders", (2,))] = senders
        fake.call_raw_results[(ADDR_A, "guardianPauseAllowed", ())] = True
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B
        fake.safe_results[ADDR_B] = (_owners(5), 3)

    def test_expected_sender_and_delay_scores_71(self):
        fake = FakeHelpers()
        self._wire(fake, [self.SENDER])
        _patch_helpers(self, fake)
        r = scorers.score_moonwell_comptroller_base(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"], r["compositeScore"]), (65, 50, 71))

    def test_unexpected_extra_sender_degrades(self):
        fake = FakeHelpers()
        self._wire(fake, [self.SENDER, bytes(12) + bytes.fromhex("dd" * 20)])
        _patch_helpers(self, fake)
        r = scorers.score_moonwell_comptroller_base(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (30, 0))

    def test_zero_delay_scores_timelock_zero(self):
        fake = FakeHelpers()
        self._wire(fake, [self.SENDER], delay=0)
        _patch_helpers(self, fake)
        r = scorers.score_moonwell_comptroller_base(FakeW3())
        self.assertEqual(r["timelockScore"], 0)


class TestIntraBaseOverlap(unittest.TestCase):
    def _entry(self, label, owners, cross=100):
        return {"label": label, "rootSafeOwners": owners, "crossExposureScore": cross, "notes": [scorers._CROSS_EXPOSURE_NOTE]}

    def test_shared_safe_costs_20_each_and_drops_stale_note(self):
        a, b = self._entry("A", _owners(7)), self._entry("B", _owners(7))
        c = self._entry("C", _owners(9, start=100), cross=80)
        scorers._apply_intra_base_overlap([a, b, c])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"], c["crossExposureScore"]), (80, 80, 80))
        self.assertNotIn(scorers._CROSS_EXPOSURE_NOTE, a["notes"])
        self.assertTrue(any("no root signer shared" in n for n in c["notes"]))

    def test_one_shared_signer_is_enough_and_stacks_on_prior_deduction(self):
        a = self._entry("A", _owners(3), cross=80)
        b = self._entry("B", _owners(3, start=3))  # shares exactly one owner
        scorers._apply_intra_base_overlap([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (60, 80))

    def test_targets_without_root_safe_are_ignored(self):
        a = self._entry("A", [])
        scorers._apply_intra_base_overlap([a])
        self.assertEqual(a["crossExposureScore"], 100)
        self.assertEqual(a["notes"], [scorers._CROSS_EXPOSURE_NOTE])


if __name__ == "__main__":
    unittest.main()
