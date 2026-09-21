#!/usr/bin/env python3
"""
Dry-run driver for chains/plasma-ecosystem/scorers.py -- read-only, no
transaction.

Imports the scorer functions from ../scorers.py and runs them live against
a public Plasma mainnet RPC (chain 9745), printing every score dimension
(adminKeyScore, multisigScore, timelockScore, oracleAuthorityScore,
crossExposureScore) plus compositeScore and every note, so a human/agent can
verify the live reads without touching the chain manually.

Usage:
    python3 chains/plasma-ecosystem/scripts/dry_run.py [rpc_url]

Defaults to https://rpc.plasma.to if no RPC URL is given. Refuses to run
against anything other than chain ID 9745 (Plasma mainnet) -- this module
scores live mainnet contracts, not testnet stand-ins.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "plasma-ecosystem"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all, PLASMA_CHAIN_ID, DEFAULT_RPC  # noqa: E402


def main():
    rpc_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPC
    w3 = get_w3(rpc_url)
    if not w3.is_connected():
        raise SystemExit(f"Could not connect to RPC: {rpc_url}")

    chain_id = w3.eth.chain_id
    block = w3.eth.block_number
    print(f"Connected to chain ID {chain_id} (expect {PLASMA_CHAIN_ID} for Plasma mainnet), block {block}")
    if chain_id != PLASMA_CHAIN_ID:
        raise SystemExit(f"Refusing to score against chain ID {chain_id} -- these scorers target Plasma mainnet (chain {PLASMA_CHAIN_ID}) only.")
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
            if "None" in note and "expected" not in note:
                errors += 1
        print()

    print(f"Scored {len(scored)} targets, {errors} note(s) contained an unexplained 'None' (possible dead/rate-limited call).")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
