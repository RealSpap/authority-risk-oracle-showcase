"""Unit tests for scripts/lib/incident_exposure.py and the reading side of scripts/incident_exposure.py -- no network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.incident_exposure import INCIDENTS, LOWEST_BAND, at_or_below, replay, summarize  # noqa: E402
import importlib.util  # noqa: E402

# scripts/incident_exposure.py and scripts/lib/incident_exposure.py share a module name: load the tool by path under its own name.
_spec = importlib.util.spec_from_file_location("aro_incident_exposure_tool", os.path.join(os.path.dirname(__file__), "..", "..", "incident_exposure.py"))
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


class Replay(unittest.TestCase):
    def test_values_worked_by_hand_from_the_safe_rooted_convention(self):
        # threshold >= 3: admin 65; multisig = 15*t + 5*(n-t); timelock 0; composite = (4a + 3m + 5) // 10
        self.assertEqual(replay(3, 6), {"adminKeyScore": 65, "multisigScore": 60, "timelockScore": 0, "compositeScore": 44})
        self.assertEqual(replay(4, 6)["compositeScore"], 47)
        self.assertEqual(replay(3, 11), {"adminKeyScore": 65, "multisigScore": 85, "timelockScore": 0, "compositeScore": 52})
        self.assertEqual(replay(3, 5)["compositeScore"], 43)
        self.assertEqual(replay(2, 5)["adminKeyScore"], 50)  # a 2-of-N Safe is one rung lower

    def test_each_incident_label_names_the_threshold_and_owners_it_replays(self):
        for label, t, n in INCIDENTS:
            self.assertIn(f"{t}-of-{n}", label)
            self.assertTrue(LOWEST_BAND < replay(t, n)["compositeScore"] < 100, label)


class Exposure(unittest.TestCase):
    ROWS = [{"compositeScore": c, "timelockScore": tl} for c, tl in ((2, 0), (10, 0), (44, 0), (44, 0), (52, 15), (90, 60))]

    def test_at_or_below_is_inclusive(self):
        self.assertEqual(at_or_below(self.ROWS, 44), 4)
        self.assertEqual(at_or_below(self.ROWS, 1), 0)

    def test_summarize(self):
        s = summarize(self.ROWS)
        self.assertEqual((s["targets"], s["no_delay"], s["lowest_band"], s["median_composite"]), (6, 4, 2, 44))
        self.assertEqual(summarize([])["targets"], 0)


SCORE = {"adminKeyScore": 65, "multisigScore": 60, "timelockScore": 0, "oracleAuthorityScore": 100, "crossExposureScore": 100, "compositeScore": 44}


class ReadPublished(unittest.TestCase):
    ORACLES = [("A", "0xa", "rpc-a"), ("B", "0xb", "rpc-b")]

    def read(self, oracles, published, solana=None):
        return tool.read_published(oracles=oracles, read=lambda addr, rpc: published[addr], solana_read=solana or (lambda: {"scores": []}))

    def test_rows_carry_ecosystem_and_target(self):
        rows, unread = self.read(self.ORACLES, {"0xa": {"0xt1": SCORE}, "0xb": {"0xt2": SCORE, "0xt3": SCORE}})
        self.assertEqual((len(rows), unread), (3, []))
        self.assertEqual({(r["ecosystem"], r["target"]) for r in rows}, {("A", "0xt1"), ("B", "0xt2"), ("B", "0xt3")})

    def test_an_oracle_that_does_not_answer_is_unread_not_empty(self):
        rows, unread = self.read(self.ORACLES, {"0xa": {"0xt1": SCORE}, "0xb": None})
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(unread), 1)
        self.assertIn("B", unread[0])

    def test_one_unread_target_is_reported_and_dropped_from_the_rows(self):
        rows, unread = self.read(self.ORACLES[:1], {"0xa": {"0xt1": SCORE, "0xt2": None}})
        self.assertEqual(len(rows), 1)
        self.assertIn("1 target(s) unread", unread[0])

    def test_a_raising_reader_and_a_raising_solana_read_are_both_reported(self):
        def boom(addr, rpc):
            raise RuntimeError("rpc down")

        def sboom():
            raise ValueError("no registry")

        rows, unread = tool.read_published(oracles=self.ORACLES[:1], read=boom, solana_read=sboom)
        self.assertEqual(rows, [])
        self.assertEqual(len(unread), 2)


if __name__ == "__main__":
    unittest.main()
