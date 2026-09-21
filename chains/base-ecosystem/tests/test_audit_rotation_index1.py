"""
Regression guard for chains/base-ecosystem/scripts/audit_rotation_index1_2026-09-21.py's
composite(). Added 2026-09-22 (review of commit e8ad7d5, reservation "BASE-ECOSYSTEM'S composite()
FIX IS THE ONE WITH NO REGRESSION GUARD"): this file's composite() was fixed to the exact-integer
form (4a+3m+3t+5)//10, replacing a float form documented (scripts/lib/scorers.py) to read one LOWER
than exact on 2054/1,030,301 (a,m,t) triples -- but chains/base-ecosystem/tests/ never imported or
touched this file, so nothing would notice if that fix were reverted. Mirrors the identical
assertion added to chains/ethereum-l1/tests/test_audit_rotation_index1.py and chains/tempo/tests/
test_audit_rotation_index.py for the same defect in their own composite() functions.

Importing this module is safe: its audit body lives entirely inside main(), guarded by
`if __name__ == "__main__":` -- no network call happens on import.

Run:  python3 -m unittest discover -s chains/base-ecosystem/tests -v
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


a = _load("aro_test_base_audit_rotation_index1", "chains/base-ecosystem/scripts/audit_rotation_index1_2026-09-21.py")


class TestComposite(unittest.TestCase):
    def test_uses_the_exact_integer_form_not_the_float_form_that_reads_one_low(self):
        # (0, 1, 24) is one of the 2054 triples where int(0.4*a+0.3*m+0.3*t+0.5) reads 7 instead of
        # the exact 8 -- independently brute-forced across all 1,030,301 (a,m,t) triples before the
        # fix that introduced this test.
        self.assertEqual(a.composite(0, 1, 24), 8)


if __name__ == "__main__":
    unittest.main()
