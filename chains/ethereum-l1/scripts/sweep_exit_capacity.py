#!/usr/bin/env python3
"""Read-only: how much of a Morpho vault's deposits could leave at once, next to the vault's timelock.
    python3 chains/ethereum-l1/scripts/sweep_exit_capacity.py [--min 1000000] [--dump exit_rows.json]
A timelock protects depositors only if they can leave before a queued change takes effect. This reads, from Morpho's public API
(an indexer, not trusted for values), each vault's total assets, its instantly withdrawable liquidity, for V2 vaults the liquidity
that a forced in-kind deallocation could pull (`forceDeallocatableLiquidityUsd`), and the timelock (V1 `timelock`, V2 `addAdapter`).
It reports the share of listed deposits in each exit-capacity band and how many deposits sit behind a short timelock and a thin
exit. It is a sizing at one instant, not a forecast: liquidity moves with utilisation, and nothing here says that any change is
pending. Nothing is sent, no key."""
import argparse, collections, json, subprocess, sys
ap = argparse.ArgumentParser(); ap.add_argument("--min", type=int, default=1000000); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
def gql(q):
    for _ in range(3):
        o = subprocess.run(["curl", "-s", "-m", "90", "-X", "POST", "-H", "content-type: application/json", "-A", "Mozilla/5.0", "--data", json.dumps({"query": q}), "https://blue-api.morpho.org/graphql"], capture_output=True, text=True).stdout
        try:
            r = json.loads(o)
            if r.get("data"): return r["data"]
        except Exception: pass
    sys.exit("Morpho API did not answer: " + o[:200])
V1 = gql('{ vaults(first: 500, where: { totalAssetsUsd_gte: %d }, orderBy: TotalAssetsUsd, orderDirection: Desc) { items { address name listed chain { id } state { totalAssetsUsd timelock } liquidity { usd } } } }' % ARGS.min)["vaults"]["items"]
V2 = gql('{ vaultV2s(first: 500, where: { totalAssetsUsd_gte: %d }, orderBy: TotalAssetsUsd, orderDirection: Desc) { items { address name listed chain { id } totalAssetsUsd liquidityUsd forceDeallocatableLiquidityUsd timelocks { functionName duration } } } }' % ARGS.min)["vaultV2s"]["items"]
rows = []
for v in V1:
    s = v["state"] or {}
    rows.append(dict(ver="V1", chain=v["chain"]["id"], name=v["name"], addr=v["address"], listed=v["listed"], tvl=s.get("totalAssetsUsd") or 0, liq=(v["liquidity"] or {}).get("usd") or 0, inkind=0, tl=s.get("timelock")))
for v in V2:
    tl = {t["functionName"]: t["duration"] for t in (v["timelocks"] or [])}
    rows.append(dict(ver="V2", chain=v["chain"]["id"], name=v["name"], addr=v["address"], listed=v["listed"], tvl=v["totalAssetsUsd"] or 0, liq=v["liquidityUsd"] or 0, inkind=v["forceDeallocatableLiquidityUsd"] or 0, tl=tl.get("addAdapter")))
L = [r for r in rows if r["listed"] and r["tvl"] > 0]; tot = sum(r["tvl"] for r in L)
print(f"{len(L)} listed vaults of ${ARGS.min/1e6:.0f}M or more, ${tot/1e9:.2f}B (V1 {sum(1 for r in L if r['ver'] == 'V1')}, V2 {sum(1 for r in L if r['ver'] == 'V2')})")
band = lambda x: "<5%" if x < .05 else "5-20%" if x < .2 else "20-50%" if x < .5 else ">=50%"
for label, f in (("instant liquidity only", lambda r: r["liq"]), ("instant liquidity + V2 in-kind exit", lambda r: min(r["tvl"], r["liq"] + r["inkind"]))):
    b = collections.defaultdict(lambda: [0, 0.0])
    for r in L: k = band(f(r) / r["tvl"]); b[k][0] += 1; b[k][1] += r["tvl"]
    print(f"\nexit capacity as a share of each vault's deposits ({label}):")
    for k in ("<5%", "5-20%", "20-50%", ">=50%"): print(f"  {k:7s} {b[k][0]:4d} vaults  ${b[k][1]/1e6:8.0f}M  {100*b[k][1]/tot:5.1f}% of deposits")
for ver in ("V1", "V2"):
    s = [r for r in L if r["ver"] == ver]; t = sum(r["tvl"] for r in s)
    print(f"{ver}: {len(s)} vaults ${t/1e6:.0f}M, instant liquidity {100*sum(r['liq'] for r in s)/t:.1f}% of deposits, with in-kind exit {100*sum(min(r['tvl'], r['liq'] + r['inkind']) for r in s)/t:.1f}%")
day = 86400
bucket = collections.Counter("unknown" if r["tl"] is None else "0" if r["tl"] == 0 else "under 3d" if r["tl"] < 3 * day else "3d (to +5 min)" if r["tl"] <= 3 * day + 300 else "3d to 7d" if r["tl"] < 7 * day else "7d" if r["tl"] == 7 * day else "over 7d" for r in L)
print("\ntimelock (V1 timelock, V2 addAdapter):", dict(bucket))
short = [r for r in L if r["tl"] is not None and r["tl"] <= 3 * day + 300]
thin = [r for r in short if r["liq"] / r["tvl"] < .2]; thin2 = [r for r in short if (r["liq"] + r["inkind"]) / r["tvl"] < .2]
print(f"timelock of about 3 days or less: {len(short)} vaults ${sum(r['tvl'] for r in short)/1e6:.0f}M ({100*sum(r['tvl'] for r in short)/tot:.0f}% of deposits); of them instant liquidity under 20% of deposits: {len(thin)} vaults ${sum(r['tvl'] for r in thin)/1e6:.0f}M ({100*sum(r['tvl'] for r in thin)/tot:.0f}%), with in-kind exit counted {len(thin2)} vaults ${sum(r['tvl'] for r in thin2)/1e6:.0f}M")
print("\nlargest listed vaults with instant liquidity under 10% of deposits:")
for r in sorted([r for r in L if r["liq"] / r["tvl"] < .10], key=lambda r: -r["tvl"])[:8]:
    print(f"  {r['ver']} chain {r['chain']:>6} ${r['tvl']/1e6:7.0f}M liquidity {100*r['liq']/r['tvl']:4.1f}%  in-kind ${r['inkind']/1e6:5.0f}M  timelock {'?' if r['tl'] is None else '%.0fd' % (r['tl'] / day):>4s}  {r['name'][:40]}")
if ARGS.dump: json.dump(rows, open(ARGS.dump, "w")); print(f"\nwrote {len(rows)} rows to {ARGS.dump}")
