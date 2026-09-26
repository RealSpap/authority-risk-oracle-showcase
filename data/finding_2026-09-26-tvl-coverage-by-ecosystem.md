# Share of each ecosystem's TVL the tracked targets cover, and the biggest untracked protocols (2026-09-26)

**Predecessor**: `data/coverage_2026-09-21-tvl-by-ecosystem.md` made the same measurement for six ecosystems on 21/09 (same method, hand-run, same reading: name matching errs both ways, TVL is not custody, SSV and wBETH are staking figures). This note makes it reproducible, adds Tempo, Hyperliquid and Solana, and corrects two entries below; it was written before I found the earlier one.

Answer to "why don't the other ecosystems grow like Robinhood": the number of targets is the wrong yardstick. `scripts/check_tvl_coverage.py` matches the tracked labels to DefiLlama's `/protocols`
by name (CEX proof-of-reserves excluded) and measures the share of value. Read-only; the match is crude, so the unmatched list matters more than the percentage.

| Ecosystem | Tracked labels | DefiLlama TVL | Protocols | Matched by name | Share of value |
|---|---|---|---|---|---|
| Robinhood Chain | 63 | $1.65B | 180 | 42 | 98.4% |
| Hyperliquid L1 | 16 | $9.81B | 172 | 11 | 92.3% |
| Plasma | 9 | $0.96B | 60 | 9 | 87.4% |
| Base | 13 | $9.60B | 728 | 22 | 86.8% |
| Tempo | 14 | $0.10B | 13 | 5 | 84.2% |
| Solana | 26 (18 published, 8 added today) | $17.24B | 331 | 40 | 71.2% (was 67.4% with 18) |
| Ethereum | 26 | $169.79B | 1,480 | 39 | 51.4% |
| Arbitrum | 13 | $3.20B | 834 | 26 | 46.7% |
| Monad | 9 | $2.14B | 128 | 11 | 46.0% |

Zcash has no DefiLlama chain page and is not measured.

## Reading

- Robinhood is not a scoring outlier, it is a small chain (180 protocols, $1.65B) that is nearly done: 63 targets cover 98% of its value. Base, Plasma, Tempo and Hyperliquid are 85 to 92% covered with 9 to 16 targets.
- The real gaps by value are **Ethereum (51%), Arbitrum (47%) and Monad (46%)**, and Solana at 71%. Those are the ecosystems where a new target moves coverage.
- Solana rose 3.8 points from the eight leads scored today (Solstice and Huma were in its untracked top ten).
- **Correction**: the first run of this note listed "EigenCloud $7.0B" as untracked and put Ethereum at 47.3%. EigenCloud is DefiLlama's new name for EigenLayer, which is a tracked target (`EigenLayer StrategyManager`); a rename alias is now in `scripts/lib/tvl_coverage.py` and Ethereum is 51.4%.

## Largest untracked, per ecosystem (top five; the full list is in the script output)

- **Ethereum**: SSV Network $14.1B, Binance staked ETH $9.5B, ether.fi Stake $5.2B, Arbitrum Bridge $3.5B, USDT0 $3.5B, Base Bridge $3.0B, Maple $3.0B, Polygon Bridge $2.9B. Five of these eight (ether.fi, USDT0, Maple, the Polygon bridge, and the Arbitrum bridge's authorities) were traced today in `finding_2026-09-26-l1-custody-authority-traces.md`; the Base bridge trace failed and is still open. The Arbitrum Security Council that controls the Arbitrum bridge is a scored target on the Arbitrum ecosystem; the L1 bridge contracts themselves are not scored targets.
- **Arbitrum**: Hyperliquid Bridge $594M (a name-match miss: it is tracked in the Hyperliquid oracle as "Hyperliquid legacy USDC bridge (Bridge2)"), Spark Savings $289M, USD AI $213M, AZverse Perps $50M, edgeX Bridge $49M.
- **Monad**: K3 Capital $385M, Pendle V2 $199M, Hyperithm $197M, Valos $105M, Reservoir Protocol $60M.
- **Solana**: Binance Staked SOL $1.24B, Sentora Curator $362M, OnRe $297M, DFDV Staked SOL $219M, CCIP $215M; then a run of liquid-staking wrappers (Phantom, The Vault, Bybit, JPool, Helius).
- **Base**: LayerZero V2 $98M, Clearstar $95M, Aera V3 $81M. **Hyperliquid**: Morpho Blue $193M (tracked on Ethereum), Veda $63M, Derive V2 $52M. **Plasma**: Veda $31M, LayerZero V2 $31M, Unit $20M.

## Limits

The match is by name: it misses renamed protocols and counts a protocol tracked on another chain as untracked (Morpho Blue on Hyperliquid, the Arbitrum bridge on Ethereum). DefiLlama's value is TVL, not custody risk: a $14B
staking network is not automatically a target this oracle can score (SSV and EigenCloud have no single authority path of the kind scored here). Nothing here adds a target; each candidate still needs an authority trace, a scorer and tests, and
a new scored target is Spap's call.

## Reproduce

`python3 scripts/check_tvl_coverage.py --cache <file> --out <file>` (labels from the live scorers, about 15 minutes; DefiLlama `/protocols`; Robinhood from `api/scores.json`).
