"""
Hyperliquid authority scorers -- 15 targets (2026-09-17, io, para, mkts,
Kinetiq's HIP3StakingManager, and para's own StakingVault all added same
day as follow-ups to the first pass; Ventuals vHYPE staking added
2026-09-18 as a further follow-up; 7 MORE targets added 2026-09-18 in the
scoring_build pass -- Kinetiq kHYPE StakingManager, the HLP vault, Unit
UBTC/UETH/USOL treasuries, the legacy Bridge2 USDC bridge, and HyperLend
Pooled -- plus a correction to `para`'s own score and to the existing
Kinetiq HIP3StakingManager scorer's oracleAuthorityScore; see
`scripts/scoring_build_2026_09_18.py` and `data/scored_targets_2026-09-18-
scoring-build.md` for the full derivation of everything added or changed
that day).

Promotes `METHODOLOGY.md` section 4 (including the 4.6 numeric mapping and
4.7 target-identifier rules added by the methodology test) into the same
`scorers.py` / `score_all()` shape every other ecosystem in this project
uses. The underlying read-and-score logic already existed, fully working
and already live-tested, in `scripts/methodology_test.py`
(`score_hip3_dex()`, `score_l1()`) -- this file imports it directly rather
than duplicating it (the same "one canonical copy" discipline already
applied this pass to `_retrying()`/`safe_score()` on the EVM side and to
`sol_read.py`'s decoders on the Solana side), and adds:
  - the `score_all()` / per-target-isolation shape this project's other
    ecosystem files share,
  - the `l1CappedComposite` field METHODOLOGY.md section 4.5 specifies
    ("notes carries l1CappedComposite = min(compositeScore, L1
    compositeScore)") but `methodology_test.py` did not yet compute.

Every number is derived live from the official Hyperliquid info API and
HyperEVM RPC on each run -- see `data/methodology_test_2026-09-16.md` for
the hand-verified reference values this file's `xyz`/L1 output is checked
against (xyz HIP-3 dex 10/15/0/4/100/9, L1 15/65/0/40/100/26).

Which HIP-3 dex to add second was checked live rather than picked from
METHODOLOGY.md 4.2's k-of-n table alone (that table orders dexes by listed
asset count, not real usage): a live open-interest sweep across all 10
existing dexes on 2026-09-17 found `flx` (15 listed assets, the second
entry in that table) has ZERO open interest and near-zero net deposit --
essentially dormant despite its listed markets -- while `io` (only 10
listed assets) carries real economic weight, ~$55.4M open interest and
~$39.5M net deposit. `io` was promoted instead of `flx` for the same reason
this project's Ethereum L1 scorer declined to promote fUSD/aBTC as
flagship targets despite a real admin-key finding attached to them: listed
market count alone doesn't establish a target is real and used.

A second same-day sweep re-checked the remaining 7 (flx, vntl, hyna, km,
abcd, cash, mkts) plus discovered an 8th, `para`, launched since the first
pass and not in that original list at all. Result: flx/vntl/hyna/km/abcd/
cash are ALL still at exactly zero open interest (genuinely dormant, not a
stale reading -- re-verified fresh, not assumed from the first pass), while
BOTH `para` (~$15.1M open interest, ~$10.5M net deposit, 35 listed assets,
third-most-used after xyz's ~$3.9B and io's ~$56M) and `mkts` (~$6.7M open
interest, the closest runner-up) carry real economic weight and were both
promoted the same pass. `mkts` shares its root deployer key with `km`
(still dormant) -- a real, live-detected cross-exposure finding, not a
coincidence of similar addresses.

A genuinely new finding surfaced while promoting these two: unlike xyz/io,
BOTH `para`'s and `mkts`/`km`'s deployer addresses carry live HyperEVM
bytecode (EIP-1967 proxies) -- `mkts`/`km`'s resolves, two hops deep, to a
real 4-of-8 Gnosis Safe. NOT folded into either score (whether this
EVM-side authority has any bearing on the underlying HyperCore-native
market is unresolved, not assumed) -- see `data/finding_2026-09-17-
hyperliquid-hip3-evm-proxy-authority.md` for the full, independently
verified derivation and what remains open.

6 dexes remain unpromoted (flx, vntl, hyna, km, abcd, cash -- all
re-confirmed at exactly zero open interest this pass), each scoutable the
same way with `score_hip3_dex(name)` if a future sweep finds real usage.

stHYPE liquid staking (`score_sthype_liquid_staking`, `methodology_test.py`)
added 2026-09-25: a FOURTH HyperEVM-native target, `0xffaa4a3d97fe9107cef8
a3f48c069f577ff76cc1` (NOT `0x94e8396e0869c9f2200760af0621afd240e1cf38`,
which is `wstHYPE`, an ERC-4626 wrapper around it -- a same-day mislabel
caught before this scorer was written). `defaultAdmin()` and `REBASER_ROLE`
(held by an intermediary "Overseer V1" controller contract whose own
`owner()` was checked live) both resolve to the SAME 4-of-6 Gnosis Safe,
live-checked for signer overlap against Kinetiq's/HyperLend's/para's own
root Safes (none found -- see the scorer's own docstring). CORRECTED before
being written at all: today's proposed multisigScore=78/compositeScore=49
read `key_score(4,6)` off METHODOLOGY.md 4.6's HyperCore-multisig example
table, the wrong ladder for a REAL on-chain Gnosis Safe -- this project's
own `_safe_rooted_scores_hyperevm` (already used by every other Safe-rooted
HyperEVM target here, and the one `score_hyperlend_pooled`'s own docstring
names for exactly this case) gives multisigScore=70, compositeScore=47
instead; full derivation in the scorer's own docstring.

HIP-4 outcome-market deployers (`out`, `txyz`, `skew`, live on mainnet, found
2026-09-19) were sized and given a scorer the same day --
`score_hip4_outcome_deployer(venue)` in `scripts/scoring_build_2026_09_19_hip4.py`,
generic in the same way `score_hip3_dex(name)` is -- and are deliberately NOT
in SIMPLE_SCORERS: their locked collateral ($1.19M / $0.40M / $8K, about
$1.17M / $0.40M / $8K when re-read at 20:07 UTC) is below the only number this
repo has written for this ecosystem's real-usage bar (the scouting selection rule
of "about $5M" of TVL or open interest in `data/scouted_targets_2026-09-17-run2.md`,
a scouting rule, not a promotion rule) and below the lightest promoted dex
(`mkts`: about $6.4M to $6.7M of open interest when promoted on 2026-09-17, two
same-day readings; $7.7M when re-read on 2026-09-19). The upper bound for `out`,
counting every outstanding Yes and No share as 1 USDC, is $2.84M, also below.
Whether that written number applies to HIP-4 collateral, or an outcome-specific
floor should replace it (`out` would clear one at about $600K or below), is a
calibration decision for the reviewers or the maintainer, not made here.
Sizing, decision and the sensitivity that would flip `out`:
`data/scored_targets_2026-09-19-hip4-outcome-deployers.md`."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
# scripts/lib is appended (never first: it has its own scorers.py); the guard is installed before methodology_test decodes anything
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
import abi_returndata_guard  # noqa: E402
abi_returndata_guard.ensure_installed("raise")
from methodology_test import score_hip3_dex, score_l1, score_kinetiq_staking_manager, score_para_staking_vault, score_ventuals_vhype_staking, score_sthype_liquid_staking, admin_key_score, key_score, composite as _mt_composite  # noqa: E402
from scoring_build_2026_09_18 import (  # noqa: E402
    score_kinetiq_khype_staking_manager, score_hlp_vault, score_unit_treasury,
    score_bridge2, score_hyperlend_pooled, kmhype_oracle_authority_correction,
)


# ---------------------------------------------------------------- scoring_build 2026-09-18 corrections
#
# Two post-processing corrections applied here rather than inside
# methodology_test.py's own (already adversarially-reviewed, previously
# committed) functions -- same architectural choice this file already makes
# for `_apply_l1_cap` below: a cross-cutting fix lives at the scorers.py
# layer, visible and auditable as its own step, rather than mutating a
# tested function's internals.

# Rule (METHODOLOGY.md 4.1, "HyperEVM contract as HyperCore identity", added
# 2026-09-18; see scripts/scoring_build_2026_09_18.py's own module
# docstring for the full derivation): `para`'s HIP-3 dex deployer is not a
# bare HyperCore key -- `userToMultiSigSigners` reads null only because the
# address is a HyperEVM StakingVault contract, and its real CoreWriter
# action-9 (addApiWallet) authority is gated by OPERATOR_ROLE, a Safe with
# threshold=1 and 3 owners (live-confirmed 2026-09-18) -- a genuine (k=1,
# n=3), weaker than the "single key" (1,1) the generic reading assumes.
# `mkts` needed NO analogous override: its own resolved single-EOA root
# (exWalletAdmin) happens to match the generic single-key reading already
# in place -- confirmed, not assumed, by `data/scouted_targets_2026-09-17-
# run2.md` target #2 -- so it is deliberately left out of this dict.
_HYPEREVM_IDENTITY_OVERRIDES = {
    "para": (1, 3),
}


def _apply_hyperevm_identity_overrides(entries: list) -> None:
    for e in entries:
        for dex_name, (k, n) in _HYPEREVM_IDENTITY_OVERRIDES.items():
            if e.get("label") == f"HIP-3 dex {dex_name}":
                old_admin, old_ms, old_oracle, old_composite = e["adminKeyScore"], e["multisigScore"], e["oracleAuthorityScore"], e["compositeScore"]
                e["adminKeyScore"] = admin_key_score(k, n)
                e["multisigScore"] = key_score(k, n)
                # oracleAuthorityScore: para's oracleUpdater field is empty,
                # so the deployer IS the oracle updater (METHODOLOGY.md 4.2
                # rule 3) -- same resolved (k, n) applies to both dimensions.
                e["oracleAuthorityScore"] = key_score(k, n)
                e["compositeScore"] = _mt_composite(e["adminKeyScore"], e["multisigScore"], e["timelockScore"])
                e.setdefault("notes", []).append(
                    f"CORRECTED (METHODOLOGY.md 4.1 'HyperEVM contract as HyperCore identity', 2026-09-18): "
                    f"deployer carries HyperEVM bytecode (a StakingVault UUPS proxy); its real addApiWallet authority "
                    f"is OPERATOR_ROLE, Safe threshold=1 over 3 owners (2 bare EOAs + a nested 1-of-1 Safe, itself no "
                    f"stronger than a bare key) -- a genuine (k=1, n=3), weaker than the generic 'null multisig -> "
                    f"single key (1,1)' reading. adminKeyScore {old_admin}->{e['adminKeyScore']}, multisigScore "
                    f"{old_ms}->{e['multisigScore']}, oracleAuthorityScore {old_oracle}->{e['oracleAuthorityScore']}, "
                    f"compositeScore {old_composite}->{e['compositeScore']}. See data/scouted_targets_2026-09-17-"
                    f"run2.md target #1 and scripts/scoring_build_2026_09_18.py for the live derivation."
                )


def _apply_kinetiq_oracle_authority_fix(entries: list) -> None:
    """Rule (METHODOLOGY.md 4.4, added 2026-09-18): the existing Kinetiq
    HIP3StakingManager scorer (kmHYPE's proxy) hardcoded
    `oracleAuthorityScore=100` ("not applicable") only because this rule
    didn't exist when it was written -- kmHYPE's OracleManager genuinely IS
    an oracle-push authority (a single EOA, unbounded -- no sanityChecker,
    live-confirmed). Does not touch compositeScore (oracleAuthorityScore is
    not a `composite()` input, verified against methodology_test.py's own
    `composite()` signature before relying on this)."""
    for e in entries:
        if e.get("label") == "Kinetiq HIP3StakingManager (HyperEVM)":
            old = e["oracleAuthorityScore"]
            score, note = kmhype_oracle_authority_correction()
            e["oracleAuthorityScore"] = score
            e.setdefault("notes", []).append(
                f"CORRECTED (METHODOLOGY.md 4.4 'bounded vs unbounded operator push', 2026-09-18): "
                f"oracleAuthorityScore {old}->{score} (was hardcoded 'not applicable' before this rule existed) -- {note}"
            )


# The role names whose holders ARE a HyperEVM target's root authority: an AccessControl DEFAULT_ADMIN_ROLE (Kinetiq) or a
# RoleRegistry owner (para, Ventuals). Keys of `reads["roleHolders"]` look like "DEFAULT_ADMIN_ROLE:0xabc...".
_HYPEREVM_ROOT_ROLES = ("DEFAULT_ADMIN_ROLE", "RoleRegistry.owner()")


def _hyperevm_root_holders(entry: dict) -> set:
    holders = (entry.get("reads") or {}).get("roleHolders") or {}
    return {key.rsplit(":", 1)[1].lower() for key in holders if key.rsplit(":", 1)[0] in _HYPEREVM_ROOT_ROLES}


def _apply_hyperevm_shared_root_exposure(entries: list) -> None:
    """crossExposureScore for HyperEVM targets that share a root holder with ANOTHER tracked target (METHODOLOGY.md 4.5,
    extended 2026-09-21).

    4.5 was written over HyperCore-native root keys, so Kinetiq's kHYPE StakingManager and its kmHYPE HIP3StakingManager, both
    rooted in the same 4-of-8 Safe (DEFAULT_ADMIN_ROLE and MANAGER_ROLE on each, read live), each scored 100 even though their
    own notes said the Safe roots both. The field means "does this target's root authority also control another tracked
    target", and a HyperEVM Safe is a root authority like any other. So: `100 - 20 * (number of OTHER tracked targets sharing a
    root holder)`, combined with min() so it can never raise a value a scorer already lowered.

    Only root roles are compared (DEFAULT_ADMIN_ROLE, RoleRegistry.owner()), not operational ones, and only holders that
    appear on BOTH targets. Not counted: HIP-3 dex `mkts`/`km`, whose deployer address is the same address as the
    HIP3StakingManager proxy: data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md's corrected conclusion found no
    verified path from that contract to dex-admin actions, so it is disclosed, not folded. Does not touch compositeScore."""
    roots = {id(e): _hyperevm_root_holders(e) for e in entries}
    for e in entries:
        mine = roots[id(e)]
        if not mine:
            continue
        sharing = [o for o in entries if o is not e and mine & roots[id(o)]]
        if not sharing:
            continue
        folded = max(0, 100 - 20 * len(sharing))
        old = e.get("crossExposureScore", 100)
        e["crossExposureScore"] = min(old, folded)
        e.setdefault("notes", []).append(
            f"crossExposureScore {e['crossExposureScore']} (was {old}): its root holder(s) {sorted(mine & set().union(*(roots[id(o)] for o in sharing)))} also "
            f"hold the root role of {len(sharing)} other tracked target(s): {[o['label'] for o in sharing]} "
            f"(METHODOLOGY.md 4.5, extended 2026-09-21 to HyperEVM root holders)"
        )


def _apply_l1_cap(entry: dict, l1_composite):
    """Same semantics as scripts/lib/scorers.py's `_apply_l1_cap` for
    Robinhood Chain: a SEPARATE field, never overwrites compositeScore
    (repo semantics per METHODOLOGY.md 4.5). Degrades to None + a note if
    the L1 composite itself could not be read this run."""
    if l1_composite is None:
        entry["l1CappedComposite"] = None
        entry.setdefault("notes", []).append("l1CappedComposite not computed this run -- Hyperliquid L1 score unavailable")
        return entry
    entry["l1CappedComposite"] = min(entry["compositeScore"], l1_composite)
    return entry


def score_xyz_dex(_unused_arg=None) -> dict:
    # Thin wrapper so this reads like every other ecosystem's SIMPLE_SCORERS
    # entries (one no-arg callable per target) even though the underlying
    # function is parameterized by dex name for reuse against other dexes later.
    return score_hip3_dex("xyz")


def score_io_dex(_unused_arg=None) -> dict:
    # ADDED 2026-09-17 (same day as xyz, as a follow-up): second-most-used
    # HIP-3 dex by real open interest (~$55.4M), not by listed asset count
    # -- see this module's own docstring for why `io` was picked over `flx`.
    # Structurally interesting in its own right: unlike xyz (where a
    # single-key haltTrading sub-deployer is the binding constraint), io's
    # weakest oracle-authority path is the DEPLOYER ITSELF (3-of-5) -- its
    # 4-of-6 oracleUpdater is actually the stronger key, but rule 4.2.3
    # keeps the deployer in the oracle set regardless (it can reassign
    # sub-deployers at any time and so reach setOracle anyway), so the
    # deployer's own weaker threshold is what actually binds.
    return score_hip3_dex("io")


def score_mkts_dex(_unused_arg=None) -> dict:
    # ADDED 2026-09-17, a same-day third follow-up: the closest real
    # runner-up after `para` in the same sweep (~$6.7M open interest,
    # ~$5.2M net deposit across 24 listed assets). Shares its ROOT
    # deployer key with `km` (still dormant, $0 open interest) --
    # `dexesSharingARootKey` (already computed by score_hip3_dex) confirms
    # this live, crossExposureScore=80. A real, differentiated story: the
    # same single key that controls a genuinely dormant market ALSO
    # controls a real, actively-traded one -- a compromise of that one key
    # is not a "small dex" problem.
    #
    # Also the dex that surfaced a genuinely new finding: unlike xyz/io,
    # this deployer address ALSO carries live HyperEVM bytecode (an
    # EIP-1967 proxy) whose admin resolves, two hops deep, to a real
    # 4-of-8 Gnosis Safe. Chased the obvious follow-up question (does this
    # EVM-side authority actually reach the HyperCore-native market?)
    # through two rounds: Hyperliquid's own CoreWriter docs confirm a
    # calling contract's OWN address becomes the HyperCore identity for
    # the resulting action, which first read as strong evidence for a real
    # second root-control path -- but reading the implementation's actual
    # VERIFIED SOURCE (not just noting its bytecode contains the CoreWriter
    # address) corrected that: it is Kinetiq's own `HIP3StakingManager`
    # (a kmHYPE liquid-staking contract -- CORRECTED 2026-09-19, this
    # comment said kHYPE; see METHODOLOGY.md's 2026-09-18 changelog and
    # data/finding_2026-09-19-hyperliquid-khype-kmhype-identity.md), and
    # every CoreWriter call it makes
    # is a staking/trading helper, not a dex-admin action. Not folded into
    # this score either way -- and even under the stronger, since-corrected
    # reading, it could not have lowered the score: the single HyperCore-
    # native key already scores adminKeyScore=10, near the floor, so the
    # minimum-over-full-power-paths convention (METHODOLOGY.md 6.2) means
    # nothing found here could ever push the composite down. Full
    # derivation, including the correction: data/finding_2026-09-17-
    # hyperliquid-hip3-evm-proxy-authority.md.
    return score_hip3_dex("mkts")


def score_para_dex(_unused_arg=None) -> dict:
    # ADDED 2026-09-17, a same-day second follow-up: a fresh open-interest
    # sweep across the 7 HIP-3 dexes this module's own docstring had left
    # unpromoted (flx, vntl, hyna, km, abcd, cash, mkts) found a NEW dex,
    # `para` (not listed in that original 7 -- launched since the last
    # scouting pass), plus reconfirmed flx/vntl/hyna/km/abcd/cash are ALL
    # still at exactly zero open interest (genuinely dormant, not a stale
    # reading). `para`: 35 listed assets, ~$15.1M open interest, ~$10.5M
    # total net deposit -- real economic weight, third-most-used HIP-3 dex
    # after xyz (~$3.9B) and io (~$56M), ahead of `mkts` (~$6.7M OI,
    # promoted the same day, see score_mkts_dex). Structurally the weakest
    # root-control key found on ANY Hyperliquid target so far: the
    # deployer is a bare single key (k=1, n=1, adminKeyScore=10) -- unlike
    # xyz (single key too, but $3.9B behind it) and io (3-of-5), and its
    # own `dexesSharingARootKey` check (already built into score_hip3_dex)
    # confirms this key is not reused across any other tracked HIP-3 dex,
    # despite superficially similar vanity "0x8888888..." prefixes on a
    # few other deployer addresses.
    #
    # Also has live HyperEVM bytecode at its deployer address (an EIP-1967
    # proxy) -- unlike xyz/io, which have none.
    #
    # CORRECTED 2026-09-17 (same day, before this was ever published):
    # an earlier version of this comment said para's EIP-1967 admin slot
    # "reads as zero (consistent with an immutable, non-upgradeable
    # proxy)" -- wrong. This is a UUPS proxy (OpenZeppelin
    # UUPSUpgradeable), which never uses the EIP-1967 ADMIN slot at all
    # (only a transparent proxy does) -- reading zero there was never
    # evidence of "no admin," only of "not a transparent proxy." Reading
    # the implementation's actual verified source found a real upgrade
    # authority (an external RoleRegistry contract's owner()) and a real
    # product behind it: a StakingVault managing ~$41.7M in delegated
    # HYPE. Promoted as its own separate target, `score_para_staking_
    # vault` below -- not folded into para's own dex score (same
    # reasoning as Kinetiq/mkts: this is a different product sharing an
    # address, not a second root-control path over the perp market
    # itself). Full derivation: data/finding_2026-09-17-hyperliquid-hip3-
    # evm-proxy-authority.md.
    return score_hip3_dex("para")


# score_para_staking_vault (imported below, added directly to
# SIMPLE_SCORERS with no wrapper, matching score_kinetiq_staking_manager's
# own precedent) closes this project's own open question about para's
# EVM-side proxy by reading its actual verified source rather than
# stopping at "admin slot reads zero." Real product (~$41.7M in delegated
# HYPE, contract name `StakingVault`), real authority chain
# (RoleRegistry.owner() plus two operational roles), scored via the same
# minimum-over-full-power-paths convention Kinetiq's promotion already
# established for HyperEVM targets. compositeScore=4 (CRITICAL): the
# MANAGER_ROLE holder -- the one role that can actually move the vault's
# funds -- is a standard, verifiable EIP-1967 proxy delegating to an
# IMPLEMENTATION with no verified source on hyperevmscan.io, which this
# project's existing conservative-fallback convention scores as the
# binding constraint rather than assumed benign. Full derivation: chains/
# hyperliquid/data/methodology_test_2026-09-17-para-staking-vault.md.

# score_ventuals_vhype_staking (added 2026-09-18): a THIRD HyperEVM
# target, found while chasing a "Similar Match" contract next to para
# StakingVault's own implementation -- that specific lead was a dead end,
# but sweeping every HIP-3 dex's deployer for its OWN EIP-1967
# implementation slot (not just eth_getCode) found still-dormant dex
# `vntl` also carries a real, NAMED product: Ventuals vHYPE, a
# liquid-staking token (~$610K in delegated HYPE). Unlike para's
# analogous case, EVERY authority path here -- including the MANAGER_ROLE
# holder, a verified StakingVaultManager contract whose gating was
# actually READ, not assumed -- resolves to the IDENTICAL 2-of-3 Gnosis
# Safe. compositeScore=31, l1CappedComposite=min(31,26)=26 -- the L1 cap
# actually binds here. Full derivation: chains/hyperliquid/data/
# methodology_test_2026-09-18-ventuals-vhype-staking.md.


# ---------------------------------------------------------------- scoring_build 2026-09-18 additions
#
# 7 new targets, all verified live at 3/3 in data/scouted_targets_2026-09-
# 17-run2.md and blocked there on a METHODOLOGY.md rule that didn't exist
# yet (see that module's own docstring for the 5 rules closed). Thin
# wrappers only where score_unit_treasury needs a symbol argument -- the
# other 5 functions are added directly, matching score_para_staking_vault's
# own no-wrapper precedent above.

def score_unit_ubtc(_unused_arg=None) -> dict:
    return score_unit_treasury("UBTC")


def score_unit_ueth(_unused_arg=None) -> dict:
    return score_unit_treasury("UETH")


def score_unit_usol(_unused_arg=None) -> dict:
    return score_unit_treasury("USOL")


SIMPLE_SCORERS = [
    score_l1,
    score_xyz_dex,
    score_io_dex,
    score_para_dex,
    score_mkts_dex,
    score_kinetiq_staking_manager,
    score_para_staking_vault,
    score_ventuals_vhype_staking,
    score_sthype_liquid_staking,
    # scoring_build additions, 2026-09-18:
    score_kinetiq_khype_staking_manager,
    score_hlp_vault,
    score_unit_ubtc,
    score_unit_ueth,
    score_unit_usol,
    score_bridge2,
    score_hyperlend_pooled,
]


def score_all(_url_unused=None) -> list:
    # Signature matches every other ecosystem's score_all(url) for the
    # update_scores.py harness's sake, even though Hyperliquid's reads are
    # fixed official endpoints (see methodology_test.py), not a caller-
    # supplied RPC URL -- accepted and ignored rather than special-cased
    # by the caller.
    results = []
    for scorer in SIMPLE_SCORERS:
        try:
            result = scorer()
            results.extend(result if isinstance(result, list) else [result])
        except Exception as e:
            print(f"score_all(): SKIPPED {scorer.__name__} this run -- {type(e).__name__}: {e}")

    # scoring_build 2026-09-18 corrections, same try/except-disclose-don't-
    # crash convention as the L1-cap step below: a correction failing to
    # apply should degrade to "uncorrected, disclosed" for that one run, not
    # discard every already-computed result.
    try:
        _apply_hyperevm_identity_overrides(results)
    except Exception as e:
        print(f"score_all(): HyperEVM-identity override FAILED this run -- {type(e).__name__}: {e} -- returning para's uncorrected generic score")
    try:
        _apply_kinetiq_oracle_authority_fix(results)
    except Exception as e:
        print(f"score_all(): Kinetiq oracle-authority fix FAILED this run -- {type(e).__name__}: {e} -- returning oracleAuthorityScore=100 (uncorrected) for Kinetiq HIP3StakingManager")

    try:
        _apply_hyperevm_shared_root_exposure(results)
    except Exception as e:
        print(f"score_all(): HyperEVM shared-root exposure FAILED this run -- {type(e).__name__}: {e} -- returning crossExposureScore uncorrected")

    # FIXED 2026-09-17 (closed a bug hunt finding): this block ran outside
    # the try/except above, so a malformed entry (e.g. missing "label")
    # crashed score_all() AFTER every scorer had already run successfully,
    # discarding every already-computed result for the run instead of just
    # skipping the l1-cap step -- the exact "unguarded post-loop step
    # discards good work" bug this project already fixed the same day in
    # scripts/lib/scorers.py's cross-exposure step.
    try:
        l1_entry = next((r for r in results if r["label"].startswith("Hyperliquid L1")), None)
        l1_composite = l1_entry["compositeScore"] if l1_entry else None
        for r in results:
            if r is l1_entry:
                continue
            _apply_l1_cap(r, l1_composite)
    except Exception as e:
        print(f"score_all(): l1 cap application FAILED this run -- {type(e).__name__}: {e} -- returning results without l1CappedComposite")
    return results
