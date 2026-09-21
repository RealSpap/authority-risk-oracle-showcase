"""
Tests for scripts/live_target_counts.py's read_counts() -- the one behavior
that matters: an oracle that cannot be read (RPC down, no bytecode) must be
REPORTED, never silently dropped from the total, or the docs would quote a
grand total that omits a whole ecosystem while looking verified.
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load(name, rel):
    path = os.path.abspath(os.path.join(REPO_ROOT, rel))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ltc = _load("aro_test_live_target_counts", "scripts/live_target_counts.py")


class _Call:
    def __init__(self, v):
        self.v = v

    def call(self):
        if isinstance(self.v, Exception):
            raise self.v
        return self.v


class _FakeWeb3:
    """Per-RPC behavior table, keyed by the RPC URL passed to HTTPProvider."""
    behavior = {}

    @staticmethod
    def HTTPProvider(url, request_kwargs=None):
        return url

    @staticmethod
    def to_checksum_address(a):
        return a

    def __init__(self, url):
        self.url = url
        b = self.behavior[url]
        outer = self

        class _Eth:
            def get_code(self_inner, addr):
                return b["code"]

            def contract(self_inner, address, abi):
                class _C:
                    class functions:
                        @staticmethod
                        def trackedTargetsCount():
                            return _Call(b["count"])
                return _C()

        self.eth = _Eth()


ORACLES = [("A", "0x01", "rpc-a"), ("B", "0x02", "rpc-b"), ("C", "0x03", "rpc-c")]


class TestReadCounts(unittest.TestCase):
    def test_all_readable_returns_every_count(self):
        _FakeWeb3.behavior = {
            "rpc-a": {"code": b"\x60", "count": 57},
            "rpc-b": {"code": b"\x60", "count": 9},
            "rpc-c": {"code": b"\x60", "count": 14},
        }
        rows = ltc.read_counts(ORACLES, web3_cls=_FakeWeb3)
        self.assertEqual(rows, [("A", 57, None), ("B", 9, None), ("C", 14, None)])

    def test_rpc_failure_is_reported_not_dropped(self):
        _FakeWeb3.behavior = {
            "rpc-a": {"code": b"\x60", "count": 57},
            "rpc-b": {"code": b"\x60", "count": ConnectionError("rpc down")},
            "rpc-c": {"code": b"\x60", "count": 14},
        }
        rows = ltc.read_counts(ORACLES, web3_cls=_FakeWeb3)
        self.assertEqual(len(rows), 3)  # B is still a row
        name, count, err = rows[1]
        self.assertEqual((name, count), ("B", None))
        self.assertIn("ConnectionError", err)
        self.assertEqual(rows[0][1], 57)  # a later/earlier failure doesn't stop the others
        self.assertEqual(rows[2][1], 14)

    def test_missing_bytecode_is_reported_not_counted_as_zero(self):
        _FakeWeb3.behavior = {
            "rpc-a": {"code": b"\x60", "count": 57},
            "rpc-b": {"code": b"", "count": 9},  # would read 9 if we skipped the code check
            "rpc-c": {"code": b"\x60", "count": 14},
        }
        rows = ltc.read_counts(ORACLES, web3_cls=_FakeWeb3)
        self.assertEqual(rows[1], ("B", None, "no bytecode at oracle address"))


class TestReadSolanaCount(unittest.TestCase):
    def test_counts_the_registrys_tracked_targets(self):
        self.assertEqual(ltc.read_solana_count(reader=lambda: {"tracked": ["a", "b", "c"]}), ("Solana (Devnet)", 3, None))

    def test_a_failing_read_is_reported_not_counted_as_zero(self):
        def boom():
            raise ConnectionError("rpc down")
        name, count, err = ltc.read_solana_count(reader=boom)
        self.assertEqual((name, count), ("Solana (Devnet)", None))
        self.assertIn("ConnectionError", err)


if __name__ == "__main__":
    unittest.main()
