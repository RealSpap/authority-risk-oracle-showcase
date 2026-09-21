"""Tests for scripts/lib/nested_signers.py and scripts/check_nested_signers.py (no RPC)."""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
import nested_signers as ns  # noqa: E402

DELEGATE = "0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B"
DELEGATED_CODE = bytes.fromhex("ef0100") + bytes.fromhex(DELEGATE[2:])
SAFE_CODE = b"\x60" * 171


def eoa(n):
    return "0x" + hex(n)[2:].zfill(40)


class World:
    """A tiny fake chain: address -> (code, safe_resolution)."""

    def __init__(self):
        self.code, self.safes, self.reads = {}, {}, {}

    def add_eoa(self, a):
        self.code[a.lower()] = b""

    def add_safe(self, a, owners, k):
        self.code[a.lower()] = SAFE_CODE
        self.safes[a.lower()] = (list(owners), k)

    def get_code(self, a):
        self.reads[a.lower()] = self.reads.get(a.lower(), 0) + 1
        return self.code.get(a.lower())

    def get_safe(self, a):
        return self.safes.get(a.lower())

    def tree(self, a):
        return ns.build_tree(a, self.get_code, self.get_safe)


def world_aave():
    """A 4-of-7 Safe with three nested 1-of-3 Safes and four EOAs, like the Aave protocol guardian."""
    w = World()
    nested = [eoa(0x100 + i) for i in range(3)]
    for j, n in enumerate(nested):
        owners = [eoa(0x200 + 10 * j + i) for i in range(3)]
        for o in owners:
            w.add_eoa(o)
        w.add_safe(n, owners, 1)
    eoas = [eoa(0x300 + i) for i in range(4)]
    for e in eoas:
        w.add_eoa(e)
    top = eoa(0x1)
    w.add_safe(top, nested + eoas, 4)
    return w, top


class TestKinds(unittest.TestCase):
    def test_signer_kind(self):
        self.assertEqual(ns.signer_kind(None), "unread")
        self.assertEqual(ns.signer_kind(b""), "EOA")
        self.assertEqual(ns.signer_kind(DELEGATED_CODE), "EOA-7702")
        self.assertEqual(ns.signer_kind(SAFE_CODE), "contract")

    def test_a_23_byte_contract_without_the_prefix_is_not_a_7702_account(self):
        self.assertEqual(ns.signer_kind(b"\x60" * 23), "contract")

    def test_delegate_of(self):
        self.assertEqual(ns.delegate_of(DELEGATED_CODE), DELEGATE.lower())
        self.assertIsNone(ns.delegate_of(b""))
        self.assertIsNone(ns.delegate_of(None))


class TestTree(unittest.TestCase):
    def test_a_nested_safe_is_resolved_to_its_own_owners(self):
        w, top = world_aave()
        tree = w.tree(top)
        self.assertEqual((tree["kind"], tree["k"], tree["n"]), ("Safe", 4, 7))
        self.assertEqual(sorted(k["kind"] for k in tree["kids"]), ["EOA"] * 4 + ["Safe"] * 3)
        self.assertEqual(len(ns.nested_safes(tree)), 3)

    def test_min_eoa_keys_of_the_aave_shape_equals_the_top_threshold_but_leaf_keys_are_thirteen(self):
        w, top = world_aave()
        tree = w.tree(top)
        self.assertEqual(ns.min_eoa_keys(tree), 4)          # three seats cost 1 key each, plus one EOA
        self.assertEqual(len(ns.leaf_keys(tree)), 13)       # 4 EOAs + 3 nested Safes x 3 owners

    def test_a_nested_quorum_costs_what_its_own_quorum_costs(self):
        # Grove shape: a 2-of-2 whose two seats are one EOA and one nested 2-of-7 Safe: 1 + 2 = 3 keys.
        w = World()
        inner_owners = [eoa(0x400 + i) for i in range(7)]
        for o in inner_owners:
            w.add_eoa(o)
        w.add_safe(eoa(0x40), inner_owners, 2)
        w.add_eoa(eoa(0x41))
        w.add_safe(eoa(0x4), [eoa(0x40), eoa(0x41)], 2)
        self.assertEqual(ns.min_eoa_keys(w.tree(eoa(0x4))), 3)

    def test_an_unresolved_contract_signer_costs_one_key_the_weakest_reading(self):
        w = World()
        w.code[eoa(0x50).lower()] = b"\x60" * 7616   # a contract that is not a Safe
        w.add_eoa(eoa(0x51))
        w.add_safe(eoa(0x5), [eoa(0x50), eoa(0x51)], 2)
        tree = w.tree(eoa(0x5))
        self.assertEqual(ns.min_eoa_keys(tree), 2)
        self.assertEqual([k for k, _ in ns.unresolved_signers(tree)], ["contract"])

    def test_an_unread_signer_is_kept_and_reported(self):
        w = World()
        w.add_safe(eoa(0x6), [eoa(0x60)], 1)   # eoa(0x60) has no code entry: get_code returns None
        tree = w.tree(eoa(0x6))
        self.assertEqual(tree["kids"][0]["kind"], "unread")
        self.assertEqual(ns.status_of_signer("unread", tree["kids"][0]), "unanalyzed")

    def test_the_same_signer_is_read_once_per_cache(self):
        w = World()
        shared = eoa(0x70)
        w.add_eoa(shared)
        for i in range(3):
            w.add_safe(eoa(0x71 + i), [shared], 1)
        w.add_safe(eoa(0x7), [eoa(0x71), eoa(0x72), eoa(0x73)], 3)
        cache = {}
        ns.build_tree(eoa(0x7), w.get_code, w.get_safe, cache=cache)
        self.assertEqual(w.reads[shared.lower()], 1)   # owner of three nested Safes, read once
        self.assertIn(shared.lower(), cache)

    def test_depth_is_bounded(self):
        w = World()
        chain = [eoa(0x800 + i) for i in range(ns.MAX_DEPTH + 3)]
        for a, b in zip(chain, chain[1:]):
            w.add_safe(a, [b], 1)
        w.add_eoa(chain[-1])
        tree = w.tree(chain[0])
        node = tree
        for _ in range(ns.MAX_DEPTH):
            node = node["kids"][0]
        self.assertEqual(node["kind"], "contract")   # the resolver stopped instead of following the chain forever


class TestStatus(unittest.TestCase):
    def test_a_known_7702_delegate_is_analyzed_and_an_unknown_one_is_not(self):
        known = {"kind": "EOA-7702", "addr": eoa(1), "delegate": DELEGATE.lower()}
        unknown = {"kind": "EOA-7702", "addr": eoa(2), "delegate": eoa(0xBAD)}
        self.assertEqual(ns.status_of_signer("EOA-7702", known), "analyzed")
        self.assertEqual(ns.status_of_signer("EOA-7702", unknown), "unanalyzed")

    def test_a_known_contract_signer_is_analyzed(self):
        node = {"kind": "contract", "addr": "0xC06Fd4F821eaC1fF1ae8067b36342899b57BAa2d"}
        self.assertEqual(ns.status_of_signer("contract", node), "analyzed")
        self.assertEqual(ns.status_of_signer("contract", {"kind": "contract", "addr": eoa(3)}), "unanalyzed")


class TestOverlaps(unittest.TestCase):
    def test_expanding_nested_owners_finds_a_link_the_first_level_cannot_see(self):
        first = {("eth", "guardian"): {"a", "b"}, ("eth", "horizon"): {"x", "y"}}
        expanded = {("eth", "guardian"): {"a", "b", "k1", "k2"}, ("eth", "horizon"): {"x", "y", "k1", "k2"}}
        self.assertEqual(ns.overlaps(first), {})
        self.assertEqual(set(ns.overlaps(expanded)), {"k1", "k2"})
        self.assertEqual(ns.new_committee_links(first, expanded), {(("eth", "guardian"), ("eth", "horizon")): 2})

    def test_a_link_that_already_existed_at_the_first_level_is_not_new(self):
        first = {("a", "g"): {"k"}, ("b", "g"): {"k"}}
        expanded = {("a", "g"): {"k", "n"}, ("b", "g"): {"k"}}
        self.assertEqual(ns.new_committee_links(first, expanded), {})
        # ... but an address whose set of sharing committees grows is still reported
        first3 = {("a", "g"): {"k"}, ("b", "g"): {"k"}, ("c", "g"): set()}
        exp3 = {("a", "g"): {"k"}, ("b", "g"): {"k"}, ("c", "g"): {"k"}}
        self.assertEqual(set(ns.new_overlaps_when_expanded(first3, exp3)), {"k"})


class TestSignerNote(unittest.TestCase):
    def test_all_plain_eoas_give_no_note(self):
        self.assertIsNone(ns.signer_note([eoa(1), eoa(2)], lambda a: b""))

    def test_a_known_delegate_is_named(self):
        codes = {eoa(1): DELEGATED_CODE}
        note = ns.signer_note([eoa(1), eoa(2)], lambda a: codes.get(a, b""))
        self.assertIn("EIP-7702", note)
        self.assertIn("MetaMask EIP7702StatelessDeleGator", note)
        self.assertIn("no score input", note)

    def test_an_unknown_delegate_and_a_contract_and_an_unread_signer(self):
        codes = {eoa(1): bytes.fromhex("ef0100") + bytes.fromhex(eoa(0xBAD)[2:]), eoa(2): SAFE_CODE, eoa(3): None}
        note = ns.signer_note([eoa(1), eoa(2), eoa(3)], lambda a: codes[a])
        self.assertIn("NOT been analyzed", note)
        self.assertIn("is a contract", note)
        self.assertIn("could not be read", note)


class TestTablesAndSweep(unittest.TestCase):
    def test_tables_are_lowercase_dated_and_free_of_long_dashes(self):
        for table in (ns.KNOWN_7702_DELEGATES, ns.KNOWN_CONTRACT_SIGNERS):
            for addr, info in table.items():
                self.assertEqual(addr, addr.lower())
                self.assertRegex(info["analyzed"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertNotIn(chr(0x2014), info["summary"])

    @classmethod
    def _script(cls):
        path = os.path.abspath(os.path.join(HERE, "..", "..", "check_nested_signers.py"))
        spec = importlib.util.spec_from_file_location("check_nested_signers_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_the_sweep_reaches_the_safes_that_have_nested_seats(self):
        out = self._script().registered_safes(self._script().GROUPS)
        for pair in (("ethereum-l1", "0x2cfe3ec4d5"), ("monad", "0x401a33127e"), ("robinhood", "0x622e19d690")):
            self.assertTrue(any(e == pair[0] and a.startswith(pair[1]) for e, a in out), pair)


if __name__ == "__main__":
    unittest.main()
