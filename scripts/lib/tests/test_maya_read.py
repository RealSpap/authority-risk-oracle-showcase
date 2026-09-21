"""
Regression test for a real bug found 2026-09-19 in
`chains/zcash/scripts/maya_read.py::get()` -- a deliberate follow-up sweep
(grepping the whole repo for "raise SystemExit" outside CLI entry points)
after fixing the identical bug in the sibling `near_read.py::rpc()`. On
retry exhaustion this used to `raise SystemExit(...)` -- a `BaseException`
subclass that escapes a plain `except Exception`.
`chains/zcash/scorers.py::score_all()` wraps `mr.active_zec_vaults()`
(which calls `vaults_asgard()`, which calls this function) in exactly that
kind of `except Exception as e:` handler -- a single bad/slow Mayanode
REST call would have crashed the entire Zcash `score_all()` run instead of
gracefully skipping just the Maya Asgard vault section. Fixed to raise
`RuntimeError`; this test locks that in.
"""
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    ecosystem_dir = os.path.dirname(file_path)
    if ecosystem_dir not in sys.path:
        sys.path.insert(0, ecosystem_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


mr = _load_module("aro_test_zcash_maya_read", "chains/zcash/scripts/maya_read.py")


class _FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


class TestGetRetryExhaustion(unittest.TestCase):
    def test_raises_runtime_error_not_system_exit(self):
        with mock.patch.object(mr.subprocess, "run", return_value=_FakeCompletedProcess("not json")), \
             mock.patch.object(mr.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                mr.get("/mayachain/vaults/asgard", tries=2)

    def test_is_caught_by_a_plain_except_exception(self):
        # The actual regression: score_all()'s own `except Exception as e:`
        # wrapper (chains/zcash/scorers.py, around active_zec_vaults())
        # must be able to catch this.
        with mock.patch.object(mr.subprocess, "run", return_value=_FakeCompletedProcess("not json")), \
             mock.patch.object(mr.time, "sleep", return_value=None):
            try:
                mr.get("/mayachain/vaults/asgard", tries=2)
                self.fail("expected get() to raise")
            except Exception:
                pass  # caught -- SystemExit would skip this clause entirely

    def test_succeeds_on_a_later_try_after_earlier_failures(self):
        bad = _FakeCompletedProcess("not json")
        good = _FakeCompletedProcess(json.dumps([{"status": "ActiveVault"}]))
        with mock.patch.object(mr.subprocess, "run", side_effect=[bad, good]), \
             mock.patch.object(mr.time, "sleep", return_value=None):
            result = mr.get("/mayachain/vaults/asgard", tries=2)
            self.assertEqual(result, [{"status": "ActiveVault"}])


class TestActiveZecVaults(unittest.TestCase):
    """Sanity coverage for active_zec_vaults()'s own filtering logic
    (status == "ActiveVault", ZEC.ZEC coin present with amount > 0) --
    previously untested at any layer alongside the SystemExit bug above."""

    def _wire_vaults_asgard(self, vaults):
        orig = mr.vaults_asgard
        mr.vaults_asgard = lambda: vaults
        self.addCleanup(lambda: setattr(mr, "vaults_asgard", orig))

    def test_filters_out_non_active_vaults(self):
        self._wire_vaults_asgard([
            {"status": "RetiringVault", "pub_key": "a", "coins": [{"asset": "ZEC.ZEC", "amount": "100"}],
             "addresses": [{"chain": "ZEC", "address": "t1A"}], "membership": ["k1"]},
        ])
        self.assertEqual(mr.active_zec_vaults(), [])

    def test_filters_out_zero_or_missing_zec_balance(self):
        self._wire_vaults_asgard([
            {"status": "ActiveVault", "pub_key": "a", "coins": [{"asset": "ZEC.ZEC", "amount": "0"}],
             "addresses": [{"chain": "ZEC", "address": "t1A"}], "membership": ["k1"]},
            {"status": "ActiveVault", "pub_key": "b", "coins": [{"asset": "BTC.BTC", "amount": "500"}],
             "addresses": [{"chain": "ZEC", "address": "t1B"}], "membership": ["k1"]},
        ])
        self.assertEqual(mr.active_zec_vaults(), [])

    def test_active_vault_with_real_zec_balance_is_included(self):
        self._wire_vaults_asgard([
            {"status": "ActiveVault", "pub_key": "mayapub1abc", "coins": [{"asset": "ZEC.ZEC", "amount": "123456789"}],
             "addresses": [{"chain": "ZEC", "address": "t1RealAddr"}], "membership": ["k1", "k2", "k3"]},
        ])
        result = mr.active_zec_vaults()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], {
            "pub_key": "mayapub1abc", "ledger_amount_zat": 123456789,
            "zec_address": "t1RealAddr", "membership": ["k1", "k2", "k3"],
        })


if __name__ == "__main__":
    unittest.main()
