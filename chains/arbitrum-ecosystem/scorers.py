"""
Arbitrum Ecosystem authority scorers -- first 5 flagship targets (2026-09-17,
scoring_build), plus 4 more added 2026-09-19 (maintenance run: Compound V3,
Pendle V2, Fluid, Uniswap V3 -- see data/scored_targets_2026-09-19-maintenance.md).
score_gmx_v2_rolestore() was CORRECTED the same day (71 -> 22), see
data/rotation_audit_2026-09-19-index0-gmx-rolestore.md.

Reuses this project's existing methodology exactly as-is (same pattern as
Robinhood Chain's `scripts/lib/scorers.py`, `chains/ethereum-l1/scorers.py`
and `chains/base-ecosystem/scorers.py`): live eth_call against a public
Arbitrum One mainnet RPC (chain 42161), address sourced from the protocol's
own official docs/GitHub repo, authority traced to its root (Safe
getOwners+getThreshold / custom RoleStore role membership / OpenZeppelin
TimelockController / cross-chain governance executor pair), never trusted
from a prior pass or a block explorer's "verified name".

The 5 targets scored here are the exact 5 approved 3/3 in the scouting pass
(maker-checker action 22, see
`chains/arbitrum-ecosystem/data/scouted_targets_2026-09-16.md` for the full
trace, verification commands, and every open thread disclosed there). Every
live call this module makes was independently re-confirmed against
`https://arb1.arbitrum.io/rpc` in this pass (2026-09-17, scoring_build
attempt 1) before this file was written -- see
`runs/2026-09-17/arbitrum-ecosystem/claims_attempt1.txt`.

Each scorer returns a dict with the AuthorityScore fields (including
`crossExposureScore`, defaulted to 100/"not applicable" here -- see its own
docstring below) plus a `notes` list explaining what was found, so a re-run's
output is still readable without re-reading this file.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
from web3_utils import (  # noqa: E402
    EIP1967_ADMIN_SLOT,
    arbitrum_l1_l2_alias,
    call_raw,
    get_w3,
    is_eoa,
    read_address_getter,
    read_slot_as_address,
    safe_owners_and_threshold,
    safe_score,
)
from safe_modules import note_for, read_guard, read_modules  # noqa: E402

# crossExposureScore is a property of the SET of tracked targets (does the same
# root signer also control ANOTHER tracked target?), computed project-wide in
# scripts/lib/signer_overlap.py for Robinhood Chain's own target set, and in
# scripts/lib/cross_ecosystem_overlap.py's ARBITRUM_GROUPS for cross-ecosystem
# comparisons. UPDATED 2026-09-19 (was stale -- this comment used to claim no
# cross-ecosystem dataset existed at all for Arbitrum, no longer true since
# 2026-09-17): score_aave_v3_pool_arbitrum() below computes a REAL
# cross-exposure value live against a known committee snapshot (see its own
# comment). Every OTHER scorer below still reports 100 ("no overlap found")
# with an explicit note that this dimension was NOT computed for that
# specific target this pass -- not fabricated, and not yet audited against
# ARBITRUM_GROUPS' full comparison set either. UPDATED 2026-09-20:
# score_radiant_lendingpool() now carries its own dated, specific note for the
# pool-admin Safe it scores (owner sets compared live against the tracked
# root-signer groups: no match; still 100, "no overlap found" not "proof of none").
_CROSS_EXPOSURE_NOTE = (
    "crossExposureScore = 100 (not computed THIS TARGET this pass -- this file's Aave scorer "
    "does compute a real cross-ecosystem value, see scripts/lib/cross_ecosystem_overlap.py's "
    "ARBITRUM_GROUPS; this target's own authority was not checked against that dataset, treated "
    "as 'not applicable' per this project's convention, not as a confirmed clean result)"
)

# See both Base's and Ethereum-L1's scorers.py for the "open item" this note
# points at: the L1 DAO root of a cross-chain-relayed governance executor
# (Aave's EXECUTOR_LVL_1, Uniswap's aliased L1 Timelock) is not re-derived
# hop-by-hop from an ecosystem-scoped scorer. The scouting pass for Arbitrum
# flagged the exact same open item for its own Aave V3 Pool target and
# proposed treating it as one shared sub-model rather than five separate
# ad hoc guesses -- see the "A faire" card already open on the tracker board
# ("transverse -- sous-modele 'gouvernance DAO externe via bridge'"). Not
# built this pass; each scorer below discloses its own slice of the gap
# individually, same as its Base/Ethereum-L1 siblings do today.


def _composite(admin_key, multisig, timelock):
    """Standard project weighting: 0.4*adminKey + 0.3*multisig + 0.3*timelock,
    oracleAuthorityScore excluded (not applicable to any of these 5 targets --
    none of them is itself an oracle/price-feed authority). Uses standard
    round-half-up via floor(x + 0.5), not Python's builtin round() (banker's
    rounding) -- same fix already applied in the root scorers.py,
    chains/ethereum-l1/scorers.py and chains/base-ecosystem/scorers.py, kept
    consistent here rather than reintroducing the bug this project already
    caught once."""
    import math

    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


_GMX_ROLE_MEMBERS_ABI = [{"name": "getRoleMembers", "type": "function", "stateMutability": "view",
                          "inputs": [{"type": "bytes32"}, {"type": "uint256"}, {"type": "uint256"}],
                          "outputs": [{"type": "address[]"}]}]
_OZ_HAS_ROLE_ABI = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                     "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
_GET_MIN_DELAY_ABI = [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]


def _gmx_role(name):
    """GMX `Role.sol` pattern: keccak256(abi.encode(string)), NOT the plain
    keccak256(bytes) OpenZeppelin uses for PROPOSER_ROLE/EXECUTOR_ROLE."""
    from eth_abi import encode
    from web3 import Web3

    return Web3.keccak(encode(["string"], [name]))


def _weakest_key(candidates):
    """Project convention (same (k, -n) ordering as chains/zcash/scorers.py):
    lowest threshold first, then the LARGER owner count at equal threshold
    (more key combinations reach it). An unresolved contract is encoded as
    k=0 so it sorts weakest -- never silently assumed to be a strong key."""
    return min(candidates, key=lambda c: (c[0], -c[1])) if candidates else None


# ADDED 2026-09-20: role holders of the GMX DAO timelock (a ROLE_ADMIN member of the RoleStore,
# 0x4bd1cdAa...). Its OpenZeppelin AccessControl is not enumerable, so the holders come from an
# indexer log replay (2026-09-20) and are re-read with hasRole on every run: a bare EOA and the
# GMX Governor contract. Each was re-confirmed on two RPCs the same day.
_GMX_DAO_TIMELOCK_HOLDER_CANDIDATES = (
    "0xE7BfFf2aB721264887230037940490351700a068",
    "0x03e8f708e9C85EDCEaa6AD7Cd06824CeB82A7E68",
)


def score_gmx_v2_rolestore(w3) -> dict:
    """GMX V2 (Synthetics) RoleStore (Arbitrum) -- ~$203M TVL (DefiLlama
    `gmx-v2-perps`, chainTvls.Arbitrum, pulled 2026-09-19). Source:
    official `gmx-io/gmx-synthetics` GitHub repo,
    `deployments/arbitrum/RoleStore.json`.

    CORRECTED 2026-09-19 (rotation audit index 0, see
    `chains/arbitrum-ecosystem/data/rotation_audit_2026-09-19-index0-gmx-rolestore.md`).
    The previous version of this scorer traced the wrong hop and missed a
    bare EOA on the path it did trace:

    1. It checked `ConfigTimelockController` at `0xC77E6C0c...DEaF5`, the
       address in GMX's repo `deployments/arbitrum/ConfigTimelockController.json`.
       Live, that contract holds NO role at all on this RoleStore
       (`hasRole(0xC77E..., ROLE_ADMIN)` = false on 2 RPCs). The live
       `ROLE_ADMIN` holders are the GMX DAO timelock (`0x4bd1cdAa...`), a
       DIFFERENT `ConfigTimelockController` (`0x2Dd99f39...`, Sourcify exact
       match) and `TimelockConfig` (`0xE7706986...`, Sourcify exact match),
       whose own `timelockController()` points at `0x2Dd99f39...`.
    2. `TIMELOCK_ADMIN` on this RoleStore is held by 3 addresses, one of
       which (`0xE014cbD6...`, labelled `timelock_admin_2` in GMX's own
       `config/roleConfigs/arbitrum.ts`) is a bare EOA. `TimelockConfig`'s
       `signalGrantRole()` and `execute()` are both `onlyTimelockAdmin`, and
       the same EOA also holds PROPOSER/EXECUTOR/CANCELLER directly on the
       live `ConfigTimelockController`. A single key can therefore queue and,
       24h later, execute a grant of ANY RoleStore role (ROLE_ADMIN
       included). The 5-of-8 `TIMELOCK_MULTISIG` Safe holds CANCELLER on
       that controller and `revokeRole()` is `onlyTimelockMultisig`, so the
       defence is a 24h veto window, not a multisig requirement.

    This scorer now resolves the path live instead of hardcoding it:
    ROLE_ADMIN members -> the one exposing `timelockController()` that is
    itself a ROLE_ADMIN member (= the live controller) -> its
    `getMinDelay()`; every other ROLE_ADMIN member must itself be a
    timelock with a non-zero delay (bypass check). Initiators = every
    `TIMELOCK_ADMIN` member, classified (Safe (k, n) / bare EOA / unresolved
    contract), and the weakest one sets adminKeyScore/multisigScore per
    METHODOLOGY.md (bare EOA root: adminKey in the 2-10 band, multisig 0).
    The delay plus the confirmed Safe veto is what timelockScore rewards.

    ADDED 2026-09-20 (unscored-role sweep, section 4, re-derived by hand): the OTHER ROLE_ADMIN
    timelock, the GMX DAO timelock `0x4bd1cdAa...` (24h delay), is not only a Governor path.
    A bare EOA (`0xE7BfFf2a...`, 2,870 transactions, ~2 ETH) holds PROPOSER, EXECUTOR and CANCELLER
    on it next to the Governor contract, and the RoleStore's 5-of-8 Safe holds NONE of those roles
    there. Simulated by `eth_call` (no transaction): `schedule(RoleStore, grantRole(x, ROLE_ADMIN))`
    passes from that EOA and reverts from a random address and from the Safe. So a single key can
    queue and, 24h later, execute a ROLE_ADMIN grant with no Governor vote AND no Safe veto: the
    same class of path as the TIMELOCK_ADMIN EOA above, but without the veto window. adminKey and
    multisig were already at the bare-EOA floor, so only timelockScore moves: a Safe veto is
    credited (60) only when it covers every EOA-initiated path; otherwise 50."""
    from web3 import Web3

    target = "0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72"
    notes = []

    def members(role_name):
        m = call_raw(w3, target, _GMX_ROLE_MEMBERS_ABI, "getRoleMembers", _gmx_role(role_name), 0, 50)
        return [Web3.to_checksum_address(a) for a in (m or [])]

    role_admins = members("ROLE_ADMIN")
    timelock_admins = members("TIMELOCK_ADMIN")
    timelock_multisigs = members("TIMELOCK_MULTISIG")
    notes.append(f"RoleStore ROLE_ADMIN members = {role_admins}")
    notes.append(f"RoleStore TIMELOCK_ADMIN members = {timelock_admins}")
    notes.append(f"RoleStore TIMELOCK_MULTISIG members = {timelock_multisigs}")

    admin_set = {a.lower() for a in role_admins}
    controller = timelock_config = None
    for m in role_admins:
        c = read_address_getter(w3, m, "timelockController")
        if c and c.lower() in admin_set:
            controller, timelock_config = Web3.to_checksum_address(c), m
            break
    delay = call_raw(w3, controller, _GET_MIN_DELAY_ABI, "getMinDelay") if controller else None
    if controller:
        notes.append(f"live ConfigTimelockController resolved via TimelockConfig {timelock_config}.timelockController() = {controller}, getMinDelay() = {delay}s")
    else:
        notes.append("no ROLE_ADMIN member exposes a timelockController() that is itself ROLE_ADMIN -- controller unresolved this run")

    others = [m for m in role_admins if controller and m.lower() not in (controller.lower(), timelock_config.lower())]
    other_delays = {m: call_raw(w3, m, _GET_MIN_DELAY_ABI, "getMinDelay") for m in others}
    bypass_free = bool(controller) and all(d is not None and d > 0 for d in other_delays.values())
    notes.append(f"bypass check, other ROLE_ADMIN members' own getMinDelay() = {other_delays} (all non-zero: {bypass_free})")

    initiators = []
    for a in timelock_admins:
        s = safe_owners_and_threshold(w3, a)
        if s:
            initiators.append((s[1], len(s[0]), a, "Safe"))
        elif is_eoa(w3, a):
            initiators.append((1, 1, a, "bare EOA"))
        else:
            initiators.append((0, 0, a, "unresolved contract"))
    notes.append("TIMELOCK_ADMIN initiators (can signalGrantRole via TimelockConfig, then execute after the delay): " + ", ".join(f"{a} = {kind} {k}-of-{n}" for k, n, a, kind in initiators))

    # ADDED 2026-09-20: the other ROLE_ADMIN timelock(s) (the GMX DAO timelock) have their own
    # proposers. A bare EOA that can propose AND execute there is one more single-key path to a
    # ROLE_ADMIN grant, and the RoleStore's veto Safe may hold no CANCELLER on that timelock.
    dao_path_unvetoed = False
    role_hash = {r: Web3.keccak(text=r) for r in ("PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE")}
    for m in others:
        if not (other_delays.get(m) or 0) > 0:
            continue
        holder_facts = []
        for h in _GMX_DAO_TIMELOCK_HOLDER_CANDIDATES:
            hh = Web3.to_checksum_address(h)
            roles = {r: call_raw(w3, m, _OZ_HAS_ROLE_ABI, "hasRole", role_hash[r], hh) for r in role_hash}
            if not any(v is True for v in roles.values()):
                continue
            holder_kind = "bare EOA" if is_eoa(w3, hh) else "contract"
            holder_facts.append(f"{hh} ({holder_kind}: " + "/".join(r.replace("_ROLE", "") for r, v in roles.items() if v is True) + ")")
            if holder_kind == "bare EOA" and roles["PROPOSER_ROLE"] is True and roles["EXECUTOR_ROLE"] is True:
                if not any(a.lower() == hh.lower() for _, _, a, _ in initiators):
                    initiators.append((1, 1, hh, "bare EOA"))
                safe_cancels = bool(timelock_multisigs) and call_raw(w3, m, _OZ_HAS_ROLE_ABI, "hasRole", role_hash["CANCELLER_ROLE"], timelock_multisigs[0]) is True
                if not safe_cancels:
                    dao_path_unvetoed = True
        if holder_facts:
            notes.append(
                f"ROLE_ADMIN timelock {m} (getMinDelay {other_delays.get(m)}s) role holders among the dated candidates: " + "; ".join(holder_facts)
                + ". A bare EOA holding PROPOSER and EXECUTOR there can queue and, after the delay, execute a RoleStore grant with no Governor vote "
                + ("and with NO veto from the RoleStore's Safe (it holds no CANCELLER on this timelock): the Safe veto credit is dropped" if dao_path_unvetoed
                   else "(the RoleStore's Safe also holds CANCELLER there, so the veto window covers it)")
                + " (simulated 2026-09-20 by eth_call, not re-simulated per run)."
            )
    weakest = _weakest_key(initiators)

    veto_safe = None
    if len(timelock_multisigs) == 1 and controller:
        vs = safe_owners_and_threshold(w3, timelock_multisigs[0])
        can_cancel = call_raw(w3, controller, _OZ_HAS_ROLE_ABI, "hasRole", Web3.keccak(text="CANCELLER_ROLE"), timelock_multisigs[0])
        if vs and can_cancel:
            veto_safe = (vs[1], len(vs[0]))
            notes.append(f"veto path confirmed: TIMELOCK_MULTISIG {timelock_multisigs[0]} is a {vs[1]}-of-{len(vs[0])} Safe holding CANCELLER_ROLE on the live controller (and revokeRole() is onlyTimelockMultisig)")
    if not veto_safe:
        notes.append("veto path NOT confirmed this run (TIMELOCK_MULTISIG not a single Safe with CANCELLER_ROLE on the live controller)")

    if not (controller and delay and delay > 0 and weakest):
        notes.append("authority path unresolved this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        k, n, weakest_addr, kind = weakest
        notes.append(f"weakest initiator by (k, -n): {weakest_addr} ({kind}, {k}-of-{n})")
        if kind == "bare EOA":
            admin_key, multisig = 10, 0  # METHODOLOGY.md bare-EOA band (2-10), top of band because the EOA cannot act inside the 24h window
        elif kind == "unresolved contract":
            admin_key, multisig = 20, 0
        else:
            admin_key = 65 if k >= 3 else (50 if k == 2 else 10)
            multisig = min(100, k * 15 + max(0, n - k) * 5)
        if not bypass_free:
            timelock_score = 0
        else:
            timelock_score = 60 if (veto_safe and not dao_path_unvetoed) else 50

    # ADDED 2026-09-21 (symmetry with score_gmx_v1_vault, tracked index 9): the tokenManager Safe that can instantly
    # replace the V1 Vault's timelock admin also holds proposer/executor/canceller rights on the GMX V2 controller that is
    # a ROLE_ADMIN of THIS RoleStore. Sharing a root is symmetric, so this target must read it too, not only the V1 Vault.
    cross_exposure = 100
    v1_gov = read_address_getter(w3, _GMX_V1_VAULT, "gov")
    v1_token_manager = read_address_getter(w3, v1_gov, "tokenManager") if v1_gov else None
    v2_timelock_is_role_admin = _GMX_V2_TIMELOCK.lower() in admin_set
    if v1_token_manager and v2_timelock_is_role_admin:
        tm_roles = {
            r: call_raw(w3, _GMX_V2_TIMELOCK, _OZ_HAS_ROLE_ABI, "hasRole", role_hash[r], Web3.to_checksum_address(v1_token_manager))
            for r in role_hash
        }
        notes.append(
            f"GMX V1 Vault tokenManager Safe {v1_token_manager} roles on the GMX V2 timelock {_GMX_V2_TIMELOCK} "
            f"(a ROLE_ADMIN member of THIS RoleStore): {tm_roles}"
        )
        if any(v is True for v in tm_roles.values()):
            cross_exposure = 80
            notes.append(
                "crossExposureScore = 80: the same Safe that can instantly replace the tracked GMX V1 Vault's timelock "
                "admin (index 9) also holds proposer/executor/canceller rights on a timelock that is a ROLE_ADMIN of this "
                "RoleStore. One committee, two tracked targets -- 100 - 20 * 1 shared group, the same value the V1 Vault "
                "reads (the relation is symmetric)."
            )
        elif all(v is False for v in tm_roles.values()):
            notes.append("crossExposureScore = 100: the V1 Vault's tokenManager Safe holds no role on the GMX V2 timelock this run")
        else:
            notes.append(_CROSS_EXPOSURE_NOTE)
    else:
        notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "GMX V2 (Synthetics) RoleStore (Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_camelot_ammv3_factory(w3) -> dict:
    """Camelot -- AMMv3 (Algebra) Factory (Arbitrum-native) -- ~$6.2M TVL for
    this deployment. Source: Camelot's own official docs,
    `docs.camelot.exchange/contracts/arbitrum/one-mainnet`, `AlgebraFactory`
    row. Authority: `owner()` -> a real Gnosis Safe, **2-of-3**, with no
    `TimelockController` layer found in front of it -- confirmed live this
    run, same result as scouting.

    Weaker than every other target in this batch on the multisig dimension
    (only 3 total signers, no delay at all), scored as-is rather than
    smoothed: this is a genuinely thinner authority setup than GMX, Radiant,
    the Security Council Safe or Aave, not a scoring artifact."""
    target = "0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B"
    notes = []

    owner = read_address_getter(w3, target, "owner")
    notes.append(f"Factory.owner() = {owner}")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}, no TimelockController found in front of it")
        eoa_flags = {o: is_eoa(w3, o) for o in owners}
        notes.append(f"owner EOA check (expected all True, bare EOAs not smart-contract signers): {eoa_flags}")
        admin_key = 50 if threshold == 2 else (65 if threshold >= 3 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController or delay found anywhere in this chain

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "Camelot AMMv3 (Algebra) Factory (Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ADDED 2026-09-20 (see data/finding_2026-09-20-unscored-role-sweep.md section 3):
# Radiant's cross-exposure check for the pool-admin Safe scored below. The
# dimension is "does the same root signer also control ANOTHER tracked target".
# The 11 owners of the pool-admin Safe and the 5 owners of the emergency-admin
# Safe were compared live on 2026-09-20 (owner addresses, case-insensitive, plus
# the two Safe addresses themselves) against every root-signer group resolved by
# scripts/check_cross_ecosystem_overlap.py's inputs (70 groups, 7 ecosystems),
# and by grep against every file of this repo: no match. This is a dated
# snapshot, not something the scorer re-runs (no second RPC connection inside a
# scorer), so it is "no overlap found", not proof of none.
_RADIANT_CROSS_EXPOSURE_NOTE = (
    "crossExposureScore = 100 (checked live 2026-09-20 against the other 70 root-signer groups tracked across 7 "
    "ecosystems in scripts/lib/signer_overlap.py and scripts/lib/cross_ecosystem_overlap.py, where both Safes are now "
    "registered as the group radiant_pool_admin: none of the pool-admin Safe's owners nor the emergency-admin Safe's "
    "owners, nor either Safe address, matches; a dated snapshot not re-run by this scorer, 'no overlap found' is not "
    "proof of none)"
)


def score_radiant_lendingpool(w3) -> dict:
    """Radiant Capital -- LendingPool (V2 Core, Arbitrum) -- ~$184K supplied /
    ~$97.7K borrowed, a tiny residual TVL flagged in scouting as itself
    informative (see below), not a "flagship by size" target. Source:
    Radiant's own docs, `docs.radiant.capital/radiant/contracts-and-security/
    arbitrum-contracts`, `lendingPool:` field, cross-checked live this run
    against `PoolAddressesProvider.getLendingPool()` -- confirms the live pool
    address rather than a stale/aggregator-sourced one (the scouting pass
    found the DefiLlama-Adapters address was NOT the live pool; this scorer
    re-derives the live address directly, not from that prior note).

    Authority chain, CORRECTED 2026-09-20 (see
    `data/finding_2026-09-20-unscored-role-sweep.md` section 3). The previous
    version credited `PoolAddressesProvider.owner()`, an OpenZeppelin
    `TimelockController` (72h `getMinDelay()`), as the only root. That is the
    root for the provider's own `onlyOwner` functions (pool / configurator
    logic upgrades), but NOT for the LendingPoolConfigurator's `onlyPoolAdmin`
    functions (`updateAToken` / `updateStableDebtToken` /
    `updateVariableDebtToken`, which `upgradeToAndCall` the token proxies,
    `freezeReserve`, `setReserveFactor`, caps,
    `setReserveInterestRateStrategyAddress`, `batchInitReserve`). Those are
    gated by `provider.getPoolAdmin()`, a DIFFERENT address on the live chain:
    a 4-of-11 Gnosis Safe, with no delay in front of it. Verified 2026-09-20
    by two independent agents plus `eth_call` simulation (passes when called
    from that Safe, reverts `Error('33')` CALLER_NOT_POOL_ADMIN from the
    timelock and from a random address); this scorer only READS state, it does
    not re-simulate. The same Safe also holds PROPOSER and CANCELLER on the
    timelock (read live here) and 6 of its 11 owners hold EXECUTOR, so the
    timelock delays that committee on the provider-level path but does not
    bind the fund-affecting token-upgrade path.

    Scoring: pool_admin unread, or provider.owner() unread (the bypass test
    needs both reads) -> conservative (20, 0, 0). Pool admin different but
    provider.owner() not answering getMinDelay() (provider-level path
    unverified) -> conservative (20, 0, 0) too. Pool admin equal to the
    timelock (no bypass) -> the previous timelock scoring, unchanged. Pool
    admin different and a Safe -> the repo's Safe-with-no-timelock scale
    (adminKey 65 if threshold >= 3, 50 if 2, 10 if 1; multisig
    threshold*15 + surplus owners*5 capped at 100; timelock 0), because the
    binding fund-affecting path has no delay. Pool admin different and NOT
    resolvable as a Safe -> conservative (20, 0, 0). A separate
    `getEmergencyAdmin()` (a 1-of-5 Safe whose owners are all also owners of
    the pool-admin Safe) can only `setPoolPause`: an availability-only path,
    DISCLOSED BUT NOT SCORED (the repo convention for pause/freeze powers,
    same treatment as `score_compound_v3_comet_arbitrum_usdc`'s pauseGuardian).
    The residual exposure figure moves and is deliberately not hardcoded.

    Aggravating context, carried forward from scouting rather than re-derived
    here (a historical event, not a live-chain fact): on 2024-10-16, Radiant
    was exploited for ~$50M via compromise of multiple multisig signers'
    devices (blind-signing), corroborated by two independent sources
    (DefiLlama's public hacks dataset and Radiant's own remediation docs).
    This is precisely the failure mode a Safe-plus-timelock pattern does not
    protect against -- the timelock delays a proposal from a compromised
    signer set, it does not stop the signers themselves being compromised --
    and the token-upgrade path scored here has no timelock at all. Not folded
    into the score as an extra penalty (this project scores the CURRENT
    authority mechanism, not historical incidents against it), but disclosed
    here since it directly bears on how much trust to place in the admin-key
    dimension for this specific target."""
    from web3 import Web3

    lending_pool = "0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886"
    provider = "0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a"
    notes = []

    live_pool = read_address_getter(w3, provider, "getLendingPool")
    notes.append(
        f"PoolAddressesProvider.getLendingPool() = {live_pool} "
        f"(matches expected/docs address: {live_pool == lending_pool if live_pool else 'N/A'})"
    )

    provider_owner = read_address_getter(w3, provider, "owner")
    notes.append(f"PoolAddressesProvider.owner() = {provider_owner} (expected the TimelockController)")

    delay = call_raw(w3, provider_owner, _GET_MIN_DELAY_ABI, "getMinDelay") if provider_owner else None
    notes.append(f"TimelockController.getMinDelay() = {delay}s (Radiant docs cite a 72h / 259,200s Security Timelock)")

    # ADDED 2026-09-20: the provider's pool admin gates the configurator's
    # token-upgrade / freeze / cap / rate-strategy functions and is NOT the
    # timelock on the live chain. See the docstring.
    pool_admin = read_address_getter(w3, provider, "getPoolAdmin")
    notes.append(f"PoolAddressesProvider.getPoolAdmin() = {pool_admin} (gates the LendingPoolConfigurator's onlyPoolAdmin functions)")
    emergency_admin = read_address_getter(w3, provider, "getEmergencyAdmin")
    emergency_safe = safe_owners_and_threshold(w3, emergency_admin) if emergency_admin else None

    notes.append(
        "Aggravating context (not folded into the score, disclosed): on 2024-10-16, Radiant "
        "was exploited for ~$50M via compromised multisig-signer devices (blind signing) "
        "across Arbitrum and BSC. A timelock does not defend against the signers themselves "
        "being compromised -- see chains/arbitrum-ecosystem/data/scouted_targets_2026-09-16.md "
        "target #3 for both independent sources (DefiLlama hacks dataset, Radiant's own docs)."
    )

    pool_confirmed = bool(live_pool and live_pool == lending_pool)
    cross_note = _CROSS_EXPOSURE_NOTE
    pool_admin_owners = None  # set only when the pool admin resolves as a Safe, used by the emergency-admin overlap note

    if not pool_admin or not provider_owner:
        # The bypass test needs both reads. An unread authority never keeps a confident score.
        missing = " and ".join(n for n, v in (("getPoolAdmin()", pool_admin), ("owner()", provider_owner)) if not v)
        notes.append(
            f"{missing} unread this run -- cannot tell whether the timelock binds the configurator's "
            "onlyPoolAdmin functions, unresolved authority, conservative score"
        )
        admin_key, multisig, timelock_score = 20, 0, 0
    elif pool_admin.lower() == provider_owner.lower():
        # No bypass: the timelock is the pool admin too. NOT the live shape on 2026-09-20 (the pool admin
        # is a separate Safe, see the Safe branch below), kept exactly as scored before that correction.
        notes.append("getPoolAdmin() equals provider.owner(): no bypass, the timelock also governs the onlyPoolAdmin functions")
        chain_closed = pool_confirmed and delay is not None
        # Capped below GMX/Aave: single-timelock root. This branch does not enumerate the timelock's own
        # PROPOSER/EXECUTOR holders (not AccessControlEnumerable, per scouting's open item), so no multisig layer
        # is credited here; the Safe branch below DOES read those roles live for the Safe it finds.
        admin_key = 55 if chain_closed else 25
        multisig = 100  # not applicable: TimelockController is not a Safe, no separate multisig layer traced in this branch
        timelock_score = 55 if delay and delay > 0 else 0  # confirmed real 72h delay live; capped below GMX's Safe+timelock combo since proposer/executor role holders are not enumerated in this branch
    elif delay is None:
        # provider.owner() did not answer getMinDelay(): the provider-level path is not confirmed as timelocked, and
        # a bare-EOA owner there would be weaker than the pool-admin Safe, so no confident score is kept.
        notes.append(
            f"getPoolAdmin() = {pool_admin} differs from provider.owner() {provider_owner}, but provider.owner() did not "
            "answer getMinDelay() (not confirmed as a TimelockController, or a transient read failure) -- the provider-level "
            "path is unverified, unresolved authority, conservative score"
        )
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        pool_safe = safe_owners_and_threshold(w3, pool_admin)
        if not pool_safe:
            notes.append(
                f"getPoolAdmin() = {pool_admin} differs from provider.owner() {provider_owner} but is NOT "
                "resolvable as a Gnosis Safe this run -- unresolved authority, conservative score"
            )
            admin_key, multisig, timelock_score = 20, 0, 0
        else:
            owners, threshold = pool_safe
            gates = (f"it does gate the provider-level owner functions such as pool / configurator logic upgrades ({delay}s delay)"
                     if delay > 0 else "provider.owner() reports a 0s delay, so even the provider-level owner functions are not delayed")
            notes.append(
                f"getPoolAdmin() differs from provider.owner() {provider_owner}: pool admin is a Gnosis Safe, "
                f"{threshold}-of-{len(owners)}, with NO timelock in front of the configurator's onlyPoolAdmin functions "
                "(updateAToken / updateStableDebtToken / updateVariableDebtToken, which upgradeToAndCall the token proxies; "
                "freezeReserve, setReserveFactor, caps, setReserveInterestRateStrategyAddress, batchInitReserve). "
                "The timelock does not bind these (simulated by the 2026-09-20 verification pass, not re-simulated by this "
                f"scorer: passes from this Safe, reverts Error('33') CALLER_NOT_POOL_ADMIN from the timelock and from a random address); {gates}"
            )
            has_role = lambda role, who: call_raw(w3, provider_owner, _OZ_HAS_ROLE_ABI, "hasRole", Web3.keccak(text=role), who)  # noqa: E731
            proposer = has_role("PROPOSER_ROLE", pool_admin)
            canceller = has_role("CANCELLER_ROLE", pool_admin)
            executors = [has_role("EXECUTOR_ROLE", o) for o in owners]
            notes.append(
                f"live role reads on the timelock: pool-admin Safe holds PROPOSER_ROLE = {proposer}, CANCELLER_ROLE = {canceller}; "
                f"{sum(1 for e in executors if e is True)} of its {len(owners)} owners hold EXECUTOR_ROLE "
                f"({sum(1 for e in executors if e is None)} unread) -- the same committee that acts immediately on the "
                "onlyPoolAdmin path also drives the timelock's own path after the delay"
            )
            pool_admin_owners = {o.lower() for o in owners}
            admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
            if not pool_confirmed:
                admin_key = min(admin_key, 25)  # same cap the pre-2026-09-20 scorer applied when the live pool diverges from the docs address
            multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
            timelock_score = 0  # the fund-affecting path (token upgrades) has no delay at all
            cross_note = _RADIANT_CROSS_EXPOSURE_NOTE

    if emergency_admin:
        if emergency_safe:
            e_owners, e_threshold = emergency_safe
            shared = ("all of its owners are also owners of the pool-admin Safe" if pool_admin_owners and {o.lower() for o in e_owners} <= pool_admin_owners
                      else "owner overlap with the pool-admin Safe not established this run")
            notes.append(
                f"PoolAddressesProvider.getEmergencyAdmin() = {emergency_admin}, a {e_threshold}-of-{len(e_owners)} Safe ({shared}): "
                f"can setPoolPause with {e_threshold} signature(s) -- availability-only path, disclosed, not scored"
            )
            # ADDED 2026-09-21: modules and guard of the emergency Safe, read live (note only, never a score input).
            notes.append(note_for(emergency_admin, read_modules(w3, emergency_admin), read_guard(w3, emergency_admin)))
        else:
            notes.append(f"PoolAddressesProvider.getEmergencyAdmin() = {emergency_admin} (not resolvable as a Safe this run) -- pause-only path, disclosed, not scored")
    else:
        notes.append("PoolAddressesProvider.getEmergencyAdmin() unread this run -- pause-only path, not scored")

    notes.append(cross_note)
    return {
        "target": live_pool or lending_pool,
        "label": "Radiant Capital LendingPool (V2 Core, Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_arbitrum_security_council_safe(w3) -> dict:
    """Arbitrum Security Council -- Emergency Safe (L2, Arbitrum One) -- not a
    protocol with its own TVL: this Safe is the emergency-upgrade authority
    for Arbitrum One's own core protocol contracts, relevant to every
    protocol on the chain. Source: `OffchainLabs/governance` (official
    Arbitrum GitHub), `files/mainnet/scmDeployment.json`,
    `emergencyGnosisSafes["42161"]`.

    Authority: a real Gnosis Safe, **9-of-12**, confirmed live this run,
    holding `EXECUTOR_ROLE` on the L2 `UpgradeExecutor` -- confirmed live --
    which can bypass the ordinary L2 core `TimelockController`'s 8-day
    `getMinDelay()` for emergency action, re-confirmed live here. This is a
    standard, publicly-documented part of Arbitrum's own security model (an
    intentional emergency-bypass path, not a discovered flaw), scored on the
    strength of the Safe itself and the delay that DOES still apply to the
    ordinary (non-emergency) path."""
    target = "0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641"
    executor = "0xCF57572261c7c2BCF21ffD220ea7d1a27D40A827"
    timelock = "0x34d45e99f7D8c45ed05B5cA72D54bbD1fb3F98f0"
    notes = []

    from web3 import Web3

    safe = safe_owners_and_threshold(w3, target)
    if not safe:
        notes.append(f"{target}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"Emergency Safe: {threshold}-of-{len(owners)}")
        # ADDED 2026-09-21: modules and guard, read live (note only, never a score input).
        notes.append(note_for(target, read_modules(w3, target), read_guard(w3, target)))

        exec_role = Web3.keccak(text="EXECUTOR_ROLE")
        role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                     "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
        has_exec_role = call_raw(w3, executor, role_abi, "hasRole", exec_role, target)
        notes.append(f"L2 UpgradeExecutor.hasRole(EXECUTOR_ROLE, Safe) = {has_exec_role} (emergency-bypass authority, standard Arbitrum design)")

        delay = call_raw(w3, timelock, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay")
        notes.append(f"L2 core TimelockController.getMinDelay() = {delay}s (the ordinary, non-emergency delay this Safe can bypass)")

        admin_key = 55 if threshold >= 9 else (45 if threshold >= 5 else 20)  # capped below GMX/Aave's confirmed-active-DAO score: this IS the chain's own emergency root, not a bounded protocol-level authority, so a compromise here is maximally systemic -- reflected as a cap, not a bonus
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 40 if delay and delay > 0 else 0  # the ordinary delay is real and long (8 days), but this Safe's entire purpose is to bypass it in an emergency -- scored well below a target where the delay is the actual binding constraint

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "Arbitrum Security Council Emergency Safe (L2, Arbitrum One)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_aave_v3_pool_arbitrum(w3) -> dict:
    """Aave V3 -- Pool (Arbitrum) -- ~$489.2M supplied / ~$339.6M borrowed, by
    far the largest TVL scouted for this ecosystem. Source:
    `bgd-labs/aave-address-book` (official Aave-ecosystem GitHub, maintained
    by BGD Labs), `src/AaveV3Arbitrum.sol`, constant `POOL`.

    Authority chain, re-confirmed live this pass, same shape as
    `chains/base-ecosystem/scorers.py`'s `score_aave_v3_base()`:
    `PoolAddressesProvider.owner()` == `.getACLAdmin()` -> `EXECUTOR_LVL_1`
    <-> `PayloadsController` (mutual `owner()` pointers, a genuine closed
    pair, standard BGD Labs Aave Governance V3 cross-chain infra, confirmed
    live not a loop hiding the real authority).
    `PayloadsController.getExecutorSettingsByAccessControl(1)` gives the real
    per-access-level delay (confirmed live). A separate `GOVERNANCE_GUARDIAN`
    Safe can veto/cancel payloads -- confirmed live to be a real Safe, matches
    `PayloadsController.guardian()` exactly.

    Open thread, disclosed rather than guessed (same gap flagged in scouting
    and in the sibling Base scorer): this scorer confirms the Arbitrum-side
    executor/payloads-controller pair matches the official address book
    exactly, but does NOT independently re-verify the Ethereum-mainnet Aave
    DAO root (proposal counts, quorum, the L1 Timelock/Executor the
    `CROSS_CHAIN_CONTROLLER` ultimately relays from) -- out of scope for an
    Arbitrum-RPC-only scorer. `chains/ethereum-l1/scorers.py`'s own
    `score_aave_v3_pool()` covers that root directly. Same open item already
    flagged for Uniswap's L1-aliased governance elsewhere in this project --
    the scouting pass proposed a single shared "external L1 DAO governance
    via bridge" sub-model rather than scoring each case ad hoc, not built
    this pass."""
    provider = "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"
    acl_manager = "0xa72636CbcAa8F5FF95B2cc47F3CDEe83F3294a0B"
    notes = []

    executor = read_address_getter(w3, provider, "owner")
    notes.append(f"PoolAddressesProvider.owner() = {executor} (expected EXECUTOR_LVL_1)")

    acl_admin = call_raw(w3, provider, [{"name": "getACLAdmin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "getACLAdmin")
    notes.append(f"PoolAddressesProvider.getACLAdmin() = {acl_admin} (matches owner(): {acl_admin == executor})")

    payloads_controller = read_address_getter(w3, executor, "owner") if executor else None
    notes.append(f"EXECUTOR_LVL_1.owner() = {payloads_controller} (PayloadsController)")

    loop_check = read_address_getter(w3, payloads_controller, "owner") if payloads_controller else None
    notes.append(f"PayloadsController.owner() = {loop_check} (closes back to EXECUTOR_LVL_1: {loop_check == executor})")

    settings_abi = [{"name": "getExecutorSettingsByAccessControl", "type": "function", "stateMutability": "view",
                      "inputs": [{"type": "uint8"}], "outputs": [{"type": "tuple", "components": [{"type": "address"}, {"type": "uint40"}]}]}]
    settings = call_raw(w3, payloads_controller, settings_abi, "getExecutorSettingsByAccessControl", 1) if payloads_controller else None
    notes.append(f"PayloadsController.getExecutorSettingsByAccessControl(1) = {settings} (executor, delaySeconds)")

    guardian = call_raw(w3, payloads_controller, [{"name": "guardian", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "guardian") if payloads_controller else None
    notes.append(f"PayloadsController.guardian() = {guardian} (can cancel proposals outside the timelock)")

    guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    if guardian_safe:
        g_owners, g_threshold = guardian_safe
        notes.append(f"GOVERNANCE_GUARDIAN is a real Gnosis Safe: {g_threshold}-of-{len(g_owners)}")
    else:
        notes.append(f"{guardian}: NOT resolvable as a Gnosis Safe this run")

    # ADDED 2026-09-17 (closed a real cross-ecosystem gap, see
    # scripts/lib/cross_ecosystem_overlap.py's ARBITRUM_GROUPS/BASE_GROUPS
    # "aave_guardian" entries and their own docstring for the full finding):
    # this Safe's own owner set was live-compared, the same day, against
    # Base's own Aave V3 GOVERNANCE_GUARDIAN Safe (a different address,
    # chains/base-ecosystem/scorers.py's score_aave_v3_base()) and found to
    # be the EXACT SAME 9 owners at 5-of-9 -- the same CREATE2-redeployed
    # shared-committee pattern this project's own sister research
    # (multisig-overlap) already documented for ether.fi/Curve,
    # now found live in this project's own tracked targets for the first
    # time. Re-checking that live, every run, would mean this Arbitrum-only
    # scorer opening a second (Base) RPC connection -- the same reliability/
    # coupling risk cross_ecosystem_overlap.py's own docstring already
    # explains why it's not wired into any live score_all() path. Compared
    # instead against a DATED snapshot of Base's owner set (re-verify with
    # scripts/check_cross_ecosystem_overlap.py, not on every push).
    #
    # UPDATED 2026-09-19: this note used to say "reaches both chains'
    # emergency-cancel path", stale since the day it was written -- Plasma
    # was added 2026-09-18 with the IDENTICAL 9-signer committee too (see
    # chains/plasma-ecosystem/scorers.py's own
    # _KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17, the same frozenset by a
    # different name), making this a 3-chain shared committee, not 2 --
    # caught by scripts/check_cross_ecosystem_overlap.py's new
    # find_subset_committees() sweep (2026-09-19), not by re-deriving it
    # from scratch here.
    KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17 = frozenset({
        "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
        "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
        "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
        "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
        "0x4C30E33758216aD0d676419c21CB8D014C68099f",
    })
    shares_committee_with_base = bool(guardian_safe) and {w3.to_checksum_address(o) for o in guardian_safe[0]} == {w3.to_checksum_address(o) for o in KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17}
    if shares_committee_with_base:
        notes.append("GOVERNANCE_GUARDIAN Safe owner set is IDENTICAL to Base's AND Plasma's own Aave V3 guardian Safes (dated 2026-09-17/18 snapshots, 3 different addresses, same 9 signers) -- one compromised committee reaches all three chains' emergency-cancel path")

    role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                 "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
    default_admin_role = "0x0000000000000000000000000000000000000000000000000000000000000000"
    acl_has_role = call_raw(w3, acl_manager, role_abi, "hasRole", default_admin_role, executor) if executor else None
    notes.append(f"ACLManager.hasRole(DEFAULT_ADMIN_ROLE, EXECUTOR_LVL_1) = {acl_has_role}")

    notes.append(
        "Open thread, disclosed rather than guessed: the Ethereum-mainnet Aave DAO root "
        "(CROSS_CHAIN_CONTROLLER relay, L1 proposal counts/quorum) was NOT re-verified live "
        "this pass -- this scorer confirms the Arbitrum-side executor/payloads-controller pair "
        "only. See chains/ethereum-l1/scorers.py's score_aave_v3_pool() for the L1 root."
    )
    if not shares_committee_with_base:
        notes.append(_CROSS_EXPOSURE_NOTE)

    delay = settings[1] if settings else None
    chain_closed = bool(payloads_controller) and loop_check == executor and bool(acl_has_role)
    admin_key = 65 if chain_closed else 30
    multisig = 100  # not applicable: PayloadsController/Executor pair is not a Safe (the separate GOVERNANCE_GUARDIAN Safe is a veto path, not the primary authority)
    timelock_score = 50 if delay and delay > 0 else 0  # confirmed real 1-day delay, capped for the unverified L1 root + guardian cancel-path outside the timelock
    # ADDED 2026-09-17: real cross-ecosystem finding, not the usual "100 not
    # applicable" default -- see the dated-snapshot comparison above.
    cross_exposure = 80 if shares_committee_with_base else 100

    return {
        "target": provider,
        "label": "Aave V3 Pool (Arbitrum, PoolAddressesProvider)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ----------------------------------------------------------------------------
# ADDED 2026-09-19 (maintenance run, budget (b)): 4 new Arbitrum One targets.
# Full trace, primary sources, TVL pulls and 2-RPC recoupe in
# chains/arbitrum-ecosystem/data/scored_targets_2026-09-19-maintenance.md.
# ----------------------------------------------------------------------------

_SAFE_GET_OWNERS_ABI = [{"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]


def _cross_exposure_from_snapshots(live_owner_set, snapshots, notes, label):
    """METHODOLOGY.md's cross-ecosystem convention (decided 2026-09-20): a root
    committee identical to a tracked target's committee on ANOTHER ecosystem
    scores a flat 80, however many other ecosystems share it. Applied against
    DATED snapshots of other ecosystems' tracked committees (same "frozen
    snapshot, live-diffed" pattern as the Aave scorer above -- re-verify with
    scripts/check_cross_ecosystem_overlap.py, not on every push, to avoid opening
    a second chain's RPC inside an Arbitrum scorer).

    CORRECTED 2026-09-21: this used to deduct 20 per matching snapshot, so
    Arbitrum's Pendle (the same Safe is tracked on Plasma and on Robinhood Chain)
    read 60 while the same committee read 80 on Plasma and Robinhood Chain. The
    deviation was disclosed in METHODOLOGY.md and is now closed. There is no
    within-Arbitrum overlap for these targets that a min() could preserve."""
    if not live_owner_set:
        notes.append(f"{label}: live owner set unavailable, crossExposureScore not computed (100 = not applicable, not a confirmed clean result)")
        return 100
    shared = [name for name, snap in snapshots.items() if {o.lower() for o in snap} == live_owner_set]
    for name in shared:
        notes.append(f"{label}: live owner set is IDENTICAL to the tracked {name} committee (dated snapshot) -- one compromised committee reaches both")
    return 80 if shared else 100


_COMPOUND_L1_GOVERNANCE_TIMELOCK = "0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"


# ADDED 2026-09-20 (registry coverage pass, real finding): Compound V3's pauseGuardian is the SAME 9-signer
# 5-of-9 committee on Ethereum L1 (Safe 0xbbf3f142...), Arbitrum (0x78E6317D...) and Base (0x3cb4653F...):
# three different Safe addresses, identical owner sets (8 bare EOAs and 1 nested contract), read live on each
# chain's public RPC. One committee can freeze three Comets. Frozen here as a dated snapshot and compared with
# the owners each scorer reads itself, so no scorer calls another chain's RPC.
_KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20 = frozenset({
    "0x2b384212edc04ae8bb41738d05ba20e33277bf33", "0x46b360011a84c5759680852ed90e6db44e18f08c",
    "0x4a3a60ee1007a477edfccb7182ee7f4ef876fa25", "0x55bea483873291eb3ded185c9962676f107cb4d6",
    "0x7e4a8391c728fed9069b2962699ab416628b19fa", "0x9a73d57bb1fb280c5672a13f655675de25f13b70",
    "0xa1bb2061febaf91738f104a19073c84589b92b53", "0xd2a79f263ec55dbc7b724ecc20fc7448d4795a0c",
    "0xfc63ef192e26e428f349057544a8786453c94f84",
})


def score_compound_v3_comet_arbitrum_usdc(w3) -> dict:
    """Compound V3 (Comet, native-USDC market, Arbitrum) -- DefiLlama
    `compound-v3` chainTvls.Arbitrum ~$73.2M across its Arbitrum markets
    (pulled 2026-09-19); this is the USDC market. Source: official
    `compound-finance/comet` repo, `deployments/arbitrum/usdc/roots.json`
    (comet 0x9c4ec768..., bridgeReceiver 0x42480C37...).

    Same authority shape as chains/base-ecosystem/scorers.py's
    score_compound_v3_comet_base_usdc(), re-derived live here, not copied:
    Comet.governor() -> LocalTimelock; EIP-1967 admin slot -> ProxyAdmin
    whose owner() is the SAME LocalTimelock (parameters AND upgrades);
    LocalTimelock.admin() -> ArbitrumBridgeReceiver (matches roots.json);
    receiver.govTimelock() -> Compound's Ethereum-mainnet Governance
    Timelock, receiver.localTimelock() closes back to governor. The local
    1-day delay is the enforced one on Arbitrum; the L1 Timelock's own
    2-day delay was read once on L1 during scouting but is not re-read by
    this Arbitrum-RPC scorer (same boundary as the Base sibling).
    pauseGuardian() (a 5-of-9 Safe) can pause supply/withdraw without the
    timelock -- disclosed, bounded to pausing, not folded into the score
    (same treatment as the Base sibling)."""
    from web3 import Web3

    target = "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf"
    expected_receiver = "0x42480C37B249e33aABaf4c22B20235656bd38068"
    notes = []

    governor = read_address_getter(w3, target, "governor")
    notes.append(f"Comet.governor() = {governor} (expected LocalTimelock)")
    proxy_admin = read_slot_as_address(w3, target, EIP1967_ADMIN_SLOT)
    proxy_admin_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    same_root = bool(governor and proxy_admin_owner) and proxy_admin_owner.lower() == governor.lower()
    notes.append(f"EIP-1967 admin slot -> ProxyAdmin {proxy_admin}, owner() = {proxy_admin_owner} (same LocalTimelock as governor: {same_root})")
    delay = call_raw(w3, governor, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay") if governor else None
    notes.append(f"LocalTimelock.delay() = {delay}s")
    receiver = read_address_getter(w3, governor, "admin") if governor else None
    receiver_ok = bool(receiver) and receiver.lower() == expected_receiver.lower()
    notes.append(f"LocalTimelock.admin() = {receiver} (matches roots.json bridgeReceiver: {receiver_ok})")
    gov_timelock = read_address_getter(w3, receiver, "govTimelock") if receiver else None
    gov_ok = bool(gov_timelock) and gov_timelock.lower() == _COMPOUND_L1_GOVERNANCE_TIMELOCK.lower()
    notes.append(f"ArbitrumBridgeReceiver.govTimelock() = {gov_timelock} (Compound's L1 Governance Timelock: {gov_ok})")
    local_check = read_address_getter(w3, receiver, "localTimelock") if receiver else None
    loop_ok = bool(local_check and governor) and local_check.lower() == governor.lower()
    notes.append(f"ArbitrumBridgeReceiver.localTimelock() = {local_check} (closes back to governor: {loop_ok})")
    pause_guardian = read_address_getter(w3, target, "pauseGuardian")
    pg = safe_owners_and_threshold(w3, pause_guardian) if pause_guardian else None
    notes.append(f"Comet.pauseGuardian() = {pause_guardian} ({f'{pg[1]}-of-{len(pg[0])} Safe' if pg else 'not a Safe this run'}) -- pause-only path outside the timelock")

    chain_closed = same_root and receiver_ok and gov_ok and loop_ok
    admin_key = 75 if chain_closed else 35
    multisig = 100  # not applicable: LocalTimelock/bridge-receiver pair is not a Safe
    if chain_closed and delay and delay > 0:
        # FIXED 2026-09-25: was 65, uncapped, while chains/ethereum-l1/scorers.py's twin Comet
        # scorer already caps this same real delay at 60 for the identical pauseGuardian bypass
        # (a same-shaped Safe, same convention this file itself already applies to Fluid
        # Liquidity's guardian path a few hundred lines below) -- METHODOLOGY.md's own rule
        # ("a confirmed bypass that is bounded... caps the score at 55") was applied on L1 and
        # to Fluid here, but not to this Comet, an inconsistency found and verified 2026-09-25
        # (data/finding_2026-09-25-repo-wide-sweep.md). Same cap as L1, not the stricter 55,
        # since the bypass shape (an identified Safe, instant pause, no fund redirect) is
        # identical to what earned L1's Comet its 60, not a new, harsher case.
        timelock_score = 60 if pg else 65
    else:
        timelock_score = 0

    cross_ecosystem = bool(pg) and {o.lower() for o in pg[0]} == _KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20
    cross_exposure = 80 if cross_ecosystem else 100
    notes.append("Real cross-chain finding, independently re-confirmed 2026-09-20: this pauseGuardian Safe's 9 owners are IDENTICAL, as an exact set, to the pauseGuardian Safes of Compound V3 on Ethereum L1 (0xbbf3f142...) and Base (0x3cb4653F...) at the same 5-of-9 (three different Safe addresses), so one committee can freeze three Comets. Folded into crossExposureScore as a flat 80 (dated snapshot _KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20 compared with the owners read this run, no second-chain RPC)." if cross_ecosystem else _CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "Compound V3 (Comet, USDC market, Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Pendle governance Safe 0x7877AdFa... owner set, live-read 2026-09-19 on
# Plasma (https://rpc.plasma.to, tracked by chains/plasma-ecosystem/scorers.py's
# score_pendle_plasma) AND on Robinhood Chain (https://rpc.mainnet.chain.robinhood.com,
# tracked by scripts/lib/scorers.py's score_pendle_v2) -- same address, same
# 5 owners, same 3-of-5 on both. Frozen here as dated snapshots.
_PENDLE_GOV_OWNERS_2026_09_19 = frozenset({
    "0x231fc5b039d66ba234cb90357082bf16be79b17c", "0x38ab4a7dea2753757f29fe6d10280df2c42abe27",
    "0x7bd456937104ca5efffbd895ccbba52421021c29", "0x9ce6de7ec862e25a515aa0d8ecfbbbb2daa8e0fb",
    "0xf517364727fcc764d58ddf4e53280874a4d0c476",
})
_PENDLE_SNAPSHOTS = {
    "Plasma Pendle (score_pendle_plasma)": _PENDLE_GOV_OWNERS_2026_09_19,
    "Robinhood Chain Pendle V2 (score_pendle_v2)": _PENDLE_GOV_OWNERS_2026_09_19,
}


def score_pendle_v2_arbitrum(w3) -> dict:
    """Pendle V2 (Router + MarketFactoryV6, Arbitrum) -- DefiLlama `pendle-v2`
    chainTvls.Arbitrum ~$147.6M (pulled 2026-09-19). Source: official
    `pendle-finance/pendle-core-v2-public` repo,
    `deployments/42161-core.json` (governance 0x7877AdFa..., router
    0x888888888889..., marketFactoryV6 0x49F2f700..., proxyAdmin 0xA28c08f1...).

    Three paths, all re-derived live, converge on ONE root:
    (1) Router.owner(); (2) MarketFactoryV6's EIP-1967 admin slot ->
    ProxyAdmin.owner(); (3) MarketFactoryV6.owner() = governanceProxy
    (a UUPS PendleGovernanceProxy, Sourcify exact match) on which the same
    Safe holds DEFAULT_ADMIN_ROLE (the deployer's grant was revoked, see the
    data file's RoleGranted/RoleRevoked scan). Root = a 3-of-5 Safe, no
    TimelockController anywhere on these paths. Disclosed, not scored: the
    proxy's GUARDIAN role (pause-only) and its scoped-access mapping
    (`aggregateWithScopedAccess`) are not enumerable by eth_call.
    crossExposure: this exact Safe (same address, same 5 owners, same
    3-of-5) is also the tracked Pendle root on Plasma and Robinhood Chain."""
    from web3 import Web3

    router = "0x888888888889758F76e7103c6CbF23ABbF58F946"
    market_factory_v6 = "0x49F2f7002669E0e4425Fa0203975625Ab4af3143"
    governance_proxy = "0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e"
    notes = []

    router_owner = read_address_getter(w3, router, "owner")
    notes.append(f"Router.owner() = {router_owner}")
    proxy_admin = read_slot_as_address(w3, market_factory_v6, EIP1967_ADMIN_SLOT)
    proxy_admin_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    notes.append(f"MarketFactoryV6 EIP-1967 admin slot -> ProxyAdmin {proxy_admin}, owner() = {proxy_admin_owner}")
    mf_owner = read_address_getter(w3, market_factory_v6, "owner")
    notes.append(f"MarketFactoryV6.owner() = {mf_owner} (expected governanceProxy {governance_proxy})")
    gp_admin = call_raw(w3, governance_proxy, _OZ_HAS_ROLE_ABI, "hasRole", b"\x00" * 32, router_owner) if router_owner else None
    notes.append(f"governanceProxy.hasRole(DEFAULT_ADMIN_ROLE, Router.owner()) = {gp_admin}")

    converge = bool(router_owner and proxy_admin_owner and mf_owner) and \
        router_owner.lower() == proxy_admin_owner.lower() and \
        mf_owner.lower() == governance_proxy.lower() and bool(gp_admin)
    notes.append(f"3 paths converge on one root: {converge}")

    safe = safe_owners_and_threshold(w3, router_owner) if router_owner else None
    cross = 100
    if not (converge and safe):
        notes.append("root not confirmed as a single Safe on all 3 paths this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append(_CROSS_EXPOSURE_NOTE)
    else:
        owners, threshold = safe
        notes.append(f"root is a {threshold}-of-{len(owners)} Safe, no TimelockController on any path")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0
        cross = _cross_exposure_from_snapshots({o.lower() for o in owners}, _PENDLE_SNAPSHOTS, notes, "Pendle governance Safe")

    return {
        "target": router,
        "label": "Pendle V2 Router + MarketFactoryV6 (Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Fluid team Avocado multisig 0x4F6F977a... signer set, live-read 2026-09-19
# on Plasma (https://rpc.plasma.to) -- the same address is the PROPOSER on
# Plasma's tracked Fluid Liquidity timelock (chains/plasma-ecosystem/scorers.py's
# score_fluid_liquidity_plasma, which left this signer set unresolved until it
# read the same set on 2026-09-20) and returns the identical 12 signers / 6 required there.
_FLUID_TEAM_SIGNERS_2026_09_19 = frozenset({
    "0x1d895e5cf6e5288c9a56face942e016696fb0c90", "0x2f1584337426e699f449fe4e582816f610a3249f",
    "0x33581f263ddd51035ab61da3b9fbc9563d5f839a", "0x5612c18e33ff219f29d463d39bb7e68731638fac",
    "0x7284a8451d9a0e7dc62b3a71c0593ea2ec5c5638", "0x88bb9b99084dcf809c4e423b90b2dd402f04c826",
    "0x97399c934d1a8b36ff6bde553bc8ed769ce730bd", "0xa32e5237e32b17e6a374dbc4c062eeeb21d69506",
    "0xa7615cd307f323172331865181dc8b80a2834324", "0xc0c72156c4007b727d1ca4a583d06a2ff9e554f3",
    "0xc7810aa3b0c6a2778eecc114b93d59b2e9da9e05", "0xd33d3fce969f0470c723e45a3e5b34ce2ed78db7",
})


def score_fluid_liquidity_arbitrum(w3) -> dict:
    """Fluid (Instadapp) Liquidity (Arbitrum) -- DefiLlama `fluid-lending`
    chainTvls.Arbitrum ~$146.9M (pulled 2026-09-19). Source: official
    `Instadapp/fluid-contracts-public` repo, `deployments/deployments.md`
    (Liquidity 0x52Aa8994... on arbitrum; Timelock 0x4d6CE4F4... with
    constructor args (86400, [0x4F6F977a...], [0x196Ed45e...], 0x0)).

    Liquidity.getAdmin() == raw EIP-1967 admin slot (upgrade admin AND
    governance, same slot in Fluid's source) -> OpenZeppelin
    TimelockController, getMinDelay() 86400s, self-administered
    (TIMELOCK_ADMIN_ROLE held by itself only). PROPOSER/CANCELLER = the Fluid
    team Avocado multisig (signers()/requiredSigners() read live: 6-of-12);
    EXECUTOR = a 3-of-5 Safe. A full RoleGranted/RoleRevoked scan of the
    timelock (data file) shows exactly these 4 grants, nothing else.
    Resolves on Arbitrum the signer set Plasma's sibling scorer left open at the
    time (Plasma reads the same set since 2026-09-20 and scores the same structure identically).

    Disclosed immediate path outside the delay: Liquidity's auths (4
    Fluid config-handler contracts whose TEAM_MULTISIG() is the same
    Avocado multisig) and its guardian (the same Avocado multisig) can
    adjust bounded config / pause without the timelock -- enumerated from
    LogUpdateAuths/LogUpdateGuardians events in the data file, not by
    this scorer. timelockScore is capped at 55 for that reason."""
    from web3 import Web3

    liquidity = "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"
    expected_proposer = "0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e"
    expected_executor = "0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"
    notes = []

    admin = read_address_getter(w3, liquidity, "getAdmin")
    slot_admin = read_slot_as_address(w3, liquidity, EIP1967_ADMIN_SLOT)
    admin_ok = bool(admin and slot_admin) and admin.lower() == slot_admin.lower()
    notes.append(f"Liquidity.getAdmin() = {admin}, EIP-1967 admin slot = {slot_admin} (identical: {admin_ok})")
    delay = call_raw(w3, admin, _GET_MIN_DELAY_ABI, "getMinDelay") if admin else None
    notes.append(f"TimelockController.getMinDelay() = {delay}s")

    def has(role_name, who):
        return call_raw(w3, admin, _OZ_HAS_ROLE_ABI, "hasRole", Web3.keccak(text=role_name), who) if admin else None

    self_admin = has("TIMELOCK_ADMIN_ROLE", admin) if admin else None
    zero_admin = has("TIMELOCK_ADMIN_ROLE", "0x0000000000000000000000000000000000000000")
    is_prop = has("PROPOSER_ROLE", expected_proposer)
    is_exec = has("EXECUTOR_ROLE", expected_executor)
    notes.append(f"hasRole: TIMELOCK_ADMIN(self)={self_admin}, TIMELOCK_ADMIN(0x0)={zero_admin}, PROPOSER(Avocado {expected_proposer})={is_prop}, EXECUTOR(Safe {expected_executor})={is_exec}")

    req = call_raw(w3, expected_proposer, [{"name": "requiredSigners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}], "requiredSigners")
    signers = call_raw(w3, expected_proposer, [{"name": "signers", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}], "signers")
    notes.append(f"proposer Avocado multisig: requiredSigners() = {req}, signers() count = {len(signers) if signers else 0}")
    exec_safe = safe_owners_and_threshold(w3, expected_executor)
    notes.append(f"executor: {f'{exec_safe[1]}-of-{len(exec_safe[0])} Safe' if exec_safe else 'not resolvable as a Safe this run'}")

    closed = admin_ok and bool(delay and delay > 0) and bool(self_admin) and not zero_admin and bool(is_prop) and bool(is_exec)
    cross = 100
    if not (closed and req and signers and exec_safe):
        notes.append("authority chain not fully confirmed this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append(_CROSS_EXPOSURE_NOTE)
    else:
        prop_k, prop_n = int(req), len(signers)
        exec_k, exec_n = exec_safe[1], len(exec_safe[0])
        admin_key = 65 if min(prop_k, exec_k) >= 3 else (50 if min(prop_k, exec_k) == 2 else 10)
        multisig = min(min(100, k * 15 + max(0, n - k) * 5) for k, n in ((prop_k, prop_n), (exec_k, exec_n)))  # weakest of the two keys sets the ceiling (same convention as scripts/lib/scorers.py)
        timelock_score = 55  # confirmed real 24h delay, self-administered -- capped for the bounded auths/guardian path outside it (see docstring)
        cross = _cross_exposure_from_snapshots({s.lower() for s in signers}, {"Plasma Fluid Liquidity proposer (score_fluid_liquidity_plasma)": _FLUID_TEAM_SIGNERS_2026_09_19}, notes, "Fluid team Avocado multisig")

    return {
        "target": liquidity,
        "label": "Fluid Liquidity (Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_UNISWAP_L1_GOVERNANCE_TIMELOCK = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"
_UNISWAP_SHARED_ROOT_NOTE = (
    "crossExposureScore = 80: the same root authority, Uniswap's Ethereum L1 Governance Timelock "
    "(" + _UNISWAP_L1_GOVERNANCE_TIMELOCK + "), re-confirmed live by this scorer, also controls tracked Uniswap targets on "
    "other ecosystems (Ethereum L1 V3 Factory and V4 PoolManager, Base V3/V2/V4, Robinhood Chain V3/V4/UniswapX/V2, "
    "Monad V4 PoolManager; dated 2026-09-20). It is a token-vote DAO contract, not a signer committee, but it is one "
    "root identity, so the cross-ecosystem fold (a flat 80) applies as for a shared Safe committee (convention of "
    "2026-09-20; the earlier 'DAO/Timelock-rooted targets are not counted' wording is retired)"
)


def score_uniswap_v3_factory_arbitrum(w3) -> dict:
    """Uniswap V3 Factory (Arbitrum One) -- DefiLlama `uniswap-v3`
    chainTvls.Arbitrum ~$144.5M (pulled 2026-09-19). Source: official
    `Uniswap/docs`, `content/protocols/v3/deployments/v3-arbitrum-deployments.mdx`
    (UniswapV3Factory 0x1F98431c...).

    Factory.owner() -> a fee-adapter contract (7,266 bytes, Sourcify
    verified) whose owner() AND feeSetter() are both the Arbitrum L1->L2
    ALIAS of Uniswap's Ethereum-mainnet Governance Timelock -- recomputed
    live with web3_utils.arbitrum_l1_l2_alias(), not trusted from a label.
    An alias has no code and reads like a bare EOA under is_eoa(); the
    2026-09-16 correction (data/correction_2026-09-16-uniswap-bridge-alias.md)
    is why that is NOT scored as one. Like the Base sibling, this scorer
    opens its own Ethereum-mainnet w3 to re-read the L1 Timelock's delay()
    / admin() and the GovernorBravo's quorumVotes() live, and degrades to
    bare-EOA-equivalent scoring if any of it fails (fail-closed, same
    80/100/75 convention as scripts/lib/scorers.py's
    _score_uniswap_bridge_alias_root())."""
    from web3 import Web3

    factory = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    notes = []

    adapter = read_address_getter(w3, factory, "owner")
    notes.append(f"Factory.owner() = {adapter}")
    adapter_owner = read_address_getter(w3, adapter, "owner") if adapter else None
    fee_setter = read_address_getter(w3, adapter, "feeSetter") if adapter else None
    notes.append(f"adapter.owner() = {adapter_owner}, adapter.feeSetter() = {fee_setter}")
    alias = arbitrum_l1_l2_alias(_UNISWAP_L1_GOVERNANCE_TIMELOCK)
    alias_ok = bool(adapter_owner and fee_setter) and adapter_owner.lower() == alias.lower() and fee_setter.lower() == alias.lower()
    notes.append(f"recomputed Arbitrum alias of Uniswap's L1 Governance Timelock ({_UNISWAP_L1_GOVERNANCE_TIMELOCK}) = {alias} -- owner and feeSetter both match: {alias_ok}")

    l1_ok = False
    if alias_ok:
        l1 = get_w3("https://ethereum-rpc.publicnode.com")
        l1_delay = call_raw(l1, _UNISWAP_L1_GOVERNANCE_TIMELOCK, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay")
        l1_admin = call_raw(l1, _UNISWAP_L1_GOVERNANCE_TIMELOCK, [{"name": "admin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "admin")
        quorum = call_raw(l1, l1_admin, [{"name": "quorumVotes", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "quorumVotes") if l1_admin else None
        l1_ok = l1_delay is not None and bool(l1_admin) and quorum is not None
        notes.append(f"re-confirmed live on Ethereum L1 (own w3): Timelock.delay() = {l1_delay}s, .admin() = {l1_admin} (GovernorBravo), quorumVotes() = {quorum} -- complete: {l1_ok}")

    if alias_ok and l1_ok:
        admin_key, multisig, timelock_score = 80, 100, 75
        cross_exposure = 80
        notes.append(_UNISWAP_SHARED_ROOT_NOTE)
    else:
        notes.append("alias or L1 re-confirmation failed this run -- degraded to bare-EOA-equivalent scoring, not kept at the higher score unverified")
        admin_key, multisig, timelock_score = 5, 0, 0
        cross_exposure = 100
        notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": factory,
        "label": "Uniswap V3 Factory (Arbitrum One)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ADDED 2026-09-20 (maintenance run, travailleur2). Tenth target, appended
# AFTER the nine already pushed so trackedTargets() indices 0-8 keep meaning
# what they mean today. Address source: DefiLlama-Adapters
# `registries/gmx.js`, `arbitrum: { vault: '0x489ee077...' }` -- an address
# source this project accepts, not an aggregator's label.
_GMX_V1_VAULT = "0x489ee077994B6658eAfA855C308275EAd8097C4A"
# The GMX V2 timelock that is one of the three ROLE_ADMIN holders of the
# ALREADY-TRACKED GMX V2 RoleStore (index 0). Read live below, not assumed:
# if the tokenManager Safe that can instantly replace THIS timelock's admin
# also holds PROPOSER/EXECUTOR/CANCELLER there, then one committee reaches two
# tracked targets and crossExposureScore is no longer 100.
_GMX_V2_TIMELOCK = "0x2Dd99f39f58445CDDC57AA5E0DB2C367335BBD44"
_BUFFER_ABI = [{"name": "buffer", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
_IS_SWAP_ENABLED_ABI = [{"name": "isSwapEnabled", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]}]
_IS_LEVERAGE_ENABLED_ABI = [{"name": "isLeverageEnabled", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]}]


def score_gmx_v1_vault(w3) -> dict:
    """GMX V1 Vault (Arbitrum One), the original perp/GLP vault. Still holds
    real collateral (WBTC/WETH/USDC/LINK/UNI whitelisted, non-zero balances on
    2026-09-20) even though `isSwapEnabled()` and `isLeverageEnabled()` are
    both false -- V1 is wound down for new trading, not emptied, which is why
    its authority still matters and why it is scored rather than skipped.

    Authority chain, each hop read live on two independent Arbitrum One RPCs:
        Vault.gov()             -> GMX's bespoke Timelock 0x718507c3...
        Timelock.buffer()       -> 86400s (24h) on the signalled actions
        Timelock.admin()        -> Safe 1.4.1, 4-of-6
        Timelock.tokenManager() -> Safe 1.4.1, 5-of-8

    The finding that moves the score is the second Safe. In GMX's own
    `contracts/peripherals/Timelock.sol` (gmx-io/gmx-contracts),
    `setAdmin(address)` is `onlyTokenManager` and writes `admin` with NO
    signal and NO buffer. That is not taken from the source alone: the
    deployed bytecode carries the `setAdmin(address)` selector, and an
    `eth_call` (no transaction) of `setAdmin` succeeds from the tokenManager
    Safe and reverts "forbidden" both from the timelock's own admin Safe and
    from a random address. So the 24h delay protects the
    gov/withdraw/mint/approve actions but not the identity of the party
    allowed to queue them.

    Checked for and ruled out, rather than assumed: `requestGov(address[])`
    is an instant gov-handover path, but it is `onlyGovRequester`, the
    registry is only writable through the delayed `setGovRequester`, and the
    chain has never emitted a single `SignalSetGovRequester` event -- no
    requester was ever registered, so that path is dormant. `SignalSetGov`
    has never been emitted either: the delayed gov-change path has never been
    used.
    """
    from web3 import Web3

    target = _GMX_V1_VAULT
    notes = []

    gov = read_address_getter(w3, target, "gov")
    notes.append(f"Vault.gov() = {gov} (expected GMX Timelock)")

    swap_on = call_raw(w3, target, _IS_SWAP_ENABLED_ABI, "isSwapEnabled")
    lev_on = call_raw(w3, target, _IS_LEVERAGE_ENABLED_ABI, "isLeverageEnabled")
    notes.append(
        f"Vault.isSwapEnabled() = {swap_on}, Vault.isLeverageEnabled() = {lev_on} -- attenuating context, disclosed: "
        "V1 is wound down for new trading. It is NOT empty (whitelisted WBTC/WETH/USDC/LINK/UNI balances all non-zero "
        "on 2026-09-20), so the authority over it is still live authority over real collateral."
    )

    if not gov:
        notes.append("Vault.gov() unreadable this run -- unresolved authority, conservative score, nothing assumed")
        notes.append(_CROSS_EXPOSURE_NOTE)
        return _gmx_v1_result(20, 0, 0, 100, notes)

    buffer_s = call_raw(w3, gov, _BUFFER_ABI, "buffer")
    admin = read_address_getter(w3, gov, "admin")
    token_manager = read_address_getter(w3, gov, "tokenManager")
    notes.append(f"Timelock.buffer() = {buffer_s}s, Timelock.admin() = {admin}, Timelock.tokenManager() = {token_manager}")

    admin_safe = safe_owners_and_threshold(w3, admin) if admin else None
    tm_safe = safe_owners_and_threshold(w3, token_manager) if token_manager else None
    if not admin_safe:
        notes.append(f"{admin}: NOT resolvable as a Gnosis Safe this run -- unresolved root, conservative score")
        notes.append(_CROSS_EXPOSURE_NOTE)
        return _gmx_v1_result(20, 0, 0, 100, notes)

    admin_owners, admin_threshold = admin_safe
    notes.append(f"Timelock.admin() is a real Gnosis Safe: {admin_threshold}-of-{len(admin_owners)}")
    multisig = min(100, admin_threshold * 15 + max(0, len(admin_owners) - admin_threshold) * 5)

    # The instant admin-replacement path. A distinct, resolvable tokenManager
    # multisig IS the bypass; if tokenManager is the admin itself, or is not a
    # multisig, there is no second committee and nothing to subtract.
    instant_admin_swap = bool(
        tm_safe and token_manager and admin and token_manager.lower() != admin.lower()
    )
    if tm_safe:
        tm_owners, tm_threshold = tm_safe
        notes.append(f"Timelock.tokenManager() is a real Gnosis Safe: {tm_threshold}-of-{len(tm_owners)}")
        tm_multisig = min(100, tm_threshold * 15 + max(0, len(tm_owners) - tm_threshold) * 5)
        shared = sorted({o.lower() for o in admin_owners} & {o.lower() for o in tm_owners})
        notes.append(
            f"signers shared between the 2 Safes: {len(shared)} of {len(admin_owners)} / {len(tm_owners)} ({shared})"
        )
        if instant_admin_swap:
            # Compromising EITHER committee is enough, so the multisig
            # dimension is the weaker of the two, not the admin Safe alone.
            multisig = min(multisig, tm_multisig)
            notes.append(
                "Timelock.setAdmin(address) is onlyTokenManager in GMX's own Timelock.sol and writes admin with no "
                "signal and no buffer: the tokenManager Safe can replace the timelock admin instantly. Confirmed by "
                "eth_call (no transaction): setAdmin succeeds from the tokenManager Safe and reverts 'forbidden' from "
                "the admin Safe and from a random address. multisigScore therefore takes the WEAKER of the two Safes."
            )
    else:
        notes.append(f"Timelock.tokenManager() = {token_manager}: not resolvable as a Safe this run -- no instant-swap path scored")

    if not buffer_s:
        timelock_score = 0
        notes.append("no readable buffer on the timelock -- timelockScore 0, a delay is not assumed")
    else:
        # A real delay on the signalled (gov / withdrawToken / mint / approve)
        # actions. Capped below the 60-75 "bypass checked and ruled out" band
        # because a bypass was checked for and FOUND, not ruled out.
        timelock_score = 60 if buffer_s >= 86400 else 30
        if instant_admin_swap:
            timelock_score -= 15
        notes.append(
            f"timelockScore {timelock_score}: the {buffer_s}s buffer really does gate signalSetGov / withdrawToken / "
            "mint / approve, but a second committee can swap the admin with no delay, so this is not the "
            "'bypass ruled out' case the 60-75 band is for (METHODOLOGY.md, timelockScore)."
        )

    admin_key = 55 if instant_admin_swap else 65
    notes.append(
        f"adminKeyScore {admin_key}: Safe root reached through a real delay"
        + (", minus the instantly-replaceable admin" if instant_admin_swap else ", no instant-swap path found")
    )

    # crossExposure, computed live here rather than from a dated snapshot.
    cross = 100
    if token_manager:
        roles = {
            r: call_raw(w3, _GMX_V2_TIMELOCK, _OZ_HAS_ROLE_ABI, "hasRole", Web3.keccak(text=r), token_manager)
            for r in ("PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE")
        }
        notes.append(
            f"tokenManager Safe roles on the GMX V2 timelock {_GMX_V2_TIMELOCK} "
            f"(a ROLE_ADMIN of the tracked index-0 RoleStore): {roles}"
        )
        if any(v is True for v in roles.values()):
            cross = 80
            notes.append(
                "crossExposureScore = 80: the same Safe that can instantly replace THIS target's timelock admin also "
                "holds proposer/executor/canceller rights on the GMX V2 timelock that is a ROLE_ADMIN of the tracked "
                "GMX V2 RoleStore (index 0). One committee, two tracked targets -- 100 - 20 * 1 shared group."
            )
        else:
            notes.append("crossExposureScore = 100: no role held by the tokenManager Safe on the GMX V2 timelock this run")
    else:
        notes.append(_CROSS_EXPOSURE_NOTE)

    notes.append(
        "Checked and ruled out live: requestGov(address[]) is an instant gov-handover but is onlyGovRequester, and "
        "the timelock has emitted zero SignalSetGovRequester events since deployment, so no requester was ever "
        "registered. Zero SignalSetGov events either -- the delayed gov-change path has never been exercised."
    )
    return _gmx_v1_result(admin_key, multisig, timelock_score, cross, notes)


def _gmx_v1_result(admin_key, multisig, timelock_score, cross, notes):
    return {
        "target": _GMX_V1_VAULT,
        "label": "GMX V1 Vault (Arbitrum One)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# --------------------------------------------------------------------- ADDED 2026-09-25
# 3 targets closed out by an independent verification pass that fixed open gaps this
# file's own prior notes had left explicitly unscored (Dolomite's enumeration gap,
# USD AI's untraced _bridgeAdapter, Gains Network's un-added 4th timelock holder).
# See chains/arbitrum-ecosystem/data/scored_targets_2026-09-20-maintenance-gmx-v1.md
# (Dolomite, Gains Network) and data/scored_targets_2026-09-19-maintenance.md (USD AI)
# for the prior state each of these closes.
_DOLOMITE_MARGIN = "0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072"
_SECONDS_TIME_LOCKED_ABI = [{"name": "secondsTimeLocked", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]


def score_dolomite_margin_arbitrum(w3) -> dict:
    """Dolomite Margin (Arbitrum) -- the live, active pool: 77 markets, DefiLlama
    `dolomite` (`api.llama.fi/protocol/dolomite`) chainTvls.Arbitrum ~$25.94M
    supplied / ~$11.49M borrowed (pulled 2026-09-25). Address source:
    DefiLlama-Adapters `projects/dolomite/index.js`.

    CLOSES a gap this ecosystem's own 2026-09-20 scouting note left open
    (`data/scored_targets_2026-09-20-maintenance-gmx-v1.md`, "Scouted, traced,
    NOT scored"): the enumeration of `DEFAULT_ADMIN_ROLE` holders on the owner
    contract rested on a single RPC's `eth_getLogs`, so it wasn't scored. That
    holder is now independently confirmed: `DolomiteMargin.owner()` =
    `0xC2B66E24...` (Sourcify exact match, "DolomiteOwnerV2", AccessControl-based),
    whose `DEFAULT_ADMIN_ROLE` is held by exactly one address, a Gnosis Safe
    1.4.1, **2-of-3** (`0xa75c21C5...`). This is NOT the older `DelayedMultiSig`
    `0xE412991F...` (1-day delay) that governs Dolomite's separate, near-empty
    legacy pool `0x6a769862...` (6 markets, zero balances) -- a different, dead
    pool this scorer does not read.

    `owner()` itself answers `secondsTimeLocked()` = **300** (5 minutes): a
    real, confirmed delay on the owner's own queued-execution path, but far
    short of this project's 24h floor for full timelockScore credit (the same
    `>= 86400` threshold `score_gmx_v1_vault`'s buffer check uses) -- scored
    accordingly, not assumed protective just because a delay exists
    (METHODOLOGY.md: "scored on the gap, not the presence of a timelock
    somewhere")."""
    target = _DOLOMITE_MARGIN
    notes = []

    owner = read_address_getter(w3, target, "owner")
    notes.append(f"DolomiteMargin.owner() = {owner} (expected DolomiteOwnerV2 0xC2B66E247daE5Ee749Ae1d827190115F3653dE06)")

    seconds_locked = call_raw(w3, owner, _SECONDS_TIME_LOCKED_ABI, "secondsTimeLocked") if owner else None
    notes.append(f"owner().secondsTimeLocked() = {seconds_locked}s")

    from web3 import Web3

    admin_role_holder = Web3.to_checksum_address("0xa75c21C5BE284122a87A37a76cc6C4DD3E55a1D4")
    has_admin_role = call_raw(w3, owner, _OZ_HAS_ROLE_ABI, "hasRole", b"\x00" * 32, admin_role_holder) if owner else None
    notes.append(f"owner().hasRole(DEFAULT_ADMIN_ROLE, {admin_role_holder}) = {has_admin_role}")

    safe = safe_owners_and_threshold(w3, admin_role_holder) if has_admin_role else None
    if not (owner and has_admin_role and safe):
        notes.append("DEFAULT_ADMIN_ROLE holder not confirmed as a Gnosis Safe this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"DEFAULT_ADMIN_ROLE holder is a real Gnosis Safe: {threshold}-of-{len(owners)}")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 60 if (seconds_locked and seconds_locked >= 86400) else (30 if seconds_locked else 0)
        notes.append(
            f"timelockScore {timelock_score}: {seconds_locked}s is a real, confirmed delay on the owner's own "
            "queued-execution path, but far below the 24h floor this project credits with the full 60-75 band "
            "(same threshold score_gmx_v1_vault's buffer check uses) -- a 5-minute window gives no one a real "
            "chance to react."
        )

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "Dolomite Margin (Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_USDAI_BRIDGE_ADAPTER = "0xffA10065Ce1d1C42FABc46e06B84Ed8FfEb4baE5"
_USDAI_UPGRADE_TIMELOCK = "0x0EEA1EE08611FF4A4E83bFE3916712751995639B"  # 48h -- upgrade-only, does not cover mint/burn


def score_usdai_bridge_adapter_arbitrum(w3) -> dict:
    """USD AI (`usd-ai`) mint/burn authority, Arbitrum -- DefiLlama
    `api.llama.fi/protocol/usdai` chainTvls.Arbitrum ~$208.3M supplied /
    ~$401.5M borrowed (pulled 2026-09-25; corrects this ecosystem's own
    2026-09-19 "considered, not added" note, which read ~$307.2M --
    `data/scored_targets_2026-09-19-maintenance.md`).

    CLOSES the exact gap that note left open: "mint()/burn() are gated by an
    immutable `_bridgeAdapter` that has no public getter, and its own
    authority was not traced ... left out rather than scored with a gap in
    its core path." That adapter is `0xffA10065...` (Sourcify exact match, a
    LayerZero V2 `OAdapter`, plain `Ownable`), owned by a **3-of-3** Gnosis
    Safe (`0x5F0BC72F...`, owners `0xe982B3f6...`/`0x986868C9...`/
    `0xD1AFfE27...`), which ALSO holds `DEFAULT_ADMIN_ROLE` on the USDai token
    itself (blacklist/pause) -- disclosed context from the same verification
    pass, not re-checked live here (no full token address confirmed this
    pass; the adapter's own `owner()` chain is what this scorer reads and
    scores). The only delay this project has ever documented for USD AI, a
    48h `TimelockController` (`0x0EEA1EE0...`), gates the EIP-1967 proxy
    UPGRADE path only -- it does not sit in front of the adapter, so it does
    not cover mint/burn, the action that actually matters here.

    Live note (2026-09-25): `owner()` resolves to exactly the Safe above, but
    this project's own module-authority gate (`scripts/lib/safe_modules.py`,
    added 2026-09-21) currently finds one unanalyzed module on it
    (`0x02878D80...`) and treats the whole Safe as UNRESOLVED authority until
    that module is analyzed -- so this scorer reads a conservative (20, 0, 0)
    live today, not the 65/45/0 the Safe's raw 3-of-3 owners/threshold alone
    would suggest. That is this shared gate doing exactly what it is for
    (METHODOLOGY.md), not a bug in this scorer; analyzing that module lifts
    it automatically."""
    target = _USDAI_BRIDGE_ADAPTER
    notes = []

    owner = read_address_getter(w3, target, "owner")
    notes.append(f"_bridgeAdapter.owner() = {owner} (expected the mint/burn Safe 0x5F0BC72Fb5952b2F3f2E11404398Ed507B25841F)")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}, no TimelockController in front of mint/burn")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0
        notes.append(
            "timelockScore 0: the only documented delay on USD AI, a 48h TimelockController "
            f"({_USDAI_UPGRADE_TIMELOCK}), gates the proxy upgrade path only -- it is not in front of this "
            "adapter, so it does not cover mint()/burn(), the action that actually matters here"
        )

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "USD AI mint/burn authority (LayerZero OAdapter, Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_GAINS_DIAMOND = "0xFF162c694eAA571f685030649814282eA457f169"
_GAINS_GOV_EMERGENCY_TIMELOCK = "0x893FCf48D56CE2e92AFB4a085941135243D5E75a"
_GAINS_SAFE_4_OF_7 = "0xc07EEd650aB255190CA9766162CfB47cFDf72f3a"
_GAINS_SAFE_2_OF_4 = "0xe8997C502fCD0729B462FCA19A50cF0DAEA0cAB5"
_GAINS_EOA_PROPOSER = "0x80fd0accC8Da81b0852d2Dca17b5DDab68f22253"


def score_gains_network_diamond_arbitrum(w3) -> dict:
    """Gains Network gTrade Diamond (Arbitrum) -- DefiLlama
    `api.llama.fi/protocol/gains-network` chainTvls.Arbitrum ~$11.74M +
    ~$1.63M staking (pulled 2026-09-25). This ecosystem's own 2026-09-20
    scouting note found a 14-day-delay controller behind the Diamond's
    upgrade path and left it "for a next run rather than scored from one hop"
    (`data/scored_targets_2026-09-20-maintenance-gmx-v1.md`).

    CLOSES that gap, and corrects what a shallower read would have scored:
    the Diamond's upgrade surface is gated by TWO other OpenZeppelin
    `TimelockController`s (a 14-day one for a full `diamondCut()` via
    ProxyAdmin, and a 3-day `GOV_TIMELOCK`), but a THIRD, previously-missed
    one is the real weakest link: `GOV_EMERGENCY_TIMELOCK` `0x893FCf48...`,
    `getMinDelay()` = **36,000s (10 hours)**. Its `PROPOSER_ROLE` and
    `CANCELLER_ROLE` are held by THREE parties: a 4-of-7 Safe
    (`0xc07EEd65...`), a 2-of-4 Safe (`0xe8997C50...`) AND a bare EOA
    (`0x80Fd0ACc...`, `eth_getCode` = `0x`). `EXECUTOR_ROLE` is held by the
    two Safes only, not the EOA. The shortest real path to a full
    `diamondCut()` is therefore: the bare EOA alone schedules, 10 hours pass,
    the weaker 2-of-4 Safe executes -- shorter AND weaker than either the
    3-day or the 14-day path, so THIS is what drives the score
    (METHODOLOGY.md: "scored on the gap, not the presence of a timelock
    somewhere"), not the 3d/14d delays a shallower read would cite.

    Aggravating context, disclosed but not scored (it does not itself skip
    the 10h delay on an already-scheduled call): the 4-of-7 Safe additionally
    holds `TIMELOCK_ADMIN_ROLE` on all THREE timelocks (14d/3d/10h) and can
    reassign who may propose or execute on any of them at will."""
    from web3 import Web3

    target = _GAINS_DIAMOND
    timelock = _GAINS_GOV_EMERGENCY_TIMELOCK
    notes = []

    delay = call_raw(w3, timelock, _GET_MIN_DELAY_ABI, "getMinDelay")
    notes.append(f"GOV_EMERGENCY_TIMELOCK {timelock}.getMinDelay() = {delay}s (expected 36000, 10h)")

    # Defensively re-checksummed here, same as score_gmx_v2_rolestore's members() -- a hardcoded
    # address passed as a *call argument* (not a contract address) must match EIP-55 exactly or
    # eth_abi's encoder raises InvalidAddress, unlike the contract address itself which web3.py
    # normalizes on its own.
    candidates = [Web3.to_checksum_address(a) for a in (_GAINS_SAFE_4_OF_7, _GAINS_SAFE_2_OF_4, _GAINS_EOA_PROPOSER)]
    proposer_role = Web3.keccak(text="PROPOSER_ROLE")
    executor_role = Web3.keccak(text="EXECUTOR_ROLE")

    proposer_flags = {a: call_raw(w3, timelock, _OZ_HAS_ROLE_ABI, "hasRole", proposer_role, a) for a in candidates}
    executor_flags = {a: call_raw(w3, timelock, _OZ_HAS_ROLE_ABI, "hasRole", executor_role, a) for a in candidates}
    notes.append(f"PROPOSER_ROLE holders: {proposer_flags}")
    notes.append(f"EXECUTOR_ROLE holders: {executor_flags}")
    notes.append(f"the bare EOA also holds EXECUTOR_ROLE (a single-key finish, not just a single-key start): {executor_flags.get(_GAINS_EOA_PROPOSER) is True}")

    initiators = []
    for a in candidates:
        if proposer_flags.get(a) is not True:
            continue
        s = safe_owners_and_threshold(w3, a)
        if s:
            initiators.append((s[1], len(s[0]), a, "Safe"))
        elif is_eoa(w3, a):
            initiators.append((1, 1, a, "bare EOA"))
        else:
            initiators.append((0, 0, a, "unresolved contract"))
    notes.append(
        "PROPOSER initiators (can schedule(), then anyone with EXECUTOR_ROLE can execute after the delay): "
        + ", ".join(f"{a} = {kind} {k}-of-{n}" for k, n, a, kind in initiators)
    )
    weakest = _weakest_key(initiators)

    if not (delay and delay > 0 and weakest):
        notes.append("authority path unresolved this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        k, n, weakest_addr, kind = weakest
        notes.append(f"weakest PROPOSER initiator by (k, -n): {weakest_addr} ({kind}, {k}-of-{n})")
        if kind == "bare EOA":
            admin_key, multisig = 10, 0
        elif kind == "unresolved contract":
            admin_key, multisig = 20, 0
        else:
            admin_key = 65 if k >= 3 else (50 if k == 2 else 10)
            multisig = min(100, k * 15 + max(0, n - k) * 5)

        timelock_score = 0
        notes.append(
            f"timelockScore 0: {delay}s (10h) is a real, confirmed delay, but it gates a path a bare EOA can enter "
            "alone with no committee check, and no INDEPENDENT party can veto it (CANCELLER_ROLE is held by that "
            "same EOA plus the same two Safes that can also execute -- not a separate check). 10h is also under "
            "this project's 24h floor for any non-zero timelockScore credit even in the best case (the same "
            "threshold score_gmx_v1_vault's buffer check uses). This is the real weakest path to a full "
            "diamondCut(), not the 3-day GOV_TIMELOCK or the 14-day ProxyAdmin upgrade path a shallower read "
            "would score against."
        )

    notes.append(
        f"aggravating, disclosed not scored: the 4-of-7 Safe ({_GAINS_SAFE_4_OF_7}) additionally holds "
        "TIMELOCK_ADMIN_ROLE on all three of Gains Network's timelocks (14d/3d/10h) and can reassign who may "
        "propose or execute on any of them at will -- it does not itself skip the 10h delay on an "
        "already-scheduled call, so it is not folded into timelockScore, but the 10h path above is not even "
        "the floor of what this Safe alone could reconfigure."
    )
    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": target,
        "label": "Gains Network gTrade Diamond (Arbitrum)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


SIMPLE_SCORERS = [
    score_gmx_v2_rolestore,
    score_camelot_ammv3_factory,
    score_radiant_lendingpool,
    score_arbitrum_security_council_safe,
    score_aave_v3_pool_arbitrum,
    # ADDED 2026-09-19 (maintenance run): appended AFTER the 5 already-pushed
    # targets so trackedTargets() indices 0-4 on the testnet oracle keep
    # meaning the same thing.
    score_compound_v3_comet_arbitrum_usdc,
    score_pendle_v2_arbitrum,
    score_fluid_liquidity_arbitrum,
    score_uniswap_v3_factory_arbitrum,
    # ADDED 2026-09-20 (maintenance run): appended AFTER the 9 already-pushed
    # targets so trackedTargets() indices 0-8 keep meaning the same thing.
    score_gmx_v1_vault,
    # ADDED 2026-09-25 (independent verification pass, 3 targets): appended
    # AFTER the 10 already-pushed targets so trackedTargets() indices 0-9
    # keep meaning the same thing.
    score_dolomite_margin_arbitrum,
    score_usdai_bridge_adapter_arbitrum,
    score_gains_network_diamond_arbitrum,
]


def score_all(w3) -> list:
    # FIXED 2026-09-17 (closed a bug hunt finding): this was a bare list
    # comprehension with no per-target failure isolation, unlike
    # chains/ethereum-l1/scorers.py and scripts/lib/scorers.py, which both
    # already use safe_score() for exactly this reason -- a single target's
    # transient RPC failure (is_eoa() in particular has no retry/guard of
    # its own) used to crash the whole 5-target batch instead of just
    # skipping the flaky one.
    results = []
    for scorer in SIMPLE_SCORERS:
        results.extend(safe_score(scorer.__name__, scorer, w3))
    return results
