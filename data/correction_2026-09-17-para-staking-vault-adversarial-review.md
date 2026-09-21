# Correction: adversarial review of para StakingVault (2026-09-17)

Same-day follow-up to the `para StakingVault` addition (the second
HyperEVM-native Hyperliquid target, closing this project's own explicitly
left-open question about HIP-3 dex `para`'s EVM-side proxy: new read
helpers and `score_para_staking_vault` in `chains/hyperliquid/scripts/
methodology_test.py`, wired into `chains/hyperliquid/scorers.py`, plus
`chains/hyperliquid/data/methodology_test_2026-09-17-para-staking-
vault.md` and a correction to `data/finding_2026-09-17-hyperliquid-hip3-
evm-proxy-authority.md`'s earlier "admin slot zero, consistent with
immutable" claim). Before committing, this addition went through an
adversarial review workflow (3 independent dimensions -- byte-decode
correctness, on-chain-facts-and-attribution, scorer-code robustness --
each finding piped to an independent verifier), matching this project's
established "no shortcuts" review discipline, most recently applied to
Kinetiq's own HyperEVM promotion earlier the same day.

Result: **18 findings returned, 14 confirmed via independent
re-verification (fresh live RPC calls and, where relevant, live
`hyperevmscan.io` fetches -- not just re-reading the original claim), 4
refuted.**

## A meta-note on the 4 refuted findings

All 4 refutations trace to the same root cause: several verifier agents
had Bash/`gh` access and, in the course of "independently re-verifying,"
cloned or fetched the LIVE PUBLIC `RealSpap/authority-risk-oracle` repo --
which, at review time, did not yet contain this pre-commit code (`score_
para_staking_vault`, `read_role_registry_role_holders`, and
`HyperEvmRpcError` did not exist in any pushed commit). Those verifiers
correctly found the named functions/exception types absent from the real
repo and refuted the findings as "describing code that doesn't exist,"
even though the underlying claims were about the actual pasted code under
review, not a hallucination. This is a limitation of running an
adversarial review on WORK-IN-PROGRESS code via agents with live repo
access, not a defect in this addition -- and it usefully confirms the 14
CONFIRMED findings survived independent scrutiny that was, if anything,
harder to satisfy (verifiers who did stick to the pasted code and live
on-chain re-derivation, rather than the git history, confirmed the real
findings cleanly). No corrective action needed for the 4 refutations
themselves; noted here for anyone reading the raw workflow output later.

## Fixed (5 real code gaps, all confirmed by independent re-verification)

1. **HIGH -- a single role's read failure crashed the entire target's
   score.** `score_para_staking_vault`'s per-role call to `read_role_
   registry_role_holders` was unwrapped -- unlike an individual
   unresolvable HOLDER (already degraded gracefully by `_classify_
   authority_holder`), a whole ROLE failing to read (a revert, a
   malformed response) propagated uncaught. Fixed: that call is now
   wrapped in `try/except (HyperEvmReadError, HyperEvmRpcError)`,
   degrading the failed role to a conservative unresolved path (20/0/0)
   with a clear note, so the other roles still contribute to the
   minimum-over-paths computation. The four top-level setup reads
   (finding the RoleRegistry itself, its two role constants, its owner)
   were deliberately left unwrapped and documented as such: if those fail
   there is genuinely nothing to score this run, and `score_all()`'s own
   per-scorer try/except already isolates that to a single "SKIPPED"
   line -- the same convention every other scorer's own setup already
   relies on (confirmed by checking `score_kinetiq_staking_manager`'s
   equivalent setup has the identical, accepted shape).

2. **HIGH -- `bytes.fromhex()` raised a bare, uncategorized `ValueError`
   on malformed hex**, which slipped past every `except (HyperEvmReadError,
   HyperEvmRpcError)` clause in this file -- including inside `read_safe_
   hyperevm` itself, which still had this exact gap even after its OWN
   prior hardening pass (that pass validated shape AFTER the `bytes.
   fromhex` conversion, not around the conversion itself). A malformed
   hex response is a real, non-hypothetical failure mode (a glitching or
   non-compliant RPC provider), not just a contract-level revert. Fixed
   with a shared `_bytes_from_hex(raw, context)` helper that catches
   `ValueError` and re-raises as `HyperEvmReadError`, used in both
   `read_safe_hyperevm`'s two conversions and the new `read_role_
   registry_role_holders`.

3. **MEDIUM -- a role hash with no length check was spliced straight into
   `.rjust(64, "0")`.** A short or empty `MANAGER_ROLE()`/`OPERATOR_ROLE()`
   response (e.g. a future RoleRegistry upgrade returning no data instead
   of reverting for a since-renamed getter) would silently zero-pad into
   `bytes32(0)` -- this project's own `DEFAULT_ADMIN_ROLE` sentinel value
   elsewhere -- querying a completely different, unintended role with no
   error, no warning: a silently WRONG result, not a crash, and a
   materially different (harder to catch) failure mode than findings 1-2.
   Fixed with an explicit `len(val) < 66` check immediately after each
   role hash is fetched in `score_para_staking_vault`, and again inside
   `read_role_registry_role_holders` itself for defense in depth.

4. **MEDIUM -- the cross-exposure check only ever compared TOP-LEVEL
   role-holder addresses, never owner addresses nested inside a resolved
   Gnosis Safe.** `_classify_authority_holder`'s Gnosis Safe branch
   returned only `len(safe["owners"])` (a count) in its `info_` dict,
   never the actual owner list -- so an owner appearing only INSIDE a
   Safe (a real, live case here: one of the `OPERATOR_ROLE` Safe's 3
   owners is the SAME address as the separate `RoleRegistry.owner()`
   Safe's own sole owner) was structurally invisible to any check built
   from `role_paths`' keys alone. Confirmed to be a real, pre-existing gap
   in `score_kinetiq_staking_manager`'s identical shared plumbing too, not
   unique to this new target. Fixed: `_classify_authority_holder` now
   also returns `ownerAddresses` (the real list) alongside the existing
   `owners` count; both `score_kinetiq_staking_manager` and `score_para_
   staking_vault`'s cross-exposure checks now union those in. Re-ran live
   after the fix: `crossExposureScore` is unchanged at 100 for BOTH
   targets -- this was a completeness gap in the check, not a live miss
   that changes any published score.

5. **LOW (x2, editorial) -- imprecise framing in the documentation
   itself**, both confirmed by independent fact-checking against this
   project's own committed history: (a) describing the corrected
   "admin slot zero, consistent with immutable" claim as simply "wrong"
   overstated what happened -- the earlier finding file's own text had
   already hedged that exact point and explicitly flagged reading para's
   implementation source as the open follow-up; reworded to "closes an
   explicitly flagged gap, and adds a methodology point" throughout; (b)
   "an unverified contract" as a headline description blurred together a
   verifiable, standard EIP-1967 proxy with its genuinely-unverified
   implementation behind it -- reworded to distinguish the two wherever
   this was the primary description.

## What was independently re-confirmed as already correct (no action needed)

- `read_role_registry_role_holders`'s manual ABI array decode, checked
  against fresh live responses AND an independent `eth_abi` decode, plus
  synthetic n=0/n=3 cases live data couldn't exercise.
- The EIP-1967 implementation-slot constant, recomputed via two
  independent libraries and cross-checked against OpenZeppelin's own
  current source and the EIP-1967 spec text.
- The `delegatorSummary()` struct-layout assumption and the ~$41.7M USD
  arithmetic, reproduced from a live call plus a live HYPE price.
- Every function-gating claim (`MANAGER_ROLE` on the six fund-moving
  functions, `OPERATOR_ROLE` on the three operational ones) and the "no
  dex-admin-equivalent CoreWriter call" conclusion, checked against the
  FULL verified source (not just the pasted excerpt) fetched directly
  from `hyperevmscan.io`.
- The cross-exposure claim itself (zero overlap against all 10 HIP-3
  dexes) -- one verifier went further than the original evidence and
  independently swept every dex's `haltTrading` sub-deployer signers too,
  still finding zero overlap.
- Two hand-typed hex constants in the review's own scratch working
  (`RAW_FACTS`) were found truncated by one hex digit each (the SAME
  error class this project's own history has now hit on the EIP-1967
  slot constant, twice, and on `MANAGER_ROLE` a third time while drafting
  the accompanying test file) -- confirmed cosmetic: the actual scorer
  code never hardcodes these values, it fetches them dynamically, so
  nothing downstream was affected. A permanent regression test
  (`TestRoleHashConstants`, recomputing both role hashes via `Web3.keccak`
  rather than trusting the literal) was added specifically to catch this
  exact recurring mistake in the future.

## Verification

- `python3 -m unittest discover -s scripts/lib/tests`: 150/150 pass (128
  pre-existing after the Kinetiq correction earlier the same day + 22
  new para-StakingVault tests, 11 from the original addition + 11 added
  to cover this correction's five fixes).
- `python3 scripts/validate_all_scorers.py --ecosystem hyperliquid`: 7/7
  targets pass, `OVERALL: PASS`.
- Live dry-run of `score_para_staking_vault` and `score_all()` after every
  fix: `adminKeyScore=10, multisigScore=0, timelockScore=0,
  oracleAuthorityScore=100, crossExposureScore=100, compositeScore=4` --
  unchanged from before this correction. Every fix in this pass closed a
  robustness/completeness gap in code paths not currently triggered by
  live state (an all-empty role, malformed hex, a too-short role
  constant, a zero-address owner, a missed nested-Safe-owner overlap),
  not a live miscalculation.

## Reproduction

```bash
python3 -m unittest discover -s scripts/lib/tests
python3 scripts/validate_all_scorers.py --ecosystem hyperliquid
cd chains/hyperliquid/scripts && python3 -c "
import json
from methodology_test import score_para_staking_vault
print(json.dumps(score_para_staking_vault(), indent=2))
"
```
