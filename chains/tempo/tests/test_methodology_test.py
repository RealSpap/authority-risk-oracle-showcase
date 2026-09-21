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


if __name__ == "__main__":
    unittest.main()
