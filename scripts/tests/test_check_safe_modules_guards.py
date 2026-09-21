"""
Unit tests for scripts/check_safe_modules_guards.py's own new logic -- no live RPC. Added 2026-09-22
(backlog item, closes an #184-review-flagged gap): since commit 894b3ac (2026-09-22 RPC-robustness
fix), safe_owners_and_threshold() RAISES RpcUnavailable on a persistent network failure instead of
returning a falsy value -- this script had no try/except around its own call site at all, so the
same network hiccup that used to just bucket a Safe as "not a Safe / unreadable" now crashed the
whole sweep by traceback instead. get_w3() and safe_owners_and_threshold() are both mocked -- no
network, no real GROUPS resolution beyond the real (but pure, no-RPC) registered_safes() call.

REVISED 2026-09-22 after action was REJECTED (a network failure was bucketed into `not_safe`,
which never drove exit status 1 -- contradicting this script's own docstring, "Exit status 1 if any
Safe ... could not be read"): network failures now land in their own `unread_root_safes` bucket that
DOES drive exit 1, kept apart from `not_safe` (a confirmed bespoke multisig, not an error).
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_safe_modules_guards  # noqa: E402


class TestNetworkFailureDoesNotCrashTheSweep(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(check_safe_modules_guards, "get_w3", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_every_safe_unreadable_is_bucketed_not_raised_and_drives_exit_status_1(self):
        with patch.object(check_safe_modules_guards, "safe_owners_and_threshold",
                           side_effect=check_safe_modules_guards.RpcUnavailable("simulated persistent RPC failure")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_safe_modules_guards.main()  # must not raise
            out = buf.getvalue()
        total = len(check_safe_modules_guards.registered_safes(check_safe_modules_guards.GROUPS))
        self.assertIn(f"{total} unreadable (network)", out)
        self.assertEqual(out.count("[UNREAD Safe, network]"), total)
        self.assertEqual(result, 1)  # matches the docstring: "Exit status 1 if any Safe ... could not be read"

    def test_a_mix_of_resolved_and_unreadable_safes_both_bucket_correctly(self):
        safes = check_safe_modules_guards.registered_safes(check_safe_modules_guards.GROUPS)
        first_addr = next(iter(safes))[1]

        def fake(w3, addr, retries=4):
            if addr.lower() == first_addr:
                raise check_safe_modules_guards.RpcUnavailable("simulated persistent RPC failure")
            return None  # every other Safe: a confirmed non-Safe/bespoke multisig, no crash either way

        with patch.object(check_safe_modules_guards, "safe_owners_and_threshold", side_effect=fake):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_safe_modules_guards.main()  # must not raise
            out = buf.getvalue()
        total = len(safes)
        self.assertIn(f"{total - 1} not a Safe (bespoke multisig), 1 unreadable (network)", out)
        self.assertEqual(out.count("[UNREAD Safe, network]"), 1)
        self.assertEqual(result, 1)  # the one network failure alone is enough to drive exit status 1

    def test_a_confirmed_bespoke_multisig_alone_does_not_drive_exit_status_1(self):
        # CHARACTERISATION: a genuinely-resolved "not a Safe" is not an error and must not itself
        # trigger exit 1 -- only network-unreadable Safes (unread_root_safes) should.
        with patch.object(check_safe_modules_guards, "safe_owners_and_threshold", return_value=None):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_safe_modules_guards.main()  # must not raise
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
