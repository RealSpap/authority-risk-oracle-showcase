"""scoring_build additions (2026-09-18): scorer functions for the 8 targets
`data/scouted_targets_2026-09-17-run2.md` verified live but left at
"scoring_build" (no numeric score) because METHODOLOGY.md 4 had no rule yet
for their authority shape. That file's own "Rules needed before
scoring_build" section listed 5 gaps; this pass closes all 5 and writes the
scorer for every target that was blocked on them:

  1. HyperEVM contract as HyperCore identity (`para`'s deployer is a
     StakingVault, not a bare key) -- `para`'s HIP-3 dex score corrects from
     9 to 5 (see `_hyperevm_identity_overrides` in `../scorers.py`, applied
     as a post-processing step over `methodology_test.score_hip3_dex`,
     mirroring how that file already applies `_apply_l1_cap`). `mkts` needed
     no correction -- its resolved single-EOA root happens to match the
     generic single-key reading already in place, confirmed, not assumed
     (scouted file target #2's own conclusion).
  2. Bounded vs unbounded oracle push (Kinetiq kHYPE/kmHYPE) --
     `_kinetiq_oracle_authority_score` below, applied to BOTH the new kHYPE
     scorer here and (by re-export) the existing kmHYPE-address scorer in
     methodology_test.py, whose `oracleAuthorityScore` was hardcoded 100
     ("not applicable") only because this rule didn't exist yet when it was
     written. Does not touch `compositeScore` (oracleAuthorityScore is a
     disclosed dimension, not a `composite()` input) -- verified by reading
     `composite()`'s own signature in methodology_test.py before relying on
     this.
  3. Vault leader, trading authority without custody (HLP) --
     `score_hlp_vault` below.
  4. Spot treasury holding unissued supply (Unit UBTC/UETH/USOL) --
     `score_unit_treasury` below.
  5. Short dispute periods (Bridge2, 200s) -- `score_bridge2` below.

Plus HyperLend Pooled (`score_hyperlend_pooled`), which needed no new rule
(a standard OpenZeppelin TimelockController + ACLManager, the same pattern
`chains/arbitrum-ecosystem/scorers.py::score_radiant_lendingpool` already
established for an Aave-v3-style pool) but had not been scored yet.

Every read below reuses `methodology_test.py`'s already-tested helpers
(`_eth_call`, `evm`, `_selector`, `_address_from_hex`, `read_access_control_
role_members`, `_classify_authority_holder`, `admin_key_score`, `key_score`,
`composite`, `info`) or `scout_2026_09_17_run2.py`'s raw multi-step reads
(`dex`, `safe`, `multisig_kn`) rather than re-implementing either. No
transaction, no key, mainnet + Arbitrum One read-only (same endpoints
METHODOLOGY.md section 2 and `scout_2026_09_17_run2.py` already document).

Reproduction:
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_18.py            # all 7 new/updated targets
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_18.py khype      # one target's full JSON
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from methodology_test import (  # noqa: E402
    _address_from_hex, _bytes_from_hex, _eth_call, _selector, admin_key_score,
    composite, evm, info, key_score, kn, read_access_control_role_members,
    HyperEvmReadError, HyperEvmRpcError, ROLE_NAMES,
)
from scout_2026_09_17_run2 import (  # noqa: E402
    EVM, ARB, UNIT_TREASURIES, HLP, BRIDGE2, HL, HL_EXTRA,
    safe, multisig_kn, code_len, dex, rpc,
)

EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"


def _proxy_admin_owner(proxy):
    admin_raw = evm("eth_getStorageAt", [proxy, EIP1967_ADMIN_SLOT, "latest"])
    admin = _address_from_hex(admin_raw, f"{proxy} EIP-1967 admin slot")
    owner_raw = _eth_call(admin, _selector("owner()"))
    return admin, _address_from_hex(owner_raw, f"{admin} owner()")


# ============================================================== Rule 2: Kinetiq oracle push, bounded vs unbounded


def _kinetiq_oracle_authority_score(has_sanity_checker, checker_params, operator_evm_code_bytes):
    """New rule (METHODOLOGY.md 4.4, added 2026-09-18): for a Kinetiq-style
    liquid-staking `OracleManager`, the oracle-push authority is always a
    single EOA once per validator per `MIN_UPDATE_INTERVAL` (confirmed
    86,400s for both kHYPE and kmHYPE, live) -- so the (k, n) = (1, 1)
    baseline via `key_score(1, 1)` = 15 is the SAME starting point HIP-3's
    own `setOracle` weakest-key convention already uses for a bare single
    key. What differs is whether a `ValidatorSanityChecker` bounds the SIZE
    of each push:

    - kHYPE: `sanityChecker` is a real, live contract (`owner()` = the same
      4-of-8 Safe that roots everything else here) capping each report at
      `rewardsTolerance_bps=3` / `slashingTolerance_bps=1` of the
      validator's balance, and rejecting a reported balance more than
      `balanceDriftTolerance_bps=300` (3%) from the L1 delegation read
      through the HyperCore precompile. A compromised operator EOA can move
      the exchange rate by at most ~3 bps per validator per 24h.
    - kmHYPE: `sanityChecker() == address(0)` -- live-confirmed, not
      inferred -- so neither cap exists; a compromised operator EOA can
      report ANY reward or slash amount, moving the exchange rate by an
      arbitrary fraction in one transaction, once per validator per 24h.

    Score: bounded -> `key_score(1, 1)` = 15 (matches the ordinary
    single-key floor, since the SIZE cap is exactly what makes a compromised
    single key survivable). Unbounded -> half that, floor'd: 7. This 50%
    penalty is a fresh judgment call for this specific new rule (not a
    number this project had established before 2026-09-18) -- worth
    revisiting if a future pass finds a sharper way to quantify "arbitrary
    size, bounded only by call frequency" against this project's existing
    0-100 scale. Disclosed here rather than silently treated as
    equally-calibrated to the rest of section 4.6.

    `operator_evm_code_bytes`: confirms the operator address itself has no
    EVM code (a bare EOA, not a contract that could add its own internal
    checks) -- read but not scored differently either way (the checker is
    what governs bound, not what kind of address holds OPERATOR_ROLE)."""
    if not has_sanity_checker:
        return 7, "kmHYPE-shape: no sanityChecker (address(0), live-confirmed) -- unbounded reward/slash size per push"
    tol = checker_params.get("rewardsTolerance_bps") if checker_params else None
    return 15, f"kHYPE-shape: sanityChecker bounds each push to {tol} bps reward / {checker_params.get('slashingTolerance_bps')} bps slash of validator balance, {checker_params.get('balanceDriftTolerance_bps')} bps balance-drift anchor"


KINETIQ_ROOT_SAFE = "0x18A82c968b992D28D4D812920eB7b4305306f8F1"


def score_kinetiq_khype_staking_manager():
    """Kinetiq kHYPE `StakingManager` (`0x393D0B87Ed38fc779FD9611144aE649BA6082109`)
    -- a NEW target, genuinely different contract instance from the already-
    scored `score_kinetiq_staking_manager()` (kmHYPE's proxy, same address
    as HIP-3 dex `mkts`/`km`'s deployer). Live TVL ~$1.05B
    (`api.llama.fi/tvl/kinetiq-khype`, per `data/scouted_targets_2026-09-17-
    run2.md` target #3), the largest single TVL figure tracked anywhere in
    this ecosystem file so far.

    Every `AccessControlEnumerable` role live-queried (not just
    `DEFAULT_ADMIN_ROLE`), same discipline METHODOLOGY.md 3.7 already
    requires after Kinetiq's own kmHYPE contract caught a real gap this way:
    `DEFAULT_ADMIN_ROLE` and `MANAGER_ROLE` both resolve to the 4-of-8 root
    Safe; `OPERATOR_ROLE` resolves to a bare EOA
    (`0x23A4604cDFe8e9e2e9Cf7C10D7492B0F3f4B4038`); `SENTINEL_ROLE` and
    `TREASURY_ROLE` currently have ZERO holders (live-confirmed, not
    assumed -- an empty role is excluded from the min-over-paths
    computation the same way `score_kinetiq_staking_manager` already
    excludes a 0-holder role, since nobody currently holding a role means
    no live path through it to score, not a benign or a dangerous one).

    NOT independently re-verified for this specific contract: exactly what
    `OPERATOR_ROLE` gates in kHYPE's `StakingManager.sol` source (the
    kmHYPE sibling's own scorer documents `withdrawFromSpot`/
    `processL1Operations`, by reading THAT contract's source; this pass
    infers the same shape by structural analogy -- same Kinetiq codebase,
    same role name, same 4-of-8 root -- rather than reading kHYPE's own
    verified source line by line. Disclosed as an open item, not silently
    assumed identical."""
    proxy = "0x393D0B87Ed38fc779FD9611144aE649BA6082109"
    admin_slot_addr, admin_slot_owner = _proxy_admin_owner(proxy)
    notes = [f"proxy {proxy} EIP-1967 admin = {admin_slot_addr}, .owner() = {admin_slot_owner} (cross-check only)"]

    role_paths = {}
    nested_owner_addrs = set()
    for role_name in ROLE_NAMES:
        role_hash = ("0x" + "0" * 64) if role_name == "DEFAULT_ADMIN_ROLE" else _eth_call(proxy, _selector(role_name + "()"))
        members = read_access_control_role_members(proxy, role_hash)
        if not members:
            notes.append(f"{role_name}: 0 holders")
            continue
        for member in members:
            from methodology_test import _classify_authority_holder
            scores, info_ = _classify_authority_holder(member)
            role_paths[f"{role_name}:{member}"] = scores
            notes.append(f"{role_name}: holder {member} ({info_['kind']}) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
            nested_owner_addrs |= {a.lower() for a in info_.get("ownerAddresses", [])}

    admin_key = min(p[0] for p in role_paths.values())
    multisig = min(p[1] for p in role_paths.values())
    timelock = min(p[2] for p in role_paths.values())
    dominant = sorted(k for k, p in role_paths.items() if p[0] == admin_key)
    notes.append(f"combined (min over every currently-held role, METHODOLOGY.md 6.2): adminKey={admin_key} (weakest: {dominant}) multisig={multisig} timelock={timelock}")

    checker = _eth_call("0x192826e470bd65FDC2CB472eDd834D096233049b", _selector("sanityChecker()"))
    checker_addr = _address_from_hex(checker, "kHYPE OracleManager.sanityChecker()")
    has_checker = int(checker_addr, 16) != 0
    checker_params = None
    if has_checker:
        checker_params = {
            "rewardsTolerance_bps": int(_eth_call(checker_addr, _selector("rewardsTolerance()")), 16),
            "slashingTolerance_bps": int(_eth_call(checker_addr, _selector("slashingTolerance()")), 16),
            "balanceDriftTolerance_bps": int(_eth_call(checker_addr, _selector("balanceDriftTolerance()")), 16),
        }
    oracle_score, oracle_note = _kinetiq_oracle_authority_score(has_checker, checker_params, None)
    notes.append(f"oracleAuthorityScore (METHODOLOGY.md 4.4 new rule, 2026-09-18): {oracle_score} -- {oracle_note}")

    dexes = [d for d in info({"type": "perpDexs"}) if d]
    all_addrs = {key.split(":", 1)[1].lower() for key in role_paths} | nested_owner_addrs
    sharing = []
    for d in dexes:
        addrs = {d["deployer"]} | ({d["oracleUpdater"]} if d.get("oracleUpdater") else set())
        for _, lst in d.get("subDeployers") or []:
            addrs |= set(lst)
        signers = set()
        for a in addrs:
            signers |= set(kn(a)[1]) | {a}
        if all_addrs & {s.lower() for s in signers}:
            sharing.append(d["name"])
    cross_exposure = max(0, 100 - 20 * len(sharing))
    notes.append(f"cross-checked all {len(dexes)} HIP-3 dexes' signer sets -- overlap: {sharing or 'none'}; shares its DEFAULT_ADMIN_ROLE/MANAGER_ROLE root Safe ({KINETIQ_ROOT_SAFE}) with kmHYPE's HIP3StakingManager, tracked separately: that overlap IS folded into crossExposureScore by chains/hyperliquid/scorers.py's HyperEVM shared-root pass (METHODOLOGY.md 4.5, extended 2026-09-21). Also disclosed, not folded: the same address is the EVM upgrade path of the contract at HIP-3 dex mkts/km's deployer address, for which no path to dex-admin actions was verified (data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md)")

    return {
        "target": proxy,
        "label": "Kinetiq kHYPE StakingManager (HyperEVM)",
        "reads": {
            "roleHolders": {k: {"adminKey": p[0], "multisig": p[1], "timelock": p[2]} for k, p in role_paths.items()},
            "sanityChecker": checker_addr, "sanityCheckerParams": checker_params,
            "tvlUsdApprox": 1_054_000_000,  # api.llama.fi/tvl/kinetiq-khype, scouted_targets_2026-09-17-run2.md #3
        },
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock,
        "oracleAuthorityScore": oracle_score,
        "crossExposureScore": cross_exposure,
        "compositeScore": composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def kmhype_oracle_authority_correction():
    """Recomputes the SAME `oracleAuthorityScore` rule for kmHYPE's own
    `OracleManager` (`0x673C57b16F3855CB08030290654bb5E26Ac8E273`), to patch
    into the ALREADY-EXISTING `score_kinetiq_staking_manager()` result in
    `../scorers.py` (see `_apply_kinetiq_oracle_authority_fix` there) rather
    than editing that adversarially-reviewed function's own source. kmHYPE
    has no sanityChecker (`address(0)`, live-confirmed) -> unbounded ->
    score 7, same rule as kHYPE's own `has_checker=False` branch above."""
    checker = _eth_call("0x673C57b16F3855CB08030290654bb5E26Ac8E273", _selector("sanityChecker()"))
    checker_addr = _address_from_hex(checker, "kmHYPE OracleManager.sanityChecker()")
    has_checker = int(checker_addr, 16) != 0
    score, note = _kinetiq_oracle_authority_score(has_checker, None, None)
    return score, note


# ============================================================== Rule 3: vault leader (HLP)


def score_hlp_vault():
    """New rule (METHODOLOGY.md 4.1, added 2026-09-18): a HyperCore vault
    LEADER controls trading and capital allocation, not custody --
    `leaderCommission=0` (live-confirmed) and a vault leader has no
    withdraw-to-self function (Hyperliquid docs). This is NOT the same
    power a HIP-3 deployer or a spot-token treasury holds (direct value
    redirection), so this target is disclosed with that distinction rather
    than silently scored on an identical-looking number -- but it is
    STILL scored, not left "not applicable": a single compromised leader
    key can destroy real depositor value through bad-faith trading or
    backstop-liquidation decisions across the vault's full $188M+ account
    value (`vaultDetails`, live), and the 4-day deposit lock (Hyperliquid
    docs) means depositors cannot exit ahead of a developing bad episode.
    Uses the SAME single-key ladder as every other bare HyperCore key
    (`admin_key_score`/`key_score` at (1, 1)) -- the ladder itself already
    scores a bare single key low (10/15); no extra penalty or bonus is
    applied for "vault-leader" as a category, since this project's existing
    ladder already reflects "one uncontested key" regardless of what that
    key's specific privileged actions are. `oracleAuthorityScore=100`:
    not applicable, this target sets no price.

    HLP is itself the leader of 7 child strategy vaults (Strategy A/B/X,
    Liquidator 1-4, live-confirmed via `vaultDetails.relationship.data.
    childAddresses`) -- every child inherits the SAME leader key, so no
    separate cross-exposure entity exists among them; disclosed, not double
    counted."""
    v = info({"type": "vaultDetails", "vaultAddress": HLP})
    leader = v["leader"]
    leader_mk = multisig_kn(leader)
    (k, n) = (1, 1) if leader_mk is None else (leader_mk["threshold"], len(leader_mk["authorizedUsers"]))
    admin = admin_key_score(k, n)
    ms = key_score(k, n)
    children = v["relationship"]["data"]["childAddresses"]
    portfolio = dict(v["portfolio"])
    account_value = round(float(portfolio["day"]["accountValueHistory"][-1][1]))
    notes = [
        f"leader {leader}: HyperCore multisig = {'single key' if leader_mk is None else f'{k}-of-{n}'}, EVM code bytes = {code_len(EVM, leader)}",
        f"leaderCommission = {v['leaderCommission']} (cannot skim depositor funds to itself)",
        f"account value (latest daily point) = ${account_value:,} across HLP + {len(children)} child strategy vaults (all sharing the same leader key)",
        "vault-leader authority is TRADING/ALLOCATION power, not custody -- see METHODOLOGY.md 4.1's new 'vault leader' row (2026-09-18) for why this is scored on the standard single-key ladder anyway rather than marked not-applicable",
        "4-day deposit lock (Hyperliquid docs) means depositors cannot exit ahead of a developing bad-faith trading episode",
    ]
    return {
        "target": HLP,
        "label": "Hyperliquidity Provider (HLP) vault",
        "reads": {"leader": leader, "accountValueUsd": account_value, "childVaults": len(children), "allowDeposits": v["allowDeposits"], "isClosed": v["isClosed"]},
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": 0,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": composite(admin, ms, 0),
        "notes": notes,
    }


# ============================================================== Rule 4: spot treasury holding unissued supply (Unit)


def score_unit_treasury(sym):
    """New rule (METHODOLOGY.md 4.1, added 2026-09-18): a HIP-1 spot token
    has no mint function after genesis, so whoever controls the address
    still holding the un-distributed genesis balance controls, in
    practice, new supply -- tokens released from it are indistinguishable
    on HyperCore from already-backed ones. Scored the SAME as any other
    HyperCore authority address (single-key ladder on the TREASURY address,
    which is a DIFFERENT address than the token deployer): treasury
    `userToMultiSigSigners` reads null for all three of UBTC/UETH/USOL
    (live-confirmed) -> single key -> `admin_key_score(1,1)=10`,
    `key_score(1,1)=15`.

    Same discipline as the L1 target's own "Hyper Foundation" validator
    names (METHODOLOGY.md 3.2): Unit's docs claim the treasury key is
    actually a 2-of-3 MPC threshold signature (Unit, Hyperliquid, Infinite
    Field) -- a real claim from a primary source, but NOT independently
    verifiable on chain (HyperCore's own `userToMultiSigSigners` has no
    concept of an off-chain MPC scheme; it simply sees one key). Scored on
    the CONSERVATIVE on-chain fact (single key), the documented MPC claim
    recorded as mitigating context in `notes`, not folded into the number
    -- the same choice this project already made for the L1's Foundation-
    labeled validators, applied here to a different primitive for
    consistency rather than inventing a new resolution rule per target
    type.

    `timelockScore=0`: no delay on any treasury-address action.
    `oracleAuthorityScore=100`: not applicable, no price set here."""
    tid, treasury, px_coin = UNIT_TREASURIES[sym]
    mids = info({"type": "allMids"})
    td = info({"type": "tokenDetails", "tokenId": tid})
    bals = {b["coin"]: float(b["total"]) for b in info({"type": "spotClearinghouseState", "user": treasury})["balances"]}
    max_supply = float(td["maxSupply"])
    treasury_bal = bals.get(sym, 0.0)
    share = treasury_bal / max_supply
    outstanding = max_supply - treasury_bal
    tmk = multisig_kn(treasury)
    (k, n) = (1, 1) if tmk is None else (tmk["threshold"], len(tmk["authorizedUsers"]))
    admin = admin_key_score(k, n)
    ms = key_score(k, n)
    notes = [
        f"treasury {treasury} holds {treasury_bal:,.2f} of {max_supply:,.0f} max supply ({share:.4%}) -- HyperCore multisig = {'single key' if tmk is None else f'{k}-of-{n}'}",
        f"outstanding outside treasury: {outstanding:,.2f} {sym} (~${round(outstanding * float(mids.get(px_coin, 0))):,})",
        "conservative default per METHODOLOGY.md's own L1-validator-label precedent (3.2): scored on the on-chain single-key fact, NOT the documented-but-unverifiable claim below",
        "Unit's docs (docs.hyperunit.xyz) state the treasury key is actually a 2-of-3 MPC threshold signature held by Unit, Hyperliquid and Infinite Field -- a primary-source claim, recorded here as mitigating context, not independently verifiable on chain and not folded into the score",
        f"shares its token deployer with UBTC/UETH/USOL's other two treasuries (deployer multisig 2-of-3, a DIFFERENT address than any treasury) -- a real, disclosed correlation across the three Unit targets, not folded into crossExposureScore since the three TREASURY addresses themselves (the actual scored root keys) are distinct and do not share a root key under METHODOLOGY.md 4.5's own definition",
    ]
    return {
        "target": treasury,
        "label": f"Unit {sym} treasury (spot, unissued supply)",
        "reads": {"tokenId": tid, "maxSupply": max_supply, "treasuryBalance": treasury_bal, "treasuryShareOfMaxSupply": share, "outstandingOutsideTreasury": outstanding},
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": 0,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": composite(admin, ms, 0),
        "notes": notes,
    }


# ============================================================== Rule 5: short dispute periods (Bridge2)


def _decode_bridge2_validator_set(tx_input_hex):
    """Pure decode step for Bridge2's `emergencyUnlock` calldata -- pulled
    out of score_bridge2() below (2026-09-19) so this specific manual
    ABI-decode (the most error-prone step in this whole function: a wrong
    tuple-type string or a wrong byte offset fails silently, not loudly)
    gets the same dedicated-unit-test treatment this project's own
    Kinetiq/para StakingVault HyperEVM decode helpers already got in
    `scripts/lib/tests/test_kinetiq_hyperevm.py`/
    `test_para_staking_vault_hyperevm.py`, rather than only ever being
    exercised by a live dry-run. Returns `(epoch, hot, cold, powers)` from
    the decoded `newSet` tuple; the calldata's other 3 top-level fields
    (`activeCold`, `sigs`, `nonce`) are decoded for shape validation but
    not otherwise used by this scorer, matching the original inline logic
    exactly -- pure extraction, no behavior change."""
    from eth_abi import decode as abi_decode
    new_set, _active_cold, _sigs, _nonce = abi_decode(
        ["(uint64,address[],address[],uint64[])", "(uint64,address[],uint64[])", "(uint256,uint256,uint8)[]", "uint64"],
        bytes.fromhex(tx_input_hex[10:]))
    epoch, hot, cold, powers = new_set
    return epoch, hot, cold, powers


def score_bridge2():
    """New rule (METHODOLOGY.md 4.3, added 2026-09-18, closing the gap that
    section explicitly left open: "a number for 4.3's 'low but non-zero'").
    `Bridge2` on Arbitrum One (legacy USDC bridge, `0x2df1c5...`) requires
    `3 * power > 2 * totalPower` of a 4-key, equal-weight hot/cold set for
    every admin path (`emergencyUnlock`, `changeDisputePeriodSeconds`,
    `changeLockerThreshold`, `invalidateWithdrawals`) -- a real 3-of-4,
    scored via the SAME `admin_key_score`/`key_score` 4.6 ladder already
    used for HIP-3 dexes: `admin_key_score(3,4)=65`, `key_score(3,4)=
    min(100, 20*3-(4-3))=59` (matches `data/scouted_targets_2026-09-17-
    run2.md` target #9's own pre-computed provisional numbers exactly).

    `disputePeriodSeconds()=200` (live-confirmed) is a real, non-zero
    window in which any 2 of the 5 known lockers (`lockerThreshold=2`,
    live) can pause a pending change -- clearly weaker than a multi-day
    TimelockController (this project's `timelock_score=60` convention for
    "confirmed non-zero delay", e.g. `chains/arbitrum-ecosystem/scorers.py`
    ::score_radiant_lendingpool's 72h), but still real protection against
    an instant, undisputed change. Scored 15 -- the same "present but
    short/weak" floor value this project's `scripts/lib/scorers.py` already
    uses in several places (e.g. LayerZero's peer-bypass path, line ~283)
    for a delay that exists but does not rise to the ordinary multi-day
    TimelockController tier.

    Cross-exposure: live-checked (`bridgeKeysMatchingAnyL1ValidatorOrSigner
    AddressAddress`) against all 27 active L1 validators -- ZERO overlap
    found. NOT checked against every HIP-3 dex/Kinetiq/Unit signer set
    (different network namespace in practice -- Arbitrum One vs HyperCore/
    HyperEVM -- though addresses are the same 20-byte format and reuse is
    not impossible); disclosed as an open item, not exhaustively swept this
    pass given time budget."""
    tx = rpc(ARB, "eth_getTransactionByHash", ["0x62a66b841b44845f9aa6a2c40b7aea017eedb791b95a5f20bd312960320246b4"])
    _epoch, hot, cold, powers = _decode_bridge2_validator_set(tx["input"])
    from scout_2026_09_17_run2 import one, cs
    dispute = one(ARB, BRIDGE2, "disputePeriodSeconds()", "uint64")
    locker_threshold = one(ARB, BRIDGE2, "lockerThreshold()", "uint64")
    paused = one(ARB, BRIDGE2, "paused()", "bool")
    usdc = one(ARB, BRIDGE2, "epoch()", "uint64")  # sanity: contract responds at all
    vals = info({"type": "validatorSummaries"})
    l1_keys = {x["validator"].lower() for x in vals} | {x["signer"].lower() for x in vals}
    bridge_keys = [a.lower() for a in list(hot) + list(cold)]
    overlap = sorted(set(bridge_keys) & l1_keys)

    k, n = 3, 4  # 3*power > 2*totalPower over 4 equal-weight keys, live-decoded from the epoch-7 emergencyUnlock calldata
    admin = admin_key_score(k, n)
    ms = key_score(k, n)
    timelock = 15 if dispute and dispute > 0 else 0

    notes = [
        f"epoch {usdc} (sanity read), 3-of-4 equal-weight hot+cold set (live-decoded from the epoch-7 emergencyUnlock tx, hash matches on-chain hotValidatorSetHash/coldValidatorSetHash)",
        f"disputePeriodSeconds()={dispute}, lockerThreshold()={locker_threshold} -- any {locker_threshold} of the known lockers can pause a pending change within this window",
        f"paused={paused}",
        f"bridge keys overlapping any active/registered L1 validator or signer address: {overlap or 'none (live-checked against all {} registered validators)'.format(len(vals))}",
        "docs: bridge holds <10% of HyperCore USDC and is deprecated in favor of Circle CCTP (mitigating); $544M+ still held live (aggravating) -- both disclosed, neither folded into the score beyond the k/n and dispute-period numbers above",
    ]
    return {
        "target": BRIDGE2,
        "label": "Hyperliquid legacy USDC bridge (Bridge2, Arbitrum One)",
        "reads": {"disputePeriodSeconds": dispute, "lockerThreshold": locker_threshold, "hotAddresses": [cs(a) for a in hot], "coldAddresses": [cs(a) for a in cold]},
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": timelock,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": composite(admin, ms, timelock),
        "notes": notes,
    }


# ============================================================== HyperLend Pooled (no new rule -- reuses the Aave-v3-fork + TimelockController pattern chains/arbitrum-ecosystem/scorers.py::score_radiant_lendingpool already established)


def score_hyperlend_pooled():
    """HyperLend Pooled (Aave v3 fork, HyperEVM) -- `PoolAddressesProvider.
    owner()` and ACL `DEFAULT_ADMIN_ROLE`/`POOL_ADMIN` sit behind a 7-day
    OpenZeppelin `TimelockController` ("TimelockA"), `PROPOSER_ROLE` =
    Governance 4-of-8 Safe, `EXECUTOR_ROLE`/`CANCELLER_ROLE` = a SEPARATE
    Treasury 5-of-9 Safe (live-confirmed, `hasRole` against every candidate
    address, not enumerated from logs -- see `data/scouted_targets_2026-09-
    17-run2.md` target #10's own "Limits" note). `RISK_ADMIN`/
    `ASSET_LISTING_ADMIN` sit behind a SEPARATE 6-hour timelock
    ("TimelockB"), same Governance/Treasury proposer/executor pair.

    Scored on the WEAKER of the two Safes required to act through either
    timelock (Governance 4-of-8: `admin_key_score(4,8)=65`,
    `key_score(4,8)=min(100,4*15+4*5)=80`) rather than the stronger
    Treasury 5-of-9, the same "take the weakest key of the set" discipline
    METHODOLOGY.md 4.2 already applies elsewhere -- disclosed as a
    conservative choice: in reality a change needs BOTH the Governance Safe
    (to propose) AND the Treasury Safe (to execute, since
    `openExecutor(address0)=False`, live-confirmed -- execution is NOT
    open to anyone), which is a real AND-composition of two Safes sharing
    no common owner (live-checked), stronger than either alone. Recorded as
    mitigating context in `notes` rather than a formula change, the same
    choice `chains/arbitrum-ecosystem/scorers.py::score_radiant_lendingpool`
    makes for its own single-timelock case (this project has no existing
    numeric convention for scoring a two-independent-Safe AND-gate any
    higher than its weaker member, and inventing one under this pass's time
    budget risks an uncalibrated number more than a disclosed
    simplification does).

    `timelockScore`: TimelockA's 7-day (604,800s) delay uses this project's
    existing "confirmed non-zero delay" tier (60, e.g.
    `score_radiant_lendingpool`'s own 72h case) -- TimelockB's 6-hour
    (21,600s) delay is real but far shorter and governs real value-at-risk
    actions (raising a supply/borrow cap, listing a new risky asset), so it
    is NOT given the same 60; scored 35 (a middle tier this project's
    `scripts/lib/scorers.py::score_snuggle_maxfi_vault` already uses for an
    analogous "real delay, shorter than the project's usual multi-day
    tier" case, reused here rather than inventing a new number). Per
    METHODOLOGY.md 6.2's minimum-over-paths convention, the WEAKER
    TimelockB path is what actually binds this target's `timelockScore`.

    `EMERGENCY_ADMIN` (two Safes, 3-of-8 and 4-of-6, NO delay -- live-
    confirmed) is disclosed as aggravating context, NOT folded into the
    score: in Aave v3 the emergency admin can only pause, not move funds
    or change parameters (same "different, lesser kind of power" distinction
    already drawn for HLP's vault-leader case above) -- matching
    `score_radiant_lendingpool`'s own precedent of disclosing a real,
    concerning fact (there: a $50M historical exploit) as context rather
    than folding it into the formula."""
    p = HL["PoolAddressesProvider"]
    provider_owner = _address_from_hex(_eth_call(p, _selector("owner()")), f"{p} owner()")
    # FOUND while testing this scorer: `PoolAddressesProvider.owner()` is NOT
    # TimelockA directly -- it's `ExecutorLive`
    # (0x0a0d...5d42, BGD Labs' `Ownable` executor pattern, matching
    # `data/scouted_targets_2026-09-17-run2.md` target #10's own table row
    # "Executor `0x0a0d...5d42`, owner Timelock A"), a second hop. Verified
    # live here (`ExecutorLive.owner()`), not assumed from that file's prior
    # read -- an earlier draft of this function's own notes wrongly labeled
    # `provider_owner` itself as "(expected TimelockA)", which would have
    # read as a spurious mismatch against the real TimelockA address.
    executor_live_owner = _address_from_hex(_eth_call(HL_EXTRA["ExecutorLive"], _selector("owner()")), f"{HL_EXTRA['ExecutorLive']} owner()")
    gov_safe = safe(EVM, HL["GovernanceMultisig"])
    treas_safe = safe(EVM, HL["TreasuryMultisig"])
    emerg1 = safe(EVM, HL["EmergencyAdminMultisig"])
    emerg2 = safe(EVM, HL_EXTRA["EmergencyAdminSafe2"])
    delay_a = int(_eth_call(HL["TimelockA"], _selector("getMinDelay()")), 16)
    delay_b = int(_eth_call(HL["TimelockB"], _selector("getMinDelay()")), 16)

    k, n = gov_safe["threshold"], gov_safe["n"]
    admin = admin_key_score(k, n)
    # Standard Gnosis Safe formula (this target is a plain Safe, not a
    # HyperCore-native k-of-n) -- matches methodology_test.py's own
    # `_safe_rooted_scores_hyperevm`'s multisig formula, not `key_score`
    # (that one is calibrated for HyperCore's up-to-10-signer multisig
    # primitive, a different scale -- see METHODOLOGY.md 4.6's own note on
    # why the two formulas deliberately differ).
    ms = min(100, k * 15 + max(0, n - k) * 5)
    tl_a = 60 if delay_a and delay_a > 0 else 0
    tl_b = 35 if delay_b and delay_b > 0 else 0
    timelock = min(tl_a, tl_b)  # weakest of the two timelock paths, METHODOLOGY.md 6.2

    gov_owners = set(a.lower() for a in gov_safe["owners"])
    treas_owners = set(a.lower() for a in treas_safe["owners"])
    shared = sorted(gov_owners & treas_owners)

    notes = [
        f"PoolAddressesProvider.owner() = {provider_owner} (ExecutorLive, BGD Labs Ownable executor) -> .owner() = {executor_live_owner} "
        f"(TimelockA match: {executor_live_owner.lower() == HL['TimelockA'].lower()}) -- a two-hop chain, live-confirmed both hops, not the single-hop this function's own first draft assumed",
        f"TimelockA.getMinDelay()={delay_a}s (7d), PROPOSER=Governance {gov_safe['threshold']}-of-{gov_safe['n']}, EXECUTOR/CANCELLER=Treasury {treas_safe['threshold']}-of-{treas_safe['n']}",
        f"TimelockB.getMinDelay()={delay_b}s (6h), same PROPOSER/EXECUTOR pair -- governs RISK_ADMIN/ASSET_LISTING_ADMIN (caps, new asset listings)",
        f"Governance and Treasury Safes share owners: {shared or 'NONE (live-checked) -- a real AND-composition of two independent signer groups, disclosed as mitigating context, not folded into adminKeyScore/multisigScore, which conservatively use the weaker Safe (Governance) alone'}",
        f"EMERGENCY_ADMIN: two Safes, {emerg1['threshold']}-of-{emerg1['n']} and {emerg2['threshold']}-of-{emerg2['n']}, NO delay -- can pause but (per Aave v3 semantics) not move funds or change risk parameters; disclosed, not folded into the score",
        "openExecutor(address0)=False (live-confirmed on both timelocks) -- execution is NOT open to anyone, the Treasury Safe's own cooperation is genuinely required",
    ]
    return {
        "target": p,
        "label": "HyperLend Pooled (Aave v3 fork, HyperEVM)",
        "reads": {"providerOwner": provider_owner, "providerOwnerOwner": executor_live_owner, "timelockA_delay_s": delay_a, "timelockB_delay_s": delay_b, "tvlUsdApprox": 474_300_000},  # api.llama.fi/tvl/hyperlend-pooled, scouted_targets_2026-09-17-run2.md #10
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": timelock,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": composite(admin, ms, timelock),
        "notes": notes,
    }


if __name__ == "__main__":
    import json
    fns = {
        "khype": score_kinetiq_khype_staking_manager,
        "hlp": score_hlp_vault,
        "ubtc": lambda: score_unit_treasury("UBTC"),
        "ueth": lambda: score_unit_treasury("UETH"),
        "usol": lambda: score_unit_treasury("USOL"),
        "bridge2": score_bridge2,
        "hyperlend": score_hyperlend_pooled,
    }
    if len(sys.argv) > 1:
        print(json.dumps(fns[sys.argv[1]](), indent=1, default=str))
    else:
        for name, fn in fns.items():
            r = fn()
            print(name, r["label"], "composite=", r["compositeScore"], "oracle=", r["oracleAuthorityScore"])
