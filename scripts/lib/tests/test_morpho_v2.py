"""Unit tests for scripts/lib/morpho_v2.py (2026-10-04): an abdicated function leaves the minimum, a reverted read makes
it UNREAD (never 0 days), everything abdicated gives inf (band 75). A fake `call` stands in for call_raw. No network."""
import os
import sys
import unittest

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import morpho_v2 as m  # noqa: E402

DAY = 86400
VAULT = "0x" + "77" * 20


def fake_call(answers):
    """answers: {(function signature, 'abdicated' | 'timelock'): value}; anything missing reverts (None)."""
    by_sel = {(bytes(Web3.keccak(text=sig)[:4]), name): v for (sig, name), v in answers.items()}

    def call(w3, vault, abi, name, selector):
        return by_sel.get((bytes(selector), name))
    return call


def shape(fund_delay=7 * DAY, gates_abdicated=(True, True, True, False), gate_delay=7 * DAY, over=None):
    a = {}
    for sig in m.FUND_REDIRECTING_FUNCTION_SIGS:
        a[(sig, "abdicated")], a[(sig, "timelock")] = False, fund_delay
    for sig, ab in zip(m.EXIT_GATE_FUNCTION_SIGS.values(), gates_abdicated):
        a[(sig, "abdicated")] = ab
        if not ab:
            a[(sig, "timelock")] = gate_delay
    a.update(over or {})
    return a


class TestTimelockAndGates(unittest.TestCase):
    def test_abdicated_fund_function_left_out(self):
        a = shape(over={("setAdapterRegistry(address)", "abdicated"): True, ("setAdapterRegistry(address)", "timelock"): 0})
        d, notes = m.timelock_and_gates(None, VAULT, call=fake_call(a))
        self.assertEqual(d, 7 * DAY)
        self.assertTrue(any("setAdapterRegistry(address): permanently abdicated" in n for n in notes))

    def test_reverted_abdicated_read_is_unread_not_zero(self):
        a = shape()
        del a[("addAdapter(address)", "abdicated")]
        d, notes = m.timelock_and_gates(None, VAULT, call=fake_call(a))
        self.assertIsNone(d)
        self.assertTrue(any("UNREAD" in n for n in notes))
        self.assertEqual(m.timelock_band(d), 0)

    def test_reverted_timelock_read_is_unread(self):
        a = shape()
        del a[("setSendAssetsGate(address)", "timelock")]
        self.assertIsNone(m.timelock_and_gates(None, VAULT, call=fake_call(a))[0])

    def test_everything_abdicated_is_inf_and_top_band(self):
        a = {(sig, "abdicated"): True for sig in m.FUND_REDIRECTING_FUNCTION_SIGS + list(m.EXIT_GATE_FUNCTION_SIGS.values())}
        d, notes = m.timelock_and_gates(None, VAULT, call=fake_call(a))
        self.assertEqual(d, float("inf"))
        self.assertEqual(m.timelock_band(d), 75)
        self.assertTrue(any("every fund-redirecting function and exit gate is abdicated" in n for n in notes))

    def test_minimum_not_maximum(self):
        a = shape(over={("increaseRelativeCap(bytes,uint256)", "timelock"): 3 * DAY})
        self.assertEqual(m.timelock_and_gates(None, VAULT, call=fake_call(a))[0], 3 * DAY)

    def test_bands(self):
        self.assertEqual([m.timelock_band(x) for x in (7 * DAY, 3 * DAY, 1, 0, None)], [75, 60, 40, 0, 0])


if __name__ == "__main__":
    unittest.main()
