#!/usr/bin/env python3
"""Read-only: how many independent verifiers stand behind the value that LayerZero OFTs hold or can mint.
    python3 chains/ethereum-l1/scripts/sweep_layerzero_verifiers.py [--chains ethereum,base,...] [--top 150] [--dump rows.json]
LayerZero V2 accepts a cross-chain message once the verifiers (DVNs) an application chose have signed it. The April 2026 KelpDAO loss
($292M) was a 1-of-1 configuration; LayerZero has said its own DVN will no longer sign for applications configured that way.
This lists every OFT deployment in LayerZero's public metadata (metadata.layerzero-api.com, an indexer: addresses are re-read on chain), values
each one (an OFT Adapter by the token it locks, an OFT by its total supply, priced with DefiLlama), then for the largest reads, for every remote
chain the token also lives on, the receive library and its resolved ULN configuration on the local EndpointV2:
required DVN count, optional DVNs and threshold, DVN identities from LayerZero's DVN registry, and whether the configuration is the default
or the application's own. The weakest inbound path of a deployment is the one with the fewest verifiers that suffice.
It also reads who owns each application and who its delegate is (the address that can change the verifier set), and classifies them.
Only EVM chains with a public RPC are covered; Solana and others are not. It measures one instant and says nothing about the DVNs' own
security, only how many of them must agree. Nothing is sent, no key."""
import argparse, collections, json, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from eth_abi import decode
from web3 import Web3
RPC = {"ethereum": ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"], "base": ["https://base-rpc.publicnode.com", "https://base.drpc.org"],
       "bsc": ["https://bsc-rpc.publicnode.com"], "arbitrum": ["https://arbitrum-one-rpc.publicnode.com", "https://arb1.arbitrum.io/rpc"],
       "avalanche": ["https://avalanche-c-chain-rpc.publicnode.com", "https://api.avax.network/ext/bc/C/rpc"], "polygon": ["https://polygon-bor-rpc.publicnode.com"],
       "optimism": ["https://optimism-rpc.publicnode.com", "https://mainnet.optimism.io"]}
LLAMA = {"ethereum": "ethereum", "base": "base", "bsc": "bsc", "arbitrum": "arbitrum", "avalanche": "avax", "polygon": "polygon", "optimism": "optimism"}
ap = argparse.ArgumentParser(); ap.add_argument("--chains", default=",".join(RPC)); ap.add_argument("--top", type=int, default=150); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
CHAINS = [c for c in ARGS.chains.split(",") if c in RPC]
def http(url, body=None, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception:
            time.sleep(1.0 * (a + 1))
    try:
        cmd = ["curl", "-s", "-m", "60", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body is not None else []) + [url]
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=90).stdout)
    except Exception:
        return None
def rpc(ch, m, p):
    for a in range(3):
        for url in RPC[ch]:
            r = http(url, {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, tries=1)
            if r and r.get("result") is not None: return r["result"]
        time.sleep(0.7 * (a + 1))
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
w = lambda n: hex(n)[2:].zfill(64)
pad = lambda a: "0" * 24 + a[2:].lower()
call = lambda ch, to, sig, args="": rpc(ch, "eth_call", [{"to": to, "data": sel(sig) + args}, "latest"])
def num(h): return int(h, 16) if h and h != "0x" else None
OFTS = http("https://metadata.layerzero-api.com/v1/metadata/experiment/ofts/list")
META = http("https://metadata.layerzero-api.com/v1/metadata")
DVNS = http("https://metadata.layerzero-api.com/v1/metadata/dvns")
if not (OFTS and META and DVNS): sys.exit("LayerZero metadata API did not answer")
chain_info = {}
for ck in CHAINS:
    for dp in (META.get(ck) or {}).get("deployments", []):
        if dp.get("version") == 2 and dp.get("stage") == "mainnet" and dp.get("endpointV2"): chain_info[ck] = (int(dp["eid"]), Web3.to_checksum_address(dp["endpointV2"]["address"]))
eid_of = {}
for ck, v in META.items():
    for dp in v.get("deployments", []):
        if dp.get("version") == 2 and dp.get("stage") == "mainnet": eid_of[ck] = int(dp["eid"])
dvn_name = {}
for ck, v in DVNS.items():
    for a, d in (v.get("dvns") or {}).items(): dvn_name[(ck, a.lower())] = d.get("canonicalName") or d.get("id")
groups = collections.defaultdict(list)
for name, lst in OFTS.items():
    for g in lst:
        if g.get("endpointVersion") == "v2":
            for ck, x in g["deployments"].items(): groups[(name, id(g))].append((ck, x))
cands = []
for (name, gid), deps in groups.items():
    remote = {ck: eid_of.get(ck) for ck, _ in deps}
    for ck, x in deps:
        if ck in chain_info and x.get("type") in ("OFT", "OFT_ADAPTER"):
            cands.append(dict(name=name, chain=ck, type=x["type"], addr=Web3.to_checksum_address(x["address"]), inner=Web3.to_checksum_address(x["innerTokenAddress"]) if x.get("innerTokenAddress") else None, remote={k: v for k, v in remote.items() if k != ck and v}))
print(f"{len(cands)} OFT v2 deployments on {len(CHAINS)} chains ({sum(1 for c in cands if c['type'] == 'OFT_ADAPTER')} adapters, {sum(1 for c in cands if c['type'] == 'OFT')} OFTs)")
def value(c):
    ch = c["chain"]; tok = c["inner"] or c["addr"]
    dec = num(call(ch, tok, "decimals()")); raw = num(call(ch, tok, "balanceOf(address)", pad(c["addr"]))) if c["type"] == "OFT_ADAPTER" else num(call(ch, c["addr"], "totalSupply()"))
    return dict(c, token=tok, decimals=dec, amount=(raw / 10 ** dec) if raw is not None and dec is not None else None)
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(value, cands))
price = {}
for ch in CHAINS:
    toks = sorted({r["token"].lower() for r in rows if r["chain"] == ch and r["amount"]})
    for i in range(0, len(toks), 40):
        d = http("https://coins.llama.fi/prices/current/" + ",".join(f"{LLAMA[ch]}:{t}" for t in toks[i:i + 40]))
        for k, v in ((d or {}).get("coins") or {}).items(): price[(ch, k.split(":")[1].lower())] = v["price"]
for r in rows:
    p = price.get((r["chain"], r["token"].lower())); r["usd"] = r["amount"] * p if p is not None and r["amount"] is not None else None
priced = [r for r in rows if r["usd"]]
print(f"priced: {len(priced)} of {len(rows)} deployments, ${sum(r['usd'] for r in priced)/1e9:.2f}B "
      f"(adapters ${sum(r['usd'] for r in priced if r['type'] == 'OFT_ADAPTER')/1e9:.2f}B locked, OFTs ${sum(r['usd'] for r in priced if r['type'] == 'OFT')/1e9:.2f}B supply)")
top = sorted(priced, key=lambda r: -r["usd"])[:ARGS.top]
ULN = "(uint64,uint8,uint8,uint8,address[],address[])"
DEAD_ADDR = "0x000000000000000000000000000000000000dead"
def cfg(r, dst_ck, eid):
    ch = r["chain"]; ep = chain_info[ch][1]
    lib = call(ch, ep, "getReceiveLibrary(address,uint32)", pad(r["addr"]) + w(eid))
    if not lib or len(lib) < 130: return None
    libaddr = Web3.to_checksum_address("0x" + lib[26:66]); isdef = int(lib[66:130], 16) == 1
    out = call(ch, libaddr, "getUlnConfig(address,uint32)", pad(r["addr"]) + w(eid))
    if not out or out == "0x": return dict(eid=eid, lib=libaddr, default=isdef, err="config unread")
    try:
        conf, = decode([ULN], bytes.fromhex(out[2:]))
    except Exception:
        return dict(eid=eid, lib=libaddr, default=isdef, err="decode failed")
    conf_, req_n, opt_n, thr, req, opt = conf
    nreq = 0 if req_n == 255 else req_n
    # a path whose verifier set contains a dead DVN (LayerZero's LZDeadDVN or the 0x...dEaD address) can never be verified: it is blocked, not weak
    dead = any(x.lower() == DEAD_ADDR or dvn_name.get((ch, x.lower())) in ("LZDeadDVN", "lz-dead-dvn") for x in list(req) + list(opt))
    return dict(eid=eid, lib=libaddr, default=isdef, blocked=dead, confirmations=conf_, required=[a.lower() for a in req], optional=[a.lower() for a in opt], threshold=thr, need=nreq + thr if nreq or thr else len(req) + thr)
def read(r):
    paths = {}
    for k, eid in r["remote"].items():
        c = cfg(r, k, eid)
        if c: paths[k] = c
    ep = chain_info[r["chain"]][1]
    own = call(r["chain"], r["addr"], "owner()"); dlg = call(r["chain"], ep, "delegates(address)", pad(r["addr"]))
    return dict(r, paths=paths, owner=Web3.to_checksum_address("0x" + own[-40:]) if own and len(own) >= 42 else None, delegate=Web3.to_checksum_address("0x" + dlg[-40:]) if dlg and len(dlg) >= 42 else None)
with ThreadPoolExecutor(6) as ex: res = list(ex.map(read, top))
def weakest(r):
    ns = [p["need"] for p in r["paths"].values() if "need" in p and not p.get("blocked")]
    return min(ns) if ns else None
tot = sum(r["usd"] for r in res) or 1
print(f"\nthe {len(res)} largest deployments, ${tot/1e9:.2f}B; paths read: {sum(len(r['paths']) for r in res)}; deployments with no readable path: {sum(1 for r in res if weakest(r) is None)}")
by = collections.defaultdict(lambda: [0, 0.0])
for r in res:
    k = weakest(r); k = "unread" if k is None else "1 verifier" if k <= 1 else "2 verifiers" if k == 2 else "3 or more"
    by[k][0] += 1; by[k][1] += r["usd"]
blocked = sum(1 for r in res for p in r["paths"].values() if p.get("blocked")); print(f"paths through a dead DVN (blocked, left out of the weakest-path reading): {blocked}")
print("weakest OPEN inbound path, verifiers that suffice:")
for k in ("1 verifier", "2 verifiers", "3 or more", "unread"): print(f"  {k:12s} {by[k][0]:4d} deployments ${by[k][1]/1e6:8.0f}M {100*by[k][1]/tot:5.1f}%")
for typ in ("OFT_ADAPTER", "OFT"):
    s = [r for r in res if r["type"] == typ]; t = sum(r["usd"] for r in s) or 1
    one = [r for r in s if weakest(r) is not None and weakest(r) <= 1]
    print(f"  {typ}: {len(s)} deployments ${t/1e6:.0f}M, with a 1-verifier path {len(one)} (${sum(r['usd'] for r in one)/1e6:.0f}M, {100*sum(r['usd'] for r in one)/t:.0f}%)")
dflt = sum(1 for r in res for p in r["paths"].values() if p.get("default")); allp = sum(len(r["paths"]) for r in res)
print(f"configuration is the LayerZero default on {dflt} of {allp} paths ({100*dflt/max(allp,1):.0f}%); the application's own on the rest")
cnt = collections.Counter();
for r in res:
    seen = set()
    for p in r["paths"].values():
        for a in p.get("required", []) + p.get("optional", []): seen.add(dvn_name.get((r["chain"], a), a[:10]))
    for n in seen: cnt[n] += 1
print("DVNs used by at least one path of a deployment (deployments, of", len(res), "):", dict(cnt.most_common(8)))
lz = [r for r in res if any(p.get("required") and not p.get("blocked") and not p.get("optional") and len(p["required"]) == 1 and dvn_name.get((r['chain'], p["required"][0])) == "LayerZero Labs" for p in r["paths"].values())]
print(f"deployments with an open path whose only verifier is LayerZero Labs' DVN: {len(lz)}, ${sum(r['usd'] for r in lz)/1e6:.0f}M")
def kind(ch, a):
    if not a or int(a, 16) == 0: return "none"
    code = rpc(ch, "eth_getCode", [a, "latest"]) or "0x"
    if code == "0x": return "EOA"
    if code.startswith("0xef0100"): return "EOA-7702"
    t = call(ch, a, "getThreshold()"); o = call(ch, a, "getOwners()")
    if t and o and len(o) > 130: return f"Safe {int(t, 16)}-of-{int(o[2 + 64:2 + 128], 16)}"
    return f"contract({(len(code) - 2) // 2}B)"
pairs = sorted({(r["chain"], a) for r in res for a in (r["owner"], r["delegate"]) if a})
with ThreadPoolExecutor(8) as ex: kinds = dict(zip(pairs, ex.map(lambda t: kind(*t), pairs)))
def cls(k): return "EOA" if k.startswith("EOA") else "1-of-N Safe" if k.startswith("Safe 1-of") else "Safe" if k.startswith("Safe") else k.split("(")[0]
for role in ("owner", "delegate"):
    c = collections.defaultdict(lambda: [0, 0.0])
    for r in res:
        k = cls(kinds[(r["chain"], r[role])]) if r[role] else "unread"; c[k][0] += 1; c[k][1] += r["usd"]
    print(f"{role}:", {k: f"{n} (${u/1e6:.0f}M)" for k, (n, u) in sorted(c.items(), key=lambda kv: -kv[1][1])})
rank = lambda k: 0 if k.startswith("EOA") else 1 if k.startswith("Safe 1-of") else 2 if k.startswith("Safe") else 3 if k.startswith("contract") else 4
weaker = [r for r in res if r["owner"] and r["delegate"] and r["owner"] != r["delegate"] and rank(kinds[(r["chain"], r["delegate"])]) < rank(kinds[(r["chain"], r["owner"])])]
print(f"the delegate (who can change the verifier set) is a weaker account than the owner in {len(weaker)} deployments, ${sum(r['usd'] for r in weaker)/1e6:.0f}M; delegate is a plain EOA while the owner is a Safe or contract in {sum(1 for r in weaker if rank(kinds[(r['chain'], r['delegate'])]) == 0)} of them")
for r in sorted(weaker, key=lambda r: -r["usd"])[:5]: print(f"  {r['chain']:>9} {r['type'][:7]:7s} ${r['usd']/1e6:7.0f}M {r['name'][:12]:12s} owner {kinds[(r['chain'], r['owner'])]} delegate {kinds[(r['chain'], r['delegate'])]}")
print("\nlargest deployments with a 1-verifier inbound path:")
for r in sorted([r for r in res if weakest(r) is not None and weakest(r) <= 1], key=lambda r: -r["usd"])[:10]:
    ones = [k for k, p in r["paths"].items() if p.get("need") is not None and p["need"] <= 1 and not p.get("blocked")]
    print(f"  {r['chain']:>9} {r['type']:11s} ${r['usd']/1e6:7.0f}M {r['name'][:14]:14s} weak paths from {ones[:4]} owner {kinds.get((r['chain'], r['owner']), '-')} delegate {kinds.get((r['chain'], r['delegate']), '-')}")
if ARGS.dump: json.dump(res, open(ARGS.dump, "w"), default=str); print(f"\nwrote {len(res)} rows to {ARGS.dump}")
