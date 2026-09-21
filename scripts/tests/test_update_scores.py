"""
Unit tests for scripts/update_scores.py's failure-alerting wrapper -- no live
RPC, no real Telegram call. Covers the 2026-09-17 fix: every failure alert
used to depend on the run reaching diff_alerts() at the very end, so a crash
anywhere earlier (several of which raise SystemExit directly, this script's
own error-signaling convention) sent nothing.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import update_scores  # noqa: E402


def _scored(target, label="Target", composite=70):
    return {"target": target, "label": label, "compositeScore": composite}


def _snapshot(*entries):
    return {"scores": list(entries)}


class TestCheckCompleteness(unittest.TestCase):
    """ADDED 2026-09-22, closes the tracked "web3_utils helpers rendent None pour un revert comme
    [backlog note]" risk (see scripts/lib/web3_utils.RpcUnavailable): score_all() now
    SKIPS a target instead of scoring it from an ambiguous None when a persistent RPC failure hits
    it -- correct for that one target, but nothing used to check score_all() still returned
    everything it should have before publishing a shortened list as if it were complete."""

    def test_no_previous_snapshot_is_a_first_publish_never_refuses(self):
        update_scores.check_completeness([_scored("0xAAA")], None)  # must not raise

    def test_nothing_missing_does_not_refuse(self):
        scored = [_scored("0xAAA"), _scored("0xBBB")]
        previous = _snapshot(_scored("0xAAA"), _scored("0xBBB"))
        update_scores.check_completeness(scored, previous)  # must not raise

    def test_a_missing_target_refuses_with_systemexit(self):
        scored = [_scored("0xAAA")]
        previous = _snapshot(_scored("0xAAA"), _scored("0xBBB", label="The One That Vanished"))
        with self.assertRaises(SystemExit) as ctx:
            update_scores.check_completeness(scored, previous)
        self.assertIn("0xbbb", str(ctx.exception).lower())

    def test_target_matching_is_case_insensitive(self):
        scored = [_scored("0xABCD")]
        previous = _snapshot(_scored("0xAbCd"))
        update_scores.check_completeness(scored, previous)  # same target, different case -- must not refuse

    def test_a_brand_new_target_with_no_prior_history_is_not_missing(self):
        # Adding a target is fine; only LOSING one that was there before refuses.
        scored = [_scored("0xAAA"), _scored("0xBBB")]
        previous = _snapshot(_scored("0xAAA"))
        update_scores.check_completeness(scored, previous)  # must not raise

    def test_multiple_missing_targets_are_all_named(self):
        scored = []
        previous = _snapshot(_scored("0xAAA"), _scored("0xBBB"))
        with self.assertRaises(SystemExit) as ctx:
            update_scores.check_completeness(scored, previous)
        message = str(ctx.exception).lower()
        self.assertIn("0xaaa", message)
        self.assertIn("0xbbb", message)
        self.assertIn("2 target", message)


class TestMainFailureAlerting(unittest.TestCase):
    def test_a_regular_exception_triggers_an_alert_and_reraises(self):
        with patch.object(update_scores, "_run", side_effect=ConnectionError("RPC unreachable")), \
             patch.object(update_scores, "send_telegram_alert", return_value=True) as mock_alert:
            with self.assertRaises(ConnectionError):
                update_scores.main()
            self.assertEqual(mock_alert.call_count, 1)
            sent_message = mock_alert.call_args[0][0]
            self.assertIn("FAILED", sent_message)
            self.assertIn("ConnectionError", sent_message)
            self.assertIn("RPC unreachable", sent_message)

    def test_a_system_exit_failure_path_also_triggers_an_alert(self):
        # SystemExit does NOT inherit from Exception -- this is exactly the
        # case a plain `except Exception` would have missed. Several real
        # failure paths in _run() raise SystemExit directly (unreachable
        # RPC, a reverted on-chain tx).
        with patch.object(update_scores, "_run", side_effect=SystemExit("Could not connect to read RPC: bad-url")), \
             patch.object(update_scores, "send_telegram_alert", return_value=True) as mock_alert:
            with self.assertRaises(SystemExit):
                update_scores.main()
            self.assertEqual(mock_alert.call_count, 1)
            self.assertIn("Could not connect to read RPC", mock_alert.call_args[0][0])

    def test_keyboard_interrupt_is_not_treated_as_a_failure_alert(self):
        # An operator hitting Ctrl+C should stop the script immediately,
        # not trigger a Telegram alert.
        with patch.object(update_scores, "_run", side_effect=KeyboardInterrupt), \
             patch.object(update_scores, "send_telegram_alert", return_value=True) as mock_alert:
            with self.assertRaises(KeyboardInterrupt):
                update_scores.main()
            mock_alert.assert_not_called()

    def test_dry_run_failure_does_not_alert(self):
        # Matches --dry-run's existing "not alerting" contract elsewhere in
        # this script (no tx sent, no api/scores.json written, no alert).
        with patch.object(sys, "argv", ["update_scores.py", "--dry-run"]), \
             patch.object(update_scores, "_run", side_effect=ConnectionError("boom")), \
             patch.object(update_scores, "send_telegram_alert", return_value=True) as mock_alert:
            with self.assertRaises(ConnectionError):
                update_scores.main()
            mock_alert.assert_not_called()

    def test_success_does_not_alert_on_failure_path(self):
        with patch.object(update_scores, "_run", return_value=None), \
             patch.object(update_scores, "send_telegram_alert", return_value=True) as mock_alert:
            update_scores.main()  # must not raise
            mock_alert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
