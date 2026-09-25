#!/usr/bin/env python3
"""Sweep every registered root Safe for enabled modules and a transaction guard.

ADDED 2026-09-21. Companion of check_cross_ecosystem_overlap.py: same registry (the `safes` of every group on
the 7 ecosystems), a different question. A Safe's threshold only describes who can act if no module and no guard
changes that (see scripts/lib/safe_modules.py). Prints one line per Safe that has a module or a guard, marks each
as analyzed (in KNOWN_ANALYSES, with what was found) or UNANALYZED, and lists Safes that could not be read. Exit
status 1 if any Safe carries an UNANALYZED module or guard, a singleton or fallback handler that is not a published build
and not analyzed, or could not be read, 0 otherwise.

    python3 scripts/check_safe_modules_guards.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.cross_ecosystem_overlap import (  # noqa: E402
    ARBITRUM_GROUPS, BASE_GROUPS, ETHEREUM_L1_GROUPS, HYPERLIQUID_GROUPS, MONAD_GROUPS, PLASMA_GROUPS, TEMPO_GROUPS,
)
from lib.safe_modules import (  # noqa: E402
    KNOWN_ANALYSES, KNOWN_SINGLETON_ANALYSES, classify, classify_fallback_handler, classify_singleton,
    read_fallback_handler, read_guard, read_modules, read_singleton,
)
from lib.signer_overlap import GROUPS as ROBINHOOD_GROUPS  # noqa: E402
from lib.web3_utils import (  # noqa: E402
    RpcUnavailable, get_w3, safe_owners_and_threshold as _gated_safe_owners_and_threshold,
)


def safe_owners_and_threshold(w3, address, retries=4):
    """Owner set and threshold only. This tool asks who signs (or whether the address is a Safe at all), so it must not go through
    the authority gate, which would return None for a Safe carrying an unanalyzed module and hide its signers."""
    return _gated_safe_owners_and_threshold(w3, address, retries, check_modules=False)



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
    """{(ecosystem, safe_address_lower): [group keys]} for every Safe listed in a registry group."""
    out = {}
    for eco, groups in groups_by_ecosystem.items():
        for key, g in groups.items():
            for s in g.get("safes", []):
                out.setdefault((eco, s.lower()), []).append(key)
    return out


def main():
    safes = registered_safes(GROUPS)
    clean = 0
    not_safe, unread, unanalyzed_rows, analyzed_rows = [], [], [], []
    unread_root_safes = []  # ADDED 2026-09-22: network failures specifically, kept apart from not_safe (see below)
    odd_singletons, odd_handlers, no_handler = [], [], 0  # ADDED 2026-09-21: singleton and fallback handler
    for (eco, addr), keys in sorted(safes.items()):
        w3 = get_w3(RPC[eco])
        # FIXED 2026-09-22 (backlog item, closes an #184-review-flagged gap): the comment two lines
        # down already documented "a Safe that could not be read after retries" as one of the two
        # things `not_safe` means -- true when this file was written, but since #180
        # safe_owners_and_threshold() RAISES RpcUnavailable on that exact case instead of returning a
        # falsy value, so it never reached this bucket at all; it crashed the whole sweep by
        # traceback instead. Restored the comment's own original promise -- but into a SEPARATE
        # bucket (unread_root_safes), not `not_safe`: this file's own docstring promises "Exit status
        # 1 if any Safe ... could not be read", which a genuine bespoke-multisig `not_safe` entry
        # never triggered on its own and still shouldn't (that's not an error, it's not a Safe) --
        # `not_safe` alone was never part of the exit-1 condition below, and a network failure landing
        # there silently (found while re-reviewing this exact fix) would exit 0 on an unread Safe,
        # contradicting the docstring. Given its own tracked bucket instead of stretching not_safe's.
        try:
            resolved = safe_owners_and_threshold(w3, addr)
        except RpcUnavailable as e:
            # Collected, not printed inline: every other bucket in this file (unread, not_safe,
            # odd_singletons, odd_handlers) is silently gathered during this loop and printed once,
            # later, in its own summary block below -- matched here rather than adding this file's
            # first inline print.
            unread_root_safes.append((eco, keys[0], addr, e))
            continue
        if not resolved:
            not_safe.append((eco, keys[0], addr))  # a bespoke multisig, or a Safe that could not be read after retries
            continue
        modules = read_modules(w3, addr)
        guard = read_guard(w3, addr)
        singleton, handler = read_singleton(w3, addr), read_fallback_handler(w3, addr)
        s_status, h_status = classify_singleton(singleton), classify_fallback_handler(handler)
        if s_status != "canonical":
            odd_singletons.append((eco, keys[0], addr, singleton, s_status))
        if h_status == "none":
            no_handler += 1
        elif h_status != "canonical":
            odd_handlers.append((eco, keys[0], addr, handler, h_status))
        verdict = classify(modules, guard)
        if verdict["status"] == "clean":
            clean += 1
        elif verdict["status"] == "unread":
            unread.append((eco, keys[0], addr))
        else:
            (unanalyzed_rows if verdict["status"] == "unanalyzed" else analyzed_rows).append((eco, keys[0], addr, verdict))

    total = len(safes)
    print(f"{total} registered Safe addresses on {len(GROUPS)} ecosystems: {clean} clean (no module, no guard), "
          f"{len(analyzed_rows)} with an analyzed module or guard, {len(unanalyzed_rows)} UNANALYZED, "
          f"{len(unread)} unread, {len(not_safe)} not a Safe (bespoke multisig), {len(unread_root_safes)} unreadable (network)")
    for eco, key, addr, v in analyzed_rows + unanalyzed_rows:
        tag = "UNANALYZED" if v["status"] == "unanalyzed" else "analyzed"
        guard = [] if v["guard"].lower() == "0x" + "0" * 40 else [v["guard"]]
        print(f"  [{tag}] {eco}/{key} {addr}: modules={v['modules']} guard={guard}")
        for a in v["modules"] + guard:
            info = KNOWN_ANALYSES.get(a.lower())
            print(f"      {a}: " + (info["name"] if info else "NOT ANALYZED"))
    canonical_count = total - len(not_safe) - len(unread_root_safes) - len(odd_singletons)
    print(f"singletons: {canonical_count} on a published Safe build, {len(odd_singletons)} not; "
          f"fallback handlers: {no_handler} none, {len(odd_handlers)} not a published build")
    for eco, key, addr, singleton, status in odd_singletons:
        info = KNOWN_SINGLETON_ANALYSES.get((singleton or "").lower())
        print(f"  [singleton {status}] {eco}/{key} {addr}: {singleton}" + (f" = {info['name']}" if info else ""))
    for eco, key, addr, handler, status in odd_handlers:
        print(f"  [fallback handler {status}] {eco}/{key} {addr}: {handler}")
    for eco, key, addr in unread:
        print(f"  [UNREAD] {eco}/{key} {addr}: a module or guard read failed after retries")
    for eco, key, addr in not_safe:
        print(f"  [not a Safe] {eco}/{key} {addr}")
    for eco, key, addr, e in unread_root_safes:
        print(f"  [UNREAD Safe, network] {eco}/{key} {addr}: {e}")
    bad_singleton = [r for r in odd_singletons if r[4] in ("unanalyzed", "unread")]
    # FIXED 2026-09-22 (review finding on this same fix): unread_root_safes now drives exit status 1,
    # matching this file's own docstring ("Exit status 1 if any Safe ... could not be read") -- a
    # network failure used to exit 0 here (silently indistinguishable from "not a Safe" in the exit
    # code, though not in the printed output) purely because #180 had nowhere else to land it before
    # this fix gave it one. not_safe itself deliberately still does NOT drive exit 1: a confirmed
    # bespoke multisig is not an error.
    return 1 if (unanalyzed_rows or unread or bad_singleton or odd_handlers or unread_root_safes) else 0


if __name__ == "__main__":
    sys.exit(main())
