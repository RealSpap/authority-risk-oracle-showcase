#!/usr/bin/env python3
"""Has any tracked target's published AUTHORITY SCORE drifted from what its scorer computes live today?

ADDED 2026-09-25 (Spap: "[backlog note]" -- a genuine
demand-driver feature, `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md` backlog item
12 "Posture-change alerts ranked by observed lead time"). This is a real gap DeFiScan and Foreshock both
sell as a headline feature ("24/7 monitoring") that this project had never automated across every
ecosystem at once -- today's own session hand-built this exact check, one ecosystem at a time, on
Monad/Solana/Arbitrum/Ethereum L1/Robinhood Chain (see REPRISE.md's "[backlog note]" entries), each
time as a throwaway script. This generalizes that into one reusable, reproducible tool.

Different from `scripts/check_implementation_changes.py` (which fingerprints a target's CODE) and
`scripts/oracle_freshness.py` (which reports the AGE of the last push, never its correctness) -- this one
answers "is the SCORE itself still right", the actual question a posture-change alert needs. Different
from `scripts/validate_all_scorers.py` (schema validation only, discards the actual field values after
checking they are well-formed ints in [0,100]) -- this one keeps them and diffs them against what is
published on-chain.

Reuses `scripts/validate_all_scorers.py`'s own subprocess-per-ecosystem isolation (`ECOSYSTEMS`,
`_RUNNER_TAIL`) rather than importing every `scorers.py` into one process: several ecosystems import a
same-named sibling module (Hyperliquid and Tempo both `import methodology_test`, pointing at two
DIFFERENT files), so importing two of them in-process makes the second one silently pick up the
first one's already-cached module -- see that file's own docstring for the concrete false-PASS this
already caused once. This tool inherits that protection instead of re-discovering it.

Solana is NOT covered here (a native Anchor program, a different getScore ABI/decode entirely) -- use
`chains/solana/deploy/read_scores_solana.py` for that, which already does the same job for that one
ecosystem. Zcash is not covered either (no testnet oracle deployed as of this writing, phase
`deploy_testnet` per REPRISE.md).

    python3 scripts/check_posture_drift.py                       # every EVM ecosystem
    python3 scripts/check_posture_drift.py --ecosystem arbitrum,ethereum-l1
    python3 scripts/check_posture_drift.py --skip robinhood-chain,tempo   # skip known-slow ones
    python3 scripts/check_posture_drift.py --timeout 900

Exit code 1 if any tracked target's published score differs from what its scorer computes live today, or
if an ecosystem's oracle or its live scorer could not be read -- 0 only if every comparison that could be
made found no drift. A target this run could not match (retired, or the live scorer no longer returns it)
is reported, never silently dropped. Strictly read-only: eth_call and getStorageAt only, no key, no
transaction, on both the testnet oracle and the mainnet targets it tracks.
"""
import argparse
import json
import os
import subprocess
import sys

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
PYTHON = sys.executable

from validate_all_scorers import ECOSYSTEMS, _RUNNER_TAIL, _ECOSYSTEM_TIMEOUT_DEFAULTS, _FALLBACK_TIMEOUT  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "hyperliquid", "deploy"))
import push_scores as _hyperliquid_push  # noqa: E402  -- reused only for its already-published derived-key rule (see below)
from live_target_counts import ORACLES  # noqa: E402

# EVM ecosystems only -- name here must match both ORACLES' first field and an ECOSYSTEMS key.
_ORACLE_BY_ECOSYSTEM = {
    "robinhood-chain": "Robinhood Chain",
    "ethereum-l1": "Ethereum L1 (Sepolia)",
    "arbitrum": "Arbitrum (Sepolia)",
    "base": "Base (Sepolia)",
    "tempo": "Tempo (Moderato)",
    "plasma": "Plasma",
    "monad": "Monad",
    "hyperliquid": "Hyperliquid (HyperEVM)",
}
_ORACLES_BY_NAME = {name: (addr, rpc) for name, addr, rpc in ORACLES}

_SCORE_ABI = [
    {"name": "trackedTargetsCount", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "trackedTargets", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
    {"name": "getScore", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "tuple", "components": [
        {"name": "adminKeyScore", "type": "uint8"}, {"name": "multisigScore", "type": "uint8"}, {"name": "timelockScore", "type": "uint8"},
        {"name": "oracleAuthorityScore", "type": "uint8"}, {"name": "crossExposureScore", "type": "uint8"}, {"name": "compositeScore", "type": "uint8"},
        {"name": "lastUpdated", "type": "uint64"}, {"name": "methodologyHash", "type": "bytes32"}]}]},
]
_DIMENSIONS = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore")


def _retry(fn, attempts=4):
    import time
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            time.sleep(0.6 * (i + 1))
    return None


def published_scores(oracle_address, oracle_rpc):
    """{target_address.lower(): {dimension: value}} read live from the deployed testnet oracle, or
    None if the oracle itself could not be read (never silently empty -- caller must tell the two
    apart)."""
    w3 = Web3(Web3.HTTPProvider(oracle_rpc, request_kwargs={"timeout": 30}))
    contract = w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=_SCORE_ABI)
    count = _retry(lambda: contract.functions.trackedTargetsCount().call())
    if count is None:
        return None
    out = {}
    for i in range(count):
        addr = _retry(lambda i=i: contract.functions.trackedTargets(i).call())
        if addr is None:
            return None
        score = _retry(lambda addr=addr: contract.functions.getScore(addr).call())
        if score is None:
            out[addr.lower()] = None  # this one target unread; the oracle itself did answer
            continue
        out[addr.lower()] = {d: score[j] for j, d in enumerate(_DIMENSIONS)}
    return out


def live_scores(ecosystem_name, timeout):
    """{target_address.lower(): {dimension: value}} re-derived live via that ecosystem's own
    scorers.py::score_all(), run in a fresh subprocess (see this file's own docstring for why).
    Returns (scores_or_None, error_or_None)."""
    script = ECOSYSTEMS[ecosystem_name] + _RUNNER_TAIL
    try:
        proc = subprocess.run([PYTHON, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    out = proc.stdout
    if "===AROVALIDATOR-JSON-START===" not in out:
        tail = (proc.stderr or out)[-2000:]
        return None, f"subprocess produced no JSON (exit {proc.returncode}); stderr tail:\n{tail}"
    try:
        payload = out.split("===AROVALIDATOR-JSON-START===", 1)[1].split("===AROVALIDATOR-JSON-END===", 1)[0]
        data = json.loads(payload)
    except Exception as e:
        return None, f"malformed subprocess output: {type(e).__name__}: {e}"
    if not data.get("ok"):
        return None, data.get("error", "unknown error")
    entries = [e for e in data["results"] if isinstance(e, dict) and e.get("target")]
    keys = oracle_keys_for(ecosystem_name, entries)
    out_map = {}
    for key, entry in zip(keys, entries):
        out_map[key.lower()] = {"label": entry.get("label", "<no label>"), **{d: entry.get(d) for d in _DIMENSIONS}}
    return out_map, None


def oracle_keys_for(ecosystem_name, entries):
    """The address each `score_all()` entry is actually keyed under once pushed -- usually just `entry["target"]`, per entry.

    Two HIP-3 dexes on Hyperliquid (mkts, para) share their raw target address with a separately-scored HyperEVM contract
    (Kinetiq's HIP3StakingManager, para's StakingVault); chains/hyperliquid/deploy/push_scores.py already solves this for the
    real push by moving the dex to a derived key (METHODOLOGY.md 4.7). Reused here so this comparison keys by the SAME
    address the oracle actually stores the dex under, instead of two entries silently colliding on one Python dict key and
    looking like a missing/dropped target (what FIRST surfaced this: a full sweep on 2026-09-27 reported both dexes as
    "not in the live scorer" while the oracle itself, and read_scores_hyperliquid.py, had always had them right)."""
    keys = [e["target"] for e in entries]
    if ecosystem_name == "hyperliquid":
        try:
            keys = _hyperliquid_push.resolve_oracle_keys([dict(e) for e in entries])
        except SystemExit:
            pass  # an unresolved collision here is a real problem for push_scores.py itself, not this tool's job
    return keys


def compare(ecosystem_name, oracle_name, timeout, verbose=True):
    """Returns (drift_count, unread_count) for one ecosystem; prints as it goes."""
    oracle_addr, oracle_rpc = _ORACLES_BY_NAME[oracle_name]
    if verbose:
        print(f"=== {oracle_name} ({ecosystem_name}) ===")
    pub = published_scores(oracle_addr, oracle_rpc)
    if pub is None:
        print(f"  [UNREAD oracle] could not read {oracle_addr} on {oracle_rpc}")
        return 0, 1
    live, err = live_scores(ecosystem_name, timeout)
    if live is None:
        print(f"  [UNREAD live scorer] {err}")
        return 0, 1

    drift = unread = 0
    for addr, pub_score in pub.items():
        live_entry = live.get(addr)
        if pub_score is None:
            print(f"  [UNREAD target] {addr}: oracle's own getScore() call failed this run")
            unread += 1
            continue
        if live_entry is None:
            print(f"  [NOT IN LIVE SCORER] {addr}: published composite={pub_score['compositeScore']}, but score_all() does not return this address today (retired on purpose, or genuinely dropped -- not distinguished here, check by hand)")
            unread += 1
            continue
        changed = [d for d in _DIMENSIONS if live_entry.get(d) is not None and live_entry[d] != pub_score[d]]
        if changed:
            drift += 1
            label = live_entry.get("label", addr)
            parts = ", ".join(f"{d} {pub_score[d]}->{live_entry[d]}" for d in changed)
            print(f"  [DRIFT] {label} ({addr}): {parts}")
        elif verbose:
            print(f"  [OK] {live_entry.get('label', addr)} ({addr}): matches")
    if drift == 0 and unread == 0 and verbose:
        print(f"  all {len(pub)} tracked targets match their live scorer")
    return drift, unread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecosystem", help="Comma-separated subset (ECOSYSTEMS keys, e.g. arbitrum,ethereum-l1).")
    ap.add_argument("--skip", help="Comma-separated ecosystems to skip.")
    ap.add_argument("--timeout", type=int, default=None, help="Per-ecosystem subprocess timeout in seconds.")
    ap.add_argument("--quiet", action="store_true", help="Only print DRIFT/UNREAD lines, not each OK match.")
    args = ap.parse_args()

    names = list(_ORACLE_BY_ECOSYSTEM)
    if args.ecosystem:
        wanted = set(args.ecosystem.split(","))
        unknown = wanted - set(names)
        if unknown:
            sys.exit(f"unknown --ecosystem value(s): {sorted(unknown)} (known: {names})")
        names = [n for n in names if n in wanted]
    if args.skip:
        skip = set(args.skip.split(","))
        names = [n for n in names if n not in skip]

    total_drift = total_unread = 0
    for name in names:
        timeout = args.timeout or _ECOSYSTEM_TIMEOUT_DEFAULTS.get(name, _FALLBACK_TIMEOUT)
        d, u = compare(name, _ORACLE_BY_ECOSYSTEM[name], timeout, verbose=not args.quiet)
        total_drift += d
        total_unread += u
        print()

    print(f"TOTAL: {total_drift} target(s) with a real score drift, {total_unread} unread across {len(names)} ecosystem(s).")
    sys.exit(1 if (total_drift or total_unread) else 0)


if __name__ == "__main__":
    main()
