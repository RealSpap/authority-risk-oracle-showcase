#!/usr/bin/env python3
"""Offline analysis of the row dumps written by sweep_morpho_vault_owners.py --dump and sweep_euler_earn.py --dump.
Groups every owner and curator address across vaults, chains and families and reports the recurring controllers.
    python3 chains/ethereum-l1/scripts/analyze_controllers.py morpho_rows.json euler_rows.json
Reads only local files, sends nothing. Deposits are the per-vault figures of the sweeps (a vault's deposits are counted once
per controller address, whatever the role)."""
import collections, json, sys
rows = []
for f in sys.argv[1:]: rows += json.load(open(f))
LISTED = lambda r: r.get("listed") is not False   # unlisted / unverified vaults are kept out of the headline numbers
ZERO = "0x0000000000000000000000000000000000000000"
ctl = collections.defaultdict(lambda: {"kind": None, "roles": set(), "chains": set(), "families": set(), "vaults": {}, "names": set()})
for r in rows:
    if not LISTED(r): continue
    for role in ("owner", "curator"):
        a = r.get(role)
        if not a or a == ZERO: continue
        c = ctl[a.lower()]; c["kind"] = r.get(role + "_kind") or c["kind"]; c["roles"].add(role); c["chains"].add(r["chain"]); c["families"].add(r["family"])
        c["vaults"][(r["chain"], r["vault"])] = r["usd"]
        if r.get("name"): c["names"].add(r["name"].split(" ")[0])
single = lambda k: bool(k) and (k.startswith("single key") or k.startswith("1-of-1"))
listed_total = sum(r["usd"] for r in rows if LISTED(r))
print(f"{sum(1 for r in rows if LISTED(r))} listed or verified vaults, ${listed_total/1e9:.2f}B, {len(ctl)} distinct owner or curator addresses\n")
print("== single-key controllers, by deposits (owner or curator role)")
top = sorted(((sum(c["vaults"].values()), a, c) for a, c in ctl.items() if single(c["kind"])), key=lambda z: -z[0])
for usd, a, c in top[:14]:
    print(f"  {a[:10]}.. ${usd/1e6:7.1f}M {len(c['vaults']):2d} vaults chains {sorted(c['chains'])} {'/'.join(sorted(c['roles']))} {c['kind']} {sorted(c['families'])} {sorted(c['names'])[:3]}")
tot_single = sum(u for u, _, _ in top)
print(f"  -> {len(top)} single-key addresses hold an owner or curator role over ${tot_single/1e6:.0f}M of vault deposits (a vault with a single-key owner and curator counts once per address)\n")
print("== the same address controlling vaults on 2 or more chains")
multi = sorted(((sum(c["vaults"].values()), a, c) for a, c in ctl.items() if len(c["chains"]) >= 2), key=lambda z: -z[0])
for usd, a, c in multi[:12]:
    print(f"  {a[:10]}.. ${usd/1e6:7.1f}M {len(c['vaults']):2d} vaults chains {sorted(c['chains'])} {c['kind']}")
print(f"  -> {len(multi)} addresses span 2 or more chains; single-key ones: {sum(1 for _, a, c in multi if single(c['kind']))}\n")
print("== the same address in both families (Morpho and Euler Earn)")
both = [(sum(c["vaults"].values()), a, c) for a, c in ctl.items() if any(f.startswith("morpho") for f in c["families"]) and "euler-earn" in c["families"]]
for usd, a, c in sorted(both, key=lambda z: -z[0])[:10]: print(f"  {a[:10]}.. ${usd/1e6:7.1f}M {c['kind']} chains {sorted(c['chains'])}")
if not both: print("  none")
print("\n== curators (address) with the most deposits, and their type")
cur = collections.defaultdict(lambda: [0.0, 0, None])
for r in rows:
    if LISTED(r) and r.get("curator") and r["curator"] != ZERO:
        x = cur[r["curator"].lower()]; x[0] += r["usd"]; x[1] += 1; x[2] = r.get("curator_kind")
for a, (usd, n, k) in sorted(cur.items(), key=lambda kv: -kv[1][0])[:10]: print(f"  {a[:10]}.. ${usd/1e6:7.1f}M {n:3d} vaults {k}")
cs = sum(u for u, n, k in cur.values() if single(k)); ct = sum(u for u, n, k in cur.values())
print(f"  -> curator is a single key for ${cs/1e6:.0f}M of ${ct/1e6:.0f}M ({100*cs/max(ct,1):.0f}%) of deposits with a curator")
