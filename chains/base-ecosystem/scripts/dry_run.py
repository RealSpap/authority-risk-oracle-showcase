#!/usr/bin/env python3
"""
Dry-run driver for chains/base-ecosystem/scorers.py -- read-only, no transaction.

Imports the 5 scorer functions from ../scorers.py and runs them live against
a public Base mainnet RPC (chain 8453), printing every score dimension
(adminKeyScore, multisigScore, timelockScore, oracleAuthorityScore,
crossExposureScore) plus compositeScore and every note, so a human/agent can
eyeball them against ../data/scored_targets_2026-09-16.md without touching
the chain.

Usage:
    python3 chains/base-ecosystem/scripts/dry_run.py [rpc_url]

Defaults to https://mainnet.base.org if no RPC URL is given. Refuses to run
against anything other than chain ID 8453 (Base mainnet) -- this module
scores live mainnet contracts, not testnet stand-ins.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "base-ecosystem"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402

DEFAULT_RPC = "https://mainnet.base.org"


def main():
    rpc_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPC
    w3 = get_w3(rpc_url)
    if not w3.is_connected():
        raise SystemExit(f"Could not connect to RPC: {rpc_url}")

    chain_id = w3.eth.chain_id
    block = w3.eth.block_number
    print(f"Connected to chain ID {chain_id} (expect 8453 for Base mainnet), block {block}")
    if chain_id != 8453:
        raise SystemExit(f"Refusing to score against chain ID {chain_id} -- these scorers target Base mainnet (chain 8453) only.")
    print()

    scored = score_all(w3)
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
            # "expected None/revert" call sites are disclosed as such in their own
            # note text and are not counted as a possible dead/rate-limited call.
            if "None" in note and "expected" not in note:
                errors += 1
        print()

    print(f"Scored {len(scored)} targets, {errors} note(s) contained an unexplained 'None' (possible dead/rate-limited call).")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
