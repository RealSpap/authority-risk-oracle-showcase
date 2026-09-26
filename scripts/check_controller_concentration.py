#!/usr/bin/env python3
"""Who really controls this oracle's own tracked Morpho V1 vaults -- rolled up per controller Safe,
not per vault. See scripts/lib/controller_concentration.py's own docstring for why and its precedent
(l1CappedComposite). Live owner()/curator()/guardian() reads plus Morpho's public API for current
TVL (an indexer, not trusted for authority -- only for the USD figure). Nothing is sent, no key.

    python3 scripts/check_controller_concentration.py

Exit status 1 if any vault's roles could not be fully read this run (report is then incomplete, not
wrong for what it did read), 0 otherwise.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
sys.path.insert(0, os.path.dirname(__file__))
from lib.controller_concentration import (  # noqa: E402
    MORPHO_API, TRACKED_MORPHO_VAULTS, build_controller_registry, config_varies_across_chains,
    fold_in_vault_v2_reach, rank_controllers, read_vault_roles,
)
from lib.web3_utils import get_w3, read_address_getter, safe_owners_and_threshold  # noqa: E402
import check_vault_v2_inventory as v2inv  # noqa: E402


def fetch_vault_v2_reach(registry_keys):
    """[(controller_addr_lower, tvl_usd, vault_label)] for every $20M+ Vault V2 target (any tracked
    ecosystem) whose owner -- read directly, or one hop further if the direct owner is itself a
    non-Safe contract (the same VaultV2Supervisor indirection check_vault_v2_inventory.read_holder()
    already chases) -- matches an address already in `registry_keys` (a V1 controller). Re-follows
    the hop here rather than reusing read_holder() directly, since that returns a formatted display
    string, not the resolved address this needs to match against. Best-effort: an unread owner is
    skipped, not guessed at, same as the rest of this report's [UNREAD] handling."""
    try:
        vaults = v2inv.fetch_vaults(20_000_000)
    except Exception as e:
        print(f"  [WARN] Vault V2 reach unreadable this run ({type(e).__name__}: {e}) -- V1-only totals below")
        return []
    w3_by_eco = {}
    rows = []
    for v in vaults:
        eco = v2inv.eco_name(v["chain"]["id"])
        if eco not in v2inv.CHAINS:
            continue
        if eco not in w3_by_eco:
            w3_by_eco[eco] = get_w3(v2inv.CHAINS[eco][1])
        w3 = w3_by_eco[eco]
        try:
            owner_addr = read_address_getter(w3, v["address"], "owner")
        except Exception:
            continue
        if not owner_addr:
            continue
        candidate = owner_addr.lower()
        if candidate not in registry_keys:
            try:
                inner = read_address_getter(w3, owner_addr, "owner")
            except Exception:
                inner = None
            if inner and inner.lower() in registry_keys:
                candidate = inner.lower()
        if candidate in registry_keys:
            rows.append((candidate, float(v["totalAssetsUsd"] or 0), v["name"]))
    return rows


def fetch_tvl(vaults):
    """{(ecosystem, label): usd} -- best-effort live read from Morpho's API, by vault address. A
    vault this API does not return (delisted, or API hiccup) is left at 0.0 -- reported, not
    guessed."""
    addrs = [v[3] for v in vaults]
    query = "{ vaults(first: 50, where: { address_in: %s }) { items { address state { totalAssetsUsd } } } }" % json.dumps(addrs)
    try:
        req = urllib.request.Request(MORPHO_API, data=json.dumps({"query": query}).encode(), headers={"content-type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=30))
        by_addr = {item["address"].lower(): (item.get("state") or {}).get("totalAssetsUsd") or 0.0 for item in data["data"]["vaults"]["items"]}
    except Exception as e:
        print(f"  [WARN] Morpho API unreachable this run ({type(e).__name__}: {e}) -- TVL figures below are 0.0, ranking still valid by vault/chain count")
        by_addr = {}
    out = {}
    for eco, _rpc, label, vault, _roles in vaults:
        out[(eco, label)] = float(by_addr.get(vault.lower(), 0.0))
    return out


def main():
    w3_by_ecosystem = {}
    for eco, rpc, *_ in TRACKED_MORPHO_VAULTS:
        if eco not in w3_by_ecosystem:
            w3_by_ecosystem[eco] = get_w3(rpc)

    unread = []
    vault_rows = []
    for eco, rpc, label, vault, roles in TRACKED_MORPHO_VAULTS:
        w3 = w3_by_ecosystem[eco]
        try:
            resolved = read_vault_roles(w3, vault, roles, read_address_getter)
        except Exception as e:
            print(f"  [UNREAD] {eco}/{label}: {type(e).__name__}: {e}")
            unread.append((eco, label))
            continue
        vault_rows.append((eco, label, vault, resolved))

    tvl_by_vault = fetch_tvl(TRACKED_MORPHO_VAULTS)

    registry = build_controller_registry(vault_rows, safe_owners_and_threshold, w3_by_ecosystem)
    v2_rows = fetch_vault_v2_reach(set(registry.keys()))
    fold_in_vault_v2_reach(registry, v2_rows)
    ranked = rank_controllers(registry, tvl_by_vault)

    total_tvl = sum(tvl_by_vault.values())
    print(f"{len(TRACKED_MORPHO_VAULTS)} tracked Morpho V1 vaults, ${total_tvl/1e6:.1f}M total TVL (Morpho API, live), {len(registry)} distinct controller addresses (owner/curator/guardian)\n")

    print("== controllers ranked by number of tracked vaults governed, then TVL governed ==")
    for addr, info, vault_count, chain_count, max_roles, tvl in ranked:
        by_eco = info["safe_by_ecosystem"]
        shapes = []
        for eco in sorted(info["ecosystems"]):
            s = by_eco.get(eco)
            shapes.append(f"{eco}={s[1]}-of-{len(s[0])}" if s else f"{eco}=bare-EOA/unresolved")
        varies = config_varies_across_chains(by_eco)
        varies_flag = "  <-- SAME address, DIFFERENT owner set/threshold per chain (no cross-chain sync)" if varies else ""
        multi_hat = [f"{eco}:{label} holds {sorted(roles)}" for (eco, label), roles in info["roles_by_vault"].items() if len(roles) >= 2]
        flag = f"  <-- holds {max_roles} roles on the same vault (no independent check between them)" if max_roles >= 2 else ""
        v2 = info.get("v2_reach")
        v2_flag = f"  <-- PLUS ${v2['tvl']/1e6:.1f}M disclosed-only Vault V2 reach ({len(v2['vaults'])} vault(s), not scored, see data/finding_2026-09-25-vault-v2-inventory.md)" if v2 else ""
        print(f"  {addr[:10]}.. [{', '.join(shapes)}] {vault_count} vault(s), {chain_count} chain(s), ${tvl/1e6:.1f}M governed{flag}{varies_flag}{v2_flag}")
        for m in multi_hat:
            print(f"      {m}")

    concentration_top2 = sum(row[5] for row in ranked[:2])
    print(f"\n-> top 2 controllers by TVL govern ${concentration_top2/1e6:.1f}M of ${total_tvl/1e6:.1f}M tracked ({100*concentration_top2/max(total_tvl,1):.0f}%)")
    multi_hat_controllers = sum(1 for row in ranked if row[4] >= 2)
    print(f"-> {multi_hat_controllers} controller(s) hold 2+ roles on the same vault with no independent check between them")

    if unread:
        print(f"\n[INCOMPLETE] {len(unread)} vault(s) could not be fully read this run: {unread} -- the report above excludes them, re-run before trusting the totals")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
