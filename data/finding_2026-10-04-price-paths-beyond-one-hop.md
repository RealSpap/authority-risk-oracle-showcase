# Price paths one hop further upstream than the oracleAuthorityScore looks: disclosed, not scored

2026-10-04. Companion to the METHODOLOGY section "oracleAuthorityScore for price consumers", decided that day. The rule
scores whoever controls what a lending market reads directly: a Chainlink proxy, a rate provider, an upgradeable feed. It
does not score that contract's own inputs. This file lists the inputs found behind the scored paths during the research
of 2026-10-04, so a reader can apply a deeper rule by hand. Every fact below was read on chain that day and re-checked
by a second, independent pass; the proofs that say "simulated" are `eth_call` from the named account, with a random
account reverting as the control.

## Summary

| Target | Score under the rule | Input one hop further | Its controller | Would give |
|---|---|---|---|---|
| Morpho V1 Adpend USDC, Morpho V1 1337 USDC (Ethereum) | 31 | deUSD minted without backing into sdeUSD | EOA with an EIP-7702 delegation | 2 |
| Aave V3 Base, Compound V3 USDC (Base) | 52 | L1 cbETH exchange rate, relayed by a Chainlink feed | bare EOA | 2 |
| Aave V3 Plasma, Aave V3 Monad | 52 | L1 Maple syrup rate controller | not read | 20 (unknown) |
| Aave V3 Ethereum Core | 52 | Stader ETHx rate behind the rsETH LRTOracle | Safe 3-of-6 | 44 |
| Aave V3 Ethereum Core, Compound V3 USDC (Ethereum) | 52 | Lido oracle reports, bounded | Lido Dual Governance (4 days) | no change |

The deeper rule was not chosen because it scores a market by the weakest link of every token it lists, several hops away,
which a reader cannot check by hand, and because each extra hop needs its own verified reading of a different protocol.

## Morpho V1 Adpend and 1337: unbacked deUSD raises the sdeUSD rate

The sdeUSD market's oracle reads `BASE_VAULT` sdeUSD `0x5C5b196a...` through `convertToAssets`. sdeUSD defines
`totalAssets()` as its deUSD balance minus the unvested amount, so any deUSD minted or sent to it raises the rate at once.
For a lender, a rising collateral price is the harmful direction.

- deUSD `0x15700b56...`: `minter()` is deUSDMinting `0x69088d25...`, whose `mint(receiver, amount)` is gated by
  `MINTER_BURNER_ROLE` with no per-block cap.
- The live holders of that role (RoleGranted replay, confirmed with `hasRole`) are the deUSD OFT adapter `0xaa110f49...`
  (owner: the Safe 3-of-5 `0xd7cdbde6...`) and the CCIP BurnFromMintTokenPool 1.5.1 `0x1016225b...`.
- The pool's `owner()` is `0x0f04909e...`, an EOA with an EIP-7702 delegation. The pool trusts its router's
  `isOffRamp`; its owner can set the router. Simulated: `setRouter` succeeds from the owner, and
  `deUSDMinting.mint(sdeUSD, 1e27)` succeeds from the pool. The inbound rate limiter is disabled on all three remote chains.
- The path reaches about 100% of both vaults' allocation. As a bare key, it would score 2.

Context: on 2026-10-04 the market's `price()` reverted because the RedStone deUSD value was stale, so no harm was live,
and the 1337 vault had set the market's cap to 0 with its removal pending. The scored 31 comes from the same market: the
RedStone `deUSD_FUNDAMENTAL` feed `0xca727511...` and its adapter sit behind ProxyAdmin `0x8223a627...`, owned by a Safe
2-of-3. The sdeUSD upgrade path (owner and `DEFAULT_ADMIN`, Safe 3-of-5) scores 43.

## Aave V3 and Compound V3 on Base: the L1 cbETH owner

Both Base markets price cbETH through the Chainlink "cbETH-ETH Exchange Rate" feed `0x868a501e...` (Compound through a
wrapper that multiplies it by ETH/USD). The path reaches 15.92% of Aave V3 Base's priced supply and 4.95% of the Base
Comet's (live runs of 2026-10-04). That feed is owned by the Chainlink Safe 4-of-9 and is scored
(52). It relays the rate of cbETH `0xBe989514...` on Ethereum, whose controls are three single keys with no delay:
`owner()` `0x4b8741c8...` (bare EOA) can call `updateOracle`, after which the new oracle sets any rate above 0; the
Zeppelin-style proxy admin `0xeee4ac8a...` (bare EOA, slot `0x10d6a54a...`) can upgrade it; and the current
ExchangeRateUpdater's owner `0xa57afe0b...` (bare EOA) sets the updaters' allowances. As a bare key, it would score 2.

## Aave V3 Plasma and Monad: L1 Maple rates not read

syrupUSDT on Plasma (about 2% of supply) and syrupUSDC on Monad (about 25%) are priced through Chainlink exchange-rate
feeds that copy L1 Maple rates (live values within about 0.01% of L1). The Chainlink feeds are scored (52). The L1 rate
controllers behind them were not read; under a deeper rule they would be UNREAD, so 20.

## Aave V3 Ethereum Core: Stader behind rsETH

rsETH's LRTOracle is scored: the `DEFAULT_ADMIN` of LRTConfig, a Safe 6-of-11 with no timelock, can switch off the price
limit and re-point an asset oracle (both simulated), which gives 56. One of its inputs is ETHx: the LRTOracle reads
EthXPriceOracle `0x3D08ccb4...`, which reads StakePoolsManager `0xcf5EA1b3...` `getExchangeRate()`, fed by StaderOracle
`0xF64bAe65...`. StaderConfig's `MANAGER` is a Safe 3-of-6 `0xaafb3178...` with no timelock (one grant, no revoke): 44.
Aave Core's score stays 52, set by the Chainlink proxies.

## Lido: bounded, and why the bound matters

stETH and wstETH rates move only by AccountingOracle reports (HashConsensus, 5 of 9 members), bounded by the
OracleReportSanityChecker; the limits, roles and upgrades belong to the Lido Agent, executable only through Dual
Governance (afterSubmit 259,200 s). The path is governance-grade and disclosed. The bound still allows a 3.6% decrease
per 36-day window. On the Ethereum USDC Comet, wstETH's liquidation point sits 4.65% below a position opened at its
borrow limit (5.9% on Base and Arbitrum), so the bound alone does not liquidate such a position; one that has drifted
closer to its limit can be.

## Inside the target's own governance (no change)

- Aave V3 Monad's "Fixed mUSD/USD" adapter `0xbbb58AA3...` has `setPrice`, callable by any POOL_ADMIN: the
  PayloadsController executor and the Aave PROTOCOL_GUARDIAN Safe 4-of-7. That seat is already scored in the market's own
  composite.

## Outside the scored set

The rule is applied to ten Aave V3, Compound V3 and Morpho V1 markets so far (METHODOLOGY, Scope). Morpho V2 vaults on
Robinhood Chain are not yet scored this way.
On Steakhouse USDG `0xBeEff033...`, the mGLO market (about 6% of the allocation) reads an immutable "PriceLowered" wrapper
over the Midas CustomAggregator `0x49d9dd1f...`, whose prices are written by `setRoundData` from a single bare EOA
`0x83b573aa...` (the only live feed-admin holder; bounds 0.1 to 1000 USD; simulated). Under the same one-hop rule, that
path would score 2.
