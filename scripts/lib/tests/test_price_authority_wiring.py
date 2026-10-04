"""Each price-consumer scorer puts price_authority's result into oracleAuthorityScore (rule of 2026-10-04), and the Robinhood
Chainlink admin (a provider) carries its own composite. Static checks on the scorer sources. No network."""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


CASES = [  # (scorer file, function, engine entry point, address it must receive)
    ("chains/ethereum-l1/scorers.py", "score_aave_v3_pool", "for_aave", "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"),
    ("chains/ethereum-l1/scorers.py", "score_compound_v3_cusdc", "for_comet", "0xc3d688B66703497DAA19211EEdff47f25384cdc3"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_adpend_usdc", "for_morpho_v1", "0x55555815a5595991C3A0Ff119B59AEF6C8B55555"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_1337_usdc", "for_morpho_v1", "0x94643e86aa5E38DDAc6c7791C1297f4E40cD96c1"),
    ("chains/base-ecosystem/scorers.py", "score_aave_v3_base", "for_aave", "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"),
    ("chains/base-ecosystem/scorers.py", "score_compound_v3_comet_base_usdc", "for_comet", "0xb125E6687d4313864e53df431d5425969c15Eb2F"),
    ("chains/arbitrum-ecosystem/scorers.py", "score_aave_v3_pool_arbitrum", "for_aave", "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"),
    ("chains/arbitrum-ecosystem/scorers.py", "score_compound_v3_comet_arbitrum_usdc", "for_comet", "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf"),
    ("chains/plasma-ecosystem/scorers.py", "score_aave_v3_pool_plasma", "for_aave", "0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9"),
    ("chains/monad/scorers.py", "score_aave_v3_monad", "for_aave", "0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"),
]


SPECS = {"chains/ethereum-l1/": "price_authority.ETHEREUM_SPECS", "chains/monad/": "price_authority.MONAD_SPECS"}


def body_of(rel, fn):
    src = open(os.path.join(ROOT, rel)).read()
    i = src.index(f"\ndef {fn}(")
    j = src.find("\ndef ", i + 5)
    return src[i:j if j > 0 else None]


class TestWiring(unittest.TestCase):
    def test_wiring_is_in_the_source_for_every_case(self):
        """The call is in the function body, with the chain's own w3, the target's address, that chain's specs and the entry's
        own notes list, and its value is what the scorer returns (a behavioural check needs a full fake chain per scorer;
        the live dry-runs of 2026-10-04 exercised each one end to end)."""
        for rel, fn, entry, address in CASES:
            with self.subTest(fn=fn):
                body = body_of(rel, fn)
                self.assertTrue(body.startswith(f"\ndef {fn}(w3)"), "the scorer's own chain w3 is what the engine reads")
                call = re.search(rf"oracle_authority = price_authority\.{entry}\((.*)\)", body)
                self.assertIsNotNone(call)
                args = [x.strip() for x in call.group(1).split(",")]
                self.assertEqual(args[0], "w3")
                self.assertEqual(re.findall(rf"^\s*{args[1]} = (.+)$", body, re.M), [f'"{address}"'])
                self.assertEqual(args[2], next((v for k, v in SPECS.items() if rel.startswith(k)), "None"))
                self.assertEqual(args[3], "notes")
                after = body[call.end():]
                self.assertNotRegex(after, re.compile(r"^\s*notes = ", re.M), "notes must not be replaced after the engine wrote into it")
                self.assertIn('"notes": notes', after)
                self.assertEqual(body.count('"oracleAuthorityScore":'), 1)
                self.assertIn('"oracleAuthorityScore": oracle_authority', body)

    def test_robinhood_chainlink_admin_is_its_own_composite(self):
        src = open(os.path.join(ROOT, "scripts/lib/scorers.py")).read()
        i = src.index("\ndef score_chainlink_admin_safe(")
        body = src[i:src.find("\ndef ", i + 5)]
        self.assertIn('"oracleAuthorityScore": composite, "compositeScore": composite', body)


if __name__ == "__main__":
    unittest.main()
