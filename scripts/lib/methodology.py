#!/usr/bin/env python3
"""methodologyHash tied to the code that produces a push, not to a hand-typed label (Spap's go, 2026-09-30).

Why: until 2026-09-30 every push script published keccak(METHODOLOGY_VERSION), a label frozen at "-v1" on every
chain but Robinhood. `scripts/score_history.py` found 22 composite changes published under an unchanged hash, 17 of
them fixes of our own scorer: a consumer reading the chain could not tell a scorer fix from a real change of the
target's keys. Now:

    code_digest  = sha256 over sorted "relpath:sha256(file bytes, CRLF read as LF)" lines, for every repo file reached
                   by import from the ecosystem's scorer AND its push script (the push decides which score goes to which
                   key), plus this file; tests excluded
    EVM          = keccak256(utf8("<label>:<code_digest>"))
    Solana       = sha256(utf8("<label>:<code_digest>"))      (the Solana tooling's existing convention)

Same hash => same code. Different hash => a file of that set changed: a scorer fix, but also an added target or a
refreshed snapshot kept in a scorer file. A change of the target's own keys never moves it.

A push pins the digest before scoring, refuses a real push unless that digest equals the one computed from the HEAD
commit's blobs (so the hash matches a commit), and refuses again if the files changed during the run. A dry run only
warns. Recompute from a checkout (or an archive without .git, digest only):

    python3 scripts/lib/methodology.py arbitrum-ecosystem --label authority-risk-oracle-arbitrum-ecosystem-v1
"""
import argparse
import ast
import functools
import hashlib
import os
import subprocess
import sys

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SELF = "scripts/lib/methodology.py"  # loaded by path in the push scripts, so no import statement points at it

# (scorer holding score_all(), push script). Robinhood Chain's scorer is the shared library itself.
ENTRY = {
    "robinhood-chain": ("scripts/lib/scorers.py", "scripts/update_scores.py"),
    "ethereum-l1": ("chains/ethereum-l1/scorers.py", "chains/ethereum-l1/deploy/update_scores_ethereum_l1.py"),
    "arbitrum-ecosystem": ("chains/arbitrum-ecosystem/scorers.py", "chains/arbitrum-ecosystem/deploy/push_scores.py"),
    "base-ecosystem": ("chains/base-ecosystem/scorers.py", "chains/base-ecosystem/deploy/push_scores.py"),
    "tempo": ("chains/tempo/scorers.py", "chains/tempo/deploy/push_scores.py"),
    "plasma-ecosystem": ("chains/plasma-ecosystem/scorers.py", "chains/plasma-ecosystem/deploy/push_scores.py"),
    "monad": ("chains/monad/scorers.py", "chains/monad/deploy/push_scores.py"),
    "hyperliquid": ("chains/hyperliquid/scorers.py", "chains/hyperliquid/deploy/push_scores.py"),
    "solana": ("chains/solana/scorers.py", "chains/solana/deploy/update_scores_solana.py"),
}


def _search_dirs(path, ecosystem, root):
    """The directories the scorers and push scripts put on sys.path."""
    here = os.path.dirname(path)
    chain = os.path.join(root, "chains", ecosystem)
    return [here, os.path.join(here, "scripts"), os.path.join(root, "scripts", "lib"), os.path.join(root, "scripts"),
            chain, os.path.join(chain, "scripts"), os.path.join(chain, "deploy")]


def _resolve(name, dirs):
    parts = name.split(".")
    for d in dirs:
        for cand in (os.path.join(d, *parts) + ".py", os.path.join(d, *parts, "__init__.py")):
            if os.path.isfile(cand):
                return os.path.realpath(cand)
    return None


def _is_test(rel):
    return "tests" in rel.split(os.sep)  # on the path RELATIVE to the repo: a clone living under a "tests" dir still works


def scoring_files(ecosystem, root=REPO_ROOT):
    """Repo-relative paths of every file reachable by import from the ecosystem's scorer and push script, plus this
    file, sorted, tests excluded. Raises if a root file is missing: an empty set would hash to a constant.
    ponytail: static import reading; an importlib.import_module("...") string would be missed (none on 2026-09-30),
    upgrade by also walking string arguments of import_module if one appears."""
    root = os.path.realpath(root)
    starts = [os.path.realpath(os.path.join(root, r)) for r in (*ENTRY[ecosystem], SELF)]
    missing = [s for s in starts if not os.path.isfile(s)]
    if missing:
        raise RuntimeError(f"methodology: root file(s) missing for {ecosystem}: {missing}")
    seen, todo = set(), list(starts)
    while todo:
        path = todo.pop()
        if path in seen or _is_test(os.path.relpath(path, root)):
            continue
        seen.add(path)
        with open(path, "rb") as f:
            tree = ast.parse(f.read(), filename=path)
        dirs = _search_dirs(path, ecosystem, root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names, where = [a.name for a in node.names], dirs
            elif isinstance(node, ast.ImportFrom):
                where = dirs
                if node.level:  # relative import: resolve from the package directory
                    base = os.path.dirname(path)
                    for _ in range(node.level - 1):
                        base = os.path.dirname(base)
                    where = [base]
                mod = node.module or ""
                names = ([mod] if mod else []) + [f"{mod}.{a.name}" if mod else a.name for a in node.names]
            else:
                continue
            for n in names:
                hit = _resolve(n, where)
                if hit and hit.startswith(root + os.sep):
                    todo.append(hit)
    files = sorted(os.path.relpath(p, root) for p in seen)
    if not all(os.path.relpath(s, root) in files for s in starts):
        raise RuntimeError(f"methodology: a root file of {ecosystem} was excluded, refusing a hash that ignores it")
    return files


def _norm(b):
    return b.replace(b"\r\n", b"\n")


def _digest(files, read):
    return hashlib.sha256("\n".join(f"{rel}:{hashlib.sha256(_norm(read(rel))).hexdigest()}" for rel in files).encode()).hexdigest()


def _read_worktree(root):
    def read(rel):
        with open(os.path.join(root, rel), "rb") as f:
            return f.read()
    return read


@functools.lru_cache(maxsize=None)
def code_digest(ecosystem, root=REPO_ROOT):
    """Digest of the files on disk, computed once per process: call it before scoring to pin the code that runs."""
    root = os.path.realpath(root)
    return _digest(scoring_files(ecosystem, root), _read_worktree(root))


def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, check=True).stdout


def _check_git_root(root):
    top = os.path.realpath(_git(root, "rev-parse", "--show-toplevel").decode().strip())
    if top != root:
        raise RuntimeError(f"git answers for {top}, not for {root} (a copy without .git inside another repository?)")


def head_digest(ecosystem, root=REPO_ROOT):
    """Same digest, from the HEAD commit's blobs. Raises if a file is not in HEAD or git cannot answer."""
    root = os.path.realpath(root)
    _check_git_root(root)
    return _digest(scoring_files(ecosystem, root), lambda rel: _git(root, "show", f"HEAD:{rel}"))


def evm_hash(ecosystem, label, root=REPO_ROOT):
    from web3 import Web3
    return bytes(Web3.keccak(text=f"{label}:{code_digest(ecosystem, root)}"))


def solana_hash(label, root=REPO_ROOT):
    return hashlib.sha256(f"{label}:{code_digest('solana', root)}".encode()).digest()


def head_commit(root=REPO_ROOT):
    try:
        return _git(os.path.realpath(root), "rev-parse", "HEAD").decode().strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def _differs_from_head(ecosystem, root):
    out = []
    for rel in scoring_files(ecosystem, root):
        try:
            head = _git(root, "show", f"HEAD:{rel}")
        except subprocess.CalledProcessError:
            out.append(f"{rel} (not in HEAD)")
            continue
        if _norm(head) != _norm(_read_worktree(root)(rel)):
            out.append(rel)
    return out


def require_committed(ecosystem, root=REPO_ROOT):
    """Before a real push: the pinned digest must equal the digest of the HEAD commit, so the published hash matches
    a commit. Fails closed (SystemExit) if it does not, or if git cannot answer. Warns if HEAD is not yet on
    origin/main (the commit exists only locally until the git push)."""
    root = os.path.realpath(root)
    pinned = code_digest(ecosystem, root)
    try:
        head = head_digest(ecosystem, root)
    except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
        raise SystemExit(f"methodologyHash: cannot check the scoring files of {ecosystem} against git ({e}); refusing a "
                         f"real push whose hash could match no commit.")
    if head != pinned:
        raise SystemExit(f"methodologyHash: the scoring files of {ecosystem} differ from HEAD, so the hash would match no "
                         f"commit. Commit them first, then push: {', '.join(_differs_from_head(ecosystem, root))}")
    if subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", "HEAD", "origin/main"], capture_output=True).returncode != 0:
        print(f"methodologyHash: WARNING, HEAD {head_commit(root)} is not on origin/main yet: the hash is reproducible "
              f"only once that commit is pushed to GitHub.", file=sys.stderr)
    return pinned


def assert_unchanged(ecosystem, root=REPO_ROOT):
    """Right before sending: the files on disk must still be the ones pinned before scoring."""
    root = os.path.realpath(root)
    now = _digest(scoring_files(ecosystem, root), _read_worktree(root))
    if now != code_digest(ecosystem, root):
        raise SystemExit(f"methodologyHash: scoring files of {ecosystem} changed on disk during this run; the hash would "
                         f"describe code that did not produce these scores. Rerun.")


def describe(ecosystem, label, root=REPO_ROOT):
    """One line for the push log: what the hash commits to. Never raises on git trouble (a dry run only warns)."""
    root = os.path.realpath(root)
    line = (f"methodologyHash covers {len(scoring_files(ecosystem, root))} files, code digest "
            f"{code_digest(ecosystem, root)[:16]}..., label {label}")
    try:
        same = head_digest(ecosystem, root) == code_digest(ecosystem, root)
        return line + f", commit {head_commit(root)}" + ("" if same else " -- WARNING: files differ from HEAD, this hash matches no commit")
    except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
        return line + f" -- WARNING: no git answer ({type(e).__name__}), hash not tied to a commit"


def main():
    ap = argparse.ArgumentParser(description="Recompute an ecosystem's methodologyHash from a checkout.")
    ap.add_argument("ecosystem", choices=sorted(ENTRY))
    ap.add_argument("--label", required=True, help="the push script's METHODOLOGY_VERSION")
    args = ap.parse_args()
    for rel in scoring_files(args.ecosystem):
        print(f"  {rel}")
    print(describe(args.ecosystem, args.label))
    h = solana_hash(args.label) if args.ecosystem == "solana" else evm_hash(args.ecosystem, args.label)
    print(f"methodologyHash = 0x{h.hex()}")


if __name__ == "__main__":
    sys.exit(main())
