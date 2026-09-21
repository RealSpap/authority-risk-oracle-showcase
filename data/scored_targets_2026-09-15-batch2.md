# Scored targets - batch 2, 2026-09-15

Six more real scores pushed in one `updateScores()` call (tx
[`0x326a88df...`](https://explorer.testnet.chain.robinhood.com/tx/0x326a88dfbd5b31660a319bb5732d97db8eded8724cfdbab9b2e13d68dec8f585)),
closing out every target queued in the first pass. Same standard as before: every
number is a live `eth_call` against Robinhood Chain mainnet, cross-checked at least
twice, with any reverting/wrong-interface guess treated as a signal to keep digging
rather than a dead end -- that discipline is what surfaced the Arcus beacon pattern
and Lighter's real upgrade-gate mechanics below.

## Uniswap v3 Factory (`0x1f7d7550B1b028f7571E69A784071F0205FD2EfA`) - 2/100

`owner()` → Uniswap Labs' own `V3OpenFeeAdapter` (`0x05C420bC...`, a real, standard,
non-custom contract confirmed against Uniswap's own `protocol-fees` repo) → but that
adapter's `owner()` **and** `feeSetter()` both resolve to the same address,
`0x2BAD8182C09F50c8318d769245beA52C32Be46CD`, confirmed a bare EOA (codesize 0, live
balance, nonce 3). `setFactoryOwner()` takes any address with zero validation and zero
delay. Scope is real but bounded: this role can only set fee tiers and redirect the
protocol's *own* fee cut (already maxed at 25% via `defaultFee()=68`) -- it cannot
touch LP principal or swap pricing.

**Worth flagging on its own**: that EOA's address shares its entire 34-character
middle segment with the real Ethereum-mainnet Uniswap Governance Timelock
(`0x1a9C8182C09F50C8318d769245beA52C32BE35BC`) while differing only in the first and
last 4 hex characters -- a vanity-grinding pattern consistent with an address designed
to *look* like real Uniswap governance to anyone skimming a truncated address.

## Uniswap v4 PoolManager (`0x8366a39CC670B4001A1121B8F6A443A643e40951`) - 2/100

Same story, same EOA: `owner()` → `0x2BAD8182...46CD` (the identical vanity-lookalike
address from the v3 finding above), which also directly owns the protocol-fee
controller it appointed. One private key controls the entire fee-authority stack on
both Uniswap v3 and v4 on this chain. Scope confirmed from the real `v4-core` source:
the owner can only reassign the fee controller, not touch pools/hooks/liquidity
directly.

## Lighter (zkLighter) Escrow proxy (`0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d`) - 54/100

The strongest setup found so far, with one real crack: a genuine, on-chain-verified
3-of-5 Gnosis Safe (`0x8Caf9FF9...321ef`, Safe v1.4.1) is the "master" that must
propose every implementation upgrade through `UpgradeGatekeeper`
(`0x43CfF77C...D321ef`), behind a real 21-day notice period
(`approvedUpgradeNoticePeriod() = 1,814,400` seconds). But the gatekeeper's own
verified source contains `cutUpgradeNoticePeriod()`, callable by a single
`securityCouncilAddress` -- confirmed on-chain as a **bare EOA**
(`0x4972E0Ca...7eFDb`, codesize 0), not the "3-of-5 security council" that third-party
write-ups (L2BEAT, a Medium post) describe. One private key can zero the 21-day window
the instant the Safe queues an upgrade. A real multisig and a real delay both exist,
but the delay's entire protective value rests on one unverified, single-signer
override.

## Arcus pToken factory + beacon (`0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB`) and both live pTokens - 43/100

Not a bare-EOA setup: the beacon's `owner()` and the factory's own AccessControl
`DEFAULT_ADMIN_ROLE` both resolve to the same real, active 2-of-3 Gnosis Safe
(`0x81B80499...541bd`, v1.4.1, no modules, no guard). But this Safe is a single point
of control over **every pToken Arcus has issued or will ever issue through this
beacon** -- one `upgradeTo()` call rewrites the shared implementation for pBTC, pBTC3x,
and anything deployed later, and there is no timelock anywhere in the chain protecting
that call. Scored identically on the factory and both live pTokens
(`0x925F92F0...90eA0` pBTC, `0x4472C69d...10E3e` pBTC3x) since they share the exact
same authority chain -- a consumer checking either token directly gets the real answer
without needing to know to check the factory separately.

## Running total

7 targets scored, all pushed and independently re-read from testnet after the
transaction: 2 Uniswap Labs contracts and 2 Arcus pTokens share their authority with
2 other now-scored targets (the shared EOA, the shared beacon+Safe), one Morpho vault
scores 19, Lighter scores highest at 54 -- still well short of what a "real timelock"
target should look like, since even that score's delay has a bare-EOA bypass.

Next: wire the recurring off-chain updater (cron / GitHub Actions) so these scores
refresh on a real cadence instead of one-off manual pushes, then move the whole stack
to Robinhood Chain mainnet.
