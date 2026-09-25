#!/usr/bin/env python3
"""Read-only look at WHO signs for the owner and curator Safes found by the vault sweeps: what kind of account each signer is
(plain EOA, EIP-7702-delegated EOA, Safe or other contract), and how many independent signer groups actually govern the deposits.
    python3 chains/ethereum-l1/scripts/sweep_safe_signers.py morpho_rows.json euler_rows.json [--dump signers.json]
Inputs are the row dumps of sweep_morpho_vault_owners.py --dump and sweep_euler_earn.py --dump. For every distinct listed owner or
curator Safe it reads getThreshold() and getOwners(), then eth_getCode for each distinct (chain, signer). Two Safes are put in the
same group when they share a plain EOA signer address (a contract signer can be a different contract on another chain, so it never
joins groups). Deposits are counted once per group. A signer that is a contract is not opened further: this reports one hop.
Nothing is sent, no key. A 7702 delegation is only reported (code starts with 0xef0100 and its target); whether the target is
harmful is not judged here."""
import argparse, collections, json, subprocess, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
RPC = {1: ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"], 8453: ["https://base-rpc.publicnode.com", "https://base.drpc.org"],
       4663: ["https://rpc.mainnet.chain.robinhood.com"], 143: ["https://rpc.monad.xyz"], 42161: ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"],
       999: ["https://rpc.hyperliquid.xyz/evm"], 4217: ["https://rpc.tempo.xyz"], 988: ["https://rpc.stable.xyz"], 10: ["https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com"],
       137: ["https://polygon-bor-rpc.publicnode.com"], 130: ["https://mainnet.unichain.org"], 747474: ["https://rpc.katana.network"],
       9745: ["https://rpc.plasma.to"], 56: ["https://bsc-rpc.publicnode.com"], 43114: ["https://api.avax.network/ext/bc/C/rpc"]}
ap = argparse.ArgumentParser(); ap.add_argument("rows", nargs="+"); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
def post(url, body):
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
        return json.load(urllib.request.urlopen(req, timeout=40))
    except Exception:
        try:   # this Python's TLS library cannot reach some hosts (rpc.katana.network): curl can
            o = subprocess.run(["curl", "-s", "-m", "40", "-X", "POST", "-H", "content-type: application/json", "-A", "Mozilla/5.0", "--data", json.dumps(body), url], capture_output=True, text=True, timeout=60)
            return json.loads(o.stdout) if o.returncode == 0 and o.stdout.strip() else None
        except Exception:
            return None
def rpc(ch, m, p):
    for a in range(3):
        for url in RPC[ch]:
            r = post(url, {"jsonrpc": "2.0", "id": 1, "method": m, "params": p})
            if r and r.get("result") is not None: return r["result"]
        time.sleep(0.8 * (a + 1))
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
call = lambda ch, to, data: rpc(ch, "eth_call", [{"to": to, "data": data}, "latest"])
def safe_owners(key):
    ch, a = key
    thr, own = call(ch, a, sel("getThreshold()")), call(ch, a, sel("getOwners()"))
    if not (thr and own and len(own) > 130): return None
    h = own[2:]; k = int(h[64:128], 16)
    return {"threshold": int(thr, 16), "owners": [Web3.to_checksum_address("0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)]) for i in range(k)]}
def classify(key):
    ch, a = key
    code = rpc(ch, "eth_getCode", [a, "latest"])
    if code is None: return ("unread", None)
    if code == "0x": return ("EOA", None)
    if code.startswith("0xef0100"): return ("7702", Web3.to_checksum_address("0x" + code[8:48]))
    nested = call(ch, a, sel("getThreshold()"))
    return ("Safe" if nested and nested != "0x" else "contract", None)
rows = []
for f in ARGS.rows: rows += json.load(open(f))
safes = {}
for r in rows:
    if r.get("listed") is False: continue
    for role in ("owner", "curator"):
        a, k = r.get(role), (r.get(role + "_kind") or "")
        if a and (k.startswith("Safe") or k.startswith("1-of-1 Safe")) and r["chain"] in RPC:
            s = safes.setdefault((r["chain"], Web3.to_checksum_address(a)), {"usd": 0.0, "roles": set()}); s["usd"] += r["usd"]; s["roles"].add(role)
keys = list(safes)
with ThreadPoolExecutor(6) as ex: own = dict(zip(keys, ex.map(safe_owners, keys)))
sig = sorted({(ch, o) for (ch, a), v in own.items() if v for o in v["owners"]})
with ThreadPoolExecutor(8) as ex: kind = dict(zip(sig, ex.map(classify, sig)))
# groups: union Safes that share a plain EOA signer address
parent = {k: k for k in keys}
def find(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
first = {}
for k in keys:
    v = own[k]
    if not v: continue
    for o in v["owners"]:
        if kind[(k[0], o)][0] in ("EOA", "7702"):
            if o in first: parent[find(k)] = find(first[o])
            else: first[o] = k
groups = collections.defaultdict(list)
for k in keys: groups[find(k)].append(k)
unread = [k for k in keys if own[k] is None]
print(f"{len(keys)} distinct listed owner/curator Safes; owners unread for {len(unread)}; {sum(len(v['owners']) for v in own.values() if v)} signer slots; {len(sig)} distinct (chain, signer) pairs")
print("signer account types (distinct chain+address):", dict(collections.Counter(v[0] for v in kind.values()).most_common()))
slots = collections.Counter(kind[(k[0], o)][0] for k in keys if own[k] for o in own[k]["owners"])
print("signer account types (by slot, a signer in two Safes counts twice):", dict(slots.most_common()))
d7702 = [(s, kind[s][1]) for s in sig if kind[s][0] == "7702"]
print(f"EIP-7702-delegated signers: {len(d7702)}; delegation targets: {dict(collections.Counter(t for _, t in d7702).most_common(4))}")
nested = [s for s in sig if kind[s][0] == "Safe"]
print(f"signers that are themselves Safes (nested): {len(nested)}; other contracts: {sum(1 for s in sig if kind[s][0] == 'contract')}")
tot = sum(v["usd"] for v in safes.values())
print(f"\nindependent signer groups (Safes sharing a plain-EOA signer are one group): {len(groups)} groups govern ${tot/1e9:.2f}B counted per Safe")
big = sorted(groups.values(), key=lambda g: -sum(safes[k]["usd"] for k in g))
sizes = [sum(safes[k]["usd"] for k in g) for g in big]
for g in big[:10]:
    signers = {o for k in g if own[k] for o in own[k]["owners"] if kind[(k[0], o)][0] in ("EOA", "7702")}
    print(f"  ${sum(safes[k]['usd'] for k in g)/1e6:7.0f}M  {len(g):3d} Safes on chains {sorted({k[0] for k in g})}  {len(signers)} distinct EOA signers; thresholds {sorted({own[k]['threshold'] for k in g if own[k]})}")
run, n = 0.0, 0
for s in sizes:
    run += s; n += 1
    if run >= tot / 2: break
print(f"the {n} largest groups hold half of the deposits counted; the {min(5, len(sizes))} largest hold {100*sum(sizes[:5])/tot:.0f}%")
multi = collections.Counter(o for k in keys if own[k] for o in own[k]["owners"] if kind[(k[0], o)][0] in ("EOA", "7702"))
top = [(o, n) for o, n in multi.most_common(6) if n > 1]
print("EOA signers appearing in the most Safes:", [(o[:10] + "..", n) for o, n in top])
if ARGS.dump:
    json.dump({"safes": [{"chain": k[0], "safe": k[1], "usd": v["usd"], "roles": sorted(v["roles"]), "threshold": (own[k] or {}).get("threshold"), "owners": (own[k] or {}).get("owners")} for k, v in safes.items()],
               "signers": [{"chain": s[0], "address": s[1], "kind": kind[s][0], "delegate": kind[s][1]} for s in sig]}, open(ARGS.dump, "w"))
    print(f"\nwrote {ARGS.dump}")
