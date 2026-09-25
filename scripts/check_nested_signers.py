#!/usr/bin/env python3
"""Who really signs the registered root Safes: nested Safe seats, EIP-7702 signers, contract signers.

ADDED 2026-09-21. Companion of check_safe_modules_guards.py and check_cross_ecosystem_overlap.py. For every registered
root Safe on the 7 ecosystems it resolves the signers all the way down (scripts/lib/nested_signers.py) and reports:

- how many signers are EOAs, nested Safes, EIP-7702 accounts or other contracts;
- for each Safe with a non-EOA signer: its tree and the effective number of EOA keys that reach quorum;
- every EIP-7702 delegate and every contract signer that is not in the analyzed tables (UNANALYZED);
- every nested Safe's modules, guard and singleton (the gate reads only the top-level Safe), UNANALYZED if unknown;
- the cross-committee overlaps that only appear once nested owners are expanded.

Exit status 1 if anything is UNANALYZED or unread, 0 otherwise.

    python3 scripts/check_nested_signers.py
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.cross_ecosystem_overlap import (  # noqa: E402
    ARBITRUM_GROUPS, BASE_GROUPS, ETHEREUM_L1_GROUPS, HYPERLIQUID_GROUPS, MONAD_GROUPS, PLASMA_GROUPS, TEMPO_GROUPS,
)
from lib.nested_signers import (  # noqa: E402
    KNOWN_7702_DELEGATES, KNOWN_CONTRACT_SIGNERS, build_tree, leaf_keys, min_eoa_keys, nested_safes,
    new_committee_links, new_overlaps_when_expanded, status_of_signer, unresolved_signers,
)
from lib.safe_modules import (  # noqa: E402
    classify, classify_singleton, read_guard, read_modules, read_singleton,
)
from lib.signer_overlap import GROUPS as ROBINHOOD_GROUPS  # noqa: E402
from lib.web3_utils import (  # noqa: E402
    RpcUnavailable, get_w3, safe_owners_and_threshold as _gated_safe_owners_and_threshold,
)

RPC = {
    "robinhood": "https://rpc.mainnet.chain.robinhood.com",
    "ethereum-l1": "https://ethereum-rpc.publicnode.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "base": "https://mainnet.base.org",
    "plasma": "https://rpc.plasma.to",
    "monad": "https://rpc.monad.xyz",
    "tempo": "https://rpc.tempo.xyz",
    "hyperliquid": "https://rpc.hyperliquid.xyz/evm",
}
GROUPS = {
    "robinhood": ROBINHOOD_GROUPS, "ethereum-l1": ETHEREUM_L1_GROUPS, "arbitrum": ARBITRUM_GROUPS,
    "base": BASE_GROUPS, "plasma": PLASMA_GROUPS, "monad": MONAD_GROUPS, "tempo": TEMPO_GROUPS,
    "hyperliquid": HYPERLIQUID_GROUPS,
}


def registered_safes(groups_by_ecosystem):
    out = {}
    for eco, groups in groups_by_ecosystem.items():
        for key, g in groups.items():
            for s in g.get("safes", []):
                out.setdefault((eco, s.lower()), []).append(key)
    return out


def _render(node, indent=0):
    pad = "  " * indent
    if node["kind"] == "Safe":
        yield f"{pad}Safe {node['addr'][:10]} {node['k']}-of-{node['n']} (effective minimum {min_eoa_keys(node)} EOA keys)"
        eoas = sum(1 for k in node["kids"] if k["kind"] == "EOA")
        for kid in node["kids"]:
            if kid["kind"] != "EOA":
                yield from _render(kid, indent + 1)
        if eoas:
            yield f"{pad}  (+{eoas} EOA signers)"
    elif node["kind"] == "EOA-7702":
        yield f"{pad}EIP-7702 account {node['addr']} delegated to {node.get('delegate')}"
    else:
        yield f"{pad}{node['kind']} {node['addr']}"


def main():
    safes = registered_safes(GROUPS)
    trees, unanalyzed, nested_issues, kinds = {}, [], [], collections.Counter()
    first_level, expanded = collections.defaultdict(set), collections.defaultdict(set)
    seen_signers = set()
    for (eco, addr), keys in sorted(safes.items()):
        w3 = get_w3(RPC[eco])
        # FIXED 2026-09-22 (backlog item, closes an #184-review-flagged gap): since #180,
        # safe_owners_and_threshold() RAISES RpcUnavailable on a persistent network failure instead
        # of returning None -- correct for score_all() (skip that one target, keep its last value),
        # but this diagnostic sweep had no try/except at all around either call site, so the SAME
        # network hiccup that used to just make it treat this Safe as "not a Safe" now crashes the
        # whole run by traceback instead. Restored to the sweep's own pre-existing "unread" reporting
        # convention (the [UNANALYZED ...] lines below, already driving exit status 1) rather than
        # silently reverting to the ambiguous None-for-both-cases bug #180 closed everywhere else.
        try:
            root_resolved = _gated_safe_owners_and_threshold(w3, addr, check_modules=False)
        except RpcUnavailable as e:
            print(f"  [UNREAD root Safe] {eco}/{keys[0]}: {addr} -- {e}")
            unanalyzed.append((eco, keys[0], "root Safe (network)", {"addr": addr}))
            continue
        if not root_resolved:
            continue  # not a Safe (bespoke multisig): out of scope here

        def get_code(a, w3=w3):
            for _ in range(4):
                try:
                    return bytes(w3.eth.get_code(w3.to_checksum_address(a)))
                except Exception:
                    continue
            return None

        def get_safe(a, w3=w3):
            # build_tree()'s own contract (scripts/lib/nested_signers.py) is "get_safe(address) ->
            # (owners, threshold) or None" -- None already means "not resolvable" to its traversal,
            # so a network failure on a NESTED Safe (unlike the root one above, which this script
            # itself decides whether to skip) is folded into that same, already-handled contract
            # rather than propagating past this closure and crashing the run. Disclosed limit, not a
            # full fix: build_tree() has no third state between "confirmed not a Safe" and "unread",
            # so this specific case still can't be told apart from the tree's own data alone -- the
            # print below is the only place that distinction survives, same trade-off the tracker
            # card accepted as lower severity than the root-Safe crash the guard just below closes.
            try:
                return _gated_safe_owners_and_threshold(w3, a, check_modules=False)
            except RpcUnavailable as e:
                print(f"  [UNREAD nested Safe, treated as unresolved] {eco}/{keys[0]}: {a} -- {e}")
                return None

        tree = build_tree(w3.to_checksum_address(addr), get_code, get_safe, cache=trees.setdefault(eco, {}))
        # FIXED 2026-09-22, closes a review finding on this same commit's own first version: the
        # ROOT Safe is read TWICE -- once by root_resolved above, again by build_tree() itself
        # (get_code then get_safe on the same address) -- and nothing checked that the second read
        # actually came back "Safe" before indexing tree["kids"] below, a key build_tree() only ever
        # sets on a resolved Safe node. Two ordinary network hiccups on that SECOND read (get_code
        # exhausting its own retries -> "unread" node; get_safe's now-caught RpcUnavailable -> None ->
        # "contract" node) still crashed this exact sweep with KeyError: 'kids' -- the very failure
        # mode this whole fix exists to close, now reached THROUGH the new get_safe try/except rather
        # than around it. Folded into the same `unanalyzed` bucket the root_resolved check above uses.
        if tree["kind"] != "Safe":
            print(f"  [UNREAD root Safe tree] {eco}/{keys[0]}: {addr} -- came back as {tree['kind']} on build_tree()'s own (second) read")
            unanalyzed.append((eco, keys[0], "root Safe tree (network)", {"addr": addr}))
            continue
        committee = (eco, keys[0])
        expanded[committee] |= leaf_keys(tree)
        first_level[committee] |= {k["addr"].lower() for k in tree["kids"] if k["kind"] in ("EOA", "EOA-7702")}
        for kid in tree["kids"]:
            if (eco, kid["addr"].lower()) not in seen_signers:
                seen_signers.add((eco, kid["addr"].lower()))
                kinds[kid["kind"]] += 1
        if any(k["kind"] != "EOA" for k in tree["kids"]):
            print(f"== {eco}/{keys[0]} {addr}")
            for line in _render(tree, 1):
                print(line)
        for kind, node in unresolved_signers(tree):
            if status_of_signer(kind, node) == "unanalyzed":
                unanalyzed.append((eco, keys[0], kind, node))
        for nested in nested_safes(tree):
            if (eco, nested["addr"].lower(), "checked") in seen_signers:
                continue
            seen_signers.add((eco, nested["addr"].lower(), "checked"))
            verdict = classify(read_modules(w3, nested["addr"]), read_guard(w3, nested["addr"]))
            s_status = classify_singleton(read_singleton(w3, nested["addr"]))
            if verdict["status"] not in ("clean", "analyzed") or s_status not in ("canonical", "analyzed"):
                nested_issues.append((eco, nested["addr"], verdict["status"], s_status))

    print()
    print(f"signers directly under the {len(safes)} registered Safe addresses, by kind: {dict(kinds)}")
    links = new_committee_links(first_level, expanded)
    print(f"committee pairs that share no first-level signer but share a key once nested owners are expanded: {len(links)}")
    for (a, b), n in sorted(links.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {a[0]}/{a[1]}  <->  {b[0]}/{b[1]}: {n} shared key(s)")
    changed = new_overlaps_when_expanded(first_level, expanded)
    print(f"({len(changed)} address(es) in total change their set of sharing committees once nested owners are expanded)")
    for eco, key, kind, node in unanalyzed:
        print(f"  [UNANALYZED {kind}] {eco}/{key}: {node['addr']}" + (f" delegate {node.get('delegate')}" if kind == "EOA-7702" else ""))
    for eco, addr, m_status, s_status in nested_issues:
        print(f"  [UNANALYZED nested Safe] {eco}: {addr} modules/guard {m_status}, singleton {s_status}")
    known = len(KNOWN_7702_DELEGATES) + len(KNOWN_CONTRACT_SIGNERS)
    print(f"analyzed signers on file: {known}; unanalyzed signers: {len(unanalyzed)}; nested Safes with an unknown module, guard or singleton: {len(nested_issues)}")
    return 1 if (unanalyzed or nested_issues) else 0


if __name__ == "__main__":
    sys.exit(main())
