"""A workflow that runs a test folder importing yaml has to install PyYAML first (it is not in requirements.txt: the Watch does not need it).
Without it the suite stops at the import, on GitHub, hours after the change: the unit-test job and the weekly mutation replay both did."""
import glob, os, re, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INSTALL = re.compile(r"pip install[^\n]*PyYAML", re.I)   # pip names are not case sensitive; known limit: an install in any job of the file counts, even if the suite runs in another job
TEST_DIRS = ["scripts/lib/tests", "scripts/tests"] + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "chains", "*", "tests")))


def yaml_dirs():
    """The test folders where a file imports yaml at load time (a guarded import inside a test skips instead of failing)."""
    return [d for d in TEST_DIRS if any(re.search(r"^(import yaml|from yaml )", open(f, encoding="utf-8").read(), re.M) for f in glob.glob(os.path.join(ROOT, d, "*.py")))]


def runs_suite(text, folder):
    """True when the workflow runs the folder: `-s <folder>`, or scripts/mutate.py, which replays scripts/tests."""
    return bool(re.search(r"-s %s(\s|$)" % re.escape(folder), text, re.M)) or (folder == "scripts/tests" and "scripts/mutate.py" in text)


def missing(text, folders):
    """The folders the workflow runs without a PyYAML install placed before the first run of that folder."""
    out = []
    for d in folders:
        if not runs_suite(text, d): continue
        i = INSTALL.search(text)
        first = min(m.start() for m in [re.search(r"-s %s(\s|$)" % re.escape(d), text, re.M), re.search(r"scripts/mutate\.py", text) if d == "scripts/tests" else None] if m)
        if not (i and i.start() < first): out.append(d)
    return out


class TestWorkflowsInstallPyYaml(unittest.TestCase):
    def test_no_workflow_runs_a_test_folder_that_imports_yaml_without_installing_it_first(self):
        folders = yaml_dirs(); self.assertIn("scripts/tests", folders)   # the import was found: a pattern that matched nothing could not pass
        files = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")))
        if not files: self.skipTest("the workflows are not in this checkout")
        checked = [os.path.basename(f) for f in files if any(runs_suite(open(f, encoding="utf-8").read(), d) for d in folders)]
        bad = {os.path.basename(f): missing(open(f, encoding="utf-8").read(), folders) for f in files}
        self.assertEqual({k: v for k, v in bad.items() if v}, {})
        self.assertGreaterEqual(len(checked), 2, checked)   # test.yml and mutation.yml were read as workflows that run the suite

    def test_the_check_sees_a_missing_install_a_late_install_and_a_good_one(self):
        run = "      - run: python3 -m unittest discover -s scripts/tests -v\n"; pip = "      - run: pip install \"PyYAML==6.0.2\"\n"; base = "      - run: pip install -r scripts/requirements.txt\n"
        self.assertEqual(missing(base + run, ["scripts/tests"]), ["scripts/tests"])
        self.assertEqual(missing(base + run + pip, ["scripts/tests"]), ["scripts/tests"])   # installed after the run is too late
        self.assertEqual(missing(base + pip + run, ["scripts/tests"]), [])
        self.assertEqual(missing(base + "      - run: python3 scripts/mutate.py\n", ["scripts/tests"]), ["scripts/tests"])
        self.assertEqual(missing(base + pip + "      - run: python3 scripts/mutate.py\n", ["scripts/tests"]), [])
        self.assertEqual(missing(base + run, ["chains/tempo/tests"]), [])   # a folder the workflow does not run is not asked for
        self.assertEqual(missing(base + "      - run: pip install pyyaml\n" + run, ["scripts/tests"]), [])


if __name__ == "__main__":
    unittest.main()
