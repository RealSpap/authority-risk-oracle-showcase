"""
Unit tests for scripts/lib/issuer_power.py's pure classification logic -- no live RPC/Blockscout.
read_abi()/read_controllers() (network calls in the CLI script) are exercised by
scripts/check_issuer_power.py against the real Blockscout API and chain RPCs, not here.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.issuer_power import KNOWN_ROLE_MEMBER_GETTERS, classify_controller, classify_functions, has_any_restrictive_power  # noqa: E402


class TestClassifyFunctions(unittest.TestCase):
    def test_finds_freeze_family(self):
        fns = {"transfer", "blacklist", "addBlackList", "mint"}
        families = classify_functions(fns)
        self.assertIn("blacklist", families["freeze"])
        self.assertIn("addBlackList", families["freeze"])
        self.assertEqual(families["seize"], [])

    def test_finds_seize_family(self):
        fns = {"destroyBlackFunds", "seizeFrom", "transfer"}
        families = classify_functions(fns)
        self.assertIn("destroyBlackFunds", families["seize"])
        self.assertIn("seizeFrom", families["seize"])

    def test_finds_pause_family(self):
        fns = {"pause", "unpause", "transfer"}
        families = classify_functions(fns)
        self.assertEqual(sorted(families["pause"]), ["pause", "unpause"])

    def test_finds_upgrade_prefix_only(self):
        fns = {"upgradeTo", "upgradeToAndCall", "upgradeable_marker_but_not_prefixed"}
        families = classify_functions(fns)
        self.assertIn("upgradeTo", families["upgrade"])
        self.assertIn("upgradeToAndCall", families["upgrade"])
        self.assertNotIn("upgradeable_marker_but_not_prefixed", families["upgrade"])

    def test_case_insensitive_matching(self):
        fns = {"BLACKLIST", "Pause"}
        families = classify_functions(fns)
        self.assertIn("BLACKLIST", families["freeze"])
        self.assertIn("Pause", families["pause"])

    def test_no_match_gives_empty_lists(self):
        families = classify_functions({"transfer", "approve", "balanceOf"})
        self.assertEqual(families, {"freeze": [], "seize": [], "pause": [], "upgrade": []})

    def test_capped_at_four_per_family(self):
        fns = {f"blacklist{i}" for i in range(10)}
        families = classify_functions(fns)
        self.assertEqual(len(families["freeze"]), 4)


class TestHasAnyRestrictivePower(unittest.TestCase):
    def test_true_when_freeze_present(self):
        self.assertTrue(has_any_restrictive_power({"freeze": ["blacklist"], "seize": [], "pause": [], "upgrade": []}))

    def test_true_when_seize_present(self):
        self.assertTrue(has_any_restrictive_power({"freeze": [], "seize": ["wipe"], "pause": [], "upgrade": []}))

    def test_true_when_pause_present(self):
        self.assertTrue(has_any_restrictive_power({"freeze": [], "seize": [], "pause": ["pause"], "upgrade": []}))

    def test_false_when_only_upgrade_present(self):
        # Upgrade alone is deliberately NOT folded into the headline "restrictive" flag -- an
        # implementation change is a different kind of risk than a direct balance action.
        self.assertFalse(has_any_restrictive_power({"freeze": [], "seize": [], "pause": [], "upgrade": ["upgradeTo"]}))

    def test_false_when_nothing_found(self):
        self.assertFalse(has_any_restrictive_power({"freeze": [], "seize": [], "pause": [], "upgrade": []}))


class TestClassifyController(unittest.TestCase):
    def test_unread_when_code_len_none(self):
        self.assertEqual(classify_controller(None, False), "unread")

    def test_eoa_when_zero_code(self):
        self.assertEqual(classify_controller(0, False), "EOA")

    def test_safe_with_shape(self):
        self.assertEqual(classify_controller(1000, True, (3, 5)), "3-of-5 Safe")

    def test_contract_when_not_safe(self):
        self.assertEqual(classify_controller(500, False), "contract (500B)")

    def test_safe_flag_without_shape_falls_back_to_contract_label(self):
        # is_safe True but no shape given (defensive: caller should always pass shape when is_safe is
        # True, but this must not crash if it doesn't).
        self.assertEqual(classify_controller(500, True, None), "contract (500B)")


class TestKnownRoleMemberGetters(unittest.TestCase):
    def test_freezer_and_pauser_are_covered(self):
        # AUSD's own gap, closed 2026-09-26: getFreezerRoleMembers/getPauserRoleMembers must be
        # present or check_issuer_power.py silently misses AUSD's freeze/pause holders again.
        self.assertIn("getFreezerRoleMembers", KNOWN_ROLE_MEMBER_GETTERS)
        self.assertIn("getPauserRoleMembers", KNOWN_ROLE_MEMBER_GETTERS)

    def test_no_duplicates(self):
        self.assertEqual(len(KNOWN_ROLE_MEMBER_GETTERS), len(set(KNOWN_ROLE_MEMBER_GETTERS)))


if __name__ == "__main__":
    unittest.main()
