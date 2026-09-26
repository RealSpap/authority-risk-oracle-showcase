"""Unit tests for scripts/lib/safe_changes.py -- pure decoding, no RPC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.safe_changes import TOPIC_TO_NAME, decode_event, rank, summarize_by_safe  # noqa: E402

OWNER = "0x" + "ab" * 20
PAD = "0" * 24


def log(name_topic, topics_extra=(), data="0x", block="0x10", tx="0x" + "12" * 32):
    return {"topics": [name_topic, *topics_extra], "data": data, "blockNumber": block, "transactionHash": tx}


def topic(name):
    return next(t for t, n in TOPIC_TO_NAME.items() if n == name)


class Decode(unittest.TestCase):
    def test_known_topic_hashes_match_the_published_safe_events(self):
        # canonical topic0 values seen on-chain for Safe v1.3.0 / v1.4.1
        self.assertEqual(TOPIC_TO_NAME["0x610f7ff2b304ae8903c3de74c60c6ab1f7d6226b3f52c5161905bb5ad4039c93"], "ChangedThreshold")
        self.assertEqual(TOPIC_TO_NAME["0x9465fa0c962cc76958e6373a993326400c1c94f8be2fe3a952adfa7f60b2ea26"], "AddedOwner")

    def test_v130_address_in_data(self):
        e = decode_event(log(topic("AddedOwner"), data="0x" + PAD + OWNER[2:]))
        self.assertEqual((e["name"], e["value"].lower(), e["block"]), ("AddedOwner", OWNER, 16))

    def test_v141_address_in_indexed_topic(self):
        e = decode_event(log(topic("EnabledModule"), topics_extra=("0x" + PAD + OWNER[2:],)))
        self.assertEqual((e["name"], e["value"].lower()), ("EnabledModule", OWNER))

    def test_threshold_is_an_int(self):
        e = decode_event(log(topic("ChangedThreshold"), data="0x" + "0" * 63 + "3"))
        self.assertEqual(e["value"], 3)

    def test_other_topic_is_ignored(self):
        self.assertIsNone(decode_event(log("0x" + "00" * 32)))


class Rank(unittest.TestCase):
    def test_module_before_owner_before_guard_then_recent_first(self):
        ev = [{"name": "ChangedGuard", "block": 9}, {"name": "AddedOwner", "block": 1}, {"name": "EnabledModule", "block": 2}, {"name": "AddedOwner", "block": 5}]
        self.assertEqual([(e["name"], e["block"]) for e in rank(ev)], [("EnabledModule", 2), ("AddedOwner", 5), ("AddedOwner", 1), ("ChangedGuard", 9)])

    def test_summary_skips_safes_without_events(self):
        s = summarize_by_safe({"a": [{"name": "AddedOwner"}, {"name": "AddedOwner"}], "b": []})
        self.assertEqual(s, {"a": {"count": 2, "names": ["AddedOwner"]}})


if __name__ == "__main__":
    unittest.main()
