"""Unit test for scripts/check_registry_diff_defiscan.py: the FULL / PREFIX / ABSENT classification and the rule that the
tool's own output is never read back as "known" (otherwise a second run would find everything). No network."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_registry_diff_defiscan as c  # noqa: E402

A = "0x7cfe99c15537753682def016d17d4b29a7cab4ee"


class TestClassify(unittest.TestCase):
    def test_full_prefix_absent(self):
        corpus = f"admin {A} here, and 0xb05a6449... elsewhere, and 0x1234abcd99 as part of a longer word"
        full = {A}
        self.assertEqual(c.classify("eth:" + A.upper().replace("0X", "0x"), corpus, full), "FULL")
        self.assertEqual(c.classify("eth:0xB05A6449f383a1A43A172970858B97394FEcDAD6", corpus, full), "PREFIX")
        # a prefix that only appears inside a longer hex string is not a mention
        self.assertEqual(c.classify("0x1234abcd00000000000000000000000000000000", corpus, full), "ABSENT")

    def test_own_output_is_not_read_back(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "data"))
        with open(os.path.join(root, "data", "registry_diff_defiscan_2026-09-30.json"), "w") as f:
            f.write(A)
        with open(os.path.join(root, "data", "finding.md"), "w") as f:
            f.write("nothing here")
        self.assertNotIn(A, c.repo_corpus(root, ("data",)))


if __name__ == "__main__":
    unittest.main()
