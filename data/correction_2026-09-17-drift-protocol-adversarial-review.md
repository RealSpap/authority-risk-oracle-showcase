# Correction: adversarial review of Drift Protocol (2026-09-17)

Same-day follow-up to the Drift Protocol addition (third retroactive
backtest, `data/backtest_2026-09-17-drift-protocol-security-council-
compromise.md`, plus a new live scorer, `chains/solana/scorers.py::
score_drift_protocol`, and `chains/solana/data/methodology_test_2026-09-17-
drift-protocol.md`). Before committing, this addition went through an
adversarial review workflow (3 independent reviewers -- byte-layout decode
correctness for the new `read_governance_v2`, independent re-derivation of
every on-chain fact claimed in the backtest, and scorer-code robustness --
each finding piped to an independent verifier), matching this project's
established "no shortcuts" review discipline. Result: **3 findings, 3
confirmed, 0 refuted.** The byte-layout dimension returned zero findings
(`read_governance_v2` independently re-verified correct against two real
accounts).

## Fixed

1. **HIGH -- missing `none_means_renounced=True`.** `score_drift_protocol`'s
   program-upgrade path called `_resolve_squads_v4` without this flag --
   the one call site in the file that didn't, unlike the structurally
   identical calls in `score_kamino_lend` (`klend_sq`, `scope_upgrade_sq`).
   Without it, a renounced (`None`) upgrade authority would score as a
   false MISMATCH (20/20/0, with a factually wrong "degrading" note)
   instead of the safest band (100/100/100) -- an inverted risk signal for
   the one state that's actually safest, the exact bug class this
   project's own code already guards against elsewhere. Drift's authority
   is not currently renounced, so the published score (`compositeScore =
   48`) is unaffected -- verified by re-running the live dry-run after the
   fix and confirming it's unchanged. A new regression test
   (`test_renounced_program_authority_is_not_scored_as_a_mismatch`)
   directly exercises the renounced case via monkeypatching, since the
   real chain state can't be used to test it (Drift's authority isn't
   renounced today).

2. **HIGH -- self-inconsistent composite-score arithmetic in the backtest
   file.** The "What changed since" section displayed the current
   program-upgrade path's own inputs (adminKey=65, multisig=87,
   timelock=2) and then wrote `compositeScore = ... = 48` -- but that
   formula, applied to those exact inputs, evaluates to `53`, not `48`
   (independently confirmed via the project's own `_composite()`
   function). `48` IS the correct, live-verified score for Drift Protocol
   as a whole, but only once METHODOLOGY.md 6.2's "minimum over every
   full-power path" rule folds in a SECOND path (Drift DAO's own Realms
   governance, `multisigScore=70`, lower than this path's `87`) -- a step
   the backtest file's own formula box never showed, even though the
   companion methodology-test file already did this combination correctly.
   Fixed: the backtest file now shows both numbers explicitly (`53` for
   this path alone, `48` combined) with the `min()` step spelled out,
   instead of a bare, arithmetically-false `= 48`.

3. **LOW -- incomplete transaction-log transcript.** The backtest's
   quoted log transcript for the first malicious transaction (Tx 1) listed
   only `VaultTransactionCreate, ProposalCreate`, omitting a third
   instruction actually present in that same transaction's own logs:
   `ProposalApprove`. This mattered beyond completeness: the multisig's
   2-of-5 threshold needs two approvals, and the two-transaction narrative
   as originally written showed only one (`ProposalApprove` in Tx 2 alone
   could not have satisfied a 2-of-5 threshold by itself). Fixed: the
   transcript now includes all three Tx 1 instructions, with an added note
   explaining the real mechanism (Tx 1's signer creates the proposal AND
   immediately self-approves it; Tx 2, one second later, casts the second
   approval from a different signer and executes once threshold is met).

## Verification

- `python3 -m unittest discover -s scripts/lib/tests`: 107/107 pass (92
  pre-existing + 15 new Drift-Protocol tests from the original addition,
  including the new renounced-authority regression test).
- `python3 scripts/validate_all_scorers.py --ecosystem solana`: 4/4 targets
  pass, `OVERALL: PASS`.
- Live dry-run of `score_drift_protocol` after the fix: `adminKeyScore=65,
  multisigScore=70, timelockScore=2, compositeScore=48` -- unchanged from
  before the fix, since Drift's authority isn't in the renounced state the
  bug only affected.

## Reproduction

```bash
python3 -m unittest discover -s scripts/lib/tests
python3 scripts/validate_all_scorers.py --ecosystem solana
cd chains/solana && python3 -c "import sys; sys.path.insert(0,'.'); from scorers import score_drift_protocol; import json; print(json.dumps(score_drift_protocol('https://api.mainnet-beta.solana.com'), indent=2, default=list))"
```
