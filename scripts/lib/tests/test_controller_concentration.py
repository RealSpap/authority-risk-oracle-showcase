"""
Unit tests for scripts/lib/controller_concentration.py's pure grouping/ranking logic -- no live RPC.
read_vault_roles() (a thin live-call wrapper) and fetch_tvl() (an HTTP call in the CLI script) are
exercised by scripts/check_controller_concentration.py against the real chains and API, not here.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.controller_concentration import (  # noqa: E402
    build_controller_registry, config_varies_across_chains, rank_controllers, same_signers_across_roles,
)


def _addr(n: int) -> str:
    # A valid, deterministic 20-byte hex address built from a digit repeated
    # 40 times -- never hand-typed, so there's no transcription risk.
    return "0x" + str(n) * 40


class TestBuildControllerRegistry(unittest.TestCase):
    def test_two_vaults_same_controller_on_one_chain_merge(self):
        controller = _addr(1)
        rows = [
            ("base", "vault-a", "0xVAULTA", {"owner": controller}),
            ("base", "vault-b", "0xVAULTB", {"owner": controller}),
        ]
        safe_fn = lambda w3, addr: ([_addr(9), _addr(8), _addr(7)], 2)
        registry = build_controller_registry(rows, safe_fn, {"base": object()})
        self.assertEqual(len(registry), 1)
        info = registry[controller.lower()]
        self.assertEqual(info["vaults"], {("base", "vault-a"), ("base", "vault-b")})
        self.assertEqual(info["ecosystems"], {"base"})
        self.assertEqual(info["safe_by_ecosystem"]["base"], ([_addr(9), _addr(8), _addr(7)], 2))

    def test_same_address_different_chains_merges_but_keeps_per_chain_safe(self):
        controller = _addr(2)
        rows = [
            ("ethereum-l1", "vault-l1", "0xL1", {"owner": controller}),
            ("base", "vault-base", "0xBASE", {"owner": controller}),
        ]

        def safe_fn(w3, addr):
            return (["l1-owner1", "l1-owner2"], 2) if w3 == "l1-w3" else (["b1", "b2", "b3"], 1)

        registry = build_controller_registry(rows, safe_fn, {"ethereum-l1": "l1-w3", "base": "base-w3"})
        info = registry[controller.lower()]
        self.assertEqual(info["ecosystems"], {"ethereum-l1", "base"})
        self.assertEqual(info["safe_by_ecosystem"]["ethereum-l1"], (["l1-owner1", "l1-owner2"], 2))
        self.assertEqual(info["safe_by_ecosystem"]["base"], (["b1", "b2", "b3"], 1))
        # the bug this module's own docstring warns about: a naive "resolve once" implementation
        # would have applied ethereum-l1's (2-owner, threshold 2) shape to base too.
        self.assertNotEqual(info["safe_by_ecosystem"]["ethereum-l1"], info["safe_by_ecosystem"]["base"])

    def test_multiple_roles_on_same_vault_recorded(self):
        controller = _addr(3)
        rows = [("base", "vault-a", "0xVAULTA", {"owner": controller, "curator": controller, "guardian": controller})]
        registry = build_controller_registry(rows, lambda w3, a: (["x"], 1), {"base": object()})
        info = registry[controller.lower()]
        self.assertEqual(info["roles_by_vault"][("base", "vault-a")], {"owner": True, "curator": True, "guardian": True})

    def test_zero_address_role_skipped(self):
        rows = [("base", "vault-a", "0xVAULTA", {"owner": "0x" + "0" * 40, "curator": _addr(4)})]
        registry = build_controller_registry(rows, lambda w3, a: (["x"], 1), {"base": object()})
        self.assertNotIn(("0x" + "0" * 40), registry)
        self.assertIn(_addr(4).lower(), registry)

    def test_unresolved_safe_recorded_as_false_not_missing(self):
        controller = _addr(5)
        rows = [("base", "vault-a", "0xVAULTA", {"owner": controller})]
        registry = build_controller_registry(rows, lambda w3, a: None, {"base": object()})
        self.assertIs(registry[controller.lower()]["safe_by_ecosystem"]["base"], False)


class TestConfigVariesAcrossChains(unittest.TestCase):
    def test_identical_shape_on_every_chain_is_false(self):
        by_eco = {"ethereum-l1": (["a", "b", "c"], 2), "base": (["x", "y", "z"], 2)}
        self.assertFalse(config_varies_across_chains(by_eco))

    def test_different_threshold_is_true(self):
        by_eco = {"ethereum-l1": (["a", "b", "c"], 2), "base": (["x", "y"], 1)}
        self.assertTrue(config_varies_across_chains(by_eco))

    def test_different_owner_count_same_threshold_is_true(self):
        by_eco = {"ethereum-l1": (["a", "b", "c"], 2), "base": (["x", "y", "z", "w"], 2)}
        self.assertTrue(config_varies_across_chains(by_eco))

    def test_unresolved_entries_ignored_not_a_mismatch(self):
        by_eco = {"ethereum-l1": (["a", "b", "c"], 2), "base": False}
        self.assertFalse(config_varies_across_chains(by_eco))

    def test_single_chain_is_false(self):
        self.assertFalse(config_varies_across_chains({"base": (["a"], 1)}))


class TestSameSignersAcrossRoles(unittest.TestCase):
    def test_two_or_more_roles_present_is_true(self):
        self.assertTrue(same_signers_across_roles({"owner": True, "curator": True}))
        self.assertTrue(same_signers_across_roles({"owner": True, "curator": True, "guardian": True}))

    def test_one_role_is_false(self):
        self.assertFalse(same_signers_across_roles({"owner": True}))


class TestRankControllers(unittest.TestCase):
    def _registry(self):
        return {
            "0xbig": {"roles_by_vault": {("base", "v1"): {"owner": True}, ("base", "v2"): {"owner": True}},
                      "safe_by_ecosystem": {}, "vaults": {("base", "v1"), ("base", "v2")}, "ecosystems": {"base"}},
            "0xsmall": {"roles_by_vault": {("base", "v3"): {"owner": True}},
                        "safe_by_ecosystem": {}, "vaults": {("base", "v3")}, "ecosystems": {"base"}},
            "0xmultihat": {"roles_by_vault": {("base", "v4"): {"owner": True, "curator": True, "guardian": True}},
                           "safe_by_ecosystem": {}, "vaults": {("base", "v4")}, "ecosystems": {"base"}},
        }

    def test_sorted_by_vault_count_desc(self):
        tvl = {("base", "v1"): 10.0, ("base", "v2"): 5.0, ("base", "v3"): 1000.0, ("base", "v4"): 1.0}
        ranked = rank_controllers(self._registry(), tvl)
        self.assertEqual(ranked[0][0], "0xbig")  # 2 vaults beats 1 vault even though 0xsmall has more TVL

    def test_max_roles_on_single_vault_computed(self):
        ranked = rank_controllers(self._registry(), {})
        by_addr = {row[0]: row for row in ranked}
        self.assertEqual(by_addr["0xmultihat"][4], 3)
        self.assertEqual(by_addr["0xbig"][4], 1)

    def test_missing_tvl_entries_default_to_zero(self):
        ranked = rank_controllers(self._registry(), {})
        by_addr = {row[0]: row for row in ranked}
        self.assertEqual(by_addr["0xsmall"][5], 0.0)


if __name__ == "__main__":
    unittest.main()
