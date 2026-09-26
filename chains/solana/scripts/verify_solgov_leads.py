#!/usr/bin/env python3
"""Cross-check SolGov's public protocol registry against the chain, one protocol at a time. Read-only, no key.

SolGov (github.com/EdgeVault/solgov, `public-dashboard/src/data/protocols.ts`) is the closest competitor on Solana: 50+ protocols, 63 multisigs, 183 programs. Its registry
is a list of LEADS here, never trusted values: for every protocol this reads the live loader-v3 upgrade authority of each listed program and the live Squads v4 multisig
(threshold, members, time lock), and reports where SolGov's stated numbers still hold and where they have drifted. It also says which protocols this oracle already tracks.

    python3 chains/solana/scripts/verify_solgov_leads.py [--out data/solgov_leads_2026-09-26.json]

Solana mainnet through the public RPC (rate-limited: a failed read is UNREAD, never "matches"). It adds nothing to the oracle: a lead becomes a target only when a scorer,
tests and a push exist, and a new target is Spap's decision.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sol_read  # noqa: E402

REGISTRY = "https://raw.githubusercontent.com/EdgeVault/solgov/main/public-dashboard/src/data/protocols.ts"
URL = "https://api.mainnet-beta.solana.com"
# SolGov entry name -> what this oracle tracks it as (its 18 Solana targets, read back 2026-09-26). Everything else is not tracked.
TRACKED = {"Orca": "Orca Whirlpool", "Drift": "Drift Protocol", "Project 0": "marginfi (main lending group)", "Kamino": "Kamino Lend + Kamino Liquidity",
           "Jupiter Perps": "Jupiter Perpetual Exchange", "Jupiter Lend": "Jupiter Lend", "Pumpfun + PumpSwap": "PumpSwap", "Sanctum": "Sanctum Infinity + validator LSTs",
           "Jupiter Agg": "Jupiter Aggregator v6", "Raydium": "Raydium", "Meteora": "Meteora DAMM v2", "Marinade": "Marinade Liquid Staking", "Jito": "JitoSOL",
           "Save (Solend)": "Save + Solend DAO realm", "SPL Stake Pool": "SPL Stake Pool program"}


def fetch():
    return subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", REGISTRY], capture_output=True, text=True).stdout


def entries(ts):
    """Top-level protocol objects of protocols.ts as dicts of the fields used here."""
    out = []
    for chunk in re.split(r"\n  \{\n    name: ", ts)[1:]:
        chunk = "\n    name: " + chunk
        g = lambda k: (re.search(rf"\n    {k}:\s*'?([^'\n,]+)'?,", chunk) or [None, None])[1]  # noqa: E731
        if not re.search(r"\n    tvl:", chunk):
            continue
        progs = re.findall(r"\{ name: '([^']*)', id: '([1-9A-HJ-NP-Za-km-z]{32,44})', authority: '([^']*)' \}", chunk)
        out.append({"name": g("name"), "tvl": g("tvl"), "category": g("category"), "version": g("version"), "threshold": g("threshold"), "members": g("totalMembers"),
                    "timelock_s": g("timelockSeconds"), "multisig": g("multisigAddress"), "authority": g("authorityAddress"),
                    "programs": [{"name": n, "id": i, "authority": a} for n, i, a in progs]})
    return out


def check(e):
    r = {**e, "programs_live": [], "multisig_live": None}
    for p in e["programs"]:
        try:
            live = sol_read.read_program(URL, p["id"])
            auth = live.get("upgrade_authority", "not-upgradeable-loader") if live["owner"] == "BPFLoaderUpgradeab1e11111111111111111111111" else "not-upgradeable-loader"
            r["programs_live"].append({**p, "live_authority": auth, "same_as_solgov": auth == p["authority"]})
        except Exception as ex:  # noqa: BLE001
            r["programs_live"].append({**p, "live_authority": f"UNREAD {type(ex).__name__}", "same_as_solgov": None})
    if e["multisig"] and (e["version"] or "").startswith("Squads V4"):
        try:
            sq = sol_read.read_squads(URL, e["multisig"])
            vault = sol_read.read_squads_vault(e["multisig"], 0)["vault"]
            r["multisig_live"] = {"threshold": sq["threshold"], "members": sq["members"], "time_lock_s": sq["time_lock_s"], "vault0": vault,
                                  "vault0_is_solgov_authority": vault == e["authority"],
                                  "same_shape_as_solgov": (str(sq["threshold"]) == str(e["threshold"]) and str(sq["members"]) == str(e["members"]) and str(sq["time_lock_s"]) == str(e["timelock_s"]))}
        except Exception as ex:  # noqa: BLE001
            r["multisig_live"] = {"error": f"UNREAD {type(ex).__name__}: {str(ex)[:80]}"}
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out")
    args = ap.parse_args()
    ents = entries(fetch())
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(check, ents))
    for r in rows:
        prog = r["programs_live"]
        same = sum(1 for p in prog if p["same_as_solgov"])
        unread = sum(1 for p in prog if p["same_as_solgov"] is None)
        ms = r["multisig_live"] or {}
        shape = ("shape same" if ms.get("same_shape_as_solgov") else "shape DIFFERS" if "threshold" in ms else ms.get("error", "no Squads v4 multisig listed"))
        live = f"{ms['threshold']}-of-{ms['members']} tl {ms['time_lock_s']}s" if "threshold" in ms else "-"
        print(f"{'TRACKED ' if r['name'] in TRACKED else 'untracked'} {r['name'][:22]:22s} {str(r['tvl'])[:14]:14s} programs {same}/{len(prog)} authority as SolGov ({unread} unread) | multisig live {live} ({shape})")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(rows, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
