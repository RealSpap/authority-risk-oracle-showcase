# Who can move the prices Aave V3 Ethereum Core lends against: 58% of supply is priced by Aave's own adapters, moved by a two-key council and one live automated agent, within limits the update path enforces (disclosed, not scored)

2026-10-01. Tool: `scripts/check_lending_price_authority.py` (read-only, eth_call only), test
`scripts/tests/test_check_lending_price_authority.py`. Amounts are from the run of about 10:50 UTC. The tool went through two independent reviews that day;
the second found that its selector search missed a compiler encoding, which changed one conclusion (see below).

## Why we looked

On 10 Mar 2026 an automated agent updated the wstETH CAPO price adapter of Aave V3 Ethereum with no multisig and no
timelock. The snapshot ratio and its timestamp ended up misaligned, the cap fell 2.85% under the live rate, and about 27 M$
(some 10,938 wstETH, 34 accounts) were liquidated
([Aave post-mortem](https://governance.aave.com/t/post-mortem-exchange-rate-misallignment-on-wsteth-core-and-prime-instances/24269)).
The repository scores who controls the Aave pool itself (`score_aave_v3_pool`), but not who can move the price the pool
uses. This is the first measurement of that path.

## What was measured

Each reserve's price source comes from `AaveOracle.getSourceOfAsset`. A source that answers `ACL_MANAGER()` is one of
Aave's own adapters: its parameters are set by RISK_ADMIN or POOL_ADMIN holders of that ACLManager. A source that
reverts there is an external feed (Chainlink and the like), whose own owner is out of scope here.

| Price source kind | Reserves | Sources | Supplied |
|---|---|---|---|
| LST CAPO adapter (setter `setCapParameters`) | 15 | 15 | $8.68B |
| Stable CAPO adapter (setter `setPriceCap`) | 11 | 10 (USDG and PT-USDG share one) | $5.43B |
| Older capped adapter, "Capped USDT/USD", used by USDe (setter `setPriceCap`) | 1 | 1 | $0.56B |
| "Capped EURC/USD" ratio-capped adapter (setter `setPriceCapRatio`) | 1 | 1 | $0.05B |
| Pendle PT adapter (setter `setDiscountRatePerYear`) | 15 | 15 | $0.004B |
| "Fixed mUSD/USD" adapter (setter `setPrice`) | 1 | 1 | about $0 |
| External feed | 23 | 20 | $10.62B |
| **All reserves** | **67** | | **$25.34B** |

So 44 reserves ($14.71B, 58% of supply) are priced by Aave adapters, each with a known setter. 42 of
them answer to the Core ACLManager `0xc2aaCf65...`; tETH and ezETH (about $1M) answer to the Prime instance's
ACLManager `0x013E2C75...`.

On each ACLManager, the RISK_ADMIN and POOL_ADMIN holders were replayed from RoleGranted/RoleRevoked since deployment
and each confirmed live by `hasRole` on two RPCs. A holder is a contract that can only do what its code does, so each
holder's code (behind one EIP-1967 hop for the two proxies) was searched for the selector of an adapter setter or of a
steward entry point that leads to one, in the three forms solc emits that the search knows (pushed whole, as a
`PUSH32` of the selector already shifted, or shifted at run time: `PUSH4 (sel >> k)`, `PUSH1 (224 + k)`, `SHL`):

| ACLManager | Holder | Name (aave-permissions-book) | Controlled by | Setter path in code |
|---|---|---|---|---|
| Core | `0x13a9CC64...` | Manual AGRS | RISK_COUNCIL `0x47c71dFE...` | LST, stable, Pendle (setters and steward entries) |
| Core | `0x6f48d9Cd...` | Manual AGRS, second one (granted 30 Sep 2026) | same RISK_COUNCIL | LST, stable, Pendle (setters, shifted form, and steward entries) |
| Core | `0x98217A06...` | Core GHO Aave Steward | RISK_COUNCIL `0x8513e6F3...` (Safe 2-of-3) | none seen |
| Core | `0x529e2374...` | PendleDiscountRateAgent | AgentHub, see below | `setDiscountRatePerYear` (shifted form) |
| Core | `0x5513224d...` | Gho Core Direct Minter (proxy, implementation 3.9 kB) | | none seen |
| Core | `0xbe284044...` | EModeCategoryAgent | | none seen |
| Core and Prime | `0x5300A1a1...` (POOL_ADMIN) | governance executor | | none seen; adapters accept POOL_ADMIN directly (checked on the USDe adapter) |
| Prime | `0x5BA8d98f...` | a steward of the same size as Manual AGRS (16,066 bytes) | same RISK_COUNCIL `0x47c71dFE...` | LST, stable, Pendle |
| Prime | `0x2cE01c87...` (proxy, implementation 4.6 kB), `0x5C905d62...` (council `0x8513e6F3...`) | | | none seen |

**The council.** `0x47c71dFE...` is a Safe 2-of-2 with no module: one bare EOA (`0x606dC57c...`) and one Safe 1-of-3
(`0xb291232F...`). So two keys, the EOA and any one of three, drive all three stewards that reach a price. The EOA also
sits in the 2-of-6 Safe under the GHO council, and `0xb291232F...` is an owner of both councils.

**What the update path lets the council do.** Read from `getRiskConfig()` of `0x13a9CC64...` and `0x5BA8d98f...` (15
limit pairs, layout from aave-dao/aave-v3-risk-stewards `IRiskSteward.sol`, main branch) and from that repository's
`RiskSteward.sol`:

- LST adapters: one update per adapter every 3 days; the maximum yearly growth may move 5% (relative) per update; the
  snapshot ratio may never be set above the live ratio, and the steward reverts if the adapter is capped after the
  update (`InvalidPriceCapUpdate()`, selector `0x10228354`).
- Stable adapters: one update every 3 days, the cap may move 0.5% per update, and the update reverts if the new cap is
  under the current price (`CapLowerThanActualPrice()`, selector `0xeefa4b6e`, raised by the adapter).
- Pendle PT adapters: one update every 2 days, the discount rate may move 2.5 points (absolute) per update.

The second Core steward `0x6f48d9Cd...` does not answer `getRiskConfig()`, so its limits were not read. All three were
then **simulated by eth_call from the council's address** (no transaction), each next to a harmless control update:

| Simulated update | Control | `0x13a9CC64...` | `0x6f48d9Cd...` | `0x5BA8d98f...` (Prime) |
|---|---|---|---|---|
| LST snapshot at half the live ratio (weETH; tETH on Prime) | 0.01% under the live ratio: accepted | refused | refused | refused |
| Stable cap 10% lower in one update (USDT) | 0.1% lower: accepted | refused | refused | no stable adapter behind Prime |
| Pendle discount 50 points higher in one update (PT-srUSDe-22OCT2026) | +0.1 point: accepted | refused | refused | no PT adapter behind Prime |

Checked by hand the same day:
- On wstETH, a snapshot at 99.9% of the live ratio passes and 99.8% is refused. With the adapter's 7-day minimum
  snapshot age and 8.8% yearly growth, the cap would land under the live rate.
- On USDT, a cap 0.5% lower passes at the live price. The same cap is refused by both Core stewards once the asset
  price is overridden above it (state-override eth_call).
- Updates sent from an unrelated address are refused (`InvalidCaller()`).
- The USDe adapter accepts any RISK_ADMIN or POOL_ADMIN caller, but it has no `getPriceCap()`, so both Core stewards'
  stable path reverts on it. Among today's holders, only the governance executor has a working path to it, per the
  code search; its direct `setPriceCap` is accepted in simulation.
- On the PT adapter with the most supply, the only update after deployment (8 Jul 2026) came in a transaction sent by
  an owner of the council's 1-of-3 Safe to that Safe.

## The automated path that is live

The March incident went through an AgentHub: an automated agent holding RISK_ADMIN, executing what a risk oracle
publishes. That path still exists, with different parties. The AgentHub `0x95E3015c...` (owner: the governance executor)
has 7 registered agents:

- 5 are disabled, among them `CapoPriceCapUpdate_Core` (the CAPO path of March) and the rate-strategy agents.
- 2 are enabled, and neither is permissioned, so anyone may trigger them. Both execute the RiskOracle `0x683d1A91...`
  ("LlamaRisk PT Risk Oracle (Aave V3 Ethereum Core)"):
  - **PendleDiscountRateAgent**, agent 5. One allowed market, PT-srUSDe-22OCT2026 ($3.5M supplied). The range module
    `0x9240a666...` lets it move the discount rate by at most 1 point (absolute) per update, with at least 2 days
    between updates. It has never injected an update.
  - **EModeCategoryAgent**, agent 6. It has injected 18 updates since 3 Sep 2026, about every 3 days, the last two on
    28 Sep 2026 (`UpdateInjected` events of the hub). These change e-mode collateral parameters, not a price.

Who can publish to that RiskOracle, read by hand from its getters and from the verified sources on Blockscout:

- **Authorized sender.** The only one replayed from `AuthorizedSenderAdded/Removed`, and confirmed by `isAuthorized`, is
  `0x1D85000D...`, a contract verified as `LlamaguardRiskOracleRouter`. It accepts reports from a configured Chainlink
  workflow forwarder (`isReportWriteSecured()` true).
- **Router owner and updater.** Both are the Safe 2-of-4 `0x1a0267E9...`, which also owns the RiskOracle. They set
  routes, throttles and report age.
- **Router guardian.** The Safe 4-of-7 `0x2CFe3ec4...`, which can pause. The same Safe is the agents' admin on the hub.
- **Shared signers.** One owner of the 2-of-4 (`0x49cE85E1...`) is also an owner of the council's 1-of-3 Safe, and the
  4-of-7 counts that 1-of-3 Safe among its owners.

Who sets the agents' limits: the agent admin of agents 5 and 6 is the same Safe 4-of-7 `0x2CFe3ec4...`. It may, in
one transaction and with no timelock, widen the range in the range module, add allowed markets, shorten the minimum
delay and enable or disable these two agents (`onlyOwnerOrAgentAdmin` and `onlyHubOwnerOrAgentAdmin` in the verified
`AgentConfigurator.sol` and `RangeValidationModule.sol`). The 2-of-4 decides what gets published. So the 1 point and 2
days above are settings, not hard limits. The hard limit is the PT adapter's own `MAX_DISCOUNT_RATE_PER_YEAR`: 10.22
points on PT-srUSDe-22OCT2026, against 3.77 today, which bounds the automated path at about 0.36% of that PT's price
today.

## What it means

- The March failure (a cap computed under the live rate at the moment of the update) is now refused by every steward
  that can reach a CAPO adapter. That is measured, not taken from a governance post.
- What remains is a bounded, slow path held by two keys with no timelock:
  - a stable cap can be walked down 0.5% every 3 days toward the live price, never under it;
  - an LST cap can be set just above the live rate, where a sudden legitimate jump of the exchange rate would hit it;
  - a PT discount can be raised 2.5 points every 2 days by the council.
  The stable and LST changes are visible on-chain when they are made, before they bite. A PT discount change lowers
  the PT price in the same transaction, by the change times the time left to maturity: about 0.06% for 1 point and
  0.14% for 2.5 points on PT-srUSDe-22OCT2026 today, about 20.5 days from maturity.
- A second, automated path is live on PT prices, held by different parties: what the LlamaRisk Safe 2-of-4 publishes
  through a Chainlink workflow, within settings the Safe 4-of-7 can change at once. Today it covers one PT ($3.5M) and
  has never fired; its hard limit is the adapter's maximum discount, about 0.36% of that PT's price.
- Among today's RISK_ADMIN holders, four carry a call path to a price setter: the three council-driven stewards and
  the PendleDiscountRateAgent. The CAPO agent of March is disabled.

## Limits

- Disclosed only: no published score reads this. Whether a bounded parameter path like this one should count as oracle
  authority in the score is a methodology decision, not taken here.
- The path search is a heuristic over a closed list of selectors, in the two forms solc emits. A holder that executes
  arbitrary calls, or builds a selector at run time, would be missed. The three Core holders without a path were
  searched in their own code, or in their implementation's code for the proxy, but the absence of an arbitrary-call
  executor was not proven. A first version of the search missed the shifted form and wrongly cleared the
  PendleDiscountRateAgent; it was caught by the second review.
- The second Core steward's own limits are unread; only its behaviour was simulated.
- One adapter per kind and steward was simulated, the one with the most supply, not all 44.
- External feeds (23 reserves, $10.62B) are out of scope here: whoever controls a Chainlink feed is a separate authority.
- One pool. Aave Prime, EtherFi and Horizon instances, other chains, and other lenders (Spark, Compound, Fluid) were not
  measured.
