# Finding (2026-09-19): two real cross-chain signer/address overlaps, found by wiring Monad into `check_cross_ecosystem_overlap.py`

Depth work, not new-ecosystem work: after Monad shipped, the standing
directive shifted from adding more chains to strengthening what's already
built (see [[feedback_oracle_depth_over_breadth]] in this pass's own
memory). The most concrete, well-scoped piece of unfinished depth sitting
in the codebase was Monad's own disclosed gap -- every one of its 7
scorers' docstrings said `crossExposureScore` was "not computed this pass"
because Monad wasn't yet wired into
[`scripts/lib/cross_ecosystem_overlap.py`](../scripts/lib/cross_ecosystem_overlap.py).
Wiring it in (`MONAD_GROUPS`, added to
[`scripts/check_cross_ecosystem_overlap.py`](../scripts/check_cross_ecosystem_overlap.py))
surfaced two real, independently-verified findings that neither Monad's
own scorers nor Robinhood Chain's own scorers could have found alone,
since each only ever reads its own chain.

## Finding 1: Robinhood Chain's own Curve target is the literal same contract, controlled by the literal same key, as Monad's

`scripts/lib/signer_overlap.py`'s `GROUPS["curve"]` (Robinhood Chain) and
`chains/monad/scorers.py::score_curve_monad()`'s target are BOTH:

- Same factory address: `0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD`
- Same admin EOA: `0xabc336d4C71ad275695744d32DdB1d8266Db1cbF`

Independently re-confirmed live against both chains (`eth_call admin()` on
Robinhood Chain mainnet and Monad mainnet, both returning the identical
address; `eth_getCode` on the admin address returns empty on both --
confirmed a bare EOA on both chains, not a Safe on either). This is
Curve Lite's own CREATE2-based cross-chain deployment pattern (the same
salt + deployer produces the same factory address on every chain Curve
Lite is deployed to) combined with Curve's own documented "deployer as
admin until DAO ownership transfer" placeholder state -- confirmed still
in that placeholder state on both chains as of this pass, per Curve's own
`curve-core` repo (`monad.yaml`, cross-checked against `sonic.yaml`/
`ink.yaml`/`taiko.yaml`, which already show a DAO-transferred admin,
unlike Monad).

**Why this is worse than an ordinary shared-signer finding**: this
project's own module docstring for `cross_ecosystem_overlap.py` already
names the general pattern ("the same Safe redeployed via CREATE2 on N
chains... one compromised key set controls every chain's deployment
simultaneously") but every prior instance found (Pendle's Safe on
Plasma/Robinhood Chain) was at least a *Safe* -- some multisig threshold,
however weak. Here there is no multisig at all on either chain: a single
compromised private key controls the identical Curve deployment on two
separate ecosystems this oracle tracks, simultaneously, right now.

**Action taken**: `score_curve_monad()`'s `crossExposureScore` now
computes this live (was hardcoded 100/"not applicable"), reads 80 when
both the factory address and the admin EOA match the known Robinhood
value. Robinhood Chain's own `curve` scorer was NOT modified -- it's
pipeline-managed with a weekly auto-push cron, out of scope for a direct
edit here; this finding is the flag for that side to pick up in its own
pass.

## Finding 2: Monad's largest Morpho vault shares its entire curator AND owner committee with Robinhood Chain's "Steakhouse" family of vaults

`chains/monad/scorers.py::score_morpho_vault_monad()`'s target (Grove x
Steakhouse High Yield AUSD) has:

- Curator/guardian Safe (2-of-6): **all 6 owners** are a subset of
  Robinhood Chain's own "steakhouse" curator Safe (3-of-7,
  `GROUPS["steakhouse"]`) -- the Robinhood-side Safe has exactly one
  additional signer Monad's doesn't.
- Owner Safe (5-of-8): **all 8 owners** are a subset of Robinhood Chain's
  own "steakhouse" owner Safe (5-of-10, shared by `GROUPS
  ["ethena_steakhouse"]`/`["steakhouse_turbo"]`/`["grove_steakhouse"]`) --
  the Robinhood-side Safe has exactly two additional signers.

Both Safe owner sets were independently re-fetched live (`getOwners()`/
`getThreshold()` against both Robinhood Chain mainnet and Monad mainnet,
same session, not reused from an earlier pass) before concluding this is
a real subset relationship, not a coincidental partial match.

**Read carefully**: this is very likely Steakhouse Financial (a real,
named professional Morpho curator firm) operating the same core team
across multiple chains -- a legitimate, common operating pattern for a
curator business, not evidence of anything improper. But "legitimate
pattern" and "real concentration risk" aren't mutually exclusive: it means
the same ~6-8 individuals are the actual, exploitable choke point behind
Monad's largest Morpho vault AND at least 3 separate Robinhood Chain
Morpho vaults this oracle already tracks. A compromise of that team
threatens deposits across two ecosystems at once, which is exactly the
class of risk `crossExposureScore` exists to surface.

**Action taken**: `score_morpho_vault_monad()`'s `crossExposureScore` now
computes this live (was hardcoded 100), reads 80 when either the curator
or owner Safe's live-fetched owner set is a subset of the known Robinhood
committee snapshot.

## What this does NOT do

- Robinhood Chain's own `curve`/`steakhouse*` scorers were not modified --
  disclosed above, left for a separate pass respecting the pipeline's own
  ownership of that file.
- The updated Monad scores were computed and tested locally
  (`chains/monad/scripts/dry_run.py`, `scripts/lib/tests/
  test_monad_scorers.py`) but NOT yet re-pushed to the deployed Monad
  testnet oracle -- only 0.002 MON remained in the shared deployer key
  after the original push (see `chains/monad/deploy/README.md`'s funding
  trail), not enough for another `updateScores()` transaction. The
  deployed oracle's `crossExposureScore` for these two targets is
  currently stale (still 100) until a future pass funds and re-pushes it
  -- disclosed here rather than silently left inconsistent between code
  and chain.
- **UPDATE 2026-09-20:** Robinhood Chain's `curve` group in `scripts/lib/signer_overlap.py` now carries a
  hand-set, dated `cross_ecosystem` flag (the identical bare EOA and factory address as Monad's), so its
  `crossExposureScore` reads 80 (was 100; on-chain since the 2026-09-20 re-push of Robinhood Chain, tx
  `0x020cf83c8a007afaef0eadf7ecb271432c80f1ffd9bfafed984ab6eca17c4978`, block 121,858,777). The `steakhouse*` groups
  were not flagged: their within-Robinhood value (40) is already below the cross-ecosystem cap of 80, and
  the cap never raises a score. The stale-oracle bullet above was closed the same day: the two Monad
  `crossExposureScore` drifts were re-pushed (tx `0xd65b649d...9e35`, per `SUBMISSION.md`, "Live per-oracle
  counts"). See
  `data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`.
- ~~No other ecosystem's `GROUPS` was audited for a similar EOA-vs-EOA or
  full-subset-Safe pattern this pass~~ -- **done in a follow-up pass the
  same day**: `find_subset_committees()` and an identical-bare-EOA check
  were added to `scripts/lib/cross_ecosystem_overlap.py`/`scripts/check_
  cross_ecosystem_overlap.py` and run across all 56 groups in all 7
  ecosystems. Result: no additional finding beyond what this doc and
  [`data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md`](finding_2026-09-19-base-morpho-blue-robinhood-overlap.md)
  already cover -- every containment/identical-address hit the sweep
  produced was one of the findings already fixed, confirming completeness
  rather than surfacing something new. See that file's own "How this was
  found" section for the full sweep output.
