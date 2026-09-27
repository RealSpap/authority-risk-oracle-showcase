"""
Inverse index over the cross-ecosystem group registries (scripts/lib/cross_ecosystem_overlap.py +
scripts/lib/signer_overlap.py): the forward view answers "who controls protocol X", this answers
"what can address Y touch", the blast radius of one compromised key. Pure functions, no RPC, so
they are testable without a chain; the network side lives in scripts/who_controls.py.

Also classifies a signer's on-chain code, because a Safe owner that is an EIP-7702 delegated EOA
is not the plain key the multisig formula assumes: Safe validates a contract-type signature (v=0)
by calling `isValidSignature` on the owner address, and a delegated EOA answers with whatever its
delegate contract implements. Disclosed only; no score reads this.
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web3_utils import ARBITRUM_L1_L2_ALIAS_OFFSET, arbitrum_l1_l2_alias  # noqa: E402

EIP7702_PREFIX = b"\xef\x01\x00"


def classify_code(code: bytes):
    """('eoa', None) | ('eip7702', delegate) | ('contract', None) from raw eth_getCode bytes.
    An EIP-7702 delegation designator is exactly 0xef0100 + a 20-byte address (23 bytes)."""
    if not code:
        return ("eoa", None)
    if len(code) == 23 and code[:3] == EIP7702_PREFIX:
        return ("eip7702", Web3.to_checksum_address(code[3:]))
    return ("contract", None)


def build_index(registries: dict, ecosystem_groups: dict) -> dict:
    """`registries`: {ecosystem: {group_key: {"safes": [...], "known_eoa": [...], ...}}} (the static
    group dicts). `ecosystem_groups`: {(ecosystem, group_key): resolved_signer_set}.
    Returns {checksum_address: sorted [(ecosystem, group_key, role)]}, role in
    {"signer", "safe", "known_eoa"}: a resolved Safe owner, a tracked Safe itself, or a hand-listed EOA."""
    idx = {}

    def add(addr, eco, key, role):
        idx.setdefault(Web3.to_checksum_address(addr), set()).add((eco, key, role))

    for eco, groups in registries.items():
        for key, g in groups.items():
            for a in g.get("safes", []):
                add(a, eco, key, "safe")
            for a in g.get("known_eoa", []):
                add(a, eco, key, "known_eoa")
    for (eco, key), signers in ecosystem_groups.items():
        for a in signers:
            add(a, eco, key, "signer")
    return {a: sorted(v) for a, v in idx.items()}


def _l2_alias_origin(address: str) -> str:
    """Inverse of web3_utils.arbitrum_l1_l2_alias: the L1 address an L2 alias comes from."""
    return Web3.to_checksum_address("0x%040x" % ((int(address, 16) - ARBITRUM_L1_L2_ALIAS_OFFSET) % (1 << 160)))


def blast_radius(index: dict, address: str) -> dict:
    """Everything one address can act on: groups (protocol-level control sets) and ecosystems.
    Also looks up the address's L1->L2 alias and its un-aliased origin: the same L1 contract (e.g. a
    timelock) shows up on Arbitrum/OP-stack chains as address + 0x1111...1111, and the index would
    otherwise treat those as two unrelated addresses. `via_alias` lists the alias addresses that matched."""
    addr = Web3.to_checksum_address(address)
    entries = list(index.get(addr, []))
    via_alias = []
    for other in (arbitrum_l1_l2_alias(addr), _l2_alias_origin(addr)):
        if index.get(other):
            via_alias.append(other)
            entries += index[other]
    entries = sorted(set(entries))
    return {"address": addr, "entries": entries, "via_alias": via_alias,
            "groups": sorted({(e, k) for e, k, _ in entries}),
            "ecosystems": sorted({e for e, _, _ in entries})}


def top_signers(index: dict, n: int = 15) -> list:
    """Signers ranked by how many distinct ecosystems then groups they sit in. Tracked Safes and
    hand-listed EOAs that are not resolved owners of anything are not signers of a group.

    Also reports `families`: the group KEY alone, ignoring which ecosystem it is in (registry family
    names are already shared across ecosystems for the same protocol -- "morpho_blue" is the exact
    same string in the ethereum-l1, base, robinhood and tempo registries, see
    scripts/check_cross_ecosystem_overlap.py::REGISTRIES). A signer on 4 groups that are all the SAME
    family (one committee, four deployments of one protocol) is a different, usually more concentrated
    finding than 4 unrelated groups with the same raw count -- `family_count` surfaces that without
    changing the ecosystem-first ranking already established. This is the family-grouping half of the
    "[backlog note]" backlog item; the TVL-weighting half needs a
    group-to-dollar-value mapping that does not exist yet and is not attempted here."""
    rows = []
    for a, entries in index.items():
        groups = {(e, k) for e, k, role in entries if role in ("signer", "known_eoa")}
        if groups:
            families = sorted({k for _, k in groups})
            rows.append((len({e for e, _ in groups}), len(groups), a, sorted(groups), families))
    rows.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return [{"address": a, "ecosystems": e, "groups": g, "where": w, "families": f, "family_count": len(f)} for e, g, a, w, f in rows[:n]]


def family_reach(index: dict) -> dict:
    """{group_key: {"ecosystems": sorted[str], "signers": sorted[address]}} for every group KEY that the
    registries reuse across two or more ecosystems (see top_signers' docstring) -- a family whose
    signer set turns out identical across chains is exactly the shape of the Morpho Blue owner Safe
    finding (the same 9-of-9-ish committee on ethereum-l1/base/robinhood), surfaced generically here
    rather than re-discovered by hand for each new family. A family present in only one ecosystem is
    left out: there is nothing cross-chain to report."""
    by_key = {}
    for a, entries in index.items():
        for e, k, role in entries:
            if role in ("signer", "known_eoa"):
                by_key.setdefault(k, {}).setdefault(e, set()).add(a)
    out = {}
    for k, by_eco in by_key.items():
        if len(by_eco) < 2:
            continue
        signers = sorted(set().union(*by_eco.values()))
        out[k] = {"ecosystems": sorted(by_eco), "signers": signers,
                   "identical_across_ecosystems": len({frozenset(v) for v in by_eco.values()}) == 1}
    return out


def hygiene_summary(classified: dict) -> dict:
    """`classified`: {(ecosystem, address): ('eoa'|'eip7702'|'contract', delegate_or_None)}, keyed per
    chain because a delegation is per chain. Counts by kind and, for delegated EOAs, which signers
    share one delegate contract (one delegate flaw, many owners)."""
    counts = {"eoa": 0, "eip7702": 0, "contract": 0}
    by_delegate = {}
    for (eco, addr), (kind, delegate) in classified.items():
        counts[kind] += 1
        if kind == "eip7702":
            by_delegate.setdefault(delegate, []).append(f"{eco}:{addr}")
    return {"counts": counts, "delegates": {d: sorted(v) for d, v in sorted(by_delegate.items(), key=lambda kv: -len(kv[1]))}}
