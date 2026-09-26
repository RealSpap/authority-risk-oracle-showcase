"""Unit tests for scripts/lib/pending_ops.py -- pure decoding, no RPC."""
import os
import sys
import unittest

from eth_abi import encode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.pending_ops import COMPOUND_QUEUED, OZ_SCHEDULED, decode_scheduled, dedupe_ops, status  # noqa: E402

TARGET = "0x" + "ab" * 20
ID = "0x" + "11" * 32
TX = "0x" + "22" * 32


def word(n):
    return "0x" + n.to_bytes(32, "big").hex()


class Decode(unittest.TestCase):
    def test_oz_call_scheduled(self):
        data = encode(["address", "uint256", "bytes", "bytes32", "uint256"], [TARGET, 5, bytes.fromhex("a9059cbb") + b"\x00" * 64, b"\x00" * 32, 172800])
        log = {"topics": [OZ_SCHEDULED, ID, word(2)], "data": "0x" + data.hex(), "blockNumber": "0x10", "transactionHash": TX}
        op = decode_scheduled("oz", log)
        self.assertEqual((op["id"], op["index"], op["target"].lower(), op["value"], op["selector"], op["delay"], op["block"]),
                         (ID, 2, TARGET, 5, "0xa9059cbb", 172800, 16))

    def test_compound_queue_transaction(self):
        data = encode(["uint256", "string", "bytes", "uint256"], [0, "setPendingAdmin(address)", b"", 1_800_000_000])
        log = {"topics": [COMPOUND_QUEUED, ID, "0x" + "0" * 24 + TARGET[2:]], "data": "0x" + data.hex(), "blockNumber": 32, "transactionHash": TX}
        op = decode_scheduled("compound", log)
        self.assertEqual((op["id"], op["target"].lower(), op["eta"], op["signature"], op["selector"], op["block"]),
                         (ID, TARGET, 1_800_000_000, "setPendingAdmin(address)", "0x", 32))

    def test_wrong_family_topic_is_ignored(self):
        log = {"topics": [COMPOUND_QUEUED, ID, word(0)], "data": "0x", "blockNumber": 1, "transactionHash": TX}
        self.assertIsNone(decode_scheduled("oz", log))


class Status(unittest.TestCase):
    def test_waiting_ready_expired(self):
        self.assertEqual(status(50, 100), "waiting")
        self.assertEqual(status(150, 100), "ready")
        self.assertEqual(status(150, 100, grace=30), "expired")
        self.assertEqual(status(120, 100, grace=30), "ready")

    def test_batch_operation_counted_once(self):
        ops = [{"id": "a", "index": 0}, {"id": "a", "index": 1}, {"id": "b", "index": 0}]
        rows = dedupe_ops(ops)
        self.assertEqual({r["id"]: r["calls"] for r in rows}, {"a": 2, "b": 1})


if __name__ == "__main__":
    unittest.main()
