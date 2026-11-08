"""Regression guard for chains/tempo/scripts/methodology_test.py's rpc(): it waits and retries when the RPC answers "rate limited"
(JSON-RPC code -32005) instead of giving up after 4 immediate attempts.

Why (observed 2026-10-18): the log scan sends ~440 eth_getLogs windows over 12 threads; rpc.tempo.xyz answers "rate limited, try again in
15ms", the 4 attempts land in the same millisecond, score_all() is SKIPPED and Tempo cannot be re-pushed (6 runs out of 6).

Run:  python3 -m unittest discover -s chains/tempo/tests -v
"""
import importlib.util
import json
import os
import subprocess
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load():
    spec = importlib.util.spec_from_file_location("mt_rate", os.path.join(REPO_ROOT, "chains", "tempo", "scripts", "methodology_test.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _reply(obj):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(obj), stderr="")


LIMITED = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32005, "message": "rate limited, try again in 15ms"}}


class TestRateLimit(unittest.TestCase):
    def test_a_rate_limited_answer_is_waited_out_and_retried(self):
        mt = _load()
        ok = _reply({"jsonrpc": "2.0", "id": 1, "result": "0x1"})
        with mock.patch("subprocess.run", side_effect=[_reply(LIMITED)] * 6 + [ok]), mock.patch("time.sleep") as slept:
            self.assertEqual(mt.rpc("http://x", "eth_blockNumber", []), "0x1")
        self.assertEqual(slept.call_count, 6)

    def test_a_revert_still_returns_none_at_once(self):
        mt = _load()
        rev = _reply({"jsonrpc": "2.0", "id": 1, "error": {"code": 3, "message": "execution reverted"}})
        with mock.patch("subprocess.run", side_effect=[rev]), mock.patch("time.sleep") as slept:
            self.assertIsNone(mt.rpc("http://x", "eth_call", []))
        slept.assert_not_called()

    def test_a_permanent_limit_still_raises_instead_of_returning_a_wrong_value(self):
        mt = _load()
        with mock.patch("subprocess.run", return_value=_reply(LIMITED)), mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                mt.rpc("http://x", "eth_getLogs", [])


if __name__ == "__main__":
    unittest.main()
