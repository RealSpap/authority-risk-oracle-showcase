#!/usr/bin/env python3
"""Read-only: who controls the LayerZero bridge configuration behind Plasma's ONE already-tracked
LayerZero-wired target -- chains/plasma-ecosystem/scorers.py's score_ethena_usde_oft_plasma()
(the Ethena USDe OFT, 0x5d3a1Ff2...). No other Plasma scorer is LayerZero-wired (Aave/Pendle/Euler/
Fluid/Telos-Euler-Earn/Yuzu are native deployments or use Chainlink/protocol-native price feeds,
not a LayerZero OApp) and none is introduced here -- this stays inside the 9 targets scorers.py
already tracks.

    python3 chains/plasma-ecosystem/scripts/sweep_plasma_layerzero_bridge_authority.py

Ports chains/ethereum-l1/scripts/sweep_layerzero_verifiers.py's method (read via the app's home
EndpointV2: delegates(oapp), then per remote path getReceiveLibrary + getUlnConfig) to this ONE
target instead of scanning LayerZero's whole OFT list -- narrower on purpose, deep on what's
already tracked, per this project's "depth, not breadth" rule.

Why this is a real gap and not just re-running an existing check: score_ethena_usde_oft_plasma()
reads owner()/pendingOwner() on the OFT contract itself -- the authority over the TOKEN's mint/
burn logic. It never reads the EndpointV2 side, which is a SEPARATE authority surface one hop
away: `delegates(oapp)` is who can change which DVNs (verifiers) must sign before a cross-chain
message is accepted -- LayerZero's OApp pattern deliberately allows this to be a DIFFERENT,
possibly weaker, key than owner() -- and the receive-library ULN config says how many independent
DVNs actually stand behind each remote chain's inbound path (a 1-DVN path is the exact failure
mode LayerZero's own sweep script above was written to find, after the April 2026 KelpDAO loss).

Every address is either the live output of scorers.score_ethena_usde_oft_plasma() (the already-
tracked target -- not a hardcoded copy that could drift) or freshly fetched this run from
LayerZero's own metadata API (metadata.layerzero-api.com, not cached), then independently
re-read on chain against https://rpc.plasma.to before being reported -- same convention as every
other script in this project. Remote chains probed are exactly the OTHER EVM ecosystems this
project already tracks (Ethereum L1, Arbitrum, Base) plus Hyperliquid -- chosen because they are
already-tracked, not because LayerZero's metadata says Plasma is wired to them (it doesn't list a
Plasma deployment for this OFT at all, see the printed WARNING below): this script empirically
probes each one on Plasma's own EndpointV2 rather than assuming a config exists. Nothing is sent,
no key."""
import json
import os
import sys
import urllib.request

from eth_abi import decode
from web3 import Web3

REPO_ROOT = os.environ.get("ARO_REPO_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "plasma-ecosystem"))
from web3_utils import get_w3, read_address_getter, safe_owners_and_threshold  # noqa: E402
import scorers  # noqa: E402 -- gives us the live, already-tracked target address, not a hardcoded copy

LZ_META = "https://metadata.layerzero-api.com/v1/metadata"
LZ_DVNS = "https://metadata.layerzero-api.com/v1/metadata/dvns"
# candidate remote chains: exactly this project's OTHER already-tracked EVM ecosystems -- used only
# to look up eids for path-probing, no new ecosystem is scored or added anywhere by this script
REMOTE_CANDIDATES = ["ethereum", "arbitrum", "base", "hyperliquid"]
DEAD_ADDR = "0x000000000000000000000000000000000000dead"


def http_json(url, tries=3):
    # LayerZero's metadata payload is a few MB; urllib occasionally truncates it (IncompleteRead) on
    # this network -- same robustness fallback sweep_layerzero_verifiers.py's own http() already uses.
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception:
            pass
    import subprocess
    out = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True, text=True, timeout=90)
    return json.loads(out.stdout)


# --- same small raw-eth_call helpers sweep_layerzero_verifiers.py uses for this exact struct-decoding
# pattern (kept identical on purpose: this is the method being ported, not reinvented) ---
def sel(sig):
    return "0x" + bytes(Web3.keccak(text=sig))[:4].hex()


def w(n):
    return hex(n)[2:].zfill(64)


def pad(a):
    return "0" * 24 + a[2:].lower()


def make_call(w3):
    def call(to, sig, args=""):
        # web3.py's .hex() here returns WITHOUT a "0x" prefix (unlike the raw JSON-RPC hex strings
        # sweep_layerzero_verifiers.py's own rpc()/call() helpers return) -- every downstream slice
        # below assumes the "0x..." form, so it is added back here rather than re-deriving every offset.
        return "0x" + w3.eth.call({"to": Web3.to_checksum_address(to), "data": sel(sig) + args}).hex()
    return call


def path_need(req, opt, thr, req_n, dvn_names):
    """How many independent DVNs must sign before this path is accepted, and whether it is blocked
    (a dead DVN is in the required or optional set, so it can never collect enough real signatures).
    `req_n` is the RAW requiredDVNCount field (255 is LayerZero's "unset" sentinel). Pure function,
    no network -- see selftest() below for the offline check on this exact logic."""
    nreq = 0 if req_n == 255 else req_n
    need = (nreq + thr) if (nreq or thr) else (len(req) + thr)
    dead = any(
        a.lower() == DEAD_ADDR or dvn_names.get(a.lower()) in ("LZDeadDVN", "lz-dead-dvn")
        for a in list(req) + list(opt)
    )
    return need, dead


def selftest():
    names = {"0xaaa": "LayerZero Labs", "0xbbb": "Nethermind", "0xdead1": "LZDeadDVN"}
    assert path_need(["0xaaa", "0xbbb"], [], 0, 2, names) == (2, False)
    assert path_need(["0xaaa"], ["0xbbb", "0xccc"], 1, 1, names) == (2, False)
    assert path_need(["0xdead1"], [], 0, 1, names) == (1, True), "name-matched dead DVN must block, not just the literal 0x..dead address"
    assert path_need([DEAD_ADDR], [], 0, 1, names) == (1, True), "literal 0x..dead address must also block"
    assert path_need([], [], 0, 255, names) == (0, False), "255 is the unset sentinel, not a real count of 255"
    print("selftest: OK")


def kind(w3, addr):
    if not addr or int(addr, 16) == 0:
        return "none"
    if len(w3.eth.get_code(Web3.to_checksum_address(addr))) == 0:
        return "EOA"
    owners_threshold = safe_owners_and_threshold(w3, addr, check_modules=False)
    if owners_threshold:
        owners, threshold = owners_threshold
        return f"Safe {threshold}-of-{len(owners)}"
    return f"contract({len(w3.eth.get_code(Web3.to_checksum_address(addr)))}B)"


def main():
    w3 = get_w3(scorers.DEFAULT_RPC)
    chain_id = w3.eth.chain_id
    print(f"Plasma RPC {scorers.DEFAULT_RPC}: chain id {chain_id} (expected {scorers.PLASMA_CHAIN_ID})")
    if chain_id != scorers.PLASMA_CHAIN_ID:
        sys.exit("chain id mismatch -- aborting, not scoring against the wrong network")

    # the already-tracked target, read live from the scorer itself (never hardcoded here)
    tracked = scorers.score_ethena_usde_oft_plasma(w3)
    oft = Web3.to_checksum_address(tracked["target"])
    print(f"\nAlready-tracked target: {tracked['label']} = {oft}")
    print(f"  scorer's own owner()-side authority: adminKeyScore={tracked['adminKeyScore']} multisigScore={tracked['multisigScore']} (from the OFT's own owner()/pendingOwner(), NOT the EndpointV2 side this script reads)")

    print("\nFetching LayerZero metadata live (not cached)...")
    meta = http_json(LZ_META)
    dvns = http_json(LZ_DVNS)
    plasma_dep = next((d for d in meta.get("plasma", {}).get("deployments", []) if d.get("version") == 2), None)
    if not plasma_dep:
        sys.exit("LayerZero metadata lists no EndpointV2 deployment for 'plasma' -- cannot proceed")
    endpoint = Web3.to_checksum_address(plasma_dep["endpointV2"]["address"])
    print(f"Plasma EndpointV2 (LayerZero metadata, fetched live): {endpoint}")

    oft_groups_have_plasma = False
    try:
        ofts = http_json("https://metadata.layerzero-api.com/v1/metadata/experiment/ofts/list")
        for _, groups in ofts.items():
            for g in groups:
                if "plasma" in (g.get("deployments") or {}):
                    oft_groups_have_plasma = True
    except Exception as e:  # noqa: BLE001 -- this is a secondary sanity check, not load-bearing
        print(f"  (could not check LayerZero's OFT registry for a Plasma entry: {e})")
    if not oft_groups_have_plasma:
        print("WARNING: LayerZero's own OFT metadata registry (the same one sweep_layerzero_verifiers.py "
              "scans) lists NO 'plasma' deployment anywhere for USDe/sUSDe/any OFT group, even though the "
              "token is live and source-verified on Plasmascan per the scorer's own docstring. This Plasma "
              "leg is invisible to LayerZero's own indexer -- everything below is read directly on-chain, "
              "not corroborated by that registry.")

    call = make_call(w3)

    # sanity: does the OFT contract itself agree this is its EndpointV2? (standard immutable getter on LZ V2 OApps)
    try:
        ep_raw = call(oft, "endpoint()")
        oft_endpoint = Web3.to_checksum_address("0x" + ep_raw[-40:]) if ep_raw and len(ep_raw) >= 42 else None
    except Exception:
        oft_endpoint = None
    if oft_endpoint:
        match = "MATCHES" if oft_endpoint == endpoint else "DOES NOT MATCH"
        print(f"OFT.endpoint() = {oft_endpoint} -- {match} LayerZero metadata's Plasma EndpointV2")
    else:
        print("OFT.endpoint() unreadable (not a standard getter on this build, or reverted) -- skipping that cross-check")

    # 1. delegates(oapp) -- the authority never read by the existing scorer
    dele_raw = call(endpoint, "delegates(address)", pad(oft))
    delegate = Web3.to_checksum_address("0x" + dele_raw[-40:]) if dele_raw and len(dele_raw) >= 42 and int(dele_raw, 16) != 0 else None
    owner_side = read_address_getter(w3, oft, "owner")  # re-read live, not parsed out of the scorer's notes text
    print(f"\nEndpointV2.delegates({oft}) = {delegate or '0x0 (unset -- falls back to owner() for config changes, per LayerZero default)'}")
    if delegate:
        delegate_kind = kind(w3, delegate)
        print(f"  delegate classified: {delegate_kind}")
        same_as_owner = delegate.lower() == owner_side.lower() if owner_side else None
        print(f"  delegate {'IS' if same_as_owner else 'is NOT (or unresolved vs.)'} the same address as owner() ({owner_side}) -- "
              f"{'no separate weaker key found' if same_as_owner else 'a SEPARATE key/committee controls DVN configuration from the one that controls the token'}")
    else:
        print("  no delegate set: owner() is also the address that must call the Endpoint's setConfig -- no separate weaker key, but also no separation of duties")

    # 2. per remote path: receive library + ULN config
    print("\nInbound verifier (DVN) configuration per remote path, read live off Plasma's EndpointV2/receive-library:")
    plasma_dvn_names = {a.lower(): d.get("canonicalName") or d.get("id") for a, d in (dvns.get("plasma", {}).get("dvns") or {}).items()}
    weakest = None
    any_path_found = False
    for ck in REMOTE_CANDIDATES:
        remote_dep = next((d for d in meta.get(ck, {}).get("deployments", []) if d.get("version") == 2 and d.get("stage") == "mainnet"), None)
        if not remote_dep:
            print(f"  {ck:11s}: no v2 mainnet deployment in LayerZero metadata, skipped")
            continue
        eid = int(remote_dep["eid"])
        lib_raw = call(endpoint, "getReceiveLibrary(address,uint32)", pad(oft) + w(eid))
        if not lib_raw or len(lib_raw) < 130 or int(lib_raw[2:66], 16) == 0:
            print(f"  {ck:11s} (eid {eid}): no receive library configured for this OApp -- no inbound path from here")
            continue
        libaddr = Web3.to_checksum_address("0x" + lib_raw[26:66])
        is_default = int(lib_raw[66:130], 16) == 1
        uln_raw = call(libaddr, "getUlnConfig(address,uint32)", pad(oft) + w(eid))
        if not uln_raw or uln_raw == "0x":
            print(f"  {ck:11s} (eid {eid}): receive library {libaddr} set but getUlnConfig unreadable")
            continue
        try:
            (confirmations, req_n, opt_n, thr, req, opt) = decode(
                ["(uint64,uint8,uint8,uint8,address[],address[])"], bytes.fromhex(uln_raw[2:])
            )[0]
        except Exception as e:  # noqa: BLE001
            print(f"  {ck:11s} (eid {eid}): ULN config present but undecodable ({e})")
            continue
        need, dead = path_need(req, opt, thr, req_n, plasma_dvn_names)
        names = [plasma_dvn_names.get(a.lower(), a[:10]) for a in req]
        opt_names = [plasma_dvn_names.get(a.lower(), a[:10]) for a in opt]
        any_path_found = True
        status = "BLOCKED (dead DVN in path)" if dead else f"{need} verifier(s) required to accept a message"
        print(f"  {ck:11s} (eid {eid}): receive lib {libaddr} ({'LayerZero default' if is_default else 'app-specific config'}), "
              f"confirmations={confirmations}, required DVNs={names or '[]'}, optional DVNs={opt_names or '[]'} (threshold {thr}) -- {status}")
        if not dead:
            weakest = need if weakest is None else min(weakest, need)

    print()
    if not any_path_found:
        print("RESULT: no inbound LayerZero path is configured from ANY of Plasma's sibling already-tracked "
              "ecosystems (Ethereum L1, Arbitrum, Base, Hyperliquid) for this OFT on Plasma's EndpointV2. "
              "Either the Plasma leg receives only from chains outside this project's tracked set, or it is "
              "not yet wired for inbound receipt at all -- worth a maintainer follow-up, not fabricated here.")
    else:
        print(f"RESULT: weakest OPEN inbound path found = {weakest} independent verifier(s). "
              f"{'A single verifier can approve a cross-chain mint into this OFT on Plasma -- the exact configuration LayerZero disabled its own DVN from signing for after the April 2026 KelpDAO loss.' if weakest is not None and weakest <= 1 else 'More than one independent verifier is required on every open path found.'}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
