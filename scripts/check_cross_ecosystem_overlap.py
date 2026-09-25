#!/usr/bin/env python3
"""
Standalone cross-ecosystem signer-overlap check -- see
scripts/lib/cross_ecosystem_overlap.py for why this is deliberately NOT
wired into the live score_all() pipeline. Re-derives every group's root
signer set live (Robinhood Chain's signer_overlap.py GROUPS plus the Ethereum
L1, Arbitrum, Base, Tempo, Plasma, Monad and Hyperliquid registries in
cross_ecosystem_overlap.py: 8 ecosystems) and reports any signer, any
identical Safe address, any identical bare-EOA address and any full committee
containment shared across ecosystems.

Role since 2026-09-20 (crossExposureScore convention decision, METHODOLOGY.md):
each scorer folds a cross-ecosystem overlap into crossExposureScore from a dated
snapshot of the other chain's committee (Robinhood Chain: a hand-set dated flag in
signer_overlap.py), never a live second-chain call. This script is what those
snapshots and flags are checked against: re-run it after a committee rotation or
a new tracked target, and update whatever it contradicts. Hyperliquid was added
2026-09-25 (only its 4 HyperEVM-side Gnosis-Safe-rooted targets -- most of its
targets are HyperCore-native, a non-EVM multisig concept this tool cannot read).
It still does not cover Solana or Zcash (genuinely incompatible key formats, not
merely unbuilt), and covers Tempo only for its two resolvable Safes.

Usage:
    python3 scripts/check_cross_ecosystem_overlap.py
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from lib.cross_ecosystem_overlap import (  # noqa: E402
    ARBITRUM_GROUPS,
    BASE_GROUPS,
    ETHEREUM_L1_GROUPS,
    HYPERLIQUID_GROUPS,
    MONAD_GROUPS,
    PLASMA_GROUPS,
    TEMPO_GROUPS,
    find_cross_ecosystem_overlaps,
    find_identical_safe_addresses,
    find_subset_committees,
    group_root_signers,
)
from lib.signer_overlap import GROUPS as ROBINHOOD_GROUPS, _safe_owners  # noqa: E402
from lib.web3_utils import get_w3, safe_owners_and_threshold as _gated_safe_owners_and_threshold  # noqa: E402


def safe_owners_and_threshold(w3, address, retries=4):
    """Owner set and threshold only. This tool asks who signs (or whether the address is a Safe at all), so it must not go through
    the authority gate, which would return None for a Safe carrying an unanalyzed module and hide its signers."""
    return _gated_safe_owners_and_threshold(w3, address, retries, check_modules=False)



ROBINHOOD_RPC = "https://rpc.mainnet.chain.robinhood.com"
ETHEREUM_L1_RPC = "https://ethereum-rpc.publicnode.com"
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
BASE_RPC = "https://mainnet.base.org"
TEMPO_RPC = "https://rpc.tempo.xyz"
PLASMA_RPC = "https://rpc.plasma.to"
MONAD_RPC = "https://rpc.monad.xyz"
HYPERLIQUID_RPC = "https://rpc.hyperliquid.xyz/evm"


def main():
    robinhood_w3 = get_w3(ROBINHOOD_RPC)
    l1_w3 = get_w3(ETHEREUM_L1_RPC)
    arb_w3 = get_w3(ARBITRUM_RPC)
    base_w3 = get_w3(BASE_RPC)
    tempo_w3 = get_w3(TEMPO_RPC)
    plasma_w3 = get_w3(PLASMA_RPC)
    monad_w3 = get_w3(MONAD_RPC)
    hyperliquid_w3 = get_w3(HYPERLIQUID_RPC)

    ecosystem_groups = {}
    ecosystem_safes = {}
    ecosystem_eoas = {}
    incomplete_groups = []  # (ecosystem, key, safe_addr, exception) -- see group_root_signers()

    def _collect(ecosystem, w3, groups, safe_fn):
        for key, g in groups.items():
            incomplete_here = []
            ecosystem_groups[(ecosystem, key)] = group_root_signers(w3, g, safe_fn, incomplete_out=incomplete_here)
            for safe_addr, exc in incomplete_here:
                incomplete_groups.append((ecosystem, key, safe_addr, exc))
            for safe_addr in g.get("safes", []):
                ecosystem_safes[(ecosystem, f"{key}:{safe_addr[:10]}")] = safe_addr
            for eoa_addr in g.get("known_eoa", []):
                ecosystem_eoas[(ecosystem, f"{key}:{eoa_addr[:10]}")] = eoa_addr

    _collect("robinhood", robinhood_w3, ROBINHOOD_GROUPS, _safe_owners)
    _collect("ethereum-l1", l1_w3, ETHEREUM_L1_GROUPS, safe_owners_and_threshold)
    _collect("arbitrum", arb_w3, ARBITRUM_GROUPS, safe_owners_and_threshold)
    _collect("base", base_w3, BASE_GROUPS, safe_owners_and_threshold)
    _collect("tempo", tempo_w3, TEMPO_GROUPS, safe_owners_and_threshold)
    _collect("plasma", plasma_w3, PLASMA_GROUPS, safe_owners_and_threshold)
    _collect("monad", monad_w3, MONAD_GROUPS, safe_owners_and_threshold)
    _collect("hyperliquid", hyperliquid_w3, HYPERLIQUID_GROUPS, safe_owners_and_threshold)

    print(f"Resolved {len(ecosystem_groups)} groups across "
          f"{len({eco for eco, _ in ecosystem_groups})} ecosystems "
          f"(robinhood: {len(ROBINHOOD_GROUPS)}, ethereum-l1: {len(ETHEREUM_L1_GROUPS)}, "
          f"arbitrum: {len(ARBITRUM_GROUPS)}, base: {len(BASE_GROUPS)}, tempo: {len(TEMPO_GROUPS)}, "
          f"plasma: {len(PLASMA_GROUPS)}, monad: {len(MONAD_GROUPS)}, hyperliquid: {len(HYPERLIQUID_GROUPS)}).\n")

    signer_overlaps = find_cross_ecosystem_overlaps(ecosystem_groups)
    print("=== Cross-ecosystem SIGNER overlaps ===")
    if signer_overlaps:
        for signer, groups in signer_overlaps.items():
            print(f"  {signer}: {sorted(groups)}")
    else:
        print("  None found.")

    print("\n=== Identical Safe ADDRESS across ecosystems (same address, different chain) ===")
    address_overlaps = find_identical_safe_addresses(ecosystem_safes)
    if address_overlaps:
        for addr, groups in address_overlaps.items():
            print(f"  {addr}: {sorted(groups)}")
    else:
        print("  None found.")

    # ADDED 2026-09-19: closes a real gap -- `ecosystem_safes` above only
    # ever held Safe addresses, so a bare EOA reused identically across
    # chains (the Curve/Monad-Robinhood finding: same admin key, same
    # factory address, on two chains) was never checked by this function,
    # only caught because a human happened to notice it. Same function,
    # applied to `known_eoa` addresses instead.
    print("\n=== Identical bare-EOA ADDRESS across ecosystems (same key, different chain) ===")
    eoa_overlaps = find_identical_safe_addresses(ecosystem_eoas)
    if eoa_overlaps:
        for addr, groups in eoa_overlaps.items():
            print(f"  {addr}: {sorted(groups)}")
    else:
        print("  None found.")

    # ADDED 2026-09-19: closes the other real gap -- the signer-overlap
    # section above flags individual shared signers, but doesn't say HOW
    # MUCH of either committee is shared. The Monad/Robinhood Morpho vault
    # finding (Monad's entire 6-signer curator committee contained inside
    # Robinhood's 7-signer one) had to be reasoned about by hand from that
    # output. This does the containment check directly.
    print("\n=== Committee CONTAINMENT across ecosystems (one group's full signer set inside another's) ===")
    subsets = find_subset_committees(ecosystem_groups)
    if subsets:
        for s in subsets:
            smaller_eco, smaller_key = s["smaller"]
            larger_eco, larger_key = s["larger"]
            print(f"  {smaller_eco}:{smaller_key} ({len(s['shared'])} signers) fully contained in {larger_eco}:{larger_key}")
    else:
        print("  None found.")

    # ADDED 2026-09-22: every section above reads `ecosystem_groups`, and a group whose Safe hit a
    # persistent network failure (group_root_signers()'s incomplete_out, see its own docstring) is
    # in there with a SMALLER signer set than it should have -- meaning a real overlap could be
    # silently missing from every "None found." above, not just this run's own inline "NETWORK
    # FAILURE" log lines scattered through the earlier resolution output. A final, unmissable
    # summary, not just those scattered prints, so re-running before trusting a clean result for an
    # affected group is a decision this script's own output forces, not one a human has to remember.
    print("\n=== Groups with an INCOMPLETE signer set this run (a Safe failed to resolve over the network) ===")
    if incomplete_groups:
        for ecosystem, key, safe_addr, exc in incomplete_groups:
            print(f"  {ecosystem}:{key} -- {safe_addr} unreadable ({type(exc).__name__}: {exc}) -- every 'None found.' above involving this group is NOT confirmed, re-run before trusting it")
    else:
        print("  None -- every group above resolved every Safe it has.")


if __name__ == "__main__":
    main()
