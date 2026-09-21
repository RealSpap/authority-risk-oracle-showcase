# Correction: adversarial review of Solend DAO governance (2026-09-17)

Same-day follow-up to the Solend DAO governance promotion
(`chains/solana/scorers.py::score_solend_dao_governance`,
`chains/solana/data/methodology_test_2026-09-17-solend-governance.md`,
`data/backtest_2026-09-17-solend-governance-emergency-powers.md`). Before
committing, this new target went through an adversarial review workflow
(3 independent reviewers -- byte-layout decode correctness, formula/
methodology consistency, scorer code robustness -- each finding piped to
an independent verifier), matching this project's established "no
shortcuts" review discipline. Result: **5 findings, 5 confirmed, 0
refuted.** All 5 are in the formula-methodology dimension; the byte-layout
and scorer-code dimensions returned zero findings (independently confirmed
correct).

## Fixed

1. **HIGH -- missing third full-power path.** `score_solend_dao_governance`
   scored the Realm's own `authority` field and the token-vote
   `GovernanceV2` account, but never read the governance PROGRAM's own
   upgrade authority -- inconsistent with `score_jupiter_aggregator_v6` and
   `score_kamino_lend`, which both score their target program's own
   upgrade authority as a matter of course. Live-checked: that authority
   (`6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT`) is ALSO a bare, active,
   on-curve EOA, not renounced. **Fix**: the function now reads and scores
   all three full-power paths, taking the minimum across all three per
   METHODOLOGY.md 6.2 -- factored through a shared `_score_bare_authority`
   helper so both EOA paths get identical classification logic and both
   correctly populate the `_signers` set for cross-exposure checking (the
   governance-program path previously would have silently evaded
   `crossExposureScore` entirely, on top of not being scored at all). The
   published composite for Solend DAO does not change (`2/100` either way
   -- the realm-authority path alone already hits the worst band), but the
   underlying claim ("minimum over full-power paths") is now actually true
   of the code that produces it, and a future scenario where the realm
   authority gets fixed while the program authority doesn't (or vice
   versa) will now be caught correctly.

2. **MEDIUM -- stale top-level docs.** `SUBMISSION.md` and `README.md`
   still stated the backtest's illustrative `compositeScore = 8/100` for
   the 2022 incident with no caveat, ~14 minutes after the backtest file
   itself gained a "Correction" section admitting that number was "guessed"
   and that the properly-tested formula gives `~62/100` for the same 2022
   parameters (with the live scorer's actual published score, `2/100`,
   being the number that matters regardless, via a separate authority
   path). **Fix**: both docs updated with the corrected numbers and a
   pointer to the backtest file's own Correction section; `SUBMISSION.md`'s
   Solana bullet also updated from 2 to 3 targets.

## Disclosed, not silently patched (open points, `chains/solana/METHODOLOGY.md` section 7)

Two more findings were confirmed real but are **deliberately left open**
rather than fixed with an under-time-pressure guess, matching this
project's established "don't invent a number, disclose the gap" discipline
(the same discipline the "Squads v4 controlled" band already follows):

3. **HIGH -- unreconciled timelock curves.** The `realms_governance`
   timelock formula and the Squads v4 timelock formula both claim to
   measure "delay before an authority action takes effect," but score a
   comparable ~6-hour delay on very different curves (Squads: 13; Realms:
   ~43) and disagree even more sharply at zero delay (Squads: 0; Realms:
   40, an algebraic floor of the additive formula, not a deliberate
   design choice). A prior version of METHODOLOGY.md's own text also
   claimed the Realms adminKey/multisig columns "credit the voting window"
   -- false as written, since `_score_full_power_path`'s `realms_governance`
   branch returns flat constants that never reference voting time at all.
   **Fixed the false claim** (METHODOLOGY.md no longer says this); **did
   NOT fix the curve mismatch itself** -- inventing a new curve under time
   pressure risks introducing an equally uncalibrated replacement, so this
   is now an explicit, named open point instead.

4. **LOW -- no documented derivation for the flat 70 baseline.** The
   "70 for token voting" adminKey/multisig constant (introduced 2026-09-16,
   before any Realms target existed) has never had a stated rationale
   (no equivalent-multisig-threshold comparison, no participation
   assumption). The 2026-09-17 changelog's "validated against Solend DAO"
   language validated the timelock hold-up=0 generalization only -- the 70
   constant itself was carried over unchanged. **Fixed the overclaiming
   changelog wording**; the missing derivation itself is now a named open
   point, distinct from the already-known voter-concentration gap.

5. **LOW -- unspecified council-threshold multisig formula.** The 6.1
   table's Realms row has a concrete adminKey formula for the countable
   council/community-threshold case but the multisig cell was just an
   unresolved-looking placeholder ("council threshold formula"), with no
   actual expression anywhere in the file -- consistent with
   `_score_full_power_path` deliberately raising `NotImplementedError` for
   that branch (no council-governed target scored yet to calibrate
   against), but this specific gap wasn't previously named in section 7
   the way the similarly-unimplemented "Squads v4 controlled" band is.
   **Fixed**: the table cell now reads "not yet calibrated" explicitly, and
   the gap is named in section 7.

## Verification

- `python3 -m unittest discover -s scripts/lib/tests`: 90/90 pass (75
  pre-existing + 15 new Solend-governance tests from the original
  promotion, unaffected by this review's fixes).
- `python3 scripts/validate_all_scorers.py --ecosystem solana`: 3/3 targets
  pass, `OVERALL: PASS`.
- Live dry-run of `score_solend_dao_governance` after the fix:
  `adminKeyScore=5, multisigScore=0, timelockScore=0, compositeScore=2` --
  unchanged from before the fix, now correctly dominated by two
  independent full-power paths instead of the one the pre-review code
  happened to compute correctly by omission.

## Reproduction

```bash
python3 -m unittest discover -s scripts/lib/tests
python3 scripts/validate_all_scorers.py --ecosystem solana
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr
```
