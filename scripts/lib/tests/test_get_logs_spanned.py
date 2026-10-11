"""get_logs_spanned: windows of at most `span` blocks, in order, and a failing window raises instead of returning a partial history."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.web3_utils import get_logs_spanned  # noqa: E402


class FakeEth:
    block_number = 25

    def __init__(self, fail_at=None):
        self.calls, self.fail_at = [], fail_at

    def get_logs(self, p):
        self.calls.append((p["fromBlock"], p["toBlock"]))
        if p["fromBlock"] == self.fail_at:
            raise RuntimeError("rpc down")
        return [{"blockNumber": p["fromBlock"]}]


class FakeW3:
    def __init__(self, **kw):
        self.eth = FakeEth(**kw)


class TestSpanned(unittest.TestCase):
    def test_windows_cover_the_range_once(self):
        w3 = FakeW3()
        out = get_logs_spanned(w3, {"fromBlock": 0, "toBlock": "latest", "address": "0x1"}, span=10)
        self.assertEqual(w3.eth.calls, [(0, 9), (10, 19), (20, 25)])
        self.assertEqual([l["blockNumber"] for l in out], [0, 10, 20])

    def test_explicit_end_and_single_window(self):
        w3 = FakeW3()
        get_logs_spanned(w3, {"fromBlock": 5, "toBlock": 7}, span=10)
        self.assertEqual(w3.eth.calls, [(5, 7)])

    def test_failed_window_raises(self):
        with self.assertRaises(RuntimeError):
            get_logs_spanned(FakeW3(fail_at=10), {"fromBlock": 0, "toBlock": "latest"}, span=10)


if __name__ == "__main__":
    unittest.main()
