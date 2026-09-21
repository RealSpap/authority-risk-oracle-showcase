"""
Tests for scripts/oracle_freshness.py: an unreadable oracle must be REPORTED (never dropped, or the
tool would read "all fresh" while an oracle was down), and the stale / stale-soon arithmetic against
`maxStaleness` must match the contract's `isStale()` rule (`block.timestamp > lastUpdated + maxStaleness`).
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load(name, rel):
    path = os.path.abspath(os.path.join(REPO_ROOT, rel))
    if os.path.dirname(path) not in sys.path:
        sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


of = _load("aro_test_oracle_freshness", "scripts/oracle_freshness.py")

DAY = 86400
NOW = 1_000_000_000


class _Call:
    def __init__(self, v):
        self.v = v

    def call(self):
        if isinstance(self.v, Exception):
            raise self.v
        return self.v


class _FakeWeb3:
    behavior = {}

    @staticmethod
    def HTTPProvider(url, request_kwargs=None):
        return url

    @staticmethod
    def to_checksum_address(a):
        return a

    def __init__(self, url):
        b = self.behavior[url]

        class _Eth:
            def get_code(_self, addr):
                return b["code"]

            def contract(_self, address, abi):
                class _F:
                    @staticmethod
                    def trackedTargetsCount():
                        return _Call(len(b["updated"]))

                    @staticmethod
                    def maxStaleness():
                        return _Call(b.get("max_staleness", 9 * DAY))

                    @staticmethod
                    def trackedTargets(i):
                        return _Call("0x%040x" % (i + 1))

                    @staticmethod
                    def getScore(t):
                        if isinstance(b["updated"], Exception):
                            return _Call(b["updated"])
                        i = int(t, 16) - 1
                        return _Call((1, 2, 3, 4, 5, 6, b["updated"][i], b"\x00" * 32))

                class _C:
                    functions = _F

                return _C()

        self.eth = _Eth()


ORACLES = [("A", "0x01", "rpc-a"), ("B", "0x02", "rpc-b")]


class TestReadFreshness(unittest.TestCase):
    def test_reads_every_target_of_every_oracle(self):
        _FakeWeb3.behavior = {
            "rpc-a": {"code": b"\x60", "updated": [NOW - DAY, NOW - 2 * DAY]},
            "rpc-b": {"code": b"\x60", "updated": [NOW]},
        }
        rows = of.read_freshness(ORACLES, web3_cls=_FakeWeb3)
        self.assertEqual([r[0] for r in rows], ["A", "B"])
        self.assertEqual(rows[0][1]["count"], 2)
        self.assertEqual(rows[0][1]["updated"][1], (1, "0x%040x" % 2, NOW - 2 * DAY))

    def test_missing_bytecode_is_reported_not_dropped(self):
        _FakeWeb3.behavior = {"rpc-a": {"code": b"", "updated": []}, "rpc-b": {"code": b"\x60", "updated": [NOW]}}
        rows = of.read_freshness(ORACLES, web3_cls=_FakeWeb3)
        self.assertEqual(rows[0], ("A", None, "no bytecode at oracle address"))
        self.assertIsNone(rows[1][2])

    def test_a_failing_read_is_reported_and_the_others_still_run(self):
        _FakeWeb3.behavior = {
            "rpc-a": {"code": b"\x60", "updated": [NOW]},
            "rpc-b": {"code": b"\x60", "updated": [NOW]},
        }

        class Boom(_FakeWeb3):
            def __init__(self, url):
                super().__init__(url)
                if url == "rpc-a":
                    raise ConnectionError("rpc down")

        rows = of.read_freshness(ORACLES, web3_cls=Boom)
        self.assertIsNone(rows[0][1])
        self.assertIn("ConnectionError", rows[0][2])
        self.assertEqual(rows[1][1]["count"], 1)


class TestReadFreshnessSolana(unittest.TestCase):
    def _oracle(self):
        return {"tracked": ["T1", "T2"], "max_staleness": 9 * DAY,
                "scores": [{"target": "T1", "lastUpdated": NOW - DAY}, {"target": "T2", "lastUpdated": NOW - 2 * DAY}]}

    def test_same_shape_as_the_evm_reader_so_summarize_needs_no_special_case(self):
        rows = of.read_freshness_solana(reader=self._oracle, name="S")
        self.assertEqual(len(rows), 1)
        name, info, err = rows[0]
        self.assertEqual((name, err), ("S", None))
        self.assertEqual(info, {"count": 2, "max_staleness": 9 * DAY, "updated": [(0, "T1", NOW - DAY), (1, "T2", NOW - 2 * DAY)]})
        s = of.summarize(info, NOW, 0)
        self.assertEqual(s["oldest"]["address"], "T2")
        self.assertEqual(s["stale"], [])

    def test_stale_entry_uses_the_registry_window_not_a_hardcoded_nine_days(self):
        o = self._oracle()
        o["max_staleness"] = DAY
        _, info, _ = of.read_freshness_solana(reader=lambda: o)[0]
        self.assertEqual([r["index"] for r in of.summarize(info, NOW, 0)["stale"]], [0, 1])

    def test_an_unreadable_program_is_reported_not_dropped(self):
        def boom():
            raise RuntimeError("Registry and score accounts disagree: 1 tracked without a score, 0 scored but not tracked")
        name, info, err = of.read_freshness_solana(reader=boom, name="S")[0]
        self.assertEqual((name, info), ("S", None))
        self.assertIn("disagree", err)


class TestSummarize(unittest.TestCase):
    def _info(self, updated, ms=9 * DAY):
        return {"count": len(updated), "max_staleness": ms, "updated": [(i, "0x%040x" % (i + 1), t) for i, t in enumerate(updated)]}

    def test_entry_at_exactly_max_staleness_is_flagged_one_second_before_the_contract_calls_it_stale(self):
        # contract rule: stale only when block.timestamp > lastUpdated + maxStaleness. The tool is deliberately
        # conservative: 0 seconds left already needs a re-push, because a second later it IS stale.
        s = of.summarize(self._info([NOW - 9 * DAY]), NOW, 0)
        self.assertEqual(s["rows"][0]["seconds_to_stale"], 0)
        self.assertEqual(len(s["stale"]), 1)
        just_fresh = of.summarize(self._info([NOW - 9 * DAY + 1]), NOW, 0)
        self.assertEqual(len(just_fresh["stale"]), 0)

    def test_fresh_stale_and_soon_are_separated(self):
        info = self._info([NOW - 10 * DAY, NOW - 8 * DAY - 3600, NOW - DAY])
        s = of.summarize(info, NOW, 48 * 3600)
        self.assertEqual([r["index"] for r in s["stale"]], [0])
        self.assertEqual([r["index"] for r in s["soon"]], [1])
        self.assertEqual(s["oldest"]["index"], 0)

    def test_soon_window_is_configurable(self):
        info = self._info([NOW - 5 * DAY])
        self.assertEqual(len(of.summarize(info, NOW, 24 * 3600)["soon"]), 0)
        self.assertEqual(len(of.summarize(info, NOW, 5 * DAY)["soon"]), 1)

    def test_custom_max_staleness_is_used(self):
        s = of.summarize(self._info([NOW - 2 * DAY], ms=DAY), NOW, 0)
        self.assertEqual(len(s["stale"]), 1)

    def test_empty_oracle_has_no_oldest(self):
        s = of.summarize(self._info([]), NOW, 0)
        self.assertIsNone(s["oldest"])
        self.assertEqual(s["rows"], [])


if __name__ == "__main__":
    unittest.main()
