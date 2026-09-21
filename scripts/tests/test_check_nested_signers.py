"""
Unit tests for scripts/check_nested_signers.py's own new logic -- no live RPC. Added 2026-09-22
(backlog item, closes an #184-review-flagged gap): since commit 894b3ac (2026-09-22 RPC-robustness
fix), safe_owners_and_threshold() RAISES RpcUnavailable on a persistent network failure instead of
returning a falsy value -- this script had no try/except at either of its two call sites (the root
Safe, and the nested `get_safe` closure build_tree() calls recursively), so the same network hiccup
that used to just skip/treat-as-unresolved a Safe now crashed the whole sweep by traceback instead.

The pure-logic parts of this script (registered_safes(), GROUPS) are already covered by
scripts/lib/tests/test_nested_signers.py's TestScriptIntegration -- this file covers only the new
try/except behavior in main(), with get_w3()/the network-facing helper both mocked.
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from web3 import Web3 as RealWeb3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_nested_signers  # noqa: E402

cs = RealWeb3.to_checksum_address


class _FakeEth:
    """Only get_code is exercised by the local get_code() closure in check_nested_signers.main()."""
    def __init__(self, code_by_addr):
        self.code_by_addr = code_by_addr

    def get_code(self, addr):
        return self.code_by_addr.get(addr.lower(), b"")


class _FakeW3:
    def __init__(self, code_by_addr):
        self.eth = _FakeEth(code_by_addr)

    @staticmethod
    def to_checksum_address(addr):
        return cs(addr)


class TestRootSafeNetworkFailureDoesNotCrashTheSweep(unittest.TestCase):
    def test_every_root_safe_unreadable_is_bucketed_not_raised(self):
        with patch.object(check_nested_signers, "get_w3", return_value=_FakeW3({})), \
             patch.object(check_nested_signers, "_gated_safe_owners_and_threshold",
                           side_effect=check_nested_signers.RpcUnavailable("simulated persistent RPC failure")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_nested_signers.main()  # must not raise
            out = buf.getvalue()
        total = len(check_nested_signers.registered_safes(check_nested_signers.GROUPS))
        self.assertEqual(out.count("[UNREAD root Safe]"), total)
        self.assertIn(f"unanalyzed signers: {total}", out)
        self.assertEqual(result, 1)  # unanalyzed is non-empty -> exit status 1, same convention as every other UNANALYZED case


class TestRootSafesSecondReadFailingDoesNotCrash(unittest.TestCase):
    """THE regression action's own review found live (rejected as a third, missed site): the
    root Safe is read TWICE -- once by the guard above, again by build_tree() itself (get_code then
    get_safe on the SAME address) -- and nothing checked the second read actually came back "Safe"
    before indexing tree["kids"], a key build_tree() only ever sets on a resolved Safe node. Two
    ordinary network hiccups on that SECOND read still crashed with KeyError: 'kids' even after the
    first fix's two try/except blocks, because both of them return successfully (None, not an
    exception) to build_tree() -- this is a THIRD site, a missing check on build_tree()'s own
    result, not a missing try/except."""

    def _one_registered_safe(self):
        safes = check_nested_signers.registered_safes(check_nested_signers.GROUPS)
        (eco, real_addr), keys = next(iter(sorted(safes.items())))
        return eco, real_addr, keys

    def test_get_code_exhausting_its_retries_on_the_roots_second_read_does_not_crash(self):
        eco, real_addr, keys = self._one_registered_safe()

        class _FailingEth(_FakeEth):
            def get_code(self, addr):
                if addr.lower() == real_addr:
                    raise ConnectionError("simulated transient failure")  # get_code's own closure retries 4x then returns None
                return b""

        class _FailingW3(_FakeW3):
            def __init__(self):
                self.eth = _FailingEth({})

        with patch.object(check_nested_signers, "get_w3", return_value=_FailingW3()), \
             patch.object(check_nested_signers, "_gated_safe_owners_and_threshold", return_value=([], 1)), \
             patch.object(check_nested_signers, "registered_safes", return_value={(eco, real_addr): keys}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_nested_signers.main()  # must not raise (was: KeyError: 'kids')
            out = buf.getvalue()
        self.assertIn("[UNREAD root Safe tree]", out)
        self.assertIn(real_addr, out.lower())
        self.assertEqual(result, 1)

    def test_get_safe_failing_on_the_roots_second_read_does_not_crash(self):
        eco, real_addr, keys = self._one_registered_safe()
        calls = []

        def fake_owners(w3, addr, retries=4, check_modules=True):
            addr = addr.lower()
            calls.append(addr)
            if addr == real_addr and calls.count(real_addr) == 1:
                return [], 1  # first read (the guard before build_tree): succeeds
            if addr == real_addr:
                raise check_nested_signers.RpcUnavailable("simulated persistent RPC failure")  # second read, inside build_tree
            return None

        with patch.object(check_nested_signers, "get_w3", return_value=_FakeW3({real_addr: b"\x60" * 100})), \
             patch.object(check_nested_signers, "_gated_safe_owners_and_threshold", side_effect=fake_owners), \
             patch.object(check_nested_signers, "registered_safes", return_value={(eco, real_addr): keys}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_nested_signers.main()  # must not raise (was: KeyError: 'kids')
            out = buf.getvalue()
        self.assertIn("[UNREAD root Safe tree]", out)
        self.assertEqual(result, 1)


class TestNestedSafeNetworkFailureIsDisclosedNotCrashed(unittest.TestCase):
    def test_a_nested_safe_that_cannot_be_read_is_treated_as_an_unresolved_contract_not_a_crash(self):
        root = cs("0x" + "11" * 20)
        nested = cs("0x" + "22" * 20)
        owner_eoa = cs("0x" + "33" * 20)
        safes = check_nested_signers.registered_safes(check_nested_signers.GROUPS)
        # Reuse ONE real registered (ecosystem, key) pair so this test doesn't have to also fake
        # registered_safes()/GROUPS -- only the network-facing calls are mocked.
        (eco, real_addr), keys = next(iter(sorted(safes.items())))

        def fake_owners(w3, addr, retries=4, check_modules=True):
            addr = addr.lower()
            if addr == real_addr:
                return [nested], 1  # the real registered root Safe: 1-of-1, its only owner is `nested`
            if addr == nested.lower():
                raise check_nested_signers.RpcUnavailable("simulated persistent RPC failure")
            return None

        code_by_addr = {real_addr: b"\x60" * 100, nested.lower(): b"\x60" * 100}  # both look like contracts

        def fake_get_w3(rpc_url):
            return _FakeW3(code_by_addr)

        with patch.object(check_nested_signers, "get_w3", side_effect=fake_get_w3), \
             patch.object(check_nested_signers, "_gated_safe_owners_and_threshold", side_effect=fake_owners), \
             patch.object(check_nested_signers, "registered_safes", return_value={(eco, real_addr): keys}), \
             patch.object(check_nested_signers, "read_modules", return_value=[]), \
             patch.object(check_nested_signers, "read_guard", return_value=None), \
             patch.object(check_nested_signers, "read_singleton", return_value=None), \
             patch.object(check_nested_signers, "classify", return_value={"status": "clean"}), \
             patch.object(check_nested_signers, "classify_singleton", return_value="canonical"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = check_nested_signers.main()  # must not raise
            out = buf.getvalue()
        self.assertIn("[UNREAD nested Safe, treated as unresolved]", out)
        self.assertIn(nested, out)


if __name__ == "__main__":
    unittest.main()
