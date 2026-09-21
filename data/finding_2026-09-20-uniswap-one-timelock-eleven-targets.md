# One Uniswap Timelock is the root of 11 tracked targets on 5 ecosystems (2026-09-20)

Found during the registry coverage pass, by asking the one question the cross-exposure field exists for: which tracked targets
share a root, across ecosystems, that the oracle still scores as if they did not?

## The finding

Uniswap's Ethereum L1 Governance Timelock (`0x1a9C8182C09F50c8318d769245bEA52c32BE35BC`, 2-day delay, GovernorBravo behind it) is
the root authority of every Uniswap target this oracle tracks, on five ecosystems, reached through three different bridges:

| Ecosystem | Tracked targets | How the Timelock is reached |
|---|---|---|
| Ethereum L1 | V3 Factory, V4 PoolManager | directly (V4) or through a fee adapter (V3) |
| Arbitrum | V3 Factory | the Arbitrum alias `0x2BAD8182...46CD` of the Timelock (an alias has no code) |
| Base | V3 Factory, V2 Factory, V4 PoolManager | one OP-stack forwarder `0x31FAfd48...72A9` whose slot 1 is the Timelock |
| Robinhood Chain | V3 Factory, V4 PoolManager, UniswapX reactor, V2 feeToSetter | the same Arbitrum-family alias |
| Monad | V4 PoolManager | a Wormhole message receiver whose trusted Ethereum sender is owned by the Timelock |

That is 11 targets under one root identity, on more ecosystems than any other single root this oracle tracks.

## What the oracle said before

`crossExposureScore` read 80 on the two Ethereum L1 targets (V3 and V4 share a root group inside L1) and **100 on the other nine**
(Arbitrum 1, Base 3, Robinhood Chain 4, Monad 1). The 100 came from a documented rule that a target that is DAO or Timelock
rooted "has no Safe signer set, so it is not counted". That rule was written when the cross-ecosystem sweep could only compare
Safe owner sets. It was a limit of the tool, not a judgement that the Timelock is not a shared root. The field's own definition
("does this target's root authority also control another tracked target") is met exactly.

## What changed

The 2026-09-20 convention (a shared root across ecosystems folds into `crossExposureScore` as a flat 80, never raising a lower
in-ecosystem value) now covers a shared contract root as well as a shared committee. Nothing else about the score moves:
`compositeScore` does not use `crossExposureScore`, so every Uniswap composite is unchanged (confirmed by the live drift check
below: only the cross column differs).

- **Scorer changes:** Arbitrum V3 Factory, Base V3/V2/V4 and Monad V4 now return 80; Ethereum L1's two keep 80 and gain an
  explicit note; Robinhood Chain's four `uniswap_stack` targets take the same flat 80 through the group's hand-set, dated
  `cross_ecosystem` flag, like Pendle, Morpho Blue and Curve.
- **Never asserted on an unverified root:** each scorer folds to 80 only if this run confirmed the root live (Arbitrum: alias
  recomputed and matching, L1 Timelock delay/admin/quorum read; Base: forwarder slot 0 is the OP-stack messenger predeploy and
  slot 1 is exactly the known Timelock; L1: the Timelock address matches and the GovernorBravo quorum is readable; Monad, hardened
  2026-09-21: the PoolManager owner is the Wormhole receiver, the receiver's `messageSender()` is the known Ethereum sender, and that
  sender's `owner()` is the Timelock, both hops read live; the first version of this fold relied on a dated snapshot for the
  Ethereum side, and the docstring named the getter `sender()`, which reverts, instead of `messageSender()`). A degraded run keeps 100
  and says why.
- **Registry:** a `uniswap_dao_timelock` group in each of the L1, Arbitrum, Base and Monad registries, holding the Timelock (and
  on Arbitrum its alias) as a single root identity, plus the Timelock added to Robinhood Chain's group, so
  `scripts/check_cross_ecosystem_overlap.py` reports the shared root instead of missing it.

## What this does not say

- It does not say Uniswap governance is weak. Its admin, multisig and timelock sub-scores are unchanged and high (80 / 100 / 75).
  It says a takeover of that one DAO would reach 11 targets on 5 ecosystems, which is what a cross-exposure score is for.
- 80 is a flat fold, not a count. Robinhood Chain (4 targets in one group) and Base (3) are not lowered further for their
  within-ecosystem sharing, because those two ecosystems compute the in-ecosystem side per signer group, not per target as
  Ethereum L1 does. That inconsistency is documented in METHODOLOGY.md and is not changed here.
- The Robinhood Chain flag is hand-set and dated. If Uniswap re-roots that alias, it must be removed by hand. Monad no longer
  depends on a snapshot (see above), and the fold there switches itself off if either hop stops matching.

## Not on-chain yet

Scorer and registry changes are on GitHub. The deployed testnet oracles still hold the previous values (Uniswap cross 100 on
Arbitrum, Base and Monad; Robinhood Chain's four also read 100). They reach the chains at the next re-push of Arbitrum, Base,
Monad and Robinhood Chain, run by the owner of the updater key; a live drift check on 2026-09-20 shows exactly these
`crossExposureScore` differences and no others beyond the Compound V3 ones already documented.
