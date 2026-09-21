# HIP-3 `setMarginTableIds` / `setMarginModes` on open positions: docs check (2026-09-19)

Status: **still OPEN**. No score change. This is a documented search, not a resolution.

Question (METHODOLOGY.md section 6): can a HIP-3 deployer's `setMarginTableIds` or
`setMarginModes` change the terms of positions that are already open, and so force
liquidations? If yes, both actions join the root-control set of rule 4.2.

## What the primary docs say

Pages fetched 2026-09-19 as Markdown from `hyperliquid.gitbook.io/hyperliquid-docs/`
(append `.md` to the page path). SHA-256 prefix of each fetched copy in brackets.

| Page | What it says that matters here |
|---|---|
| `for-developers/api/hip-3-deployer-actions` [bbd228094d478f1e] | `SetMarginTableIds` = sorted list of (asset, margin table id), ids non-zero. `InsertMarginTable`: at most 3 tiers, max leverage 1 to 50. `SetMarginModes` = list of (coin, `strictIsolated` / `noCross` / `normal`). `SetOpenInterestCaps` is bounded (cap at least max(1,000,000, half of current OI)). **No statement about open positions for either margin action.** |
| `for-developers/api/hip-3-deployer-actions-1` [fa8d4e1c1dca6da2] | Same types, older shape. No statement about open positions. |
| `trading/margin-tiers` [f6e6f5ec37b26359] | Maintenance margin rate and deduction "depend only on the margin tiers, not the asset". |
| `trading/margining` [95891a47102caca3] | "Leverage is only checked upon opening a position". Strict isolated: margin cannot be removed. HIP-3 dexes also have `noCross`. |
| `hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals` [31358d37ccd0ace6] | "Enabling cross margin on an asset is irreversible", and mainnet validators enforce eligibility standards before a deployer may enable it. |

## Reading

- `setMarginTableIds`: maintenance margin is a function of the margin tiers alone, and
  liquidation uses maintenance margin. If an asset's table id changes, the natural
  reading is that open positions are measured against the new table from then on, which
  would let a deployer push existing positions under maintenance. This is an
  **inference**. No page says it, and the "leverage is only checked upon opening" line
  is about initial leverage, not maintenance.
- `setMarginModes`: bounded in one direction only. Cross margin cannot be switched
  off once enabled (irreversible), and turning it on needs validator eligibility. The
  docs do not say what happens to open isolated positions when a mode moves between
  `strictIsolated` and `noCross`.

## What would close it

A testnet experiment (deploy a HIP-3 dex on HyperCore testnet, open a position, change
the margin table, read `clearinghouseState`). This needs a funded HyperCore testnet
account, which runs into the same faucet blocker as the HyperEVM deploy (a mainnet
deposit is required first). The other option is a statement from the Hyperliquid team.
Until then the two actions stay in `notes`, outside the root-control set, as before.
