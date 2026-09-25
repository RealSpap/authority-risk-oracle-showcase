#!/usr/bin/env python3
"""Read-only: the same question as sweep_asset_authority.py (can a token's issuer freeze, seize, pause or replace the code of what a protocol holds), asked of
the other large lenders so the Morpho figure has something to be compared with.
    python3 chains/ethereum-l1/scripts/sweep_lending_asset_authority.py [--min 1000000] [--dump rows.json]
Pools come from DefiLlama's public yields API (an indexer: each pool of a lending project is one asset with its TVL and the address of its underlying token).
For every underlying token on a chain with a Blockscout instance (Ethereum, Base, Arbitrum, Optimism, Polygon) it reads the verified code and looks by function
name for four families: freeze (blacklist, blocklist, denylist, freeze), seize (wipe, destroyBlackFunds, seize, clawback, forceTransfer), pause and upgrade
(a proxy). It reports, per project, the share of TVL in tokens with each capability. Tokens on other chains, native coins and unverified tokens are counted as
unread, so every share is a lower bound. A function name is only a signal: the modifiers that limit who may call it are not read. It measures capability, not
use. Nothing is sent, no key."""
import argparse, collections, json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
ap = argparse.ArgumentParser(); ap.add_argument("--min", type=float, default=1000000); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
PROJECTS = ["aave-v3", "morpho-blue", "sky-lending", "maple", "compound-v3", "venus-core-pool", "fluid-lending", "spark-savings", "dolomite", "lista-lending", "euler-v2"]
BLOCKSCOUT = {"Ethereum": "eth.blockscout.com", "Base": "base.blockscout.com", "Arbitrum": "arbitrum.blockscout.com", "Optimism": "optimism.blockscout.com", "Polygon": "polygon.blockscout.com"}
FAM = {"freeze": re.compile(r"blacklist|blocklist|denylist|freeze|frozen|banaddress|blockaccount", re.I),
       "seize": re.compile(r"wipe|destroyblack|seize(?!cooldown)|clawback|forcetransfer|forcedtransfer|confiscate|forceburn", re.I),
       "pause": re.compile(r"pause", re.I), "upgrade": re.compile(r"^upgradeto", re.I)}
def curl(url):
    for a in range(3):
        try: return json.loads(subprocess.run(["curl", "-s", "-m", "120", "-A", "Mozilla/5.0", url], capture_output=True, text=True).stdout)
        except Exception: time.sleep(1.0 * (a + 1))
data = (curl("https://yields.llama.fi/pools") or {}).get("data")
if not data: sys.exit("DefiLlama yields API did not answer")
pools = [p for p in data if p.get("project") in PROJECTS and (p.get("tvlUsd") or 0) >= ARGS.min and p.get("underlyingTokens") and p["underlyingTokens"][0] and int(p["underlyingTokens"][0], 16) != 0]
tot = collections.defaultdict(float); tvl_all = collections.defaultdict(float)
for p in data:
    if p.get("project") in PROJECTS: tvl_all[p["project"]] += p.get("tvlUsd") or 0
tokens = sorted({(p["chain"], p["underlyingTokens"][0].lower()) for p in pools if p["chain"] in BLOCKSCOUT})
print(f"{len(pools)} pools of {ARGS.min/1e6:.0f}M or more in {len(PROJECTS)} projects; {len(tokens)} distinct tokens on chains with an explorer")
def analyse(k):
    ch, a = k; out = dict(fam={f: [] for f in FAM}, proxy=False, name=None, read=False)
    d = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{a}")
    if not d or d.get("message") or (not d.get("is_verified") and not d.get("abi") and not d.get("implementations")): return k, out
    abis = [d.get("abi") or []]
    for im in (d.get("implementations") or [])[:1]:
        ia = im.get("address") or im.get("address_hash"); di = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{ia}") if ia else None
        if di: abis.append(di.get("abi") or [])
    fns = {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") not in ("view", "pure")}
    out.update(read=True, name=d.get("name"), proxy=bool(d.get("proxy_type") or d.get("implementations")), fam={f: sorted(n for n in fns if rx.search(n))[:3] for f, rx in FAM.items()})
    return k, out
with ThreadPoolExecutor(4) as ex: info = dict(ex.map(analyse, tokens))
rows = []
for p in pools:
    k = (p["chain"], p["underlyingTokens"][0].lower()); i = info.get(k)
    rows.append(dict(project=p["project"], chain=p["chain"], symbol=p["symbol"], tvl=p["tvlUsd"], token=k[1], read=bool(i and i["read"]), fam=(i or {}).get("fam") or {}, proxy=bool(i and i["proxy"])))
def pct(x, d): return f"{100 * x / d:4.0f}%" if d else "   - "
print(f"\n{'project':16s} {'TVL of pools >= min':>20s} {'read':>6s} | freeze  seize  pause  any3  upgradeable   (share of the project's pooled TVL, tokens read only counted)")
for proj in PROJECTS:
    rs = [r for r in rows if r["project"] == proj]; t = sum(r["tvl"] for r in rs)
    if not t: continue
    g = lambda pred: sum(r["tvl"] for r in rs if r["read"] and pred(r))
    print(f"{proj:16s} ${t/1e9:8.2f}B{'':>8s} {pct(g(lambda r: True), t)} | {pct(g(lambda r: r['fam'].get('freeze')), t)}  {pct(g(lambda r: r['fam'].get('seize')), t)}  {pct(g(lambda r: r['fam'].get('pause')), t)}  {pct(g(lambda r: r['fam'].get('freeze') or r['fam'].get('seize') or r['fam'].get('pause')), t)}  {pct(g(lambda r: r['proxy']), t)}")
allr = [r for r in rows if r["read"]]; T = sum(r["tvl"] for r in rows)
anyp = lambda r: r["fam"].get("freeze") or r["fam"].get("seize") or r["fam"].get("pause")
print(f"\nall projects: ${T/1e9:.2f}B of pools, read {100*sum(r['tvl'] for r in allr)/T:.0f}%; freeze, seize or pause {100*sum(r['tvl'] for r in allr if anyp(r))/T:.0f}% of that TVL (lower bound)")
by = collections.defaultdict(lambda: [0.0, None, set()])
for r in allr:
    x = by[(r["chain"], r["token"])]; x[0] += r["tvl"]; x[1] = r["symbol"]; x[2].add(r["project"])
print("\nlargest tokens across these lenders (F freeze, S seize, P pause, U upgradeable):")
for (ch, tk), (v, s, pr) in sorted(by.items(), key=lambda kv: -kv[1][0])[:14]:
    i = info[(ch, tk)]; f = "".join(c if i["fam"].get(n) else "-" for n, c in (("freeze", "F"), ("seize", "S"), ("pause", "P"))) + ("U" if i["proxy"] else "-")
    print(f"  {ch:9s} {str(i.get('name') or s)[:22]:22s} ${v/1e9:5.2f}B {f} in {sorted(pr)}")
if ARGS.dump: json.dump(rows, open(ARGS.dump, "w")); print(f"\nwrote {len(rows)} rows to {ARGS.dump}")
