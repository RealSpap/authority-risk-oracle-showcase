# Bounded-power timelockScore cap: investigated across 8 files, no unfixed gap found

2026-09-25. Roadmap item 2 ("voit large" round 2), the second of the two items held back pending
Spap's explicit go (received 2026-09-25). The earlier competitor-research synthesis described this
as the largest, most mechanical candidate: "dizaines d'occurrences" of a confirmed-bounded emergency
power (pause/freeze, not upgrade/fund-redirect) bypassing a real timelock, not yet capped the way
`score_fluid_liquidity_arbitrum`/`score_compound_v3_comet_*` already are (a real 55/60 cap, applied
2026-09-25 to Compound V3 Arbitrum/Base by commit `d6dca5e`).

## What was checked

Every function in the 8 files the synthesis's list touched or should have touched
(`chains/{base-ecosystem,ethereum-l1,hyperliquid,arbitrum-ecosystem,solana,plasma-ecosystem,zcash}/scorers.py`,
`scripts/lib/scorers.py`) mentioning "bounded", "pause-only", "availability-only" or "disclosed" --
read function by function, code body included, not just the grep hit -- via a dedicated research
pass, following the exact same discipline as the nested-signers investigation (verify each claim
against the current code, not the synthesis's line numbers, which had already been wrong once today
about Hyperliquid).

## Result: zero clean, unambiguous candidates

**Ten targets are already correctly capped** (Fluid Liquidity Arbitrum/Plasma, Compound V3 L1/
Arbitrum/Base, Ethena Minting, USDtb PSM, SparkLend Pool, Aave V3 Pool, Moonwell). Every OTHER
"bounded"/"disclosed" mention checked resolves to one of:

- **No timelock exists on the scored path at all** (Aerodrome PoolFactory, Aave V3 Horizon, Pendle
  V2, UNCX/Orvex lockers, Zenrock zenZEC/NEAR bridge, Radiant's real live branch) -- `timelockScore`
  is already 0 for that reason; there is nothing to bypass, so the Fluid/Compound V3 pattern does
  not apply.
- **The power is not actually bounded** (Arbitrum Security Council Safe, Robinhood Chain's L1
  rollup authority) -- these are full upgrade authorities, already scored more harshly (<=40) than
  the bounded-power cap band, correctly.
- **The bypass is worse than a simple freeze, scored accordingly** (Ethena's LayerZero OFT
  `setPeer`, a cross-chain redirect, not a pause) -- `timelockScore=15`, deliberately below the
  Fluid cap, not a gap.
- **The bounded claim is explicitly NOT confirmed** (Jupiter Lend's `guardians` on Solana, Euler's
  AccessControlEmergencyGovernor on Plasma) -- the scorer's own docstring says so ("inferred from
  the field's name... not independently confirmed", "the live read did NOT confirm") -- excluded by
  the project's own "confirmed, not assumed" discipline, correctly.
- **The bypassed value is already at the floor for a different reason** (Yuzu Money's real
  fund-affecting path has no delay regardless of its separate, bounded PAUSE_MANAGER_ROLE; Convex
  Finance Booster's real bypass is a Safe holding the intermediate layer in full power, not a
  bounded role).

## One genuine borderline case, already deliberately left uncapped -- a real open question, not a bug

**EigenLayer StrategyManager** (`chains/ethereum-l1/scorers.py:1576`,
`score_eigenlayer_strategy_manager`): a 1-of-7 Pauser Safe can freeze the contract, bounded
(freeze-only, no fund-redirect), same shape as Fluid's own bypass. But `timelockScore` here is
already fixed at 20 for a SEPARATE, more severe reason: the scored root itself is a 1-of-2 Safe that
can bypass the 10-day delay in FULL power (upgrade included), not just freeze. The scorer's own code
already reasons through this explicitly: *"there is no existing convention in this file for
stacking a second, independent bypass discount on top of a bypass already reflected in
timelockScore, so one is not invented here."* This is a genuine, unresolved methodology question
(should two independent bypasses on the same target compound, and how) -- not an oversight, and not
something to resolve unilaterally by inventing a stacking convention. Flagged for Spap; not applied.

## Conclusion

No code changed. The "dizaines d'occurrences" framing significantly overstated what a careful,
function-by-function read actually supports -- the same lesson as the nested-signers investigation
(`data/finding_2026-09-25-nested-signers-formula-investigation.md`): a research synthesis's summary
is a starting point for verification, not a work order. Applying a blanket cap across "dozens" of
sites without this check would very likely have double-discounted several targets whose scores were
already correct for other, more severe reasons.
