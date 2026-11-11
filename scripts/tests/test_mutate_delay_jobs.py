"""The mutation replay has to finish in the time the workflow gives it, and to say what it is doing while it runs.

On 2026-11-10 the weekly replay was cancelled after exactly its 150 minutes, in the step that replays 425 mutants one after the other, with an empty log. The cause is not established.
Two things could have contributed, and are corrected here: a mutant that makes the code loop waited a fixed 300 s whatever the suite takes (the run of the same day took about 7 s per mutant on average,
which is not the time of the untouched suite), and nothing was printed until the end (standard output is buffered under CI), so the next run can say what happened.
1. the clock of a mutant is derived from the time of the untouched suite, not a constant;
2. one line per mutant is printed as soon as it is known (a reader sees the progress while the process runs), and the slow mutants reach the job summary;
3. `--jobs N` replays N mutants at once, each worker on its own copy of the tree: same report, same exit code as a sequence (checked on six planted mutants);
4. a mutant that hangs is a TIMEOUT, it does not block the others, and a process it started does not outlive it (the kill takes the whole process group: a looping
   child left behind could keep a CPU of the runner busy for every mutant that follows);
5. two suites running at the same time do not share the temporary folder: each run of the suite has its own, removed afterwards (a test of the repository compares the entries of that folder before and
   after, and fails when another suite is creating and removing entries in it at the same moment: a mutant that survives would then be counted as caught).
The cases that start processes and wait for a hang are skipped when the suite itself runs on a mutant (ARO_MUTATING): they would add seconds to each of the 425 runs.
Standard library only, no network."""
import json, os, select, subprocess, sys, tempfile, threading, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mutate  # noqa: E402

MUTATE = os.path.join(ROOT, "scripts", "mutate.py")
CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
TEST = ("import unittest\nfrom calc import add, sub\n\n\nclass T(unittest.TestCase):\n"
        "    def test_add(self): self.assertEqual(add(2, 3), 5)\n    def test_sub(self): self.assertEqual(sub(5, 3), 2)\n")
HEAVY = unittest.skipIf(os.environ.get("ARO_MUTATING"), "starts processes and waits for a hang: not repeated on each mutant")


def mut(old, new, why="planted"): return {"file": "scripts/calc.py", "old": old, "new": new, "why": why}


SIX = [mut("a + b", "a - b", "add subtracts"), mut("a - b", "a + b", "sub adds"), mut("a + b", "b + a", "same thing, swapped"),
       mut("a - b", "a -", "does not compile"), mut("absent", "x", "stale"), mut("return a - b", "while True: pass", "sub never returns")]
BEAT = "import os, sys, time\nwhile True:\n    open(sys.argv[1], 'w').write('%d %f' % (os.getpid(), time.time())); time.sleep(0.2)"


def grandchild(heartbeat):
    """A mutant that loops AND starts a child that writes a heartbeat file until it is killed."""
    return mut("return a - b", "import subprocess, sys\n    subprocess.Popen([sys.executable, '-c', %r, %r])\n    while True: pass" % (BEAT, heartbeat), "loops and leaves a child running")


def toy(tmp):
    root = os.path.join(tmp, "repo"); os.makedirs(os.path.join(root, "scripts", "tests"))
    for rel, text in (("scripts/calc.py", CALC), ("scripts/tests/__init__.py", ""), ("scripts/tests/test_calc.py", TEST)):
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f: f.write(text)
    return root


def spec(tmp, muts):
    p = os.path.join(tmp, "spec.json")
    with open(p, "w", encoding="utf-8") as f: json.dump({"mutations": muts}, f)
    return p


def run(tmp, muts, *extra, timeout=60):
    root = toy(tmp) if not os.path.isdir(os.path.join(tmp, "repo")) else os.path.join(tmp, "repo")
    t0 = time.time(); r = subprocess.run([sys.executable, MUTATE, "--spec", spec(tmp, muts), "--root", root, *extra], capture_output=True, text=True, timeout=timeout, env=dict(os.environ, TMPDIR=tmp))   # its copies of the tree go to the folder of the test and disappear with it
    return r.returncode, r.stdout, r.stderr, time.time() - t0, root


SUITE_TMP = """import os, shutil, tempfile, time, unittest


class T(unittest.TestCase):
    def test_the_temporary_folder_is_mine(self):   # what test_watch_mechanisms does with the aro-demo-* entries of the temporary folder: look at it, create in it, look again
        d = tempfile.gettempdir(); mine = tempfile.mkdtemp(prefix="aro-demo-")
        try:
            open(os.path.join(os.environ["RDV"], str(os.getpid())), "w").close(); t0 = time.time()
            while len(os.listdir(os.environ["RDV"])) < 2 and time.time() - t0 < 8: time.sleep(0.05)   # both suites are alive here
            self.assertEqual(len(os.listdir(os.environ["RDV"])), 2, "the other suite never started")
            self.assertEqual([n for n in os.listdir(d) if n.startswith("aro-demo-")], [os.path.basename(mine)])
        finally: shutil.rmtree(mine, ignore_errors=True)
"""


class TestMutateDelayAndJobs(unittest.TestCase):
    def test_two_suites_at_the_same_time_do_not_share_the_temporary_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots, rdv, res = [], os.path.join(tmp, "rdv"), [None, None]; os.makedirs(rdv)
            for k in (0, 1):
                roots.append(toy(os.path.join(tmp, str(k)))) if os.makedirs(os.path.join(tmp, str(k))) is None else None
                with open(os.path.join(roots[k], "scripts", "tests", "test_tmp.py"), "w", encoding="utf-8") as f: f.write(SUITE_TMP)
            old = os.environ.get("RDV"); os.environ["RDV"] = rdv
            try:
                ts = [threading.Thread(target=lambda i=i: res.__setitem__(i, mutate.run_suite(roots[i], timeout=60))) for i in (0, 1)]
                [x.start() for x in ts]; [x.join() for x in ts]
            finally:
                if old is None: os.environ.pop("RDV", None)
                else: os.environ["RDV"] = old
            self.assertEqual([r[0] for r in res], [0, 0], [r[1][-300:] for r in res])   # one folder for both: each sees the entry of the other and fails

    def test_the_clock_of_a_mutant_is_derived_from_the_untouched_suite(self):
        self.assertEqual(mutate.timeout_for(7.0), 60.0)       # the runner: 7 s per suite, a looping mutant waits 60 s, not 300
        self.assertEqual(mutate.timeout_for(30.0), 180.0)     # a slower suite gets a longer clock
        self.assertEqual(mutate.timeout_for(0.2, 6, 2), 2.0)  # the floor
        self.assertEqual(mutate.timeout_for(10, 6, 2), 60.0)
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err, _dt, _root = run(tmp, [SIX[0]], "--timeout-factor", "1", "--timeout-floor", "3")
            self.assertEqual(code, 0, err); self.assertIn("a mutant may take 3 s", out)
            code, out, err, _dt, _root = run(tmp, [SIX[0]], "--timeout", "7")
            self.assertIn("a mutant may take 7 s", out)

    def test_the_markdown_report_has_a_table_of_the_slow_mutants(self):
        res = [{"verdict": "CAUGHT", "file": "scripts/a.py", "why": "fast one", "detail": "", "seconds": 7.0},
               {"verdict": "CAUGHT", "file": "scripts/b.py", "why": "slow one", "detail": "", "seconds": 45.0},
               {"verdict": "TIMEOUT", "file": "scripts/c.py", "why": "hung one", "detail": "", "seconds": 1.0}]   # a hung mutant is listed even when its clock was short
        n = {"CAUGHT": 2, "TIMEOUT": 1, "SURVIVED": 0, "INVALID": 0, "ANCHOR_MISSING": 0}
        md = mutate.markdown(res, n, 120.0, slow_after=20.0)
        self.assertIn("Slow mutants (2", md); self.assertIn("slow one", md); self.assertIn("hung one", md)
        self.assertNotIn("| 7 |", md)   # the fast one is not in the table
        self.assertNotIn("Slow mutants", mutate.markdown(res, n, 120.0))   # the old call keeps its old report

    def test_jobs_cannot_be_combined_with_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err, _dt, _root = run(tmp, [SIX[0]], "--jobs", "2", "--in-place")
            self.assertEqual(code, 2); self.assertIn("--in-place", out)

    @HEAVY
    def test_a_line_per_mutant_is_printed_while_the_process_runs_and_the_slow_one_reaches_the_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = toy(tmp); md = os.path.join(tmp, "summary.md")
            p = subprocess.Popen([sys.executable, MUTATE, "--spec", spec(tmp, [SIX[0], SIX[5]]), "--root", root, "--timeout", "3", "--slow", "1", "--markdown", md],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ, TMPDIR=tmp))   # no -u: the tool itself has to flush; killed below, its copies of the tree are removed with the folder of the test
            try:
                seen, t0 = "", time.time()
                while time.time() - t0 < 2.5 and "[1/2]" not in seen:
                    if select.select([p.stdout], [], [], 0.2)[0]: seen += p.stdout.readline()
                running = p.poll() is None   # the hung mutant is still being waited for
                self.assertIn("[1/2]", seen, "no progress line while the process runs")
                self.assertTrue(running, "the first line only came with the end of the process")
            finally:
                p.kill(); p.wait(); p.stdout.close(); p.stderr.close()
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "summary.md")
            code, out, err, _dt, _root = run(tmp, [SIX[0], SIX[5]], "--timeout", "3", "--slow", "1", "--markdown", md)
            text = open(md, encoding="utf-8").read()
            self.assertIn("slow mutant", text); self.assertIn("Slow mutants (1", text); self.assertIn("sub never returns", text)

    @HEAVY
    def test_jobs_give_the_same_report_and_exit_code_as_a_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = run(tmp, SIX, "--json", "--timeout", "3")
        with tempfile.TemporaryDirectory() as tmp:
            b = run(tmp, SIX, "--json", "--timeout", "3", "--jobs", "3")
            self.assertEqual(open(os.path.join(b[4], "scripts", "calc.py")).read(), CALC)   # the tree given is not touched
        self.assertEqual((a[0], b[0]), (1, 1), (a[2], b[2]))   # a mutant survived: exit 1 in both
        ja, jb = json.loads(a[1]), json.loads(b[1])
        key = lambda d: [(r["file"], r["old"], r["why"], r["verdict"], r["detail"]) for r in d["results"]]
        self.assertEqual(key(ja), key(jb))                      # same order as the spec, same verdicts
        self.assertEqual(ja["summary"], jb["summary"])
        self.assertEqual([r["verdict"] for r in ja["results"]], ["CAUGHT", "CAUGHT", "SURVIVED", "INVALID", "ANCHOR_MISSING", "TIMEOUT"])

    @HEAVY
    def test_a_hung_mutant_is_a_timeout_it_does_not_hold_the_others_and_its_children_do_not_outlive_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            hb = os.path.join(tmp, "heartbeat")
            try:
                code, out, err, dt, _root = run(tmp, [grandchild(hb), SIX[0], SIX[1]], "--json", "--timeout", "3", "--jobs", "2", timeout=40)
                d = json.loads(out)
                self.assertEqual([r["verdict"] for r in d["results"]], ["TIMEOUT", "CAUGHT", "CAUGHT"])
                self.assertLess(dt, 15)
                self.assertTrue(os.path.exists(hb), "the child never started: the case proves nothing")
                before = os.path.getmtime(hb); time.sleep(1.0)
                self.assertEqual(before, os.path.getmtime(hb), "a process started by the mutant is still running after its TIMEOUT")
            finally:
                try: os.kill(int(open(hb).read().split()[0]), 9)   # whatever happens, do not leave it running
                except (OSError, ValueError, IndexError): pass


if __name__ == "__main__":
    unittest.main()
