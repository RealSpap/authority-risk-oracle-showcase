"""Regression guard for chains/tempo/deploy/push_scores_checked.py: a Tempo push that is missing a tracked target (Held's arbiter dropped by
score_all() with only a "NOT scored this run" line) is refused, in a dry run too. Offline: no RPC, no key.

Run:  python3 -m unittest discover -s chains/tempo/tests -v
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load():
    spec = importlib.util.spec_from_file_location("push_scores_checked", os.path.join(REPO_ROOT, "chains", "tempo", "deploy", "push_scores_checked.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _lines(ps, skip=None):
    mt = ps.scorers.mt
    addrs = ["0x%040x" % (i + 1) for i in range(ps.expected_count())]
    addrs[-1] = list(mt.HELD_ARBITER_TARGETS.values())[0]   # Held's arbiter is the last line, as score_all() appends it
    return [{"target": a} for a in addrs if a != skip]


class TestRequireAllTracked(unittest.TestCase):
    def test_fifteen_lines_today(self):
        # counted from the code; this fails on purpose when a target is added, so the number is updated deliberately
        self.assertEqual(_load().expected_count(), 15)

    def test_a_complete_push_passes(self):
        ps = _load()
        ps.require_all_tracked(_lines(ps))

    def test_a_push_without_held_is_refused(self):
        ps = _load()
        held = list(ps.scorers.mt.HELD_ARBITER_TARGETS.values())[0]
        with self.assertRaises(SystemExit) as cm:
            ps.require_all_tracked(_lines(ps, skip=held))
        self.assertIn("REFUSING", str(cm.exception))
        self.assertIn("Held arbiter", str(cm.exception))

    def test_a_push_with_one_mainnet_target_missing_is_refused(self):
        ps = _load()
        with self.assertRaises(SystemExit):
            ps.require_all_tracked(_lines(ps)[1:])

    def test_main_refuses_a_push_without_held_before_encoding_anything(self):
        ps = _load()
        held = list(ps.scorers.mt.HELD_ARBITER_TARGETS.values())[0]
        with mock.patch.object(ps.ps, "score_all", return_value=_lines(ps, skip=held)), mock.patch.object(sys, "argv", ["push_scores.py", "--dry-run"]), \
                mock.patch.object(ps.ps, "build_targets_and_tuples", side_effect=AssertionError("encoded a push that is missing Held")):
            with self.assertRaises(SystemExit) as cm:
                ps.main()
        self.assertIn("REFUSING", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
