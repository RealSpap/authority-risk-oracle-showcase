#!/usr/bin/env python3
"""Issuer power (freeze/seize/pause/upgrade + controller identity) for every base and collateral
asset of this oracle's 3 already-tracked, already-scored Compound V3 Comet markets (Ethereum L1,
Arbitrum, Base -- `score_compound_v3_cusdc`/`score_compound_v3_comet_arbitrum_usdc`/
`score_compound_v3_comet_base_usdc`). Same precedent as `check_aave_v3_pool_issuer_power.py`
(2026-09-26, same day): a lending market's own admin/multisig/timelock score says nothing about
what the ASSETS it lists -- both the base (borrowed) asset and every collateral asset -- can do to
depositors and borrowers regardless of Compound's own governance.

Live: each Comet's own `baseToken()` and `numAssets()`/`getAssetInfo(i)` (never hardcoded -- the
asset list changes as Compound governance lists/delists collateral), then the exact same
Blockscout-ABI + controller-getter + role-member-getter classification `check_issuer_power.py`
already built and tested, reused here via direct import (same discipline
`check_aave_v3_pool_issuer_power.py` and `check_controller_concentration.py` already established
today: import a sibling script's functions rather than duplicate logic). `check_issuer_power.py`'s
own `BLOCKSCOUT`/`RPC` dicts extended with chain 42161 (Arbitrum) for this script's use -- purely
additive, never touching that script's own Morpho-vault-scoped main().

    python3 scripts/check_compound_v3_comet_issuer_power.py

Disclosed only -- same precedent as every other extension this week: no `adminKeyScore`/
`multisigScore`/`timelockScore`/`AuthorityScore` change, no on-chain push.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
sys.path.insert(0, os.path.dirname(__file__))
from check_issuer_power import fetch_json, read_abi, read_controllers, read_role_members  # noqa: E402
from lib.issuer_power import has_any_restrictive_power, classify_functions  # noqa: E402
from lib.web3_utils import get_w3, call_raw, read_address_getter  # noqa: E402

COMETS = [
    (1, "0xc3d688B66703497DAA19211EEdff47f25384cdc3", "Ethereum L1 (cUSDCv3)", "https://ethereum-rpc.publicnode.com"),
    (8453, "0xb125E6687d4313864e53df431d5425969c15Eb2F", "Base (USDC market)", "https://mainnet.base.org"),
    (42161, "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf", "Arbitrum (native-USDC market)", "https://arb1.arbitrum.io/rpc"),
]
NUM_ASSETS_ABI = [{"name": "numAssets", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}]
ASSET_INFO_ABI = [{"name": "getAssetInfo", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint8"}],
                   "outputs": [{"type": "tuple", "components": [{"type": "uint8"}, {"type": "address"}, {"type": "address"},
                                                                 {"type": "uint64"}, {"type": "uint64"}, {"type": "uint64"},
                                                                 {"type": "uint64"}, {"type": "uint128"}]}]}]


def fetch_reserve_list():
    """[(chain_id, address, label)] -- each Comet's live baseToken() plus every live getAssetInfo(i)
    collateral, never hardcoded from a prior pass. Two different chains' assets at the same address
    (e.g. cbBTC, CREATE2-shared) are kept as SEPARATE entries -- the issuer's controllers may differ
    per deployment even at a shared address, exactly the discipline this project's own Steakhouse
    Safe cross-chain-config finding (2026-09-25) established."""
    out = []
    for chain_id, comet, label, rpc in COMETS:
        w3 = get_w3(rpc)
        base_token = read_address_getter(w3, comet, "baseToken")
        out.append((chain_id, base_token, f"{label}: base asset"))
        n = call_raw(w3, comet, NUM_ASSETS_ABI, "numAssets") or 0
        for i in range(n):
            info = call_raw(w3, comet, ASSET_INFO_ABI, "getAssetInfo", i)
            out.append((chain_id, info[1], f"{label}: collateral #{i}"))
    return out


def fetch_symbol(chain_id, address):
    from check_issuer_power import BLOCKSCOUT
    d = fetch_json(f"https://{BLOCKSCOUT[chain_id]}/api/v2/tokens/{address}")
    return (d or {}).get("symbol") or address[:10]


def analyse_one(w3, chain_id, address, source_label):
    symbol = fetch_symbol(chain_id, address)
    fns, getters, array_getters, name = read_abi(chain_id, address)
    if fns is None:
        return {"chain_id": chain_id, "address": address, "symbol": symbol, "source": source_label, "unread": True}
    families = classify_functions(fns)
    controllers = read_controllers(w3, chain_id, address, getters)
    role_members = read_role_members(w3, address, array_getters)
    return {
        "chain_id": chain_id, "address": address, "symbol": symbol, "source": source_label, "unread": False,
        "name": name, "families": families, "restrictive": has_any_restrictive_power(families),
        "controllers": controllers, "role_members": role_members,
    }


def main():
    reserves = fetch_reserve_list()
    print(f"{len(reserves)} base/collateral asset instances across 3 tracked Compound V3 Comet markets (live getAssetInfo(), never hardcoded)\n")

    w3_by_chain = {chain_id: get_w3(rpc) for chain_id, _, _, rpc in COMETS}
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda r: analyse_one(w3_by_chain[r[0]], r[0], r[1], r[2]), reserves))

    unread = [r for r in rows if r["unread"]]
    restrictive = [r for r in rows if not r["unread"] and r["restrictive"]]
    eoa_controlled = []
    seen = {}

    for r in sorted(rows, key=lambda r: (r["symbol"], r["chain_id"])):
        if r["unread"]:
            print(f"  [UNREAD] chain {r['chain_id']} {r['symbol']:10s} {r['address']} ({r['source']})")
            continue
        key = (r["chain_id"], r["address"].lower())
        dup_note = ""
        if key in seen:
            dup_note = f"  (SAME as {seen[key]}, not re-listed below)"
            print(f"\n{r['symbol']:10s} chain {r['chain_id']} ({r['source']}){dup_note}")
            continue
        seen[key] = r["source"]
        flag = " <-- freeze/seize/pause capable" if r["restrictive"] else ""
        print(f"\n{r['symbol']:10s} chain {r['chain_id']} ({r['name']}) -- {r['source']}{flag}")
        f = r["families"]
        if any(f.values()):
            print(f"    functions: freeze={f['freeze']} seize={f['seize']} pause={f['pause']} upgrade={f['upgrade']}")
        for getter, (holder, label) in r["controllers"].items():
            print(f"    {getter}() = {holder} [{label}]")
            if label == "EOA":
                eoa_controlled.append((r["symbol"], r["chain_id"], getter))
        for getter, members in r["role_members"].items():
            for m, label in members:
                print(f"    {getter}() = {m} [{label}]")
                if label == "EOA":
                    eoa_controlled.append((r["symbol"], r["chain_id"], getter))

    print(f"\n{len(reserves)} instances checked ({len(seen)} distinct chain+address pairs), {len(unread)} unread, {len(restrictive)} freeze/seize/pause-capable.")
    print(f"{len(eoa_controlled)} controller/role-member reads resolved to a bare EOA (no multisig): {eoa_controlled}")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
