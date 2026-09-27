"""Unit tests for scripts/lib/tvl_coverage.py -- pure logic, no network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.tvl_coverage import coverage, is_tracked, label_tokens, significant  # noqa: E402

PROTOCOLS = [
    {"name": "Aave V3", "category": "Lending", "chainTvls": {"Base": 900.0}},
    {"name": "Steakhouse Financial", "category": "Yield", "chainTvls": {"Base": 600.0}},
    {"name": "Binance CEX", "category": "CEX", "chainTvls": {"Base": 5000.0}},
    {"name": "SmallThing", "category": "Dexs", "chainTvls": {"Base": 50.0, "Arbitrum": 1.0}},
    {"name": "Elsewhere", "category": "Dexs", "chainTvls": {"Arbitrum": 10.0}},
]


class Match(unittest.TestCase):
    def test_significant_drops_version_and_generic_words(self):
        self.assertEqual(significant("Aave V3 Protocol"), ["aave"])
        self.assertEqual(significant("The Steakhouse Financial"), ["steakhouse", "financial"])

    def test_first_significant_token_must_appear_in_a_label(self):
        lt = label_tokens(["Aave V3 Pool (Base)", "Morpho Steakhouse USDC"])
        self.assertTrue(is_tracked("Aave V3", lt))
        self.assertTrue(is_tracked("Steakhouse Financial", lt))
        self.assertFalse(is_tracked("SmallThing", lt))


class Alias(unittest.TestCase):
    def test_a_renamed_protocol_matches_its_old_label(self):
        self.assertTrue(is_tracked("EigenCloud", label_tokens(["EigenLayer StrategyManager (Ethereum L1)"])))
        self.assertFalse(is_tracked("EigenCloud", label_tokens(["Aave V3 Pool"])))

    def test_a_rename_keyed_by_full_name_does_not_leak_to_a_namesake(self):
        lt = label_tokens(["GMSOL (GMTrade, six programs)"])
        self.assertTrue(is_tracked("GMX Solana", lt))
        self.assertFalse(is_tracked("GMX V2", lt))  # a different protocol that shares the first token

    def test_a_name_with_no_significant_token_can_still_be_aliased(self):
        # "USD AI" -> tokens ["usd","ai"]: "usd" is a stopword, "ai" is under the 3-char floor -- significant() is empty,
        # so without the alias this name could never match any label, however it is tracked.
        self.assertEqual(significant("USD AI"), [])
        self.assertTrue(is_tracked("USD AI", label_tokens(["USD AI mint/burn authority (LayerZero OAdapter, Arbitrum)"])))
        self.assertFalse(is_tracked("USD AI", label_tokens(["Aave V3 Pool"])))


class Coverage(unittest.TestCase):
    def test_cex_excluded_and_share_and_unmatched_order(self):
        c = coverage(PROTOCOLS, "Base", ["Aave V3 Pool", "Morpho Steakhouse"])
        self.assertEqual(c["protocols"], 3)
        self.assertEqual(c["total_usd"], 1550.0)
        self.assertAlmostEqual(c["share"], 1500.0 / 1550.0)
        self.assertEqual([r[0] for r in c["largest_unmatched"]], ["SmallThing"])

    def test_chain_without_the_protocol_is_ignored(self):
        self.assertEqual(coverage(PROTOCOLS, "Arbitrum", [])["protocols"], 2)


if __name__ == "__main__":
    unittest.main()
