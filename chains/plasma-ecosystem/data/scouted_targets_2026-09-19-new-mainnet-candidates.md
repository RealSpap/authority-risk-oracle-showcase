# Plasma Ecosystem -- new mainnet candidate scouting, 2026-09-19

Phase: scouting, addendum to the 2026-09-18 batch. Task: find 2-3 NEW
legitimate Plasma MAINNET (chain 9745) targets with real Plasma-specific
TVL/usage (not global multi-chain TVL), verified on 2+ independent
sources/RPCs, and screened for duplicate authority already tracked
elsewhere in this project.

## Method

1. Pulled DefiLlama's full protocol list (`api.llama.fi/protocols`,
   8.87MB, 71 protocols with `'Plasma'` in `chains[]`), sorted by
   `chainTvls.Plasma` (the Plasma-SPECIFIC figure, not `tvl` which is
   global across every chain a protocol supports).
2. Cross-checked the top candidates against `yields.llama.fi/pools`
   filtered to `chain == 'Plasma'` (45 pools) for pool-level granularity.
3. For each real candidate, traced the authority live via direct
   `eth_call`/`eth_getCode` JSON-RPC against `https://rpc.plasma.to`,
   cross-verified on a second independent public RPC
   (`https://plasma.gateway.tenderly.co` -- found reachable this pass;
   `9745.rpc.thirdweb.com`, already used by `score_pendle_plasma()`,
   returned HTTP 403 this pass).
4. Grepped every candidate's resolved authority address(es) case-
   insensitively against this ENTIRE repository (not just
   `chains/plasma-ecosystem/`) to check for duplicate authority already
   tracked under a different label, per this pass's explicit instruction
   to prioritize that check.

## Top Plasma-specific TVL, DefiLlama `chainTvls.Plasma`, 2026-09-19

| Protocol | Plasma TVL | Status |
|---|---|---|
| Aave V3 | $489.7M | already tracked (`score_aave_v3_pool_plasma`) |
| Binance CEX | $422.0M | excluded -- custodial balance, no authority contract |
| Telos Consilium | $91.8M | **NEW TARGET** -- see below |
| Gate | $67.3M | excluded -- CEX |
| Pendle V2 | $65.2M | already tracked (`score_pendle_plasma`) |
| Yuzu Money | $61.5M | **NEW TARGET** -- see below |
| Bybit | $59.0M | excluded -- CEX |
| Fluid DEX | $52.2M | excluded -- duplicate authority, see below |
| Fluid Lending | $43.9M | already tracked via `score_fluid_liquidity_plasma` (shared root) |
| Plasma Saving Vaults | $32.3M | excluded -- same vault as Veda, ambiguous root, see below |
| Veda | $31.5M | excluded -- same vault as Plasma Saving Vaults |
| Re7 Labs | $14.3M | excluded -- too small on Plasma specifically (own vault: $3.75M) |
| Plasma One | $12.5M | excluded -- below the significance bar this pass, and no on-chain lending/vault authority surface (a card/banking product) |
| Euler V2 (protocol-level) | $1.99M | already tracked (`score_euler_v2_*`, DefiLlama's own protocol-level number undercounts the EulerEarn curator vaults, which get separate per-curator attribution) |

## NEW TARGET 1: Telos Consilium ("TelosC Surge" EulerEarn vault)

Full sourcing, live-read numbers and authority-chain trace are in
`chains/plasma-ecosystem/scorers.py`'s own
`score_telos_consilium_euler_earn_plasma()` docstring -- not duplicated
here. Summary: found by enumerating `eulerEarnFactory`
(`0xA3843A73e6a9F81309B931237Ca4759B3B02ff0E`, from the official
`euler-xyz/euler-interfaces` address book) live -- 19 EulerEarn vaults
deployed on Plasma, each individually read. "TelosC Surge"
(`0xA9C251f8304b1B3Fc2B9e8FCAE78D94eFF82Ac66`) holds ~$100.0M USDT0
(live `totalAssets()`, cross-verified on 2 RPCs), owner==curator = a real
2-of-5 Gnosis Safe, no guardian set. "TelosC Haven" (~$3.4M) shares the
identical Safe -- disclosed in the scorer's own notes, not pushed as a
second target (would double-count the same authority).

**Duplicate-authority check: NEGATIVE (genuinely new).** The 5 Safe owner
addresses do not appear anywhere else in this repository -- not in the
Aave guardian committee, not the Ethena L1 committee, not Euler's own
Plasma DAO/labs/securityCouncil Safes, not any other ecosystem's hardcoded
committee.

## NEW TARGET 2: Yuzu Money (yzUSD / syzUSD / yzPP)

Full sourcing and authority-chain trace in `scorers.py`'s
`score_yuzu_money_plasma()` docstring. Summary: yzUSD
(`0x6695c0f8706c5ace3bdf8995073179cca47926dc`, source-verified on
Plasmascan) is owned by a real, live OpenZeppelin TimelockController
(`0x2130457539612ae9838e0314cda1a8abbdb7cfbc`, `getMinDelay()` =
172,800s / 2 days, confirmed identical on 2 independent RPCs). syzUSD and
yzPP share the exact same owner -- one authority, not three. DefiLlama:
$61.5M Plasma vs. $7.6M Monad vs. $6.6M Ethereum -- ~80% Plasma-specific,
not a multi-chain-diluted number.

**Duplicate-authority check: NEGATIVE (genuinely new).** The Timelock
address does not appear anywhere else in this repository.

**Disclosed gap, not fabricated:** this Timelock is confirmed NOT
self-administered (unlike Fluid's own Timelock, which this file's
`score_fluid_liquidity_plasma()` confirmed IS self-administered) --
meaning an external admin controls its roles, and that admin was not
identified this pass (Plasmascan's tx-history API needs a key this
session doesn't have and wasn't requested; `eth_getLogs` for the full
RoleGranted history hit the public RPC's block-range limit). Scored as an
explicit "unresolved contract" (20/100 adminKeyScore) per
`METHODOLOGY.md`'s own stated convention for this exact situation, not
assumed either safe or compromised.

## Excluded candidates, with reasoning

**Fluid DEX ($52.2M Plasma TVL)** -- Instadapp's own
`deployments/deployments.md` shows Fluid DEX's own Plasma contracts
(factories, resolvers, oracles) constructor-referencing the SAME Liquidity
address (`0x52Aa899454998Be5b000Ad077a46Bbe360F4e497`) this file's
`score_fluid_liquidity_plasma()` already tracks as the shared admin/
governance root for every Fluid product on Plasma (Lending AND DEX both
sit on top of the same Liquidity Layer / AdminModule). Scoring "Fluid DEX"
separately would be re-scoring the identical authority chain under a
different label, not a new finding -- excluded per this pass's explicit
instruction to screen out duplicates honestly.

**Veda / "Plasma Saving Vaults" ($31.5M / $32.3M)** -- DefiLlama's own
`yields.llama.fi/pools` shows both protocol adapters reading from the
SAME pool (`veda` project, symbol `PLASMAUSD`, $32.3M -- there is no
separate "Plasma Saving Vaults" pool entry at pool granularity; it is the
identical vault counted under two protocol labels, the branded Plasma
frontend and the underlying Veda infra provider). Separately, that
specific vault's own root contract ("Plasma: USD Vault", per Etherscan's
public name tag) reads as a BoringVault deployed on ETHEREUM MAINNET, not
Plasma -- its Plasma-side presence is a cross-chain share/teller, not a
Plasma-native authority contract, and Veda's own infra is shared across
13 other chains (`chains: [...]`), raising a real risk that whatever
Plasma-side admin key exists is the same cross-chain-shared key Veda uses
elsewhere -- not independently confirmed either way this pass, and rather
than guess, excluded as not clearly meeting "a real Plasma-specific
authority" and to avoid the double-counting risk above.

**Re7 Labs / K3 Capital / Hyperithm / Edge-UltraYield / Clearstar / TID
Capital EulerEarn vaults** -- all found via the same `eulerEarnFactory`
19-vault enumeration used for Telos Consilium. Every one of these
curators' own vault(s) individually read well under $10M in live
`totalAssets()` on Plasma specifically (Re7 USDT0 Core ~$3.75M, Hyperithm
Euler USDT ~$9.02M, K3 Capital USDT0 Vault ~$20.3K, Edge UltraYield USDT0
~$7.8K, Clearstar's two vaults ~$9.0K combined, TID Capital's two vaults
under $103) -- an order of magnitude below Telos Consilium's ~$100M and
below this project's existing tracked-target TVL floor. Not tracked this
pass; a legitimate future candidate if any of these grows materially.

**CEX entries (Binance CEX $422.0M, Gate $67.3M, Bybit $59.0M, Backpack,
Bitvavo, WEEX, Gate US)** -- DefiLlama's "TVL" for these is custodial
balances held on Plasma addresses the exchange controls, not a DeFi
protocol with an on-chain authority surface (owner/multisig/timelock) to
trace -- structurally outside what this project's methodology scores.

**Plasma One ($12.5M)** -- Plasma's own card/banking product
(`plasma.to/one`). Below this pass's significance bar relative to the two
targets above, and its authority surface (a card-issuance/custody stack)
does not map cleanly onto this project's owner/multisig/timelock
methodology the way a DeFi lending/vault protocol does -- not pursued
this pass, disclosed rather than silently skipped.

## What this pass did NOT do

- Did not run `scripts/lib/cross_ecosystem_overlap.py`'s live tool (it is
  explicitly "not wired in yet" per its own docstring, and Plasma has no
  `GROUPS`-style registry entry in it) -- substituted a manual, repo-wide
  case-insensitive grep of both new targets' resolved authority addresses
  instead, which is narrower in mechanism but was actually performed
  (not skipped) and returned a clean, disclosed negative result for both.
- Did not obtain a Plasmascan API key to resolve Yuzu Money's Timelock
  proposer/executor -- disclosed as an open gap in that scorer's own
  docstring and notes, not fabricated.
- Did not enumerate all 19 EulerEarn vaults' own downstream risk (which
  underlying EVK markets each one allocates into) -- out of scope for an
  authority-tracing pass; this file already discloses the analogous gap
  for `score_euler_v2_evault_factory_plasma()`'s own 156 EVK vaults.
