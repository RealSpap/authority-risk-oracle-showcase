#!/usr/bin/env python3
"""
Standalone runner for the two defi-admin-key-risk-motivated checks in
scripts/lib/account_classification.py -- see that module's own docstring
for why each exists. Re-checks every address this project hardcodes
anywhere in scripts/lib/scorers.py (57 addresses: all ~42 Robinhood Chain
targets plus their intermediate authority addresses) for a hidden EIP-7702
delegation, and the newly-discovered EthenaTimelockController's operational
roles for self-escalation risk.

Usage:
    python3 scripts/check_data_collection_hardening.py
"""
import os
import re
import sys

from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from lib.account_classification import check_self_escalation_risk, classify_account  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402

ROBINHOOD_RPC = "https://rpc.mainnet.chain.robinhood.com"
ETHEREUM_L1_RPC = "https://eth.drpc.org"
SCORERS_PATH = os.path.join(os.path.dirname(__file__), "lib", "scorers.py")
ETHENA_TIMELOCK = "0xe8Dc0FAB349eA169283C48ccFd09d797e6dB7c94"
ETHENA_TIMELOCK_ROLES = {
    "DEFAULT_ADMIN_ROLE": b"\x00" * 32,
    "PROPOSER_ROLE": Web3.keccak(text="PROPOSER_ROLE"),
    "EXECUTOR_ROLE": Web3.keccak(text="EXECUTOR_ROLE"),
    "CANCELLER_ROLE": Web3.keccak(text="CANCELLER_ROLE"),
    "WHITELISTED_EXECUTOR_ROLE": Web3.keccak(text="WHITELISTED_EXECUTOR_ROLE"),
}


def main():
    with open(SCORERS_PATH) as f:
        source = f.read()
    addresses = sorted(set(re.findall(r'"(0x[a-fA-F0-9]{40})"', source)))
    print(f"=== EIP-7702 delegation check ({len(addresses)} Robinhood Chain addresses) ===")
    w3 = get_w3(ROBINHOOD_RPC)
    delegated = []
    for addr in addresses:
        result = classify_account(w3, addr)
        if result["kind"] == "eip7702_delegated":
            delegated.append((addr, result["delegate"]))
            print(f"  DELEGATED: {addr} -> {result['delegate']}")
    if not delegated:
        print("  None found.")

    print("\n=== AccessControl self-escalation check (EthenaTimelockController) ===")
    l1_w3 = get_w3(ETHEREUM_L1_RPC)
    for name, role in ETHENA_TIMELOCK_ROLES.items():
        r = check_self_escalation_risk(l1_w3, ETHENA_TIMELOCK, role)
        if not r["checked"]:
            print(f"  {name}: getRoleAdmin() reverted, not checked")
        else:
            flag = "SELF-ADMINISTERING" if r["self_administering"] else "gated by a separate role"
            print(f"  {name}: {flag} (role_admin = 0x{r['role_admin'].hex()})")


if __name__ == "__main__":
    main()
