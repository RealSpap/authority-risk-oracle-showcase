# Nine Morpho markets ($130M) price their collateral from a number a role holder POSTS, not from a market

2026-09-26. Follow-up to `finding_2026-09-26-morpho-market-oracle-authority-rerun.md`. Its "no admin found" bucket hid a different kind of
authority: a feed whose contract has no `owner()` and no proxy admin can still be **posted by a role holder**. `scripts/check_morpho_market_oracles.py`
now flags any feed, or the feed it wraps through `underlyingFeed()`, whose dispatcher exposes `setRoundData(int256)` (selector `0xa4381d1f`, read from the
implementation of an EIP-1967 proxy or from the contract itself, so it works on a chain with no explorer). Disclosed only: no score reads this.

## What was found (Morpho API listed markets >= $1M on the 6 tracked chains, 0 unread)

9 markets, **$130M supplied**, price by `setRoundData`: Robinhood mGLO/USDG $32M, Ethereum mWIN/PYUSD $26M, Ethereum mF-ONE/USDC $25M, Base mGLO/USDC
$24M, Ethereum mM1-USD/USDC $9M, Ethereum mGLOeuro/EURCV $6M, Monad mHyperBTC/cbBTC $4M, Ethereum mHyperBTC/USDC $3M, Ethereum
CarryTradeUSDTRYLeverage/USDC $2M. The selector was matched on all nine. The access-control model was read from verified source for mF-ONE and mGLO; the role holders, bounds and
last answers of eight of the nine were then read live by `scripts/check_posted_price_feeds.py` (the ninth, Monad, has no full-history log source here).

## Read in full: mF-ONE (Ethereum), mGLO (Base and Robinhood Chain)

The Morpho oracle reads a read-only wrapper (`CustomAggregatorV3CompatibleFeedDiscounted` / `...Adjusted`, no write function, immutable discount or
adjustment) whose `underlyingFeed()` is a `TransparentUpgradeableProxy` for Midas's `MFOneCustomAggregatorFeed` / `MGloCustomAggregatorFeed`.

- **The price is written by `setRoundData(int256)`, restricted to the holder of `feedAdminRole()`, and bounded only by `[minAnswer, maxAnswer]`** (verified
  source, `contracts/feeds/CustomAggregatorV3CompatibleFeed.sol`). The bounds are **$0.10 and $1,000.00** (8 decimals) against a last answer of $1.1255
  (mF-ONE, 295 rounds) and $1.0058 (mGLO, 5 to 6 rounds): the holder can post any price from -91% to about +88,700% (mF-ONE) or +99,300% (mGLO) in one
  transaction. The deviation cap (`maxAnswerDeviation`, 40% and 100%) is enforced only by the separate `setRoundDataSafe`, not by `setRoundData`.
- **The role holder is one bare EOA per feed** (RoleGranted replay from the access-control contract, matched to live `hasRole`): `0x85A56E09...` for mF-ONE,
  `0x83b573AA...` for mGLO. **The same `0x83b573AA...` posts mGLO on both Base and Robinhood Chain**, and the two chains carry the identical last answer
  (`100576635`) one second apart (timestamps 1790326703 and 1790326704, 2026-09-25 08:58 UTC): one key, one batch, two chains and $56M of markets.
- **Root of the role**: the shared `MidasAccessControl` (`0x0312A9D1...`, same address on Ethereum and Base) has `DEFAULT_ADMIN_ROLE` held live by **a bare
  EOA `0xd4195CF4...` and a 1-of-3 Safe `0xB60842E9...`** (the same two on both chains, read by log replay and live `hasRole`; earlier holders revoked: 2 on Ethereum, 4 on Base),
  with no delay: either can grant the feed role to any address immediately. Robinhood Chain uses its own access-control contract (`0xe5F08720...`); its
  `DEFAULT_ADMIN_ROLE` is the same bare EOA `0xd4195CF4...` plus another 1-of-3 Safe (`0x563e0fc2...`).
- **The upgrade path is delayed, the price path is not**: each feed proxy's ProxyAdmin is owned by a 7,971-byte timelock with `getMinDelay()` = 172,800 s
  (2 days) on Ethereum, Base and Robinhood Chain. Posting a price does not go through it.
- Not read: the identity of any of these keys, Midas's off-chain process around them, whether the NAV updates are reviewed. A NAV-priced token has to trust
  its issuer for the price; this is the concentration of that trust, not evidence of misuse. Last updates were routine (2026-09-25).

## All eight readable markets (`scripts/check_posted_price_feeds.py`, live 2026-09-26)

| Market | Chain | Supplied | Posting role holder | Bounds vs last price | Last post |
|---|---|---|---|---|---|
| mGLO/USDG | Robinhood | $32M | bare EOA `0x83b573AA...` (same as Base) | -90% / +99,327% | 09-25 08:58 |
| mWIN/PYUSD | Ethereum | $26M | bare EOA `0x532FEDcF...` | **-31% / +7%** | 09-25 10:11 |
| mF-ONE/USDC | Ethereum | $25M | bare EOA `0x85A56E09...` | -91% / +88,746% | 09-25 17:05 |
| mGLO/USDC | Base | $24M | bare EOA `0x83b573AA...` | -90% / +99,327% | 09-25 08:58 |
| mM1-USD/USDC | Ethereum | $9M | bare EOA `0x9e104D8B...` | -90% / +96,767% | 09-23 17:20 |
| mGLOeuro/EURCV | Ethereum | $6M | bare EOA `0xa301F0eD...` | **-10% / +10%** | 09-23 10:39 |
| mHyperBTC/USDC | Ethereum | $3M | bare EOA `0x40468649...` | -90% / +97,359% | 09-21 15:02 |
| CarryTradeUSDTRYLeverage/USDC | Ethereum | $2M | bare EOA `0xf2e01868...` | -91% / +87,887% | 09-25 13:36 |
| mHyperBTC/cbBTC | Monad | $4M | UNREAD (no full-history log source) | -90% / +97,359% | 09-21 15:02 |

- **Eight of eight readable feeds have exactly one bare EOA as posting role holder**, each feed its own EOA except mGLO (one EOA on Base and Robinhood).
- **Bounds are not uniform**: two feeds (mWIN, mGLOeuro; $32M) have realistic ranges (a bad post can move the price by at most -31% / +7%, or +-10%); the
  other six ($99M including the Monad one) accept any price from $0.10 to $1,000 against a ~$1 price.
- `DEFAULT_ADMIN_ROLE` of the access-control contract behind every read feed is the same bare EOA `0xd4195CF4...` plus a 1-of-3 Safe (`0xB60842E9...` on
  Ethereum and Base, `0x563e0fc2...` on Robinhood Chain), no delay; every ProxyAdmin owner read is a timelock of 172,800 s (2 days).
- mHyperBTC carries the same last answer and timestamp on Ethereum and Monad: one post, two chains, as for mGLO.

## What this is and isn't

Measured, live, read-only. Not shown: how each market's LLTV, liquidity and liquidation setup would limit the damage of a bad price, or whether the two narrow-range feeds
are narrowed on purpose. The Monad feed's holders were not read. No score changed,
no new target: rating a market oracle is a new target type and Spap's decision. The two EOAs above are added to the overlap registry (Ethereum, Base;
Robinhood's registry is deliberately not touched), which lets `who_controls.py` answer for those addresses.

## Verification

`python3 scripts/check_morpho_market_oracles.py --min-usd 1e6` (Morpho API, 6 public RPCs) lists the nine; the role holders come from
`RoleGranted`/`RoleRevoked` logs (Tenderly for Ethereum, Blockscout's logs API for Base, the Robinhood RPC for Robinhood) matched against live `hasRole`;
bounds and last answers from direct `eth_call`; source from Blockscout (`eth.blockscout.com`). No key, nothing sent.
