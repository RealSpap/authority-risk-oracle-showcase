"""Unit tests for scripts/lib/incident_exposure.py -- pure logic, no network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.incident_exposure import BARE_KEY_BAND, INCIDENTS, at_or_below, replay, summarize  # noqa: E402


class Replay(unittest.TestCase):
    def test_values_worked_by_hand_from_the_safe_rooted_convention(self):
        # threshold >= 3: admin 65; multisig = 15*t + 5*(n-t); timelock 0; composite = (4a + 3m + 5) // 10
        self.assertEqual(replay(3, 6), {"adminKeyScore": 65, "multisigScore": 60, "timelockScore": 0, "compositeScore": 44})
        self.assertEqual(replay(4, 6)["compositeScore"], 47)
        self.assertEqual(replay(3, 11), {"adminKeyScore": 65, "multisigScore": 85, "timelockScore": 0, "compositeScore": 52})
        self.assertEqual(replay(3, 5)["compositeScore"], 43)
        self.assertEqual(replay(2, 5)["adminKeyScore"], 50)  # a 2-of-N Safe is one rung lower

    def test_every_incident_replays_and_has_no_timelock(self):
        for label, t, n in INCIDENTS:
            r = replay(t, n)
            self.assertEqual(r["timelockScore"], 0, label)
            self.assertTrue(BARE_KEY_BAND < r["compositeScore"] < 100, label)


class Exposure(unittest.TestCase):
    ROWS = [{"compositeScore": c, "timelockScore": tl} for c, tl in ((2, 0), (10, 0), (44, 0), (44, 0), (52, 15), (90, 60))]

    def test_at_or_below_is_inclusive(self):
        self.assertEqual(at_or_below(self.ROWS, 44), 4)
        self.assertEqual(at_or_below(self.ROWS, 1), 0)

    def test_summarize(self):
        s = summarize(self.ROWS)
        self.assertEqual((s["targets"], s["no_delay"], s["bare_key_band"], s["median_composite"]), (6, 4, 2, 44))
        self.assertEqual(summarize([])["targets"], 0)


if __name__ == "__main__":
    unittest.main()
