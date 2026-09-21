"""Tests for scripts/lib/implementation_watch.py and scripts/check_implementation_changes.py (no RPC)."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
import implementation_watch as iw  # noqa: E402


def keccak(b):
    return "h:" + bytes(b).hex()[:12]


def word(addr):
    return bytes(12) + bytes.fromhex(addr[2:])


T, IMPL, IMPL2, BEACON = "0x" + "aa" * 20, "0x" + "bb" * 20, "0x" + "cc" * 20, "0x" + "dd" * 20


class Chain:
    def __init__(self):
        self.code, self.storage, self.beacon = {}, {}, {}

    def fp(self, target=T):
        return iw.fingerprint(target, lambda a: self.code.get(a), lambda a, slot: self.storage.get((a, slot)),
                              lambda b: self.beacon.get(b), keccak)


class TestFingerprint(unittest.TestCase):
    def test_an_eoa_target_has_no_code(self):
        c = Chain(); c.code[T] = b""
        self.assertEqual(c.fp()["kind"], "no code")

    def test_a_failed_code_read_is_unread_never_a_fingerprint(self):
        self.assertEqual(Chain().fp(), {"kind": "unread"})

    def test_a_plain_contract_is_fingerprinted_by_its_own_code(self):
        c = Chain(); c.code[T] = b"\x60\x01"
        fp = c.fp()
        self.assertEqual((fp["kind"], fp["implementation"], fp["codeHash"]), ("plain", None, keccak(b"\x60\x01")))

    def test_an_eip1967_proxy_is_fingerprinted_by_its_implementation(self):
        c = Chain(); c.code[T] = b"\x60\x01"; c.code[IMPL] = b"\x61\x02"
        c.storage[(T, iw.IMPL_SLOT)] = word(IMPL)
        fp = c.fp()
        self.assertEqual((fp["kind"], fp["implementation"], fp["implementationCodeHash"]), ("eip1967 proxy", IMPL, keccak(b"\x61\x02")))

    def test_a_beacon_proxy_follows_the_beacon(self):
        c = Chain(); c.code[T] = b"\x60\x01"; c.code[IMPL] = b"\x61\x02"
        c.storage[(T, iw.BEACON_SLOT)] = word(BEACON); c.beacon[BEACON] = IMPL
        fp = c.fp()
        self.assertEqual((fp["kind"], fp["implementation"]), ("beacon proxy", IMPL))

    def test_an_erc1167_clone_carries_its_implementation(self):
        c = Chain()
        c.code[T] = bytes.fromhex("363d3d373d3d3d363d73") + bytes.fromhex(IMPL[2:]) + bytes.fromhex("5af43d82803e903d91602b57fd5bf3")
        c.code[IMPL] = b"\x62"
        self.assertEqual(c.fp()["kind"], "erc1167 clone")
        self.assertEqual(c.fp()["implementation"], IMPL)

    def test_an_all_zero_implementation_slot_is_not_a_proxy(self):
        c = Chain(); c.code[T] = b"\x60\x01"; c.storage[(T, iw.IMPL_SLOT)] = bytes(32)
        self.assertEqual(c.fp()["kind"], "plain")


class TestDiff(unittest.TestCase):
    def _snap(self, impl, code=b"\x61\x02"):
        c = Chain(); c.code[T] = b"\x60\x01"; c.code[impl] = code; c.storage[(T, iw.IMPL_SLOT)] = word(impl)
        return c.fp()

    def test_an_unchanged_target_reports_nothing(self):
        self.assertEqual(iw.diff({"k": self._snap(IMPL)}, {"k": self._snap(IMPL)}),
                         {"changed": {}, "new": [], "removed": [], "unread": []})

    def test_a_new_implementation_address_is_a_change(self):
        result = iw.diff({"k": self._snap(IMPL)}, {"k": self._snap(IMPL2)})
        self.assertEqual(result["changed"]["k"]["implementation"], (IMPL, IMPL2))

    def test_a_same_address_with_different_code_is_a_change(self):
        result = iw.diff({"k": self._snap(IMPL, b"\x61\x02")}, {"k": self._snap(IMPL, b"\x61\x03")})
        self.assertIn("implementationCodeHash", result["changed"]["k"])

    def test_new_and_removed_targets(self):
        result = iw.diff({"old": self._snap(IMPL)}, {"fresh": self._snap(IMPL)})
        self.assertEqual((result["new"], result["removed"]), (["fresh"], ["old"]))

    def test_an_unread_target_is_reported_and_never_a_change(self):
        result = iw.diff({"k": self._snap(IMPL)}, {"k": {"kind": "unread"}})
        self.assertEqual((result["changed"], result["unread"], result["new"]), ({}, ["k"], []))

    def test_an_unread_snapshot_entry_never_flags_a_change(self):
        self.assertEqual(iw.changed_fields({"kind": "unread"}, self._snap(IMPL)), {})


class TestSnapshotFile(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            self.assertEqual(iw.load_snapshot(path), {"takenAt": None, "targets": {}})
            iw.save_snapshot(path, "2026-09-21T00:00Z", {"b": {"kind": "plain"}, "a": {"kind": "no code"}})
            loaded = iw.load_snapshot(path)
            self.assertEqual(loaded["takenAt"], "2026-09-21T00:00Z")
            self.assertEqual(list(loaded["targets"]), ["a", "b"])  # stable order: clean diffs in git


class TestScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.abspath(os.path.join(HERE, "..", "..", "check_implementation_changes.py"))
        spec = importlib.util.spec_from_file_location("check_implementation_changes_under_test", path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_every_deployed_oracle_has_a_mainnet_rpc_so_no_target_is_silently_skipped(self):
        names = {name for name, _, _ in self.script.ORACLES}
        self.assertEqual(names - set(self.script.MAINNET_RPC), set())

    def test_every_oracle_has_a_chain_id_for_the_verification_lookup(self):
        self.assertEqual({name for name, _, _ in self.script.ORACLES} - set(self.script.CHAIN_ID), set())

    def _code(self, *sels):
        return b"".join(b"\x80\x63" + bytes.fromhex(x[2:]) + b"\x14\x61\x00\x10\x57" for x in sels) + b"\x00" * 8

    def test_review_lines_say_what_a_changed_implementation_adds_and_where_it_is_verified(self):
        codes = {"0xold": self._code("0xaaaaaaaa"), "0xnew": self._code("0xaaaaaaaa", "0x11111111")}
        lines = self.script.review_lines(
            {"implementation": ("0xold", "0xnew")}, codes.get, 9745,
            resolve=lambda sels: {"0x11111111": ["setNav(uint256)"]},
            verify=lambda chain, addr: [{"source": "sourcify", "status": "not verified", "name": None},
                                        {"source": "routescan", "status": "verified", "name": "YuzuUSDV3"}])
        text = "\n".join(lines)
        self.assertIn("1 added", text)
        self.assertIn("setNav(uint256)", text)
        self.assertIn("source of the new implementation: verified", text)
        self.assertIn("routescan: verified as YuzuUSDV3", text)

    def test_review_lines_for_a_chain_with_no_queryable_explorer_say_unknown_not_unverified(self):
        codes = {"0xold": self._code("0xaaaaaaaa"), "0xnew": self._code("0xaaaaaaaa")}
        lines = self.script.review_lines(
            {"implementation": ("0xold", "0xnew")}, codes.get, 4663, resolve=lambda s: {},
            verify=lambda chain, addr: [{"source": "sourcify", "status": "not verified", "name": None},
                                        {"source": "explorer", "status": "unknown (bot check)", "name": None}])
        self.assertIn("source of the new implementation: unknown", "\n".join(lines))
        self.assertNotIn("NOT verified", "\n".join(lines))

    def test_review_lines_when_the_old_implementation_is_gone_or_the_new_one_unreadable(self):
        codes = {"0xnew": self._code("0xaaaaaaaa")}
        lines = self.script.review_lines({"implementation": ("0x0", "0xnew")}, codes.get, 1, resolve=lambda s: {}, verify=lambda c, a: [])
        self.assertIn("previous implementation had no readable code", "\n".join(lines))
        self.assertEqual(self.script.review_lines({"implementation": ("0xold", "0xmissing")}, codes.get, 1), ["the new implementation's code could not be read"])

    def test_review_lines_ignore_a_change_that_is_not_an_implementation_change(self):
        self.assertEqual(self.script.review_lines({"codeHash": ("a", "b")}, lambda a: None, 1), [])

    def test_the_committed_snapshot_is_dated_and_covers_every_kind_of_target(self):
        snap = json.load(open(self.script.SNAPSHOT))
        self.assertRegex(snap["takenAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")
        self.assertGreaterEqual(len(snap["targets"]), 140)
        self.assertTrue({"plain", "eip1967 proxy"} <= {fp["kind"] for fp in snap["targets"].values()})
        for key in snap["targets"]:
            oracle, address = key.rsplit(":", 1)  # "<oracle name>:<lowercase address>"
            self.assertIn(oracle, {name for name, _, _ in self.script.ORACLES})
            self.assertEqual(address, address.lower())


if __name__ == "__main__":
    unittest.main()
