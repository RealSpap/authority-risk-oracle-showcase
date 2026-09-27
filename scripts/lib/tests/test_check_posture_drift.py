"""oracle_keys_for(), the one branch of scripts/check_posture_drift.py that isn't a live RPC read: does it key Hyperliquid's
two colliding HIP-3 dexes the same way the real push does, and leave every other ecosystem untouched?"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
_spec = importlib.util.spec_from_file_location("aro_check_posture_drift", os.path.join(HERE, "..", "..", "check_posture_drift.py"))
cpd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpd)

PARA_DEX = {"target": "0x8888888c43cbb7e1c4132542e46831bffd866ed3", "label": "HIP-3 dex para"}
PARA_VAULT = {"target": "0x8888888c43cbb7e1c4132542e46831bffd866ed3", "label": "para StakingVault (HyperEVM)"}
MKTS_DEX = {"target": "0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec", "label": "HIP-3 dex mkts"}
KINETIQ = {"target": "0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec", "label": "Kinetiq HIP3StakingManager (HyperEVM)"}
OTHER = {"target": "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303", "label": "Hyperliquidity Provider (HLP) vault"}


class OracleKeysFor(unittest.TestCase):
    def test_hyperliquid_colliding_dexes_get_the_same_derived_key_the_real_push_uses(self):
        keys = cpd.oracle_keys_for("hyperliquid", [PARA_DEX, PARA_VAULT, MKTS_DEX, KINETIQ, OTHER])
        self.assertEqual(len(set(k.lower() for k in keys)), 5, "each entry must end up under its own key, no collision")
        self.assertEqual(keys[1].lower(), PARA_VAULT["target"])  # the HyperEVM contract keeps its real address
        self.assertEqual(keys[3].lower(), KINETIQ["target"])
        self.assertNotEqual(keys[0].lower(), PARA_DEX["target"])  # the dex itself moves to a derived key
        self.assertNotEqual(keys[2].lower(), MKTS_DEX["target"])
        self.assertEqual(keys[4].lower(), OTHER["target"])  # untouched

    def test_other_ecosystems_are_never_remapped_even_with_a_collision(self):
        # A same-address pair on any OTHER ecosystem is not this function's problem to solve (push_scores.py
        # there would refuse it, per the shared assert_unique_oracle_keys guard) -- it must not silently remap.
        keys = cpd.oracle_keys_for("ethereum-l1", [PARA_DEX, PARA_VAULT])
        self.assertEqual([k.lower() for k in keys], [PARA_DEX["target"], PARA_VAULT["target"]])

    def test_no_collision_on_hyperliquid_leaves_every_key_as_is(self):
        keys = cpd.oracle_keys_for("hyperliquid", [MKTS_DEX, OTHER])
        self.assertEqual([k.lower() for k in keys], [MKTS_DEX["target"], OTHER["target"]])


if __name__ == "__main__":
    unittest.main()
