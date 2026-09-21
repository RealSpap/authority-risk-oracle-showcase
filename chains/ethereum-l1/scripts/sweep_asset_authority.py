#!/usr/bin/env python3
"""Read-only: what the issuer of a token can do to the balances that Morpho vaults and markets hold in it.
    python3 chains/ethereum-l1/scripts/sweep_asset_authority.py [--min 1000000] [--dump rows.json]
A vault can have a perfect owner, curator and guardian and still hold a token whose issuer can freeze the vault's address, seize its balance,
pause every transfer or upgrade the token's code. This lists the loan asset of every listed Morpho vault and the loan and collateral assets of every
listed market (Morpho's public API, an indexer: values are not trusted), reads each token's verified code on Blockscout (an ABI lists the functions that
change state; the implementation behind a proxy is followed), and looks for four families of function by name: freeze (blacklist, blocklist, denylist,
freeze), seize (wipe, destroyBlackFunds, seize, clawback, forceTransfer, confiscate), pause, and upgrade. It then reads the address that holds each
zero-argument controller getter the token exposes (owner, admin, blacklister, pauser, masterMinter, assetProtectionRole, supplyController) plus the EIP-1967
admin, and classifies it (plain EOA, Safe t-of-n, other contract).
Names are only a signal: a function called `pause` is reported, a modifier that limits who may call it is not read; an AccessControl token's role holders are
not enumerated (that needs event logs); tokens on chains without a Blockscout instance are reported as unread. It measures capability, not intent, and it does
not say any issuer has used a power. Nothing is sent, no key."""
import argparse, collections, json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://base-rpc.publicnode.com", 42161: "https://arbitrum-one-rpc.publicnode.com", 10: "https://optimism-rpc.publicnode.com",
       137: "https://polygon-bor-rpc.publicnode.com", 130: "https://mainnet.unichain.org"}
BLOCKSCOUT = {1: "eth.blockscout.com", 8453: "base.blockscout.com", 42161: "arbitrum.blockscout.com", 10: "optimism.blockscout.com", 137: "polygon.blockscout.com"}
ap = argparse.ArgumentParser(); ap.add_argument("--min", type=int, default=1000000); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
def curl(url, body=None, tries=3):
    cmd = ["curl", "-s", "-m", "90", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body is not None else []) + [url]
    for a in range(tries):
        try:
            return json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
        except Exception:
            time.sleep(1.0 * (a + 1))
def gql(q):
    r = curl("https://blue-api.morpho.org/graphql", {"query": q})
    if not r or not r.get("data"): sys.exit("Morpho API did not answer")
    return r["data"]
def rpc(ch, m, p):
    for a in range(3):
        r = curl(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, tries=1)
        if r and r.get("result") is not None: return r["result"]
        time.sleep(0.7 * (a + 1))
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
call = lambda ch, to, sig: rpc(ch, "eth_call", [{"to": to, "data": sel(sig)}, "latest"])
V1 = gql('{ vaults(first: 500, where: { totalAssetsUsd_gte: %d }) { items { listed chain { id } asset { address symbol } state { totalAssetsUsd } } } }' % ARGS.min)["vaults"]["items"]
V2 = gql('{ vaultV2s(first: 500, where: { totalAssetsUsd_gte: %d }) { items { listed chain { id } asset { address symbol } totalAssetsUsd } } }' % ARGS.min)["vaultV2s"]["items"]
MK, skip = [], 0
while True:
    d = gql('{ markets(first: 500, skip: %d, where: { supplyAssetsUsd_gte: %d }) { items { listed chain { id } loanAsset { address symbol } collateralAsset { address symbol } state { supplyAssetsUsd collateralAssetsUsd } } pageInfo { countTotal } } }' % (skip, ARGS.min))["markets"]
    MK += d["items"]; skip += 500
    if skip >= d["pageInfo"]["countTotal"] or not d["items"]: break
dep = collections.defaultdict(float); col = collections.defaultdict(float); sym = {}
for v in V1:
    if v["listed"] and v["asset"]: k = (v["chain"]["id"], v["asset"]["address"].lower()); dep[k] += (v["state"] or {}).get("totalAssetsUsd") or 0; sym[k] = v["asset"]["symbol"]
for v in V2:
    if v["listed"] and v["asset"]: k = (v["chain"]["id"], v["asset"]["address"].lower()); dep[k] += v["totalAssetsUsd"] or 0; sym[k] = v["asset"]["symbol"]
for m in MK:
    if not m["listed"]: continue
    for a, fld, tgt in (("collateralAsset", "collateralAssetsUsd", col),):
        if m[a]: k = (m["chain"]["id"], m[a]["address"].lower()); tgt[k] += (m["state"] or {}).get(fld) or 0; sym[k] = m[a]["symbol"]
assets = sorted(set(dep) | set(col), key=lambda k: -(dep.get(k, 0) + col.get(k, 0)))
totdep, totcol = sum(dep.values()), sum(col.values())
print(f"{len(assets)} distinct assets: vault deposits ${totdep/1e9:.2f}B in {len(dep)}, market collateral ${totcol/1e9:.2f}B in {len(col)}")
FAM = {"freeze": re.compile(r"blacklist|blocklist|denylist|freeze|frozen|banaddress|blockaccount", re.I),
       "seize": re.compile(r"wipe|destroyblack|seize|clawback|forcetransfer|forcedtransfer|confiscate|forceburn", re.I),
       "pause": re.compile(r"pause", re.I), "upgrade": re.compile(r"^upgradeto", re.I)}
GETTERS = ("owner", "admin", "blacklister", "pauser", "masterMinter", "assetProtectionRole", "supplyController", "governance", "freezer", "guardian")
ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"; IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
def kind(ch, a):
    if not a or int(a, 16) == 0: return "none"
    code = rpc(ch, "eth_getCode", [a, "latest"]) or "0x"
    if code == "0x": return "EOA"
    if code.startswith("0xef0100"): return "EOA-7702"
    t, o = call(ch, a, "getThreshold()"), call(ch, a, "getOwners()")
    if t and t != "0x" and o and len(o) > 130: return f"Safe {int(t, 16)}-of-{int(o[2 + 64:2 + 128], 16)}"
    return f"contract({(len(code) - 2) // 2}B)"
def analyse(k):
    ch, a = k; out = dict(chain=ch, token=a, symbol=sym.get(k), deposits=dep.get(k, 0), collateral=col.get(k, 0), fam={}, controllers={}, note=None)
    if ch not in BLOCKSCOUT: out["note"] = "no explorer for this chain"; return out
    d = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{a}")
    if not d or d.get("message") or not d.get("is_verified") and not d.get("abi") and not d.get("implementations"): out["note"] = "not verified or unread"; return out
    abis = [d.get("abi") or []]
    for im in (d.get("implementations") or [])[:1]:
        ia = im.get("address") or im.get("address_hash")
        di = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{ia}") if ia else None
        if di: abis.append(di.get("abi") or [])
    fns = {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") not in ("view", "pure")}
    views = {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") in ("view", "pure") and not x.get("inputs") and x.get("outputs") and x["outputs"][0].get("type") == "address"}
    out["name"] = d.get("name"); out["proxy"] = bool(d.get("proxy_type") or d.get("implementations"))
    out["fam"] = {f: sorted(n for n in fns if rx.search(n))[:4] for f, rx in FAM.items()}
    out["roles"] = any(n in fns for n in ("grantRole", "revokeRole"))
    for g in GETTERS:
        if g in views:
            r = call(ch, a, f"{g}()")
            if r and len(r) >= 42 and int(r, 16): out["controllers"][g] = "0x" + r[-40:]
    ad = rpc(ch, "eth_getStorageAt", [a, ADMIN_SLOT, "latest"])
    if ad and int(ad, 16):
        adm = "0x" + ad[-40:]; out["controllers"]["proxy admin"] = adm
        ow = call(ch, adm, "owner()")
        if ow and len(ow) >= 42 and int(ow, 16): out["controllers"]["proxy admin owner"] = "0x" + ow[-40:]
    out["kinds"] = {g: kind(ch, v) for g, v in out["controllers"].items()}
    return out
with ThreadPoolExecutor(4) as ex: res = list(ex.map(analyse, assets))
read = [r for r in res if not r["note"]]
print(f"read: {len(read)} assets; deposits covered ${sum(r['deposits'] for r in read)/1e9:.2f}B of ${totdep/1e9:.2f}B, collateral ${sum(r['collateral'] for r in read)/1e9:.2f}B of ${totcol/1e9:.2f}B; unread: {[(r['symbol'], r['note']) for r in res if r['note']][:8]}")
def share(pred, key, tot):
    s = [r for r in read if pred(r)]; return len(s), sum(r[key] for r in s), (100 * sum(r[key] for r in s) / tot if tot else 0)
for label, pred in (("can freeze or blacklist an address", lambda r: bool(r["fam"]["freeze"])), ("can seize or wipe a balance", lambda r: bool(r["fam"]["seize"])),
                    ("can pause transfers", lambda r: bool(r["fam"]["pause"])), ("upgradeable code (proxy)", lambda r: r.get("proxy")), ("freeze, seize or pause", lambda r: bool(r["fam"]["freeze"] or r["fam"]["seize"] or r["fam"]["pause"]))):
    n, u, p = share(pred, "deposits", totdep); n2, u2, p2 = share(pred, "collateral", totcol)
    print(f"  {label:36s} deposits: {n:3d} assets ${u/1e9:5.2f}B ({p:4.1f}%) | collateral: {n2:3d} assets ${u2/1e9:5.2f}B ({p2:4.1f}%)")
print("\nlargest assets by exposure (deposits + collateral):")
for r in sorted(res, key=lambda r: -(r["deposits"] + r["collateral"]))[:16]:
    f = "".join(c if r["fam"].get(n) else "-" for n, c in (("freeze", "F"), ("seize", "S"), ("pause", "P"), ("upgrade", "U"))) if not r["note"] else "????"
    ks = ", ".join(f"{g}={k}" for g, k in (r.get("kinds") or {}).items() if g in ("owner", "blacklister", "pauser", "admin", "proxy admin owner", "masterMinter", "assetProtectionRole", "supplyController"))
    print(f"  {r['chain']:>5} {str(r['symbol'])[:12]:12s} deposits ${r['deposits']/1e6:7.0f}M collateral ${r['collateral']/1e6:7.0f}M {f} {'AccessControl' if r.get('roles') else ''} {ks[:110] or (r['note'] or '')}")
kinds = collections.Counter(); val = collections.defaultdict(float)
for r in read:
    if r["fam"]["freeze"] or r["fam"]["seize"]:
        for g, k in r["kinds"].items():
            if g in ("blacklister", "owner", "assetProtectionRole", "proxy admin owner", "admin"):
                c = "EOA" if k.startswith("EOA") else "Safe" if k.startswith("Safe") else k.split("(")[0]; kinds[c] += 1; val[c] += r["deposits"] + r["collateral"]
print("\ncontroller accounts of freeze or seize capable tokens (owner, blacklister, admin, one per role read):", {k: f"{n} (${val[k]/1e9:.2f}B)" for k, n in kinds.most_common()})
if ARGS.dump: json.dump(res, open(ARGS.dump, "w")); print(f"\nwrote {len(res)} rows to {ARGS.dump}")
