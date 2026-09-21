"""
Solana authority scorers -- first 2 flagship targets (2026-09-17).

Promotes `METHODOLOGY.md`'s deterministic formulas (section 6.1) and the two
targets already fully worked by hand in `data/methodology_test_2026-09-16.md`
(Jupiter Aggregator v6, Kamino Lend main market) into a real, re-runnable
scorer module -- the same "backlog research -> live-verified scorer"
promotion pattern already used this pass for Ethereum L1
(`chains/ethereum-l1/scorers.py`).

Every number below is DERIVED LIVE from Solana Mainnet Beta on each run, not
replayed from the methodology test file. Two things are intentionally
hardcoded as constants and re-verified, never trusted blind:
  1. The target program/market addresses themselves (sourced from official
     docs/repos, same convention as every other ecosystem file here).
  2. The Squads multisig account that the methodology test identified as
     controlling each off-curve authority PDA (via
     `sol_read.resolve_controller_via_last_tx`, itself just a
     transaction-history lookup, not proof). Each hardcoded multisig
     candidate is independently re-checked EVERY run by offline PDA
     re-derivation (`sol_read.read_squads_vault` / the Squads v3 `authority_N`
     seed) and REQUIRED to exactly match the live-read authority pubkey --
     if it doesn't, the scorer degrades rather than silently trusting a
     stale identification. This mirrors the Arbitrum L1->L2 bridge-alias
     re-derivation already used on the EVM side of this project.

Reproduction / independent re-verification of the byte layouts and formulas:
see `data/methodology_test_2026-09-16.md` (hand-derived) and
`data/sol_read_refactor_check_2026-09-17.md` (confirms the refactored
`scripts/sol_read.py` this file imports still reads byte-identical values).
"""
import base64
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
import sol_read  # noqa: E402

SQUADS_V3_PROGRAM = "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu"
SQUADS_V4_PROGRAM = "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"
SYSTEM_PROGRAM_DEFAULT = "11111111111111111111111111111111"


def _composite(admin_key, multisig, timelock):
    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


def _round_half_up(x):
    # This project's established rounding convention (see
    # scripts/lib/tests/test_scorers.py's TestComposite.
    # test_round_half_up_not_bankers_rounding) applied consistently to every
    # "round(...)" call in METHODOLOGY.md section 6.1's formulas -- Python's
    # builtin round() uses banker's rounding, which this project already
    # rejected once on the EVM side.
    return math.floor(x + 0.5)


def _delay_timelock_score(d_hours):
    """Post-DECISION notice-period curve (METHODOLOGY.md 6.1), shared
    verbatim by Squads v4's `time_lock` and (CLOSED 2026-09-19, see section
    7's changelog) Realms' `transactions_hold_up_time`. `d_hours` must
    already be the delay between a decision being FINAL/unstoppable and
    that decision taking effect -- nothing before that point (a Squads
    approval race, a Realms proposal's voting window) belongs in this
    function; see the `realms_governance` branch below for why."""
    if d_hours == 0:
        return 0
    if d_hours < 24:
        return _round_half_up(50 * d_hours / 24)
    return min(80, 50 + min(30, _round_half_up(10 * (d_hours / 24 - 1))))


def _score_full_power_path(kind, threshold=None, voters=None, delay_s=None,
                            voting_s=None, cooloff_s=0, holdup_s=0):
    """One full-power authority path -> (adminKey, multisig, timelock), per
    METHODOLOGY.md section 6.1's deterministic formulas.

    kind: "none" | "on_curve" | "off_curve_unresolved" | "squads_v3" | "squads_v4" | "realms_governance"

    The "Squads v4 controlled (config_authority set)" band from 6.1 is
    deliberately NOT implemented here: no target scored in this file has a
    non-default config_authority on any resolved path (every multisig read
    below has config_authority == system default), so there is nothing to
    calibrate it against yet -- raises rather than guessing a number."""
    if kind == "none":
        return 100, 100, 100
    if kind == "on_curve":
        return 5, 0, 0
    if kind == "off_curve_unresolved":
        return 20, 0, 0
    if kind in ("squads_v3", "squads_v4"):
        if threshold == 1:
            return 5, 0, 0
        multisig = min(100, _round_half_up(15 * threshold + 40 * threshold / voters))
        d_hours = 0 if (kind == "squads_v3" or delay_s == 0) else delay_s / 3600
        if d_hours == 0:
            admin = 40 + min(20, 5 * (threshold - 1))
        elif d_hours < 24:
            admin = 50 + min(20, 5 * (threshold - 1))
        else:
            admin = 60 + min(20, 5 * (threshold - 1))
        timelock = _delay_timelock_score(d_hours)
        return admin, multisig, timelock
    if kind == "realms_governance":
        # Validated 2026-09-17 against Solend DAO (chains/solana/data/
        # methodology_test_2026-09-17-solend-governance.md) for the pure
        # token-voting branch (threshold=None, no council mint) -- closes
        # METHODOLOGY.md 6.1's "untested" flag.
        #
        # The countable council/community-threshold branch (threshold is
        # not None) was ALSO calibrated 2026-09-17, against a real data
        # point found the same day (see
        # data/finding_2026-09-17-spl-governance-shared-instance-controller.md):
        # the SPL Governance shared default instance's own controlling
        # council is a real, live 5-of-7-by-weight council. A council-
        # threshold Realms vote is structurally the same "t-of-n,
        # weight-gated" shape the Squads formulas already score, so this
        # reuses that SAME calibrated multisig formula rather than
        # inventing a new one for a single data point.
        if threshold is not None:
            if threshold == 1:
                admin, multisig = 5, 0
            else:
                admin = 60 + min(30, 5 * (threshold - 1))
                multisig = min(100, _round_half_up(15 * threshold + 40 * threshold / voters))
        else:
            # INVESTIGATED 2026-09-19, still undocumented (METHODOLOGY.md 7):
            # this flat 70 has no recoverable derivation -- checked git
            # history (bare literal since the commit that introduced this
            # row, no comment/rationale ever attached), checked whether it
            # equals this SAME formula at t=3 (60+min(30,5*2))=70 (it does,
            # but nothing ties that to why 70 was picked -- rejected as a
            # coincidence, not adopted as a post-hoc justification), and
            # checked it against the two real targets that hit this exact
            # branch (Solend's real 1% YesVotePercentage threshold, Drift's
            # real 2%) -- neither value feeds this formula at all, so
            # neither could have calibrated it. Left unchanged rather than
            # replaced with an equally uncalibrated new number.
            admin = 70
            multisig = 70
        # timelock -- RECONCILED 2026-09-19 (METHODOLOGY.md 7, was flagged
        # "NOT yet closed"). Previously this summed voting_s + cooloff_s +
        # holdup_s into one "total_hours" and fed the SAME additive curve
        # Squads v4 uses for its POST-approval `time_lock` -- but
        # spl-governance's own source (governance/program/src/state/
        # governance.rs's doc comments on GovernanceConfig) establishes
        # these are NOT the same concept:
        #   - `transactions_hold_up_time`: "the wait time ... before
        #     transactions can be executed AFTER proposal is SUCCESSFULLY
        #     VOTED ON" -- the decision is already final; nothing can
        #     change the outcome, only postpone it. This is the TRUE
        #     Squads-`time_lock` equivalent.
        #   - `voting_base_time`: "the base voting time ... for proposal to
        #     be open for voting. Voting is unrestricted ... any vote types
        #     can be cast." The decision is NOT yet final -- this is still
        #     part of REACHING the decision, with no Squads-side analogue
        #     scored anywhere in this file (Squads' own time-to-collect-
        #     signatures is never scored as a delay).
        #   - `voting_cool_off_time`: "extend[s]" voting_base_time, during
        #     which "only negative votes (Veto and Deny) are allowed" --
        #     STILL part of the voting/decision process (a proposal can
        #     still be stopped here), not a post-decision notice period.
        # Folding voting_s/cooloff_s into the delay curve conflated
        # "time to decide" with "notice after deciding," which is why the
        # two curves diverged sharply at short/zero delay (Squads d=0 -> 0,
        # old Realms formula floored at 40 even at holdup=0) despite both
        # claiming to measure "delay before an action takes effect."
        # Reconciled by scoring ONLY holdup_s, with the EXACT SAME
        # `_delay_timelock_score` curve Squads v4 uses -- no new curve
        # invented, since the two now measure the identical concept.
        # voting_s/cooloff_s remain accepted parameters (every call site
        # still reads and discloses them in its own notes) but no longer
        # feed this score. Checked against every real target scored so far
        # (Solend, Drift, Marinade): each one's PUBLISHED overall
        # timelockScore is unchanged by this fix, because a DIFFERENT
        # full-power path (a bare on-curve authority or a short-delay
        # Squads path) already dominated the min() in every one of them --
        # this reconciliation is not yet load-bearing on any live number,
        # only on this formula's own internal correctness and on whatever
        # future target has the Realms path as its binding constraint.
        timelock = _delay_timelock_score((holdup_s or 0) / 3600)
        return admin, multisig, timelock
    raise ValueError(f"unknown authority-path kind: {kind}")


def _voters_with_vote_permission(squads_v4_read):
    # Squads v4 Member.permissions bitmask: Initiate=1, Vote=2, Execute=4
    # (METHODOLOGY.md 3.4) -- threshold counts voters, not all members.
    return sum(1 for m in squads_v4_read["member_list"] if m["mask"] & 2)


RENOUNCED = "RENOUNCED"  # sentinel distinct from both None (unresolved) and a resolved Squads dict


def _resolve_squads_v4(url, label, authority, ms_candidate, notes, none_means_renounced=False):
    """Offline-re-derive vault index 0 of `ms_candidate` and require an exact
    match with the live-read `authority`. Returns the live `read_squads()`
    dict on match, None if unresolved/mismatched (caller must degrade, not
    guess), or the RENOUNCED sentinel if `authority` is None AND the caller
    has confirmed (via `none_means_renounced=True`) that a None here means a
    genuine on-chain `Option::None` (loader-v3 upgrade authority renounced --
    the SAFEST possible state, METHODOLOGY.md 6.1), not merely a field read
    that failed. FIXED 2026-09-17 (closed a bug hunt finding): a bare
    `authority is not None and derived == authority` check treated
    "renounced" and "mismatch/unresolved" identically, inverting the risk
    signal for the safest state a program can be in."""
    if authority is None and none_means_renounced:
        notes.append(f"{label}: upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1, not a failed read")
        return RENOUNCED
    derived = sol_read.read_squads_vault(ms_candidate, 0)["vault"]
    matched = authority is not None and derived == authority
    notes.append(
        f"{label}: offline vault-0 PDA of candidate multisig {ms_candidate} = {derived} "
        f"(expected live authority {authority}) -- {'MATCH' if matched else 'MISMATCH, degrading'}"
    )
    if not matched:
        return None
    sq = sol_read.read_squads(url, ms_candidate)
    if sq["config_authority"] != SYSTEM_PROGRAM_DEFAULT:
        raise NotImplementedError(
            f"{label}: config_authority is set (not default) on {ms_candidate} -- the "
            "'Squads v4 controlled' scoring band is not implemented (see _score_full_power_path docstring)"
        )
    return sq


def score_jupiter_aggregator_v6(url) -> dict:
    """Jupiter Aggregator v6. Source: Jupiter's own CPI crate
    (jup-ag/jupiter-cpi `src/lib.rs`), cross-checked against the on-chain
    Anchor IDL's own `address` field. Full derivation already worked by hand
    in `data/methodology_test_2026-09-16.md` section "Target 1" -- this
    function re-derives every number live rather than replaying it.

    Authority: loader-v3 program-upgrade authority is a PDA
    (`CvQZZ23qYDWF2RUpxYJ8y9K4skmuvYEEjH7fK58jtipQ`), identified as Squads v3
    Ms account `7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf` authority index
    1 via the last upgrade transaction -- re-confirmed every run by offline
    PDA re-derivation, required to exactly match the live upgrade authority.
    4-of-7, no time-lock field exists on Squads v3 (METHODOLOGY.md 3.4).

    Not scored (informational, see docstring precedent in
    `chains/ethereum-l1/scorers.py`'s governance-capture notes): the same
    authority PDA is the upgrade authority of 22 other ProgramData accounts
    (blast-radius fact, not folded into this target's own score -- no
    defensible way to turn "controls N other programs" into a 0-100 number
    for THIS target's own risk without double-counting)."""
    JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    JUPITER_MS = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"
    notes = []

    prog = sol_read.read_program(url, JUPITER_PROGRAM)
    authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {authority}")

    ms = sol_read.read_squadsv3(url, JUPITER_MS, authority_index=1)
    derived = ms.get("authority_1")
    notes.append(f"Squads v3 Ms({JUPITER_MS}) authority_1 (offline PDA re-derivation) = {derived}")

    signers = set()
    # FIXED 2026-09-17 (closed a bug hunt finding): `authority is None` means
    # the program has RENOUNCED its upgrade authority -- METHODOLOGY.md 6.1's
    # own safest band (100/100/100), not a read that "didn't match". A bare
    # truthy check on `authority` collapsed that case into the same degraded
    # 20/20/0 branch as a genuine mismatch, inverting the risk signal for the
    # one state that's actually the safest possible. `_score_full_power_path`
    # already had a "none" branch for exactly this; it was just never wired up.
    if authority is None:
        admin, multisig, timelock = _score_full_power_path("none")
        notes.append("program.upgrade_authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1, not a failed read")
    elif derived and authority == derived:
        threshold, voters = ms["threshold"], ms["n_keys"]
        admin, multisig, timelock = _score_full_power_path("squads_v3", threshold=threshold, voters=voters)
        signers = set(ms["keys"])
        notes.append(
            f"Offline-derived authority_1 MATCHES the live program.upgrade_authority -- "
            f"real controller confirmed, {threshold}-of-{voters}, no time-lock field on Squads v3"
        )
    else:
        admin, multisig, timelock = 20, 20, 0
        notes.append(
            "Offline-derived Squads v3 authority PDA did NOT match the live program.upgrade_authority "
            "this run -- degraded rather than trusting the hardcoded JUPITER_MS constant"
        )

    return {
        "target": JUPITER_PROGRAM, "label": "Jupiter Aggregator v6",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_solend_dao_governance(url) -> dict:
    """Solend DAO governance -- the first Realms-governed target this project
    scores. Full derivation in `data/methodology_test_2026-09-17-solend-
    governance.md`, surfaced as a byproduct of independently re-verifying the
    2022 "emergency powers" incident for `data/backtest_2026-09-17-solend-
    governance-emergency-powers.md`.

    Solend deploys its OWN dedicated governance program
    (`A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr`), confirmed live, NOT the
    shared default SPL Governance instance documented in METHODOLOGY.md 3.6
    -- a wrong first-pass assumption caught before it became a stale
    citation, not guessed.

    FIXED 2026-09-17 (closed an adversarial-review finding on this same-day
    addition): a first version of this function scored only 2 of 3
    full-power paths, omitting the governance PROGRAM's own upgrade
    authority -- an inconsistency with every other multi-authority target in
    this file (score_jupiter_aggregator_v6 and score_kamino_lend both read
    their target's own program upgrade_authority as a first-class path).
    Live-checked: that authority is ALSO a bare, on-curve, actively used EOA
    (`6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT`, not renounced) -- a
    third path, as severe as the realm-authority path, that could rewrite
    the governance program's own vote-counting and execution logic outright.

    Three full-power paths (METHODOLOGY.md 6.2), scored independently,
    minimum taken across all three like every other multi-authority target
    in this file:

      1. The Realm's own `authority` field (`RealmV2.authority`, distinct
         from any Governance account under it) -- can unilaterally rewrite
         which mint counts for voting power, add a council mint, or change
         the minimum weight to create a governance, with NO token-holder
         vote at all. Solend's realm authority is a bare, on-curve, actively
         used wallet (real lamport balance, real recent transaction history)
         -- the spl-governance docs' own recommended end state (transferring
         this field to the realm's own Governance PDA, making it fully
         self-governed) has not happened here.
      2. The `GovernanceV2` account over the SLND mint -- pure community
         token-weighted voting (no council mint exists on this realm), zero
         `transactions_hold_up_time`, `voting_base_time` currently 3 days.
         This is the SAME account SLND1 and SLND2 both voted through in
         2022, still the realm's only Governance account today.
      3. The governance PROGRAM's own loader-v3 upgrade authority -- whoever
         holds it can replace the program's code outright, bypassing both
         paths above entirely (METHODOLOGY.md 3.6's own point: "a DAO... on
         [a] shared instance inherits that authority as a dependency"
         applies just as much to a dedicated instance, just with a
         different, still-real, holder).

    Two of the three paths independently resolve to the same bare-EOA band
    and dominate the composite regardless of exactly how the token-voting
    formula is calibrated -- all three published anyway, both because this
    is the methodology's first real Realms-governance validation and
    because either EOA being replaced by a self-governing PDA would make
    the remaining paths the ones that actually matter.

    Not scored (informational, disclosed rather than folded into a number):
    `community_vote_threshold` decodes to `YesVotePercentage(1)`, an
    unusually low bar, consistent with but not independently re-confirmed
    against the realized SLND1/SLND2 vote weights this pass -- see the
    methodology test file's caveat. Also not scored: METHODOLOGY.md 7's
    disclosed gaps that (a) the flat "70 for token voting" baseline does not
    account for realized voter concentration, which Solend's own 2022
    incident is real evidence for, and (b) the realms_governance timelock
    curve is not reconciled with the Squads v4 timelock curve at short
    delays."""
    REALM = "7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn"
    GOVERNANCE = "4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc"
    GOVERNANCE_PROGRAM = "A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr"
    SLND_MINT = "SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp"
    notes = []
    signers = set()

    def _score_bare_authority(label, authority):
        """Shared classification for a raw Option<Pubkey>-style authority
        field: None -> renounced (safest), on-curve -> bare EOA (worst
        realistic band), off-curve -> unresolved PDA (degraded). Used for
        both the realm authority and the governance program's own upgrade
        authority -- the same classification ladder applies to either."""
        if authority is None:
            notes.append(f"{label} is None -- renounced, the safest band, not a failed read")
            return _score_full_power_path("none")
        kt = sol_read.read_keytype(url, authority)
        if kt["on_curve"]:
            signers.add(authority)
            notes.append(f"{label} {authority} is a bare on-curve key (owner={kt['owner']}) -- no vote required")
            return _score_full_power_path("on_curve")
        notes.append(f"{label} {authority} is off-curve (a PDA) -- controller not resolved this pass, degraded rather than assumed self-governed")
        return _score_full_power_path("off_curve_unresolved")

    realm = sol_read.read_realm(url, REALM)
    if realm["community_mint"] != SLND_MINT:
        raise ValueError(f"Realm {REALM} community_mint {realm['community_mint']} != expected SLND mint -- wrong account, aborting rather than scoring the wrong DAO")
    notes.append(f"Realm.authority = {realm['authority']}")
    path_a = _score_bare_authority("Realm.authority", realm["authority"])

    gov = sol_read.read_governance(url, GOVERNANCE)
    if gov["realm"] != REALM or gov["governed_account"] != SLND_MINT:
        raise ValueError(f"Governance {GOVERNANCE} realm/governed_account mismatch -- wrong account, aborting rather than scoring the wrong target")
    notes.append(
        f"Governance({GOVERNANCE}) over the SLND mint: proposals_count={gov['proposals_count']} "
        f"transactions_hold_up_time_s={gov['transactions_hold_up_time_s']} voting_base_time_s={gov['voting_base_time_s']} "
        f"community_vote_threshold={gov['community_vote_threshold']} (raw value not independently re-confirmed, not used as a score input)"
    )
    if realm["council_mint"] is not None:
        # Dead branch for Solend specifically -- its realm has no council
        # mint, confirmed above, so this never executes here. STALE COMMENT
        # FIXED 2026-09-18: this used to say the countable-threshold branch
        # of _score_full_power_path("realms_governance", ...) "deliberately
        # raises NotImplementedError," which stopped being true the same day
        # it was written (see the changelog: that branch was calibrated
        # 2026-09-17 against the SPL Governance shared-instance council).
        # `score_marinade` is now the real, live, working example of this
        # branch -- see its own docstring for the actual threshold/voters
        # derivation (ceil(vote_threshold_pct * total_council_weight)), not
        # the placeholder threshold=1 this dead branch still passes.
        path_b = _score_full_power_path(
            "realms_governance", threshold=1, voting_s=gov["voting_base_time_s"], holdup_s=gov["transactions_hold_up_time_s"])
    else:
        path_b = _score_full_power_path(
            "realms_governance", voting_s=gov["voting_base_time_s"], holdup_s=gov["transactions_hold_up_time_s"])
    notes.append(
        f"community token-vote path (no council mint): adminKey={path_b[0]} multisig={path_b[1]} timelock={path_b[2]} "
        f"(voting={gov['voting_base_time_s']/3600:.1f}h hold-up={gov['transactions_hold_up_time_s']/3600:.1f}h)"
    )

    prog = sol_read.read_program(url, GOVERNANCE_PROGRAM)
    notes.append(f"governance program.upgrade_authority = {prog.get('upgrade_authority')}")
    path_c = _score_bare_authority("governance program.upgrade_authority", prog.get("upgrade_authority"))

    paths = {"Realm.authority": path_a, "community token-vote": path_b, "governance program.upgrade_authority": path_c}
    admin = min(p[0] for p in paths.values())
    multisig = min(p[1] for p in paths.values())
    timelock = min(p[2] for p in paths.values())
    dominant = sorted({name for name, p in paths.items() if p[0] == admin or p[1] == multisig or p[2] == timelock})
    notes.append(
        f"combined (min over all three full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock} "
        f"-- dominated by: {dominant}"
    )

    return {
        "target": REALM, "label": "Solend DAO (governance realm)",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


DRIFT_MS = "7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM"


def score_drift_protocol(url) -> dict:
    """Drift Protocol (perpetuals DEX). Full derivation in `data/
    methodology_test_2026-09-17-drift-protocol.md`, surfaced while
    independently re-verifying the 2026-04-01 $285M Security Council
    compromise for `data/backtest_2026-09-17-drift-protocol-security-
    council-compromise.md` -- Drift's own README/SolGov-comparison
    citation made this an obvious next target once the incident itself
    was confirmed to be a genuine authority-risk failure (a compromised
    2-of-5, zero-timelock Squads multisig), not a smart-contract bug.

    FIXED 2026-09-17 (closed an adversarial-review finding on this same-day
    addition): the program-upgrade path's `_resolve_squads_v4` call was
    missing `none_means_renounced=True` -- the same flag Kamino's own
    program-upgrade calls already pass. Without it, a renounced (`None`)
    upgrade authority would have been scored as a MISMATCH (20/20/0) with
    a factually false "degrading" note, instead of the safest band
    (100/100/100) -- an inverted risk signal for the one state that's
    actually safest, the exact bug class `_resolve_squads_v4`'s own
    docstring already warns about. Drift's authority is not currently
    renounced, so this had no effect on the published score, but would
    have silently mis-scored a future renouncement.

    Two full-power paths (METHODOLOGY.md 6.2), minimum taken across both:

      1. The program's own loader-v3 upgrade authority -- a Squads v4
         multisig, independently re-derived and required to match (same
         discipline as Jupiter/Kamino): 4-of-7 (one of seven members lacks
         Vote permission, leaving 6 real voters), a REAL 1-hour
         `time_lock`, autonomous `config_authority` -- a genuine
         post-incident improvement over the compromised multisig's 2-of-5,
         ZERO time_lock, non-default `config_authority` (see the backtest
         file for that full derivation).
      2. The Realm's own `authority` field -- unlike Solend's bare EOA,
         Drift's realm authority IS a Governance PDA (self-governed): pure
         community token voting (2% yes threshold), a REAL 1-day
         post-vote hold-up, 4-day base voting time, plus a separate
         5-seat council that can VETO (not pass) a proposal at 30% weight.

    Not scored (informational, disclosed rather than forced into a
    number): the council-veto shape has no dedicated METHODOLOGY.md 6.1
    formula branch (the existing countable-threshold branch models a
    council that PASSES votes, not one that only vetoes) -- scored via the
    flat token-voting numbers instead of inventing an uncalibrated veto
    formula. Also not scored: whether the 5-seat council's members overlap
    with the Squads v4 multisig's 7 members (would matter for
    `crossExposureScore` if the same people sit on both bodies -- not
    cross-checked this pass).

    oracleAuthorityScore -- CLOSED 2026-09-19 (METHODOLOGY.md 7's "Add
    Switchboard On-Demand oracle authority primitives" open point): this
    used to be a flat, unjustified 100 like every other non-Kamino target in
    this file. Drift runs ~150 perp/spot markets across several oracle
    types (Pyth, PythLazer, SwitchboardOnDemand, Prelaunch); enumerating
    live on-chain which markets currently use which type found ZERO live
    perp markets on SwitchboardOnDemand today (Drift's OWN published SDK
    constant for W-PERP, `sdk/src/constants/perpMarkets.ts`, is stale --
    live-read `amm.oracle` for that market no longer matches, migrated to
    PythLazer since) but 16 live SPOT markets that do, confirmed by account
    OWNER (`SBondMDrcV3K4kxZR1HNVT7osZxAHVHgYXL5Ze1oMUv`, the official
    mainnet Switchboard On-Demand program id per the SDK's own
    `ON_DEMAND_MAINNET_PID` constant -- a first recalled guess for this id
    was wrong and caught only by checking the primary source), not trusted
    from any SDK file. One real, live, named market (AI16Z, not one of the
    market's "Default Market Name" placeholder shells) is scored as a
    concrete example of this oracle-authority surface, the same
    disclosed-scope convention `score_kamino_lend` already uses for its one
    scored Scope config rather than claiming to be exhaustive over every
    reserve. Three full-power-over-the-price paths (METHODOLOGY.md 6.3
    pattern, adapted -- Switchboard is a direct provider here, not an
    aggregator over a further provider):
      1. The feed's own `authority` (`PullFeedAccountData.authority`) --
         can rewrite `feed_hash`, i.e. the ENTIRE job schema/computation
         that produces this feed's price, with no quorum and no delay of
         its own. Live-read: a bare on-curve EOA.
      2. The default mainnet queue's `authority`
         (`QueueAccountData.authority`, queue `A43DyUGA7s8eXPxqEjJY6EBu1KK
         bNgfxF8h17VAHn13w`, confirmed to be Switchboard's own published
         default queue, not a Drift-specific one) -- controls which oracle
         operators may serve ANY feed on this shared queue, the Switchboard
         analogue of Pyth's `governance_authority`/`valid_data_sources`.
      3. The Switchboard On-Demand PROGRAM's own loader-v3 upgrade
         authority -- whoever holds it can replace the entire oracle
         system's code.
    Live-read (2 independent RPCs, `api.mainnet-beta.solana.com` and
    `solana-rpc.publicnode.com`, byte-identical): paths 2 and 3 resolve to
    the EXACT SAME Squads v4 vault PDA
    (`DREcTwxxuehtUVgnGwDpTcKT9zTK5uDmdLbnRY7cijEx`), independently
    re-derived offline against candidate multisig
    `93RQfY6VHRkqXBCEhMY5u92bCGp428DTzqZUEA2Hjr9h` and required to match
    (same discipline as every other Squads resolution in this file): a real
    3-of-8 multisig (all 8 members hold full Initiate|Vote|Execute
    permissions), autonomous `config_authority`, `time_lock = 0`. Scored
    with the EXISTING, already-calibrated `squads_v4` formula -- no new
    curve invented for this. `oracleAuthorityScore` = min over each path's
    OWN standalone composite (6.3's rule), and is DOMINATED by path 1 (the
    bare-EOA feed authority, composite 2) even though the shared
    queue/program layer behind it is a reasonable multisig -- the same
    "one weak undelayed path caps the whole dimension" shape
    `score_kamino_lend`'s Scope-admin path already demonstrated. Not
    scored: the other 15 live Switchboard-On-Demand spot markets' own
    `authority` fields (not cross-checked whether they share the same bare
    EOA or differ -- would matter for `crossExposureScore` if so, not
    checked this pass), and every Pyth/PythLazer-sourced market (a
    separate, not-yet-scored provider-authority surface)."""
    DRIFT_PROGRAM = "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH"
    REALM = "FVVXu18aNUqyFCfq8sGktPM62mqJAGaenv4z6UGUs5em"
    DRIFT_MINT = "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7"
    # AI16Z spot market's live oracle account (getProgramAccounts scan,
    # 2026-09-19, over all 66 live Drift SpotMarket accounts filtered by
    # oracle-account owner == the Switchboard On-Demand program id --
    # chosen because it is a real, named, live market, not one of the
    # several "Default Market Name" placeholder shells that also resolve to
    # a Switchboard On-Demand oracle account on this same program).
    SWITCHBOARD_FEED = "BHqLyA9ov1VPNzt8eb5bt75X2Vk1EVKw1d9Qa78Gk5tR"
    SWITCHBOARD_UPGRADE_MS = "93RQfY6VHRkqXBCEhMY5u92bCGp428DTzqZUEA2Hjr9h"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, DRIFT_PROGRAM)
    program_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {program_authority}")
    ms_a = _resolve_squads_v4(url, "program upgrade", program_authority, DRIFT_MS, notes, none_means_renounced=True)
    if ms_a is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif ms_a == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        threshold, voters = ms_a["threshold"], _voters_with_vote_permission(ms_a)
        admin_a, multisig_a, timelock_a = _score_full_power_path("squads_v4", threshold=threshold, voters=voters, delay_s=ms_a["time_lock_s"])
        signers |= {m["key"] for m in ms_a["member_list"]}
        notes.append(f"program upgrade Squads v4: {threshold}-of-{ms_a['members']} ({voters} with Vote permission) delay={ms_a['time_lock_s']}s config_authority={ms_a['config_authority']}")

    realm = sol_read.read_realm(url, REALM)
    if realm["community_mint"] != DRIFT_MINT:
        raise ValueError(f"Realm {REALM} community_mint {realm['community_mint']} != expected DRIFT mint -- wrong account, aborting rather than scoring the wrong DAO")
    authority = realm["authority"]
    notes.append(f"Realm.authority = {authority}")
    if authority is None:
        admin_b, multisig_b, timelock_b = _score_full_power_path("none")
    else:
        kt = sol_read.read_keytype(url, authority)
        if not kt["on_curve"] and kt["owner"] == "dgov7NC8iaumWw3k8TkmLDybvZBCmd1qwxgLAGAsWxf":
            gov = sol_read.read_governance_v2(url, authority)
            if gov["realm"] != REALM:
                raise ValueError(f"Governance {authority} realm mismatch -- wrong account, aborting rather than scoring the wrong target")
            admin_b, multisig_b, timelock_b = _score_full_power_path(
                "realms_governance", voting_s=gov["voting_base_time_s"],
                cooloff_s=gov["voting_cool_off_time_s"], holdup_s=gov["transactions_hold_up_time_s"])
            notes.append(
                f"Realm.authority is Drift's own self-governed Governance PDA (community token vote, no council mint on this path): "
                f"adminKey={admin_b} multisig={multisig_b} timelock={timelock_b} "
                f"(voting={gov['voting_base_time_s']/3600:.1f}h cooloff={gov['voting_cool_off_time_s']/3600:.1f}h hold-up={gov['transactions_hold_up_time_s']/3600:.1f}h); "
                f"council_veto_vote_threshold={gov['council_veto_vote_threshold']} (a 5-seat council can VETO, not pass, a proposal here -- "
                f"not folded into a score, no calibrated formula for a veto-only council exists yet)"
            )
        elif kt["on_curve"]:
            admin_b, multisig_b, timelock_b = _score_full_power_path("on_curve")
            signers.add(authority)
            notes.append(f"Realm.authority {authority} is a bare on-curve key -- no vote required")
        else:
            admin_b, multisig_b, timelock_b = _score_full_power_path("off_curve_unresolved")
            notes.append(f"Realm.authority {authority} is an unrecognized PDA (owner={kt['owner']}) -- degraded rather than assumed self-governed")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    # oracleAuthorityScore -- CLOSED 2026-09-19, METHODOLOGY.md 7's "Add
    # Switchboard On-Demand oracle authority primitives". See the
    # docstring above for the full derivation; this scores one real, live,
    # named Switchboard On-Demand-sourced market (AI16Z) as a concrete
    # example, not an exhaustive scan of every Drift market/oracle type.
    feed = sol_read.read_switchboard_pull_feed(url, SWITCHBOARD_FEED)
    if feed["owner"] != sol_read.SWITCHBOARD_ON_DEMAND_PROGRAM or not feed["discriminator_ok"]:
        raise ValueError(f"{SWITCHBOARD_FEED}: not a live Switchboard On-Demand PullFeedAccountData this run -- aborting rather than scoring a wrong/stale account")
    notes.append(f"Switchboard On-Demand feed {SWITCHBOARD_FEED} (AI16Z spot market): authority={feed['authority']} queue={feed['queue']}")

    if feed["authority"] is None:
        feed_auth_path = _score_full_power_path("none")
    else:
        kt_feed_auth = sol_read.read_keytype(url, feed["authority"])
        if kt_feed_auth["on_curve"]:
            feed_auth_path = _score_full_power_path("on_curve")
            signers.add(feed["authority"])
            notes.append(f"feed.authority {feed['authority']} is a bare on-curve key -- can rewrite feed_hash (the whole price computation) with no quorum, no delay")
        else:
            feed_auth_path = _score_full_power_path("off_curve_unresolved")
            notes.append(f"feed.authority {feed['authority']} is an unresolved PDA -- degraded rather than assumed safe")

    is_default_queue = feed["queue"] == sol_read.SWITCHBOARD_ON_DEMAND_MAINNET_QUEUE
    notes.append(f"feed.queue {feed['queue']} == Switchboard's own published default mainnet queue? {is_default_queue}")
    queue = sol_read.read_switchboard_queue(url, feed["queue"])
    if queue["owner"] != sol_read.SWITCHBOARD_ON_DEMAND_PROGRAM or not queue["discriminator_ok"]:
        raise ValueError(f"{feed['queue']}: not a live Switchboard On-Demand QueueAccountData this run -- aborting rather than scoring a wrong/stale account")

    sbod_prog = sol_read.read_program(url, sol_read.SWITCHBOARD_ON_DEMAND_PROGRAM)
    notes.append(f"Switchboard On-Demand program.upgrade_authority = {sbod_prog.get('upgrade_authority')}; queue.authority = {queue['authority']}")

    queue_sq = _resolve_squads_v4(url, "Switchboard queue authority", queue["authority"], SWITCHBOARD_UPGRADE_MS, notes, none_means_renounced=True)
    prog_sq = _resolve_squads_v4(url, "Switchboard program upgrade", sbod_prog.get("upgrade_authority"), SWITCHBOARD_UPGRADE_MS, notes, none_means_renounced=True)

    def _sbod_path(sq):
        if sq is None:
            return 20, 20, 0
        if sq == RENOUNCED:
            return 100, 100, 100
        return _score_full_power_path("squads_v4", threshold=sq["threshold"], voters=_voters_with_vote_permission(sq), delay_s=sq["time_lock_s"])

    queue_auth_path = _sbod_path(queue_sq)
    prog_auth_path = _sbod_path(prog_sq)
    for sq in (queue_sq, prog_sq):
        if sq and sq != RENOUNCED:
            signers |= {m["key"] for m in sq["member_list"]}

    sbod_composites = {
        "feed authority (feed_hash rewrite)": _composite(*feed_auth_path),
        "queue authority (oracle permission set)": _composite(*queue_auth_path),
        "On-Demand program upgrade": _composite(*prog_auth_path),
    }
    oracle_authority = min(sbod_composites.values())
    notes.append(f"oracleAuthorityScore = min({sbod_composites}) = {oracle_authority}")

    return {
        "target": DRIFT_PROGRAM, "label": "Drift Protocol",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": oracle_authority, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_kamino_lend(url) -> dict:
    """Kamino Lend, main market (SOL/BTC). Source: Kamino-Finance/klend
    README (program id), official Kamino API `v2/kamino-market`
    (`isPrimary: true` for this market). Full derivation already worked by
    hand in `data/methodology_test_2026-09-16.md` section "Target 2" -- this
    function re-derives every number live rather than replaying it.

    Seven distinct authority paths exist on this protocol (METHODOLOGY.md
    6.2's full-power/bounded/restrict-only classification); this scorer
    reads the four that feed a score dimension:
      - klend program upgrade (full-power): Squads v4, 5-of-10, 24h delay.
      - market owner (full-power): Squads v4, 4-of-10, 12h delay -- gates
        every reserve-risk-config mode that isn't global-admin-only or
        emergency-council-restricted (LTV, liquidation threshold, limits,
        AND the oracle mapping functions).
      - Scope (the price aggregator this market's SOL/USDC reserves read
        through) mapping admin (oracle only): Squads v4, 4-of-10, ZERO
        delay -- can re-point the exact price feed these reserves use,
        including to a hardcoded FixedPrice, with no notice.
      - Scope program upgrade (oracle only): Squads v4, 5-of-10, 24h delay.
    adminKeyScore/multisigScore/timelockScore take the min across the first
    two (full-power, non-oracle) paths only; oracleAuthorityScore takes the
    min of each of the three oracle-relevant paths' OWN standalone composite
    (METHODOLOGY.md 6.3) -- oracle-provider weakness is published once, in
    its own dimension, not double-counted into the admin-key dimension too.

    Genuinely aggravating finding, disclosed rather than smoothed: the code
    path is delayed 24h and the risk-parameter path 12h, but the SAME ten
    signers can re-map the SOL/USDC price entries through the Scope admin
    multisig with NO delay at all -- a price source is as powerful as an LTV
    change for a lending market, and this second, undelayed path is exactly
    what caps oracleAuthorityScore below what the two slower paths alone
    would suggest.

    Multisig identification: each of the four authority PDAs above was
    matched to its controlling Squads v4 multisig via
    `sol_read.resolve_controller_via_last_tx` (a transaction-history lookup,
    not proof by itself) and is independently re-verified EVERY run by
    offline vault-PDA re-derivation, required to exactly match the live
    authority -- never trusted from the hardcoded candidate alone."""
    KLEND_PROGRAM = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD"
    MARKET = "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF"
    SCOPE_PROGRAM = "HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ"
    SCOPE_CONFIG = "6cMwdbrJ95D7v5655Zsoe7oXmjQJMnagWK8EcdG6qmGM"  # feeds this market's SOL/USDC reserve price entries

    KLEND_UPGRADE_MS = "6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM"
    MARKET_OWNER_MS = "7idEEVRidWrahZJhxXMqniDbV6ESj7ZjyLrigcMcEt6H"
    SCOPE_ADMIN_MS = "EFZxQRB58g7nTYw6bag8sJYXn7wUWHoKt3AcCNzHbe24"
    SCOPE_UPGRADE_MS = "DDJGaWjVREXffoMe9nyvb1c7wpajLdh7fTnAb2giD9RM"

    notes = []

    prog = sol_read.read_program(url, KLEND_PROGRAM)
    klend_authority = prog.get("upgrade_authority")
    notes.append(f"klend program.upgrade_authority = {klend_authority}")

    market = sol_read.read_klend_market(url, MARKET)
    market_owner_authority = market.get("lending_market_owner")
    notes.append(f"LendingMarket({MARKET}, name={market.get('name')!r}).lending_market_owner = {market_owner_authority}")
    if market.get("lending_market_owner_cached") != market_owner_authority:
        notes.append(
            f"lending_market_owner_cached ({market.get('lending_market_owner_cached')}) differs from "
            f"lending_market_owner -- a governance transfer is PENDING, not yet finalized; scored on the "
            f"current (non-cached) owner, consistent with 'current authority, not a future one' elsewhere in this project"
        )

    scope_configs = sol_read.read_scope_configs(url, SCOPE_PROGRAM)
    scope_config = next((c for c in scope_configs if c["configuration"] == SCOPE_CONFIG), None)
    scope_admin_authority = scope_config["admin"] if scope_config else None
    notes.append(f"Scope Configuration({SCOPE_CONFIG}).admin = {scope_admin_authority}")

    scope_prog = sol_read.read_program(url, SCOPE_PROGRAM)
    scope_upgrade_authority = scope_prog.get("upgrade_authority")
    notes.append(f"Scope program.upgrade_authority = {scope_upgrade_authority}")

    # klend/Scope UPGRADE authorities are a genuine loader-v3 `Option<Pubkey>`
    # -- None there means renounced (the safest state). market_owner/Scope-
    # admin are fixed-size fields inside a zero-copy account, never actually
    # absent on-chain; a None there only ever means the read itself failed,
    # so none_means_renounced stays False (the default) for those two paths.
    klend_sq = _resolve_squads_v4(url, "klend upgrade", klend_authority, KLEND_UPGRADE_MS, notes, none_means_renounced=True)
    market_sq = _resolve_squads_v4(url, "market owner", market_owner_authority, MARKET_OWNER_MS, notes)
    scope_admin_sq = _resolve_squads_v4(url, "Scope admin", scope_admin_authority, SCOPE_ADMIN_MS, notes)
    scope_upgrade_sq = _resolve_squads_v4(url, "Scope upgrade", scope_upgrade_authority, SCOPE_UPGRADE_MS, notes, none_means_renounced=True)

    all_resolved = all(sq is not None for sq in (klend_sq, market_sq, scope_admin_sq, scope_upgrade_sq))
    signers = set()
    for sq in (klend_sq, market_sq, scope_admin_sq, scope_upgrade_sq):
        if sq and sq != RENOUNCED:
            signers |= {m["key"] for m in sq["member_list"]}

    if all_resolved:
        def _path(sq):
            if sq == RENOUNCED:
                return 100, 100, 100
            return _score_full_power_path("squads_v4", threshold=sq["threshold"],
                                           voters=_voters_with_vote_permission(sq), delay_s=sq["time_lock_s"])

        def _describe(label, sq):
            if sq == RENOUNCED:
                return f"{label} renounced (no upgrade authority)"
            return f"{label} {sq['threshold']}-of-{sq['members']} delay={sq['time_lock_s']}s"

        klend_path = _path(klend_sq)
        market_path = _path(market_sq)
        scope_admin_path = _path(scope_admin_sq)
        scope_upgrade_path = _path(scope_upgrade_sq)

        admin_key = min(klend_path[0], market_path[0])
        multisig = min(klend_path[1], market_path[1])
        timelock = min(klend_path[2], market_path[2])

        oracle_composites = {
            "market-owner oracle modes": _composite(*market_path),
            "Scope admin (price re-map)": _composite(*scope_admin_path),
            "Scope program upgrade": _composite(*scope_upgrade_path),
        }
        oracle_authority = min(oracle_composites.values())
        notes.append(f"oracleAuthorityScore = min({oracle_composites}) = {oracle_authority}")
        notes.append(
            f"{_describe('klend upgrade', klend_sq)} ; "
            f"{_describe('market owner', market_sq)} ; "
            f"{_describe('Scope admin', scope_admin_sq)} "
            f"(instant re-map of the price source this market's SOL/USDC reserves read) ; "
            f"{_describe('Scope upgrade', scope_upgrade_sq)}"
        )
    else:
        admin_key, multisig, timelock, oracle_authority = 20, 20, 0, 20
        notes.append(
            "One or more authority chains did not resolve/match this run (an upgrade_authority/admin read "
            "failed, or an offline PDA re-derivation did not match its hardcoded multisig candidate) -- "
            "scores degraded, treat as unverified rather than trusting a stale identification"
        )

    return {
        "target": MARKET, "label": "Kamino Lend (main market, SOL/BTC)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": oracle_authority, "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def _resolve_squads_v3(url, label, authority, ms_candidate, notes, authority_index=1, none_means_renounced=False):
    """Same discipline as `_resolve_squads_v4` for a Squads v3 ('squads-mpl')
    authority PDA: offline-re-derive `authority_index`'s PDA of `ms_candidate`
    and require an exact match with the live-read `authority`. Squads v3 has
    no `config_authority`/`time_lock` fields at all (METHODOLOGY.md 3.4), so
    there is nothing to guard against there, unlike the v4 case.

    `none_means_renounced=True` (program-upgrade call sites only) returns the RENOUNCED sentinel for an
    authority of None: a loader-v3 upgrade authority that is `Option::None` is the SAFEST state
    (METHODOLOGY.md 6.1), not a failed read. Fixed 2026-09-20, the same fix the v4 helper got on
    2026-09-17."""
    if authority is None and none_means_renounced:
        notes.append(f"{label}: upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1, not a failed read")
        return RENOUNCED
    derived = sol_read.read_squadsv3(url, ms_candidate, authority_index=authority_index).get(f"authority_{authority_index}")
    matched = authority is not None and derived == authority
    notes.append(
        f"{label}: offline authority_{authority_index} PDA of candidate Squads v3 Ms {ms_candidate} = {derived} "
        f"(expected live authority {authority}) -- {'MATCH' if matched else 'MISMATCH, degrading'}"
    )
    if not matched:
        return None
    return sol_read.read_squadsv3(url, ms_candidate, authority_index=authority_index)


def score_raydium(url) -> dict:
    """Raydium (AMM v4, CLMM, CPMM, LaunchLab share one upgrade authority).
    Surfaced by `chains/solana/data/scouted_targets_2026-09-17-run2.md`
    (target #1, upper-bound composite 43) -- this function closes that
    file's own "decode Raydium AMM config" open point by finding and
    scoring a SECOND, SEPARATE, WEAKER full-power path this project's own
    minimum-over-paths convention (METHODOLOGY.md 6.2) requires.

    Two full-power paths, both re-derived live every run, not replayed
    from a prior scouting pass:

      1. **Program upgrade authority** -- ALL THREE programs (AMM v4,
         CLMM, CPMM) share ONE Squads v4 vault (`tr8rgazUrZzgdkfc6Q622nV
         JHMMzh29trdBE2uBHb4u`, vault 0), 3-of-4, no delay. Each program's
         own `upgrade_authority` is independently re-checked against this
         same candidate every run (not assumed identical because it was
         true once).
      2. **`admin::ID`** -- a Rust constant compiled into all three
         programs (`raydium-clmm`, `raydium-cp-swap`, `raydium-amm`'s
         `lib.rs`/`processor.rs`, confirmed identical across all three by
         direct GitHub source comparison), gating `create_amm_config`/
         `update_amm_config` (trade/protocol/fund fee rates, and
         reassigning `owner`/`fund_owner` outright) plus `update_pool_
         status` (a protocol-wide pause-equivalent) and `transfer_reward_
         owner` on CLMM -- confirmed FULL-POWER, not bounded, by reading
         the actual instruction source (`update_amm_config.rs`'s
         `#[account(address = crate::admin::ID)]` gate covers the whole
         instruction, not just a fee-collection sub-case). Unlike the
         upgrade authority, this constant is invisible to a plain account
         read (METHODOLOGY.md 6.2's own "hardcoded keys" caveat) -- but
         CLMM's on-chain Anchor IDL DOES expose it, as the fixed `owner`/
         `authority` account on several instructions
         (`sol_read.read_anchor_idl`'s own `hardcoded_addresses`
         mechanism, built for exactly this case), so this is read LIVE
         from the chain every run, not hardcoded from a citation.

         This constant resolves to a Squads v3 Ms account (`EXZY7FPccNuE
         vgHZMCMpww2Fen8oLWBSJzdgCsX3Djwm`, authority index 1), 2-of-3 --
         genuinely WEAKER than the 3-of-4 upgrade path, and NOT the same
         multisig: this is the SAME Ms account that used to hold the
         program's own upgrade authority before a 2026-04-22 rotation to
         the current Squads v4 vault (see `data/finding_2026-09-17-...`
         reference in the scouting file's own "What changed" table) --
         retired for CODE upgrades, but never rotated for this
         config-admin role.

    NOT scored as full-power (bounded, per METHODOLOGY.md 6.2's own
    example list): CLMM's `AmmConfig.owner`/`fund_owner` and CPMM's
    `AmmConfig.protocol_owner`/`fund_owner` fields -- all four gate only
    `collect_protocol_fee`/`collect_fund_fee` (withdraw already-accrued
    fees), confirmed by reading those instructions' own account
    constraints, not the fee-RATE-setting power `admin::ID` alone holds.
    AMM v4's `pnl_owner`/`cancel_owner` are pre-Anchor legacy fields with
    the same bounded shape. Not independently enumerated here since they
    can only ever raise, never lower, the published composite.

    Not re-checked this pass: LaunchLab (`LanMV9sAd7wArD4vJFi2qDdfnVhFxYS
    Ug6eADduJ3uj`), the 4th program the original scouting listed as
    sharing this same upgrade authority -- not verified here to still
    share it, nor checked for its own admin::ID-equivalent constant.
    Disclosed rather than assumed; would need its own pass to fold in."""
    RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    RAYDIUM_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
    RAYDIUM_CPMM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
    UPGRADE_MS = "tr8rgazUrZzgdkfc6Q622nVJHMMzh29trdBE2uBHb4u"
    ADMIN_MS = "EXZY7FPccNuEvgHZMCMpww2Fen8oLWBSJzdgCsX3Djwm"
    notes = []
    signers = set()

    upgrade_authorities = {}
    for label, prog_id in (("AMM v4", RAYDIUM_AMM_V4), ("CLMM", RAYDIUM_CLMM), ("CPMM", RAYDIUM_CPMM)):
        prog = sol_read.read_program(url, prog_id)
        upgrade_authorities[label] = prog.get("upgrade_authority")
        notes.append(f"{label} program.upgrade_authority = {upgrade_authorities[label]}")
    if len(set(upgrade_authorities.values())) != 1:
        raise ValueError(f"Raydium programs' upgrade authorities diverged this run -- {upgrade_authorities}, aborting rather than scoring a stale 'they're all the same' assumption")

    upgrade_sq = _resolve_squads_v4(url, "shared program upgrade", next(iter(upgrade_authorities.values())), UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"shared program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    idl = sol_read.read_anchor_idl(url, RAYDIUM_CLMM)
    hardcoded = {(h["instruction"], h["account"]): h["address"] for h in idl["hardcoded_addresses"]}
    admin_id = hardcoded.get(("update_amm_config", "owner"))
    notes.append(f"CLMM on-chain Anchor IDL: update_amm_config.owner fixed address (admin::ID) = {admin_id}")
    if admin_id is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
        notes.append("admin::ID not found in the live on-chain IDL this run -- degraded rather than trusting a hardcoded citation")
    else:
        ms3 = _resolve_squads_v3(url, "admin::ID", admin_id, ADMIN_MS, notes)
        if ms3 is None:
            admin_b, multisig_b, timelock_b = 20, 20, 0
        else:
            admin_b, multisig_b, timelock_b = _score_full_power_path("squads_v3", threshold=ms3["threshold"], voters=ms3["n_keys"])
            signers |= set(ms3["keys"])
            notes.append(f"admin::ID Squads v3: {ms3['threshold']}-of-{ms3['n_keys']}, no time-lock field")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": RAYDIUM_CLMM, "label": "Raydium (AMM v4, CLMM, CPMM)",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_marginfi(url) -> dict:
    """marginfi, main flagship lending group. Surfaced by `chains/solana/
    data/scouted_targets_2026-09-17-run2.md` (target #4, upper-bound
    composite 54) -- this function closes that file's own "decode
    MarginfiGroup.admin" open point, finding a SEPARATE, WEAKER full-power
    path than the upper bound assumed (which only had the program upgrade
    authority to go on).

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- Squads v4 vault
         `J3oBkTkDXU3TcAggJEa3YeBZE5om5yNAdTtLVNXFD47` (vault 0 of
         multisig `7FCPipJWVbPbdHymVt1gJYwKciakkJz5GahdQySemvHk`),
         7-of-15, all 15 members have Vote permission, no delay.
      2. **`MarginfiGroup.admin`** -- a DIFFERENT Squads v4 vault
         (`CYXEgwbPHu2f9cY3mcUkinzDoDcsSan7myh1uBvYRbEw`, vault 0 of
         multisig `74QKjjvoSrq2cGqFzzQNN8ox3gomYS1mBwcLsbiYaH8j`),
         5-of-17 (15 of 17 listed members have Vote permission), no
         delay -- genuinely a DIFFERENT multisig account (different
         address, different create_key, not the same vault reused).
         Decoded from the account's first field after its 8-byte Anchor
         discriminator (`admin: pubkey`, confirmed via the live on-chain
         IDL's own field-order listing for `MarginfiGroup`, not assumed
         from source alone) -- this is marginfi's real protocol-parameter
         admin (bank risk configs, interest curves, etc. all route
         through `MarginfiGroup.admin`-gated instructions per
         mrgnlabs/marginfi-v2's own `group_admin.rs`).

    Honest caveat on path independence, added after an adversarial review
    (2026-09-18) caught this project's own first draft understating it:
    despite being a genuinely separate multisig, `ADMIN_MS`'s membership
    is NOT an independent governing body -- live-verified every run
    below, all 15 Vote-permissioned members of `UPGRADE_MS` (the 7-of-15
    upgrade path) are a STRICT SUBSET of `ADMIN_MS`'s 17 members. The 2
    extra members carry mask=0 (no permissions at all) and mask=1
    (Initiate-only, cannot Vote or Execute). So the "second full-power
    path" is, in practice, the identical governing body voting under a
    lower bar (5-of-15 effective, vs. 7-of-15) rather than two distinct
    sets of people cross-checking each other -- which is exactly why the
    per-dimension minimum already picks it up as the binding constraint.
    This does not change the composite (the threshold/voter counts used
    were always read correctly), only the honesty of what "two paths"
    means here.

    NOT decoded this pass (disclosed, not folded in -- see `sol_read.
    read_marginfi_group`'s own docstring): SEVEN more admin-named fields
    the same on-chain IDL lists on `MarginfiGroup` (`emode_admin`,
    `delegate_curve_admin`, `delegate_limit_admin`, `delegate_emissions_
    admin`, `risk_admin`, `metadata_admin`, `delegate_flow_admin`) --
    their byte offsets depend on resolving several nested `defined` types
    first (`FeeStateCache`, `PanicStateCache`, `WithdrawWindowCache`,
    `GroupRateLimiter`), not done this pass. Per METHODOLOGY.md 6.2, any
    of these could only LOWER the composite below what is published
    here, never raise it -- this function's own output is itself still an
    upper bound, now a tighter one than the original scouting pass, not a
    final number."""
    MARGINFI_PROGRAM = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
    MAIN_GROUP = "4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8"
    UPGRADE_MS = "7FCPipJWVbPbdHymVt1gJYwKciakkJz5GahdQySemvHk"
    ADMIN_MS = "74QKjjvoSrq2cGqFzzQNN8ox3gomYS1mBwcLsbiYaH8j"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, MARGINFI_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v4(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    group = sol_read.read_marginfi_group(url, MAIN_GROUP)
    group_admin = group["admin"]
    notes.append(f"MarginfiGroup({MAIN_GROUP}).admin = {group_admin}")
    admin_sq = _resolve_squads_v4(url, "MarginfiGroup.admin", group_admin, ADMIN_MS, notes)
    if admin_sq is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        admin_b, multisig_b, timelock_b = _score_full_power_path(
            "squads_v4", threshold=admin_sq["threshold"], voters=_voters_with_vote_permission(admin_sq), delay_s=admin_sq["time_lock_s"])
        signers |= {m["key"] for m in admin_sq["member_list"]}
        notes.append(f"MarginfiGroup.admin Squads v4: {admin_sq['threshold']}-of-{admin_sq['members']} delay={admin_sq['time_lock_s']}s -- a DIFFERENT multisig account than the program upgrade authority")

        if admin_sq not in (None, RENOUNCED) and upgrade_sq not in (None, RENOUNCED):
            upgrade_voters = {m["key"] for m in upgrade_sq["member_list"] if m["mask"] & 2}
            admin_voters = {m["key"] for m in admin_sq["member_list"] if m["mask"] & 2}
            if upgrade_voters and upgrade_voters <= admin_voters:
                notes.append(
                    f"caveat: all {len(upgrade_voters)} Vote-permissioned members of the upgrade "
                    f"multisig are a SUBSET of the admin multisig's {len(admin_voters)} voters -- "
                    "same governing body voting under a lower threshold, not an independent "
                    "second check, even though the two multisig accounts are genuinely distinct")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": MAIN_GROUP, "label": "marginfi (main lending group)",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_kamino_liquidity(url) -> dict:
    """Kamino Liquidity (yvaults), the automated-strategy vault product --
    a SEPARATE Kamino program from `score_kamino_lend`'s own klend market,
    with its own authority chain. Surfaced by `chains/solana/data/
    scouted_targets_2026-09-17-run2.md` (target #14, upper-bound composite
    77) -- closes that file's own "decode Kamino strategy admin" open
    point, finding a SEPARATE, WEAKER full-power path.

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- a Squads v4 vault (vault index
         0 of multisig `E7994UpSGhSpbpnuSepPXHBuMy3eRvHJL36DjTs1kb2b`),
         5-of-7, **24h delay**.
      2. **`GlobalConfig.adminAuthority`** -- a DIFFERENT Squads v4 vault
         (`5dcEb1jGeBZuXbVKmNkq3unPcrveG46B2PMJKAGcSh67`, vault 0 of
         multisig `HvYoRSJdVcj6WRWV57yLu2Vmwh1ccqJRdkCwhNsSfRu4`), SAME
         5-of-7 threshold shape but **ZERO delay** -- the SAME weakness
         pattern this project's own Kamino Lend scorer already found
         between its own market-owner and Scope-admin paths (one delayed
         path, a same-signer-shape path with no delay at all). Decoded
         at a byte offset computed field-by-field from Kamino-Finance's
         own published Codama codec source (`sol_read.
         read_kliquidity_global_config`'s own docstring), independently
         confirmed against a raw byte-presence search of the live
         account, not guessed.

    Since the two paths have the IDENTICAL threshold/voter shape (5-of-7),
    adminKeyScore and multisigScore are unaffected by this finding --
    only timelockScore changes, from the upgrade path's 24h-delay band
    down to the admin path's zero-delay band, since METHODOLOGY.md 6.2
    takes the minimum per DIMENSION, not per path as a whole.

    NOT decoded this pass (disclosed, not folded in): `GlobalConfig.
    actionsAuthority`, the field immediately BEFORE `adminAuthority` in
    the same struct -- name suggests an operational/keeper role (compare
    Hyperliquid's own MANAGER_ROLE-triggers-batch-processing pattern),
    not chased this pass. `pendingAdmin` (a proposed-but-not-yet-accepted
    transfer target, not a live authority) and `emergencyCouncil`/
    `unfreezeAuthority` (named, by Kamino's own doc-comment on the
    latter, as a "may only unset emergency/block flags" role -- restrict-
    only per METHODOLOGY.md 6.2's own definition, not full-power) are
    also present on this struct but not scored, matching this project's
    existing convention of not force-fitting restrict-only paths into
    the full-power minimum."""
    KLIQUIDITY_PROGRAM = "6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc"
    GLOBAL_CONFIG = "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB"
    UPGRADE_MS = "E7994UpSGhSpbpnuSepPXHBuMy3eRvHJL36DjTs1kb2b"
    ADMIN_MS = "HvYoRSJdVcj6WRWV57yLu2Vmwh1ccqJRdkCwhNsSfRu4"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, KLIQUIDITY_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v4(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    gc = sol_read.read_kliquidity_global_config(url, GLOBAL_CONFIG)
    admin_authority = gc["admin_authority"]
    notes.append(f"GlobalConfig({GLOBAL_CONFIG}).adminAuthority = {admin_authority}")
    admin_sq = _resolve_squads_v4(url, "GlobalConfig.adminAuthority", admin_authority, ADMIN_MS, notes)
    if admin_sq is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        admin_b, multisig_b, timelock_b = _score_full_power_path(
            "squads_v4", threshold=admin_sq["threshold"], voters=_voters_with_vote_permission(admin_sq), delay_s=admin_sq["time_lock_s"])
        signers |= {m["key"] for m in admin_sq["member_list"]}
        notes.append(f"GlobalConfig.adminAuthority Squads v4: {admin_sq['threshold']}-of-{admin_sq['members']} delay={admin_sq['time_lock_s']}s -- a DIFFERENT multisig than the program upgrade authority, same shape but NO delay")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": GLOBAL_CONFIG, "label": "Kamino Liquidity (yvaults)",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_jupiter_perps(url) -> dict:
    """Jupiter Perpetual Exchange. Surfaced by `chains/solana/data/
    scouted_targets_2026-09-17-run2.md` (target #12, upper-bound composite
    69) -- closes that file's own "decode Jupiter Perps admin" open point,
    finding a SEPARATE, materially WEAKER full-power path.

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- Squads v4 vault
         `5myNNmEmPm3UAnJ2ggLEpnTFb9t9Gk8369wKw6n3uAKx` (vault 0 of
         multisig `AxkJ8oH5aDu4ZRWfsujPtxdb6Vhq4gDehpoReBgrUUSm`), 4-of-8,
         **24h delay**.
      2. **`Perpetuals.admin`** -- a Squads v3 Ms account
         (`7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf`, authority index
         1), 4-of-7, **no time-lock field at all** (Squads v3 has none) --
         this is the SAME multisig that used to be Jupiter Aggregator
         v6's own upgrade authority before Jupiter's broader migration to
         Squads v4 (see `score_jupiter_aggregator_v6`'s own docstring) --
         retired for that program's code upgrades, but still holds real,
         live power here as the perp exchange's own application-level
         admin. Decoded at offset 51 of the compact 120-byte `Perpetuals`
         account (`sol_read.read_jupiter_perpetuals`), confirmed via raw
         byte presence (conclusive at this account size).

    Genuinely weaker on BOTH threshold (4-of-7 vs 4-of-8, though the
    admin/multisig formula only cares about voter COUNT, not n, so this
    barely moves those two numbers) and, decisively, on delay -- the
    24h-timelock upgrade path's own protection is fully bypassed by an
    admin path with zero notice at all.

    Not scored (informational, disclosed not chased further): the
    'Doves' oracle program (`DoVEsk76QybCEHQGzkvYPWLQu9gzNoZZZt3TPiL597e`)
    referenced by this project's own prior scouting turned out, on
    checking, to share the SAME Squads v4 vault as this program's own
    upgrade authority -- not an independent finding, so not folded in as
    a separate path; METHODOLOGY.md 6.3's oracle-authority treatment for
    this target remains an open point regardless."""
    JUPITER_PERPS_PROGRAM = "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu"
    PERPETUALS = "H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj"
    UPGRADE_MS = "AxkJ8oH5aDu4ZRWfsujPtxdb6Vhq4gDehpoReBgrUUSm"
    ADMIN_MS = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, JUPITER_PERPS_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v4(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    perp = sol_read.read_jupiter_perpetuals(url, PERPETUALS)
    perp_admin = perp["admin"]
    notes.append(f"Perpetuals({PERPETUALS}).admin = {perp_admin}")
    admin_sq = _resolve_squads_v3(url, "Perpetuals.admin", perp_admin, ADMIN_MS, notes)
    if admin_sq is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        admin_b, multisig_b, timelock_b = _score_full_power_path("squads_v3", threshold=admin_sq["threshold"], voters=admin_sq["n_keys"])
        signers |= set(admin_sq["keys"])
        notes.append(f"Perpetuals.admin Squads v3: {admin_sq['threshold']}-of-{admin_sq['n_keys']}, no time-lock field -- a DIFFERENT, older multisig than the program upgrade authority")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": PERPETUALS, "label": "Jupiter Perpetual Exchange",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_jupiter_lend(url) -> dict:
    """Jupiter Lend (liquidity, lending, vaults, oracle -- 4 programs).
    Surfaced by `chains/solana/data/scouted_targets_2026-09-17-run2.md`
    (target #13, upper-bound composite 60, the largest-TVL target in that
    whole scouting pass at >$900M) -- closes that file's own "decode
    Jupiter Lend admin" open point, finding a SEPARATE, weaker full-power
    path shared by all four programs' own application-level admin
    accounts.

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- ALL FOUR programs share ONE
         Squads v4 vault (`4MsgBB5VPoTrUSp5XnfbViV386C1UnsTdifLBw33ZMSJ`,
         vault 0 of multisig `J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P`),
         4-of-6, **12h delay**.
      2. **The `Liquidity` program's own `Liquidity.authority` field**
         (and, per this project's own prior scouting, the SAME address on
         the lending/vaults/oracle programs' own equivalent top-level
         admin accounts too, not independently re-verified for all three
         here) -- a DIFFERENT Squads v4 vault
         (`HqPrpa4ESBDnRHRWaiYtjv4xe93wvCS9NNZtDwR89cVa`, vault 0 of
         multisig `5Y93cxqp8rGtjDhxGkehewfhFdxLkrCfPDWookCGeASF`), 5-of-10,
         **6h delay** -- a lower threshold-and-voter shape AND a shorter
         delay than the upgrade path. Decoded from the Liquidity
         program's own published Anchor IDL (`target/idl/liquidity.json`
         in jup-ag/jupiter-lend), `authority` confirmed as the literal
         first field after the discriminator.

    NOT independently re-derived this pass for the lending/vaults/oracle
    programs' own admin accounts (`LendingAdmin`/`VaultAdmin`/
    `OracleAdmin`) -- this project's own prior scouting pass reported the
    identical vault address for all three, but only the `Liquidity`
    program's own account was re-checked byte-for-byte here. Disclosed,
    not assumed identical without having read it -- would need its own
    pass to independently confirm the other three, though even if they
    diverged, they could only ever match or be WEAKER than this vault,
    never stronger, so this function's own output remains a valid (if
    possibly still-not-final) tighter bound.

    NOT decoded this pass: the `AuthorizationList` account (`auth_users`/
    `guardians` fields) this same program's IDL also defines -- name
    suggests a possible restrict-only/emergency-response role, not
    chased further."""
    LIQUIDITY_PROGRAM = "jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC"
    LIQUIDITY_ACCOUNT = "7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z"
    UPGRADE_MS = "J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P"
    ADMIN_MS = "5Y93cxqp8rGtjDhxGkehewfhFdxLkrCfPDWookCGeASF"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, LIQUIDITY_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"liquidity program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v4(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    liq = sol_read.read_jupiter_lend_liquidity(url, LIQUIDITY_ACCOUNT)
    liq_authority = liq["authority"]
    notes.append(f"Liquidity({LIQUIDITY_ACCOUNT}).authority = {liq_authority}")
    admin_sq = _resolve_squads_v4(url, "Liquidity.authority", liq_authority, ADMIN_MS, notes)
    if admin_sq is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        admin_b, multisig_b, timelock_b = _score_full_power_path(
            "squads_v4", threshold=admin_sq["threshold"], voters=_voters_with_vote_permission(admin_sq), delay_s=admin_sq["time_lock_s"])
        signers |= {m["key"] for m in admin_sq["member_list"]}
        notes.append(f"Liquidity.authority Squads v4: {admin_sq['threshold']}-of-{admin_sq['members']} delay={admin_sq['time_lock_s']}s -- a DIFFERENT multisig than the program upgrade authority")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": LIQUIDITY_ACCOUNT, "label": "Jupiter Lend",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_pumpswap(url) -> dict:
    """PumpSwap (and the pump.fun bonding-curve program it succeeds).
    Surfaced by `chains/solana/data/scouted_targets_2026-09-17-run2.md`
    (target #8, upper-bound composite 43) -- closes that file's own
    "decode PumpSwap GlobalConfig admin" open point. Unlike several other
    targets in this same batch, this ONE does NOT reveal a weaker
    separate path -- it confirms the upper bound as the real, final
    score, via a genuinely different (not reused) multisig of the
    identical shape.

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- BOTH programs (PumpSwap AMM and
         the pump.fun bonding curve) share ONE Squads v4 vault
         (`7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8`, vault 0 of
         multisig `2yMoQqQrtbhq3nQ3wFoQQawWS65qcqUXcwHEYha4rshW`), 3-of-4,
         no delay.
      2. **`GlobalConfig.admin`** (PumpSwap) and **`Global.authority`**
         (the bonding curve) -- BOTH fields resolve to the SAME vault
         (`FFWtrEQ4B4PKQoVuHYzZq8FabGkVatYzDpEVHsK5rrhF`, vault 0 of
         multisig `8EujzwPFNhZ5m4Kpa2XtrumNgwCbhgWwny9YWLCKA5at`), a
         GENUINELY DIFFERENT multisig account than the upgrade authority
         above -- but the SAME 3-of-4 shape, so the score is unaffected.
         Both application-level fields confirmed identical via a real
         on-chain Anchor IDL (`GlobalConfig.admin` is the literal first
         field), and a live transaction (same Squads v4 execute updated
         both fields together) further confirms this isn't a
         coincidental shape match."""
    PUMPSWAP_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    GLOBAL_CONFIG = "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"
    UPGRADE_MS = "2yMoQqQrtbhq3nQ3wFoQQawWS65qcqUXcwHEYha4rshW"
    ADMIN_MS = "8EujzwPFNhZ5m4Kpa2XtrumNgwCbhgWwny9YWLCKA5at"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, PUMPSWAP_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"PumpSwap program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v4(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    gc = sol_read.read_pumpswap_global_config(url, GLOBAL_CONFIG)
    gc_admin = gc["admin"]
    notes.append(f"GlobalConfig({GLOBAL_CONFIG}).admin = {gc_admin}")
    admin_sq = _resolve_squads_v4(url, "GlobalConfig.admin", gc_admin, ADMIN_MS, notes)
    if admin_sq is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        admin_b, multisig_b, timelock_b = _score_full_power_path(
            "squads_v4", threshold=admin_sq["threshold"], voters=_voters_with_vote_permission(admin_sq), delay_s=admin_sq["time_lock_s"])
        signers |= {m["key"] for m in admin_sq["member_list"]}
        notes.append(f"GlobalConfig.admin Squads v4: {admin_sq['threshold']}-of-{admin_sq['members']} delay={admin_sq['time_lock_s']}s -- a DIFFERENT multisig than the program upgrade authority, same shape")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": GLOBAL_CONFIG, "label": "PumpSwap (and pump.fun bonding curve)",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


# Meteora DAMM v2's ADMINS[] pair is a Rust compile-time constant compared
# via #[access_control(is_admin(...))] on create_operator_account/close_
# operator_account -- NOT an `#[account(address=...)]` constraint, so it
# is invisible to sol_read.read_anchor_idl's own hardcoded_addresses
# mechanism (confirmed live 2026-09-18: fetched the on-chain IDL, none of
# its 20 hardcoded addresses relate to admin/operator). METHODOLOGY.md
# 6.2's own disclosed exception for this exact situation ("Hardcoded
# authority keys compiled into a binary are invisible to account reads")
# applies -- hardcoded here from MeteoraAg/damm-v2's own verified GitHub
# source (programs/cp-amm/src/instructions/admin/auth.rs), not derivable
# live by any other means this project has.
METEORA_DAMM_V2_ADMINS = (
    "5unTfT2kssBuNvHPY6LbJfJpLqEcdMxGYLWHwShaeTLi",
    "DHLXnJdACTY83yKwnUkeoDjqi4QBbsYGa1v8tJL76ViX",
)


def score_meteora_damm_v2(url) -> dict:
    """Meteora DAMM v2 (the newest of Meteora's three DEX programs;
    DLMM and DAMM v1 are NOT scored here -- see this function's own
    "Honest limitations" paragraph). Surfaced by `chains/solana/data/
    scouted_targets_2026-09-17-run2.md` (target #7, upper-bound composite
    47) -- closes that file's own "decode Meteora admin" open point with
    the single most severe finding in this whole batch: a full-power path
    dramatically weaker than the already-known upgrade authority.

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- Squads v3 Ms account
         `CoEsykatDegLB7pcMJia79JSriDdi71nPnjgeSfw623k`, authority index
         1, 4-of-7.
      2. **`ADMINS[]`** -- a hardcoded, compile-time constant array of
         TWO bare on-curve EOAs (`METEORA_DAMM_V2_ADMINS` above),
         OR-gated (`ADMINS.iter().any(...)` in `auth.rs` -- either key
         ALONE is sufficient, no threshold at all), confirmed by reading
         the actual instruction source: `is_admin()` gates
         `create_operator_account`/`close_operator_account`, the ONLY
         two functions the program's own source comments literally label
         "ADMIN FUNCTIONS". Every other privileged action (`create_
         config`, `create_dynamic_config`, `create_token_badge`, `set_
         pool_status`, `update_pool_fees`) is gated one level down by
         `is_valid_operator_role`, checking a per-permission `Operator`
         PDA -- but that PDA's own `whitelisted_address` and `permission`
         bits can ONLY be set by an `ADMINS[]` key in the first place, so
         `ADMINS[]` is the true root of the whole permission tree, not a
         narrower or bounded role. Scored via `_score_full_power_path
         ("on_curve", ...)` -- the same floor this project already uses
         for ANY bare single key or t=1 multisig, since the practical
         barrier to compromise is exactly one private key either way.

    The two paths could not be more different: neither multisig member
    list nor threshold nor delay softens `ADMINS[]`'s own worst-case
    floor -- `compositeScore` collapses to near-zero, the same CRITICAL
    band as this project's own Kinetiq/`para` StakingVault findings on
    the Hyperliquid side of this project, for the identical underlying
    reason (a single compromised key, not a coordinated multisig, is
    sufficient to seize the whole permission system).

    Honest limitations -- why DLMM and DAMM v1 are NOT scored here even
    though they very likely share this same risk:

    Transaction-forensic evidence (not source-level, since neither
    program's real on-chain Rust logic is public -- `damm-v1-sdk`'s own
    published `lib.rs` has every instruction handler stubbed to
    `Ok(())`, and `dlmm-sdk` ships no `programs/` directory at all)
    strongly suggests the SAME two `ADMINS[]` keys control equivalent
    root-admin roles on both other Meteora programs: `5unTfT2...` is the
    creator of a real DAMM v1 pool-fee `Config` account, and `DHLXnJd...`
    is the signer who created a DLMM `Operator` PDA. Both facts are real
    and independently checkable, but circumstantial -- a transaction
    signer is not proof of the underlying access-control LOGIC the way
    reading real source is (this project's own earlier CoreWriter/
    Kinetiq overclaim on the Hyperliquid side, since corrected, is the
    exact "transaction evidence isn't source-level proof" lesson this
    disclosure applies here). DLMM and DAMM v1 remain at their prior
    upper-bound composite (47) pending either program's real source
    becoming available to read, rather than force a specific number this
    project cannot fully defend."""
    METEORA_DAMM_V2_PROGRAM = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
    UPGRADE_MS = "CoEsykatDegLB7pcMJia79JSriDdi71nPnjgeSfw623k"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, METEORA_DAMM_V2_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v3(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path("squads_v3", threshold=upgrade_sq["threshold"], voters=upgrade_sq["n_keys"])
        signers |= set(upgrade_sq["keys"])
        notes.append(f"program upgrade Squads v3: {upgrade_sq['threshold']}-of-{upgrade_sq['n_keys']}, no time-lock field")

    admin_b, multisig_b, timelock_b = _score_full_power_path("on_curve")
    signers |= set(METEORA_DAMM_V2_ADMINS)
    notes.append(
        f"ADMINS[] (hardcoded compile-time constant, MeteoraAg/damm-v2 programs/cp-amm/src/instructions/admin/auth.rs, "
        f"NOT derivable from any live account read): {METEORA_DAMM_V2_ADMINS} -- OR-gated, either key alone gates "
        f"create_operator_account/close_operator_account, the root of the entire permission tree -> "
        f"adminKey={admin_b} multisig={multisig_b} timelock={timelock_b}"
    )

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": METEORA_DAMM_V2_PROGRAM, "label": "Meteora DAMM v2",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_orca_whirlpool(url) -> dict:
    """Orca Whirlpool. Surfaced by `chains/solana/data/scouted_targets_
    2026-09-17-run2.md` (target #2, upper-bound composite 76) -- closes
    that file's own "decode Whirlpools config authorities" open point,
    finding a THIRD authority on the same `WhirlpoolsConfig` account,
    dramatically weaker than the other two.

    `WhirlpoolsConfig` (exact layout confirmed from orca-so/whirlpools'
    own Rust source, `sol_read.read_whirlpools_config`) holds THREE
    authority fields:

      1. **`fee_authority`** -- resolves to the SAME Squads v4 vault as
         the program's own upgrade authority (`GwH3Hiv5mACLX3ufTw1pFsrhS
         Pon5tdw252DBs4Rx4PV`, vault 0 of multisig `BQsDWkL417U4tVE2sDnP
         ks469pKdm6YzFgKH77doiEjF`), 5-of-13 (9 with Vote permission),
         **24h delay**. Not an independent path -- the same multisig,
         confirmed live, not assumed.
      2. **`collect_protocol_fees_authority`** -- a bare on-curve EOA.
         NOT scored as full-power: confirmed by reading the actual
         instruction source (`collect_protocol_fees.rs`) that this
         field ONLY gates withdrawing already-accrued protocol fees --
         bounded, per METHODOLOGY.md 6.2's own example list, matching
         the identical pattern already found and disclosed on the
         Raydium/Kamino side of this same batch.
      3. **`reward_emissions_super_authority`** -- a DIFFERENT Squads v4
         vault (`DXnB9N9JLH5c9AYdKMGHQyspewSsvhFnwLK1tz1iPmZw`, vault 0
         of multisig `5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN`),
         **1-of-8, no delay** -- scores identically to a bare single key
         per METHODOLOGY.md 6.1's own rule ("A Squads multisig... with a
         threshold of 1 scores as an on-curve key, whatever its member
         count or time lock").

    Classifying `reward_emissions_super_authority` as FULL-POWER, not
    bounded, is a judgment call this docstring makes explicit rather than
    silently assumes: reading the actual instruction source confirms it
    can unilaterally reassign the per-pool `reward_authority` field on
    ANY Whirlpool, for ANY pool, without that pool's current reward
    authority's consent (`set_reward_authority_by_super_authority.rs` --
    "Only the current reward emissions super authority has permission to
    invoke this instruction"); the resulting `reward_authority` can then
    directly set that pool's `emissions_per_second_x64`
    (`set_reward_emissions.rs`). Reward-token emission rate is a real
    economic parameter flowing value to every LP in a pool with active
    rewards -- closer to a risk/economic parameter (METHODOLOGY.md 6.2's
    own full-power language) than to the bounded "protocol-owned
    balances, fees, or not-yet-live assets" examples the same section
    gives. Disclosed as a judgment call, not a certainty, precisely so a
    future reviewer can push back on it with the same reasoning laid out
    here rather than having to re-derive it from scratch.

    With this classification, `reward_emissions_super_authority`
    dominates every dimension: `compositeScore` collapses from the
    76-upper-bound (driven by the 24h-delay, 5-of-13 `fee_authority`
    path alone) down to the same near-floor CRITICAL band this batch's
    Meteora DAMM v2 finding also lands on."""
    WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    WHIRLPOOLS_CONFIG = "2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ"
    UPGRADE_MS = "BQsDWkL417U4tVE2sDnPks469pKdm6YzFgKH77doiEjF"
    REWARD_SUPER_MS = "5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN"
    notes = []
    signers = set()

    prog = sol_read.read_program(url, WHIRLPOOL_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {upgrade_authority}")
    upgrade_sq = _resolve_squads_v4(url, "program upgrade", upgrade_authority, UPGRADE_MS, notes, none_means_renounced=True)
    if upgrade_sq is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_sq == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path(
            "squads_v4", threshold=upgrade_sq["threshold"], voters=_voters_with_vote_permission(upgrade_sq), delay_s=upgrade_sq["time_lock_s"])
        signers |= {m["key"] for m in upgrade_sq["member_list"]}
        notes.append(f"program upgrade Squads v4: {upgrade_sq['threshold']}-of-{upgrade_sq['members']} delay={upgrade_sq['time_lock_s']}s")

    cfg = sol_read.read_whirlpools_config(url, WHIRLPOOLS_CONFIG)
    notes.append(
        f"WhirlpoolsConfig({WHIRLPOOLS_CONFIG}): fee_authority={cfg['fee_authority']} "
        f"collect_protocol_fees_authority={cfg['collect_protocol_fees_authority']} (bounded -- fee collection only, not scored as full-power) "
        f"reward_emissions_super_authority={cfg['reward_emissions_super_authority']}"
    )
    reward_sq = _resolve_squads_v4(url, "reward_emissions_super_authority", cfg["reward_emissions_super_authority"], REWARD_SUPER_MS, notes)
    if reward_sq is None:
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        admin_b, multisig_b, timelock_b = _score_full_power_path(
            "squads_v4", threshold=reward_sq["threshold"], voters=_voters_with_vote_permission(reward_sq), delay_s=reward_sq["time_lock_s"])
        signers |= {m["key"] for m in reward_sq["member_list"]}
        notes.append(f"reward_emissions_super_authority Squads v4: {reward_sq['threshold']}-of-{reward_sq['members']} delay={reward_sq['time_lock_s']}s -- threshold=1 scores as a bare key per METHODOLOGY.md 6.1")

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": WHIRLPOOLS_CONFIG, "label": "Orca Whirlpool",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def _resolve_legacy_serum_multisig(url, label, authority, ms_candidate, notes, none_means_renounced=False):
    """Same offline-re-derivation discipline as `_resolve_squads_v3`/
    `_resolve_squads_v4`, for the old (2021-era) serum-style multisig shape
    (METHODOLOGY.md gap H1, closed here): PDA seeds are just the multisig
    account's own pubkey, and `bump` is not searched for, it IS the on-chain
    `nonce` field (`marinade-finance/multisig@v0.7.0`'s own
    `execute_transaction` re-derives it the same way). No config_authority/
    time_lock fields exist on this account type at all -- confirmed from the
    real source, not merely absent from what's decoded here.

    `none_means_renounced=True` (program-upgrade call site only): an upgrade authority of None is a renounced
    program, the safest band (METHODOLOGY.md 6.1), returned as the RENOUNCED sentinel rather than scored as a
    failed read. Fixed 2026-09-20."""
    if authority is None and none_means_renounced:
        notes.append(f"{label}: upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1, not a failed read")
        return RENOUNCED
    ms = sol_read.read_legacy_serum_multisig(url, ms_candidate)
    derived, bump = sol_read.find_program_address([sol_read.b58dec(ms_candidate)], MARINADE_MULTISIG_PROGRAM)
    bump_matches_nonce = bump == ms["nonce"]
    matched = authority is not None and derived == authority and bump_matches_nonce
    notes.append(
        f"{label}: offline PDA of candidate legacy multisig {ms_candidate} (seeds=[multisig], canonical bump={bump}, "
        f"stored nonce={ms['nonce']}) = {derived} (expected live authority {authority}) -- {'MATCH' if matched else 'MISMATCH, degrading'}"
    )
    if not matched:
        return None
    return ms


MARINADE_PROGRAM = "MarBmsSgKXdrN1egZf5sqe1TMai9K1rChYNDJgjq7aD"
MARINADE_MULTISIG_PROGRAM = "msigmtwzgXJHj2ext4XJjCDmpbcMuufFb5cHuwg6Xdt"


def score_marinade(url) -> dict:
    """Marinade Liquid Staking. Surfaced by `chains/solana/data/
    scouted_targets_2026-09-17-run2.md` (target #3, upper-bound composite
    54) -- this function closes that file's own "decode Marinade
    State.admin_authority" open point AND its "Methodology gap H1 (legacy
    serum-style multisig)" open point in the same pass, since both apply to
    this one target.

    Two full-power paths, both re-derived live every run:

      1. **Program upgrade authority** -- a 2021-era "serum-style" multisig
         (`marinade-finance/multisig`, a verbatim fork of the archived
         project-serum/multisig template; the multisig PROGRAM itself is
         immutable, its own upgrade authority burned in 2021 -- only the
         Marinade PROGRAM it controls is still live). Multisig account
         `magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed`, 6-of-13, no
         permission bitmask (any owner can sign) and NO timelock field
         anywhere in the struct (confirmed against the real source, not
         just absent from the decoded bytes) -- METHODOLOGY.md gap H1,
         closed here: this shape scores via the SAME zero-delay `squads_v3`
         formula (t-of-n, no new branch needed), since the two shapes are
         formula-identical (fixed threshold-of-members, zero enforced
         delay), not because they're the same program.
      2. **`State.admin_authority`** -- NOT a multisig at all: a
         Realms/SPL-Governance native-treasury PDA
         (`42VJbDihcS81YJPbuhHnHgvo1ehu42j8VK9sNwrnAarR`) of a dedicated
         Governance record in Marinade's own DAO deployment
         (`GovMaiHfpVPw8BAM1mbdzgmSZYDw2tdP32J2fapoQoYs`, realm "Marinade
         DAO"). This specific Governance record has COMMUNITY (MNDE
         token-holder) voting structurally DISABLED
         (`community_vote_threshold = Disabled`) -- only its COUNCIL can
         vote (`council_vote_threshold = YesVotePercentage(50%)`). The
         council mint's entire 5-token supply sits, as expected for
         spl-governance's normal deposit-pooling design, in the realm's own
         pooled holding PDA -- NOT evidence of concentration; the real
         voters are found one level deeper, in each member's own
         `TokenOwnerRecordV2`, enumerated live (not hardcoded) via
         `sol_read.list_token_owner_records`: 5 distinct owners, 1 token
         (1 vote) each, a genuine one-seat-per-member council (mirroring
         this project's own `data/finding_2026-09-17-spl-governance-
         shared-instance-controller.md` precedent and its exact `ceil(pct *
         total_weight)` method for turning a percentage threshold into a
         countable one: `ceil(0.50 * 5) = 3` -- an effective 3-of-5
         council).

    Classification judgment call, disclosed rather than silently made:
    `admin_authority` is scored as FULL-POWER, not bounded. It gates
    `ChangeAuthority` (single signature, no timelock, can reassign itself
    and every other top-level authority field on `State` at will) and
    `ConfigMarinade` (reward_fee, hard-capped <=10% by an in-code constant
    the admin cannot itself raise -- clearly bounded on its own). The
    full-power case rests on a TRANSITIVE path: `ChangeAuthority` lets
    `admin_authority` instantly self-grant `validator_system.
    manager_authority`, which then gates `SetValidatorScore` and
    `EmergencyUnstake`/`PartialUnstake` -- the ability to force-redirect up
    to 100% of ALL depositors' currently-staked SOL away from one validator
    per epoch. FOUND BY ADVERSARIAL REVIEW (2026-09-18), stronger than
    first written here: the per-epoch movement cap `admin_authority` also
    controls via `ConfigMarinade` has NO enforced ceiling at all -- real
    source (`config_marinade.rs`) explicitly comments out the >=100% check
    ("probably for some emergency case we need to move the same stake
    multiple times"), so this is not "raisable to 100%," there is no
    upper bound to raise it to. No instruction moves user PRINCIPAL to an
    admin-controlled
    address -- the only value admin can extract is the same hard-capped
    reward-fee skim -- so this is not a fund-custody bypass. But validator
    selection is the primary counterparty/slashing-risk determinant for a
    liquid-staking protocol, the closest real analogue this target has to
    METHODOLOGY.md 6.2's own full-power example of a "price source": it
    lets one signature redirect where real, live, already-deployed user
    value is exposed, not merely which fees get skimmed or which
    not-yet-live asset gets configured. A reviewer who weighs "SOL never
    technically leaves a Marinade-owned account" more heavily than the
    redirection power itself may reasonably classify this as bounded
    instead -- the instruction-level evidence above is what that
    disagreement should be argued from, not a re-read of this docstring
    alone.

    Cross-exposure note: owner `8HVYKgq2PA4SCDuPZSfHBH1aupTBJYPVru6kq3UfuSX9`
    sits on BOTH the 6-of-13 program-upgrade multisig AND holds one of the
    5 council seats gating `admin_authority` -- one compromised key reaches
    both full-power paths on this single target, live-detected via the
    `_signers` set exactly like every other cross-exposure finding in this
    file."""
    notes = []
    signers = set()

    prog = sol_read.read_program(url, MARINADE_PROGRAM)
    upgrade_authority = prog.get("upgrade_authority")
    notes.append(f"program.upgrade_authority = {upgrade_authority}")
    upgrade_ms = _resolve_legacy_serum_multisig(url, "program upgrade", upgrade_authority, "magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed", notes, none_means_renounced=True)
    if upgrade_ms is None:
        admin_a, multisig_a, timelock_a = 20, 20, 0
    elif upgrade_ms == RENOUNCED:
        admin_a, multisig_a, timelock_a = _score_full_power_path("none")
    else:
        admin_a, multisig_a, timelock_a = _score_full_power_path("squads_v3", threshold=upgrade_ms["threshold"], voters=len(upgrade_ms["owners"]))
        signers |= set(upgrade_ms["owners"])
        notes.append(f"program upgrade legacy multisig: {upgrade_ms['threshold']}-of-{len(upgrade_ms['owners'])} delay=0s (no timelock field exists on this account type)")

    state = sol_read.read_marinade_state(url, "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC")
    if state["msol_mint"] != "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So":
        raise ValueError(f"State msol_mint {state['msol_mint']} != expected mSOL mint -- wrong account, aborting rather than scoring the wrong target")
    admin_authority = state["admin_authority"]
    notes.append(f"State.admin_authority = {admin_authority}")

    GOV_PROGRAM = "GovMaiHfpVPw8BAM1mbdzgmSZYDw2tdP32J2fapoQoYs"
    REALM = "899YG3yk4F66ZgbNWLHriZHTXSKk9e1kvsKEquW7L6Mo"
    GOVERNANCE = "M5Fg6GipNvPzWgXNr5wj1EDcp8GB9J53cgyE7YGYLbL"
    COUNCIL_MINT = "6MGwpuJ5YE1c8jJaF8FKurQdDJeYRf1adX76dovkXxRs"

    derived_treasury, _ = sol_read.find_program_address([b"native-treasury", sol_read.b58dec(GOVERNANCE)], GOV_PROGRAM)
    if derived_treasury != admin_authority:
        notes.append(f"admin_authority does NOT match the offline-derived native-treasury PDA of {GOVERNANCE} ({derived_treasury}) -- degrading")
        admin_b, multisig_b, timelock_b = 20, 20, 0
    else:
        gov = sol_read.read_governance_v2(url, GOVERNANCE)
        if gov["realm"] != REALM:
            raise ValueError(f"Governance {GOVERNANCE} realm {gov['realm']} != expected {REALM} -- wrong account, aborting")
        if gov["community_vote_threshold"]["kind"] != "Disabled":
            raise ValueError("community voting is no longer Disabled on this Governance record -- scoring assumption stale, aborting rather than silently mis-scoring")
        if gov["council_vote_threshold"]["kind"] != "YesVotePercentage":
            raise ValueError(f"council_vote_threshold is no longer YesVotePercentage ({gov['council_vote_threshold']}) -- scoring assumption stale, aborting")
        tors = sol_read.list_token_owner_records(url, GOV_PROGRAM, REALM, COUNCIL_MINT)
        council_voters = [t for t in tors if t["governing_token_deposit_amount"] > 0]
        deposit_sum = sum(t["governing_token_deposit_amount"] for t in council_voters)
        # spl-governance's own vote-tallying (state/proposal.rs
        # get_max_voter_weight_from_mint_supply) uses the MINT'S TOTAL
        # SUPPLY as max_voter_weight for a council-mint vote, not the sum
        # of currently-deposited TokenOwnerRecord amounts -- these happen
        # to coincide today (found by adversarial review, 2026-09-18), but
        # the council mint's mintAuthority is not renounced and deposits
        # can be partially withdrawn, so a future mint or withdrawal could
        # silently make deposit_sum < the real on-chain denominator,
        # UNDERSTATING council_threshold. Read the real denominator live
        # and abort rather than silently trust the deposit-sum proxy if it
        # ever diverges (same "raise on a stale assumption" discipline as
        # the community/council_vote_threshold checks just above).
        council_mint = sol_read.read_mint(url, COUNCIL_MINT)
        total_weight = council_mint["supply"]
        if total_weight != deposit_sum:
            raise ValueError(
                f"council mint {COUNCIL_MINT} supply ({total_weight}) != sum of TokenOwnerRecord deposits "
                f"({deposit_sum}) -- the deposit-sum/mint-supply assumption this scorer relies on is stale, aborting rather than silently mis-scoring")
        pct = gov["council_vote_threshold"]["pct"]
        # Integer ceiling: math.ceil(pct / 100 * weight) is off by one whenever pct / 100 * weight lands a hair
        # above an integer in binary floating point (28% of 25 gives 8, the exact value is 7).
        council_threshold = -(-pct * total_weight // 100)
        signers |= {t["governing_token_owner"] for t in council_voters}
        notes.append(
            f"council governance ({GOVERNANCE}): {len(council_voters)} TokenOwnerRecords with nonzero deposit, "
            f"council mint supply={total_weight} (matches deposit sum, live-checked), council_vote_threshold={pct}% -> "
            f"ceil({pct}%*{total_weight})={council_threshold}-of-{total_weight} "
            f"(community voting confirmed Disabled on this record; method matches data/finding_2026-09-17-"
            f"spl-governance-shared-instance-controller.md's own ceil(pct*total) calibration), "
            f"holdup={gov['transactions_hold_up_time_s']}s voting_base={gov['voting_base_time_s']}s cooloff={gov['voting_cool_off_time_s']}s"
        )
        admin_b, multisig_b, timelock_b = _score_full_power_path(
            "realms_governance", threshold=council_threshold, voters=total_weight,
            voting_s=gov["voting_base_time_s"], cooloff_s=gov["voting_cool_off_time_s"], holdup_s=gov["transactions_hold_up_time_s"])

    admin = min(admin_a, admin_b)
    multisig = min(multisig_a, multisig_b)
    timelock = min(timelock_a, timelock_b)
    notes.append(f"combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey={admin} multisig={multisig} timelock={timelock}")

    return {
        "target": "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC", "label": "Marinade Liquid Staking",
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }



# ---------------------------------------------------------------------------
# The five scouted targets promoted on 2026-09-20 (`data/scored_targets_2026-09-20-staking-and-save.md`):
# Save, the SPL Stake Pool program, JitoSOL, Sanctum Infinity and the Sanctum validator LSTs. Their authority
# shapes were live-verified on 2026-09-17 (`data/scouted_targets_2026-09-17-run2.md` rows 9, 10, 11, 15, 16)
# and re-verified on 2026-09-20 with that file's own reproduction commands (all `OK`), then re-derived by the
# functions below on every run with the same discipline as every scorer above: each hardcoded multisig
# candidate must reproduce the live authority PDA offline, or the target degrades instead of trusting it.
# ---------------------------------------------------------------------------
SAVE_PROGRAM = "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo"
SPL_STAKE_POOL_PROGRAM = "SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy"
SPL_STAKE_POOL_MS = "3yqoHFE4nBGchuVH5rJuZMFvsmnaDTuLLdvGPDUEJcbW"  # Squads v3, authority index 1, 6-of-10
SANCTUM_MS = "AApfiPZgV5MoPU691GwhdDhq5sKEMMH1Uh8S4Z9xvP6b"  # Squads v3, authority index 1, 6-of-11
SANCTUM_S_CONTROLLER = "5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx"
SANCTUM_ADMIN_MS = "8EamQU8L2ubwC4FHMxf5BfinEkUFknboK7gpPzvshWyo"  # Squads v4, vault 0, 4-of-8, no delay
SANCTUM_LST_PROGRAMS = (
    "SP12tWFxD9oJsVWNavTTBZvMbA6gkAmxtVgxdqvyvhY",  # SanctumSpl
    "SPMBzsVUuoHA4Jm6KunbsotaahvVikZs1JyTW6iJvbn",  # SanctumSplMulti
)
JITO_POOL = "Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb"
JITO_MINT = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"
JITO_MANAGER = "5eosrve6LktMZgVNszYzebgmmC7BjLK8NoWyRQtcmGTF"  # native treasury of the Jito DAO governance
JITO_STEWARD_PROGRAM = "Stewardf95sJbmtcZsyagb2dg4Mo8eVQho8gpECvLx8"  # owner of the pool's `staker`


def _squads_v3_upgrade_path(url, label, program, ms_candidate, notes):
    """One program whose upgrade authority is a Squads v3 authority PDA -> (adminKey, multisig, timelock, signers).
    Same offline re-derivation as `score_jupiter_aggregator_v6`; a renounced authority is the safest band, a
    mismatch degrades to 20/20/0 rather than trusting the hardcoded multisig."""
    authority = sol_read.read_program(url, program).get("upgrade_authority")
    notes.append(f"{label}: program.upgrade_authority = {authority}")
    if authority is None:
        notes.append(f"{label}: upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1, not a failed read")
        return (*_score_full_power_path("none"), set())
    ms = _resolve_squads_v3(url, label, authority, ms_candidate, notes)
    if ms is None:
        return 20, 20, 0, set()
    admin, multisig, timelock = _score_full_power_path("squads_v3", threshold=ms["threshold"], voters=ms["n_keys"])
    notes.append(f"{label}: Squads v3 {ms['threshold']}-of-{ms['n_keys']}, no time-lock field on Squads v3 (METHODOLOGY.md 3.4)")
    return admin, multisig, timelock, set(ms["keys"])


def _staking_result(target, label, admin, multisig, timelock, notes, signers):
    notes.append(f"combined: adminKey={admin} multisig={multisig} timelock={timelock}")
    return {
        "target": target, "label": label,
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "compositeScore": _composite(admin, multisig, timelock),
        "notes": notes, "_signers": signers,
    }


def score_save(url) -> dict:
    """Save (ex Solend), the lending program (scouted target #9, upper bound 2 -- and 2 is final).

    The program's upgrade authority is a single on-curve key with no multisig wrapper, so the only full-power
    path this scorer needs is the bare-key rung of the ladder: 5 / 0 / 0, composite 2. The lending market
    `owner` (an open point in the scouting file) cannot change that number: a bare key is already the lowest
    rung any authority path can score, so no further path could push it lower. Oracle authority is not scored
    for this target (a flat 100, same convention as marginfi)."""
    notes = []
    authority = sol_read.read_program(url, SAVE_PROGRAM).get("upgrade_authority")
    notes.append(f"Save program.upgrade_authority = {authority}")
    if authority is None:
        kind = "none"
        notes.append("upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1")
    elif sol_read.on_curve(authority):
        kind = "on_curve"
        notes.append("the upgrade authority is a bare on-curve key: one signature can replace the lending program's code, no delay")
    else:
        kind = "off_curve_unresolved"
        notes.append("the upgrade authority is off-curve (a PDA) that this scorer does not resolve -- degraded to 20/0/0, re-scout this target")
    admin, multisig, timelock = _score_full_power_path(kind)
    notes.append("lending market `owner` not decoded: cannot lower a bare-key 5/0/0, which is the bottom rung of the ladder")
    return _staking_result(SAVE_PROGRAM, "Save (ex Solend) lending program", admin, multisig, timelock, notes, set())


def score_spl_stake_pool_program(url) -> dict:
    """SPL Stake Pool program (shared infrastructure behind JitoSOL and other stake pools; scouted target #10).
    Upgrade authority is a Squads v3 6-of-10 committee (Jito's docs call it a committee of Solana staking
    ecosystem participants), no time-lock field on Squads v3: 60 / 100 / 0, composite 54. Five of its ten signers
    also sit on Sanctum's 6-of-11 (scouting file, cross-exposure section); the shared-signer check below re-derives that."""
    notes = []
    admin, multisig, timelock, signers = _squads_v3_upgrade_path(url, "program upgrade", SPL_STAKE_POOL_PROGRAM, SPL_STAKE_POOL_MS, notes)
    return _staking_result(SPL_STAKE_POOL_PROGRAM, "SPL Stake Pool program (shared infrastructure)", admin, multisig, timelock, notes, signers)


def score_jitosol(url) -> dict:
    """JitoSOL (Jito Liquid Staking, scouted target #11). One full-power path: the SPL Stake Pool program's own
    upgrade authority (new code could move all pool stake). Three roles on the pool itself are classed BOUNDED in
    the scouting file (row 11 and its role table, which cites the `spl-stake-pool` source): `manager` (Jito DAO's
    native treasury: fee changes are delayed two epochs or capped, `WithdrawStake` stays permissionless), `staker`
    (a Steward program account) and the stake deposit authority. The JitoSOL mint authority is the pool's withdraw
    PDA, so no human key can mint. This function re-reads those roles every run and RAISES if any has drifted from
    the classification (a skipped target keeps its old on-chain value; a silently wrong score would not)."""
    notes = []
    admin, multisig, timelock, signers = _squads_v3_upgrade_path(url, "SPL Stake Pool upgrade (the pool's code)", SPL_STAKE_POOL_PROGRAM, SPL_STAKE_POOL_MS, notes)
    d = base64.b64decode(sol_read.acct(url, JITO_POOL)["data"][0])
    manager, staker, mint = sol_read.b58(d[1:33]), sol_read.b58(d[33:65]), sol_read.b58(d[162:194])
    withdraw_pda = sol_read.find_program_address([sol_read.b58dec(JITO_POOL), b"withdraw"], SPL_STAKE_POOL_PROGRAM)[0]
    staker_owner = sol_read.read_keytype(url, staker)["owner"]
    mint_authority = sol_read.read_mint(url, mint)["mintAuthority"]
    notes.append(f"pool manager = {manager}, staker = {staker} (owned by {staker_owner}), pool mint = {mint}, mint authority = {mint_authority}")
    drift = [name for name, ok in (
        ("manager", manager == JITO_MANAGER), ("staker owner", staker_owner == JITO_STEWARD_PROGRAM),
        ("pool mint", mint == JITO_MINT), ("mint authority", mint_authority == withdraw_pda)) if not ok]
    if drift:
        raise RuntimeError(f"JitoSOL pool roles changed since the 2026-09-17 classification: {drift} -- re-classify before scoring")
    notes.append("manager, staker and mint authority match the bounded classification of 2026-09-17; the mint authority is the pool's withdraw PDA")
    return _staking_result(JITO_POOL, "JitoSOL (Jito Liquid Staking)", admin, multisig, timelock, notes, signers)


def score_sanctum_infinity(url) -> dict:
    """Sanctum Infinity (S Controller, scouted target #15). Two full-power paths: the program upgrade (Squads v3
    6-of-11, 60 / 100 / 0) and the pool `admin` in the S Controller state (Squads v4 vault 0, 4-of-8, no time lock:
    55 / 80 / 0), which decides `SetSolValueCalculator` and `SetPricingProgram` for every LST. The single on-curve
    `rebalance_authority` is bounded (`EndRebalance` must follow in the same transaction and rejects any drop in
    pool SOL value), so it is disclosed, not scored. Min over paths: 55 / 80 / 0, composite 46."""
    notes = []
    up_admin, up_multisig, up_timelock, signers = _squads_v3_upgrade_path(url, "S Controller program upgrade", SANCTUM_S_CONTROLLER, SANCTUM_MS, notes)
    state = sol_read.find_program_address([b"state"], SANCTUM_S_CONTROLLER)[0]
    d = base64.b64decode(sol_read.acct(url, state)["data"][0])
    pool_admin, rebalance = sol_read.b58(d[16:48]), sol_read.b58(d[144:176])
    notes.append(f"S Controller state PDA {state}: admin = {pool_admin}, rebalance_authority = {rebalance}")
    sq = _resolve_squads_v4(url, "pool admin", pool_admin, SANCTUM_ADMIN_MS, notes)
    if sq is None:
        ad_admin, ad_multisig, ad_timelock = 20, 20, 0
    else:
        ad_admin, ad_multisig, ad_timelock = _score_full_power_path(
            "squads_v4", threshold=sq["threshold"], voters=_voters_with_vote_permission(sq), delay_s=sq["time_lock_s"])
        signers |= {m["key"] for m in sq["member_list"]}
        notes.append(f"pool admin Squads v4: {sq['threshold']}-of-{sq['members']} delay={sq['time_lock_s']}s")
    notes.append(f"rebalance_authority {rebalance} is a single key but bounded (EndRebalance in the same transaction, rejects any drop in pool SOL value): disclosed, not scored")
    return _staking_result(SANCTUM_S_CONTROLLER, "Sanctum Infinity (S Controller)", min(up_admin, ad_admin), min(up_multisig, ad_multisig),
                           min(up_timelock, ad_timelock), notes, signers)


def score_sanctum_validator_lsts(url) -> dict:
    """Sanctum validator LSTs (the SanctumSpl and SanctumSplMulti stake pool programs, scouted target #16). Both
    programs share the upgrade authority of Sanctum Infinity (Squads v3 6-of-11): 60 / 100 / 0, composite 54.
    UPPER BOUND, not a final score: the per-LST pool managers (a bounded role class, like JitoSOL's) were not
    enumerated, so this scores only the program upgrade path that every LST inherits. Each program is re-read
    and both must resolve to the same committee, or the target degrades."""
    notes = []
    results = [_squads_v3_upgrade_path(url, f"{name} upgrade", program, SANCTUM_MS, notes)
               for name, program in zip(("SanctumSpl", "SanctumSplMulti"), SANCTUM_LST_PROGRAMS)]
    admin = min(r[0] for r in results)
    multisig = min(r[1] for r in results)
    timelock = min(r[2] for r in results)
    signers = set().union(*(r[3] for r in results))
    notes.append("upper bound: per-LST pool managers (bounded role class) are not enumerated, only the shared program upgrade path is scored")
    return _staking_result(SANCTUM_LST_PROGRAMS[0], "Sanctum validator LSTs (SanctumSpl, SanctumSplMulti)", admin, multisig, timelock, notes, signers)


SIMPLE_SCORERS = [
    score_jupiter_aggregator_v6,
    score_kamino_lend,
    score_solend_dao_governance,
    score_drift_protocol,
    score_raydium,
    score_marginfi,
    score_kamino_liquidity,
    score_jupiter_perps,
    score_jupiter_lend,
    score_pumpswap,
    score_meteora_damm_v2,
    score_orca_whirlpool,
    score_marinade,
    score_save,
    score_spl_stake_pool_program,
    score_jitosol,
    score_sanctum_infinity,
    score_sanctum_validator_lsts,
]


def _apply_cross_exposure(results: list):
    # Real within-ecosystem check (repo-wide signer-overlap formula), not a
    # flat 100 default -- matches the same-day Hyperliquid/Tempo/Zcash
    # convention.
    #
    # CORRECTED 2026-09-21 (the previous comment here claimed this "currently
    # resolves to 100" for Jupiter and Kamino, which stopped being true once
    # the Jupiter and Meteora targets were added -- a stale comment, not a
    # scoring bug: the arithmetic below was right the whole time and the
    # on-chain values already reflect it). Re-measured this run from both
    # api.mainnet-beta.solana.com and solana.leorpc.com, with an independent
    # decoder (runs/2026-09-21/solana/audit_index0_crossexposure.py):
    #   Jupiter Aggregator v6 -> 40, sharing with Jupiter Perps (whose admin
    #     multisig IS Jupiter's own Squads v3 Ms 7ZyDFzet...), Jupiter Lend
    #     (2 shared keys) and Meteora DAMM v2 (1 shared key, CHRDWWqU...).
    #   Kamino Lend -> 80 on-chain, i.e. one overlap, not the clean 100 the
    #     old comment asserted.
    # The check is real and it is already catching overlaps -- which is the
    # point the old comment was trying to make, with the wrong numbers.
    for r in results:
        others_sharing = [
            o["label"] for o in results
            if o is not r and o["_signers"] and r["_signers"] & o["_signers"]
        ]
        r["crossExposureScore"] = max(0, 100 - 20 * len(others_sharing))
        if others_sharing:
            r["notes"].append(f"shares at least one signer with: {others_sharing}")
    for r in results:
        del r["_signers"]


def score_all(url) -> list:
    # Per-target failure isolation, same convention as every other
    # ecosystem's score_all() in this project (see
    # scripts/lib/web3_utils.py's safe_score docstring) -- reimplemented
    # locally rather than importing the EVM one, since that module imports
    # web3.py at load time and this file has no EVM dependency at all.
    results = []
    for scorer in SIMPLE_SCORERS:
        try:
            result = scorer(url)
            results.extend(result if isinstance(result, list) else [result])
        except Exception as e:
            print(f"score_all(): SKIPPED {scorer.__name__} this run -- {type(e).__name__}: {e}")
    _apply_cross_exposure(results)
    return results
