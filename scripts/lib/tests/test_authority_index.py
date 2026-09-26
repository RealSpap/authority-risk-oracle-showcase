"""Unit tests for scripts/lib/authority_index.py -- pure logic, no RPC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.authority_index import blast_radius, build_index, classify_code, hygiene_summary, top_signers  # noqa: E402

A = "0x" + "11" * 20
B = "0x" + "22" * 20
C = "0x" + "33" * 20
SAFE = "0x" + "44" * 20
DELEGATE = "0x" + "ab" * 20


class ClassifyCode(unittest.TestCase):
    def test_empty_is_eoa(self):
        self.assertEqual(classify_code(b""), ("eoa", None))

    def test_7702_designator_returns_checksummed_delegate(self):
        kind, delegate = classify_code(b"\xef\x01\x00" + bytes.fromhex(DELEGATE[2:]))
        self.assertEqual(kind, "eip7702")
        self.assertEqual(delegate.lower(), DELEGATE.lower())

    def test_ordinary_bytecode_is_contract(self):
        self.assertEqual(classify_code(b"\x60\x80\x60\x40"), ("contract", None))

    def test_ef0100_prefix_with_wrong_length_is_not_a_delegation(self):
        # a real designator is exactly 23 bytes; a longer blob that merely starts 0xef0100 is a contract
        self.assertEqual(classify_code(b"\xef\x01\x00" + b"\x00" * 30)[0], "contract")


class Index(unittest.TestCase):
    def setUp(self):
        self.registries = {"base": {"g1": {"safes": [SAFE], "known_eoa": [C]}}, "arbitrum": {"g2": {"safes": [], "known_eoa": []}}}
        self.groups = {("base", "g1"): {A, B, C}, ("arbitrum", "g2"): {A}}
        self.index = build_index(self.registries, self.groups)

    def test_blast_radius_spans_ecosystems(self):
        r = blast_radius(self.index, A)
        self.assertEqual(r["ecosystems"], ["arbitrum", "base"])
        self.assertEqual(len(r["groups"]), 2)

    def test_tracked_safe_is_indexed_as_safe_not_signer(self):
        self.assertEqual({role for _, _, role in blast_radius(self.index, SAFE)["entries"]}, {"safe"})

    def test_unknown_address_has_empty_radius(self):
        self.assertEqual(blast_radius(self.index, "0x" + "99" * 20)["entries"], [])

    def test_top_signers_ranks_multi_ecosystem_first_and_skips_bare_safe(self):
        top = top_signers(self.index)
        self.assertEqual(top[0]["address"].lower(), A.lower())
        self.assertEqual(top[0]["ecosystems"], 2)
        self.assertNotIn(SAFE.lower(), [t["address"].lower() for t in top])


class Alias(unittest.TestCase):
    # Uniswap V3 timelock on L1 and its Arbitrum alias (both really appear in this project's registries).
    L1 = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"
    L2 = "0x2BAD8182C09F50c8318d769245beA52C32Be46CD"

    def test_l1_contract_query_finds_its_l2_alias_groups_and_vice_versa(self):
        index = {self.L1: [("ethereum-l1", "uni", "known_eoa")], self.L2: [("arbitrum", "uni", "known_eoa")]}
        for probe, other in ((self.L1, self.L2), (self.L2, self.L1)):
            r = blast_radius(index, probe)
            self.assertEqual(r["ecosystems"], ["arbitrum", "ethereum-l1"])
            self.assertEqual(r["via_alias"], [other])

    def test_no_alias_hit_for_unrelated_address(self):
        self.assertEqual(blast_radius({A: [("base", "g", "signer")]}, A)["via_alias"], [])


class Hygiene(unittest.TestCase):
    def test_counts_and_shared_delegate(self):
        classified = {("base", A): ("eip7702", DELEGATE), ("l1", B): ("eip7702", DELEGATE), ("l1", C): ("eoa", None), ("l1", SAFE): ("contract", None)}
        s = hygiene_summary(classified)
        self.assertEqual(s["counts"], {"eoa": 1, "eip7702": 2, "contract": 1})
        self.assertEqual(len(s["delegates"][DELEGATE]), 2)


if __name__ == "__main__":
    unittest.main()
