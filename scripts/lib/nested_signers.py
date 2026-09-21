"""Who really signs: resolve a Safe's signers all the way down.

ADDED 2026-09-21. A Safe's owner list is not always a list of people. In the registered root Safes, 27 of the 405 distinct signer
addresses are themselves Safes (nested seats), one is an EOA that delegated its code through EIP-7702, and one is a
TimelockController. `safe_owners_and_threshold` counts each of them as one signer, and the cross-ecosystem overlap check compared
only the first level. This module builds the whole tree (nested Safes resolved to their own owners, up to MAX_DEPTH), and derives:

- `min_eoa_keys`: the fewest distinct EOA keys that reach quorum, with a nested Safe seat costing what its own quorum costs;
- `leaf_keys`: every EOA key that can contribute to a seat, however deep;
- the signers that are neither an EOA nor a resolvable Safe, so that each one is either analyzed (KNOWN_*) or reported.

The readers are injected (`get_code`, `get_safe`), so the logic runs without a chain; scripts/check_nested_signers.py wires the real ones.
"""

MAX_DEPTH = 4
EIP7702_PREFIX = bytes.fromhex("ef0100")

# EIP-7702 delegate contracts that have been read. Keys are lowercase. A delegate not in here is reported as UNANALYZED.
KNOWN_7702_DELEGATES = {
    "0x63c0c19a282a1b52b07dd5a65b58948a07dae32b": {
        "analyzed": "2026-09-21",
        "name": "MetaMask EIP7702StatelessDeleGator",
        "summary": (
            "Sourcify exact match on Ethereum mainnet for src/EIP7702/EIP7702StatelessDeleGator.sol (MetaMask Delegation "
            "Framework). The copy on Monad (11,185 bytes) differs from the verified one in 33 bytes only: the chain id constant "
            "(1 vs 143) and the EIP-712 domain separator, both chain-specific. The account keeps its own key as the signing "
            "authority (the delegator validates signatures against the account itself) and adds the ability to redeem "
            "delegations the account signed. No new signer is created; the exposure is a signed delegation being redeemed by "
            "someone else, on top of the key itself."
        ),
    },
}

# Contract signers that are neither a Safe nor an EOA and have been read.
KNOWN_CONTRACT_SIGNERS = {
    "0xc06fd4f821eac1ff1ae8067b36342899b57baa2d": {
        "analyzed": "2026-09-21",
        "name": "EigenLayer TimelockController (10-day delay)",
        "summary": (
            "One of the two owners of EigenLayer's 1-of-2 executor Safe, beside the 9-of-13 community Safe. A real "
            "TimelockController, already traced and scored by score_eigenlayer_strategy_manager, which records that the "
            "community Safe can act alone without the delay."
        ),
    },
}


def signer_kind(code):
    """"EOA", "EOA-7702" (23 bytes of code: 0xef0100 + delegate), "contract", or "unread" (code is None)."""
    if code is None:
        return "unread"
    if len(code) == 0:
        return "EOA"
    if len(code) == 23 and bytes(code[:3]) == EIP7702_PREFIX:
        return "EOA-7702"
    return "contract"


def delegate_of(code):
    """The delegate address (lowercase, 0x-prefixed) of an EIP-7702 account, else None."""
    if code is not None and len(code) == 23 and bytes(code[:3]) == EIP7702_PREFIX:
        return "0x" + bytes(code[3:]).hex()
    return None


def build_tree(address, get_code, get_safe, depth=0, cache=None):
    """Signer tree of `address`.

    get_code(address) -> bytes or None (None = the read failed); get_safe(address) -> (owners, threshold) or None.
    Node kinds: "EOA", "EOA-7702", "Safe" (with k, n, kids), "contract" (not a Safe, or beyond MAX_DEPTH), "unread"."""
    cache = {} if cache is None else cache
    key = address.lower()
    if key in cache:
        return cache[key]
    code = get_code(address)
    kind = signer_kind(code)
    node = {"addr": address, "kind": kind}
    if kind == "EOA-7702":
        node["delegate"] = delegate_of(code)
    elif kind == "contract":
        resolved = get_safe(address) if depth < MAX_DEPTH else None
        if resolved:
            owners, threshold = resolved
            node.update({
                "kind": "Safe", "k": threshold, "n": len(owners),
                "kids": [build_tree(o, get_code, get_safe, depth + 1, cache) for o in owners],
            })
        else:
            node["codeLen"] = len(code)
    cache[key] = node
    return node


def min_eoa_keys(node):
    """Fewest distinct EOA keys that reach this node's quorum. An EOA (delegated or not) costs 1; a nested Safe costs the sum of its
    k cheapest seats; a contract that is not a Safe, or an unread signer, is assumed to cost 1 (the weakest reading, never
    promoted). Distinct-key overlap between seats is ignored, so this is an upper bound on the true minimum."""
    if node["kind"] != "Safe":
        return 1
    costs = sorted(min_eoa_keys(kid) for kid in node["kids"])
    return sum(costs[:node["k"]])


def leaf_keys(node):
    """Lowercase addresses of every EOA (delegated or not) that can contribute to this node, however deep."""
    if node["kind"] in ("EOA", "EOA-7702"):
        return {node["addr"].lower()}
    out = set()
    for kid in node.get("kids", []):
        out |= leaf_keys(kid)
    return out


def walk(node):
    """Every node of the tree, the root included."""
    yield node
    for kid in node.get("kids", []):
        yield from walk(kid)


def nested_safes(node):
    """The Safe nodes below `node` (not the root itself)."""
    return [n for n in walk(node) if n["kind"] == "Safe" and n is not node]


def unresolved_signers(node):
    """(kind, node) for every signer that is neither an EOA nor a resolved Safe: contracts that are not Safes, EIP-7702
    accounts and unread ones. The 7702 accounts are included because their delegate must be analyzed."""
    return [(n["kind"], n) for n in walk(node) if n["kind"] in ("EOA-7702", "contract", "unread")]


def status_of_signer(kind, node, known_7702=None, known_contracts=None):
    """"analyzed" or "unanalyzed" for an unresolved signer of `unresolved_signers`."""
    known_7702 = KNOWN_7702_DELEGATES if known_7702 is None else known_7702
    known_contracts = KNOWN_CONTRACT_SIGNERS if known_contracts is None else known_contracts
    if kind == "EOA-7702":
        return "analyzed" if (node.get("delegate") or "").lower() in known_7702 else "unanalyzed"
    if kind == "contract":
        return "analyzed" if node["addr"].lower() in known_contracts else "unanalyzed"
    return "unanalyzed"  # unread


def overlaps(sets_by_committee):
    """{address: {committee, ...}} for every address held by more than one committee. `sets_by_committee`: {committee: set}."""
    seen = {}
    for committee, addrs in sets_by_committee.items():
        for a in addrs:
            seen.setdefault(a, set()).add(committee)
    return {a: cs for a, cs in seen.items() if len(cs) > 1}


def new_overlaps_when_expanded(first_level, expanded):
    """Overlaps that exist only once nested owners are expanded, or whose set of committees grows: {address: (before, after)}."""
    before, after = overlaps(first_level), overlaps(expanded)
    return {a: (before.get(a, set()), cs) for a, cs in after.items() if before.get(a, set()) != cs}


def new_committee_links(first_level, expanded):
    """Pairs of committees that share no key at the first level but do once nested owners are expanded:
    {(committee_a, committee_b): number_of_shared_keys}. These are the overlaps the first-level check could not see."""
    def pair_counts(sets_by_committee):
        counts = {}
        for a, b in _pairs(sorted(sets_by_committee)):
            shared = sets_by_committee[a] & sets_by_committee[b]
            if shared:
                counts[(a, b)] = len(shared)
        return counts
    before, after = pair_counts(first_level), pair_counts(expanded)
    return {pair: n for pair, n in after.items() if pair not in before}


def _pairs(items):
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            yield a, b


def signer_note(owners, get_code, known_7702=None, known_contracts=None):
    """One note line about the signers of a Safe that are not plain EOAs (EIP-7702 accounts and contracts), or None when all are
    plain EOAs. `owners` are the Safe's direct owners; `get_code(address)` -> bytes or None. Never a score input."""
    known_7702 = KNOWN_7702_DELEGATES if known_7702 is None else known_7702
    known_contracts = KNOWN_CONTRACT_SIGNERS if known_contracts is None else known_contracts
    parts = []
    for owner in owners:
        code = get_code(owner)
        kind = signer_kind(code)
        if kind == "EOA":
            continue
        if kind == "EOA-7702":
            delegate = delegate_of(code)
            info = known_7702.get(delegate)
            what = (f"{info['name']}, analyzed {info['analyzed']}: {info['summary']}" if info
                    else "a delegate that has NOT been analyzed")
            parts.append(f"signer {owner} is an EOA that delegated its code through EIP-7702 to {delegate} ({what})")
        elif kind == "contract":
            info = known_contracts.get(owner.lower())
            parts.append(f"signer {owner} is a contract" + (f" ({info['name']}, analyzed {info['analyzed']})" if info else " (a nested Safe or another contract; see scripts/check_nested_signers.py)"))
        else:
            parts.append(f"signer {owner} could not be read")
    if not parts:
        return None
    return "Signers that are not plain EOAs (note only, no score input): " + "; ".join(parts)
