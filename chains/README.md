# Chains

One folder per ecosystem. Each holds the scorer that re-derives its targets from live chain state, the deploy record and push
script for its oracle, dated audits in `data/`, and (where the ecosystem differs from the common method) its own `METHODOLOGY.md`.

| Folder | Oracle published on | Targets | Oracle kind | What is specific |
|---|---|---|---|---|
| [`ethereum-l1/`](ethereum-l1/) | Sepolia | 25 | Solidity | the deepest set: Safe, Timelock and DAO resolution, Morpho vaults, Aave and Compound price paths |
| [`arbitrum-ecosystem/`](arbitrum-ecosystem/) | Arbitrum Sepolia | 13 | Solidity | GMX V2, Compound V3, Pendle, Fluid, Uniswap V3; Aave V3 guardian Safe shared with Base; bridge-alias arithmetic for L1-to-L2 timelocks |
| [`base-ecosystem/`](base-ecosystem/) | Base Sepolia | 13 | Solidity | Morpho Blue and Aerodrome among others; signer overlap with Arbitrum and Robinhood Chain ([finding](../data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md)) |
| `robinhood-chain` (scorers in the shared library) | Robinhood Chain testnet | 63 | Solidity | the longest tail of small protocols; the mainnet target |
| [`tempo/`](tempo/) | Tempo Moderato | 14 | Solidity | stablecoins (USDC.e, USDT0, pathUSD, EURC.e, ...) and Morpho Vault V2 instances, own [methodology](tempo/METHODOLOGY.md) |
| [`plasma-ecosystem/`](plasma-ecosystem/) | Plasma testnet | 9 | Solidity | Euler Earn and Yuzu among others |
| [`monad/`](monad/) | Monad testnet | 9 | Solidity | picked as the largest uncovered mainnet TVL among eight candidate chains |
| [`hyperliquid/`](hyperliquid/) | HyperEVM testnet | 15 | Solidity | HIP-3 dex proxies, key collisions moved to a derived `oracleKey`, own [methodology](hyperliquid/METHODOLOGY.md) |
| [`solana/`](solana/) | Devnet | 18 published (26 scored) | native Anchor program ([`program/`](solana/program/)) | Squads v4 multisigs, SPL Governance, upgrade authorities, own [methodology](solana/METHODOLOGY.md) |
| [`zcash/`](zcash/) | Testnet | 6 attested | none: OP_RETURN commitments | Zcash has no contract VM, so scores are committed in transactions, own [methodology](zcash/METHODOLOGY.md) |

The oracles publish on testnets; the targets are mainnet protocols read from mainnet RPCs. Counts are the ones read live from each oracle (`python3 scripts/live_target_counts.py`). The shared scoring helpers
(`classify_holder`, Safe and timelock resolution, cross-ecosystem overlap, price-path walking) live in
[`../scripts/lib/`](../scripts/lib/), and each ecosystem's `scorers.py` is a thin layer over them.

To add a target: write its scorer entry with a note for every fact that was read, add a test that pins the score, run
`python3 scripts/validate_all_scorers.py --ecosystem <folder>`, and push through the ecosystem's `deploy/push_scores.py`
(dry run by default).
