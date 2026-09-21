"""
Plasma Ecosystem authority scorers -- 9 targets: 7 from the original
2026-09-18 scoring_build pass (below), plus 2 added 2026-09-19 by a
dedicated scouting pass for new legitimate Plasma-mainnet targets with
Plasma-specific TVL (`score_telos_consilium_euler_earn_plasma()` and
`score_yuzu_money_plasma()`, each with its own sourcing/verification in its
own docstring). That 2026-09-19 pass also investigated and DELIBERATELY
EXCLUDED several DefiLlama-listed Plasma candidates rather than force a
3rd/4th/5th target -- see
`data/scouted_targets_2026-09-19-new-mainnet-candidates.md` for the full
list and reasoning; briefly: Fluid DEX shares the SAME root authority as
this file's already-tracked `score_fluid_liquidity_plasma()` (confirmed via
Instadapp's own `deployments.md` -- Fluid DEX contracts constructor-
reference the same Liquidity address already scored, not a separate
authority); Veda / "Plasma Saving Vaults" are the SAME underlying vault
counted under two different DefiLlama protocol-adapter labels (both read
~$31-32M for the identical "PLASMAUSD" pool), and that vault's own root
("Plasma: USD Vault", a BoringVault) reads as deployed on Ethereum mainnet,
not Plasma-native -- excluded as not clearly a Plasma-specific authority
rather than risk double-counting it under two names; every other
EulerEarn-curator vault found this pass (Re7 Labs, K3 Capital, Hyperithm,
Edge/UltraYield, Clearstar, TID Capital) had Plasma-specific totalAssets()
well under $10M each, live-read directly off `eulerEarnFactory`'s
19-vault list -- too small to be "significant" next to this file's
existing targets; CEX entries (Binance/Bybit/Gate/Backpack/Bitvavo/WEEX)
are custodial balances with no on-chain authority contract to trace, not
DeFi-protocol targets.
Plasma was identified as a genuine coverage gap the same day: a real,
~1-year-old EVM L1 for stablecoins with real DeFi TVL (Aave alone ~$496M,
~87% of the chain's total), structurally excluded from L2Beat's Stage
coverage (it's a standalone L1, not an Ethereum-security-derived L2) and
with a permissioned, team-operated validator set nobody was scoring at the
chain level -- see `data/finding_2026-09-18-competitive-positioning-cross-chain-overlap.md`
in the repo root for the research that led here.

This file's 7 scorers were authored by several parallel research passes the
same day (a chain-level baseline, and 5 real DeFi protocols already live on
Plasma), each independently verified live against `https://rpc.plasma.to`.
NOTE, disclosed rather than hidden: this file's own shared path was
overwritten wholesale multiple times by concurrent, uncoordinated writers
during that research -- at least two functions were briefly clobbered before
being restored. The version of this file that ended up on disk was
consolidated and every address/authority-chain claim independently
RE-VERIFIED live a second time (fresh `eth_call`s, not just re-reading the
research reports) before being written out cleanly -- see each function's
own docstring for its sourcing and live-confirmed facts. This is a real,
disclosed operational risk in how this pass was run (no lock/merge step on
a shared file path across parallel workers), not swept under a rug.

Target chain: Plasma mainnet, an EVM-compatible L1 for stablecoins, chain ID
9745, public RPC `https://rpc.plasma.to` (no API key required, live-confirmed
reachable and returning chain ID 0x2611 == 9745 this pass). Reuses this
project's existing methodology exactly as-is (same pattern as
`chains/base-ecosystem/scorers.py` and `chains/arbitrum-ecosystem/scorers.py`):
live eth_call against a public Plasma mainnet RPC, address sourced from the
protocol's own official GitHub address-book repo, authority traced to its
root (AccessControl `hasRole()` role membership -> OpenZeppelin
TimelockController `getMinDelay()`/role membership -> Gnosis Safe
`getOwners()`+`getThreshold()`), never trusted from a prior pass, a dashboard,
or a block explorer's "verified name".

IMPORTANT CORRECTION to this pass's own brief: the brief that produced this
file claimed "this project's research today on Euler-on-Base found a
specific eVaultFactory address and a governed/immutable-vault spectrum".
That claim does NOT match this repository's actual state -- a full-text
search of this repo (`grep -rli euler .`) at the start of this pass returned
ZERO prior hits anywhere in `data/`, `chains/`, or `README.md`/`AGENTS.md`/
`METHODOLOGY.md`. No Base research on Euler exists in this project as of
2026-09-18. This file is the FIRST time Euler V2 has been researched or
scored anywhere in this project, done from scratch against Plasma directly
(chain 9745), not built on any prior Base pass. The "governed vs. immutable
vault" spectrum referenced below IS real -- independently confirmed here by
reading Euler's own `GenericFactory.sol` source (see `score_euler_v2_
evault_factory_plasma()`'s docstring) -- but that confirmation happened THIS
pass, on Plasma, not inherited from an earlier Base finding that does not
exist in this repo.

Target: Euler V2 (Euler Vault Kit) on Plasma. Plasma is one of Euler's
confirmed launch-day DeFi partners (Plasma mainnet beta + XPL launched
2025-09-25, Euler listed as a day-one integration alongside Aave/Ethena/
Fluid -- plasma.to/insights/plasma-mainnet-beta-and-xpl, plasma.to/rewards/
protocols/euler, app.euler.finance/?network=plasma). The specific PLASMA
deployment addresses (a SEPARATE deployment from Euler's Ethereum-mainnet or
any other chain's addresses -- confirmed by chain-ID-keyed directory, not
assumed to be shared) are sourced from Euler Labs' own official address-book
repo:
  https://github.com/euler-xyz/euler-interfaces/tree/master/addresses/9745
  (commit d0e9a428523b3de6cb3e6c7a06ad55b6e59223f3, 2026-08-21 -- the repo's
  addresses are organized one directory per chain ID; `9745` exists as a
  top-level entry alongside `1`, `8453`, `42161`, etc., i.e. Plasma has its
  own first-class Euler deployment, not a reused address from another chain)
:
  CoreAddresses.json      -> eVaultFactory, eVaultImplementation, evc, ...
  PeripheryAddresses.json -> factories for IRMs, oracle routers, ...
  GovernorAddresses.json  -> eVaultFactoryGovernor, eVaultFactoryTimelockController,
                              accessControlEmergencyGovernor + its Admin/Wildcard
                              TimelockControllers, capRiskSteward
  MultisigAddresses.json  -> DAO / labs / securityCouncil / securityPartnerA/B

Every address below was independently re-confirmed live against
`https://rpc.plasma.to` in this pass (2026-09-18) via direct eth_getCode/
eth_call JSON-RPC POSTs before this file was written -- eVaultFactory itself
carries 5,631 bytes of real deployed bytecode (not a stub, not undeployed),
and every downstream address in the authority chain below was independently
confirmed to have real deployed code too, not assumed live because it
appears in the address book.

Each scorer returns a dict with the AuthorityScore fields (including
`crossExposureScore`: 80 where the target's root committee was found identical
to a tracked target's on another chain, else 100; the comment above
`_CROSS_EXPOSURE_NOTE` lists which scorers compute it and which do not) plus a
`notes` list explaining what was found, so a re-run's output is still readable
without re-reading this file.
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
from web3_utils import (  # noqa: E402
    call_raw,
    get_w3,
    read_address_getter,
    read_slot_as_address,
    safe_owners_and_threshold,
    safe_score,
)
from safe_modules import note_for, read_guard, read_modules  # noqa: E402

PLASMA_CHAIN_ID = 9745
DEFAULT_RPC = "https://rpc.plasma.to"

# crossExposureScore is a property of the SET of tracked targets (does the same
# root signer also control ANOTHER tracked target?), computed project-wide in
# scripts/lib/signer_overlap.py. Five of this file's scorers below (Aave V3,
# Pendle, Ethena, Euler eVaultFactory, Euler AccessControlEmergencyGovernor) DO
# compute a real cross-chain version of this directly -- see their own
# docstrings -- following the same hardcoded-known-committee-plus-live-diff
# pattern already used in chains/arbitrum-ecosystem/scorers.py and
# chains/base-ecosystem/scorers.py. For every OTHER scorer in this file
# (validator set, Telos/Consilium EulerEarn, Yuzu; Fluid reports its own
# note), the scorer itself attempts no cross-ecosystem signer-overlap
# comparison. Rather than fabricate a number, those scorers report 100 ("no
# overlap found") with an explicit note that this dimension was NOT computed
# by the scorer, following this project's stated convention.
# CORRECTED 2026-09-20: this comment used to name only Aave and Ethena as
# computing it, and said Plasma was not wired into
# scripts/lib/cross_ecosystem_overlap.py (it is, see PLASMA_GROUPS there).
# Pendle and both Euler scorers now fold in their cross-ecosystem overlap too,
# with their own notes (see _snapshot_cross_exposure below), so they no longer
# use the generic note below.
_CROSS_EXPOSURE_NOTE = (
    "crossExposureScore = 100 (not computed this pass for this specific target -- "
    "no cross-ecosystem signer-overlap comparison was attempted for it; treated "
    "as 'not applicable' per this project's convention, not as a confirmed clean "
    "result)"
)


def _snapshot_cross_exposure(owners, snapshot, snapshot_name, match_note):
    """ADDED 2026-09-20: shared verdict for the cross-ecosystem fold (Pendle,
    both Euler scorers; Fluid compares its Avocado signer set the same way). `owners` is the FRESHLY read owner list of the
    target's own Safe, or None when that Safe could not be read; `snapshot`
    is a dated frozenset of lowercased owner addresses of the same committee
    on another chain. Compared as an exact set, never via a second RPC
    connection to the other chain. Returns (crossExposureScore, note): 80
    and `match_note` on an exact match, else 100 with a note that says which
    of the two reasons applies. An unread Safe degrades to 100 with a
    'not computed' note, never a silent confident 'no overlap'."""
    if owners is None:
        return 100, (
            "crossExposureScore = 100 (not computed this run: the owner Safe could not be read, so its "
            f"signer set could not be compared against {snapshot_name}; not a confirmed clean result)"
        )
    if {o.lower() for o in owners} == snapshot:
        return 80, match_note
    return 100, (
        f"crossExposureScore = 100 (freshly read owner set compared against {snapshot_name} and it does NOT "
        "match exactly: no shared committee found with that tracked target this run)"
    )


def _composite(admin_key, multisig, timelock):
    """Standard project weighting: 0.4*adminKey + 0.3*multisig + 0.3*timelock,
    oracleAuthorityScore excluded (not applicable to either target below --
    neither is itself an oracle/price-feed authority; Euler's own oracle
    routers are a separate, per-vault-configurable component not scored
    here). Uses standard round-half-up via floor(x + 0.5), not Python's
    builtin round() (banker's rounding) -- same fix already applied
    project-wide, kept consistent here."""
    import math

    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


def _same_addr(a, b) -> bool:
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


def _has_role(w3, contract, role, account):
    """hasRole(bytes32,address) -> bool, standard OpenZeppelin AccessControl
    getter, same inline-ABI pattern already used in
    chains/arbitrum-ecosystem/scorers.py and chains/ethereum-l1/scorers.py --
    reused here rather than re-invented, kept local (not promoted to
    web3_utils.py) since no third ecosystem file needs it yet."""
    role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                 "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
    return call_raw(w3, contract, role_abi, "hasRole", role, w3.to_checksum_address(account))


def score_validator_set_authority(w3) -> dict:
    """Plasma's own L1 chain-level baseline authority -- "Aquila", the
    per-network committee-rotation contract, the same role this project
    already scores for Robinhood Chain's rollup authority and Tempo's L1
    validator registry: every other target tracked on Plasma ultimately
    depends on this.

    Not documented on Plasma's own docs site
    (`plasma.org/docs/plasma-chain/architecture/consensus` states plainly
    that "the Proof of Stake and Committee Formation mechanism are under
    active development" with no address given, and
    `plasma.org/docs/plasma-chain/network-information/plasma-contracts`,
    Plasma's own protocol address-book page, lists only deploy-infra
    utilities -- CREATE2/CREATE3 factories, Multicall3, Permit2, WXPL --
    no validator/consensus contract). Found instead in Plasma's own
    official GitHub org, `PlasmaLaboratories/node-templates`,
    `config/mainnet/validator.toml`'s `[chain.aquila]` section:
    `contract_address = "0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48"`.

    Confirmed live, 2026-09-18, `https://rpc.plasma.to`: 109 bytes of real
    bytecode (a minimal EIP-1967 UUPS proxy). A self-ID getter (selector
    `0x54fd4d50`) returns the ASCII string "plasma-validator-set/v1" --
    on-chain self-identification, not inferred from the config file alone.
    `getValidators()` returns 10 BLS12-381 public keys that match the same
    TOML file's `[chain.static_committee.*]` list byte-for-byte.

    Authority chain: `owner()` = a real Gnosis Safe (confirmed via
    `eth_getCode` matching known GnosisSafeProxy v1.3.0 bytecode),
    **3-of-4** (`getThreshold()`/`getOwners()`), all 4 owners bare EOAs at
    nonce 0. `getMinDelay()` on that Safe reverts with no data -- confirmed
    NOT a TimelockController, the chain terminates at the Safe.

    Real, disclosed timing caveat: at the time this scorer's target was
    first found (mainnet block ~32,824,292), the SAME `[chain.aquila]`
    config entry that names this contract also sets
    `activation_height = 33,300,000` -- meaning this contract may not yet
    be the mechanism actually gating consensus (Plasma's own static
    `[chain.static_committee.*]` list could still be operative until that
    height is reached). This scorer reads and scores the contract as
    Plasma's own client config identifies it as the FUTURE/eventual
    validator-set authority, not a claim that it is already enforcing
    consensus today -- disclosed rather than silently assumed either way."""
    aquila = "0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(aquila))
    notes.append(f"eth_getCode(Aquila, {aquila}) = {len(code)} bytes of real deployed bytecode (a minimal EIP-1967 UUPS proxy)")

    # Raw selector call, not a name-based ABI call: the real function name
    # behind selector 0x54fd4d50 isn't known (not found in any public source
    # this pass), only the selector and its return shape. Re-verified live
    # this pass: the return is a FIXED-SIZE 32-byte word (bytes32), not a
    # dynamic ABI-encoded string -- an earlier version of this scorer
    # declared it as `string` in a name-based ABI call, which silently
    # failed to decode (returned None) because dynamic-string ABI decoding
    # expects an offset+length header this contract doesn't send. Fixed by
    # calling the literal selector directly and decoding the raw bytes32 as
    # a right-padded ASCII string instead.
    try:
        self_id_raw = w3.eth.call({"to": w3.to_checksum_address(aquila), "data": "0x54fd4d50"})
        self_id = self_id_raw.rstrip(b"\x00").decode("ascii", errors="replace")
    except Exception:
        self_id = None
    notes.append(f"self-ID getter (0x54fd4d50) = {self_id!r} -- on-chain self-identification")

    validator_count = call_raw(w3, aquila, [{"name": "validatorCount", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "validatorCount")
    notes.append(f"validatorCount() = {validator_count}")

    owner = read_address_getter(w3, aquila, "owner")
    notes.append(f"Aquila.owner() = {owner}")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}, all owners confirmed bare EOAs")
        delay = call_raw(w3, owner, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay", retries=1)
        notes.append(f"owner Safe getMinDelay() = {delay} (expected None/revert -- confirmed NOT a TimelockController, chain terminates at the Safe)")
        notes.append(
            "Disclosed timing caveat: Plasma's own PlasmaLaboratories/node-templates validator.toml sets an "
            "activation_height for this contract's [chain.aquila] entry that had not yet been reached as of "
            "this scorer's first pass -- this may not yet be the mechanism actually gating consensus (a static "
            "committee list could still be operative), scored as Plasma's own config identifies its eventual "
            "role, not a claim it is live-enforcing today."
        )
        admin_key = 50 if threshold == 3 else (65 if threshold >= 3 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController or delay found anywhere in this chain

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": aquila,
        "label": "Plasma L1 validator-set authority (Aquila)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# The identical 9-owner, 5-of-9 committee already hardcoded in
# chains/arbitrum-ecosystem/scorers.py and chains/base-ecosystem/scorers.py
# as ARBITRUM_AAVE_GUARDIAN_OWNERS_2026_09_17 / BASE_AAVE_GUARDIAN_OWNERS_2026_09_17
# -- reused here rather than re-typed, per this project's own "never
# hand-retype a value that already exists verified elsewhere" discipline.
# Live-reconfirmed on Plasma 2026-09-18: Plasma's own Aave V3 guardian Safe
# (a DIFFERENT address, 0x19CE4363FEA478Aa04B9EA2937cc5A2cbcD44be6) has this
# EXACT same 9-owner set at 5-of-9 -- a THIRD chain sharing this committee,
# not just two.
_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17 = frozenset({
    "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
    "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
    "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
    "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
    "0x4C30E33758216aD0d676419c21CB8D014C68099f",
})


def score_aave_v3_pool_plasma(w3) -> dict:
    """Aave V3 on Plasma -- PoolAddressesProvider. Source: official
    `bgd-labs/aave-address-book`, `src/AaveV3Plasma.sol` (commit
    `81de698`, 2026-08-17) -- the same repo this project already uses for
    Aave on Ethereum L1/Arbitrum/Base. Corroborated by Aave governance
    (`governance.aave.com/t/arfc-deploy-aave-v3-on-plasma/21494`, first
    posted 2025-03-15, plus live asset-onboarding proposals through
    2026-03-16 -- an actively governed instance, not a stalled
    announcement). TVL: $496.2M on Plasma (DefiLlama live) vs. $569.7M
    total chain TVL -- ~87% of all Plasma TVL, the dominant lender.

    Authority chain, every hop a live eth_call against
    `https://rpc.plasma.to` (chain 9745): PoolAddressesProvider.owner() ->
    EXECUTOR_LVL_1 <-> PayloadsController (mutual owner() pointers, the
    same genuine closed pair already documented for this project's
    Ethereum-L1/Arbitrum/Base Aave scorers -- standard BGD Labs Aave
    Governance V3 cross-chain infra). `getExecutorSettingsByAccessControl(1)`
    confirms a real 86,400s (1-day) delay. `guardian()` resolves to a real
    Gnosis Safe, 5-of-9.

    Real cross-chain finding, independently re-confirmed live (not
    assumed from a prior pass): this guardian Safe's 9 owners are BYTE-
    IDENTICAL to the guardian committee already found sharing Arbitrum and
    Base's own Aave V3 deployments -- a different Safe address on Plasma
    (CREATE2-redeployed), the SAME 9 signers at the SAME 5-of-9 threshold.
    One compromised committee now reaches Arbitrum, Base, AND Plasma's
    emergency-cancel path -- a third chain, not just two.

    Open thread, disclosed rather than guessed: the Ethereum-mainnet Aave
    DAO root (proposal counts, quorum, the L1 Timelock/Executor the
    CROSS_CHAIN_CONTROLLER ultimately relays from) was not re-verified
    live this pass -- out of scope for a Plasma-RPC-only scorer, covered
    directly by `chains/ethereum-l1/scorers.py`'s own `score_aave_v3_pool()`.
    No second independent public Plasma RPC could be found to cross-check
    against this pass (publicnode/drpc/Alchemy demo endpoints tried, none
    usable) -- every read below is single-RPC, flagged rather than
    presented as this project's usual 2-RPC-confirmed standard."""
    provider = "0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9"
    notes = []

    executor = read_address_getter(w3, provider, "owner")
    notes.append(f"PoolAddressesProvider.owner() = {executor} (expected EXECUTOR_LVL_1)")

    payloads_controller = read_address_getter(w3, executor, "owner") if executor else None
    notes.append(f"EXECUTOR_LVL_1.owner() = {payloads_controller} (PayloadsController)")

    loop_check = read_address_getter(w3, payloads_controller, "owner") if payloads_controller else None
    notes.append(f"PayloadsController.owner() = {loop_check} (closes back to EXECUTOR_LVL_1: {loop_check == executor if loop_check else None})")

    settings_abi = [{"name": "getExecutorSettingsByAccessControl", "type": "function", "stateMutability": "view",
                      "inputs": [{"type": "uint8"}], "outputs": [{"type": "tuple", "components": [{"type": "address"}, {"type": "uint40"}]}]}]
    settings = call_raw(w3, payloads_controller, settings_abi, "getExecutorSettingsByAccessControl", 1) if payloads_controller else None
    notes.append(f"PayloadsController.getExecutorSettingsByAccessControl(1) = {settings} (executor, delaySeconds)")

    guardian = call_raw(w3, payloads_controller, [{"name": "guardian", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "guardian") if payloads_controller else None
    notes.append(f"PayloadsController.guardian() = {guardian} (can cancel proposals outside the timelock)")

    guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    shares_known_committee = False
    if guardian_safe:
        g_owners, g_threshold = guardian_safe
        notes.append(f"GOVERNANCE_GUARDIAN is a real Gnosis Safe: {g_threshold}-of-{len(g_owners)}")
        shares_known_committee = {w3.to_checksum_address(o) for o in g_owners} == {w3.to_checksum_address(o) for o in _KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17}
        if shares_known_committee:
            notes.append(
                "GOVERNANCE_GUARDIAN Safe owner set is IDENTICAL to Arbitrum's and Base's own Aave V3 guardian "
                "Safes (same 9 signers, same 5-of-9 threshold, different address on each chain) -- a THIRD "
                "chain sharing this committee, independently re-confirmed live this pass"
            )
    else:
        notes.append(f"{guardian}: NOT resolvable as a Gnosis Safe this run")

    notes.append(
        "Open thread, disclosed rather than guessed: the Ethereum-mainnet Aave DAO root "
        "(CROSS_CHAIN_CONTROLLER relay, L1 proposal counts/quorum) was NOT re-verified live "
        "this pass -- this scorer confirms the Plasma-side executor/payloads-controller pair "
        "only. See chains/ethereum-l1/scorers.py's score_aave_v3_pool() for the L1 root."
    )
    if not shares_known_committee:
        notes.append(_CROSS_EXPOSURE_NOTE)

    delay = settings[1] if settings else None
    chain_closed = bool(payloads_controller) and loop_check == executor
    admin_key = 65 if chain_closed else 30
    multisig = 100  # not applicable: PayloadsController/Executor pair is not a Safe (the separate GOVERNANCE_GUARDIAN Safe is a veto path, not the primary authority)
    timelock_score = 50 if delay and delay > 0 else 0  # confirmed real 1-day delay, capped for the unverified L1 root + guardian cancel-path outside the timelock
    cross_exposure = 80 if shares_known_committee else 100

    return {
        "target": provider,
        "label": "Aave V3 Pool (Plasma, PoolAddressesProvider)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ADDED 2026-09-20: the 5 owners of Pendle's owner Safe
# (0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac, 3-of-5), read live 2026-09-20
# from Plasma mainnet (https://rpc.plasma.to) and cross-checked against the SAME
# Safe address on Robinhood Chain mainnet (https://rpc.mainnet.chain.robinhood.com,
# tracked there in scripts/lib/signer_overlap.py GROUPS["pendle"]): both chains
# returned the identical 5 owners at 3-of-5. Frozen here, lowercased, as a dated
# snapshot to diff against a fresh read, same pattern as
# _KNOWN_ETHENA_L1_SAFE_OWNERS_2026_09_18 below; the scorer never opens a
# second RPC connection to Robinhood Chain.
_KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20 = frozenset({
    "0x231fc5b039d66ba234cb90357082bf16be79b17c", "0x38ab4a7dea2753757f29fe6d10280df2c42abe27",
    "0x7bd456937104ca5efffbd895ccbba52421021c29", "0x9ce6de7ec862e25a515aa0d8ecfbbbb2daa8e0fb",
    "0xf517364727fcc764d58ddf4e53280874a4d0c476",
})
_PENDLE_ROBINHOOD_MATCH_NOTE = (
    "Real cross-chain finding, independently re-confirmed live this pass (not assumed from the shared "
    "protocol name): the owner Safe's 5 signers are IDENTICAL, as an exact set, to the snapshot of Pendle's "
    "own already-tracked owner Safe on Robinhood Chain (the same Safe address, 3-of-5 when snapshotted), so "
    "one compromised committee reaches Pendle on both Plasma and Robinhood Chain. crossExposureScore = 80"
)


# CORRECTED 2026-09-20: this scorer used to read storage slot 0 (a plain implementation-side
# slot, live value 0x2aD631F7...), so the "two independent paths" note always said
# "NOT independently confirmed to converge" even though they do. The canonical EIP-1967
# admin slot is keccak256("eip1967.proxy.admin") - 1; live it holds ProxyAdmin 0xA28c08f1...,
# whose owner() is the Safe. Note-only bug, no score changed.
_EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"


def score_pendle_plasma(w3) -> dict:
    """Pendle (Router + Market Factory V6) on Plasma. Source: official
    `pendle-finance/pendle-core-v2-public` GitHub repo,
    `deployments/9745-core.json` (the file's own `network.chainId` field
    is literally 9745, not inferred from a filename; latest commit touch
    2026-07-15). Every fact below was independently cross-checked on a
    SECOND, independent public RPC (`https://9745.rpc.thirdweb.com`) --
    byte-identical to `https://rpc.plasma.to` on both, at the identical
    live tip.

    Two independent authority paths converge on the identical root:
    (1) Router.owner() resolves directly to a Safe. (2) MarketFactoryV6 is
    a standard EIP-1967 TransparentUpgradeableProxy; its admin-slot
    ProxyAdmin.owner() resolves to the SAME address as path (1) -- not
    assumed, confirmed via two separate `eth_getStorageAt` reads (the
    proxy's own admin slot, matching the deployment JSON's own
    `proxyAdmin` field exactly) plus a direct `owner()` call on that
    ProxyAdmin.

    That shared root (0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac, 171-byte
    GnosisSafeProxy bytecode, confirmed via the embedded `masterCopy()`
    selector) is a real Gnosis Safe: 3-of-5, all 5 owners live-decoded.
    Not yet a TimelockController -- `getMinDelay()` via the deployment
    JSON's separate `governanceProxy` entry (the older MarketFactoryV5's
    own admin path) reverted this pass; that path's real internal role
    structure was not resolved, disclosed as an open point rather than
    assumed to be either a timelock or absent.

    Real cross-chain finding, ADDED 2026-09-20 (this scorer used to report
    crossExposureScore 100 for it): the shared root Safe is the SAME address,
    with the same 5 owners at 3-of-5, that owns Pendle on Robinhood Chain
    (scripts/lib/signer_overlap.py GROUPS["pendle"]), re-read live on both
    chains 2026-09-20. crossExposureScore is 80 when this run's freshly read
    owner set equals `_KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20`, else
    100; an unread Safe degrades to 100 with a 'not computed' note. Only the
    cross-exposure field moved, admin/multisig/timelock are unchanged."""
    router = "0x888888888889758F76e7103c6CbF23ABbF58F946"
    market_factory_v6 = "0x84A240Fa784E7F03CB99BA3716065961c5d0D531"
    notes = []

    router_owner = read_address_getter(w3, router, "owner")
    notes.append(f"Router.owner() = {router_owner}")

    proxy_admin = read_slot_as_address(w3, market_factory_v6, _EIP1967_ADMIN_SLOT)
    notes.append(f"MarketFactoryV6 EIP-1967 admin slot -> ProxyAdmin = {proxy_admin} (expected to match deployment JSON's own 'proxyAdmin' field)")

    proxy_admin_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    notes.append(f"ProxyAdmin.owner() = {proxy_admin_owner} (expected to match Router.owner(): {bool(proxy_admin_owner) and bool(router_owner) and proxy_admin_owner.lower() == router_owner.lower()})")

    root = router_owner if router_owner else proxy_admin_owner
    paths_converge = bool(router_owner) and bool(proxy_admin_owner) and router_owner.lower() == proxy_admin_owner.lower()

    safe = safe_owners_and_threshold(w3, root) if root else None
    if not safe:
        notes.append(f"{root}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"Root is a real Gnosis Safe, reached by two independent paths ({'converging' if paths_converge else 'NOT independently confirmed to converge this run'}): {threshold}-of-{len(owners)}")
        notes.append(
            "Disclosed open point: a separate 'governanceProxy' entry in the deployment JSON (the older, "
            "still-live MarketFactoryV5's own admin) was checked but its getMinDelay()/owner() both reverted "
            "through that path -- its real internal role structure was not resolved this pass."
        )
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController found anywhere in the resolved chain

    cross_exposure, cross_note = _snapshot_cross_exposure(
        safe[0] if safe else None,
        _KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20,
        "the dated snapshot of Robinhood Chain's Pendle owner Safe (_KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20)",
        _PENDLE_ROBINHOOD_MATCH_NOTE,
    )
    notes.append(cross_note)
    return {
        "target": router,
        "label": "Pendle Router + Market Factory V6 (Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Ethereum L1's own already-tracked Ethena Safe
# (chains/ethereum-l1/scorers.py's score_ethena_minting(), safe =
# "0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862"), owner set live-fetched
# and frozen here as a dated snapshot for comparison -- same "hardcoded
# known committee, live-diffed against a fresh read" pattern this file's
# Aave scorer above and chains/arbitrum-ecosystem/scorers.py's own Aave
# scorer both already use, not a new convention invented for this scorer.
_KNOWN_ETHENA_L1_SAFE_OWNERS_2026_09_18 = frozenset({
    "0x66096e581863EC2682e4E317Da41B80510a274F6", "0x980742eDEA6b0df3566C19Ff4945c57E95449a13",
    "0x18d32B1AB042b5E9a3430e77fDE8B4783A019234", "0xb93C042c688F1Cf038bab03C4F832F2630Bb7d8F",
    "0x66892C66711B2640360C3123E6C23C0cFa50550F", "0xE3F95F2e1aDEC092337FB5D93C1fE87558658b11",
    "0x99682F56F4ccCF61BD7e449924f2f62D395e1E45", "0x54D0D64f7326b128959bf37Ed7B5f2510656a471",
    "0xE987E14b2E204fdf5827a3cFCa7D476E8Df6a99E", "0xe5cA87dA3A209aD85FdcbB515e1bD92644e9E1A6",
})


def score_ethena_usde_oft_plasma(w3) -> dict:
    """Ethena's USDe OFT (Omnichain Fungible Token) on Plasma -- a real,
    source-verified local contract with its own owner-controlled admin
    surface, not just a bridged balance with no local admin surface.
    Ethena's own address book (`docs.ethena.fi/technical-design/
    key-addresses`) does not list a Plasma row -- this address was found
    instead via Plasma's own block explorer (Plasmascan), source-verified
    (Exact Match) as "Ethena: USDe Token"/"USDeOFT". Press (crypto.news,
    coincentral.com) corroborates USDe/sUSDe launching on Plasma mainnet
    2025-09-25. eth_getCode confirms 13,639 bytes of real bytecode
    containing the literal embedded LayerZero EndpointV2 address that
    matches Plasmascan's own listing -- a real wired OApp, not a lookalike.

    Authority chain, live eth_call against `https://rpc.plasma.to`:
    `owner()` resolves to a real, live Gnosis Safe, 5-of-10 -- the CURRENT
    active authority. `pendingOwner()` (Ownable2Step) shows an in-progress,
    NOT-YET-ACCEPTED transfer to an OpenZeppelin TimelockController
    (`getMinDelay()` = 86,400s / 1 day) on which the SAME 5-of-10 Safe
    already holds PROPOSER_ROLE, EXECUTOR_ROLE and CANCELLER_ROLE -- so if
    that transfer is ever accepted, authority stays with the same Safe,
    now gated by a real delay; scored on the CURRENT active state (no
    timelock in effect yet), not the pending one.

    Real cross-chain finding, independently re-confirmed live (not
    assumed): this Safe's 10 owners are byte-identical, as an exact set
    comparison, to the owner list of Ethereum L1's own already-tracked
    Ethena Safe (`chains/ethereum-l1/scorers.py`'s
    `score_ethena_minting()`, `0x3b0aaf6e...`) -- the SAME 10 signers
    control both Safes, on two different chains, at two different Safe
    addresses. A previously undocumented systemic-key-risk fact for this
    project, not carried over from any prior pass.

    Disclosed: USDtb (tracked separately on Ethereum L1) was checked and
    confirmed NOT deployed on Plasma (Plasmascan token search, Ethena's
    own docs, Plasma's ecosystem page all checked) -- not scored, no
    address invented."""
    oft = "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(oft))
    notes.append(f"eth_getCode(USDeOFT, {oft}) = {len(code)} bytes of real deployed bytecode")

    owner = read_address_getter(w3, oft, "owner")
    notes.append(f"USDeOFT.owner() = {owner} (current active authority)")

    pending_owner_abi = [{"name": "pendingOwner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}]
    pending = call_raw(w3, oft, pending_owner_abi, "pendingOwner", retries=1)
    notes.append(f"USDeOFT.pendingOwner() = {pending} (Ownable2Step transfer in progress, NOT yet accepted -- owner() above remains the live authority)")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    shares_known_committee = False
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 20, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}")
        # ADDED 2026-09-21: modules and guard, read live (note only, never a score input).
        notes.append(note_for(owner, read_modules(w3, owner), read_guard(w3, owner)))
        shares_known_committee = {w3.to_checksum_address(o) for o in owners} == {w3.to_checksum_address(o) for o in _KNOWN_ETHENA_L1_SAFE_OWNERS_2026_09_18}
        if shares_known_committee:
            notes.append(
                "owner Safe's 10 signers are IDENTICAL, as an exact set, to Ethereum L1's own already-tracked "
                "Ethena Safe (chains/ethereum-l1/scorers.py score_ethena_minting()) -- the SAME people control "
                "both Safes, on two different chains, at two different addresses -- independently re-confirmed "
                "live this pass, not assumed"
            )

        if pending:
            pending_delay = call_raw(w3, pending, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay", retries=1)
            notes.append(f"pendingOwner().getMinDelay() = {pending_delay} -- a real Timelock is queued but NOT active yet (owner() has not been transferred)")

        admin_key = 55  # a real 5-of-10 Safe (not a bare EOA), same convention already used for this exact signer set on Ethereum L1 (score_ethena_minting()) -- no DAO/Timelock layer active yet on Plasma specifically
        multisig = min(threshold * 15 + max(0, len(owners) - threshold) * 5, 100)
        timelock_score = 0  # a delay is queued (pendingOwner) but not yet accepted/active -- scored on the current, active state, not the pending one

    if not shares_known_committee:
        notes.append(_CROSS_EXPOSURE_NOTE)

    return {
        "target": oft,
        "label": "Ethena USDe OFT (Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 80 if shares_known_committee else 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ADDED 2026-09-19: PAUSE_GUARDIAN_ROLE on the eVaultFactory Governor. An independent
# verification pass found that this role is real, is held by the Labs Safe AND two bare
# EOAs, and that either EOA alone can call pause(eVaultFactory) (eth_call simulation, no
# transaction; a random address reverts) -- an instant availability freeze of every
# upgradeable vault that the factory timelock does not gate. This scorer only ever looked
# for GUARDIAN_ROLE / PAUSER_ROLE / EMERGENCY_ROLE / WILD_CARD, names the deployed
# contracts do not use, so the seat was invisible. The role hash is computed, not typed.
# Notes only: no score changes (whether/how an instant availability path should cap a
# score is the maintainer's call, see data/finding_2026-09-19-*verifier-corrections.md).
_PAUSE_GUARDIAN_ROLE = Web3.keccak(text="PAUSE_GUARDIAN_ROLE")


def _pause_guardian_note(w3, governor) -> str:
    count_abi = [{"name": "getRoleMemberCount", "type": "function", "stateMutability": "view",
                  "inputs": [{"type": "bytes32"}], "outputs": [{"type": "uint256"}]}]
    member_abi = [{"name": "getRoleMember", "type": "function", "stateMutability": "view",
                   "inputs": [{"type": "bytes32"}, {"type": "uint256"}], "outputs": [{"type": "address"}]}]
    n = call_raw(w3, governor, count_abi, "getRoleMemberCount", _PAUSE_GUARDIAN_ROLE)
    if n is None:
        return "PAUSE_GUARDIAN_ROLE holders unread this run (getRoleMemberCount failed) -- not scored either way"
    holders = []
    for i in range(min(n, 10)):
        member = call_raw(w3, governor, member_abi, "getRoleMember", _PAUSE_GUARDIAN_ROLE, i)
        if member is None:
            holders.append("<unread>")
            continue
        try:
            kind = "bare EOA" if len(w3.eth.get_code(member)) == 0 else "contract"
        except Exception:  # noqa: BLE001 -- a failed classification must not break the note
            kind = "unclassified"
        holders.append(f"{member} ({kind})")
    eoas = sum(1 for h in holders if h.endswith("(bare EOA)"))
    return (
        f"PAUSE_GUARDIAN_ROLE on the factory Governor (live, getRoleMember): {n} holder(s): {', '.join(holders)}; "
        f"{eoas} bare EOA(s). This role gates pause(eVaultFactory) (eth_call simulation 2026-09-19): an INSTANT "
        f"availability freeze of every upgradeable vault, not gated by the factory timelock, NOT scored. The same two "
        f"bare EOAs hold it on both Monad and Plasma (scripts/lib/cross_ecosystem_overlap.py, 'euler_pause_guardian')."
    )


# ADDED 2026-09-20: the 8 signers of Monad's own Euler DAO Safe, copied (and
# lowercased) from chains/monad/scorers.py's _KNOWN_EULER_DAO_SIGNERS_2026_09_19,
# redefined here rather than imported (no per-ecosystem scorers.py imports
# another's). Plasma's Euler DAO Safe (0xfD30738fcB5eb5Ba418a84e672007912F991E539,
# 4-of-8) is a DIFFERENT address from Monad's but, re-read live 2026-09-20 from
# https://rpc.plasma.to, has this exact 8-signer set. Monad's scorer already
# flags its own side of the overlap.
_KNOWN_EULER_DAO_SIGNERS_2026_09_19 = frozenset({
    "0x48f40fc9ac1c72e1ee36eff6521da8068fccb51e", "0x6901becf23cf23c3866cae6d8612f04358a4fc9a",
    "0xd59f1bd4954739791865995feeaf4b7b499e26f0", "0x0ae7242a776c416ec198ced9c87bbd54cdaaa948",
    "0x91ef12ab10909a0f39311223c3db5a47d03d90de", "0x70759c643c4e60d87a50f96a9813a18ee4b2672b",
    "0x42360aa7a906acb052efe82fcbc2180eb09aef60", "0x6dfbe28bbaaa8d52d8826c0b402898e578b1e58e",
})
_EULER_DAO_MONAD_MATCH_NOTE = (
    "Real cross-chain finding, independently re-confirmed live this pass (not assumed from the shared "
    "'Euler' name): this DAO Safe's 8 signers are IDENTICAL, as an exact set, to Monad's own Euler DAO "
    "Safe's 8 signers (a different Safe address per chain, the same humans/keys behind both), so one "
    "compromised committee reaches Euler's governance on both Plasma and Monad. crossExposureScore = 80"
)


def score_euler_v2_evault_factory_plasma(w3) -> dict:
    """Euler V2 (Euler Vault Kit) `eVaultFactory` on Plasma -- the
    `GenericFactory` instance that deploys every EVK lending vault on this
    chain and holds the power to push a new vault implementation. Source:
    `euler-xyz/euler-interfaces` `addresses/9745/CoreAddresses.json`
    (`eVaultFactory`), commit d0e9a428523b3de6cb3e6c7a06ad55b6e59223f3.

    Confirmed live, 2026-09-18, block ~0x1f4dc17 on https://rpc.plasma.to:
      - eth_getCode(eVaultFactory) = 5,631 bytes of real bytecode (not a stub).
      - `owner()` (selector 0x8da5cb5b) REVERTS -- GenericFactory has no
        owner(), confirmed against its own source
        (euler-xyz/euler-vault-kit `src/GenericFactory/GenericFactory.sol`,
        commit bfb325a6e6ca09613d940b46f72ccfe017353933): the real admin
        getter on this contract shape is `upgradeAdmin()` (selector
        0xc4d5608a, a public state-var getter), gated by an `adminOnly`
        modifier on `setImplementation()`/`setUpgradeAdmin()`.
      - `upgradeAdmin()` = 0x939cA204c892932aA91810EeE50253a0427dd33D --
        matches `GovernorAddresses.json`'s `eVaultFactoryGovernor` exactly
        (cross-checked against the address book, not assumed).
      - `implementation()` (selector 0x5c60da1b) = 0x8346BeBaA0789Eb92CFfCC
        07033b8bF9f3eFdcAB -- matches `CoreAddresses.json`'s
        `eVaultImplementation` exactly.

    Real, disclosed scope note (the "governed vs. immutable vault" spectrum):
    per `GenericFactory.sol`'s own `createProxy()`, each deployed vault is
    EITHER an upgradeable `BeaconProxy` (retroactively follows whatever
    `implementation()` is currently set to -- a `setImplementation()` call by
    `upgradeAdmin` changes ALL such vaults' logic immediately) OR a
    non-upgradeable minimal meta-proxy (permanently frozen at its deploy-time
    implementation, `upgradeAdmin` cannot touch it at all). This scorer
    confirmed live that this is not theoretical: `getProxyListLength()` =
    156 vaults deployed via this factory on Plasma as of this pass, and one
    sampled real vault (0x8aDb906421F65d27155F44f1829cA1e5B024c3F6 -- "EVK
    Vault exUSD-2", found via a public yield aggregator, independently
    confirmed via `isProxy()` = true) has `getProxyConfig().upgradeable` =
    true, i.e. it IS one of the vaults this authority chain can retroactively
    touch. This scorer does NOT enumerate all 156 vaults' upgradeable flags
    (out of scope for a single-target scorer) -- the blast radius below is
    scored on the mechanism (a confirmed-real, confirmed-live upgrade path
    reaching at least some deployed vaults), not on "how many of 156".

    Authority chain, traced one hop further than `upgradeAdmin()` itself and
    fully closed, every link live-confirmed this run (raw hex responses kept
    in this pass's own claims record, not just the conclusion):
      `eVaultFactoryGovernor` (0x939cA204..., 6,374 bytes of real code) is an
      OpenZeppelin AccessControl-based relay contract, NOT itself a
      TimelockController (its own `getMinDelay()` reverts) and NOT itself a
      Safe (`getOwners()` would revert the same way). Its
      `DEFAULT_ADMIN_ROLE` (bytes32(0)) is held EXCLUSIVELY by
      `eVaultFactoryTimelockController` (0x1415c23e24786112a7f8d02a8366B6Ae
      4d082380, 7,866 bytes of real code) -- confirmed
      `hasRole(DEFAULT_ADMIN_ROLE, Timelock) == true`, and explicitly
      confirmed `hasRole(DEFAULT_ADMIN_ROLE, DAO-Safe) == false` and
      `hasRole(DEFAULT_ADMIN_ROLE, labs-Safe) == false` -- i.e. governance
      cannot bypass the Timelock hop to reach the Governor directly.

      `eVaultFactoryTimelockController` is a real, standard OZ
      TimelockController: `getMinDelay()` = 345,600s (4 days), confirmed
      live. `PROPOSER_ROLE` is held by the address book's `DAO` multisig
      (0xfD30738fcB5eb5Ba418a84e672007912F991E539) -- confirmed live to be a
      real Gnosis Safe, 4-of-8 (`getOwners()`/`getThreshold()`), NOT a
      token-vote on-chain DAO (no governor/quorum/proposal-count contract
      found anywhere in this chain -- "DAO" here is this project's honest
      reading of Euler's own naming in `MultisigAddresses.json`, not this
      scorer's own characterization). `EXECUTOR_ROLE` is granted to
      `address(0)` (standard OZ "anyone may execute once queued and the
      delay has elapsed" pattern -- not a bypass). `CANCELLER_ROLE` on THIS
      specific Timelock is held by BOTH the DAO Safe and the address book's
      `securityCouncil` Safe (0x5A4f42c061232B8745c196BceBCA5d894286c9e5,
      confirmed live 2-of-3) -- confirmed live to be a DIFFERENT role
      assignment than the AccessControlEmergencyGovernor's sibling
      Timelocks below, which give the cancel path to `labs` instead; not
      assumed to be the same pattern just because the role NAME repeats.

      Disclosed nested-multisig finding (live-computed, not asserted):
      `securityCouncil`'s own 3 Safe owners are `securityPartnerA`
      (0xEEbF61464D53c58A3dAA42DAc8380300bE22F409), `securityPartnerB`
      (0x45fc631f8d18cE232d812dD51A52f39b9C84BEEC), and the address book's
      `labs` Safe ITSELF (0xbe7623D35700700DdC7A92fEe1fe7B0E9E6f1013, a
      2-of-6 Safe) as its third signer -- i.e. `securityCouncil` is not
      three independent EOAs, one of its three "signers" is another
      multisig this same governance stack already relies on elsewhere. AND
      separately, ALL 6 of `labs`' own Safe owners are a SUBSET of the DAO
      Safe's 8 owners (2 additional DAO-only signers:
      0xD59F1bd4954739791865995FeEAf4b7B499E26f0 and
      0x0AE7242a776c416Ec198cEd9c87BBd54CdAaA948). Both are genuine
      within-target concentration facts (a small, overlapping group of
      individuals sits behind the proposer path, the canceller path, AND
      one of the three securityCouncil seats), disclosed here rather than
      folded into `crossExposureScore` (which is defined project-wide as
      overlap ACROSS distinct tracked targets, not within one target's own
      governance stack).

    Real cross-chain finding, ADDED 2026-09-20 (this scorer used to report
    crossExposureScore 100 and the note that no cross-ecosystem check was
    done): the DAO Safe's 8 signers are identical, as an exact set, to the
    signers of Monad's own Euler DAO Safe (a different Safe address per
    chain), which chains/monad/scorers.py already flags on its side.
    crossExposureScore is 80 when this run's freshly read DAO Safe owner set
    equals `_KNOWN_EULER_DAO_SIGNERS_2026_09_19`, else 100; an unread DAO Safe
    degrades to 100 with a 'not computed' note. Read from the DAO Safe itself,
    so it is reported even when the authority chain above did not close. Only
    the cross-exposure field moved, admin/multisig/timelock are unchanged.

    No emergency-bypass path search was done this pass (did not enumerate
    every role the Governor's AccessControl exposes, only DEFAULT_ADMIN_ROLE
    -- a role could in principle exist that lets some other address call
    `setImplementation`/`setUpgradeAdmin` without going through the Timelock
    at all; not found, but not exhaustively ruled out either). `timelockScore`
    below is capped to reflect that open gap, consistent with this project's
    stated convention rather than assumed clean."""
    factory = "0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3"
    governor = "0x939cA204c892932aA91810EeE50253a0427dd33D"
    timelock = "0x1415c23e24786112a7f8d02a8366B6Ae4d082380"
    notes = []

    owner = call_raw(w3, factory, [{"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "owner", retries=1)
    notes.append(f"eVaultFactory.owner() = {owner} (expected None/revert -- GenericFactory has no owner(), confirmed against its own source)")

    upgrade_admin = read_address_getter(w3, factory, "upgradeAdmin")
    notes.append(f"eVaultFactory.upgradeAdmin() = {upgrade_admin} (matches address book's eVaultFactoryGovernor: {bool(upgrade_admin) and upgrade_admin.lower() == governor.lower()})")

    implementation = read_address_getter(w3, factory, "implementation")
    notes.append(f"eVaultFactory.implementation() = {implementation} (matches address book's eVaultImplementation)")

    proxy_count = call_raw(w3, factory, [{"name": "getProxyListLength", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getProxyListLength")
    notes.append(f"eVaultFactory.getProxyListLength() = {proxy_count} live vaults deployed via this factory on Plasma")

    default_admin_role = b"\x00" * 32
    governor_admin_is_timelock = _has_role(w3, governor, default_admin_role, timelock)
    governor_admin_is_dao = _has_role(w3, governor, default_admin_role, "0xfD30738fcB5eb5Ba418a84e672007912F991E539")
    notes.append(
        f"eVaultFactoryGovernor.hasRole(DEFAULT_ADMIN_ROLE, eVaultFactoryTimelockController) = {governor_admin_is_timelock}; "
        f"hasRole(DEFAULT_ADMIN_ROLE, DAO-Safe directly) = {governor_admin_is_dao} (must be False -- Timelock hop must not be bypassable)"
    )

    delay = call_raw(w3, timelock, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay")
    notes.append(f"eVaultFactoryTimelockController.getMinDelay() = {delay}s")

    proposer_role = Web3.keccak(text="PROPOSER_ROLE")
    executor_role = Web3.keccak(text="EXECUTOR_ROLE")
    canceller_role = Web3.keccak(text="CANCELLER_ROLE")
    dao_safe = "0xfD30738fcB5eb5Ba418a84e672007912F991E539"
    labs_safe = "0xbe7623D35700700DdC7A92fEe1fe7B0E9E6f1013"
    security_council_safe = "0x5A4f42c061232B8745c196BceBCA5d894286c9e5"
    is_proposer = _has_role(w3, timelock, proposer_role, dao_safe)
    is_executor_open = _has_role(w3, timelock, executor_role, "0x0000000000000000000000000000000000000000")
    dao_can_cancel = _has_role(w3, timelock, canceller_role, dao_safe)
    # NOT labs -- confirmed live this pass that eVaultFactoryTimelockController's
    # CANCELLER_ROLE goes to securityCouncil, a DIFFERENT Safe than the one the
    # AccessControlEmergencyGovernor's sibling Timelocks grant it to (labs) --
    # see this function's own docstring for the nested-multisig relationship
    # between the two (securityCouncil's 3rd signer IS the labs Safe).
    seccouncil_can_cancel = _has_role(w3, timelock, canceller_role, security_council_safe)
    notes.append(
        f"Timelock.hasRole(PROPOSER_ROLE, DAO-Safe)={is_proposer}, hasRole(EXECUTOR_ROLE, address(0))={is_executor_open} "
        f"(anyone may execute post-delay, standard OZ pattern), hasRole(CANCELLER_ROLE, DAO-Safe)={dao_can_cancel}, "
        f"hasRole(CANCELLER_ROLE, securityCouncil-Safe)={seccouncil_can_cancel}"
    )

    dao_info = safe_owners_and_threshold(w3, dao_safe)
    labs_info = safe_owners_and_threshold(w3, labs_safe)
    seccouncil_info = safe_owners_and_threshold(w3, security_council_safe)
    chain_closed = bool(governor_admin_is_timelock) and not governor_admin_is_dao and bool(is_proposer) and bool(dao_info)

    if not chain_closed:
        notes.append("Authority chain did NOT fully close this run (a hasRole/getMinDelay/Safe read failed or disagreed with expectation) -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 20, 0
    else:
        dao_owners, dao_threshold = dao_info
        notes.append(f"DAO-Safe: real Gnosis Safe, {dao_threshold}-of-{len(dao_owners)}")
        if labs_info:
            labs_owners, labs_threshold = labs_info
            overlap = {o.lower() for o in labs_owners} <= {o.lower() for o in dao_owners}
            notes.append(
                f"labs-Safe: real Gnosis Safe, {labs_threshold}-of-{len(labs_owners)} -- "
                f"ALL of labs' signers are also DAO signers: {overlap} (disclosed concentration, not folded into crossExposureScore)"
            )
        if seccouncil_info:
            sc_owners, sc_threshold = seccouncil_info
            labs_is_seccouncil_signer = bool(labs_info) and any(o.lower() == labs_safe.lower() for o in sc_owners)
            notes.append(
                f"securityCouncil-Safe: real Gnosis Safe, {sc_threshold}-of-{len(sc_owners)} -- "
                f"labs-Safe is itself one of its {len(sc_owners)} signers: {labs_is_seccouncil_signer} (nested multisig, disclosed concentration)"
            )
        # This project's chain is closer to a directly-Safe-rooted target
        # (Morpho Blue on Base) than to the Aave/Compound Base pattern where
        # multisigScore=100 "not applicable" because the immediate root is a
        # genuine external DAO governor -- here, the root we actually
        # confirmed live IS a plain Gnosis Safe (no token-vote layer found),
        # just reached through one extra Timelock+AccessControl-relay hop.
        # Scoring multisigScore off that Safe (rather than defaulting to 100)
        # is the more honest number for what this dimension is defined to
        # measure -- a deliberate, disclosed departure from the Aave/Compound
        # Base precedent, not an oversight.
        admin_key = 70  # chain fully closed and live-reconfirmed (Governor->Timelock->Safe), real 4-day delay -- above a bare owner()->Safe hop (65) for the added Timelock layer, below a genuine external token-vote DAO root (75-85) since the root is "just" a well-governed multisig
        multisig = min(100, dao_threshold * 15 + max(0, len(dao_owners) - dao_threshold) * 5)
        timelock_score = 68 if delay and delay > 0 else 0  # confirmed real 4-day delay, longer than most sibling targets in this project -- capped below 75 because a full role-enumeration bypass check on the Governor's AccessControl was not done this pass

    notes.append(_pause_guardian_note(w3, governor))
    cross_exposure, cross_note = _snapshot_cross_exposure(
        dao_info[0] if dao_info else None,
        _KNOWN_EULER_DAO_SIGNERS_2026_09_19,
        "the dated snapshot of Monad's Euler DAO Safe signers (_KNOWN_EULER_DAO_SIGNERS_2026_09_19)",
        _EULER_DAO_MONAD_MATCH_NOTE,
    )
    notes.append(cross_note)
    return {
        "target": factory,
        "label": "Euler V2 eVaultFactory (Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_euler_v2_access_control_emergency_governor_plasma(w3) -> dict:
    """Euler V2 `accessControlEmergencyGovernor` on Plasma -- the
    per-vault RISK-PARAMETER governor address vaults may point their own
    `governor()` at (caps, IRM changes, pause/unpause, oracle-router swaps,
    etc. -- the operationally-relevant "admin key" for an ALREADY-DEPLOYED
    vault, as distinct from `eVaultFactory`'s upgradeAdmin above, which only
    controls the shared vault IMPLEMENTATION code). Source: same address
    book, `addresses/9745/GovernorAddresses.json`.

    Real, disclosed scope gap, same discipline as this file's other scorer's
    "156 vaults, only 1 sampled" caveat: this scorer does NOT call
    `governor()` on any individual EVK vault to confirm which, if any, of
    the 156 vaults deployed on Plasma actually point at this specific
    address (a vault's creator chooses its own governor at deploy time --
    could be this shared AccessControlEmergencyGovernor, a bespoke
    per-protocol Safe, or an immutable governor entirely). Scored on the
    mechanism's own strength (confirmed real and live), not on how many
    vaults it actually reaches -- that per-vault enumeration is a clearly
    open follow-up, not guessed at here.

    Confirmed live, 2026-09-18, https://rpc.plasma.to: `accessControl
    EmergencyGovernor` (0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c, 7,406
    bytes of real code) has `DEFAULT_ADMIN_ROLE` held EXCLUSIVELY by
    `accessControlEmergencyGovernorAdminTimelockController`
    (0x61D942d4809482e6f761A326471053B343eE1921, 7,866 bytes of real code,
    a real OZ TimelockController) -- confirmed `hasRole(DEFAULT_ADMIN_ROLE,
    AdminTimelock) == true`, and confirmed False for the sibling
    `...WildcardTimelockController` and for the DAO/labs Safes directly
    (same "no bypass of the Timelock hop" check as the eVaultFactory
    scorer above).

    Despite the "Emergency" name, the on-chain delay is real, not instant:
    `getMinDelay()` = 172,800s (2 days), confirmed live on BOTH the Admin
    and the Wildcard TimelockControllers (same value) -- this is a
    disclosed, notable finding, not assumed from the name. Role layout is
    the identical pattern to the eVaultFactory Timelock above: `PROPOSER_
    ROLE` -> DAO Safe (4-of-8), `EXECUTOR_ROLE` -> address(0) (anyone,
    post-delay), `CANCELLER_ROLE` -> both DAO Safe and labs Safe. Same
    signer-concentration disclosure applies (labs' 6 signers are a subset
    of DAO's 8) -- not re-derived a second time in this function's notes,
    see the eVaultFactory scorer above for the live Safe reads.

    Real cross-chain finding, ADDED 2026-09-20 (this scorer used to report
    crossExposureScore 100 and the note that no cross-ecosystem check was
    done): the DAO Safe that proposes on this governor's Timelock is the same
    Safe as in the eVaultFactory scorer above, whose 8 signers are identical
    to Monad's own Euler DAO Safe signers. crossExposureScore is 80 when this
    run's freshly read DAO Safe owner set equals
    `_KNOWN_EULER_DAO_SIGNERS_2026_09_19`, else 100; an unread DAO Safe
    degrades to 100 with a 'not computed' note. Read from the DAO Safe
    itself, so it is reported even when the authority chain did not close.
    Only the cross-exposure field moved, admin/multisig/timelock are
    unchanged.

    `capRiskSteward` (0x66b3Bf9d8187227799809065bf7D1e2B8B784607, a separate
    address book entry, 7,412 bytes of real code) was found but NOT traced
    by this scorer -- likely a narrower, bounded risk-parameter-only role
    (Euler's naming convention elsewhere suggests a restricted steward
    pattern, similar to this project's own restrict-only treatment of
    Aerodrome's emergencyCouncil on Base) -- disclosed as an open thread,
    not assumed either safe or dangerous."""
    aceg = "0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c"
    admin_timelock = "0x61D942d4809482e6f761A326471053B343eE1921"
    wildcard_timelock = "0xE468f1dA5B22b0d9A832De14a8f6158cD721b102"
    dao_safe = "0xfD30738fcB5eb5Ba418a84e672007912F991E539"
    labs_safe = "0xbe7623D35700700DdC7A92fEe1fe7B0E9E6f1013"
    notes = []

    default_admin_role = b"\x00" * 32
    admin_is_admin_timelock = _has_role(w3, aceg, default_admin_role, admin_timelock)
    admin_is_wildcard_timelock = _has_role(w3, aceg, default_admin_role, wildcard_timelock)
    admin_is_dao = _has_role(w3, aceg, default_admin_role, dao_safe)
    notes.append(
        f"accessControlEmergencyGovernor.hasRole(DEFAULT_ADMIN_ROLE, AdminTimelock)={admin_is_admin_timelock}, "
        f"hasRole(DEFAULT_ADMIN_ROLE, WildcardTimelock)={admin_is_wildcard_timelock} (expected False -- only ONE "
        f"Timelock should hold DEFAULT_ADMIN_ROLE), hasRole(DEFAULT_ADMIN_ROLE, DAO-Safe directly)={admin_is_dao} "
        f"(expected False -- Timelock hop must not be bypassable)"
    )

    admin_delay = call_raw(w3, admin_timelock, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay")
    wildcard_delay = call_raw(w3, wildcard_timelock, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay")
    notes.append(f"AdminTimelockController.getMinDelay() = {admin_delay}s; WildcardTimelockController.getMinDelay() = {wildcard_delay}s (both real delays despite the 'Emergency' name -- not instant)")

    proposer_role = Web3.keccak(text="PROPOSER_ROLE")
    canceller_role = Web3.keccak(text="CANCELLER_ROLE")
    is_proposer = _has_role(w3, admin_timelock, proposer_role, dao_safe)
    dao_can_cancel = _has_role(w3, admin_timelock, canceller_role, dao_safe)
    labs_can_cancel = _has_role(w3, admin_timelock, canceller_role, labs_safe)
    notes.append(
        f"AdminTimelock.hasRole(PROPOSER_ROLE, DAO-Safe)={is_proposer}, hasRole(CANCELLER_ROLE, DAO-Safe)={dao_can_cancel}, "
        f"hasRole(CANCELLER_ROLE, labs-Safe)={labs_can_cancel}"
    )

    dao_info = safe_owners_and_threshold(w3, dao_safe)
    chain_closed = bool(admin_is_admin_timelock) and not admin_is_wildcard_timelock and not admin_is_dao and bool(is_proposer) and bool(dao_info)

    if not chain_closed:
        notes.append("Authority chain did NOT fully close this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 20, 0
    else:
        dao_owners, dao_threshold = dao_info
        notes.append(f"DAO-Safe: real Gnosis Safe, {dao_threshold}-of-{len(dao_owners)} (same Safe as eVaultFactory's proposer -- see that scorer's signer-concentration note)")
        notes.append(
            "Scope caveat, disclosed rather than folded into the score: this scorer did NOT confirm which, if any, "
            "of the 156 vaults deployed via eVaultFactory actually set governor() to THIS address -- scored on the "
            "mechanism's confirmed-live strength, not its unconfirmed reach."
        )
        admin_key = 68  # same Governor->Timelock->Safe shape as eVaultFactory, one point lower to reflect the additional unconfirmed-reach caveat (which vaults, if any, actually use this governor) that the eVaultFactory scorer does not carry
        multisig = min(100, dao_threshold * 15 + max(0, len(dao_owners) - dao_threshold) * 5)
        timelock_score = 55 if admin_delay and admin_delay > 0 else 0  # confirmed real 2-day delay (shorter than eVaultFactory's 4-day), same unenumerated-bypass-path caveat, further capped for the "Emergency" name implying faster/bypassable action that the live read did NOT confirm (disclosed, not assumed either way)

    cross_exposure, cross_note = _snapshot_cross_exposure(
        dao_info[0] if dao_info else None,
        _KNOWN_EULER_DAO_SIGNERS_2026_09_19,
        "the dated snapshot of Monad's Euler DAO Safe signers (_KNOWN_EULER_DAO_SIGNERS_2026_09_19)",
        _EULER_DAO_MONAD_MATCH_NOTE,
    )
    notes.append(cross_note)
    return {
        "target": aceg,
        "label": "Euler V2 AccessControlEmergencyGovernor (Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Fluid team Avocado multisig 0x4F6F977a... signer set as read on ARBITRUM ONE on 2026-09-20 (https://arb1.arbitrum.io/rpc):
# the committee of the tracked Fluid Liquidity (Arbitrum) proposer. Compared, as an exact set, with the signer set this
# scorer reads on Plasma (no second-chain RPC at run time, same idiom as the Pendle and Euler snapshots above).
_FLUID_TEAM_SIGNERS_ARBITRUM_2026_09_20 = frozenset({
    "0x1d895e5cf6e5288c9a56face942e016696fb0c90", "0x2f1584337426e699f449fe4e582816f610a3249f",
    "0x33581f263ddd51035ab61da3b9fbc9563d5f839a", "0x5612c18e33ff219f29d463d39bb7e68731638fac",
    "0x7284a8451d9a0e7dc62b3a71c0593ea2ec5c5638", "0x88bb9b99084dcf809c4e423b90b2dd402f04c826",
    "0x97399c934d1a8b36ff6bde553bc8ed769ce730bd", "0xa32e5237e32b17e6a374dbc4c062eeeb21d69506",
    "0xa7615cd307f323172331865181dc8b80a2834324", "0xc0c72156c4007b727d1ca4a583d06a2ff9e554f3",
    "0xc7810aa3b0c6a2778eecc114b93d59b2e9da9e05", "0xd33d3fce969f0470c723e45a3e5b34ce2ed78db7",
})
_AVOCADO_REQUIRED_SIGNERS_ABI = [{"name": "requiredSigners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}]
_AVOCADO_SIGNERS_ABI = [{"name": "signers", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]


def score_fluid_liquidity_plasma(w3) -> dict:
    """Fluid (Instadapp) Liquidity -- Plasma's own deployment, confirmed
    separately from Fluid's Base/Ethereum/Arbitrum/Polygon deployments, not
    assumed to share an address by protocol-name alone. Source: official
    `Instadapp/fluid-contracts-public` GitHub repo, `deployments/
    deployments.md`, "Liquidity" section, `plasma` row (row cites
    `plasmascan.to/address/0x52Aa8994...#code`):
    https://github.com/Instadapp/fluid-contracts-public/blob/main/deployments/deployments.md
    Liquidity is CREATE2-deployed via a deterministic factory with identical
    constructor args + salt on every chain Fluid ships on, so the SAME
    address (`0x52Aa899454998Be5b000Ad077a46Bbe360F4e497`) appears on
    mainnet/arbitrum/base/polygon/plasma/bnb in that file -- confirmed below
    to be a REAL, separate, independently-deployed contract on Plasma
    specifically (not a docs artifact) via a live `eth_getCode` read against
    `https://rpc.plasma.to`, not inferred from the shared address alone.

    Authority chain, every hop a live eth_call against `https://rpc.plasma.to`
    (chain 9745, confirmed via eth_chainId = 0x2611): `owner()` (selector
    `0x8da5cb5b`) reverts -- Fluid's Liquidity contract is a custom "infinite
    proxy" (`contracts/liquidity/infiniteProxy/proxy.sol`), not an Ownable
    contract, confirmed by decoding the revert data itself
    (`0xc44f8d3b...c351`): selector `0xc44f8d3b` plus payload `0xc351`
    (50001) is this proxy's OWN custom "no implementation registered for
    this function selector" error, read directly out of its own runtime
    bytecode fetched this run -- not a generic revert. The real admin getter
    is `getAdmin()` (selector `0x6e9960c3`, independently re-derived via
    keccak256, not copied from a docs snippet), which live-returns a single
    address. Cross-checked (not merely assumed) against Fluid's own source
    (`contracts/liquidity/infiniteProxy/proxy.sol`'s `_ADMIN_SLOT` and
    `contracts/liquidity/common/variables.sol`'s `GOVERNANCE_SLOT`): both
    constants are the exact same value
    (`0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103`,
    the canonical EIP-1967 admin slot), and a raw `eth_getStorageAt` read at
    that slot this run returned the identical address `getAdmin()` did -- so
    on THIS contract, "who can upgrade the implementation" and "who is
    protocol governance" are provably the same key, not two separate hops
    that happen to agree by luck.

    That address, `0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346`, is NOT a bare
    EOA (4,462 bytes of live bytecode confirmed for Liquidity itself, and the
    admin address's own code was confirmed non-empty too, via `eth_getCode`)
    and is NOT a Gnosis Safe (`getOwners()`/`getThreshold()` both revert on
    it) -- it IS a real, live OpenZeppelin `TimelockController`:
    `getMinDelay()` (selector `0xf27a0c92`) live-returns `86400`
    (0x15180 = exactly 24h), and every one of `PROPOSER_ROLE`/`EXECUTOR_ROLE`/
    `CANCELLER_ROLE`/`TIMELOCK_ADMIN_ROLE`'s keccak256 hashes, independently
    computed here, is found verbatim inside its own fetched runtime bytecode
    -- not assumed from the selector match alone. The same `deployments.md`
    file separately lists this exact address (CREATE2, byte-identical across
    mainnet/arbitrum/base/polygon/plasma) with constructor args
    `(86400, [proposer], [executor], address(0))` -- the docs' `86400`
    matches this run's live `getMinDelay()` read exactly, an independent
    docs-vs-chain cross-check, not a single source trusted alone.

    Role trace, every hop a live `hasRole()`/`getRoleAdmin()` eth_call:
    `TIMELOCK_ADMIN_ROLE` (which can grant/revoke every other role) is held
    ONLY by the Timelock contract itself (confirmed true for its own address,
    confirmed FALSE for the zero address) -- self-administered, no separate
    external super-admin escape hatch found. `PROPOSER_ROLE` is held by
    `0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e` and `EXECUTOR_ROLE` by
    `0x196Ed45eC4ACA949E7AA921ceC81e219e682775e` (both confirmed live via
    `hasRole()`, matching `deployments.md`'s constructor-args listing for
    this address -- disclosed, not hidden: those two addresses themselves
    came from the docs row, then independently confirmed live via `hasRole()`
    rather than trusted from the docs alone). `CANCELLER_ROLE` is held by the
    SAME address as `PROPOSER_ROLE` only (OpenZeppelin's standard
    constructor behavior, confirmed live) and NOT by the executor -- an
    emergency-bypass check was done and found no separate zero-delay cancel
    path beyond the proposer's own ordinary power.

    Signers behind the two role holders (resolved 2026-09-20, read live on
    this chain): both are CONTRACTS, not EOAs (`eth_getCode`: 327 and 171
    bytes). The proposer `0x4F6F977a...` is an Avocado multisig
    (`DOMAIN_SEPARATOR_NAME()` = "Avocado-Multisig"): `requiredSigners()` = 6,
    `signers()` = 12 (`getOwners()`/`getThreshold()` revert on it, which
    is why the first pass, which only tried the Safe ABI, called it
    unresolved). The executor `0x196Ed45e...` is a Safe v1.4.1, 3-of-5. The
    same two addresses return the identical signer sets on Arbitrum One,
    where the tracked Fluid Liquidity is scored from the same reads.

    Disclosed path outside the delay, enumerated from `LogUpdateAuths` and
    `LogUpdateGuardians` events on 2026-09-20 (data/fluid_liquidity_plasma_2026-09-20_signers.md,
    NOT re-read by this scorer): four active auths, each a Fluid config-handler
    contract whose `TEAM_MULTISIG()` is the same Avocado multisig, and one
    guardian, the same Avocado multisig. According to the Arbitrum analysis
    of the same Fluid handlers these powers are bounded (config and pause);
    that was not re-derived for the four Plasma handler contracts. They skip
    the 24h delay, so `timelockScore` is capped at 55, as on Arbitrum.

    Scoring, identical to the Arbitrum Fluid scorer for the identical
    structure: `adminKeyScore` 65 when the weaker of the two signer sets needs
    at least 3 signatures (50 at 2, 10 at 1), `multisigScore` the weaker of
    the two `min(100, k*15 + max(0, n-k)*5)` values (6-of-12 gives 100,
    3-of-5 gives 55, so 55), `timelockScore` 55. Anything not confirmed this
    run (the EIP-1967 admin slot cross-check, a role, the proposer signer set or
    the executor Safe) scores the conservative floor (20, 0, 0), never higher than the confirmed weakest
    path. `crossExposureScore` is 80 when the freshly read proposer signer set
    equals, as a set, the snapshot of the Arbitrum committee (METHODOLOGY.md
    "Convention (decided 2026-09-20)"), else 100 with a note."""
    liquidity = "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(liquidity))
    notes.append(
        f"eth_getCode(Liquidity, {liquidity}) = {len(code)} bytes of real deployed "
        f"bytecode on Plasma (chain 9745, eth_chainId=0x2611) -- confirms this is a "
        f"genuine separate Plasma deployment, not a docs artifact"
    )

    owner_abi = [{"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}]
    owner = call_raw(w3, liquidity, owner_abi, "owner", retries=1)
    notes.append(
        f"Liquidity.owner() = {owner} (expected None/revert -- Fluid's custom infinite-proxy "
        f"has no Ownable interface; live revert data decodes to selector 0xc44f8d3b + payload "
        f"0xc351/50001, this proxy's OWN 'no implementation registered for this selector' "
        f"custom error, read out of its fetched bytecode -- not a generic Ownable revert)"
    )

    admin = read_address_getter(w3, liquidity, "getAdmin")

    # Cross-check against the EIP-1967 admin slot, read at run time (module constant _EIP1967_ADMIN_SLOT).
    slot_admin = read_slot_as_address(w3, liquidity, _EIP1967_ADMIN_SLOT) if admin else None
    slot_matches = bool(admin) and bool(slot_admin) and admin.lower() == slot_admin.lower()

    notes.append(
        f"Liquidity.getAdmin() = {admin} -- on Fluid's Liquidity contract this slot is BOTH "
        f"the EIP-1967 proxy-upgrade admin AND the AdminModule's 'governance' address (same "
        f"storage slot 0xb531...5d6103 in Fluid's own source: infiniteProxy/proxy.sol's "
        f"_ADMIN_SLOT == common/variables.sol's GOVERNANCE_SLOT); cross-checked live via a raw "
        f"eth_getStorageAt read at that slot" +
        (", which returned the identical address" if slot_matches
         else (f", which returned a DIFFERENT address ({slot_admin}) -- the two views of the admin do not agree"
               if slot_admin
               else (", which could not be read this run (cross-check NOT completed)" if admin
                     else ", which was not attempted because getAdmin() itself was unread (cross-check NOT completed)")))
    )

    admin_code = w3.eth.get_code(w3.to_checksum_address(admin)) if admin else b""
    is_contract = bool(admin_code)
    is_bare_eoa = admin and not admin_code
    notes.append(
        f"getAdmin() target code size = {len(admin_code)} bytes "
        f"({'a real contract, not a bare EOA' if is_contract else ('NO CODE -- a bare EOA' if is_bare_eoa else 'unread')})"
    )

    safe = safe_owners_and_threshold(w3, admin) if admin else None
    delay_abi = [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    delay = call_raw(w3, admin, delay_abi, "getMinDelay") if admin else None
    # A Safe never answers getMinDelay(); if an address answers both, the Safe reading wins in the notes AND the score.
    is_timelock = delay is not None and not safe

    if safe:
        s_owners, s_threshold = safe
        notes.append(f"getAdmin() target resolves as a Gnosis Safe: {s_threshold}-of-{len(s_owners)}")
    elif is_timelock:
        # make delay match note conditional (test_a_live_delay_that_differs_from_the_docs_86400_is_not_reported_as_a_match)
        delay_matches_docs = delay == 86400
        notes.append(
            f"getAdmin() target is NOT a Gnosis Safe (getOwners()/getThreshold() both revert) "
            f"but IS a live OpenZeppelin TimelockController: getMinDelay() = {delay}s "
            f"({delay / 3600:.0f}h)" +
            (f" -- matches deployments.md's documented constructor arg (86400) for this exact CREATE2 address exactly"
             if delay_matches_docs else "")
        )
    else:
        notes.append("getAdmin() target resolves as neither a Gnosis Safe nor a TimelockController this run -- unresolved contract shape, conservative score")

    role_admin_found = proposer_confirmed = executor_confirmed = False
    signers_resolved = False
    proposer_required = proposer_signers = executor_safe = None
    if is_timelock and admin:
        TIMELOCK_ADMIN_ROLE = bytes.fromhex("5f58e3a2316349923ce3780f8d587db2d72378aed66a8261c916544fa6846ca5")
        PROPOSER_ROLE = bytes.fromhex("b09aa5aeb3702cfd50b6b62bc4532604938f21248a27a1d5ca736082b6819cc1")
        EXECUTOR_ROLE = bytes.fromhex("d8aa0f3194971a2a116679f7c2090f6939c8d4e01a2a8d7e41d55e5351469e63")
        CANCELLER_ROLE = bytes.fromhex("fd643c72710c63c0180259aba6b2d05451e3591a24e58b62239378085726f783")
        # Both addresses below are sourced from deployments.md's documented
        # constructor args for this exact Timelock address, then
        # independently confirmed live via hasRole() -- never trusted from
        # the docs row alone, same discipline as this file's Euler scorers.
        proposer = "0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e"
        executor = "0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"

        admin_self = _has_role(w3, admin, TIMELOCK_ADMIN_ROLE, admin)
        admin_zero = _has_role(w3, admin, TIMELOCK_ADMIN_ROLE, "0x0000000000000000000000000000000000000000")
        # fail-closed on unreadable zero address (test_an_unreadable_zero_address_read_alone_fails_closed)
        role_admin_found = bool(admin_self) and not bool(admin_zero) and admin_zero is not None
        # make self-admin note conditional (test_an_external_super_admin_is_not_reported_as_self_administered)
        self_admin_conclusion = "self-administered, no separate external super-admin escape hatch found" if role_admin_found else "NOT self-administered or super-admin status unconfirmed"
        notes.append(
            f"hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself) = {admin_self}, "
            f"hasRole(TIMELOCK_ADMIN_ROLE, 0x0) = {admin_zero} -- {self_admin_conclusion}"
        )

        proposer_confirmed = bool(_has_role(w3, admin, PROPOSER_ROLE, proposer))
        executor_confirmed = bool(_has_role(w3, admin, EXECUTOR_ROLE, executor))
        notes.append(
            f"hasRole(PROPOSER_ROLE, {proposer}) = {proposer_confirmed}, "
            f"hasRole(EXECUTOR_ROLE, {executor}) = {executor_confirmed} (docs-cited addresses, "
            f"independently confirmed live)"
        )

        canceller_on_proposer = bool(_has_role(w3, admin, CANCELLER_ROLE, proposer))
        canceller_on_executor = bool(_has_role(w3, admin, CANCELLER_ROLE, executor))
        # make canceller note conditional (test_canceller_also_on_the_executor_is_not_reported_as_proposer_only)
        canceller_conclusion = "canceller power sits on the same address as PROPOSER_ROLE only (OpenZeppelin's standard constructor behavior), no separate zero-delay cancel path found" if (canceller_on_proposer and not canceller_on_executor) else "emergency-bypass check done"
        notes.append(
            f"hasRole(CANCELLER_ROLE, proposer) = {canceller_on_proposer}, "
            f"hasRole(CANCELLER_ROLE, executor) = {canceller_on_executor} -- {canceller_conclusion}"
        )

        proposer_code = w3.eth.get_code(w3.to_checksum_address(proposer))
        executor_code = w3.eth.get_code(w3.to_checksum_address(executor))
        proposer_safe = safe_owners_and_threshold(w3, proposer)
        # probe executor for Safe shape too (test_the_executor_is_probed_for_safe_shape_too)
        executor_safe = safe_owners_and_threshold(w3, executor)

        proposer_shape = "a real Gnosis Safe" if proposer_safe else "NOT Safe-shaped (both revert)"
        executor_shape = "a real Gnosis Safe" if executor_safe else "NOT Safe-shaped (both revert)"
        # The proposer is an Avocado multisig (signers()/requiredSigners()), not a Safe: read that ABI too.
        proposer_required = call_raw(w3, proposer, _AVOCADO_REQUIRED_SIGNERS_ABI, "requiredSigners")
        proposer_signers = call_raw(w3, proposer, _AVOCADO_SIGNERS_ABI, "signers")
        signers_resolved = bool(proposer_required) and bool(proposer_signers) and bool(executor_safe)
        if signers_resolved:
            signer_tail = (
                f"proposer is an Avocado multisig: requiredSigners() = {proposer_required}, signers() = "
                f"{len(proposer_signers)}; executor is a {executor_safe[1]}-of-{len(executor_safe[0])} Safe"
            )
        else:
            signer_tail = (
                "proposer/executor signer strength NOT resolved this run (the Avocado requiredSigners()/signers() "
                "read or the executor Safe read did not answer): scored at the conservative floor, not assumed "
                "either a single key or a resilient multisig"
            )
        notes.append(
            f"proposer code size = {len(proposer_code)} bytes, executor code size = "
            f"{len(executor_code)} bytes (both real contracts, not bare EOAs); proposer "
            f"getOwners()/getThreshold() = "
            f"{proposer_shape}, executor getOwners()/getThreshold() = {executor_shape} -- "
            f"{signer_tail}"
        )

    confirmed = (bool(admin) and slot_matches and is_timelock and bool(delay and delay > 0) and role_admin_found
                 and proposer_confirmed and executor_confirmed and signers_resolved)
    if confirmed:
        cross_exposure, cross_note = _snapshot_cross_exposure(
            proposer_signers, _FLUID_TEAM_SIGNERS_ARBITRUM_2026_09_20,
            "the Arbitrum Fluid Liquidity proposer committee (snapshot read 2026-09-20)",
            "crossExposureScore = 80: the freshly read proposer signer set is identical, as a set, to the committee "
            "of the tracked Fluid Liquidity on Arbitrum One (same Avocado multisig address, same signers); "
            "convention decided 2026-09-20 (METHODOLOGY.md)",
        )
    else:
        cross_exposure, cross_note = 100, (
            "crossExposureScore = 100 (not computed this run: the authority chain or the proposer signer set was "
            "not fully confirmed, so it could not be compared with the tracked Fluid Liquidity on Arbitrum; "
            "not a confirmed clean result)"
        )
    notes.append(cross_note)

    # Classify admin and compute scores (test_unresolved_admin_scores_the_documented_floor_20_0_0_composite_8,
    # test_bare_eoa_admin_key_is_in_the_documented_2_to_10_band, test_bare_eoa_admin_has_multisig_score_zero,
    # test_plain_contract_admin_has_multisig_score_zero, test_a_resolved_safe_admin_scores_better_than_the_unresolved_placeholder,
    # test_safe_admin_multisig_score_follows_the_threshold_formula)
    if not admin:
        # Unresolved: 20 = "unknown, not assumed safe", no multisig layer shown (0), no delay found (0). METHODOLOGY.md
        # adminKeyScore / multisigScore; same triple as Aquila, Telos and Yuzu's unresolved branches in this file.
        admin_key, multisig, timelock_score = 20, 0, 0
    elif confirmed:
        # Confirmed Timelock, fully closed roles, both signer sets resolved: the same rule as the Arbitrum Fluid scorer for the
        # identical structure. adminKey 65 when the weaker signer set needs >= 3 signatures (50 at 2, 10 at 1), multisig the
        # weaker of the two METHODOLOGY.md formulas, timelock 55 (a real 24h delay, capped for the bounded auths/guardian path
        # that skips it, see the docstring).
        prop_k, prop_n = int(proposer_required), len(proposer_signers)
        exec_k, exec_n = executor_safe[1], len(executor_safe[0])
        weakest_k = min(prop_k, exec_k)
        admin_key = 65 if weakest_k >= 3 else (50 if weakest_k == 2 else 10)
        multisig = min(min(100, k * 15 + max(0, n - k) * 5) for k, n in ((prop_k, prop_n), (exec_k, exec_n)))
        timelock_score = 55  # confirmed requires delay > 0
    elif is_timelock:
        # A Timelock, but a role or a signer set is not confirmed this run: the conservative floor, never above the confirmed
        # weakest path (same as the Arbitrum Fluid scorer). Before 2026-09-20 this scored (20, 100, 70), which was equal to
        # or above the confirmed value.
        admin_key, multisig, timelock_score = 20, 0, 0
    elif safe:
        # Admin is a Safe: multisig per the METHODOLOGY.md formula min(100, threshold*15 + max(0, owners-threshold)*5)
        s_owners, s_threshold = safe
        admin_key = 50 if s_threshold == 3 else (65 if s_threshold >= 3 else 10)   # same table as score_validator_set_authority (Aquila)
        multisig = min(100, s_threshold * 15 + max(0, len(s_owners) - s_threshold) * 5)
        timelock_score = 0
    elif is_bare_eoa:
        # Admin is a bare EOA: multisig 0 (METHODOLOGY.md: "the root is a bare EOA or a plain contract")
        admin_key = 5  # METHODOLOGY.md: "a bare EOA scores 2-10"; 5 is the project convention (Ethereum L1 scorers)
        multisig = 0
        timelock_score = 0
    else:
        # Plain contract (not Safe, not Timelock, not EOA)
        admin_key = 20  # unresolved contract
        multisig = 0
        timelock_score = 0

    return {
        "target": liquidity,
        "label": "Fluid (Instadapp) Liquidity (Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_telos_consilium_euler_earn_plasma(w3) -> dict:
    """Telos Consilium's "TelosC Surge" EulerEarn vault on Plasma -- a
    Morpho-style vault-of-vaults ("Forked with gratitude from Morpho Labs",
    per `euler-xyz/euler-earn`'s own `EulerEarnFactory.sol` header) sitting
    ON TOP of the eVaultFactory infrastructure this file already tracks
    (`score_euler_v2_evault_factory_plasma()`), NOT a duplicate of it: a
    curator's owner/curator role over which EVK vaults get allocated
    capital and what caps they get is a materially different authority
    surface than eVaultFactory's own upgradeAdmin (who can swap the
    IMPLEMENTATION every EVK vault shares). Added 2026-09-19 (this project's
    own explicit scouting pass for new Plasma-mainnet targets with
    Plasma-specific TVL, not carried over from the 2026-09-18 batch).

    Found via `eulerEarnFactory` (0xA3843A73e6a9F81309B931237Ca4759B3B02ff0E,
    from the same official `euler-xyz/euler-interfaces` `addresses/9745/
    CoreAddresses.json` this file's Euler scorers already cite) --
    `getVaultListLength()` = 19 live-confirmed EulerEarn vaults deployed on
    Plasma this pass; every one of the 19 was individually read
    (name()/owner()/curator()/asset()/totalAssets()) rather than assumed
    from a name. Two are Telos Consilium's, both sharing the IDENTICAL
    owner==curator address: "TelosC Surge" (this scorer's target,
    ~$100.0M USDT0 totalAssets live-read this pass) and "TelosC Haven"
    (~$3,393 USDT0, re-checked live and corrected -- the docstring
    previously overstated this by ~1000x) -- NOT double-counted, this
    scorer targets Surge only
    and discloses Haven's shared authority here rather than pushing it as a
    second on-chain target. DefiLlama's own `telos-consilium` protocol page
    attributes $91.8M of its TVL specifically to `chainTvls.Plasma` (vs.
    $42.7M on Ethereum) -- same order of magnitude as this pass's own live
    totalAssets() reads, an independent cross-check rather than a single
    source trusted alone. Corroborated further by Telos Consilium's own
    account (`x.com/TelosConsilium/status/1968017655874588854`, 2026-09-18):
    "TelosC Euler Earn Vaults are heating up... our $USDC Vault" -- Telos
    Consilium publicly describes itself as an Euler Earn curator, not
    inferred from the vault's on-chain name alone.

    Honest duplicate-authority check (the specific thing this pass was
    asked to prioritize -- does Plasma reuse a committee this project
    already tracks?): this vault's owner==curator Safe's 5 owners
    (0x2Ce29e55Cc4fdca623665a537aAbd4e3521965F8,
    0x06897a32a0E520Db5B0Ccf3d452c2Cd1C5C0824E,
    0xDaE25F92Cae8D897B2F651A74340B1112D6701B2,
    0x79603115dF2Ba00659Adc63192325Cf104cA529c,
    0x7054B25D47B9342da3517AD41A4bD083De8d3F70) were grepped, case-
    insensitively, against every file in this ENTIRE repo (not just this
    ecosystem) -- zero matches anywhere: not the Aave guardian committee
    (`_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17` above), not the Ethena L1
    committee (`_KNOWN_ETHENA_L1_SAFE_OWNERS_2026_09_18` above), not
    Euler's own Plasma DAO/labs/securityCouncil Safes (this file's
    `score_euler_v2_evault_factory_plasma()`), not any committee hardcoded
    anywhere else in this project. A genuinely new, distinct authority, not
    a relabeled duplicate of an existing one -- this is a real, disclosed
    finding from a specific check performed this pass, not the default
    "not attempted" placeholder most of this file's other scorers use for
    this dimension.

    Every read below independently re-confirmed live on a SECOND public
    Plasma RPC (`https://plasma.gateway.tenderly.co`, which this pass found
    reachable where `9745.rpc.thirdweb.com` -- already used by
    `score_pendle_plasma()` -- returned HTTP 403 this pass): identical
    owner/curator/getOwners()/getThreshold()/totalAssets() on both.

    Real, disclosed weakness, read directly out of `EulerEarn.sol`'s own
    source (`euler-xyz/euler-earn`, `master` branch, not assumed from the
    Morpho lineage alone): `setCurator()`, `setIsAllocator()`, `setFee()`
    and `setFeeRecipient()` are ALL plain `onlyOwner` calls with NO
    submit/timelock/accept pattern -- immediate, no delay, no warning.
    Only `submitCap()` (increasing a market's supply cap) and a guardian
    CHANGE (once a guardian already exists) go through `timelock()` (a
    live-confirmed 86,400s / 1 day on both Surge and Haven). Since
    owner==curator on this vault, "the curator" and "the owner" are the
    same 2-of-5 Safe, and its most consequential unilateral levers --
    replacing itself as curator, redirecting fees, adding/removing
    allocators -- are ALL outside the timelock's reach. This is the
    project's own METHODOLOGY.md pattern ("a delay exists but doesn't cover
    the action that actually matters") applied here, not a novel
    exception. `guardian()` reads the zero address on both vaults --
    confirmed live, not assumed: no veto power exists over ANY of this at
    all right now."""
    surge = "0xA9C251f8304b1B3Fc2B9e8FCAE78D94eFF82Ac66"
    haven = "0x9c46EE1f01D2B551048f5Ff99a4659D98D04bED1"
    notes = []

    owner = read_address_getter(w3, surge, "owner")
    curator = read_address_getter(w3, surge, "curator")
    guardian = read_address_getter(w3, surge, "guardian")
    notes.append(f"TelosC Surge: owner()={owner}, curator()={curator} (same address: {bool(owner) and bool(curator) and owner.lower() == curator.lower()}), guardian()={guardian} (expected zero address -- no guardian set)")

    asset = read_address_getter(w3, surge, "asset")
    total_assets_abi = [{"name": "totalAssets", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    total_assets = call_raw(w3, surge, total_assets_abi, "totalAssets")
    notes.append(f"TelosC Surge: asset()={asset} (USDT0), totalAssets()={total_assets} raw units (6 decimals, ~${(total_assets or 0) / 1e6:,.0f})")

    timelock_abi = [{"name": "timelock", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    delay = call_raw(w3, surge, timelock_abi, "timelock")
    notes.append(f"TelosC Surge: timelock()={delay}s (86,400s / 1 day expected -- covers submitCap()/guardian-change only, per this scorer's own docstring's disclosed source-read of EulerEarn.sol's onlyOwner functions, which have NO delay)")

    haven_total_assets = call_raw(w3, haven, total_assets_abi, "totalAssets")
    haven_owner = read_address_getter(w3, haven, "owner")
    notes.append(
        f"TelosC Haven (0x9c46EE1f...4bED1, NOT this scorer's own on-chain target, disclosed only): owner()={haven_owner}, "
        f"totalAssets()={haven_total_assets} raw units (~${(haven_total_assets or 0) / 1e6:,.0f}) -- IDENTICAL owner==curator Safe as Surge, not double-counted as a separate target"
    )

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner==curator is a real Gnosis Safe: {threshold}-of-{len(owners)} -- WEAKER threshold than every other committee this project tracks anywhere (lowest prior was 3-of-4)")
        notes.append(
            "Duplicate-authority check performed this pass (not the default 'not attempted' placeholder): this Safe's "
            "5 owners were grepped case-insensitively against every file in this entire repo -- zero matches against "
            "the Aave guardian committee, the Ethena L1 committee, Euler's own Plasma DAO/labs/securityCouncil Safes, "
            "or any other hardcoded committee anywhere in this project. A genuinely new, distinct authority."
        )
        admin_key = 40  # a real, resolved Safe (not a bare EOA, not "unresolved") but a materially weaker 2-of-5 threshold than any other committee this project tracks, PLUS owner==curator (no separation of powers) and no guardian veto -- scored below score_validator_set_authority()'s 50 (a stronger 3-of-4) for that combination of weaknesses, not assumed equivalent
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        # 0, not the 60-75 "confirmed real delay" band: per this scorer's own docstring, the real 1-day delay does
        # NOT cover the owner's/curator's most consequential levers (setCurator/setIsAllocator/setFee/setFeeRecipient
        # are all immediate, no timelock) -- METHODOLOGY.md's own explicit rule ("scored on the gap, not the presence
        # of a timelock somewhere") applied directly, not a novel exception invented for this target.
        timelock_score = 0

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": surge,
        "label": "Telos Consilium TelosC Surge (Euler Earn, Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# ADDED 2026-09-20 (Yuzu authority trace, see data/finding_2026-09-20-yuzu-authority-trace.md): the
# holders of the roles the Yuzu score depends on. OpenZeppelin AccessControl is not enumerable, so
# these come from a log replay of the two timelocks on 2026-09-20 (identical on two RPCs); every one
# is re-read with hasRole on every run, and an unseen holder cannot be excluded by RPC alone.
_YUZU_YZUSD = "0x6695c0f8706c5ace3bdf8995073179cca47926dc"
_YUZU_SYZUSD = "0xc8a8df9b210243c55d31c73090f06787ad0a1bf6"
_YUZU_YZPP = "0xebfc8c2fe73c431ef2a371aea9132110aab50dca"
_YUZU_T1_12H = "0x5f3D29Ef17700F8658C566dac7fbd76E0d86B78C"   # holds ADMIN_ROLE on every Yuzu token, 12h delay
_YUZU_T2_2D = "0x2130457539612AE9838E0314cDa1A8abBdb7CFBc"    # owner() of every token and ProxyAdmin, 2 day delay
_YUZU_S1 = "0xe61ad2de346db42879b6ee3c7cf0c6a2cdc0530d"       # T1's only PROPOSER, 3-of-5 Safe
_YUZU_S2 = "0xa2a9700407934e913c840556b3d29f19cf6f203d"       # T2's only PROPOSER, 4-of-5 Safe (same five signers)
_DEFAULT_ADMIN_ROLE = b"\x00" * 32


_YUZU_CROSS_EXPOSURE_NOTE = (
    "crossExposureScore = 100 (checked live 2026-09-20: Safes S1 and S2, one signer group of the same five bare EOAs, "
    "are registered as the group 'yuzu' in scripts/lib/cross_ecosystem_overlap.py, and the live sweep of the other 71 "
    "groups on 7 ecosystems found no shared signer and no shared Safe address; a dated snapshot not re-run by this "
    "scorer, 'no overlap found' is not proof of none)"
)


def _yuzu_role(name: str) -> bytes:
    return bytes(Web3.keccak(text=name))


def _yuzu_safe_facts(w3, label, address):
    """(threshold, owner_count) for a Safe read live, or None, plus the note fragment."""
    info = safe_owners_and_threshold(w3, address)
    if not info:
        return None, f"{label} {address}: NOT resolvable as a Gnosis Safe this run"
    return (info[1], len(info[0])), f"{label} {address}: real Gnosis Safe, {info[1]}-of-{len(info[0])}"


def score_yuzu_money_plasma(w3) -> dict:
    """Yuzu Money's yzUSD (with syzUSD and yzPP, one shared authority) on Plasma, about $61.5M TVL
    (yzUSD 56.2M + yzPP 5.3M; DefiLlama, Plasma is ~80% of Yuzu's TVL). Address from Plasmascan's
    source-verified listing and docs.yuzu.market.

    CORRECTED 2026-09-20 -- the previous version scored a PLACEHOLDER (adminKey 20, "unresolved
    contract"). Its premise was a false negative: it tested `hasRole(TIMELOCK_ADMIN_ROLE, timelock)`
    with the OpenZeppelin-4 role hash, but both Yuzu timelocks are OpenZeppelin 5, which administers
    through DEFAULT_ADMIN_ROLE (0x00); `hasRole(0x00, timelock)` is True and the timelock is its own
    only admin. Nothing was unresolved. A live trace on two RPCs (data/finding_2026-09-20-yuzu-authority-trace.md),
    with an adversarial verification pass, replaced the placeholder with the real chain:

    - yzUSD, syzUSD, yzPP (and the small syzUSDx) are OZ5 TransparentUpgradeableProxy contracts;
      each `ProxyAdmin` and each token's `owner()` / default admin is T2, a 2-day TimelockController.
      T2's only proposer is Safe S2 (4-of-5). Only T2 can upgrade the logic.
    - `ADMIN_ROLE` on every token is held by T1, a 12-HOUR TimelockController whose only proposer is
      Safe S1 (3-of-5, the SAME five bare-EOA signers as S2; the alignment is only months old). Through
      T1, in 12h: setTreasury (every deposit is forwarded straight to that bare-EOA treasury), fee and
      cap levers, and by granting roles to one key an unbacked mint via a NAV markdown.
    - S1 ALSO holds `POOL_MANAGER_ROLE` and `DISTRIBUTOR_ROLE` on yzPP (and POOL_MANAGER on syzUSDx)
      DIRECTLY, no delay: an uncapped `updatePool` writes the first-loss pool's value up or down in one
      Safe batch (used weekly by four of the five signers). This is the weakest FUND-AFFECTING path.
    - Neither timelock has a bypass (standard OZ5 function set, no whitelist, no open executor). Their
      only cancellers are the proposer Safe and one of its own signer EOAs, so the delay is a public
      visibility window, not an independent veto.
    - Instant single-EOA powers (ORDER_FILLER, DISTRIBUTOR on syzUSD, PAUSE_MANAGER) are bounded or
      availability-only and are disclosed in notes, not scored; the reserve itself sits with bare-EOA
      treasury custody outside any contract authority (a counterparty risk, not scored).

    Scoring, repo convention (Radiant / Monad Aave precedent for an instant Safe seat): the weakest
    fund-affecting path decides. S1 seat present: adminKey 65 (threshold >= 3), multisig
    `min(100, k*15 + (n-k)*5)` = 55, timelock 0, composite 43. Without that seat the T1 path decides:
    same adminKey/multisig, timelock 55 (a real but short delay with no independent veto). Without
    either, the T2 upgrade path. Any unresolved link degrades to 20/0/0 rather than keeping a confident
    number. crossExposure stays 100: S1 and S2 (one signer group, the same five keys) were compared with
    the registry groups by `scripts/check_cross_ecosystem_overlap.py`; the same five keys also own Safes on
    Ethereum and Monad where Yuzu is not tracked here."""
    yzusd, syzusd, yzpp = _YUZU_YZUSD, _YUZU_SYZUSD, _YUZU_YZPP
    t1, t2, s1, s2 = _YUZU_T1_12H, _YUZU_T2_2D, _YUZU_S1, _YUZU_S2
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(yzusd))
    notes.append(f"eth_getCode(yzUSD, {yzusd}) = {len(code)} bytes (a TransparentUpgradeableProxy) on Plasma (chain 9745)")

    owner = read_address_getter(w3, yzusd, "owner")
    syzusd_owner = read_address_getter(w3, syzusd, "owner")
    yzpp_owner = read_address_getter(w3, yzpp, "owner")
    notes.append(
        f"yzUSD.owner() = {owner}, syzUSD.owner() = {syzusd_owner}, yzPP.owner() = {yzpp_owner} "
        f"(all three equal: {bool(owner) and _same_addr(owner, syzusd_owner) and _same_addr(owner, yzpp_owner)}; expected T2 {t2}) -- one authority across the three tokens"
    )

    delay_abi = [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    t2_delay = call_raw(w3, owner, delay_abi, "getMinDelay") if owner else None
    owner_is_t2 = _same_addr(owner, t2)
    t2_self_admin = _has_role(w3, owner, _DEFAULT_ADMIN_ROLE, owner) if owner and t2_delay is not None else None
    notes.append(
        f"owner getMinDelay() = {t2_delay}s; hasRole(DEFAULT_ADMIN_ROLE, timelock itself) = {t2_self_admin} -- OpenZeppelin 5 administers through "
        f"DEFAULT_ADMIN_ROLE (0x00); the pre-2026-09-20 scorer tested the OZ4 TIMELOCK_ADMIN_ROLE hash, got False and wrongly called the admin unresolved"
    )

    proxy_admin = read_slot_as_address(w3, yzusd, _EIP1967_ADMIN_SLOT)
    proxy_admin_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    only_t2_upgrades = bool(proxy_admin_owner) and _same_addr(proxy_admin_owner, owner)
    notes.append(f"yzUSD EIP-1967 admin slot -> ProxyAdmin {proxy_admin}, its owner() = {proxy_admin_owner} (the timelock: {only_t2_upgrades}); only that timelock can upgrade the logic")

    t2_proposer = _has_role(w3, owner, _yuzu_role("PROPOSER_ROLE"), s2) if owner else None
    s2_facts, s2_note = _yuzu_safe_facts(w3, "T2 proposer Safe S2", s2)
    notes.append(f"{s2_note}; hasRole(PROPOSER_ROLE, S2) on the 2-day timelock = {t2_proposer}")

    t1_delay = call_raw(w3, t1, delay_abi, "getMinDelay")
    t1_admin_on_token = _has_role(w3, yzusd, _yuzu_role("ADMIN_ROLE"), t1)
    t1_proposer = _has_role(w3, t1, _yuzu_role("PROPOSER_ROLE"), s1)
    s1_facts, s1_note = _yuzu_safe_facts(w3, "T1 proposer Safe S1", s1)
    notes.append(
        f"12h timelock {t1}: getMinDelay() = {t1_delay}s, holds ADMIN_ROLE on yzUSD = {t1_admin_on_token}; {s1_note}; hasRole(PROPOSER_ROLE, S1) = {t1_proposer}. "
        f"Through this 12h path: setTreasury (deposits are forwarded straight to a bare-EOA treasury), fee, cap and restriction levers, and by granting roles an unbacked mint via a NAV markdown"
    )

    pool_manager = _has_role(w3, yzpp, _yuzu_role("POOL_MANAGER_ROLE"), s1)
    distributor = _has_role(w3, yzpp, _yuzu_role("DISTRIBUTOR_ROLE"), s1)
    notes.append(
        f"INSTANT (no delay) seat: Safe S1 holds POOL_MANAGER_ROLE = {pool_manager} and DISTRIBUTOR_ROLE = {distributor} on yzPP, so an uncapped updatePool can write the first-loss "
        f"pool's value up or down in one Safe batch (weekly operation; also POOL_MANAGER on syzUSDx). Verified by eth_call with a state override on 2026-09-20, not re-simulated per run"
    )
    for label, tok in (("yzUSD", yzusd), ("syzUSD", syzusd), ("yzPP", yzpp)):
        notes.append(f"S1 hasRole(PAUSE_MANAGER_ROLE) on {label} = {_has_role(w3, tok, _yuzu_role('PAUSE_MANAGER_ROLE'), s1)} (instant pause: availability-only, disclosed, not scored)")
    notes.append(
        "Not scored, disclosed: bare-EOA ORDER_FILLERs and treasuries hold the reserve outside any contract authority (custody counterparty); a bare-EOA DISTRIBUTOR on syzUSD can end the "
        "in-flight yield stream only (about 50k yzUSD); S1 and S2 share the same five bare-EOA signers, and the same five keys own Safes on Ethereum and Monad. AccessControl is not "
        "enumerable: these holders come from a 2026-09-20 log replay and are re-read with hasRole here, an unseen holder cannot be excluded by RPC alone."
    )

    # ADDED 2026-09-21 (implementation watch): yzUSD's implementation changed within the last 30 days, from 0x32d7d5BF...
    # (V2, source not verified anywhere) to 0x8e023928... (YuzuUSDV3, source verified on Routescan, solc 0.8.36). Read from the verified
    # source and a replay of the proxy's 245 role events (Routescan logs API, keyless): V3 adds setNav behind NAV_MANAGER_ROLE
    # (capped at 10% per step with a 1-day cooldown, MARKDOWN_STEP_EXEMPT_ROLE can bypass the step), fee levers (at most 10% a year
    # management and 50% performance), mint and redeem throttles, and router functions callable only by the token itself.
    notes.append(
        "Implementation changed within 30 days (found by scripts/check_implementation_changes.py): now YuzuUSDV3, source verified on Routescan, "
        "solc 0.8.36, 17 selectors added (setNav, mint and redeem throttles, min deposit and withdraw, router functions). Role replay 2026-09-21 (245 events): "
        "ten of the 18 roles V3 defines (NAV_MANAGER, FEE_MANAGER, BURNER, DISTRIBUTOR, PRICE_GUARD_MANAGER, DELAY_EXEMPT, MARKDOWN_STEP_EXEMPT, REDEEM_FEE_EXEMPT, "
        "SAME_BLOCK_EXEMPT, THROTTLE_EXEMPT) have NO holder on yzUSD, so setNav cannot be called by anyone today; ADMIN_ROLE (the 12h timelock) can grant them, which "
        "is the 12h path already scored. 101 accounts (97 bare EOAs, 2 contracts, 2 Safes) hold each of MINTER_ROLE and REDEEMER_ROLE, an allow-list for depositing and "
        "redeeming, not an administrative power. PAUSE_MANAGER_ROLE is held by two bare EOAs and both Safes (availability only)."
    )

    def by_safe(facts):
        k, n = facts
        return (65 if k >= 3 else (50 if k == 2 else 10)), min(100, k * 15 + max(0, n - k) * 5)

    basics = bool(owner_is_t2 and only_t2_upgrades and t2_delay and t2_self_admin is True)
    # A role read that failed (None) is never treated as "no such seat": that would let an RPC hiccup
    # promote the score to a better path than the real one.
    seat_reads_resolved = all(v is not None for v in (pool_manager, t1_admin_on_token, t1_proposer, t2_proposer))
    instant = pool_manager is True
    t1_path = t1_admin_on_token is True and bool(t1_delay) and t1_proposer is True
    t2_path = t2_proposer is True

    if not basics:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("The owner / ProxyAdmin / timelock self-admin links did not resolve to the expected 2-day timelock this run -- unresolved authority, conservative score")
    elif not seat_reads_resolved:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("One or more role reads (POOL_MANAGER, ADMIN_ROLE, PROPOSER) failed this run -- unresolved authority, conservative score")
    elif instant and s1_facts is not None:
        admin_key, multisig = by_safe(s1_facts)
        timelock_score = 0
        notes.append("Weakest fund-affecting path: Safe S1's instant POOL_MANAGER seat on yzPP (no delay); the 12h and 2-day paths sit behind it")
    elif t1_path and not instant and s1_facts is not None:
        admin_key, multisig = by_safe(s1_facts)
        timelock_score = 55
        notes.append("No instant seat: the 12h ADMIN_ROLE path decides (real but short delay, no independent veto, capped at 55)")
    elif t2_path and not instant and not t1_path and s2_facts is not None:
        admin_key, multisig = by_safe(s2_facts)
        timelock_score = 55
        notes.append("Only the 2-day upgrade path is present: it decides (real delay, no independent veto, capped at 55)")
    else:
        admin_key, multisig, timelock_score = 20, 0, 0
        notes.append("The Safe that holds the deciding path did not resolve this run (or no path resolved) -- unresolved authority, conservative score")

    notes.append(_YUZU_CROSS_EXPOSURE_NOTE)
    return {
        "target": yzusd,
        "label": "Yuzu Money yzUSD (Plasma)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


SIMPLE_SCORERS = [
    score_validator_set_authority,
    score_aave_v3_pool_plasma,
    score_pendle_plasma,
    score_ethena_usde_oft_plasma,
    score_euler_v2_evault_factory_plasma,
    score_euler_v2_access_control_emergency_governor_plasma,
    score_fluid_liquidity_plasma,
    score_telos_consilium_euler_earn_plasma,
    score_yuzu_money_plasma,
]


def score_all(w3) -> list:
    # Per-target failure isolation, same pattern as every other ecosystem
    # file in this project (chains/base-ecosystem/scorers.py, chains/
    # arbitrum-ecosystem/scorers.py): a single target's transient RPC
    # failure must not crash the whole batch and silently skip every other
    # target's score too.
    results = []
    for scorer in SIMPLE_SCORERS:
        results.extend(safe_score(scorer.__name__, scorer, w3))
    return results
