# A vault's timelock next to its actual exit capacity

2026-09-25. Roadmap item 10 ("voit large" round 2), continued after Spap's go-ahead ("continue"). The
research already existed in full (`data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`,
"eighth pass": `chains/ethereum-l1/scripts/sweep_exit_capacity.py`, a 167-vault, $5.95B market-wide
sweep -- "no product was found that puts a DeFi vault's timelock next to its exit capacity") but was
never scoped to this oracle's own 9 tracked Morpho vaults or turned into a disclosed field. Built here:
`scripts/lib/exit_capacity.py` (pure classification, 18 new unit tests) + `scripts/check_exit_capacity.py`
(live read, same Morpho API query shape as the existing market-wide sweep).

## Why this is a real gap, not a gadget

A timelock only protects depositors if they can leave before a queued malicious change takes effect.
`timelockScore` already asks "is there a real delay" -- it says nothing about whether that delay is
actually useful to someone trying to exit. The market-wide research already found this matters at
scale: 44 of 167 listed vaults, $1,910M (32% of that sample), sit behind a ~3-day-or-shorter timelock
with under 20% of deposits instantly withdrawable.

## Result on this oracle's own 9 tracked vaults ($1,664.4M)

| Vault | TVL | Exit capacity | Timelock | Flag |
|---|---|---|---|---|
| Gauntlet USDC Prime (Base) | $415.7M | 45.6% | 7d | |
| Adpend USDC (L1) | $361.9M | 0.0% | over 7d | |
| Spark USDC Vault (Base) | $312.0M | 56.7% | over 7d | |
| 1337 USDC (L1) | $193.0M | 0.0% | **0 (no delay)** | **thin behind a short delay** |
| Steakhouse USDC (Base) | $127.0M | 100.0% | 7d | |
| Grove x Steakhouse USDC High Yield (Base) | $101.1M | 83.1% | over 7d | |
| Steakhouse USDT (L1) | $87.4M | 29.3% | 7d | |
| Steakhouse USDC (L1) | $66.2M | 67.6% | 7d | |
| Grove x Steakhouse High Yield AUSD (Monad) | $0.1M | 18.3% | over 7d | |

**1 of 9 tracked vaults** (1337 USDC, $193.0M) combines a short/nonexistent timelock with zero instant
exit liquidity. Not a new authority-risk finding on its own -- this vault is already scored at the
floor (adminKeyScore=5, bare on-curve EOA root, Morpho's own red warnings `short_timelock`/
`oracle_unusable` already disclosed in `chains/ethereum-l1/scorers.py::score_morpho_1337_usdc`) -- but
it is a genuinely new, quantified fact: $193M sits in a vault where, if anything did go wrong, a
depositor's instant exit is 0%, not just "risky admin".

## A stale comment found and fixed along the way (not a score bug)

Building this surfaced that `_score_steakhouse_l1_vault`'s own comment claimed a "3-day floor per
Morpho's own listing policy" for the two Ethereum L1 Steakhouse vaults' curator timelock. Live data
(this tool, and cross-checked against `sweep_exit_capacity.py`'s own field) shows the real configured
delay is 7 days, not 3 -- the comment described Morpho's minimum LISTING requirement, not this
vault's own configuration. `timelock_score` itself never depended on the exact duration (it's set from
whether the guardian is independent, not from days), so no published score was ever wrong -- only the
comment next to it. Fixed in `chains/ethereum-l1/scorers.py`.

## What this is not

Not folded into `timelockScore`, `adminKeyScore` or `multisigScore` -- a different question
(protection-window usefulness, not delay-existence), disclosed the same way as the controller-
concentration report: off-chain only, no `AuthorityScore` field added, no on-chain push. A sizing at
one instant, not a forecast (liquidity moves with utilisation) -- same limit the source research
states.

## Verification

18 new unit tests (`scripts/lib/tests/test_exit_capacity.py`, pure logic, no network). Full suite (6
test directories, 2367 tests) green. `python3 scripts/check_exit_capacity.py` -- read-only, Morpho's
public API only, no key, no transaction.
