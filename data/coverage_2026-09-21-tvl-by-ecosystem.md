# How much of each ecosystem's value do the tracked targets cover? (2026-09-21)

A first measurement, from open data only (DefiLlama's `/protocols` for TVL per chain, matched by protocol name to the labels of the
targets each oracle tracks; for Robinhood Chain also hoodscan's public project registry). It is an estimate with a stated method and known
errors, not an audit, and it measures **listed TVL**, not risk.

## Result

| Ecosystem | DefiLlama TVL | Protocols | Share tracked by name | Largest not matched |
|---|---|---|---|---|
| Robinhood Chain | $1.58B | 163 | **99.0%** ($16.3M untracked over 126 protocols) | Neutral Trade $2.2M, StonkBrokers $1.8M, DexFi $1.4M |
| Plasma | $0.96B | 59 | 88.4% | Veda $30M, Unit $20M |
| Base | $9.62B | 723 | 59.6% | Steakhouse Financial $1.54B, Gauntlet $0.61B, Spark Liquidity Layer $0.27B, Grove $0.27B |
| Ethereum L1 | $167B | 1,462 | 52.6% | SSV Network $14.1B, Binance staked ETH $9.6B, USDT0 $3.3B, Maple $3.0B, Base Bridge $3.0B |
| Arbitrum | $3.27B | 832 | 51.0% | Hyperliquid Bridge $0.6B, Spark Savings $0.29B |
| Monad | $2.19B | 122 | 46.2% | K3 Capital $0.4B, Pendle V2 $0.21B, Hyperithm $0.2B |

Tempo, Hyperliquid and Solana were not measured.

## How to read it

- **Robinhood Chain's 99.0%** needs four manual corrections to the name match, because the protocol is tracked under another label:
  Steakhouse Financial ($511M, tracked through its Morpho vaults), Lighter ($96.5M, its escrow proxy), up v2 ($1.2M, governed by the same
  Safe as the tracked up v3) and Arcus pTokens ($0.6M). Without them the raw match reads 60.5%. The remaining $16.3M is spread thin: the
  largest is $2.2M.
- **Name matching errs both ways.** `EigenCloud` on Ethereum is EigenLayer's new name and is tracked; `Hyperliquid Bridge` on Arbitrum is
  tracked in the Hyperliquid oracle; a protocol counted as tracked may be tracked through one contract of several.
- **TVL is not custody.** SSV Network ($14.1B) and Binance staked ETH ($9.6B) are staking-attestation figures: the ETH sits behind
  validators' withdrawal credentials, not in a contract whose authority this oracle would score. Counting them as gaps overstates the gap;
  bridges and vault layers are the opposite, they hold real funds and their TVL understates how much trust they carry.

## Leads for real custody, not yet traced

Named because the figures are large and the contracts hold funds; each needs a full authority trace before anything is claimed about it:

- Maple (Ethereum, $3.0B, lending pools) and USDT0 (Ethereum, $3.3B, an OFT adapter that locks USDT);
- the Steakhouse and Gauntlet vault layer on Base ($2.15B together): the Morpho Blue singleton is tracked, the vaults' owner and curator
  Safes are not (the Robinhood Chain vault scorer already does this for its own vaults);
- the L1 bridge contracts of Arbitrum and Base ($3.5B and $3.0B), whose authority is an Arbitrum DAO and Security Council path partly
  tracked from the L2 side;
- on Robinhood Chain, hoodscan's registry lists 115 projects, 79 with confirmed contracts, and 54 with contracts and no tracked one by name.
  The custody-shaped ones are lending (accountable, termmax, ripe-protocol, gage, own, ravenhood), bridges (debridge, across, relay),
  lockers and launchpads (hoodlock, pons, par-family). Their TVL is small; their shape (funds or bridged authority) is why they are listed.

## What this does not say

- It does not say 99% of the risk is covered: TVL is one lens, and a small bridge or launchpad can hold a large tail risk.
- The name match is approximate and was corrected by hand only for Robinhood Chain.
- Adding a target is a scoring project (an authority trace, a scorer, tests, an append on the oracle pushed by the maintainer); this note
  only says where the value is.
