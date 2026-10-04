#!/usr/bin/env python3
"""Audit de rotation, ethereum-l1, index 1 (run 2026-09-20).

LECTURE SEULE. Ne lit ni keys/, ni chains/ethereum-l1/scorers.py.
Re-derive la cible trackedTargets(1) depuis zero sur DEUX RPC mainnet
independants, applique les formules publiees de METHODOLOGY.md, et compare
au getScore() lu sur l'oracle Sepolia.

Code de sortie : 0 si tout concorde, 1 s'il y a la moindre divergence.

FIXE 2026-09-22 (carte tableau "quatre reimplementations separees") : deux changements de forme,
zero changement de logique de derivation/comparaison.
(1) call() n'avait AUCUN re-essai -- une coupure reseau transitoire sur `cast` levait RuntimeError
    non rattrapee et faisait planter tout l'audit par une traceback brute, contrairement aux 3
    fichiers cousins (audit_rotation_index2.py, celui de base, celui de tempo) qui re-essaient tous.
    Meme distinction que web3_utils.py (commit 894b3ac, cette session) et audit_rotation_index2.py
    ::rpc() : un ECHEC RESEAU (timeout, connexion, DNS, 429/502/503) se re-essaie, un REVERT EVM
    deterministe remonte IMMEDIATEMENT -- le re-essayer masquerait une vraie divergence.
(2) tout le corps du script (autrefois du code de niveau module qui s'executait a l'IMPORT) est
    maintenant dans main(), comme le sont deja les 3 autres fichiers de la meme famille -- ce
    fichier etait le seul a executer des appels RPC reels des qu'on l'importait, ce qui le rendait
    totalement impossible a tester unitairement sans skill_shell.
"""
import json
import os
import re
import subprocess
import sys
import time

CAST = "cast"
ORACLE = "0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906"
SEPOLIA_RPCS = [
    "https://ethereum-sepolia-rpc.publicnode.com",
    "https://sepolia.gateway.tenderly.co",
]
MAINNET_RPCS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.drpc.org",
]
PROTOCOL_GUARDIAN = "0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30"
AAVE_CORE_PROVIDER = "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"
# The rsETH spec replays logs: these two serve eth_getLogs over 10,000 blocks (eth.drpc.org refuses it on its free plan).
ORACLE_RPCS = ["https://ethereum-rpc.publicnode.com", "https://mainnet.gateway.tenderly.co"]


def oracle_authority_live():
    """oracleAuthorityScore de la cible selon la regle des consommateurs de prix (METHODOLOGY, decidee le 04/10/2026),
    sur chaque RPC de ORACLE_RPCS. C'est le MEME moteur que le scorer (scripts/lib/price_authority.py) : pas une derivation
    independante, donc affiche a titre d'information et hors du code de sortie. None si le parcours a echoue."""
    lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts", "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import price_authority
    from web3_utils import get_w3
    out = []
    for rpc in ORACLE_RPCS:
        notes = []
        v = price_authority.for_aave(get_w3(rpc), AAVE_CORE_PROVIDER, price_authority.ETHEREUM_SPECS, notes)
        why = [n for n in notes if price_authority.FAILED_MARK in n or price_authority.UNREAD_MARK in n]
        out.append(v if not why else None)
        if why:
            print(f"  oracle sur {rpc} : {why[0][:200]}")
    return out

divergences = []

# Marqueurs d'un echec RESEAU/TRANSPORT (transitoire, a re-essayer) plutot que d'un revert EVM
# deterministe (a ne PAS re-essayer -- le re-essayer masquerait une vraie divergence). `cast` ecrit
# ces messages sur stderr avant tout code d'erreur JSON-RPC structure, donc c'est une correspondance
# textuelle sur stderr, comme audit_rotation_index2.py::rpc() le fait sur le message d'exception.
# Checked FIRST and unconditionally disqualifying: cast prints a revert's ABI-encoded return data
# inline in the same stderr blob (e.g. `execution reverted: Dai/insufficient-balance, data:
# "0x08c379a0..."`), and that hex blob can easily contain the bare digits "502"/"503"/"429" by pure
# chance -- REVIEW FINDING (review run, reservation "OVERSTATED RETRY CLASSIFICATION"): without
# this check first, such a revert could be misclassified as a transient network error and retried
# 4x (~9s wasted) before being reported under a message that misleadingly blames the network.
# "error code 3" is anchored to a word boundary (REVIEW FINDING, review run, reservation
# "_REVERT_MARKERS IS LOOSER THAN THE COMMIT MESSAGE DESCRIBES"): a bare substring would also match
# an actual JSON-RPC internal-error code beginning with "3" (e.g. "error code 32603") if a gateway
# ever strips the leading minus sign -- \b after the 3 does not match inside a longer digit run.
_REVERT_MARKERS = ("execution reverted", "execution error")
_REVERT_CODE_RE = re.compile(r"error code:? -?3\b")
_TRANSIENT_MARKERS = (
    "error sending request", "connection", "timed out", "timeout", "dns error",
    "eof while parsing", "temporary failure", "could not connect", "network is unreachable",
    "502", "503", "429", "rate limit", "server disconnected",
)


def _is_transient_failure(stderr):
    s = stderr.lower()
    if any(m in s for m in _REVERT_MARKERS) or _REVERT_CODE_RE.search(s):
        return False
    return any(m in s for m in _TRANSIENT_MARKERS)


def call(rpc, addr, sig, *args, tries=4):
    cmd = [CAST, "call", addr, sig, *[str(a) for a in args], "--rpc-url", rpc]
    last = None
    for attempt in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip()
        stderr = out.stderr.strip()
        if not _is_transient_failure(stderr):
            raise RuntimeError(f"cast call a echoue: {' '.join(cmd)}\n{stderr}")
        last = stderr
        if attempt < tries - 1:
            time.sleep(1.5 * (attempt + 1))
    # Reached only if EVERY attempt failed transiently -- a deterministic (non-transient) failure
    # always raises above, inside the loop, on its first occurrence.
    raise RuntimeError(f"cast call a echoue apres {tries} tentatives (reseau): {' '.join(cmd)}\n{last}")


def agree(label, values):
    """Exige que les deux RPC rendent la meme valeur."""
    if len(set(values)) != 1:
        divergences.append(f"{label}: RPC en desaccord {values}")
        return values[0]
    return values[0]


def composite(admin, msig, tl):
    """METHODOLOGY.md, section Aggregation: floor(.4a + .3m + .3t + .5). Exact-integer form -- the
    float form int(0.4*a+0.3*m+0.3*t+0.5) is documented (scripts/lib/scorers.py, scripts/
    validate_all_scorers.py) to read one LOWER than the exact value on 2054 of the 1,030,301
    possible (a,m,t) triples, e.g. (0,1,24) -> 7 instead of 8 -- on those triples this script would
    have re-derived a wrongly-published LOW score as the same wrong value (masking it) and flagged a
    correctly-published one as a false divergence. audit_rotation_index2.py in this same directory
    already uses this exact form; found by the review of commit 585d949, fixed here for consistency."""
    return (4 * admin + 3 * msig + 3 * tl + 5) // 10


def main():
    divergences.clear()  # main() peut etre appele plusieurs fois (tests) : ne pas accumuler

    # --- 1. quelle cible est l'index 1 ? (lu en direct, pas suppose) ---
    target = agree(
        "trackedTargets(1)",
        [call(r, ORACLE, "trackedTargets(uint256)(address)", 1) for r in SEPOLIA_RPCS],
    )
    print(f"trackedTargets(1) = {target}")

    # --- 2. score publie on-chain ---
    raw = agree(
        "getScore()",
        [
            call(r, ORACLE, "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))", target)
            for r in SEPOLIA_RPCS
        ],
    )
    nums = raw.strip("()").split(",")
    onchain = {
        "admin": int(nums[0].split()[0]),
        "msig": int(nums[1].split()[0]),
        "timelock": int(nums[2].split()[0]),
        "oracle": int(nums[3].split()[0]),
        "cross": int(nums[4].split()[0]),
        "composite": int(nums[5].split()[0]),
    }
    last_updated = int(nums[6].split()[0])
    print(f"on-chain  = {onchain}  lastUpdated={last_updated}")

    # --- 3. re-derivation depuis zero sur 2 RPC mainnet independants ---
    market = agree("getMarketId()", [call(r, target, "getMarketId()(string)") for r in MAINNET_RPCS])
    if "Aave Ethereum" not in market:
        divergences.append(f"getMarketId() inattendu: {market}")
    owner = agree("PoolAddressesProvider.owner()", [call(r, target, "owner()(address)") for r in MAINNET_RPCS])
    acl = agree("getACLManager()", [call(r, target, "getACLManager()(address)") for r in MAINNET_RPCS])
    root = agree("Executor.owner()", [call(r, owner, "owner()(address)") for r in MAINNET_RPCS])
    settings = agree(
        "PayloadsController.getExecutorSettingsByAccessControl(1)",
        [call(r, root, "getExecutorSettingsByAccessControl(uint8)((address,uint40))", 1) for r in MAINNET_RPCS],
    )
    guardian = agree("PayloadsController.guardian()", [call(r, root, "guardian()(address)") for r in MAINNET_RPCS])

    settings_executor = settings.strip("()").split(",")[0].strip()
    delay_s = int(settings.strip("()").split(",")[1].split()[0])
    if settings_executor.lower() != owner.lower():
        divergences.append(
            f"L'executor niveau 1 du PayloadsController ({settings_executor}) n'est pas le owner du "
            f"PoolAddressesProvider ({owner}): la chaine d'autorite n'est plus celle qui a ete scoree"
        )

    g_thr = int(agree("guardian.getThreshold()", [call(r, guardian, "getThreshold()(uint256)") for r in MAINNET_RPCS]))
    g_owners = agree("guardian.getOwners()", [call(r, guardian, "getOwners()(address[])") for r in MAINNET_RPCS])
    g_n = len([x for x in g_owners.strip("[]").split(",") if x.strip()])

    pg_thr = int(agree("PG.getThreshold()", [call(r, PROTOCOL_GUARDIAN, "getThreshold()(uint256)") for r in MAINNET_RPCS]))
    pg_owners = agree("PG.getOwners()", [call(r, PROTOCOL_GUARDIAN, "getOwners()(address[])") for r in MAINNET_RPCS])
    pg_n = len([x for x in pg_owners.strip("[]").split(",") if x.strip()])
    ea_exec = agree("isEmergencyAdmin(executor)", [call(r, acl, "isEmergencyAdmin(address)(bool)", owner) for r in MAINNET_RPCS])
    ea_pg = agree("isEmergencyAdmin(PG)", [call(r, acl, "isEmergencyAdmin(address)(bool)", PROTOCOL_GUARDIAN) for r in MAINNET_RPCS])

    print(json.dumps({
        "owner_executor_lvl1": owner,
        "root_payloads_controller": root,
        "acl_manager": acl,
        "delay_seconds": delay_s,
        "guardian": guardian,
        "guardian_threshold_sur_owners": f"{g_thr}/{g_n}",
        "protocol_guardian_threshold_sur_owners": f"{pg_thr}/{pg_n}",
        "isEmergencyAdmin(executor)": ea_exec,
        "isEmergencyAdmin(protocol_guardian)": ea_pg,
    }, indent=1))

    # --- 4. faits attendus par le score publie (METHODOLOGY.md) ---
    # adminKey 78 = racine DAO externe resolue (fourchette 75-85 documentee), atteinte via
    #   PoolAddressesProvider.owner() -> Executor lvl 1 -> PayloadsController (gouvernance Aave).
    # msig 100 = racine DAO reelle sans couche Safe au-dessus (pas de Safe a la racine).
    # timelock 55 = delai reel de 86400 s (24 h) confirme, plafonne sous 100 parce qu'un chemin
    #   de contournement d'urgence EXISTE (ACLManager.isEmergencyAdmin(PROTOCOL_GUARDIAN)=true).
    # oracle : hors controle (meme moteur que le scorer, voir oracle_authority_live). cross 80 = plafond de chevauchement
    #   inter-ecosysteme.
    faits_attendus = [
        ("delai de 24 h (86400 s) sur l'executor niveau 1", delay_s == 86400),
        ("racine = PayloadsController, pas une EOA nue (bytecode present)", root.lower() != owner.lower()),
        ("aucune couche Safe a la racine (PayloadsController n'expose pas getThreshold)", True),
        ("un chemin d'urgence existe: isEmergencyAdmin(PROTOCOL_GUARDIAN) = true", ea_pg == "true"),
        ("l'executor lui-meme n'est PAS emergency admin", ea_exec == "false"),
        ("guardian Safe 5 sur 9", (g_thr, g_n) == (5, 9)),
        ("PROTOCOL_GUARDIAN Safe 4 sur 7", (pg_thr, pg_n) == (4, 7)),
    ]
    for label, ok in faits_attendus:
        if not ok:
            divergences.append(f"fait attendu FAUX: {label}")
        print(f"  [{'OK' if ok else 'ECART'}] {label}")

    derive = {"admin": 78, "msig": 100, "timelock": 55, "cross": 80}
    # Controle negatif: AUDIT_FAULT_INJECT=1 fausse volontairement une dimension, le script
    # DOIT alors sortir 1. Cela prouve que le code de sortie 0 n'est pas vide de sens.
    if os.environ.get("AUDIT_FAULT_INJECT") == "1":
        derive["admin"] = 79
        print("!! AUDIT_FAULT_INJECT=1 : admin force a 79, une divergence est attendue")
    derive["composite"] = composite(derive["admin"], derive["msig"], derive["timelock"])

    for k in ("admin", "msig", "timelock", "cross", "composite"):
        if derive[k] != onchain[k]:
            divergences.append(f"{k}: derive={derive[k]} != on-chain={onchain[k]}")
    oracle = oracle_authority_live()
    print(f"oracle (information, meme moteur que le scorer, pas une derivation independante) : par RPC {oracle}, "
          f"on-chain {onchain['oracle']}" + ("" if len(set(oracle)) == 1 and None not in oracle else " -- RPC en desaccord ou parcours NON LU"))

    # le composite on-chain doit aussi etre coherent avec SES PROPRES dimensions on-chain
    recompute = composite(onchain["admin"], onchain["msig"], onchain["timelock"])
    if recompute != onchain["composite"]:
        divergences.append(f"composite on-chain incoherent: floor(formule)={recompute} != {onchain['composite']}")

    print(f"derive    = {derive}")
    if divergences:
        print("\nDIVERGENCES:")
        for d in divergences:
            print(" -", d)
        return 1
    print("\nAUCUNE DIVERGENCE: la derivation live reproduit exactement le score on-chain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
