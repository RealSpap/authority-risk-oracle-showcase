#!/usr/bin/env python3
"""Replay the mutation checks behind the claim "the tests catch this": break the code one way at a time and see whether the suite notices.

    python3 scripts/mutate.py                                  # every mutation of scripts/tests/mutations.json, on a COPY of the repository
    python3 scripts/mutate.py --only dossier.py --json
    python3 scripts/mutate.py --in-place                       # on the files themselves (each one is restored in a `finally`)

A mutation is a file, an exact piece of text that must appear once in it, its replacement, and a sentence saying what is being broken. For each one the tool:
  1. refuses it (ANCHOR_MISSING) if the text is not there exactly once: the code moved on and the mutation is stale, which is worth knowing, not guessing around;
  2. refuses it (INVALID) if the mutated file does not compile, or if the suite cannot even be imported with it: a mutant that does not run proves nothing, and counting it as "caught"
     because the suite failed is the mistake this tool exists to avoid;
  3. runs the suite on the mutant: any failing test = CAUGHT, a hang = TIMEOUT (caught by the clock), a clean pass = SURVIVED, which is a gap in the tests.
Exit code 1 if a mutant survived, 2 if a mutation is stale or invalid, 0 otherwise. Standard library only.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__)); DEFAULT_SPEC = os.path.join(HERE, "tests", "mutations.json")
IMPORT_FAILURE = ("_FailedTest", "ModuleNotFoundError", "ImportError: Failed to import test module", "SyntaxError", "IndentationError")


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
    try:
        r = subprocess.run([sys.executable, "-B", "-W", "ignore", "-m", "unittest", "discover", "-s", os.path.join(root, test_dir), "-t", os.path.join(root, top)], capture_output=True, text=True, timeout=timeout, cwd=root, env=dict(os.environ, ARO_MUTATING="1"))   # the suite knows it runs on a mutant: the test that reads the mutation list from the files stands aside (see TestMutationSpec)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired: return None, "timeout"


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


def markdown(res, n, seconds):
    """The report for a job summary: the counts first, every mutation that is not caught in a table, the caught ones folded away."""
    bad = [r for r in res if r["verdict"] not in ("CAUGHT", "TIMEOUT")]
    out = ["## Mutation replay: %d mutation(s), %d caught, %d by timeout, %d survived, %d invalid, %d stale (%.0f s)" % (len(res), n["CAUGHT"], n["TIMEOUT"], n["SURVIVED"], n["INVALID"], n["ANCHOR_MISSING"], seconds), ""]
    if bad: out += ["| Verdict | File | What was broken | Detail |", "|---|---|---|---|"] + ["| **%s** | `%s` | %s | %s |" % (r["verdict"], r["file"], r["why"], r.get("detail") or "") for r in bad] + [""]
    else: out += ["Every mutation is caught: the tests notice each of these breakages.", ""]
    out += ["<details><summary>The %d caught mutation(s)</summary>" % (len(res) - len(bad)), ""] + ["- `%s`: %s" % (r["file"], r["why"]) for r in res if r["verdict"] in ("CAUGHT", "TIMEOUT")] + ["", "</details>", ""]
    return "\n".join(out)


def copy_tree(root):
    dst = tempfile.mkdtemp(prefix="aro-mutate-"); shutil.copytree(root, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", "*.pyc", "who_controls.json"))
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--spec", default=DEFAULT_SPEC); ap.add_argument("--root", default=os.path.dirname(HERE)); ap.add_argument("--only", help="a substring of the file name")
    ap.add_argument("--in-place", action="store_true"); ap.add_argument("--json", action="store_true"); ap.add_argument("--markdown", help="append a report to this file (the job summary of a workflow)"); a = ap.parse_args()
    muts = [m for m in json.load(open(a.spec, encoding="utf-8"))["mutations"] if not a.only or a.only in m["file"]]
    if not muts: print("no mutation to run"); sys.exit(2)
    base = run_suite(a.root)
    if base[0] != 0: print("the suite does not pass on the unmodified tree, nothing to compare with:\n" + base[1][-600:]); sys.exit(2)
    work = a.root if a.in_place else copy_tree(a.root); res = []; t0 = time.time()
    try:
        for m in muts:
            v, why = check(work, m); res.append(dict(m, verdict=v, detail=why))
            if not a.json: print("%-14s %-22s %s%s" % (v, m["file"], m["why"], (" (" + why + ")") if why else ""))
    finally:
        if not a.in_place: shutil.rmtree(work, ignore_errors=True)
    n = {k: sum(1 for r in res if r["verdict"] == k) for k in ("CAUGHT", "TIMEOUT", "SURVIVED", "INVALID", "ANCHOR_MISSING")}
    if a.markdown:
        with open(a.markdown, "a", encoding="utf-8") as f: f.write(markdown(res, n, time.time() - t0))
    if a.json: print(json.dumps({"summary": n, "seconds": round(time.time() - t0, 1), "results": res}, indent=1))
    else: print("\n%d mutation(s): %d caught, %d by timeout, %d SURVIVED, %d invalid, %d stale (%.0f s)" % (len(res), n["CAUGHT"], n["TIMEOUT"], n["SURVIVED"], n["INVALID"], n["ANCHOR_MISSING"], time.time() - t0))
    sys.exit(1 if n["SURVIVED"] else (2 if n["INVALID"] or n["ANCHOR_MISSING"] else 0))


if __name__ == "__main__":
    main()
