"""The Solana push script refuses what the EVM push scripts refuse: a target the Registry tracks but the scorer did not return,
an unreadable published state, and a held score. review_before_push is executed from the script's source (importing the module
would shadow this directory's `scorers`, see test_oracle_keys)."""
import ast
import os
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts", "lib"))
import push_guard  # noqa: E402

SRC = os.path.join(REPO, "chains", "solana", "deploy", "update_scores_solana.py")


def _load():
    source = open(SRC, encoding="utf-8").read()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "review_before_push")
    ns = {"push_guard": push_guard}
    exec(compile(ast.Module(body=[node], type_ignores=[]), SRC, "exec"), ns)
    return ns["review_before_push"]


review_before_push = _load()
A, B = "So11111111111111111111111111111111111111112", "Vote111111111111111111111111111111111111111"


def entry(target, composite=70, notes=()):
    return {"target": target, "label": target[:4], "compositeScore": composite, "adminKeyScore": 50, "multisigScore": 50,
            "timelockScore": 50, "oracleAuthorityScore": 100, "crossExposureScore": 100, "notes": list(notes)}


def pub(composite=70, oracle=100, cross=100):
    return {"compositeScore": composite, "oracleAuthorityScore": oracle, "crossExposureScore": cross}


class TestSolanaPushGuard(unittest.TestCase):
    def test_everything_tracked_and_unchanged_passes(self):
        review_before_push([entry(A), entry(B)], ([A, B], {A: pub(), B: pub()}))

    def test_a_tracked_target_the_scorer_lost_refuses(self):
        with self.assertRaises(SystemExit) as c:
            review_before_push([entry(A)], ([A, B], {A: pub()}))
        self.assertIn(B, str(c.exception))

    def test_a_retired_target_can_be_accepted_by_address(self):
        review_before_push([entry(A)], ([A, B], {A: pub()}), accepted_missing=[B])

    def test_unreadable_published_state_refuses_unless_skipped(self):
        with self.assertRaises(SystemExit):
            review_before_push([entry(A)], ([], None))
        review_before_push([entry(A)], ([], None), skip_published_check=True)

    def test_a_big_drop_is_held_then_accepted_by_address(self):
        with self.assertRaises(SystemExit) as c:
            review_before_push([entry(A, 40)], ([A], {A: pub(70)}))
        self.assertIn("--accept-held=" + A, str(c.exception))
        review_before_push([entry(A, 40)], ([A], {A: pub(70)}), accepted=[A])

    def test_a_first_publish_has_nothing_to_compare(self):
        review_before_push([entry(A), entry(B)], ([], {}))

    def test_a_degraded_branch_is_held(self):
        with self.assertRaises(SystemExit):
            review_before_push([entry(A, 60, ["conservative score: authority unresolved"])], ([A], {A: pub(70)}))


if __name__ == "__main__":
    unittest.main()
