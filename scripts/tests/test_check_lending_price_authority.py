"""Unit test for scripts/check_lending_price_authority.py: selector search in bytecode, source classification, the
tri-state two-RPC read, the steward-limit decoding (15 pairs or UNREAD), and the rule that a simulation only means
something when its harmless control passed. No network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_lending_price_authority as c  # noqa: E402


class FakeEth:
    def __init__(self, ret):
        self.ret = ret

    def call(self, tx):
        if isinstance(self.ret, Exception):
            raise self.ret
        return self.ret


class FakeW3:
    def __init__(self, ret):
        self.eth = FakeEth(ret)


class TestSlotConstants(unittest.TestCase):
    def test_each_slot_is_its_eip1967_derivation(self):  # BEACON_SLOT was wrong until 2026-10-04 (no holder had one set)
        from web3 import Web3
        k = lambda t: int.from_bytes(Web3.keccak(text=t), "big") - 1  # noqa: E731
        self.assertEqual((c.IMPL_SLOT, c.ADMIN_SLOT, c.BEACON_SLOT),
                         (k("eip1967.proxy.implementation"), k("eip1967.proxy.admin"), k("eip1967.proxy.beacon")))


class TestCodePaths(unittest.TestCase):
    def test_push_only(self):
        sel = c.selector("updateLstPriceCaps((address,(uint104,uint48,uint16))[])")
        code = b"\x60\x80" + c.push_bytes("updateLstPriceCaps((address,(uint104,uint48,uint16))[])") + b"\x00" + c.selector("setPriceCap(int256)")
        self.assertEqual(c.code_paths(code), ["updateLstPriceCaps"])  # setPriceCap's selector is there, but not pushed
        self.assertEqual(len(c.push_bytes("x")), 1 + len(c.selector("x").lstrip(b"\0")))
        self.assertEqual(c.push_bytes("updateLstPriceCaps((address,(uint104,uint48,uint16))[])")[0], 0x63)
        self.assertEqual(sel.hex(), "2cd77b80")

    def test_shifted_selector_is_found(self):
        # via-IR form seen in the PendleDiscountRateAgent: PUSH4 20730b65 PUSH1 e2 SHL == setDiscountRatePerYear(uint64) << 224
        code = b"\x60\x80" + bytes.fromhex("6320730b6560e21b")
        self.assertEqual(c.code_paths(code), ["setDiscountRatePerYear"])
        self.assertEqual(c.selector("setDiscountRatePerYear(uint64)").hex(), "81cc2d94")

    def test_push32_form_is_found(self):
        code = b"\x60\x80\x7f" + c.selector("setPriceCap(int256)") + bytes(28)
        self.assertEqual(c.code_paths(code), ["setPriceCap"])

    def test_leading_zero_selector_uses_push3(self):
        with mock.patch.object(c, "selector", return_value=bytes.fromhex("00abcdef")):
            self.assertEqual(c.push_bytes("any"), bytes.fromhex("62abcdef"))


class TestClassifySource(unittest.TestCase):
    NO = (None, False)

    def probes(self, **over):
        p = {"getSnapshotRatio": self.NO, "getPriceCap": self.NO, "discountRatePerYear": self.NO, "getPriceCapRatio": self.NO,
             "description": ("Fixed mUSD/USD", True)}
        p.update(over)
        return p

    def test_kinds(self):
        acl = ("0xacl", True)
        self.assertEqual(c.classify_source(acl, self.probes(getSnapshotRatio=(1, True))), c.LST)
        self.assertEqual(c.classify_source(acl, self.probes(getPriceCap=(1, True))), c.STABLE)
        self.assertEqual(c.classify_source(acl, self.probes(discountRatePerYear=(1, True))), c.PENDLE)
        self.assertEqual(c.classify_source(acl, self.probes(getPriceCapRatio=(1, True))), c.RATIO)
        self.assertEqual(c.classify_source(acl, self.probes()), "other Aave adapter (Fixed mUSD/USD)")
        self.assertEqual(c.classify_source((None, False), self.probes()), "external feed")

    def test_unread_is_never_a_kind(self):
        self.assertEqual(c.classify_source((None, None), self.probes()), "UNREAD")
        self.assertEqual(c.classify_source(("0xacl", True), self.probes(getPriceCap=(None, None))), "UNREAD")


class TestTwoRpcs(unittest.TestCase):
    def run_with(self, results):
        it = iter(results)
        with mock.patch.object(c, "read", side_effect=lambda *a, **k: next(it)), mock.patch.object(c, "get_w3"):
            return c.two_rpcs("RISK_COUNCIL", "0x" + "11" * 20)

    def test_states(self):
        self.assertEqual(self.run_with([("0xa", True), ("0xa", True)]), ("0xa", "ok"))
        self.assertEqual(self.run_with([(None, False), (None, False)]), (None, "absent"))
        self.assertEqual(self.run_with([(None, None), (None, False)]), (None, "unread"))
        self.assertEqual(self.run_with([("0xa", True), (None, False)]), (None, "unread"))
        self.assertEqual(self.run_with([("0xa", True), ("0xb", True)]), (None, "unread"))


class TestStewardBounds(unittest.TestCase):
    def test_fifteen_distinct_pairs(self):
        words = []
        for i in range(15):
            words += [86400 * (i + 1), 10 * (i + 1)]
        words[-1] = 3 * 10 ** 16  # Pendle: absolute, in 1e18 units
        raw = b"".join(w.to_bytes(32, "big") for w in words)
        out = c.steward_bounds(FakeW3(raw), "0x" + "11" * 20)
        self.assertIn("maxYearlyGrowth may move 1.3% (relative) per update, one update per 13 d", out)
        self.assertIn("stable: cap may move 1.4% per update, one per 14 d", out)
        self.assertIn("Pendle: discount rate may move 3 points (absolute) per update, one per 15 d", out)

    def test_other_layout_is_unread(self):
        self.assertIn("UNREAD", c.steward_bounds(FakeW3(b"\x00" * 32 * 32), "0x" + "11" * 20))
        with mock.patch.object(c.time, "sleep"):
            self.assertIn("UNREAD", c.steward_bounds(FakeW3(RuntimeError("429")), "0x" + "11" * 20))


class TestReplaySenders(unittest.TestCase):
    def test_chain_order(self):
        add, rem = bytes(c.Web3.keccak(text="AuthorizedSenderAdded(address)")), bytes(c.Web3.keccak(text="AuthorizedSenderRemoved(address)"))
        a, b = bytes(12) + b"\xaa" * 20, bytes(12) + b"\xbb" * 20
        logs = [{"topics": [rem, a], "data": b"", "blockNumber": 9, "logIndex": 0}, {"topics": [add, a], "data": b"", "blockNumber": 5, "logIndex": 0},
                {"topics": [add], "data": b, "blockNumber": 7, "logIndex": 0}]  # address in data, not indexed
        self.assertEqual(c.replay_senders(logs), [c.Web3.to_checksum_address("0x" + "bb" * 20)])


class TestVerdict(unittest.TestCase):
    def test_control_must_pass(self):
        self.assertIn("INCONCLUSIVE", c._verdict(False, False, "x"))
        self.assertIn("UNREAD", c._verdict(None, False, "x"))
        self.assertIn("UNREAD", c._verdict(True, None, "x"))
        self.assertIn("REFUSES", c._verdict(True, False, "x"))
        self.assertIn("ACCEPTS", c._verdict(True, True, "x"))


if __name__ == "__main__":
    unittest.main()
