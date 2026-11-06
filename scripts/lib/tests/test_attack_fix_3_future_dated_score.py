"""A score dated in the future must not be VERIFIED.

Weakness class: `lastUpdated` is supplied by whoever pushes the score, and the contract does not check it. A score dated after the block it is read
at never turns stale on chain (the staleness check measures from that date). The Watch says it once in the journal and lists the target in
`future_dated` of the score file, but the trust rule did not read that list, so the target could stay VERIFIED for as long as the date held.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trust_support import A, B, NOW, Watch, status, codes  # noqa: E402
from lib import trust_rules as tr  # noqa: E402


def trust_with(fn, now=NOW):
    w = Watch()
    try:
        w.edit("scores/robinhood-chain.json", fn)
        return w.trust(now=now)
    finally:
        w.close()


class TestAScoreDatedInTheFuture(unittest.TestCase):
    def test_a_target_listed_in_future_dated_is_not_verified(self):
        def f(d):   # the variant as found: a date a year ahead, the target in future_dated, the block time read
            d["targets"][0]["lastUpdated"] = NOW + 365 * 86400; d["future_dated"] = [A]; d["block_time"] = NOW - 3600
        doc = trust_with(f)
        self.assertNotEqual(status(doc, A), "VERIFIED")
        self.assertEqual(status(doc, A), "UNVERIFIED")
        self.assertIn("score_future_dated", codes(doc, A))

    def test_a_date_after_the_block_time_is_caught_without_the_list(self):
        def f(d):
            d["targets"][0]["lastUpdated"] = NOW + 3600; d["block_time"] = NOW - 60
        doc = trust_with(f)
        self.assertIn("score_future_dated", codes(doc, A))

    def test_without_a_block_time_the_read_time_is_the_reference(self):
        def f(d):
            d.pop("block_time", None); d["targets"][0]["lastUpdated"] = d["readAt"] + 86400
        self.assertIn("score_future_dated", codes(trust_with(f), A))

    def test_an_address_in_another_case_still_matches(self):
        doc = trust_with(lambda d: d.update(future_dated=[A.upper().replace("0X", "0x")]))
        self.assertIn("score_future_dated", codes(doc, A))

    def test_the_reason_is_in_the_vocabulary_and_waiting_does_not_help(self):
        self.assertEqual(tr.REASONS["score_future_dated"], ("reading", "unverified", "decides"))
        self.assertIn("score_future_dated", tr.PERMANENT)
        from lib import reader_audit
        self.assertEqual(tr.SCORE_FUTURE_TOLERANCE_SECONDS, reader_audit.LASTUPDATED_FUTURE_TOLERANCE)

    # controls
    def test_control_the_base_run_stays_verified(self):
        doc = trust_with(lambda d: None)
        self.assertEqual(status(doc, A), "VERIFIED", codes(doc, A))
        self.assertNotIn("score_future_dated", codes(doc, B))

    def test_control_a_date_within_the_tolerance_stays_verified(self):
        def f(d):
            d["block_time"] = NOW - 3600; d["targets"][0]["lastUpdated"] = NOW - 3600 + 200; d["future_dated"] = []
        doc = trust_with(f)
        self.assertEqual(status(doc, A), "VERIFIED", codes(doc, A))

    def test_control_only_the_listed_target_is_touched(self):
        doc = trust_with(lambda d: d.update(future_dated=[A]))
        self.assertEqual(status(doc, B), "VERIFIED", codes(doc, B))


if __name__ == "__main__":
    unittest.main()
