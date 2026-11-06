"""
Regression guard for chains/tempo/scripts/methodology_test.py's composite(). Added 2026-09-22
(review of commit e8ad7d5, reservation "INCOMPLETE ROOT-CAUSE FIX"): this file had the identical
defective float composite() the audit_rotation_index* family was just fixed for -- same formula,
same 2054/1,030,301 exposure, found by the review reading the whole tree rather than trusting the
commit message's "fixed in all 3 files" claim (which was true only of the audit_rotation_index*
family, not of this sibling live-re-derivation script in the same directory).

Importing this module is safe: its body lives entirely inside main(), guarded by
`if __name__ == "__main__":` -- no network call happens on import.

Run:  python3 -m unittest discover -s chains/tempo/tests -v
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mt = _load("aro_test_tempo_methodology_test", "chains/tempo/scripts/methodology_test.py")


class TestComposite(unittest.TestCase):
    def test_uses_the_exact_integer_form_not_the_float_form_that_reads_one_low(self):
        self.assertEqual(mt.composite(0, 1, 24), 8)


class TestResolverArbiter(unittest.TestCase):
    """R10 (2026-11-06): Held's arbiter on Tempo testnet. Offline: rpc() and call() are replaced, no network."""
    ARB = "0xe80694d6feC5d676aD4B7D51478559BE8CC54F3e"
    RES = "0x3E33eDf4Ab2Cc43fc4a5aA4511835CB924eD38bD"
    CODE = bytes([0x60, 0xF4, 0x00])    # PUSH1 0xf4 (data, not an instruction), STOP

    def run_score(self, code=None, owner=None, resolver_code="0x", slot=0):
        code = self.CODE if code is None else code
        h = mt.keccak(self.CODE).hex()

        def rpc(url, method, params):
            if method == "eth_getCode":
                return "0x" + code.hex() if params[0] == self.ARB else resolver_code
            if method == "eth_getStorageAt":
                return hex(slot)
            raise AssertionError(method)

        def call(to, sig, arg_types=(), args=(), out_types=(), url=None):
            return {"owner()": owner, "resolver()": (self.RES,)}[sig]
        old = (mt.rpc, mt.call, mt.HELD_ARBITER_CODE_HASH)
        mt.rpc, mt.call, mt.HELD_ARBITER_CODE_HASH = rpc, call, h
        try:
            return mt.score_resolver_arbiter("x", self.ARB)
        finally:
            mt.rpc, mt.call, mt.HELD_ARBITER_CODE_HASH = old

    def test_the_data_of_a_push_is_not_an_instruction(self):
        self.assertTrue(mt._opcode_absent(bytes([0x60, 0xF4]), (0xF4,)))
        self.assertFalse(mt._opcode_absent(bytes([0xF4]), (0xF4,)))
        self.assertFalse(mt._opcode_absent(bytes([0x60, 0x01, 0xFF]), (0xFF,)))

    def test_an_immutable_arbiter_with_a_plain_resolver_key_is_scored_as_that_key(self):
        r = self.run_score()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (10, 15, 0, 9))
        self.assertTrue(all(r["reads"]["checks"].values()))

    def test_a_different_code_an_owner_a_proxy_slot_or_a_resolver_with_code_degrades_to_the_unresolved_key(self):
        for kw in ({"code": bytes([0x00])}, {"owner": (self.RES,)}, {"slot": 1}, {"resolver_code": "0x6001"}):
            r = self.run_score(**kw)
            self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (20, 0, 8), kw)


if __name__ == "__main__":
    unittest.main()
