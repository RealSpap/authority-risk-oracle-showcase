#!/usr/bin/env python3
"""Side effect of _apply_cross_exposure() after the addition of the 4 new targets.

READ-ONLY on Ethereum mainnet (chain 1). Runs the REAL score_all() twice
against the SAME RPC: once with the 14 original scorers, once with
the 18 (14 + the 4 added in this run). If the crossExposureScore, or any
other dimension, of a PRE-EXISTING target moves, exit 1.

Usage: python3 chains/ethereum-l1/scripts/check_cross_exposure_side_effects.py [rpc_url]
"""
import importlib.util
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts", "lib"))
spec = importlib.util.spec_from_file_location("eth_scorers", os.path.join(REPO, "chains", "ethereum-l1", "scorers.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from web3_utils import get_w3  # noqa: E402

NOUVEAUX = {
    "score_lido_steth",
    "score_eigenlayer_strategy_manager",
    "score_curve_stableswap_ng_factory",
    "score_rocketpool_storage",
}
rpc = sys.argv[1] if len(sys.argv) > 1 else "https://ethereum-rpc.publicnode.com"
w3 = get_w3(rpc)
assert w3.eth.chain_id == 1, f"refused: chain_id {w3.eth.chain_id}, expected 1 (read-only mainnet)"

tous = list(m.SIMPLE_SCORERS)
anciens = [f for f in tous if f.__name__ not in NOUVEAUX]
assert len(tous) - len(anciens) == 4, "the 4 new scorers are not all in SIMPLE_SCORERS"

DIMS = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore")


def run(scorers):
    m.SIMPLE_SCORERS = scorers
    return {r["target"]: {d: r[d] for d in DIMS} for r in m.score_all(w3)}


avant = run(anciens)
apres = run(tous)

ecarts = []
for t, v in avant.items():
    if t not in apres:
        ecarts.append((t, "disappeared", v, None))
    elif apres[t] != v:
        ecarts.append((t, "modified", v, apres[t]))

print(f"RPC={rpc}  targets before={len(avant)}  after={len(apres)}")
for t in sorted(avant):
    etat = "CHANGED" if apres.get(t) != avant[t] else "unchanged"
    print(f"  {etat:9s} {t} cross={avant[t]['crossExposureScore']} -> {apres.get(t, {}).get('crossExposureScore')}")
print("  --- new ---")
for t in sorted(set(apres) - set(avant)):
    print(f"            {t} {apres[t]}")

if len(apres) - len(avant) != 4:
    ecarts.append(("count", f"{len(avant)} -> {len(apres)}", None, None))
if ecarts:
    print("\nSIDE EFFECT DETECTED:")
    for e in ecarts:
        print(" -", e)
    sys.exit(1)
print(f"\nNO side effect: the {len(avant)} pre-existing targets are identical on all 6 dimensions.")
sys.exit(0)
