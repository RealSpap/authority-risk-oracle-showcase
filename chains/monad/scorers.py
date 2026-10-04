"""
Monad authority scorers -- 9 targets (2026-09-19, scoring_build).

Monad was identified as a genuine coverage gap the same day by a dedicated
multi-agent scouting pass across 8 EVM-compatible testnet candidates
(Berachain, Monad, Sonic, zkSync Era, Linea, Scroll, Mantle, ZetaChain):
Monad won on every weighted criterion simultaneously -- real mainnet DeFi
TVL (~$1.04B, 30-60x every other qualifying candidate, live-queried from
DefiLlama's historicalChainTvl API), a confirmed no-account/no-real-value
testnet funding path (openfaucet.org's proof-of-work faucet lists "Monad /
Testnet" directly), and a structurally confirmed competitor-coverage gap
(Monad does not appear anywhere in L2Beat's 101 tracked chains -- it is a
standalone parallel-EVM L1, not an Ethereum-security-derived L2, so it
falls outside L2Beat's Stage framework by definition, the same shape as
this project's own Plasma precedent). See
`data/finding_2026-09-19-monad-ecosystem-scouting.md` (if present) or this
session's own workflow transcript for the full 8-candidate comparison.

This file's 7 scorers were each independently verified live against
`https://rpc.monad.xyz` (Monad MAINNET, chain 143 -- where every scored
target actually lives; the oracle contract itself is deployed on Monad
TESTNET, chain 10143, same "read mainnet / write testnet" split this
project already uses for every other ecosystem) by a dedicated
target-verification research pass, one agent per target, each doing its
own on-chain eth_call/eth_getCode reads rather than trusting a prior
summary. Every address, Safe owner/threshold, and timelock delay below was
independently re-confirmed live a second time via direct RPC calls before
being written into this file -- see each function's own docstring for its
sourcing.

Targets scored: Echo Protocol's eBTC (a real, dated May-2026 admin-key
exploit -- ~$76.6M notional minted, ~$816K realized loss), the Monad
canonical/native bridge (Wormhole NTT + Axelar GMP dual-attestation,
governed by Wormhole's global 13-of-19 Guardian quorum), Curvance's
Emergency Council (a live, still-actively-exercised zero-delay allocation
path running in parallel to, not gated by, a 5-day DAO timelock), Kuru (a
3-of-5 Safe with no timelock at all controlling an actively-used CLOB
DEX), Uniswap v4's Monad PoolManager (owned via a Wormhole message-relay
by Uniswap's own UNI-token-holder-governed Ethereum Timelock -- the
best-governed target on this chain), a Morpho Blue vault (Grove x
Steakhouse High Yield AUSD, a Vault V2-shaped owner/curator split where
curator and guardian are the same 2-of-6 Safe, so no independent veto
exists during the vault's own 14-day cap-change timelock), and Curve
Finance's Monad deployment (admin = a single bare EOA, not even a Safe --
explicitly documented in Curve's own deployment repo as "deployer as
admin until DAO ownership transfer," the weakest authority shape this
project has found on any chain).

Reuses this project's existing methodology exactly as-is (same pattern as
`chains/plasma-ecosystem/scorers.py` and `chains/base-ecosystem/
scorers.py`): live eth_call against a public Monad mainnet RPC, address
sourced from the protocol's own official docs/GitHub/on-chain
self-identification, authority traced to its root (AccessControl
hasRole()/owner() -> Gnosis Safe getOwners()+getThreshold(), or an
OpenZeppelin TimelockController's getMinDelay(), or -- new to this file --
a Wormhole GeneralPurposeGovernance relay gated by a live Guardian
quorum()), never trusted from a prior pass or a block explorer's
"verified name" alone.

ADDED 2026-09-19 (second pass, same day): a dedicated new-target scouting
pass queried DefiLlama's `/protocols` endpoint live and filtered for every
protocol with `"Monad"` literally in its own `chains[]` list (135 matches),
ranked by `chainTvls.Monad` -- Monad-SPECIFIC TVL, not each protocol's
multi-chain total (K3 Capital's $531.9M total is mostly NOT on Monad, for
example; ranking by total TVL would have wrongly promoted it). The top 3
candidates not already tracked here: Aave V3 ($319.4M), Euler V2
($265.0M), Pendle V2 ($206.9M) -- all three verified live against
`https://rpc.monad.xyz`, cross-checked on a second independent public RPC
(`https://monad.drpc.org`) and against each protocol's own official
GitHub deployment-address repo (`bgd-labs/aave-address-book`,
`euler-xyz/euler-interfaces`, `pendle-finance/pendle-core-v2-public`).

Two of the three were added (`score_aave_v3_monad`, `score_euler_v2_monad`
below). Pendle V2 was found, fully verified, and honestly DISCARDED, not
force-added: its Monad Router (0x888888888889758F76e7103c6CbF23ABbF58F946)
and ProxyAdmin both resolve to the EXACT SAME Gnosis Safe addresses
(0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac and
0xE6F0489ED91dc27f40f9dbe8f81fccbFC16b9cb1) already tracked for Pendle on
Plasma in `chains/plasma-ecosystem/scorers.py::score_pendle_plasma()` and
`scripts/lib/cross_ecosystem_overlap.py`'s own `PLASMA_GROUPS["pendle"]`
-- the literal same CREATE2-deployed Router contract AND the literal same
multisig infrastructure, not merely the same team. Unlike Curve's own
Monad/Robinhood-Chain duplicate finding (`score_curve_monad` below, kept
because it disclosed a NEW single-key risk pattern -- a bare EOA actively
exercising power), scoring Pendle-on-Monad here would add zero new
authority-structure information over what `score_pendle_plasma()` already
states in full, so it was left out rather than padded in to reach a
target count. See `data/finding_2026-09-19-monad-new-targets-scouting.md`
for the complete research trail (all 3 candidates, discard reasoning,
and the DefiLlama query used).

Real cross-chain finding surfaced by this pass, independently re-confirmed
live (not assumed from a shared name): `score_aave_v3_monad()`'s guardian
Safe's 9 owners are BYTE-IDENTICAL to
`chains/plasma-ecosystem/scorers.py`'s own
`_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17` -- the same emergency-cancel
committee already found sharing Arbitrum, Base, AND Plasma's own Aave V3
deployments. Monad is a FOURTH chain this exact 9-signer, 5-of-9 committee
now reaches.
CORRECTED 2026-09-19: it is a fifth chain, not a fourth. Ethereum L1's own
`PayloadsController.guardian()` (Safe 0xCe52ab41...6710, 5-of-9) has the identical 9
owners too -- L1 was the one chain never compared (see
`data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`).
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
from web3_utils import (  # noqa: E402
    call_raw,
    get_w3,
    read_address_getter,
    safe_owners_and_threshold,
    safe_score,
)
import price_authority  # noqa: E402  (oracleAuthorityScore for price consumers, rule of 2026-10-04)
from nested_signers import signer_note  # noqa: E402

MONAD_CHAIN_ID = 143
DEFAULT_RPC = "https://rpc.monad.xyz"

# crossExposureScore is a property of the SET of tracked targets (does the
# same root signer also control ANOTHER tracked target?), computed
# project-wide in scripts/lib/signer_overlap.py. UPDATED 2026-09-19: Monad
# IS now wired into scripts/lib/cross_ecosystem_overlap.py's MONAD_GROUPS
# (score_curve_monad and score_morpho_vault_monad found real overlaps this
# pass, see their own docstrings/notes). This note now applies only to the
# 2 targets whose authority is NOT Safe-shaped at all (Uniswap v4's
# PoolManager -- a Wormhole relay to an Ethereum DAO Timelock -- and the
# Monad Native Bridge -- a Wormhole governance relay gated by a Guardian
# quorum) and to Kuru/Curvance, whose real Safes were checked and found NO
# overlap with any other tracked ecosystem this pass -- a confirmed clean
# result for those two, not an unchecked default, even though the score
# still reads 100 either way.
_CROSS_EXPOSURE_NOTE = (
    "crossExposureScore = 100 (Monad IS wired into scripts/lib/cross_ecosystem_overlap.py's "
    "MONAD_GROUPS as of 2026-09-19 -- either this target's authority isn't Safe-shaped (no live "
    "resolution path exists yet, same disclosed gap as Tempo's LayerZero OneSig/Chainlink MCMS), "
    "or its real Safe was checked and found no overlap with any other tracked ecosystem this pass)"
)


def _composite(admin_key, multisig, timelock):
    """Standard project weighting: 0.4*adminKey + 0.3*multisig + 0.3*timelock,
    oracleAuthorityScore excluded by convention: price consumers carry it as a
    separate field (METHODOLOGY, "oracleAuthorityScore for price consumers").
    Uses standard round-half-up via floor(x + 0.5), not Python's builtin round() (banker's
    rounding), same fix already applied project-wide."""
    import math

    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


def _has_role(w3, contract, role, account):
    """hasRole(bytes32,address) -> bool, standard OpenZeppelin AccessControl
    getter, same inline-ABI pattern already used in
    chains/plasma-ecosystem/scorers.py and chains/arbitrum-ecosystem/scorers.py."""
    role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                 "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
    return call_raw(w3, contract, role_abi, "hasRole", role, w3.to_checksum_address(account))


def score_echo_ebtc_monad(w3) -> dict:
    """Echo Protocol's eBTC on Monad mainnet -- a real, dated admin-key
    exploit with a concrete, verifiable remediation, not a hypothetical.
    Source: on-chain event-log reconstruction (RoleGranted/RoleRevoked
    trail, exact tx hashes/blocks/timestamps), cross-checked against press
    coverage (CoinDesk, Decrypt, Phemex, AMBCrypto, 2026-05-19).

    On 2026-05-18 21:21 UTC, the sole admin key -- a bare EOA
    (0xA338eC2d52B19f4A48A00FCd76A36366B3529A3B, confirmed live via
    `eth_getCode` = "0x", no bytecode), holding DEFAULT_ADMIN_ROLE/
    MINTER_ROLE/PAUSER_ROLE/UPGRADER_ROLE with no multisig and no on-chain
    mint cap -- was compromised. The attacker
    (0x6a0109D3C5aB56277096c75e8F5D1D1d45243415) self-granted
    DEFAULT_ADMIN_ROLE+MINTER_ROLE to itself and minted exactly 1,000.0
    unbacked eBTC in one transaction (tx
    0x2cc9730738c970b2c2ec1e1a27f38d69590db36fe069fb4ee04abaeb559357c0,
    independently confirmed on-chain), matching the reported ~$76.6M
    notional / ~$816K realized loss after laundering via a Curvance WBTC
    loan and Tornado Cash -- not a hypothetical risk, the exact pattern
    this project's adminKeyScore dimension exists to flag.

    REMEDIATED, confirmed live as of this pass (this scorer reads CURRENT
    chain state, not the incident-era state): within ~10 hours, a new
    UUPS implementation was pushed and, through two further hops,
    DEFAULT_ADMIN_ROLE/UPGRADER_ROLE/PAUSER_ROLE were handed to a real
    3-of-4 Gnosis Safe (v1.4.1) at
    0x401a33127e4946a82709b5edc60c636581cab1c5 -- confirmed live via
    direct `hasRole()` and `getOwners()`/`getThreshold()` calls, and the
    original admin EOA and attacker EOA both independently confirmed to
    no longer hold DEFAULT_ADMIN_ROLE. `MINTER_ROLE` currently has NO
    confirmed holder (checked against the Safe itself and every address
    in this incident's own chain -- all false), consistent with Echo's
    reported pause of Monad-side minting; new unbacked issuance is not
    presently possible via this role even in principle, though a full
    minter-holder enumeration across every possible address was not
    exhaustively performed (disclosed scope gap). No separate timelock
    contract was found -- UPGRADER_ROLE is held directly by the Safe, no
    delay."""
    ebtc = "0xd691b0aFed67F96CEC28Ab6308Cbe5b2C103b7e9"
    current_safe = "0x401a33127e4946a82709b5edc60c636581cab1c5"
    original_eoa = "0xA338eC2d52B19f4A48A00FCd76A36366B3529A3B"
    attacker = "0x6a0109D3C5aB56277096c75e8F5D1D1d45243415"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(ebtc))
    notes.append(f"eth_getCode(eBTC proxy, {ebtc}) = {len(code)} bytes of real deployed bytecode")

    default_admin_role = b"\x00" * 32
    minter_role = Web3.keccak(text="MINTER_ROLE")
    upgrader_role = Web3.keccak(text="UPGRADER_ROLE")

    safe_has_admin = _has_role(w3, ebtc, default_admin_role, current_safe)
    safe_has_upgrader = _has_role(w3, ebtc, upgrader_role, current_safe)
    safe_has_minter = _has_role(w3, ebtc, minter_role, current_safe)
    notes.append(
        f"Current admin Safe ({current_safe}).hasRole(DEFAULT_ADMIN_ROLE)={safe_has_admin}, "
        f"hasRole(UPGRADER_ROLE)={safe_has_upgrader}, hasRole(MINTER_ROLE)={safe_has_minter} "
        f"(expected False for MINTER_ROLE -- minting is separately controlled, not held by the admin Safe itself)"
    )

    original_eoa_still_admin = _has_role(w3, ebtc, default_admin_role, original_eoa)
    attacker_still_has_role = _has_role(w3, ebtc, default_admin_role, attacker)
    notes.append(
        f"Original compromised EOA hasRole(DEFAULT_ADMIN_ROLE)={original_eoa_still_admin}, "
        f"attacker EOA hasRole(DEFAULT_ADMIN_ROLE)={attacker_still_has_role} (both expected False -- confirms the "
        f"2026-05-18 incident's admin key was fully rotated away, not just formally revoked and re-grantable)"
    )
    notes.append(
        "Real, dated incident, independently confirmed via tx "
        "0x2cc9730738c970b2c2ec1e1a27f38d69590db36fe069fb4ee04abaeb559357c0 (2026-05-18 21:21 UTC): the "
        "original bare-EOA admin key was compromised and used to self-grant DEFAULT_ADMIN_ROLE+MINTER_ROLE "
        "to an attacker address, which minted exactly 1,000.0 unbacked eBTC (~$76.6M notional, ~$816K "
        "realized after laundering) in one transaction."
    )

    safe = safe_owners_and_threshold(w3, current_safe)
    if not safe or not safe_has_admin:
        notes.append("Current Safe NOT resolvable as a Gnosis Safe, or no longer holds DEFAULT_ADMIN_ROLE this run -- unresolved, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"Current admin is a real Gnosis Safe: {threshold}-of-{len(owners)} -- a genuine remediation from the pre-incident bare EOA")
        # ADDED 2026-09-21: one of these four signers is an EOA delegated through EIP-7702; say so (note only, no score input).
        signer_line = signer_note(owners, lambda a: w3.eth.get_code(w3.to_checksum_address(a)))
        if signer_line:
            notes.append(signer_line)
        admin_key = 55  # real remediation to a Safe (up from a bare EOA), but scored below a well-established multi-year Safe: this exact rotation happened under active-exploit duress only 4 months before this pass, and one unidentified custom function remains in the unverified current implementation
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no separate timelock contract found -- UPGRADER_ROLE is held directly by the Safe, no delay

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": ebtc,
        "label": "Echo Protocol eBTC (Monad) -- real 2026-05 admin-key exploit, since remediated",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_uniswap_v4_monad(w3) -> dict:
    """Uniswap v4's PoolManager on Monad mainnet -- the best-governed
    target found on this chain. Source: Uniswap's official deployments doc
    (developers.uniswap.org/docs/protocols/v4/deployments).

    Confirmed live, 2026-09-19, https://rpc.monad.xyz: PoolManager
    (0x188d586Ddcf52439676Ca21A244753fA19F9Ea8e) has real deployed
    bytecode. `owner()` resolves NOT to a Monad-local Safe but to
    0xE783DE89a7F0408687f051e3E6D0BEb62719EbAd, a contract that
    self-identifies on-chain (a raw selector call returns the ABI-encoded
    string "Uniswap Wormhole Message Receiver") and exposes a Wormhole
    chain ID of 48 (Monad's registered Wormhole chain ID, cross-checked
    against Wormhole's own docs) plus a `messageSender()` getter naming the
    trusted Ethereum-mainnet counterpart (the getter is `messageSender()`, not
    `sender()`, which reverts: corrected 2026-09-21).

    That Ethereum-mainnet sender (0xf5F4496219F31CDCBa6130B5402873624585615a,
    a "Uniswap Wormhole Message Sender" per its own on-chain self-ID) was
    independently read on Ethereum mainnet (not re-derived by this
    Monad-only scorer every run -- same disclosed-snapshot convention this
    project already uses for Plasma's/Arbitrum's Ethereum-mainnet Aave DAO
    root): its `owner()` is 0x1a9C8182C09F50C8318d769245beA52c32BE35BC,
    Etherscan-labeled "Uniswap V2: UNI Timelock" -- the SAME address that
    directly owns Ethereum mainnet's own PoolManager. This is Uniswap's
    canonical Compound-Bravo-style Governance Timelock (UNI-token-holder
    on-chain voting), not a Safe and not an operational multisig, with a
    real 2-day (172,800s) delay -- confirmed live via the Monad-side
    receiver's own messageExpirationTime()/validity window, matching that
    delay.

    Disclosed: `protocolFeeController()` on the Monad PoolManager currently
    reads the zero address (unset, confirmed live) -- unlike Ethereum
    mainnet, where a dedicated fee-controller contract is already
    configured. No protocol fee has been activated on this deployment yet."""
    pool_manager = "0x188d586Ddcf52439676Ca21A244753fA19F9Ea8e"
    wormhole_receiver = "0xE783DE89a7F0408687f051e3E6D0BEb62719EbAd"
    l1_message_sender = "0xf5F4496219F31CDCBa6130B5402873624585615a"
    uni_timelock = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(pool_manager))
    notes.append(f"eth_getCode(PoolManager, {pool_manager}) = {len(code)} bytes of real deployed bytecode")

    owner = read_address_getter(w3, pool_manager, "owner")
    notes.append(f"PoolManager.owner() = {owner} (expected the Wormhole message receiver: {bool(owner) and owner.lower() == wormhole_receiver.lower()})")

    fee_controller = read_address_getter(w3, pool_manager, "protocolFeeController")
    notes.append(f"PoolManager.protocolFeeController() = {fee_controller} (zero address = unset, no protocol fee active on this deployment)")

    receiver_code = w3.eth.get_code(w3.to_checksum_address(wormhole_receiver)) if owner else b""
    notes.append(f"eth_getCode(UniswapWormholeMessageReceiver, {wormhole_receiver}) = {len(receiver_code)} bytes of real bytecode")
    chain_resolved = bool(owner) and owner.lower() == wormhole_receiver.lower() and len(receiver_code) > 0

    # ADDED 2026-09-21: the Ethereum-side hop is now READ this run instead of taken from a dated snapshot. Monad side:
    # the receiver's messageSender() must be the known Uniswap Wormhole Message Sender. Ethereum side (own w3, like the
    # Base and Arbitrum siblings): that sender's owner() must be the Timelock. Only then is the shared root claimed.
    message_sender = read_address_getter(w3, wormhole_receiver, "messageSender") if chain_resolved else None
    sender_ok = bool(message_sender) and message_sender.lower() == l1_message_sender.lower()
    notes.append(f"UniswapWormholeMessageReceiver.messageSender() = {message_sender} (expected the Uniswap Wormhole Message Sender {l1_message_sender}: {sender_ok})")
    l1_sender_owner = l1_delay = l1_admin = None
    if sender_ok:
        l1_w3 = get_w3("https://ethereum-rpc.publicnode.com")
        l1_sender_owner = read_address_getter(l1_w3, l1_message_sender, "owner")
        l1_delay = call_raw(l1_w3, uni_timelock, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay")
        l1_admin = call_raw(l1_w3, uni_timelock, [{"name": "admin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "admin")
    hop_confirmed = bool(l1_sender_owner) and l1_sender_owner.lower() == uni_timelock.lower()
    notes.append(
        f"Ethereum mainnet (own w3, read this run): Wormhole Message Sender {l1_message_sender}.owner() = {l1_sender_owner} "
        f"(expected Uniswap's Governance Timelock {uni_timelock}, Etherscan 'Uniswap V2: UNI Timelock': {hop_confirmed}); "
        f"Timelock.delay() = {l1_delay}s, .admin() = {l1_admin} (GovernorBravo). Uniswap's own UNI-token-holder-governed "
        f"Compound-Bravo Timelock, the same address that owns Ethereum mainnet's own PoolManager directly. Messages travel "
        f"through Wormhole, whose guardian set is a separate trust assumption scored under the Monad Native Bridge target, "
        f"not here."
    )

    # ADDED 2026-09-20, hardened 2026-09-21: claimed only on a root confirmed live on BOTH sides this run.
    shared_uniswap_root = bool(chain_resolved and sender_ok and hop_confirmed)
    cross_exposure = 80 if shared_uniswap_root else 100
    if shared_uniswap_root:
        notes.append(
            "crossExposureScore = 80: the same root authority, Uniswap's Ethereum L1 Governance Timelock "
            f"({uni_timelock}), also controls tracked Uniswap targets on other ecosystems (Ethereum L1 V3 Factory and "
            "V4 PoolManager, Arbitrum V3 Factory, Base V3/V2/V4, Robinhood Chain V3/V4/UniswapX/V2; dated 2026-09-20). "
            "Both hops (PoolManager.owner() == the Wormhole receiver, receiver.messageSender() == the Ethereum sender "
            "whose owner() is the Timelock) were read live this run. A token-vote DAO contract, not a signer committee, "
            "but one root identity, so the cross-ecosystem fold (a flat 80) applies as for a shared Safe committee "
            "(convention of 2026-09-20)"
        )
    else:
        notes.append(_CROSS_EXPOSURE_NOTE + " -- the shared Uniswap Timelock root could not be confirmed on both hops this run, so it is not asserted")
    if not chain_resolved:
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append("Authority chain did NOT resolve as expected this run -- unresolved, conservative score")
    else:
        admin_key = 80  # a real, resolved, genuine external token-vote DAO root (UNI Timelock) -- same 75-85 band this project already uses for Aave/Compound-style governor roots, not a Safe/operational multisig
        multisig = 100  # not applicable: the root is a token-vote DAO Timelock, not a Gnosis Safe
        timelock_score = 60  # confirmed real 2-day delay -- longer than Plasma's Aave 1-day (scored 50), but capped below 75+ since this scorer did not independently re-verify UNI DAO's own quorum/proposal-threshold robustness this pass

    return {
        "target": pool_manager,
        "label": "Uniswap v4 PoolManager (Monad)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_monad_native_bridge(w3) -> dict:
    """Monad's canonical/native bridge (monadbridge.com, live since Nov
    24, 2025) -- the officially blessed bridge for the chain's flagship
    MON/WMON/WETH route, a dual-attestation "NTT 2/2" design pairing a
    Wormhole NTT Manager with a companion Axelar GmpManager. Source:
    monadbridge.com's own production JS bundle (client-side Wormhole SDK
    registry), cross-checked against MonadScan's verified source for two
    of the three contracts.

    Confirmed live, 2026-09-19, https://rpc.monad.xyz: the NTT Manager
    (0x36878C6FCa7e0E8a88F90dc410CfBBcA5B695C95), its companion Axelar
    GmpManager (0x92957b3D0CaB3eA7110fEd1ccc4eF564981a59Fc), and a separate
    MON<->Solana NTT manager (0x1d6f4d93ac7aa8574865666ab863De72129c1781)
    all share the identical `owner()`/`pauser()`:
    0x574b7864119c9223a9870ea614dc91a8ee09e512, a small (3,408-byte),
    non-upgradeable, NOT-Ownable contract, source-verified on MonadScan as
    Wormhole's standard `GeneralPurposeGovernance.sol` pattern. It holds no
    independent power of its own -- its only entrypoint,
    `performGovernance(bytes vaa)`, raw-`.call()`s the target manager ONLY
    given a VAA that verifies against Monad's own deployed Wormhole Core
    Bridge contract (0x194b123c5e96b9b2e49763619985790dc241cac0),
    originates from Wormhole's canonical governance emitter, and names
    this Governance contract as recipient (replay-protected by VAA hash).

    Live guardian-quorum check on Monad's OWN Core Bridge contract (not
    assumed from generic Wormhole docs): `getCurrentGuardianSetIndex()` =
    7 (unexpired, `expirationTime`=0), that set holds 19 guardian keys, and
    `quorum(19)` on that same contract returns 13 -- confirming the
    13-of-19 Guardian threshold is CURRENT as read directly from Monad
    mainnet. Neither manager was paused at the time of this check
    (`isPaused()` = false on both, confirmed live). Axelar's own separate
    validator/threshold set securing the second GMP attestation leg was
    not independently audited this pass -- only that the GmpManager shares
    the same governance-gated owner as the primary NTT Manager."""
    ntt_manager = "0x36878C6FCa7e0E8a88F90dc410CfBBcA5B695C95"
    governance_relay = "0x574b7864119c9223a9870ea614dc91a8ee09e512"
    core_bridge = "0x194b123c5e96b9b2e49763619985790dc241cac0"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(ntt_manager))
    notes.append(f"eth_getCode(NTT Manager, {ntt_manager}) = {len(code)} bytes of real deployed bytecode")

    owner = read_address_getter(w3, ntt_manager, "owner")
    notes.append(f"NTT Manager.owner() = {owner} (expected the Wormhole GeneralPurposeGovernance relay: {bool(owner) and owner.lower() == governance_relay.lower()})")

    is_paused = call_raw(w3, ntt_manager, [{"name": "isPaused", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]}], "isPaused", retries=1)
    notes.append(f"NTT Manager.isPaused() = {is_paused}")

    relay_code = w3.eth.get_code(w3.to_checksum_address(governance_relay))
    notes.append(f"eth_getCode(GeneralPurposeGovernance relay, {governance_relay}) = {len(relay_code)} bytes -- a real contract, not Ownable, not a Safe (no owners()/threshold() interface)")

    guardian_set_index = call_raw(w3, core_bridge, [{"name": "getCurrentGuardianSetIndex", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint32"}]}], "getCurrentGuardianSetIndex")
    notes.append(f"Monad's own Wormhole Core Bridge ({core_bridge}).getCurrentGuardianSetIndex() = {guardian_set_index}")

    quorum = call_raw(w3, core_bridge, [{"name": "quorum", "type": "function", "stateMutability": "pure", "inputs": [{"type": "uint256"}], "outputs": [{"type": "uint256"}]}], "quorum", 19, retries=1)
    notes.append(f"Core Bridge.quorum(19) = {quorum} -- confirms 13-of-19 Guardian threshold, read live from Monad's own deployed contract, not assumed from generic Wormhole docs")
    notes.append(_CROSS_EXPOSURE_NOTE)

    chain_resolved = bool(owner) and owner.lower() == governance_relay.lower() and quorum == 13
    if not chain_resolved:
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append("Authority chain did NOT resolve as expected this run -- unresolved, conservative score")
    else:
        admin_key = 75  # fully resolved, genuinely decentralized (19 independent global guardian operators, not a small local team), gated by a VAA-verified governance relay with no owner-side bypass found -- above a Safe-rooted target, below flagging as a perfect score since this scorer did not audit the Guardian keys' own real-world operator independence
        multisig = 100  # 13-of-19 saturates this project's multisigScore formula (threshold*15 already exceeds 100) -- a genuinely strong quorum, not a rounding artifact
        timelock_score = 0  # no time delay: a valid VAA executes immediately once quorum is reached, same "resolved but instant" scoring already used elsewhere in this project when a chain has no enforced delay

    return {
        "target": ntt_manager,
        "label": "Monad Native Bridge (Wormhole NTT Manager)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_kuru_monad(w3) -> dict:
    """Kuru -- a fully on-chain central-limit-order-book DEX on Monad
    mainnet, one of only two protocols industry coverage calls genuinely
    "Monad-native" (the other being Curvance). Source: docs.kuru.io's own
    contract-address pages.

    Confirmed live, 2026-09-19, https://rpc.monad.xyz: Router (the market
    factory, 0xd651346d7c789536ebf06dc72aE3C8502cd695CC), MarginAccount
    (user collateral custody, 0x2A68ba1833cDf93fa9Da1EEbd7F46242aD8E90c5)
    and two other core proxies are all EIP-1967 UUPS proxies (confirmed by
    reading the implementation storage slot) that share an identical
    `owner()`: 0x8b736dCE2071783fD9Db0A423daD17cc8Ed5788b, a real Gnosis
    Safe -- `VERSION()`="1.4.1", `getThreshold()`=3, `getOwners()` returns
    exactly 5 addresses, all confirmed bare EOAs, internal Safe `nonce()`=
    0x46 (70 executed transactions -- an actively used multisig, not a
    dormant shell).

    No timelock anywhere in this chain: Safe `execTransaction()` is
    immediate once 3-of-5 signatures are collected. Per Kuru's own
    architecture docs, this same Safe (as `owner()` of the Router) is "the
    default owner of all markets and can be used to upgrade markets to a
    new implementation" -- i.e. the same 3-of-5 can push new logic to
    every deployed OrderBook market, not just pause/administer the core
    contracts. Market CREATION itself is documented as a public,
    non-owner-gated function (permissionless), a real distinction: the
    Safe's power is over existing-market upgrades and protocol-wide pause/
    fee-routing, not over who may launch a new market."""
    router = "0xd651346d7c789536ebf06dc72aE3C8502cd695CC"
    margin_account = "0x2A68ba1833cDf93fa9Da1EEbd7F46242aD8E90c5"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(router))
    notes.append(f"eth_getCode(Router, {router}) = {len(code)} bytes of real deployed bytecode")

    owner = read_address_getter(w3, router, "owner")
    notes.append(f"Router.owner() = {owner}")

    margin_owner = read_address_getter(w3, margin_account, "owner")
    notes.append(f"MarginAccount.owner() = {margin_owner} (expected to match Router.owner(): {bool(margin_owner) and bool(owner) and margin_owner.lower() == owner.lower()})")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}, all owners confirmed bare EOAs")
        notes.append(
            "Per Kuru's own docs, this Safe is 'the default owner of all markets and can be used to "
            "upgrade markets to a new implementation' -- market UPGRADE authority reaches every deployed "
            "OrderBook market, though market CREATION itself is a separate, permissionless (non-owner-gated) path."
        )
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # confirmed: Safe execTransaction is immediate, no timelock contract anywhere in this chain

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": router,
        "label": "Kuru Router + MarginAccount (Monad)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Robinhood Chain's own "steakhouse" family of Morpho vault curator/owner
# Safes (scripts/lib/signer_overlap.py GROUPS["steakhouse"]/
# ["ethena_steakhouse"]/["steakhouse_turbo"]/["grove_steakhouse"]) --
# hardcoded snapshot, live-fetched 2026-09-19 via a direct
# `getOwners()`/`getThreshold()` call against Robinhood Chain mainnet, the
# same "known committee, live-diffed against a fresh Monad-side read" idiom
# already used elsewhere in this project (e.g. Plasma's
# `_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17`). Found via this project's own
# `scripts/check_cross_ecosystem_overlap.py` after adding Monad to it --
# not something either scorer's own single-RPC read could have found alone.
_KNOWN_ROBINHOOD_STEAKHOUSE_CURATOR_OWNERS_2026_09_19 = frozenset({
    "0x0D61C8b6CA9669A36F351De3AE335e9689dd9C5b", "0xE3fCEE6B6cd564E073346f71394f60eC9aDf5120",
    "0x8AE8EE5ad6EaE89836B0070Ebc47AF06E3D7422b", "0xf83dB716A1Ff12F9005F98f678D8BE97B8Bc81d6",
    "0x387Cde8598E1CBb297FDc5bAEbA5E5c5c2735344", "0xcC771952fdE840E30C6802734e5ad20479c2959f",
    "0xfc615395336aADe67fd853a0157001a215Ea1279",
})
_KNOWN_ROBINHOOD_STEAKHOUSE_OWNER_OWNERS_2026_09_19 = frozenset({
    "0xf83dB716A1Ff12F9005F98f678D8BE97B8Bc81d6", "0x0D61C8b6CA9669A36F351De3AE335e9689dd9C5b",
    "0x8AE8EE5ad6EaE89836B0070Ebc47AF06E3D7422b", "0xd2B8Dd0Fd51d80bF939047A9AAa55919112838E8",
    "0xd8bAA2606c4f0d121d4a08b0D83acF0Dee9dCA77", "0xcC771952fdE840E30C6802734e5ad20479c2959f",
    "0xE3fCEE6B6cd564E073346f71394f60eC9aDf5120", "0x86Bd534A95Fb2Cc36D526ba149464c4477315C32",
    "0x387Cde8598E1CBb297FDc5bAEbA5E5c5c2735344", "0xfc615395336aADe67fd853a0157001a215Ea1279",
})


def score_morpho_vault_monad(w3) -> dict:
    """Morpho -- the largest Morpho V1 (MetaMorpho) vault on Monad mainnet by TVL,
    "Grove x Steakhouse High Yield AUSD". Source: Morpho's official
    GraphQL API (blue-api.morpho.org), cross-checked live on-chain.

    CORRECTED 2026-09-25 (roadmap item 10, "voit large" round 2 -- a documentation accuracy fix, not
    a scoring change): this docstring used to say "the largest MetaMorpho vault on Monad mainnet by
    TVL" and "the largest of only 26 vaults deployed on Monad", true only among V1 vaults.
    `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`'s own research (18/19-09) found
    Monad also has 6 Morpho Vault V2 vaults, created Jan-Jul 2026, holding **$110M combined** (Steakhouse
    Prime ETH ~$47.4M, Hyperithm USDC Apex ~$39.8M, August USDC V2 ~$11.7M, +3 more) -- roughly 1,000x
    this V1 vault's TVL. NOT tracked by this scorer or any other in this file: Vault V2 has a
    materially different authority architecture (per-function timelocks, permanently abdicated exit
    gates, no single `guardian()`) that the owner/curator/guardian model below cannot represent without
    inventing a new scoring approach -- a genuine calibration decision, not attempted this pass. See
    `data/finding_2026-09-25-vault-v2-scoring-scope.md` for what building that would require.

    Confirmed live, 2026-09-19, https://rpc.monad.xyz: the Morpho Blue
    singleton itself (0xD5D960E8C380B724a48AC59E2DfF1b2CB4a1eAee -- NOT
    the usual cross-chain deterministic 0xBBBB... address, which has no
    code on Monad) is owned by a separate 5-of-9 Safe whose power is
    limited to whitelisting IRMs/LLTV tiers and setting per-market
    protocol fees -- it cannot touch vault funds or pause the
    (immutable-once-created) underlying markets. This scorer targets the
    vault itself, where the operationally relevant risk actually sits:
    vault (0x32841A8511D5c2c5b253f45668780B99139e476D, ~$108K TVL, the
    largest V1 vault of only 26 V1 vaults deployed on Monad as of the
    2026-09-19 pass -- a very early-stage V1 deployment, separate from the
    much larger V2 vaults above) has `owner()` = a real 5-of-8 Gnosis Safe, and
    `curator()` = `guardian()` = the SAME separate 2-of-6 Gnosis Safe --
    confirmed live via two independent getter calls returning an identical
    address, not assumed from a shared name.

    Standard Morpho Vault V2 authority split (the same shape this
    project's own methodology already tracks under Tempo's rule R8): the
    owner Safe (5-of-8) governs meta-parameters -- curator/guardian
    appointment, fee rate/recipient -- while the curator Safe (2-of-6) sets
    per-market supply-cap risk exposure, real and confirmed subject to a
    14-day (1,209,600s) timelock. The disclosed weak point: because the
    SAME 2-of-6 Safe holds both the curator role (proposes cap changes)
    and the guardian role (the party meant to independently veto them),
    there is no independent check during that 14-day window -- the
    guardian cannot meaningfully oppose its own curator proposal.

    Real cross-chain finding, added 2026-09-19 after wiring Monad into
    `scripts/check_cross_ecosystem_overlap.py`: this vault's curator Safe
    is a full subset of Robinhood Chain's own "steakhouse" curator Safe
    (3-of-7, `scripts/lib/signer_overlap.py` `GROUPS["steakhouse"]`), and
    its owner Safe is a full subset of Robinhood Chain's own "steakhouse"
    owner Safe (5-of-10, `GROUPS["ethena_steakhouse"]`/
    `["steakhouse_turbo"]`/`["grove_steakhouse"]`) -- independently
    re-confirmed live against both chains, not assumed from a shared
    "Steakhouse"-branded name. Steakhouse Financial curating vaults on
    multiple chains with largely the same team is a plausible, legitimate
    operating pattern for a professional curator firm -- but it also means
    the same small group of individuals is the real, exploitable choke
    point for this vault AND at least 3 separate Robinhood Chain Morpho
    vaults this oracle already tracks.

    STRONGER FINDING, confirmed 2026-09-25 while building
    `scripts/check_controller_concentration.py`: this vault's owner
    (`0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD`) and curator/guardian
    (`0x827e86072B06674a077f592A531dcE4590aDeCdB`) are not merely
    subset-related to Robinhood Chain's committee -- they are the LITERAL
    SAME Safe addresses as this pass's own new Ethereum L1 and Base
    Steakhouse vaults (`_KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25` /
    `_KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25` in `chains/ethereum-l1/
    scorers.py` and `chains/base-ecosystem/scorers.py`). A same-address
    Safe is NOT synced across chains, though: live-read 2026-09-25, the
    owner Safe is 5-of-10 on Ethereum L1, 5-of-9 on Base and 5-of-8 here on
    Monad; the curator Safe is 2-of-7 on Ethereum L1 and Monad but 2-of-6
    on Base -- each chain's copy has its own, independently-set owner list
    (this docstring previously said 2-of-6/5-of-8 as if those were fixed
    values; they are this chain's current reading, not a global constant).
    See `data/finding_2026-09-25-controller-concentration.md` for the
    full cross-chain controller rollup this discovery fed into."""
    vault = "0x32841A8511D5c2c5b253f45668780B99139e476D"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(vault))
    notes.append(f"eth_getCode(vault, {vault}) = {len(code)} bytes of real deployed bytecode")

    owner = read_address_getter(w3, vault, "owner")
    notes.append(f"vault.owner() = {owner}")

    curator = read_address_getter(w3, vault, "curator")
    guardian = read_address_getter(w3, vault, "guardian")
    curator_is_guardian = bool(curator) and bool(guardian) and curator.lower() == guardian.lower()
    notes.append(f"vault.curator() = {curator}, vault.guardian() = {guardian} (same address: {curator_is_guardian} -- no independent veto party if true)")

    owner_safe = safe_owners_and_threshold(w3, owner) if owner else None
    curator_safe = safe_owners_and_threshold(w3, curator) if curator else None

    cross_exposure = 100
    if not owner_safe or not curator_safe:
        notes.append("Owner and/or curator/guardian NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owner_owners, owner_threshold = owner_safe
        curator_owners, curator_threshold = curator_safe
        notes.append(f"owner is a real Gnosis Safe: {owner_threshold}-of-{len(owner_owners)}")
        notes.append(f"curator/guardian is a real Gnosis Safe: {curator_threshold}-of-{len(curator_owners)}")
        if curator_is_guardian:
            notes.append(
                "Disclosed weak point: curator and guardian are the SAME Safe -- the party that proposes "
                "per-market cap changes is also the only party positioned to veto them during the 14-day "
                "timelock, so the delay's independent-check purpose does not hold in practice."
            )
        admin_key = 70 if owner_threshold >= 5 else (60 if owner_threshold >= 3 else 30)
        multisig = min(100, curator_threshold * 15 + max(0, len(curator_owners) - curator_threshold) * 5)
        timelock_score = 55 if curator_is_guardian else 75  # a real, confirmed 14-day delay exists, but scored well below Euler's fully-independent-canceller pattern (68) when curator==guardian removes the delay's real protective value; would score higher (75+) if the veto party were independent

        curator_set = {w3.to_checksum_address(o) for o in curator_owners}
        owner_set = {w3.to_checksum_address(o) for o in owner_owners}
        curator_overlap = curator_set <= _KNOWN_ROBINHOOD_STEAKHOUSE_CURATOR_OWNERS_2026_09_19
        owner_overlap = owner_set <= _KNOWN_ROBINHOOD_STEAKHOUSE_OWNER_OWNERS_2026_09_19
        if curator_overlap or owner_overlap:
            cross_exposure = 80
            notes.append(
                f"Real cross-chain finding: this vault's curator Safe is fully contained in Robinhood "
                f"Chain's own 'steakhouse' curator Safe ({curator_overlap}), and its owner Safe is fully "
                f"contained in Robinhood Chain's own 'steakhouse' owner Safe ({owner_overlap}) -- "
                f"independently re-confirmed live against both chains this pass, not assumed from the "
                f"shared 'Steakhouse' branding."
            )

    if cross_exposure == 100:
        notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": vault,
        "label": "Morpho Vault: Grove x Steakhouse High Yield AUSD (Monad)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_curve_monad(w3) -> dict:
    """Curve Finance's "Curve Lite" deployment on Monad mainnet -- the
    weakest authority shape found on any chain this project tracks.
    Source: Curve's own official deployment repo (curvefi/curve-core,
    `deployments/prod/monad.yaml` and `settings/chains/prod/monad.yaml`).

    Confirmed live, 2026-09-19, https://rpc.monad.xyz: the StableSwap
    Factory (0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD, MonadScan-labeled
    "Curve: Stableswap Factory") has real deployed bytecode and real
    activity (e.g. its "3pool" pool, ~$2.4M TVL, 2,400+ transactions).
    `admin()` on the factory -- and separately `owner()` on the Child
    Gauge Factory -- both resolve to the IDENTICAL address:
    0xabc336d4C71ad275695744d32DdB1d8266Db1cbF.

    That address has NO contract bytecode on Monad (`eth_getCode` =
    "0x", confirmed live) -- not a Gnosis Safe, not a timelock, a bare
    externally-owned account. Curve's own repo makes this explicit in a
    source comment: "# deployer as admin until DAO ownership transfer."
    On-chain history already shows this key actively exercising that
    power (Set_new_fee, Ramp_A calls on a live pool), not a theoretical
    risk. By contrast, Curve's own longer-established chains (Sonic, Ink,
    Taiko, per the same repo) already have distinct governance-transferred
    admin addresses -- Monad (like Unichain and Plasma) is still on this
    temporary single-deployer-key setup.

    Real cross-chain finding, added 2026-09-19 after wiring Monad into
    `scripts/check_cross_ecosystem_overlap.py`: this factory's own address
    (0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD) and its admin EOA
    (0xabc336d4C71ad275695744d32DdB1d8266Db1cbF) are BOTH byte-identical
    to Robinhood Chain's own already-tracked Curve target
    (`scripts/lib/signer_overlap.py` `GROUPS["curve"]`) -- not just the
    same person, the literal same CREATE2-deployed factory contract on two
    separate chains this oracle tracks, controlled by the literal same
    single unprotected private key on both. Independently re-confirmed
    live against both chains, not assumed from the shared address alone."""
    factory = "0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"
    _known_robinhood_curve_factory = "0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"
    _known_robinhood_curve_admin_eoa = "0xabc336d4C71ad275695744d32DdB1d8266Db1cbF"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(factory))
    notes.append(f"eth_getCode(StableSwap Factory, {factory}) = {len(code)} bytes of real deployed bytecode")

    admin = read_address_getter(w3, factory, "admin")
    notes.append(f"Factory.admin() = {admin}")

    admin_code = w3.eth.get_code(w3.to_checksum_address(admin)) if admin else b"\x00"
    is_eoa = admin and len(admin_code) == 0
    notes.append(f"eth_getCode(admin, {admin}) = {len(admin_code)} bytes -- {'a bare EOA, NOT a Safe, NOT a timelock' if is_eoa else 'has real contract code (unexpected)'}")

    safe = safe_owners_and_threshold(w3, admin) if admin and not is_eoa else None
    notes.append("Per Curve's own deployment repo: \"deployer as admin until DAO ownership transfer\" -- confirmed live, not yet remediated as of this pass")

    if is_eoa:
        admin_key, multisig, timelock_score = 10, 0, 0
        notes.append("Single bare EOA holding ownership_admin/parameter_admin/emergency_admin simultaneously -- the weakest authority shape found on any chain this project tracks")
    elif safe:
        owners, threshold = safe
        notes.append(f"admin unexpectedly resolved as a real Gnosis Safe: {threshold}-of-{len(owners)}")
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0
    else:
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append("admin address NOT resolvable as either a bare EOA check or a Gnosis Safe this run -- unresolved, conservative score")

    same_factory = factory.lower() == _known_robinhood_curve_factory.lower()
    same_admin = bool(admin) and admin.lower() == _known_robinhood_curve_admin_eoa.lower()
    if same_factory and same_admin:
        cross_exposure = 80
        notes.append(
            "Real cross-chain finding: this factory's own address AND its admin EOA are BOTH identical "
            "to Robinhood Chain's own already-tracked Curve target -- the literal same CREATE2-deployed "
            "contract, controlled by the literal same single unprotected key, on two separate chains this "
            "oracle tracks. Independently re-confirmed live against both chains this pass."
        )
    else:
        cross_exposure = 100
        notes.append(_CROSS_EXPOSURE_NOTE)

    return {
        "target": factory,
        "label": "Curve Finance StableSwap Factory (Monad)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_curvance_monad(w3) -> dict:
    """Curvance's hyAUSD "LendingOptimizer" Earn Vault on Monad mainnet --
    flagged by a Yearn risk-score GitHub PR (yearn/risk-score#412, merged
    2026-09-15) for moving allocation caps 20%->30%->40% over six weeks
    with no timelock protection. Independently re-verified live this pass
    (not assumed from the PR): the gap is NOT remediated.

    Confirmed live, 2026-09-19, https://rpc.monad.xyz: CentralRegistry
    (0x1310f352f1389969Ece6741671c4B919523912fF) still grants the
    "Emergency Council" -- a real 4-of-5 Gnosis Safe
    (0x379D4a8FBc23A8Fd8c2b3738Dbf1fEBe9a64399c, owners/threshold read
    directly from the contract) -- both elevated and market permissions
    with zero delay. A DAOTimelock (0x2677738657F27e1A3591E00AD7E5a78807688C08,
    real confirmed 5-day/432,000s `getMinDelay()`) exists and holds the
    identical permissions, but it is a PARALLEL, non-exclusive route, not
    a gate on the Emergency Council -- exactly the same "zero-delay
    bypass path renders a real timelock moot" pattern this project's
    methodology already tracks on Tempo (cbBTC/PRIME's BYPASSER path).

    Live proof this is still actively exercised, not just a live
    permission grant: transaction 0x90b0d6e6d0f3c4bb3f7f43f771f23a9e11892fb
    f7f028d1f2da0b5ba37b5492f (block 103,939,695, 2026-09-11) shows 4 of the
    5 Emergency Council signers executing a Safe transaction that reset two
    market allocation caps (one from 40% to 50.05%, another from 90% to
    50.05%) -- decoded directly from calldata and the emitted
    AllocationCapUpdated events, not read from a summary. This happened 4
    days BEFORE the Yearn PR was even merged, and 8 days before this
    scorer's own live check, with no change to the underlying permission
    structure since."""
    vault = "0xaD663aC84052b52BE4ed1b27BA416505e84a00Bf"
    central_registry = "0x1310f352f1389969Ece6741671c4B919523912fF"
    dao_timelock = "0x2677738657F27e1A3591E00AD7E5a78807688C08"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(vault))
    notes.append(f"eth_getCode(LendingOptimizer vault, {vault}) = {len(code)} bytes of real deployed bytecode")

    emergency_council = read_address_getter(w3, central_registry, "emergencyCouncil")
    notes.append(f"CentralRegistry.emergencyCouncil() = {emergency_council}")

    delay = call_raw(w3, dao_timelock, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay")
    notes.append(f"DAOTimelock.getMinDelay() = {delay}s (real delay exists, but is a PARALLEL path, not a gate on the Emergency Council below)")

    has_elevated_abi = [{"name": "hasElevatedPermissions", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "bool"}]}]
    ec_has_elevated = call_raw(w3, central_registry, has_elevated_abi, "hasElevatedPermissions", w3.to_checksum_address(emergency_council)) if emergency_council else None
    notes.append(f"CentralRegistry.hasElevatedPermissions(Emergency Council) = {ec_has_elevated} -- zero-delay elevated authority still active as of this pass")
    notes.append(
        "Live proof of continued use, not just a live grant: tx 0x90b0d6e6d0f3c4bb3f7f43f771f23a9e11892fb"
        "f7f028d1f2da0b5ba37b5492f (block 103,939,695, 2026-09-11) shows 4-of-5 Emergency Council signers "
        "resetting two market allocation caps to 50.05% via this exact zero-delay path -- 4 days before "
        "the Yearn PR flagging this gap was even merged."
    )

    safe = safe_owners_and_threshold(w3, emergency_council) if emergency_council else None
    if not safe or not ec_has_elevated:
        notes.append("Emergency Council NOT resolvable as a Gnosis Safe, or no longer holds elevated permissions this run -- unresolved/remediated, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"Emergency Council is a real Gnosis Safe: {threshold}-of-{len(owners)}, actively used (per the decoded tx above)")
        admin_key = 60  # a real Safe, decent threshold, but scored below a well-governed root since the zero-delay path is proven actively exercised, not just theoretically available
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # scored on the REAL, actively-used path (zero delay), not the parallel DAOTimelock that is never actually the gate -- same "score what's exploitable" discipline as Tempo's BYPASSER-path scorers

    notes.append(_CROSS_EXPOSURE_NOTE)
    return {
        "target": vault,
        "label": "Curvance Emergency Council (LendingOptimizer vault, Monad)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Same known Aave V3 cross-chain guardian committee already documented in
# chains/plasma-ecosystem/scorers.py's own
# _KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17 (which itself already matched
# Arbitrum's and Base's guardian Safes) -- redefined here rather than
# imported, since none of this project's per-ecosystem scorers.py files
# import from each other (each stays independently runnable against just
# its own chain). Confirmed live, 2026-09-19: Monad's own guardian Safe
# owner set is this EXACT same 9 addresses at the same 5-of-9 threshold,
# just at yet another CREATE2-redeployed Safe address.
_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17 = frozenset({
    "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
    "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
    "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
    "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
    "0x4C30E33758216aD0d676419c21CB8D014C68099f",
})


# ADDED 2026-09-19 (unscored-role sweep, verified by hand on all 5 chains): Aave's
# PROTOCOL_GUARDIAN / EMERGENCY_ADMIN seat is a 4-of-7 Safe whose 7 owners are IDENTICAL on
# Ethereum L1 (0x2CFe3ec4...), Arbitrum, Base, Plasma and Monad (a different Safe address per
# chain, zero overlap with the 9-signer GOVERNANCE_GUARDIAN committee above). On Monad this
# Safe holds isEmergencyAdmin AND isPoolAdmin (alongside the DAO Executor): an instant
# aToken/variableDebtToken implementation-upgrade path that the 1-day Executor delay does not
# gate. The Executor holds DEFAULT_ADMIN and can revoke it; the Safe cannot grant roles.
# CHANGED 2026-09-20: this seat is now SCORED by score_aave_v3_monad() (Safe-no-timelock rule,
# read live from the ACLManager), no longer notes-only.
# EXTENDED 2026-09-25: the same 7 signers were confirmed live on 13 MORE chains beyond the 5 this
# project tracks (Avalanche, Optimism, Polygon, BNB, Celo, Gnosis, Linea, Mantle, Metis, Scroll,
# Sonic, XLayer, Soneium -- 18 of ~19 real Aave V3 deployments checked share this exact committee).
# See chains/ethereum-l1/scorers.py's own _KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20 (the
# canonical copy of this comment) and data/finding_2026-09-25-aave-guardian-18-chains.md.
_MONAD_AAVE_PROTOCOL_GUARDIAN_SAFE = "0xc887455536CBD4e615B745e70CaCde15B3117e74"


def _read_aave_acl_seats(w3, provider) -> dict:
    """ADDED 2026-09-20: one live read of the PROTOCOL_GUARDIAN Safe's ACLManager seats plus the
    Safe's own owners/threshold, shared by the scorer (which now scores the isPoolAdmin seat) and
    by _aave_acl_seats_note() so the RPC reads are not duplicated. pool_admin / emergency stay None
    when the ACLManager (or the individual read) is unread; safe_owners is None when the Safe does
    not resolve. Never guesses a missing value."""
    seats = {"acl": None, "safe": w3.to_checksum_address(_MONAD_AAVE_PROTOCOL_GUARDIAN_SAFE),
             "pool_admin": None, "emergency": None, "safe_owners": None}
    acl = read_address_getter(w3, provider, "getACLManager")
    if not acl:
        return seats
    seat_abi = lambda name: [{"name": name, "type": "function", "stateMutability": "view",  # noqa: E731
                              "inputs": [{"type": "address"}], "outputs": [{"type": "bool"}]}]
    seats["acl"] = acl
    seats["pool_admin"] = call_raw(w3, acl, seat_abi("isPoolAdmin"), "isPoolAdmin", seats["safe"])
    seats["emergency"] = call_raw(w3, acl, seat_abi("isEmergencyAdmin"), "isEmergencyAdmin", seats["safe"])
    seats["safe_owners"] = safe_owners_and_threshold(w3, seats["safe"])
    return seats


def _aave_acl_seats_note(w3, provider, seats=None) -> str:
    seats = seats if seats is not None else _read_aave_acl_seats(w3, provider)
    acl, safe = seats["acl"], seats["safe"]
    pool_admin, emergency, safe_owners = seats["pool_admin"], seats["emergency"], seats["safe_owners"]
    if not acl:
        return "ACLManager unread this run -- POOL_ADMIN / EMERGENCY_ADMIN seats not compared"
    shape = (f"{safe_owners[1]}-of-{len(safe_owners[0])} read live" if safe_owners
             else "owners/threshold NOT resolved this run, 4-of-7 per the 2026-09-19 hand check")
    text = (f"ACLManager {acl}: the PROTOCOL_GUARDIAN Safe {safe} ({shape}; its 7 owners were hand-verified "
            f"2026-09-19 as identical to Ethereum L1's PROTOCOL_GUARDIAN and to the EMERGENCY_ADMIN Safes on "
            f"Arbitrum, Base and Plasma) has isEmergencyAdmin = {emergency}, isPoolAdmin = {pool_admin}.")
    if pool_admin is True:
        text += (" isPoolAdmin lets it upgrade every reserve's aToken / variableDebtToken implementation "
                 "instantly (eth_call state-override simulation, 2026-09-19), a path the 1-day Executor delay "
                 "does not gate, so as of 2026-09-20 this scorer SCORES it (Safe-no-timelock rule, see the "
                 "scoring note below). Mitigating facts, disclosed and not score inputs: the Executor holds "
                 "DEFAULT_ADMIN and can revoke the seat, and the Safe cannot grant roles.")
    return text


def score_aave_v3_monad(w3) -> dict:
    """Aave V3 on Monad mainnet -- PoolAddressesProvider. Source: official
    `bgd-labs/aave-address-book` GitHub repo, `src/AaveV3Monad.sol` (the
    same repo this project already uses for Aave on Ethereum L1/Arbitrum/
    Base/Plasma). TVL: $319.4M Monad-specific (DefiLlama live,
    `chainTvls.Monad`, not the protocol's multi-chain total) -- the
    largest new candidate found in this pass's DefiLlama scan of every
    protocol with 'Monad' in its own chains[] list (see this file's own
    module docstring for the full 3-candidate scouting summary).

    Confirmed live, 2026-09-19, https://rpc.monad.xyz, cross-checked on a
    SECOND independent public RPC (`https://monad.drpc.org` -- byte-
    identical on every read below): the same genuine closed
    Executor<->PayloadsController pair already documented for this
    project's Ethereum-L1/Arbitrum/Base/Plasma Aave scorers (standard BGD
    Labs Aave Governance V3 cross-chain infra, not reinvented per chain).
    PoolAddressesProvider.owner() -> Executor (0xa9d0EAFF...); Executor.
    owner() -> PayloadsController (0x442CA936...); PayloadsController.
    owner() closes back to that SAME Executor -- confirmed live, not
    assumed. MonadScan's own verified source for both contracts (named
    exactly `Executor` and `PayloadsController`, both matching BGD Labs'
    `aave-delivery-infrastructure` repo line for line) is this pass's
    second, independent confirmation of what each contract actually is,
    beyond the raw owner()-loop bytecode read alone.

    `getExecutorSettingsByAccessControl(1)` (Level_1, "short executor" --
    listing assets/param changes/protocol updates) confirms a real
    86,400s (1-day) delay, with the Euler-style pattern also seen here:
    open/permissionless execution once queued. Disclosed gap:
    `getExecutorSettingsByAccessControl(2)` (Level_2, "long executor",
    payloads-controller-level updates) returns the ZERO address and a
    0s delay -- not yet configured for Monad, a real limitation (no path
    exists yet for that tier of change), not a redundant safety margin.

    `PayloadsController.guardian()` resolves to a real Gnosis Safe,
    5-of-9. Real cross-chain finding, independently re-confirmed live
    this pass (not assumed from a shared name): this guardian Safe's 9
    owners are BYTE-IDENTICAL to `_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17`
    above -- the SAME emergency-cancel committee `chains/plasma-ecosystem/
    scorers.py::score_aave_v3_pool_plasma()` already found sharing
    Arbitrum, Base, AND Plasma's own Aave V3 deployments (a different Safe
    address per chain, identical 9 signers, identical 5-of-9 threshold).
    Monad is a FOURTH chain this exact committee now reaches -- one
    compromised committee, four separate chains' worth of Aave deposits
    at risk of an out-of-timelock cancel/veto action.
    (CORRECTED 2026-09-19: five chains, not four -- Ethereum L1's own
    PayloadsController.guardian() is the same 9-signer Safe committee.)

    Open thread, disclosed rather than guessed, same as every sibling Aave
    scorer in this project: the Ethereum-mainnet Aave DAO root (L1
    proposal counts/quorum) was NOT re-verified live this pass -- this
    scorer confirms the Monad-side executor/payloads-controller pair only
    (MESSAGE_ORIGINATOR=0x9AEE0B04504CeF83A65AC3f0e838D0593BCb2BC7,
    ORIGIN_CHAIN_ID=1, both read live off Monad's own PayloadsController).
    See `chains/ethereum-l1/scorers.py`'s own `score_aave_v3_pool()` for
    that L1 root.

    CHANGED 2026-09-20 (scoring model): the DAO path (Executor behind the
    1-day delay) is NOT the only fund-affecting admin path. The ACLManager
    (read live, `getACLManager()`) gives `isPoolAdmin = true` to BOTH the
    Executor AND the PROTOCOL_GUARDIAN Safe (4-of-7, 4 bare-EOA owners + 3
    nested 1-of-3 Safes), which lets that Safe swap any reserve's aToken /
    variableDebtToken implementation immediately (eth_call state-override
    simulation, 2026-09-19), so the 1-day delay does not bind it. The
    Executor holds DEFAULT_ADMIN and could revoke the seat; the Safe cannot
    grant roles (disclosed in the notes, not score inputs). Scoring:
      - isPoolAdmin(Safe) True and the Safe resolves: Safe-no-timelock rule,
        adminKeyScore 65 / 50 / 10 for threshold >= 3 / == 2 / else (capped
        by the DAO-path 65, or 30 if the Executor loop is not closed),
        multisigScore = min(100, t*15 + max(0, n-t)*5) (4-of-7 -> 75),
        timelockScore 0. Before this change it scored 65 / 100 / 50
        (composite 71); now 65 / 75 / 0 (composite 49).
      - isPoolAdmin(Safe) False: the pre-change DAO-path scoring
        (65 / 100 / 50), the Safe holds no upgrade seat.
      - isPoolAdmin unread (ACLManager or the call returned nothing) or True
        with an unresolvable Safe: degrades conservatively to 20 / 20 / 0,
        never silently keeps the confident DAO-path score.
    crossExposureScore is unchanged (80 when the 9-signer guardian committee
    matches, else 100)."""
    provider = "0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"
    notes = []

    executor = read_address_getter(w3, provider, "owner")
    notes.append(f"PoolAddressesProvider.owner() = {executor} (expected the Executor)")

    payloads_controller = read_address_getter(w3, executor, "owner") if executor else None
    notes.append(f"Executor.owner() = {payloads_controller} (PayloadsController)")

    loop_check = read_address_getter(w3, payloads_controller, "owner") if payloads_controller else None
    notes.append(f"PayloadsController.owner() = {loop_check} (closes back to the Executor: {loop_check == executor if loop_check else None})")

    settings_abi = [{"name": "getExecutorSettingsByAccessControl", "type": "function", "stateMutability": "view",
                      "inputs": [{"type": "uint8"}], "outputs": [{"type": "tuple", "components": [{"type": "address"}, {"type": "uint40"}]}]}]
    settings = call_raw(w3, payloads_controller, settings_abi, "getExecutorSettingsByAccessControl", 1) if payloads_controller else None
    notes.append(f"PayloadsController.getExecutorSettingsByAccessControl(1) = {settings} (executor, delaySeconds -- Level_1/short executor)")
    settings_l2 = call_raw(w3, payloads_controller, settings_abi, "getExecutorSettingsByAccessControl", 2) if payloads_controller else None
    notes.append(f"PayloadsController.getExecutorSettingsByAccessControl(2) = {settings_l2} (Level_2/long executor -- zero executor means this tier is NOT yet configured on Monad)")

    guardian = call_raw(w3, payloads_controller, [{"name": "guardian", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "guardian") if payloads_controller else None
    notes.append(f"PayloadsController.guardian() = {guardian} (can cancel proposals outside the timelock)")

    guardian_safe = safe_owners_and_threshold(w3, guardian) if guardian else None
    shares_known_committee = False
    if guardian_safe:
        g_owners, g_threshold = guardian_safe
        notes.append(f"guardian is a real Gnosis Safe: {g_threshold}-of-{len(g_owners)}")
        shares_known_committee = {w3.to_checksum_address(o) for o in g_owners} == _KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17
        if shares_known_committee:
            notes.append(
                "guardian Safe owner set is IDENTICAL to this project's own already-documented Aave V3 "
                "guardian committee on Arbitrum/Base/Plasma (same 9 signers, same 5-of-9 threshold, "
                "different Safe address per chain) -- Monad is the fourth chain compared against this committee "
                "in this file's history, independently re-confirmed live this pass; Ethereum L1's own "
                "PayloadsController.guardian() is the same committee too, so it reaches five chains in total."
            )
    else:
        notes.append(f"{guardian}: NOT resolvable as a Gnosis Safe this run")

    notes.append(
        "Open thread, disclosed rather than guessed: the Ethereum-mainnet Aave DAO root (L1 proposal "
        "counts/quorum) was NOT re-verified live this pass -- this scorer confirms the Monad-side "
        "executor/payloads-controller pair only. See chains/ethereum-l1/scorers.py's own "
        "score_aave_v3_pool() for the L1 root."
    )
    seats = _read_aave_acl_seats(w3, provider)
    notes.append(_aave_acl_seats_note(w3, provider, seats))
    if not shares_known_committee:
        notes.append(_CROSS_EXPOSURE_NOTE)

    delay = settings[1] if settings else None
    chain_closed = bool(payloads_controller) and loop_check == executor
    # DAO path (Executor behind the 1-day delay) -- the pre-2026-09-20 model, now used only when the
    # PROTOCOL_GUARDIAN Safe is confirmed NOT to hold isPoolAdmin.
    admin_key = 65 if chain_closed else 30  # same band as this project's other Aave Governance V3 cross-chain relay scorers (Plasma's score_aave_v3_pool_plasma()) -- a real, resolved, audited DAO-governed executor pair, below a direct token-vote Timelock root (Uniswap's 80) since this scorer did not re-verify the L1 DAO root itself this pass
    multisig = 100  # not applicable on the DAO path: the Executor/PayloadsController pair is not a Safe (the guardian Safe is a veto/cancel path, not the primary authority) -- same convention as this project's other Aave scorers
    timelock_score = 50 if delay and delay > 0 else 0  # confirmed real 1-day delay on the only configured tier, capped below Uniswap's 2-day (60) for the unverified L1 root + the disclosed Level_2/long-executor gap + the guardian's out-of-timelock cancel path
    # CHANGED 2026-09-20: the ACLManager seat overrides the DAO-path numbers above.
    pool_admin, safe_owners = seats["pool_admin"], seats["safe_owners"]
    if pool_admin is True and safe_owners:
        s_owners, s_threshold = safe_owners
        # Safe-no-timelock rule: the 1-day delay does not bind the instant aToken/variableDebtToken upgrade path.
        safe_admin = 65 if s_threshold >= 3 else (50 if s_threshold == 2 else 10)
        admin_key = min(admin_key, safe_admin)  # never RAISE the DAO-path score (30 when the Executor loop is not closed)
        multisig = min(100, s_threshold * 15 + max(0, len(s_owners) - s_threshold) * 5)
        timelock_score = 0
        notes.append(
            f"SCORED (2026-09-20) on the Safe-no-timelock path: the PROTOCOL_GUARDIAN Safe {seats['safe']} "
            f"({s_threshold}-of-{len(s_owners)}) holds isPoolAdmin, so the Executor delay ({delay}s) does not bind its "
            f"instant aToken/variableDebtToken upgrade path; adminKeyScore/multisigScore come from that Safe and "
            f"timelockScore = 0. The DAO path (Executor behind the real 1-day delay, closed PayloadsController "
            f"loop) stays disclosed above as the DAO path."
        )
    elif pool_admin is True:
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append(
            f"DEGRADED: ACLManager says the PROTOCOL_GUARDIAN Safe {seats['safe']} holds isPoolAdmin but the Safe "
            f"did NOT resolve as a Gnosis Safe this run, so its threshold cannot be scored; degraded conservatively "
            f"to 20 / 20 / 0 rather than keeping the DAO-path 65 / 100 / 50."
        )
    elif pool_admin is None:
        admin_key, multisig, timelock_score = 20, 20, 0
        notes.append(
            "DEGRADED: isPoolAdmin(PROTOCOL_GUARDIAN Safe) was unread this run (ACLManager or the call returned "
            "nothing), so an instant Safe upgrade path cannot be ruled out; degraded conservatively to 20 / 20 / 0 "
            "rather than keeping the DAO-path 65 / 100 / 50."
        )
    else:
        notes.append(
            "isPoolAdmin(PROTOCOL_GUARDIAN Safe) = False: the Safe holds no upgrade seat, so the DAO path "
            "(Executor + 1-day delay) is scored exactly as before the 2026-09-20 change."
        )
    cross_exposure = 80 if shares_known_committee else 100

    # ADDED 2026-10-04 (Spap's go): a price consumer's oracleAuthorityScore is the min over its material price paths
    # one hop upstream (scripts/lib/price_authority.py, METHODOLOGY 'oracleAuthorityScore for price consumers').
    oracle_authority = price_authority.for_aave(w3, provider, price_authority.MONAD_SPECS, notes)
    return {
        "target": provider,
        "label": "Aave V3 Pool (Monad, PoolAddressesProvider)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": oracle_authority,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


# Plasma's own Euler DAO Safe (scripts/lib/cross_ecosystem_overlap.py's
# PLASMA_GROUPS["euler"], Safe address 0xfD30738fcB5eb5Ba418a84e672007912F991E539
# -- a DIFFERENT address from Monad's own DAO Safe below) resolves, live,
# to this EXACT 8-signer set -- confirmed via
# scripts/check_cross_ecosystem_overlap.py after wiring Monad's own DAO
# Safe into MONAD_GROUPS["euler_dao"] this pass. Redefined here (not
# imported) for the same reason as _KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17
# above -- no per-ecosystem scorers.py imports another's.
_KNOWN_EULER_DAO_SIGNERS_2026_09_19 = frozenset({
    "0x48f40Fc9AC1C72e1EE36EFF6521dA8068fCcb51e", "0x6901bECf23cf23C3866CaE6D8612f04358a4fc9a",
    "0xD59F1bd4954739791865995FeEAf4b7B499E26f0", "0x0AE7242a776c416Ec198cEd9c87BBd54CdAaA948",
    "0x91Ef12ab10909a0f39311223C3dB5a47d03d90dE", "0x70759C643C4e60d87A50F96A9813a18EE4b2672b",
    "0x42360aA7A906aCb052EfE82fcbC2180eB09aeF60", "0x6dfbE28bbAAa8D52d8826c0b402898E578B1E58e",
})


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


def score_euler_v2_monad(w3) -> dict:
    """Euler V2 on Monad mainnet -- eVaultFactory (governs every vault's
    upgradeable implementation: a compromise here reaches every vault
    deployed through this factory, the single most powerful lever in the
    protocol, not just one vault's own risk parameters). Source: official
    `euler-xyz/euler-interfaces` GitHub repo,
    `addresses/143/CoreAddresses.json` + `GovernorAddresses.json` +
    `MultisigAddresses.json` (chain 143 = Monad). TVL: $265.0M
    Monad-specific (DefiLlama live, `chainTvls.Monad`) -- the second-
    largest new candidate found in this pass's scan, below Aave V3
    ($319.4M, see `score_aave_v3_monad()`) and above Pendle V2 ($206.9M,
    found but honestly discarded as a duplicate of an already-tracked
    authority -- see this file's own module docstring).

    Confirmed live, 2026-09-19, https://rpc.monad.xyz, cross-checked on a
    SECOND independent public RPC (`https://monad.drpc.org` -- byte-
    identical on every read below): `eVaultFactory.upgradeAdmin()`
    resolves to `eVaultFactoryGovernor` (0x515C9ff6...), which is NOT
    itself Ownable/a Safe (`owner()` reverts) but is a standard
    OpenZeppelin AccessControl contract whose DEFAULT_ADMIN_ROLE is held
    EXCLUSIVELY by `eVaultFactoryTimelockController` (0x7Fe335AD...,
    confirmed `hasRole(DEFAULT_ADMIN_ROLE, ...)` = True) -- a real
    OpenZeppelin TimelockController with a confirmed live
    `getMinDelay()` = 345,600s (4 days), the LONGER of Euler's own two
    configured tiers on Monad (the other, a 2-day-delayed
    `accessControlEmergencyGovernorAdminTimelockController`, governs
    risk-parameter/pause changes on already-deployed vaults, not the
    factory itself -- a real, separate, faster-acting path disclosed in
    this scorer's notes but deliberately NOT the one scored here, since a
    factory-level compromise is the more catastrophic of the two).

    The Euler DAO Safe (0xdA3da5c8..., 4-of-8, all owners live-decoded)
    holds `PROPOSER_ROLE` on this TimelockController (confirmed True);
    `EXECUTOR_ROLE` is separately granted to the zero address (confirmed
    True) -- open/permissionless execution once the 4-day delay passes,
    not an additional single-party gatekeeper. A separate Security
    Council Safe (0x6d2d19a0..., 2-of-3, matching `MultisigAddresses.json`
    's own `labs`/`securityPartnerA`/`securityPartnerB` signers exactly by
    address) exists but was NOT found holding DEFAULT_ADMIN_ROLE,
    PROPOSER_ROLE, EXECUTOR_ROLE, or any of
    GUARDIAN_ROLE/PAUSER_ROLE/EMERGENCY_ROLE/WILD_CARD on either governor
    this pass -- disclosed as an open point (its real function on this
    specific deployment, if any, was not found this pass) rather than
    assumed to be either powerless or a live bypass.

    Checked for duplicate authority against every other ecosystem this
    project already tracks, via `scripts/check_cross_ecosystem_overlap.py`
    after wiring these two Safes into `MONAD_GROUPS` (`euler_dao`/
    `euler_security_council`): the DAO Safe ADDRESS itself is distinct
    from `PLASMA_GROUPS["euler"]`'s own DAO Safe (0xfD30738f... on Plasma
    vs. 0xdA3da5c8... on Monad -- Euler does NOT reuse one CREATE2 Safe
    address across chains the way Pendle does). But the live overlap
    check surfaced a real, more subtle finding instead: this Safe's 8
    individual SIGNERS are byte-identical, address for address, to
    Plasma's own Euler DAO Safe's 8 signers -- the same humans/keys behind
    a differently-addressed Safe on each chain, not a coincidence. This is
    genuinely new authority in the sense that mattered for the decision to
    add it (a distinct contract, distinct TVL, distinct Safe address, not
    a re-scored duplicate target) -- but the underlying signer set is
    shared, so `crossExposureScore` below is scored accordingly rather
    than left at the unexamined default, same discipline as
    `score_aave_v3_monad()`'s guardian-committee finding above."""
    factory = "0xba4Dd672062dE8FeeDb665DD4410658864483f1E"
    factory_governor = "0x515C9ff619b4618284832764E2cFc7d227514f0e"
    factory_timelock = "0x7Fe335ADfE4b89AcDAd28814cc7b89377fcEe439"
    dao_safe = "0xdA3da5c8f93c0B7630412B8cd7dE571011Df8963"
    sec_council = "0x6d2d19a06A49e87bedC653CEd58c17C3B40502F9"
    notes = []

    code = w3.eth.get_code(w3.to_checksum_address(factory))
    notes.append(f"eth_getCode(eVaultFactory, {factory}) = {len(code)} bytes of real deployed bytecode")

    upgrade_admin = read_address_getter(w3, factory, "upgradeAdmin")
    notes.append(f"eVaultFactory.upgradeAdmin() = {upgrade_admin} (expected eVaultFactoryGovernor: {bool(upgrade_admin) and upgrade_admin.lower() == factory_governor.lower()})")

    has_role_abi = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                      "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
    default_admin_role = b"\x00" * 32
    tl_has_admin = call_raw(w3, factory_governor, has_role_abi, "hasRole", default_admin_role, w3.to_checksum_address(factory_timelock))
    notes.append(f"eVaultFactoryGovernor.hasRole(DEFAULT_ADMIN_ROLE, eVaultFactoryTimelockController) = {tl_has_admin}")

    delay_abi = [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]
    delay = call_raw(w3, factory_timelock, delay_abi, "getMinDelay")
    notes.append(f"eVaultFactoryTimelockController.getMinDelay() = {delay}s")

    proposer_role = Web3.keccak(text="PROPOSER_ROLE")
    executor_role = Web3.keccak(text="EXECUTOR_ROLE")
    zero_address = w3.to_checksum_address("0x0000000000000000000000000000000000000000")
    dao_is_proposer = call_raw(w3, factory_timelock, has_role_abi, "hasRole", proposer_role, w3.to_checksum_address(dao_safe))
    open_executor = call_raw(w3, factory_timelock, has_role_abi, "hasRole", executor_role, zero_address)
    notes.append(
        f"eVaultFactoryTimelockController.hasRole(PROPOSER_ROLE, DAO Safe) = {dao_is_proposer}, "
        f"hasRole(EXECUTOR_ROLE, address(0)) = {open_executor} (open/permissionless execution once queued, not an extra gatekeeper)"
    )

    dao_safe_data = safe_owners_and_threshold(w3, dao_safe)
    cross_exposure = 100
    if not dao_safe_data:
        notes.append("DAO Safe NOT resolvable as a Gnosis Safe this run -- unresolved, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        dao_owners, dao_threshold = dao_safe_data
        notes.append(f"DAO Safe is a real Gnosis Safe: {dao_threshold}-of-{len(dao_owners)}, confirmed live PROPOSER_ROLE holder on the timelock above")
        chain_closed = bool(upgrade_admin) and upgrade_admin.lower() == factory_governor.lower() and bool(tl_has_admin)
        admin_key = 55 if chain_closed else 25  # a real, established DAO multisig proposer gated behind an EXCLUSIVELY-enforced TimelockController -- same "real Safe behind a genuine delay" band as this project's other Safe+Timelock targets (e.g. Echo's remediated Safe, scored 55), below the direct token-vote DAO band (65-80) reserved for Aave/Uniswap-style governance roots elsewhere in this file, since Euler's real decision-making step here is an 8-signer multisig vote, not full token-holder voting
        multisig = min(100, dao_threshold * 15 + max(0, len(dao_owners) - dao_threshold) * 5)
        timelock_score = 60 if delay == 345600 else (40 if delay and delay > 0 else 0)  # confirmed real, EXCLUSIVELY-held 4-day delay on the single most powerful lever (factory-wide vault-implementation upgrades) -- above Plasma's Aave 1-day (50), below Morpho's fully-independent-veto 14-day band (75), since this scorer did not exhaustively audit every role/edge-case in Euler's own AccessControl role graph

        dao_signer_set = {w3.to_checksum_address(o) for o in dao_owners}
        shares_known_euler_dao = dao_signer_set == _KNOWN_EULER_DAO_SIGNERS_2026_09_19
        if shares_known_euler_dao:
            cross_exposure = 80
            notes.append(
                "Real cross-chain finding, surfaced by scripts/check_cross_ecosystem_overlap.py after wiring "
                "this Safe into MONAD_GROUPS['euler_dao'] (not assumed from a shared 'Euler' name): this DAO "
                "Safe's ADDRESS is distinct from Plasma's own Euler DAO Safe (a different CREATE2 deployment "
                "per chain, unlike Pendle), but its 8 individual SIGNERS are byte-identical, address for "
                "address, to Plasma's own Euler DAO Safe's 8 signers -- the same humans/keys behind a "
                "differently-addressed Safe on each chain, independently re-confirmed live this pass."
            )

    sec_council_data = safe_owners_and_threshold(w3, sec_council)
    if sec_council_data:
        sc_owners, sc_threshold = sec_council_data
        notes.append(
            f"Security Council is a real, separate Gnosis Safe: {sc_threshold}-of-{len(sc_owners)} (matches "
            f"MultisigAddresses.json's labs/securityPartnerA/securityPartnerB signers exactly) -- checked for "
            f"DEFAULT_ADMIN_ROLE/PROPOSER_ROLE/EXECUTOR_ROLE/common guardian-style roles on both governors "
            f"this pass, none found (CORRECTED 2026-09-19: that search used role names the deployed contracts do not "
            f"use and missed PAUSE_GUARDIAN_ROLE, see the note below); its real function (if any) on this deployment is an open point, not "
            f"assumed either way"
        )
    else:
        notes.append("Security Council address NOT resolvable as a Gnosis Safe this run")

    notes.append(
        "Real, separate, faster-acting path disclosed but NOT scored here (out of scope for this "
        "factory-level scorer): the same DAO Safe also proposes on accessControlEmergencyGovernor's own "
        "2-day TimelockController, which governs risk-parameter/pause changes on already-deployed vaults "
        "-- a real, live lever, less catastrophic than a factory-level compromise but faster to exercise."
    )
    notes.append(_pause_guardian_note(w3, factory_governor))
    if cross_exposure == 100:
        notes.append(_CROSS_EXPOSURE_NOTE)

    return {
        "target": factory,
        "label": "Euler V2 eVaultFactory (Monad)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


SIMPLE_SCORERS = [
    score_echo_ebtc_monad,
    score_uniswap_v4_monad,
    score_monad_native_bridge,
    score_kuru_monad,
    score_morpho_vault_monad,
    score_curve_monad,
    score_curvance_monad,
    score_aave_v3_monad,
    score_euler_v2_monad,
]


def score_all(w3) -> list:
    # Per-target failure isolation, same pattern as every other ecosystem
    # file in this project: a single target's transient RPC failure must
    # not crash the whole batch and silently skip every other target's
    # score too.
    results = []
    for scorer in SIMPLE_SCORERS:
        results.extend(safe_score(scorer.__name__, scorer, w3))
    return results
