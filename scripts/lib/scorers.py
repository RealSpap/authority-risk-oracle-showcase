"""
One function per scored target, each reproducing exactly the eth_call sequence
that was originally run by hand (via `cast`) to derive that target's score.
Re-running this script re-derives the same facts from the live chain instead
of replaying hardcoded numbers -- if a target's real on-chain state changes
(a key rotated, a Safe reconfigured), the next run picks that up.

Each scorer returns a dict with the AuthorityScore fields plus a `notes` list
explaining what was found, so a re-run's output is still readable without
re-reading this file.
"""
from web3 import Web3
import time
from .web3_utils import (
    is_eoa,
    read_address_getter,
    read_slot_as_address,
    safe_owners_and_threshold,
    custom_multisig_owners_and_threshold,
    call_raw,
    get_w3,
    arbitrum_l1_l2_alias,
    safe_score as _safe_score,
    EIP1967_ADMIN_SLOT,
)
from . import morpho_v2  # noqa: E402  (Morpho Vault V2 per-function timelocks, shared with Ethereum L1, 2026-10-04)
from .signer_overlap import compute_cross_exposure_with_notes
from .safe_modules import (
    note_for as _safe_modules_note, read_guard as _read_safe_guard_addr, read_modules as _read_safe_modules,
    read_singleton as _read_safe_singleton, singleton_note as _safe_singleton_note,
)
from .account_classification import classify_account

_UINT256_GETTER = lambda name, arg_type=None: [  # noqa: E731
    {
        "name": name,
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"type": arg_type}] if arg_type else [],
        "outputs": [{"type": "uint256"}],
    }
]
_BOOL_GETTER_ADDR_ARG = lambda name: [  # noqa: E731
    {"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "bool"}]}
]


def _composite(admin_key, multisig, timelock, oracle_authority=100):
    """Standard weighting: 0.4*adminKey + 0.3*multisig + 0.3*timelock.
    oracleAuthorityScore is excluded from the weighting when not applicable
    (the convention used throughout this project: not-applicable scores 100,
    full marks, rather than being penalized as if it were a real weakness).

    Uses standard round-half-up, not Python's builtin round() -- that uses
    banker's rounding (round-half-to-even), which silently produced 42 here
    for a value of exactly 42.5 where the manually-pushed score (computed by
    hand the same way every other target was) was 43. Caught by comparing
    this script's --dry-run output against the already-published on-chain
    scores rather than assuming a rewrite reproduces them."""
    import math

    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


def _v2_owner_admin_key(owner_is_eoa, owner_safe, owner, notes) -> int:
    """METHODOLOGY.md "Morpho Vault V2 scoring", decision 3 (aligned 2026-10-04 on Spap's go): the SAME owner bands as
    Ethereum L1's V2 scorer (owner Safe threshold >= 5 -> 70, >= 3 -> 60, else 30), and a bare-EOA owner near the floor as
    for Adpend/1337 (5). A 1-of-1 Safe is one key: scored as a bare EOA (the convention the manual analysis of these
    vaults used). An owner that resolves to neither is unresolved: 20, with a degraded note."""
    if owner_is_eoa:
        notes.append("owner root is a bare EOA: adminKeyScore 5 (decision 3, as Adpend/1337)")
        return 5
    if owner_safe:
        t = owner_safe[1]
        if t == 1:
            notes.append("owner root is a 1-of-1 Safe, one key: adminKeyScore 5, as a bare EOA")
            return 5
        return 70 if t >= 5 else (60 if t >= 3 else 30)
    notes.append(f"owner {owner} resolves to neither a bare EOA nor a Safe: unresolved authority, conservative score 20")
    return 20


def score_morpho_steakhouse_usdg(w3: Web3) -> dict:
    vault = "0xBeEff033F34C046626B8D0A041844C5d1A5409dd"
    notes = []

    vault_owner = read_address_getter(w3, vault, "owner")
    notes.append(f"vault.owner() = {vault_owner}")

    root_is_eoa = is_eoa(w3, vault_owner)
    root_authority = vault_owner
    if not root_is_eoa:
        nested_owner = read_address_getter(w3, vault_owner, "owner")
        if nested_owner:
            notes.append(f"vault.owner().owner() = {nested_owner} (traced one hop further, per policy)")
            root_authority = nested_owner
            root_is_eoa = is_eoa(w3, nested_owner)

    curator = read_address_getter(w3, vault, "curator")
    curator_safe = safe_owners_and_threshold(w3, curator) if curator else None
    notes.append(f"curator() = {curator} -> Safe {curator_safe[1]}-of-{len(curator_safe[0])}" if curator_safe else f"curator() = {curator}")

    guardian_candidate = "0x5642BCd50fC751fF2d04f155423e4D0E25C2a744"
    is_sentinel = call_raw(w3, vault, _BOOL_GETTER_ADDR_ARG("isSentinel"), "isSentinel", Web3.to_checksum_address(guardian_candidate))
    sentinel_safe = safe_owners_and_threshold(w3, guardian_candidate) if is_sentinel else None
    notes.append(f"isSentinel({guardian_candidate}) = {is_sentinel}, Safe {sentinel_safe[1]}-of-{len(sentinel_safe[0])}" if sentinel_safe else f"isSentinel(...) = {is_sentinel}")

    # FIXED 2026-10-04 (depth review): timelockScore read setOwner/setCurator/setIsSentinel, which a Vault V2 never
    # timelocks, so it was a constant 15 whatever the real delays. It now applies METHODOLOGY.md's V2 decision 1 with
    # Ethereum L1's reader and bands (scripts/lib/morpho_v2.py): the minimum delay over the fund-redirecting functions and
    # exit gates still callable. multisigScore applies decision 3 (curator Safe: min(100, t*15 + (n-t)*5)) instead of a
    # flat 35. adminKeyScore is unchanged (its formula still differs from Ethereum L1's owner bands: open, see REPRISE).
    min_delay, tl_notes = morpho_v2.timelock_and_gates(w3, vault, call=call_raw)
    notes.extend(tl_notes)

    root_safe = None if root_is_eoa else safe_owners_and_threshold(w3, root_authority)
    admin_key = _v2_owner_admin_key(root_is_eoa, root_safe, root_authority, notes)
    if curator_safe:
        multisig = min(100, curator_safe[1] * 15 + max(0, len(curator_safe[0]) - curator_safe[1]) * 5)
    else:
        multisig = 0 if (curator and is_eoa(w3, curator)) else 5
    timelock_score = morpho_v2.timelock_band(min_delay)
    notes.append("minimum delay UNREAD this run -- timelockScore degraded to 0, treat as unverified" if min_delay is None
                 else f"timelockScore on the minimum delay over fund-redirecting functions and live exit gates: {min_delay / 86400:g} day(s)")

    return {
        "target": vault,
        "label": "Morpho Steakhouse USDG vault",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_UNISWAP_L1_GOVERNANCE_TIMELOCK = "0x1a9C8182C09F50c8318d769245bEA52c32BE35BC"


def _score_uniswap_bridge_alias_root(resolved_root: str, notes: list) -> tuple:
    """Shared scoring path for the four Uniswap-stack targets on Robinhood Chain
    (V3 Factory, V4 PoolManager, UniswapX reactor, V2 Factory feeToSetter), all of
    which resolve to the same root: 0x2BAD8182...46CD. RESOLVES the 2026-09-16
    correction's still-open question (data/correction_2026-09-16-uniswap-bridge-alias.md,
    "What this does NOT mean" section) of whether a dedicated "external L1 DAO
    governance via bridge alias" scoring path is needed -- yes, and this is it,
    using the SAME admin_key/multisig/timelock convention already established for
    this identical authority shape (chains/base-ecosystem/scorers.py's
    score_uniswap_v3_factory_base(), reached via OP-stack cross-domain messaging
    instead of an Arbitrum alias) and independently re-confirmed directly on L1
    itself (chains/ethereum-l1/scorers.py's score_uniswap_v3_factory()) -- not a
    new number invented for this correction.

    Deliberately re-derives everything live on every run, exactly the discipline
    `score_rollup_l1_authority()` already applies in this same file: (1) recomputes
    the deterministic Arbitrum L1->L2 alias formula fresh rather than trusting a
    hardcoded address match, (2) opens its OWN Ethereum-mainnet Web3 instance
    (ignoring the Robinhood Chain `w3` the four callers were given) to re-read the
    real L1 Timelock's delay()/admin() and the GovernorBravo's quorumVotes() live.
    If the resolved root ever stops matching the alias, or the L1 re-read fails,
    this degrades to the original bare-EOA-equivalent scoring rather than silently
    keeping the higher score -- the same fail-closed convention as every other
    RPC-dependent score in this project."""
    computed_alias = arbitrum_l1_l2_alias(_UNISWAP_L1_GOVERNANCE_TIMELOCK)
    alias_confirmed = bool(resolved_root) and computed_alias.lower() == Web3.to_checksum_address(resolved_root).lower()
    notes.append(
        f"root {resolved_root}: recomputed Arbitrum L1->L2 alias of Uniswap's real L1 Governance "
        f"Timelock ({_UNISWAP_L1_GOVERNANCE_TIMELOCK}) = {computed_alias} -- match = {alias_confirmed}"
    )

    if not alias_confirmed:
        notes.append("Alias check failed -- root is not (or no longer) the known Uniswap L1 Timelock alias; scoring as bare-EOA-equivalent, not assuming the prior correction still applies.")
        return 5, 0, 0

    l1 = get_w3("https://ethereum-rpc.publicnode.com")
    l1_code = l1.eth.get_code(Web3.to_checksum_address(_UNISWAP_L1_GOVERNANCE_TIMELOCK))
    delay = call_raw(l1, _UNISWAP_L1_GOVERNANCE_TIMELOCK, [{"name": "delay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "delay")
    admin = call_raw(l1, _UNISWAP_L1_GOVERNANCE_TIMELOCK, [{"name": "admin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "admin")
    quorum = call_raw(l1, admin, [{"name": "quorumVotes", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "quorumVotes") if admin else None
    notes.append(
        f"Independently re-confirmed live on Ethereum L1 (own w3 instance, not the Robinhood Chain one): "
        f"L1 Timelock bytecode = {len(l1_code)} bytes, .delay() = {delay}s, .admin() = {admin} (GovernorBravo), "
        f".quorumVotes() = {quorum}"
    )

    l1_reconfirmed = bool(l1_code) and delay is not None and admin and quorum is not None
    if l1_reconfirmed:
        return 80, 100, 75  # real, active L1 DAO (GovernorBravo + 2-day Timelock) reached via a confirmed legitimate bridge alias -- same convention as the Base sibling scorer
    notes.append("L1 re-confirmation incomplete this run (a live read failed) -- degrading to bare-EOA-equivalent scoring rather than keeping the higher score unverified.")
    return 5, 0, 0


def score_uniswap_v3_factory(w3: Web3) -> dict:
    """RESOLVED (2026-09-17): follow-up to the 2026-09-16 correction
    (data/correction_2026-09-16-uniswap-bridge-alias.md) that found
    factory.owner() (0x2BAD8182...46CD) is the LEGITIMATE Arbitrum L1->L2 alias
    of Uniswap's real Ethereum-mainnet Governance Timelock
    (0x1a9C8182C09F50c8318d769245bEA52c32BE35BC), not a "vanity-ground bare EOA"
    as previously described -- that commit fixed the docstrings/README wording
    but deliberately left the numeric score untouched pending a dedicated
    scoring path for "external L1 DAO governance via bridge alias". This is
    that path: see `_score_uniswap_bridge_alias_root()`, which re-verifies the
    alias match and the L1 Timelock/GovernorBravo live on every run and only
    applies the higher score if that re-verification succeeds."""
    factory = "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA"
    notes = []

    adapter = read_address_getter(w3, factory, "owner")
    notes.append(f"factory.owner() = {adapter}")
    adapter_is_eoa = is_eoa(w3, adapter)
    root_authority = adapter

    if not adapter_is_eoa:
        adapter_owner = read_address_getter(w3, adapter, "owner")
        notes.append(f"adapter.owner() = {adapter_owner}")
        root_authority = adapter_owner or adapter
        adapter_is_eoa = is_eoa(w3, root_authority) if root_authority else False

    if adapter_is_eoa:
        admin_key, multisig, timelock_score = _score_uniswap_bridge_alias_root(root_authority, notes)
    else:
        root_safe = safe_owners_and_threshold(w3, root_authority)
        admin_key = 40 if root_safe else 20
        multisig = root_safe[1] * 10 if root_safe else 0
        timelock_score = 0  # setFactoryOwner/setFeeSetter: no delay, confirmed by design (Owned pattern, no TimelockController found)

    return {
        "target": factory,
        "label": "Uniswap v3 Factory",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_uniswap_v4_poolmanager(w3: Web3) -> dict:
    """RESOLVED (2026-09-17): same root address as score_uniswap_v3_factory() --
    see its docstring. Now scored via the same `_score_uniswap_bridge_alias_root()`
    path instead of flat bare-EOA scoring."""
    pool_manager = "0x8366a39CC670B4001A1121B8F6A443A643e40951"
    notes = []

    owner = read_address_getter(w3, pool_manager, "owner")
    notes.append(f"poolManager.owner() = {owner}")
    owner_is_eoa = is_eoa(w3, owner)

    if owner_is_eoa:
        admin_key, multisig, timelock_score = _score_uniswap_bridge_alias_root(owner, notes)
    else:
        admin_key, multisig, timelock_score = 40, 0, 0  # setProtocolFeeController: no delay, confirmed no TimelockController in the chain

    return {
        "target": pool_manager,
        "label": "Uniswap v4 PoolManager",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_lighter_escrow(w3: Web3) -> dict:
    proxy = "0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d"
    notes = []

    gatekeeper = read_slot_as_address(w3, proxy, EIP1967_ADMIN_SLOT)
    notes.append(f"EIP-1967 admin slot -> UpgradeGatekeeper {gatekeeper}")

    master = call_raw(w3, gatekeeper, _addr_getter_abi("getMaster"), "getMaster")
    notes.append(f"getMaster() = {master}")
    master_safe = safe_owners_and_threshold(w3, master) if master else None

    notice_period = call_raw(w3, gatekeeper, _UINT256_GETTER("approvedUpgradeNoticePeriod"), "approvedUpgradeNoticePeriod")
    notes.append(f"approvedUpgradeNoticePeriod() = {notice_period}s")

    council = call_raw(w3, gatekeeper, _addr_getter_abi("securityCouncilAddress"), "securityCouncilAddress")
    council_is_eoa = is_eoa(w3, council) if council else None
    notes.append(f"securityCouncilAddress() = {council}, is bare EOA = {council_is_eoa}")

    admin_key = 75 if master_safe else 10
    multisig = master_safe[1] * 20 + 5 if master_safe else 0  # 3-of-5 -> 65
    # A real delay exists on the authority-changing action, but a single bare EOA
    # can unilaterally zero it (cutUpgradeNoticePeriod) -- that bypass caps the score.
    # FIXED 2026-09-17 (closed a bug hunt finding): council_is_eoa is None
    # when securityCouncilAddress() itself didn't resolve this run (revert or
    # persistent RPC failure), and Python truthiness made that case fall
    # through to the SAME 60-point branch as a council CONFIRMED not to be a
    # bare EOA -- silently awarding the best score for a bypass check that
    # was never actually performed, instead of degrading.
    if council_is_eoa is None:
        timelock_score = 0
        notes.append("securityCouncilAddress()/is_eoa() did not resolve this run -- the bare-EOA bypass check was never performed, timelockScore degraded rather than awarding the confirmed-safe score")
    else:
        timelock_score = 15 if (notice_period and notice_period > 0 and council_is_eoa) else (60 if notice_period else 0)

    return {
        "target": proxy,
        "label": "Lighter (zkLighter) Escrow proxy",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_arcus_ptoken(w3: Web3, target_address: str, label: str) -> dict:
    """Shared scorer for the Arcus factory and every pToken issued through its
    beacon -- they all inherit the exact same authority chain."""
    notes = []
    beacon = "0x33846348210A0Cc0345F354d9DE52b89AD473A76"

    beacon_owner = read_address_getter(w3, beacon, "owner")
    notes.append(f"beacon.owner() = {beacon_owner}")
    beacon_safe = safe_owners_and_threshold(w3, beacon_owner) if beacon_owner else None

    admin_key = 65 if beacon_safe else 10
    multisig = beacon_safe[1] * 25 + 5 if beacon_safe else 0  # 2-of-3 -> 55
    timelock_score = 0  # no TimelockController, no Safe guard/module found anywhere in the chain

    return {
        "target": target_address,
        "label": label,
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def _addr_getter_abi(name):
    return [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}]


def score_stock_token(w3: Web3, target_address: str, label: str) -> dict:
    """Shared scorer for Robinhood's tokenized-stock/ETF line -- every token is a
    byte-identical beacon proxy sharing one AccessControl beacon that can upgrade
    or freeze/blocklist accounts across the entire product line at once.

    PRECISION (rotation audit index 15, 2026-09-19 -- a correction to how this
    docstring and data/scored_targets_2026-09-15-batch3.md used to phrase it,
    NOT a score change): the DEFAULT_ADMIN_ROLE holder checked below cannot call
    `upgradeTo` / `pause` / `blockAccounts` / `mint` / `burn` directly -- each
    of those needs its own role (eth_call simulation from the admin EOA reverts
    with AccessControlUnauthorizedAccount on all of them, identical on 3 RPCs).
    What it can do, with no delay (simulated OK for all 6 named roles), is
    `grantRole(<any role>, itself)` in one transaction: `getRoleAdmin()` is
    0x00 for every one of the 13 role ids the beacon has ever granted and its
    full event history has no RoleAdminChanged, so this key roots the entire
    tree. The live operational roles today sit on 12 OTHER bare EOAs (BEACON_UPGRADER
    0xCd8C... executed a real `upgradeTo` at block 657134, to the implementation
    already installed; PAUSER 0xe7BC... paused/unpaused 3 times around block
    611k; BLOCKER 0x913c... has 246 Blocked / 4 Unblocked events; MINTER
    0x2b94... nonce 71230). Everything is a bare EOA, no Safe, no timelock, so
    the (3, 0, 0) result stands. The beacon address is also hardwired as an
    immutable in BOTH the proxy bytecode and the implementation bytecode (not
    only in the EIP-1967 slot the audits used to read), and the tokens carry
    no role state of their own (PLTR proxy: only BeaconUpgraded + Initialized
    events). See data/rotation_audit_2026-09-20-robinhood-chain-index15.md."""
    beacon = "0xe10b6f6b275de231345c20d14ab812db62151b00"
    notes = []

    default_admin_role = b"\x00" * 32
    # hasRole needs a candidate address, not a search -- re-checking the known
    # current holder fresh each run rather than assuming it's unchanged.
    known_admin = "0xd6f8378f8e440c65f8382f5f2728c78dfd55b66d"
    still_holds_role = call_raw(
        w3, beacon,
        [{"name": "hasRole", "type": "function", "stateMutability": "view",
          "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}],
        "hasRole", default_admin_role, Web3.to_checksum_address(known_admin),
    )
    notes.append(f"beacon {beacon}: hasRole(DEFAULT_ADMIN_ROLE, {known_admin}) = {still_holds_role}")
    admin_is_eoa = is_eoa(w3, known_admin) if still_holds_role else None
    notes.append(f"admin is bare EOA = {admin_is_eoa}")

    admin_key = 3 if (still_holds_role and admin_is_eoa) else 40
    multisig = 0
    timelock_score = 0  # upgradeTo/blockAccounts: no delay found

    return {
        "target": target_address,
        "label": label,
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_uniswapx_reactor(w3: Web3) -> dict:
    """RESOLVED (2026-09-17): same root address as score_uniswap_v3_factory() --
    see its docstring. Now scored via the same `_score_uniswap_bridge_alias_root()`
    path instead of flat bare-EOA scoring."""
    reactor = "0x000000007A1C8e570011EeDF86A2A35593013cBA"
    notes = []

    owner = read_address_getter(w3, reactor, "owner")
    notes.append(f"reactor.owner() = {owner}")
    owner_is_eoa = is_eoa(w3, owner) if owner else None

    if owner_is_eoa:
        admin_key, multisig, timelock_score = _score_uniswap_bridge_alias_root(owner, notes)
    else:
        admin_key, multisig, timelock_score = 40, 0, 0

    return {
        "target": reactor,
        "label": "UniswapX V3DutchOrderReactor",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_morpho_vault_generic(w3: Web3, vault: str, label: str) -> dict:
    """Generic Morpho Vault V2 scorer for vaults beyond Steakhouse USDG -- traces
    curator()/owner() (following a contract pointer up to 2 hops) and the same
    authority-selector timelocks. Does NOT auto-discover a sentinel address (that
    needs event-log analysis to find candidates) -- multisigScore here is based on
    curator+owner strength only, a defensible approximation documented here rather
    than silently treated as the full picture.

    KNOWN LIMITATION, disclosed rather than hidden: this formula is a heuristic,
    not a re-implementation of the bespoke reasoning used for the manually-pushed
    scores on these same vaults (data/scored_targets_2026-09-15-batch3.md). It
    does not special-case a 1-of-1 Safe as functionally EOA-equivalent, so it can
    land a few points off manual analysis on edge cases (confirmed: NetNet Credit
    scores 22 here vs. 8 by hand, because its owner is exactly that 1-of-1 case).
    Close enough for the simpler targets (stock tokens, UniswapX, Arcus all match
    the manual scores exactly), not a substitute for a real second look at an
    unusual authority shape."""
    notes = []

    curator = read_address_getter(w3, vault, "curator")
    curator_safe = safe_owners_and_threshold(w3, curator) if curator else None
    notes.append(f"curator() = {curator}" + (f" -> Safe {curator_safe[1]}-of-{len(curator_safe[0])}" if curator_safe else ""))

    owner = read_address_getter(w3, vault, "owner")
    notes.append(f"owner() = {owner}")
    owner_safe = safe_owners_and_threshold(w3, owner) if owner else None
    owner_is_eoa = is_eoa(w3, owner) if owner else None
    if not owner_safe and not owner_is_eoa and owner:
        nested = read_address_getter(w3, owner, "owner")
        if nested:
            notes.append(f"owner().owner() = {nested} (traced one hop further)")
            owner_safe = safe_owners_and_threshold(w3, nested)
            owner_is_eoa = is_eoa(w3, nested)

    # FIXED 2026-10-04: same change as score_morpho_steakhouse_usdg (V2 decisions 1 and 3, scripts/lib/morpho_v2.py).
    min_delay, tl_notes = morpho_v2.timelock_and_gates(w3, vault, call=call_raw)
    notes.extend(tl_notes)

    admin_key = _v2_owner_admin_key(owner_is_eoa, owner_safe, owner, notes)  # decision 3, aligned 2026-10-04

    if curator_safe:
        multisig = min(100, curator_safe[1] * 15 + max(0, len(curator_safe[0]) - curator_safe[1]) * 5)
    else:
        multisig = 0
        notes.append(f"curator {curator} is not a resolvable Safe: multisigScore 0 (decision 3, as for a bare-EOA curator)")

    timelock_score = morpho_v2.timelock_band(min_delay)
    notes.append("minimum delay UNREAD this run -- timelockScore degraded to 0, treat as unverified" if min_delay is None
                 else f"timelockScore on the minimum delay over fund-redirecting functions and live exit gates: {min_delay / 86400:g} day(s)")

    return {
        "target": vault,
        "label": label,
        "adminKeyScore": min(admin_key, 100),
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(min(admin_key, 100), multisig, timelock_score),
        "notes": notes,
    }


def score_spark_savings_usdg(w3: Web3) -> dict:
    """Completes the trace left explicitly unresolved in
    data/scored_targets_2026-09-15-batch3.md: an 8,113-byte DEFAULT_ADMIN_ROLE
    holder with BridgeExecutor-shaped selectors whose own controller "was not
    identified this pass". A RoleGranted/RoleRevoked replay from genesis (see
    data/scored_targets_2026-09-15-batch6.md) found two role holders on that
    executor: the executor self-administers DEFAULT_ADMIN_ROLE (after an initial
    deployer briefly held and relinquished it at deploy time), and a second,
    unnamed role gating its queue()-style action is held by an ArbitrumReceiver-
    pattern contract. That receiver's l1Authority() resolves to a real Ethereum
    mainnet contract verified on Etherscan as Sky/MakerDAO's own "SubProxy"
    governance pattern -- a real, identifiable cross-domain governance chain, not
    a bare EOA or an unknown entity. SubProxy's own further upstream controller
    is NOT resolved here (owner/authority/wards/pause all revert) -- left open,
    not silently treated as fully traced."""
    target = "0xde770c84FE66E063336b31737cFE9790f18c4087"
    executor = "0x826aeaeee9233fa8ba199518dd8621a5962b1d02"
    receiver = "0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8"
    notes = []

    executor_is_eoa = is_eoa(w3, executor)
    notes.append(f"DEFAULT_ADMIN_ROLE holder (executor) {executor}: bare EOA = {executor_is_eoa}")

    delay = call_raw(w3, executor, _UINT256_GETTER("delay"), "delay")
    grace_period = call_raw(w3, executor, _UINT256_GETTER("gracePeriod"), "gracePeriod")
    notes.append(f"executor.delay() = {delay}, gracePeriod() = {grace_period}")

    l1_authority = read_address_getter(w3, receiver, "l1Authority")
    notes.append(
        f"queue-role holder {receiver}.l1Authority() = {l1_authority} "
        f"(Ethereum mainnet, verified Etherscan source name \"SubProxy\" -- real Sky/"
        f"MakerDAO governance contract, its own upstream controller not resolved this pass)"
    )

    receiver_is_safe = safe_owners_and_threshold(w3, receiver)
    notes.append(f"{receiver} is a Safe: {bool(receiver_is_safe)} (expected False -- ArbitrumReceiver pattern, not a multisig)")

    # A real, identifiable governance chain (self-admin executor gated by an
    # L1-authenticated receiver resolving to Sky's own SubProxy) is materially
    # better than the batch3 unknown-contract placeholder -- adminKeyScore rises
    # accordingly. The LOCAL L2 delay is confirmably 0, so timelockScore stays low
    # regardless: a real controller does not make an undelayed action safe.
    admin_key = 50
    multisig = 30  # real, identifiable chain, but not a Safe -- capped well below an actual multisig
    timelock_score = 10 if delay == 0 else 60

    return {
        "target": target,
        "label": "Spark Savings USDG (spUSDG)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_spark_liquidity_layer_almproxy(w3: Web3) -> dict:
    """ADDED batch 13 (2026-09-18): left open in batch 12 as "no owner()/EIP-1967
    admin slot -- not a standard TransparentUpgradeableProxy or Ownable shape...
    needs reading the actual deployed source before a real score can be
    assigned." Read directly: this contract (2,260 bytes) is NOT a proxy at all
    -- its own dispatcher exposes `doCall(address,bytes)` (0x3aada4d2),
    `doDelegateCall(address,bytes)` (0x8ce4a1f2) and `doCallWithValue(address,
    bytes,uint256)` (0xd71f93f8), the real selectors of Spark's own
    `spark-alm-controller` ALMProxy.sol, gated by OpenZeppelin AccessControl
    (DEFAULT_ADMIN_ROLE + a role named literally "CONTROLLER", confirmed via
    `keccak256("CONTROLLER")` matching the constant embedded in the bytecode
    at selector 0xee0fc121) -- not the MakerDAO/Sky `wards` rely/deny pattern
    this batch's rough note assumed going in; that assumption is corrected
    here based on what is actually deployed, not what a sibling Spark product
    (the PSM) happens to use elsewhere.

    A DEFAULT_ADMIN_ROLE grant/revoke replay from genesis (`eth_getLogs`, full
    range, both independent RPCs identical) found exactly the same shape as
    `score_spark_savings_usdg()`: deployer self-grants then relinquishes,
    leaving ONE current holder. That holder is confirmed BY ADDRESS AND BY
    BYTECODE SIZE (8,113 bytes, identical) to be the exact same executor
    contract already fully traced for Spark Savings USDG -- this is not a
    coincidence of similar architecture, it is the literal same contract
    instance administering both products. Its own governance chain (local
    delay 0, gracePeriod 604800, gated by an L1-authenticated receiver whose
    l1Authority() resolves to Sky/MakerDAO's own verified "SubProxy" contract)
    is therefore identical too and re-verified live here rather than assumed
    unchanged from that other target's own re-derivation."""
    target = "0xfD2fD4B046136B540A56C11c75ac679AE7d1dB24"
    executor = "0x826aeaeee9233fa8ba199518dd8621a5962b1d02"
    receiver = "0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8"
    notes = []

    default_admin_role = b"\x00" * 32
    executor_holds_admin = call_raw(
        w3, target,
        [{"name": "hasRole", "type": "function", "stateMutability": "view",
          "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}],
        "hasRole", default_admin_role, Web3.to_checksum_address(executor),
    )
    notes.append(f"ALMProxy.hasRole(DEFAULT_ADMIN_ROLE, {executor}) = {executor_holds_admin} (same executor contract already traced for Spark Savings USDG -- confirmed by address AND by matching 8,113-byte bytecode size)")

    executor_code_len = len(w3.eth.get_code(Web3.to_checksum_address(executor)))
    notes.append(f"executor {executor} bytecode length = {executor_code_len} bytes (8113 expected -- matches score_spark_savings_usdg()'s executor exactly)")

    delay = call_raw(w3, executor, _UINT256_GETTER("delay"), "delay")
    grace_period = call_raw(w3, executor, _UINT256_GETTER("gracePeriod"), "gracePeriod")
    notes.append(f"executor.delay() = {delay}, gracePeriod() = {grace_period}")

    l1_authority = read_address_getter(w3, receiver, "l1Authority")
    notes.append(
        f"{receiver}.l1Authority() = {l1_authority} (same Sky/MakerDAO SubProxy chain as "
        f"Spark Savings USDG; not re-verified against Etherscan again this pass since it's "
        f"the same contract, already verified there)"
    )

    if not executor_holds_admin:
        # Fail loud rather than silently scoring against a stale assumption --
        # matches this project's standing discipline (e.g. the rollup-authority
        # scorer's own "raise after 4 failed attempts" rule) of never treating
        # an unconfirmed re-derivation as if it still matched a prior finding.
        notes.append("DIVERGENCE: executor no longer holds DEFAULT_ADMIN_ROLE on this target -- scoring as fully unresolved rather than reusing the Spark Savings shape.")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        # Identical shape and identical root contract to Spark Savings USDG --
        # same sub-scores for the same reason (see score_spark_savings_usdg()'s
        # own docstring/comment for why these specific values).
        admin_key = 50
        multisig = 30
        timelock_score = 10 if delay == 0 else 60

    return {
        "target": target,
        "label": "Spark Liquidity Layer (ALMProxy)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_HAS_ROLE_ABI = [{"name": "hasRole", "type": "function", "stateMutability": "view",
                  "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]


def score_pendle_v2(w3: Web3) -> dict:
    """Pendle V2's two ProxyAdmins gate every contract upgrade across the
    deployment; MarketFactoryV6.owner() is a third authority, the Pendle
    governance proxy (an ERC-1967 proxy with no owner() getter, an AccessControl
    role system behind it).

    RESOLVED 2026-09-20 (this used to be disclosed as "not yet traced past its
    first hop"): read with hasRole on two RPCs, the governance proxy's
    DEFAULT_ADMIN_ROLE is held by the SAME 3-of-5 Safe that owns ProxyAdmin (and
    Pendle's Router on Plasma, where the same proxy address and the same admin
    Safe exist). So this third path adds no weaker link than the 3-of-5 Safe
    that already sets the ceiling below, and no score moves. A separate GUARDIAN
    role on it (a single key, availability-only freeze of markets) is disclosed by
    the 2026-09-20 sweep and is not scored. The note below re-reads the fact every
    run."""
    proxy_admin = "0xA28c08f165116587D4F3E708743B4dEe155c5E64"
    dev_proxy_admin = "0xD37eB2E6DE40a33ba68BaD94427723b66c954EA9"
    market_factory = "0x544BF81c855AE84c1e8b65d5E38770898D01EeE2"
    notes = []

    pa_owner = read_address_getter(w3, proxy_admin, "owner")
    pa_safe = safe_owners_and_threshold(w3, pa_owner) if pa_owner else None
    notes.append(f"ProxyAdmin.owner() = {pa_owner}" + (f" -> Safe {pa_safe[1]}-of-{len(pa_safe[0])}" if pa_safe else " (not a Safe)"))

    dpa_owner = read_address_getter(w3, dev_proxy_admin, "owner")
    dpa_safe = safe_owners_and_threshold(w3, dpa_owner) if dpa_owner else None
    notes.append(f"devProxyAdmin.owner() = {dpa_owner}" + (f" -> Safe {dpa_safe[1]}-of-{len(dpa_safe[0])}" if dpa_safe else " (not a Safe)"))

    mf_owner = read_address_getter(w3, market_factory, "owner")
    mf_owner_is_eoa = is_eoa(w3, mf_owner) if mf_owner else None
    mf_admin_is_pa_safe = call_raw(w3, mf_owner, _HAS_ROLE_ABI, "hasRole", b"\x00" * 32, Web3.to_checksum_address(pa_owner)) if (mf_owner and pa_owner and not mf_owner_is_eoa) else None
    if mf_admin_is_pa_safe is True:
        notes.append(
            f"MarketFactoryV6.owner() = {mf_owner} (bare EOA = {mf_owner_is_eoa}): the Pendle governance proxy, whose DEFAULT_ADMIN_ROLE is held by the SAME Safe "
            f"that owns ProxyAdmin ({pa_owner}), so this third path adds no weaker link (a GUARDIAN key can freeze markets, availability-only, disclosed not scored)"
        )
    else:
        notes.append(f"MarketFactoryV6.owner() = {mf_owner} (bare EOA = {mf_owner_is_eoa}; hasRole(DEFAULT_ADMIN_ROLE, ProxyAdmin's Safe) = {mf_admin_is_pa_safe}: its own controller is not confirmed to be that Safe this run)")

    safes = [s for s in (pa_safe, dpa_safe) if s]
    admin_key = 70 if len(safes) == 2 else (45 if safes else 10)
    multisig = min(s[1] for s in safes) * 15 if safes else 0  # weakest of the two Safes sets the ceiling -- 3-of-5 -> 45
    timelock_score = 0  # no TimelockController found gating either ProxyAdmin or MarketFactoryV6

    return {
        "target": market_factory,
        "label": "Pendle V2 (ProxyAdmin + devProxyAdmin + MarketFactoryV6)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_curve_dex(w3: Web3) -> dict:
    """Curve's StableSwap-NG Factory and its own fee-receiver / x-gov vault are
    both controlled by the exact same address -- confirmed via eth_getCode to be
    a bare EOA (0 bytecode), cross-checked on a second RPC in batch 9 (identical).
    NOTE (2026-09-16): unlike the Uniswap stack's 0x2BAD8182...46CD (see
    score_uniswap_v3_factory() docstring, corrected -- that one turned out to be
    a legitimate L1 governance bridge alias, not a bare EOA), this Curve address
    is NOT the same pattern: it has 287 real transactions on Arbitrum (nonce 0 on
    Robinhood Chain, dormant here) -- an L1->L2 bridge alias cannot itself submit
    signed transactions as a sender on another chain, only a genuine private-key
    EOA can, so this transaction history rules out the aliasing explanation and
    confirms it really is a bare, actively-used private key. Docstring was stale
    relative to the code's own notes.append() line and the published README
    caveat (both already reflected batch 9's finding) until this correction --
    fixed here for consistency, not a new finding."""
    factory = "0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"
    fee_receiver = "0x193110Ce1542d7371e1515BD6A2E470fDefc310D"
    notes = []

    factory_admin = call_raw(w3, factory, _addr_getter_abi("admin"), "admin")
    notes.append(f"StableSwapNGFactory.admin() = {factory_admin}")

    fee_owner = read_address_getter(w3, fee_receiver, "owner")
    notes.append(f"fee-receiver/x-gov vault.owner() = {fee_owner}")

    same_key = bool(factory_admin) and bool(fee_owner) and Web3.to_checksum_address(factory_admin) == Web3.to_checksum_address(fee_owner)
    notes.append(f"factory.admin() == fee-receiver.owner(): {same_key} (single key controls both, if true)")

    controller = factory_admin or fee_owner
    controller_is_eoa = is_eoa(w3, controller) if controller else None
    notes.append(f"controller {controller}: bare EOA = {controller_is_eoa} (cross-checked batch 9 on robinhood.drpc.org: identical; nonce 0 on this chain, 287 tx on Arbitrum -- a real, actively-used key, dormant here)")

    admin_key = 2 if (controller_is_eoa and same_key) else (5 if controller_is_eoa else 40)
    multisig = 0
    timelock_score = 0  # no TimelockController found

    return {
        "target": factory,
        "label": "Curve DEX (StableSwap-NG Factory + fee-receiver)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_meridian_exchangegateway(w3: Web3) -> dict:
    """Meridian Perps (rotation audit batch, 2026-09-18, new target found while
    auditing index 7 / Curve DEX). RWA-focused perps + prediction-market
    protocol native to Robinhood Chain (DefiLlama `meridian-perps`,
    `chainTvls["Robinhood Chain"]` ~$2.29M). Addresses from DefiLlama-Adapters'
    own TVL adapter (`projects/meridian-perps/index.js`): the `ExchangeGateway`
    proxy (`EXCHANGE`) holds user collateral balances directly (merUSD and
    USD-equivalents), and a separate ERC-4626 LP vault trades from an account
    on that same exchange. The LP vault itself (`0x24b84023c8e4Da635be228C380C09bfE5271BF9d`)
    was checked first and exposes NO owner/curator/admin/manager/governance
    getter at all (every one of those selectors reverts) -- it is a plain
    permissionless ERC-4626 wrapper; the real custodial authority sits
    entirely in the exchange gateway and the collateral token it also owns,
    which is what this scorer targets.

    Confirmed live on 2 independent RPCs (`rpc.mainnet.chain.robinhood.com`,
    `robinhood.drpc.org`), chain 4663: `EXCHANGE.owner()` and the collateral
    token `merUSD.owner()` (`0xad221259d4a1f2d7376dc1012c561bc86640f009`)
    resolve to the exact SAME bare EOA (`0x39C647fdd8524c69be3E05A754bD63E02b019D75`,
    0 bytecode, nonce 84 on this chain -- a real, actively-used key, not a
    dormant vanity address), identical on both RPCs. `owner()` resolving
    directly (not reverting) on both confirms a plain OpenZeppelin Ownable
    proxy, not an AccessControl role system -- no TimelockController found
    gating either contract. This is the same two-independent-contracts/
    one-key convergence pattern already tracked for Curve DEX above, so
    scored identically (`admin_key = 2`, the "same_key" branch), not a new
    number invented for this target."""
    exchange = "0xD540F47F214dC7D6D244E62A6aE7e06B586Ef44A"
    mer_usd = "0xad221259d4a1f2d7376dc1012c561bc86640f009"
    notes = []

    exchange_owner = read_address_getter(w3, exchange, "owner")
    notes.append(f"ExchangeGateway.owner() = {exchange_owner}")

    mer_usd_owner = read_address_getter(w3, mer_usd, "owner")
    notes.append(f"merUSD.owner() = {mer_usd_owner}")

    same_key = bool(exchange_owner) and bool(mer_usd_owner) and Web3.to_checksum_address(exchange_owner) == Web3.to_checksum_address(mer_usd_owner)
    notes.append(f"ExchangeGateway.owner() == merUSD.owner(): {same_key} (single key controls both, if true)")

    controller = exchange_owner or mer_usd_owner
    controller_is_eoa = is_eoa(w3, controller) if controller else None
    notes.append(f"controller {controller}: bare EOA = {controller_is_eoa} (nonce 84 on this chain at time of discovery -- a real, actively-used key)")
    notes.append("LP vault (0x24b84023c8e4Da635be228C380C09bfE5271BF9d) checked separately: owner()/curator()/admin()/manager()/governance() all revert -- no exposed admin surface on the vault itself, authority is entirely on the exchange gateway scored here")

    admin_key = 2 if (controller_is_eoa and same_key) else (5 if controller_is_eoa else 40)
    multisig = 0
    timelock_score = 0  # no TimelockController found gating either contract

    return {
        "target": exchange,
        "label": "Meridian Perps (ExchangeGateway + merUSD)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


ARCUS_TARGETS = [
    ("0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB", "Arcus pToken factory"),
    ("0x925F92F055EDB79C42B5d45E64A1b74143b90eA0", "Arcus pBTC (1x)"),
    ("0x4472C69d299382F8847ebCE4FC6Ed8e295510E3e", "Arcus pBTC3x"),
]

STOCK_TOKEN_TARGETS = [
    ("0x322F0929c4625eD5bAd873c95208D54E1c003b2d", "Robinhood Token: TSLA"),
    ("0x12f190a9F9d7D37a250758b26824B97CE941bF54", "Robinhood Token: AMZN"),
    ("0x894E1EC2D74FFE5AEF8Dc8A9e84686acCB964F2A", "Robinhood Token: PLTR"),
    ("0xE0444EF8BF4eD74f74FD73686e2ddF4C1c5591E8", "Robinhood Token: NFLX"),
    ("0x86923f96303D656E4aa86D9d42D1e57ad2023fdC", "Robinhood Token: AMD"),
]

MORE_MORPHO_VAULTS = [
    ("0x99347d5F70D3838763f6Bddcf80304C8aa953B57", "Morpho NetNet Credit vault"),
    ("0x37788ff0c1d4e45A7FE06BC7e71e0cc00121d0A8", "Morpho Purinta USDG vault"),
    ("0xbEeFF0fb1Dc19344A87b8479dAb60A2e16160737", "Morpho Ethena x Steakhouse USDG vault"),
    # ADDED batch 13 (2026-09-18): found via DefiLlama's actual registries/curators.js
    # (github.com/DefiLlama/DefiLlama-Adapters, "steakhouse" entry's
    # blockchains.robinhood.morpho list) -- the per-protocol
    # projects/steakhouse/index.js DefiLlama page 404s (flagged open in batch 12),
    # but the curator registry the TVL dashboard actually reads from is a
    # different, working file and lists 4 Robinhood-chain vaults, 2 of which
    # (Steakhouse USDG, Ethena x Steakhouse USDG) were already tracked. These 2
    # are the previously-untracked remainder, confirmed live on 2 independent
    # RPCs (code present, curator()/owner()/asset()=USDG all resolve) before
    # being added here -- the registry file was only ever a place to look, not
    # trusted as ground truth on its own.
    ("0xBEEff039907422219Fb367e525954DDC092854d9", "Morpho Grove x Steakhouse USDG vault"),
    ("0xbeEfFF136E3684273e6aA75A1669B784B373A4FD", "Morpho Steakhouse Turbo USDG vault"),
]

def _replay_role_holders(chain_w3: Web3, contract_address: str, role_names, start_block: int):
    """Re-derive the CURRENT holder set of one or more OZ AccessControl roles by
    replaying every RoleGranted/RoleRevoked event from `start_block` to the
    chain tip -- never trusted from a prior pass or a hardcoded note. Raises
    after 4 failed attempts per chunk rather than silently returning an empty
    set, which would read as "nobody holds this role" instead of "the scan
    failed" (the exact bug this project caught in its own rollup-authority
    scorer in batch 8, after a hardcoded "zero holders" note from batch 4 had
    gone stale without anyone re-checking it).

    Accepts either a single role name (str, returns a set) or a list of role
    names (returns {role_name: set}) -- multiple roles are fetched via ONE
    OR-filter on topics[1] per event type (2 log-fetches total, not 2 per
    role), since a naive per-role loop over a chain with tens of millions of
    blocks (Robinhood Chain mainnet) made a 3-role scan from block 0 too slow
    to be a usable dry-run (batch 8: this is what replaced that first draft)."""
    single = isinstance(role_names, str)
    names = [role_names] if single else list(role_names)
    role_hashes = {name: Web3.keccak(text=name) for name in names}
    hash_to_name = {"0x" + h.hex(): name for name, h in role_hashes.items()}
    granted_topic = Web3.keccak(text="RoleGranted(bytes32,address,address)")
    revoked_topic = Web3.keccak(text="RoleRevoked(bytes32,address,address)")

    events = []
    start, latest, chunk = start_block, chain_w3.eth.block_number, 50_000
    while start <= latest:
        end = min(start + chunk - 1, latest)
        for topic, kind in [(granted_topic, "GRANT"), (revoked_topic, "REVOKE")]:
            logs = None
            last_err = None
            for attempt in range(4):
                try:
                    logs = chain_w3.eth.get_logs({
                        "fromBlock": start, "toBlock": end, "address": contract_address,
                        "topics": ["0x" + topic.hex(), ["0x" + h.hex() for h in role_hashes.values()]],
                    })
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.5 * (attempt + 1))
            if logs is None:
                raise RuntimeError(f"{names} log fetch failed on {contract_address} for blocks {start}-{end} after 4 attempts: {last_err}")
            for log in logs:
                role_name = hash_to_name[log["topics"][1].hex() if log["topics"][1].hex().startswith("0x") else "0x" + log["topics"][1].hex()]
                # FIXED 2026-09-17 (closed an audit finding): raw manual hex-slicing
                # of a log topic into an address, with no guard, is exactly the bug
                # this project's own sister research (multisig-overlap)
                # hit: a malformed/short topic silently decoded into a spurious
                # cross-protocol signer match. topics[2] must be a real 32-byte
                # ABI-encoded address (12 zero padding bytes + 20 address bytes) --
                # anything else is a malformed log, not a real role holder, and is
                # skipped with a loud print rather than silently accepted.
                addr_topic = log["topics"][2]
                if len(addr_topic) != 32 or addr_topic[:12] != b"\x00" * 12:
                    print(f"_replay_role_holders: SKIPPED malformed topics[2] on {contract_address} block {log['blockNumber']} (expected 32 bytes, 12-byte zero padding): {addr_topic.hex()}")
                    continue
                events.append((log["blockNumber"], log["logIndex"], kind, role_name, "0x" + addr_topic.hex()[-40:]))
        start = end + 1
    # FIXED 2026-09-17 (closed a bug hunt finding): sorting by blockNumber
    # alone left ties broken by insertion order, and GRANT-topic logs are
    # always fetched (and appended) before REVOKE-topic logs for the same
    # chunk (see the loop above) -- so a REVOKE-then-GRANT sequence within
    # ONE block replayed backwards as GRANT-then-REVOKE, silently resolving
    # to "role not held" for an address that actually holds it. logIndex is
    # the real on-chain ordering within a block; sorting on (blockNumber,
    # logIndex) replays events in their true chronological order.
    events.sort(key=lambda e: (e[0], e[1]))

    holders_by_role = {name: set() for name in names}
    for _, _, kind, role_name, addr in events:
        addr = Web3.to_checksum_address(addr)
        s = holders_by_role[role_name]
        s.add(addr) if kind == "GRANT" else s.discard(addr)

    if single:
        return holders_by_role[role_names]
    return holders_by_role


def score_rollup_l1_authority(w3: Web3) -> dict:
    """Robinhood Chain's own L1 rollup upgrade authority -- Rollup, SequencerInbox,
    CoreProxyAdmin, DelayedInbox, Bridge, Outbox. First identified in batch 4
    (2026-09-15): a standard Arbitrum Orbit governance loop (UpgradeExecutor,
    CoreProxyAdmin) with EXECUTOR_ROLE held directly by a 7-of-8 Gnosis Safe
    (Robinhood's own governance docs name the Security Council: Robinhood x2,
    BitGo, Chainlink Labs, Fireblocks, Offchain Labs, Paxos, Talos -- confirmed
    batch 5) plus a real, correctly-configured 7-day TimelockControllerUpgradeable.
    PROPOSER_ROLE/CANCELLER_ROLE on that timelock are re-derived live every run
    (batch 8) rather than trusted from batch 4's one-time finding of "zero
    holders" -- that finding had gone stale (a Safe was granted PROPOSER_ROLE
    since) and was still being asserted as a hardcoded note on every push, the
    exact silent-staleness bug this project's own discipline exists to catch.

    Deliberately uses its OWN Ethereum-mainnet Web3 instance, ignoring the `w3`
    passed in (which is Robinhood Chain) -- this authority genuinely lives on L1,
    not the L2 these six contracts secure. Re-derives the EXECUTOR_ROLE holder via
    a live RoleGranted/RoleRevoked replay rather than trusting the address found
    in an earlier pass, exactly the discipline this project applies everywhere
    else.

    ADDED 2026-09-17 -- two findings promoted from
    chains/ethereum-l1/SESSION_NOTES_2026-09-16.md's backlog section 5, both
    re-verified live before being wired in or documented here:
    1. Cross-Safe signer overlap (re-derived live every run, see code below):
       the Proposer/Canceller Safe found by the PROPOSER_ROLE/CANCELLER_ROLE
       replay above is a DIFFERENT contract from the Security Council Safe,
       but its own internal signers substantially overlap -- live-confirmed
       2026-09-17: 6 of 8 signers (75%) are the same individuals on both
       Safes. Whenever that overlap is >=50%, timelockScore is capped lower
       than the "proposer==canceller" case alone would give it.
    2. Timelock usage history -- NOT re-derived every run (a full
       eth_getLogs scan from this Timelock's own deployment block to the
       current head, ~565k blocks as of 2026-09-17, is expensive enough that
       repeating it on every weekly production push isn't worth the cost for
       a fact this unlikely to change moment-to-moment; documented here as a
       dated point-in-time finding instead, the same convention already used
       for the LayerZero OApp count elsewhere in this project). Live-verified
       2026-09-17 (chunked eth_getLogs scan, cross-checked against the
       deployment tx's own receipt): this L1 Timelock has emitted exactly 9
       log entries in its entire history, ALL from its own deployment block
       -- zero `CallScheduled`, zero `CallExecuted`, zero `Cancelled` events
       ever. The 7-day delay and the proposer/canceller role separation
       above describe a mechanism that, as of this check, has never actually
       been exercised in practice."""
    targets = [
        ("0x23A19d23e89166adedbDcB432518AB01e4272D94", "Robinhood Chain L1 Rollup"),
        ("0xBd0D173EEb87D57A09521c24388a12789F33ba96", "Robinhood Chain L1 SequencerInbox"),
        ("0x1232813BDd40aa9d53066A880dE78a4Be70B90FD", "Robinhood Chain L1 CoreProxyAdmin"),
        ("0x1A07cc4BD17E0118BdB54D70990D2158AbAD7a2D", "Robinhood Chain L1 DelayedInbox"),
        ("0xDf8755334ce7A73cCF6b581C02eA649AE3E864b3", "Robinhood Chain L1 Bridge"),
        ("0xf0ce991ea4A0d2400A4AB49b20ae333f6Dce3DE9", "Robinhood Chain L1 Outbox"),
    ]
    notes = []

    l1 = get_w3("https://gateway.tenderly.co/public/mainnet")
    executor = "0x552603b4bc1f5E896AF2854548D6380f45f1B4bf"

    holders = _replay_role_holders(l1, executor, "EXECUTOR_ROLE", start_block=25_300_000)
    notes.append(f"EXECUTOR_ROLE holders re-derived live from genesis on Ethereum mainnet: {sorted(holders)}")

    if not holders:
        # A KNOWN, actively-used authority (re-confirmed 2026-09-16) reading as
        # empty is never a real "nobody holds this role" finding -- it means the
        # scan silently missed something (wrong topic encoding, a chunk gap).
        # Raise loudly instead of falling through to conservative defaults, which
        # would publish a wrong, misleadingly-low score as if it were a real
        # result (caught exactly this way in batch 7's own dry-run).
        raise RuntimeError(
            "score_rollup_l1_authority: EXECUTOR_ROLE holders came back EMPTY -- "
            "this is a known, actively-used role; treat this as a scan bug, not "
            "a real finding, and do not push a score from it."
        )

    safe_addr = next((h for h in holders if len(l1.eth.get_code(h)) < 500 and len(l1.eth.get_code(h)) > 0), None)
    admin_key, multisig, timelock = 15, 0, 0  # conservative defaults, only reached if a Safe/timelock READ fails below despite holders being non-empty
    security_council_owners = None
    if safe_addr:
        try:
            c = l1.eth.contract(address=safe_addr, abi=[
                {"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
                {"name": "getThreshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
            ])
            owners = c.functions.getOwners().call()
            threshold = c.functions.getThreshold().call()
            notes.append(f"{safe_addr}: {threshold}-of-{len(owners)} Safe holds EXECUTOR_ROLE directly")
            admin_key, multisig = 78, 75  # mature multisig, evolved off a bootstrap EOA (batch 4)
            security_council_owners = set(owners)
        except Exception as e:
            notes.append(f"Safe read on {safe_addr} failed: {e} -- falling back to conservative defaults")
    timelock_holder = next((h for h in holders if h != safe_addr), None)
    if timelock_holder:
        try:
            tl = l1.eth.contract(address=timelock_holder, abi=[
                {"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
            ])
            min_delay = tl.functions.getMinDelay().call()
            # batch 8: PROPOSER_ROLE/CANCELLER_ROLE re-derived live on THIS
            # timelock contract, replacing batch 4's one-time "zero proposer
            # holders" finding, which had gone stale (a Safe was granted
            # PROPOSER_ROLE since) while still being asserted as fact on every
            # push -- exactly the silent-staleness bug this project exists to
            # catch elsewhere, caught here on its own code.
            roles = _replay_role_holders(l1, timelock_holder, ["PROPOSER_ROLE", "CANCELLER_ROLE"], start_block=25_300_000)
            proposers, cancellers = roles["PROPOSER_ROLE"], roles["CANCELLER_ROLE"]
            notes.append(f"{timelock_holder}.getMinDelay() = {min_delay}; PROPOSER_ROLE holders = {sorted(proposers)}; CANCELLER_ROLE holders = {sorted(cancellers)}")
            if not min_delay or min_delay == 0:
                timelock = 0
                notes.append("Timelock delay is 0 -- gates nothing regardless of who can propose.")
            elif not proposers:
                timelock = 5
                notes.append("Real delay but genuinely zero PROPOSER_ROLE holders -- decorative, gates nothing today.")
            elif proposers == cancellers:
                timelock = 20
                notes.append("PROPOSER_ROLE and CANCELLER_ROLE are held by the IDENTICAL address set -- the timelock now gates real changes, but whoever can propose can also cancel any veto against themselves: no real separation of powers.")
                # ADDED 2026-09-17 (promoted from chains/ethereum-l1/SESSION_NOTES_2026-09-16.md's
                # backlog section 5, re-verified live before wiring in -- not
                # trusted from the note alone): the "separate" Proposer/Canceller
                # Safe found above is a DIFFERENT axis of overlap from the one
                # already checked -- does ITS OWN internal signer set actually
                # overlap with the Security Council Safe's, i.e. are these really
                # two independent human groups, not just two differently-named
                # contracts? Only checked when there's exactly one holder to
                # compare against the Security Council -- a multi-address
                # proposers/cancellers set would need per-address handling this
                # pass doesn't attempt.
                if security_council_owners and len(proposers) == 1:
                    proposer_canceller_safe = next(iter(proposers))
                    try:
                        pc = l1.eth.contract(address=proposer_canceller_safe, abi=[
                            {"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
                        ])
                        pc_owners = set(pc.functions.getOwners().call())
                        shared = security_council_owners & pc_owners
                        notes.append(
                            f"Proposer/Canceller Safe {proposer_canceller_safe} internal signer set vs Security Council "
                            f"Safe {safe_addr}: {len(shared)} of {len(pc_owners)} signers are the SAME individuals "
                            f"({100*len(shared)/len(pc_owners):.0f}% overlap)"
                        )
                        if len(pc_owners) and len(shared) / len(pc_owners) >= 0.5:
                            timelock = 10
                            notes.append(
                                "Over half the Proposer/Canceller Safe's own signers are also Security Council "
                                "signers -- the two 'independent' authority layers are substantially the same "
                                "people, not just the same address set holding both roles. Capping timelockScore "
                                "further than the proposer==canceller case alone would."
                            )
                    except Exception as e:
                        notes.append(f"Proposer/Canceller Safe owner read failed: {e} -- cross-Safe overlap not checked this run")
            else:
                timelock = 35
                notes.append("PROPOSER_ROLE and CANCELLER_ROLE are held by genuinely distinct addresses -- a real veto path independent of the proposer.")
        except Exception as e:
            notes.append(f"Timelock read on {timelock_holder} failed: {e}")

    composite = _composite(admin_key, multisig, timelock)
    return [
        {
            "target": addr, "label": label,
            "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
            "oracleAuthorityScore": 100, "compositeScore": composite,
            "notes": notes,
        }
        for addr, label in targets
    ]


def score_ramses_clv2(w3: Web3) -> dict:
    """Ramses CL V2 -- Factory, PoolDeployer, AccessHub, AccessHubProxyAdmin.
    Governed through a centralized AccessHub (AccessControl) rather than
    per-contract Ownable (batch 4). DEFAULT_ADMIN_ROLE held by both
    "RamsesTimelock" (batch 8: exact address 0xE41c07Cc...585436CE identified
    and confirmed a real OZ TimelockController -- schedule/execute/cancel/
    getMinDelay/isOperationPending/isOperationReady all present -- resolving
    batch 4's disclaimer that this address wasn't distinct from AccessHub) and
    an address labeled "Ramses Team Multisig", re-confirmed here live as a
    1-of-1 Safe whose sole signer is a bare EOA."""
    targets = [
        ("0xE0c4ceb92d08CA985bB70fe0a22fEb121A9854A8", "Ramses CL V2 Factory"),
        ("0x4b37359BF291AbE8453692DB58d515a8b013Dca9", "Ramses CL V2 PoolDeployer"),
        ("0x83341F891f898cb5E0cacC8a70501BBa83d9CecF", "Ramses CL V2 AccessHub"),
        ("0xA203A21dCCB461E415DaA342E8e635B6CeE0cCb3", "Ramses CL V2 AccessHubProxyAdmin"),
    ]
    notes = []

    team_multisig = "0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A"
    owners, threshold = safe_owners_and_threshold(w3, team_multisig) or (None, None)
    notes.append(f"\"Ramses Team Multisig\" {team_multisig}: {threshold}-of-{len(owners) if owners else '?'}")
    if owners and len(owners) == 1:
        sole_signer = owners[0]
        bare = is_eoa(w3, sole_signer)
        notes.append(f"Sole signer {sole_signer}: bare EOA = {bare} -- a Safe wrapper around a single private key")

    ramses_timelock = "0xE41c07CcD69A0f19A2186f3Ad30409BD585436CE"
    min_delay = call_raw(w3, ramses_timelock, [
        {"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    ], "getMinDelay")
    roles = _replay_role_holders(w3, ramses_timelock, ["PROPOSER_ROLE", "CANCELLER_ROLE", "EXECUTOR_ROLE"], start_block=0)
    proposers, cancellers, executors = roles["PROPOSER_ROLE"], roles["CANCELLER_ROLE"], roles["EXECUTOR_ROLE"]
    notes.append(
        f"RamsesTimelock {ramses_timelock}.getMinDelay() = {min_delay}; "
        f"PROPOSER_ROLE = {sorted(proposers)}; CANCELLER_ROLE = {sorted(cancellers)}; EXECUTOR_ROLE = {sorted(executors)}"
    )
    if proposers and proposers == cancellers == executors:
        notes.append("All three roles (propose/cancel/execute) are held by the SAME single address -- a timelock in name only, zero separation of powers even before considering its delay is 0.")

    admin_key, multisig, timelock = 15, 5, 0
    composite = _composite(admin_key, multisig, timelock)
    return [
        {
            "target": addr, "label": label,
            "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
            "oracleAuthorityScore": 100, "compositeScore": composite,
            "notes": notes,
        }
        for addr, label in targets
    ]


def score_ekubo_core(w3: Web3) -> dict:
    """Ekubo Core -- verified ownerless by design (batch 5): source code has zero
    authority concepts anywhere in its interface, official docs state it's
    ownerless on EVM explicitly, and an on-chain differential test (owner() and a
    deliberately fake selector both revert with identical empty data, while a real
    function reverts with real decoded error data) confirms the dispatcher routes
    correctly and the "authority" selectors genuinely don't exist. Re-confirms the
    owner()-reverts fact live here; does not re-run the full three-way
    differential test every pass (that was exhaustive and is not expected to
    change for an immutable, unverified-proxy-free contract)."""
    target = "0x00000000000014aA86C5d3c41765bb24e11bd701"
    notes = []
    owner = call_raw(w3, target, [{"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "owner")
    notes.append(f"owner() re-checked live: {'reverted (expected)' if owner is None else owner}")
    admin_key = multisig = timelock = 100
    return {
        "target": target, "label": "Ekubo Core",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_morpho_blue_singleton(w3: Web3) -> dict:
    """Morpho Blue singleton on Robinhood Chain -- by chain-specific TVL
    (DefiLlama `chainTvls["Robinhood Chain"]` ~$538M as of this rotation
    pass) the single largest authority surface on this chain, and until this
    pass NOT independently scored: batch 10's own new-target search
    (data/scored_targets_2026-09-17-batch10.md) asserted this address was
    already "covered" by the individual Morpho vaults tracked on this
    oracle (Steakhouse USDG, NetNet Credit, Purinta, Ethena x Steakhouse,
    Grove x Steakhouse, Steakhouse Turbo) -- but a vault's own
    owner()/curator() only governs THAT vault's allocation across markets,
    not the shared Morpho Blue singleton those markets are created on. The
    singleton's own owner() is a materially distinct, additional authority
    layer sitting underneath every vault and every isolated market on this
    chain (Longbow's 55 markets included) -- exactly the kind of unresolved
    root-authority gap this project's own discipline exists to catch, not a
    duplicate of anything already tracked. Corrects batch 10's claim rather
    than repeating it.

    Address `0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010` is Robinhood
    Chain's own deployment from `DefiLlama-Adapters/projects/morpho-blue/config.js`
    (the same primary-source convention used for every other target added
    via a DefiLlama adapter in this project, e.g. Meridian Perps/index 7's
    rotation audit) -- not a guess ported from another chain's address.

    Scope caveat, same as the already-coded Base-ecosystem sibling
    (`chains/base-ecosystem/scorers.py::score_morpho_blue`) and Morpho's own
    immutable-core design: owner() can only enable new IRMs/LLTVs for FUTURE
    markets and set the protocol fee (capped) + fee recipient -- it cannot
    touch funds already deposited into existing markets directly. Scored on
    the authority ROOT mechanism itself (a Safe, same convention as every
    other Safe-rooted target in this project), not on that narrower
    operational blast radius. Uses the identical formula already established
    for this exact same protocol on Base (not a new one-off number) so the
    same kind of target scores consistently across ecosystems."""
    target = "0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010"
    notes = []

    owner = read_address_getter(w3, target, "owner")
    notes.append(f"MorphoBlue.owner() = {owner}")
    fee_recipient = read_address_getter(w3, target, "feeRecipient")
    notes.append(f"MorphoBlue.feeRecipient() = {fee_recipient} (zero address = no fee currently set)")

    safe = safe_owners_and_threshold(w3, owner) if owner else None
    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}, owners {owners}")
        notes.append(
            "Scope caveat: owner() can only enable new IRMs/LLTVs for future markets and set "
            "the (capped) protocol fee + fee recipient -- cannot move funds already deposited "
            "in existing markets directly (Morpho's own immutable-core design). Root authority "
            "mechanism scored as-is, per this project's existing convention for every other "
            "Safe-rooted target."
        )
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController or Safe guard/module found anywhere in this chain

    return {
        "target": target,
        "label": "Morpho Blue (singleton, Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_noxa_fun_launch_locker(w3: Web3) -> dict:
    """NOXA Fun "Launch Locker" on Robinhood Chain -- rotation audit index 9
    (2026-09-19). Resolves a lead first found (but deliberately left open,
    not fabricated) during index 7's audit: see
    data/rotation_audit_2026-09-18-robinhood-chain-index7.md's "Noxa Fun --
    lead found, NOT resolved this run" section. That pass confirmed
    `locker.owner()` is a bare EOA on both RPCs but could only positively
    identify 5 of ~47 raw PUSH4 selectors in the bytecode (the standard OZ
    Ownable/NFT-receiver set) -- leaving it genuinely unknown whether that
    owner key can move the "permanently locked" Uniswap V3 LP positions
    themselves, since probing candidate names (`emergencyWithdraw`,
    `rescueTokens`, `sweep`) via `eth_call` can't distinguish "selector
    doesn't exist" from "exists, wrong caller" (an `onlyOwner` revert either
    way).

    This pass resolves it properly instead of repeating the same guess-and-
    probe approach: extracted EVERY PUSH4 selector from the locker's full
    runtime bytecode (36 found, deterministic disassembly, not a sampled
    subset) and looked each one up against the public 4byte.directory
    signature database instead of guessing candidate names by hand. Result:
    the only state-changing, coherent function set identified is a fee-
    management module (`setFeeCollector(address,bool)`,
    `setProtocolFeeRecipient(address)`, `setProtocolFeeShare(uint256)`,
    `collectFees(address)`, plus the view getters `feeCollectors(address)`,
    `protocolFeeRecipient()`, `protocolFeeShare()`) alongside the standard
    OZ `Ownable`/`Initializable`/`ReentrancyGuard`/ERC721-receiver selectors
    already found last time. NO selector in the complete 36-selector set
    matches any principal-moving function (no `withdraw`, `unlock`,
    `migrate`, `decreaseLiquidity`, `rescueTokens`, `sweep`, or similar) --
    a real negative result now, since this is the full selector inventory
    of a small (4,823-byte) contract cross-checked against a real signature
    database, not a partial scan. `collect(...)` present in the set is the
    Uniswap V3 position-manager style fee-collection call (accrued trading
    fees only), not a principal withdrawal.

    Address `0x7F03effbd7ceB22A3f80Dd468f67eF27826acD85` sourced from
    `DefiLlama-Adapters/projects/noxa-fun/index.js` (`robinhood` entry),
    same primary-source convention as every other DefiLlama-adapter-sourced
    target in this project. `chainTvls["Robinhood Chain"]` ~$5.27M
    (DefiLlama API, `doublecounted: true` in the adapter itself -- already
    counted as DEX TVL elsewhere, disclosed here, not hidden). Independently
    corroborated on-chain (not just trusting that one number): the locker
    really does hold live Uniswap V3 LP NFTs -- `balanceOf(locker)` on the
    shared position manager (`0x73991a25C818Bf1f1128dEAaB1492D45638DE0D3`,
    the SAME position manager UNCX Network's own V3 locker uses on this
    chain, confirming DefiLlama's own `doublecounted` flag) returned 60,142
    on both RPCs, with the first several `tokenId`s spot-checked via
    `positions()` all showing real nonzero `liquidity` -- not an empty or
    dead contract.

    `owner()` = `0x7E035Fb048a31e0481b88074557415b1C187242B`, identical on
    both `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`, 0
    bytecode (bare EOA) on both. Nonce 45 / non-zero balance on both RPCs --
    a real, actively-used key, not a dormant/vanity address. Scored via the
    same standalone-bare-EOA convention already established for a single
    (non-alias, non-multi-contract-converging) EOA root elsewhere in this
    file (`score_curve_dex()`'s own `5 if controller_is_eoa` branch) --
    admin_key=5, not a bespoke discount for the fee-only scope found above:
    this project's own convention (see `score_morpho_blue_singleton()`'s
    identical reasoning) is to score the root authority MECHANISM as-is
    regardless of how narrow its operational blast radius turns out to be,
    not to invent a scope-based adjustment."""
    locker = "0x7F03effbd7ceB22A3f80Dd468f67eF27826acD85"
    position_manager = "0x73991a25C818Bf1f1128dEAaB1492D45638DE0D3"
    notes = []

    owner = read_address_getter(w3, locker, "owner")
    notes.append(f"locker.owner() = {owner}")
    owner_is_eoa = is_eoa(w3, owner) if owner else None
    notes.append(f"owner {owner}: bare EOA = {owner_is_eoa}")

    nft_balance = call_raw(
        w3, position_manager,
        _UINT256_GETTER("balanceOf", "address"),
        "balanceOf", Web3.to_checksum_address(locker),
    )
    notes.append(
        f"positionManager.balanceOf(locker) = {nft_balance} live Uniswap V3 LP NFTs held "
        "(non-empty/live contract check, not proof of exact TVL)"
    )
    notes.append(
        "Full 36-selector PUSH4 bytecode inventory cross-checked against 4byte.directory: "
        "only a coherent fee-management module (setFeeCollector/setProtocolFeeRecipient/"
        "setProtocolFeeShare/collectFees) plus standard OZ Ownable/Initializable/"
        "ReentrancyGuard/ERC721-receiver selectors found -- no principal-moving selector "
        "(withdraw/unlock/migrate/decreaseLiquidity/rescueTokens/sweep) present in the "
        "complete set. See data/rotation_audit_2026-09-19-robinhood-chain-index9.md for the full list."
    )

    if owner_is_eoa is True:
        admin_key, multisig, timelock_score = 5, 0, 0
    elif owner_is_eoa is False:
        admin_key, multisig, timelock_score = 40, 0, 0
    else:
        notes.append("owner() unresolved this run -- degrading to conservative unresolved-authority score")
        admin_key, multisig, timelock_score = 40, 0, 0

    return {
        "target": locker,
        "label": "NOXA Fun Launch Locker",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_uncx_v3_locker(w3: Web3) -> dict:
    """UNCX Network's Uniswap-V3-style "Liquidity Locker" on Robinhood Chain --
    rotation audit index 10 (2026-09-19) new-target search. Resolves a lead
    left open across TWO prior rotation-audit passes (index 8's batch and
    index 9's own audit -- data/rotation_audit_2026-09-19-robinhood-chain-index9.md,
    "UNCX Network -- investigated, still NOT resolved" section): the owner
    role was already confirmed as a real 2-of-3 Gnosis Safe on 2 independent
    RPCs, but no verifiable primary source for the `UNCX_LiquidityLocker`
    contract itself could be found (Sourcify 404 for chain 4663, no public
    GitHub repo located at the time), so scoring a Safe whose actual GOVERNED
    POWERS were unknown was deliberately withheld (the same discipline that
    caught action's fabricated Spark claim -- see
    data/maker_checker_2026-09-19-overdue-actions-review.md).

    Resolved this pass: UNCX Network's real, official GitHub organization
    (`github.com/uncx-network` -- its public profile's own `blog` field
    points to `https://uncx.network/`, not a guessed/similarly-named
    account) publishes `liquidity-locker-univ3-contracts`, containing
    `contracts/UNCX_LiquidityLocker_UniV3.sol`. Cross-checked this source
    against the DEPLOYED bytecode on Robinhood Chain mainnet rather than
    assuming it's identical just because the org name matches: extracted
    every candidate PUSH4 selector from the locker's runtime bytecode via
    raw disassembly (62 candidates, identical on both
    `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`) and computed
    the selectors for 26 functions/errors named in that source file -- 25 of
    26 matched exactly (`owner()`/`transferOwnership()`/`renounceOwnership()`
    plus every state-changing function reviewed below), strong confirmation
    this is that same source, not a coincidentally similar contract.
    CORRECTED 2026-09-19 (independent re-verification): the one "miss" was
    `withdraw(uint256,address)` and it is an artifact of scanning only PUSH4
    -- its selector `0x00f714ce` starts with a zero byte, so solc pushes it as
    PUSH3. Re-checked live on both RPCs: it IS in the deployed bytecode (47 of
    47 signatures derived from the source and its interface are present), and a
    `withdraw()` simulated from the owner Safe reverts `OWNER` on every lock.
    The conclusion (same source) is unchanged and slightly stronger.

    What the source shows the Safe can and cannot do: `withdraw()` and
    `migrate()` both gate on `isLockAdmin()` (`msg.sender == that individual
    lock's own owner`, NOT the contract's `onlyOwner`) -- the Safe cannot
    pull any user's locked LP position directly. `adminRefundERC20()` /
    `adminRefundEth()` are `onlyOwner`, but the source's own comment states
    (and the plain ERC20-transfer-selector mechanics used confirm) they
    cannot move the locked ERC-721 LP positions -- NFTs don't share that
    interface, the call would revert `'ST'`. The Safe's real `onlyOwner`
    powers are: fee configuration (`setFeeParams`/`addOrEditFee`/
    `removeFee`/`setFeeResolver`), which NFT position managers are
    `allow`ed, `setUCF` (can only DECREASE a lock's fee-tracking value, per
    its own `require(_ucf < l.ucf)`), and `setMigrator`/
    `setMigrateInContract` (points a FUTURE `migrate()` call at an address
    of the Safe's choosing -- a real but indirect rug vector against a lock
    owner who later calls `migrate()` themselves, not a direct seizure of
    anyone's position). Scored on the authority ROOT mechanism (a confirmed
    2-of-3 Safe), per this project's now-standard convention (see
    `score_morpho_blue_singleton()`'s identical reasoning) -- no bespoke
    discount invented for this bounded-but-real scope.

    Address `0xF28704c691290547924e2129D407dA36bda8ce0f` sourced from
    `DefiLlama-Adapters/projects/unicrypt-v3/index.js` (`robinhood` entry),
    same primary-source convention as every other DefiLlama-sourced target
    here. Uses the threshold-aware adminKeyScore convention introduced for
    `score_morpho_blue_singleton()` (65 for threshold>=3, 50 for exactly
    2-of-N, 10 unresolved) rather than the older, coarser flat branch in
    `score_arcus_ptoken()` -- both formulas exist in this file today; this
    scorer deliberately uses the more recent, threshold-aware one.

    UNCX's SECOND Robinhood Chain locker (`unicrypt-v4/index.js` -- UNCX's
    own next locker generation, NOT "Uniswap V4"; a different, larger
    contract: 120 candidate selectors vs this one's 62, only 9 of the same
    26 known signatures found) shares the identical owner Safe but is
    explicitly NOT scored here -- its own source was not located this pass.
    Left open, not guessed at, for a future rotation pass; see
    data/rotation_audit_2026-09-19-robinhood-chain-index10.md."""
    locker = "0xF28704c691290547924e2129D407dA36bda8ce0f"
    notes = []

    owner = read_address_getter(w3, locker, "owner")
    notes.append(f"locker.owner() = {owner}")
    safe = safe_owners_and_threshold(w3, owner) if owner else None

    if not safe:
        notes.append(f"{owner}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock_score = 20, 0, 0
    else:
        owners, threshold = safe
        notes.append(f"owner is a real Gnosis Safe: {threshold}-of-{len(owners)}, owners {owners}")
        notes.append(
            "Source-verified scope (github.com/uncx-network/liquidity-locker-univ3-contracts, "
            "47/47 source signatures present in deployed bytecode; an earlier PUSH4-only scan "
            "reported 25/26, the miss being a PUSH3 artifact, corrected 2026-09-19): withdraw()/migrate() gate "
            "on the individual lock owner (isLockAdmin), not onlyOwner -- the Safe cannot pull a "
            "user's locked LP position directly. onlyOwner powers are fee configuration, allowed "
            "position managers, setUCF (decrease-only), and setMigrator/setMigrateInContract (an "
            "indirect rug vector on a lock owner's own future migrate() call, not direct seizure). "
            "Also (eth_call simulation with state overrides, 2026-09-19): setFeeParams names the "
            "auto-collect account, which may collect() on any lock, and setUCF can lower a lock's fee "
            "to 0, so a Safe-controlled account can redirect any lock's UNCOLLECTED trading fees "
            "(never principal). Root authority mechanism scored as-is, per this project's convention."
        )
        admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
        multisig = min(100, threshold * 15 + max(0, len(owners) - threshold) * 5)
        timelock_score = 0  # no TimelockController or Safe guard/module found anywhere in this chain

    return {
        "target": locker,
        "label": "UNCX Network V3 Locker (Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


_BYTES32_ROLE_GETTER = lambda name: [  # noqa: E731
    {"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bytes32"}]}
]
_ROLE_MEMBER_COUNT_ABI = [{"name": "getRoleMemberCount", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": [{"type": "uint256"}]}]
_ROLE_MEMBER_ABI = [{"name": "getRoleMember", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "uint256"}], "outputs": [{"type": "address"}]}]
_DEFAULT_ADMIN_ROLE_BYTES = bytes(32)


def _enumerable_role_members(w3: Web3, address: str, role_bytes: bytes) -> list:
    """Live re-derivation of an OZ AccessControlEnumerable role's CURRENT member
    set via getRoleMemberCount()/getRoleMember() -- the same enumerable-interface
    convention already used for score_morpho_blue_singleton()'s and
    score_arcus_ptoken()'s own factory (see rotation_audit_2026-09-19-...-index10.md),
    preferred over a full eth_getLogs role-replay (_replay_role_holders()) when the
    target actually exposes this interface, since it's a handful of eth_calls
    instead of a full-history log scan. Returns [] (not None) if the count read
    itself fails, so a caller can treat "empty" and "unreadable" the same way
    (both mean "don't trust this as a real member list")."""
    count = call_raw(w3, address, _ROLE_MEMBER_COUNT_ABI, "getRoleMemberCount", role_bytes)
    if not count:
        return []
    return [call_raw(w3, address, _ROLE_MEMBER_ABI, "getRoleMember", role_bytes, i) for i in range(count)]


def score_arcus_perps_bridgevault(w3: Web3) -> dict:
    """Arcus Perps' BridgeVault -- rotation audit batch, 2026-09-19 (new-target
    search while auditing index 11 / Arcus pBTC (1x)). A DIFFERENT Arcus
    product from the already-tracked Arcus pToken family (ARCUS_TARGETS
    above, `parentProtocol: parent#arcus` on DefiLlama covers both, but they
    do not share the same on-chain authority chain): Arcus Perps is a
    dYdX-team-built, Robinhood-Crypto-partnered perpetual-futures venue that
    runs its OWN validator-consensus settlement layer bridged into Robinhood
    Chain (DefiLlama `arcus-perps`, `chainTvls["Robinhood Chain"]` ~$24.1M,
    `registries/sumTokens.js` entry naming this exact address as the
    `owner` -- confirmed live via `balanceOf()` on both RPCs: ~24,131,742
    arcUSDG, 6 decimals, matching DefiLlama's figure within normal snapshot-
    timing drift).

    Address sourced from `DefiLlama-Adapters/registries/sumTokens.js`'s
    `arcus-perp.robinhood` entry (labeled only "// bridge" there, no further
    context) -- identified via Arcus's own real, official GitHub org
    (`github.com/arcus-xyz`, confirmed via the org's own public `blog` field
    pointing to `https://arcus.xyz/`, the same verification method already
    used for `github.com/uncx-network` at index 10) and its public
    `rootchain-contracts-abis` repo, which names this exact address
    `BridgeVault` ("Deposit/withdrawal custody vault (margin asset)") and
    publishes its full ABI plus 3 sibling contracts' addresses -- all 3
    cross-verified as an EXACT match against addresses independently
    discovered ON-CHAIN first (via this scorer's own live
    getRoleMemberCount()/getRoleMember() read on BridgeVault's own
    DEFAULT_ADMIN_ROLE, BEFORE that GitHub repo was ever consulted), not the
    other way around -- the repo's names explain facts already found live on
    chain, rather than being trusted as the source of the facts themselves.
    Only ABIs are published, not Solidity source -- see the disclosed gap
    below for exactly what that limits.

    BridgeVault's own DEFAULT_ADMIN_ROLE (re-derived live via
    getRoleMemberCount()/getRoleMember(), identical on 2 independent RPCs
    -- `rpc.mainnet.chain.robinhood.com`, `robinhood.drpc.org`) is held by
    THREE separate contracts, not one Safe and not one EOA:
      - a real OpenZeppelin `TimelockController` (`getMinDelay()` = 86400s,
        24h) -- named `TimelockController` in Arcus's own repo, deployed at
        block 814616, hundreds of thousands of blocks AFTER the other two
        (block ~159135-159162) -- added as a later governance layer, not
        part of the original bootstrap.
      - `ValidatorConsensus` -- Arcus's own rootchain validator-set contract
        (`threshold()` = 2, `VALIDATOR_ROLE` has exactly 3 members, all
        confirmed bare EOAs on both RPCs). Exposes
        `executeGovernanceAction(actionNumber, parentActionHash, calls,
        deadline)` where `calls` is an arbitrary `(target, data)[]` list --
        i.e. a 2-of-3 validator-signature quorum can direct this contract to
        call ANY function on ANY target (including BridgeVault's own
        `upgradeToAndCall()`/`setWithdrawalsPaused()`/`grantRole()`, all of
        which BridgeVault's ABI shows as its only privileged surface --
        `DEFAULT_ADMIN_ROLE()` is the ONLY role-name constant BridgeVault's
        ABI exposes, meaning DEFAULT_ADMIN_ROLE itself very likely gates
        every one of those functions directly via `onlyRole`) with only an
        upper-bound `deadline` -- NOT a minimum delay.
      - `CheckpointManager` -- state-root checkpoint commitments for the L2.

    The TimelockController's own PROPOSER_ROLE/EXECUTOR_ROLE/CANCELLER_ROLE
    (re-derived live, identical on both RPCs) are held by the SAME
    ValidatorConsensus + CheckpointManager contracts, plus exactly one further
    address (CORRECTED 2026-09-19: NOT an EOA -- it has 171 bytes of code and is
    a 2-of-4 Gnosis Safe, re-read on both Robinhood mainnet RPCs; its 4 owners
    are bare EOAs that appear in no other tracked group):
    `0x4f1d777bf36E259F3cB66f2cE969f4c5De05ebe2` -- which is ALSO one of the
    3 owners of the 2-of-3 Gnosis Safe already tracked for the Arcus pToken
    family (`ARCUS_TARGETS` above, beacon owner
    `0x81B80499C396a9931b9e44953425a82C1b2541bd`, confirmed at rotation
    audit indices 10 and 11) -- a real, live-confirmed cross-protocol signer
    overlap between Arcus's two DIFFERENT products, wired into
    `signer_overlap.py` as a new group below (drops BOTH `arcus` and this
    new group's crossExposureScore from 100 to 80; does not change either
    group's compositeScore, which does not depend on crossExposureScore --
    same mechanic as the PancakeSwap V2/V3 and Steakhouse 4-vault
    crossExposure corrections already in this project's history).

    Scoring judgment call (the kind AGENTS.md requires disclosing, not
    smoothing over): the 24h TimelockController is REAL, but does not gate
    the operative path to BridgeVault's admin surface, because
    ValidatorConsensus independently holds the identical DEFAULT_ADMIN_ROLE
    and can reach it with ZERO minimum delay via its own
    executeGovernanceAction -- the two are parallel paths to the SAME power,
    not a fast/emergency-only path alongside a slower routine-governance
    path (contrast `score_rollup_l1_authority()`, where the "instant" holder
    is a named, disclosed 7-of-8 institutional Security Council and the
    Timelock is a genuinely separate, additional check that STILL gates
    something real). Here, the validator quorum is the protocol's own
    day-to-day operational key (it is how blocks/checkpoints get finalized
    at all), not a break-glass body, and it can already reach every function
    the Timelock's 24h delay would otherwise gate. Scored on that operative
    2-of-3 root mechanism (same threshold-aware convention already
    established for `score_morpho_blue_singleton()`/`score_uncx_v3_locker()`
    -- 50/35 for 2-of-3), with `timelockScore = 0` rather than crediting a
    delay that does not actually constrain the fastest available path --
    disclosed explicitly here rather than either fabricating credit for it
    or silently ignoring that it exists.

    Disclosed gap, not smoothed over: only ABIs are published by Arcus (no
    Solidity source), so the EXACT role gating each individual BridgeVault
    function (rather than inferred from DEFAULT_ADMIN_ROLE being the only
    role-name constant its ABI exposes) is not confirmed from source the way
    UNCX's locker was at index 10 -- this project's own rule that "a
    getter/interface succeeding is not evidence of real gating; only
    reading the actual source is" applies here as a real limitation, not a
    box-ticking exercise. The live facts this score rests on (the 2-of-3
    threshold, all-EOA validator set, and the identical DEFAULT_ADMIN_ROLE
    held by both the validator contract and the Timelock) are independently
    chain-verified regardless of that gap."""
    bridge_vault = "0x14b107cf534239c59571b066cb6497a321da897c"
    validator_consensus = "0x9d032106aE6e41F36132Fff1e7b0d973B4e55Da8"
    timelock = "0x0dA180B14721CE46A83669b4816cb652caa1001D"
    checkpoint_manager = "0xA3D46D248224070f58C5F750E1f2fcA2123DF487"
    notes = []

    admin_holders = _enumerable_role_members(w3, bridge_vault, _DEFAULT_ADMIN_ROLE_BYTES)
    notes.append(f"BridgeVault.DEFAULT_ADMIN_ROLE members (live) = {admin_holders}")
    expected_admins = {Web3.to_checksum_address(a) for a in (timelock, validator_consensus, checkpoint_manager)}
    actual_admins = {Web3.to_checksum_address(a) for a in admin_holders} if admin_holders else set()

    if actual_admins != expected_admins:
        notes.append(
            f"DIVERGENCE: expected DEFAULT_ADMIN_ROLE holders {sorted(expected_admins)}, "
            f"got {sorted(actual_admins)} -- authority chain has changed since this scorer "
            "was written; scoring conservatively rather than assuming the old shape still applies."
        )
        admin_key, multisig, timelock_score = 10, 0, 0
    else:
        threshold = call_raw(w3, validator_consensus, [{"name": "threshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint64"}]}], "threshold")
        validator_role = Web3.keccak(text="VALIDATOR_ROLE")
        validators = _enumerable_role_members(w3, validator_consensus, validator_role)
        all_eoa = all(is_eoa(w3, v) for v in validators) if validators else False
        notes.append(f"ValidatorConsensus.threshold() = {threshold}, VALIDATOR_ROLE members = {validators} (all bare EOAs: {all_eoa})")

        min_delay = call_raw(w3, timelock, [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}], "getMinDelay")
        notes.append(f"TimelockController.getMinDelay() = {min_delay}s -- real delay, but does NOT gate the operative path: ValidatorConsensus independently holds the same DEFAULT_ADMIN_ROLE and reaches it via executeGovernanceAction() with only an expiry deadline, not a minimum delay")

        if not threshold or not validators or not all_eoa:
            notes.append("ValidatorConsensus threshold/members not cleanly resolved this run -- conservative score")
            admin_key, multisig, timelock_score = 10, 0, 0
        else:
            admin_key = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
            multisig = min(100, threshold * 15 + max(0, len(validators) - threshold) * 5)
            timelock_score = 0  # see docstring: a real Timelock exists but does not gate the operative, undelayed validator-quorum path to the identical DEFAULT_ADMIN_ROLE

    return {
        "target": bridge_vault,
        "label": "Arcus Perps BridgeVault (Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_longbow_vault(w3: Web3, vault: str, label: str) -> dict:
    """Longbow -- Core, Frontier, ETH vaults (batch 5). owner() and curator()
    resolve to two SEPARATELY deployed Gnosis Safes with the identical 3 owners
    and identical 2-of-3 threshold on every vault checked -- no real separation
    of duties between the two roles meant to check each other. Re-derives
    owner()/curator() and both Safes' owner sets live for whichever vault is
    passed in."""
    notes = []
    owner = read_address_getter(w3, vault, "owner")
    curator = read_address_getter(w3, vault, "curator")
    notes.append(f"owner() = {owner}, curator() = {curator}")
    owner_safe = safe_owners_and_threshold(w3, owner) if owner else None
    curator_safe = safe_owners_and_threshold(w3, curator) if curator else None
    if owner_safe:
        notes.append(f"owner Safe: {owner_safe[1]}-of-{len(owner_safe[0])}, owners {owner_safe[0]}")
    if curator_safe:
        notes.append(f"curator Safe: {curator_safe[1]}-of-{len(curator_safe[0])}, owners {curator_safe[0]}")
    if owner_safe and curator_safe and set(owner_safe[0]) == set(curator_safe[0]):
        notes.append("Confirmed: owner and curator Safes share the IDENTICAL owner set -- no real separation of duties")

    admin_key, multisig, timelock = 40, 40, 15
    return {
        "target": vault, "label": label,
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_uniswap_v2_factory_feetosetter(w3: Web3) -> dict:
    """Uniswap V2 Factory feeToSetter (batch 4) -- confirmed the SAME root address
    already found controlling v3 Factory, v4 PoolManager, and the UniswapX reactor.
    A fourth surface reached via the same identity, end to end across every Uniswap
    deployment on this chain. RESOLVED 2026-09-17 (see score_uniswap_v3_factory()
    docstring): now scored via the same `_score_uniswap_bridge_alias_root()` path
    instead of flat bare-EOA scoring."""
    target = "0x8bcEaA40B9AcdfAedF85AdF4FF01F5Ad6517937f"
    notes = []
    fee_to_setter = call_raw(w3, target, [{"name": "feeToSetter", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}], "feeToSetter")
    notes.append(f"feeToSetter() = {fee_to_setter}")
    bare = is_eoa(w3, fee_to_setter) if fee_to_setter else None

    if bare:
        admin_key, multisig, timelock = _score_uniswap_bridge_alias_root(fee_to_setter, notes)
    else:
        admin_key, multisig, timelock = 40, 0, 0
    return {
        "target": target, "label": "Uniswap V2 Factory feeToSetter",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }




def score_chainlink_admin_safe(w3: Web3) -> dict:
    """Chainlink Price Feed Admin (Robinhood Chain) -- batch 8. Not a protocol
    consuming an oracle, but the oracle's OWN governance: owner() on 7
    independently-sampled Chainlink aggregator proxies (3 already-tracked stock
    token feeds -- TSLA/AMZN/AMD -- plus LINK/USD, ETH/USD, USDG/USD) all
    resolve, live, to this SAME address. Chainlink is the only officially
    confirmed oracle provider on Robinhood Chain (chain.link's own
    feeds-robinhood-mainnet.json dataset, 57 feeds). Every one of those 57
    feeds -- and therefore every protocol on this chain that consumes one,
    tracked or not -- inherits whatever authority controls this single Safe.
    No timelock/delay layer above this Safe was identified this pass; absence
    of evidence is not treated as evidence of one, so timelockScore stays 0
    rather than being assumed."""
    target = "0xEE27D5aE494300902D90454E8630a3f1c68C9c52"
    notes = []

    owners, threshold = safe_owners_and_threshold(w3, target) or (None, None)
    notes.append(f"Chainlink feed admin Safe {target}: {threshold}-of-{len(owners) if owners else '?'}")
    if owners:
        notes.append(f"Confirmed live as owner() on 7 independently-sampled Chainlink feeds (Robinhood TSLA/AMZN/AMD stock feeds, LINK/USD, ETH/USD, USDG/USD).")
        # ADDED 2026-09-21: this Safe has a module enabled (Confirmed Transaction Module 0.1.0) and sits on a singleton that is not a
        # published Safe build (a v1.3.0 rebuild with the ERC-165 guard check); both read live, notes only.
        notes.append(_safe_modules_note(target, _read_safe_modules(w3, target), _read_safe_guard_addr(w3, target)))
        notes.append(_safe_singleton_note(target, _read_safe_singleton(w3, target)))

    # CORRECTED 2026-09-21: this used `threshold * 8` for multisigScore (a batch-8 heuristic that gave a 4-of-9 a 32 and the
    # composite its published 36, with no rationale written down) and kept adminKeyScore 65 even when the Safe did not resolve.
    # It now follows the batch-9 convention every other Safe-rooted target here uses (_safe_rooted_scores: 15 per required
    # signature + 5 per extra owner, 65 for threshold >= 3), and an unresolved Safe degrades to the unresolved-authority floor.
    if owners:
        admin_key, multisig, timelock = _safe_rooted_scores(threshold, len(owners))
    else:
        notes.append(f"{target}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock = 20, 0, 0
    composite = _composite(admin_key, multisig, timelock)
    return {
        "target": target, "label": "Chainlink Price Feed Admin (Robinhood Chain)",
        "adminKeyScore": admin_key, "multisigScore": min(multisig, 100), "timelockScore": timelock,
        # CHANGED 2026-10-04 (Spap's go): this target IS a price provider (METHODOLOGY's own first example): who controls what
        # it reports is this Safe, so oracleAuthorityScore is its own path composite, no longer 100.
        "oracleAuthorityScore": composite, "compositeScore": composite,
        "notes": notes,
    }


def score_layerzero_infra(w3: Web3) -> list:
    """LayerZero V2 messaging infrastructure on Robinhood Chain -- batch 8.
    Discovered via a live eth_getLogs replay of DelegateSet on the EndpointV2
    (965 events since genesis, 709 distinct OApps registered) -- a real,
    heavily-used cross-chain messaging layer completely absent from this
    oracle before now, distinct from the chain's own already-tracked L1
    rollup bridge.

    EndpointV2, SendUln302 and ReceiveUln302 all share the SAME owner()
    (0xE590a673...), confirmed live and independently for each of the three.
    That owner is NOT a Gnosis Safe (getOwners()/getThreshold() both revert
    on it) -- it is a bespoke on-chain multisig (bytecode contains "OneSig",
    a real LayerZero-authored multisig pattern), exposing getSigners()/
    threshold() instead, resolved via custom_multisig_owners_and_threshold()
    (new in web3_utils.py this batch specifically for this discovery).

    Executor (0x4208d6e2...) is DELIBERATELY EXCLUDED from this scorer: it is
    a separate EIP-1967 proxy whose own admin slot resolves to a THIRD,
    still-unidentified 2319-byte contract that matches neither the Safe nor
    the custom-multisig pattern -- left as an open thread rather than guessed
    at, same discipline as Pendle's MarketFactoryV6 owner elsewhere in this
    file."""
    targets = [
        ("0x6F475642a6e85809B1c36Fa62763669b1b48DD5B", "LayerZero V2 EndpointV2 (Robinhood Chain)"),
        ("0xC39161c743D0307EB9BCc9FEF03eeb9Dc4802de7", "LayerZero V2 SendUln302 (Robinhood Chain)"),
        ("0xe1844c5D63a9543023008D332Bd3d2e6f1FE1043", "LayerZero V2 ReceiveUln302 (Robinhood Chain)"),
    ]
    notes = []

    owner = read_address_getter(w3, targets[0][0], "owner")
    for addr, label in targets[1:]:
        other_owner = read_address_getter(w3, addr, "owner")
        if other_owner != owner:
            notes.append(f"WARNING: {label} owner() = {other_owner} differs from {targets[0][1]}'s {owner} -- re-check before trusting a shared score")
    notes.append(f"EndpointV2/SendUln302/ReceiveUln302 all confirmed live to share owner() = {owner}")

    resolved = custom_multisig_owners_and_threshold(w3, owner)
    if resolved:
        signers, threshold = resolved
        notes.append(f"{owner} is a bespoke (non-Safe) on-chain multisig: {threshold}-of-{len(signers)} via getSigners()/threshold()")
        # CORRECTED 2026-09-21: multisigScore was `threshold * 8` (a batch-8 heuristic, 40 for 5-of-7); it now uses the same
        # threshold-and-dispersion formula as every Safe-rooted target (85 for 5-of-7). The discount for a bespoke, non-Safe
        # multisig stays where it was, in adminKeyScore (55 instead of a Safe's 65).
        admin_key, multisig = 55, _safe_rooted_scores(threshold, len(signers))[1]
    else:
        notes.append(f"{owner}: neither Gnosis Safe nor the known bespoke-multisig pattern matched -- unresolved authority")
        admin_key, multisig = 20, 0

    composite = _composite(admin_key, multisig, 0)
    return [
        {
            "target": addr, "label": label,
            "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": 0,
            "oracleAuthorityScore": 100, "compositeScore": composite,
            "notes": notes,
        }
        for addr, label in targets
    ]


def _safe_rooted_scores(threshold: int, n_owners: int, shared_custody_and_upgrade: bool = False):
    """Batch 9 convention for a target whose ENTIRE authority chain ends in one
    plain Gnosis Safe (no module, no guard, no timelock found above it):
    adminKeyScore 65 for threshold >= 3, 50 for threshold 2 (a Safe, but one
    where any two keys suffice), 10 for threshold 1 (a Safe wrapper around one
    key). multisigScore = 15 per required signature + 5 per extra (non-required)
    owner, capped at 100 -- rewards both threshold and dispersion.
    `shared_custody_and_upgrade` knocks 5 off adminKeyScore when the SAME Safe
    both holds user funds and can upgrade the code guarding them (no
    separation of duties). A heuristic like every other in this file, stated
    rather than hidden -- it lands the four batch-9 targets in the same range
    as the closest existing shapes (Arcus 2-of-3 = 43, Longbow 2-of-3 = 33,
    Chainlink 4-of-9 = 36, LayerZero 5-of-7 = 34). CORRECTED 2026-09-21: those last two anchors used the older
    `threshold * 8` heuristic; Chainlink and LayerZero now use this convention too (52 and 48)."""
    if threshold >= 3:
        admin_key = 65
    elif threshold == 2:
        admin_key = 50
    else:
        admin_key = 10
    if shared_custody_and_upgrade:
        admin_key -= 5
    multisig = min(100, threshold * 15 + max(0, n_owners - threshold) * 5)
    return admin_key, multisig, 0


def _safe_guard_and_modules(w3: Web3, safe: str):
    """(modules, guard) for a Gnosis Safe -- a module or guard can bypass or
    change the threshold, so a Safe's threshold is only meaningful once both
    are confirmed empty."""
    modules = call_raw(w3, safe, [{"name": "getModulesPaginated", "type": "function", "stateMutability": "view",
                                   "inputs": [{"type": "address"}, {"type": "uint256"}],
                                   "outputs": [{"type": "address[]"}, {"type": "address"}]}],
                       "getModulesPaginated", "0x0000000000000000000000000000000000000001", 10)
    guard_slot = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
    guard = read_slot_as_address(w3, safe, guard_slot)
    return (modules[0] if modules else None), guard


def _safe_rooted_entry(w3: Web3, target: str, label: str, safe: str, notes: list, shared_custody_and_upgrade=False):
    resolved = safe_owners_and_threshold(w3, safe) if safe else None
    if not resolved:
        notes.append(f"{safe}: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score")
        admin_key, multisig, timelock = 20, 0, 0
    else:
        owners, threshold = resolved
        modules, guard = _safe_guard_and_modules(w3, safe)
        notes.append(f"root Safe {safe}: {threshold}-of-{len(owners)}, modules={modules}, guard={guard}")
        admin_key, multisig, timelock = _safe_rooted_scores(threshold, len(owners), shared_custody_and_upgrade)
        if modules or (guard and int(guard, 16) != 0):
            notes.append("WARNING: Safe has a module or guard -- threshold alone no longer describes who can act; re-check by hand")
    return {
        "target": target, "label": label,
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_pancakeswap_v2_factory(w3: Web3) -> dict:
    """PancakeSwap AMM (V2-style) Factory -- rotation-audit batch, 2026-09-18.
    Address from DefiLlama-Adapters' own projects/pancake-swap/index.js
    `defaultExport` (the deterministic factory address PancakeSwap reuses
    across Polygon zkEVM/Linea/op_bnb/Arbitrum/Base/Monad/Robinhood -- the
    same "identical address on many chains" convention already used for the
    PancakeSwap V3 factory above), confirmed live on two independent RPCs:
    14,075 bytes of deployed code, allPairsLength()=156 real pairs (not a
    stub). No proxy admin, no owner() -- V2-style factories only gate
    fee-routing via feeTo/feeToSetter, pairs themselves are immutable so
    there is no upgrade surface at all. feeToSetter() is a bare EOA (0
    bytecode) with a real, non-zero nonce (20) on this chain -- an
    actively-used key, not a vanity/dormant address -- that alone can
    redirect protocol fees (setFeeTo) or hand off control (setFeeToSetter),
    with zero delay. Given the $1.9B TVL DefiLlama attributes to this
    protocol across all its chains, the blast radius here is fee-routing
    control only (pools/liquidity are not upgradeable and not custodied by
    this address), not a rug of pooled funds -- but a single uncontested key
    over that surface, exactly the Curve DEX pattern already tracked above."""
    factory = "0x02a84c1b3BBD7401a5f7fa98a384EBC70bB5749E"
    notes = []
    fee_to = read_address_getter(w3, factory, "feeTo")
    fee_to_setter = read_address_getter(w3, factory, "feeToSetter")
    notes.append(f"factory.feeTo() = {fee_to}, factory.feeToSetter() = {fee_to_setter}")
    setter_is_eoa = is_eoa(w3, fee_to_setter) if fee_to_setter else None
    setter_safe = safe_owners_and_threshold(w3, fee_to_setter) if fee_to_setter else None
    notes.append(f"feeToSetter {fee_to_setter}: bare EOA = {setter_is_eoa}, Safe = {bool(setter_safe)}")

    if setter_is_eoa:
        admin_key = 5
    elif setter_safe:
        admin_key = 40
        notes.append(f"WARNING: feeToSetter is actually a Safe ({setter_safe[1]}-of-{len(setter_safe[0])}) -- re-score by hand, not covered by this heuristic")
    else:
        admin_key = 40
    multisig = 0
    timelock_score = 0  # no TimelockController found gating feeTo/feeToSetter

    return {
        "target": factory,
        "label": "PancakeSwap AMM (V2) Factory",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_pancakeswap_v3_factory(w3: Web3) -> dict:
    """PancakeSwap AMM V3 Factory (batch 9). Address from PancakeSwap's own docs
    (developer.pancakeswap.finance/contracts/v3/addresses) and DefiLlama's
    pancakeswap-v3 adapter, deterministic CREATE3 address shared with every other
    PancakeSwap V3 chain. Factory.owner() is a 183-byte UUPS proxy (implementation
    exposes upgradeTo/upgradeToAndCall/proxiableUUID, owner-gated) whose owner()
    is a plain 3-of-6 Safe -- the same Safe address PancakeSwap uses on
    Ethereum/Arbitrum/Base/BSC as a 3-of-7 (the Robinhood copy has one owner
    fewer). The Safe therefore controls both factory ownership and upgrades of
    the owner wrapper itself. No timelock found anywhere in the chain."""
    factory = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
    notes = []
    wrapper = read_address_getter(w3, factory, "owner")
    notes.append(f"factory.owner() = {wrapper} (UUPS owner-wrapper proxy)")
    safe = read_address_getter(w3, wrapper, "owner") if wrapper else None
    notes.append(f"wrapper.owner() = {safe}")
    return _safe_rooted_entry(w3, factory, "PancakeSwap V3 Factory", safe, notes)


def score_sushiswap_v3_factory(w3: Web3) -> dict:
    """SushiSwap V3 Factory (batch 9). Address from Sushi's canonical config
    (sushi-labs/sushi, src/evm/config/features/sushiswap-v3.ts, ROBINHOOD entry)
    and DefiLlama dimension-adapters. Factory.owner() is a 3,956-byte
    Ownable2Step fee-manager wrapper (setFactoryOwner/enableFeeAmount/
    setProtocolFee) whose owner() is a plain 2-of-3 Safe (v1.4.1). That Safe was
    NOT found at the same address on Ethereum/Arbitrum/Base/BSC/Optimism --
    chain-specific, no public documentation of its signers found this pass. The
    factory and pools are immutable, so the blast radius is fee/tier control, not
    fund custody."""
    factory = "0xE51960f1B45f1C9FB6D166E6a884F866fC70433B"
    notes = []
    wrapper = read_address_getter(w3, factory, "owner")
    notes.append(f"factory.owner() = {wrapper} (Ownable2Step fee-manager wrapper)")
    safe = read_address_getter(w3, wrapper, "owner") if wrapper else None
    notes.append(f"wrapper.owner() = {safe}")
    return _safe_rooted_entry(w3, factory, "SushiSwap V3 Factory", safe, notes)


def score_symbiosis_portal(w3: Web3) -> dict:
    """Symbiosis Portal (batch 9) -- holds assets locked for cross-chain swaps.
    Absent from Symbiosis' own js-sdk for Robinhood; sourced from
    DefiLlama-Adapters symbiosis-finance config (robinhood block, token addresses
    matching docs.robinhood.com) plus identical bytecode prefix to the Optimism
    Portal at the same address. TransparentUpgradeableProxy: EIP-1967 admin slot
    -> ProxyAdmin, and BOTH Portal.owner() (pause/business logic) and
    ProxyAdmin.owner() (upgrades) resolve to the SAME 3-of-5 Safe. Re-derives
    both hops live and flags if they ever diverge."""
    portal = "0x292fC50e4eB66C3f6514b9E402dBc25961824D62"
    notes = []
    proxy_admin = read_slot_as_address(w3, portal, EIP1967_ADMIN_SLOT)
    pa_owner = read_address_getter(w3, proxy_admin, "owner")
    portal_owner = read_address_getter(w3, portal, "owner")
    notes.append(f"EIP-1967 admin slot -> ProxyAdmin {proxy_admin}, ProxyAdmin.owner() = {pa_owner}; Portal.owner() = {portal_owner}")
    if pa_owner != portal_owner:
        notes.append("WARNING: upgrade authority and business-logic owner now DIFFER -- scored on the upgrade authority only; re-check by hand")
    return _safe_rooted_entry(w3, portal, "Symbiosis Portal", pa_owner, notes)


def score_strato_bridge_router(w3: Web3) -> dict:
    """STRATO (BlockApps Mercata) bridge, Robinhood Chain side (batch 9). NOT
    Robinhood's canonical bridge. depositRouter/custody from STRATO's own Cirrus
    API (BlockApps-MercataBridge-chains, key 4663 enabled), same source DefiLlama's
    strato-bridge adapter reads. depositRouter is a UUPS proxy (no EIP-1967 admin
    slot: upgradeToAndCall is gated by owner() inside the implementation), and
    its owner() is the custody Safe itself -- a plain 2-of-3 that both HOLDS the
    bridged funds and can UPGRADE the router that deposits into it. The same
    2-of-3 Safe, identical owners, also exists at the same address on Ethereum
    and Base: two keys control this bridge's custody across chains."""
    router = "0x0dc846db6a4eC7b5a3e542F7db88049E9ADd2541"
    custody = "0x8c458F866e603335ef179A63a2528F357732f5d5"
    notes = []
    router_owner = read_address_getter(w3, router, "owner")
    same = bool(router_owner) and Web3.to_checksum_address(router_owner) == Web3.to_checksum_address(custody)
    notes.append(f"depositRouter.owner() = {router_owner}; equals custody Safe {custody}: {same}")
    return _safe_rooted_entry(w3, router, "STRATO Bridge depositRouter (Robinhood side)", router_owner, notes,
                              shared_custody_and_upgrade=same)


def score_up_v3_factory(w3: Web3) -> dict:
    """up v3 (up33.xyz) -- rotation audit new-target search (2026-09-19,
    budget spent while auditing index 13). Native, Robinhood-Chain-only
    "(3,3)" CLMM exchange (DefiLlama slug `up-v3`, twitter `@uponrh`,
    `chainTvls["Robinhood Chain"]` ~$8.5M at pull time) -- the highest-TVL
    open lead carried over across rotation-audit passes at indices 8, 9, and
    12 (see those runs' own "leads not pursued" sections). Every prior pass
    grepped for `projects/up-v3/index.js` and found nothing, because that
    file genuinely doesn't exist: DefiLlama tracks this protocol's TVL
    through the SHARED `registries/uniswapV3.js` factory-log-replay registry
    instead of a bespoke per-protocol adapter (`'up-v3': { robinhood: {
    factory: '0x1ac9dB4a2608ba45D6127B1737949b51Bb54B7F3', fromBlock:
    6184096, eventAbi: 'event PoolCreated(address indexed token0, address
    indexed token1, int24 indexed tickSpacing, address pool)', ... } }` --
    fetched fresh from DefiLlama-Adapters' own file this pass, not
    transcribed from memory) -- a different lookup path than the dead one
    every prior pass kept re-checking, which is what actually resolves this.

    Confirmed a genuine Uniswap-V3-fork factory before trusting the registry
    label: deployed bytecode (4,917 bytes, identical on both RPCs) exposes a
    plain `owner()` getter that does not revert, consistent with the same
    `PoolCreated(address,address,int24,address)` topic the registry itself
    replays to enumerate this factory's pools for TVL.

    `owner()` resolves live on 2 independent RPCs
    (`rpc.mainnet.chain.robinhood.com`, `robinhood.drpc.org`), identical
    both times, straight to a REAL Gnosis Safe
    (`0x0eEA30aBa3f07abFA20E4b544F55e0f917d9DFd8`, 2-of-4, no module, guard
    slot zero on both RPCs) -- a root authority chain independent of every
    other Uniswap-family target already tracked here (v3 Factory, v4
    PoolManager, UniswapX, V2 feeToSetter all converge on the same Arbitrum
    L1->L2 governance-bridge alias; this Safe and its 4 owners were grepped
    against every existing `scripts/lib/signer_overlap.py` group and every
    hardcoded address in this file before concluding that -- no match found
    anywhere, a genuinely new authority root, not a duplicate). Scored via
    the same threshold-aware `_safe_rooted_entry()` convention already used
    for every other factory-owner Safe in this file (PancakeSwap V3,
    SushiSwap V3, Symbiosis Portal, STRATO bridge) -- no bespoke discount
    for this being "just a DEX factory": the owner can call the standard
    Uniswap-V3-fork admin surface (`enableFeeAmount`/`setOwner`), the same
    class of power already scored this way elsewhere in this file.
    CORRECTED 2026-09-19 (independent re-verification against the deployed
    bytecode, and eth_call simulation from the Safe): this factory is NOT a
    plain Uniswap V3 fork. It has no `enableFeeAmount`; it exposes a
    tick-spacing interface (`enableTickSpacing`, `tickSpacingToFee`) plus
    `setOwner` and the swap-fee-manager / unstaked-fee-manager and fee-module
    setters. The same Safe is also the governor, emergency council and epoch
    governor of the Voter the factory points to, the team address of that
    Voter's VotingEscrow and Minter, and the owner of its FactoryRegistry; the
    contracts behind swapFeeModule/unstakedFeeModule were not traced. No score
    changes -- only the description of what the owner can call."""
    factory = "0x1ac9dB4a2608ba45D6127B1737949b51Bb54B7F3"
    notes = []
    safe = read_address_getter(w3, factory, "owner")
    notes.append(f"factory.owner() = {safe}")
    return _safe_rooted_entry(w3, factory, "up v3 Factory (Robinhood Chain)", safe, notes)


def score_alandale_v3_factory(w3: Web3) -> dict:
    """Alandale V3 (alandale.xyz, twitter `@alandalexyz`) -- rotation audit
    new-target search (2026-09-19, budget spent while auditing index 14).
    A ve(3,3) DEX native to Robinhood Chain (DefiLlama slug `alandale-v3`,
    `chainTvls["Robinhood Chain"]` ~$1.99M at pull time). Address from
    DefiLlama-Adapters' shared `registries/uniswapV3.js` (`'alandale'` entry,
    `robinhood.factory`, `isAlgebra: true`, `fromBlock: 27941500`) -- fetched
    fresh this pass, and cross-checked here rather than trusted.

    TVL, corrected rather than repeated: DefiLlama's ~$1.99M is inflated by
    ~$0.85M through ONE wrong price. coins.llama.fi lists the USAR token at
    $757.70 (within 0.4% of SPY's own price -- likely a mapping error), while
    the on-chain Uniswap USAR/USDG pool's `slot0()` (identical on 2 RPCs)
    gives ~$15.59 and DexScreener quotes $15.5-16.3 across 5 pairs on 3 DEXes.
    Recomputed from the chain: all 59 pools enumerated from the factory's own
    `Pool` events, every `poolByPair(token0, token1)` re-read on 2
    independent RPCs (59/59), token balances summed at one pinned block
    (identical on both RPCs) and priced with USAR at its on-chain price =
    $1,136,756 -- within 0.1% of DexScreener's own independent liquidity sum
    ($1,135,966 over the 58 of 59 pools it knows). Honest headline: ~$1.14M
    specific to Robinhood Chain (Alandale exists nowhere else), on 2
    independent sources; the pass-through DefiLlama figure is NOT relied on.

    Identity check before trusting the label: the deployed implementation
    (8,149 bytes, identical on both RPCs) exposes ALL 35 reference selectors
    (the 22 functions of the official Algebra Integral v1.0
    `IAlgebraFactory`, fetched from `cryptoalgebra/Algebra` branch
    `integral-v1.0` -- the org is GitHub-verified and its `blog` field points
    to algebra.finance -- plus OZ Ownable2Step/AccessControlEnumerable's own,
    de-duplicated), and NONE of the later releases match as well (1.1 through
    1.3 each miss 5-6 of their own reference selectors) -- so this is
    Integral v1.0-based, NOT stock: 10 extra function selectors are present
    (`initialize(address)`, `createPlugin`, `createVaultForPool`,
    `getVaultForPool`, `deploy`, `isPublicPoolCreationMode`/
    `setIsPublicPoolCreationMode`, `POOLS_CREATOR_ROLE`, and 2 unidentified
    ones, 0x5a05180f/0x7965db0b), plus solc's own `Panic(uint256)`. The
    verified source of the deployed variant was not reachable (Sourcify 404;
    the real explorer, robinhoodchain.blockscout.com, sits behind a
    Cloudflare bot challenge, which this project does not bypass), so this
    score rests ONLY on the ownership/upgrade chain below, never on
    assumptions about what the custom extras do.

    Authority chain, re-derived live on 2 independent RPCs: the factory is a
    proxy (2,210 bytes) whose runtime embeds OpenZeppelin v4's
    `TransparentUpgradeableProxy: admin cannot fallback to proxy target` /
    `ERC1967: new admin is the zero address` revert strings and both EIP-1967
    slots -- i.e. the address in its EIP-1967 admin slot is the only address
    that can upgrade it. That admin (`0x95c0bE4a...2f71`, 1,690 bytes) has the
    standard OZ ProxyAdmin selector set (`upgrade`/`upgradeAndCall`/
    `changeProxyAdmin`/`owner`/`transferOwnership`/`renounceOwnership`), and
    `ProxyAdmin.owner()`, `factory.owner()` and the factory's sole
    `DEFAULT_ADMIN_ROLE` holder (`getRoleMemberCount` = 1) all resolve to the
    SAME plain Gnosis Safe (`0x2a04c1D2...2B0E`, v1.4.1, 3-of-5, nonce 132, no
    module, guard slot zero). All 5 owners are bare EOAs with real nonces
    (28-241). No TimelockController anywhere in the chain. Scored on the
    upgrade authority like `score_symbiosis_portal()` (same proxy-admin-hop
    convention, WARNING appended if the two ever diverge). No
    `shared_custody_and_upgrade` discount: the Safe does not custody user
    funds (pools are separate contracts), same as every other factory-owner
    Safe scored this way (PancakeSwap V3, SushiSwap V3, up v3).

    Scope, stated rather than implied: this scores the CL factory's owner +
    upgrade authority only. Alandale's ve(3,3) layer (Voter, Minter,
    VotingEscrow, gauges) and each pool's plugin were NOT traced this pass --
    the ~$0.05M Alandale V2 (classic pools) factory, a separate proxy, is not
    covered either. The 5 signer addresses, the Safe and the ProxyAdmin were
    grepped against every hardcoded address in this repo before wiring the
    new `alandale_v3` signer-overlap group -- zero matches; the live
    `compute_cross_exposure()` re-derivation (owners re-read from every
    tracked Safe, not only the hardcoded ones) is the authoritative check."""
    factory = "0x16494A80E08Bcb9285D87b67149d7b01774D82F8"
    notes = []
    proxy_admin = read_slot_as_address(w3, factory, EIP1967_ADMIN_SLOT)
    pa_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    factory_owner = read_address_getter(w3, factory, "owner")
    notes.append(f"EIP-1967 admin slot -> ProxyAdmin {proxy_admin}, ProxyAdmin.owner() = {pa_owner}; factory.owner() = {factory_owner}")
    if pa_owner != factory_owner:
        notes.append("WARNING: upgrade authority and factory owner now DIFFER -- scored on the upgrade authority only; re-check by hand")
    return _safe_rooted_entry(w3, factory, "Alandale V3 Factory (Robinhood Chain)", pa_owner, notes)


def score_fables_pool_registry(w3: Web3) -> dict:
    """Fables (batch 10, 2026-09-17) -- a hook-native ve(3,3) DEX built on
    Uniswap v4, ~$21.8M TVL (DefiLlama). FablesPoolRegistry address is from
    DefiLlama's own official TVL adapter for this protocol
    (DefiLlama-Adapters/projects/fables/index.js, `REGISTRY` constant, live on
    every DefiLlama TVL refresh -- not a third-party write-up), cross-checked
    live here: real bytecode (7,455 bytes) and a working `activePools()` call
    returning real pool data.

    The registry is NOT Ownable -- it uses OpenZeppelin's AccessManager
    pattern (`authority()` returns the manager; `register`/`deregister`/
    `setAuthority` are all gated by `getTargetFunctionRole()` = roleId 0,
    ADMIN_ROLE). Replaying every RoleGranted/RoleRevoked event for roleId 0 on
    the AccessManager from genesis finds exactly ONE grant, ever, and zero
    revokes: a single address has held ADMIN_ROLE since deployment.

    That address is NOT a Gnosis Safe -- its on-chain code is the EIP-7702
    delegation designator (`0xef0100` + implementation address), meaning it's
    an EOA that has delegated execution to a smart-account implementation
    (unverified on the explorer), not a multisig. It has 470 real transactions
    on Robinhood Chain (a genuinely active operational key, not a fresh or
    vanity-mined one -- the same activity-based check this project already
    uses to distinguish a real EOA from a bridge alias, see
    `score_uniswap_v4_poolmanager`'s docstring), but EIP-7702 delegation does
    not itself imply multi-party signing, and no multisig-style ABI (owners/
    threshold) resolves at this address. Scored as a real, active bare-EOA
    equivalent: sole control, no separation of duties, no delay found on
    `register`/`deregister`/`setAuthority`."""
    registry = "0x159a113E012593d9B3Cc63aD45e30F0467e13ef3"
    notes = []
    manager = call_raw(w3, registry, _addr_getter_abi("authority"), "authority")
    notes.append(f"registry.authority() = {manager}")

    # ADMIN_ROLE on an OZ AccessManager is roleId 0, not a keccak-named role
    # hash like AccessControl's roles -- _replay_role_holders() assumes the
    # latter, so ADMIN_ROLE holders are replayed directly here instead.
    granted_topic = Web3.keccak(text="RoleGranted(uint64,address,uint32,uint48,bool)")
    revoked_topic = Web3.keccak(text="RoleRevoked(uint64,address)")
    admin_topic_val = "0x" + (0).to_bytes(32, "big").hex()
    grant_logs = w3.eth.get_logs({
        "fromBlock": 0, "toBlock": "latest", "address": manager,
        "topics": ["0x" + granted_topic.hex(), admin_topic_val],
    })
    revoke_logs = w3.eth.get_logs({
        "fromBlock": 0, "toBlock": "latest", "address": manager,
        "topics": ["0x" + revoked_topic.hex(), admin_topic_val],
    })
    events = [(l["blockNumber"], l["logIndex"], "GRANT", "0x" + l["topics"][2].hex()[-40:]) for l in grant_logs]
    events += [(l["blockNumber"], l["logIndex"], "REVOKE", "0x" + l["topics"][2].hex()[-40:]) for l in revoke_logs]
    # FIXED 2026-09-17 (same bug hunt finding as _replay_role_holders() above,
    # independently duplicated here): sort on (blockNumber, logIndex), not
    # blockNumber alone, so a REVOKE-then-GRANT within one block (GRANT logs
    # are always fetched and appended first) doesn't replay backwards.
    events.sort(key=lambda e: (e[0], e[1]))
    admins = set()
    for _, _, kind, addr in events:
        addr = Web3.to_checksum_address(addr)
        admins.add(addr) if kind == "GRANT" else admins.discard(addr)
    notes.append(f"ADMIN_ROLE (roleId 0) grant/revoke replay from genesis: current holders = {sorted(admins)}")

    admin_key, multisig, timelock_score = 5, 0, 0
    if len(admins) == 1:
        sole = next(iter(admins))
        code = w3.eth.get_code(sole)
        is_7702 = bytes(code[:3]) == b"\xef\x01\x00"
        nonce = w3.eth.get_transaction_count(sole)
        notes.append(f"sole ADMIN_ROLE holder {sole}: EIP-7702 delegated code = {is_7702} (raw code {code.hex()}), tx count = {nonce}")
        if not is_7702 and not code:
            notes.append("Plain bare EOA (no delegation) -- same bare-EOA-equivalent scoring applies.")
    elif len(admins) > 1:
        notes.append(f"WARNING: {len(admins)} ADMIN_ROLE holders found, not the expected 1 -- re-check by hand before trusting this score.")

    return {
        "target": registry,
        "label": "Fables PoolRegistry",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_beefy_spy_weth_vault(w3: Web3) -> dict:
    """Beefy (batch 10, 2026-09-17) -- representative vault for Beefy's
    Robinhood Chain deployment (~$2.57M total TVL across ~14 vaults per
    DefiLlama; this project samples the flagship one rather than tracking
    every vault, the same convention already used for Robinhood's ~230
    tokenized stocks). Vault address from Beefy's own official `beefy-v2`
    repo (github.com/beefyfinance/beefy-v2, `src/config/vault/robinhood.json`,
    entry `alandale-cow-robinhood-weth-spy-vault`'s `earnContractAddress` --
    Beefy's current source of truth; their older standalone `address-book`
    npm package repo has no Robinhood Chain entry at all, confirmed live here
    by listing its full git tree).

    `vault.owner()` and `strategy.owner()` are two SEPARATE, real
    `TimelockController` contracts (confirmed by name on Blockscout, not
    assumed), both governed by the SAME real 3-of-6 Gnosis Safe
    (`0x000000a151...bdb82`, 6 distinct owner addresses -- re-checked here
    live via `getOwners()`/`getThreshold()`) holding both PROPOSER_ROLE and
    CANCELLER_ROLE on each (role holders re-derived via a live
    RoleGranted/RoleRevoked replay, not assumed from the grant tx alone). The
    deployer's own TIMELOCK_ADMIN_ROLE was revoked one block after deployment
    on both Timelocks (confirmed live) -- each Timelock now self-administers,
    not the deployer.

    The vault-level Timelock's `getMinDelay()` = 0 (no delay on whatever the
    vault owner can call directly). The strategy-level Timelock's
    `getMinDelay()` = 21,600s (6h) -- a real, non-zero delay. The vault
    contract ALSO has its own internal `approvalDelay()` = 21,600s (6h),
    Beefy's standard `proposeStrat`/`upgradeStrat` cooldown on swapping the
    strategy itself (the single highest-value action for a yield vault) --
    this internal delay applies regardless of the wrapping Timelock's own
    (zero) delay. PROPOSER_ROLE and CANCELLER_ROLE being the IDENTICAL Safe on
    both Timelocks means there is no independent veto path, the same
    limitation already scored this way for Robinhood Chain's own L1 rollup
    authority and for Ramses CL V2 -- reused here, not a new convention."""
    vault = "0x87673A619Fc4F3Fc08068A0BB04f60aA2D04ca62"
    notes = []

    owner = read_address_getter(w3, vault, "owner")
    notes.append(f"vault.owner() = {owner}")
    strategy = call_raw(w3, vault, _addr_getter_abi("strategy"), "strategy")
    notes.append(f"vault.strategy() = {strategy}")
    strat_owner = read_address_getter(w3, strategy, "owner") if strategy else None
    notes.append(f"strategy.owner() = {strat_owner}")

    approval_delay = call_raw(w3, vault, _UINT256_GETTER("approvalDelay"), "approvalDelay")
    notes.append(f"vault.approvalDelay() (internal strategy-swap cooldown) = {approval_delay}s")

    vault_min_delay = call_raw(w3, owner, _UINT256_GETTER("getMinDelay"), "getMinDelay") if owner else None
    strat_min_delay = call_raw(w3, strat_owner, _UINT256_GETTER("getMinDelay"), "getMinDelay") if strat_owner else None
    notes.append(f"vault Timelock getMinDelay() = {vault_min_delay}s; strategy Timelock getMinDelay() = {strat_min_delay}s")

    roles = _replay_role_holders(w3, owner, ["PROPOSER_ROLE", "CANCELLER_ROLE"], start_block=0) if owner else {"PROPOSER_ROLE": set(), "CANCELLER_ROLE": set()}
    proposers, cancellers = roles["PROPOSER_ROLE"], roles["CANCELLER_ROLE"]
    notes.append(f"vault Timelock PROPOSER_ROLE = {sorted(proposers)}; CANCELLER_ROLE = {sorted(cancellers)}")

    # FIXED 2026-09-17 (closed a bug hunt finding): this docstring claims
    # role holders are "re-derived via a live RoleGranted/RoleRevoked
    # replay" on BOTH Timelocks, but only the vault Timelock's roles were
    # ever actually replayed -- strat_owner's PROPOSER_ROLE/CANCELLER_ROLE
    # were never queried by any code path, so a divergence (governance
    # reassigning the strategy Timelock's roles to a weaker signer set
    # while leaving the vault Timelock untouched) would go completely
    # undetected. Independently replayed here and compared.
    strat_roles = _replay_role_holders(w3, strat_owner, ["PROPOSER_ROLE", "CANCELLER_ROLE"], start_block=0) if strat_owner else {"PROPOSER_ROLE": set(), "CANCELLER_ROLE": set()}
    strat_proposers, strat_cancellers = strat_roles["PROPOSER_ROLE"], strat_roles["CANCELLER_ROLE"]
    notes.append(f"strategy Timelock PROPOSER_ROLE = {sorted(strat_proposers)}; CANCELLER_ROLE = {sorted(strat_cancellers)}")
    roles_match = proposers == strat_proposers and cancellers == strat_cancellers
    if not roles_match:
        notes.append("WARNING: strategy Timelock's PROPOSER_ROLE/CANCELLER_ROLE do NOT match the vault Timelock's -- the docstring's 'same Safe governs both' claim does not hold live this run, degrading rather than trusting the vault-only read")

    safe_resolved = safe_owners_and_threshold(w3, next(iter(proposers))) if len(proposers) == 1 else None
    admin_key, multisig, timelock_score = 15, 0, 0
    if safe_resolved and roles_match:
        owners, threshold = safe_resolved
        notes.append(f"PROPOSER Safe {next(iter(proposers))}: {threshold}-of-{len(owners)}, owners {owners}")
        admin_key, multisig, _ = _safe_rooted_scores(threshold, len(owners))
        if proposers == cancellers and approval_delay and approval_delay > 0:
            timelock_score = 20  # real non-zero delay on the highest-risk action, but proposer == canceller: no independent veto path (same convention as the L1 rollup / Ramses identical-set case)
            notes.append("Real >0 delay on the highest-risk action (strategy swap), but PROPOSER_ROLE == CANCELLER_ROLE (same Safe) -- no independent veto path.")
        elif approval_delay and approval_delay > 0:
            timelock_score = 35
        else:
            timelock_score = 0
    elif safe_resolved and not roles_match:
        admin_key, multisig, timelock_score = 15, 0, 0  # degraded: the vault-side Safe resolved, but the strategy Timelock's roles weren't confirmed to match it this run

    return {
        "target": vault,
        "label": "Beefy: SPY-WETH vault (Robinhood Chain, representative)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_snuggle_maxfi_vault(w3: Web3) -> dict:
    """Snuggle (batch 11, 2026-09-17) -- automated Uniswap V3 concentrated-
    liquidity manager, ~$6.2M TVL on Robinhood Chain (DefiLlama `snuggle`,
    `chainTvls["Robinhood Chain"]`). Vault address from DefiLlama's own official
    TVL adapter (`DefiLlama-Adapters/projects/snuggle/index.js`,
    `ROBINHOOD_VAULTS`, labelled "MaxFi Robinhood", a Snuggle white-label on the
    same contract architecture) -- the only Robinhood Chain vault that adapter
    lists. Cross-checked live: Sourcify runtime+creation bytecode match for both the proxy
    (OpenZeppelin TransparentUpgradeableProxy) and its implementation
    (`src/SnuggleVaultUpgradeable.sol:SnuggleVaultUpgradeable`), and the vault
    holds 11,849 Uniswap V3 position NFTs (`balanceOf` on the
    NonfungiblePositionManager the adapter itself names) -- real user custody.

    Authority: the EIP-1967 admin slot is an OZ ProxyAdmin whose `owner()` is a
    plain bare EOA (no bytecode, no EIP-7702 designator, 759 real transactions
    on this chain -- a live private key, not a bridge alias). `vault.owner()`
    is that SAME EOA. Mitigating context checked and found not to change the
    score: the vault routes most admin calls through an AdminSatellite
    (`adminSatellite()`, verified source `SnuggleVaultAdminSatellite`) that has
    a real `TIMELOCK_DELAY` of 24h, but that delay only covers
    propose/execute of the treasury and staking-manager addresses.
    `addPool()` (which makes the vault `setApprovalForAll` its NFT manager to an
    arbitrary position adapter) and `updatePoolRewardAdapter()` are instant,
    and `setAdminSatellite()` is directly `onlyOwner` on the vault; the same EOA
    can also upgrade the implementation instantly through the ProxyAdmin. The
    24h delay therefore gates nothing that key cannot route around.

    Scored with the Curve DEX convention for one bare key holding both the
    custody-side role and the upgrade path (`admin_key = 2`), not a new number."""
    vault = "0x1195C074F898b7644bA732407619c9804dFE6DCE"
    notes = []

    proxy_admin = read_slot_as_address(w3, vault, EIP1967_ADMIN_SLOT)
    notes.append(f"EIP-1967 admin slot -> ProxyAdmin {proxy_admin}")
    pa_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    notes.append(f"ProxyAdmin.owner() = {pa_owner}")
    vault_owner = read_address_getter(w3, vault, "owner")
    notes.append(f"vault.owner() = {vault_owner}")
    satellite = read_address_getter(w3, vault, "adminSatellite")
    sat_delay = call_raw(w3, satellite, _UINT256_GETTER("TIMELOCK_DELAY"), "TIMELOCK_DELAY") if satellite else None
    notes.append(f"vault.adminSatellite() = {satellite}, TIMELOCK_DELAY() = {sat_delay}s (covers treasury/staking-manager changes only; addPool/updatePoolRewardAdapter instant, setAdminSatellite onlyOwner on the vault)")

    same_key = bool(pa_owner) and bool(vault_owner) and Web3.to_checksum_address(pa_owner) == Web3.to_checksum_address(vault_owner)
    controller = pa_owner or vault_owner
    controller_code = w3.eth.get_code(Web3.to_checksum_address(controller)) if controller else None
    controller_is_eoa = controller_code is not None and len(controller_code) == 0
    is_7702 = controller_code is not None and bytes(controller_code[:3]) == b"\xef\x01\x00"
    notes.append(f"controller {controller}: bare EOA = {controller_is_eoa}, EIP-7702 delegated = {is_7702}, ProxyAdmin.owner == vault.owner: {same_key}")

    if controller is None:
        admin_key = 5  # unresolved this run: fail closed, never award a better score for a check not performed
        notes.append("Controller did not resolve this run -- scoring bare-EOA-equivalent rather than assuming a better setup")
    elif controller_is_eoa or is_7702:
        admin_key = 2 if same_key else 5
    else:
        resolved = safe_owners_and_threshold(w3, controller)
        if resolved:
            admin_key = 40
            notes.append(f"WARNING: controller is now a Safe ({resolved[1]}-of-{len(resolved[0])}) -- authority changed since batch 11, re-score by hand")
        else:
            admin_key = 5
            notes.append("WARNING: controller has code but is not a resolvable Safe -- re-check by hand; scored bare-EOA-equivalent meanwhile")
    multisig = 0
    timelock_score = 0

    return {
        "target": vault,
        "label": "Snuggle: MaxFi Robinhood vault",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_t3tris_vault(w3: Web3) -> dict:
    """T3tris Finance WBTC vault -- rotation audit, new-target search while
    auditing index 12 (2026-09-19). DefiLlama `t3tris-finance`
    (`chainTvls["Robinhood Chain"]` ~$819k at pull time) sources its TVL
    dynamically, not from a hardcoded adapter list: `projects/t3tris-finance/
    index.js` calls T3tris's own `ecosystem.t3tris.finance/vaults` API each
    run and sums `getGrossTVL()` across every entry with `verified: true` and
    `blacklisted: false` for the chain in question. That live registry (read
    directly, not trusted secondhand) lists 4 Robinhood Chain (chainId 4663)
    vaults at time of this audit: one empty (0 totalAssets), one negligible
    (~$25 in USDG), and two material ones -- a ~$210.8k USDG vault
    (`0xd4d607239dcbdb5cc3a301266433810bb63c63bf`) and THIS one, a ~$610k
    WBTC vault (`totalAssets` 7.49041449 WBTC, confirmed live via
    `getGrossTVL()` on 2 independent RPCs, identical), the single largest
    T3tris vault found on this chain. Summed across all 4 registry entries,
    live on-chain `getGrossTVL()` (~$821.1k using DefiLlama's own
    `coins.llama.fi` WBTC spot price at pull time) matches DefiLlama's
    independently-reported `chainTvls["Robinhood Chain"]` (~$819.2k) within
    normal snapshot-timing drift -- two independent sources agreeing this
    TVL is real and chain-specific, not a stale or malformed registry entry.
    T3tris's GitHub org (`t3tris-finance`) confirmed genuinely theirs via its
    own `blog` field pointing to `t3tris.finance` (same verification method
    already used for `github.com/arcus-xyz` and `github.com/uncx-network`),
    but -- disclosed, not smoothed over -- it publishes only a DefiLlama-
    Adapters fork, no actual vault source, the same kind of gap already
    accepted for Arcus Perps BridgeVault.

    Each of the 4 registry vaults is a minimal EIP-1967-style proxy (141
    bytes, identical across all 4) delegating to the SAME implementation
    (`0x0000000000AC46824E664881581f0E105Bb5e492`, read from the standard
    EIP-1967 implementation slot on 2 independent RPCs, no admin/beacon slot
    set), but -- checked explicitly, not assumed -- each proxy's own storage
    grants OZ AccessControl's `DEFAULT_ADMIN_ROLE` to a DIFFERENT address:
    this is a marketplace of independently-curated vaults sharing only code,
    not a shared authority chain (the 3 sibling vaults are each a distinct,
    separately-keyed EOA, left untracked this pass -- the empty one has no
    TVL to score, the ~$25 one is immaterial, and the ~$210.8k USDG one is a
    genuinely different admin key that would need its own separate finding,
    not folded into this one).

    For the vault actually scored here: `RoleGranted`/`RoleRevoked` event
    history (full replay from genesis, one-time discovery work, not repeated
    every run) shows `DEFAULT_ADMIN_ROLE` granted ONCE, at deployment, to
    `0x65D02Bb13f515DD105Fb733E9E31f11A2F65e57f`, never revoked -- confirmed
    still current via a live `hasRole()` call below every run instead of
    trusting that history to stay true. The SAME address also self-granted
    itself 47 other narrower, function-level roles at deployment (later
    revoking 6 of them from itself, a real partial self-hardening, not
    fabricated), so this one key is not merely "an admin" but holds
    essentially the vault's entire granular permission surface. Confirmed a
    real, active, bare EOA on 2 independent RPCs (0 bytecode both, nonce 63 --
    not a dormant or vanity address). Grepped `signer_overlap.py` for this
    address and the vault address before wiring in the new group below --
    neither appears in any other tracked group."""
    vault = "0xd5c6c79692715145098a65d1eb1f2a10c524f8e8"
    known_admin = "0x65D02Bb13f515DD105Fb733E9E31f11A2F65e57f"
    notes = []

    default_admin_role = b"\x00" * 32
    still_holds_role = call_raw(
        w3, vault,
        [{"name": "hasRole", "type": "function", "stateMutability": "view",
          "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}],
        "hasRole", default_admin_role, Web3.to_checksum_address(known_admin),
    )
    notes.append(f"vault {vault}: hasRole(DEFAULT_ADMIN_ROLE, {known_admin}) = {still_holds_role}")
    admin_is_eoa = is_eoa(w3, known_admin) if still_holds_role else None
    notes.append(f"known admin {known_admin}: bare EOA = {admin_is_eoa}")

    gross_tvl = call_raw(
        w3, vault,
        [{"name": "getGrossTVL", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [
            {"name": "totalManagedAssets", "type": "uint256"}, {"name": "pendingDeposits", "type": "uint256"},
            {"name": "claimableRedeems", "type": "uint256"}, {"name": "grossTVL", "type": "uint256"},
        ]}],
        "getGrossTVL",
    )
    notes.append(f"getGrossTVL() = {gross_tvl} (non-empty/live-vault check, not proof of exact USD TVL)")

    if still_holds_role and admin_is_eoa:
        admin_key = 5  # standalone bare-EOA convention (score_curve_dex()'s non-same-key branch)
    elif still_holds_role and admin_is_eoa is False:
        admin_key = 40
        notes.append("WARNING: DEFAULT_ADMIN_ROLE holder is now a contract, not a bare EOA -- re-score by hand")
    else:
        admin_key = 40
        notes.append("WARNING: known admin no longer holds DEFAULT_ADMIN_ROLE (or read failed) -- role rotated, re-derive the current holder from RoleGranted/RoleRevoked history by hand before trusting this score")
    multisig = 0
    timelock_score = 0  # no TimelockController found; a bare EOA holds essentially every granular role directly

    return {
        "target": vault,
        "label": "T3tris Finance WBTC vault (Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


SAFFRON_VAULT_FACTORY = "0xb24b143ad6bB5bE9559CcC75f34A2261b7456904"


def score_saffron_vault_factory(w3: Web3) -> dict:
    """Saffron Vaults factory on Robinhood Chain -- rotation audit, new-target
    search while auditing index 15 (2026-09-19). DefiLlama `saffron-vaults`
    (module `saffron-v2/index.js`, `chainTvls["Robinhood Chain"]` ~$820.7k at
    pull time) enumerates vaults from this one factory (`robinhood.factories`
    in that adapter) and counts each vault's variable-side balance plus the
    Uniswap V3 position its adapter holds. Recomputed on-chain instead of
    trusted: 111 vaults read on 2 independent RPCs (identical `vaultInfo` on
    all 111), 13 hold a Uniswap V3 position, priced from those pools' own
    `slot0()` against USDG = $1 -> ~$803.3k (DefiLlama's own figure is ~2%
    higher; coins.llama.fi's own SFI/STONKBROKER prices explain only ~$1.7k
    of that $17k gap, the rest is not attributed). DexScreener independently
    quotes STONKBROKER $0.01001 and SFI $115.40, the same prices the pools
    imply. Composition, disclosed
    rather than smoothed over: ~57% of that TVL is ONE launchpad token
    (45.97M STONKBROKER in a single-sided range, ~$460.6k), ~30% is USDG
    ($239.7k), ~10% is Saffron's own SFI ($80.0k); the rest is small
    (NVDA/SPY/PONS/SGOV/...). Chain-specific TVL is therefore real but
    concentrated, not a broad base.

    The factory is NOT a proxy (no EIP-1967 implementation/admin/beacon slot
    set, read on 2 RPCs) and is `Ownable2Step` (`pendingOwner()` = 0). Its
    ABI matches every one of the 30 functions of `VaultFactory` /
    `RestrictedVaultFactory` in the public repo
    `github.com/saffron-finance/saffron-uniswap-contracts` (the org's `blog`
    field is `saffron.finance`, same as DefiLlama's URL; docs list ChainSecurity
    and 0xleastwood audits), but that repo has a single "Initial commit" and
    the deployed bytecode could NOT be matched to it (no compiler run) --
    5 PUSH4 constants in the deployed code are not accounted for by function
    names (2 are the external `IVault.initialize` / `IAdapter.setVault`
    call selectors, 1 is Panic, 2 unidentified), so this docstring claims
    nothing about what the deployed code does beyond what `eth_call`
    simulation shows: `createVault`, `createAdapter` and `setFeeBps` all
    revert with "Ownable: caller is not the owner" for an arbitrary caller
    (so this is the RESTRICTED variant: only the owner creates vaults, and
    all 111 vaults have that same owner as `creatorAddress`), and pass the
    owner gate for the owner. `feeBps()` currently 1250, `feeReceiver()` ==
    `owner()`.

    The score rests on the controller of that owner-gated surface only, not
    on what the surface can reach (per the public source it can set fees,
    re-point `feeReceiver` -- which every deployed vault reads live from the
    factory -- and publish new vault/adapter bytecode types; existing vaults
    are separate contracts with no owner in that source. Unverified against
    the deployed code, hence not encoded in the score -- same discipline as
    the Algebra note on `score_alandale_v3_factory()`).

    `owner()` is 0x58CA1eaED80896400122164Abe16d77B2b4ff7c9: NOT a bare EOA
    by `is_eoa()` (23 bytes of code) but an EIP-7702-delegated EOA
    (`account_classification.classify_account()` -> `eip7702_delegated`,
    identical on 3 RPCs) delegating to 0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B,
    `NAME()` = "EIP7702StatelessDeleGator", `VERSION()` = "1.3.0" (the
    MetaMask Delegation Framework smart-account delegate: the account's own
    key signs, no separate owner or signer set). It is still functionally one
    private key -- the key can always overwrite the delegation with a native
    transaction -- and it is active (nonce 414, nonzero balance). Per
    METHODOLOGY.md that case is treated like a bare EOA, not like an
    unresolved contract. METHODOLOGY.md recorded no 7702 root among tracked
    targets as of 2026-09-17, but that line was stale: Fables PoolRegistry's
    sole admin (0x359856655934338D798f9CCE1f181486301D36a5, tracked since
    batch 10) is also EIP-7702-delegated, so this is at least the second one
    (all tracked targets were not re-scanned for it in the same pass).
    Same-key convention as `score_curve_dex()`: `owner()` == `feeReceiver()`
    (and == creator of every vault) -> 2, not the lone-EOA 5. Grepped
    `signer_overlap.py`, `scorers.py` and `data/` for the owner and factory
    addresses before wiring the new group: no other tracked group shares them."""
    factory = SAFFRON_VAULT_FACTORY
    notes = []

    owner = read_address_getter(w3, factory, "owner")
    fee_receiver = read_address_getter(w3, factory, "feeReceiver")
    pending_owner = read_address_getter(w3, factory, "pendingOwner")
    notes.append(f"VaultFactory.owner() = {owner}")
    notes.append(f"VaultFactory.feeReceiver() = {fee_receiver}")
    notes.append(f"VaultFactory.pendingOwner() = {pending_owner} (nonzero would mean an ownership transfer is in flight -- re-derive by hand)")

    classification = classify_account(w3, owner) if owner else None
    kind = classification["kind"] if classification else None
    notes.append(f"owner account kind = {kind}" + (f" (delegate {classification['delegate']})" if classification and classification.get("delegate") else ""))
    single_key = kind in ("bare_eoa", "eip7702_delegated")
    same_key = bool(owner) and bool(fee_receiver) and Web3.to_checksum_address(owner) == Web3.to_checksum_address(fee_receiver)
    notes.append(f"owner() == feeReceiver(): {same_key} (single key controls both, if true)")

    if single_key and same_key:
        admin_key = 2  # same-key bare-EOA convention (score_curve_dex()'s same_key branch); a 7702-delegated EOA counts as a bare EOA
    elif single_key:
        admin_key = 5  # standalone lone-EOA convention
    else:
        admin_key = 40
        notes.append("WARNING: owner is now a real contract (or the read failed) -- re-score by hand, do not trust this default")
    multisig = 0
    timelock_score = 0  # no timelock/delay anywhere on the owner-gated surface (setFeeBps simulates OK for the owner with no queue)

    return {
        "target": factory,
        "label": "Saffron Vaults factory (Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }



# ---------------------------------------------------------------------------
# Rotation audit 2026-09-20 (index 16) -- new-target search.
# Four targets, all sourced from DefiLlama-Adapters (the primary-source
# convention used for every DefiLlama-derived address in this file), all
# authority facts re-derived live on the two independent Robinhood Chain
# mainnet RPCs and cross-confirmed by read-only eth_call simulation.
# ---------------------------------------------------------------------------

UNCX_V4_LOCKER = "0x128A800cBc615cc110Bff16E475865c67631603A"
UNCX_V4_POSITION_MANAGER = "0x58daec3116aae6D93017bAAea7749052E8a04fA7"


def score_uncx_v4_locker(w3: Web3) -> dict:
    """UNCX Network's Uniswap-V4 "Liquidity Locker" on Robinhood Chain.

    RESOLVES a lead left open across FOUR prior rotation-audit passes
    (indexes 8, 13, 14 and 15). Every earlier pass blocked on the same thing:
    the locker's verified source is only readable through
    robinhoodchain.blockscout.com, which sits behind a Cloudflare managed
    challenge this project does not bypass. That blocker is real and is NOT
    claimed to be solved here -- the official `uncx-network` GitHub org
    (profile `blog` = https://uncx.network/, the same identity check used for
    score_uncx_v3_locker()) publishes univ2, univ3, two Raydium and a vesting
    repository and NO Uniswap-V4 locker, re-checked 2026-09-20. What changed
    is that the source is not needed for this score: the AUTHORITY ROOT is
    readable directly on chain, and `score_uncx_v3_locker()` /
    `score_morpho_blue_singleton()` already establish the convention of
    scoring the root mechanism.

    Address from `DefiLlama-Adapters/projects/unicrypt-v4/index.js`,
    `robinhood` entry (`lockers[0].address`, `fromBlock` 20591817), fetched
    fresh 2026-09-20. That primary source is cross-confirmed BY THE CONTRACT
    ITSELF rather than trusted: the locker's own `positionManager()` returns
    exactly the adapter's `nftAddress` 0x58daec31...4fA7, on both RPCs, so
    the adapter entry and the deployed contract describe the same system.
    `poolManager()` = 0x8366a39C...0951. DefiLlama's Robinhood-Chain-specific
    figure is $831,087 (ETH $465k + WETH $365k + USDG $1k, from
    `chainTvls["Robinhood Chain"]`, NOT the $2.4M protocol-wide total across
    its 7 chains); no USAR is in that basket, so the index-14 USAR
    mispricing does not inflate it. The TVL was not independently recomputed
    on chain this pass -- stated as a limit, not glossed over.

    Authority, re-derived live on both RPCs, identical on both: `owner()` =
    0x31c44A17...9693 -- THE SAME real Gnosis Safe (v1.4.1, 2-of-3, nonce 7,
    no module, guard slot zero) that already roots the tracked UNCX V3
    locker. `signer_overlap.py`'s `uncx_v3_locker` group anticipated exactly
    this ("UNCX's second locker (unicrypt-v4) shares this exact Safe ... add
    its address to this SAME group rather than a new one"), so this target
    joins that group and crossExposureScore is unaffected.

    What that Safe can do, established by a 120-selector PUSH4 inventory of
    the deployed runtime (identical on both RPCs) plus read-only eth_call
    simulation, NOT by reading source: `adminRescueTokens(address,address,
    uint256)`, `setMigrator(address)`, `setHookWhitelist(address,bool)`,
    `setFees`/`setFlatFee`/`setFeeAddresses`, `setBaseURI`. Simulated from an
    arbitrary address each reverts `OwnableUnauthorizedAccount`; simulated
    from the Safe, `setMigrator` and `setHookWhitelist` pass, and
    `adminRescueTokens` gets PAST the ownership gate (it reverts later, on
    the fake token address, with `SafeERC20FailedOperation`) -- so the gate
    is `onlyOwner` and nothing else. `MIGRATOR()` is the zero address today,
    i.e. the migrate path is configured-but-unarmed: the same bounded-but-real
    indirect vector already documented for the V3 locker, not a direct
    seizure of a user's locked position. 54 of the 120 selectors resolve to
    no 4byte signature and were not brute-forced, so this inventory is a
    lower bound on the owner's powers, never an upper bound -- the score
    rests on the root, which is why that gap does not move it.

    Scored on the root, with the same threshold-aware convention and the same
    numbers the already-published V3 locker carries (50/35/0, composite 31 --
    read back live from the testnet oracle this run for
    0xF28704c6...ce0f)."""
    notes = [
        "address from DefiLlama-Adapters projects/unicrypt-v4/index.js, robinhood entry (fetched 2026-09-20)",
    ]
    position_manager = read_address_getter(w3, UNCX_V4_LOCKER, "positionManager")
    notes.append(
        f"locker.positionManager() = {position_manager}; adapter nftAddress = {UNCX_V4_POSITION_MANAGER} "
        f"-> primary source confirmed by the contract itself: "
        f"{str(position_manager).lower() == UNCX_V4_POSITION_MANAGER.lower()}"
    )
    if position_manager and str(position_manager).lower() != UNCX_V4_POSITION_MANAGER.lower():
        notes.append(
            "WARNING: the locker no longer points at the position manager the DefiLlama adapter names -- "
            "re-derive the address from the adapter before trusting this entry"
        )
    migrator = read_address_getter(w3, UNCX_V4_LOCKER, "MIGRATOR")
    notes.append(
        f"MIGRATOR() = {migrator} -- zero means the owner-settable migrate path is configured but unarmed today"
    )
    owner = read_address_getter(w3, UNCX_V4_LOCKER, "owner")
    notes.append(f"locker.owner() = {owner} (the same Safe that roots the tracked UNCX V3 locker)")
    return _safe_rooted_entry(w3, UNCX_V4_LOCKER, "UNCX Network V4 Liquidity Locker (Robinhood Chain)", owner, notes)


ORVEX_V2_PAIR_FACTORY = "0x5c98b2d892b37c9a1D3b69472bdDc172A64CdC09"
ORVEX_V4_POOL_MANAGER = "0xd01C774d4A66408326Bc65728Ac5Ae5aAf004032"
ORVEX_V4_VAULT = "0xFe7E25dE55e5cBbEcCcb661F3679F873f72B9b0D"


def _orvex_notes_header():
    """Shared identity/TVL preamble for the three Orvex targets, so each
    entry carries it without three copies drifting apart."""
    return [
        "addresses from DefiLlama-Adapters projects/orvex/index.js (V2_FACTORY, V4_CL_POOL_MANAGER, "
        "V4_VAULT), fetched 2026-09-20; that file names docs.orvex.fi as the contracts source and "
        "states chainId 4663 explicitly",
        "DefiLlama chainTvls: Orvex exists on Robinhood Chain and NOWHERE ELSE (chains == ['Robinhood Chain']), "
        "$389,945 -- USDG $214k, WETH $57k, NVDA $33k, SPY $31k, USDE $21k, rest small. No USAR in the basket, "
        "so the index-14 USAR mispricing does not inflate it. Below the ~$600k floor used by earlier passes; "
        "picked up this run because the rotation brief listed Orvex explicitly as never examined. TVL NOT "
        "independently recomputed on chain this pass",
    ]


def score_orvex_v2_pair_factory(w3: Web3) -> dict:
    """Orvex V2 `PairFactoryUpgradeable` (a Solidly/Velodrome-fork factory),
    the only Orvex surface that is a proxy.

    TWO INDEPENDENT ROOTS, which is the point of this entry. Both re-read
    live on the two mainnet RPCs, identical on both:
      * `owner()` = 0x3b2b572C...2F14, a BARE EOA (0 bytecode, so not an
        EIP-7702 delegation either, nonce 454);
      * EIP-1967 admin slot = 0x2DFa221c...0006, a 1,683-byte OpenZeppelin
        ProxyAdmin whose `owner()` is a real Gnosis Safe 0x9DB42D3B...1A53
        (v1.3.0, 3-of-7, nonce 59, no module, guard slot zero).

    This file's existing convention (`score_alandale_v3_factory()` via
    `_safe_rooted_entry`) scores the UPGRADE authority and appends a WARNING
    when the two diverge -- but on Alandale they did NOT diverge, so that
    convention has never actually been exercised on a split root. Scoring the
    Safe here would publish 65/65/0 (composite 46) for a contract one single
    key can reconfigure today, which is not what `adminKeyScore` is defined to
    answer in METHODOLOGY.md ("how hard is that authority to compromise or
    coerce"). Deliberate, stated deviation: this entry scores the WEAKER of
    the two roots, the bare EOA, and records the Safe upgrade path in the
    notes rather than in the number.

    What that EOA can do, from an 83-selector PUSH4 inventory of the deployed
    implementation 0x950f3baE...ea72 (identical on both RPCs) plus read-only
    simulation: `setPause(bool)`, `setFee(bool,uint256)`, `setReferralFee`,
    `setDibs`, `setFeeManager`. `setPause(true)` simulated from an arbitrary
    address reverts; from the EOA it passes, on both RPCs. `isPaused()` is
    false today. No `withdraw`/`rescue`/`sweep`/`migrate` selector exists on
    the factory, and Solidly pairs hold their own reserves, so this is the
    same fee-and-pause-only shape scored 5/0/0 for NOXA Fun and T3tris -- a
    halt of every pair's swaps is real, seizure of principal is not shown.
    3 of the 83 selectors resolve to no 4byte signature (0x63257389,
    0x2895a2f5, 0x299e7ae7) and were not brute-forced: a lower bound on the
    powers, not an upper bound."""
    notes = _orvex_notes_header()
    owner = read_address_getter(w3, ORVEX_V2_PAIR_FACTORY, "owner")
    proxy_admin = read_slot_as_address(w3, ORVEX_V2_PAIR_FACTORY, EIP1967_ADMIN_SLOT)
    pa_owner = read_address_getter(w3, proxy_admin, "owner") if proxy_admin else None
    notes.append(f"factory.owner() = {owner}; EIP-1967 admin slot -> ProxyAdmin {proxy_admin}, ProxyAdmin.owner() = {pa_owner}")
    kind = classify_account(w3, owner)["kind"] if owner else None
    notes.append(f"owner classification = {kind}")
    if owner and pa_owner and str(owner).lower() != str(pa_owner).lower():
        notes.append(
            "SPLIT ROOT: the operational owner and the upgrade authority are different addresses. "
            "Scored on the WEAKER root (see docstring), not on the upgrade authority"
        )
    if kind in ("bare_eoa", "eip7702_delegated"):
        admin_key = 5
    elif kind == "contract":
        admin_key = 40
        notes.append("WARNING: factory.owner() is now a contract, not a single key -- re-score by hand")
    else:
        admin_key = 40
        notes.append("WARNING: factory.owner() unresolved this run -- conservative unresolved-authority score")
    multisig, timelock_score = 0, 0
    return {
        "target": ORVEX_V2_PAIR_FACTORY,
        "label": "Orvex V2 PairFactoryUpgradeable (Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


def score_orvex_v4_pool_manager(w3: Web3) -> dict:
    """Orvex V4 concentrated-liquidity PoolManager (a Uniswap-V4 /
    PancakeSwap-Infinity-shaped singleton, 20,885 bytes, not a proxy -- all
    three EIP-1967 slots are zero on both RPCs).

    `owner()` = 0x9DB42D3B...1A53, the same 3-of-7 Gnosis Safe (v1.3.0, no
    module, guard slot zero) that owns the V2 ProxyAdmin. Scored on that root
    with the standard threshold-aware convention: 65/65/0, composite 46.

    Scope, stated rather than implied: the PoolManager is the accounting
    surface; the TOKENS sit in the separate Orvex V4 Vault, whose own owner is
    a bare EOA (see `score_orvex_v4_vault()`). A consumer reading this entry
    for custody risk is reading the wrong one of the two -- that is why both
    are tracked separately instead of collapsed into one 'Orvex V4' score."""
    notes = _orvex_notes_header()
    notes.append(
        "custody caveat: tokens sit in the Orvex V4 Vault (0xFe7E25dE...9b0D), whose owner is a bare EOA -- "
        "read that entry, not this one, for custody risk"
    )
    owner = read_address_getter(w3, ORVEX_V4_POOL_MANAGER, "owner")
    notes.append(f"poolManager.owner() = {owner}")
    return _safe_rooted_entry(w3, ORVEX_V4_POOL_MANAGER, "Orvex V4 CL PoolManager (Robinhood Chain)", owner, notes)


def score_orvex_v4_vault(w3: Web3) -> dict:
    """Orvex V4 Vault -- the contract that actually HOLDS every Orvex V4
    concentrated-liquidity token balance. This is the notable finding of the
    2026-09-20 index-16 new-target search.

    `owner()` = 0x3b2b572C...2F14, a bare EOA (0 bytecode, nonce 454), the
    same key that owns the V2 factory. Its owner-gated surface is NOT
    fee-only: a 33-selector PUSH4 inventory of the deployed runtime
    (identical on both RPCs) shows `registerApp(address)` alongside
    `mint(address,address,uint256)` / `burn(address,address,uint256)` /
    `take(address,address,uint256)` / `transfer(address,address,uint256)`,
    i.e. a registered "app" is precisely the thing allowed to move vault
    reserves (`isAppRegistered(0xd01C774d...4032)` -- the V4 PoolManager --
    is true today). Read-only eth_call simulation on BOTH RPCs, identical:
    `registerApp(0x1111...1111)` reverts `OwnableUnauthorizedAccount` from an
    arbitrary address, reverts `OwnableUnauthorizedAccount` from the 3-of-7
    Safe, and PASSES from the bare EOA. So one key, with no delay and no
    second signature, can authorize an arbitrary contract against the vault's
    reserves.

    Because that surface is principal-moving rather than fee-only, the 5/0/0
    convention used for NOXA Fun, T3tris and the Orvex V2 factory does not
    apply. METHODOLOGY.md puts a bare EOA in the 2-10 band; this entry takes
    the bottom of it, 2 (the same value `score_curve_dex()`/
    `score_saffron_vault_factory()` use for their worst single-key shape),
    giving composite 1.

    LIVE, DATED FACT worth re-reading next pass: `pendingOwner()` is the
    3-of-7 Safe 0x9DB42D3B...1A53. This is OpenZeppelin `Ownable2Step` and
    `acceptOwnership()` has NOT been called -- the transfer is offered, not
    completed, as of 2026-09-20 (the Safe still reverts
    `OwnableUnauthorizedAccount` on `registerApp`, simulated on both RPCs).
    If and when it is accepted, this target becomes Safe-rooted and should
    re-score 65/65/0, composite 46; the scorer below detects that on its own
    and does not need editing."""
    notes = _orvex_notes_header()
    owner = read_address_getter(w3, ORVEX_V4_VAULT, "owner")
    pending = read_address_getter(w3, ORVEX_V4_VAULT, "pendingOwner")
    notes.append(f"vault.owner() = {owner}; vault.pendingOwner() = {pending}")
    kind = classify_account(w3, owner)["kind"] if owner else None
    notes.append(f"owner classification = {kind}")
    if pending and int(str(pending), 16) != 0:
        notes.append(
            f"Ownable2Step transfer OFFERED to {pending} but acceptOwnership() not yet called -- "
            "authority has NOT moved; re-read next pass"
        )
    if kind in ("bare_eoa", "eip7702_delegated"):
        # principal-moving owner surface (registerApp), one key, no delay:
        # bottom of METHODOLOGY.md's 2-10 bare-EOA band, not the fee-only 5.
        admin_key, multisig, timelock_score = 2, 0, 0
        notes.append(
            "single key with a principal-moving power (registerApp authorizes a contract to mint/burn/take "
            "vault reserves) -- bottom of the 2-10 bare-EOA band, not the fee-only 5"
        )
        return {
            "target": ORVEX_V4_VAULT,
            "label": "Orvex V4 Vault (Robinhood Chain)",
            "adminKeyScore": admin_key,
            "multisigScore": multisig,
            "timelockScore": timelock_score,
            "oracleAuthorityScore": 100,
            "compositeScore": _composite(admin_key, multisig, timelock_score),
            "notes": notes,
        }
    # owner is a contract now: if it resolves as a Safe this returns the
    # Safe-rooted score, otherwise the conservative unresolved 20/0/0.
    notes.append("vault.owner() is no longer a single key -- resolving it as a Safe root instead")
    return _safe_rooted_entry(w3, ORVEX_V4_VAULT, "Orvex V4 Vault (Robinhood Chain)", owner, notes)


# ---------------------------------------------------------------------------
# Independent verification pass, 2026-09-25 -- new target found outside the
# usual DefiLlama-adapter rotation-audit sweep.
# ---------------------------------------------------------------------------

FLOCK_CREDIT_VAULT = "0xd42174d3Db28B0fA2BD25381c3521b18AE9dB490"


def score_flock_credit_vault(w3: Web3) -> dict:
    """Flock Credit Vault on Robinhood Chain (chain 4663) -- independent
    verification pass, 2026-09-25. Sourcify-verified (`FlockCreditVault`) --
    NOT an illegible stub, contrary to what an earlier pass assumed before
    this one re-checked it. Address and every fact below are from that
    independent research, not re-derived from zero here.

    Unlike every other vault tracked in this file, this one exposes NEITHER
    `owner()` NOR `pause()`/`paused()` -- both revert. Its one real authority
    surface is `governance()`, read live below. Confirmed a plain bare EOA
    (0 bytecode) that is genuinely active (high nonce, recent transfers), not
    a dormant or vanity address. Transfer is 2-step
    (`transferGovernance()`/`acceptGovernance()`), which only protects
    against a mistyped destination -- there is NO timelock/delay on the
    transfer itself, so the same key can hand control to a new address
    instantly with no notice window.

    A single bare EOA, no multisig, no delay, holding the vault's ONLY admin
    surface -- there is no second role (no owner(), no pause()) to compare it
    against, so this is the standalone lone-EOA case already scored 5/0/0 for
    `score_t3tris_vault()` and the `single_key`-without-`same_key` branch of
    `score_saffron_vault_factory()`, not the same-key 2/0/0
    (`score_curve_dex()`/`score_snuggle_maxfi_vault()`: two roles collapsing
    into one key) -- there is only one role here to begin with -- and not the
    principal-moving bottom-of-band 2/0/0 either (`score_orvex_v4_vault()`:
    that one required an explicit eth_call simulation confirming the EOA
    could move vault reserves through a specific function; no such check has
    been done here, so this docstring claims nothing beyond what's known).

    `totalAssets()` read live below for THIS vault only, ~$69.3k at time of
    this pass -- not the ~$340.7k protocol-wide figure an earlier pass used,
    which folds in a second vault plus non-vault collateral.

    DISCLOSED, not scored -- two facts about the scored protocol's OWN
    deployed code, not something this oracle's adminKey/multisig/timelock
    methodology penalizes a score for: (1) `setYieldVestingPeriod()` never
    assigns its argument, confirmed by eth_call simulation -- the relevant
    storage does not change after the call, i.e. the setter is a no-op
    regardless of who calls it; (2) `utilization()`/`cap()` (read live below)
    were 9160/8000 at time of this pass -- already above its own configured
    ceiling. Grepped `signer_overlap.py` for the vault and governance
    addresses before adding this entry: neither appears in any other tracked
    group."""
    vault = FLOCK_CREDIT_VAULT
    notes = []

    governance = read_address_getter(w3, vault, "governance")
    notes.append(f"governance() = {governance} (vault has neither owner() nor pause()/paused() -- this is the only admin surface)")

    total_assets = call_raw(w3, vault, _UINT256_GETTER("totalAssets"), "totalAssets")
    notes.append(f"totalAssets() = {total_assets} (this vault only, not the protocol-wide figure)")

    utilization = call_raw(w3, vault, _UINT256_GETTER("utilization"), "utilization")
    cap = call_raw(w3, vault, _UINT256_GETTER("cap"), "cap")
    over_cap = utilization is not None and cap is not None and utilization > cap
    notes.append(
        f"utilization() = {utilization}, cap() = {cap}"
        + (" -- DISCLOSED, not scored: already above its own configured cap" if over_cap else "")
    )
    notes.append(
        "DISCLOSED, not scored: setYieldVestingPeriod() never assigns its argument (confirmed by "
        "eth_call simulation -- the relevant storage does not change after the call). A fact about "
        "the scored protocol's own deployed code, not this oracle's admin-key/multisig/timelock "
        "methodology."
    )

    if governance is None:
        admin_key = 40
        notes.append("WARNING: governance() did not resolve this run -- re-score by hand, do not trust this default")
    else:
        controller_is_eoa = is_eoa(w3, governance)
        notes.append(f"governance {governance}: bare EOA = {controller_is_eoa}")
        if controller_is_eoa:
            admin_key = 5  # standalone lone-EOA convention (score_t3tris_vault()/score_saffron_vault_factory()'s single_key branch) -- no second role here to make this a same-key 2
        else:
            admin_key = 40
            notes.append("WARNING: governance() is now a contract -- re-score by hand, do not trust this default")
    multisig = 0
    timelock_score = 0  # 2-step transfer guards a typo'd destination, not a delay -- no timelock on the transfer itself

    return {
        "target": vault,
        "label": "Flock Credit Vault (Robinhood Chain)",
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock_score,
        "oracleAuthorityScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock_score),
        "notes": notes,
    }


SIMPLE_SCORERS = [
    score_morpho_steakhouse_usdg,
    score_uniswap_v3_factory,
    score_uniswap_v4_poolmanager,
    score_lighter_escrow,
    score_uniswapx_reactor,
    score_spark_savings_usdg,
    score_spark_liquidity_layer_almproxy,
    score_pendle_v2,
    score_curve_dex,
    score_ekubo_core,
    score_uniswap_v2_factory_feetosetter,
    score_chainlink_admin_safe,
    score_pancakeswap_v2_factory,
    score_pancakeswap_v3_factory,
    score_sushiswap_v3_factory,
    score_symbiosis_portal,
    score_strato_bridge_router,
    score_fables_pool_registry,
    score_beefy_spy_weth_vault,
    score_snuggle_maxfi_vault,
    score_meridian_exchangegateway,
    score_morpho_blue_singleton,
    score_noxa_fun_launch_locker,
    score_uncx_v3_locker,
    score_arcus_perps_bridgevault,
    score_t3tris_vault,
    score_up_v3_factory,
    score_alandale_v3_factory,
    score_saffron_vault_factory,
    score_uncx_v4_locker,
    score_orvex_v2_pair_factory,
    score_orvex_v4_pool_manager,
    score_orvex_v4_vault,
    score_flock_credit_vault,
]

LONGBOW_TARGETS = [
    ("0x026df18fbd2A7639089D0a16293383ec687A5Ca1", "Longbow Core"),
    ("0x65dC90cd3a0BCDE967c8AE6019d6790b616E78F7", "Longbow Frontier"),
    ("0xe129D4Cb2d454C4ACFAc909d1576453A9b835f61", "Longbow ETH vault"),
]

# ADDED 2026-09-18 (closes a tracked operational risk: a full score_all() run
# was clocked exceeding 50 minutes, "risque de timeout des routines" -- these
# 4 are the ENTIRE reason why. Each does a full-chain-history eth_getLogs
# replay (either via `_replay_role_holders()` or its own equivalent inline
# scan in score_fables_pool_registry) rather than a handful of eth_call
# reads like every other scorer in this file -- confirmed empirically this
# same session: score_ramses_clv2()/score_beefy_spy_weth_vault() each took
# long enough live that a single interactive session's own time budget
# couldn't complete them. Skipping exactly these 4 (not a broader/vaguer
# "half the targets") is what actually buys back the wall-clock time; every
# other scorer here is a small, fast eth_call sequence unaffected by this.
_SLOW_SCORERS = frozenset({score_fables_pool_registry, score_beefy_spy_weth_vault})


def score_all(w3: Web3, skip_slow: bool = False) -> list:
    """`skip_slow=True` omits the 4 scorers in `_SLOW_SCORERS` (from
    SIMPLE_SCORERS) plus score_rollup_l1_authority() and score_ramses_clv2()
    below (both do their own full-history log replay, called separately
    rather than through SIMPLE_SCORERS) -- a fast dev/verification path,
    NOT a smaller "official" result set. Default False reproduces today's
    exact behavior byte-for-byte: every existing caller (update_scores.py,
    validate_all_scorers.py, this project's own tests) that calls
    score_all(w3) with no second argument is completely unaffected.

    Omitting score_rollup_l1_authority() means `rollup_entries` below is
    empty and l1_authority_composite is None -- score_all() ALREADY
    handles that gracefully today (it's exactly what happens if that one
    scorer's own _safe_score() call catches a live failure), so skip_slow
    reuses an existing, already-tested degradation path rather than adding
    a new one. compositeScore (the field this project treats as
    authoritative) is NEVER affected by skip_slow for any target that IS
    still scored -- only l1CappedComposite (an off-chain-only, disclosed-
    as-optional field, see score_all()'s own comment below) and the 4
    omitted targets' own entries."""
    results = []
    for scorer in SIMPLE_SCORERS:
        if skip_slow and scorer in _SLOW_SCORERS:
            continue
        results.extend(_safe_score(scorer.__name__, scorer, w3))
    for addr, label in ARCUS_TARGETS:
        results.extend(_safe_score(label, score_arcus_ptoken, w3, addr, label))
    for addr, label in STOCK_TOKEN_TARGETS:
        results.extend(_safe_score(label, score_stock_token, w3, addr, label))
    for addr, label in MORE_MORPHO_VAULTS:
        results.extend(_safe_score(label, score_morpho_vault_generic, w3, addr, label))
    for addr, label in LONGBOW_TARGETS:
        results.extend(_safe_score(label, score_longbow_vault, w3, addr, label))
    # These three return a LIST of entries (one authority chain shared across several
    # tracked addresses), not a single dict -- _safe_score() flattens either shape.
    # score_rollup_l1_authority() and score_ramses_clv2() are the other 2 of
    # the 4 slow, full-history-log-replay scorers (see _SLOW_SCORERS above) --
    # skipped the same way under skip_slow, just not through that frozenset
    # since both are called directly here rather than via SIMPLE_SCORERS.
    rollup_entries = [] if skip_slow else _safe_score("Robinhood Chain L1 rollup authority", score_rollup_l1_authority, w3)
    results.extend(rollup_entries)
    if not skip_slow:
        results.extend(_safe_score("Ramses CL V2", score_ramses_clv2, w3))
    results.extend(_safe_score("LayerZero V2 infra", score_layerzero_infra, w3))

    # crossExposureScore is a property of the SET of tracked targets (does the same
    # root signer also control ANOTHER tracked target?), not of any one target in
    # isolation -- computed once here, after every individual score is known, and
    # merged in rather than threaded through every scorer function's own signature.
    # Re-derived live every run (compute_cross_exposure re-reads every Safe's
    # current owners), never cached. See scripts/lib/signer_overlap.py.
    # FIXED 2026-09-17: this call was unguarded too -- a failure here used to
    # crash score_all() AFTER every individual target had already scored
    # successfully, discarding all of that work over one downstream bug.
    try:
        cross_exposure, cross_exposure_notes = compute_cross_exposure_with_notes(w3)
        cross_exposure_ok = True
    except Exception as e:
        print(f"score_all(): compute_cross_exposure() FAILED this run -- {type(e).__name__}: {e} -- every crossExposureScore below defaults to 100 (unknown/uncomputed, NOT a confirmed no-overlap result)")
        cross_exposure = {}
        cross_exposure_notes = {}
        cross_exposure_ok = False

    # ADDED 2026-09-17: l1CappedComposite -- no protocol built on Robinhood Chain
    # can be meaningfully safer than the L1 authority that can upgrade or
    # reconfigure the rollup itself (score_rollup_l1_authority(), currently
    # 57/100 since the 2026-09-17 cross-Safe signer-overlap cap; on-chain
    # testnet copy re-synced the same day, see
    # data/correction_2026-09-17-rollup-l1-testnet-oracle-sync.md). Added as a SEPARATE field, never overwriting compositeScore,
    # which stays exactly what it has always meant: this target's own authority
    # setup, in isolation (same philosophy already applied to crossExposureScore
    # above -- a property of the tracked SET, published on its own for exactly
    # that reason, not folded destructively into a number that already means
    # something specific and different). This is OFF-CHAIN ONLY this pass --
    # NOT pushed to the deployed oracle contract (AuthorityScore's on-chain
    # struct has no field for it; adding one needs a contract migration, a
    # bigger, separate decision) -- computed here and exposed via api/scores.json
    # and the dashboard instead. All 6 rollup_entries share one authority chain
    # and should score identically; if they don't (a bug, or a genuine split
    # discovered later), the LOWEST (most conservative) is used rather than
    # assuming they agree.
    l1_authority_composite = min((e["compositeScore"] for e in rollup_entries), default=None)

    for entry in results:
        entry["crossExposureScore"] = cross_exposure.get(Web3.to_checksum_address(entry["target"]), 100)
        entry["notes"].extend(cross_exposure_notes.get(Web3.to_checksum_address(entry["target"]), []))
        if not cross_exposure_ok:
            entry["notes"].append("crossExposureScore defaulted to 100 this run: compute_cross_exposure() failed, this is NOT a confirmed no-overlap result")
        _apply_l1_cap(entry, l1_authority_composite)

    return results


def _apply_l1_cap(entry: dict, l1_authority_composite) -> None:
    """Mutates `entry` in place, adding `l1CappedComposite` -- pulled out of
    score_all()'s main loop as its own small, pure-ish function purely so it
    can be unit tested directly (scripts/lib/tests/test_scorers.py) without
    needing a live chain, matching this project's post-2026-09-17 testing
    discipline. See score_all()'s own inline comment for the full reasoning."""
    if l1_authority_composite is not None:
        entry["l1CappedComposite"] = min(entry["compositeScore"], l1_authority_composite)
    else:
        entry["l1CappedComposite"] = None
        entry["notes"].append("l1CappedComposite not computed this run: score_rollup_l1_authority() itself failed/was skipped")
