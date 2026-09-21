"""
Unit tests for pure, RPC-free logic in the per-ecosystem `scorers.py` files
under `chains/` -- closing a coverage gap a 2026-09-17 adversarial bug hunt
found: `_apply_cross_exposure` (chains/ethereum-l1/scorers.py,
chains/solana/scorers.py) and Tempo's field-normalization fix
(chains/tempo/scorers.py's `_normalize_field_names`) are all plain list/dict
manipulation with no network I/O -- exactly the shape scripts/lib/tests/
already tests for `_composite`/`_apply_l1_cap` -- but neither had a test,
so a future regression (an off-by-one in the "100 - 20*others" ladder, or a
reverted pop() order) would pass all existing tests green.

Each ecosystem's `scorers.py` is loaded via importlib under a unique module
name rather than a bare `import scorers` -- every ecosystem in this project
has a file literally named `scorers.py`, and a bare import would collide
with whichever one Python already cached under that name if more than one
test module in this same unittest run imported one (the exact bug a
2026-09-17 bug hunt found in scripts/validate_all_scorers.py's own first
version).
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_scorers(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    ecosystem_dir = os.path.dirname(file_path)
    if ecosystem_dir not in sys.path:
        sys.path.insert(0, ecosystem_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


eth_l1 = _load_scorers("aro_test_eth_l1_scorers", "chains/ethereum-l1/scorers.py")
solana = _load_scorers("aro_test_solana_scorers", "chains/solana/scorers.py")
tempo = _load_scorers("aro_test_tempo_scorers", "chains/tempo/scorers.py")


class TestEthereumL1ApplyCrossExposure(unittest.TestCase):
    def _entry(self, label, group, composite=50):
        return {"label": label, "compositeScore": composite, "notes": [], "_rootGroup": group}

    def test_solo_target_gets_100_and_no_note(self):
        results = [self._entry("A", "group-a")]
        eth_l1._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 100)
        self.assertFalse(any("shares its root authority" in n for n in results[0]["notes"]))

    def test_ladder_is_100_minus_20_per_other_sharer(self):
        # 5 targets sharing one root group: each should see 4 "others" -> 100 - 20*4 = 20
        results = [self._entry(f"T{i}", "shared") for i in range(5)]
        eth_l1._apply_cross_exposure(results)
        for r in results:
            self.assertEqual(r["crossExposureScore"], 20)

    def test_two_way_sharing_gives_80(self):
        results = [self._entry("A", "shared"), self._entry("B", "shared"), self._entry("C", "solo")]
        eth_l1._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 80)
        self.assertEqual(results[1]["crossExposureScore"], 80)
        self.assertEqual(results[2]["crossExposureScore"], 100)

    def test_internal_rootgroup_field_is_deleted_afterward(self):
        results = [self._entry("A", "group-a")]
        eth_l1._apply_cross_exposure(results)
        self.assertNotIn("_rootGroup", results[0])


class TestSolanaApplyCrossExposure(unittest.TestCase):
    def _entry(self, label, signers, composite=50):
        return {"label": label, "compositeScore": composite, "notes": [], "_signers": set(signers)}

    def test_disjoint_signers_score_100(self):
        results = [self._entry("Jupiter", {"a", "b"}), self._entry("Kamino", {"c", "d"})]
        solana._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 100)
        self.assertEqual(results[1]["crossExposureScore"], 100)

    def test_shared_signer_drops_score_by_20_per_sharer(self):
        results = [self._entry("A", {"x", "y"}), self._entry("B", {"y", "z"})]
        solana._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 80)
        self.assertEqual(results[1]["crossExposureScore"], 80)

    def test_empty_signers_never_falsely_matches_another_empty_set(self):
        # two unresolved/degraded targets both with empty _signers must NOT
        # be reported as "sharing" (an empty set intersected with anything,
        # including another empty set, is falsy)
        results = [self._entry("A", set()), self._entry("B", set())]
        solana._apply_cross_exposure(results)
        self.assertEqual(results[0]["crossExposureScore"], 100)
        self.assertEqual(results[1]["crossExposureScore"], 100)

    def test_internal_signers_field_is_deleted_afterward(self):
        results = [self._entry("A", {"a"})]
        solana._apply_cross_exposure(results)
        self.assertNotIn("_signers", results[0])


class TestTempoNormalizeFieldNames(unittest.TestCase):
    def test_swaps_target_and_address_into_label_and_target(self):
        results = [{"target": "USDC.e", "address": "0xABC123"}]
        tempo._normalize_field_names(results)
        self.assertEqual(results[0]["label"], "USDC.e")
        self.assertEqual(results[0]["target"], "0xABC123")
        self.assertNotIn("address", results[0])

    def test_idempotent_second_call_is_a_safe_no_op(self):
        # Regression test for a 2026-09-17 bug hunt finding: the original
        # implementation destructively popped "target"/"address", so a
        # second call clobbered "label" with the address and then raised
        # KeyError on the already-removed "address" key.
        results = [{"target": "USDC.e", "address": "0xABC123"}]
        tempo._normalize_field_names(results)
        first_pass = dict(results[0])
        tempo._normalize_field_names(results)  # must not raise, must not change anything
        self.assertEqual(results[0], first_pass)
        self.assertEqual(results[0]["label"], "USDC.e")
        self.assertEqual(results[0]["target"], "0xABC123")


if __name__ == "__main__":
    unittest.main()
