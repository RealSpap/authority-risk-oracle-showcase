"""
Unit tests for scripts/lib/alerts.py -- pure logic, no live RPC needed.

Run: python3 -m unittest discover -s scripts/lib/tests -v
(from the repo root; see scripts/lib/tests/README.md for why these exist)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.alerts import DROP_THRESHOLD, NEW_TARGET_ALERT_CEILING, _band, diff_alerts, format_summary, send_telegram_alert  # noqa: E402


class TestBand(unittest.TestCase):
    def test_boundaries(self):
        # _band's own thresholds: <20 CRITICAL, <40 WEAK, <60 MODERATE, <80 DECENT, else STRONG
        cases = [
            (0, "CRITICAL"), (19, "CRITICAL"),
            (20, "WEAK"), (39, "WEAK"),
            (40, "MODERATE"), (59, "MODERATE"),
            (60, "DECENT"), (79, "DECENT"),
            (80, "STRONG"), (100, "STRONG"),
        ]
        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(_band(score), expected)


def _entry(target, label, composite):
    return {"target": target, "label": label, "compositeScore": composite}


class TestDiffAlerts(unittest.TestCase):
    def test_first_publish_low_score_alerts(self):
        current = [_entry("0xAAA", "New Target", NEW_TARGET_ALERT_CEILING)]
        alerts = diff_alerts(None, current)
        self.assertEqual(len(alerts), 1)
        self.assertIn("NEW", alerts[0])
        self.assertIn("New Target", alerts[0])

    def test_first_publish_high_score_no_alert(self):
        current = [_entry("0xAAA", "New Target", NEW_TARGET_ALERT_CEILING + 1)]
        self.assertEqual(diff_alerts(None, current), [])

    def test_drop_at_threshold_alerts(self):
        previous = {"scores": [_entry("0xAAA", "Target", 70)]}
        current = [_entry("0xAAA", "Target", 70 - DROP_THRESHOLD)]
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 1)
        self.assertIn("DROP", alerts[0])

    def test_drop_just_under_threshold_same_band_no_alert(self):
        # 55 -> 46: both MODERATE (40-59), drop of 9 < DROP_THRESHOLD (10)
        previous = {"scores": [_entry("0xAAA", "Target", 55)]}
        current = [_entry("0xAAA", "Target", 46)]
        self.assertEqual(diff_alerts(previous, current), [])

    def test_small_drop_crossing_band_still_alerts(self):
        # 60 (DECENT) -> 59 (MODERATE): drop of only 1, but the band changed
        previous = {"scores": [_entry("0xAAA", "Target", 60)]}
        current = [_entry("0xAAA", "Target", 59)]
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 1)
        self.assertIn("DECENT", alerts[0])
        self.assertIn("MODERATE", alerts[0])

    def test_improvement_never_alerts(self):
        # Even a band-crossing improvement (59 -> 60) must never alert --
        # this is a risk feed, not a changelog, per alerts.py's own module docstring.
        previous = {"scores": [_entry("0xAAA", "Target", 59)]}
        current = [_entry("0xAAA", "Target", 60)]
        self.assertEqual(diff_alerts(previous, current), [])

    def test_unchanged_score_no_alert(self):
        previous = {"scores": [_entry("0xAAA", "Target", 50)]}
        current = [_entry("0xAAA", "Target", 50)]
        self.assertEqual(diff_alerts(previous, current), [])

    def test_target_matching_is_case_insensitive(self):
        previous = {"scores": [_entry("0xAbCd", "Target", 70)]}
        current = [_entry("0xABCD", "Target", 70 - DROP_THRESHOLD)]
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 1)

    def test_alerts_are_sorted_alphabetically_by_prefix(self):
        # Plain alphabetical sort on the "[NEW..."/"[DROP..." prefix -- "D" < "N",
        # so DROP alerts sort first. (Caught scripts/lib/alerts.py's own inline
        # comment claiming the opposite; fixed there, not here -- this test
        # documents the real, verified behavior.)
        previous = {"scores": [_entry("0xAAA", "Existing", 70)]}
        current = [
            _entry("0xAAA", "Existing", 70 - DROP_THRESHOLD),  # DROP
            _entry("0xBBB", "Brand New", 10),  # NEW
        ]
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 2)
        self.assertTrue(alerts[0].startswith("[DROP"))
        self.assertTrue(alerts[1].startswith("[NEW"))

    def test_empty_current_scores_no_alerts(self):
        previous = {"scores": [_entry("0xAAA", "Target", 70)]}
        self.assertEqual(diff_alerts(previous, []), [])

    def test_a_target_present_last_run_and_absent_this_run_gets_a_missing_alert(self):
        # ADDED 2026-09-22, closes the tracked risk: score_all() now SKIPS a target instead of
        # scoring it from an ambiguous None when a persistent RPC failure hits it (see
        # web3_utils.RpcUnavailable) -- this used to produce NO alert at all, an invisible omission
        # from api/scores.json rather than a wrong number.
        previous = {"scores": [_entry("0xAAA", "Vanished Target", 70), _entry("0xBBB", "Still Here", 50)]}
        current = [_entry("0xBBB", "Still Here", 50)]
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0].startswith("[MISSING"))
        self.assertIn("Vanished Target", alerts[0])
        self.assertIn("0xAAA", alerts[0])
        self.assertIn("70/100", alerts[0])

    def test_missing_target_matching_is_case_insensitive(self):
        previous = {"scores": [_entry("0xAbCd", "Target", 70), _entry("0xBBB", "Other", 50)]}
        current = [_entry("0xABCD", "Target", 70)]  # same target, different case -- must NOT alert as missing
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0].startswith("[MISSING"))
        self.assertIn("0xBBB", alerts[0])

    def test_a_missing_target_and_a_drop_both_alert_and_drop_sorts_first(self):
        previous = {"scores": [_entry("0xAAA", "Dropping", 70), _entry("0xBBB", "Vanished", 50)]}
        current = [_entry("0xAAA", "Dropping", 70 - DROP_THRESHOLD)]
        alerts = diff_alerts(previous, current)
        self.assertEqual(len(alerts), 2)
        self.assertTrue(alerts[0].startswith("[DROP"))
        self.assertTrue(alerts[1].startswith("[MISSING"))

    def test_nothing_missing_when_every_previous_target_is_still_present(self):
        previous = {"scores": [_entry("0xAAA", "Target", 70)]}
        current = [_entry("0xAAA", "Target", 70)]
        self.assertEqual(diff_alerts(previous, current), [])

    def test_first_publish_has_nothing_to_be_missing_from(self):
        current = [_entry("0xAAA", "Brand New", 90)]
        self.assertEqual(diff_alerts(None, current), [])


class TestFormatSummary(unittest.TestCase):
    def test_includes_count_and_dashboard_url(self):
        summary = format_summary(["[DROP] one thing"], "https://example.test/dashboard")
        self.assertIn("1 target(s)", summary)
        self.assertIn("[DROP] one thing", summary)
        self.assertIn("https://example.test/dashboard", summary)

    def test_zero_alerts(self):
        summary = format_summary([], "https://example.test/dashboard")
        self.assertIn("0 target(s)", summary)


class TestSendTelegramAlert(unittest.TestCase):
    def test_returns_false_without_crashing_when_unconfigured(self):
        # alerts.py's own contract: never raise, never depend on alerting
        # being configured for the scoring pipeline to keep working.
        env_backup = {k: os.environ.pop(k, None) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        try:
            self.assertFalse(send_telegram_alert("test message"))
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
