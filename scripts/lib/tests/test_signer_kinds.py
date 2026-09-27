"""Unit tests for scripts/lib/signer_kinds.py -- pure logic, no RPC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.signer_kinds import diff, key, snapshot  # noqa: E402

A, B, C = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40
D1, D2 = "0x" + "1" * 40, "0x" + "2" * 40


class Snapshot(unittest.TestCase):
    def test_keys_are_lowercase_and_unread_is_left_out(self):
        s = snapshot({("base", A.upper().replace("0X", "0x")): ("eoa", None), ("base", B): ("unread", "boom"), ("monad", C): ("eip7702", D1.upper().replace("0X", "0x"))})
        self.assertEqual(set(s), {key("base", A), key("monad", C)})
        self.assertEqual(s[key("monad", C)], {"kind": "eip7702", "delegate": D1})


class Diff(unittest.TestCase):
    def test_identical_is_quiet(self):
        s = snapshot({("base", A): ("eoa", None)})
        self.assertEqual(diff(s, s), {"changed": [], "new": [], "gone": []})

    def test_eoa_becoming_delegated_is_high(self):
        old, new = snapshot({("base", A): ("eoa", None)}), snapshot({("base", A): ("eip7702", D1)})
        self.assertEqual(diff(old, new)["changed"], [("HIGH", key("base", A), f"eoa -> EIP-7702 delegated to {D1}")])

    def test_delegate_change_is_high_and_removal_is_info(self):
        old = snapshot({("base", A): ("eip7702", D1), ("base", B): ("eip7702", D1)})
        new = snapshot({("base", A): ("eip7702", D2), ("base", B): ("eoa", None)})
        got = {k: s for s, k, _ in diff(old, new)["changed"]}
        self.assertEqual(got, {key("base", A): "HIGH", key("base", B): "INFO"})

    def test_new_and_gone_pairs_are_listed_separately(self):
        old, new = snapshot({("base", A): ("eoa", None), ("base", B): ("eoa", None)}), snapshot({("base", B): ("eoa", None), ("base", C): ("eoa", None)})
        d = diff(old, new)
        self.assertEqual((d["new"], d["gone"], d["changed"]), ([key("base", C)], [key("base", A)], []))

    def test_an_unread_signer_is_never_reported_as_gone(self):
        old = snapshot({("base", A): ("eoa", None), ("base", B): ("eoa", None)})
        new = snapshot({("base", A): ("eoa", None)})  # B could not be read this time
        self.assertEqual(diff(old, new, unread={key("base", B)})["gone"], [])
        self.assertEqual(diff(old, new)["gone"], [key("base", B)])

    def test_a_new_signer_that_is_already_delegated_is_high_and_a_new_contract_is_info(self):
        old = snapshot({("base", A): ("eoa", None)})
        new = snapshot({("base", A): ("eoa", None), ("base", B): ("eip7702", D1), ("base", C): ("contract", None)})
        got = {k: s for s, k, _ in diff(old, new)["changed"]}
        self.assertEqual(got, {key("base", B): "HIGH", key("base", C): "INFO"})

    def test_contract_change_is_high(self):
        old, new = snapshot({("base", A): ("eoa", None)}), snapshot({("base", A): ("contract", None)})
        self.assertEqual(diff(old, new)["changed"][0][0], "HIGH")


if __name__ == "__main__":
    unittest.main()
