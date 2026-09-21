# Correction (2026-09-17): `crossExposureScore` was entirely missing from two ecosystem scorers

## What was found

While auditing `METHODOLOGY.md`'s claim that `crossExposureScore` "defaults to 100
(not applicable)" on every `scoring_build`-phase ecosystem outside Robinhood Chain,
a direct `grep` for the field across every `chains/*/scorers.py` found it absent
entirely -- not defaulted to 100, just never set -- in two files:

- `chains/ethereum-l1/scorers.py` (all 9 targets, including the 3 added earlier
  today: `score_usdtb`, `score_usdtb_psm`, `score_ethena_layerzero_oft`)
- `chains/solana/scorers.py` (both targets, added earlier today)

`chains/arbitrum-ecosystem/scorers.py` and `chains/base-ecosystem/scorers.py`
already had the field, explicitly set to `100` with a comment explaining why --
this correction only affects the two files where the field was missing outright,
which could have caused a `KeyError` (or a silently wrong on-chain tuple) the day
either ecosystem's deploy script actually tried to push these scores.

## Fix

Rather than the flat `100` default `arbitrum-ecosystem`/`base-ecosystem` use,
both files were fixed with a REAL within-ecosystem signer-overlap check --
matching the stronger convention `chains/hyperliquid`, `chains/tempo` and
`chains/zcash` already established earlier the same day (each computes real
overlap among its own tracked targets, not a lazy default).

### Ethereum L1 -- a real, previously undisclosed finding

Grouping each target by its live-documented root authority surfaced that
**5 of the file's 9 targets share the exact same root**, the 5-of-10 Safe
`0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862` (reached directly by Ethena
Minting, and via the shared `EthenaTimelockController` by USDtb PSM and all 3
LayerZero OFTAdapters -- USDe, sUSDe, ENA):

| Target | crossExposureScore |
|---|---|
| Ethena EthenaMinting (USDe) | 20 |
| USDtb PSM | 20 |
| USDe OFTAdapter (LayerZero) | 20 |
| sUSDe OFTAdapter (LayerZero) | 20 |
| ENA OFTAdapter (LayerZero) | 20 |
| Uniswap V3 Factory / Aave V3 Pool / MakerDAO-Sky / USDtb | 100 (no shared root with any other tracked target) |

Each of these 5 targets' own docstring already separately documented sharing
that Safe with one or two siblings -- this fix is the first time it was
connected into a single cross-target number. USDtb (the bare-EOA-governed
token) is deliberately NOT grouped with the Safe cluster: its docstring
already flags this as a genuine, current inconsistency within Ethena's own
infrastructure (one token's admin was migrated to a Safe+Timelock, this one
never was), and grouping it anyway would have hidden that finding rather than
surfaced it.

### Solana -- checked, no overlap found today

Jupiter Aggregator v6's Squads v3 Ms (7 signers) and Kamino Lend's 4 Squads v4
multisigs (11 distinct signers) were compared live: no shared signer.
`crossExposureScore` = 100 for both -- a real, live-checked result, not a
default that happens to read the same.

### Checked but not upgraded: Arbitrum and Base's own flat defaults

Given Ethereum L1's fix surfaced a real finding, the same question was
checked for these two files' own tracked targets: do any of their root Safes
share a signer? Live-checked pairwise across Arbitrum's 4 Safe-governed
targets (GMX's `TIMELOCK_MULTISIG` holder, Camelot's factory owner, the
Arbitrum Security Council Safe, Aave's `PayloadsController` guardian) -- zero
overlap found. Unlike Ethereum L1 (a real bug: the field was silently
absent) or Solana (checked as part of adding the field for the first time),
`arbitrum-ecosystem`/`base-ecosystem`'s flat `crossExposureScore = 100` was
already a correctly disclosed, honest default -- not upgraded to real
per-target signer-set machinery this pass, since doing so would not have
changed the published number and the existing disclosure is already
accurate.

## Verification

Both fixes were dry-run live against their respective mainnets after the
change; 65/65 existing unit tests remained green (this fix only added a field
to existing return dicts and one new post-processing pass per `score_all()`,
no existing logic changed). See the commit for the exact dry-run output.

## Follow-up (same day): the deploy script was silently discarding the fix

Checking whether this fix would actually reach chain found a second bug one
layer down: `chains/ethereum-l1/deploy/update_scores_ethereum_l1.py` built its
on-chain `updateScores()` tuple with a hardcoded `DEFAULT_CROSS_EXPOSURE = 100`
constant instead of reading `entry["crossExposureScore"]` -- a reasonable
placeholder when it was written (the field didn't exist in `scorers.py` yet),
but it would have silently overwritten today's real 20-value finding for the
5 Ethena-Safe-rooted targets back to 100 the moment this ecosystem's scores
actually got pushed. Fixed to read the real per-entry value; re-verified live
that the encoded on-chain tuple for each of the 9 targets now carries the
same `crossExposureScore` `scorers.py` computed (100/100/100/**20**/100/
**20**/**20**/**20**/**20**), not a flat 100. `chains/arbitrum-ecosystem` and
`chains/base-ecosystem`'s own deploy scripts were checked too and already
read the field directly with no hardcoded override -- only Ethereum L1's had
this gap.
