"""
Unit tests for scripts/lib/vault_v2_inventory.py's pure classification logic -- no live RPC/API.
fetch_vaults()/read_holder() (network calls in the CLI script) are exercised by
scripts/check_vault_v2_inventory.py against the real Morpho API and chain RPCs, not here.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.vault_v2_inventory import DISCLOSED_TIMELOCK_FUNCTIONS, classify_holder, format_holder, timelock_summary  # noqa: E402


class TestClassifyHolder(unittest.TestCase):
    def test_unread_when_code_len_is_none(self):
        self.assertEqual(classify_holder(None, False), "unread")
        self.assertEqual(classify_holder(None, True), "unread")  # is_safe irrelevant if code couldn't be read

    def test_safe_when_flagged_safe_regardless_of_code_len(self):
        self.assertEqual(classify_holder(1000, True), "safe")

    def test_eoa_when_zero_code_and_not_safe(self):
        self.assertEqual(classify_holder(0, False), "eoa")

    def test_contract_when_positive_code_and_not_safe(self):
        self.assertEqual(classify_holder(500, False), "contract")


class TestFormatHolder(unittest.TestCase):
    def test_safe_with_shape(self):
        self.assertEqual(format_holder("safe", (3, 5)), "3-of-5 Safe")

    def test_safe_without_shape(self):
        self.assertEqual(format_holder("safe", None), "Safe (shape unread)")

    def test_eoa(self):
        self.assertEqual(format_holder("eoa"), "bare EOA")

    def test_contract(self):
        self.assertEqual(format_holder("contract"), "contract (not a Safe)")

    def test_unread(self):
        self.assertEqual(format_holder("unread"), "unread")


class TestTimelockSummary(unittest.TestCase):
    def test_restricted_to_disclosed_functions(self):
        raw = {"addAdapter": 259200, "someOtherFunction": 999, "abdicate": 604800}
        summary = timelock_summary(raw)
        self.assertEqual(set(summary), set(DISCLOSED_TIMELOCK_FUNCTIONS))
        self.assertEqual(summary["addAdapter"], 259200)
        self.assertEqual(summary["abdicate"], 604800)
        self.assertNotIn("someOtherFunction", summary)

    def test_missing_function_is_none_not_zero(self):
        summary = timelock_summary({"addAdapter": 259200})
        self.assertIsNone(summary["removeAdapter"])
        self.assertIsNone(summary["abdicate"])

    def test_empty_input_all_none(self):
        summary = timelock_summary({})
        self.assertTrue(all(v is None for v in summary.values()))


if __name__ == "__main__":
    unittest.main()
