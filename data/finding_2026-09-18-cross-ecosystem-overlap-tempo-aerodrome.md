# Cross-ecosystem check extended to Tempo and Aerodrome's emergencyCouncil (2026-09-18) -- clean result

## What this closes

`data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md` (the
day this module first went live) explicitly disclosed: "Does not extend
this same check to Solana/Hyperliquid/Tempo/Zcash -- their signer formats
... are not directly comparable to EVM addresses." That reasoning is
correct for Solana (base58 Ed25519 pubkeys), Hyperliquid, and Zcash
(P2SH), but was never actually true for **Tempo** -- it's a standard EVM
chain (chain id 4217, full JSON-RPC compatibility, real Gnosis Safe
deployments) whose signer addresses are directly comparable to any other
tracked EVM ecosystem's. Tempo just didn't have any resolved Safes to
check yet when that line was written (2026-09-17); the same-day
controller-resolution work (`chains/tempo/data/scored_targets_2026-09-18-
controller-types.md`) changed that.

Also closes a smaller, adjacent gap: `BASE_GROUPS["aerodrome"]` only
tracked PoolFactory's `pauser()`/`feeManager()` Safe -- `Voter.
emergencyCouncil()`, a genuinely separate Safe traced the same day
(`chains/base-ecosystem/data/finding_2026-09-18-aerodrome-voter-governor-
identity.md`), was never added to this cross-ecosystem registry even
though its 5 real signers are exactly the kind of thing this module
exists to check.

## What was added

`scripts/lib/cross_ecosystem_overlap.py`:
- `TEMPO_GROUPS` (new): `cap_safe` (`0xb8fc49402df3ee4f8587268fb89fda4d621a8793`,
  3-of-5 -- controls cUSD's TimelockController proposer/executor/canceller
  AND is the same OFT's LayerZero endpoint delegate) and `usdt0_safe`
  (`0x4DFF9b5b0143E642a3F63a5bcf2d1C328e600bf8`, 3-of-5 -- USDT0's TIP-403
  policy admin and `DEFAULT_ADMIN_ROLE` holder).
- `BASE_GROUPS["aerodrome_emergency_council"]` (new): `0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D`,
  3-of-5.

`scripts/check_cross_ecosystem_overlap.py`: wired in Tempo's own RPC
(`https://rpc.tempo.xyz`).

**Deliberately NOT added**: Tempo's LayerZero OneSig (USDC.e/EURC.e's
shared admin) and its 3 Chainlink MCMS instances (cbBTC/PRIME's
proposer/bypasser/canceller). Neither shape is a Gnosis Safe, so this
module's existing `safe_owners_and_threshold` resolution path can't read
them, and there's no live-resolution path for them here yet -- putting a
hand-copied signer list in `known_eoa` would go stale silently the moment
membership changed, exactly what this project's own discipline avoids
elsewhere. A disclosed gap for a future pass (would need a small
extension to `group_root_signers` accepting a resolver callback per
group, not just Safe-shaped ones), not a silent omission.

## What was found

Re-ran the full live check: **37 groups across 5 ecosystems** now (24
Robinhood Chain, 3 Ethereum L1, 4 Arbitrum, 4 Base, 2 Tempo -- up from 33
across 4 the day before).

**Clean result: zero new overlaps.** Neither Tempo's Cap Safe nor its
USDT0 Safe shares a single signer with any of the other 35 groups
checked (Robinhood Chain's 24, Ethereum L1's 3, Arbitrum's 4, Base's 4).
Aerodrome's `emergencyCouncil` likewise shares zero signers with anything
tracked elsewhere, confirming (from a different angle) what `chains/
base-ecosystem/data/finding_2026-09-18-aerodrome-voter-governor-identity.md`
already found when checking it specifically against Base's own other 3
targets. The only overlap this run still finds is the already-known one:
Arbitrum's and Base's Aave V3 `GOVERNANCE_GUARDIAN` committees (9 shared
signers, `crossExposureScore=80` already applied on both scorers since
2026-09-17). No identical Safe address across ecosystems either
(`find_identical_safe_addresses`, unchanged: none).

## Why a clean result is still worth publishing

This project's own established discipline (used throughout for
disclosed-negative findings, e.g. Meteora DLMM/DAMM v1's non-promotion,
Sanctum cross-checks on Solana) treats "checked and found nothing" as a
real result worth recording, not a non-event -- a reader of this
project's cross-exposure claims should be able to see EXACTLY what was
checked and when, not just the positive hits. Concretely: Tempo's two
newest, highest-stakes admin keys (Cap's timelock proposer and USDT0's
policy admin) are now confirmed independent of every other Safe this
project tracks, not merely assumed to be.

## Verification

- Every group's signers resolved LIVE this run (`safe_owners_and_
  threshold` against `https://rpc.tempo.xyz` for the 2 new Tempo groups,
  `https://mainnet.base.org` for the new Base group), not from a cached
  snapshot.
- `python3 -m unittest scripts.lib.tests.test_cross_ecosystem_overlap
  scripts.lib.tests.test_cross_ecosystem_fixes`: 23/23 pass (pure-logic
  tests, unaffected by adding new GROUPS entries -- no new decode logic
  introduced this pass, only more data for the same, already-tested
  resolution/overlap functions).
- `python3 scripts/check_cross_ecosystem_overlap.py`: runs clean, 37
  groups, 1 known overlap (Aave guardian), 0 new ones.

## Reproduction

```
python3 scripts/check_cross_ecosystem_overlap.py
```
