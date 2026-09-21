#!/usr/bin/env python3
"""Read-only: how many parties must agree before a Hyperlane warp route accepts a message, and who can change that rule.
    python3 chains/ethereum-l1/scripts/sweep_hyperlane_isms.py [--top 150] [--dump rows.json]
A Hyperlane token route (warp route) is a router contract per chain. It accepts a message when its Interchain Security Module (ISM) says so: the
router's own, or the Mailbox's default when the router sets none. ISMs nest (a routing ISM picks a module per origin chain, an aggregation ISM needs
k of n modules, a multisig ISM needs t of n validators). This reads the route list and the chain list from the public hyperlane-registry repository,
values each EVM router (a collateral router by the token it holds, a synthetic one by its supply, priced with DefiLlama), then for the largest reads,
for every other chain of the same route, the ISM tree the router would apply to a message from that chain, by calling the ISM's view functions with a
synthetic message. The weakest origin is the one where the fewest parties must be compromised: a multisig contributes its threshold, an aggregation
its k cheapest modules, a trusted-relayer ISM one party. It also reads the router's owner (the account that can replace the ISM) and classifies it.
Registry files are an indexer of deployments, addresses are re-read on chain; chains without a usable public RPC or price are counted as unread or
unpriced. Weighted multisig, CCIP-read, rollup-bridge ISMs and non-EVM routers are reported as unresolved, not guessed. It measures one instant and
says nothing about the validators' own security. Nothing is sent, no key."""
import argparse, collections, json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
import yaml
from eth_abi import decode, encode
from web3 import Web3
ap = argparse.ArgumentParser(); ap.add_argument("--top", type=int, default=150); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
RAW = "https://raw.githubusercontent.com/hyperlane-xyz/hyperlane-registry/main/"
LLAMA = {"ethereum": "ethereum", "base": "base", "bsc": "bsc", "arbitrum": "arbitrum", "optimism": "optimism", "polygon": "polygon", "avalanche": "avax", "gnosis": "xdai",
         "celo": "celo", "mantle": "mantle", "linea": "linea", "scroll": "scroll", "zksync": "era", "blast": "blast", "mode": "mode", "sonic": "sonic", "berachain": "berachain",
         "unichain": "unichain", "ink": "ink", "worldchain": "wc", "fraxtal": "fraxtal", "zeronetwork": "zero", "soneium": "soneium", "hyperevm": "hyperliquid"}
def curl(url, body=None, tries=3, raw=False):
    cmd = ["curl", "-s", "-m", "60", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body is not None else []) + [url]
    for a in range(tries):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True).stdout
            return out if raw else json.loads(out)
        except Exception:
            time.sleep(0.8 * (a + 1))
tree = curl("https://api.github.com/repos/hyperlane-xyz/hyperlane-registry/git/trees/main?recursive=1") or {}
paths = [x["path"] for x in tree.get("tree", [])]
route_files = [p for p in paths if p.startswith("deployments/warp_routes/") and p.endswith("-config.yaml")]
if not route_files: sys.exit("could not list the registry (GitHub API)")
def load(p):
    try: return yaml.safe_load(curl(RAW + p, raw=True))
    except Exception: return None
with ThreadPoolExecutor(8) as ex: cfgs = list(ex.map(load, route_files))
routers = []; chains_needed = set()
for p, c in zip(route_files, cfgs):
    for t in ((c or {}).get("tokens") or []):
        if str(t.get("standard", "")).startswith("Evm") and str(t.get("addressOrDenom", "")).startswith("0x"):
            routers.append(dict(route=p.split("/")[2] + "/" + p.split("/")[3].replace("-config.yaml", ""), chain=t["chainName"], std=t["standard"], addr=Web3.to_checksum_address(t["addressOrDenom"]),
                                coll=Web3.to_checksum_address(t["collateralAddressOrDenom"]) if str(t.get("collateralAddressOrDenom", "")).startswith("0x") else None, symbol=t.get("symbol"), decimals=t.get("decimals"),
                                siblings=[x["chainName"] for x in c["tokens"] if x["chainName"] != t["chainName"]]))
            chains_needed.add(t["chainName"])
        for x in (t.get("connections") or []): pass
        chains_needed.add(t["chainName"])
print(f"{len(route_files)} route config files; {len(routers)} EVM routers on {len({r['chain'] for r in routers})} chains")
def chain_info(name):
    m, a = load(f"chains/{name}/metadata.yaml"), load(f"chains/{name}/addresses.yaml")
    if not m: return name, None
    urls = [u["http"] for u in (m.get("rpcUrls") or []) if u.get("http") and "{" not in u["http"] and "YOUR" not in u["http"].upper()][:3]
    return name, dict(domain=m.get("domainId"), rpcs=urls, mailbox=(a or {}).get("mailbox"), protocol=m.get("protocol"), cg=m.get("gasCurrencyCoinGeckoId"))
allchains = set(chains_needed) | {s for r in routers for s in r["siblings"]}
with ThreadPoolExecutor(8) as ex: CH = dict(ex.map(chain_info, sorted(allchains)))
def rpc(ch, m, p):
    info = CH.get(ch)
    for url in (info or {}).get("rpcs", []):
        r = curl(url, {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, tries=1)
        if r and r.get("result") is not None: return r["result"]
        if r and r.get("error") and "revert" in json.dumps(r["error"]).lower(): return "REVERT"   # a reverted view call is an answer, not a network failure
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()[0:8]
def call(ch, to, sig, args=b""):
    return rpc(ch, "eth_call", [{"to": to, "data": sel(sig) + args.hex()}, "latest"])
def num(h): return int(h, 16) if h and h not in ("0x", "REVERT") else None
def value(r):
    ch = r["chain"]
    if ch not in CH or not CH[ch] or not CH[ch]["rpcs"]: return dict(r, usd=None, why="no rpc")
    tok = r["coll"]; dec = r["decimals"]   # the registry's decimals are only a fallback: a token's own decimals() decide the value
    try:
        if r["std"].endswith("Synthetic") or "Synthetic" in r["std"]: raw = num(call(ch, r["addr"], "totalSupply()")); tok = r["addr"]
        elif r["std"] == "EvmHypNative": raw = num(rpc(ch, "eth_getBalance", [r["addr"], "latest"])); tok = None
        elif tok: raw = num(call(ch, tok, "balanceOf(address)", bytes.fromhex("00" * 12 + r["addr"][2:])))
        else: raw = None
    except Exception:
        raw = None
    if r["std"] == "EvmHypNative": dec = 18
    else:
        onchain = num(call(ch, tok, "decimals()")) if tok else None
        dec = onchain if onchain is not None else dec
    if raw is None or dec is None: return dict(r, usd=None, why="unread")
    return dict(r, token=tok, amount=raw / 10 ** dec, usd=None)
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(value, routers))
price = {}
by = collections.defaultdict(set)
for r in rows:
    if r.get("token") and r["chain"] in LLAMA: by[r["chain"]].add(r["token"].lower())
for ch, toks in by.items():
    toks = sorted(toks)
    for i in range(0, len(toks), 40):
        d = curl("https://coins.llama.fi/prices/current/" + ",".join(f"{LLAMA[ch]}:{t}" for t in toks[i:i + 40])) or {}
        for k, v in (d.get("coins") or {}).items(): price[(ch, k.split(":")[1].lower())] = v["price"]
for r in rows:
    if r.get("amount") is None: continue
    if r.get("token"): p = price.get((r["chain"], r["token"].lower()))
    else:
        p = None
        d = curl(f"https://coins.llama.fi/prices/current/coingecko:{CH[r['chain']]['cg']}") if CH.get(r["chain"]) and CH[r["chain"]].get("cg") else None
        p = ((d or {}).get("coins") or {}).get(f"coingecko:{CH[r['chain']]['cg']}", {}).get("price") if d else None
    r["usd"] = r["amount"] * p if p is not None else None
priced = [r for r in rows if r.get("usd")]
print(f"priced routers: {len(priced)} of {len(rows)}, ${sum(r['usd'] for r in priced)/1e9:.2f}B "
      f"(collateral held ${sum(r['usd'] for r in priced if 'Collateral' in r['std'] or 'Native' in r['std'] or 'Lockbox' in r['std'])/1e9:.2f}B, synthetic supply ${sum(r['usd'] for r in priced if 'Synthetic' in r['std'])/1e9:.2f}B)")
top = sorted(priced, key=lambda r: -r["usd"])[:ARGS.top]
MT = {1: "routing", 2: "aggregation", 3: "legacy multisig", 4: "merkle multisig", 5: "message-id multisig", 6: "null", 7: "ccip-read", 8: "arb-l2-to-l1", 9: "weighted merkle multisig", 10: "weighted message-id multisig", 11: "op-l2-to-l1"}
def msg(origin, dest, recipient): return bytes([3]) + (0).to_bytes(4, "big") + origin.to_bytes(4, "big") + b"\0" * 32 + dest.to_bytes(4, "big") + bytes.fromhex("00" * 12 + recipient[2:])
cache = {}
def resolve(ch, ism, m, depth=0):
    key = (ch, ism, m[5:9], depth)
    if key in cache: return cache[key]
    out = dict(need=None, desc="unresolved", vals=set(), types=set(), blocked=False)
    if depth > 8 or not ism or int(ism, 16) == 0: cache[key] = out; return out
    t = num(call(ch, ism, "moduleType()")); name = MT.get(t, f"type {t}"); out["types"].add(name)
    try:
        if t == 1:
            r = call(ch, ism, "route(bytes)", encode(["bytes"], [m]))
            if r == "REVERT": out = dict(need=None, desc="no module set for this origin, messages refused", vals=set(), types={name}, blocked=True)
            elif r: k = resolve(ch, Web3.to_checksum_address("0x" + r[-40:]), m, depth + 1); out = dict(k, types=k["types"] | {name})
        elif t == 2:
            r = call(ch, ism, "modulesAndThreshold(bytes)", encode(["bytes"], [m]))
            mods, thr = decode(["address[]", "uint8"], bytes.fromhex(r[2:]))
            kids = [resolve(ch, Web3.to_checksum_address(x), m, depth + 1) for x in mods]
            open_kids = [k for k in kids if not k["blocked"]]; ns = sorted(k["need"] for k in open_kids if k["need"] is not None)
            desc = f"{thr} of {len(mods)} modules [" + "; ".join(k["desc"] for k in kids) + "]"
            vals = set().union(*[k["vals"] for k in kids]) if kids else set(); types = set().union(*[k["types"] for k in kids]) | {name}
            if len(open_kids) < thr: out = dict(need=None, desc="blocked: " + desc, vals=vals, types=types, blocked=True)
            else: out = dict(need=sum(ns[:thr]) if len(ns) >= thr else None, desc=desc, vals=vals, types=types, blocked=False)
        elif t in (3, 4, 5):
            r = call(ch, ism, "validatorsAndThreshold(bytes)", encode(["bytes"], [m]))
            vals, thr = decode(["address[]", "uint8"], bytes.fromhex(r[2:]))
            out = dict(need=thr, desc=f"{thr}-of-{len(vals)} validators", vals={v.lower() for v in vals}, types={name}, blocked=False)
        elif t == 6:
            tr = call(ch, ism, "trustedRelayer()")
            if tr and tr != "REVERT": out = dict(need=1, desc="trusted relayer (1 party)", vals=set(), types={"trusted relayer"}, blocked=False)
            else: out = dict(need=0, desc="null or pausable ISM (no verification)", vals=set(), types={name}, blocked=False)
        else:
            out = dict(need=None, desc=name, vals=set(), types={name}, blocked=False)
    except Exception:
        out = dict(need=None, desc="unresolved", vals=set(), types=out["types"], blocked=False)
    cache[key] = out; return out
def kind(ch, a):
    if not a or int(a, 16) == 0: return "none"
    code = rpc(ch, "eth_getCode", [a, "latest"]) or "0x"
    if code == "0x": return "EOA"
    if code.startswith("0xef0100"): return "EOA-7702"
    t, o = call(ch, a, "getThreshold()"), call(ch, a, "getOwners()")
    if t and t != "0x" and o and len(o) > 130: return f"Safe {int(t, 16)}-of-{int(o[2 + 64:2 + 128], 16)}"
    return f"contract({(len(code) - 2) // 2}B)"
def read(r):
    ch = r["chain"]; info = CH[ch]; dest = info["domain"]
    own_ism = call(ch, r["addr"], "interchainSecurityModule()"); own_ism = ("0x" + own_ism[-40:]) if own_ism and len(own_ism) >= 42 else None
    mb = call(ch, r["addr"], "mailbox()"); mb = ("0x" + mb[-40:]) if mb and len(mb) >= 42 else info.get("mailbox")
    default = False
    ism = own_ism if own_ism and int(own_ism, 16) else None
    if ism is None and mb:
        d = call(ch, Web3.to_checksum_address(mb), "defaultIsm()"); ism = ("0x" + d[-40:]) if d and len(d) >= 42 else None; default = True
    per = {}
    for s in r["siblings"]:
        if CH.get(s) and CH[s].get("domain") is not None and ism: per[s] = resolve(ch, Web3.to_checksum_address(ism), msg(int(CH[s]["domain"]), int(dest), r["addr"]))
    ow = call(ch, r["addr"], "owner()")
    return dict(r, ism=ism, default_ism=default, paths=per, owner=("0x" + ow[-40:]) if ow and len(ow) >= 42 and int(ow, 16) else None)
with ThreadPoolExecutor(6) as ex: res = list(ex.map(read, top))
def weakest(r):
    ns = [p["need"] for p in r["paths"].values() if p["need"] is not None and not p["blocked"]]
    return min(ns) if ns else None
tot = sum(r["usd"] for r in res) or 1
print(f"origins whose messages are refused (no module set, or fewer open modules than the threshold): {sum(1 for r in res for p in r['paths'].values() if p['blocked'])} of {sum(len(r['paths']) for r in res)} paths read")
print(f"\nthe {len(res)} largest routers, ${tot/1e9:.2f}B; paths read {sum(len(r['paths']) for r in res)}; routers whose ISM could not be resolved for any origin: {sum(1 for r in res if weakest(r) is None)} (${sum(r['usd'] for r in res if weakest(r) is None)/1e6:.0f}M)")
b = collections.defaultdict(lambda: [0, 0.0])
for r in res:
    k = weakest(r); k = "unresolved" if k is None else "1 party" if k <= 1 else "2 parties" if k == 2 else "3 parties" if k == 3 else "4 or more"
    b[k][0] += 1; b[k][1] += r["usd"]
print("weakest origin, parties that must be compromised:")
for k in ("1 party", "2 parties", "3 parties", "4 or more", "unresolved"): print(f"  {k:11s} {b[k][0]:4d} routers ${b[k][1]/1e6:8.0f}M {100*b[k][1]/tot:5.1f}%")
print(f"router uses the Mailbox's default ISM: {sum(1 for r in res if r['default_ism'])} routers (${sum(r['usd'] for r in res if r['default_ism'])/1e6:.0f}M)")
types = collections.Counter();
for r in res:
    seen = set()
    for p in r["paths"].values(): seen |= p["types"]
    for t in seen: types[t] += 1
print("ISM types met on at least one path (routers):", dict(types.most_common()))
vc = collections.Counter()
for r in res:
    seen = set()
    for p in r["paths"].values(): seen |= p["vals"]
    for v in seen: vc[v] += 1
print(f"distinct validator addresses across those routers: {len(vc)}; the most shared appear in {vc.most_common(1)[0][1] if vc else 0} routers; top five: {[c for _, c in vc.most_common(5)]}")
pairs = sorted({(r["chain"], r["owner"]) for r in res if r["owner"]})
with ThreadPoolExecutor(8) as ex: kinds = dict(zip(pairs, ex.map(lambda t: kind(*t), pairs)))
cls = lambda k: "EOA" if k.startswith("EOA") else "1-of-N Safe" if k.startswith("Safe 1-of") else "Safe" if k.startswith("Safe") else k.split("(")[0]
c = collections.defaultdict(lambda: [0, 0.0])
for r in res:
    k = cls(kinds[(r["chain"], r["owner"])]) if r["owner"] else "unread"; c[k][0] += 1; c[k][1] += r["usd"]
print("owner of the router (can replace the ISM):", {k: f"{n} (${u/1e6:.0f}M)" for k, (n, u) in sorted(c.items(), key=lambda kv: -kv[1][1])})
print("\nlargest routers whose weakest origin needs 2 parties or fewer:")
for r in sorted([r for r in res if weakest(r) is not None and weakest(r) <= 2], key=lambda r: -r["usd"])[:12]:
    w = min((p for p in r["paths"].values() if p["need"] is not None and not p["blocked"]), key=lambda p: p["need"])
    print(f"  {r['chain']:>10} ${r['usd']/1e6:7.0f}M {r['route'][:34]:34s} {'default' if r['default_ism'] else 'own':7s} weakest: {w['desc'][:70]}; owner {kinds.get((r['chain'], r['owner']), '-')}")
if ARGS.dump: json.dump(res, open(ARGS.dump, "w"), default=lambda o: sorted(o) if isinstance(o, set) else str(o)); print(f"\nwrote {len(res)} rows to {ARGS.dump}")
