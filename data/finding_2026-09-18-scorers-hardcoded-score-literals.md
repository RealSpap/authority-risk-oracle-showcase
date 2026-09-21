# Finding (2026-09-18): 5 scorers in `scripts/lib/scorers.py` perform real live reads but never actually condition their score on the result

Surfaced as a side effect of the 2026-09-18 test-coverage audit (writing
`scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`,
`test_robinhood_vault_and_infra_scorers.py`, and
`test_robinhood_event_replay_scorers.py`), not from a dedicated bug hunt.
Each was found while independently tracing a scorer's real branch logic to
design a test fixture -- not fixed here, per this project's own
"understanding vs. changing" split: a scoring-logic change needs its own
adversarial review before committing (see `AGENTS.md`'s "Before
committing" section), which this pass did not run. Documented so the gap
is not silently lost, and so a future session doesn't have to re-derive it
from scratch. `scripts/lib/scorers.py` itself is unmodified by this
finding.

## The pattern

The module's own docstring states the whole file's premise: *"Re-running
this script re-derives the same facts from the live chain instead of
replaying hardcoded numbers -- if a target's real on-chain state changes
... the next run picks that up."* Five scorers perform real `eth_call`/
`eth_getLogs` reads, append genuinely useful facts to their `notes` list --
but the actual `adminKeyScore`/`multisigScore`/`timelockScore` triple is
either a flat literal untouched by any of those reads, or only
*partially* gated in a way that fails open (an unresolved read lands on
the BETTER score, not a degraded one, the opposite of every other scorer
in this file).

1. **`score_ramses_clv2`** (line ~905) -- reads the Ramses Team Multisig's
   threshold/owners, `RamsesTimelock.getMinDelay()`, and replays
   PROPOSER_ROLE/CANCELLER_ROLE/EXECUTOR_ROLE holders live. All three
   scores are then set to a flat `admin_key, multisig, timelock = 15, 5,
   0`, regardless of what any of those reads returned. A Safe
   reconfigured from 1-of-1 to, say, 3-of-5 with a real nonzero delay
   would still report the identical 15/5/0 forever.

2. **`score_longbow_vault`** (line ~961) -- reads `owner()`/`curator()`
   and both Safes' owner sets/thresholds live, and even checks whether the
   two Safes share an identical owner set (a real, useful finding). Then
   `admin_key, multisig, timelock = 40, 40, 15` regardless. Unlike every
   other scorer in the same batch (Arcus, stock-token, Pendle,
   Morpho-generic), a total read failure (both `owner()` and `curator()`
   unresolved) reports the SAME "confirmed" score as the fully-verified
   case -- no degrade-on-failure path exists here at all.

3. **`score_spark_savings_usdg`** (line ~497) -- `admin_key = 50` and
   `multisig = 30` are flat literals, not derived from `executor_is_eoa`,
   `l1_authority`, or `receiver_is_safe`. Worse, `timelockScore` has a
   real **fail-open** bug: `timelock_score = 10 if delay == 0 else 60`.
   If `delay` is `None` (every retry hit a transient RPC failure, or the
   call reverts), `None == 0` is `False`, so the code lands on `60` --
   the score for a CONFIRMED nonzero delay -- instead of degrading. This
   is the inverse of the fail-closed convention every other scorer in
   this file uses on an unresolved read (compare
   `score_uniswap_v3_factory`'s explicit `# FIXED 2026-09-17: ... degrade
   instead of silently keeping the confident score` comments elsewhere in
   this same file).

4. **`score_ekubo_core`** (line ~932, lower confidence / more
   defensible) -- re-checks `owner()` live purely as a sanity ping
   (expected to keep reverting), but the result never changes the flat
   `100/100/100`. If `owner()` ever stopped reverting (e.g. a future
   proxy-style upgrade reintroducing an authority concept), the live
   re-check would note it without downgrading the score. More defensible
   than the three above since the docstring frames this explicitly as a
   lightweight re-confirmation of an already-exhaustive one-time
   differential test, not a full re-derivation -- but the same shape of
   gap.

5. **`score_fables_pool_registry`** (lines 1318-1319, a narrower gap
   than the other four -- not a scoring-literal issue) -- this function
   replays `RoleGranted`/`RoleRevoked` for an OZ AccessManager by hand
   (it does NOT call the shared `_replay_role_holders()` helper, since
   AccessManager's event shape differs). Its own comment says it ported
   `_replay_role_holders()`'s FIXED-2026-09-17 `(blockNumber, logIndex)`
   sort-order fix "independently duplicated here" -- but it did **not**
   port the sibling FIXED-2026-09-17 fix in the same helper: the
   malformed-`topics[2]` guard (32-byte length + 12-byte zero-padding
   check before decoding an indexed address). Here, `"0x" +
   l["topics"][2].hex()[-40:]` decodes with no validation at all. A
   malformed or RPC-anomalous log would silently produce a spurious
   ADMIN_ROLE holder address instead of being skipped -- the exact
   vulnerability class `_replay_role_holders()`'s own guard (and this
   project's sister research, `multisig-overlap`) already
   exists to catch, just not propagated to this duplicate
   implementation.

## What this does NOT do

- Does not change any `compositeScore`, `adminKeyScore`, `multisigScore`,
  or `timelockScore` currently published for any of these 5 targets.
- Does not modify `scripts/lib/scorers.py`. Each gap is now instead
  locked in by a dedicated test asserting the CODE'S ACTUAL current
  behavior (not the behavior the module docstring implies it should
  have) in the three test files listed above -- so a future fix to any
  of these 5 scorers will fail its own existing test until the fixture
  is updated to match the new, presumably-correct, behavior. That is a
  deliberate tripwire, not an oversight.
- Does not attempt a fix. A fix to #1-#4 would need a real design
  decision (what should the score formula actually be, conditioned on
  which reads?) that this test-coverage pass is not the right context to
  make unilaterally -- it needs this project's own adversarial-review
  discipline before committing a scoring-logic change, per
  `AGENTS.md`. #5 is more mechanical (port the existing guard) and is
  the most likely of the five to be a quick, low-risk follow-up.
- Does not check whether any OTHER scorer in this file (the ~19 not yet
  covered by this test-coverage pass, still a follow-up) has the same
  hardcoded-literal shape -- this finding covers only the 5 instances the
  audit incidentally surfaced while writing tests for a specific batch of
  functions, not an exhaustive sweep for this exact pattern across the
  whole file.

## Reproduction

Each of the 5 claims above is independently reproducible by reading the
cited line numbers in `scripts/lib/scorers.py` directly -- no live RPC
call is needed to see the hardcoded literal or the `delay == 0` vs `None`
comparison. The dedicated regression tests are in:

- `scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`
  (`TestScoreRamsesClv2`, `TestScoreEkuboCore`)
- `scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`
  (`TestScoreLongbowVault`, `TestScoreSparkSavingsUsdg`)
- `scripts/lib/tests/test_robinhood_event_replay_scorers.py`
  (the `score_fables_pool_registry` tests note the missing guard in a
  comment; no dedicated malformed-topic test exists for this function
  specifically, since the audit's mandate was test-coverage, not a fix)
