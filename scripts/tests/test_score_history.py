"""Unit tests for scripts/score_history.py -- no RPC. The change detector and the
cause join are the logic; the live witness (22 changes under an unchanged hash,
17 corrections / 5 postures on 2026-09-30) is checked by running the script."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import score_history as sh  # noqa: E402

H1, H2 = "0x" + "11" * 32, "0x" + "22" * 32


def ev(block, target, composite, h=H1, li=0):
    return {"block": block, "logIndex": li, "tx": "0xt", "target": target, "composite": composite,
            "lastUpdated": 1_790_000_000, "methodologyHash": h}


class TestCompositeChanges(unittest.TestCase):
    def test_only_changes_per_target_are_listed(self):
        events = [ev(1, "0xA", 50), ev(1, "0xB", 70, li=1), ev(2, "0xA", 50), ev(3, "0xA", 40), ev(3, "0xB", 70, li=1)]
        changes = sh.composite_changes(events)
        self.assertEqual([(c["target"], c["from"], c["to"], c["block"]) for c in changes], [("0xA", 50, 40, 3)])
        self.assertTrue(changes[0]["sameHash"])

    def test_hash_change_is_flagged(self):
        changes = sh.composite_changes([ev(1, "0xA", 57, H1), ev(2, "0xA", 60, H2)])
        self.assertFalse(changes[0]["sameHash"])

    def test_first_push_is_not_a_change(self):
        self.assertEqual(sh.composite_changes([ev(1, "0xA", 10)]), [])


class TestClassify(unittest.TestCase):
    def test_join_is_case_insensitive_and_unknown_is_unclassified(self):
        causes = {("Plasma", "0xabc", 5): {"cause": "correction", "ref": "b464fbe", "label": "Yuzu"}}
        out = sh.classify("Plasma", [{"target": "0xABC", "block": 5}, {"target": "0xABC", "block": 6}], causes)
        self.assertEqual([c["cause"] for c in out], ["correction", "UNCLASSIFIED"])

    def test_shipped_causes_file_is_well_formed(self):
        causes = sh.load_causes()
        self.assertTrue(causes)
        self.assertTrue(all(r["cause"] in ("correction", "posture", "mixed") for r in causes.values()))


if __name__ == "__main__":
    unittest.main()
