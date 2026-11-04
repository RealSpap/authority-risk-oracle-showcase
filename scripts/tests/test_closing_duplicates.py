"""Closing addition of 30/10/2026: a contract listed twice in a score file is signalled by the agent tools instead of answered with the first row. Standard library only; no network."""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import agent_tools  # noqa: E402
A = "0xaaa0000000000000000000000000000000000001"


class TestDuplicateRows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.W = self.tmp.name; os.makedirs(os.path.join(self.W, "scores"))

    def row(self, addr=A, comp=70, **kw):
        return dict({"target": addr, "adminKeyScore": 80, "multisigScore": 100, "timelockScore": 75, "oracleAuthorityScore": 100, "crossExposureScore": 80, "compositeScore": comp, "lastUpdated": 1790000000, "stale": False, "methodologyHash": "0x" + "ab" * 32}, **kw)

    def write(self, rows):
        json.dump({"name": "Base (Sepolia)", "kind": "evm", "oracle": "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "rpc": "https://sepolia.base.org", "block": 1, "maxStaleness": 777600, "readAt": 1790000100, "targets": rows},
                  open(os.path.join(self.W, "scores", "base-sepolia.json"), "w"))

    def test_one_row_is_unchanged(self):
        self.write([self.row()]); r = agent_tools.get_score(self.W, "base", A)
        self.assertEqual((r["status"], r["composite"]), ("ok", 70)); self.assertNotIn("duplicate_rows", r)

    def test_two_different_rows_are_not_answered_with_the_first(self):
        self.write([self.row(comp=70), self.row(comp=30)]); r = agent_tools.get_score(self.W, "base", A)
        self.assertEqual(r["status"], "not_read"); self.assertIsNone(r["composite"]); self.assertTrue(r["duplicate"]); self.assertEqual(r["duplicate_rows"], 2)
        json.dump({"results": [{"chain": "base", "target": A, "kind": "eoa", "holder": "0xccc0000000000000000000000000000000000003", "posture": "a plain key"}]}, open(os.path.join(self.W, "second_opinion.json"), "w"))
        w = agent_tools.who_controls(self.W, "base", A); self.assertEqual((w["status"], w["duplicate"]), ("not_read", True))   # with the independent reader present, only the duplicate check can refuse
        self.write([self.row(), self.row()]); w = agent_tools.who_controls(self.W, "base", A); self.assertEqual((w["status"], w["duplicate_rows"]), ("ok", 2))

    def test_a_row_that_differs_only_in_a_sub_score_is_also_ambiguous(self):
        self.write([self.row(), self.row(timelockScore=0)]); self.assertTrue(agent_tools.get_score(self.W, "base", A)["duplicate"])

    def test_a_row_that_differs_only_in_the_previous_composite_is_ambiguous(self):
        self.write([self.row(previousComposite=10), self.row(previousComposite=20)]); self.assertTrue(agent_tools.get_score(self.W, "base", A)["duplicate"])

    def test_two_equal_rows_answer_and_say_they_are_two(self):
        self.write([self.row(), self.row()]); r = agent_tools.get_score(self.W, "base", A)
        self.assertEqual((r["status"], r["composite"], r["duplicate_rows"]), ("ok", 70, 2))

    def test_a_contract_listed_twice_is_counted_in_the_lists(self):
        self.write([self.row(), self.row(), self.row(addr="0xbbb0000000000000000000000000000000000002")])
        self.assertEqual(agent_tools.list_targets(self.W)["contracts_listed_twice"], 1)
        self.write([self.row(), self.row(addr="0xbbb0000000000000000000000000000000000002")]); self.assertEqual(agent_tools.list_targets(self.W)["contracts_listed_twice"], 0)

    def test_a_retired_contract_listed_twice_is_not_counted_as_listed(self):
        self.write([self.row(), self.row()]); json.dump({"targets": {"base:" + A: {"scope": "retired"}}}, open(os.path.join(self.W, "tvl_scope.json"), "w"))
        r = agent_tools.list_targets(self.W); self.assertEqual((r["of"], r["retired_not_listed"], r["contracts_listed_twice"]), (0, 2, 0))


if __name__ == "__main__":
    unittest.main()
