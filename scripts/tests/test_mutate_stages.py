"""The mutation replay is faster without being less strict: a mutant is first checked by the test modules that name its file, in a failfast run, and only a mutant that passes them meets the whole suite.

What has to stay true, one test each (planted mutants on a toy repository, the real suite is not run here):
1. a mutant caught by a linked module stops at the first failing test, the rest of the linked modules is not run;
2. a survivor always runs the ENTIRE suite: every test module ran, and only then is it SURVIVED;
3. a mutant that only a module which does not name its file can see is found by the second stage (CAUGHT, by that module);
4. a hang is a TIMEOUT, an import failure is INVALID: neither is ever CAUGHT, in the first stage or in the second;
5. the verdict of every mutant is the same with the stages and without them (`--no-stages`), and the exit code too;
6. the cache of verdicts: a CAUGHT mutant whose content did not change since the last green run is not replayed; any change of what it depends on (the mutated file, what that file imports, a
   linked test module, the module that caught it, the python version, the mutation itself) or an entry older than the limit means a replay; a run with a survivor writes nothing;
   a survivor, a hang and an invalid mutant are never stored.
Standard library only, no network. The cases that start processes are skipped when the suite runs on a mutant (ARO_MUTATING)."""
import json, os, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mutate  # noqa: E402

MUTATE = os.path.join(ROOT, "scripts", "mutate.py")
HEAVY = unittest.skipIf(os.environ.get("ARO_MUTATING"), "starts processes: not repeated on each mutant")

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n"
HELPER = "def twice(x):\n    return 2 * x\n"
CALC_IMPORTING = "from helper import twice\n\n\ndef add(a, b):\n    return a + b\n\n\ndef dbl(a):\n    return twice(a)\n"
LOG = "import os\n\n\ndef mark():\n    open(os.path.join(os.environ['RDV'], __name__.split('.')[-1]), 'a').write('ran\\n')\n\n\n"   # each test leaves a trace of its module when it runs (not at import: the loader imports every module)
T_CALC = LOG + "import unittest\nfrom calc import add, sub\n\n\nclass T(unittest.TestCase):\n    def setUp(self): mark()\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n    def test_sub(self): self.assertEqual(sub(5, 3), 2)\n"
T_OTHER = LOG + "import importlib, unittest\n\n\nclass T(unittest.TestCase):\n    def setUp(self): mark()\n\n    def test_mul(self):\n        self.assertEqual(importlib.import_module('ca' + 'lc').mul(3, 4), 12)   # reaches the module without naming it\n"
T_PLAIN = LOG + "import unittest\n\n\nclass T(unittest.TestCase):\n    def setUp(self): mark()\n    def test_nothing(self): self.assertTrue(True)\n"
T_FAILS_FIRST = LOG + "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def setUp(self): mark()\n    def test_add_first(self): self.assertEqual(add(2, 3), 5)\n"
T_MARK = LOG + "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def setUp(self): mark()\n    def test_other(self): self.assertEqual(add(1, 1), 2)\n"


def mut(old, new, why="planted", file="scripts/calc.py"): return {"file": file, "old": old, "new": new, "why": why}


def toy(tmp, tests=None, calc=CALC):
    root = os.path.join(tmp, "repo"); os.makedirs(os.path.join(root, "scripts", "tests")); rdv = os.path.join(tmp, "rdv"); os.makedirs(rdv)
    files = {"scripts/calc.py": calc, "scripts/helper.py": HELPER, "scripts/tests/__init__.py": ""}
    for name, text in (tests or {"test_calc": T_CALC, "test_other": T_OTHER, "test_plain": T_PLAIN}).items(): files["scripts/tests/%s.py" % name] = text
    for rel, text in files.items():
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f: f.write(text)
    os.environ["RDV"] = rdv
    return root, rdv


def ran(rdv): return sorted(os.listdir(rdv))


class Env(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get("RDV"); self.addCleanup(lambda: os.environ.pop("RDV", None) if self.saved is None else os.environ.__setitem__("RDV", self.saved))


class Linking(Env):
    def test_only_the_modules_that_name_the_file_are_linked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp)
            self.assertEqual(mutate.linked_modules(root, "scripts/calc.py"), ["tests.test_calc"])   # test_other uses calc without naming it, test_plain does not use it
            self.assertEqual(mutate.linked_modules(root, "scripts/helper.py"), [])

    def test_a_word_inside_another_word_is_not_a_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp, tests={"test_x": "import unittest\n# calculator, recalc, calcium\nclass T(unittest.TestCase):\n    def test_y(self): pass\n"})
            self.assertEqual(mutate.linked_modules(root, "scripts/calc.py"), [])


@HEAVY
class Stages(Env):
    def staged(self, root, m, durations=None, timeout=60):
        return mutate.check(root, m, suite=mutate.staged(m["file"], durations or {}, timeout=timeout))

    def test_a_caught_mutant_stops_at_the_first_failing_linked_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, rdv = toy(tmp, tests={"test_calc": T_FAILS_FIRST, "test_calc_slowmodule": T_MARK, "test_plain": T_PLAIN})
            m = mut("a + b", "a - b", "add subtracts")
            rc, out = mutate.staged("scripts/calc.py", {"tests.test_calc": 0.1, "tests.test_calc_slowmodule": 9.0}, timeout=60)(self._mutated(root, m))
            self.assertNotEqual(rc, 0); self.assertIn("ARO-STAGE 1", out); self.assertNotIn("ARO-STAGE 2", out)
            self.assertEqual(ran(rdv), ["test_calc"], "the second linked module must not have run: the first one already failed")   # the slow module and test_plain would have left a trace

    def _mutated(self, root, m):
        p = os.path.join(root, m["file"]); src = open(p).read(); open(p, "w").write(mutate.apply(src, m["old"], m["new"])); return root

    def test_a_test_that_raises_names_its_module_as_the_catcher_like_one_that_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp)
            rc, out = mutate.staged("scripts/calc.py", {}, timeout=60)(self._mutated(root, mut("return a + b", "return a + undefined_name", "add raises")))
            self.assertEqual(mutate.classify(rc, out), "CAUGHT"); self.assertIn("ARO-CATCHER tests.test_calc", out)

    def test_a_survivor_runs_the_entire_suite_before_it_is_called_survived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, rdv = toy(tmp)
            v, _ = self.staged(root, mut("return a + b", "return a + b + 0", "same thing"))
            self.assertEqual(v, "SURVIVED"); self.assertEqual(ran(rdv), ["test_calc", "test_other", "test_plain"])   # all three modules, not only the linked one

    def test_a_mutant_only_an_unlinked_module_sees_is_caught_by_the_second_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, rdv = toy(tmp)
            rc, out = mutate.staged("scripts/calc.py", {}, timeout=60)(self._mutated(root, mut("a * b", "a + b", "mul adds")))
            self.assertEqual(mutate.classify(rc, out), "CAUGHT"); self.assertIn("ARO-STAGE 2", out); self.assertIn("ARO-CATCHER tests.test_other", out)

    def test_a_hang_is_a_timeout_in_the_first_stage_and_never_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp)
            rc, out = mutate.staged("scripts/calc.py", {}, timeout=3)(self._mutated(root, mut("return a + b", "while True: pass", "add never returns")))
            self.assertEqual(mutate.classify(rc, out), "TIMEOUT"); self.assertTrue(out.endswith("ARO-STAGE 1"), "the hang is the answer of the first stage: the whole suite is not run after it")

    def test_a_hang_in_the_second_stage_is_a_timeout_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp)
            v, _ = self.staged(root, mut("return a * b", "while True: pass", "mul never returns"), timeout=3)   # no linked module calls mul: the loop is met by test_other, in the second stage
            self.assertEqual(v, "TIMEOUT")

    def test_an_import_failure_is_invalid_in_both_stages_never_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp)
            self.assertEqual(self.staged(root, mut("def add(a, b):", "import no_such_module_anywhere\ndef add(a, b):", "cannot import"))[0], "INVALID")   # first stage: the linked module fails to import calc
            root2, _ = toy(os.path.join(tmp, "b") if os.makedirs(os.path.join(tmp, "b")) is None else tmp, tests={"test_plain": T_PLAIN, "test_other": T_OTHER})
            self.assertEqual(self.staged(root2, mut("def add(a, b):", "import no_such_module_anywhere\ndef add(a, b):", "cannot import"))[0], "INVALID")   # no linked module: the second stage meets the import failure

    def test_a_module_that_dies_on_something_else_than_an_import_error_is_invalid_never_caught(self):
        bad = mut("def add(a, b):", "x = undefined_name_zz\ndef add(a, b):", "the file raises a NameError when it loads")   # the loader of the named modules only knows ImportError: the runner dies, no test failed
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp); self.assertEqual(self.staged(root, bad)[0], "INVALID")   # first stage
            self.assertEqual(mutate.check(root, bad, suite=lambda r: mutate.run_suite(r, timeout=60))[0], "INVALID")   # no stages

    def test_the_order_is_by_known_duration_and_unknown_ones_come_first(self):
        self.assertEqual(sorted(["b", "a", "c"], key=lambda n: {"a": 5.0, "b": 1.0}.get(n, 0)), ["c", "b", "a"])   # the rule the stage uses, written once so that a change of it is seen
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = toy(tmp, tests={"test_calc": T_CALC, "test_calc_two": T_CALC.replace("test_add", "test_add2")})
            seen = []
            real = mutate.run_suite
            try:
                mutate.run_suite = lambda *a, **k: (seen.append(k.get("names")), (0, ""))[1]
                mutate.staged("scripts/calc.py", {"tests.test_calc": 5.0, "tests.test_calc_two": 1.0})(root)
            finally: mutate.run_suite = real
            self.assertEqual(seen[0], ["tests.test_calc_two", "tests.test_calc"]); self.assertEqual(seen[1], None)


@HEAVY
class SameVerdicts(Env):
    SPEC = [mut("a + b", "a - b", "add subtracts"), mut("a - b", "a + b", "sub adds"), mut("return a + b", "return a + b + 0", "same thing"), mut("a - b", "a -", "does not compile"),
            mut("absent", "x", "stale"), mut("return a - b", "while True: pass", "sub never returns"), mut("a * b", "a + b", "mul adds: only the unlinked module sees it"),
            mut("def add(a, b):", "import no_such_module_anywhere\ndef add(a, b):", "cannot import")]

    def cli(self, tmp, *extra):
        root, _ = toy(tmp); spec = os.path.join(tmp, "spec.json"); json.dump({"mutations": self.SPEC}, open(spec, "w"))
        r = subprocess.run([sys.executable, MUTATE, "--spec", spec, "--root", root, "--json", "--timeout", "4", *extra], capture_output=True, text=True, timeout=240, env=dict(os.environ, TMPDIR=tmp))
        return r.returncode, [(x["why"], x["verdict"]) for x in json.loads(r.stdout)["results"]]

    def test_the_stages_and_the_plain_replay_give_the_same_verdict_for_each_mutant(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            rc1, staged = self.cli(a); rc2, plain = self.cli(b, "--no-stages")
            self.assertEqual(staged, plain); self.assertEqual(rc1, rc2)
            self.assertEqual([v for _, v in staged], ["CAUGHT", "CAUGHT", "SURVIVED", "INVALID", "ANCHOR_MISSING", "TIMEOUT", "CAUGHT", "INVALID"])


@HEAVY
class CacheFile(Env):
    def cli(self, tmp, muts, *extra):
        root, _ = toy(tmp); spec = os.path.join(tmp, "spec.json"); json.dump({"mutations": muts}, open(spec, "w")); cache = os.path.join(tmp, "cache.json")
        r = subprocess.run([sys.executable, MUTATE, "--spec", spec, "--root", root, "--json", "--timeout", "4", "--cache", cache, *extra], capture_output=True, text=True, timeout=240, env=dict(os.environ, TMPDIR=tmp))
        return r.returncode, cache

    def test_only_a_green_run_writes_the_file_and_a_second_one_replays_nothing_that_is_cached(self):
        caught, survivor, hang = mut("a + b", "a - b", "add subtracts"), mut("return a + b", "return a + b + 0", "same thing"), mut("return a - b", "while True: pass", "sub never returns")
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2, tempfile.TemporaryDirectory() as t3, tempfile.TemporaryDirectory() as t4:
            rc, f = self.cli(t1, [caught, survivor]); self.assertEqual(rc, 1); self.assertFalse(os.path.exists(f), "a run with a survivor keeps nothing")
            rc, f = self.cli(t2, [caught, hang]); self.assertEqual(rc, 0); self.assertFalse(os.path.exists(f), "a run with a hang keeps nothing")
            rc, f = self.cli(t3, [caught]); self.assertEqual(rc, 0); self.assertEqual(len(json.load(open(f))["entries"]), 1)
            rc, f = self.cli(t4, [caught]); self.assertEqual(len(json.load(open(f))["entries"]), 1)


class Cache(Env):
    def setUp(self):
        super().setUp(); self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root, self.rdv = toy(self.tmp.name, calc=CALC_IMPORTING, tests={"test_calc": T_CALC.replace("from calc import add, sub", "from calc import add, dbl").replace("sub(5, 3), 2", "dbl(4), 8").replace("test_sub", "test_dbl"), "test_other": T_OTHER, "test_plain": T_PLAIN})
        self.m = mut("a + b", "a - b", "add subtracts"); self.path = os.path.join(self.tmp.name, "cache.json"); self.now = 1_000_000.0

    def cache(self): return mutate.Cache(self.path, now=lambda: self.now, max_age_days=28)   # the limit tested here is the one given; the default of the tool is 7 days
    def key(self, m=None, names=None):
        return mutate.cache_key(self.root, m or self.m, ["tests.test_calc"] if names is None else names)
    def stored(self, c=None, m=None, catcher="tests.test_calc"):
        c = c or self.cache(); c.put(self.key(m), catcher, self.root); c.save(); return self.cache()

    def test_an_unchanged_caught_mutant_is_a_hit(self):
        self.assertTrue(self.stored().hit(self.key(), self.root))

    def test_nothing_is_a_hit_in_an_empty_or_missing_or_broken_cache(self):
        self.assertFalse(self.cache().hit(self.key(), self.root))
        open(self.path, "w").write("{not json"); self.assertFalse(self.cache().hit(self.key(), self.root))
        open(self.path, "w").write(json.dumps({"entries": {self.key(): "not a dict"}})); self.assertFalse(self.cache().hit(self.key(), self.root))

    def edit(self, rel, old, new):
        p = os.path.join(self.root, rel); s = open(p).read(); self.assertEqual(s.count(old), 1); open(p, "w").write(s.replace(old, new))

    def test_each_thing_the_verdict_depends_on_is_part_of_the_key(self):
        c = self.stored(); k0 = self.key()
        self.edit("scripts/calc.py", "def add", "# touched\ndef add"); self.assertNotEqual(self.key(), k0); self.assertFalse(c.hit(self.key(), self.root))   # the mutated file
        self.edit("scripts/calc.py", "# touched\n", ""); self.assertEqual(self.key(), k0)
        self.edit("scripts/helper.py", "2 * x", "3 * x"); self.assertNotEqual(self.key(), k0)   # a file the mutated file imports
        self.edit("scripts/helper.py", "3 * x", "2 * x")
        self.edit("scripts/tests/test_calc.py", "assertEqual(add(2, 3), 5)", "assertEqual(add(2, 3), 5)  # weaker?"); self.assertNotEqual(self.key(), k0)   # a linked test module
        self.edit("scripts/tests/test_calc.py", "  # weaker?", "")
        self.assertNotEqual(self.key(mut("a + b", "a + a", "other mutation")), k0)   # the mutation itself
        self.assertNotEqual(self.key(names=["tests.test_calc", "tests.test_other"]), k0)   # the set of linked modules
        real = mutate.sys.version
        try: mutate.sys.version = "9.9.9 other python"; self.assertNotEqual(self.key(), k0)
        finally: mutate.sys.version = real

    def test_the_module_that_caught_the_mutant_must_be_unchanged_even_if_it_is_not_linked(self):
        c = self.stored(catcher="tests.test_other"); self.assertTrue(c.hit(self.key(), self.root))
        self.edit("scripts/tests/test_other.py", "mul(3, 4), 12", "mul(3, 4), 13"); self.assertFalse(c.hit(self.key(), self.root))   # the unlinked module that did the catching changed: replay

    def test_the_digest_of_the_whole_tree_is_part_of_the_key_when_given(self):
        t0 = mutate.tree_digest(self.root); k0 = mutate.cache_key(self.root, self.m, ["tests.test_calc"], tree=t0)
        open(os.path.join(self.root, "scripts", "caller.py"), "w").write("import calc\n")   # a caller of the mutated file: not in its closure, not a linked test, but it can decide whether a test sees the mutant
        t1 = mutate.tree_digest(self.root); self.assertNotEqual(t0, t1); self.assertEqual(self.key(), mutate.cache_key(self.root, self.m, ["tests.test_calc"]))
        self.assertNotEqual(mutate.cache_key(self.root, self.m, ["tests.test_calc"], tree=t1), k0)
        os.makedirs(os.path.join(self.root, "data")); open(os.path.join(self.root, "data", "x.json"), "w").write("{}"); self.assertNotEqual(mutate.tree_digest(self.root), t1)   # a data file too
        os.makedirs(os.path.join(self.root, "scripts", "__pycache__")); open(os.path.join(self.root, "scripts", "__pycache__", "calc.cpython-39.pyc"), "w").write("x"); t2 = mutate.tree_digest(self.root)
        open(os.path.join(self.root, "scripts", "__pycache__", "calc.cpython-39.pyc"), "w").write("y"); self.assertEqual(mutate.tree_digest(self.root), t2)   # bytecode is not content

    def test_an_entry_older_than_the_limit_is_replayed(self):
        c = self.stored(); self.now += 28 * 86400 - 1; self.assertTrue(self.cache().hit(self.key(), self.root))
        self.now += 2; self.assertFalse(self.cache().hit(self.key(), self.root))

    def test_an_entry_dated_in_the_future_is_never_a_hit_and_is_not_kept(self):
        c = self.stored(); self.now -= 3600; self.assertFalse(self.cache().hit(self.key(), self.root))   # the clock of the run is before the date of the entry
        c2 = self.cache(); c2.put(self.key(mut("a + b", "a + a")), "tests.test_calc", self.root); c2.save(); self.assertEqual(len(json.load(open(self.path))["entries"]), 1)

    def test_the_file_is_written_in_a_folder_that_does_not_exist_yet(self):
        self.path = os.path.join(self.tmp.name, "new", "folder", "cache.json"); self.stored(); self.assertTrue(self.cache().hit(self.key(), self.root))

    def test_an_expired_entry_is_dropped_from_the_file_at_the_next_green_save(self):
        self.stored(); self.now += 29 * 86400; c = self.cache(); c.put(self.key(mut("a + b", "a + a")), "tests.test_calc", self.root); c.save()
        self.assertEqual(len(json.load(open(self.path))["entries"]), 1)

    def test_a_catcher_that_is_not_a_module_of_the_repository_is_never_stored(self):
        c = self.cache(); c.put(self.key(), "unittest.loader", self.root); c.put(self.key(), None, self.root); c.save()   # an import failure reports unittest.loader, a run without failure reports nothing
        self.assertFalse(self.cache().hit(self.key(), self.root))

    def test_a_run_with_a_survivor_writes_nothing_and_a_green_one_keeps_older_entries(self):
        c = self.stored(); k = self.key()
        self.edit("scripts/helper.py", "2 * x", "5 * x"); c2 = self.cache(); c2.put(self.key(), "tests.test_calc", self.root)
        c2.save(green=False); self.assertTrue(self.cache().hit(k, self.root)); self.assertFalse(self.cache().hit(self.key(), self.root))   # the red run added nothing
        c2.save(green=True); self.assertTrue(self.cache().hit(self.key(), self.root))   # the green one adds its entry; the entry of before is still there
        self.edit("scripts/helper.py", "5 * x", "2 * x"); self.assertTrue(self.cache().hit(k, self.root))

    def test_a_closure_follows_imports_inside_functions_and_relative_ones(self):
        self.edit("scripts/calc.py", "from helper import twice\n\n\ndef add", "def add"); self.edit("scripts/calc.py", "def dbl(a):\n    return twice(a)", "def dbl(a):\n    from helper import twice as t\n    return t(a)"); k = self.key()   # the only import is now inside a function
        self.edit("scripts/helper.py", "2 * x", "7 * x"); self.assertNotEqual(self.key(), k)
        self.assertIn("scripts/helper.py", mutate.closure(self.root, "scripts/calc.py"))
        self.assertEqual(sorted(mutate.closure(self.root, "scripts/helper.py")), ["scripts/helper.py"])


@HEAVY
class Replay(Env):
    def test_a_hit_is_not_replayed_and_a_miss_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, rdv = toy(tmp); path = os.path.join(tmp, "cache.json"); muts = [mut("a + b", "a - b", "add subtracts")]
            shown = []
            def run():
                c = mutate.Cache(path); r = mutate.replay(muts, [root], 60, lambda k, n, r: shown.append(r), cache=c, durations={}); c.save(green=True); return r
            r1 = run(); self.assertEqual(r1[0]["verdict"], "CAUGHT"); self.assertNotEqual(r1[0]["detail"], "cached")
            r2 = run(); self.assertEqual((r2[0]["verdict"], r2[0]["detail"]), ("CAUGHT", "cached")); self.assertEqual(r2[0]["seconds"], 0.0)
            open(os.path.join(root, "scripts/tests/test_calc.py"), "a").write("\n# edited\n")
            r3 = run(); self.assertNotEqual(r3[0]["detail"], "cached")

    def test_with_the_tree_digest_any_file_of_the_repository_that_changes_means_a_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, rdv = toy(tmp); path = os.path.join(tmp, "cache.json"); muts = [mut("a + b", "a - b", "add subtracts")]
            def run():
                c = mutate.Cache(path, tree=mutate.tree_digest(root)); r = mutate.replay(muts, [root], 60, lambda k, n, r: None, cache=c, durations={}); c.save(green=True); return r
            run(); self.assertEqual(run()[0]["detail"], "cached")
            open(os.path.join(root, "scripts", "caller.py"), "w").write("import calc\n"); self.assertNotEqual(run()[0]["detail"], "cached")


if __name__ == "__main__":
    unittest.main()
