# Who can move the price a Morpho market trusts: 5-day rerun, MetaOracles unwrapped, a second feed committee found

2026-09-26. New read-only tool `scripts/check_morpho_market_oracles.py` (+ `scripts/lib/market_oracles.py`, 7 tests).
It complements, and does not replace, `chains/ethereum-l1/scripts/sweep_morpho_oracle_authority.py` (21/09, ninth pass of
`data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`), which first showed that the price authority of Morpho
markets sits in the feed proxies and that four 4-of-9 Safes with the same 9 signers own the Chainlink ones. That sweep
was re-run today (171 markets, $5.98B, same shape: 77 markets, $3.74B, 62% behind those Safes, up from 75 and 61% on 21/09).
Disclosed only: no score, scorer or on-chain push reads any of this.

## What the new tool adds

1. **EIP-1967 proxy-admin path.** The 21/09 sweep reads `owner()` of each feed; a feed that is a `TransparentUpgradeableProxy`
   has no `owner()` and was among the "$0.87B owner not read". The tool reads the EIP-1967 admin slot, then the ProxyAdmin's owner.
2. **MetaOracles unwrapped.** A `MetaOracleDeviationTimelock` has no owner and no setter (21/09, still true: the Robinhood
   ($339M) and Monad ($24M) implementations the 21/09 sweep could not read have exactly the same 27 dispatcher selectors as the
   verified Base/Ethereum one, compared through `lib/code_review.selectors`). But it reads a `primaryOracle()` and a
   `backupOracle()`, whose feeds have owners. Following them is what the "no admin" conclusion stopped short of.
3. **Committee grouping.** Controllers are classified (EOA / Safe k-of-n / timelock delay) and Safes with the same threshold and
   signer set on different chains are grouped, so a committee's reach is one number, not one per chain.

## Result (163 listed markets >= $1M on the 6 chains this oracle tracks, $5,765M; 141 feeds/oracles read, 0 unread)

| Committee (same threshold and signers, all chains read live) | Chains | Live price path | Incl. MetaOracle backup path |
|---|---|---|---|
| **Chainlink feed-proxy owner Safes, 4-of-9, 9 signers** | Ethereum, Base, Robinhood, Arbitrum, Monad | **92 markets, $4,140M, 72.4%** | 99 markets, $4,902M, 85.8% (of $5,717M) |
| **RedStone-built feed proxies' ProxyAdmin Safes, 2-of-3, 3 signers** | Ethereum, Monad, HyperEVM (+ Tempo, not in Morpho's API) | 15 markets, $98M | same |
| **1-of-1 Safe, one signer** | Ethereum, Monad (same address) | 0 | 2 markets, $26M (backup oracle of a PT-USDat market) |

- "Live price path" = direct feeds, or a MetaOracle's primary oracle. "Backup path" only takes over after a deviation, a
  challenge and a timelock. A market counts once. The 7 markets ($763M) reached only through a backup path include the two
  largest custom-oracle markets: **Base USDe/USDC $390M and Robinhood USDe/USDG $339M**. On the Robinhood one I re-checked by
  hand (independent `eth_call`s): its `backupOracle()` -> `BASE_FEED_1()` -> `owner()` = the Robinhood Chainlink Safe `0xeE27D5Ae...`.
- The Chainlink figure is **higher than the 62% published 21/09** (72% live, 86% with backup). Not reconciled row by row: the
  denominators differ (this tool: tracked chains only; the sweep: every chain incl. Katana, Arc, OP), this one also reads the Arbitrum
  and Monad Safes and the proxy-admin path, and five days passed. It is a snapshot of one instant, not a trend.
- The 9 Chainlink signers are identical on all five chains (set equality read live on L1, Base, Robinhood, Arbitrum, Monad); the
  RedStone 3 are identical on Ethereum, Monad, HyperEVM and Tempo. The identical Chainlink signers were already in the 21/09
  finding; the RedStone committee is new.
- **RedStone group, what was verified**: the feeds are `TransparentUpgradeableProxy` contracts whose verified implementation
  source is RedStone's (`"RedStone Price Feed for strUSD_FUNDAMENTAL"`, `@redstone-finance/evm-adapters`), ProxyAdmin owner =
  the 2-of-3 Safe, no timelock on the upgrade path. **Not verified**: who the three signers are (RedStone's own keys or the
  protocols'), so this does not say RedStone runs them. It closes the backlog item about Tempo's cbBTC/pathUSD market oracle: same
  three signers as the Ethereum/Monad/HyperEVM committee (`0x32e59eCD...` on Tempo).
- **Weak controllers** (bare EOA or Safe threshold <= 2): 17 markets, $124M in total, all inside the two small committees above
  (kHYPE/WHYPE/lstHYPE/UBTC markets on HyperEVM $64M; strUSD, trUSD, FXRP, LBTC markets on Ethereum $29M; Monad $5M) plus the
  1-of-1 Safe.
- **"No admin found"**: 43 markets, $689M, feeds with neither an EIP-1967 admin nor `owner()`: exchange-rate adapters (wstETH,
  weETH), Pendle PT linear-discount wrappers, custom aggregator feeds, tranche oracles. NOT proven immutable: some of these
  types may carry role-based admins that neither `owner()` nor the proxy slot would show (not checked here).

## Registry additions (registry only, no score reads it)

`scripts/lib/cross_ecosystem_overlap.py` gained `chainlink_feed_admin` (Ethereum, Base, Arbitrum, Monad), `redstone_feed_admin`
(Ethereum, Monad, HyperEVM, Tempo) and `single_signer_feed_admin` (Ethereum, Monad). `who_controls.py` now indexes 110 groups,
457 addresses, 372 signers; 26 signers reach 5 ecosystems (17 Aave guardians, 9 Chainlink), 12 reach 4 (9 Morpho, 3 RedStone).

## Not done, on purpose

No score changed and no new tracked target: rating a market's oracle would be a new target type and a calibration decision that
is Spap's. Role-based admins on the custom aggregator feeds and the unread Katana/Arc/OP chains stay open.

## Verification

`python3 scripts/check_morpho_market_oracles.py --min-usd 1e6` against Morpho's public API and 6 public RPCs, exit 0, 0 unread
(an earlier run on `mainnet.base.org` hit 429 and reported 8 feeds UNREAD rather than "no admin": the tool counts a failed read as
unread, and Base/Arbitrum now use their publicnode endpoints). `python3 -m unittest` on `test_market_oracles.py` (7). No key read,
nothing sent.
