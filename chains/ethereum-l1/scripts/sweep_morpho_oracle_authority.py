#!/usr/bin/env python3
"""Read-only: who can change the price oracle under Morpho's listed markets.
    python3 chains/ethereum-l1/scripts/sweep_morpho_oracle_authority.py [--min 1000000]
Morpho's public API lists each market's supply and oracle (an indexer: values are not trusted, addresses are re-read on chain).
1. Classifies listed markets by oracle type and supplied value.
2. For markets whose oracle type the API calls "Unknown", resolves each EIP-1167 clone to its implementation and lists the
   implementation's state-changing functions from its verified ABI on Blockscout (an ABI without owner or setter functions shows no admin key).
3. For markets on the Chainlink-based Morpho oracle, reads owner() of every feed proxy, groups the owners, opens each owner Safe
   (threshold, signers, modules, guard, version), compares the signer sets across chains, and reports the share of listed market supply
   that depends on at least one feed owned by the largest owner groups. A market counts once, whatever its number of feeds.
It measures a trust assumption at one instant. It says nothing about the identity of the signers, nor that Chainlink's process
around the keys is weak. Nothing is sent, no key."""
import argparse, collections, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://base-rpc.publicnode.com", 42161: "https://arbitrum-one-rpc.publicnode.com", 10: "https://optimism-rpc.publicnode.com",
       137: "https://polygon-bor-rpc.publicnode.com", 143: "https://rpc.monad.xyz", 999: "https://rpc.hyperliquid.xyz/evm", 747474: "https://rpc.katana.network",
       130: "https://mainnet.unichain.org", 4663: "https://rpc.mainnet.chain.robinhood.com"}
BLOCKSCOUT = {1: "eth.blockscout.com", 8453: "base.blockscout.com", 42161: "arbitrum.blockscout.com"}
ap = argparse.ArgumentParser(); ap.add_argument("--min", type=int, default=1000000); ARGS = ap.parse_args()
def curl(url, body=None):
    cmd = ["curl", "-s", "-m", "120", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body is not None else []) + [url]
    for _ in range(3):
        try:
            return json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
        except Exception: pass
def gql(q):
    r = curl("https://blue-api.morpho.org/graphql", {"query": q})
    if not r or not r.get("data"): sys.exit("Morpho API did not answer")
    return r["data"]
def rpc(ch, m, p):
    for _ in range(3):
        r = curl(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p})
        if r and r.get("result") is not None: return r["result"]
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
call = lambda ch, to, sig, args="": rpc(ch, "eth_call", [{"to": to, "data": sel(sig) + args}, "latest"])
items, skip = [], 0
while True:
    d = gql('{ markets(first: 500, skip: %d, where: { supplyAssetsUsd_gte: %d }) { items { marketId listed chain { id } oracle { address type data { ... on MorphoChainlinkOracleV2Data { baseFeedOne { address } baseFeedTwo { address } quoteFeedOne { address } quoteFeedTwo { address } } } } state { supplyAssetsUsd } } pageInfo { countTotal } } }' % (skip, ARGS.min))["markets"]
    items += d["items"]; skip += 500
    if skip >= d["pageInfo"]["countTotal"] or not d["items"]: break
L = [m for m in items if m["listed"]]; usd = lambda m: (m["state"] or {}).get("supplyAssetsUsd") or 0; tot = sum(usd(m) for m in L)
print(f"{len(L)} listed markets with ${ARGS.min/1e6:.0f}M or more of supply, ${tot/1e9:.2f}B")
by_type = collections.defaultdict(lambda: [0, 0.0])
for m in L: t = (m["oracle"] or {}).get("type"); by_type[t][0] += 1; by_type[t][1] += usd(m)
for t, (n, u) in sorted(by_type.items(), key=lambda kv: -kv[1][1]): print(f"  oracle type {str(t):22s} {n:4d} markets ${u/1e6:7.0f}M {100*u/tot:5.1f}%")
# 2. custom ("Unknown") oracles: clone implementation and its state-changing functions
unk = collections.defaultdict(float)
for m in L:
    if (m["oracle"] or {}).get("type") == "Unknown": unk[(m["chain"]["id"], m["oracle"]["address"])] += usd(m)
impls = collections.defaultdict(lambda: [0, 0.0])
for (ch, a), u in unk.items():
    code = (rpc(ch, "eth_getCode", [a, "latest"]) or "0x")[2:].lower() if ch in RPC else ""
    key = (ch, "0x" + code[20:60]) if code.startswith("363d3d373d3d3d363d73") else (ch, "not an EIP-1167 clone: " + a)
    impls[key][0] += 1; impls[key][1] += u
print(f"\ncustom oracles: {len(unk)} contracts resolve to {len(impls)} implementations")
for (ch, imp), (n, u) in sorted(impls.items(), key=lambda kv: -kv[1][1]):
    name, fn = "not queried (no explorer for this chain)", None
    if ch in BLOCKSCOUT and imp.startswith("0x"):
        d = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{imp}") or {}
        name = d.get("name"); fn = sorted({x["name"] for x in (d.get("abi") or []) if x.get("type") == "function" and x.get("stateMutability") not in ("view", "pure")})
    print(f"  chain {ch:>6} {n} contracts ${u/1e6:5.0f}M implementation {imp[:14]}.. {name}; state-changing functions: {fn}")
# 3. Chainlink-based Morpho oracle: owners of the feed proxies
feeds = {}; mk = []
for m in L:
    o = m["oracle"] or {}
    if o.get("type") != "ChainlinkOracleV2": continue
    dd = o.get("data") or {}; ch = m["chain"]["id"]
    fs = [(ch, f["address"].lower()) for f in (dd.get("baseFeedOne"), dd.get("baseFeedTwo"), dd.get("quoteFeedOne"), dd.get("quoteFeedTwo")) if f and f.get("address")]
    mk.append((usd(m), fs))
    for k in fs: feeds[k] = None
def owner(k):
    ch, a = k
    if ch not in RPC: return k, "no RPC"
    r = call(ch, a, "owner()")
    return k, (("0x" + r[-40:]) if r and len(r) >= 42 and int(r, 16) else "unread")
with ThreadPoolExecutor(8) as ex:
    for k, o in ex.map(owner, list(feeds)): feeds[k] = o
print(f"\nChainlink-based Morpho oracle: {len(mk)} markets, {len(feeds)} distinct feed contracts")
grp = collections.defaultdict(lambda: [0, 0.0])
for (ch, a), o in feeds.items(): grp[(ch, o)][0] += 1
for m_usd, fs in mk:
    for (ch, o) in {(k[0], feeds[k]) for k in fs}: grp[(ch, o)][1] += m_usd
top = [(k, v) for k, v in sorted(grp.items(), key=lambda kv: -kv[1][1]) if k[1].startswith("0x")][:4]
sets, info = {}, {}
for (ch, o), (n, u) in top:
    o = Web3.to_checksum_address(o); t, ow = call(ch, o, "getThreshold()"), call(ch, o, "getOwners()")
    if t and ow and len(ow) > 130:
        h = ow[2:]; k = int(h[64:128], 16); sets[(ch, o)] = {Web3.to_checksum_address("0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)]) for i in range(k)}
        ver = call(ch, o, "VERSION()"); mods = call(ch, o, "getModulesPaginated(address,uint256)", "0" * 63 + "1" + hex(20)[2:].zfill(64)); g = rpc(ch, "eth_getStorageAt", [o, "0x" + bytes(Web3.keccak(text="guard_manager.guard.address")).hex(), "latest"])
        kinds = collections.Counter("EOA" if (rpc(ch, "eth_getCode", [s, "latest"]) or "0x") == "0x" else "contract" for s in sets[(ch, o)])
        info[(ch, o)] = f"Safe {int(t, 16)}-of-{k} v{bytes.fromhex(ver[130:130 + 2 * int(ver[66:130], 16)]).decode() if ver and len(ver) > 130 else '?'}, modules {int(mods[2 + 128:2 + 192], 16) if mods and len(mods) >= 194 else '?'}, guard {'yes' if g and int(g, 16) else 'no'}, signers {dict(kinds)}"
    print(f"  chain {ch:>6} owner {o} owns {n:3d} feeds, ${u/1e6:6.0f}M of market supply (a market counts once per owner)  {info.get((ch, o), 'not a Safe or unread')}")
if len(sets) > 1:
    ks = list(sets); print("signers common to all listed owner Safes:", len(set.intersection(*sets.values())), "of", len(set.union(*sets.values())), "distinct")
owned = {o for (ch, o), _ in top}; hit = 0.0; nh = 0
for m_usd, fs in mk:
    if any(feeds[k] in {x.lower() for x in owned} for k in fs): hit += m_usd; nh += 1
unread = sum(m_usd for m_usd, fs in mk if any(feeds[k] in ("unread", "no RPC") for k in fs) and not any(feeds[k] in {x.lower() for x in owned} for k in fs))
print(f"\nmarkets with at least one feed owned by these Safes: {nh}, ${hit/1e9:.2f}B = {100*hit/tot:.0f}% of listed market supply; owners not read on a further ${unread/1e9:.2f}B")
