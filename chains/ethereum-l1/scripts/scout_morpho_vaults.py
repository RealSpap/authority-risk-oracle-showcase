#!/usr/bin/env python3
"""Read-only scouting of the MetaMorpho vault layer (Ethereum + Base): who owns, curates and guards the biggest vaults,
re-read on-chain on two RPCs (the vault list itself comes from Morpho's public API, blue-api.morpho.org, an indexer that is
NOT trusted for the values: owner / curator / guardian / timelock are re-read with eth_call). Nothing is sent, no key.
    python3 chains/ethereum-l1/scripts/scout_morpho_vaults.py
Prints, per vault, the four values, then for each distinct controlling address whether it is a Safe (threshold, owners, modules),
how many vaults it controls, and the signer overlap between the Safes."""
import json, os, subprocess, sys, time, urllib.request
from collections import defaultdict
from web3 import Web3
RPC = {1: ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"], 8453: ["https://base-rpc.publicnode.com", "https://base.drpc.org"]}
API = "https://blue-api.morpho.org/graphql"
Q = '{ vaults(first: 40, where: { chainId_in: [1, 8453] }, orderBy: TotalAssetsUsd, orderDirection: Desc) { items { address name chain { id } state { totalAssetsUsd } } } }'
sel = lambda sig: "0x" + bytes(Web3.keccak(text=sig))[:4].hex()
S = {n: sel(n + "()") for n in ("owner", "curator", "guardian", "timelock")}
def post(url, body):
    for a in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"}), timeout=40))
        except Exception:
            time.sleep(1.5 * (a + 1))
def call(chain, to, data):
    vals = []
    for u in RPC[chain]:
        r = post(u, {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]})
        vals.append((r or {}).get("result"))
    return vals[0] if vals[0] == vals[1] else "DISAGREE:%s|%s" % tuple(vals)
def addr(h): return Web3.to_checksum_address("0x" + h[-40:]) if h and h.startswith("0x") and len(h) >= 42 else h
vaults = post(API, {"query": Q})["data"]["vaults"]["items"]
rows, ctl = [], defaultdict(list)
for v in vaults:
    ch, a = v["chain"]["id"], v["address"]
    r = {k: call(ch, a, s) for k, s in S.items()}
    row = dict(chain=ch, name=v["name"], vault=a, tvl=(v["state"] or {}).get("totalAssetsUsd") or 0,
               owner=addr(r["owner"]), curator=addr(r["curator"]), guardian=addr(r["guardian"]), timelock=(int(r["timelock"], 16) if r["timelock"] and r["timelock"].startswith("0x") else r["timelock"]))
    rows.append(row)
    for role in ("owner", "curator", "guardian"):
        if row[role] and row[role] != "0x0000000000000000000000000000000000000000" and str(row[role]).startswith("0x"):
            ctl[(ch, row[role], role)].append(row)
for r in rows:
    print(f"{r['chain']:>5} {r['name'][:30]:30s} ${r['tvl']/1e6:7.1f}M owner={str(r['owner'])[:10]} curator={str(r['curator'])[:10]} guardian={str(r['guardian'])[:10]} timelock={r['timelock']}")
print("\n== controlling addresses that hold a role on 2 or more vaults")
safes = {}
def safe(chain, a):
    k = (chain, a)
    if k in safes: return safes[k]
    thr, own, mods = call(chain, a, "0xe75235b8"), call(chain, a, "0xa0e67e2b"), call(chain, a, "0xcc2f8452" + "0" * 63 + "1" + "0" * 62 + "0a")
    if not (thr and thr.startswith("0x") and len(thr) > 2 and own and own.startswith("0x")):
        safes[k] = None; return None
    h = own[2:]; n = int(h[64:128], 16)
    safes[k] = (int(thr, 16), sorted("0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(n)), int(mods[2:][128:192], 16) if mods and mods.startswith("0x") and len(mods) > 194 else None)
    return safes[k]
for (ch, a, role), vs in sorted(ctl.items(), key=lambda kv: -sum(x["tvl"] for x in kv[1])):
    if len(vs) < 2: continue
    s = safe(ch, a)
    kind = f"Safe {s[0]}-of-{len(s[1])}, modules={s[2]}" if s else "not a Safe (EOA or other contract)"
    print(f"chain {ch} {role:8s} {a} controls {len(vs):2d} vaults, ${sum(x['tvl'] for x in vs)/1e6:6.0f}M, {kind}")
print("\n== signer overlap between the distinct Safes found (any role, any vault)")
found = {k: v for k, v in safes.items() if v}
keys = sorted(found)
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        a, b = set(found[keys[i]][1]), set(found[keys[j]][1])
        if a & b: print(f"  {keys[i][1][:10]}(chain {keys[i][0]}) and {keys[j][1][:10]}(chain {keys[j][0]}) share {len(a & b)} signer(s)")
print("\nSafes read:", {f"{k[0]}:{k[1][:10]}": f"{v[0]}-of-{len(v[1])}" for k, v in found.items()})
