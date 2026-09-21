#!/usr/bin/env python3
"""Read-only sweep of the Euler Earn vaults (a fork of MetaMorpho V1: owner, curator, guardian, timelock) on every chain
where Euler publishes a factory. Nothing is sent, no key.
    python3 chains/ethereum-l1/scripts/sweep_euler_earn.py [--min 250000] [--dump rows.json]
Factories come from Euler's own registry (github.com/euler-xyz/euler-interfaces, addresses/<chain id>/CoreAddresses.json and
PeripheryAddresses.json). Vaults are enumerated on-chain (getVaultListLength / getVaultListSlice), every role is re-read with
eth_call, deposits are totalAssets valued with DefiLlama's price for the asset (a vault whose asset has no price is counted
as "price unknown", never guessed), and `verified` is the factory perspective's isVerified(vault). A chain whose RPC does
not answer with the right chain id is named and skipped."""
import argparse, collections, json, subprocess, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://base-rpc.publicnode.com", 42161: "https://arb1.arbitrum.io/rpc", 143: "https://rpc.monad.xyz",
       999: "https://rpc.hyperliquid.xyz/evm", 130: "https://mainnet.unichain.org", 56: "https://bsc-rpc.publicnode.com", 146: "https://rpc.soniclabs.com",
       43114: "https://api.avax.network/ext/bc/C/rpc", 59144: "https://rpc.linea.build", 9745: "https://rpc.plasma.to"}
LLAMA = {1: "ethereum", 8453: "base", 42161: "arbitrum", 143: "monad", 999: "hyperliquid", 130: "unichain", 56: "bsc", 146: "sonic", 43114: "avax", 59144: "linea", 9745: "plasma"}
REG = "https://raw.githubusercontent.com/euler-xyz/euler-interfaces/master/addresses/%d/%s.json"
ap = argparse.ArgumentParser(); ap.add_argument("--min", type=float, default=250000); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
def http(url, body=None, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception:
            time.sleep(1.2 * (a + 1))
    if body is not None:
        try:
            o = subprocess.run(["curl", "-s", "-m", "60", "-X", "POST", "-H", "content-type: application/json", "-A", "Mozilla/5.0", "--data", json.dumps(body), url], capture_output=True, text=True, timeout=90)
            return json.loads(o.stdout) if o.returncode == 0 and o.stdout.strip() else None
        except Exception:
            return None
def rpc(ch, m, p):
    for a in range(4):
        r = http(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, tries=1)
        if r and r.get("result") is not None: return r["result"]
        time.sleep(0.8 * (a + 1))
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
call = lambda ch, to, sig, args="": rpc(ch, "eth_call", [{"to": to, "data": sel(sig) + args}, "latest"])
addr = lambda h: Web3.to_checksum_address("0x" + h[-40:]) if h and len(h) >= 42 else None
w = lambda n: hex(n)[2:].zfill(64)
hx = lambda x: int(x, 16) if x and x != "0x" else None   # an empty answer is unread, never zero
def kind(ch, a):
    code = rpc(ch, "eth_getCode", [a, "latest"])
    if code is None: return ("UNREAD", None, [])
    n = (len(code) - 2) // 2
    if n == 0: return ("EOA", None, [])
    if code.startswith("0xef0100"): return ("EOA-7702", None, [])
    thr, own = call(ch, a, "getThreshold()"), call(ch, a, "getOwners()")
    if thr and own and len(thr) > 2 and len(own) > 130:
        h = own[2:]; k = int(h[64:128], 16); return ("Safe", int(thr, 16), ["0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(k)])
    return (f"contract({n}B)", None, [])
vaults = []
for ch in RPC:
    got = http(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, tries=2)
    if not got or int(got["result"], 16) != ch: print(f"skipped chain {ch}: RPC did not answer with that chain id"); continue
    core, per = http(REG % (ch, "CoreAddresses")), http(REG % (ch, "PeripheryAddresses"))
    fac = (core or {}).get("eulerEarnFactory"); persp = (per or {}).get("eulerEarnFactoryPerspective")
    n = int(call(ch, fac, "getVaultListLength()") or "0x0", 16) if fac else 0
    if not n: continue
    r = call(ch, fac, "getVaultListSlice(uint256,uint256)", w(0) + w(n))
    if not r: print(f"chain {ch}: could not list vaults"); continue
    h = r[2:]; cnt = int(h[64:128], 16)
    for i in range(cnt): vaults.append({"chain": ch, "vault": addr(h[128 + 64 * i: 128 + 64 * (i + 1)]), "persp": persp})
def read(v):
    ch, a = v["chain"], v["vault"]; g = lambda s: call(ch, a, s)
    asset = addr(g("asset()")); ta = g("totalAssets()"); dec = call(ch, asset, "decimals()") if asset else None; sym = call(ch, asset, "symbol()") if asset else None
    ver = call(ch, v["persp"], "isVerified(address)", "0" * 24 + a[2:].lower()) if v["persp"] else None
    tl = hx(g("timelock()")); ta, dec, ver = hx(ta), hx(dec), hx(ver)
    return dict(v, owner=addr(g("owner()")), curator=addr(g("curator()")), guardian=addr(g("guardian()")), timelock=tl, asset=asset,
                assets=(ta / 10 ** dec) if ta is not None and dec is not None else None, verified=(ver == 1) if ver is not None else None)
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(read, vaults))
by_chain = collections.defaultdict(list)
for r in rows:
    if r["asset"]: by_chain[r["chain"]].append(r["asset"])
price = {}
for ch, assets in by_chain.items():
    keys = sorted(set(assets))
    for i in range(0, len(keys), 25):
        d = http("https://coins.llama.fi/prices/current/" + ",".join(f"{LLAMA[ch]}:{k}" for k in keys[i:i + 25]))
        for k, v in ((d or {}).get("coins") or {}).items(): price[(ch, k.split(":")[1].lower())] = v["price"]
for r in rows:
    p = price.get((r["chain"], (r["asset"] or "").lower())); r["usd"] = r["assets"] * p if p is not None and r["assets"] is not None else None
ZERO = "0x0000000000000000000000000000000000000000"
uniq = sorted({(r["chain"], a) for r in rows for a in (r["owner"], r["curator"], r["guardian"]) if a and a != ZERO and (r["usd"] or 0) >= ARGS.min})
with ThreadPoolExecutor(8) as ex: kinds = dict(zip(uniq, ex.map(lambda t: kind(*t), uniq)))
sole = {k: (k[0], Web3.to_checksum_address(v[2][0])) for k, v in kinds.items() if v[0] == "Safe" and v[1] == 1 and len(v[2]) == 1}
with ThreadPoolExecutor(4) as ex: signer = dict(zip(sole.values(), ex.map(lambda t: kind(*t), sole.values())))
def tier(ch, a):
    if not a or a == ZERO: return "none"
    kd = kinds.get((ch, a))
    if kd is None: return "not read (below the minimum)"
    if kd[0] in ("EOA", "EOA-7702"): return "single key (" + kd[0] + ")"
    if kd[0] == "Safe" and kd[1] == 1 and (ch, a) in sole: return "1-of-1 Safe, signer is " + signer[sole[(ch, a)]][0]
    if kd[0] == "Safe" and kd[1] == 1: return f"Safe 1-of-{len(kd[2])} (any one signer acts)"
    return f"Safe {kd[1]}-of-{len(kd[2])}" if kd[0] == "Safe" else kd[0]
big = [r for r in rows if (r["usd"] or 0) >= ARGS.min]
unpriced = [r for r in rows if r["usd"] is None]
print(f"{len(rows)} Euler Earn vaults found on {len({r['chain'] for r in rows})} chains; {len(big)} with deposits >= ${ARGS.min:,.0f} (${sum(r['usd'] for r in big)/1e6:,.0f}M); {len(unpriced)} with an unpriced asset")
tiers = collections.defaultdict(lambda: [0, 0.0]); zero_tl = [0, 0.0]; noguard = [0, 0.0]
for r in big:
    t = tier(r["chain"], r["owner"]); tiers[t][0] += 1; tiers[t][1] += r["usd"]
    if r["timelock"] == 0: zero_tl[0] += 1; zero_tl[1] += r["usd"]
    if not r["guardian"] or r["guardian"] == ZERO: noguard[0] += 1; noguard[1] += r["usd"]
for t, (n, x) in sorted(tiers.items(), key=lambda kv: -kv[1][1])[:9]: print(f"  owner {t:38s} {n:3d} vaults ${x/1e6:7.1f}M")
single = sum(x for t, (n, x) in tiers.items() if t.startswith("single key") or t.startswith("1-of-1"))
print(f"owner is a single key: ${single/1e6:.1f}M = {100*single/max(sum(r['usd'] for r in big), 1):.0f}% | timelock 0: {zero_tl[0]} vaults ${zero_tl[1]/1e6:.1f}M | no guardian: {noguard[0]} vaults ${noguard[1]/1e6:.1f}M")
print("\nlargest vaults with a single-key owner:")
for r in sorted((r for r in big if tier(r["chain"], r["owner"]).startswith(("single key", "1-of-1"))), key=lambda r: -r["usd"])[:10]:
    print(f"  {r['chain']:>6} ${r['usd']/1e6:6.1f}M {r['vault']} owner {tier(r['chain'], r['owner'])}; curator {tier(r['chain'], r['curator'])}; timelock {r['timelock']}s; guardian {'none' if not r['guardian'] or r['guardian'] == ZERO else tier(r['chain'], r['guardian'])}; verified {r['verified']}")
if ARGS.dump:
    out = [{"family": "euler-earn", "chain": r["chain"], "vault": r["vault"], "name": None, "usd": r["usd"] or 0, "listed": r["verified"], "owner": r["owner"], "owner_kind": tier(r["chain"], r["owner"]),
            "curator": r["curator"], "curator_kind": tier(r["chain"], r["curator"]), "guardian": r["guardian"], "timelock": r["timelock"]} for r in rows]
    json.dump(out, open(ARGS.dump, "w")); print(f"\nwrote {len(out)} rows to {ARGS.dump}")
