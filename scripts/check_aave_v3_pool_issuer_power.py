#!/usr/bin/env python3
"""Issuer power (freeze/seize/pause/upgrade + controller identity) for every reserve asset of the
Aave V3 Ethereum Pool -- the SAME already-tracked, already-scored target `score_aave_v3_pool()`
covers ($14.77B TVL, `chains/ethereum-l1/scorers.py`). ADDED 2026-09-26, extending today's own
`check_issuer_power.py` (built for the 9 tracked Morpho V1 vaults' 4 underlying assets) to a much
bigger, already-scored surface: a depositor's collateral or borrowed position can be frozen, seized,
or paused by ITS OWN issuer regardless of anything Aave's governance decides -- a risk this oracle's
existing `score_aave_v3_pool()` composite says nothing about (it scores the Pool's OWN admin/
multisig/timelock/oracle authority, not the tokens it lists).

Live: Aave V3 Ethereum Pool's own `getReservesList()` (67 reserves, read 2026-09-26 -- NOT
hardcoded from any prior research doc), then the exact same Blockscout-ABI + controller-getter +
role-member-getter classification `scripts/check_issuer_power.py` already built and tested today,
reused here (not reimplemented) via direct import. Nothing is sent, no key.

    python3 scripts/check_aave_v3_pool_issuer_power.py

Disclosed only -- same precedent as check_issuer_power.py and every other extension this week: no
`adminKeyScore`/`multisigScore`/`timelockScore`/`AuthorityScore` change, no on-chain push.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
sys.path.insert(0, os.path.dirname(__file__))
from check_issuer_power import fetch_json, read_abi, read_controllers, read_role_members  # noqa: E402
from lib.issuer_power import has_any_restrictive_power, classify_functions  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402

CHAIN_ID = 1
BLOCKSCOUT = "eth.blockscout.com"
RPC = "https://ethereum-rpc.publicnode.com"
POOL_ADDRESSES_PROVIDER = "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"

_POOL_ABI = [{"name": "getPool", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}]
_RESERVES_ABI = [{"name": "getReservesList", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]


def fetch_reserve_list(w3):
    """Live `PoolAddressesProvider.getPool()` then `Pool.getReservesList()` -- never hardcoded, the
    reserve list changes as Aave governance lists/delists assets."""
    from web3 import Web3
    provider = w3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESSES_PROVIDER), abi=_POOL_ABI)
    pool_addr = provider.functions.getPool().call()
    pool = w3.eth.contract(address=Web3.to_checksum_address(pool_addr), abi=_RESERVES_ABI)
    return pool.functions.getReservesList().call()


def fetch_symbol(address):
    d = fetch_json(f"https://{BLOCKSCOUT}/api/v2/tokens/{address}")
    return (d or {}).get("symbol") or address[:10]


def analyse_one(w3, address):
    symbol = fetch_symbol(address)
    fns, getters, array_getters, name = read_abi(CHAIN_ID, address)
    if fns is None:
        return {"address": address, "symbol": symbol, "unread": True}
    families = classify_functions(fns)
    controllers = read_controllers(w3, CHAIN_ID, address, getters)
    role_members = read_role_members(w3, address, array_getters)
    return {
        "address": address, "symbol": symbol, "unread": False, "name": name,
        "families": families, "restrictive": has_any_restrictive_power(families),
        "controllers": controllers, "role_members": role_members,
    }


def main():
    w3 = get_w3(RPC)
    reserves = fetch_reserve_list(w3)
    print(f"{len(reserves)} reserve assets on the Aave V3 Ethereum Pool (live getReservesList(), {POOL_ADDRESSES_PROVIDER})\n")

    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda a: analyse_one(w3, a), reserves))

    unread = [r for r in rows if r["unread"]]
    restrictive = [r for r in rows if not r["unread"] and r["restrictive"]]
    eoa_controlled = []

    for r in sorted(rows, key=lambda r: r["symbol"]):
        if r["unread"]:
            print(f"  [UNREAD] {r['symbol']:10s} {r['address']}")
            continue
        flag = " <-- freeze/seize/pause capable" if r["restrictive"] else ""
        print(f"\n{r['symbol']:10s} ({r['name']}){flag}")
        f = r["families"]
        if any(f.values()):
            print(f"    functions: freeze={f['freeze']} seize={f['seize']} pause={f['pause']} upgrade={f['upgrade']}")
        for getter, (holder, label) in r["controllers"].items():
            print(f"    {getter}() = {holder} [{label}]")
            if label == "EOA":
                eoa_controlled.append((r["symbol"], getter))
        for getter, members in r["role_members"].items():
            for m, label in members:
                print(f"    {getter}() = {m} [{label}]")
                if label == "EOA":
                    eoa_controlled.append((r["symbol"], getter))

    print(f"\n{len(reserves)} reserves checked, {len(unread)} unread, {len(restrictive)} freeze/seize/pause-capable.")
    print(f"{len(eoa_controlled)} controller/role-member reads resolved to a bare EOA (no multisig): {eoa_controlled}")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
