"""Behaviour test added on 30/10/2026: the reader publishes the gap between the Watch's reading of the oracle and its own reading in SECONDS (`read_gap_seconds`), never in blocks, because the oracle and the contract it scores run on different networks. It runs second_opinion.main() against the in-process fake node of test_reader_extras. No network."""
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_reader_extras as tre  # noqa: E402  -- the module, not its classes: the classes of that file must not be collected twice


class TestTheReadGapIsPublishedInSeconds(tre.TestSecondOpinionAgainstAFakeNode):
    NOW = 1790000500   # 500 s after the Watch read the oracle (readAt 1790000000 in the fake scores file)

    def run_at(self, now, read_at="keep"):
        if read_at != "keep":
            p = os.path.join(self.d, "scores", "ethereum-l1-sepolia.json"); doc = json.load(open(p))
            if read_at is None: doc.pop("readAt")
            else: doc["readAt"] = read_at
            json.dump(doc, open(p, "w"))
        with mock.patch.object(self.so.time, "time", return_value=now):
            return self.run_reader()

    def test_the_gap_is_the_difference_of_the_two_reading_times_in_seconds(self):
        r = self.rec(self.run_at(self.NOW), tre.T_OWN)
        self.assertEqual(r["scores_read_at"], 1790000000); self.assertEqual(r["read_gap_seconds"], 500); self.assertEqual(r["since_score_push_seconds"], self.NOW - 1789999000)
        self.assertNotIn("read_gap_blocks", r)

    def test_a_scores_file_without_a_reading_time_gives_none_never_zero(self):
        r = self.rec(self.run_at(self.NOW, read_at=None), tre.T_OWN)
        self.assertIsNone(r["scores_read_at"]); self.assertIsNone(r["read_gap_seconds"])

    def test_a_reading_time_in_the_future_gives_a_gap_of_zero_not_a_negative(self):
        r = self.rec(self.run_at(1789999000), tre.T_OWN); self.assertEqual(r["read_gap_seconds"], 0)


# the inherited tests belong to test_reader_extras and are not run again here
for _n in [n for n in dir(TestTheReadGapIsPublishedInSeconds) if n.startswith("test_") and n not in vars(TestTheReadGapIsPublishedInSeconds)]:
    setattr(TestTheReadGapIsPublishedInSeconds, _n, None)


if __name__ == "__main__":
    unittest.main()
