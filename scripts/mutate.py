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
import argparse, json, os, queue, shutil, signal, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); DEFAULT_SPEC = os.path.join(HERE, "tests", "mutations.json")
TIMEOUT_FACTOR, TIMEOUT_FLOOR = 6.0, 60.0
IMPORT_FAILURE = ("_FailedTest", "ModuleNotFoundError", "ImportError: Failed to import test module", "SyntaxError", "IndentationError")


def timeout_for(base_seconds, factor=TIMEOUT_FACTOR, floor=TIMEOUT_FLOOR):
    """Seconds a mutant may take: `factor` times the untouched suite, never under `floor`. A mutant that makes the code loop is the only one that reaches it."""
    return max(floor, factor * base_seconds)


def apply(src, old, new):
    """The mutated source, or None when `old` is not present exactly once."""
    return src.replace(old, new) if src.count(old) == 1 else None


def compiles(src, path="<mutant>"):
    try: compile(src, path, "exec"); return True
    except (SyntaxError, ValueError): return False


def run_suite(root, test_dir="scripts/tests", top="scripts", timeout=300):
    """(return code, output); return code None on a timeout. Stale bytecode is removed first and none is written: Python trusts a .pyc whose
    source has the same size and the same mtime in whole seconds, and a one-character mutation ("a + b" -> "a - b") made within the same
    second as the previous run is exactly that, so the suite would run the OLD code and report SURVIVED (seen on GitHub Actions, 2026-10-10)."""
    for d, dirs, _files in os.walk(root):
        if "__pycache__" in dirs: shutil.rmtree(os.path.join(d, "__pycache__"), ignore_errors=True); dirs.remove("__pycache__")
    cmd = [sys.executable, "-B", "-W", "ignore", "-m", "unittest", "discover", "-s", os.path.join(root, test_dir), "-t", os.path.join(root, top)]
    tmp = tempfile.mkdtemp(prefix="aro-mutate-tmp-")   # its own temporary folder: the suite compares the entries of the system one before and after (test_watch_mechanisms), which two suites running at once cannot both do; removed with the run
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", cwd=root, start_new_session=True, env=dict(os.environ, ARO_MUTATING="1", TMPDIR=tmp))   # the suite knows it runs on a mutant: the test that reads the mutation list from the files stands aside (see TestMutationSpec); its own process group, so that a timeout can kill what the suite started too
        try:
            out, err = p.communicate(timeout=timeout)
            return p.returncode, out + err
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


def replay(muts, roots, timeout, show, on_slow=None, slow_after=None):
    """Every mutation checked, `len(roots)` at a time, each worker on its own copy of the tree. The list is in the order of `muts`, whatever the order of completion."""
    free = queue.Queue(); [free.put(r) for r in roots]; out = [None] * len(muts); lock = threading.Lock(); done = [0]

    def one(i):
        root = free.get()
        try: t0 = time.time(); v, why = check(root, muts[i], suite=lambda r: run_suite(r, timeout=timeout)); dt = time.time() - t0
        finally: free.put(root)
        r = dict(muts[i], verdict=v, detail=why, seconds=round(dt, 1)); out[i] = r
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
    a = ap.parse_args()
    if a.jobs < 1 or (a.jobs > 1 and a.in_place): print("--jobs wants a number of 1 or more, and cannot be used with --in-place (each worker needs its own copy)"); sys.exit(2)
    muts = [m for m in json.load(open(a.spec, encoding="utf-8"))["mutations"] if not a.only or a.only in m["file"]]
    if not muts: print("no mutation to run"); sys.exit(2)
    tb = time.time(); base = run_suite(a.root, timeout=a.base_timeout); base_s = time.time() - tb
    if base[0] != 0: print("the suite does not pass on the unmodified tree, nothing to compare with:\n" + base[1][-600:]); sys.exit(2)
    timeout = a.timeout if a.timeout else timeout_for(base_s, a.timeout_factor, a.timeout_floor); slow_after = a.slow if a.slow is not None else max(20.0, 3 * base_s)
    if not a.json: print("%d mutation(s), %d worker(s); the untouched suite took %.1f s, a mutant may take %.0f s, slow from %.0f s" % (len(muts), a.jobs, base_s, timeout, slow_after), flush=True)
    roots = [a.root] if a.in_place else [copy_tree(a.root) for _ in range(a.jobs)]; t0 = time.time()

    def show(k, total, r):
        if not a.json: print("[%d/%d] %-14s %-22s %s%s (%.0f s)" % (k, total, r["verdict"], r["file"], r["why"], (" (" + r["detail"] + ")") if r["detail"] else "", r["seconds"]), flush=True)

    def on_slow(r):   # the job summary keeps what was slow even if the job is stopped before its end
        if a.markdown: append_text(a.markdown, "- slow mutant, %.0f s, %s: `%s` %s\n" % (r["seconds"], r["verdict"], r["file"], r["why"]))
    try: res = replay(muts, roots, timeout, show, on_slow, slow_after)
    finally:
        if not a.in_place:
            for r_ in roots: shutil.rmtree(r_, ignore_errors=True)
    n = {k: sum(1 for r in res if r["verdict"] == k) for k in ("CAUGHT", "TIMEOUT", "SURVIVED", "INVALID", "ANCHOR_MISSING")}
    if a.markdown:
        with open(a.markdown, "a", encoding="utf-8") as f: f.write("\n" + markdown(res, n, time.time() - t0, slow_after))
    if a.json: print(json.dumps({"summary": n, "seconds": round(time.time() - t0, 1), "results": res}, indent=1))
    else: print("\n%d mutation(s): %d caught, %d by timeout, %d SURVIVED, %d invalid, %d stale (%.0f s)" % (len(res), n["CAUGHT"], n["TIMEOUT"], n["SURVIVED"], n["INVALID"], n["ANCHOR_MISSING"], time.time() - t0), flush=True)
    sys.exit(1 if n["SURVIVED"] else (2 if n["INVALID"] or n["ANCHOR_MISSING"] else 0))


if __name__ == "__main__":
    main()
