#!/usr/bin/env python3
"""Read-only diagnostic: does PRIVATE_KEY (env var) parse as a valid EVM key,
and does its derived address match the expected updater address? Never
prints the key itself -- only the (public) derived address.

Added 2026-09-24 after a real incident: the shared EVM updater key's file
moved during the workspace_PROPRE migration (keys/evm-testnet-shared.json ->
keys/authority-risk-oracle/evm-testnet-shared/.env, a JSON file despite the
name), and every doc in this repo still pointed at the old path -- two
failed pushes (Monad, Base) before the real path was found, each one
safely rejected by eth_account before signing (0-byte key), but only by
luck of that library raising early. Run this BEFORE a real push, not after:

    PRIVATE_KEY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["private_key"])' <key_file>) \\
    python3 scripts/check_evm_key_matches.py <expected_updater_address>

The shared updater address (base/plasma/monad/arbitrum/l1/tempo/hyperliquid)
is 0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5, confirmed live 2026-09-24."""
import os
import sys

from eth_account import Account

expected = sys.argv[1] if len(sys.argv) > 1 else None

key = os.environ.get("PRIVATE_KEY")
if not key:
    print("PRIVATE_KEY is not set in this shell -- nothing to check.")
    sys.exit(1)

address = Account.from_key(key).address
print(f"derived address: {address}")
if expected:
    print(f"expected updater address: {expected}")
    print(f"matches expected: {'YES' if address.lower() == expected.lower() else 'NO'}")
