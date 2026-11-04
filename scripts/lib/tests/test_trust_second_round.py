"""Tests added by the second round of review: a score row that is not readable, whether waiting can help, and how many chat channels the run had.

No network. The documents are the real output of the trust rule (scripts/trust.py) on the fixture of a Watch run, altered the way each test says.
"""
import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "adversarial"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
from lib import trust_rules as tr  # noqa: E402
import harness  # noqa: E402
import trust_support as kit  # noqa: E402


def doc_of(edit=None):
    w = kit.Watch()
    try:
        if edit:
            edit(w)
        return w.trust(), w
    finally:
        w.close()


def row_edit(**fields):
    def f(w):
        def g(d):
            d["targets"][0].update(fields)
        w.edit("scores/robinhood-chain.json", g)
    return f


def first_key(d):
    return next(k for k in d["by_target"] if k.endswith(kit.A))


class TestEveryReasonIsClassified(unittest.TestCase):
    def test_each_code_is_transient_or_permanent_never_both_never_neither(self):
        codes = set(tr.REASONS)
        self.assertEqual(tr.TRANSIENT & tr.PERMANENT, set())
        self.assertEqual(codes - tr.TRANSIENT - tr.PERMANENT, set(), "a new reason must be classified: can a later run take it away by itself?")
        self.assertEqual((tr.TRANSIENT | tr.PERMANENT) - codes, set(), "a classified code that does not exist")


class TestAScoreRowThatCannotBeRead(unittest.TestCase):
    def test_a_row_without_composite_or_with_a_composite_outside_0_100_is_unverified(self):
        for bad in (None, True, 101, -1, 50.0, "50", [], {}):
            d, _ = doc_of(row_edit(compositeScore=bad))
            rec = d["by_target"][first_key(d)]
            self.assertEqual(rec["status"], "UNVERIFIED", repr(bad))
            self.assertIn("score_row_unreadable", [r["code"] for r in rec["reasons"]], repr(bad))

    def test_a_row_whose_stale_flag_is_not_a_boolean_is_unverified_and_true_is_stale_not_unverified(self):
        for bad in (None, "false", 0, 1, [], "true"):
            d, _ = doc_of(row_edit(stale=bad))
            rec = d["by_target"][first_key(d)]
            self.assertEqual(rec["status"], "UNVERIFIED", repr(bad))
            self.assertIn("stale_flag_unknown", [r["code"] for r in rec["reasons"]], repr(bad))
        d, _ = doc_of(row_edit(stale=True))
        rec = d["by_target"][first_key(d)]
        self.assertEqual(rec["status"], "STALE")
        self.assertNotIn("stale_flag_unknown", [r["code"] for r in rec["reasons"]])

    def test_a_missing_stale_key_is_unknown_not_fresh(self):
        def drop(w):
            def g(d):
                del d["targets"][0]["stale"]
            w.edit("scores/robinhood-chain.json", g)
        d, _ = doc_of(drop)
        self.assertIn("stale_flag_unknown", [r["code"] for r in d["by_target"][first_key(d)]["reasons"]])

    def test_the_fixture_and_the_boundaries_stay_verified(self):
        for comp in (0, 1, 99, 100):
            d, _ = doc_of(row_edit(compositeScore=comp))
            self.assertEqual(d["by_target"][first_key(d)]["status"], "VERIFIED", comp)


class TestASignatureThatWasRefusedLastTime(unittest.TestCase):
    def doc(self, sig_run, previous_run, signed=True):
        def f(w):
            w.edit("signature.json", lambda d: d.update({"run_utc": sig_run, "signed": signed}))
            w.edit("latest.json", lambda d: d.update({"previous_run_utc": previous_run}))
        return doc_of(f)[0]

    def test_a_manifest_older_than_the_previous_run_means_that_run_was_not_signed(self):
        d = self.doc("2026-10-21T00:00:00Z", "2026-10-30T00:20:00Z")
        rec = d["by_target"][first_key(d)]
        self.assertIn("signature_previous_run_missing", [r["code"] for r in rec["reasons"]])
        self.assertEqual(rec["status"], "PARTIAL")
        self.assertTrue(rec["retry_may_help"])

    def test_an_unsigned_manifest_says_unsigned_and_not_also_missing(self):
        d = self.doc("2026-10-21T00:00:00Z", "2026-10-30T00:20:00Z", signed=False)
        codes = [r["code"] for r in d["by_target"][first_key(d)]["reasons"]]
        self.assertIn("run_unsigned", codes)
        self.assertNotIn("signature_previous_run_missing", codes)

    def test_the_usual_case_and_the_unknown_cases_are_not_accused(self):
        for sig_run, prev in (("2026-10-30T00:20:00Z", "2026-10-30T00:20:00Z"), ("2026-10-30T06:20:00Z", "2026-10-30T00:20:00Z"), (None, "2026-10-30T00:20:00Z"),
                              ("2026-10-21T00:00:00Z", None), ("not a date", "2026-10-30T00:20:00Z")):
            d = self.doc(sig_run, prev)
            self.assertNotIn("signature_previous_run_missing", [r["code"] for r in d["by_target"][first_key(d)]["reasons"]], (sig_run, prev))


class TestWaitingCanHelp(unittest.TestCase):
    def test_flag_by_status_and_reason(self):
        self.assertFalse(tr._record({})["retry_may_help"])                                             # VERIFIED: nothing to wait for
        self.assertFalse(tr._record({"money_unknown": "x", "executor_open": "y"})["retry_may_help"])   # information only: still VERIFIED
        self.assertTrue(tr._record({"alert_undelivered": "x"})["retry_may_help"])                      # PARTIAL: the next run delivers it
        self.assertTrue(tr._record({"score_stale": "x", "input_stale:tvl": "y"})["retry_may_help"])    # STALE: the next read may refresh it
        self.assertTrue(tr._record({"alert_undelivered": "x", "money_unknown": "y"})["retry_may_help"])   # an information reason beside it does not count: money that no source figures is not what holds the status back
        self.assertFalse(tr._record({"score_fixed_by_decision": "x"})["retry_may_help"])             # PARTIAL for good: a decision, not a read
        self.assertFalse(tr._record({"native_entity": "x"})["retry_may_help"])                       # UNVERIFIED for good
        self.assertFalse(tr._record({"score_stale": "x", "native_entity": "y"})["retry_may_help"])   # one permanent reason is enough: STALE hides it, waiting does not remove it
        self.assertFalse(tr._record({"alert_undelivered": "x", "money_unknown": "y", "score_fixed_by_decision": "z"})["retry_may_help"])

    def test_every_published_record_carries_the_flag_as_a_boolean(self):
        d, _ = doc_of()
        for rec in d["by_target"].values():
            self.assertIsInstance(rec["retry_may_help"], bool)


class TestChannelsOfTheRun(unittest.TestCase):
    def alerts_edit(self, value):
        def f(w):
            def g(d):
                if value == "drop":
                    d.pop("channels_configured", None)
                else:
                    d["channels_configured"] = value
            w.edit("alerts.json", g)
        return f

    def test_the_run_block_says_how_many_chat_channels_the_alert_step_had(self):
        for value, want in ((0, 0), (2, 2), ("drop", None), (True, None), ("2", None), (None, None), (-0.5, None)):
            d, _ = doc_of(self.alerts_edit(value))
            self.assertEqual(d["run"]["alert_channels"], want, repr(value))

    def test_the_alert_step_writes_the_number_of_channels_it_had(self):
        with harness.Delivery(1, channels=()) as d:
            out = d.run()
        self.assertEqual(out["channels_configured"], 0)
        with harness.Delivery(1, channels=("discord", "webhook")) as d:
            out = d.run()
        self.assertEqual(out["channels_configured"], 2)


if __name__ == "__main__":
    unittest.main()
