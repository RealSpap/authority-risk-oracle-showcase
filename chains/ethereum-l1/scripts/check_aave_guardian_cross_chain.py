#!/usr/bin/env python3
"""Does the same 7-signer Aave PROTOCOL_GUARDIAN committee this project already tracks on 5 chains
(Ethereum L1, Arbitrum, Base, Plasma, Monad -- `_KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20` in
chains/ethereum-l1/scorers.py) also hold the EMERGENCY_ADMIN seat on Aave's OTHER real V3
deployments?

ADDED 2026-09-25 (roadmap item 9, "voit large" round 2). PROTOCOL_GUARDIAN addresses are sourced from
Aave DAO's own published registry, bgd-labs/aave-address-book (`src/Misc<Chain>.sol`), each address's
provenance recorded in ADDRESSES below -- the address is NOT assumed to carry the same owners just
because it matches (an identical CREATE2 address CAN carry different owners per chain, see this
session's own Steakhouse-Safe finding, `data/finding_2026-09-25-controller-concentration.md`); every
chain's owner set is read live from that chain's own RPC before being compared.

Read-only: getOwners()/getThreshold() only, no key, no transaction.

    python3 chains/ethereum-l1/scripts/check_aave_guardian_cross_chain.py

Exit status 1 if any chain's Safe could not be read this run (result is then incomplete, not wrong
for what it did read), 0 otherwise. A chain reading a DIFFERENT owner set, or not resolving as a
Safe at all, is reported, never silently dropped -- see the zkSync case already found and disclosed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "lib"))
from web3_utils import get_w3, safe_owners_and_threshold  # noqa: E402

# Already tracked by this oracle (5 chains) -- the canonical committee this checks every other chain against.
KNOWN_COMMITTEE = frozenset({
    "0x3fa960f8355d00874d9c7e3350147f5e94859bc2", "0x4ab2bed1d667260db34244ba412817651c2dd52b",
    "0xa2dcdd6e0b5e0d118e2fa8922552ac0fe26efe58", "0xb291232f480f41c75802c4a60f1d2ac03404afef",
    "0xc2674c1a1af0557e1d217ff4f13df44a637c7c13", "0xd4af2e86a27f8f77b0556e081f97b215c9ca8f2e",
    "0xe6838d834674ec35edd53d485770baa10bdd6aae",
})

# (chain label, RPC, PROTOCOL_GUARDIAN address) for every real (non-testnet) Aave V3 deployment NOT
# already tracked by this oracle, per bgd-labs/aave-address-book's src/Misc<Chain>.sol, checked
# 2026-09-25. Fantom and Harmony have no PROTOCOL_GUARDIAN entry in their Misc*.sol files (checked,
# not found -- not included here, plausibly frozen/deprecated markets, not investigated further).
UNTRACKED_CHAINS = [
    ("avalanche", "https://api.avax.network/ext/bc/C/rpc", "0x56C1a4b54921DEA9A344967a8693C7E661D72968"),
    ("optimism", "https://mainnet.optimism.io", "0x56C1a4b54921DEA9A344967a8693C7E661D72968"),
    ("polygon", "https://polygon-bor-rpc.publicnode.com", "0xCb45E82419baeBCC9bA8b1e5c7858e48A3B26Ea6"),
    ("bnb", "https://bsc-rpc.publicnode.com", "0xCb45E82419baeBCC9bA8b1e5c7858e48A3B26Ea6"),
    ("celo", "https://celo-rpc.publicnode.com", "0x88E7aB6ee481Cf92e548c0e1169F824F99142c85"),
    ("gnosis", "https://gnosis-rpc.publicnode.com", "0xCb45E82419baeBCC9bA8b1e5c7858e48A3B26Ea6"),
    ("linea", "https://linea-rpc.publicnode.com", "0x0BF186764D8333a938f35e5dD124a7b9b9dccDF9"),
    ("mantle", "https://mantle-rpc.publicnode.com", "0x172867391d690Eb53896623DaD22208624230686"),
    ("metis", "https://andromeda.metis.io/?owner=1088", "0x56C1a4b54921DEA9A344967a8693C7E661D72968"),
    ("scroll", "https://scroll-rpc.publicnode.com", "0xCb45E82419baeBCC9bA8b1e5c7858e48A3B26Ea6"),
    ("soneium", "https://rpc.soneium.org", "0xEf323B194caD8e02D9E5D8F07B34f625f1c088f1"),
    ("sonic", "https://sonic-rpc.publicnode.com", "0xA4aF5175ed38e791362F01c67a487DbA4aE07dFe"),
    ("xlayer", "https://xlayerrpc.okx.com", "0xD0D1CcB0391aADF1EaD96814ce7ab4008Ebdb336"),
    ("zksync", "https://mainnet.era.zksync.io", "0xba845c27903F7dDB5c676e5b74728C871057E000"),
]


def check_chain(label, rpc_url, address):
    """(status, detail) -- status is "match", "mismatch", "not_a_safe" or "unread"."""
    try:
        w3 = get_w3(rpc_url)
    except Exception as e:
        return "unread", f"{type(e).__name__}: {e}"
    try:
        resolved = safe_owners_and_threshold(w3, address)
    except Exception as e:
        return "unread", f"{type(e).__name__}: {e}"
    if resolved is None:
        try:
            code = w3.eth.get_code(w3.to_checksum_address(address))
            return "not_a_safe", f"has real bytecode ({len(code)} bytes) but does not resolve as a standard Gnosis Safe"
        except Exception as e:
            return "unread", f"{type(e).__name__}: {e}"
    owners, threshold = resolved
    owner_set = {o.lower() for o in owners}
    if owner_set == KNOWN_COMMITTEE:
        return "match", f"{threshold}-of-{len(owners)}, identical to the known 7"
    overlap = len(owner_set & KNOWN_COMMITTEE)
    return "mismatch", f"{threshold}-of-{len(owners)}, {overlap}/{len(KNOWN_COMMITTEE)} signers shared with the known committee"


def main():
    print(f"Known committee (already tracked on Ethereum L1, Arbitrum, Base, Plasma, Monad): {len(KNOWN_COMMITTEE)} signers\n")
    matches = mismatches = unread = 0
    for label, rpc, addr in UNTRACKED_CHAINS:
        status, detail = check_chain(label, rpc, addr)
        print(f"  {label:10s} {addr}  {status:12s} {detail}")
        if status == "match":
            matches += 1
        elif status == "unread":
            unread += 1
        else:
            mismatches += 1
    print(f"\n{matches} of {len(UNTRACKED_CHAINS)} untracked chains share the exact same 7-signer committee "
          f"({matches + 5} of {len(UNTRACKED_CHAINS) + 5} real Aave V3 chains checked in total, tracked + untracked).")
    if unread:
        print(f"[INCOMPLETE] {unread} chain(s) could not be read this run -- re-run before trusting the totals")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
