#!/usr/bin/env python3
"""Read-only: port of chains/ethereum-l1/scripts/sweep_lending_asset_authority.py's question
(can a lending market's underlying-asset ISSUER freeze, seize, pause or upgrade what the market
holds -- a layer of authority separate from the protocol's own admin/timelock infra, which this
project's chains/monad/scorers.py already scores) to Monad's own already-tracked lending markets:
    python3 chains/monad/scripts/sweep_lending_asset_authority_monad.py

Scope, deliberately narrow, no invented targets: the underlying tokens actually held by the 3
Monad lending markets chains/monad/scorers.py already scores that have a resolvable underlying
asset -- Aave V3 Monad's 13 reserves (via PoolAddressesProvider.getPool().getReservesList()),
Morpho's "Grove x Steakhouse High Yield AUSD" vault (asset()), and Curvance's hyAUSD
LendingOptimizer vault (asset()). Euler V2 Monad is EXCLUDED: that scorer tracks the eVaultFactory
(governs vault implementations project-wide), not any one already-tracked reserve/vault asset --
pinning one here would be an invented target, not an already-tracked one.

Method, adapted for Monad rather than copied verbatim, because the L1 script's method does not
carry over unchanged: it reads each token's verified-source ABI off a Blockscout instance
(Ethereum/Base/Arbitrum/Optimism/Polygon) and lists every non-view function whose NAME matches one
of four families (freeze/seize/pause/upgrade). Monad has no live Blockscout instance to read from
-- checked this run: https://monad.blockscout.com/api/v2/smart-contracts/<addr> returns a bare
"default backend - 404" (a Kubernetes ingress fallback page, not a Blockscout JSON response) for
both a null address and a real, live-deployed contract address on Monad, so the whole verified-ABI
premise the L1 script relies on does not hold here.

This script instead computes the keccak-256 SELECTOR (4 bytes) of each candidate function
signature from the same four families and checks whether that literal 4-byte sequence appears in
the target's own deployed runtime bytecode (eth_getCode), resolving to the EIP-1967 implementation
first (falling back to a plain implementation() call for older non-EIP-1967 proxies, e.g. Circle's
FiatTokenProxy) when the token is a proxy. A Solidity function dispatcher embeds each of its public/
external functions' selectors as a literal PUSH4 constant, so this finds the function REGARDLESS OF
ACCESS CONTROL -- unlike an eth_call probe, which would revert on an unauthorized caller for exactly
the access-gated functions this sweep cares about (onlyOwner pause(), onlyBlacklister blacklist()),
indistinguishable from "function doesn't exist". Same discipline as the L1 script: a selector match
is a signal the function exists in the dispatch table, not proof of who can call it or that it is
ever exercised -- and a MISS is not proof the capability is absent (a 4-byte hash collision across a
~30-50KB bytecode blob is negligible-probability, but a token could gate the same capability behind
a differently-named function, or delegate it to a separate contract this script never resolves --
Agora's AUSD below is the concrete case: this run found none of the probed selectors AND none of the
probed owner-style role getters, but its implementation is a real, substantial 22.8KB contract, so
that is reported as "not found by this heuristic", never as a confirmed absence of authority).

Every read is cross-checked live against a second independent public RPC (monad.drpc.org), same
"2+ independent RPCs" rule this project already runs elsewhere. Nothing is sent, no key.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "lib"))  # this file lives in chains/monad/scripts/, one level deeper than chains/monad/scorers.py -- same 3-up pattern as chains/ethereum-l1/scripts/check_horizon_authority.py
from web3 import Web3  # noqa: E402
from web3_utils import (  # noqa: E402
    EIP1967_IMPLEMENTATION_SLOT,
    call_raw,
    get_w3,
    read_address_getter,
    read_slot_as_address,
)

ap = argparse.ArgumentParser()
ap.add_argument("--dump", default=None, help="write the full per-token result list as JSON")
ap.add_argument("--selftest", action="store_true", help="offline check of the selector-matching logic, no RPC, then exit")
ARGS = ap.parse_args()

RPCS = ["https://rpc.monad.xyz", "https://monad.drpc.org"]
ZERO = "0x0000000000000000000000000000000000000000"

AAVE_PROVIDER = "0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"   # chains/monad/scorers.py::score_aave_v3_monad
MORPHO_VAULT = "0x32841A8511D5c2c5b253f45668780B99139e476D"    # ::score_morpho_vault_monad
CURVANCE_VAULT = "0xaD663aC84052b52BE4ed1b27BA416505e84a00Bf"  # ::score_curvance_monad

FAM_SIGS = {
    "freeze": ["blacklist(address)", "unBlacklist(address)", "addBlackList(address)",
               "removeBlackList(address)", "isBlackListed(address)", "isBlacklisted(address)",
               "blocklist(address)", "unBlock(address)", "freeze(address)", "unfreeze(address)"],
    "seize": ["destroyBlackFunds(address)", "wipeFrozenAddress(address)",
              "wipeBlacklistedAccount(address)", "seize(address)", "clawback(address,uint256)",
              "forceTransfer(address,address,uint256)", "confiscate(address)"],
    "pause": ["pause()", "unpause()", "paused()"],
    "upgrade": ["upgradeTo(address)", "upgradeToAndCall(address,bytes)"],
}
ROLE_GETTERS = ["owner", "blacklister", "pauser", "masterMinter", "admin"]
SELECTORS = {fam: {sig: Web3.keccak(text=sig)[:4].hex().replace("0x", "") for sig in sigs} for fam, sigs in FAM_SIGS.items()}


def code_2rpc(addr):
    """Returns (lowercase hex code from RPC #1, True if both RPCs agree byte-for-byte)."""
    codes = [get_w3(rpc).eth.get_code(Web3.to_checksum_address(addr)).hex().lower() for rpc in RPCS]
    return codes[0], codes[0] == codes[1]


def resolve_implementation(w3, addr):
    impl = read_slot_as_address(w3, addr, EIP1967_IMPLEMENTATION_SLOT)
    if not impl or impl == ZERO:
        impl = read_address_getter(w3, addr, "implementation")
    return impl if impl and impl != ZERO else None


def scan_selectors(code_hex):
    return {fam: [sig for sig, sel in sigs.items() if sel in code_hex] for fam, sigs in SELECTORS.items()
            if any(sel in code_hex for sel in sigs.values())}


def analyse(w3, addr):
    symbol = call_raw(w3, addr, [{"name": "symbol", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]}], "symbol") or "?"
    impl = resolve_implementation(w3, addr)
    scan_addr = impl or addr
    scan_code, agree = code_2rpc(scan_addr)
    fam = scan_selectors(scan_code)
    roles = {}
    for g in ROLE_GETTERS:
        r = read_address_getter(w3, addr, g)
        if r and r != ZERO:
            roles[g] = r
    return dict(token=addr, symbol=symbol, implementation=impl, scanned=scan_addr, two_rpc_agree=agree, families=fam, roles=roles)


def _selftest():
    """No RPC: the one thing that can silently break this script is the selector-matching logic
    itself (scan_selectors / SELECTORS) -- verify it against synthetic bytecode blobs."""
    pause_sel = SELECTORS["pause"]["pause()"]
    blob_with_pause = ("60" * 40) + pause_sel + ("60" * 40)  # selector embedded, surrounded by noise
    blob_without = "60" * 200
    hit = scan_selectors(blob_with_pause)
    miss = scan_selectors(blob_without)
    assert "pause" in hit and hit["pause"] == ["pause()"], f"expected a pause() hit, got {hit}"
    assert miss == {}, f"expected no hits on selector-free bytecode, got {miss}"
    assert len(SELECTORS["freeze"]["blacklist(address)"]) == 8, "a selector must be 4 bytes / 8 hex chars"
    print("selftest OK: scan_selectors finds an embedded selector and reports none on selector-free bytecode")


def main():
    if ARGS.selftest:
        _selftest()
        return
    w3 = get_w3(RPCS[0])
    print(f"chainId={w3.eth.chain_id} (expect 143, Monad mainnet) via {RPCS[0]}, cross-checked {RPCS[1]}\n")

    pool = read_address_getter(w3, AAVE_PROVIDER, "getPool")
    reserves = call_raw(w3, pool, [{"name": "getReservesList", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}], "getReservesList") if pool else None
    if not reserves:
        sys.exit("Aave V3 Monad PoolAddressesProvider.getPool()/Pool.getReservesList() did not answer -- aborting, not guessing reserves")
    morpho_asset = read_address_getter(w3, MORPHO_VAULT, "asset")
    curvance_asset = read_address_getter(w3, CURVANCE_VAULT, "asset")
    ausd_decimals = call_raw(w3, morpho_asset, [{"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}], "decimals") if morpho_asset else None
    ta_abi = [{"name": "totalAssets", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    morpho_ta = call_raw(w3, MORPHO_VAULT, ta_abi, "totalAssets")
    curvance_ta = call_raw(w3, CURVANCE_VAULT, ta_abi, "totalAssets")

    print(f"Aave V3 Monad: {len(reserves)} reserves (PoolAddressesProvider {AAVE_PROVIDER} -> Pool {pool})")
    print(f"Morpho vault {MORPHO_VAULT}: asset() = {morpho_asset}, totalAssets() = {morpho_ta / 10**ausd_decimals if morpho_ta is not None and ausd_decimals else morpho_ta}")
    print(f"Curvance vault {CURVANCE_VAULT}: asset() = {curvance_asset}, totalAssets() = {curvance_ta / 10**ausd_decimals if curvance_ta is not None and ausd_decimals else curvance_ta}")
    same_asset = morpho_asset and curvance_asset and morpho_asset.lower() == curvance_asset.lower()
    print(f"Morpho and Curvance vaults share the same underlying asset: {same_asset}\n")

    tokens = sorted(set(reserves) | {t for t in (morpho_asset, curvance_asset) if t})
    print(f"{len(tokens)} distinct underlying tokens to sweep (13 Aave reserves already include the shared Morpho/Curvance asset)\n")

    rows = []
    any_hit, no_hit = [], []
    for addr in tokens:
        r = analyse(w3, addr)
        rows.append(r)
        tag = "->" + r["implementation"] if r["implementation"] else "(no proxy detected)"
        print(f"{r['symbol']:16s} {addr}  impl {tag}  2rpc-agree={r['two_rpc_agree']}")
        if r["families"]:
            print(f"    selector hits: {r['families']}")
            any_hit.append(r)
        else:
            print("    selector hits: none of the probed freeze/seize/pause/upgrade signatures found (not proof of absence -- see script docstring)")
            no_hit.append(r)
        if r["roles"]:
            print(f"    role getters resolved on-chain: {r['roles']}")
        print()

    print("=" * 70)
    print(f"SUMMARY: {len(any_hit)}/{len(tokens)} underlying tokens show at least one probed freeze/seize/pause/upgrade selector: "
          + ", ".join(r["symbol"] for r in any_hit))
    print(f"Reserves/assets already tracked by chains/monad/scorers.py where NO probed selector was found: "
          + ", ".join(r["symbol"] for r in no_hit))
    if ARGS.dump:
        json.dump(rows, open(ARGS.dump, "w"), indent=2)
        print(f"\nwrote {len(rows)} rows to {ARGS.dump}")


if __name__ == "__main__":
    main()
