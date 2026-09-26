# The 4 "untracked" HIP-3 dexes flagged by the bounded-loop routine (flx, hyna, abcd, cash) are delisted or empty

2026-09-26. The 26/09 bounded-loop routine's Hyperliquid worker listed four HIP-3 perp dexes the oracle does not track. Checked live, read-only
(`api.hyperliquid.xyz/info` `perpDexs` and `metaAndAssetCtxs` per dex, plus `eth_getCode` on HyperEVM for each address): the lead has no economic weight today.

| Dex | Markets | Delisted | Open interest | 24 h volume | Tracked |
|---|---|---|---|---|---|
| xyz | 125 | 16 | **$3,800M** (109 active assets) | $523M | yes |
| io (EntropyIO) | 11 | | $56.6M | $19M | yes |
| para (Paragon) | 36 | | $17.7M | $3M | yes |
| mkts (Markets by Kinetiq) | 24 | | $7.9M | $9M | yes |
| flx (Felix Exchange) | 16 | **16 of 16** | $0 | $0 | no |
| hyna (HyENA) | 25 | **25 of 25** | $0 | $0 | no |
| cash (dreamcash) | 17 | **17 of 17** | $0 | $0 | no |
| abcd (ABCDEx) | 1 | | $0 | $0 | no |

The tracked dexes hold effectively all of the ~$3.88B open interest; the four untracked ones have every asset delisted (or a single empty market). Not a coverage gap.
Nothing to add, no score touched.

Two facts the read gave along the way, disclosed only:
- **xyz, the largest HIP-3 dex ($3.8B open interest), has a bare EOA deployer** (`0x88806a71...`, no code on HyperEVM); it is already a tracked, scored target.
- **One EOA, `0x94757f8d...`, is the `oracleUpdater` of two dexes, io (tracked) and flx (delisted).** A key that posts prices for a live dex also posts for a wound-down one;
  no exposure through flx today since it has no open interest.

## Verification

`perpDexs` (10 dexes) and `metaAndAssetCtxs` per dex from Hyperliquid's public info endpoint; open interest = sum of `openInterest x markPx` over assets; delisting from each
asset's `isDelisted`; address classification by `eth_getCode` on `rpc.hyperliquid.xyz/evm` (`lib/authority_index.classify_code`, Safe shape via `safe_owners_and_threshold`).
