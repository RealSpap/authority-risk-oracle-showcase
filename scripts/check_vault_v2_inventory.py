#!/usr/bin/env python3
"""Disclosed-only inventory of Morpho Vault V2 targets ($20M+) on this oracle's own tracked ecosystems.
See scripts/lib/vault_v2_inventory.py's own docstring for why this is disclosed, not scored, and its
precedent. Live read: Morpho's public API for the vault list and timelocks, each chain's own RPC for
owner()/curator() and Safe resolution. Nothing is sent, no key.

    python3 scripts/check_vault_v2_inventory.py [--min 20000000]

Exit status 1 if any vault's owner/curator could not be read this run, 0 otherwise.
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
sys.path.insert(0, os.path.dirname(__file__))
from lib.vault_v2_inventory import DISCLOSED_TIMELOCK_FUNCTIONS, classify_holder, format_holder, timelock_summary  # noqa: E402
from lib.web3_utils import get_w3, read_address_getter, safe_owners_and_threshold  # noqa: E402

MORPHO_API = "https://blue-api.morpho.org/graphql"

# Morpho's API does not index Plasma (chain 9745, checked 2026-09-25: "unsupported chainId"). Arbitrum
# and Hyperliquid have no V2 vault of $20M or more today (checked the same pass) -- included here so a
# future re-run that finds one isn't silently missed by an incomplete chain list.
CHAINS = {
    "ethereum-l1": (1, "https://ethereum-rpc.publicnode.com"),
    "robinhood": (4663, "https://rpc.mainnet.chain.robinhood.com"),
    "monad": (143, "https://rpc.monad.xyz"),
    "tempo": (4217, "https://rpc.tempo.xyz"),
    "arbitrum": (42161, "https://arb1.arbitrum.io/rpc"),
    "hyperliquid": (999, "https://rpc.hyperliquid.xyz/evm"),
}


def fetch_vaults(min_usd):
    chain_ids = [cid for cid, _ in CHAINS.values()]
    query = (
        "{ vaultV2s(first: 150, where: { chainId_in: %s, totalAssetsUsd_gte: %d }, orderBy: TotalAssetsUsd, orderDirection: Desc) "
        "{ items { address name chain { id } totalAssetsUsd timelocks { functionName duration } } } }"
    ) % (json.dumps(chain_ids), min_usd)
    req = urllib.request.Request(MORPHO_API, data=json.dumps({"query": query}).encode(), headers={"content-type": "application/json"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if data.get("errors"):
        print(f"  [WARN] Morpho API returned errors: {data['errors']} -- results below may be incomplete")
    return data.get("data", {}).get("vaultV2s", {}).get("items", [])


def eco_name(chain_id):
    for name, (cid, _rpc) in CHAINS.items():
        if cid == chain_id:
            return name
    return str(chain_id)


def _resolve_one(w3, addr):
    """(kind, safe_shape) for a single address, no further hops."""
    try:
        code = w3.eth.get_code(w3.to_checksum_address(addr))
        code_len = len(code)
    except Exception:
        return "unread", None
    safe = None
    if code_len:
        try:
            safe = safe_owners_and_threshold(w3, addr)
        except Exception:
            safe = None
    kind = classify_holder(code_len, safe is not None)
    shape = (safe[1], len(safe[0])) if safe else None
    return kind, shape


def read_holder(w3, addr):
    """(kind, detail) for one owner/curator address -- kind from classify_holder(), detail is a
    formatted label. If the address is a contract that is NOT a Safe, follows ONE hop of its own
    `owner()` (the same pattern already used elsewhere in this project -- score_aave_v3_pool's
    executor/PayloadsController chain, _score_steakhouse_l1_vault's owner Safe) rather than
    reporting "contract (not a Safe)" and stopping: found live 2026-09-25 that 6 Steakhouse-family
    V2 vaults' owner is a verified `VaultV2Supervisor` contract whose OWN owner() is the exact same
    Steakhouse Safe (0x0A0e559b...) this oracle already tracks as the owner of 4 Morpho V1 vaults on
    Ethereum L1 and Base (scripts/lib/controller_concentration.py) -- a one-hop indirection, not a
    dead end. Never guesses past that single hop: if the inner owner() is unset, unread, or itself
    not a Safe, this is reported as-is, not chased further."""
    if not addr or int(addr, 16) == 0:
        return "unread", "not set"
    kind, shape = _resolve_one(w3, addr)
    if kind == "contract":
        try:
            inner_addr = read_address_getter(w3, addr, "owner")
        except Exception:
            inner_addr = None
        if inner_addr and int(inner_addr, 16) != 0:
            inner_kind, inner_shape = _resolve_one(w3, inner_addr)
            if inner_kind == "safe":
                return "safe", f"{format_holder('safe', inner_shape)} (via {addr[:10]}..)"
            # Inner hop didn't resolve to a Safe either -- report what WAS found, not the dead guess.
            return kind, f"{format_holder(kind, shape)}, owner() -> {inner_addr[:10]}.. ({inner_kind})"
    return kind, format_holder(kind, shape)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=20_000_000)
    args = ap.parse_args()

    vaults = fetch_vaults(args.min)
    w3_by_eco = {}

    total_tvl = sum(v["totalAssetsUsd"] or 0 for v in vaults)
    print(f"{len(vaults)} Vault V2 targets of ${args.min/1e6:.0f}M or more on tracked ecosystems, ${total_tvl/1e6:.1f}M total (Morpho API, live)\n")

    unread = 0
    by_eco_totals = {}
    for v in sorted(vaults, key=lambda x: -(x["totalAssetsUsd"] or 0)):
        eco = eco_name(v["chain"]["id"])
        by_eco_totals[eco] = by_eco_totals.get(eco, 0) + (v["totalAssetsUsd"] or 0)
        if eco not in w3_by_eco:
            w3_by_eco[eco] = get_w3(CHAINS[eco][1])
        w3 = w3_by_eco[eco]

        owner_addr = read_address_getter(w3, v["address"], "owner")
        curator_addr = read_address_getter(w3, v["address"], "curator")
        owner_kind, owner_label = read_holder(w3, owner_addr)
        curator_kind, curator_label = read_holder(w3, curator_addr)
        if owner_kind == "unread" or curator_kind == "unread":
            unread += 1

        tl = {t["functionName"]: t["duration"] for t in (v.get("timelocks") or [])}
        tl_summary = timelock_summary(tl)
        tl_str = ", ".join(f"{fn}={'unread' if d is None else str(d//86400)+'d'}" for fn, d in tl_summary.items())

        print(f"  {eco:12s} {v['name'][:38]:38s} ${(v['totalAssetsUsd'] or 0)/1e6:7.1f}M  owner={owner_label:16s} curator={curator_label:20s} [{tl_str}]")

    print(f"\nBy ecosystem: {by_eco_totals}")
    if unread:
        print(f"\n[INCOMPLETE] {unread} vault(s) had an owner or curator that could not be classified this run -- re-run before trusting the totals")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
