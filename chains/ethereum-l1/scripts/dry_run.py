#!/usr/bin/env python3
"""
Dry-run driver for chains/ethereum-l1/scorers.py -- read-only, no transaction.

Imports the existing scorer functions (written and committed manually in
commit 4d74261, see chains/ethereum-l1/scorers.py's module docstring) and
runs them live against a public Ethereum mainnet RPC, printing every score
and note so a human/agent can eyeball them against
data/scored_targets_2026-09-16-ethereum-l1.md without touching the chain.

Usage:
    python3 chains/ethereum-l1/scripts/dry_run.py [rpc_url]

Defaults to https://ethereum-rpc.publicnode.com if no RPC URL is given.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "ethereum-l1"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402

DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"


def main():
    rpc_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPC
    w3 = get_w3(rpc_url)
    if not w3.is_connected():
        raise SystemExit(f"Could not connect to RPC: {rpc_url}")

    chain_id = w3.eth.chain_id
    block = w3.eth.block_number
    print(f"Connected to chain ID {chain_id} (expect 1 for Ethereum mainnet), block {block}")
    if chain_id != 1:
        raise SystemExit(f"Refusing to score against chain ID {chain_id} -- these scorers target Ethereum L1 mainnet (chain 1) only.")
    print()

    scored = score_all(w3)
    errors = 0
    for entry in scored:
        print(f"=== {entry['label']} ({entry['target']}) ===")
        print(f"  adminKeyScore={entry['adminKeyScore']} multisigScore={entry['multisigScore']} "
              f"timelockScore={entry['timelockScore']} compositeScore={entry['compositeScore']}")
        for note in entry["notes"]:
            print(f"    {note}")
            if "None" in note:
                errors += 1
        print()

    print(f"Scored {len(scored)} targets, {errors} note(s) contained a raw 'None' (possible dead call).")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
