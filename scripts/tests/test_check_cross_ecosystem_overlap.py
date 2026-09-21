"""
Unit tests for scripts/check_cross_ecosystem_overlap.py's own new logic -- no live RPC. The real
overlap-finding algorithms (find_cross_ecosystem_overlaps, find_subset_committees, ...) are already
covered directly in scripts/lib/tests/test_cross_ecosystem_overlap.py; this file covers only what's
specific to THIS script: gathering group_root_signers()'s `incomplete_out` across every ecosystem
and printing an honest, unmissable summary of which groups' results might not be trustworthy this
run -- ADDED 2026-09-22, alongside group_root_signers()'s own incomplete_out parameter, closing a
residual of the same-day web3_utils RpcUnavailable fix (see scripts/lib/web3_utils.py and
scripts/lib/signer_overlap.py's history) on the one caller that's a human-reviewed standalone sweep
rather than the live score_all() path.

TestIncompleteGroupsSummary below mocks BOTH get_w3() and group_root_signers() -- no network, no
real GROUPS resolution -- and only proves main()'s own aggregation/printing logic. That first
version of this file (action, maker-checker journal) was REJECTED by an independent independent reviewers
review for exactly what full mocking of group_root_signers() hides: this script imports
safe_owners_and_threshold via `from lib.web3_utils import ...` (see check_cross_ecosystem_overlap.py
itself), a DIFFERENT cached module than the bare `web3_utils` that scripts/lib/cross_ecosystem_overlap.py
catches RpcUnavailable through -- so the REAL group_root_signers(), given this script's REAL
safe_owners_and_threshold wrapper, never actually populated incomplete_out for 6 of 7 ecosystems,
while this file's fully-mocked tests stayed green throughout. Root-caused and fixed by canonicalizing
RpcUnavailable in scripts/lib/rpc_unavailable.py (see its docstring and web3_utils.py's import of it) --
but per the review's own words, "a test that calls the real group_root_signers() with the real
safe_owners_and_threshold ... is the only form of test that can catch this": TestRealProductionImportBoundary
below is that test, added alongside the fix, not a substitute for it.
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_cross_ecosystem_overlap  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from lib import cross_ecosystem_overlap as _ceo  # noqa: E402
from lib import web3_utils as _pkg_web3_utils  # noqa: E402


class TestIncompleteGroupsSummary(unittest.TestCase):
    def setUp(self):
        # get_w3 must not touch the network -- every real call site just threads its return value
        # through to the (also mocked) group_root_signers below, never dereferenced.
        patcher = patch.object(check_cross_ecosystem_overlap, "get_w3", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()

    def _run_with_fake_group_root_signers(self, fake):
        with patch.object(check_cross_ecosystem_overlap, "group_root_signers", side_effect=fake):
            buf = io.StringIO()
            with redirect_stdout(buf):
                check_cross_ecosystem_overlap.main()
            return buf.getvalue()

    def test_no_incomplete_groups_prints_the_all_clear_line(self):
        def fake(w3, group, safe_fn, incomplete_out=None):
            return set()  # every Safe "resolved" (trivially, to nothing) -- nothing incomplete
        output = self._run_with_fake_group_root_signers(fake)
        self.assertIn("Groups with an INCOMPLETE signer set this run", output)
        self.assertIn("None -- every group above resolved every Safe it has.", output)

    def test_one_incomplete_group_is_named_with_its_ecosystem_and_safe(self):
        calls = []

        def fake(w3, group, safe_fn, incomplete_out=None):
            calls.append(1)
            if len(calls) == 1 and incomplete_out is not None:
                # main()'s summary PRINTING code only ever does type(exc).__name__/str(exc) on this,
                # never an isinstance check, so a plain exception is fine for exercising THAT part in
                # isolation. What a plain exception here can NOT prove is that the real,
                # unmocked group_root_signers() actually calls incomplete_out.append(...) at all for
                # this script's real safe_owners_and_threshold wrapper -- see
                # TestRealProductionImportBoundary below for that half, the half action skipped.
                incomplete_out.append(("0x" + "9" * 40, RuntimeError("network blip")))
            return set()
        output = self._run_with_fake_group_root_signers(fake)
        self.assertIn("0x" + "9" * 40, output)
        self.assertIn("network blip", output)
        self.assertIn("NOT confirmed, re-run before trusting it", output)
        # And the all-clear line must NOT also appear alongside a real finding.
        self.assertNotIn("None -- every group above resolved every Safe it has.", output)

    def test_multiple_incomplete_groups_across_different_calls_are_all_named(self):
        calls = []

        def fake(w3, group, safe_fn, incomplete_out=None):
            # bug found running this test live: `calls.append(1)` appended the literal 1 every
            # time, so calls[-1] never advanced past 1 -- every simulated group got the SAME fake
            # address instead of a distinct one, and the test couldn't tell "accumulates across
            # calls" from "only ever recorded the first call". Track a real running index instead.
            idx = len(calls) + 1
            calls.append(idx)
            if incomplete_out is not None:
                incomplete_out.append((f"0x{idx:040x}", RuntimeError(f"blip {idx}")))
            return set()
        output = self._run_with_fake_group_root_signers(fake)
        # At least the first two distinct fake Safe addresses (one per group_root_signers() call)
        # must each be named -- proves incomplete_groups accumulates across every _collect() call,
        # not just the first ecosystem or the first group.
        self.assertIn(f"0x{1:040x}", output)
        self.assertIn(f"0x{2:040x}", output)


class _NetworkDownEth:
    """Stands in for Web3().eth: contract() -- the actual boundary safe_owners_and_threshold()'s
    inner _call() crosses (see web3_utils.py) -- raises a real, network-shaped exception every time,
    as a persistent RPC outage would. Not `w3=None`: that also ends up inside _read()'s except
    clause via an unrelated AttributeError, which LOOKS like it proves the same thing but doesn't
    exercise the boundary this test is named for (found by the #184 review: see its own history)."""

    def contract(self, address=None, abi=None):
        raise ConnectionError("simulated persistent RPC failure")


class _NetworkDownW3:
    eth = _NetworkDownEth()


class TestRealProductionImportBoundary(unittest.TestCase):
    """The form of test action's own review said was the only one that could have caught its
    defect: the REAL, unmocked lib.cross_ecosystem_overlap.group_root_signers() (imported the way
    scripts/check_cross_ecosystem_overlap.py itself imports it, via the `lib.` package path -- see
    this file's own top-level import of it above) driven by THIS SCRIPT's real
    safe_owners_and_threshold wrapper (which internally imports web3_utils via `lib.web3_utils`, not
    bare). Nothing about RpcUnavailable itself is mocked or substituted -- only the network call deep
    inside web3_utils.py's own retry loop is faked, exactly the boundary a persistent RPC failure
    would actually cross in production.

    HISTORY: the first version of this test (action) patched `_pkg_web3_utils._retrying`,
    which safe_owners_and_threshold() never calls (it goes through `_read()` instead) -- an inert
    mock. The test still passed, but for the wrong reason: `w3=None` raised an unrelated
    AttributeError inside `_call()`, which `_read()` retried 4 times (2.4s of real `time.sleep`,
    almost the whole runtime of this suite) before raising RpcUnavailable anyway. Found by the
    independent review that approved #184 (action's own reservations). Fixed by faking the
    actual boundary (`w3.eth.contract()`, a real network-shaped exception) and the actual retry
    delay (`time.sleep`, patched to a no-op) instead."""

    def test_a_persistent_network_failure_through_the_real_wrapper_is_recognized_as_incomplete(self):
        group = {"safes": ["0x" + "3" * 40], "known_eoa": []}
        incomplete = []
        with patch.object(_pkg_web3_utils.time, "sleep", return_value=None):
            result = _ceo.group_root_signers(
                _NetworkDownW3(), group, check_cross_ecosystem_overlap.safe_owners_and_threshold, incomplete_out=incomplete)
        self.assertEqual(result, set())
        self.assertEqual(len(incomplete), 1)
        self.assertEqual(incomplete[0][0], "0x" + "3" * 40)
        self.assertIsInstance(incomplete[0][1], _pkg_web3_utils.RpcUnavailable)


if __name__ == "__main__":
    unittest.main()
