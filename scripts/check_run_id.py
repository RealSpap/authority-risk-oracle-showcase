#!/usr/bin/env python3
"""Do the published files come from the same passage of the Watch? (30/10/2026)

    python3 scripts/check_run_id.py [--watch watch]

Reads `run_id` (scripts/run_id.py: the GitHub Actions run and attempt) in the files that carry it, `latest.json`, `status.json` and `signature.json`, and compares them. The identifier of `latest.json` is
covered by the signed manifest; the other two sit outside it, so this is a check against a step that failed and left an old file in place, not against someone who rewrites files.
Exit 0: every file that carries a run_id carries the same one (and at least two do). Exit 1: two files carry different ones (they are named). Exit 3: fewer than two files carry one (a run outside
GitHub Actions, or from before this check): nothing could be compared, which is not a pass.
"""
import argparse, json, os, sys

FILES = ("latest.json", "status.json", "signature.json")


def read(watch):
    """{file: run_id} for the files that exist, parse, and carry a run_id."""
    out = {}
    for n in FILES:
        try:
            with open(os.path.join(watch, n), encoding="utf-8") as f: d = json.load(f)
        except (OSError, ValueError): continue
        if isinstance(d, dict) and isinstance(d.get("run_id"), str) and d["run_id"]: out[n] = d["run_id"]
    return out


def verdict(found):
    """(exit code, sentence)."""
    if len(found) < 2: return 3, "run_id: %d file(s) carry one (%s): nothing to compare, not a pass" % (len(found), ", ".join(sorted(found)) or "none")
    if len(set(found.values())) > 1: return 1, "run_id: the files are not from the same run: " + ", ".join("%s=%s" % (k, v) for k, v in sorted(found.items()))
    return 0, "run_id: %d files carry the same run (%s)" % (len(found), next(iter(found.values())))


def main(argv=None, out=print):
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); a = ap.parse_args(argv)
    code, text = verdict(read(a.watch)); out(text); return code


if __name__ == "__main__":
    sys.exit(main())
