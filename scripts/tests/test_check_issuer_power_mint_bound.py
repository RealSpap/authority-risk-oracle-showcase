"""Unit test for scripts/check_issuer_power.py's minter replay (R10, 2026-10-01): the current FiatToken minter set follows
chain order (block, logIndex), not the order the logs arrive in. No network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_issuer_power as c  # noqa: E402

A, B = "0x" + "aa" * 20, "0x" + "bb" * 20


def log(topic, who, block, idx):
    return {"topics": [topic, bytes(12) + bytes.fromhex(who[2:])], "blockNumber": block, "logIndex": idx}


class TestReplayMinters(unittest.TestCase):
    def test_chain_order_wins(self):
        logs = [log(c.MINTER_CONFIGURED, A, 10, 2), log(c.MINTER_REMOVED, A, 10, 1), log(c.MINTER_CONFIGURED, B, 5, 0),
                log(c.MINTER_REMOVED, B, 12, 0)]
        # A removed at index 1 then reconfigured at index 2 of the same block: still a minter. B removed later: gone.
        self.assertEqual(c.replay_minters(logs), {c.Web3.to_checksum_address(A)})

    def test_empty(self):
        self.assertEqual(c.replay_minters([]), set())


class TestMintBoundUnread(unittest.TestCase):
    """A reverted read on an identified interface is UNREAD, never 'no member' or a zero (review of 2026-10-01)."""

    def bound(self, call_raw, members):
        with mock.patch.object(c, "call_raw", side_effect=call_raw), mock.patch.object(c, "read_address_array_getter", side_effect=members):
            return c.read_mint_bound(object(), 1, "0x" + "cc" * 20, set())

    def test_decimals_revert(self):
        self.assertIn("UNREAD", self.bound(lambda *a: None, lambda *a: []))

    def test_agora_member_getter_revert(self):
        def call_raw(w3, addr, abi, name, *args):
            return {"decimals": 6, "minterAllowance": None, "getAmountCanBeMinted": (0, 5 * 10 ** 6), "isMintPaused": False}[name]
        out = self.bound(call_raw, lambda w3, addr, getter: None if getter == "getBridgeMinterRoleMembers" else [A])
        self.assertIn("getBridgeMinterRoleMembers() reverted: UNREAD", out)

    def test_agora_member_with_both_roles_counted_once(self):
        def call_raw(w3, addr, abi, name, *args):
            return {"decimals": 6, "minterAllowance": None, "getAmountCanBeMinted": (0, 5 * 10 ** 6), "isMintPaused": False}[name]
        out = self.bound(call_raw, lambda w3, addr, getter: [A])
        self.assertIn(": 5 mintable now", out)
        self.assertIn("Minter+BridgeMinter", out)


if __name__ == "__main__":
    unittest.main()
