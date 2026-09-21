#!/usr/bin/env python3
"""Cross-ecosystem scorer schema/consistency validator.

Added 2026-09-17 after two real bugs were found only by manual audit in the
same session: `crossExposureScore` silently absent from two ecosystems'
return dicts (not defaulted, just missing -- would have KeyError'd or
produced a malformed on-chain tuple the first time either ecosystem's
scores were actually pushed), and a deploy script silently discarding a
real computed value behind a stale hardcoded constant. Neither needed a
live chain re-derivation to catch -- both are exactly the kind of thing a
mechanical schema check finds immediately. This script is that check,
covering every ecosystem's `score_all()` output at once, so this class of
bug doesn't need a fresh manual audit to be caught again.

This does NOT re-verify that any score is factually correct (that's what
each ecosystem's own dry-run scripts, cross-RPC checks and live re-reads
are for) -- it only checks that every returned entry has the shape every
downstream consumer (an ABI-encoded on-chain tuple, `api/scores.json`,
this project's own cross-ecosystem tooling) already assumes.

EACH ECOSYSTEM RUNS IN ITS OWN SUBPROCESS, not imported in-process. Caught
during this script's own first real run, not assumed: several ecosystems'
`scorers.py` import a same-named sibling module via a bare `import` relying
on a `sys.path` insert (Hyperliquid and Tempo both do `import
methodology_test`, pointing at two DIFFERENT files) -- loading two such
ecosystems into the same Python process makes the second one silently pick
up the FIRST one's already-cached module under that name. This produced a
real false "PASS" the first time this script tried to import in-process:
Tempo's score_all() silently returned zero entries (its own error path
caught the resulting AttributeError and printed a warning to stderr, not a
crash), and a naive checker would have reported that ecosystem clean.
Subprocess isolation is the fix: no import cache is shared between
ecosystems, so this class of collision cannot happen no matter how many
same-named modules any ecosystem's scripts/ directory uses internally.

Usage:
    python3 scripts/validate_all_scorers.py             # run every ecosystem
    python3 scripts/validate_all_scorers.py --ecosystem solana
    python3 scripts/validate_all_scorers.py --skip zcash,tempo   # slow ones
"""
import argparse
import json
import math
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON = sys.executable

# Each entry: (import statement(s) to reach a bound score_all callable named
# `_call`, executed inside a fresh subprocess with REPO_ROOT as cwd).
ECOSYSTEMS = {
    "robinhood-chain": """
import sys, os
sys.path.insert(0, os.path.join('scripts', 'lib'))
sys.path.insert(0, 'scripts')
from web3_utils import get_w3
from lib.scorers import score_all
w3 = get_w3('https://rpc.mainnet.chain.robinhood.com')
def _call(): return score_all(w3)
""",
    "ethereum-l1": """
import sys, os
sys.path.insert(0, os.path.join('scripts', 'lib'))
sys.path.insert(0, os.path.join('chains', 'ethereum-l1'))
from web3_utils import get_w3
from scorers import score_all
w3 = get_w3('https://ethereum-rpc.publicnode.com')
def _call(): return score_all(w3)
""",
    "arbitrum": """
import sys, os
sys.path.insert(0, os.path.join('scripts', 'lib'))
sys.path.insert(0, os.path.join('chains', 'arbitrum-ecosystem'))
from web3_utils import get_w3
from scorers import score_all
w3 = get_w3('https://arb1.arbitrum.io/rpc')
def _call(): return score_all(w3)
""",
    "base": """
import sys, os
sys.path.insert(0, os.path.join('scripts', 'lib'))
sys.path.insert(0, os.path.join('chains', 'base-ecosystem'))
from web3_utils import get_w3
from scorers import score_all
w3 = get_w3('https://mainnet.base.org')
def _call(): return score_all(w3)
""",
    "solana": """
import sys, os
sys.path.insert(0, 'chains/solana')
from scorers import score_all
def _call(): return score_all('https://api.mainnet-beta.solana.com')
""",
    "hyperliquid": """
import sys, os
sys.path.insert(0, 'chains/hyperliquid')
from scorers import score_all
def _call(): return score_all()
""",
    "tempo": """
import sys, os
sys.path.insert(0, 'chains/tempo')
from scorers import score_all
def _call(): return score_all()
""",
    "zcash": """
import sys, os
sys.path.insert(0, 'chains/zcash')
from scorers import score_all
def _call(): return score_all()
""",
    "plasma": """
import sys, os
sys.path.insert(0, os.path.join('scripts', 'lib'))
sys.path.insert(0, os.path.join('chains', 'plasma-ecosystem'))
from web3_utils import get_w3
from scorers import score_all
w3 = get_w3('https://rpc.plasma.to')
def _call(): return score_all(w3)
""",
    # ADDED 2026-09-19: Monad (a 9th ecosystem, 9 targets by this date) was never
    # registered here after it shipped, so its score_all() output had never been
    # schema-checked by this tool at all -- found while investigating an unrelated
    # false FAIL (Tempo's timeout) and noticing the "8 ecosystem(s)" total was one
    # short of the 9 this project actually tracks.
    "monad": """
import sys, os
sys.path.insert(0, os.path.join('scripts', 'lib'))
sys.path.insert(0, os.path.join('chains', 'monad'))
from web3_utils import get_w3
from scorers import score_all
w3 = get_w3('https://rpc.monad.xyz')
def _call(): return score_all(w3)
""",
}

_RUNNER_TAIL = """
import json
try:
    results = _call()
    print("===AROVALIDATOR-JSON-START===")
    print(json.dumps({"ok": True, "results": results}, default=str))
    print("===AROVALIDATOR-JSON-END===")
except Exception as e:
    print("===AROVALIDATOR-JSON-START===")
    print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
    print("===AROVALIDATOR-JSON-END===")
"""

REQUIRED_SCORE_FIELDS = (
    "adminKeyScore", "multisigScore", "timelockScore",
    "oracleAuthorityScore", "crossExposureScore", "compositeScore",
)


def _composite(admin, multisig, timelock):
    # Exact integer arithmetic, same as every scorer's _composite (the float form is one low for 2054 triples).
    return (4 * admin + 3 * multisig + 3 * timelock + 5) // 10


def validate_entry(entry: dict) -> list:
    """Returns a list of problem strings; empty means the entry is clean."""
    problems = []

    for field in ("target", "label"):
        if not entry.get(field) or not isinstance(entry[field], str):
            problems.append(f"missing or non-string '{field}'")

    for field in REQUIRED_SCORE_FIELDS:
        if field not in entry:
            problems.append(f"MISSING required field '{field}'")
            continue
        v = entry[field]
        if v is None:
            continue  # an explicit None (e.g. Zcash's degrade path) is a disclosed "unverified this run", not a schema violation
        if not isinstance(v, int) or isinstance(v, bool):
            problems.append(f"'{field}' = {v!r} is not an int")
        elif not (0 <= v <= 100):
            problems.append(f"'{field}' = {v} out of [0,100] range")

    if all(isinstance(entry.get(f), int) and not isinstance(entry.get(f), bool) for f in ("adminKeyScore", "multisigScore", "timelockScore", "compositeScore")):
        expected = _composite(entry["adminKeyScore"], entry["multisigScore"], entry["timelockScore"])
        if entry["compositeScore"] != expected:
            problems.append(f"compositeScore={entry['compositeScore']} does not match floor(0.4*admin+0.3*multisig+0.3*timelock+0.5)={expected}")

    leaked = [k for k in entry if k.startswith("_")]
    if leaked:
        problems.append(f"internal field(s) leaked into final output: {leaked}")

    if "notes" in entry and not isinstance(entry["notes"], (list, dict)):
        problems.append(f"'notes' present but neither a list nor a dict: {type(entry['notes'])}")

    return problems


# FIXED 2026-09-19: a single flat 300s default made this tool report a false
# "ECOSYSTEM-LEVEL FAILURE ... OVERALL: FAIL" for any ecosystem whose real,
# healthy score_all() run simply takes longer than that -- nothing was broken,
# the ecosystem just grew past the default. Both values below are MEASURED
# full runs on 2026-09-19 (all targets `ok`, OVERALL: PASS), each given ~2x
# headroom, not guessed:
#   tempo           547s wall-clock (13 targets, ~40s CPU, mostly network wait)
#   robinhood-chain 1530s wall-clock = 25m30s (56 targets, ~33s CPU)
# The repo's two earlier figures for Robinhood both turned out wrong: a comment
# in scripts/lib/scorers.py said a full run "exceeds 50 minutes" and
# README.md's dev section said "~600s". An explicit --timeout still overrides
# all of these.
_ECOSYSTEM_TIMEOUT_DEFAULTS = {
    "tempo": 900,
    "robinhood-chain": 3000,
}
_FALLBACK_TIMEOUT = 300


def run_ecosystem(name: str, timeout=300) -> dict:
    script = ECOSYSTEMS[name] + _RUNNER_TAIL
    try:
        proc = subprocess.run([PYTHON, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"name": name, "error": f"timed out after {timeout}s", "entries": []}

    out = proc.stdout
    if "===AROVALIDATOR-JSON-START===" not in out:
        tail = (proc.stderr or out)[-2000:]
        return {"name": name, "error": f"subprocess produced no JSON (exit {proc.returncode}); stderr tail:\n{tail}", "entries": []}

    # FIXED 2026-09-17 (closed a bug hunt finding): everything below used to
    # run with no try/except, so a malformed/truncated payload (e.g. the
    # child process dying abruptly -- SIGKILL/OOM/segfault -- between the
    # START marker and the END marker) raised an uncaught exception that
    # propagated out of run_ecosystem() into main()'s per-ecosystem loop,
    # which has no guard either -- killing the ENTIRE validator run and
    # silently skipping every remaining ecosystem, the exact "one bad target
    # takes down the whole batch" failure class this project has been fixing
    # everywhere else, except here it was one bad ECOSYSTEM taking down every
    # other one. run_ecosystem() must always return a dict, never raise.
    try:
        payload = out.split("===AROVALIDATOR-JSON-START===", 1)[1].split("===AROVALIDATOR-JSON-END===", 1)[0]
        data = json.loads(payload)
        if not data.get("ok"):
            return {"name": name, "error": data.get("error", "unknown error"), "entries": []}

        entries = []
        for entry in data["results"]:
            if not isinstance(entry, dict):
                return {"name": name, "error": f"score_all() entry is not a dict: {entry!r}", "entries": []}
            entries.append({"label": entry.get("label", "<no label>"), "target": entry.get("target"), "problems": validate_entry(entry)})
        return {"name": name, "error": None, "entries": entries}
    except Exception as e:
        return {"name": name, "error": f"malformed subprocess output: {type(e).__name__}: {e}", "entries": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ecosystem", help="Run only this one ecosystem (comma-separated for several).")
    parser.add_argument("--skip", help="Skip these ecosystems (comma-separated).")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Per-ecosystem subprocess timeout in seconds. Default: a per-ecosystem value for known-slow "
                             "ecosystems (see _ECOSYSTEM_TIMEOUT_DEFAULTS), else 300. An explicit value overrides all of them.")
    args = parser.parse_args()

    names = list(ECOSYSTEMS)
    if args.ecosystem:
        wanted = set(args.ecosystem.split(","))
        unknown = wanted - set(ECOSYSTEMS)
        if unknown:
            raise SystemExit(f"Unknown ecosystem(s): {unknown}. Known: {sorted(ECOSYSTEMS)}")
        names = [n for n in names if n in wanted]
    if args.skip:
        skip = set(args.skip.split(","))
        names = [n for n in names if n not in skip]

    overall_ok = True
    total_targets = 0
    total_problems = 0

    for name in names:
        print(f"\n=== {name} ===")
        timeout = args.timeout if args.timeout is not None else _ECOSYSTEM_TIMEOUT_DEFAULTS.get(name, _FALLBACK_TIMEOUT)
        report = run_ecosystem(name, timeout=timeout)
        if report["error"]:
            print(f"  ECOSYSTEM-LEVEL FAILURE: {report['error']}")
            overall_ok = False
            continue
        if not report["entries"]:
            print("  (score_all() returned zero entries)")
            continue
        for e in report["entries"]:
            total_targets += 1
            if e["problems"]:
                overall_ok = False
                total_problems += len(e["problems"])
                print(f"  FAIL  {e['label']} ({e['target']})")
                for p in e["problems"]:
                    print(f"          - {p}")
            else:
                print(f"  ok    {e['label']}")

    print(f"\n{'='*60}")
    print(f"{total_targets} target(s) checked across {len(names)} ecosystem(s), {total_problems} problem(s) found.")
    print("OVERALL: PASS" if overall_ok else "OVERALL: FAIL")
    if not overall_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
