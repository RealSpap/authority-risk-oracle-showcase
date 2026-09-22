#!/usr/bin/env python3
"""Read-only sweep of who OWNS the large Morpho vaults, V1 (MetaMorpho) and V2 (Vault V2), on the chains given by --chains.
The vault lists come from Morpho's public API (an indexer, not trusted for values); every owner is re-read on-chain
(eth_call owner(), then eth_getCode / Safe getThreshold+getOwners) and classified: EOA, EIP-7702 EOA (code 0xef0100...),
Safe t-of-n (a 1-of-1 Safe is resolved to its single signer), or another contract. Nothing is sent, no key.
    python3 chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py                       # Ethereum + Base, V1 >= $2M, V2 >= $1M
    python3 chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py --chains 4663,143,42161,999,4217,988,10,480 --min 250000
A chain whose RPC does not answer with the right chain id is skipped and named, an owner that could not be read is
reported as UNREAD: nothing is guessed."""
import argparse, collections, json, subprocess, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
API = "https://blue-api.morpho.org/graphql"
RPC = {1: ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"], 8453: ["https://base-rpc.publicnode.com", "https://base.drpc.org"],
       4663: ["https://rpc.mainnet.chain.robinhood.com"], 143: ["https://rpc.monad.xyz"], 42161: ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"],
       999: ["https://rpc.hyperliquid.xyz/evm"], 4217: ["https://rpc.tempo.xyz"], 988: ["https://rpc.stable.xyz"], 10: ["https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com"],
       480: ["https://worldchain-mainnet.g.alchemy.com/public", "https://480.rpc.thirdweb.com"], 137: ["https://polygon-bor-rpc.publicnode.com"], 130: ["https://mainnet.unichain.org"],
       5042: ["https://rpc.mainnet.arc.io"], 747474: ["https://rpc.katana.network"]}
ap = argparse.ArgumentParser()
ap.add_argument("--chains", default="1,8453")
ap.add_argument("--min", type=float, default=None, help="minimum deposits in USD for both V1 and V2 (default: V1 2M, V2 1M)")
ARGS = ap.parse_args()
CHAINS = [int(c) for c in ARGS.chains.split(",")]
V1_MIN, V2_MIN = (ARGS.min, ARGS.min) if ARGS.min else (2000000, 1000000)
def post(url, body, tries=5):
    for a in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"}), timeout=60))
        except Exception:
            time.sleep(1.2 * (a + 1))
    # last resort: curl (this Python's TLS library cannot reach some hosts, e.g. rpc.katana.network)
    try:
        out = subprocess.run(["curl", "-s", "-m", "60", "-X", "POST", "-H", "content-type: application/json", "-A", "Mozilla/5.0", "--data", json.dumps(body), url], capture_output=True, text=True, timeout=90)
        return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None
    except Exception:
        return None
def rpc(ch, m, p):
    for a in range(5):
        r = post(RPC[ch][a % len(RPC[ch])], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, tries=1)
        if r and r.get("result") is not None: return r["result"]
        time.sleep(0.8 * (a + 1))
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
def gql(q): return post(API, {"query": q})["data"]
v1 = [dict(v, ver="V1", usd=(v["state"] or {}).get("totalAssetsUsd") or 0) for v in gql('{ vaults(first: 200, where: { totalAssetsUsd_gte: %d, chainId_in: %s }, orderBy: TotalAssetsUsd, orderDirection: Desc) { items { address name listed warnings { type level } chain { id } state { totalAssetsUsd } } } }' % (V1_MIN, CHAINS))["vaults"]["items"]]
v2 = [dict(v, ver="V2", usd=v["totalAssetsUsd"] or 0) for v in gql('{ vaultV2s(first: 200, where: { totalAssetsUsd_gte: %d, chainId_in: %s }, orderBy: TotalAssetsUsd, orderDirection: Desc) { items { address name listed warnings { type level } chain { id } totalAssetsUsd timelocks { duration } } } }' % (V2_MIN, CHAINS))["vaultV2s"]["items"]]
vaults = v1 + v2
bad = []
for ch in sorted({v["chain"]["id"] for v in vaults}):
    got = None
    for u in RPC.get(ch, []):
        r = post(u, {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, tries=2)
        if r and r.get("result"): got = int(r["result"], 16); break
    if got != ch: bad.append(ch)
if bad: print(f"skipped (no RPC answering with the right chain id): {bad}")
vaults = [v for v in vaults if v["chain"]["id"] not in bad]
def owner_of(v):
    o = rpc(v["chain"]["id"], "eth_call", [{"to": v["address"], "data": sel("owner()")}, "latest"])
    return Web3.to_checksum_address("0x" + o[-40:]) if o else None
def kind(ch, a):
    code = rpc(ch, "eth_getCode", [a, "latest"])
    if code is None: return ("UNREAD", None, [])
    n = (len(code) - 2) // 2
    if n == 0: return ("EOA", None, [])
    if code.startswith("0xef0100"): return ("EOA-7702", None, [])
    thr, own = rpc(ch, "eth_call", [{"to": a, "data": "0xe75235b8"}, "latest"]), rpc(ch, "eth_call", [{"to": a, "data": "0xa0e67e2b"}, "latest"])
    if thr and own and len(thr) > 2 and len(own) > 130:
        h = own[2:]; k = int(h[64:128], 16)
        return ("Safe", int(thr, 16), ["0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(k)])
    return (f"contract({n}B)", None, [])
with ThreadPoolExecutor(8) as ex: owners = list(ex.map(owner_of, vaults))
uniq = sorted({(v["chain"]["id"], o) for v, o in zip(vaults, owners) if o})
with ThreadPoolExecutor(8) as ex: kinds = dict(zip(uniq, ex.map(lambda t: kind(*t), uniq)))
sole = {k: (k[0], Web3.to_checksum_address(v[2][0])) for k, v in kinds.items() if v[0] == "Safe" and v[1] == 1 and len(v[2]) == 1}
with ThreadPoolExecutor(4) as ex: signer = dict(zip(sole.values(), ex.map(lambda t: kind(*t), sole.values())))
def tier(k):
    kd = kinds[k]
    if kd[0] in ("EOA", "EOA-7702"): return "single key (" + kd[0] + ")"
    if kd[0] == "Safe" and kd[1] == 1: return "1-of-1 Safe, signer is " + signer[sole[k]][0]
    return f"Safe {kd[1]}-of-{len(kd[2])}" if kd[0] == "Safe" else kd[0]
def report(subset, label):
    tiers = collections.defaultdict(lambda: [0, 0.0])
    for v, o in subset:
        t = tier((v["chain"]["id"], o)) if o else "UNREAD"
        tiers[t][0] += 1; tiers[t][1] += v["usd"]
    total = sum(v["usd"] for v, _ in subset)
    single = sum(x for t, (n, x) in tiers.items() if t.startswith("single key") or t.startswith("1-of-1"))
    nsingle = sum(n for t, (n, x) in tiers.items() if t.startswith("single key") or t.startswith("1-of-1"))
    print(f"\n== {label}: {len(subset)} vaults, ${total/1e9:.2f}B")
    for t, (n, x) in sorted(tiers.items(), key=lambda kv: -kv[1][1])[:8]: print(f"  {t:40s} {n:3d} vaults ${x/1e6:7.0f}M")
    print(f"  owner is a single key: {nsingle} vaults, ${single/1e6:.0f}M = {100*single/max(total,1):.0f}% of this group")
    rows = sorted(((v["usd"], v, o) for v, o in subset if o and (tier((v['chain']['id'], o)).startswith("single key") or tier((v['chain']['id'], o)).startswith("1-of-1"))), key=lambda z: -z[0])
    for x, v, o in rows[:8]:
        red = [w["type"] for w in (v.get("warnings") or []) if w["level"] == "RED"]
        print(f"    {v['chain']['id']:>5} {v['ver']} {(v['name'] or '')[:28]:28s} ${x/1e6:6.0f}M {v['address']} {tier((v['chain']['id'], o))}; red warnings: {red}")
pairs = list(zip(vaults, owners))
print(f"{len(vaults)} vaults ({sum(1 for v in vaults if v['ver'] == 'V1')} V1 + {sum(1 for v in vaults if v['ver'] == 'V2')} V2), ${sum(v['usd'] for v in vaults)/1e9:.2f}B on chains {sorted({v['chain']['id'] for v in vaults})}")
report([(v, o) for v, o in pairs if v.get("listed")], "LISTED on Morpho (shown in its app)")
report([(v, o) for v, o in pairs if not v.get("listed")], "NOT listed (Morpho does not show them; many carry red warnings)")

print("\n== by chain (listed vaults only for the single-key column)")
pc = collections.defaultdict(lambda: [0, 0.0, 0, 0.0, 0, 0.0])
for v, o in pairs:
    r = pc[v["chain"]["id"]]; r[0] += 1; r[1] += v["usd"]
    if o and v.get("listed") and (tier((v["chain"]["id"], o)).startswith("single key") or tier((v["chain"]["id"], o)).startswith("1-of-1")): r[2] += 1; r[3] += v["usd"]
    if not v.get("listed"): r[4] += 1; r[5] += v["usd"]
for ch, (n, t, ns, ts, nu, tu) in sorted(pc.items(), key=lambda kv: -kv[1][1]):
    print(f"  chain {ch:>7}: {n:3d} vaults ${t/1e6:7.1f}M | listed single-key owner: {ns:2d} vaults ${ts/1e6:7.1f}M | unlisted: {nu:2d} vaults ${tu/1e6:6.1f}M")
