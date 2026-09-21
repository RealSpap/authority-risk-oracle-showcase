#!/usr/bin/env python3
"""Effet de bord de _apply_cross_exposure() apres l'ajout des 4 nouvelles cibles.

LECTURE SEULE sur Ethereum mainnet (chain 1). Lance le VRAI score_all() deux
fois contre le MEME RPC : une fois avec les 14 scorers d'origine, une fois avec
les 18 (14 + les 4 ajoutes ce run). Si le crossExposureScore -- ou n'importe
quelle autre dimension -- d'une cible PREEXISTANTE bouge, sortie 1.

Usage: python3 audit/check_cross_exposure_side_effects.py [rpc_url]
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
assert w3.eth.chain_id == 1, f"refus: chain_id {w3.eth.chain_id}, attendu 1 (lecture seule mainnet)"

tous = list(m.SIMPLE_SCORERS)
anciens = [f for f in tous if f.__name__ not in NOUVEAUX]
assert len(tous) - len(anciens) == 4, "les 4 nouveaux scorers ne sont pas tous dans SIMPLE_SCORERS"

DIMS = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore")


def run(scorers):
    m.SIMPLE_SCORERS = scorers
    return {r["target"]: {d: r[d] for d in DIMS} for r in m.score_all(w3)}


avant = run(anciens)
apres = run(tous)

ecarts = []
for t, v in avant.items():
    if t not in apres:
        ecarts.append((t, "disparue", v, None))
    elif apres[t] != v:
        ecarts.append((t, "modifiee", v, apres[t]))

print(f"RPC={rpc}  cibles avant={len(avant)}  apres={len(apres)}")
for t in sorted(avant):
    etat = "CHANGE" if apres.get(t) != avant[t] else "inchange"
    print(f"  {etat:9s} {t} cross={avant[t]['crossExposureScore']} -> {apres.get(t, {}).get('crossExposureScore')}")
print("  --- nouvelles ---")
for t in sorted(set(apres) - set(avant)):
    print(f"            {t} {apres[t]}")

if len(apres) - len(avant) != 4:
    ecarts.append(("comptage", f"{len(avant)} -> {len(apres)}", None, None))
if ecarts:
    print("\nEFFET DE BORD DETECTE:")
    for e in ecarts:
        print(" -", e)
    sys.exit(1)
print(f"\nAUCUN effet de bord: les {len(avant)} cibles preexistantes sont identiques sur les 6 dimensions.")
sys.exit(0)
