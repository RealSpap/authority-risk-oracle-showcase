#!/usr/bin/env python3
"""Replay the mutation checks behind the claim "the tests catch this": break the code one way at a time and see whether the suite notices.

    python3 scripts/mutate.py                                  # every mutation of scripts/tests/mutations.json, on a COPY of the repository
    python3 scripts/mutate.py --only dossier.py --json
    python3 scripts/mutate.py --in-place                       # on the files themselves (each one is restored in a `finally`)
    python3 -u scripts/mutate.py --jobs 4                      # four workers, each on its own copy of the tree; the report is the one of a sequential run

A mutation is a file, an exact piece of text that must appear once in it, its replacement, and a sentence saying what is being broken. For each one the tool:
  1. refuses it (ANCHOR_MISSING) if the text is not there exactly once: the code moved on and the mutation is stale, which is worth knowing, not guessing around;
  2. refuses it (INVALID) if the mutated file does not compile, or if the suite cannot even be imported with it: a mutant that does not run proves nothing, and counting it as "caught"
     because the suite failed is the mistake this tool exists to avoid;
  3. runs the suite on the mutant: any failing test = CAUGHT, a hang = TIMEOUT (caught by the clock), a clean pass = SURVIVED, which is a gap in the tests.
Time: the clock of a mutant is derived from the time the untouched suite took (TIMEOUT_FACTOR times it, never under TIMEOUT_FLOOR seconds), not a constant: a
suite that takes 7 s gives a mutant that loops 60 s, not 300 s. A hung mutant is killed with its whole process group, so a grandchild holding the pipes cannot hold the run.
Output: one line per mutant, printed as soon as it is known (flushed: a CI log shows the progress), and the slow mutants are written to the job summary as they happen.
Exit code 1 if a mutant survived, 2 if a mutation is stale or invalid, 0 otherwise. Standard library only.
"""
import argparse, ast, hashlib, json, os, queue, re, shutil, signal, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); DEFAULT_SPEC = os.path.join(HERE, "tests", "mutations.json")
TIMEOUT_FACTOR, TIMEOUT_FLOOR = 6.0, 60.0
IMPORT_FAILURE = ("_FailedTest", "ModuleNotFoundError", "ImportError: Failed to import test module", "SyntaxError", "IndentationError", "ARO-RUNNER-BROKEN")


def timeout_for(base_seconds, factor=TIMEOUT_FACTOR, floor=TIMEOUT_FLOOR):
    """Seconds a mutant may take: `factor` times the untouched suite, never under `floor`. A mutant that makes the code loop is the only one that reaches it."""
    return max(floor, factor * base_seconds)


def apply(src, old, new):
    """The mutated source, or None when `old` is not present exactly once."""
    return src.replace(old, new) if src.count(old) == 1 else None


def compiles(src, path="<mutant>"):
    try: compile(src, path, "exec"); return True
    except (SyntaxError, ValueError): return False


# What runs a suite: the whole of it (discovery, as `python -m unittest discover -s <tests> -t <top>`) or the named modules only, optionally stopping at the first failure. It adds to the output
# one line naming the module of the first failing test (ARO-CATCHER), and writes the seconds each module took (to order the modules of the first stage).
RUNNER = r'''
import json, sys, time, unittest
start, top, names, failfast, times = sys.argv[1:6]
sys.path.insert(0, top)
class R(unittest.TextTestResult):
    def __init__(s, *a, **k): super().__init__(*a, **k); s.sec = {}; s.t0 = 0.0; s.first = None
    def startTest(s, test): s.t0 = time.time(); super().startTest(test)
    def stopTest(s, test): m = type(test).__module__; s.sec[m] = s.sec.get(m, 0.0) + time.time() - s.t0; super().stopTest(test)
    def note(s, test):
        if s.first is None: s.first = type(test).__module__; sys.stderr.write("\nARO-CATCHER %s\n" % s.first)
    def addFailure(s, test, err): s.note(test); super().addFailure(test, err)
    def addError(s, test, err): s.note(test); super().addError(test, err)
loader = unittest.defaultTestLoader
suite = loader.loadTestsFromNames(names.split(",")) if names else loader.discover(start, top_level_dir=top)
res = unittest.TextTestRunner(resultclass=R, failfast=failfast == "1", verbosity=1).run(suite)
if times: json.dump(res.sec, open(times, "w"))
sys.exit(0 if res.wasSuccessful() else 1)
'''


def run_suite(root, test_dir="scripts/tests", top="scripts", timeout=300, names=None, failfast=False, times=None):
    """(return code, output); return code None on a timeout. `names`: dotted test modules to run instead of the whole suite; `failfast`: stop at the first failing test (a mutant that is caught needs no more).
    Stale bytecode is removed first and none is written: Python trusts a .pyc whose
    source has the same size and the same mtime in whole seconds, and a one-character mutation ("a + b" -> "a - b") made within the same
    second as the previous run is exactly that, so the suite would run the OLD code and report SURVIVED (seen on GitHub Actions, 2026-10-10)."""
    for d, dirs, _files in os.walk(root):
        if "__pycache__" in dirs: shutil.rmtree(os.path.join(d, "__pycache__"), ignore_errors=True); dirs.remove("__pycache__")
    cmd = [sys.executable, "-B", "-W", "ignore", "-c", RUNNER, os.path.join(root, test_dir), os.path.join(root, top), ",".join(names or []), "1" if failfast else "0", times or ""]
    tmp = tempfile.mkdtemp(prefix="aro-mutate-tmp-")   # its own temporary folder: the suite compares the entries of the system one before and after (test_watch_mechanisms), which two suites running at once cannot both do; removed with the run
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", cwd=root, start_new_session=True, env=dict(os.environ, ARO_MUTATING="1", TMPDIR=tmp))   # the suite knows it runs on a mutant: the test that reads the mutation list from the files stands aside (see TestMutationSpec); its own process group, so that a timeout can kill what the suite started too
        try:
            out, err = p.communicate(timeout=timeout); text = out + err
            if p.returncode != 0 and "ARO-CATCHER" not in text: text += "\nARO-RUNNER-BROKEN"   # a run that failed without a single failing test (a module raising something else than ImportError while it loads, a crash) proves nothing: INVALID, never CAUGHT
            return p.returncode, text
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): p.kill()
            try: p.communicate(timeout=10)
            except subprocess.TimeoutExpired:   # something left the group and still holds the pipes: do not wait for it, close our ends
                for f in (p.stdout, p.stderr):
                    try: f.close()
                    except Exception: pass
            return None, "timeout"
    finally: shutil.rmtree(tmp, ignore_errors=True)


def classify(rc, out):
    if rc is None: return "TIMEOUT"
    if rc == 0: return "SURVIVED"
    return "INVALID" if any(m in out for m in IMPORT_FAILURE) else "CAUGHT"


def check(root, m, suite=run_suite):
    """Verdict for one mutation dict {file, old, new, why} on the tree at root. The file is always restored."""
    path = os.path.join(root, m["file"])
    if not os.path.exists(path): return "ANCHOR_MISSING", "file not found: " + m["file"]
    src = open(path, encoding="utf-8").read(); mutated = apply(src, m["old"], m["new"])
    if mutated is None: return "ANCHOR_MISSING", "the text appears %d time(s), it must appear once" % src.count(m["old"])
    if path.endswith(".py") and not compiles(mutated, path): return "INVALID", "the mutated file does not compile"   # only Python is compiled: a workflow or a data file has no such test
    open(path, "w", encoding="utf-8").write(mutated)
    try: rc, out = suite(root)
    finally: open(path, "w", encoding="utf-8").write(src)
    v = classify(rc, out)
    return v, ("the suite cannot be imported with this mutation" if v == "INVALID" else "")


def linked_modules(root, rel, test_dir="scripts/tests", top="scripts"):
    """The test modules (dotted, as the suite imports them) whose source names the file `rel` (its name without extension, as a whole word, or the file name itself): the ones that can be expected to see a
    mutation of it. A link can be missed (a module that reaches the file without naming it): that is what the second stage is for, it is never a reason for a mutant to be called caught."""
    stem = os.path.splitext(os.path.basename(rel))[0]; pat = re.compile(r"(?<!\w)" + re.escape(stem) + r"(?!\w)"); pkg = os.path.relpath(test_dir, top).replace(os.sep, "."); d = os.path.join(root, test_dir)
    return [pkg + "." + f[:-3] for f in sorted(os.listdir(d)) if f.startswith("test") and f.endswith(".py") and pat.search(open(os.path.join(d, f), encoding="utf-8", errors="replace").read())]


def staged(rel, durations, test_dir="scripts/tests", top="scripts", timeout=300):
    """A `suite(root)` for `check`, in two stages. 1: the modules that name the mutated file, the quickest first (`durations`: seconds per module, unknown = first), stopping at the first failing test;
    that failure is the answer (CAUGHT, or INVALID if the module could not be imported), and so is a hang (TIMEOUT). 2: only a mutant that passed them all meets the ENTIRE suite (also failfast: a failure
    is a CAUGHT, a clean pass is SURVIVED, and a survivor has therefore run every test). When no module is linked, straight to stage 2. The output ends with the stage that decided (ARO-STAGE)."""
    def suite(root):
        t0 = time.time(); names = sorted(linked_modules(root, rel, test_dir, top), key=lambda n: durations.get(n, 0))   # one clock for both stages: a mutant never takes more than `timeout` in all
        if names:
            rc, out = run_suite(root, test_dir, top, timeout, names=names, failfast=True)
            if rc != 0: return rc, out + "\nARO-STAGE 1"
        rc, out = run_suite(root, test_dir, top, max(1.0, timeout - (time.time() - t0)), failfast=True)
        return rc, out + "\nARO-STAGE 2"
    return suite


def file_sha(root, rel):
    try: return hashlib.sha256(open(os.path.join(root, rel), "rb").read()).hexdigest()
    except OSError: return None


def closure(root, rel, top="scripts"):
    """{path: sha256} of the file and of every file of the repository it imports, directly or not (found in the syntax tree, so an import inside a function counts)."""
    seen, todo = {}, [rel]
    while todo:
        r = todo.pop()
        if r in seen or file_sha(root, r) is None: continue
        seen[r] = file_sha(root, r)
        if not r.endswith(".py"): continue
        try: tree = ast.parse(open(os.path.join(root, r), encoding="utf-8").read())
        except (SyntaxError, ValueError): continue
        for n in ast.walk(tree):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else ([n.module or ""] + [(n.module + "." if n.module else "") + a.name for a in n.names] if isinstance(n, ast.ImportFrom) else [])
            for mod in filter(None, mods):
                p = mod.replace(".", "/")
                todo += [c for c in (top + "/" + p + ".py", top + "/" + p + "/__init__.py", top + "/lib/" + p + ".py", os.path.dirname(r) + "/" + p + ".py") if file_sha(root, c)]
    return seen


def tree_digest(root):
    """sha256 of every file of the repository (what `copy_tree` copies), by path and content. The verdict of a mutant can depend on any of them (a caller of the mutated function, a data file a test reads, a script a test starts,
    this tool, the list of mutations): the cache is therefore valid for an identical tree only."""
    h = hashlib.sha256()
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in (".git", "__pycache__", "node_modules"))
        for f in sorted(files):
            if f.endswith(".pyc") or f == "who_controls.json": continue
            rel = os.path.relpath(os.path.join(d, f), root); h.update(("%s %s\0" % (rel, file_sha(root, rel))).encode())
    return h.hexdigest()


def environment():
    try:
        from importlib import metadata
        pkgs = sorted("%s==%s" % (d.metadata["Name"], d.version) for d in metadata.distributions())
    except Exception: pkgs = ["?"]
    return sys.version + "\n" + "\n".join(pkgs)


def cache_key(root, m, names, top="scripts", tree=None):
    """What the verdict CAUGHT of a mutation depends on: the mutation, the python and the packages, the mutated file and what it imports, the linked test modules (their sources), and, when `tree` is given, the digest of the whole tree (see `tree_digest`)."""
    h = hashlib.sha256()
    for part in (m["file"], m["old"], m["new"], environment(), tree or ""): h.update(part.encode("utf-8") + b"\0")
    for r, s in sorted(closure(root, m["file"], top).items()): h.update(("%s %s\0" % (r, s)).encode())
    for n in sorted(names): h.update(("%s %s\0" % (n, file_sha(root, top + "/" + n.replace(".", "/") + ".py"))).encode())
    return h.hexdigest()


class Cache:
    """Verdicts CAUGHT kept from the last green run, by content (the key holds the digest of the whole tree when `tree` is given, as the tool does: a finer key would miss callers, data files and scripts started by a test): {key: {at, catcher, catcher_sha}}. A hit needs the same key, an entry younger than `max_age_days`, and the module that caught the mutant
    (it may not be a linked one) unchanged. Only CAUGHT is ever stored: a survivor, a hang, an invalid or a stale mutation is always replayed. A run that is not green writes nothing. The file lives
    outside the repository (a branch or an artifact of the workflow), never in main."""
    def __init__(self, path, now=time.time, max_age_days=7, top="scripts", tree=None):
        self.path, self.now, self.max_age, self.top, self.tree, self.pending = path, now, max_age_days * 86400, top, tree, {}
        try: e = json.load(open(path, encoding="utf-8")).get("entries", {})
        except (OSError, ValueError, AttributeError): e = {}
        self.entries = {k: v for k, v in e.items() if isinstance(v, dict)} if isinstance(e, dict) else {}

    def _sha(self, root, catcher): return file_sha(root, self.top + "/" + catcher.replace(".", "/") + ".py") if isinstance(catcher, str) else None

    def hit(self, key, root):
        e = self.entries.get(key)
        if not e or not isinstance(e.get("at"), (int, float)) or self.now() - e["at"] > self.max_age: return False
        return e.get("catcher_sha") is not None and e.get("catcher_sha") == self._sha(root, e.get("catcher"))

    def put(self, key, catcher, root):
        sha = self._sha(root, catcher)
        if sha: self.pending[key] = {"at": self.now(), "catcher": catcher, "catcher_sha": sha}

    def save(self, green=True):
        if not green: return
        keep = {k: v for k, v in {**self.entries, **self.pending}.items() if isinstance(v.get("at"), (int, float)) and self.now() - v["at"] <= self.max_age}
        tmp = self.path + ".tmp"; json.dump({"version": 1, "entries": keep}, open(tmp, "w", encoding="utf-8")); os.replace(tmp, self.path)


def markdown(res, n, seconds, slow_after=None):
    """The report for a job summary: the counts first, every mutation that is not caught in a table, the slow ones in another, the caught ones folded away."""
    bad = [r for r in res if r["verdict"] not in ("CAUGHT", "TIMEOUT")]
    out = ["## Mutation replay: %d mutation(s), %d caught, %d by timeout, %d survived, %d invalid, %d stale (%.0f s)" % (len(res), n["CAUGHT"], n["TIMEOUT"], n["SURVIVED"], n["INVALID"], n["ANCHOR_MISSING"], seconds), ""]
    if bad: out += ["| Verdict | File | What was broken | Detail |", "|---|---|---|---|"] + ["| **%s** | `%s` | %s | %s |" % (r["verdict"], r["file"], r["why"], r.get("detail") or "") for r in bad] + [""]
    else: out += ["Every mutation is caught: the tests notice each of these breakages.", ""]
    slow = [r for r in res if slow_after is not None and (r["verdict"] == "TIMEOUT" or r.get("seconds", 0) >= slow_after)]
    if slow: out += ["### Slow mutants (%d took %.0f s or more, or hung)" % (len(slow), slow_after), "", "| Seconds | Verdict | File | What was broken |", "|---|---|---|---|"] + ["| %.0f | %s | `%s` | %s |" % (r.get("seconds", 0), r["verdict"], r["file"], r["why"]) for r in sorted(slow, key=lambda r: -r.get("seconds", 0))] + [""]
    out += ["<details><summary>The %d caught mutation(s)</summary>" % (len(res) - len(bad)), ""] + ["- `%s`: %s" % (r["file"], r["why"]) for r in res if r["verdict"] in ("CAUGHT", "TIMEOUT")] + ["", "</details>", ""]
    return "\n".join(out)


def append_text(path, text):
    with open(path, "a", encoding="utf-8") as f: f.write(text)


def copy_tree(root):
    dst = tempfile.mkdtemp(prefix="aro-mutate-"); shutil.copytree(root, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", "*.pyc", "who_controls.json"))
    return dst


def replay(muts, roots, timeout, show, on_slow=None, slow_after=None, durations=None, cache=None):
    """Every mutation checked, `len(roots)` at a time, each worker on its own copy of the tree. The list is in the order of `muts`, whatever the order of completion.
    `durations` (seconds per test module) turns the two stages on, None replays the whole suite for each mutant; `cache` (a Cache) skips a mutant whose verdict CAUGHT is still valid."""
    free = queue.Queue(); [free.put(r) for r in roots]; out = [None] * len(muts); lock = threading.Lock(); done = [0]

    def one(i):
        root = free.get(); box = {}
        try:
            t0 = time.time(); m = muts[i]; key = None
            if cache is not None:
                try: key = cache_key(root, m, linked_modules(root, m["file"]), tree=cache.tree)
                except (OSError, KeyError): key = None
            if key and cache.hit(key, root): v, why = "CAUGHT", "cached"
            else:
                base = staged(m["file"], durations, timeout=timeout) if durations is not None else (lambda r: run_suite(r, timeout=timeout))
                def suite(r): rc, o = base(r); box["out"] = o; return rc, o
                v, why = check(root, m, suite=suite)
                c = re.search(r"ARO-CATCHER (\S+)", box.get("out", ""))
                if key and v == "CAUGHT" and c: cache.put(key, c.group(1), root)
            dt = time.time() - t0
        finally: free.put(root)
        r = dict(muts[i], verdict=v, detail=why, seconds=round(dt, 1) if why != "cached" else 0.0); out[i] = r
        with lock:
            done[0] += 1; show(done[0], len(muts), r)
            if on_slow and slow_after is not None and (v == "TIMEOUT" or dt >= slow_after): on_slow(r)
    with ThreadPoolExecutor(max_workers=len(roots)) as ex: list(ex.map(one, range(len(muts))))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--spec", default=DEFAULT_SPEC); ap.add_argument("--root", default=os.path.dirname(HERE)); ap.add_argument("--only", help="a substring of the file name")
    ap.add_argument("--in-place", action="store_true"); ap.add_argument("--json", action="store_true"); ap.add_argument("--markdown", help="append a report to this file (the job summary of a workflow)")
    ap.add_argument("--jobs", type=int, default=1, help="mutants replayed at the same time, each worker on its own copy of the tree (default 1)")
    ap.add_argument("--timeout", type=float, help="seconds a mutant may take (default: derived from the untouched suite)"); ap.add_argument("--timeout-factor", type=float, default=TIMEOUT_FACTOR); ap.add_argument("--timeout-floor", type=float, default=TIMEOUT_FLOOR)
    ap.add_argument("--slow", type=float, help="seconds from which a mutant is called slow (default: the larger of 20 s and 3 times the untouched suite)"); ap.add_argument("--base-timeout", type=float, default=900, help="seconds the untouched suite may take")
    ap.add_argument("--no-stages", action="store_true", help="replay the whole suite for every mutant, as before (default: the test modules that name the mutated file first, then the whole suite for a mutant that passed them)")
    ap.add_argument("--cache", help="a file of verdicts CAUGHT kept from the last green run, by content (outside the repository: a branch or an artifact); written only by a green run"); ap.add_argument("--cache-days", type=float, default=7, help="age after which a kept verdict is replayed (default 7)")
    a = ap.parse_args()
    if a.jobs < 1 or (a.jobs > 1 and a.in_place): print("--jobs wants a number of 1 or more, and cannot be used with --in-place (each worker needs its own copy)"); sys.exit(2)
    muts = [m for m in json.load(open(a.spec, encoding="utf-8"))["mutations"] if not a.only or a.only in m["file"]]
    if not muts: print("no mutation to run"); sys.exit(2)
    tfile = tempfile.mkstemp(prefix="aro-mutate-times-")[1]; tb = time.time(); base = run_suite(a.root, timeout=a.base_timeout, times=tfile); base_s = time.time() - tb
    try: durations = json.load(open(tfile)) if not a.no_stages else None
    except (OSError, ValueError): durations = {}
    finally: os.unlink(tfile)
    if base[0] != 0: print("the suite does not pass on the unmodified tree, nothing to compare with:\n" + base[1][-600:]); sys.exit(2)
    timeout = a.timeout if a.timeout else timeout_for(base_s, a.timeout_factor, a.timeout_floor); slow_after = a.slow if a.slow is not None else max(20.0, 3 * base_s)
    if not a.json: print("%d mutation(s), %d worker(s); the untouched suite took %.1f s, a mutant may take %.0f s, slow from %.0f s" % (len(muts), a.jobs, base_s, timeout, slow_after), flush=True)
    roots = [a.root] if a.in_place else [copy_tree(a.root) for _ in range(a.jobs)]; t0 = time.time()

    def show(k, total, r):
        if not a.json: print("[%d/%d] %-14s %-22s %s%s (%.0f s)" % (k, total, r["verdict"], r["file"], r["why"], (" (" + r["detail"] + ")") if r["detail"] else "", r["seconds"]), flush=True)

    def on_slow(r):   # the job summary keeps what was slow even if the job is stopped before its end
        if a.markdown: append_text(a.markdown, "- slow mutant, %.0f s, %s: `%s` %s\n" % (r["seconds"], r["verdict"], r["file"], r["why"]))
    cache = Cache(a.cache, max_age_days=a.cache_days, tree=tree_digest(a.root)) if a.cache else None
    try: res = replay(muts, roots, timeout, show, on_slow, slow_after, durations=durations, cache=cache)
    finally:
        if not a.in_place:
            for r_ in roots: shutil.rmtree(r_, ignore_errors=True)
    n = {k: sum(1 for r in res if r["verdict"] == k) for k in ("CAUGHT", "TIMEOUT", "SURVIVED", "INVALID", "ANCHOR_MISSING")}
    if cache: cache.save(green=not (n["SURVIVED"] or n["INVALID"] or n["ANCHOR_MISSING"] or n["TIMEOUT"]))   # a green run only: nothing is kept from a run that found a gap, a stale mutation or a hang
    if a.markdown:
        with open(a.markdown, "a", encoding="utf-8") as f: f.write("\n" + markdown(res, n, time.time() - t0, slow_after))
    if a.json: print(json.dumps({"summary": n, "seconds": round(time.time() - t0, 1), "results": res}, indent=1))
    else: print("\n%d mutation(s): %d caught, %d by timeout, %d SURVIVED, %d invalid, %d stale (%.0f s)" % (len(res), n["CAUGHT"], n["TIMEOUT"], n["SURVIVED"], n["INVALID"], n["ANCHOR_MISSING"], time.time() - t0), flush=True)
    sys.exit(1 if n["SURVIVED"] else (2 if n["INVALID"] or n["ANCHOR_MISSING"] else 0))


if __name__ == "__main__":
    main()
