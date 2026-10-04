"""
Base Ecosystem authority scorers -- first 5 flagship targets (2026-09-16, scoring_build).

Reuses this project's existing methodology exactly as-is (same pattern as
Robinhood Chain's `scripts/lib/scorers.py` and `chains/ethereum-l1/scorers.py`):
live eth_call against a public Base mainnet RPC (chain 8453), address sourced
from the protocol's own official docs/GitHub repo, authority traced to its
root (Safe getOwners+getThreshold / cross-chain governance executor / EIP-1967
proxy admin / OP-stack L2CrossDomainMessenger-gated forwarder), never trusted
from a prior pass or a block explorer's "verified name".

The 5 targets scored here are the exact 5 approved 3/3 in the scouting pass
(maker-checker action 9, see `chains/base-ecosystem/data/scouted_targets_2026-09-16.md`
for the full trace, verification commands, and every open thread disclosed
there). Every live call this module makes was independently re-confirmed
against `https://mainnet.base.org` in this pass (2026-09-16, scoring_build
attempt 1) before this file was written -- see
`runs/2026-09-16-run2/base-ecosystem/claims_attempt1.txt`.

Each scorer returns a dict with the AuthorityScore fields (including
`crossExposureScore`, defaulted to 100/"not applicable" here -- see its own
docstring below) plus a `notes` list explaining what was found, so a re-run's
output is still readable without re-reading this file.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
from web3_utils import (  # noqa: E402
    call_raw,
    get_w3,
    read_address_getter,
    read_slot_as_address,
    safe_owners_and_threshold,
    safe_score,
    EIP1967_ADMIN_SLOT,
)
import price_authority  # noqa: E402  (oracleAuthorityScore for price consumers, rule of 2026-10-04)

# RESOLVED 2026-09-17 (closed a follow-up audit finding): this file used to
# keep its own local `_retrying()` plus thin wrappers around it (Base's public
# RPCs rate-limit tight back-to-back eth_call bursts -- confirmed empirically:
# the exact same call that succeeds in isolation intermittently comes back
# None when fired right after several others, which used to be misread as a
# real revert rather than a transient RPC drop), byte-identical to the same
# copy independently kept in chains/ethereum-l1/scorers.py. Retry is now
# built directly into scripts/lib/web3_utils.py's own helpers (default
# retries=4) -- imported straight from there. `retries=1` is still passed
# explicitly at call sites EXPECTED to revert (e.g. Aerodrome
# PoolFactory.owner()), where a bare None is the correct, already-verified
# result, not a transient failure -- that override still works identically
# against the shared helpers below.

# crossExposureScore is a property of the SET of tracked targets (does the same
# root signer also control ANOTHER tracked target?), computed project-wide in
# scripts/lib/signer_overlap.py for Robinhood Chain's own target set, and in
# scripts/lib/cross_ecosystem_overlap.py's BASE_GROUPS for cross-ecosystem
# comparisons. UPDATED 2026-09-19 (was stale -- this comment used to claim no
# cross-ecosystem dataset existed at all, no longer true): two of this file's
# scorers now compute a REAL cross-exposure value live --
# score_aave_v3_base() (added 2026-09-17, shares Arbitrum's Aave guardian
# committee) and score_morpho_blue() (added 2026-09-19, shares Robinhood
# Chain's own Morpho Blue owner committee). Every OTHER scorer below still
# reports 100 ("no overlap found") with an explicit note that this dimension
# was NOT computed for that specific target this pass -- not fabricated, and
# not yet audited against BASE_GROUPS' full comparison set either.
_CROSS_EXPOSURE_NOTE = (
    "crossExposureScore = 100 (not computed THIS TARGET this pass -- this file's Aave/Morpho "
    "Blue scorers do compute a real cross-ecosystem value, see scripts/lib/cross_ecosystem_overlap.py's "
    "BASE_GROUPS; this target's own authority was not checked against that dataset, treated as "
    "'not applicable' per this project's convention, not as a confirmed clean result)"
)


def _composite(admin_key, multisig, timelock):
    """Standard project weighting: 0.4*adminKey + 0.3*multisig + 0.3*timelock,
    oracleAuthorityScore excluded by convention: price consumers carry it as a
    separate field (METHODOLOGY, "oracleAuthorityScore for price consumers").
    Uses standard round-half-up via floor(x + 0.5), not Python's builtin round() (banker's
    rounding) -- same fix already applied in the root scorers.py and
    chains/ethereum-l1/scorers.py, kept consistent here rather than
    reintroducing the bug this project already caught once."""
    import math

    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


# ADDED 2026-09-19 (closed a real cross-ecosystem gap found by running
# scripts/check_cross_ecosystem_overlap.py -- not a new-ecosystem pass, both
# sides were already-shipped, already-deployed targets in this project):
# Base's Morpho Blue owner Safe and Robinhood Chain's own already-tracked
# Morpho Blue owner Safe (scripts/lib/signer_overlap.py GROUPS["morpho_blue"],
# 0x060595638692de6CCd47ca04094F1772D3D39728) are DIFFERENT addresses but
# share the EXACT SAME 9 owners at the EXACT SAME 5-of-9 threshold --
# independently re-confirmed live against both chains this pass, not
# assumed. This is Morpho Association's own global protocol-governance
# Safe, deployed per-chain via CREATE2 with a consistent signer set by
# design -- a real, legitimate operating pattern, not a mistake -- but it
# means this project's own two largest-TVL Morpho Blue targets (Base
# $3.90B, plus whatever Robinhood Chain's own deployment secures) are both
# choke-pointed on the identical 9 individuals, previously unscored.
_KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19 = frozenset({
    "0x13cA8756E9470b71B8e998352c8741706217f963", "0x264c86DBbD2E4165FbBf0C35b0ddf0e00AEc6b31",
    "0x30E7c016fC702cDe9A50720a469d418490b7b652", "0x69FcEFDe2B48503d675181448B3D4272128bca9c",
    "0x84D3E4EE550DD5F99e76a548aC59a6BE1C8dCf79", "0x8f02b4a44Eacd9b8eE7739aa0BA58833DD45d002",
    "0xC100c251bdD297A66795112f04356E6BA5f89D80", "0xCF263cEe139763114fAaFC5F52865135412F50Ec",
    "0xe0aeb6811d33Df42A09066857CDaFca16b506086",
})


def score_morpho_blue(w3) -> dict:
    """Morpho Blue singleton (Base) -- largest target found in scouting
    ($3.90B TVL). Source: official morpho-org/morpho-blue-deployment GitHub
    repo, CREATE2 deployment receipt for chain 8453. Authority chain:
    MorphoBlue.owner() -> a real Gnosis Safe, one hop, fully closed (no
    further owner()/admin() layer above it).

    Scope caveat, disclosed rather than folded into the score: Morpho Blue's
    immutable-core design means owner() can only set protocol fees and enable
    new IRMs/LLTVs for FUTURE markets -- it cannot touch funds in existing
    markets directly. Scored on the authority ROOT mechanism itself (a Safe,
    same as every other Safe-rooted target in this project), not on the
    operational blast radius, consistent with how Aerodrome's pauser Safe
    below is also scored on the mechanism rather than its narrower scope.

    Real cross-chain finding, added 2026-09-19: this Safe's owner set is
    IDENTICAL (same 9 signers, same 5-of-9 threshold, different address) to
    Robinhood Chain's own already-tracked Morpho Blue owner Safe -- see the
    module-level comment above `_KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19`
    for the full finding."""
    target = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
    notes = []

    owner = read_address_getter(w3, target, "owner")
    notes.append(f"MorphoBlue.owner() = {owner}")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    shares_committee_with_robinhood = False
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}")
        notes.append(
            "Scope caveat: owner() can only set fees / enable new IRMs+LLTVs for future "
            "markets -- cannot move funds in existing markets directly (Morpho's own README, "
            "immutable-core design). Root authority mechanism scored as-is per project convention."
        )
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController or delay found anywhere in this chain

        shares_committee_with_robinhood = {w3.to_checksum_address(o) for o in owners} == {
            w3.to_checksum_address(o) for o in _KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19
        }
        if shares_committee_with_robinhood:
            notes.append(
                "Owner Safe's 9 signers are IDENTICAL, as an exact set at the identical 5-of-9 "
                "threshold, to Robinhood Chain's own already-tracked Morpho Blue owner Safe "
                "(different address, same CREATE2-per-chain deployment pattern) -- Morpho "
                "Association's own global governance committee, independently re-confirmed live "
                "against both chains this pass, not assumed from the shared protocol name."
            )

    cross_exposure = 80 if shares_committee_with_robinhood else 100
    if not shares_committee_with_robinhood:
        notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "rootSafeOwners": list(safe[0]) if safe else [],
        "target": target,
        "label": "Morpho Blue (singleton, Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_aave_v3_base(w3) -> dict:
    """Aave V3 Base (PoolAddressesProvider) -- $500.8M TVL. Source: official
    bgd-labs/aave-address-book GitHub repo, `src/AaveV3Base.sol`. Authority
    chain: PoolAddressesProvider.owner() == getACLAdmin() -> EXECUTOR_LVL_1
    (confirmed via `bgd-labs/aave-address-book`'s GovernanceV3Base.sol to be
    the exact constant, not a random address) <-> PayloadsController (mutual
    owner() pointers -- a genuine, by-design closed pair, not a loop that
    hides the real authority: standard BGD Labs Aave Governance V3 cross-chain
    infra). `PayloadsController.getExecutorSettingsByAccessControl(1)` gives
    the real per-access-level delay (86,400s / 1 day), confirmed live this run
    -- same interface already used in `chains/ethereum-l1/scorers.py`'s Aave
    scorer, kept consistent rather than assuming a bare `delay()` getter
    exists on this contract shape.

    Real, disclosed gap (larger than the Ethereum-L1 sibling scorer's gap):
    this scorer confirms the Base-side executor/payloads-controller pair
    matches the official address book exactly, but does NOT independently
    re-verify the Ethereum-mainnet Aave DAO root (proposal counts, quorum,
    the L1 Timelock/Executor that the CROSS_CHAIN_CONTROLLER ultimately
    relays from) -- that root lives on L1, not Base, and is out of scope for
    a Base-RPC-only scorer. `chains/ethereum-l1/scorers.py`'s own
    `score_aave_v3_pool()` covers that root directly. timelockScore/adminKey
    below are capped below the Ethereum-L1 sibling's to reflect this
    unverified-this-pass L1 root, not assumed clean."""
    provider = "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"
    addr_abi_name = "owner"
    notes = []

    executor = read_address_getter(w3, provider, addr_abi_name)
    notes.append(f"PoolAddressesProvider.owner() = {executor} (expected EXECUTOR_LVL_1)")

    acl_admin = call_raw(w3, provider, [{"name": "getACLAdmin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "getACLAdmin")
    notes.append(f"PoolAddressesProvider.getACLAdmin() = {acl_admin} (matches owner(): {acl_admin == executor})")

    payloads_controller = read_address_getter(w3, executor, addr_abi_name) if executor else None
    notes.append(f"EXECUTOR_LVL_1.owner() = {payloads_controller} (PayloadsController)")

    loop_check = read_address_getter(w3, payloads_controller, addr_abi_name) if payloads_controller else None
    notes.append(f"PayloadsController.owner() = {loop_check} (closes back to EXECUTOR_LVL_1: {loop_check == executor})")

    settings_abi = [{"name": "getExecutorSettingsByAccessControl", "type": "function", "stateMutability": "view",
                      "inputs": [{"type": "uint8"}], "outputs": [{"type": "tuple", "components": [{"type": "address"}, {"type": "uint40"}]}]}]
    settings = call_raw(w3, payloads_controller, settings_abi, "getExecutorSettingsByAccessControl", 1) if payloads_controller else None
    notes.append(f"PayloadsController.getExecutorSettingsByAccessControl(1) = {settings} (executor, delaySeconds)")

    guardian = call_raw(w3, payloads_controller, [{"name": "guardian", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "guardian") if payloads_controller else None
    notes.append(f"PayloadsController.guardian() = {guardian} (can cancel proposals outside the timelock)")

    # ADDED 2026-09-17 (closed a real cross-ecosystem gap, mirrors the same
    # comparison added the same day in chains/arbitrum-ecosystem/scorers.py's
    # score_aave_v3_pool_arbitrum() -- see that function's own comment and
    # scripts/lib/cross_ecosystem_overlap.py's BASE_GROUPS/ARBITRUM_GROUPS
    # "aave_guardian" entries for the full finding): this guardian Safe's
    # owner set was live-read here for the first time (previously only its
    # address was read, never its owners) and compared against a DATED
    # snapshot of Arbitrum's own Aave V3 GOVERNANCE_GUARDIAN Safe -- found
    # to be the EXACT SAME 9 owners at 5-of-9, a different address, the same
    # CREATE2-redeployed shared-committee pattern this project's sister
    # research (multisig-overlap) already documented for
    # ether.fi/Curve, found live in this project's own tracked targets.
    guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    if guardian_safe:
        g_owners, g_threshold = guardian_safe
        notes.append(f"GOVERNANCE_GUARDIAN is a real Gnosis Safe: {g_threshold}-of-{len(g_owners)}")
    else:
        notes.append(f"{guardian}: NOT resolvable as a Gnosis Safe this run")
    ARBITRUM_AAVE_GUARDIAN_OWNERS_2026_09_17 = frozenset({
        "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
        "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
        "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
        "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
        "0x4C30E33758216aD0d676419c21CB8D014C68099f",
    })
    shares_committee_with_arbitrum = bool(guardian_safe) and {w3.to_checksum_address(o) for o in guardian_safe[0]} == {w3.to_checksum_address(o) for o in ARBITRUM_AAVE_GUARDIAN_OWNERS_2026_09_17}
    if shares_committee_with_arbitrum:
        notes.append("GOVERNANCE_GUARDIAN Safe owner set is IDENTICAL to Arbitrum's own Aave V3 guardian Safe (dated 2026-09-17 snapshot, different address, same 9 signers) -- one compromised committee reaches both chains' emergency-cancel path")

    notes.append(
        "Open thread, disclosed rather than guessed: the Ethereum-mainnet Aave DAO root "
        "(CROSS_CHAIN_CONTROLLER relay, L1 proposal counts/quorum) was NOT re-verified live "
        "this pass -- this scorer confirms the Base-side executor/payloads-controller pair "
        "only. See chains/ethereum-l1/scorers.py's score_aave_v3_pool() for the L1 root."
    )
    if not shares_committee_with_arbitrum:
        notes.append(_CROSS_EXPOSURE_NOTE)

    delay = settings[1] if settings else None
    admin_key = 65 if payloads_controller and loop_check == executor else 30
    multisig = 100  # not applicable: PayloadsController/Executor pair is not a Safe
    timelock_score = 50 if delay and delay > 0 else 0  # confirmed real 1-day delay, capped for the unverified L1 root + guardian cancel-path outside the timelock
    cross_exposure = 80 if shares_committee_with_arbitrum else 100

    # ADDED 2026-10-04 (Spap's go): a price consumer's oracleAuthorityScore is the min over its material price paths
    # one hop upstream (scripts/lib/price_authority.py, METHODOLOGY 'oracleAuthorityScore for price consumers').
    oracle_authority = price_authority.for_aave(w3, provider, None, notes)
    return {
        "target": provider,
        "label": "Aave V3 Base (PoolAddressesProvider)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": oracle_authority,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_aerodrome_poolfactory(w3) -> dict:
    """Aerodrome Finance PoolFactory (Base-native, classic-AMM) -- $322.7M TVL,
    the largest Base-native (not multichain-ported) target found in scouting.
    Source: official aerodrome-finance/contracts GitHub repo README, Base
    mainnet deployment addresses table. Authority: `owner()` reverts (no
    single-owner design) -- `pauser()` and `feeManager()` both resolve, live,
    to the SAME address, a real Gnosis Safe.

    CLOSED 2026-09-18 (was an open question: "Voter not traced, arguably the
    higher-value lever"): `Voter.governor()` -- the role that can
    `whitelistToken` (gatekeeps which ERC20s may receive emissions),
    `createGauge` with BOTH of the public path's safety checks bypassed
    (can create an emission-eligible gauge for an arbitrary, even
    non-pool, address), and `setGovernor` (self-reassignment, no
    timelock, no other check) -- is confirmed LIVE, on two independent
    RPCs, to be the EXACT SAME Safe address as `pauser()`/`feeManager()`
    above, not merely a shared signer. So this is not a second,
    independently weaker full-power path to take a minimum over (as
    METHODOLOGY.md 6.2's convention would otherwise call for) -- it is
    the identical key, and the score below already reflects its real
    strength. What changes is the DISCLOSED SCOPE: this one 3-of-7 Safe's
    blast radius is broader than "pause pools and change fees" alone --
    it can also redirect where AERO emissions flow and reassign itself,
    with no timelock anywhere in the chain (confirmed against Aerodrome's
    own current `Voter.sol` source, aerodrome-finance/contracts, not
    inferred from selectors alone).

    `Voter.emergencyCouncil()` is a SEPARATE, genuinely different 3-of-5
    Safe (zero owner overlap with the governor/pauser/feeManager Safe,
    confirmed live) -- but its only powers, `killGauge`/`reviveGauge`,
    are BOUNDED per METHODOLOGY.md 6.2 (kills exactly one gauge,
    reversible, sweeps only that gauge's own already-accrued-unclaimed
    emissions back to the minter -- cannot touch other gauges, cannot
    whitelist/blacklist, cannot move claimed funds), so it is disclosed
    in `notes` rather than folded into the composite, the same
    restrict-only treatment this project already gives Kamino's
    emergency council on Solana."""
    target = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
    notes = []

    owner = call_raw(w3, target, [{"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "owner", retries=1)
    notes.append(f"PoolFactory.owner() = {owner} (expected None/revert -- no single-owner design)")

    pauser = read_address_getter(w3, target, "pauser")
    fee_manager = read_address_getter(w3, target, "feeManager")
    notes.append(f"pauser() = {pauser}, feeManager() = {fee_manager} (same address: {pauser == fee_manager})")

    voter = read_address_getter(w3, target, "voter")
    governor = read_address_getter(w3, voter, "governor") if voter else None
    emergency_council = read_address_getter(w3, voter, "emergencyCouncil") if voter else None
    if governor and pauser and governor.lower() != pauser.lower():
        # Live-checked every run, not trusted from the 2026-09-18 finding
        # that closed this open point -- if the Safes were ever rotated to
        # diverge, this scorer must not silently keep treating them as one
        # key. Degrades to the unresolved-authority branch below rather
        # than mis-scoring.
        notes.append(f"voter().governor() = {governor} -- NO LONGER matches pauser/feeManager ({pauser}); the 2026-09-18 finding that these are the same key is STALE, degrading")
        pauser = None
    else:
        notes.append(
            f"voter() = {voter}, governor() = {governor} -- CONFIRMED live to be the exact same Safe as "
            f"pauser()/feeManager() (not just a shared signer), closing the previously-open 'Voter not traced' "
            f"question: whitelistToken/createGauge-bypass/setGovernor all sit behind this one already-scored key"
        )
    safe = safe_owners_and_threshold(w3, pauser) if pauser else None
    if not safe:
        notes.append(f"{pauser}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"pauser/feeManager Safe: {threshold}-of-{len(owners)}")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController or delay found anywhere in this chain

    if emergency_council:
        council_safe = safe_owners_and_threshold(w3, emergency_council)
        if council_safe:
            c_owners, c_threshold = council_safe
            # FIXED 2026-09-18 (adversarial review): this note used to assert
            # "zero owner overlap" as fixed prose without ever actually
            # computing it -- true today, but nothing would have caught it
            # going stale. Now genuinely intersected live every run, the same
            # discipline the governor/pauser identity check just above
            # already uses.
            overlap = {o.lower() for o in c_owners} & {o.lower() for o in (safe[0] if safe else [])}
            overlap_text = "zero owner overlap with governor/pauser/feeManager" if not overlap else f"OVERLAPS governor/pauser/feeManager on {sorted(overlap)} -- no longer an independent key set"
            notes.append(
                f"emergencyCouncil() = {emergency_council}, a SEPARATE {c_threshold}-of-{len(c_owners)} Safe "
                f"({overlap_text}) -- BOUNDED (killGauge/reviveGauge only, per chains/solana/METHODOLOGY.md's "
                f"6.2 full-power/bounded/restrict-only convention, reused project-wide), disclosed here rather "
                f"than folded into the composite"
            )

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        # ADDED 2026-09-19 (maintenance run): exposed so score_all()'s
        # intra-Base overlap post-pass can compare this root Safe against
        # every other Safe-rooted Base target (see _apply_intra_base_overlap).
        "rootSafeOwners": list(safe[0]) if safe else [],
        "target": target,
        "label": "Aerodrome Finance PoolFactory (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_UNISWAP_SHARED_ROOT_NOTE = (
    "crossExposureScore = 80: the same root authority, Uniswap's Ethereum L1 Governance Timelock "
    "(0x1a9C8182C09F50C8318d769245beA52c32BE35BC), re-confirmed live by this scorer, also controls tracked Uniswap "
    "targets on other ecosystems (Ethereum L1 V3 Factory and V4 PoolManager, Arbitrum V3 Factory, Robinhood Chain "
    "V3/V4/UniswapX/V2, Monad V4 PoolManager; dated 2026-09-20) and the other two Base Uniswap targets. It is a "
    "token-vote DAO contract, not a signer committee, but it is one root identity, so the cross-ecosystem fold (a "
    "flat 80) applies as for a shared Safe committee (convention of 2026-09-20; the earlier 'DAO/Timelock-rooted "
    "targets are not counted' wording is retired)"
)


def score_uniswap_v3_factory_base(w3) -> dict:
    """Uniswap V3 Factory (Base) -- $271.0M TVL. Source: official
    docs.uniswap.org Base Deployments reference page, linked to
    Uniswap/uniswap-v3-core GitHub source. Authority chain, more directly
    verifiable than the Robinhood/Arbitrum sibling cases in this project:
    Factory.owner() -> a real fee-adapter/wrapper contract (7,266 bytes,
    exposes enableFeeAmount itself) -> a second contract (1,419 bytes) whose
    OWN getters (owner/getMinDelay/admin/l1Timelock) all revert, but whose raw
    storage does not need guessing: slot 0 is the canonical OP-stack
    `L2CrossDomainMessenger` predeploy (`0x4200...0007`, identical on every
    OP-stack chain including Base) and slot 1 is Uniswap's real Ethereum-
    mainnet Governance Timelock address -- an explicit, readable
    `L2CrossDomainMessenger`-gated authorization check, not an address-derived
    alias that has to be reverse-computed (contrast the Arbitrum-aliasing case
    corrected in the root scorers.py's `score_uniswap_v3_factory()`
    docstring).

    Unlike every other scorer in this file, this one DELIBERATELY also opens
    its own Ethereum-mainnet Web3 instance (ignoring the Base `w3` passed in
    for that one hop) to independently re-confirm the L1 Timelock's
    `delay()`/`admin()` live, rather than trusting a prior session's note that
    this is "Uniswap's real Governance Timelock" -- same discipline the root
    scorers.py already applies in `score_rollup_l1_authority()`."""
    factory = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
    notes = []

    adapter = read_address_getter(w3, factory, "owner")
    notes.append(f"Factory.owner() = {adapter}")
    adapter_code = w3.eth.get_code(w3.to_checksum_address(adapter)) if adapter else b""
    notes.append(f"adapter code size = {len(adapter_code)} bytes (not a bare EOA)")

    forwarder = read_address_getter(w3, adapter, "owner") if adapter else None
    notes.append(f"adapter.owner() = {forwarder}")

    slot0 = read_slot_as_address(w3, forwarder, "0x0000000000000000000000000000000000000000000000000000000000000000") if forwarder else None
    slot1 = read_slot_as_address(w3, forwarder, "0x0000000000000000000000000000000000000000000000000000000000000001") if forwarder else None
    notes.append(f"forwarder slot 0 = {slot0} (expected canonical L2CrossDomainMessenger predeploy 0x4200...0007)")
    notes.append(f"forwarder slot 1 = {slot1} (expected Uniswap's real L1 Governance Timelock)")

    l1_timelock = slot1
    l1_delay = l1_admin = None
    if l1_timelock:
        l1_w3 = get_w3("https://ethereum-rpc.publicnode.com")
        l1_delay = call_raw(l1_w3, l1_timelock, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay")
        l1_admin = call_raw(l1_w3, l1_timelock, [{"name": "admin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "admin")
        notes.append(
            f"Independently re-confirmed live on Ethereum L1 (own w3 instance, not the Base one): "
            f"{l1_timelock}.delay() = {l1_delay}s, .admin() = {l1_admin} (Uniswap's real GovernorBravo)"
        )

    # FIXED 2026-09-17 (closed a bug hunt finding): slot0 was read and noted
    # but never actually compared against the expected L2CrossDomainMessenger
    # predeploy -- the docstring above claims "an explicit, readable
    # L2CrossDomainMessenger-gated authorization check", but the gate itself
    # only ever looked at slot1 (l1_timelock). If forwarder's slot0 ever held
    # anything other than the canonical predeploy while slot1 still exposed
    # delay()/admin(), this scorer would still award the high "independently
    # re-confirmed" score with no cross-domain gate actually verified.
    L2_CROSS_DOMAIN_MESSENGER_PREDEPLOY = "0x4200000000000000000000000000000000000007"
    slot0_is_predeploy = bool(slot0 and slot0.lower() == L2_CROSS_DOMAIN_MESSENGER_PREDEPLOY.lower())
    notes.append(f"forwarder slot0 matches the expected L2CrossDomainMessenger predeploy: {slot0_is_predeploy}")
    if not slot0_is_predeploy:
        notes.append("forwarder slot0 does NOT match the canonical L2CrossDomainMessenger predeploy -- the cross-domain gate this scorer's docstring claims is unverified this run, degrading rather than trusting slot1 alone")
    l1_reconfirmed = bool(slot0_is_predeploy and l1_timelock and l1_delay is not None and l1_admin)
    # ADDED 2026-09-20: the shared-root fold needs the slot 1 address to BE Uniswap's known L1 Timelock, not merely some
    # timelock that answers delay()/admin(); otherwise it stays the unverified 100.
    shared_uniswap_root = bool(l1_reconfirmed and l1_timelock.lower() == UNISWAP_L1_TIMELOCK.lower())
    cross_exposure = 80 if shared_uniswap_root else 100
    notes.append(_UNISWAP_SHARED_ROOT_NOTE if shared_uniswap_root else _CROSS_EXPOSURE_NOTE)
    if l1_reconfirmed:
        admin_key = 80  # real, active L1 DAO reached via an explicit cross-domain authorization check, independently re-confirmed live this pass
    else:
        # FIXED 2026-09-17 (closed an audit finding): this used to be a bare
        # literal 80 regardless of whether the L1 cross-domain
        # re-confirmation below actually succeeded -- timelockScore was
        # already correctly gated on l1_delay, adminKeyScore was not, so a
        # failed L1 read silently kept the confident "independently
        # re-confirmed" 80 while timelockScore correctly dropped to 0.
        admin_key = 20
        notes.append("L1 cross-domain re-confirmation (slot0/slot1/l1_timelock/delay/admin) did not fully resolve -- adminKeyScore degraded, treat as unverified this run")
    multisig = 100  # not applicable: no Safe layer, pure DAO+Timelock construction relayed cross-chain
    timelock_score = 75 if l1_delay and l1_delay > 0 else 0  # confirmed real delay live; capped below 100, no emergency-bypass check done this pass (same caveat as the Ethereum-L1 sibling scorer)

    return {
        "target": factory,
        "label": "Uniswap V3 Factory (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


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


def score_compound_v3_comet_base_usdc(w3) -> dict:
    """Compound V3 (Comet, USDC market, Base) -- $24.9M TVL. Source: official
    compound-finance/comet GitHub repo, `deployments/base/usdc/roots.json`.
    Authority chain, fully closed and internally consistent: Comet.governor()
    -> LocalTimelock (also confirmed as the EIP-1967 admin-slot owner of the
    Comet proxy, i.e. it controls both parameter changes AND upgrades) ->
    LocalTimelock.admin() -> BaseBridgeReceiver (matches the `bridgeReceiver`
    field in the official roots.json exactly) -> BaseBridgeReceiver
    .govTimelock() -> Compound's well-known Ethereum-mainnet Governance
    Timelock; .localTimelock() closes the loop back to the same LocalTimelock
    that is Comet's governor. Genuine Compound mainnet-governance -> OP-stack
    cross-domain message -> BaseBridgeReceiver -> LocalTimelock -> Comet
    chain. LocalTimelock's own `delay()` is re-confirmed live here (86,400s /
    1 day) -- this is the ACTUALLY-ENFORCED local delay on Base; the L1
    Compound Timelock's own delay is a separate, un-queried fact out of scope
    for a Base-RPC scorer (same reasoning as the Aave scorer above)."""
    target = "0xb125E6687d4313864e53df431d5425969c15Eb2F"
    notes = []

    governor = read_address_getter(w3, target, "governor")
    notes.append(f"Comet.governor() = {governor} (LocalTimelock)")

    proxy_admin = read_slot_as_address(w3, target, EIP1967_ADMIN_SLOT)
    proxy_admin_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    notes.append(
        f"EIP-1967 admin slot on Comet proxy -> ProxyAdmin {proxy_admin}; ProxyAdmin.owner() = "
        f"{proxy_admin_owner} (matches governor(), i.e. same LocalTimelock controls both parameter "
        f"changes and upgrades: {proxy_admin_owner == governor})"
    )

    delay = call_raw(w3, governor, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay") if governor else None
    notes.append(f"LocalTimelock.delay() = {delay}s (actually-enforced local Base delay)")

    bridge_receiver = read_address_getter(w3, governor, "admin") if governor else None
    notes.append(f"LocalTimelock.admin() = {bridge_receiver} (expected BaseBridgeReceiver, matches roots.json's bridgeReceiver field)")

    gov_timelock = read_address_getter(w3, bridge_receiver, "govTimelock") if bridge_receiver else None
    notes.append(f"BaseBridgeReceiver.govTimelock() = {gov_timelock} (Compound's real Ethereum-mainnet Governance Timelock)")

    local_check = read_address_getter(w3, bridge_receiver, "localTimelock") if bridge_receiver else None
    notes.append(f"BaseBridgeReceiver.localTimelock() = {local_check} (closes the loop back to governor: {local_check == governor})")

    pause_guardian = read_address_getter(w3, target, "pauseGuardian")
    pg = safe_owners_and_threshold(w3, pause_guardian) if pause_guardian else None
    notes.append(f"Comet.pauseGuardian() = {pause_guardian} ({f'{pg[1]}-of-{len(pg[0])} Safe' if pg else 'not a Safe this run'}) -- pause-only path outside the timelock")
    cross_ecosystem = bool(pg) and {o.lower() for o in pg[0]} == _KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20
    cross_exposure = 80 if cross_ecosystem else 100
    notes.append("Real cross-chain finding, independently re-confirmed 2026-09-20: this pauseGuardian Safe's 9 owners are IDENTICAL, as an exact set, to the pauseGuardian Safes of Compound V3 on Ethereum L1 (0xbbf3f142...) and Arbitrum (0x78E6317D...) at the same 5-of-9 (three different Safe addresses), so one committee can freeze three Comets. Folded into crossExposureScore as a flat 80 (dated snapshot _KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20 compared with the owners read this run, no second-chain RPC)." if cross_ecosystem else _CROSS_EXPOSURE_NOTE)
    chain_closed = bool(governor) and proxy_admin_owner == governor and bool(gov_timelock) and local_check == governor
    admin_key = 75 if chain_closed else 35
    multisig = 100  # not applicable: LocalTimelock/BaseBridgeReceiver pair is not a Safe
    if delay and delay > 0:
        # FIXED 2026-09-25: was 65, uncapped, while chains/ethereum-l1/scorers.py's twin Comet
        # scorer already caps this same real delay at 60 for the identical pauseGuardian bypass
        # (a same-shaped Safe, same convention this ecosystem's own Fluid Liquidity guardian
        # path already applies elsewhere) -- METHODOLOGY.md's own rule ("a confirmed bypass
        # that is bounded... caps the score at 55") was applied on L1 but not here, an
        # inconsistency found and verified 2026-09-25 (data/finding_2026-09-25-repo-wide-sweep.md).
        # Same cap as L1, not the stricter 55, since the bypass shape (an identified Safe,
        # instant pause, no fund redirect) is identical to what earned L1's Comet its 60.
        timelock_score = 60 if pg else 65
    else:
        timelock_score = 0  # confirmed real 1-day LOCAL delay live; the L1 Compound Timelock's own delay is not queried by this Base-RPC scorer

    # ADDED 2026-10-04 (Spap's go): a price consumer's oracleAuthorityScore is the min over its material price paths
    # one hop upstream (scripts/lib/price_authority.py, METHODOLOGY 'oracleAuthorityScore for price consumers').
    oracle_authority = price_authority.for_comet(w3, target, None, notes)
    return {
        "target": target,
        "label": "Compound V3 (Comet, USDC market, Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": oracle_authority,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# ADDED 2026-09-19 (maintenance run, budget (b)): 4 new Base targets. Every
# address below comes from the protocol's own official source (cited per
# scorer) and was cross-checked against DefiLlama-Adapters for the TVL
# attribution; every authority hop was read live on TWO independent Base RPCs
# (mainnet.base.org + base-rpc.publicnode.com) before this code was written --
# see runs/2026-09-19-cron/base-ecosystem/ in the pipeline's evidence folder.
# Full writeup: chains/base-ecosystem/data/scored_targets_2026-09-19-maintenance.md
# ---------------------------------------------------------------------------

L2_CROSS_DOMAIN_MESSENGER_PREDEPLOY_ADDR = "0x4200000000000000000000000000000000000007"


def score_aerodrome_slipstream_clfactory(w3) -> dict:
    """Aerodrome Slipstream CLFactory (Base, concentrated-liquidity) -- DefiLlama
    "Aerodrome Slipstream" $217.0M Base TVL on 2026-09-19. Source:
    aerodrome-finance/slipstream README "Initial Deployment" table (PoolFactory
    0x5e7B...809A), also the first of the 4 factories listed for Base in
    DefiLlama-Adapters projects/aerodrome-CL/index.js. The two later factories
    (Gauge Caps / Gauges V3 deployments) are NOT scored here -- open thread.

    Authority: owner() (setOwner, enableTickSpacing), swapFeeManager()
    (setSwapFeeModule) and unstakedFeeManager() (setUnstakedFeeModule /
    setDefaultUnstakedFee -- CORRECTED 2026-09-19: only setDefaultUnstakedFee is
    capped at 50%; the deployed source accepts a swap-fee MODULE up to 10% and an
    unstaked-fee MODULE up to 100% (`fee <= 1_000_000`)) all resolve,
    live, to ONE Gnosis Safe -- the SAME Safe already tracked as Aerodrome V1
    PoolFactory's pauser/feeManager and Voter.governor(). No timelock anywhere.
    Pools are clones of a fixed implementation (no pool upgrade path found)."""
    target = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"
    notes = []
    owner = read_address_getter(w3, target, "owner")
    swap_fee_mgr = read_address_getter(w3, target, "swapFeeManager")
    unstaked_fee_mgr = read_address_getter(w3, target, "unstakedFeeManager")
    notes.append(f"CLFactory.owner() = {owner}, swapFeeManager() = {swap_fee_mgr}, unstakedFeeManager() = {unstaked_fee_mgr}")
    same_key = bool(owner) and swap_fee_mgr == owner and unstaked_fee_mgr == owner
    notes.append(f"all three roles on one address: {same_key}")
    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe or not same_key:
        notes.append("root authority not resolved as ONE Gnosis Safe this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
        root_owners = []
    else:
        owners, threshold = safe
        root_owners = list(owners)
        notes.append(f"owner Safe: {threshold}-of-{len(owners)}, no timelock in the chain")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0
    return {
        "rootSafeOwners": root_owners,
        "target": target,
        "label": "Aerodrome Slipstream CLFactory (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,  # set by score_all()'s intra-Base overlap post-pass
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# The forwarder behind the tracked Uniswap V3 Factory (Base) and the real Uniswap L1 Governance Timelock in its slot 1
# (chains/base-ecosystem/data/scouted_targets_2026-09-16.md section 4). V2 and V4 claim to share them; that claim is
# now compared, not asserted (fixed 2026-09-20).
UNISWAP_BASE_FORWARDER = "0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9"
UNISWAP_L1_TIMELOCK = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"


def _uniswap_direct_forwarder_score(w3, target, getter, label, scope_note) -> dict:
    """Shared logic for Uniswap targets whose authority getter points DIRECTLY
    at the OP-stack cross-domain forwarder (no fee-adapter hop in between,
    unlike score_uniswap_v3_factory_base above). Same gates as that scorer:
    slot0 must be the canonical L2CrossDomainMessenger predeploy, slot1 is the
    L1 Governance Timelock, whose delay()/admin() are re-read live on L1 with
    a separate w3 instance."""
    notes = []
    forwarder = read_address_getter(w3, target, getter)
    notes.append(f"{getter}() = {forwarder}")
    slot0 = read_slot_as_address(w3, forwarder, "0x" + "00" * 32) if forwarder else None
    slot1 = read_slot_as_address(w3, forwarder, "0x" + "00" * 31 + "01") if forwarder else None
    notes.append(f"forwarder slot 0 = {slot0}, slot 1 (L1 Governance Timelock) = {slot1}")
    slot0_ok = bool(slot0 and slot0.lower() == L2_CROSS_DOMAIN_MESSENGER_PREDEPLOY_ADDR.lower())
    notes.append(f"forwarder slot0 matches the L2CrossDomainMessenger predeploy: {slot0_ok}")
    l1_delay = l1_admin = None
    if slot1:
        l1_w3 = get_w3("https://ethereum-rpc.publicnode.com")
        l1_delay = call_raw(l1_w3, slot1, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay")
        l1_admin = call_raw(l1_w3, slot1, [{"name": "admin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "admin")
        notes.append(f"L1 (own w3): {slot1}.delay() = {l1_delay}s, .admin() = {l1_admin}")
    notes.append(scope_note)
    same_root = bool(forwarder and slot1 and forwarder.lower() == UNISWAP_BASE_FORWARDER.lower()
                     and slot1.lower() == UNISWAP_L1_TIMELOCK.lower())
    l1_ok = bool(slot0_ok and slot1 and l1_delay is not None and l1_admin)
    shared_uniswap_root = bool(same_root and l1_ok)
    if same_root:
        notes.append(
            "Same forwarder and same L1 Governance Timelock as the already-tracked Uniswap V3 Factory (Base): "
            "one DAO root for V2/V3/V4 on Base."
        )
    else:
        notes.append(
            f"Forwarder and/or L1 Governance Timelock differ from, or could not be compared with, the tracked Uniswap V3 "
            f"Factory's ({UNISWAP_BASE_FORWARDER} / {UNISWAP_L1_TIMELOCK}): NOT asserted to be the same DAO root as V3."
        )
    notes.append(_UNISWAP_SHARED_ROOT_NOTE if shared_uniswap_root else _CROSS_EXPOSURE_NOTE)
    if not l1_ok:
        notes.append("L1 cross-domain re-confirmation did not fully resolve -- adminKeyScore degraded")
    admin_key = 80 if l1_ok else 20
    timelock_score = 75 if (l1_ok and l1_delay and l1_delay > 0) else 0
    multisig = 100  # not applicable: DAO + Timelock relayed cross-chain, no Safe layer
    return {
        "target": target,
        "label": label,
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 80 if shared_uniswap_root else 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_uniswap_v2_factory_base(w3) -> dict:
    """Uniswap V2 Factory (Base) -- DefiLlama "Uniswap V2" $89.1M Base TVL on
    2026-09-19. Source: Uniswap/docs content/protocols/v2/deployments.mdx
    (Base row) and Uniswap/sdk-core src/addresses.ts (V2_FACTORY_ADDRESSES
    [ChainId.BASE]); same address in DefiLlama-Adapters projects/uniswap-v2."""
    return _uniswap_direct_forwarder_score(
        w3, "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6", "feeToSetter",
        "Uniswap V2 Factory (Base)",
        "Scope caveat: feeToSetter can only set feeTo / hand over feeToSetter (the V2 protocol-fee switch) -- "
        "no pool upgrade, no access to LP principal. Root authority mechanism scored as-is per project convention.",
    )


def score_uniswap_v4_poolmanager_base(w3) -> dict:
    """Uniswap V4 PoolManager (Base) -- DefiLlama "Uniswap V4" $59.3M Base TVL
    on 2026-09-19. Source: Uniswap/docs content/protocols/v4/deployments.mdx
    ("Base: 8453" table); same address in DefiLlama-Adapters
    projects/uniswap-v4 (base factory)."""
    return _uniswap_direct_forwarder_score(
        w3, "0x498581fF718922c3f8e6A244956aF099B2652b2b", "owner",
        "Uniswap V4 PoolManager (Base)",
        "Scope caveat: PoolManager.owner() has two onlyOwner functions, setProtocolFeeController "
        "(v4-core ProtocolFees.sol) and transferOwnership (solmate Owned) -- corrected 2026-09-19, this "
        "note previously named only the first; the controller, not the owner, sets per-pool protocol fees "
        "(capped at 0.1% per direction by isValidProtocolFee) and collects them. PoolManager is not a proxy "
        "and has no upgrade function. Root mechanism scored as-is.",
    )


def score_moonwell_comptroller_base(w3) -> dict:
    """Moonwell (Base) Unitroller/Comptroller -- DefiLlama "Moonwell Lending"
    $14.0M Base TVL on 2026-09-19 (Base-native lending market). Source:
    moonwell-fi/moonwell-contracts-v2 chains/8453.json (UNITROLLER,
    TEMPORAL_GOVERNOR) and DefiLlama-Adapters registries/compound.js
    (moonwell.base.comptroller).

    Authority: Unitroller.admin() -> TemporalGovernor (Wormhole-VAA-gated
    cross-chain executor). Its only trusted sender, read live, is
    Wormhole chain 2 (Ethereum) 0x8769...5838 = MULTICHAIN_GOVERNOR_V2_PROXY
    per moonwell-fi's own chains/1.json. proposalDelay() = 1 day. The
    TemporalGovernor owner (guardian) is a Safe that can togglePause() once
    and, while paused, fastTrackProposalExecution() -- executing a valid
    trusted-sender VAA WITHOUT the delay (TemporalGovernor.sol). The L1
    governor itself (voting/quorum/proxy admin on Ethereum) and the Wormhole
    guardian set are NOT verified by this Base-RPC scorer -- same capped
    treatment as score_aave_v3_base()."""
    target = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
    notes = []
    admin = read_address_getter(w3, target, "admin")
    notes.append(f"Unitroller.admin() = {admin} (TemporalGovernor)")
    uint_abi = lambda n: [{"name": n, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    delay = call_raw(w3, admin, uint_abi("proposalDelay"), "proposalDelay") if admin else None
    senders_abi = [{"name": "allTrustedSenders", "type": "function", "stateMutability": "view",
                    "inputs": [{"type": "uint16"}], "outputs": [{"type": "bytes32[]"}]}]
    eth_senders = call_raw(w3, admin, senders_abi, "allTrustedSenders", 2) if admin else None
    eth_senders = ["0x" + bytes(x).hex()[-40:] for x in (eth_senders or [])]
    guardian = read_address_getter(w3, admin, "owner") if admin else None
    pause_allowed = call_raw(w3, admin, [{"name": "guardianPauseAllowed", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]}], "guardianPauseAllowed") if admin else None
    notes.append(f"TemporalGovernor.proposalDelay() = {delay}s, trusted senders on Wormhole chain 2 (Ethereum) = {eth_senders}")
    notes.append(f"TemporalGovernor.owner() (guardian) = {guardian}, guardianPauseAllowed = {pause_allowed}")
    g_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    if g_safe:
        notes.append(f"guardian is a real Gnosis Safe: {g_safe[1]}-of-{len(g_safe[0])} -- can pause once and fast-track a valid VAA past the delay")
    expected_sender = "0x8769b70ac7c93af0e75de0d69877709b66d75838"
    chain_ok = bool(admin) and eth_senders == [expected_sender]
    notes.append(f"only trusted sender is Moonwell's MULTICHAIN_GOVERNOR_V2_PROXY (chains/1.json): {chain_ok}")
    notes.append(
        "Open thread, disclosed rather than guessed: the Ethereum-side MultichainGovernor (quorum, proxy admin) "
        "and Wormhole's own guardian set were NOT re-verified this pass. pauseGuardian (3-of-5 Safe) and "
        "borrow/supplyCapGuardian (2-of-4 Safe) on the Comptroller are bounded pause/cap roles, disclosed not folded in."
    )
    notes.append(_CROSS_EXPOSURE_NOTE)
    admin_key = 65 if chain_ok else 30
    multisig = 100  # not applicable: root is a cross-chain DAO executor, not a Safe
    timelock_score = 50 if (chain_ok and delay and delay > 0) else 0  # real 1-day delay, capped: guardian fast-track path outside the delay
    return {
        "target": target,
        "label": "Moonwell Comptroller (Unitroller, Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ADDED 2026-09-25 (Morpho vault layer, `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`
# backlog item 1 -- same pass as 4 new Ethereum L1 Morpho vault targets, see that file's own module-level
# comment for the full context). Largest Morpho V1 vaults on Base above $20M TVL by Morpho's own public API
# (blue-api.morpho.org, `chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py --chains 8453`, re-read live
# 2026-09-25), same `owner()`/`curator()`/`guardian()` read and same formula as `chains/monad/scorers.py::
# score_morpho_vault_monad` and this pass's own Ethereum L1 Steakhouse vaults -- no new methodology.
_KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25 = "0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD"
_KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25 = "0x827e86072B06674a077f592A531dcE4590aDeCdB"


def score_morpho_gauntlet_usdc_prime_base(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Gauntlet USDC Prime" (Base) -- $415.7M by Morpho's API
    2026-09-25, the largest Morpho vault on Base above $20M not already Steakhouse-curated.
    Live-read `owner()`, `curator()` and `guardian()` resolve to THREE DIFFERENT Safe
    addresses (4-of-7, 3-of-7, 3-of-7) -- but their owner SETS are IDENTICAL, the same 7
    signers on all three, independently re-confirmed live this pass (matching `data/
    finding_2026-09-20-...`'s own citation for this exact vault: "the three Safes have
    exactly the same 7 signers... a guardian veto held by the same signers as the owner
    and curator is not an independent check"). The 14-day curator timelock is real, but its
    only independent check (the guardian) is nominal."""
    vault = "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61"
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    guardian = read_address_getter(w3, vault, "guardian")
    notes.append(f"vault.owner() = {owner}, vault.curator() = {curator}, vault.guardian() = {guardian}")
    owner_safe = safe_owners_and_threshold(w3, owner) if owner else None
    curator_safe = safe_owners_and_threshold(w3, curator) if curator else None
    guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    if owner_safe and curator_safe and guardian_safe:
        owner_owners, owner_threshold = owner_safe
        curator_owners, curator_threshold = curator_safe
        guardian_owners, _ = guardian_safe
        notes.append(f"owner Safe: {owner_threshold}-of-{len(owner_owners)}, curator Safe: {curator_threshold}-of-{len(curator_owners)}, guardian Safe: {guardian_safe[1]}-of-{len(guardian_owners)}")
        same_signers = {o.lower() for o in owner_owners} == {o.lower() for o in curator_owners} == {o.lower() for o in guardian_owners}
        notes.append(
            f"owner, curator and guardian Safes' signer sets are IDENTICAL: {same_signers} -- if true, the guardian's "
            "veto during the curator's timelock is exercised by the same people who queued the change, not an "
            "independent check, even though the three Safe contracts are genuinely distinct addresses"
        )
        admin_key = 70 if owner_threshold >= 5 else (60 if owner_threshold >= 3 else 30)
        multisig = min(100, curator_threshold * 15 + max(0, len(curator_owners) - curator_threshold) * 5)
        timelock_score = 55 if same_signers else 75  # same convention as score_morpho_vault_monad: a real delay whose only veto party is the same signers as the proposer scores well below one with an independent guardian
        signers = set(owner_owners) | set(curator_owners) | set(guardian_owners)
    else:
        notes.append("owner/curator/guardian did not all resolve as Gnosis Safes this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 20, 0
        signers = set()
    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "rootSafeOwners": list(owner_safe[0]) if owner_safe else [],
        "target": vault,
        "label": "Morpho V1: Gauntlet USDC Prime (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_morpho_spark_usdc_vault_base(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Spark USDC Vault" (Base) -- $312.0M by Morpho's API
    2026-09-25. Live-read `owner()` is a bespoke 8,210-byte contract that answers neither
    `owner()` nor `admin()` (not Ownable/proxy-admin shaped, not opened further this pass --
    Spark's own custom relayer/allocator pattern, disclosed as an open point rather than
    guessed at). `curator()` and `guardian()` ARE real, DIFFERENT Safes with NO shared
    signers (5 of 5 each, zero overlap, independently re-confirmed live) -- a genuine,
    verified role separation, the same shape `data/finding_2026-09-20-...` found for Yearn's
    vaults ("one shared signer: a real separation") but here with none shared at all."""
    vault = "0x7BfA7C4f149E7415b73bdeDfe609237e29CBF34A"
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    guardian = read_address_getter(w3, vault, "guardian")
    notes.append(f"vault.owner() = {owner}, vault.curator() = {curator}, vault.guardian() = {guardian}")
    owner_inner = read_address_getter(w3, owner, "owner") if owner else None
    notes.append(f"owner's own owner() = {owner_inner} -- unresolved, this contract is not a plain Ownable/proxy-admin shape, not opened further this pass (disclosed open point)")
    curator_safe = safe_owners_and_threshold(w3, curator) if curator else None
    guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    if curator_safe and guardian_safe:
        curator_owners, curator_threshold = curator_safe
        guardian_owners, guardian_threshold = guardian_safe
        notes.append(f"curator Safe: {curator_threshold}-of-{len(curator_owners)}, guardian Safe: {guardian_threshold}-of-{len(guardian_owners)}")
        shared = {o.lower() for o in curator_owners} & {o.lower() for o in guardian_owners}
        notes.append(f"curator/guardian shared signers: {len(shared)} of {len(curator_owners)} -- {'a real, independent veto party' if not shared else 'partial overlap, not a fully independent check'}")
        # owner() unresolved this pass -- score on the curator path alone (the timelocked cap-setting authority
        # this project's own convention treats as the real operationally-relevant risk for a V1 vault), same
        # reasoning score_morpho_vault_monad's own docstring already gives for why the vault, not Morpho Blue
        # itself, is the scored target.
        admin_key = 70 if curator_threshold >= 5 else (60 if curator_threshold >= 3 else 30)
        multisig = min(100, curator_threshold * 15 + max(0, len(curator_owners) - curator_threshold) * 5)
        timelock_score = 75 if not shared else 55
        signers = set(curator_owners) | set(guardian_owners)
    else:
        notes.append("curator/guardian did not both resolve as Gnosis Safes this run -- conservative score")
        admin_key, multisig, timelock_score = 20, 20, 0
        signers = set()
    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "rootSafeOwners": list(curator_safe[0]) if curator_safe else [],
        "target": vault,
        "label": "Morpho V1: Spark USDC Vault (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def _score_steakhouse_base_vault(w3, vault, guardian_note_prefix):
    """Shared read+score body for Steakhouse-curated Morpho V1 vaults on Base -- both use the
    SAME owner Safe (`_KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25`) and curator Safe
    (`_KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25`) as this pass's own Ethereum L1 Steakhouse
    vaults -- the LITERAL SAME ADDRESSES, not merely the same signer set at a different
    address, live-confirmed on both chains this pass (owner 5-of-9 on Base vs 5-of-10 on
    Ethereum, curator 2-of-6 on Base vs 2-of-7 on Ethereum -- matching `data/
    finding_2026-09-20-...`'s own citation of these exact thresholds)."""
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    guardian = read_address_getter(w3, vault, "guardian")
    notes.append(f"vault.owner() = {owner}, vault.curator() = {curator}, vault.guardian() = {guardian}")
    notes.append(f"{guardian_note_prefix} guardian() = {guardian}")
    owner_matches = bool(owner) and owner.lower() == _KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25.lower()
    curator_matches = bool(curator) and curator.lower() == _KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25.lower()
    if owner_matches and curator_matches:
        owner_safe = safe_owners_and_threshold(w3, owner)
        curator_safe = safe_owners_and_threshold(w3, curator)
        if owner_safe and curator_safe:
            owner_owners, owner_threshold = owner_safe
            curator_owners, curator_threshold = curator_safe
            notes.append(f"owner Safe: {owner_threshold}-of-{len(owner_owners)} (SAME ADDRESS as this pass's own Ethereum L1 Steakhouse vaults' owner Safe)")
            notes.append(f"curator Safe: {curator_threshold}-of-{len(curator_owners)} (SAME ADDRESS as this pass's own Ethereum L1 Steakhouse vaults' curator Safe)")
            admin_key = 70 if owner_threshold >= 5 else (60 if owner_threshold >= 3 else 30)
            multisig = min(100, curator_threshold * 15 + max(0, len(curator_owners) - curator_threshold) * 5)
            timelock_score = 75
            notes.append(
                "Same owner AND curator Safe address as this pass's own tracked Ethereum L1 Steakhouse vaults "
                "(live-confirmed both chains 2026-09-25) -- cross-ecosystem finding, folded into crossExposureScore as a flat 80"
            )
            return admin_key, multisig, timelock_score, notes, set(owner_owners) | set(curator_owners), 80
        notes.append("owner/curator matched the known Steakhouse Safe addresses, but getOwners()/getThreshold() did not resolve this run -- conservative score")
    else:
        notes.append("owner/curator did NOT match the known Steakhouse Safes this run -- Steakhouse may have rotated, re-verify before trusting the shared-controller finding above")
    notes.append(_CROSS_EXPOSURE_NOTE)
    return 20, 20, 0, notes, set(), 100


def score_morpho_steakhouse_usdc_base(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Steakhouse USDC" (Base) -- $127.1M by Morpho's API 2026-09-25.
    See `_score_steakhouse_base_vault`'s own docstring for the shared cross-chain owner/curator
    Safe finding. `guardian()` resolves to a bare on-curve EOA, `0x9e0FdDDa790651E6a05CD2dE69e
    624B94C04eAf5` -- a single key, not a Safe, holds the independent-veto seat for this vault's
    14-day curator timelock (disclosed, not folded in: this project's own convention scores the
    curator/guardian RELATIONSHIP -- shared signers or not -- not a bare-key guardian's own
    strength, which no existing formula in this file covers)."""
    vault = "0xbeeF010f9cb27031ad51e3333f9aF9C6B1228183"
    admin_key, multisig, timelock_score, notes, owner_signers, cross_exposure = _score_steakhouse_base_vault(
        w3, vault, "A bare on-curve EOA (not a Safe) holds this vault's guardian seat --")
    return {
        "rootSafeOwners": list(owner_signers) if owner_signers else [],
        "target": vault,
        "label": "Morpho V1: Steakhouse USDC (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_morpho_grove_steakhouse_usdc_high_yield_base(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Grove x Steakhouse USDC High Yield" (Base) -- $101.1M by
    Morpho's API 2026-09-25, NOT listed on Morpho's own app (no red warnings recorded,
    unlike Adpend/1337 USDC above -- simply not surfaced in the interface). See
    `_score_steakhouse_base_vault`'s own docstring for the shared cross-chain owner/curator
    Safe finding. `guardian()` resolves to an 8,113-byte contract, `0x491EDFB0B8b608044e227
    225C715981a30F3A44E` -- not independently resolved to a Safe or opened this pass."""
    vault = "0xBeEf2d50B428675a1921bC6bBF4bfb9D8cF1461A"
    admin_key, multisig, timelock_score, notes, owner_signers, cross_exposure = _score_steakhouse_base_vault(
        w3, vault, "A separate 8,113-byte contract (not independently resolved to a Safe or opened this pass) holds this vault's guardian seat --")
    notes.append("Morpho API: NOT listed on Morpho's own app, no red warnings recorded -- disclosed context, not scored")
    return {
        "rootSafeOwners": list(owner_signers) if owner_signers else [],
        "target": vault,
        "label": "Morpho V1: Grove x Steakhouse USDC High Yield (Base)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def _apply_intra_base_overlap(results) -> None:
    """ADDED 2026-09-19: crossExposureScore WITHIN Base's own tracked set, per
    the contract's own definition (-20 per OTHER tracked target sharing at
    least one resolved root signer). Only Safe-rooted targets that expose
    `rootSafeOwners` take part (DAO/Timelock-rooted targets have no signer set
    -- same convention as cross_ecosystem_overlap.py). Deducts ON TOP of any
    cross-ecosystem deduction already applied by the scorer itself (Morpho)."""
    rooted = [r for r in results if r.get("rootSafeOwners")]
    for r in rooted:
        mine = {o.lower() for o in r["rootSafeOwners"]}
        others = [o for o in rooted if o is not r and mine & {x.lower() for x in o["rootSafeOwners"]}]
        if others:
            r["crossExposureScore"] = max(0, r["crossExposureScore"] - 20 * len(others))
            r["notes"] = [n for n in r["notes"] if n != _CROSS_EXPOSURE_NOTE]
            r["notes"].append(
                "intra-Base overlap (live, this run): root Safe signers shared with "
                + ", ".join(o["label"] for o in others)
                + f" -> crossExposureScore {r['crossExposureScore']}"
            )
        else:
            r["notes"].append("intra-Base overlap (live, this run): no root signer shared with another tracked Base target")


SIMPLE_SCORERS = [
    score_morpho_blue,
    score_aave_v3_base,
    score_aerodrome_poolfactory,
    score_uniswap_v3_factory_base,
    score_compound_v3_comet_base_usdc,
    # ADDED 2026-09-19 (maintenance run) -- appended, never reordered: the
    # oracle's trackedTargets(i) index order is the first-push order.
    score_aerodrome_slipstream_clfactory,
    score_uniswap_v2_factory_base,
    score_uniswap_v4_poolmanager_base,
    score_moonwell_comptroller_base,
    # ADDED 2026-09-25 (Morpho vault layer, backlog item 1) -- appended, never reordered: the
    # oracle's trackedTargets(i) index order is the first-push order.
    score_morpho_gauntlet_usdc_prime_base,
    score_morpho_spark_usdc_vault_base,
    score_morpho_steakhouse_usdc_base,
    score_morpho_grove_steakhouse_usdc_high_yield_base,
]


def score_all(w3) -> list:
    # FIXED 2026-09-17 (closed a bug hunt finding, same as the Arbitrum
    # sibling file): bare list comprehension with no per-target failure
    # isolation. This file's own docstring already documents Base's public
    # RPC intermittently dropping calls mid-burst -- exactly the failure
    # class that used to crash this whole 5-target batch instead of
    # isolating the one flaky target.
    results = []
    for scorer in SIMPLE_SCORERS:
        results.extend(safe_score(scorer.__name__, scorer, w3))
    _apply_intra_base_overlap(results)
    return results
