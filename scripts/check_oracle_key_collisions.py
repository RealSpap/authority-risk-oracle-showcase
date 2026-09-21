#!/usr/bin/env python3
"""Cross-ecosystem oracle key collision audit (read-only: public RPC reads, no key, no transaction).

The oracle stores one score per key, so two scored targets that map to the same key silently overwrite each other on a
push (see scripts/lib/oracle_keys.py). This runs every ecosystem's `score_all()` live, in its own subprocess and in
parallel (same isolation as validate_all_scorers.py, whose ECOSYSTEMS table it reuses), and reports, per ecosystem, the
entries that share a key. Hyperliquid's derived keys are applied first, exactly as its push script does. An ecosystem
whose `score_all()` cannot be run or returns nothing is reported as FAILED, never as clean.

    python3 scripts/check_oracle_key_collisions.py                        # every ecosystem
    python3 scripts/check_oracle_key_collisions.py --ecosystem solana,base
    python3 scripts/check_oracle_key_collisions.py --skip robinhood-chain # the slow one (about 25 minutes)

Exit code 0 only if every ecosystem ran and none has an unresolved collision.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import oracle_keys  # noqa: E402
import validate_all_scorers as v  # noqa: E402

# Keys that are not EVM addresses are compared exactly (base58 and Zcash ids are case-sensitive).
EXACT_KEY_ECOSYSTEMS = {"solana", "zcash"}


def fetch_entries(name, timeout):
    """(entries, error) from one ecosystem's live score_all(), in a fresh subprocess."""
    script = v.ECOSYSTEMS[name] + v._RUNNER_TAIL
    try:
        proc = subprocess.run([sys.executable, "-c", script], cwd=v.REPO_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return [], f"timed out after {timeout}s"
    out = proc.stdout
    if "===AROVALIDATOR-JSON-START===" not in out:
        return [], f"no JSON from the subprocess (exit {proc.returncode}): {(proc.stderr or out)[-400:]}"
    try:
        data = json.loads(out.split("===AROVALIDATOR-JSON-START===", 1)[1].split("===AROVALIDATOR-JSON-END===", 1)[0])
    except ValueError as e:
        return [], f"malformed subprocess output: {e}"
    if not data.get("ok"):
        return [], data.get("error", "unknown error")
    return data["results"], None


def _hyperliquid_resolver():
    # The one exception to the one-subprocess-per-ecosystem isolation: Hyperliquid's own key resolution is a plain function of the
    # entries, so it is loaded in this process. Loading it registers its own imports (`scorers`, `web3_utils`) in this process's
    # sys.modules under names other ecosystems also use, and only sys.path is restored afterwards: nothing in this process reads
    # those modules (every other ecosystem runs in a subprocess, and resolve_oracle_keys uses neither), so it is safe here.
    path = os.path.join(v.REPO_ROOT, "chains", "hyperliquid", "deploy", "push_scores.py")
    saved = list(sys.path)
    sys.path.insert(0, os.path.join(v.REPO_ROOT, "chains", "hyperliquid"))
    try:
        spec = importlib.util.spec_from_file_location("hl_push_scores_for_key_audit", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = saved
    return mod.resolve_oracle_keys


def audit(name, timeout):
    entries, err = fetch_entries(name, timeout)
    if err:
        return {"name": name, "error": err, "entries": 0, "collisions": {}, "resolved": {}}
    if not entries:
        return {"name": name, "error": "score_all() returned zero entries", "entries": 0, "collisions": {}, "resolved": {}}
    exact = name in EXACT_KEY_ECOSYSTEMS
    before = oracle_keys.find_key_collisions(entries, exact)
    if name == "hyperliquid":
        # the push script's own resolution: colliding HIP-3 dexes move to a derived key, anything else is a hard failure
        try:
            _hyperliquid_resolver()(entries)
        except SystemExit as e:
            return {"name": name, "error": f"the push script's own resolution refuses: {e}", "entries": len(entries),
                    "collisions": before, "resolved": {}}
    # after Hyperliquid's own resolution its push script pushes `oracleKey`, every other script pushes `target`
    after = oracle_keys.find_key_collisions(entries, exact, honour_oracle_key=(name == "hyperliquid"))
    resolved = {k: labels for k, labels in before.items() if k not in after}
    return {"name": name, "error": None, "entries": len(entries), "collisions": after, "resolved": resolved}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecosystem", help="only these ecosystems (comma-separated)")
    ap.add_argument("--skip", help="skip these ecosystems (comma-separated)")
    ap.add_argument("--timeout", type=int, default=None, help="per-ecosystem timeout in seconds (default: validate_all_scorers' own)")
    args = ap.parse_args()
    names = list(v.ECOSYSTEMS)
    if args.ecosystem:
        wanted = set(args.ecosystem.split(","))
        unknown = wanted - set(v.ECOSYSTEMS)
        if unknown:
            raise SystemExit(f"Unknown ecosystem(s): {sorted(unknown)}. Known: {sorted(v.ECOSYSTEMS)}")
        names = [n for n in names if n in wanted]
    if args.skip:
        skipped = set(args.skip.split(","))
        unknown = skipped - set(v.ECOSYSTEMS)
        if unknown:
            raise SystemExit(f"Unknown ecosystem(s) in --skip: {sorted(unknown)}. Known: {sorted(v.ECOSYSTEMS)}")
        names = [n for n in names if n not in skipped]
    if not names:
        raise SystemExit("no ecosystem selected: refusing to report a clean result for an empty audit")

    def one(name):
        t = args.timeout if args.timeout is not None else v._ECOSYSTEM_TIMEOUT_DEFAULTS.get(name, v._FALLBACK_TIMEOUT)
        return audit(name, t)

    with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        reports = list(pool.map(one, names))

    ok = True
    total = 0
    for r in reports:
        total += r["entries"]
        if r["error"]:
            ok = False
            print(f"{r['name']:16} FAILED  {r['error']}")
            continue
        if r["collisions"]:
            ok = False
            print(f"{r['name']:16} COLLISION  {r['entries']} entries")
            for k, labels in sorted(r["collisions"].items()):
                print(f"    {k} <- {labels}")
            continue
        note = ""
        if r["resolved"]:
            note = f"  ({len(r['resolved'])} colliding address(es) resolved by derived keys: " + "; ".join(f"{k} <- {l}" for k, l in sorted(r["resolved"].items())) + ")"
        print(f"{r['name']:16} ok  {r['entries']} entries, {r['entries']} distinct keys{note}")
    print(f"\n{total} entries across {len(reports)} ecosystem(s)")
    print("RESULT: NO UNRESOLVED KEY COLLISION" if ok else "RESULT: FAIL (collision, or an ecosystem could not be checked)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
