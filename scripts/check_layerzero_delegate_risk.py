#!/usr/bin/env python3
"""
Standalone LayerZero delegate-risk check -- see
scripts/lib/layerzero_delegate_risk.py for why this isn't wired into
score_all() as a scored dimension yet. Re-checks every address this project
currently hardcodes anywhere in scripts/lib/scorers.py (the ~42 tracked
targets plus their intermediate authority addresses) against Robinhood
Chain's LayerZero V2 EndpointV2, live.

Usage:
    python3 scripts/check_layerzero_delegate_risk.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.layerzero_delegate_risk import find_registered_oapps  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402

ENDPOINT_ADDRESS = "0x6F475642a6e85809B1c36Fa62763669b1b48DD5B"  # LayerZero V2 EndpointV2, Robinhood Chain
ROBINHOOD_RPC = "https://rpc.mainnet.chain.robinhood.com"
SCORERS_PATH = os.path.join(os.path.dirname(__file__), "lib", "scorers.py")


def main():
    with open(SCORERS_PATH) as f:
        source = f.read()
    addresses = sorted(set(re.findall(r'"(0x[a-fA-F0-9]{40})"', source)))
    print(f"Checking {len(addresses)} addresses (every literal address in scripts/lib/scorers.py) "
          f"against EndpointV2.delegates()...\n")

    w3 = get_w3(ROBINHOOD_RPC)
    registered = find_registered_oapps(w3, ENDPOINT_ADDRESS, addresses)

    if registered:
        print(f"{len(registered)} tracked address(es) ARE registered LayerZero OApps:")
        for addr, delegate in registered.items():
            print(f"  {addr} -> delegate = {delegate}")
    else:
        print("None found -- no currently-tracked target (or its authority chain) is a registered LayerZero OApp.")


if __name__ == "__main__":
    main()
