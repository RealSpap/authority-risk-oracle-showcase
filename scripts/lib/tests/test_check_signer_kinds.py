"""The command-line logic of scripts/check_signer_kinds.py (exit codes, refusal to write a lossy snapshot, no false outage alarms), with the RPC layer faked."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
_spec = importlib.util.spec_from_file_location("aro_check_signer_kinds", os.path.join(HERE, "..", "..", "check_signer_kinds.py"))
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

A, B, C = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40
D1 = "0x" + "1" * 40
BASE = {("base", A): ("eoa", None), ("base", B): ("eoa", None), ("base", C): ("eoa", None)}


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        tool.SNAPSHOT = os.path.join(self.tmp, "snap.json")

    def run_tool(self, classified, args=(), incomplete=()):
        tool.resolve_all = lambda: ({}, {}, {}, list(incomplete), {})
        tool.code_scan = lambda groups, w3s: classified
        old_argv, sys.argv = sys.argv, ["check_signer_kinds.py", *args]
        buf, code = io.StringIO(), None
        try:
            with contextlib.redirect_stdout(buf):
                try:
                    tool.main()
                except SystemExit as e:
                    code = e.code
        finally:
            sys.argv = old_argv
        return code, buf.getvalue()

    def baseline(self):
        self.assertEqual(self.run_tool(BASE, ["--update"])[0], 0)

    def test_quiet_when_nothing_changed(self):
        self.baseline()
        code, out = self.run_tool(BASE)
        self.assertEqual(code, 0)
        self.assertIn("0 changed, 0 new, 0 gone", out)

    def test_eoa_turning_delegated_exits_1_and_is_flagged(self):
        self.baseline()
        code, out = self.run_tool({**BASE, ("base", B): ("eip7702", D1)})
        self.assertEqual(code, 1)
        self.assertIn("[CHANGED]", out)

    def test_removed_delegation_is_info_and_exits_0(self):
        self.run_tool({**BASE, ("base", B): ("eip7702", D1)}, ["--update"])
        code, out = self.run_tool(BASE)
        self.assertEqual(code, 0)
        self.assertIn("[INFO]", out)

    def test_update_is_refused_while_a_signer_is_unread_and_the_snapshot_keeps_it(self):
        self.baseline()
        code, out = self.run_tool({**BASE, ("base", B): ("unread", "boom")}, ["--update"])
        self.assertEqual(code, 1)
        self.assertIn("snapshot NOT written", out)
        self.assertIn("base:" + B, json.load(open(tool.SNAPSHOT))["signers"])

    def test_an_unread_signer_is_unread_not_gone(self):
        self.baseline()
        code, out = self.run_tool({**BASE, ("base", B): ("unread", "boom")})
        self.assertEqual(code, 1)
        self.assertIn("[UNREAD]", out)
        self.assertIn("0 gone", out)

    def test_a_signer_that_left_every_group_exits_1(self):
        self.baseline()
        code, out = self.run_tool({k: v for k, v in BASE.items() if k[1] != A})
        self.assertEqual(code, 1)
        self.assertIn("[GONE]", out)

    def test_an_unresolved_group_gives_one_unconfirmed_count_not_one_alarm_per_owner(self):
        self.baseline()
        gone = {k: v for k, v in BASE.items() if k[1] == C}  # A and B vanish because their group could not be resolved
        code, out = self.run_tool(gone, incomplete=[("base", "grp", "0xsafe", "RpcUnavailable")])
        self.assertEqual(code, 1)
        self.assertEqual(out.count("[GONE]"), 0)
        self.assertIn("[GONE?] 2 signer(s) missing", out)
        self.assertIn("[UNREAD]", out)


if __name__ == "__main__":
    unittest.main()
