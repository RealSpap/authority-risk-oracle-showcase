"""Tests for scripts/lib/methodology.py (methodologyHash tied to the code, 2026-09-30, hardened after an independent
review the same day). No network. A throwaway git repo shaped like this one checks what the change rests on: the hash
moves when a scoring or push file changes and stays put otherwise; a real push is refused unless the files equal the
HEAD commit (including an edit git status does not show); a change during the run is refused; a clone that lives under
a directory named "tests" still hashes its files; a copy without .git only warns in describe()."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("aro_methodology_t", os.path.join(HERE, "..", "methodology.py"))
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


def git(root, *args):
    subprocess.run(["git", "-C", root, "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True, capture_output=True)


def fake_repo(parent):
    root = os.path.join(parent, "depot")
    write(root, "chains/tempo/scorers.py", "import os\nimport helper\nfrom web3_utils import get_w3\n\ndef f():\n    import lazy_mod\n")
    write(root, "chains/tempo/deploy/push_scores.py", "from oracle_keys import check\nMETHODOLOGY_VERSION = 'x-v1'\n")
    write(root, "chains/tempo/scripts/helper.py", "X = 1\n")
    write(root, "chains/tempo/scripts/lazy_mod.py", "Y = 1\n")
    write(root, "chains/tempo/scripts/unrelated_sweep.py", "Z = 1\n")
    write(root, "scripts/lib/web3_utils.py", "from .rpc import x\n")
    write(root, "scripts/lib/rpc.py", "x = 1\n")
    write(root, "scripts/lib/oracle_keys.py", "def check(): pass\n")
    write(root, "scripts/lib/methodology.py", "# the formula file\n")
    write(root, "scripts/lib/tests/test_web3_utils.py", "import web3_utils\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return os.path.realpath(root)


class FakeRepo(unittest.TestCase):
    def setUp(self):
        self.root = fake_repo(tempfile.mkdtemp())
        m.code_digest.cache_clear()

    def test_files_follow_scorer_and_push_imports_lazy_and_relative_plus_the_formula_not_tests(self):
        self.assertEqual(m.scoring_files("tempo", self.root), [
            "chains/tempo/deploy/push_scores.py", "chains/tempo/scorers.py", "chains/tempo/scripts/helper.py",
            "chains/tempo/scripts/lazy_mod.py", "scripts/lib/methodology.py", "scripts/lib/oracle_keys.py",
            "scripts/lib/rpc.py", "scripts/lib/web3_utils.py"])

    def test_hash_moves_with_scoring_or_push_code_only(self):
        h0 = m.evm_hash("tempo", "label-v1", self.root)
        for rel, moves in (("chains/tempo/scripts/unrelated_sweep.py", False), ("scripts/lib/oracle_keys.py", True),
                           ("chains/tempo/deploy/push_scores.py", True), ("scripts/lib/rpc.py", True)):
            write(self.root, rel, "changed = True\n" + rel)
            m.code_digest.cache_clear()
            h = m.evm_hash("tempo", "label-v1", self.root)
            self.assertEqual(h != h0, moves, rel)
            h0 = h
        self.assertNotEqual(m.evm_hash("tempo", "label-v2", self.root), m.evm_hash("tempo", "label-v1", self.root))

    def test_crlf_checkout_hashes_like_lf(self):
        h0 = m.evm_hash("tempo", "l", self.root)
        with open(os.path.join(self.root, "scripts/lib/rpc.py"), "wb") as f:
            f.write(b"x = 1\r\n")
        m.code_digest.cache_clear()
        self.assertEqual(m.evm_hash("tempo", "l", self.root), h0)

    def test_real_push_refused_unless_files_equal_head(self):
        m.require_committed("tempo", self.root)
        write(self.root, "chains/tempo/scripts/unrelated_sweep.py", "Z = 3\n")
        m.code_digest.cache_clear()
        m.require_committed("tempo", self.root)  # a non-scoring edit does not block
        write(self.root, "chains/tempo/scripts/helper.py", "X = 2\n")
        m.code_digest.cache_clear()
        with self.assertRaises(SystemExit):
            m.require_committed("tempo", self.root)

    def test_an_edit_hidden_from_git_status_is_still_refused(self):
        git(self.root, "update-index", "--skip-worktree", "chains/tempo/scripts/helper.py")
        write(self.root, "chains/tempo/scripts/helper.py", "X = 99\n")
        m.code_digest.cache_clear()
        with self.assertRaises(SystemExit):
            m.require_committed("tempo", self.root)

    def test_a_change_during_the_run_is_refused(self):
        m.code_digest("tempo", self.root)  # pinned before scoring
        m.assert_unchanged("tempo", self.root)
        write(self.root, "chains/tempo/scorers.py", "import helper\n# edited while scoring\n")
        with self.assertRaises(SystemExit):
            m.assert_unchanged("tempo", self.root)

    def test_a_clone_under_a_tests_directory_still_hashes_its_files(self):
        root = fake_repo(os.path.join(tempfile.mkdtemp(), "tests"))
        files = m.scoring_files("tempo", root)
        self.assertIn("chains/tempo/scorers.py", files)
        self.assertNotIn("scripts/lib/tests/test_web3_utils.py", files)

    def test_a_copy_without_git_warns_in_describe_and_refuses_a_real_push(self):
        copy = os.path.join(tempfile.mkdtemp(), "copy")
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        self.assertIn("WARNING", m.describe("tempo", "l", copy))
        with self.assertRaises(SystemExit):
            m.require_committed("tempo", copy)


class RealRepo(unittest.TestCase):
    def test_every_ecosystem_covers_its_scorer_push_and_formula_and_no_test_file(self):
        for eco, roots in m.ENTRY.items():
            files = m.scoring_files(eco)
            for r in (*roots, m.SELF):
                self.assertIn(r, files, eco)
            self.assertFalse([f for f in files if "tests" in f.split(os.sep)], eco)

    def test_solana_rule(self):
        import hashlib
        self.assertEqual(m.solana_hash("authority-risk-oracle-solana-v1"),
                         hashlib.sha256(f"authority-risk-oracle-solana-v1:{m.code_digest('solana')}".encode()).digest())


if __name__ == "__main__":
    unittest.main()
