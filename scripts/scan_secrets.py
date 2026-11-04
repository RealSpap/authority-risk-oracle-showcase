#!/usr/bin/env python3
"""A scan of the files of the repository for things that must never be committed, run by the workflow `secret-scan.yml` on every push and pull request (30/10/2026).

    python3 scripts/scan_secrets.py [--root .]      # exit 0: nothing found; exit 1: at least one finding (file:line and the kind, never the value)

It looks for the shapes of secrets that are public knowledge: a private-key header, a GitHub token, an AWS access key id, a Slack token, a Google API key, a secret API key with the `sk-` prefix, and a 64-character hexadecimal
value written next to a word such as key, seed, secret or private. It does NOT know the names, e-mail addresses or private paths of the owner: those patterns are not written in a public file and
live in the owner's own pre-push guard. A line that ends with `# pragma: allowlist secret` is skipped (a public key or a test vector written on purpose). Standard library only; reads files, writes nothing.
"""
import argparse, os, re, subprocess, sys

PATTERNS = (
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("secret API key (sk- prefix)", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("hexadecimal secret", re.compile(r"(?i)\b(?:private[_ -]?key|secret|seed|signing[_ -]?key|mnemonic)\b[^\n]{0,24}?['\"=: ]\s*['\"]?(?:0x)?[0-9a-f]{64}\b")),
)
ALLOW = "pragma: allowlist secret"
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".zip", ".gz", ".tgz", ".whl", ".pyc")


def files(root):
    """The files git tracks, or every file under root when there is no git."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, timeout=60, check=True).stdout.decode("utf-8", "replace")
        return [os.path.join(root, f) for f in out.split("\0") if f]
    except (OSError, subprocess.SubprocessError):
        return [os.path.join(b, n) for b, d, ns in os.walk(root) if ".git" not in b.split(os.sep) for n in ns]


def scan(root):
    found = []
    for path in files(root):
        if path.lower().endswith(SKIP_SUFFIX) or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if ALLOW in line:
                        continue
                    for kind, rx in PATTERNS:
                        if rx.search(line):
                            found.append((os.path.relpath(path, root), n, kind))
        except OSError:
            continue
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    found = scan(a.root)
    for rel, n, kind in found:
        print("SECRET? %s:%d: %s" % (rel, n, kind))
    print("%d finding(s) in %s" % (len(found), os.path.abspath(a.root)) if found else "no secret-shaped value found")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
