"""Tests added by the second round of review for the workflow, the signed manifest and the secret scan. No network. Each test is a case an independent reviewer ran by hand.
"""
import contextlib, io, json, os, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS); sys.path.insert(0, os.path.join(SCRIPTS, "lib")); sys.path.insert(0, os.path.join(ROOT, "integrations"))
import agent_tools, alarm_gate, authority_facts_gate, authority_facts_gate_strict  # noqa: E402
from lib import reader_audit  # noqa: E402

import sign_run  # noqa: E402


class TestTheSignedManifestNamesTheCodeThatScores(unittest.TestCase):
    def test_the_code_field_covers_scripts_lib_and_chains_but_not_tests(self):
        import sign_run
        with tempfile.TemporaryDirectory() as t:
            for rel in ("scripts/a.py", "scripts/lib/scorers.py", "scripts/lib/tests/test_x.py", "scripts/tests/test_y.py", "scripts/lib/__pycache__/z.py", "chains/base/scorers.py", "chains/base/tests/test_b.py",
                        "rules.json", ".github/workflows/watch.yml"):
                os.makedirs(os.path.dirname(os.path.join(t, rel)), exist_ok=True); open(os.path.join(t, rel), "w").write("x = 1\n")
            os.makedirs(os.path.join(t, "watch")); open(os.path.join(t, "watch", "latest.json"), "w").write("{}")
            code = sign_run.manifest(os.path.join(t, "watch"))["code"]
        self.assertEqual(sorted(code), [".github/workflows/watch.yml", "chains/base/scorers.py", "rules.json", "scripts/a.py", "scripts/lib/scorers.py"])


class TestTheWorkflow(unittest.TestCase):
    WF = open(os.path.join(ROOT, ".github", "workflows", "watch.yml"), encoding="utf-8").read()

    def test_the_log_must_still_end_where_the_previous_signed_manifest_says_before_the_run_continues_it(self):
        i, j = self.WF.index("--head \"$head\""), self.WF.index("python3 scripts/watch_run.py 2>&1 | tee watch/run.log")
        self.assertLess(i, j)
        self.assertIn('echo "code=2" >> "$GITHUB_OUTPUT"', self.WF[i:j])        # the alarm steps read code 2: a refused continuation is an alarm
        self.assertIn("exit 1", self.WF[i:j])

    def test_the_counters_written_to_the_step_outputs_are_integers(self):
        import re
        for name in ("disagree", "overdue"):
            line = next(l for l in self.WF.splitlines() if l.strip().startswith('echo "%s=$(' % name))
            self.assertIn("print(int(json.load(", line, name)
        outs = [l for l in self.WF.splitlines() if l.strip().startswith('echo "') and ">> \"$GITHUB_OUTPUT\"" in l and "$(python3 -c" in l]
        self.assertTrue(outs)
        for l in outs:
            self.assertRegex(l, r"print\((int|len|sum)\(", l)


class TestTheSecretScan(unittest.TestCase):
    """The shapes are built from pieces here so that this file does not trip the scan itself."""
    def scan(self, files):
        import scan_secrets
        with tempfile.TemporaryDirectory() as t:
            for name, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(t, name)) or t, exist_ok=True); open(os.path.join(t, name), "w").write(text)
            return scan_secrets.scan(t), scan_secrets.main(["--root", t])

    def test_every_shape_is_found_with_its_file_and_line_and_never_its_value(self):
        shapes = {"private key block": "-----BEGIN " + "RSA PRIVATE KEY" + "-----", "GitHub token": "ghp" + "_" + "a" * 36, "AWS access key id": "AKI" + "A" + "B" * 16, "Slack token": "xox" + "b-" + "1" * 12,
                  "secret API key (sk- prefix)": "sk" + "-" + "x" * 40, "Google API key": "AI" + "za" + "z" * 35, "hexadecimal secret": "PRIVATE_KEY = '" + "0x" + "ab" * 32 + "'"}
        for kind, text in shapes.items():
            found, code = self.scan({"d/f.txt": "ok\n" + text + "\n"})
            self.assertEqual((found, code), ([("d/f.txt", 2, kind)], 1), kind)

    def test_clean_text_a_public_key_with_the_pragma_and_binary_names_are_not_findings(self):
        h = "ab" * 32
        found, code = self.scan({"a.md": "the public key is " + h + "\n", "b.py": "seed = '" + h + "'  # pragma: allowlist secret\n", "c.png": "ghp" + "_" + "a" * 36, "e.txt": "AKIA is a prefix\n"})
        self.assertEqual((found, code), ([], 0))

    def test_a_64_hex_value_without_a_secret_word_next_to_it_is_a_hash_not_a_finding(self):
        found, _ = self.scan({"x.json": '{"sha256": "' + "cd" * 32 + '"}\n'})
        self.assertEqual(found, [])


class TestTheFiveWordsAreNotBuiltInThePublishedTestFile(unittest.TestCase):
    def test_the_words_come_from_outside_the_repository(self):
        src = open(os.path.join(ROOT, "scripts", "tests", "test_watch_mechanisms.py"), encoding="utf-8").read()
        self.assertNotRegex(src, r'(?m)^CERV, SIM, EGO, PIEU, USERS = "')
        self.assertIn('os.environ.get("PUBLICATION_GUARD_WORDS")', src)


if __name__ == "__main__":
    unittest.main()
