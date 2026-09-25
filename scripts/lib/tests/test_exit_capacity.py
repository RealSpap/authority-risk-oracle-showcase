"""
Unit tests for scripts/lib/exit_capacity.py's pure classification logic -- no live RPC/API.
fetch_rows() (an HTTP call in the CLI script) is exercised by scripts/check_exit_capacity.py against
the real Morpho API, not here.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.exit_capacity import DAY, exit_band, exit_share, is_thin_behind_a_short_delay, timelock_bucket  # noqa: E402


class TestExitShare(unittest.TestCase):
    def test_instant_liquidity_only(self):
        self.assertAlmostEqual(exit_share(100.0, 20.0), 0.2)

    def test_instant_plus_in_kind(self):
        self.assertAlmostEqual(exit_share(100.0, 20.0, 30.0), 0.5)

    def test_capped_at_100_percent(self):
        self.assertEqual(exit_share(100.0, 80.0, 80.0), 1.0)

    def test_zero_tvl_is_none_not_zero(self):
        self.assertIsNone(exit_share(0.0, 10.0))

    def test_negative_tvl_is_none(self):
        self.assertIsNone(exit_share(-5.0, 10.0))

    def test_zero_liquidity_is_zero_not_none(self):
        self.assertEqual(exit_share(100.0, 0.0), 0.0)


class TestExitBand(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(exit_band(0.0), "<5%")
        self.assertEqual(exit_band(0.049), "<5%")
        self.assertEqual(exit_band(0.05), "5-20%")
        self.assertEqual(exit_band(0.199), "5-20%")
        self.assertEqual(exit_band(0.20), "20-50%")
        self.assertEqual(exit_band(0.499), "20-50%")
        self.assertEqual(exit_band(0.50), ">=50%")
        self.assertEqual(exit_band(1.0), ">=50%")

    def test_none_is_unknown(self):
        self.assertEqual(exit_band(None), "unknown")


class TestTimelockBucket(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(timelock_bucket(None), "unknown")
        self.assertEqual(timelock_bucket(0), "0 (no delay)")
        self.assertEqual(timelock_bucket(2 * DAY), "under 3d")
        self.assertEqual(timelock_bucket(3 * DAY), "3d")
        self.assertEqual(timelock_bucket(3 * DAY + 300), "3d")
        self.assertEqual(timelock_bucket(3 * DAY + 301), "3d to 7d")
        self.assertEqual(timelock_bucket(6 * DAY), "3d to 7d")
        self.assertEqual(timelock_bucket(7 * DAY), "7d")
        self.assertEqual(timelock_bucket(8 * DAY), "over 7d")


class TestIsThinBehindAShortDelay(unittest.TestCase):
    def test_short_and_thin_is_true(self):
        self.assertTrue(is_thin_behind_a_short_delay(3 * DAY, 0.10))

    def test_short_but_deep_liquidity_is_false(self):
        self.assertFalse(is_thin_behind_a_short_delay(3 * DAY, 0.50))

    def test_long_and_thin_is_false(self):
        self.assertFalse(is_thin_behind_a_short_delay(7 * DAY, 0.10))

    def test_no_delay_and_thin_is_true(self):
        self.assertTrue(is_thin_behind_a_short_delay(0, 0.0))

    def test_none_seconds_is_false(self):
        self.assertFalse(is_thin_behind_a_short_delay(None, 0.10))

    def test_none_share_is_false(self):
        self.assertFalse(is_thin_behind_a_short_delay(3 * DAY, None))

    def test_boundary_exactly_20_percent_is_false(self):
        self.assertFalse(is_thin_behind_a_short_delay(3 * DAY, 0.20))

    def test_boundary_exactly_3d_plus_5min_is_true(self):
        self.assertTrue(is_thin_behind_a_short_delay(3 * DAY + 300, 0.10))

    def test_boundary_just_over_3d_plus_5min_is_false(self):
        self.assertFalse(is_thin_behind_a_short_delay(3 * DAY + 301, 0.10))


if __name__ == "__main__":
    unittest.main()
