#!/usr/bin/env python3
"""Shorten every root-signer address (a tracked target that also signs elsewhere stays whole: its address is the row's key) (the keys of the signer index, which itself is never published) in the files that leave with the
run: a signer's full address is the one thing this watch does not publish. Contract addresses (targets, Safes, timelocks) stay whole.

    python3 scripts/redact_signers.py --index "$RUNNER_TEMP/who_controls.json" watch/digest.md watch/safe_changes.json
"""
import argparse, glob, json, os, re, sys

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--index", required=True); ap.add_argument("--scores", default="watch/scores", help="tracked targets are never shortened, even when they also sign elsewhere"); ap.add_argument("files", nargs="*"); ap.add_argument("--allow-file", help="with --check: public contract addresses that may appear in full although the private index names them (one per line, # comments), e.g. a DAO timelock written about in a hand-made text"); ap.add_argument("--check", metavar="WATCH_DIR", help="redact nothing: scan every published file under this folder and exit 1 if one still names a signer address (a detective control, fail closed)"); a = ap.parse_args()
    if not a.check and not a.files: ap.error("files are required unless --check is given")
    signers = {k.lower() for k in json.load(open(a.index))} if os.path.exists(a.index) else set()
    if not signers: print("redact: no signer index this run; the contract whitelist alone decides")
    if a.check and not signers:
        # the scan compares files to the private index: without it there is nothing to compare, and "0 files name a signer" would be a reassurance the scan did not earn
        print("::warning::redact check NOT RUN: no signer index this run (the who_controls step failed or timed out); the files of the redaction list were redacted strictly, the others were not scanned")
        print("redact check: not run (no signer index)")
        sys.exit(0)
    # contracts are never shortened: the tracked targets, the watched timelocks, the Safes themselves
    keep = set()
    for f in glob.glob(os.path.join(a.scores, "*.json")):
        for t in json.load(open(f)).get("targets", []): keep.add(str(t["target"]).lower())
    wd = os.path.dirname(a.scores.rstrip("/")) or "watch"
    for name, fields in (("pending_ops.json", ("address", "target")), ("safe_changes.json", ("safes", "address", "safe"))):
        p = os.path.join(wd, name)
        if os.path.exists(p):
            for m in re.finditer(r'"(?:address|target|safe)": ?"(0x[0-9a-fA-F]{40})"', open(p).read()): keep.add(m.group(1).lower())
            for m in re.finditer(r'"safes": ?\[([^\]]*)\]', open(p).read()):
                for a2 in re.findall(r"0x[0-9a-fA-F]{40}", m.group(1)): keep.add(a2.lower())
    signers -= keep
    if a.check:
        # since 2026-10-10: the redaction list is written by hand, and a new published file that names a Safe or a role holder was left out of it once (side_roles.json: 11 of 51
        # addresses were in the signer index). This scan reads EVERYTHING the run publishes, whatever its name, so that an omission stops the commit instead of reaching the public repository.
        import fnmatch
        gi = os.path.join(a.check, ".gitignore"); pats = [l.strip() for l in open(gi) if l.strip() and not l.startswith("#")] if os.path.exists(gi) else []
        allow = {m.group(0).lower() for l in (open(a.allow_file) if a.allow_file and os.path.exists(a.allow_file) else []) if not l.lstrip().startswith("#") for m in re.finditer(r"0x[0-9a-fA-F]{40}", l)}
        bad = []
        for root, _d, fs in os.walk(a.check):
            _d[:] = [d for d in _d if d != ".git"]   # the branch clone's own git folder is not published content
            for f in sorted(fs):
                if not f.endswith((".json", ".jsonl", ".md", ".xml", ".ics", ".csv", ".html", ".js", ".svg", ".webmanifest")) or any(fnmatch.fnmatch(f, q) for q in pats): continue   # job logs and the files the repository ignores are not published
                path = os.path.join(root, f)
                try: t = open(path, encoding="utf-8").read()
                except (OSError, UnicodeDecodeError): continue
                hits = {m.group(0).lower() for m in re.finditer(r"(?<![0-9a-zA-Z])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])", t)} & (signers - allow)
                if hits: bad.append((path, len(hits)))
        for path, k in bad: print("LEAK: %s names %d signer address(es) of the private index in full" % (path, k))
        print("redact check: %d published file(s) name a signer address in full" % len(bad))
        sys.exit(1 if bad else 0)
    n = 0
    for f in a.files:
        if not os.path.exists(f): continue
        t = open(f).read()
        strict = os.path.basename(f) in ("digest.md", "safe_changes.json") or not signers   # no signer index this run: every file is redacted by the contract whitelist alone   # there, every address that is not a known contract is a person's key
        def short(m):
            nonlocal n; s = m.group(0)
            if s.lower() in signers or (strict and s.lower() not in keep): n += 1; return s[:6] + "…" + s[-4:]
            return s
        t2 = re.sub(r"(?<![0-9a-zA-Z])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])", short, t)   # bounded: a 66-character hash is not an address
        if strict:   # Squads members (base58) on the lines that name them
            def short58(m):
                nonlocal n; n += 1; return m.group(1) + m.group(2)[:4] + "…" + m.group(2)[-4:]
            t2 = re.sub(r"(member (?:added|removed)[^\n]*?)\b([1-9A-HJ-NP-Za-km-z]{32,44})\b", short58, t2)
        if t2 != t: open(f, "w").write(t2)
    print(f"redact: {n} signer address(es) shortened in {len(a.files)} file(s)")

if __name__ == "__main__":
    main()
