"""
Every copy of the project's composite formula, floor(0.4 a + 0.3 m + 0.3 t + 0.5), must use exact arithmetic.

In binary floating point that expression comes out one LOWER than the exact value for 2,054 of the 1,030,301
possible (a, m, t), for example (0, 1, 24): 0.3 + 7.199999999999999 + 0.5 floors to 7, the exact value is 8. No
published score was affected (checked against every live oracle entry on 2026-09-20), but the bias was latent in
nine copies of the formula. The reference here is written with `fractions.Fraction`, not with the code's own
formula, and it is checked on the 2,054 known-affected triples, the half-way boundaries and a fixed pseudo-random
sample of the whole domain, for every scorer module that defines `_composite`.
"""
import importlib.util
import math
import os
import random
import sys
import unittest
from fractions import Fraction

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

MODULES = {
    "base": ("chains/base-ecosystem/scorers.py", "_composite"),
    "plasma": ("chains/plasma-ecosystem/scorers.py", "_composite"),
    "ethereum-l1": ("chains/ethereum-l1/scorers.py", "_composite"),
    "solana": ("chains/solana/scorers.py", "_composite"),
    "monad": ("chains/monad/scorers.py", "_composite"),
    "arbitrum": ("chains/arbitrum-ecosystem/scorers.py", "_composite"),
    "zcash": ("chains/zcash/scorers.py", "_composite"),
    "shared": ("scripts/lib/scorers.py", "_composite"),
    "validator": ("scripts/validate_all_scorers.py", "_composite"),
}


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    d = os.path.dirname(path)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("aro_test_composite_" + name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def exact(a, m, t):
    return math.floor(Fraction(4 * a + 3 * m + 3 * t, 10) + Fraction(1, 2))


def float_form(a, m, t):
    return math.floor(0.4 * a + 0.3 * m + 0.3 * t + 0.5)


AFFECTED = [(a, m, t) for a in range(101) for m in range(101) for t in range(101) if float_form(a, m, t) != exact(a, m, t)]


class TestCompositeIsExact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fns = {}
        for name, (rel, fn) in MODULES.items():
            if name == "shared":   # uses package-relative imports, so it must be imported as a package module
                mod = importlib.import_module("scripts.lib.scorers")
            else:
                mod = _load(name, rel)
            cls.fns[name] = getattr(mod, fn)

    def test_the_float_form_really_is_wrong_on_these_triples(self):
        # guards the premise of this file: if this stops holding, the affected list below would be empty and vacuous
        self.assertEqual(len(AFFECTED), 2054)
        self.assertIn((0, 1, 24), AFFECTED)
        self.assertTrue(all(float_form(*x) == exact(*x) - 1 for x in AFFECTED))

    def test_every_copy_is_exact_on_every_affected_triple(self):
        for name, fn in self.fns.items():
            wrong = [x for x in AFFECTED if fn(*x) != exact(*x)]
            self.assertEqual(wrong[:3], [], name)

    def test_every_copy_is_exact_on_the_half_way_boundaries(self):
        # x.5 boundaries: 4a + 3m + 3t + 5 is a multiple of 10 exactly when the exact value sits on an integer
        pts = [(a, m, t) for a in range(0, 101, 5) for m in range(0, 101, 5) for t in range(0, 101, 5)]
        pts += [(0, 0, 0), (100, 100, 100), (0, 1, 24), (40, 57, 48), (7, 0, 0), (5, 18, 0), (65, 100, 0), (20, 50, 35)]
        for name, fn in self.fns.items():
            self.assertEqual([x for x in pts if fn(*x) != exact(*x)][:3], [], name)

    def test_every_copy_is_exact_on_a_fixed_random_sample_of_the_domain(self):
        rng = random.Random(20260920)
        pts = [(rng.randint(0, 100), rng.randint(0, 100), rng.randint(0, 100)) for _ in range(20000)]
        for name, fn in self.fns.items():
            self.assertEqual([x for x in pts if fn(*x) != exact(*x)][:3], [], name)

    def test_published_composites_are_unchanged(self):
        # (admin, multisig, timelock) -> composite, as published in the Zcash attestation and the Solana README
        published = {(20, 50, 35): 34, (50, 39, 0): 32, (5, 18, 0): 7, (65, 100, 0): 56}
        for name, fn in self.fns.items():
            for triple, comp in published.items():
                self.assertEqual(fn(*triple), comp, (name, triple))


if __name__ == "__main__":
    unittest.main()
