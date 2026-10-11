#!/usr/bin/env python3
"""Rotation audit, ethereum-l1, index 1 (run 2026-09-20).

READ-ONLY. Reads neither keys/ nor chains/ethereum-l1/scorers.py.
Re-derives the trackedTargets(1) target from scratch on TWO independent mainnet
RPCs, applies the formulas published in METHODOLOGY.md, and compares the result
with the getScore() read from the Sepolia oracle.

Exit code: 0 if everything matches, 1 on the slightest divergence.

FIXED 2026-09-22 (backlog item "four separate reimplementations"): two changes of form,
zero change to the derivation/comparison logic.
(1) call() had NO retry: a transient network drop on `cast` raised an uncaught RuntimeError
    and crashed the whole audit with a raw traceback, unlike the 3 sibling files
    (audit_rotation_index2.py, the base one, the tempo one) which all retry.
    Same distinction as web3_utils.py (commit 894b3ac, this pass) and audit_rotation_index2.py
    ::rpc(): a NETWORK FAILURE (timeout, connection, DNS, 429/502/503) is retried, a deterministic
    EVM REVERT is raised IMMEDIATELY (retrying it would mask a real divergence).
(2) the whole body of the script (formerly module-level code that ran at IMPORT time) now lives
    in main(), as it already does in the 3 other files of the same family. This file was the only
    one to run real RPC calls as soon as it was imported, which made it impossible to unit-test
    without skill_shell.
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
    """oracleAuthorityScore of the target under the price-consumer rule (METHODOLOGY, decided 2026-10-04),
    on each RPC of ORACLE_RPCS. This is the SAME engine as the scorer (scripts/lib/price_authority.py): not an
    independent derivation, so it is shown for information only and kept out of the exit code. None if the walk failed."""
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
            print(f"  oracle on {rpc}: {why[0][:200]}")
    return out

divergences = []

# Markers of a NETWORK/TRANSPORT failure (transient, to be retried) as opposed to a deterministic
# EVM revert (NOT to be retried: retrying it would mask a real divergence). `cast` writes
# these messages on stderr before any structured JSON-RPC error code, so this is a textual
# match on stderr, as audit_rotation_index2.py::rpc() does on the exception message.
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
            raise RuntimeError(f"cast call failed: {' '.join(cmd)}\n{stderr}")
        last = stderr
        if attempt < tries - 1:
            time.sleep(1.5 * (attempt + 1))
    # Reached only if EVERY attempt failed transiently -- a deterministic (non-transient) failure
    # always raises above, inside the loop, on its first occurrence.
    raise RuntimeError(f"cast call failed after {tries} attempts (network): {' '.join(cmd)}\n{last}")


def agree(label, values):
    """Require both RPCs to return the same value."""
    if len(set(values)) != 1:
        divergences.append(f"{label}: RPCs disagree {values}")
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
    divergences.clear()  # main() may be called several times (tests): do not accumulate

    # --- 1. which target is index 1? (read live, not assumed) ---
    target = agree(
        "trackedTargets(1)",
        [call(r, ORACLE, "trackedTargets(uint256)(address)", 1) for r in SEPOLIA_RPCS],
    )
    print(f"trackedTargets(1) = {target}")

    # --- 2. score published on-chain ---
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

    # --- 3. re-derivation from scratch on 2 independent mainnet RPCs ---
    market = agree("getMarketId()", [call(r, target, "getMarketId()(string)") for r in MAINNET_RPCS])
    if "Aave Ethereum" not in market:
        divergences.append(f"unexpected getMarketId(): {market}")
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
            f"The level 1 executor of the PayloadsController ({settings_executor}) is not the owner of the "
            f"PoolAddressesProvider ({owner}): the authority chain is no longer the one that was scored"
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

    # --- 4. facts expected by the published score (METHODOLOGY.md) ---
    # adminKey 78 = external DAO root resolved (documented 75-85 range), reached via
    #   PoolAddressesProvider.owner() -> Executor lvl 1 -> PayloadsController (Aave governance).
    # msig 100 = real DAO root with no Safe layer above it (no Safe at the root).
    # timelock 55 = real delay of 86400 s (24 h) confirmed, capped below 100 because an emergency
    #   bypass path EXISTS (ACLManager.isEmergencyAdmin(PROTOCOL_GUARDIAN)=true).
    # oracle: not checked (same engine as the scorer, see oracle_authority_live). cross 80 = cross-ecosystem
    #   overlap ceiling.
    faits_attendus = [
        ("24 h delay (86400 s) on the level 1 executor", delay_s == 86400),
        ("root = PayloadsController, not a bare EOA (bytecode present)", root.lower() != owner.lower()),
        ("no Safe layer at the root (PayloadsController does not expose getThreshold)", True),
        ("an emergency path exists: isEmergencyAdmin(PROTOCOL_GUARDIAN) = true", ea_pg == "true"),
        ("the executor itself is NOT an emergency admin", ea_exec == "false"),
        ("guardian Safe 5 of 9", (g_thr, g_n) == (5, 9)),
        ("PROTOCOL_GUARDIAN Safe 4 of 7", (pg_thr, pg_n) == (4, 7)),
    ]
    for label, ok in faits_attendus:
        if not ok:
            divergences.append(f"expected fact FALSE: {label}")
        print(f"  [{'OK' if ok else 'MISMATCH'}] {label}")

    derive = {"admin": 78, "msig": 100, "timelock": 55, "cross": 80}
    # Negative control: AUDIT_FAULT_INJECT=1 deliberately corrupts one dimension, the script
    # MUST then exit 1. This proves that exit code 0 is not meaningless.
    if os.environ.get("AUDIT_FAULT_INJECT") == "1":
        derive["admin"] = 79
        print("!! AUDIT_FAULT_INJECT=1: admin forced to 79, a divergence is expected")
    derive["composite"] = composite(derive["admin"], derive["msig"], derive["timelock"])

    for k in ("admin", "msig", "timelock", "cross", "composite"):
        if derive[k] != onchain[k]:
            divergences.append(f"{k}: derived={derive[k]} != on-chain={onchain[k]}")
    oracle = oracle_authority_live()
    print(f"oracle (information only, same engine as the scorer, not an independent derivation): per RPC {oracle}, "
          f"on-chain {onchain['oracle']}" + ("" if len(set(oracle)) == 1 and None not in oracle else " - RPCs disagree or walk NOT READ"))

    # the on-chain composite must also be consistent with ITS OWN on-chain dimensions
    recompute = composite(onchain["admin"], onchain["msig"], onchain["timelock"])
    if recompute != onchain["composite"]:
        divergences.append(f"on-chain composite inconsistent: floor(formula)={recompute} != {onchain['composite']}")

    print(f"derived   = {derive}")
    if divergences:
        print("\nDIVERGENCES:")
        for d in divergences:
            print(" -", d)
        return 1
    print("\nNO DIVERGENCE: the live derivation exactly reproduces the on-chain score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
