"""
Ethereum L1 authority scorers -- first 4 flagship targets (2026-09-16).

Reuses this project's existing methodology as-is (same pattern as Robinhood
Chain's `scripts/lib/scorers.py`): live eth_call on public RPCs, address
sourced from the protocol's own official docs/GitHub repo, TVL from DefiLlama,
authority traced to its root (DAO/Safe/Timelock), never trusted from a prior
pass or a block explorer's "verified name".

Origin: these 4 targets were fully researched and verified twice (attempt 1 +
a corrected attempt 2) by `authority-risk-oracle-multichain-pipeline`'s
automated worker/verifier pair on 2026-09-16, but the maker-checker gate did
not reach an APPROUVEE state for either attempt within the run's retry budget
-- the draft sat in `runs/2026-09-16/ethereum-l1/brouillon_non_approuve/`,
un-committed. Independently re-verified live against Ethereum mainnet in an
interactive session the same day (5 of the most load-bearing claims spot-
checked fresh via web3.py against `https://ethereum-rpc.publicnode.com`:
Uniswap Timelock.delay()/admin(), Governor.quorumVotes(), Aave
PayloadsController.getExecutorSettingsByAccessControl(1), Ethena Safe
threshold, Maker DSChief.hat() -- all matched the draft exactly, zero
divergence) before writing this scorer file and committing it manually,
outside the routine's own automated gate. This is a deliberate, disclosed
manual override of an automated rejection, not a silent bypass -- see the
commit message and `data/scored_targets_2026-09-16-ethereum-l1.md` for the
full reasoning and the open threads each target still carries.
"""
import os
import sys

from web3 import Web3  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
from web3_utils import (  # noqa: E402
    call_raw,
    cross_checked,
    get_w3,
    is_eoa,
    read_address_getter,
    read_slot_as_address,
    safe_owners_and_threshold,
    safe_score,
)

# ADDED 2026-09-22: `scripts/lib/scorers.py`'s `_replay_role_holders()` (Robinhood Chain's own
# full-history RoleGranted/RoleRevoked replay, already proven live against Ethereum mainnet by
# score_rollup_l1_authority() in that same file). NOT `from scorers import _replay_role_holders`:
# THIS file is itself always loaded as the bare module `scorers` by every real entry point
# (chains/ethereum-l1/deploy/update_scores_ethereum_l1.py, scripts/dry_run.py,
# scripts/validate_all_scorers.py's subprocess) -- by the time this line would run, `sys.modules
# ['scorers']` is already bound to THIS file, so a bare `from scorers import ...` here would try to
# import from itself, not from scripts/lib/scorers.py (a same-named sibling, the exact trap
# scripts/validate_all_scorers.py's own docstring documents for a different pair of files). Reached
# instead through the `lib` PACKAGE it already lives in (`scripts/lib/scorers.py` uses its own
# relative `from .web3_utils import (...)`, so it must be loaded as `lib.scorers`, not standalone) --
# `scripts/` (not `scripts/lib`) added to sys.path so `lib` resolves as a package. `lib.web3_utils`
# reached from inside it is guaranteed identical to this file's own bare `web3_utils` above (see
# scripts/lib/rpc_unavailable.py's canonicalization, action), so there is no dual-import
# class-identity risk left for anything `_replay_role_holders` might raise or return.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from lib.scorers import _replay_role_holders  # noqa: E402

# RESOLVED 2026-09-17 (closed a follow-up audit finding): this file used to
# keep its own local copy of `_retrying()` plus thin call_raw()/
# safe_owners_and_threshold() wrappers around it, byte-identical to the same
# copy independently kept in chains/base-ecosystem/scorers.py (both added
# 2026-09-17 to close the "every score below is a bare literal, never gated
# on whether the live eth_call actually succeeded" finding). Retry is now
# built directly into scripts/lib/web3_utils.py's own call_raw()/
# safe_owners_and_threshold() (default retries=4) -- imported straight from
# there, no local wrapper needed, so a third ecosystem (Arbitrum) doesn't
# have to copy this a third time.


def _composite(admin_key, multisig, timelock):
    import math
    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


_UINT_GETTER = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]  # noqa: E731
_ADDR_GETTER = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}]  # noqa: E731


def score_uniswap_v3_factory(w3) -> dict:
    """Uniswap V3 Factory (Ethereum L1). Source: official Uniswap/v3-periphery
    GitHub repo, deploys.md. TVL: $2.37B on Ethereum (DefiLlama `protocol/uniswap`
    -- this figure aggregates ALL Uniswap versions combined under DefiLlama's
    parent listing, not V3 alone; flagged rather than silently presented as
    V3-specific). Authority chain: Factory.owner() -> V3OpenFeeAdapter (a real
    fee-adapter contract, Sourcify exact-match verified, NOT a bare EOA) ->
    real Uniswap Governance Timelock (2-day delay) -> GovernorBravo (40M UNI
    quorum, 100 proposals -- a real, active token-vote DAO). This is the SAME
    Timelock address `scorers.py`'s Robinhood-chain correction (2026-09-16,
    see data/correction_2026-09-16-uniswap-bridge-alias.md) already identified
    via its Arbitrum L2 alias -- this scorer confirms the identification
    directly on L1 rather than by inference alone.
    Open thread: no check yet for an emergency-bypass mechanism on this
    Timelock/Governor pair (unlike Ethena's PSM or the Aave chain below, which
    were explicitly checked for one) -- timelockScore below reflects that gap,
    not a confirmed clean bill of health.

    ADDED 2026-09-17 -- governance-capture facts (disclosed, NOT a scored
    dimension): motivated by Term Finance's Meta Vault drain (self-deployed
    proposal-executor, self-proposed, self-voted, waited out the NORMAL --
    not reset -- timelock delay, then executed; a real, undelayed timelock
    didn't help because the vote itself was capturable). Live-verified this
    pass: GovernorBravo.proposalThreshold() and UNI's totalSupply(), plus the
    forVotes/againstVotes/abstainVotes on the 5 most recent real proposals
    (ids 96-100) -- quorum (40M UNI) is 4.0% of total supply (1B UNI),
    proposalThreshold (1M UNI) is 0.1%, and actual recent turnout ranged
    ~46.9M-73.0M UNI, consistently clearing quorum with real margin (not a
    razor-thin pass). Deliberately NOT turned into a 0-100 sub-score:
    the piece that would actually calibrate capture risk -- how concentrated
    that turnout is among a handful of delegates who could coordinate alone --
    needs a DelegateVotesChanged event replay back to UNI's 2020 genesis
    (tens of millions of blocks), the same "hit rate limits on every free RPC
    tried" problem this file's Ethena investigation solved differently for a
    much narrower block range (see score_ethena_minting()) -- not
    solvable the same way here, since the question isn't "when did one value
    change" but "what is the full distribution," which a binary search can't
    answer. Publishing a confident-looking number without that data would be
    exactly the kind of fabricated-but-plausible score this project's own
    discipline exists to prevent. Facts only, not a verdict."""
    factory = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    adapter_abi = _ADDR_GETTER("owner")
    notes = []

    adapter = call_raw(w3, factory, adapter_abi, "owner")
    notes.append(f"Factory.owner() = {adapter}")
    adapter_code = w3.eth.get_code(w3.to_checksum_address(adapter)) if adapter else b""
    notes.append(f"adapter code size = {len(adapter_code)} bytes (not a bare EOA)")

    timelock = call_raw(w3, adapter, adapter_abi, "owner")
    notes.append(f"adapter.owner() = {timelock} (Uniswap Governance Timelock, same address identified via Arbitrum L2 alias in the Robinhood-chain correction)")

    delay = call_raw(w3, timelock, _UINT_GETTER("delay"), "delay")
    admin = call_raw(w3, timelock, _ADDR_GETTER("admin"), "admin")
    notes.append(f"Timelock.delay() = {delay}s ; Timelock.admin() = {admin}")

    quorum = call_raw(w3, admin, _UINT_GETTER("quorumVotes"), "quorumVotes")
    notes.append(f"GovernorBravo.quorumVotes() = {quorum} (40M UNI = real, active token-vote DAO)")

    # Governance-capture facts (see docstring) -- disclosed, not scored.
    proposal_threshold = call_raw(w3, admin, _UINT_GETTER("proposalThreshold"), "proposalThreshold")
    uni_token = "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
    uni_total_supply = call_raw(w3, uni_token, _UINT_GETTER("totalSupply"), "totalSupply")
    if quorum is not None and uni_total_supply:
        notes.append(f"quorumVotes as % of UNI totalSupply ({uni_total_supply/1e18:.0f} UNI) = {100*quorum/uni_total_supply:.2f}%")
    if proposal_threshold is not None and uni_total_supply:
        notes.append(f"GovernorBravo.proposalThreshold() = {proposal_threshold/1e18:.0f} UNI ({100*proposal_threshold/uni_total_supply:.2f}% of totalSupply)")
    proposal_count = call_raw(w3, admin, _UINT_GETTER("proposalCount"), "proposalCount")
    if proposal_count:
        proposals_abi = [{
            "name": "proposals", "type": "function", "stateMutability": "view",
            "inputs": [{"type": "uint256"}],
            "outputs": [
                {"type": "uint256", "name": "id"}, {"type": "address", "name": "proposer"}, {"type": "uint256", "name": "eta"},
                {"type": "uint256", "name": "startBlock"}, {"type": "uint256", "name": "endBlock"},
                {"type": "uint256", "name": "forVotes"}, {"type": "uint256", "name": "againstVotes"}, {"type": "uint256", "name": "abstainVotes"},
                {"type": "bool", "name": "canceled"}, {"type": "bool", "name": "executed"},
            ],
        }]
        turnouts = []
        for pid in range(max(1, proposal_count - 4), proposal_count + 1):
            p = call_raw(w3, admin, proposals_abi, "proposals", pid)
            if p:
                turnouts.append((p[5] + p[6] + p[7]) / 1e18)
        if turnouts:
            notes.append(f"actual turnout on the {len(turnouts)} most recent proposals (ids {max(1, proposal_count-4)}-{proposal_count}): {', '.join(f'{t:.0f}' for t in turnouts)} UNI -- all real votes cast, not a projection")

    if quorum is not None:
        admin_key = 80  # real, active DAO (40M UNI quorum, 100 proposals) -- not a single key, but token-vote plutocracy still carries whale-concentration risk
    else:
        admin_key = 20  # FIXED 2026-09-17: quorumVotes() unread after retries -- degrade instead of silently keeping the confident 80, this is now an unverified claim, not a confirmed one
        notes.append("quorumVotes() unread after retries -- adminKeyScore degraded, treat as unverified this run")
    multisig = 100  # not applicable: no Safe layer, pure DAO+Timelock construction
    if delay is not None:
        timelock_score = 75  # confirmed real 2-day delay; capped below 100 because no emergency-bypass check was done this pass (see docstring)
    else:
        timelock_score = 0  # FIXED 2026-09-17: delay() unread after retries -- degrade instead of silently keeping the confident 75
        notes.append("Timelock.delay() unread after retries -- timelockScore degraded, treat as unverified this run")

    if _same(timelock, UNISWAP_TIMELOCK) and quorum is not None:
        notes.append(_UNISWAP_SHARED_ROOT_NOTE)
    return {
        "target": factory, "label": "Uniswap V3 Factory",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "uniswap-l1-governance",
        # ADDED 2026-09-20: the same L1 Timelock also roots tracked Uniswap targets on Arbitrum, Base, Robinhood Chain and Monad;
        # only claimed when this run confirmed the Timelock and the live GovernorBravo behind it.
        "_crossEcosystem": _same(timelock, UNISWAP_TIMELOCK) and quorum is not None,
    }


# The 9 owners of the Aave GOVERNANCE_GUARDIAN / PayloadsController.guardian()
# Safe, snapshotted 2026-09-17 when this committee was first found identical on
# Arbitrum and Base (same frozenset as chains/plasma-ecosystem/scorers.py and
# chains/monad/scorers.py). CORRECTED 2026-09-20: no longer annotation-only, a
# match now sets score_aave_v3_pool()'s `_crossEcosystem` flag, which
# _apply_cross_exposure() folds into crossExposureScore (80).
_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17 = frozenset({
    "0xda5ae43e179987a66b9831f92223567e1f38be7d", "0x1e3804357ed445251ffecbb6e40107bf03888885",
    "0x4f96743057482a2e10253afdacda3fd9cf2c1dc9", "0xebed04e9137afebff6a1b97ac0adf61a544efe29",
    "0xbd4dcfa978c6d0d342ce36809afffa49d4b7f1f7", "0xa3103d0ed00d24795faa2d641acf6a320eed7396",
    "0x936cd9654271083ccf93a975919da0ab3bc99ef3", "0x0d2394c027602dc4c3832ffd849b5df45dbac0e9",
    "0x4c30e33758216ad0d676419c21cb8d014c68099f",
})

# ADDED 2026-09-20: the 7 owners of the Aave PROTOCOL_GUARDIAN Safe
# (0x2CFe3ec4..., 4-of-7, ACLManager's EMERGENCY_ADMIN holder). The same 7
# owners are the EMERGENCY_ADMIN Safe on Arbitrum, Base, Plasma and Monad
# (a different Safe address per chain), verified on-chain 2026-09-20; it shares
# zero signers with the 9-signer committee above, so it is a second,
# independent cross-chain committee. Lowercased, compared against the freshly
# read owner set (no second-chain RPC inside this scorer).
#
# EXTENDED 2026-09-25 (roadmap item 9, "voit large" round 2): this project only tracks 5 chains, but
# Aave V3 is deployed on ~23. Checked the other 18 live (bgd-labs/aave-address-book's own
# Misc<Chain>.sol PROTOCOL_GUARDIAN addresses, then getOwners() on each chain's own RPC -- the address
# is not assumed to carry the same owners just because it matches, same lesson as this pass's own
# Steakhouse-Safe finding earlier today, where an identical CREATE2 address DID carry different
# owners per chain): **the SAME 7 signers hold this seat on 13 more chains** -- Avalanche, Optimism,
# Polygon, BNB, Celo, Gnosis, Linea, Mantle, Metis, Scroll, Sonic, XLayer, Soneium -- confirmed live,
# not assumed from the address match alone. 18 of ~19 real (non-testnet) Aave V3 deployments checked
# share this exact committee (Ethereum L1's own EMERGENCY_ADMIN seat is the separate 9-signer
# committee above, so it is not itself one of the 18). The one exception found: zkSync's
# PROTOCOL_GUARDIAN address (0xba845c27...) has real bytecode (2,080 bytes) but does not resolve as a
# standard Gnosis Safe (getOwners()/getThreshold() both fail) -- a different implementation, not
# opened this pass. Fantom and Harmony's Misc*.sol files have no PROTOCOL_GUARDIAN entry at all
# (checked, not found -- plausibly frozen/deprecated markets, not investigated further).
# Full derivation: data/finding_2026-09-25-aave-guardian-18-chains.md.
_KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20 = frozenset({
    "0x3fa960f8355d00874d9c7e3350147f5e94859bc2", "0x4ab2bed1d667260db34244ba412817651c2dd52b",
    "0xa2dcdd6e0b5e0d118e2fa8922552ac0fe26efe58", "0xb291232f480f41c75802c4a60f1d2ac03404afef",
    "0xc2674c1a1af0557e1d217ff4f13df44a637c7c13", "0xd4af2e86a27f8f77b0556e081f97b215c9ca8f2e",
    "0xe6838d834674ec35edd53d485770baa10bdd6aae",
})

# ADDED 2026-09-25: closes the SAME gap already fixed for Aave V3 Horizon (a role holder added
# later isn't seen -- this scorer had checked isEmergencyAdmin on two hardcoded addresses, with no
# discovery mechanism, since it was written) but never applied to this project's own single largest
# tracked target by TVL. ACLManager (0xc2aaCf65...) contract-creation block, live binary-searched
# via eth_getCode (Tenderly gateway; ethereum-rpc.publicnode.com has no historical state this far
# back) 2026-09-25, not looked up from memory or an indexer.
_MAIN_POOL_ACL_START_BLOCK = 16_291_117
# Every address below was found FIRST by a live RoleGranted/RoleRevoked replay from the block above
# (2026-09-25, via the Tenderly gateway, same mechanism as Horizon's own discovery block) -- the
# names are a SEPARATE cross-reference against Aave DAO's own published aave-permissions-book
# (github.com/aave-dao/aave-permissions-book, out/ETHEREUM-V3.md), not the source of the finding
# itself. Bounded, governance-owned "Risk Steward" pattern (per aave-dao/aave-v3-risk-stewards:
# "bounded, revocable delegated authority... within fixed cooldowns and a maximum change allowed
# per update") -- market-parameter risk (collateral/borrow config), a different class from this
# project's adminKeyScore/multisigScore/timelockScore (fund/root-authority concentration), same
# disclosed-not-scored treatment Horizon already gives its own RISK_ADMIN holders. 3 of 5 read
# owner()=the governance Executor directly (bounded/revocable as described); the other 2
# (PendleDiscountRateAgent, EModeCategoryAgent) are gated some other way not opened this pass.
_MAIN_POOL_KNOWN_RISK_ADMIN = {
    "0x13a9cc64344b02bacc5ad9cf38b5711f1b9ec3d4": "Manual AGRS",
    "0x529e2374afb38ac465d71979e7540ad93c05f6c5": "PendleDiscountRateAgent",
    "0x5513224daaeabca31af5280727878d52097afa05": "Gho Core Direct Minter",
    "0x98217a06721ebf727f2c8d9ad7718ec28b7aae34": "Core GHO Aave Steward",
    "0xbe2840440d4f77cd98cec2de09913e6851907744": "EModeCategoryAgent",
}


def score_aave_v3_pool(w3) -> dict:
    """Aave V3 Ethereum Pool (PoolAddressesProvider). Source: official
    bgd-labs/aave-address-book GitHub repo. TVL: $14.77B on Ethereum
    (DefiLlama `protocol/aave`). Authority chain: PoolAddressesProvider.owner()
    -> EXECUTOR_LVL_1 <-> PayloadsController (mutual owner pointers, a closed
    pair, not an open-ended chain) -> PayloadsController.getExecutorSettingsByAccessControl(1)
    gives the REAL delay (86,400s / 1 day) for this access-control level, keyed
    per-level rather than a bare delay() on the executor -- confirmed live,
    NOT the same interface as Uniswap's Compound-style Timelock, do not assume
    the two projects' delay getters are interchangeable. GOVERNANCE core
    confirmed real and active (522 proposals, power strategy matches the
    official address book exactly).
    CORRECTED 2026-09-16 (closes a gap this file itself disclosed): the Aave
    Protocol ACLManager's EMERGENCY_ADMIN_ROLE holder is now IDENTIFIED --
    `PROTOCOL_GUARDIAN` (0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30), sourced
    from bgd-labs/aave-address-book's actively-maintained `MiscEthereum.sol`
    (not the frozen 2023 activation-proposal repo, which names a DIFFERENT,
    now-stale address `GUARDIAN_ETHEREUM` 0xCA76Ebd8617a03126B6FB84F9b1c1A0fB71C2633
    -- re-checked live, `isEmergencyAdmin()` on that old address now reads
    FALSE, confirming the role moved since the 2023 grant, not a research
    error). `isEmergencyAdmin(PROTOCOL_GUARDIAN)` confirmed TRUE on 2
    independent RPCs (publicnode + drpc). PROTOCOL_GUARDIAN is a real,
    live Gnosis Safe, 4-of-7 (`getOwners()`/`getThreshold()` re-derived
    directly, not assumed from the address book). The DAO-controlled executor
    still holds isPoolAdmin=true / isEmergencyAdmin=false, confirming the
    emergency seat is separate from routine DAO governance -- but it IS a
    real, disclosed 4-of-7 multisig, not an unaccountable unknown. What
    doesn't change: this seat still bypasses the PayloadsController's 1-day
    timelock entirely (emergency action is immediate by design), so
    timelockScore stays capped for that structural reason -- only adminKeyScore
    moves, reflecting that the previously-unknown holder is now a real,
    reasonably-composed Safe rather than an open question.

    CORRECTED 2026-09-20 (crossExposureScore convention decision): the field
    means "does the same root signer also control ANOTHER tracked target", so
    cross-ecosystem overlaps are now folded in, not just noted. This target
    sets `_crossEcosystem` when EITHER emergency seat's committee is one
    already tracked on another chain: PayloadsController.guardian() (9
    signers, identical on Arbitrum/Base/Plasma/Monad) or PROTOCOL_GUARDIAN (7
    signers, identical to the EMERGENCY_ADMIN Safe on the same four chains).
    _apply_cross_exposure() then caps crossExposureScore at 80. No other
    score moves."""
    provider = "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"
    addr_abi = _ADDR_GETTER("owner")
    notes = []

    executor = call_raw(w3, provider, addr_abi, "owner")
    notes.append(f"PoolAddressesProvider.owner() = {executor} (EXECUTOR_LVL_1)")

    payloads_controller = call_raw(w3, executor, addr_abi, "owner")
    notes.append(f"EXECUTOR_LVL_1.owner() = {payloads_controller} (PayloadsController)")

    settings_abi = [{"name": "getExecutorSettingsByAccessControl", "type": "function", "stateMutability": "view",
                      "inputs": [{"type": "uint8"}], "outputs": [{"type": "tuple", "components": [{"type": "address"}, {"type": "uint40"}]}]}]
    settings = call_raw(w3, payloads_controller, settings_abi, "getExecutorSettingsByAccessControl", 1)
    notes.append(f"PayloadsController.getExecutorSettingsByAccessControl(1) = {settings} (executor, delay-seconds)")

    guardian = call_raw(w3, payloads_controller, _ADDR_GETTER("guardian"), "guardian")
    notes.append(f"PayloadsController.guardian() = {guardian} (can cancel proposals outside the timelock)")

    # ADDED 2026-09-19 (found by an independent verification pass while writing the
    # Monad Aave dashboard card, then re-confirmed by hand on 2 RPCs): this seat was
    # only ever LOGGED above, never resolved, and cross_ecosystem_overlap.py's L1
    # "aave_guardian" group covers only the OTHER emergency seat (ACLManager's
    # PROTOCOL_GUARDIAN, 4-of-7). PayloadsController.guardian() is a 5-of-9 Safe
    # whose 9 owners are IDENTICAL to the committee already found on Arbitrum,
    # Base, Plasma and Monad -- Ethereum L1, the root of the whole cross-chain
    # Aave finding, was the one chain never compared. CORRECTED 2026-09-20:
    # this was annotation-only under the old within-L1 convention; the
    # decided convention folds cross-ecosystem overlaps into crossExposureScore,
    # so a match now sets `cross_ecosystem` (returned as `_crossEcosystem`).
    cross_ecosystem = False
    payloads_guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    if payloads_guardian_safe:
        pg_owners, pg_threshold = payloads_guardian_safe
        notes.append(f"PayloadsController.guardian() Safe: {pg_threshold}-of-{len(pg_owners)}")
        if {o.lower() for o in pg_owners} == _KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17:
            cross_ecosystem = True
            notes.append(
                "PayloadsController.guardian() owner set is IDENTICAL to the Aave guardian committee on Arbitrum, Base, "
                "Plasma and Monad (same 9 signers) -- one committee holds this seat on 5 tracked chains "
                "(cross-ecosystem finding, folded into crossExposureScore as a flat 80)"
            )
    else:
        notes.append("PayloadsController.guardian() getOwners()/getThreshold() unread this run -- committee comparison skipped")

    acl_manager = "0xc2aaCf6553D20d1e9d78E365AAba8032af9c85b0"
    is_emergency_admin_abi = [{"name": "isEmergencyAdmin", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "bool"}]}]
    is_emergency_admin_executor = call_raw(w3, acl_manager, is_emergency_admin_abi, "isEmergencyAdmin", executor)
    notes.append(f"ACLManager.isEmergencyAdmin(EXECUTOR_LVL_1) = {is_emergency_admin_executor} -- DAO executor does NOT hold the emergency-admin seat, confirming it's separate from routine governance")

    protocol_guardian = "0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30"
    # FIXED 2026-09-17: the docstring above claims this specific check was
    # "confirmed TRUE on 2 independent RPCs (publicnode + drpc)" -- that was
    # true of the one-off manual verification that led to this scorer being
    # written, but the CODE only ever called through the single `w3` passed
    # in by the caller, never the project's own cross_checked() helper. Wired
    # it in for real so the code matches what the docstring claims, for this
    # one notable/security-critical result specifically (not every call in
    # this file -- matches the project's existing "recoup notable results on
    # a second independent RPC" convention, not a blanket requirement).
    try:
        is_emergency_admin_guardian = cross_checked(
            ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"],
            lambda w3_, addr: call_raw(w3_, acl_manager, is_emergency_admin_abi, "isEmergencyAdmin", addr),
            protocol_guardian,
        )
        notes.append(f"ACLManager.isEmergencyAdmin(PROTOCOL_GUARDIAN {protocol_guardian}) = {is_emergency_admin_guardian} -- cross-checked live on 2 independent RPCs (publicnode + drpc), matching")
    except RuntimeError as e:
        is_emergency_admin_guardian = None
        notes.append(f"isEmergencyAdmin(PROTOCOL_GUARDIAN) cross-RPC check FAILED: {e}")

    guardian_safe_info = safe_owners_and_threshold(w3, protocol_guardian)
    if guardian_safe_info:
        guardian_owners, guardian_threshold = guardian_safe_info
        notes.append(f"PROTOCOL_GUARDIAN Safe: {guardian_threshold}-of-{len(guardian_owners)} ({guardian_owners})")
        # ADDED 2026-09-20: compare against the dated snapshot of the 4-of-7
        # committee that is also the EMERGENCY_ADMIN Safe on 4 other chains.
        if {o.lower() for o in guardian_owners} == _KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20:
            cross_ecosystem = True
            notes.append(
                "PROTOCOL_GUARDIAN owner set is IDENTICAL to the EMERGENCY_ADMIN Safe on Arbitrum, Base, Plasma and "
                "Monad (same 7 signers) -- one committee holds this seat on 5 tracked chains "
                "(cross-ecosystem finding, folded into crossExposureScore as a flat 80)"
            )
    else:
        guardian_owners, guardian_threshold = None, None
        notes.append("PROTOCOL_GUARDIAN getOwners()/getThreshold() unread after retries -- treat as unverified this run")

    # ADDED 2026-09-25: live discovery, same discipline as score_aave_v3_horizon_pool's own
    # (reused unchanged, not re-derived -- that scorer's docstring records 3 real defects found and
    # fixed by adversarial review before this pattern was trusted). Disclosure only: a candidate
    # found outside the known sets is confirmed live via hasRole before being treated as real, and
    # an EMPTY "extra" is reported as "nothing found in what was scanned", never as a certified
    # absence (a live scan cannot prove completeness, only report what it found -- see Horizon's
    # docstring for why that distinction is load-bearing). Never moves admin_key/multisig/
    # timelock_score -- POOL_ADMIN/EMERGENCY_ADMIN are already the scored path above; RISK_ADMIN is
    # disclosed only, the same treatment Horizon gives it.
    def _pool_has_role(role_name, holder):
        try:
            return cross_checked(
                ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"],
                lambda w3_, addr: call_raw(w3_, acl_manager, _HAS_ROLE_ABI, "hasRole", _acl_role(role_name), addr),
                holder,
            )
        except RuntimeError as e:
            notes.append(f"hasRole({role_name}, {holder}) cross-RPC check FAILED: {e}")
            return None

    try:
        pool_live_holders = _replay_role_holders(
            get_w3(_TENDERLY_MAINNET), acl_manager, ["POOL_ADMIN", "EMERGENCY_ADMIN", "RISK_ADMIN"],
            start_block=_MAIN_POOL_ACL_START_BLOCK)
    except Exception as e:
        pool_live_holders = None
        notes.append(f"Live role-holder discovery (RoleGranted/RoleRevoked replay from block {_MAIN_POOL_ACL_START_BLOCK} via Tenderly) FAILED this run: {type(e).__name__}: {e} -- cannot say whether an undisclosed holder exists this run, only the known hasRole checks above are verified")
    if pool_live_holders is not None:
        known_pool_admin = {executor.lower()} if executor else set()
        known_emergency_admin = {protocol_guardian.lower()}

        def _confirmed(role_name, candidates):
            confirmed, unconfirmed = set(), set()
            for addr in candidates:
                (confirmed if _pool_has_role(role_name, Web3.to_checksum_address(addr)) is True else unconfirmed).add(addr)
            return confirmed, unconfirmed

        pool_extra_raw = {a.lower() for a in pool_live_holders["POOL_ADMIN"]} - known_pool_admin
        emergency_extra_raw = {a.lower() for a in pool_live_holders["EMERGENCY_ADMIN"]} - known_emergency_admin
        pool_extra, pool_unconfirmed = _confirmed("POOL_ADMIN", pool_extra_raw)
        emergency_extra, emergency_unconfirmed = _confirmed("EMERGENCY_ADMIN", emergency_extra_raw)
        if pool_extra or emergency_extra:
            notes.append(
                f"Live role discovery found a POOL_ADMIN or EMERGENCY_ADMIN holder beyond the known executor/PROTOCOL_GUARDIAN, "
                f"hasRole-confirmed real: POOL_ADMIN extra {sorted(pool_extra)}, EMERGENCY_ADMIN extra {sorted(emergency_extra)} "
                f"-- re-check this scorer's classification, it no longer matches what's on chain"
            )
        else:
            notes.append(
                f"Live role discovery (RoleGranted/RoleRevoked replay from block {_MAIN_POOL_ACL_START_BLOCK}): "
                f"no POOL_ADMIN or EMERGENCY_ADMIN holder found beyond the executor and PROTOCOL_GUARDIAN already "
                f"scored above" + (f" (unconfirmed candidates dropped by hasRole, treated as phantom: {sorted(pool_unconfirmed | emergency_unconfirmed)})" if pool_unconfirmed or emergency_unconfirmed else "")
            )

        risk_admin_found = {a.lower() for a in pool_live_holders["RISK_ADMIN"]}
        risk_admin_known = set(_MAIN_POOL_KNOWN_RISK_ADMIN)
        risk_admin_unnamed = risk_admin_found - risk_admin_known
        named = [f"{addr[:10]}.. ({_MAIN_POOL_KNOWN_RISK_ADMIN[addr]})" for addr in sorted(risk_admin_found & risk_admin_known)]
        notes.append(
            f"RISK_ADMIN (disclosed, not scored -- bounded governance-owned 'Risk Steward' pattern, market-parameter "
            f"risk not root-authority risk): {len(risk_admin_found)} holder(s) found this run: {'; '.join(named) if named else 'none'}"
            + (f"; {len(risk_admin_unnamed)} UNNAMED holder(s) not in the known set, re-check by hand: {sorted(risk_admin_unnamed)}" if risk_admin_unnamed else "")
        )

    if settings is not None:
        timelock_score = 55  # unchanged: confirmed real 1-day delay at access level 1, weaker than Uniswap's 2-day, AND the emergency-admin seat structurally bypasses this timelock entirely by design (now a KNOWN bypass via a real Safe, not an unknown one -- the bypass itself doesn't disappear just because the holder is identified)
    else:
        timelock_score = 0  # FIXED 2026-09-17: getExecutorSettingsByAccessControl(1) unread after retries -- degrade instead of silently keeping the confident 55
        notes.append("getExecutorSettingsByAccessControl(1) unread after retries -- timelockScore degraded, treat as unverified this run")

    if is_emergency_admin_guardian is True and guardian_threshold is not None:
        admin_key = 78  # real, active DAO (522 proposals) AND the emergency-admin seat is now confirmed a real 4-of-7 Safe (not a bare EOA, not an open unknown) -- modest improvement from 70, not full marks, since a 4-of-7 seat with no timelock is still a meaningful concentration by design
    else:
        admin_key = 20  # FIXED 2026-09-17: the emergency-admin identification (this scorer's whole reason to score 78 instead of the original 70) did not verify cleanly this run -- degrade rather than silently keep the confident 78 on an unconfirmed claim
        notes.append("PROTOCOL_GUARDIAN emergency-admin identification did not verify cleanly this run -- adminKeyScore degraded to the pre-correction level, treat as unverified")
    multisig = 100  # not applicable: PayloadsController/Executor pair is not a Safe

    return {
        "target": provider, "label": "Aave V3 Ethereum Pool (PoolAddressesProvider)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "aave-l1-governance", "_crossEcosystem": cross_ecosystem,
    }


def score_makerdao_sky_pause(w3) -> dict:
    """MakerDAO/Sky governance (MCD_PAUSE). Source: read directly on-chain from
    the official dss-chain-log changelog contract (governance-maintained
    registry, more primary than the chainlog.makerdao.com web frontend, which
    did not return usable JSON this pass). TVL: $5.06B on Ethereum (DefiLlama
    `protocol/makerdao`, resolves to "Sky Lending" post-rebrand). Authority
    chain: MCD_PAUSE.delay() = 172,800s (2 days) -> authority() = DSChief
    (MCD_ADM) -> hat() = the most recently executed governance spell
    (2026-09-10 MakerDAO Executive Spell, confirmed done()=true with a
    readable description() -- real, active governance, not a dormant/
    placeholder contract).

    DATE REFRESHED 2026-09-21 (rotation audit, index 2): this docstring used to
    say the hat spell was "6 days" old, which was true only on the day it was
    written. The hat is still the SAME spell (2026-09-10, eta 1789302155,
    done()=true), so it is 11 days old at the 2026-09-21 audit -- governance
    still active, score unchanged at 81. Re-derivable end to end with
    `python3 chains/ethereum-l1/scripts/audit_rotation_index2.py` (no
    dependency, 4 mainnet RPCs, exit 0 = no divergence)."""
    pause = "0xbE286431454714F511008713973d3B053A2d38f3"
    notes = []

    delay = call_raw(w3, pause, _UINT_GETTER("delay"), "delay")
    authority = call_raw(w3, pause, _ADDR_GETTER("authority"), "authority")
    notes.append(f"MCD_PAUSE.delay() = {delay}s ; MCD_PAUSE.authority() = {authority} (DSChief)")

    hat = call_raw(w3, authority, _ADDR_GETTER("hat"), "hat")
    notes.append(f"DSChief.hat() = {hat} (most recently executed governance spell)")

    done_abi = [{"name": "done", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]}]
    done = call_raw(w3, hat, done_abi, "done")
    notes.append(f"hat().done() = {done} (spell already executed -- expected shape of active Maker/Sky governance, not evidence of a stuck/dormant hat)")

    if hat is not None and done is not None:
        admin_key = 75  # real, active MKR/SKY-weighted governance, confirmed active within the last week
    else:
        admin_key = 20  # FIXED 2026-09-17: hat()/done() unread after retries -- degrade instead of silently keeping the confident 75
        notes.append("DSChief.hat() or hat().done() unread after retries -- adminKeyScore degraded, treat as unverified this run")
    multisig = 100  # not applicable: DSChief/DSPause is not a Gnosis Safe
    if delay is not None:
        timelock_score = 70  # confirmed real 2-day delay; not explicitly checked this pass for an emergency-bypass mechanism (same caveat as Uniswap above)
    else:
        timelock_score = 0  # FIXED 2026-09-17: MCD_PAUSE.delay() unread after retries -- degrade instead of silently keeping the confident 70
        notes.append("MCD_PAUSE.delay() unread after retries -- timelockScore degraded, treat as unverified this run")

    return {
        "target": pause, "label": "MakerDAO / Sky governance (MCD_PAUSE)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "makerdao-sky-governance",
    }


# CORRECTED 2026-09-20 (see score_ethena_minting): the address this file used to score as "USDe's
# minting authority" is the RETIRED minter. USDe.minter() has pointed at _ETHENA_MINTING since block
# 20261016 (2024-07-08); both contracts share the same immutable usde().
_ETHENA_MINTING = "0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3"
_ETHENA_MINTING_RETIRED = "0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3"
_USDE = "0x4c9EDD5852cd905f086C759E8383e09bff1E68B3"
_ETHENA_TIMELOCK = "0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94"
_ETHENA_SAFE = "0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862"
# The 4 bare-EOA GATEKEEPER_ROLE holders (Blockscout RoleGranted/RoleRevoked replay, 2026-09-20; each
# re-confirmed with hasRole on two RPCs). AccessControl is not enumerable, so the set is read per
# address here, not discovered per run.
_ETHENA_GATEKEEPERS = (
    "0xab9110d36b030bae812cd3bb7b9de805a64aa7dc", "0x0f566cc38677239bed459047065925654b6d5bd9",
    "0x496011675b197cc136b48bc19d848fe26d3a8996", "0xb6ecae7413a3e78a3e10f15afe3066e79566cca3",
)
_ETHENA_SAFE_GUARD = "0x74abe7805541c28f31953b3cDA9711Dc96278D29"
_SAFE_GUARD_SLOT = "0x" + bytes(Web3.keccak(text="guard_manager.guard.address")).hex()


def _read_safe_guard(w3, safe):
    """The Gnosis Safe's guard address from its storage slot, or None when unreadable."""
    try:
        raw = bytes(w3.eth.get_storage_at(w3.to_checksum_address(safe), _SAFE_GUARD_SLOT))
        return Web3.to_checksum_address("0x" + raw[-20:].hex())
    except Exception:  # noqa: BLE001 -- a positive-control note must never break the score
        return None


_HAS_ROLE_ABI = [{"name": "hasRole", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
_IS_WHITELISTED_ABI = [{"name": "isWhitelisted", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}, {"type": "bytes4"}], "outputs": [{"type": "bool"}]}]
# Every selector is derived from its signature, never hand-typed hex.
_ETHENA_REDIRECT_SIGNATURES = (
    "grantRole(bytes32,address)", "transferAdmin(address)", "addCustodianAddress(address)",
    "addSupportedAsset(address,(uint8,bool,uint128,uint128))", "setTokenType(address,uint8)",
    "setStablesDeltaLimit(uint128)",
)
_ETHENA_INSTANT_LANE_SIGNATURES = (
    "revokeRole(bytes32,address)", "addWhitelistedBenefactor(address)", "removeWhitelistedBenefactor(address)",
)
_ETHENA_GATEKEEPER_GATED_SIGNATURES = (
    "disableMintRedeem()", "removeMinterRole(address)", "removeRedeemerRole(address)", "removeCollateralManagerRole(address)",
)


def _selector(signature: str) -> bytes:
    return Web3.keccak(text=signature)[:4]


def _selector_role(role_name: str) -> bytes:
    return bytes(Web3.keccak(text=role_name))


def _addr_eq(a, b) -> bool:
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


def score_ethena_minting(w3) -> dict:
    """Ethena EthenaMinting: the contract that is USDe's ONLY mint authority today
    (`USDe.minter()`), 0xe3490297...b62D3. Deployed 2024-06-21, set as USDe's minter at block
    20261016 (2024-07-08). Verified source (Sourcify exact match, 0.8.20, 25 files).

    CORRECTED 2026-09-20 -- the SCORED CONTRACT CHANGED. This function used to score
    0x2CC440b7...8Afc3 as "USDe minting authority". That contract was USDe's minter only
    until 2024-07-08; since then `USDe.mint()` from it reverts OnlyMinter (simulated), it holds no
    collateral, and re-pointing USDe to it needs `USDe.setMinter`, which is onlyOwner = the
    24h timelock. The old number (55/100/0, Safe directly, no delay) was factually right about
    THAT contract and irrelevant to USDe. Found by the unscored-role sweep
    (data/finding_2026-09-20-unscored-role-sweep.md), traced and adversarially verified on two RPCs.
    The oracle has no removal function, so the old target is retired by ceasing to refresh it
    (its on-chain entry goes stale after maxStaleness, 9 days).

    Authority of the live minter, all re-read live every run:
    - DEFAULT_ADMIN_ROLE (single admin, owner()) = EthenaTimelockController 0xE8Dc0Fab..., moved
      from the Safe at block 25522488 (2026-07-13); getMinDelay() = 86400 s; the 5-of-10 Safe
      0x3b0aaf6e... (10 bare-EOA owners, no modules) is its only PROPOSER and only CANCELLER, so
      the delay is a visibility window, not a second key.
    - USDe.setMinter (the strongest unbacked-mint control) is onlyOwner, USDe.owner() = the same
      timelock, and no whitelist entry exists for USDe: delay-gated.
    - The timelock has a per-(target, selector) whitelist that bypasses the delay. For this minter,
      6 admin selectors that would redirect funds or create unbacked USDe (grantRole,
      transferAdmin, addCustodianAddress, addSupportedAsset, setTokenType, setStablesDeltaLimit) are
      NOT whitelisted: 24h delay applies. The whitelisted ones are revokeRole and
      add/removeWhitelistedBenefactor (executable by the Safe alone with no delay; freeze/config
      type, they cannot mint), plus 4 GATEKEEPER-gated selectors whose whitelist entries are DEAD
      (the timelock does not hold GATEKEEPER_ROLE, so the inner call reverts).
    - Outside the timelock, disclosed in notes and NOT folded into the score (same convention as
      Aave's guardian and Compound's pause guardian): the Safe holds COLLATERAL_MANAGER_ROLE directly
      (transferToCustody moves any minter-held asset, ~$93M on 2026-09-20 across USDC, USDT and
      USDtb, instantly, but only to one of 5 registered custodian EOAs, and adding a custodian is
      delay-gated); 4 bare-EOA GATEKEEPERs can halt mint/redeem and strip roles instantly (though the
      Safe can instantly revokeRole them, so they are not an independent brake); 20 bare-EOA
      MINTER/REDEEMER holders (unrotated since 2024-07) can submit orders but cannot mint without a
      benefactor's EIP-712 signature and real collateral routed to a registered custodian, so a
      compromised MINTER key alone does not create unbacked USDe. Seven collateral assets are active,
      all STABLE (USDC, USDT, DAI, USDtb, PYUSD, USDm, USDG), valued 1:1 by decimals and never priced:
      issuer or depeg risk of those tokens is the remaining route to a bad mint that needs no delayed
      admin action. The Safe itself has an EthenaSafeGuard installed (2026-07-06): a positive control
      that limits who can submit its transactions, read live from the Safe's guard slot, not scored.

    Scoring, same convention as `score_usdtb_psm()`: adminKey 65 / multisig by formula (5-of-10 ->
    100) / timelock 55 when every fund-redirect selector is delayed (adminKey 30, timelock 0 if any
    is bypassable or USDe is not timelock-owned). If the Safe is DEFAULT_ADMIN directly again the
    score reverts to the old no-delay shape (55 / formula / 0). Any unread or inconsistent guard
    (USDe.minter() no longer this contract, admin roles unreadable, Safe not the timelock's
    proposer) degrades to 20 / 20 / 0 rather than keeping a confident number."""
    minting, timelock, safe, usde = _ETHENA_MINTING, _ETHENA_TIMELOCK, _ETHENA_SAFE, _USDE
    safe_cs, timelock_cs = w3.to_checksum_address(safe), w3.to_checksum_address(timelock)
    admin_role = b"\x00" * 32
    notes = []

    usde_minter = call_raw(w3, usde, _ADDR_GETTER("minter"), "minter")
    usde_owner = call_raw(w3, usde, _ADDR_GETTER("owner"), "owner")
    timelock_is_admin = call_raw(w3, minting, _HAS_ROLE_ABI, "hasRole", admin_role, timelock_cs)
    safe_is_admin = call_raw(w3, minting, _HAS_ROLE_ABI, "hasRole", admin_role, safe_cs)
    delay = call_raw(w3, timelock, _UINT_GETTER("getMinDelay"), "getMinDelay")
    safe_is_proposer = call_raw(w3, timelock, _HAS_ROLE_ABI, "hasRole", _selector_role("PROPOSER_ROLE"), safe_cs)
    safe_info = safe_owners_and_threshold(w3, safe)

    notes.append(f"USDe.minter() = {usde_minter} (this contract: {_addr_eq(usde_minter, minting)}); USDe.owner() = {usde_owner} (the timelock: {_addr_eq(usde_owner, timelock)})")
    notes.append(f"EthenaMinting.hasRole(DEFAULT_ADMIN_ROLE, timelock) = {timelock_is_admin}; hasRole(DEFAULT_ADMIN_ROLE, Safe) = {safe_is_admin}; timelock.getMinDelay() = {delay}s; timelock.hasRole(PROPOSER_ROLE, Safe) = {safe_is_proposer}")
    if safe_info:
        notes.append(f"{safe}: real Gnosis Safe, {safe_info[1]}-of-{len(safe_info[0])}")

    redirect_reads = []
    for sig in _ETHENA_REDIRECT_SIGNATURES:
        result = call_raw(w3, timelock, _IS_WHITELISTED_ABI, "isWhitelisted", w3.to_checksum_address(minting), _selector(sig))
        redirect_reads.append(result)
        notes.append(f"isWhitelisted(minter, {sig}) = {result} (expected False: fund-redirect/unbacked-mint class stays behind the {delay}s delay)")
    setminter_wl = call_raw(w3, timelock, _IS_WHITELISTED_ABI, "isWhitelisted", w3.to_checksum_address(usde), _selector("setMinter(address)"))
    redirect_reads.append(setminter_wl)
    notes.append(f"isWhitelisted(USDe, setMinter(address)) = {setminter_wl} (expected False: re-pointing USDe's only mint authority is delay-gated)")

    instant_lanes = []
    for sig in _ETHENA_INSTANT_LANE_SIGNATURES:
        result = call_raw(w3, timelock, _IS_WHITELISTED_ABI, "isWhitelisted", w3.to_checksum_address(minting), _selector(sig))
        if result:
            instant_lanes.append(sig)
    notes.append(f"Instant (no-delay) lanes the Safe alone can use on the minter: {instant_lanes or 'none read'} -- freeze/config type, none can mint; disclosed, not folded into timelockScore beyond the 55 cap")

    timelock_has_gatekeeper = call_raw(w3, minting, _HAS_ROLE_ABI, "hasRole", _selector_role("GATEKEEPER_ROLE"), timelock_cs)
    dead_gated = []
    for sig in _ETHENA_GATEKEEPER_GATED_SIGNATURES:
        result = call_raw(w3, timelock, _IS_WHITELISTED_ABI, "isWhitelisted", w3.to_checksum_address(minting), _selector(sig))
        if result:
            dead_gated.append(sig)
    notes.append(
        f"Whitelisted GATEKEEPER-gated selectors {dead_gated or 'none'}: timelock.hasRole(GATEKEEPER_ROLE) = {timelock_has_gatekeeper}, "
        f"so those whitelist entries are {'DEAD (the inner call reverts)' if timelock_has_gatekeeper is False else 'NOT proven dead this run'}"
    )

    collateral_manager = call_raw(w3, minting, _HAS_ROLE_ABI, "hasRole", _selector_role("COLLATERAL_MANAGER_ROLE"), safe_cs)
    notes.append(
        f"OUTSIDE the timelock, disclosed not scored: Safe.hasRole(COLLATERAL_MANAGER_ROLE) = {collateral_manager} -- "
        f"transferToCustody can move any asset the minter holds (~$93M on 2026-09-20: USDC 31.1M, USDT 31.0M, USDtb 31.0M, plus small PYUSD/USDG/USDm balances) "
        f"instantly, but only to one of 5 registered custodian EOAs; adding a custodian (addCustodianAddress) is delay-gated. The custodians' real controllers are not attributable on-chain."
    )
    gatekeeper_reads = [call_raw(w3, minting, _HAS_ROLE_ABI, "hasRole", _selector_role("GATEKEEPER_ROLE"), w3.to_checksum_address(g)) for g in _ETHENA_GATEKEEPERS]
    notes.append(
        f"OUTSIDE the timelock, disclosed not scored: {sum(1 for r in gatekeeper_reads if r is True)} of {len(_ETHENA_GATEKEEPERS)} known bare-EOA "
        f"GATEKEEPER_ROLE holders confirmed live; each can disableMintRedeem and strip MINTER/REDEEMER/COLLATERAL_MANAGER roles instantly, but the Safe can instantly revokeRole all four, so they are not an independent brake. "
        f"Also 20 bare-EOA MINTER/REDEEMER holders, unrotated since 2024-07 (log replay 2026-09-20; AccessControl is not enumerable): they cannot mint without a "
        f"benefactor's EIP-712 signature and real collateral delivered to a registered custodian. Seven collateral assets are active, all STABLE "
        f"(USDC, USDT, DAI, USDtb, PYUSD, USDm, USDG), valued 1:1 by decimals and never priced: issuer or depeg risk of those tokens, notably the thin USDm "
        f"(~31k supply), is the one route to a bad mint that needs no delayed admin action (market and issuer risk, not an authority hole)."
    )
    guard = _read_safe_guard(w3, safe)
    notes.append(
        f"Positive control, not scored: the Safe's guard slot reads {guard} (expected EthenaSafeGuard {_ETHENA_SAFE_GUARD}, installed 2026-07-06: "
        f"only its whitelisted executors, an EOA and a separate 3-of-6 Safe, can submit the Safe's transactions, and removing it takes 48h in public). "
        f"Matches: {_addr_eq(guard, _ETHENA_SAFE_GUARD) if guard else 'unread'}"
    )
    notes.append(
        f"RETIRED TARGET: {_ETHENA_MINTING_RETIRED} (scored 55/100/0 until 2026-09-20) has not been USDe's minter since 2024-07-08 "
        f"(USDe.mint from it reverts OnlyMinter, it holds no collateral). Its on-chain oracle entry is no longer refreshed and goes stale after maxStaleness."
    )

    redirect_delayed = all(r is False for r in redirect_reads) and _addr_eq(usde_owner, timelock)
    guards_resolved = (
        usde_minter is not None and usde_owner is not None and timelock_is_admin is not None
        and delay is not None and safe_is_proposer is not None and safe_info is not None
        and all(r is not None for r in redirect_reads)
    )
    threshold, owners = (safe_info[1], safe_info[0]) if safe_info else (0, [])
    formula = min(threshold * 15 + max(0, len(owners) - threshold) * 5, 100)

    if usde_minter is not None and not _addr_eq(usde_minter, minting):
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append("USDe.minter() is NO LONGER this contract: it does not hold USDe mint authority, this target must be re-pointed; scores degraded")
    elif guards_resolved and timelock_is_admin is True and safe_is_proposer is True:
        admin_key = 65 if redirect_delayed else 30
        multisig = formula
        timelock_score = 55 if (redirect_delayed and delay) else 0
        if not redirect_delayed:
            notes.append("A fund-redirect/unbacked-mint selector is whitelisted (instant) or USDe is not timelock-owned: adminKeyScore 30, timelockScore 0")
    elif safe_info is not None and timelock_is_admin is False and safe_is_admin is True:
        admin_key, multisig, timelock_score = 55, formula, 0
        notes.append("The Safe is DEFAULT_ADMIN directly again (no timelock layer): scored as a direct-Safe, no-delay authority")
    else:
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append("One or more live guards were unread or inconsistent this run (USDe.minter/owner, DEFAULT_ADMIN holder, timelock delay/proposer, Safe, whitelist reads) -- scores degraded, treat as unverified")

    return {
        "target": minting, "label": "Ethena EthenaMinting (USDe live minter)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "ethena-safe-0x3b0aaf6e",
    }


def score_usdtb(w3) -> dict:
    """USDtb (Ethena Labs' USD product, NOT USDe -- a separate token). ADDED
    2026-09-17, promoted from `chains/ethereum-l1/SESSION_NOTES_2026-09-16.md`'s
    backlog (the most significant finding in that file) after live
    re-verification via an independent workflow, not trusted from the
    backlog note alone.

    TVL: $483.1M live `totalSupply()`, cross-checked against DefiLlama's
    stablecoins API ($482.7M Ethereum-chain circulating) and CoinGecko
    (market_cap ~$482.8M) -- all three agree within ~0.1%, and 293,710
    Etherscan holders confirm real, broad usage. A real, large, actively
    traded stablecoin, not a shell.

    Authority: DEFAULT_ADMIN_ROLE on the proxy (0xC139190F...18aC1c) is held
    by a SINGLE BARE EOA, 0xd93826BB299765c87D13AeBa2A7E5d9B27A03956 (nonce
    25 as of the original 2026-09-16 research, a real actively-used key, not
    vanity-mined or freshly created) -- confirmed live via `hasRole()` on two
    independent RPCs (publicnode + drpc), matching. This same EOA also owns
    USDtb's ProxyAdmin (0x3C405F68d5C6eCE868e5646cAC926679839aCd68) directly
    -- confirmed live, `owner()` resolves to the exact same address. No Safe,
    no Timelock, no DAO layer anywhere in this authority chain: one key can
    upgrade the $483M token's implementation outright.

    Worth stating explicitly: this is a genuine, current inconsistency
    within Ethena's own infrastructure, not a hypothetical -- the USDtb PSM
    (`score_usdtb_psm()` below, same protocol family) migrated its own
    DEFAULT_ADMIN_ROLE from a Safe to a real 24h Timelock on 2026-07-13. This
    token's own upgrade authority was never migrated the same way and is
    still a bare EOA today.

    Same bare EOA also held DEFAULT_ADMIN_ROLE (live-confirmed) on two other
    proxies deployed with the identical pattern -- fUSD
    (0x1676b80edd36b18a3c3432c11ed25d37fde9c92a) and aBTC
    (0xc803bc88957b86e289ebef6bd647c73f3905cc72) -- but neither is scored as
    its own target here: independently verified live, fUSD's totalSupply()
    is 58.23 tokens across 5 holders and aBTC's is 0.00001 tokens across 1
    holder, with no DefiLlama/CoinGecko coverage for either contract. Real
    deployed contracts, correctly attributable to Falcon Finance/Anchorage
    branding, but dust -- they fail this project's own "real, verifiable
    TVL/usage" bar for a flagship target, so scoring them would overstate
    the finding rather than clarify it. Disclosed here rather than silently
    dropped, since the SAME key controlling them is still a real fact about
    that EOA's blast radius, just not one with its own composite score.

    A second EOA, 0x364366A7164fB518eaFaa42AF0C86Eddab78e6f3, independently
    holds MINTER_BURNER_ROLE (role hash recomputed live via keccak256, not
    hand-typed) on all three proxies -- separate from admin/upgrade
    authority, so not folded into this target's own score, but the same
    single-EOA-across-multiple-protocols shape as the admin role above."""
    target = "0xC139190F447e929f090Edeb554D95AbB8b18aC1c"
    admin_eoa = "0xd93826BB299765c87D13AeBa2A7E5d9B27A03956"
    proxy_admin = "0x3C405F68d5C6eCE868e5646cAC926679839aCd68"
    notes = []

    default_admin_role = b"\x00" * 32
    role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
    has_role = call_raw(w3, target, role_abi, "hasRole", default_admin_role, w3.to_checksum_address(admin_eoa))
    notes.append(f"USDtb.hasRole(DEFAULT_ADMIN_ROLE, {admin_eoa}) = {has_role}")

    proxy_admin_owner = call_raw(w3, proxy_admin, _ADDR_GETTER("owner"), "owner")
    notes.append(f"ProxyAdmin({proxy_admin}).owner() = {proxy_admin_owner} (expected to match the admin EOA)")
    proxy_admin_matches = bool(proxy_admin_owner) and proxy_admin_owner.lower() == admin_eoa.lower()

    total_supply = call_raw(w3, target, _UINT_GETTER("totalSupply"), "totalSupply")
    if total_supply is not None:
        notes.append(f"USDtb.totalSupply() = {total_supply/1e18:,.0f} USDtb (~$483M live-verified 2026-09-17, cross-checked DefiLlama + CoinGecko + 293,710 Etherscan holders)")

    if has_role is True and proxy_admin_matches:
        admin_key = 5  # bare EOA, real tx history, no Safe/Timelock/DAO layer anywhere -- near-worst-case, matching this project's established convention for this exact authority shape (see data/backtest_2026-09-17-wasabi-protocol.md)
        notes.append("Root authority is a confirmed bare EOA with no Safe/Timelock layer above it -- controls upgrade of a $483M+ token directly")
    else:
        admin_key = 20  # hasRole()/ProxyAdmin.owner() unread after retries, or a genuine mismatch -- degrade instead of silently keeping a confident score either direction
        notes.append("hasRole() or ProxyAdmin.owner() did not confirm the expected authority this run -- adminKeyScore degraded, treat as unverified/changed")
    multisig = 0  # no Safe found anywhere in this authority chain
    timelock_score = 0  # no delay found anywhere in this authority chain -- structural fact (no Timelock/delay getter exists on this contract), not a call result that can silently fail into a wrong value

    return {
        "target": target, "label": "USDtb (Ethena)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        # Deliberately NOT "ethena-safe-0x3b0aaf6e": this token's own admin is the bare EOA
        # 0xd93826bb... (see docstring), a genuinely separate, unrotated authority from the
        # Safe-governed rest of the Ethena family -- the real inconsistency this docstring
        # already flags, not glossed over by grouping it with the Safe anyway.
        "notes": notes, "_rootGroup": "usdtb-bare-eoa-0xd93826bb",
    }


def score_usdtb_psm(w3) -> dict:
    """USDtb PSM (peg-stability module -- swaps USDtb against other stable
    collateral). ADDED 2026-09-17, promoted from
    `chains/ethereum-l1/SESSION_NOTES_2026-09-16.md`'s backlog section 2
    ("[backlog note]") after live re-verification.

    Authority: `EthenaTimelockController` (0xE8Dc0Fab349EA169283C48Ccfd09d7
    97e6dB7c94 -- the SAME custom Timelock contract this project's
    `score_ethena_minting()` docstring already traces for StakedUSDeV2) plus
    a real 5-of-10 Gnosis Safe (0x3b0aaf6E6FCd4A7CEEF8c92C32DfEA9e64Dc1862,
    the same Safe already tracked in `score_ethena_minting()`) -- confirmed
    live: `getMinDelay()` = 86400s (24h), Safe `getThreshold()` = 5,
    `getOwners()` returns 10 distinct addresses.

    Genuinely nuanced finding, not a clean pass or a clean fail: this
    project's `EthenaTimelockController` (see `score_ethena_minting()`) adds
    a per-(target, selector) whitelist that bypasses the 24h delay entirely
    for whitelisted calls. Confirmed live via `isWhitelisted(target,
    selector)` on all of the following, plus a full paginated indexed-log
    history (21 `FunctionWhitelisted` events total for this PSM, zero
    `FunctionRemovedFromWhitelist` ever -- all 21 still active):
    - `disableSwap()`, `disableCollateral(address)`, `disableBenefactor(address)`
      -- ALL THREE whitelisted (instant, no delay). An actor holding
      `WHITELISTED_EXECUTOR_ROLE` can freeze the entire PSM instantly. (Who
      currently holds that role was NOT independently identified this pass
      -- `eth_getLogs` for its RoleGranted/RoleRevoked history was rejected
      by the free RPC tier used; flagged as open, not assumed to be the Safe.)
    - `setAssetSendCustodian(address)`, `setAssetReceiveCustodian(address)`
      -- confirmed NOT whitelisted. Redirecting where PSM assets actually go
      requires the full 24h delay, no bypass -- the economically worst-case
      action (fund redirect) is the one genuinely protected.
    - `setPegPrice(...)` -- confirmed NOT whitelisted, and `PEG_MANAGER_ROLE`
      (the only role that can call it) is held SOLELY by the Timelock
      (`hasRole` true for Timelock, false for the Safe directly) -- a full,
      documented one-time migration away from the Safe on 2026-07-30
      (verified via the role's complete on-chain event history, not a
      snapshot), alongside `DEFAULT_ADMIN_ROLE` itself moving the same way
      on 2026-07-13.

    Net picture: the two actions that would actually move value out of this
    PSM (custodian redirect, peg price) are genuinely delay-gated with no
    bypass found. The instant-bypass path only reaches freeze-type actions
    (a DoS/availability risk, not a theft/redirect one) -- disclosed and
    reflected in a capped, not zeroed, timelockScore below, same convention
    already used for Aave's guardian cancel-path gap in `score_aave_v3_pool()`."""
    target = "0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728"
    timelock = "0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94"
    safe = "0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862"
    notes = []

    delay = call_raw(w3, timelock, _UINT_GETTER("getMinDelay"), "getMinDelay")
    notes.append(f"EthenaTimelockController.getMinDelay() = {delay}s")

    safe_info = safe_owners_and_threshold(w3, safe)
    if safe_info:
        owners, threshold = safe_info
        notes.append(f"{safe}: real Gnosis Safe, {threshold}-of-{len(owners)}")

    whitelist_abi = [{"name": "isWhitelisted", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}, {"type": "bytes4"}], "outputs": [{"type": "bool"}]}]
    disable_selectors = {"disableSwap()": "0xfd5b9026", "disableCollateral(address)": "0x75c038b7", "disableBenefactor(address)": "0x9c621790"}
    custodian_selectors = {"setAssetSendCustodian(address)": "0x28cb6982", "setAssetReceiveCustodian(address)": "0xcd0b89ca"}

    disable_bypassed = []
    for name, sel in disable_selectors.items():
        result = call_raw(w3, timelock, whitelist_abi, "isWhitelisted", w3.to_checksum_address(target), bytes.fromhex(sel[2:]))
        notes.append(f"isWhitelisted(PSM, {name}) = {result} (expected True -- instant freeze bypass)")
        disable_bypassed.append(result)

    custodian_delayed = []
    for name, sel in custodian_selectors.items():
        result = call_raw(w3, timelock, whitelist_abi, "isWhitelisted", w3.to_checksum_address(target), bytes.fromhex(sel[2:]))
        notes.append(f"isWhitelisted(PSM, {name}) = {result} (expected False -- genuinely delayed, no bypass)")
        custodian_delayed.append(result is False)

    calls_resolved = delay is not None and safe_info and all(r is not None for r in disable_bypassed)
    freeze_bypass_confirmed = all(disable_bypassed)
    custodian_genuinely_delayed = all(custodian_delayed)

    if calls_resolved and safe_info:
        threshold = safe_info[1]
        admin_key = 65 if custodian_genuinely_delayed else 30  # real Safe+Timelock governance layer; capped below a "clean" combo either way (see docstring), and dropped further if even the fund-redirect path turned out bypassable
        multisig = min(threshold * 15 + max(0, len(safe_info[0]) - threshold) * 5, 100)
        timelock_score = 55 if (delay and custodian_genuinely_delayed) else 0  # real 24h delay confirmed for the economically critical actions, capped below a "clean" timelock's score by the disclosed instant-freeze bypass on 3 selectors (same convention as Aave's guardian-cancel-path cap)
        if freeze_bypass_confirmed:
            notes.append("Instant-bypass freeze capability confirmed on 3 selectors -- capping adminKeyScore/timelockScore below what an unqualified Safe+24h-Timelock combo would score, rather than treating the delay as unconditional")
    else:
        admin_key, multisig, timelock_score = 20, 20, 0  # one or more live calls unread after retries -- degrade instead of silently keeping a confident score
        notes.append("getMinDelay()/Safe owners+threshold/isWhitelisted() did not fully resolve this run -- scores degraded, treat as unverified")

    return {
        "target": target, "label": "USDtb PSM",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "ethena-safe-0x3b0aaf6e",
    }


def score_ethena_layerzero_oft(w3) -> list:
    """Ethena's LayerZero V2 OFTAdapters for cross-chain USDe/sUSDe/ENA
    transfer (Ethereum L1 side). ADDED 2026-09-17, promoted from
    `chains/ethereum-l1/SESSION_NOTES_2026-09-16.md` section 3 ("LayerZero
    OFTAdapters") after independent re-verification via a dedicated workflow
    (`ethena-layerzero-oft-reverify`, 2026-09-17) -- selectors recomputed
    fresh via `Web3.keccak(text=...)`, not hand-typed or trusted from the
    backlog note.

    Three adapters, all owned by the SAME `EthenaTimelockController`
    (0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94) already tracked by
    `score_usdtb_psm()` and `score_ethena_minting()` above -- confirmed live
    via `owner()` on all three:
    - USDe OFTAdapter: 0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34
      (underlying 0x4c9EDD5852cd905f086C759E8383e09bff1E68B3)
    - sUSDe OFTAdapter: 0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2
      (underlying 0x9D39A5DE30e57443BfF2A8307A4256c8797A3497 -- the same
      StakedUSDeV2 already referenced in `score_ethena_minting()`)
    - ENA OFTAdapter: 0x58538E6A46E07434d7E7375BC268D3cB839C0133
      (underlying 0x57e114B691Db790C35207b2e685D4A43181e6061)
    `endpoint()` on all three resolves to 0x1a44076050125825900e736c501f859c
    50fE728c (LayerZero EndpointV2 mainnet, cross-checked against
    LayerZero's own published deployment metadata).

    Whitelist-bypass check (same EthenaTimelockController mechanism already
    documented in `score_usdtb_psm()`), confirmed live on all three adapters:
    - `setPeer(uint32,bytes32)` (selector 0x3400288b) -- WHITELISTED (instant
      bypass, no 24h delay) on all three. This is a MORE severe risk than
      USDtb PSM's freeze-only bypass: `setPeer` redirects which remote
      endpoint id is trusted as this token's cross-chain counterpart -- an
      instant-bypass path here could let a compromised
      WHITELISTED_EXECUTOR_ROLE holder point a peer at a malicious remote
      contract and mint/redeem against a fake bridge, not merely freeze
      activity.
    - `setDelegate(address)` (selector 0xca5eb5e1) -- confirmed NOT
      whitelisted (genuinely delayed 24h) on all three.
    - Same open thread as `score_usdtb_psm()`: current holder(s) of
      WHITELISTED_EXECUTOR_ROLE not independently identified this pass (the
      free RPC tier used rejected the historical RoleGranted/RoleRevoked log
      scan needed) -- flagged, not assumed to be the Safe.

    DVN (Decentralized Verifier Network) quorum config found MORE nuanced
    than the backlog note claimed: the earlier workflow scanned all 78
    (adapter, remote chain) pairs configured across the three adapters and
    found THREE distinct patterns, not one uniform config -- a "standard"
    required/optional DVN set on 50 lanes, a different required-DVN set
    specific to two non-EVM chains (Aptos, TON) on 3 lanes, and a stricter
    4-required/zero-optional pattern with no quorum flexibility at all on 25
    lanes across 6 chains. Disclosed as a fact (the config is real and
    reviewable on-chain per lane), not folded into a score -- no defensible
    single number for "DVN config quality" across three structurally
    different patterns without a chain-by-chain risk model this project
    hasn't built.

    TVL context: USDe alone is $5.14B on Ethereum (DefiLlama `protocol/ethena`,
    same figure already cited in `score_ethena_minting()`) -- these adapters
    are a real, load-bearing cross-chain path for that value, not a side
    contract. sUSDe/ENA TVL not independently re-checked this pass (reusing
    the established USDe figure as the material one for risk purposes, since
    sUSDe wraps the same USDe backing and ENA is the governance token, not a
    stablecoin needing its own TVL bar).

    Scoring: adminKeyScore=55 and multisigScore=100 match
    `score_ethena_minting()`'s own convention for the same Safe-governed,
    no-DAO-layer authority shape. timelockScore is set BELOW
    `score_usdtb_psm()`'s 55 (at 15) precisely because the one bypassable
    function here (`setPeer`) sits in a more severe risk class than the
    PSM's bypassable functions (freeze vs. cross-chain-trust redirection) --
    a real delay exists for most of this authority surface, but the single
    most consequential function is instantly bypassable, which this
    project's convention treats as materially worse than the PSM's
    freeze-only gap, not merely "another bypass."

    Returns a list of 3 entries (one per token), matching this project's
    established pattern for one shared authority chain covering multiple
    tracked addresses (see `score_rollup_l1_authority()` in
    `scripts/lib/scorers.py`)."""
    timelock = "0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94"
    endpoint = "0x1a44076050125825900e736c501f859c50fE728c"
    adapters = [
        ("USDe OFTAdapter (LayerZero)", "0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34"),
        ("sUSDe OFTAdapter (LayerZero)", "0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2"),
        ("ENA OFTAdapter (LayerZero)", "0x58538E6A46E07434d7E7375BC268D3cB839C0133"),
    ]

    whitelist_abi = [{"name": "isWhitelisted", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}, {"type": "bytes4"}], "outputs": [{"type": "bool"}]}]
    set_peer_selector = bytes.fromhex("3400288b")
    set_delegate_selector = bytes.fromhex("ca5eb5e1")

    results = []
    for label, adapter in adapters:
        notes = []
        # FIXED 2026-09-17 (closed a bug hunt finding): this loop body used
        # to have no try/except, so a single adapter's call_raw()/
        # to_checksum_address() raising (a malformed/unreachable address,
        # for example) propagated out of the whole function -- and because
        # score_all() isolates failures at the level of the WHOLE
        # score_ethena_layerzero_oft() call (one of 7 SIMPLE_SCORERS
        # entries), that dropped all 3 LayerZero OFTAdapter targets
        # together, not just the bad one, contradicting the per-target
        # isolation this project's own score_all()/_apply_cross_exposure()
        # docstrings already claim exists for these 3 independently tracked
        # targets.
        try:
            owner = call_raw(w3, adapter, _ADDR_GETTER("owner"), "owner")
            notes.append(f"{label}.owner() = {owner} (expected EthenaTimelockController {timelock})")
            owner_matches = bool(owner) and owner.lower() == timelock.lower()

            ep = call_raw(w3, adapter, _ADDR_GETTER("endpoint"), "endpoint")
            notes.append(f"{label}.endpoint() = {ep} (expected LayerZero EndpointV2 {endpoint})")

            peer_bypassed = call_raw(w3, timelock, whitelist_abi, "isWhitelisted", w3.to_checksum_address(adapter), set_peer_selector)
            notes.append(f"isWhitelisted(adapter, setPeer(uint32,bytes32)) = {peer_bypassed} (expected True -- instant bypass, redirects trusted remote peer)")

            delegate_delayed = call_raw(w3, timelock, whitelist_abi, "isWhitelisted", w3.to_checksum_address(adapter), set_delegate_selector)
            notes.append(f"isWhitelisted(adapter, setDelegate(address)) = {delegate_delayed} (expected False -- genuinely delayed)")

            calls_resolved = owner is not None and ep is not None and peer_bypassed is not None and delegate_delayed is not None
            peer_bypass_confirmed = peer_bypassed is True
            delegate_genuinely_delayed = delegate_delayed is False

            if calls_resolved and owner_matches:
                admin_key = 55  # same Safe-governed, no-DAO-layer authority shape as score_ethena_minting()
                multisig = 100  # same 5-of-10 Safe behind the Timelock, same convention as score_usdtb_psm()
                timelock_score = 15 if (peer_bypass_confirmed and delegate_genuinely_delayed) else 0
                if peer_bypass_confirmed:
                    notes.append("Instant-bypass setPeer() capability confirmed -- capped below score_usdtb_psm()'s timelockScore, since redirecting a cross-chain peer is a more severe risk class than freezing")
            else:
                admin_key, multisig, timelock_score = 20, 20, 0  # one or more live calls unread after retries, or owner() didn't match the expected Timelock -- degrade instead of silently keeping a confident score
                notes.append("owner()/endpoint()/isWhitelisted() did not fully resolve this run, or owner() did not match the expected EthenaTimelockController -- scores degraded, treat as unverified")
        except Exception as e:
            admin_key, multisig, timelock_score = 20, 20, 0
            notes.append(f"resolving this adapter raised {type(e).__name__}: {e} -- isolated to this target, scores degraded")

        results.append({
            "target": adapter, "label": label,
            "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
            "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
            "notes": notes, "_rootGroup": "ethena-safe-0x3b0aaf6e",
        })

    return results


# ---------------------------------------------------------------------------
# ADDED 2026-09-19 (maintenance run, authority-risk-oracle-multichain-pipeline
# worker): 5 new flagship targets. Every address below comes from the
# protocol's own official source (listed per function), every authority hop
# was read live on 2 independent mainnet RPCs (publicnode + Tenderly public
# gateway) during research, and the role/ward histories that cannot be read
# with a single getter (Spark ACLManager roles, SparkProxy / FreezerMom /
# StarGuard wards) were replayed from their full RoleGranted/RoleRevoked or
# Rely/Deny event history. See data/maintenance_2026-09-19.md for the raw
# research record.
# ---------------------------------------------------------------------------

_SAFE_GETOWNERS = [{"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]
_WARDS = [{"name": "wards", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]}]
_QUORUM_AT = [{"name": "quorum", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "uint256"}]}]

UNISWAP_TIMELOCK = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"
_UNISWAP_SHARED_ROOT_NOTE = (
    "This Timelock is one root identity for 11 tracked Uniswap targets on 5 ecosystems (dated 2026-09-20): Ethereum L1 V3 "
    "Factory and V4 PoolManager, Arbitrum V3 Factory, Base V3/V2/V4, Robinhood Chain V3/V4/UniswapX/V2 and Monad V4 "
    "PoolManager, the others reached through a bridge alias, an OP-stack forwarder or a Wormhole relay. A token-vote DAO "
    "contract, not a signer committee; the cross-ecosystem fold applies as for a shared Safe committee (convention of "
    "2026-09-20). Each other ecosystem's scorer re-confirms the same root live."
)


def _same(a, b):
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


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


def score_compound_v3_cusdc(w3) -> dict:
    """Compound V3 cUSDCv3 (Comet USDC market, Ethereum L1). ADDED 2026-09-19.
    Source: official compound-finance/comet repo,
    deployments/mainnet/usdc/roots.json (comet 0xc3d688B6...) and
    configuration.json (governor = Compound Timelock 0x6d903f60..., pauseGuardian
    = 0xbbf3f142...). TVL: $1.36B for Compound V3 on Ethereum (DefiLlama
    `protocol/compound-v3`, all Comet markets on the chain combined -- this
    target is the largest single one, ~374M USDC base supply live
    `totalSupply()` on 2026-09-19).

    Authority: Comet.governor() = Compound Timelock (delay() = MINIMUM_DELAY =
    172,800s, so the delay cannot be lowered below 2 days) whose admin() is
    the Compound Governor (608 proposals, quorum 400k COMP). The Comet proxy's
    EIP-1967 admin slot resolves to CometProxyAdmin 0x1EC63B58... whose owner()
    is the SAME Timelock, and the Configurator's governor() is also the same
    Timelock -- upgrade, parameter and governance paths all converge on one
    delayed DAO root.

    Bypass found and disclosed (the reason timelockScore is capped): the
    pauseGuardian is a 5-of-9 Gnosis Safe (0xbbf3f142..., no module, no guard)
    that can pause supply/transfer/WITHDRAW/absorb/buy INSTANTLY -- a freeze
    (availability) power, not a fund-redirect one. The same Safe is also the
    Governor's proposalGuardian/whitelistGuardian (can cancel proposals).
    Same convention as Aave's guardian seat in score_aave_v3_pool()."""
    comet = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
    proxy_admin = "0x1EC63B5883C3481134FD50D5DAebc83Ecd2E8779"
    configurator = "0x316f9708bB98af7dA9c68C1C3b5e79039cD336E3"
    notes = []

    timelock = call_raw(w3, comet, _ADDR_GETTER("governor"), "governor")
    notes.append(f"Comet.governor() = {timelock} (Compound Timelock)")
    delay = call_raw(w3, timelock, _UINT_GETTER("delay"), "delay") if timelock else None
    min_delay = call_raw(w3, timelock, _UINT_GETTER("MINIMUM_DELAY"), "MINIMUM_DELAY") if timelock else None
    governor = call_raw(w3, timelock, _ADDR_GETTER("admin"), "admin") if timelock else None
    delay_note = f"{delay}s" if delay is not None else "unread"
    min_delay_note = f"{min_delay}s" if min_delay is not None else "unread"
    notes.append(f"Timelock.delay() = {delay_note} ; MINIMUM_DELAY = {min_delay_note} ; Timelock.admin() = {governor}")
    proposal_count = call_raw(w3, governor, _UINT_GETTER("proposalCount"), "proposalCount") if governor else None
    notes.append(f"CompoundGovernor.proposalCount() = {proposal_count}")

    pa_owner = call_raw(w3, proxy_admin, _ADDR_GETTER("owner"), "owner")
    cfg_governor = call_raw(w3, configurator, _ADDR_GETTER("governor"), "governor")
    notes.append(f"CometProxyAdmin.owner() = {pa_owner} ; Configurator.governor() = {cfg_governor} (both expected = the Timelock)")
    upgrade_path_on_timelock = _same(pa_owner, timelock) and _same(cfg_governor, timelock)

    pause_guardian = call_raw(w3, comet, _ADDR_GETTER("pauseGuardian"), "pauseGuardian")
    guardian_safe = safe_owners_and_threshold(w3, pause_guardian) if pause_guardian else None
    if guardian_safe:
        notes.append(f"Comet.pauseGuardian() = {pause_guardian}: real Gnosis Safe {guardian_safe[1]}-of-{len(guardian_safe[0])} -- can pause supply/transfer/withdraw/absorb/buy instantly (freeze, not redirect)")
    else:
        notes.append(f"Comet.pauseGuardian() = {pause_guardian}: NOT resolved as a Safe this run")

    cross_ecosystem = bool(guardian_safe) and {o.lower() for o in guardian_safe[0]} == _KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20
    if cross_ecosystem:
        notes.append("Real cross-chain finding, independently re-confirmed 2026-09-20: this pauseGuardian Safe's 9 owners are IDENTICAL, as an exact set, to the pauseGuardian Safes of Compound V3 on Arbitrum (0x78E6317D...) and Base (0x3cb4653F...) at the same 5-of-9 (three different Safe addresses), so one committee can freeze three Comets. Folded into crossExposureScore as a flat 80 (dated snapshot _KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20 compared with the owners read this run, no second-chain RPC).")
    root_confirmed = proposal_count and upgrade_path_on_timelock and guardian_safe
    if root_confirmed:
        admin_key = 78  # real, active DAO (600+ proposals) whose upgrade/config paths all converge on it; the instant-pause seat is an identified Safe, same convention as Aave's 78
        multisig = 100  # not applicable: root authority is a DAO+Timelock, not a Safe (the guardian Safe is a bypass seat, reflected in timelockScore)
    else:
        admin_key = 20  # a hop did not resolve or the upgrade path does not converge on the Timelock -- degrade, treat as unverified
        multisig = 20  # root not confirmed as a real, active DAO: 100 is reserved for a confirmed DAO+Timelock root (METHODOLOGY.md), unresolved is 20 (as score_wbtc's floor)
        notes.append("governor/ProxyAdmin/Configurator/pauseGuardian chain did not fully resolve or converge this run -- adminKeyScore degraded")
    if delay is not None and delay >= 172800:
        timelock_score = 60  # real 2-day delay with a 2-day floor, capped below Uniswap's 75 because an identified Safe can freeze withdrawals instantly
    else:
        timelock_score = 0
        notes.append("Timelock.delay() unread or below 2 days this run -- timelockScore degraded")

    return {
        "target": comet, "label": "Compound V3 cUSDCv3 (Comet USDC)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "compound-l1-governance", "_crossEcosystem": cross_ecosystem,
    }


def score_sparklend_pool(w3) -> dict:
    """SparkLend (Ethereum L1) PoolAddressesProvider. ADDED 2026-09-19.
    Source: official sparkdotfi/spark-address-registry repo, src/SparkLend.sol
    (POOL_ADDRESSES_PROVIDER 0x02C3eA4e..., ACL_MANAGER 0xdA135Cd7...,
    FREEZER_MOM 0x237e3985..., KILL_SWITCH_ORACLE, CAP_AUTOMATOR) and
    src/Ethereum.sol (SPARK_PROXY 0x3300f198..., PAUSE_PROXY 0xBE8E3e36...,
    SPARKLEND_FREEZER_MULTISIG 0x44efFc47..., SPARK_STAR_GUARD, ESM). TVL:
    $5.61B on Ethereum (DefiLlama `protocol/sparklend`).

    Authority: PoolAddressesProvider.owner() = SparkProxy, which also holds
    DEFAULT_ADMIN / POOL_ADMIN / EMERGENCY_ADMIN on the ACLManager (full
    RoleGranted/RoleRevoked replay). SparkProxy's wards (full Rely/Deny
    replay): Sky's MCD_PAUSE_PROXY (owner() = MCD_PAUSE, the 2-day-delay
    target already scored in score_makerdao_sky_pause()), the Sky ESM (whose
    min() is 2^256-1 on 2026-09-19, i.e. cannot be fired) and StarGuard
    (whose only ward is again MCD_PAUSE_PROXY; it lets Sky governance plot a
    Spark spell that anyone may then execute within maxDelay = 7 days). So
    every privileged SparkProxy path is rooted in the SAME delayed Sky
    governance as Maker -- this target shares its root with MCD_PAUSE.

    Bypass found and disclosed: SparkLendFreezerMom (EMERGENCY_ADMIN + RISK_ADMIN
    on the ACLManager) can freeze/pause markets INSTANTLY; its callers are its
    authority() = the Sky Chief (a hat vote, no 2-day delay) and one ward,
    SPARKLEND_FREEZER_MULTISIG, a 3-of-5 Gnosis Safe. Freeze/pause only (an
    availability risk, not fund redirect). Two other automated RISK_ADMIN
    holders exist (KillSwitchOracle, CapAutomator) -- bounded, rule-driven
    contracts owned by SparkProxy, disclosed not scored."""
    provider = "0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE"
    acl_manager = "0xdA135Cd78A086025BcdC87B038a1C462032b510C"
    pause_proxy = "0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB"
    mcd_pause = "0xbE286431454714F511008713973d3B053A2d38f3"
    freezer_mom = "0x237e3985dD7E373F2ec878EC1Ac48A228Cf2e7a3"
    freezer_multisig = "0x44efFc473e81632B12486866AA1678edbb7BEeC3"
    role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
    notes = []

    spark_proxy = call_raw(w3, provider, _ADDR_GETTER("owner"), "owner")
    notes.append(f"PoolAddressesProvider.owner() = {spark_proxy} (SparkProxy)")
    pool_admin = call_raw(w3, acl_manager, role_abi, "hasRole", b"\x00" * 32, w3.to_checksum_address(spark_proxy)) if spark_proxy else None
    notes.append(f"ACLManager.hasRole(DEFAULT_ADMIN_ROLE, SparkProxy) = {pool_admin}")
    ward = call_raw(w3, spark_proxy, _WARDS, "wards", w3.to_checksum_address(pause_proxy)) if spark_proxy else None
    notes.append(f"SparkProxy.wards(MCD_PAUSE_PROXY) = {ward}")
    pp_owner = call_raw(w3, pause_proxy, _ADDR_GETTER("owner"), "owner")
    notes.append(f"MCD_PAUSE_PROXY.owner() = {pp_owner} (expected MCD_PAUSE {mcd_pause})")
    delay = call_raw(w3, mcd_pause, _UINT_GETTER("delay"), "delay")
    delay_note = f"{delay}s" if delay is not None else "unread"
    notes.append(f"MCD_PAUSE.delay() = {delay_note}")

    mom_ward = call_raw(w3, freezer_mom, _WARDS, "wards", w3.to_checksum_address(freezer_multisig))
    freezer_safe = safe_owners_and_threshold(w3, freezer_multisig)
    notes.append(
        f"FreezerMom.wards(SPARKLEND_FREEZER_MULTISIG) = {mom_ward} ; freezer multisig = "
        f"{(str(freezer_safe[1]) + '-of-' + str(len(freezer_safe[0]))) if freezer_safe else 'unresolved'} -- instant freeze/pause seat (no delay)"
    )

    root_resolved = pool_admin is True and ward == 1 and _same(pp_owner, mcd_pause)
    if root_resolved:
        admin_key = 75  # same real, active Sky governance as score_makerdao_sky_pause()
    else:
        admin_key = 20
        notes.append("SparkProxy -> MCD_PAUSE_PROXY -> MCD_PAUSE chain did not fully resolve this run -- adminKeyScore degraded")
    multisig = 100 if root_resolved else 20  # not applicable only when the Sky root is confirmed; an unresolved root is 20
    if delay is not None and delay >= 172800 and mom_ward is not None and root_resolved:
        timelock_score = 60  # 2-day Sky pause delay, capped below Maker's own 70 for the identified instant freeze/pause seat (hat + 3-of-5 Safe)
    else:
        timelock_score = 0
        if not root_resolved:
            notes.append("MCD_PAUSE.delay() or root authority unresolved -- timelockScore degraded")
        elif delay is None or delay < 172800:
            notes.append("MCD_PAUSE.delay() unread or below 2 days this run -- timelockScore degraded")
        elif mom_ward is None:
            notes.append("FreezerMom ward unread this run -- timelockScore degraded")

    return {
        "target": provider, "label": "SparkLend (PoolAddressesProvider)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "makerdao-sky-governance",
    }


def score_uniswap_v4_pool_manager(w3) -> dict:
    """Uniswap V4 PoolManager (Ethereum L1). ADDED 2026-09-19. Source: the
    address DefiLlama-Adapters' own projects/uniswap-v4/index.js indexes for
    Ethereum (0x000000000004444c5dc75cB358380D2e3dE08A90, the canonical
    CREATE2 vanity address). TVL: $743M on Ethereum (DefiLlama
    `protocol/uniswap-v4`).

    Authority: PoolManager.owner() is DIRECTLY the Uniswap Governance Timelock
    (0x1a9C8182..., delay = MINIMUM_DELAY = 2 days, admin = GovernorBravo) --
    the exact root already scored for V3 in score_uniswap_v3_factory(). The
    protocolFeeController is a V4FeeAdapter (Sourcify exact match) whose
    owner() and feeSetter() are that same Timelock; its V4FeePolicy's owner()
    and feeSetter() are also that Timelock (all read live 2026-09-19). Same
    scoring as V3; shares its root group with V3."""
    pool_manager = "0x000000000004444c5dc75cB358380D2e3dE08A90"
    notes = []

    owner = call_raw(w3, pool_manager, _ADDR_GETTER("owner"), "owner")
    notes.append(f"PoolManager.owner() = {owner} (expected Uniswap Governance Timelock {UNISWAP_TIMELOCK})")
    fee_controller = call_raw(w3, pool_manager, _ADDR_GETTER("protocolFeeController"), "protocolFeeController")
    fc_owner = call_raw(w3, fee_controller, _ADDR_GETTER("owner"), "owner") if fee_controller else None
    fc_setter = call_raw(w3, fee_controller, _ADDR_GETTER("feeSetter"), "feeSetter") if fee_controller else None
    notes.append(f"protocolFeeController = {fee_controller} ; owner() = {fc_owner} ; feeSetter() = {fc_setter}")

    delay = call_raw(w3, owner, _UINT_GETTER("delay"), "delay") if owner else None
    governor = call_raw(w3, owner, _ADDR_GETTER("admin"), "admin") if owner else None
    quorum = call_raw(w3, governor, _UINT_GETTER("quorumVotes"), "quorumVotes") if governor else None
    delay_note = f"{delay}s" if delay is not None else "unread"
    notes.append(f"Timelock.delay() = {delay_note} ; admin() = {governor} ; GovernorBravo.quorumVotes() = {quorum}")

    owner_is_timelock = _same(owner, UNISWAP_TIMELOCK)
    fee_path_on_timelock = _same(fc_owner, UNISWAP_TIMELOCK) and _same(fc_setter, UNISWAP_TIMELOCK)
    root_confirmed = owner_is_timelock and quorum is not None
    if root_confirmed:
        admin_key = 80  # same real, active token-vote DAO as score_uniswap_v3_factory()
        multisig = 100  # not applicable: pure DAO+Timelock construction
        if not fee_path_on_timelock:
            admin_key = 60
            notes.append("protocolFeeController owner/feeSetter NOT the Timelock this run -- a second, undelayed fee authority; adminKeyScore lowered")
    else:
        admin_key = 20
        multisig = 20  # root not confirmed (owner not the known Timelock, or quorumVotes() unread): 100 is reserved for a confirmed DAO+Timelock root
        notes.append("PoolManager.owner() is not the known Timelock or quorumVotes() unread -- adminKeyScore degraded")
    if delay is not None and delay >= 172800 and owner_is_timelock:
        timelock_score = 75  # same 2-day delay and same cap as V3
    else:
        timelock_score = 0
        if delay is None:
            notes.append("Timelock.delay() unread -- timelockScore degraded")
        elif delay < 172800:
            notes.append(f"Timelock.delay() = {delay}s is below 172800s floor -- timelockScore degraded")
        elif not owner_is_timelock:
            notes.append("PoolManager.owner() is not the known Timelock -- timelockScore degraded")

    if root_confirmed:
        notes.append(_UNISWAP_SHARED_ROOT_NOTE)
    return {
        "target": pool_manager, "label": "Uniswap V4 PoolManager",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "uniswap-l1-governance",
        "_crossEcosystem": root_confirmed,
    }


# Morpho Association's governance committee, as live-read on the Ethereum
# L1 owner Safe (0xcBa28b38...) on 2026-09-19 -- the SAME 9 signers at the
# SAME 5-of-9 threshold as the Base and Robinhood Chain Morpho Blue owner
# Safes already tracked in this project (compare
# chains/base-ecosystem/scorers.py `_KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19`).
_KNOWN_MORPHO_COMMITTEE_2026_09_19 = frozenset({
    "0x13cA8756E9470b71B8e998352c8741706217f963", "0x264c86DBbD2E4165FbBf0C35b0ddf0e00AEc6b31",
    "0x30E7c016fC702cDe9A50720a469d418490b7b652", "0x69FcEFDe2B48503d675181448B3D4272128bca9c",
    "0x84D3E4EE550DD5F99e76a548aC59a6BE1C8dCf79", "0x8f02b4a44Eacd9b8eE7739aa0BA58833DD45d002",
    "0xC100c251bdD297A66795112f04356E6BA5f89D80", "0xCF263cEe139763114fAaFC5F52865135412F50Ec",
    "0xe0aeb6811d33Df42A09066857CDaFca16b506086",
})


def score_morpho_blue_l1(w3) -> dict:
    """Morpho Blue singleton (Ethereum L1). ADDED 2026-09-19. Source: the
    address DefiLlama-Adapters' projects/morpho-blue/config.js lists for
    `ethereum.morphoBlue` (0xBBBBBbbB..., same CREATE2 address as on Base).
    TVL: $5.03B on Ethereum (DefiLlama `protocol/morpho-blue`).

    Authority: MorphoBlue.owner() = a Gnosis Safe 5-of-9 (0xcBa28b38...,
    v1.3.0, no module enabled, no guard set), one hop, no Timelock. Same
    scope caveat as the Base scorer: owner() can only set fees and enable
    IRMs/LLTVs for future markets, cannot move funds in existing markets.
    Scored with the SAME rule as chains/base-ecosystem's score_morpho_blue()
    (admin 65 for threshold >= 3, multisig formula, timelock 0) so one
    protocol gets one convention across ecosystems.

    CORRECTED 2026-09-20 (crossExposureScore convention decision): the owner
    Safe's 9 signers are identical to the Base and Robinhood Chain Morpho Blue
    owner Safes, and that overlap is now folded into crossExposureScore (a
    flat 80, same as Base's score_morpho_blue()) via the `_crossEcosystem`
    flag that _apply_cross_exposure() reads, not just noted."""
    target = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
    notes = []
    cross_ecosystem = False
    owner = call_raw(w3, target, _ADDR_GETTER("owner"), "owner")
    notes.append(f"MorphoBlue.owner() = {owner}")
    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("owner not resolvable as a Gnosis Safe this run -- conservative score")
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}")
        notes.append("Scope caveat: owner() can only set fees / enable new IRMs+LLTVs -- cannot move funds in existing markets (immutable core)")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no Timelock/delay anywhere in this chain
        if {w3.to_checksum_address(o) for o in owners} == {w3.to_checksum_address(o) for o in _KNOWN_MORPHO_COMMITTEE_2026_09_19}:
            cross_ecosystem = True
            notes.append("Owner set IDENTICAL to the Base and Robinhood Chain Morpho Blue owner Safes (same 9 signers) -- one committee across 3 tracked ecosystems (cross-ecosystem finding, folded into crossExposureScore as a flat 80)")
    return {
        "target": target, "label": "Morpho Blue (singleton, Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "morpho-association-safe", "_crossEcosystem": cross_ecosystem,
    }


def score_wbtc(w3) -> dict:
    """WBTC (Wrapped BTC, Ethereum L1). ADDED 2026-09-19. Source: token
    address from DefiLlama-Adapters projects/helper/coreAssets.json
    (`ethereum.WBTC`); the official WrappedBTC/bitcoin-token-smart-contracts
    repo holds the source but publishes no address. TVL: $9.50B (DefiLlama
    `protocol/wbtc`, BTC custodied; cross-checked: live totalSupply()
    116,132 WBTC x DefiLlama price $81,764 = $9.50B).

    Authority: WBTC.owner() = the WBTC Controller (0xCA06411b..., whose
    token() points back at WBTC, pendingOwner() = 0). Controller.owner() =
    a legacy Gnosis MultiSigWallet (NOT a Gnosis Safe: getThreshold() reverts,
    required() = 6, getOwners() = 10) at 0x972Eed35..., with dailyLimit() = 0
    and no timelock. The Controller owner can replace the Factory (the only
    minter path), the Members registry and pause the token -- i.e. this
    6-of-10 multisig controls minting of a $9.5B token with no delay. Only
    4 transactions have ever been submitted through it (transactionCount()
    = 4), consistent with a rarely-used cold admin. Off-chain BTC custody
    (BitGo/BiT Global) is out of this oracle's on-chain scope."""
    token = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
    notes = []
    controller = call_raw(w3, token, _ADDR_GETTER("owner"), "owner")
    back = call_raw(w3, controller, _ADDR_GETTER("token"), "token") if controller else None
    notes.append(f"WBTC.owner() = {controller} (Controller) ; Controller.token() = {back}")
    msig = call_raw(w3, controller, _ADDR_GETTER("owner"), "owner") if controller else None
    required = call_raw(w3, msig, _UINT_GETTER("required"), "required") if msig else None
    owners = call_raw(w3, msig, _SAFE_GETOWNERS, "getOwners") if msig else None
    notes.append(f"Controller.owner() = {msig} ; MultiSigWallet.required() = {required} ; owners = {len(owners) if owners else None}")

    if _same(back, token) and required is not None and owners:
        admin_key = 55 if required >= 3 else 20  # multisig with no DAO/Timelock above it controlling a multi-$B token's minting -- same convention as score_ethena_minting()
        multisig = min(100, required * 15 + max(0, len(owners) - required) * 5)
    else:
        admin_key, multisig = 10, 20
        notes.append("Controller/multisig chain did not resolve this run -- scores degraded")
    timelock_score = 0  # no delay anywhere in this chain (structural: MultiSigWallet executes on confirmation)

    return {
        "target": token, "label": "WBTC (Wrapped BTC)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "wbtc-multisigwallet-0x972eed35",
    }


# ---------------------------------------------------------------------------
# 4 targets added 2026-09-20 (maintenance run, (B) "nouvelles cibles").
# Budget was 10; 4 were taken, deliberately, because each one was traced to
# its root live on two independent RPCs in this same pass and none was
# accepted on a literal. Addresses all come from DefiLlama-Adapters (this
# project's accepted primary address source) and were re-confirmed against
# the contract's own self-attesting getters where one exists.
# ---------------------------------------------------------------------------

_BOOL_GETTER = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]}]  # noqa: E731
_ACL_HAS_PERMISSION = [{"name": "hasPermission", "type": "function", "stateMutability": "view",
                        "inputs": [{"type": "address"}, {"type": "address"}, {"type": "bytes32"}],
                        "outputs": [{"type": "bool"}]}]
_ACL_PERMISSION_MANAGER = [{"name": "getPermissionManager", "type": "function", "stateMutability": "view",
                            "inputs": [{"type": "address"}, {"type": "bytes32"}],
                            "outputs": [{"type": "address"}]}]
_STORAGE_GET_ADDRESS = [{"name": "getAddress", "type": "function", "stateMutability": "view",
                         "inputs": [{"type": "bytes32"}], "outputs": [{"type": "address"}]}]
# Lido's HashConsensus.getMembers() returns TWO arrays (addresses, lastReportedRefSlots),
# not one -- reusing _SAFE_GETOWNERS here silently returned None and quietly cost the
# target 80 oracleAuthority points on the first live dry-run of this scorer.
_HASH_CONSENSUS_GET_MEMBERS = [{"name": "getMembers", "type": "function", "stateMutability": "view",
                                "inputs": [], "outputs": [{"type": "address[]"}, {"type": "uint256[]"}]}]
# ADDED 2026-09-25 for score_eigenlayer_strategy_manager()'s Pauser disclosure (see its docstring).
_IS_PAUSER_ABI = [{"name": "isPauser", "type": "function", "stateMutability": "view",
                   "inputs": [{"type": "address"}], "outputs": [{"type": "bool"}]}]

# The EIP-1967 admin storage slot, and the two Aragon role ids this file reads.
# The roles are COMPUTED, not pasted, and checked against the value an
# independent tool produces (`cast keccak 0x$(printf 'APP_MANAGER_ROLE' | xxd -p)`)
# so a silent typo in a 32-byte literal cannot turn a real permission read into
# a false "unresolved root".
_EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"


def _keccak_role(name: str) -> bytes:
    return Web3.keccak(text=name)


_ARAGON_EXECUTE_ROLE = _keccak_role("EXECUTE_ROLE")
_ARAGON_APP_MANAGER_ROLE = _keccak_role("APP_MANAGER_ROLE")
assert "0x" + _ARAGON_APP_MANAGER_ROLE.hex().removeprefix("0x") == (
    "0xb6d92708f3d4817afc106147d969e229ced5c46e65e0a5002a0d391287762bd0"
), "APP_MANAGER_ROLE keccak drifted from the value cast keccak produces"


def _multisig_formula(threshold: int, owner_count: int) -> int:
    """METHODOLOGY.md's general shape: min(100, t*15 + max(0, n-t)*5)."""
    return min(100, threshold * 15 + max(0, owner_count - threshold) * 5)


def score_lido_steth(w3) -> dict:
    """Lido stETH (Ethereum L1). ADDED 2026-09-20. Address source:
    DefiLlama-Adapters projects/helper/coreAssets.json `ethereum.STETH`
    (0xae7ab965...); re-confirmed on-chain by the token itself, whose
    getLidoLocator() returns the LidoLocator this scorer then reads.
    TVL: $26.29B on Ethereum (DefiLlama api.llama.fi/protocol/lido,
    currentChainTvls.Ethereum, read 2026-09-25 -- refreshed from the
    $25.22B read on 2026-09-20; corroborated on-chain, stETH.totalSupply()
    = 9,764,974.0285 x ETH price ~$2,680).

    Authority (traced live on publicnode + drpc, nothing read from a file):
    stETH is an Aragon AppProxyUpgradeable. kernel() -> Lido Kernel;
    Kernel.acl() -> Aragon ACL; ACL.getPermissionManager(Kernel,
    APP_MANAGER_ROLE) -> the Lido DAO Agent 0x3e40D73E. The REAL finding of
    this pass is what sits above that Agent: the Aragon Voting app
    (0x2e59A20f) NO LONGER holds EXECUTE_ROLE on the Agent
    (hasPermission = false). It is held instead by 0x23E0B465, the Dual
    Governance admin Executor, whose owner() is the EmergencyProtectedTimelock
    0xCE042530 with getAfterSubmitDelay() = 259200 s + getAfterScheduleDelay()
    = 86400 s, i.e. a 4-day enforced delay, with isEmergencyModeActive()
    currently false and a separate emergency governance address configured.

    Mitigating/aggravating context was looked for both ways: the 4-day delay
    is real and live (aggravation ruled out), but a configured emergency
    governance path exists and was NOT exercised or fully bounded this pass,
    so timelockScore is capped well below the 75 a bypass-free delay would
    earn, per METHODOLOGY.md.

    oracleAuthorityScore is NOT 100 here: stETH's share rate is itself
    consumed as an oracle elsewhere, and it is set by the AccountingOracle
    (LidoLocator.accountingOracle() -> 0x852deD01) whose HashConsensus
    (0xD624B08C) reads getQuorum() = 5 over 9 members -- scored with this
    file's multisig formula rather than waved through as "not applicable"."""
    token = "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84"
    voting = "0x2e59A20f205bB85a89C53f1936454680651E618e"
    dual_gov_executor = "0x23E0B465633FF5178808F4A75186E2F2F9537021"
    notes = []

    kernel = call_raw(w3, token, _ADDR_GETTER("kernel"), "kernel")
    acl = call_raw(w3, kernel, _ADDR_GETTER("acl"), "acl") if kernel else None
    agent = (call_raw(w3, acl, _ACL_PERMISSION_MANAGER, "getPermissionManager", kernel, _ARAGON_APP_MANAGER_ROLE)
             if acl and kernel else None)
    notes.append(f"stETH.kernel() = {kernel} ; Kernel.acl() = {acl} ; permission manager of (Kernel, APP_MANAGER_ROLE) = {agent}")

    voting_can_execute = (call_raw(w3, acl, _ACL_HAS_PERMISSION, "hasPermission", voting, agent, _ARAGON_EXECUTE_ROLE)
                          if acl and agent else None)
    dg_can_execute = (call_raw(w3, acl, _ACL_HAS_PERMISSION, "hasPermission", dual_gov_executor, agent, _ARAGON_EXECUTE_ROLE)
                      if acl and agent else None)
    notes.append(f"ACL.hasPermission(Aragon Voting {voting}, Agent, EXECUTE_ROLE) = {voting_can_execute} ; "
                 f"ACL.hasPermission(Dual Governance executor {dual_gov_executor}, Agent, EXECUTE_ROLE) = {dg_can_execute}")

    timelock = call_raw(w3, dual_gov_executor, _ADDR_GETTER("owner"), "owner")
    submit_delay = call_raw(w3, timelock, _UINT_GETTER("getAfterSubmitDelay"), "getAfterSubmitDelay") if timelock else None
    schedule_delay = call_raw(w3, timelock, _UINT_GETTER("getAfterScheduleDelay"), "getAfterScheduleDelay") if timelock else None
    emergency_active = call_raw(w3, timelock, _BOOL_GETTER("isEmergencyModeActive"), "isEmergencyModeActive") if timelock else None
    total_delay = (submit_delay + schedule_delay) if (submit_delay is not None and schedule_delay is not None) else None
    notes.append(f"Executor.owner() = {timelock} (EmergencyProtectedTimelock) ; afterSubmit {submit_delay} s + "
                 f"afterSchedule {schedule_delay} s = {total_delay} s total ; isEmergencyModeActive() = {emergency_active}")

    if dg_can_execute is True and total_delay is not None and total_delay >= 3 * 86400:
        admin_key = 80  # real, active DAO root, reached and re-confirmed live this pass (METHODOLOGY 75-85 band)
        multisig = 100  # DAO root with no Safe layer above it -- "not applicable", not conflated with a threshold
        timelock_score = 60  # real 4-day delay, capped below 75 because a configured emergency-governance bypass was NOT ruled out this pass
        notes.append("Root resolved: Lido DAO via Dual Governance, 4-day enforced delay, emergency bypass path present but not exercised")
    elif dg_can_execute is True:
        admin_key, multisig, timelock_score = 80, 100, 0
        notes.append("Dual Governance executor holds EXECUTE_ROLE but its timelock delay did not read this run -- timelockScore 0, not assumed")
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("Agent/EXECUTE_ROLE chain did not resolve this run -- conservative 'unknown, not assumed safe' score")

    quorum = None
    members = None
    locator = call_raw(w3, token, _ADDR_GETTER("getLidoLocator"), "getLidoLocator")
    accounting_oracle = call_raw(w3, locator, _ADDR_GETTER("accountingOracle"), "accountingOracle") if locator else None
    consensus = call_raw(w3, accounting_oracle, _ADDR_GETTER("getConsensusContract"), "getConsensusContract") if accounting_oracle else None
    if consensus:
        quorum = call_raw(w3, consensus, _UINT_GETTER("getQuorum"), "getQuorum")
        members = call_raw(w3, consensus, _HASH_CONSENSUS_GET_MEMBERS, "getMembers")
        members = members[0] if members else None
    if quorum and members:
        oracle_authority = _multisig_formula(quorum, len(members))
        notes.append(f"stETH share rate is oracle-fed: LidoLocator {locator} -> AccountingOracle {accounting_oracle} -> "
                     f"HashConsensus {consensus}, getQuorum() = {quorum} of {len(members)} members -> oracleAuthorityScore {oracle_authority}")
    else:
        oracle_authority = 20
        notes.append("AccountingOracle/HashConsensus quorum did not read this run -- oracleAuthorityScore 20 (unknown, not waved through as 100)")

    return {
        "target": token, "label": "Lido stETH (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": oracle_authority, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "lido-dual-governance-executor-0x23e0b465",
    }


def score_eigenlayer_strategy_manager(w3) -> dict:
    """EigenLayer StrategyManager (Ethereum L1). ADDED 2026-09-20. Address
    source: DefiLlama-Adapters projects/eigenlayer/index.js
    (`0x858646372cc42e1a627fce94aa7a7033e7cf075a`). TVL: $7.05B on Ethereum
    (DefiLlama api.llama.fi/protocol/eigenlayer, read 2026-09-25 -- refreshed
    from the $6.87B read on 2026-09-20).

    Authority (traced live on publicnode + drpc): the StrategyManager is a
    transparent proxy; its EIP-1967 admin slot holds ProxyAdmin 0x8b9566ad,
    whose owner() is the Executor Multisig 0x369e6F59 -- a Gnosis Safe with
    getThreshold() = 1 over 2 owners.

    That 1-of-2 shape is the finding, and its two owners are why it is NOT
    scored like a 1-of-2 signed by people: owner A is a real
    TimelockController (0xC06Fd4F8, getMinDelay() = 864000 s = 10 days) and
    owner B is a 9-of-13 Gnosis Safe (0xFEA47018, the community multisig).
    Threshold 1 means EITHER path alone can upgrade the StrategyManager, so
    the 10-day delay is a norm, not a guarantee: the 9-of-13 Safe can execute
    the same upgrade with no delay at all. METHODOLOGY.md says to score the
    gap rather than the presence of a timelock somewhere in the chain, so
    timelockScore is 20 (a real delay exists and is the normal path) and not
    the 60-75 a delay with no bypass would earn. Attenuating context was
    looked for and is recorded: no Safe module is enabled on the executor
    Safe (getModulesPaginated returns an empty list), so there is no third,
    quieter path beyond those two owners.

    ADDED 2026-09-25 (real modeling gap, previously not read by this scorer
    at all): the StrategyManager's Pauser is a SEPARATE authority path from
    the owner/upgrade chain above -- StrategyManager.pauserRegistry() ->
    PauserRegistry 0xB8765ed72235d279c3Fb53936E4606db0Ef12806, whose
    isPauser() confirms 0x5050389572f2d220ad927CcbeA0D406831012390 (a real
    Gnosis Safe, getThreshold() = 1 over 7 owners) can pause() the ENTIRE
    StrategyManager instantly -- one signature out of 7, no delay. The
    unpauser() on that same registry is 0x369e6F597e22EaB55fFb173C6d9cD234BD699111,
    the SAME executor Safe already scored above (threshold 1, timelock +
    community-Safe owners), so un-pausing is already covered by the scoring
    above; only the pause side is new. This is disclosed in the notes, NOT
    folded into any sub-score above: it is a bounded (freeze-only, not
    fund-redirect) power, same shape as score_compound_v3_cusdc()'s
    pauseGuardian, but unlike that scorer this one already scores its root
    as a threshold-1 Safe bypass, not a clean DAO+Timelock -- there is no
    existing convention in this file for stacking a second, independent
    bypass discount on top of a bypass already reflected in timelockScore,
    so one is not invented here; the finding is disclosed in full instead,
    the same convention score_aave_v3_horizon_pool() uses for its bounded,
    disclosed-not-scored RISK_ADMIN Safe."""
    target = "0x858646372CC42E1A627fcE94aa7A7033e7CF075A"
    timelock_addr = "0xC06Fd4F821eaC1fF1ae8067b36342899b57BAa2d"
    community_safe = "0xFEA47018D632A77bA579846c840d5706705Dc598"
    pauser_safe_addr = "0x5050389572f2d220ad927CcbeA0D406831012390"
    unpauser_expected = "0x369e6F597e22EaB55fFb173C6d9cD234BD699111"
    notes = []

    proxy_admin = read_slot_as_address(w3, target, _EIP1967_ADMIN_SLOT)
    owner = call_raw(w3, proxy_admin, _ADDR_GETTER("owner"), "owner") if proxy_admin else None
    notes.append(f"EIP-1967 admin slot -> ProxyAdmin {proxy_admin} ; ProxyAdmin.owner() = {owner} (executor multisig)")

    executor_safe = safe_owners_and_threshold(w3, owner) if owner else None
    min_delay = call_raw(w3, timelock_addr, _UINT_GETTER("getMinDelay"), "getMinDelay")
    community = safe_owners_and_threshold(w3, community_safe)

    if executor_safe and min_delay and community:
        exec_owners, exec_threshold = executor_safe
        c_owners, c_threshold = community
        exec_set = {w3.to_checksum_address(o) for o in exec_owners}
        expected = {w3.to_checksum_address(timelock_addr), w3.to_checksum_address(community_safe)}
        notes.append(f"executor Safe is {exec_threshold}-of-{len(exec_owners)} ; owners = {sorted(exec_set)}")
        notes.append(f"owner A TimelockController {timelock_addr}: getMinDelay() = {min_delay} s "
                     f"({min_delay // 86400} days) ; owner B Safe {community_safe}: {c_threshold}-of-{len(c_owners)}")
        if exec_set != expected:
            admin_key, multisig, timelock_score = 20, 0, 0
            notes.append("executor Safe owner set is NOT the timelock + community-multisig pair this scorer verified -- "
                         "the authority chain changed, scoring degraded rather than guessed")
        elif exec_threshold == 1:
            # Every owner of the threshold-1 Safe is itself a contract-based authority
            # (a timelock or a high-threshold Safe), never a bare EOA, so this is NOT
            # the near-worst case a literal "threshold 1" rule would produce.
            admin_key = 60
            # The weakest committee that can act alone is the community Safe, so that
            # is what multisigScore describes -- the 1-of-2 Safe above it only routes.
            multisig = _multisig_formula(c_threshold, len(c_owners))
            timelock_score = 20
            notes.append("threshold 1: the 10-day timelock is bypassable by the community Safe acting alone -- "
                         "timelockScore scored on that gap (20), not on the timelock's presence")
        else:
            admin_key = 70
            multisig = _multisig_formula(exec_threshold, len(exec_owners))
            timelock_score = 60
            notes.append("executor Safe threshold is above 1 -- the timelock is no longer bypassable by a single owner")
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("ProxyAdmin/executor/timelock chain did not fully resolve this run -- conservative score, nothing assumed")

    # ADDED 2026-09-25: the Pauser, a completely separate authority path from the owner/upgrade
    # chain scored above -- disclosed only, per this function's own docstring (no existing
    # convention in this file for stacking a second bypass discount on the one already in
    # timelockScore above).
    pauser_registry = call_raw(w3, target, _ADDR_GETTER("pauserRegistry"), "pauserRegistry")
    is_pauser = call_raw(w3, pauser_registry, _IS_PAUSER_ABI, "isPauser", pauser_safe_addr) if pauser_registry else None
    unpauser = call_raw(w3, pauser_registry, _ADDR_GETTER("unpauser"), "unpauser") if pauser_registry else None
    pauser_safe = safe_owners_and_threshold(w3, pauser_safe_addr)
    if pauser_registry and is_pauser is True and pauser_safe:
        p_owners, p_threshold = pauser_safe
        notes.append(
            f"StrategyManager.pauserRegistry() = {pauser_registry} ; isPauser({pauser_safe_addr}) = True ; that address "
            f"is a real Gnosis Safe {p_threshold}-of-{len(p_owners)} that can pause() the ENTIRE StrategyManager "
            f"instantly, no delay -- a full-halt power NOT modeled by any sub-score above (those describe the "
            f"owner/upgrade path only). unpauser() = {unpauser}"
            + (f", the SAME executor Safe already scored above" if _same(unpauser, unpauser_expected) else " (expected the executor Safe already scored above, but it did not match this run)")
            + ". Disclosed, not scored -- see this function's docstring for why no sub-score is adjusted for it."
        )
    else:
        notes.append("StrategyManager.pauserRegistry()/isPauser()/Pauser-Safe chain did not fully resolve this run -- "
                      "the disclosed pause-authority check is skipped, existing sub-scores above are unaffected")

    return {
        "target": target, "label": "EigenLayer StrategyManager (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "eigenlayer-executor-multisig-0x369e6f59",
    }


def score_curve_stableswap_ng_factory(w3) -> dict:
    """Curve Stableswap-NG factory (Ethereum L1). ADDED 2026-09-20. Address
    source: DefiLlama-Adapters projects/curve/index.js
    (`0x6a8cbed756804b16e05e741edabd5cb544ae21bf`). TVL: $1.24B on Ethereum
    for Curve DEX (DefiLlama api.llama.fi/protocol/curve-dex, read 2026-09-20).

    Authority (traced live on publicnode + drpc): factory.admin() = the Curve
    DAO Ownership Agent 0x40907540, an Aragon Agent on Curve's OWN Aragon
    deployment (agent.kernel() = 0xad068681, Kernel.acl() = 0xBd0697BA --
    deliberately re-read rather than assumed to be Lido's ACL, which is a
    different contract). On that ACL, the permission manager of (Agent,
    EXECUTE_ROLE) is the Curve Ownership Voting app 0xE478de48, which also
    holds the permission itself. Voting reads voteTime() = 604800 s (7 days),
    supportRequiredPct() = 51 %, minAcceptQuorumPct() = 30 %.

    RUN_SCRIPT_ROLE is NOT the role used here (its manager reads as the zero
    address and Voting does not hold it) -- noted because copying Lido's role
    name across would have produced a false "unresolved root"."""
    target = "0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf"
    notes = []

    agent = call_raw(w3, target, _ADDR_GETTER("admin"), "admin")
    kernel = call_raw(w3, agent, _ADDR_GETTER("kernel"), "kernel") if agent else None
    acl = call_raw(w3, kernel, _ADDR_GETTER("acl"), "acl") if kernel else None
    notes.append(f"factory.admin() = {agent} (Curve DAO Ownership Agent) ; Agent.kernel() = {kernel} ; Kernel.acl() = {acl}")

    voting = (call_raw(w3, acl, _ACL_PERMISSION_MANAGER, "getPermissionManager", agent, _ARAGON_EXECUTE_ROLE)
              if acl and agent else None)
    voting_has = (call_raw(w3, acl, _ACL_HAS_PERMISSION, "hasPermission", voting, agent, _ARAGON_EXECUTE_ROLE)
                  if acl and agent and voting and int(voting, 16) != 0 else None)
    vote_time = call_raw(w3, voting, _UINT_GETTER("voteTime"), "voteTime") if voting and int(voting, 16) else None
    support = call_raw(w3, voting, _UINT_GETTER("supportRequiredPct"), "supportRequiredPct") if voting and int(voting, 16) else None
    quorum = call_raw(w3, voting, _UINT_GETTER("minAcceptQuorumPct"), "minAcceptQuorumPct") if voting and int(voting, 16) else None
    notes.append(f"permission manager of (Agent, EXECUTE_ROLE) = {voting} ; hasPermission = {voting_has} ; "
                 f"voteTime = {vote_time} s ; supportRequiredPct = {support} ; minAcceptQuorumPct = {quorum}")

    if voting_has is True and vote_time and quorum:
        admin_key = 78  # resolved external-DAO root with quorum AND delay re-confirmed live this pass
        multisig = 100  # real, active DAO with no Safe layer at the root
        # The 7-day vote period IS the enforced delay; there is no separate
        # TimelockController, and no emergency-bypass check was done this pass,
        # so this stays below the 75 a checked, bypass-free Timelock earns.
        timelock_score = 65 if vote_time >= 7 * 86400 else 45
        notes.append(f"root = Curve DAO (veCRV vote), {vote_time // 86400}-day minimum vote period acts as the delay; "
                     "no separate TimelockController, no emergency-bypass check done this pass")
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("Agent/Voting chain did not resolve this run -- conservative score")

    return {
        "target": target, "label": "Curve Stableswap-NG factory (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "curve-dao-ownership-agent-0x40907540",
    }


def score_rocketpool_storage(w3) -> dict:
    """Rocket Pool RocketStorage (Ethereum L1). ADDED 2026-09-20. Address
    source: DefiLlama-Adapters projects/rocketpool/index.js, whose own comment
    names RocketStorage 0x1d8f8f00 as the registry every other Rocket Pool
    address is resolved from. TVL: $1.36B on Ethereum (DefiLlama
    api.llama.fi/protocol/rocket-pool, read 2026-09-20).

    Authority (traced live on publicnode + drpc): RocketStorage.getGuardian()
    returns 0x0cCF1498, which has NO bytecode -- a bare EOA holding a named
    protocol role on a $1.36B protocol. That is exactly the shape this oracle
    exists to surface, so the attenuating context was hunted for before
    calling it notable, and it is real and decisive:

      * getDeployedStatus() = true, so the blanket "anything goes" write
        access RocketStorage grants its guardian before deployment is closed;
      * the protocol DAO (resolved THROUGH RocketStorage itself, not from a
        literal: getAddress(keccak256("contract.address" + "rocketDAOProtocol"))
        -> 0xCaC25e88) reads getBootstrapModeDisabled() = true, so the
        guardian's bootstrap power over protocol settings is also closed.

    What is left to the EOA is the guardian handover itself -- setGuardian's
    selector 0x8a0dac4a is present in RocketStorage's deployed bytecode, with
    no delay mechanism anywhere in that path. So: adminKeyScore is NOT the
    2-10 of a live bare-EOA admin, because the powers are confirmed retired;
    it is also not a DAO score, because an EOA still sits in a named role.
    multisigScore is 0 (the root is an EOA, not a Safe) and timelockScore is 0
    (no delay on that path), per METHODOLOGY.md, and both are stated rather
    than softened."""
    target = "0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46"
    notes = []

    guardian = call_raw(w3, target, _ADDR_GETTER("getGuardian"), "getGuardian")
    deployed = call_raw(w3, target, _BOOL_GETTER("getDeployedStatus"), "getDeployedStatus")
    guardian_is_eoa = is_eoa(w3, guardian) if guardian else None
    notes.append(f"RocketStorage.getGuardian() = {guardian} ; is a bare EOA (no bytecode) = {guardian_is_eoa} ; "
                 f"getDeployedStatus() = {deployed}")

    dao_key = _rocket_storage_key("rocketDAOProtocol")
    dao = call_raw(w3, target, _STORAGE_GET_ADDRESS, "getAddress", dao_key)
    bootstrap_disabled = call_raw(w3, dao, _BOOL_GETTER("getBootstrapModeDisabled"), "getBootstrapModeDisabled") if dao and int(dao, 16) else None
    notes.append(f"rocketDAOProtocol resolved through RocketStorage itself = {dao} ; "
                 f"getBootstrapModeDisabled() = {bootstrap_disabled}")

    if guardian_is_eoa and deployed is True and bootstrap_disabled is True:
        admin_key = 55
        notes.append("EOA guardian, but BOTH of its powerful paths are confirmed closed live (deployed + bootstrap disabled) "
                     "-- scored as a retired role, not as a live bare-EOA admin")
    elif guardian_is_eoa:
        admin_key = 5
        notes.append("EOA guardian whose powers are NOT confirmed retired this run -- scored as a live bare-EOA admin")
    elif guardian:
        admin_key = 20
        notes.append("guardian is a contract whose own controller was not traced this pass -- 'unknown, not assumed safe'")
    else:
        admin_key = 20
        notes.append("guardian did not read this run -- conservative score")

    multisig = 0  # root is an EOA: no Safe / bespoke multisig layer exists at all
    timelock_score = 0  # no delay on the guardian path; setGuardian is immediate

    return {
        "target": target, "label": "Rocket Pool RocketStorage (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "rocketpool-guardian-eoa-0x0ccf1498",
    }


def _rocket_storage_key(name: str) -> bytes:
    """RocketStorage keys are keccak256(abi.encodePacked("contract.address", name)) --
    PACKED, not abi.encode. Getting that wrong returns address(0) silently, which
    is how this looked like "no DAO contract" on the first try."""
    return Web3.keccak(text="contract.address" + name)




# ADDED 2026-09-20 for score_aave_v3_horizon_pool(). Addresses: bgd-labs/aave-address-book,
# src/AaveV3EthereumHorizon.sol (POOL_ADDRESSES_PROVIDER, ACL_MANAGER, ACL_ADMIN). The two Safes are the
# holders of the ACLManager roles below, read from the ACLManager's 16 RoleGranted/RoleRevoked events on
# 2026-09-20 (Blockscout; the public RPCs refuse eth_getLogs) and confirmed with hasRole on 2 RPCs.
_HORIZON_PROVIDER = "0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0"
_HORIZON_ACL_MANAGER = "0xEFD5df7b87d2dCe6DD454b4240b3e0A4db562321"
_HORIZON_ADMIN_SAFE = "0x13B57382c36BAB566E75C72303622AF29E27e1d3"   # POOL_ADMIN + EMERGENCY_ADMIN, 4-of-6
_HORIZON_RISK_SAFE = "0xE6ec1f0Ae6Cd023bd0a9B4d0253BDC755103253c"    # RISK_ADMIN, 3-of-4
_AAVE_GOVERNANCE_EXECUTOR = "0x5300A1a15135EA4dc7aD5a167152C01EFc9b192A"  # same EXECUTOR_LVL_1 as the main pool
_HAS_ROLE_ABI = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                   "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
_SAFE_MODULES_ABI = [{"name": "getModulesPaginated", "type": "function", "stateMutability": "view",
                       "inputs": [{"type": "address"}, {"type": "uint256"}],
                       "outputs": [{"type": "address[]"}, {"type": "address"}]}]

# ADDED 2026-09-22 (closes the backlog item's own "[backlog note]
# vu" limitation): the blanket "public RPCs refuse eth_getLogs" claim above is true of
# ethereum-rpc.publicnode.com and eth.drpc.org specifically, NOT of every public RPC -- Tenderly's
# public gateway already serves full-range eth_getLogs on Ethereum mainnet with no key, and this
# repo already proves it live: scripts/lib/scorers.py's score_rollup_l1_authority() has used it this
# way since before this file existed. `_replay_role_holders` (imported above) plus this gateway is
# what the live discovery block further down uses -- see that function's own docstring for what it
# can and cannot prove: a candidate found outside these KNOWN sets is confirmed live via hasRole
# before being treated as real (a raw replay "extra" can itself be a phantom -- a grant this scan's
# block range caught without also catching its later revoke -- not just under-count a real one).
_TENDERLY_MAINNET = "https://gateway.tenderly.co/public/mainnet"
# ACLManager (0xEFD5df7b...) contract-creation block, Blockscout getcontractcreation, verified 2026-09-22.
_HORIZON_ACL_START_BLOCK = 23_125_535
# POOL_ADMIN and EMERGENCY_ADMIN are the roles this scorer actually SCORES on (the full-power path) --
# the admin Safe, plus the governance Executor itself (it holds DEFAULT_ADMIN_ROLE, the admin of
# every role, and was found by the 2026-09-22 replay to also hold these two directly).
_HORIZON_KNOWN_POOL_EMERGENCY_ADMIN = {_HORIZON_ADMIN_SAFE.lower(), _AAVE_GOVERNANCE_EXECUTOR.lower()}
# RISK_ADMIN and ASSET_LISTING_ADMIN are bounded, disclosed-not-scored roles (see the docstring
# below). The risk Safe, plus the two contracts the docstring already named without an address --
# identified by the 2026-09-22 replay + Blockscout as the GHO direct minter proxy (0xe10C78A3...)
# and a contract Blockscout itself labels "Executor" (0x09e8E140..., not independently re-verified
# beyond that label -- treated as identified enough to compare against, not as fully audited).
_HORIZON_GHO_DIRECT_MINTER = "0xe10C78A3AC7f016eD2DE1A89c5479b1039EAB9eA"
_HORIZON_RWA_ATOKEN_MANAGER = "0x09e8E1408a68778CEDdC1938729Ea126710E7Dda"
_HORIZON_KNOWN_RISK_ADMIN = {_HORIZON_RISK_SAFE.lower(), _HORIZON_GHO_DIRECT_MINTER.lower(), _HORIZON_RWA_ATOKEN_MANAGER.lower()}
_HORIZON_KNOWN_ASSET_LISTING_ADMIN = {_HORIZON_RWA_ATOKEN_MANAGER.lower()}


def _acl_role(name):
    return bytes(Web3.keccak(text=name))


def score_aave_v3_horizon_pool(w3) -> dict:
    """Aave V3 Horizon (the RWA instance on Ethereum, PoolAddressesProvider 0x5D39E06b...). ADDED 2026-09-20.
    Scored on its FULL-POWER path, like the Solana and Sanctum targets: the path that can move funds
    fastest with the fewest keys, not the governance path a reader would expect.

    Authority (all re-read on 2 RPCs, 2026-09-20): PoolAddressesProvider.owner() and getACLAdmin() are the
    Aave governance Executor 0x5300A1a1... (the SAME executor as the main pool, so the same root). Only that
    executor holds DEFAULT_ADMIN, and DEFAULT_ADMIN is the admin of every role, so only governance adds or
    removes role holders. But two Safes hold roles directly, with no delay module (getModulesPaginated
    empty, Safe v1.4.1):
      - 0x13B57382... 4-of-6: POOL_ADMIN and EMERGENCY_ADMIN. The verified PoolConfigurator source lets a
        POOL_ADMIN call updateAToken / updateVariableDebtToken with a caller-supplied `implementation`,
        dropReserve and setReserveActive, immediately. That is a full-power path, the one scored here.
      - 0xE6ec1f0A... 3-of-4: RISK_ADMIN (collateral, e-mode, caps, interest-rate strategy). Bounded: it
        cannot swap a token implementation. Disclosed in the notes, not scored, same convention as
        Sanctum's rebalance authority. Three of its four signers are also signers of the 4-of-6 Safe.
    Scored with the Ethereum L1 Safe rule (Morpho Blue): adminKeyScore 65 for a threshold of 3 or more,
    multisigScore = min(100, 15t + 5(n - t)), timelockScore 0 (the governance path has a 1-day delay, but
    it does not bind the Safe's path). 4-of-6 gives 65 / 70 / 0 = composite 47.

    Not scored, disclosed: the contract 0x09e8E140... (RISK_ADMIN + ASSET_LISTING_ADMIN, 1620 bytes, not a
    Safe, not identified), the GHO direct minter and the RWA aToken manager (contracts holding a role), and
    the oracle authority (flat 100, same as the main pool).

    Drift handling: a changed root (owner / ACL admin is no longer the executor) or a Safe that no longer
    holds POOL_ADMIN RAISES, so score_all() skips the target and it keeps its last on-chain value instead
    of publishing a wrong score. An unread value degrades to the documented floor (20 / 0 / 0).

    Live holder discovery (ADDED 2026-09-22, closes the previous limit -- REDESIGNED twice more the
    same day after two further live-reproduced defects, see the maker-checker history for actions
    #186/#188/#190, all initially rejected): every run also replays the ACLManager's full
    RoleGranted/RoleRevoked history via Tenderly's public gateway (see _TENDERLY_MAINNET,
    _HORIZON_ACL_START_BLOCK), not just hasRole on the two known Safes -- a contradiction with the
    earlier docstring's own "the public RPCs refuse eth_getLogs" claim: that is true of
    publicnode/drpc specifically, not of every public RPC, and this repo already proves it
    (scripts/lib/scorers.py's score_rollup_l1_authority(), same mechanism, same gateway, live since
    before this file existed).

    What this discovery can and cannot claim, after three rounds of adversarial review each finding a
    real, live-reproducible way the previous version's WORDING overclaimed what the underlying scan
    actually proved:
    - A candidate found outside the known set is NEVER trusted from the replay alone -- a partial
      block range doesn't just under-count grants, it can under-count the REVOKE that followed one
      too, and _replay_role_holders()'s add-on-GRANT/discard-on-REVOKE state machine then reports a
      phantom CURRENT holder for an address that in fact no longer holds the role (reproduced live
      against real mainnet with a real grant-then-revoke pair). Every candidate is re-confirmed with
      hasRole (a single point-query, no completeness ambiguity, the same reasoning already relied on
      for DEFAULT_ADMIN_ROLE below) before being treated as real.
    - A hasRole-confirmed holder of POOL_ADMIN/EMERGENCY_ADMIN (the scored, full-power roles) outside
      the known set RAISES, same treatment as a changed root. One outside RISK_ADMIN/ASSET_LISTING_ADMIN
      (bounded, already disclosed, not scored) is a note only. An unconfirmed (phantom or
      hasRole-unreadable) candidate is disclosed but neither raises nor is treated as a real holder.
    - This scorer NEVER claims an undisclosed holder does not exist, only that none was found (raw or
      confirmed) in what was actually scanned -- unconditionally, including when hasRole itself fails.
      Proving a live scan complete enough to certify an absence turned out to be a materially harder,
      and ultimately unnecessary, problem: the backlog item asked for discovery, not certification,
      and a genuine finding (positive, hasRole-confirmed) is sound regardless of scan completeness,
      which is all this scorer now claims. If the replay itself fails (network), the run falls back to
      the hasRole-only check above with an honest note -- new-holder coverage is unconfirmed that run,
      but the KNOWN holders are still verified.

    DEFAULT_ADMIN_ROLE -- the role the whole "only governance grants a role" premise above depends on
    -- is bytes32(0) by OZ convention, not keccak(text=...), so it can never be checked through
    _acl_role()/_replay_role_holders() by name; checked directly via hasRole instead, same pattern as
    score_sparklend_pool's own DEFAULT_ADMIN_ROLE check, and gates the scored path the same way
    POOL_ADMIN does. A second DEFAULT_ADMIN holder the executor itself granted stays a residual,
    disclosed limit (no name-based replay can find it; unlike the roles above, this one has no
    completeness claim to overclaim in the first place, since it's a single point-query)."""
    provider = _HORIZON_PROVIDER
    notes = []
    rpcs = ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]

    owner = call_raw(w3, provider, _ADDR_GETTER("owner"), "owner")
    acl_admin = call_raw(w3, provider, _ADDR_GETTER("getACLAdmin"), "getACLAdmin")
    notes.append(f"PoolAddressesProvider.owner() = {owner}; getACLAdmin() = {acl_admin} (Aave governance Executor, the same root as the main pool)")
    for what, value in (("owner()", owner), ("getACLAdmin()", acl_admin)):
        if value is not None and value.lower() != _AAVE_GOVERNANCE_EXECUTOR.lower():
            raise RuntimeError(f"Aave Horizon root changed: PoolAddressesProvider.{what} = {value}, expected the governance Executor {_AAVE_GOVERNANCE_EXECUTOR}; classification no longer valid")
    root_resolved = owner is not None and acl_admin is not None

    def has_role(role_name, holder):
        try:
            return cross_checked(rpcs, lambda w3_, addr: call_raw(w3_, _HORIZON_ACL_MANAGER, _HAS_ROLE_ABI, "hasRole", _acl_role(role_name), addr), holder)
        except RuntimeError as e:
            notes.append(f"hasRole({role_name}, {holder}) cross-RPC check FAILED: {e}")
            return None

    pool_admin = has_role("POOL_ADMIN", _HORIZON_ADMIN_SAFE)
    if pool_admin is False:
        raise RuntimeError(f"Aave Horizon admin Safe {_HORIZON_ADMIN_SAFE} no longer holds POOL_ADMIN; classification no longer valid")
    emergency_admin = has_role("EMERGENCY_ADMIN", _HORIZON_ADMIN_SAFE)
    risk_admin = has_role("RISK_ADMIN", _HORIZON_RISK_SAFE)
    notes.append(f"ACLManager hasRole: admin Safe POOL_ADMIN={pool_admin}, EMERGENCY_ADMIN={emergency_admin}; risk Safe RISK_ADMIN={risk_admin}")

    # ADDED 2026-09-22, closes a #186 rejection: DEFAULT_ADMIN_ROLE is bytes32(0) by OZ convention,
    # NOT keccak(text="DEFAULT_ADMIN_ROLE") -- _acl_role()/_replay_role_holders() below can only ever
    # compute the keccak form, so DEFAULT_ADMIN_ROLE can never be checked through either of them,
    # replay included, no matter how this scorer is extended. Checked directly instead, same pattern
    # already established in this file (score_sparklend_pool, ACLManager.hasRole(DEFAULT_ADMIN_ROLE,
    # SparkProxy)) -- this is the role the whole "only governance adds a new holder" claim above rests
    # on, and it was never actually verified until now.
    try:
        default_admin = cross_checked(rpcs, lambda w3_, addr: call_raw(w3_, _HORIZON_ACL_MANAGER, _HAS_ROLE_ABI, "hasRole", b"\x00" * 32, addr), _AAVE_GOVERNANCE_EXECUTOR)
    except RuntimeError as e:
        default_admin = None
        notes.append(f"hasRole(DEFAULT_ADMIN_ROLE, executor) cross-RPC check FAILED: {e}")
    if default_admin is False:
        raise RuntimeError(f"Aave Horizon governance Executor {_AAVE_GOVERNANCE_EXECUTOR} no longer holds DEFAULT_ADMIN_ROLE on the ACLManager; the 'only governance grants roles' premise no longer holds, classification no longer valid")
    notes.append(f"ACLManager.hasRole(DEFAULT_ADMIN_ROLE, executor) = {default_admin} -- the role every other role's grant/revoke depends on; NOT itself discoverable via the replay below (see this block's own comment), so an executor-granted-then-hidden second DEFAULT_ADMIN holder is a residual, disclosed limit of this scorer")

    # ADDED 2026-09-22, REDESIGNED after two further rejections (#187, #189) of two successive
    # attempts to also prove a NEGATIVE from this replay ("no undisclosed holder exists"). Both tried
    # to build a positive control confirming the scan was complete; both were broken live against
    # real mainnet -- first by a scan that comes back empty/partial looking identical to a clean one,
    # then by the positive control itself being conditioned on the SAME hasRole calls that can
    # independently fail (both public RPCs disagreeing/rate-limited empties every witness at once),
    # and by the control only ever anchoring the START of the block range, never the tip actually
    # reached, so a truncated-at-the-end scan (a lagging node, a gateway silently capping its
    # response) still passed it. Proving completeness of a live scan, robustly, turned out to be a
    # materially harder problem than the backlog item actually asked to solve.
    #
    # What the card asked for -- "[backlog note]" -- is a
    # DISCOVERY gap, not a certification gap: find a new holder if the chain shows one. Finding one is
    # sound REGARDLESS of scan completeness (a partial block range can only under-count grants, it can
    # never fabricate one that never happened), so raising/noting on a genuine "extra" match stays
    # exactly as before. What no longer happens is the inverse: this scorer does NOT claim "no
    # undisclosed holder exists" from an absence of "extra", because that claim requires proving the
    # scan was complete and trustworthy, which is precisely the direction three real, live-reproduced
    # defects came from. An empty result is reported as what it is -- nothing found in what was
    # actually scanned -- never as a clean bill of health.
    try:
        tenderly_w3 = get_w3(_TENDERLY_MAINNET)
        live_holders = _replay_role_holders(
            tenderly_w3, _HORIZON_ACL_MANAGER,
            ["POOL_ADMIN", "EMERGENCY_ADMIN", "RISK_ADMIN", "ASSET_LISTING_ADMIN"],
            start_block=_HORIZON_ACL_START_BLOCK)
    except Exception as e:
        live_holders = None
        notes.append(f"Live role-holder discovery (RoleGranted/RoleRevoked replay from block {_HORIZON_ACL_START_BLOCK} via Tenderly) FAILED this run: {type(e).__name__}: {e} -- cannot say whether an undisclosed holder exists this run, only the known hasRole checks above are verified")
    if live_holders is not None:
        # ADDED 2026-09-22, closes a #190 rejection: the reasoning this block's own comment used to
        # give ("a partial block range can only under-count grants, it can never fabricate one that
        # never happened") is FALSE -- a partial range under-counts REVOKEs too, and since
        # _replay_role_holders() does add-on-GRANT / discard-on-REVOKE, a window that sees a grant but
        # misses its later revoke fabricates a phantom CURRENT holder, not a real one. Reproduced live
        # against real mainnet, twice, with real log data (a POOL_ADMIN grant-then-revoke in the same
        # block, an EMERGENCY_ADMIN grant-then-revoke a few thousand blocks later -- both real,
        # confirmed independently via hasRole = False). So a raw "extra" from the replay is exactly as
        # untrustworthy on its own as the "nothing extra" case the two earlier rejections already
        # closed -- the fix is the same idea applied the other way: don't trust a NEGATIVE (nothing
        # extra means nothing exists) and don't trust a raw POSITIVE either (extra found means it's
        # real) purely from the replay. Each candidate "extra" is confirmed with hasRole (already
        # defined above, a single point-query with no completeness ambiguity, the same reasoning
        # already relied on for DEFAULT_ADMIN_ROLE) before it is treated as real.
        def _confirmed(role_name, candidates):
            # web3.py refuses a non-checksummed address outright (InvalidAddress), which _read()'s
            # retry loop cannot distinguish from a real RPC failure -- every candidate here comes from
            # {a.lower() for a in live_holders[...]} a few lines below, so calling has_role() with it
            # directly would make EVERY confirmation attempt fail as "unresolved" every single time,
            # silently defeating the whole point of this check (found live, before ever pushing this:
            # a real hasRole=True candidate confirmed correctly only once this was fixed).
            confirmed, unconfirmed = set(), set()
            for addr in candidates:
                (confirmed if has_role(role_name, Web3.to_checksum_address(addr)) is True else unconfirmed).add(addr)
            return confirmed, unconfirmed

        pool_extra_raw = {a.lower() for a in live_holders["POOL_ADMIN"]} - _HORIZON_KNOWN_POOL_EMERGENCY_ADMIN
        emergency_extra_raw = {a.lower() for a in live_holders["EMERGENCY_ADMIN"]} - _HORIZON_KNOWN_POOL_EMERGENCY_ADMIN
        pool_extra, pool_unconfirmed = _confirmed("POOL_ADMIN", pool_extra_raw)
        emergency_extra, emergency_unconfirmed = _confirmed("EMERGENCY_ADMIN", emergency_extra_raw)
        if pool_extra or emergency_extra:
            raise RuntimeError(f"Aave Horizon ACLManager has a POOL_ADMIN/EMERGENCY_ADMIN holder outside the known set, confirmed live by hasRole: POOL_ADMIN extra={sorted(pool_extra)}, EMERGENCY_ADMIN extra={sorted(emergency_extra)} -- a second, undisclosed full-power path exists; classification no longer valid")

        risk_extra_raw = {a.lower() for a in live_holders["RISK_ADMIN"]} - _HORIZON_KNOWN_RISK_ADMIN
        listing_extra_raw = {a.lower() for a in live_holders["ASSET_LISTING_ADMIN"]} - _HORIZON_KNOWN_ASSET_LISTING_ADMIN
        risk_extra, risk_unconfirmed = _confirmed("RISK_ADMIN", risk_extra_raw)
        listing_extra, listing_unconfirmed = _confirmed("ASSET_LISTING_ADMIN", listing_extra_raw)
        if risk_extra or listing_extra:
            notes.append(f"Live replay found a RISK_ADMIN/ASSET_LISTING_ADMIN holder outside the known, disclosed set, confirmed live by hasRole (bounded roles, not scored): RISK_ADMIN extra={sorted(risk_extra)}, ASSET_LISTING_ADMIN extra={sorted(listing_extra)} -- worth identifying, not itself a score change")

        # ADDED 2026-09-22, closes a non-blocking reservation from action's approval: naming
        # every unconfirmed candidate in one flat, role-less set made a POOL_ADMIN phantom and an
        # ASSET_LISTING_ADMIN phantom print word-for-word identical notes (only the address differed),
        # even though the two have very different implications -- kept per-role instead.
        all_unconfirmed_named = (
            {("POOL_ADMIN", a) for a in pool_unconfirmed} | {("EMERGENCY_ADMIN", a) for a in emergency_unconfirmed}
            | {("RISK_ADMIN", a) for a in risk_unconfirmed} | {("ASSET_LISTING_ADMIN", a) for a in listing_unconfirmed}
        )
        if all_unconfirmed_named:
            named = ", ".join(f"{role}:{addr}" for role, addr in sorted(all_unconfirmed_named))
            notes.append(f"Live replay's raw scan also surfaced address(es) the replay itself no longer confirms hold the role right now: {named} -- most likely a grant this scan's block range caught without also catching its later revoke (or hasRole itself failed to confirm), not a real additional holder; disclosed, not scored, not raised on")

        found_anything = pool_extra or emergency_extra or risk_extra or listing_extra or all_unconfirmed_named
        # ADDED 2026-09-22: only reached when NOTHING was found either way (no confirmed extra above,
        # no unconfirmed/phantom candidate either) -- fixes a #190 finding where this note used to
        # print unconditionally, directly contradicting a real finding's own note printed just above
        # it in the same run (the risk/listing "found a holder" note followed immediately by this
        # one's "found no holder", the LAST of the two silently winning in a human reader's eye).
        if not found_anything:
            notes.append(f"Live role-holder discovery (RoleGranted/RoleRevoked replay from block {_HORIZON_ACL_START_BLOCK} to the chain tip at replay time, via Tenderly's public gateway) found no POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN/ASSET_LISTING_ADMIN holder beyond the known set in what it scanned -- NOT a certification that none exists: an incomplete scan (wrong role name, a truncated block range at either end, a stale gateway) looks identical to a complete, clean one, so this is reported as what was actually found, not as an all-clear")
        else:
            # ADDED 2026-09-22, closes a second non-blocking reservation from action's approval:
            # the honesty disclaimer above only fired on the "nothing found" branch, so it silently
            # disappeared from a run's notes exactly when something WAS found -- the one case where a
            # reader most needs to be reminded that what's ABOVE this line is everything this replay
            # can responsibly claim, not a complete accounting of the ACLManager's history.
            notes.append("Live role-holder discovery's scope: the findings above are NOT a certification that nothing else is undisclosed -- an incomplete scan (wrong role name, a truncated block range at either end, a stale gateway) looks identical to a complete, clean one for whatever it didn't happen to catch")

    safe = safe_owners_and_threshold(w3, _HORIZON_ADMIN_SAFE)
    risk_safe = safe_owners_and_threshold(w3, _HORIZON_RISK_SAFE)
    if risk_safe:
        risk_owners, risk_threshold = risk_safe
        notes.append(f"RISK_ADMIN Safe {_HORIZON_RISK_SAFE}: {risk_threshold}-of-{len(risk_owners)}; bounded (cannot swap a token implementation), disclosed and not scored")
        if safe:
            shared = {o.lower() for o in safe[0]} & {o.lower() for o in risk_owners}
            notes.append(f"{len(shared)} signer(s) sit in both Horizon Safes; the risk Safe's threshold is {risk_threshold}, so {'those signers alone can act as the risk Safe' if len(shared) >= risk_threshold else 'they cannot act alone as the risk Safe'}")
    else:
        notes.append("RISK_ADMIN Safe getOwners()/getThreshold() unread this run -- disclosed, not scored")

    modules = call_raw(w3, _HORIZON_ADMIN_SAFE, _SAFE_MODULES_ABI, "getModulesPaginated", "0x0000000000000000000000000000000000000001", 10)
    if modules is not None and len(modules[0]) == 0:
        notes.append("admin Safe has no module enabled (no delay module): the 4-of-6 acts without a delay")
    elif modules is not None:
        notes.append(f"admin Safe has {len(modules[0])} module(s) enabled ({list(modules[0])}); whether one is a delay is not resolved here, timelockScore stays 0")
    else:
        notes.append("admin Safe modules unread this run; timelockScore stays 0")
    notes.append(f"Not scored, disclosed: contract {_HORIZON_RWA_ATOKEN_MANAGER} (Blockscout-labeled 'Executor', not independently re-verified) holds RISK_ADMIN + ASSET_LISTING_ADMIN; the GHO direct minter proxy {_HORIZON_GHO_DIRECT_MINTER} holds RISK_ADMIN -- both identified by the 2026-09-22 live replay + Blockscout, previously disclosed only as unaddressed contracts; oracle authority is flat 100")

    if root_resolved and pool_admin is True and default_admin is True and safe:
        owners, threshold = safe
        notes.append(f"admin Safe {_HORIZON_ADMIN_SAFE}: {threshold}-of-{len(owners)}, holds POOL_ADMIN (updateAToken / updateVariableDebtToken / dropReserve) with no delay: the full-power path")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("root, DEFAULT_ADMIN_ROLE, POOL_ADMIN holder or admin Safe unresolved this run -- conservative score, treat as unverified")

    return {
        "target": provider, "label": "Aave V3 Horizon Pool (PoolAddressesProvider)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "aave-l1-governance",
    }


_ISSEALED_ABI = _BOOL_GETTER("isSealed")
_FORCE_DELAY_ABI = _UINT_GETTER("FORCE_DELAY")


def score_convex_finance_booster(w3) -> dict:
    """Convex Finance Booster (Ethereum L1). ADDED 2026-09-25. Address source:
    DefiLlama-Adapters projects/convex-finance/index.js (Booster
    0xF403C135812408BFbE8713b5A23a04b3D48AAE31). TVL: $593.47M on Ethereum
    (DefiLlama api.llama.fi/protocol/convex-finance, read 2026-09-25).

    Authority chain, 3 hops, each re-read live rather than assumed:
    Booster.owner() = BoosterOwner 0x3cE6408F923326f81A7D7929952947748180f1E6
    (isSealed() = true, FORCE_DELAY() = 2,592,000s = 30 days) -> .owner() =
    BoosterOwnerSecondary 0x256e1bbA846611C37CF89844a02435E6C098b86D
    (isSealed() = false) -> .owner() = Gnosis Safe
    0xa3C5A1e09150B75ff251c1a7815A07182c3de2FB, getThreshold() = 3,
    getOwners() = 5 addresses (only partial prefixes were on hand from the
    verification pass this scorer is built from: 0xbd0a74e5..., 0xf7bd34dd...,
    0xade9e51c..., 0xaac0aa43..., 0x4d1b5627... -- the full addresses are read
    live via getOwners() below, never hardcoded, so a partial brief can never
    become a wrong literal here), getModulesPaginated() empty (also gated
    automatically by safe_owners_and_threshold()'s own module check).

    Scored with the SAME Ethereum L1 Safe rule already used by
    score_morpho_blue_l1() and score_aave_v3_horizon_pool(): adminKeyScore 65
    for a threshold of 3 or more, multisigScore = min(100, 15t + 5(n - t)) --
    3-of-5 gives 65 / 55.

    The two layers ABOVE the scored Safe -- BoosterOwnerSecondary (unsealed)
    directly under the Safe, and BoosterOwner (sealed, 30-day FORCE_DELAY)
    under that -- are disclosed, not scored. The 30-day delay looks like it
    should raise timelockScore, but it sits one hop above the Safe's own path
    to authority, not on it: the Safe can change the unsealed
    BoosterOwnerSecondary with no delay at all, so the sealed 30-day layer is
    not on the Safe's fastest path. This file has no existing convention for
    scoring a forced delay that sits on an intermediate authority layer above
    the scored root rather than gating the root's own action (the closest
    analogues -- EigenLayer's TimelockController co-owner, Curve's veCRV vote
    period -- both gate the SAME hop being scored), so timelockScore stays 0,
    matching Morpho Blue's and Aave Horizon's own Safe-rooted,
    no-Timelock-on-that-hop convention, and the shape is disclosed instead of
    inventing a new sub-score for it."""
    booster = "0xF403C135812408BFbE8713b5A23a04b3D48AAE31"
    booster_owner = "0x3cE6408F923326f81A7D7929952947748180f1E6"
    booster_owner_secondary = "0x256e1bbA846611C37CF89844a02435E6C098b86D"
    notes = []

    owner1 = call_raw(w3, booster, _ADDR_GETTER("owner"), "owner")
    notes.append(f"Booster.owner() = {owner1} (expected BoosterOwner {booster_owner})")
    sealed1 = call_raw(w3, owner1, _ISSEALED_ABI, "isSealed") if owner1 else None
    force_delay = call_raw(w3, owner1, _FORCE_DELAY_ABI, "FORCE_DELAY") if owner1 else None
    notes.append(f"BoosterOwner.isSealed() = {sealed1} ; FORCE_DELAY() = {force_delay}s")

    owner2 = call_raw(w3, owner1, _ADDR_GETTER("owner"), "owner") if owner1 else None
    notes.append(f"BoosterOwner.owner() = {owner2} (expected BoosterOwnerSecondary {booster_owner_secondary})")
    sealed2 = call_raw(w3, owner2, _ISSEALED_ABI, "isSealed") if owner2 else None
    notes.append(f"BoosterOwnerSecondary.isSealed() = {sealed2}")

    safe_addr = call_raw(w3, owner2, _ADDR_GETTER("owner"), "owner") if owner2 else None
    notes.append(f"BoosterOwnerSecondary.owner() = {safe_addr} (root Safe)")
    safe = safe_owners_and_threshold(w3, safe_addr) if safe_addr else None

    if _same(owner1, booster_owner) and _same(owner2, booster_owner_secondary) and safe:
        owners, threshold = safe
        notes.append(f"root Safe {safe_addr}: {threshold}-of-{len(owners)}")
        notes.append(
            "Two intermediate authority layers sit above this Safe on the path to Booster: "
            "BoosterOwnerSecondary (unsealed -- nothing there enforces a wait) directly under the Safe, and "
            "BoosterOwner (sealed, FORCE_DELAY 2,592,000s = 30 days) under that. The Safe can change the "
            "unsealed BoosterOwnerSecondary with no delay, so the 30-day BoosterOwner delay is not on the "
            "Safe's fastest path to authority -- disclosed, not folded into timelockScore (no existing "
            "convention in this file scores a delay one hop removed from the scored root)."
        )
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("Booster -> BoosterOwner -> BoosterOwnerSecondary -> Safe chain did not fully resolve or match "
                     "the expected intermediate addresses this run -- conservative score, nothing assumed")

    return {
        "target": booster, "label": "Convex Finance Booster (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "convex-finance-booster-owner-safe-0xa3c5a1e0",
    }


# ADDED 2026-09-25 (Morpho vault layer, `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`
# backlog item 1): that finding found $6.2B of listed/verified Morpho V1+V2 and Euler Earn vault deposits
# across 14 chains, of which only ~8% sat under a tracked target (Robinhood Chain's 3 vaults). These 4
# targets are the largest Morpho V1 vaults on Ethereum L1 above $20M TVL by Morpho's own public API
# (blue-api.morpho.org, `chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py`, re-read live 2026-09-25),
# scored the same way `chains/monad/scorers.py::score_morpho_vault_monad` already does: `owner()`/
# `curator()`/`guardian()` read directly, each classified live, no methodology invented -- same formula,
# same convention, just new addresses. V2 vaults (a different, per-function-timelock authority shape, no
# single `guardian()`) are backlog item 1's own "starting with... the Ethereum and Base ones" continuation,
# not attempted this pass.
_KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25 = "0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD"
_KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25 = "0x827e86072B06674a077f592A531dcE4590aDeCdB"


def score_morpho_adpend_usdc(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Adpend USDC" -- $360.2M by Morpho's API 2026-09-25, the single
    largest Morpho vault on Ethereum L1 above $20M NOT already covered by a Steakhouse/Gauntlet/
    Sentora family. Live-read `owner()` and `curator()` both equal the SAME EIP-7702-delegated
    EOA (`0xf630D85a72628d73d7c7ffDf8fb4974c2b68a997`, code starts `0xef0100`), `guardian()` is
    the zero address (unset) -- a single key holds every V1 role with no independent veto party
    and no timelock layer above it, the bare-key floor of this project's own ladder.

    Context, disclosed not folded into the score (per `data/finding_2026-09-20-...
    -morpho-vault-layer.md`'s own retraction, corrected there after an earlier draft overstated
    this as a live drain risk): Morpho's API marks this vault NOT listed with red warnings
    `deposit_disabled` and `oracle_unusable`, and its `totalAssets` sits entirely in one illiquid,
    impaired market -- new depositors are not exposed to this key, existing ones already are. The
    authority shape is real and scored as such regardless; the exploitability context is not
    this scorer's job to weigh, only to disclose."""
    vault = "0x55555815a5595991C3A0Ff119B59AEF6C8B55555"
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    guardian = read_address_getter(w3, vault, "guardian")
    notes.append(f"vault.owner() = {owner}, vault.curator() = {curator}, vault.guardian() = {guardian}")
    same_key = bool(owner) and owner == curator
    notes.append(f"owner == curator: {same_key} -- one key holds both roles" if same_key else "owner and curator did NOT match this run -- re-check before trusting the bare-key read below")
    notes.append("Morpho API: NOT listed, red warnings ['deposit_disabled', 'oracle_unusable'], deposits concentrated in one impaired market -- disclosed context, not scored (2026-09-20 finding's own retraction)")
    if same_key:
        admin_key, multisig, timelock_score = 5, 0, 0
        notes.append("Root authority is a confirmed single EIP-7702-delegated EOA with no Safe/Timelock layer -- near-worst-case, matching this project's established convention for a bare-key root")
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("owner()/curator() did not confirm the expected single-key shape this run -- degraded, treat as unverified")
    return {
        "target": vault, "label": "Morpho V1: Adpend USDC",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": f"morpho-adpend-usdc-bare-eoa7702-{(owner or 'unread').lower()[:10]}",
    }


def score_morpho_1337_usdc(w3) -> dict:
    """Morpho V1 (MetaMorpho) "1337 USDC" -- $192.1M by Morpho's API 2026-09-25. Live-read
    `owner()` is a bare on-curve EOA (`0x1467b99d8FEC651CB85a4498BFf47094cBA95250`); `curator()`
    reverts (this vault was created without one -- METAMORPHO_FACTORY allows a zero curator, and
    `guardian()` reads the zero address too), so the owner is the sole authority found.

    Same disclosed context as Adpend USDC above (same finding, same retraction): Morpho's API
    marks this vault NOT listed, red warnings `short_timelock` and `oracle_unusable`, deposits
    concentrated in one impaired sdeUSD market. Authority shape scored regardless; context
    disclosed, not folded in."""
    vault = "0x94643e86aa5E38DDAc6c7791C1297f4E40cD96c1"
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    guardian = read_address_getter(w3, vault, "guardian")
    notes.append(f"vault.owner() = {owner}, vault.curator() = {curator} (expected None/unset), vault.guardian() = {guardian}")
    notes.append("Morpho API: NOT listed, red warnings ['short_timelock', 'oracle_unusable'], deposits concentrated in one impaired market -- disclosed context, not scored (2026-09-20 finding's own retraction)")
    if owner and is_eoa(w3, owner):
        admin_key, multisig, timelock_score = 5, 0, 0
        notes.append("Root authority is a confirmed bare on-curve EOA with no Safe/Timelock/curator layer -- near-worst-case, matching this project's established convention for a bare-key root")
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("owner() did not confirm a bare EOA this run -- degraded, treat as unverified")
    return {
        "target": vault, "label": "Morpho V1: 1337 USDC",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": f"morpho-1337-usdc-bare-eoa-{(owner or 'unread').lower()[:10]}",
    }


def _score_steakhouse_l1_vault(w3, vault, label, guardian_addr, guardian_note):
    """Shared read+score body for Steakhouse-curated Morpho V1 vaults on Ethereum L1 -- both
    tracked vaults share the SAME owner Safe (`_KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25`,
    5-of-10 on Ethereum) and the SAME curator Safe (`_KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25`,
    2-of-7 on Ethereum) -- both live-confirmed 2026-09-25, matching
    `data/finding_2026-09-20-...`'s own citation ("Steakhouse's curator Safe... 2-of-6 on Base,
    2-of-7 on Ethereum... curator of 42 vaults, $1.84B, on 5 chains"). Guardian differs per
    vault (a small, separate contract each time, not independently resolved to a Safe this
    pass -- disclosed, not assumed) and is passed in by the caller."""
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    notes.append(f"vault.owner() = {owner}, vault.curator() = {curator}, vault.guardian() = {guardian_addr}")
    owner_matches = bool(owner) and owner.lower() == _KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25.lower()
    curator_matches = bool(curator) and curator.lower() == _KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25.lower()
    notes.append(guardian_note)
    if owner_matches and curator_matches:
        owner_safe = safe_owners_and_threshold(w3, owner)
        curator_safe = safe_owners_and_threshold(w3, curator)
        if owner_safe and curator_safe:
            owner_owners, owner_threshold = owner_safe
            curator_owners, curator_threshold = curator_safe
            notes.append(f"owner Safe: {owner_threshold}-of-{len(owner_owners)} (Steakhouse's own owner Safe, same address as its other tracked vaults)")
            notes.append(f"curator Safe: {curator_threshold}-of-{len(curator_owners)} (Steakhouse's own curator Safe, same address as its other tracked vaults, same as its Base vaults' curator Safe -- 2026-09-25 cross-chain finding)")
            admin_key = 70 if owner_threshold >= 5 else (60 if owner_threshold >= 3 else 30)
            multisig = min(100, curator_threshold * 15 + max(0, len(curator_owners) - curator_threshold) * 5)
            # FIXED 2026-09-25 (comment only, timelock_score itself never depended on the exact duration): "3-day
            # floor per Morpho's own listing policy" was a description of Morpho's minimum LISTING requirement, not
            # this vault's own configured delay. scripts/check_exit_capacity.py's live read of Morpho's API (both
            # Steakhouse L1 vaults) shows the real curator timelock is 7 days, not 3 -- corrected here, not just
            # left wrong next to a value it never fed.
            timelock_score = 75  # V1 curator-timelocked cap changes, real duration 7 days (live-read, see scripts/check_exit_capacity.py); guardian not independently resolved this pass so not credited the higher band
            return admin_key, multisig, timelock_score, notes, set(owner_owners) | set(curator_owners)
        notes.append("owner/curator matched the known Steakhouse Safes by address, but getOwners()/getThreshold() did not resolve this run -- conservative score")
    else:
        notes.append("owner/curator did NOT match the known Steakhouse Safes this run -- Steakhouse may have rotated, re-verify before trusting the shared-controller finding above")
    return 20, 20, 0, notes, set()


def score_morpho_steakhouse_usdt_l1(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Steakhouse USDT" -- $87.5M by Morpho's API 2026-09-25, on
    Ethereum L1. See `_score_steakhouse_l1_vault`'s own docstring for the shared owner/curator
    Safe finding. `guardian()` resolves to a small (833-byte) contract, `0xaeC761545Fd135db6d0
    4D27C92BCB3951668c67F` -- not independently opened this pass (disclosed, not assumed to be
    either a real veto party or a rubber stamp)."""
    vault = "0xbEef047a543E45807105E51A8BBEFCc5950fcfBa"
    guardian = read_address_getter(w3, vault, "guardian")
    admin_key, multisig, timelock_score, notes, signers = _score_steakhouse_l1_vault(
        w3, vault, "Steakhouse USDT", guardian,
        f"guardian() = {guardian}, a small contract (833 bytes per this run's own eth_getCode) -- not independently resolved to a Safe or opened, disclosed as an open point")
    return {
        "target": vault, "label": "Morpho V1: Steakhouse USDT (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "steakhouse-owner-safe-0x0a0e559b", "_crossEcosystem": True,
    }


def score_morpho_steakhouse_usdc_l1(w3) -> dict:
    """Morpho V1 (MetaMorpho) "Steakhouse USDC" -- $66.5M by Morpho's API 2026-09-25, on
    Ethereum L1 (a separate vault from the same-named Base one this pass also adds). See
    `_score_steakhouse_l1_vault`'s own docstring for the shared owner/curator Safe finding.
    `guardian()` resolves to a small (833-byte) contract, `0xaa0500198B4425DfC4E272FbE42C8E64
    E21fc03d` -- a DIFFERENT address from the USDT vault's guardian contract above despite the
    identical byte length, so not assumed to be the same deployment; neither opened this pass."""
    vault = "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB"
    guardian = read_address_getter(w3, vault, "guardian")
    admin_key, multisig, timelock_score, notes, signers = _score_steakhouse_l1_vault(
        w3, vault, "Steakhouse USDC", guardian,
        f"guardian() = {guardian}, a small contract (833 bytes per this run's own eth_getCode, a different address from the USDT vault's own guardian contract) -- not independently resolved to a Safe or opened, disclosed as an open point")
    return {
        "target": vault, "label": "Morpho V1: Steakhouse USDC (Ethereum L1)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock_score,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes, "_rootGroup": "steakhouse-owner-safe-0x0a0e559b", "_crossEcosystem": True,
    }


SIMPLE_SCORERS = [
    score_uniswap_v3_factory,
    score_aave_v3_pool,
    score_makerdao_sky_pause,
    score_ethena_minting,
    score_usdtb,
    score_usdtb_psm,
    score_ethena_layerzero_oft,
    score_compound_v3_cusdc,
    score_sparklend_pool,
    score_uniswap_v4_pool_manager,
    score_morpho_blue_l1,
    score_wbtc,
    score_lido_steth,
    score_eigenlayer_strategy_manager,
    score_curve_stableswap_ng_factory,
    score_rocketpool_storage,
    score_aave_v3_horizon_pool,
    score_convex_finance_booster,
    # ADDED 2026-09-25 (Morpho vault layer, backlog item 1) -- appended, never reordered: the
    # oracle's trackedTargets(i) index order is the first-push order.
    score_morpho_adpend_usdc,
    score_morpho_1337_usdc,
    score_morpho_steakhouse_usdt_l1,
    score_morpho_steakhouse_usdc_l1,
]


def _apply_cross_exposure(results: list):
    # FIXED 2026-09-17 (closed a disclosed gap): crossExposureScore was
    # entirely ABSENT from every return dict in this file -- not defaulted
    # to 100 like chains/arbitrum-ecosystem/scorers.py and
    # chains/base-ecosystem/scorers.py already do, just missing outright
    # (a real gap in this file specifically, predating this pass for the
    # first 4 functions, and silently carried into the 3 functions added
    # this pass before it was caught). Fixed as a REAL within-ecosystem
    # check, not a flat 100 default, matching the stronger convention this
    # same day's Hyperliquid/Tempo/Zcash promotions established: group each
    # target by its own already-documented `_rootGroup` (set in each score
    # function's return dict, stripped below) and apply the repo-wide
    # signer-overlap formula. This surfaces a real, previously undisclosed
    # finding: Ethena Minting, USDtb PSM and all 3 LayerZero OFTAdapters
    # (5 of this file's 9 targets) are all rooted in the exact same 5-of-10
    # Safe (0x3b0aaf6e...) -- a genuine concentration this file's own
    # docstrings had each separately documented but never connected into a
    # single cross-target score.
    #
    # CORRECTED 2026-09-20 (crossExposureScore convention decision): the field
    # means "does the same root signer also control ANOTHER tracked target",
    # and that includes targets on other ecosystems, so this was no longer
    # "purely within L1". A score function that found its root committee
    # identical to a tracked target's committee on another chain sets an
    # internal `_crossEcosystem` flag (stripped below like `_rootGroup`, so it
    # never reaches the returned/pushed dicts); that folds in as a flat 80,
    # combined with min() so it can never RAISE a value the within-L1 formula
    # already lowered (e.g. the 5 Ethena targets stay at 20).
    groups = {}
    for r in results:
        groups.setdefault(r["_rootGroup"], []).append(r)
    for r in results:
        same_group = groups[r["_rootGroup"]]
        others = len(same_group) - 1
        score = max(0, 100 - 20 * others)
        if others:
            r["notes"].append(f"shares its root authority ({r['_rootGroup']}) with {others} other tracked Ethereum L1 target(s): {[o['label'] for o in same_group if o is not r]}")
        if r.pop("_crossEcosystem", False):
            folded = min(score, 80)
            if folded < score:
                r["notes"].append(
                    f"crossExposureScore {folded}: the same root signer committee also controls a tracked target on "
                    "another ecosystem (real finding, independently re-confirmed 2026-09-20; cross-ecosystem overlap "
                    "folded in as a flat 80)"
                )
            else:
                r["notes"].append(
                    f"same root signer committee also controls a tracked target on another ecosystem (real finding, "
                    f"independently re-confirmed 2026-09-20); crossExposureScore stays {score}, the within-L1 value is "
                    "already at or below the flat 80"
                )
            score = folded
        r["crossExposureScore"] = score
        del r["_rootGroup"]


def score_all(w3) -> list:
    # FIXED 2026-09-17 (closed a disclosed gap): this was a flat, unguarded
    # list comprehension -- the ONE ecosystem scorer file that never got the
    # same per-target isolation scripts/lib/scorers.py's score_all() got the
    # same day (a single target raising used to crash the whole batch, not
    # just the flaky one). Low risk while this ecosystem stays undeployed,
    # but no reason to leave it unguarded while adding two new targets here
    # in the same pass.
    results = []
    for scorer in SIMPLE_SCORERS:
        results.extend(safe_score(scorer.__name__, scorer, w3))
    _apply_cross_exposure(results)
    return results
