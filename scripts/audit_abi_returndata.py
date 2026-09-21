#!/usr/bin/env python3
"""Cross-ecosystem ABI return-data audit (read-only: public RPC reads, no key, no transaction).

Runs every ecosystem's `score_all()` live, each in its own subprocess and in parallel (same table and isolation as
validate_all_scorers.py), with scripts/lib/abi_returndata_guard.py installed in RECORD mode: every ABI decode whose return data has
not the size the declared outputs require is listed with the file and line that asked for it. Decoding itself is unchanged, so
the scores are the ones a normal run produces. See the guard's docstring for the trap this looks for (a struct or several outputs
read with a single-value ABI silently gives its first word).

    python3 scripts/audit_abi_returndata.py                        # every ecosystem, four at a time
    python3 scripts/audit_abi_returndata.py --workers 1            # one at a time (the public RPCs rate-limit: parallel runs make reads fail)
    python3 scripts/audit_abi_returndata.py --ecosystem solana,base
    python3 scripts/audit_abi_returndata.py --skip robinhood-chain # the slow one (about 25 minutes)

An answer of empty data (an address without code answers an eth_call that way, and the helpers probe bare addresses to see whether they
are a Safe) is reported as an informational probe, not as a failure: web3 raises on it and no scorer takes it for a success. Exit code 0
only if every ecosystem ran COMPLETELY (a target that `score_all()` skipped after a failed read makes the audit partial, so it fails
closed) and no answer had a wrong non-empty size (more, fewer, a dynamic head shortfall, or a dynamic layout that does not re-encode
to the length returned).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_all_scorers as v  # noqa: E402

PREFIX = """
import sys
sys.path.append('scripts/lib')
import abi_returndata_guard as _abi_guard
_abi_guard.install('record', {sink!r})
"""


def audit(name, timeout):
    fd, sink = tempfile.mkstemp(prefix=f"abiaudit_{name}_", suffix=".json")
    os.close(fd)
    os.unlink(sink)
    script = PREFIX.format(sink=sink) + v.ECOSYSTEMS[name] + v._RUNNER_TAIL
    try:
        proc = subprocess.run([sys.executable, "-c", script], cwd=v.REPO_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"name": name, "error": f"timed out after {timeout}s", "checked": 0, "mismatches": [], "scored": 0}
    out = proc.stdout
    if "===AROVALIDATOR-JSON-START===" not in out:
        return {"name": name, "error": f"no JSON from the subprocess (exit {proc.returncode}): {(proc.stderr or out)[-300:]}",
                "checked": 0, "mismatches": [], "scored": 0}
    skipped = [l.strip() for l in out.split("===AROVALIDATOR-JSON-START===", 1)[0].splitlines() if l.strip().startswith("score_all(): SKIPPED")]
    try:
        data = json.loads(out.split("===AROVALIDATOR-JSON-START===", 1)[1].split("===AROVALIDATOR-JSON-END===", 1)[0])
    except ValueError as e:
        return {"name": name, "error": f"malformed subprocess output: {e}", "checked": 0, "mismatches": [], "scored": 0}
    if not data.get("ok"):
        return {"name": name, "error": data.get("error", "unknown error"), "checked": 0, "mismatches": [], "scored": 0}
    if not os.path.exists(sink):
        return {"name": name, "error": "the guard wrote no result file (it did not run)", "checked": 0, "mismatches": [], "scored": 0}
    with open(sink, encoding="utf-8") as f:
        rec = json.load(f)
    os.unlink(sink)
    if skipped:
        return {"name": name, "error": f"partial audit: score_all() skipped {len(skipped)} target(s) after a failed read ({skipped[0][:110]})",
                "checked": rec["checked"], "mismatches": rec["mismatches"], "scored": len(data["results"])}
    return {"name": name, "error": None, "checked": rec["checked"], "mismatches": rec["mismatches"], "scored": len(data["results"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecosystem", help="only these ecosystems (comma-separated)")
    ap.add_argument("--skip", help="skip these ecosystems (comma-separated)")
    ap.add_argument("--timeout", type=int, default=None, help="per-ecosystem timeout in seconds (default: validate_all_scorers' own)")
    ap.add_argument("--workers", type=int, default=4, help="ecosystems run at the same time (default 4; the public RPCs rate-limit, "
                                                          "and a skipped target makes the audit fail as partial)")
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

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        reports = list(pool.map(one, names))

    ok = True
    for r in reports:
        if r["error"]:
            ok = False
            print(f"{r['name']:16} FAILED  {r['error']}")
            continue
        size = [m for m in r["mismatches"] if m["kind"] != "empty"]
        empty = [m for m in r["mismatches"] if m["kind"] == "empty"]
        if size:
            ok = False
        print(f"{r['name']:16} {'MISMATCH' if size else 'ok':8} {r['scored']} entries scored, {r['checked']} ABI decodes checked, "
              f"{len(size)} size mismatch(es), {sum(m['count'] for m in empty)} empty-data probe(s)")
        for m in size:
            print(f"    {m['caller']}  x{m['count']}  {m['problem']}")
        for m in empty:
            print(f"    (informational) {m['caller']}  x{m['count']}  empty answer")
    print("\nRESULT: NO ABI RETURN-DATA SIZE MISMATCH" if ok else "\nRESULT: FAIL (a size mismatch, or an ecosystem that could not be checked)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
