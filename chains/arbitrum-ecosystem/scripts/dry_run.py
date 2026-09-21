#!/usr/bin/env python3
"""
Dry-run driver for chains/arbitrum-ecosystem/scorers.py -- read-only, no
transaction.

Imports the 5 scorer functions from ../scorers.py and runs them live against
a public Arbitrum One mainnet RPC (chain 42161), printing every score
dimension (adminKeyScore, multisigScore, timelockScore, oracleAuthorityScore,
crossExposureScore) plus compositeScore and every note, so a human/agent can
eyeball them against ../data/scored_targets_2026-09-17.md without touching
the chain.

Usage:
    python3 chains/arbitrum-ecosystem/scripts/dry_run.py [rpc_url]

Defaults to https://arb1.arbitrum.io/rpc if no RPC URL is given. Refuses to
run against anything other than chain ID 42161 (Arbitrum One mainnet) -- this
module scores live mainnet contracts, not testnet stand-ins.

After the primary run, every target's compositeScore is independently
re-derived against a second, unrelated public RPC
(https://arbitrum-one-rpc.publicnode.com, override with a 2nd argv) and the
two runs are diffed -- a live, automated form of this project's own
'2+ independent RPCs' rule (scripts/lib/web3_utils.py's `cross_checked()`
documents the same convention), catching a compromised or lagging RPC rather
than trusting a single provider's view of live chain state.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "arbitrum-ecosystem"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402

DEFAULT_RPC = "https://arb1.arbitrum.io/rpc"
CROSS_CHECK_RPC = "https://arbitrum-one-rpc.publicnode.com"
ARBITRUM_ONE_CHAIN_ID = 42161


def run_once(rpc_url, label):
    w3 = get_w3(rpc_url)
    if not w3.is_connected():
        raise SystemExit(f"Could not connect to RPC ({label}): {rpc_url}")

    chain_id = w3.eth.chain_id
    block = w3.eth.block_number
    print(f"[{label}] Connected to chain ID {chain_id} (expect {ARBITRUM_ONE_CHAIN_ID} for Arbitrum One mainnet), block {block}")
    if chain_id != ARBITRUM_ONE_CHAIN_ID:
        raise SystemExit(f"Refusing to score against chain ID {chain_id} -- these scorers target Arbitrum One mainnet (chain {ARBITRUM_ONE_CHAIN_ID}) only.")

    return score_all(w3)


def main():
    rpc_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPC
    cross_check_rpc = sys.argv[2] if len(sys.argv) > 2 else CROSS_CHECK_RPC

    scored = run_once(rpc_url, "primary")
    print()

    errors = 0
    for entry in scored:
        print(f"=== {entry['label']} ({entry['target']}) ===")
        print(
            f"  adminKeyScore={entry['adminKeyScore']} multisigScore={entry['multisigScore']} "
            f"timelockScore={entry['timelockScore']} oracleAuthorityScore={entry['oracleAuthorityScore']} "
            f"crossExposureScore={entry['crossExposureScore']} compositeScore={entry['compositeScore']}"
        )
        for note in entry["notes"]:
            print(f"    {note}")
            # "expected None/revert" or "NOT resolvable"/"unresolved authority" call
            # sites are disclosed as such in their own note text and are not counted
            # as a possible dead/rate-limited call.
            if "None" in note and "expected" not in note and "NOT resolvable" not in note:
                errors += 1
        print()

    print(f"Scored {len(scored)} targets on primary RPC, {errors} note(s) contained an unexplained 'None' (possible dead/rate-limited call).")

    print(f"\nCross-checking every compositeScore against a second, independent RPC: {cross_check_rpc}")
    scored_cross = run_once(cross_check_rpc, "cross-check")
    mismatches = []
    for a, b in zip(scored, scored_cross):
        if a["target"] != b["target"] or a["compositeScore"] != b["compositeScore"]:
            mismatches.append((a["label"], a["target"], a["compositeScore"], b["target"], b["compositeScore"]))
    if mismatches:
        print(f"MISMATCH between primary and cross-check RPC on {len(mismatches)} target(s):")
        for label, ta, sa, tb, sb in mismatches:
            print(f"  {label}: primary target={ta} score={sa}  vs  cross-check target={tb} score={sb}")
    else:
        print(f"All {len(scored)} targets' compositeScore agree exactly between {rpc_url} and {cross_check_rpc}.")

    if errors or mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
