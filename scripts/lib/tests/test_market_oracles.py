"""Unit tests for scripts/lib/market_oracles.py -- pure logic, no RPC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.market_oracles import concentration, controller_of, group_by_signers, market_feeds, path_split, weak_controller  # noqa: E402


class Feeds(unittest.TestCase):
    def test_extracts_distinct_nonnull_feeds(self):
        m = {"oracle": {"data": {"baseFeedOne": {"address": "0xA"}, "baseFeedTwo": None, "quoteFeedOne": {"address": "0xa"}, "quoteFeedTwo": {"address": "0xB"}}}}
        self.assertEqual(market_feeds(m), ["0xA", "0xB"])

    def test_custom_oracle_without_data_has_no_feeds(self):
        self.assertEqual(market_feeds({"oracle": {"type": "Unknown", "data": None}}), [])
        self.assertEqual(market_feeds({"oracle": None}), [])


class Controller(unittest.TestCase):
    def test_priority_proxyadmin_owner_then_admin_then_feed_owner(self):
        self.assertEqual(controller_of({"admin_owner": "O", "admin": "A", "feed_owner": "F"}), "O")
        self.assertEqual(controller_of({"admin": "A", "feed_owner": "F"}), "A")
        self.assertEqual(controller_of({"feed_owner": "F"}), "F")
        self.assertIsNone(controller_of({}))


class Concentration(unittest.TestCase):
    def test_market_with_two_feeds_behind_one_admin_counted_once(self):
        rows = [{"chain": 1, "market": "m1", "supplyUsd": 100.0, "controller": "X", "controller_class": "EOA"},
                {"chain": 1, "market": "m1", "supplyUsd": 100.0, "controller": "X", "controller_class": "EOA"},
                {"chain": 1, "market": "m2", "supplyUsd": 50.0, "controller": "X", "controller_class": "EOA"},
                {"chain": 8453, "market": "m3", "supplyUsd": 500.0, "controller": "X", "controller_class": "EOA"},
                {"chain": 1, "market": "m4", "supplyUsd": 5.0, "controller": None}]
        out = concentration(rows)
        self.assertEqual([(o["chain"], o["markets"], o["supplyUsd"]) for o in out], [(8453, 1, 500.0), (1, 2, 150.0)])


class Weak(unittest.TestCase):
    def test_weak_shapes(self):
        self.assertTrue(weak_controller("EOA"))
        self.assertTrue(weak_controller("2-of-3 Safe"))
        self.assertFalse(weak_controller("5-of-9 Safe"))
        self.assertFalse(weak_controller("contract (1200B)"))
        self.assertFalse(weak_controller(None))


class Groups(unittest.TestCase):
    def test_same_threshold_and_signers_on_two_chains_form_one_group(self):
        s = frozenset({"a", "b", "c"})
        g = group_by_signers({(1, "X"): (2, s), (8453, "Y"): (2, s), (1, "Z"): (3, s), (1, "W"): (2, frozenset({"a"}))})
        self.assertEqual(sorted(g[(2, s)]), [(1, "X"), (8453, "Y")])
        self.assertEqual(len(g), 3)


class PathSplit(unittest.TestCase):
    def test_backup_only_market_is_split_out_and_counted_once(self):
        members = {(1, "C")}
        rows = [{"chain": 1, "controller": "C", "market": "direct", "supplyUsd": 100.0, "kind": "feed"},
                {"chain": 1, "controller": "C", "market": "meta_primary", "supplyUsd": 10.0, "kind": "primaryOracle-feed"},
                {"chain": 1, "controller": "C", "market": "meta_primary", "supplyUsd": 10.0, "kind": "backupOracle-feed"},
                {"chain": 1, "controller": "C", "market": "meta_backup", "supplyUsd": 40.0, "kind": "backupOracle-feed"},
                {"chain": 1, "controller": "OTHER", "market": "elsewhere", "supplyUsd": 999.0, "kind": "feed"}]
        r = path_split(rows, members, 1000.0)
        self.assertEqual(r["live"], (2, 110.0))
        self.assertEqual(r["backup_only"], (1, 40.0))
        self.assertEqual(r["all"], (3, 150.0))
        self.assertAlmostEqual(r["live_share"], 0.11)
        self.assertAlmostEqual(r["all_share"], 0.15)


class PostedPriceSelector(unittest.TestCase):
    def test_set_round_data_selector_is_the_one_read_on_the_midas_feeds(self):
        # 0xa4381d1f was matched in the dispatcher of the mF-ONE / mGLO feed implementations on 2026-09-26.
        import check_morpho_market_oracles as census
        self.assertEqual(census.SET_ROUND_DATA, "0xa4381d1f")


if __name__ == "__main__":
    unittest.main()
