"""
Regression test for a real bug found 2026-09-19 in
`chains/zcash/scripts/near_read.py::rpc()` while auditing this ecosystem's
test coverage: on retry exhaustion it used to `raise SystemExit(...)` --
a `BaseException` subclass that escapes a plain `except Exception`, unlike
every other RPC helper in this project (all of which raise `RuntimeError`
or a subclass on failure). `chains/zcash/scorers.py::score_all()` wraps
`score_ext_zec_omft()` (the only caller of this module) in exactly that
kind of `except Exception as e:` -- so a single bad/slow NEAR RPC call
would have crashed the entire Zcash `score_all()` run instead of
gracefully skipping just this one target, the same "SKIPPED <target> --
RuntimeError: RPC down" degradation every other target in this project
gets. Fixed to raise `RuntimeError`; this test locks that in.
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


nr = _load_module("aro_test_zcash_near_read", "chains/zcash/scripts/near_read.py")


class _FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


class TestRpcRetryExhaustion(unittest.TestCase):
    # rpc() does `import time` INSIDE its own body (not at module level),
    # so the name to patch is the real, global `time` module -- the local
    # import just looks it up in sys.modules at call time either way.
    def test_raises_runtime_error_not_system_exit(self):
        with mock.patch.object(nr.subprocess, "run", return_value=_FakeCompletedProcess("not json")), \
             mock.patch("time.sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                nr.rpc("https://rpc.example", "query", {}, tries=2)

    def test_is_caught_by_a_plain_except_exception(self):
        # The actual regression: score_all()'s own `except Exception as e:`
        # wrapper (chains/zcash/scorers.py) must be able to catch this.
        with mock.patch.object(nr.subprocess, "run", return_value=_FakeCompletedProcess("not json")), \
             mock.patch("time.sleep", return_value=None):
            try:
                nr.rpc("https://rpc.example", "query", {}, tries=2)
                self.fail("expected rpc() to raise")
            except Exception:
                pass  # caught -- this is the assertion; SystemExit would skip this clause entirely

    def test_error_field_in_response_also_retries_then_raises_runtime_error(self):
        response = _FakeCompletedProcess(json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}}))
        with mock.patch.object(nr.subprocess, "run", return_value=response), \
             mock.patch("time.sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                nr.rpc("https://rpc.example", "query", {}, tries=2)

    def test_succeeds_on_a_later_try_after_earlier_failures(self):
        bad = _FakeCompletedProcess("not json")
        good = _FakeCompletedProcess(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}))
        with mock.patch.object(nr.subprocess, "run", side_effect=[bad, good]), \
             mock.patch("time.sleep", return_value=None):
            result = nr.rpc("https://rpc.example", "query", {}, tries=2)
            self.assertEqual(result, {"ok": True})


class TestCallView(unittest.TestCase):
    def test_json_result_is_parsed(self):
        raw_json = json.dumps({"total_supply": "123"}).encode()
        with mock.patch.object(nr, "rpc", return_value={"result": list(raw_json)}):
            result = nr.call_view("https://rpc.example", "zec.omft.near", "ft_total_supply")
            self.assertEqual(result, {"total_supply": "123"})

    def test_non_json_result_falls_back_to_decoded_string(self):
        # A bare digit string like "12345" is itself valid JSON (decodes to
        # an int) -- use genuinely non-JSON bytes to exercise the fallback.
        raw = b"not-valid-json{"
        with mock.patch.object(nr, "rpc", return_value={"result": list(raw)}):
            result = nr.call_view("https://rpc.example", "zec.omft.near", "ft_total_supply")
            self.assertEqual(result, "not-valid-json{")


if __name__ == "__main__":
    unittest.main()
