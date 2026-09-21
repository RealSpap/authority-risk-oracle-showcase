"""
Regression guard for chains/hyperliquid/scripts/methodology_test.py's composite(). Added 2026-09-22
(review of commit e8ad7d5, reservation "INCOMPLETE ROOT-CAUSE FIX"): same defective float
composite() the audit_rotation_index* family was just fixed for (int(0.4*a+0.3*m+0.3*t+0.5), one
LOWER than exact on 2054/1,030,301 (a,m,t) triples), found in this sibling live-re-derivation script.

This is the first test file under chains/hyperliquid/ -- wired into
.github/workflows/test.yml alongside it, so it isn't added silently unrun like the
audit_rotation_index* tests were before commit e8ad7d5.

Importing this module is safe: its body lives entirely inside main(), guarded by
`if __name__ == "__main__":` -- no network call happens on import.

Run:  python3 -m unittest discover -s chains/hyperliquid/tests -v
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


mt = _load("aro_test_hyperliquid_methodology_test", "chains/hyperliquid/scripts/methodology_test.py")


class TestComposite(unittest.TestCase):
    def test_uses_the_exact_integer_form_not_the_float_form_that_reads_one_low(self):
        self.assertEqual(mt.composite(0, 1, 24), 8)


if __name__ == "__main__":
    unittest.main()
