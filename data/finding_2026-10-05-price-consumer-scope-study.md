# Which other tracked targets read prices, how to score them, and what that needs decided first

2026-10-05. The price-consumer rule of 2026-10-04 (METHODOLOGY, "oracleAuthorityScore for price consumers") was built for
ten lending markets. This study asked the same question of every other tracked target that might read prices. One reader
studied each family of targets: it built the priced rows, read the governance delay and ran the engine. A second reader
then re-ran every recipe live and checked every claimed fact. Figures below are those re-runs. A target is wired (its
published field computed by the engine) only where the table says so; everywhere else the field still publishes 100,
which METHODOLOGY now calls "not yet computed".

## Not price consumers: 100 stays, and means not applicable

| Target | Why |
|---|---|
| Morpho Blue singletons (Ethereum, Base, Robinhood Chain) | Each market's oracle is fixed when the market is created (permissionless, no setter), and bad debt stays inside that market. The owner has no lever on any price. The exposure is scored at the vault layer. The METHODOLOGY wording ("neither reports nor reads a price") needs one clause for this case. |
| Solend DAO governance (Solana realm) | Vote weight is deposited SLND, no price read. The real Solend price consumer, the Save lending program, is not tracked yet. |
| Spark Savings USDG and the Spark ALM proxy (Robinhood Chain) | The share price is an accumulator bounded by a rate range; the ALM controller has no oracle-priced path wired today (re-check if its PSM becomes non-zero). |
| Euler access-control emergency governor (Plasma) | A governance relay that holds no funds; the vaults it governs are counted under the Euler factory. |

## Wired on 2026-10-05

| Target | Score | Binding path |
|---|---|---|
| Aave V3 Horizon | 52 | Chainlink proxies, Safe 4-of-9, no delay (GHO priced by a provable constant) |
| Morpho V1 Gauntlet USDC Prime, Spark USDC, Steakhouse USDC, Grove x Steakhouse USDC High Yield (Base) | 52 each | Chainlink proxies, Safe 4-of-9 |
| Morpho Vault V2 Steakhouse USDG (Robinhood Chain) | 2 | its mGLO market (about 6%) is priced by `setRoundData` from a single bare EOA |
| Morpho Vault V2 NetNet Credit (Robinhood Chain) | 2 | the stock tokens' beacon admin role sits with a bare EOA (every tokenized-stock market) |
| Morpho Vault V2 Ethena x Steakhouse, Grove x Steakhouse (Robinhood Chain) | 100 | nothing allocated today; a note says live caps let the allocator allocate at once |
| Morpho Vault V2 Steakhouse Turbo, Purinta (Robinhood Chain) | 20 | Turbo: 99% idle, the priced remainder reads spUSDG, which has no spec yet. Purinta: API3 feeds behind a Safe deployed without a proxy, not cleared by the Safe gate |
| Morpho Vault V2 Steakhouse Prime USDC and EURCV, Morpho V1 Steakhouse USDT and USDC (Ethereum), Morpho V1 vault (Monad) | 20 | waiting on the first two methodology choices below (EtherFi and Lido delays shorter than the vaults' 7 days, Sky's sUSDS; Chronicle on Monad), and on a spec for a Vault V2 whose share price is another market's rate (steakUSDC, steakEURCV) |
| Radiant (Arbitrum, Aave V2 fork) | 52 | Chainlink proxies (Arbitrum Safe 4-of-9); its oracle owner is a Safe with no delay |
| GMX V2 Synthetics (Arbitrum) | 52 | the Chainlink Data Streams VerifierProxy owner, a Safe 4-of-9, behind every provider price |
| GMX V1 Vault (Arbitrum) | 2 | the PriceFeedTimelock `admin()`, a bare EOA (no code on two RPCs), can switch secondary prices on and change the price deviation instantly (both simulated); the vault is wound down but holds about 1.1M USD with open positions |

## Readable with engine work only (no methodology choice)

| Target | Expected | What it needs |
|---|---|---|
| Fluid Liquidity (Plasma / Arbitrum) | 52 / 43 | A Fluid-specific walk of the vaults' oracles and an on-chain USD weight for every vault (two dust vaults keep Arbitrum at 20 until they are valued). |
| Euler V2 factory (Plasma) | 2 | Row sources that are several addresses, getters feed, oracleBaseCross, oracleCrossQuote, specs per EulerRouter. The binding path is the sdeUSD rate (3.3%): its `owner()` on Plasma is `0x0f04909E8AC81B8727FF7f0b2EF4e9F817033978`, a bare key there (no code, read 2026-10-05). On Ethereum the same address carries an EIP-7702 delegation and owns the deUSD CCIP pool behind Morpho Adpend/1337. |
| Euler V2 (Monad) | 2 | Same engine work. Seven routers (about 83% of supply) are governed by a 1-of-2 Safe (composite 10); a vUSD rate behind 11.9% has an investment manager that is a bare EOA. |
| Telos Consilium Euler Earn (Plasma) | 43 | Same engine work plus a Pendle oracle spec. About 90% of its allocation prices exUSD at a fixed 1 USD (disclosed). |
| Kamino Liquidity, Jupiter Lend (Solana) | 45, 35 | Solana readers for the Scope configuration and for Jupiter's oracle accounts; Jupiter also needs a Pyth receiver spec. |

## Blocked on a methodology choice

| Choice | Targets | Score under each option |
|---|---|---|
| A timelock shorter than the target's own delay: UNREAD (today) or score its proposer | Steakhouse USDT and USDC V1, Prime USDC and EURCV V2 (Ethereum, 7-day bar against EtherFi's 2-day OPERATION timelock); Morpho vault on Monad (Chronicle) | UNREAD: 20 (published from the next push). Proposer scored: 49 (EtherFi Safe 4-of-7), 31 on Monad (Chronicle Safe 2-of-3). |
| A DAO-governed rate (Lido Dual Governance, Sky): count the vote period as delay, or give the DAO a convention score | the same Ethereum vaults, SparkLend | UNREAD: 20. Counted: governance-grade or about 80. |
| A median of three feeds (Chronicle, Chainlink, RedStone): the weakest feed, or two of three | SparkLend (72% of supply) | Weakest: 31 (RedStone Safe 2-of-3). Two of three: 52. |
| A downward-only or banded lever: bounded or scored | Jupiter Lend (a loss authority can only mark a token down), Moonwell (a RedStone primary held within 2%) | Bounded: 45 and 52. Scored: 35 and 31. |
| One convention for the same 4-of-9 multisig on Solana and on EVM | Jupiter Lend, Kamino | Solana formula 45, EVM formula 52. |
| A Safe deployed without a proxy (API3) passes the Safe gate once its vendored code is diffed | Morpho Purinta USDG | 20 until then; the reviewer also argues the dAPI name setter (a 4-of-4 signer set) should be scored. |
| Dolomite's GMX GM markets: prove each keeper-settable config key bounded, or score the weakest keeper | Dolomite (24.7%) | Proven: 52. Weakest keeper: 2. Today: 20. |

## Engine limit found by the study

Solidity can place constant data (a long revert string, a `description()` string) between the last INVALID opcode and the
metadata map. The opcode scan then reads those bytes as code, so a verified immutable wrapper fails the immutability test
and its path is UNREAD (fail-closed, but wrong). Seen on Chronicle's OracleAggregator (SparkLend) and a Moonwell composite
oracle. Fixing it means recognizing that data section; until then those paths stay UNREAD.

The data section is now recognized (`_executable`, 2026-10-05): both Chronicle Aggors and the Moonwell LBTC composite pass
as immutable wrappers, live.

## Decisions of 2026-10-05 and what they changed

The project owner took the choices of the table above on 2026-10-05, each time the recommended option:

| Choice | Decision |
|---|---|
| A timelock shorter than the target's delay | Score the accounts that can schedule on it, behind its delay (`delay_points`: the notice-period curve, capped at 60). Only a timelock whose code is a verified TimelockController build is credited at all. |
| A DAO's delay | The whole window its code imposes. Lido: vote 5 days + Dual Governance afterSubmit 3 days (+ afterSchedule 1 day, left out while emergency protection lets the committees skip it): 8 days. Sky, with no minimum vote, counts its 2-day pause only and is scored with its DAO convention (81). |
| A median of several feeds | The weakest feed. |
| A banded or downward-only lever | A band bounded by code that only the target's governance can widen is bounded (Moonwell); a downward-only lever is scored (Jupiter Lend's Huma loss authority). |
| Solana and EVM | Each chain keeps its formula. |
| A proxyless Safe | Accepted after a line-by-line comparison with the release it vendors (API3's Safe: 15 files identical to safe-contracts v1.3.0). |
| Dolomite's GMX keeper keys | Proven bounded, or UNREAD. The proof failed on several keys: UNREAD. |
| Fluid's weights | Fluid's API for USD weights only; an unpriced vault is material. |

Results, live on 2026-10-05 (every wired target re-run end to end on the final code):

| Target | Before | After | Binding path |
|---|---|---|---|
| Morpho V1 Steakhouse USDT and USDC, Vault V2 Prime USDC and EURCV (Ethereum) | 20 | 52 | Chainlink proxies, Safe 4-of-9. EtherFi's OPERATION proposer (a 4-of-7 Safe behind 2 days) scores 67, Sky 81, Lido and the steakUSDC share price are governance-grade |
| SparkLend (Ethereum) | 100 (not computed) | 31 | RedStone inside each Chronicle Aggor median, its ProxyAdmin owned by a 2-of-3 Safe |
| Morpho V1 vault (Monad) | 20 | 49 | Chronicle's two 7-day timelocks, each scheduled by a 2-of-3 Safe, against the vault's 14 days |
| Moonwell (Base) | 100 (not computed) | 52 | Chainlink proxies, Safe 4-of-9; the RedStone LBTC primary is bounded |
| Fluid Liquidity (Plasma) | 100 (not computed) | 52 | Chainlink SUSDAI-USDAI exchange-rate feed, Safe 4-of-9 |
| Fluid Liquidity (Arbitrum) | 100 (not computed) | 20 | the sUSDai rate (75% of debt) has no spec; its admin Safe carries an unanalyzed module |
| Dolomite (Arbitrum) | 100 (not computed) | 20 | GMX keeper keys of the GM markets (25%) unbounded |
| Jupiter Lend (Solana) | 100 (not computed) | 35 | Huma PST loss authority, a 2-of-3 Squads with no delay |
| Morpho Vault V2 Purinta (Robinhood Chain) | 20 | 50 | API3 reader proxies, a proxyless 4-of-8 Safe |
| Morpho Vault V2 Steakhouse Turbo (Robinhood Chain) | 20 | 52 | Chainlink USDE/USD, Safe 4-of-9; spUSDG bounded, its upgrade through Sky (81) |

TelosC Surge EulerEarn (Plasma) moved from 43 to 34: an EulerEarn's owner and curator are no longer the target's own, so the two EulerRouters its curator Safe (2-of-5) governs, which re-point any price at once, are scored. Every other wired target is unchanged. Two regressions were caught by these live re-runs and not by the tests: the generic
getters `oracle()` (GMX V2 read its own Oracle: 52 fell to 20) and `base()` (an Euler adapter's base token: TelosC fell from
43 to 2). Both are now followed only beside a getter that identifies the build.

A second independent review of the merged families (four readers, 2026-10-05) found no fail-open path that moves a published
score today, and eleven weaknesses, fixed the same day: Sky's pause is Sky governance only while `MCD_PAUSE.owner()` is zero;
a Chronicle ward of an unknown kind is UNREAD, not dropped; Moonwell's and Dolomite's own-governance verdicts are added by
their own entry points alone, and Moonwell's own set needs the admin to be the pinned TemporalGovernor; Fluid's team multisig
is scored (an Avocado 6-of-12 with no delay: 56) instead of called own, an oracle input that is an account with no code is a
bare key, and the Liquidity timelock counts only because its build is verified; the Euler FactoryGovernor is pinned by code.

## Left open on 2026-10-05

- Moonwell: the RedStone LBTC primary's controller (a 2-of-3 Safe) cannot move the price outside the band, but it can make
  every LBTC read revert (the market freezes) and can hold LBTC inside the band while the real price leaves it, so the
  Chainlink fallback never takes over. Scored, it would give 31.
- Purinta: the dAPI name setter behind API3's server (a 4-of-4 signer set) is one hop deeper and disclosed. Scored, 44.
- Steakhouse Prime vaults (Morpho Vault V2) as a share-price input: `setIsAllocator` and the fee setters have a 0-second
  timelock and an allocator can call `setMaxRate` at once. Bounded by code (capped fee and rate, the share price cannot
  fall at once), disclosed, not scored. Scored, the two Prime vaults would follow their curator Safe, about 31.
- Fluid: the composite still calls the team multisig's instant powers a bounded bypass and credits the 24-hour timelock,
  while the oracle field now scores it (56).
- Dolomite: accounts holding both EXECUTOR and BYPASS_TIMELOCK roles on DolomiteOwnerV2 execute any queued call at once, so
  the governance delay is 0, while the composite still credits 300 seconds. Its DEFAULT_ADMIN Safe (2-of-3) can swap any
  market's oracle at once through AdminPauseMarket, and one of three bare keys can freeze any market. The score stays 20
  for three reasons: the GMX keeper keys, the three GMX ROLE_ADMIN timelock paths, two frozen markets of unknown value.
- Fluid Arbitrum stays 20 for two reasons: the sUSDai rate (75% of debt) has no spec and its admin Safe carries an
  unanalyzed module, and 23 dust vaults that the API does not price (a few dollars of debt) count as material.
- Unverified timelocks stay UNREAD wherever they are reached: four Euler timelocks on Monad, two on Plasma (one with a
  10-second delay), GMX's ConfigTimelockController. None binds a score today. The Aave V2, GMX and Euler factory entry
  points read their own timelock's delay without the verified-build test.
- A Vault V2 whose `curator()` is zero is UNREAD even when its timelock already meets the target's delay (fail-closed).
