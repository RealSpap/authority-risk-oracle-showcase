"""Unit tests for scripts/lib/squads_watch.py -- pure logic, no RPC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.squads_watch import diff, multisig_constants, shape  # noqa: E402

ADDR = "J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P"


def sq(members, threshold=4, tl=43200, cfg="1" * 32):
    return {"threshold": threshold, "time_lock_s": tl, "config_authority": cfg, "member_list": [{"key": k, "mask": m} for k, m in members.items()]}


class Constants(unittest.TestCase):
    def test_finds_local_and_module_level_ms_constants(self):
        src = f'    UPGRADE_MS = "{ADDR}"\nDRIFT_MS = "7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM"\nNOT_ONE = "abc"\n'
        got = multisig_constants(src)
        self.assertEqual(got[ADDR], ["UPGRADE_MS"])
        self.assertIn("7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM", got)
        self.assertEqual(len(got), 2)


class Diff(unittest.TestCase):
    def test_identical_is_empty(self):
        s = shape(sq({"a": 7, "b": 7}))
        self.assertEqual(diff(s, s), [])

    def test_removed_member_is_reported(self):
        old, new = shape(sq({"a": 7, "b": 7, "c": 7})), shape(sq({"a": 7, "b": 7}))
        self.assertEqual(diff(old, new), ["member removed c"])

    def test_added_member_threshold_timelock_and_permissions(self):
        old, new = shape(sq({"a": 7, "b": 7})), shape(sq({"a": 3, "b": 7, "d": 7}, threshold=3, tl=0))
        out = diff(old, new)
        self.assertIn("member added d (permissions 7)", out)
        self.assertIn("member a permissions 7 -> 3", out)
        self.assertIn("threshold 4 -> 3", out)
        self.assertIn("time lock (s) 43200 -> 0", out)


if __name__ == "__main__":
    unittest.main()
