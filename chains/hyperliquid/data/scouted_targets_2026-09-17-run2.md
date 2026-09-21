# Hyperliquid: scouted targets, 2026-09-17 (run 2)

**Resolved 2026-09-18**: this file's own "Rules needed before scoring_build"
section (5 items) is now closed and all 10 targets below are scored -- see
[`../METHODOLOGY.md`](../METHODOLOGY.md) section 4 for the 5 new rules and
[`scored_targets_2026-09-18-scoring-build.md`](scored_targets_2026-09-18-scoring-build.md)
for the numbers. This file is left otherwise unchanged as the historical
scouting record.

Phase: scouting. Mainnet read-only: official HyperCore info API
(`https://api.hyperliquid.xyz/info`), official HyperEVM RPC
(`https://rpc.hyperliquid.xyz/evm`, chain 999), public Arbitrum One RPC
(`https://arb1.arbitrum.io/rpc`) for the legacy bridge, and HyperLend's own
public archive RPC (listed in its docs) for one historical role-log scan.
No transaction, no key.

All live reads for this file: `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py <subcommand>`
(subcommands: `para`, `mkts`, `kinetiq`, `unit`, `hlp`, `bridge2`,
`hyperlend`, `hyperlend-acl-logs`). Values below were read on 2026-09-17
evening and drift (open interest, balances, TVL).

Already scored before this run and NOT counted here: Hyperliquid L1,
HIP-3 dex `xyz`, HIP-3 dex `io` (`chains/hyperliquid/scorers.py`).

## What changed versus this morning's refused draft

The morning draft (not approved, 2/3 twice) proposed `io`, `para`, `mkts`,
kHYPE, kmHYPE. `io` has since been added to the scorer by the interactive
session, so it is dropped here. The other four are kept, and every open or
wrong qualification of the draft is corrected below:

| Draft claim | What the full code and live state show | Effect |
|---|---|---|
| kHYPE oracle: "bounded only by a 1-hour-per-validator rate limit and an unaudited sanityChecker" | The `ValidatorSanityChecker` (`0x8b64...97d`, verified source read in full) caps each report at +3 bps rewards and +1 bp slashing of the validator's balance, and rejects a reported balance more than 3% away from the L1 delegation read through the HyperCore precompile. `OracleManager.MIN_UPDATE_INTERVAL` is 86,400 s (24 h), not 1 h (1 h is the `DefaultOracle` interval) | kHYPE oracle push is **bounded** (about 3 bps of staked HYPE per day at most). The draft overstated it |
| kmHYPE oracle: "one fewer layer" than kHYPE | kmHYPE's `OracleManager` has no sanity checker, and neither `DefaultOracle.updateValidatorMetrics` nor `ValidatorManager.reportRewardEvent` caps the reward or slash amount. The exchange rate is `(totalStaked + totalRewards - totalClaimed - totalSlashing) / supply` | kmHYPE oracle push is **unbounded in size**, once per validator per 24 h, by one EOA. The draft understated the gap |
| `para` deployer and oracle updater: "single-key on both sides" | The `para` deployer `0x8888888c...6ed3` is a UUPS proxy contract on HyperEVM (Paragon `StakingVault`), not a key. Its HyperCore signing rights come from `addApiWallet` (CoreWriter action 9), gated by `OPERATOR_ROLE`, held by a **1-of-3** Safe | Effective root key is 1-of-3, weaker than the "single key" the current scorer function would report |
| `mkts` CoreWriter link: "not investigated, immaterial" | Resolved: `HIP3StakingManager.setApiWallet` is callable only by `EXManager`, which requires an EIP-712 signature from `GlobalConfig.exWalletAdmin()`, a plain EOA | Effective root of the deployer identity is a single EOA, consistent with the score the scorer already derives |
| HyperLend: "authority chain unresolved" | Resolved: upgrades and pool admin sit behind a 7-day OpenZeppelin `TimelockController` (proposer 4-of-8, executor 5-of-9); risk/listing admin behind a 6-hour timelock; full `ACLManager` role history enumerated from logs | HyperLend retained |

## Funnel

| Step | Count | Detail |
|---|---|---|
| HIP-3 dexes live in `perpDexs` | 10 | `xyz` and `io` already scored |
| Morning draft targets re-verified and kept | 4 | `para`, `mkts`, kHYPE, kmHYPE |
| New HyperCore targets (not in the draft) | 5 | HLP vault, Unit UBTC / UETH / USOL treasuries, legacy USDC bridge (validator-set governed) |
| New HyperEVM targets | 1 | HyperLend Pooled (unresolved in the draft, resolved here) |
| Checked, not retained this run | 2 | stHYPE (role map not enumerated), Felix CDP (not re-opened) |
| **New targets retained (`cibles_traitees`)** | **10** | |

Selection rule: DefiLlama TVL or HyperCore open interest above about $5M,
plus an authority address taken from a primary source (protocol docs or the
official API), plus the full authority chain read on chain.

## Retained targets

Scores: only HyperCore targets whose authority shape already has a rule in
`METHODOLOGY.md` 4.6 get a provisional number. Everything else is marked
"scoring_build" and needs a rule first (listed at the end). No score in this
file is pushed anywhere.

| # | Protocol | Address / id | Source of the address | Usage + source | Authority pattern (root) | Provisional score (4.6) |
|---|---|---|---|---|---|---|
| 1 | HIP-3 dex `para` (Paragon) | deployer `0x8888888c43cbb7e1c4132542e46831bffd866ed3` | `perpDexs` (official API); Paragon docs `docs.paragon.trade` list the same deployer and oracle updater | OI $15.0M, net deposit $10.4M (`metaAndAssetCtxs`, `perpDexStatus`) | Deployer is an HyperEVM UUPS `StakingVault`. HyperCore signer = API wallet added by `OPERATOR_ROLE` = Safe `0x5a24...BA04` **1-of-3**. Upgrade and role grants = `RoleRegistry.owner()` = Safe `0x8D23...CA91` 1-of-1. `setOracle` sub-deployer `0x764e...4335` plain key | root 1-of-3: admin 5, multisig 10, timelock 0, composite **5**, oracle 10 |
| 2 | HIP-3 dex `mkts` (Markets by Kinetiq) | deployer `0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec` | `perpDexs`; Kinetiq docs `kinetiq.xyz/docs/contracts-and-audits` list the address, HyperEVMScan labels it "Kinetiq: kmHYPE Ex Staking Manager" | OI $6.4M, net deposit $5.2M | Deployer is Kinetiq `HIP3StakingManager` (proxy). API wallet set only through `EXManager` with a signature of `exWalletAdmin` `0x64D6...cd27` (EOA). Sub-deployers `haltTrading` / `setOracle` are plain keys. Upgrade of both contracts: 4-of-8 Safe `0x18A8...f8F1` | root single key: admin 10, multisig 15, timelock 0, composite **9**, oracle 15, crossExposure 80 (`km`) |
| 3 | Kinetiq kHYPE | StakingManager `0x393D0B87Ed38fc779FD9611144aE649BA6082109` | Kinetiq docs | TVL $1.054B (`api.llama.fi/tvl/kinetiq-khype`) | Upgrade + all admin roles: 4-of-8 Safe `0x18A8...f8F1`, no module, no guard, no delay. Oracle operator: EOA `0x23A4...4038`, bounded by sanity checker (see below) | scoring_build |
| 4 | Kinetiq kmHYPE | StakingManager `0x71F0019cC7fa79E4f42587FB7b9a817D8d2429EC` | Kinetiq docs | TVL $48.3M (`api.llama.fi/tvl/kinetiq-kmhype`) | Same 4-of-8 Safe for upgrade/admin. Oracle operator EOA `0x4459...82Fa`, **no sanity checker**, unbounded reward/slash size per 24 h | scoring_build |
| 5 | Hyperliquidity Provider (HLP) vault | vault `0xdfc24b077bc1425ad1dea75bcb6f8158e10df303` | Hyperliquid docs (`llms-full.txt`, `vaultDetails` example) and `vaultDetails` API | Account value $187.6M (`vaultDetails` portfolio); DefiLlama `hyperliquid-hlp` $187.5M | Leader `0x677d...84e7` is a plain HyperCore key (`userToMultiSigSigners` null, no EVM code) with 6 named API wallets; it leads all 7 child strategy vaults | scoring_build (vault-leader type has no 4.1 rule) |
| 6 | Unit UBTC (HIP-1 spot) | token `0x8f254b963e8468305d409b33aa137c67`, treasury `0x574bAFCe69d9411f662a433896e74e4F153096FA` | Unit docs `docs.hyperunit.xyz` "Key Addresses > Mainnet" and "Token Metadata" | 6,656 UBTC outside treasury, about $512M; DefiLlama `unit` $825M all assets | Treasury holds 20,993,344 of 21,000,000 UBTC max supply. On HyperCore it is a single key (null multisig). Unit docs: 2-of-3 MPC threshold signature among Unit, Hyperliquid, Infinite Field (off-chain, not verifiable on chain) | scoring_build (spot-treasury type has no rule) |
| 7 | Unit UETH | token `0xe1edd30daaf5caac3fe63569e24748da`, treasury `0x8DAfBe89302656a7Df43c470e9EbCB4c540835c0` | Unit docs | 89,516 UETH outside treasury, about $221M | Same pattern: treasury single HyperCore key holding 99.91% of max supply | scoring_build |
| 8 | Unit USOL | token `0x49b67c39f5566535de22b29b0e51e685`, treasury `0xA822a9cEB6D6CB5b565bD10098AbCFA9Cf18D748` | Unit docs | 336,613 USOL outside treasury, about $34M | Same pattern (99.93% of max supply in treasury) | scoring_build |
| 9 | Hyperliquid legacy USDC bridge (`Bridge2`, Arbitrum One) | `0x2df1c51e09aecf9cacb7bc98cb1742757f163df7` | Hyperliquid docs (`Bridge2.sol` link, bridge address) | 475.9M USDC held (`balanceOf` on Arbitrum USDC) | Non-upgradeable. Withdrawals and admin need `3 * power > 2 * total` of a **4-key, equal-power** hot or cold set (i.e. 3-of-4), 200 s dispute period, at least 5 lockers (threshold 2) can pause | admin 65, multisig 59 (3-of-4), timelock n/d (no 4.3 number for 200 s) |
| 10 | HyperLend Pooled (Aave v3 fork) | PoolAddressesProvider `0x72c98246a98bFe64022a3190e7710E157497170C` | HyperLend docs `docs.hyperlend.finance/developer-documentation/contract-addresses` | TVL $474.3M (`api.llama.fi/tvl/hyperlend-pooled`) | Upgrades, pool admin, ACL admin: Timelock A (7 days, proposer Gov 4-of-8, executor/canceller Treasury 5-of-9). Risk and listing admin: Executor owned by Timelock B (6 h). Emergency admin: two Safes, 3-of-8 and 4-of-6, no delay | scoring_build |

## Per-target detail: verification commands and context

### 1. `para` (Paragon)

Commands:
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py para`
- Source read: `https://hyperevmscan.io/address/0x8888888c43cbb7e1c4132542e46831bffd866ed3#code` (`StakingVault.sol`, `Base.sol`, `RoleRegistry.sol`)

Authority chain, read in full:

| Layer | Fact | Read |
|---|---|---|
| HyperCore | `userToMultiSigSigners(deployer)` = null, so the scorer's `kn()` reads it as a single key | `para` subcommand |
| HyperEVM | same address has code (EIP-1967 proxy, implementation `0x00000006711d...9fBe`) | `deployerEvmCodeBytes`, `deployerIsUupsProxyImpl` |
| Signing path | `StakingVault.addApiWallet(address,string)` is `onlyOperator` and calls CoreWriter action 9 (add API wallet) | verified source |
| `OPERATOR_ROLE` | exactly one holder, Safe `0x5a24D40ef0B6856AeFEEFe65C332ce7Cc7D9bA04`, threshold 1, owners `0x4661...cEbA` (EOA), `0xF5dF...7d31` (EOA), Safe `0x8D23...CA91`; no module, no guard | `RoleRegistry.roleHolders` (solady `EnumerableRoles`, exact list) |
| Owner | `RoleRegistry.owner()` = Safe `0x8D23...CA91`, 1-of-1 (EOA `0xbc6E...8Ad5`); it can upgrade `StakingVault`, grant roles and pause | same |
| Live signer | one named API wallet `main` `0x4f6d...9f61` (valid until 2026-10) | `extraAgents` |

Aggravating: any one of 3 keys can add an API wallet that signs deployer
actions (`haltTrading`, `setOracle`, `setSubDeployers`) with no delay; the
deployer also acts as its own oracle updater. Mitigating: 500,801 HYPE
delegated by the deployer (above the 500k HIP-3 slashable stake), and HIP-3
`setOracle` clamps (1% per update, 2.5 s spacing). Inference, stated as such:
the docs do not say in words that an API wallet may sign `perpDeploy`
actions, but the dex exists and is operated with a contract as deployer,
which has no key, so API-wallet signing is the only path the live state
allows.

### 2. `mkts` (Markets by Kinetiq)

Commands:
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py mkts`
- Sources read: `HIP3StakingManager.sol` + `HIP3L1Write.sol` (implementation `0x2626...70b8`), `EXManager.sol` + `EIP712Verifier.sol` (implementation `0xA4ea...a7bc`), `GlobalConfig.sol` (implementation `0x5945...baf0`), all on hyperevmscan.io

| Layer | Fact |
|---|---|
| `setApiWallet(wallet)` | `require(msg.sender == exManager())`, then CoreWriter action 9 |
| `EXManager.updateWallet` | callable only by `globalConfig.exWalletAdmin()`, and `_updateWallet` checks an ECDSA (EOA only, no ERC-1271) EIP-712 signature from the same address; `walletNonce` is 7, so the API wallet has been rotated 7 times |
| `exWalletAdmin` | `0x64D668b358E4915Fda4Aa8d3bffe36A6d3D8cd27`, no EVM code |
| Who can replace `exWalletAdmin` | `GlobalConfig.setWalletAdmin`, `CONFIG_ADMIN_ROLE` = 4-of-8 Safe `0x18A8...f8F1` (enumerated, 1 member) |
| Upgrades | ProxyAdmin owner of both `HIP3StakingManager` and `EXManager` = the same 4-of-8 Safe |
| Sub-deployers | `haltTrading` `0xecc1...9e41`, `setOracle` `0x6475...c46e` and `0xe992...86c4`, `registerAsset` `0x2cb0...8e19` and `0xc451...957c`: all null multisig, no EVM code |

Conclusion: the morning draft's open question is closed. The HyperCore
deployer identity resolves to one EOA (`exWalletAdmin`) plus whatever API
wallet it last approved; the sub-deployers are separate plain keys. Weakest
key is a single key either way, so the scorer's generic reading (composite 9)
happens to be right for `mkts`, for a reason it does not model.
Cross-exposure: the same 4-of-8 Safe is root of kHYPE, kmHYPE and `mkts`.

### 3 and 4. Kinetiq kHYPE and kmHYPE

Commands:
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py kinetiq`
- Sources read: `OracleManager.sol` (kHYPE impl `0xe6cc...0767`, kmHYPE impl `0xedaa...405b`), `ValidatorSanityChecker.sol` (`0x8b64...97d`), `DefaultOracle.sol` (`0x9c2F...FCA2`), `ValidatorManager.sol`, `StakingAccountant.sol`

| Fact | kHYPE | kmHYPE |
|---|---|---|
| DEFAULT_ADMIN_ROLE (StakingManager, OracleManager), ProxyAdmin owner | 4-of-8 Safe `0x18A8...f8F1` | same Safe |
| `OracleManager` OPERATOR_ROLE (enumerated) | EOA `0x23A4...4038` | EOA `0x4459...82Fa` |
| same EOA holds OPERATOR_ROLE on `DefaultOracle` | yes | yes |
| `ValidatorManager` ORACLE_MANAGER_ROLE (enumerated) | only the `OracleManager` | only the `OracleManager` |
| `OracleManager.MIN_UPDATE_INTERVAL` | 86,400 s | 86,400 s |
| `MIN_VALID_ORACLES` | 1 | 1 |
| `sanityChecker` | `0x8b64...97d` | none (`address(0)`) |
| rewards tolerance / slashing tolerance per report | 3 bps / 1 bp of balance | no cap |
| balance anchor | reported balance within 300 bps of the L1 delegation read by precompile | none |
| sanity checker owner (can loosen up to 1000 bps) | 4-of-8 Safe | n/a |
| `setSanityChecker` (can remove it) | DEFAULT_ADMIN_ROLE = 4-of-8 Safe, no delay | n/a |
| exchange rate formula | `(totalStaked + totalRewards - totalClaimed - totalSlashing) / supply` (`StakingAccountant._getExchangeRatio`) | same |

Qualification. kHYPE: a compromised operator EOA can over-report rewards by at
most about 3 bps of each validator's delegated HYPE per 24 h (about 0.03% of
TVL per day), and cannot fake a balance by more than 3%. Loosening or
removing this needs the 4-of-8 Safe. kmHYPE: the same EOA can report any
reward or slash amount once per validator per 24 h, moving the kmHYPE
exchange rate by an arbitrary amount in one transaction. Mitigating for both:
pausable (`PauserRegistry`, admin = same Safe); kmHYPE TVL is 20x smaller.
The morning draft's single number (oracle 15 for both) does not separate
these two cases, so no oracle number is given here; this is the rule gap
"bounded operator push" listed below.

Docs accuracy notes carried over from the draft and re-checked: none of the
role reads above depend on the two Kinetiq docs-table inconsistencies the
draft reported (kHYPE `OracleAdapter` and `PauserRegistry` rows).

### 5. HLP vault

Commands: `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py hlp`

- Leader `0x677d831aef5328190852e24f13c46cac05f984e7`: null multisig, no EVM
  code, 6 named API wallets (`a`, `a2`, `a3`, `b`, `b2`, `b3`).
- It is the leader of HLP, and HLP is itself the leader of the 7 child vaults
  (Strategy A, B, X, Liquidator 1 to 4).
- Aggravating: one key (or any of its 6 API wallets) trades $187.6M of
  depositor capital and runs backstop liquidations; depositors are locked
  4 days after a deposit (docs: "HLP has a lock-up period of 4 days"), so they
  cannot exit ahead of a bad strategy.
- Mitigating: a vault leader cannot withdraw depositor funds to itself;
  `leaderCommission` is 0. Scope limit: the leader's power is trading and
  allocation, not custody. This is why no 4.6 number is given: the admin-key
  ladder was written for keys that can redirect funds.

### 6 to 8. Unit UBTC, UETH, USOL

Commands:
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py unit`
- Second, independent source for backing: `curl -s https://mempool.space/api/address/bc1pdwu79dady576y3fupmm82m3g7p2p9f6hgyeqy0tdg7ztxg7xrayqlkl8j9` (Unit's documented BTC treasury)

| Fact | UBTC | UETH | USOL |
|---|---|---|---|
| Genesis: 100% of max supply to deployer `0xF036...6155` | yes | yes | yes |
| Deployer | native 2-of-3 multisig, 2 named API wallets | same | same |
| Treasury share of max supply today | 99.968% | 99.910% | 99.933% |
| Outstanding outside treasury | 6,656 | 89,516 | 336,613 |
| Treasury on HyperCore | single key (null multisig), no named API wallet | same | same |

Qualification: the unissued supply sits in one HyperCore address per asset.
Whoever can sign for that address can send unbacked tokens that are
indistinguishable from backed ones on HyperCore, and those tokens are
collateral elsewhere (HyperLend lists UBTC, UETH, USOL). HIP-1 has no mint
after genesis, so this treasury balance is the effective mint authority.
Mitigating: Unit's docs state the treasury key is a 2-of-3 MPC threshold
signature held by Unit, Hyperliquid and Infinite Field; backing is publicly
checkable: the BTC treasury address held about 6,628 BTC against about
6,656 UBTC outstanding at read time (about 99.6%; the gap is not explained
here and may be deposits in per-user addresses not yet swept). The MPC claim
cannot be verified on chain, so the on-chain view (single key) and the
documented view (2-of-3) are both recorded; choosing between them is a
methodology decision, not a scouting one.

### 9. Legacy USDC bridge (`Bridge2`, Arbitrum One)

Commands:
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py bridge2`
- `cast call 0x2df1c51e09aecf9cacb7bc98cb1742757f163df7 "hotValidatorSetHash()(bytes32)" --rpc-url https://arb1.arbitrum.io/rpc`

| Fact | Value |
|---|---|
| Current epoch | 7 |
| How the epoch-7 set was installed | `emergencyUnlock` tx `0x62a66b84...46b4` (signed by the cold set), decoded: 4 hot addresses, 4 cold addresses, powers `[1,1,1,1]` |
| Hash check | `keccak256(abi.encode(validators, powers, epoch))` of the decoded sets equals the on-chain `hotValidatorSetHash` and `coldValidatorSetHash` |
| Quorum | `3 * power > 2 * totalPower` with total 4, so 3 of 4 keys |
| Lockers / finalizers | the 4 hot addresses plus `0xf9d2...48c5` (added by a `ModifiedLocker`/`ModifiedFinalizer` event) are lockers and finalizers; constructor-set lockers emit no event, so the list is a lower bound; `lockerThreshold` 2; no lock vote pending |
| Dispute period | 200 s |
| Upgradeability | none (EIP-1967 slot zero, plain contract) |
| Overlap with L1 validator set | none of the 8 bridge addresses equals any `validator` or `signer` address in `validatorSummaries` (35 registered, 27 active) |

Qualification: `METHODOLOGY.md` 3.6 says admin paths "require validator
signatures with `3 * power > 2 * totalPower`". That is the right formula, but
the set it applies to today is 4 equal-weight keys, not the 27-validator
stake distribution. The docs also say "the L1 validators will sign"
withdrawals. On-chain data cannot show who holds the 4 keys (validators may
use separate bridge keys), so this is recorded as "3-of-4 set of unidentified
operators", not as "not validators". Mitigating: 200 s dispute window in
which any 2 lockers can pause; docs say the bridge is deprecated
and holds under 10% of HyperCore USDC. Aggravating: $475.9M is still held.
This answers open question 2 of `METHODOLOGY.md` section 6.

### 10. HyperLend Pooled

Commands:
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py hyperlend`
- `python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py hyperlend-acl-logs` (full `RoleGranted`/`RoleRevoked` history of `ACLManager` since its deployment block 779,363)
- Sources read: `Executor.sol` (`0x0a0d...5d42`, BGD Labs `Ownable` executor), `Timelock.sol` (`0xaAaa...7879`, plain OpenZeppelin `TimelockController`), `CapAutomator.sol` (`0x01f5...a312`)

| Control point | Holder (live) | Delay |
|---|---|---|
| `PoolAddressesProvider.owner()` (can swap pool/configurator implementations) | Executor `0x0a0d...5d42`, owner Timelock A | 7 days |
| ProxyAdmin owner | Timelock A | 7 days |
| ACL `DEFAULT_ADMIN_ROLE`, `POOL_ADMIN` | Timelock A, Executor `0x0a0d...` (owned by Timelock A) | 7 days |
| ACL `RISK_ADMIN`, `ASSET_LISTING_ADMIN` | Executor `0x1a54...6B22` owned by Timelock B; `CapAutomator` (admin Timelock B) holds `RISK_ADMIN` too | 6 hours |
| ACL `EMERGENCY_ADMIN` | Safe `0xC2A0...7cAc` 3-of-8 and Safe `0xB6c2...8616` 4-of-6 | none |
| Timelock A and B `PROPOSER_ROLE` | Governance Safe `0x2110...E9C` 4-of-8 | |
| Timelock A and B `EXECUTOR_ROLE`, `CANCELLER_ROLE` | Treasury Safe `0xCBF4...3d7b` 5-of-9 | |
| Timelock A and B `DEFAULT_ADMIN_ROLE` | the timelock itself | |

Why the morning draft could not resolve it: it compared owners against the
docs' "Governance Multisig" only. The docs page also lists Timelock A and B
and an Executor, and the live owner is a second Executor not in the docs,
owned by Timelock A.

Aggravating: `EMERGENCY_ADMIN` has no delay and 3-of-8; 5 of the 8 Governance
signers also sign the 3-of-8 Emergency Safe. Mitigating: in Aave v3 the
emergency admin can pause, not move funds; proposer (Governance 4-of-8) and
executor (Treasury 5-of-9) share no signer, so a change needs two
distinct signer groups plus 7 days. Limits: timelock role
holders are checked by `hasRole` against the documented and discovered
addresses, not enumerated from logs (a new grant would itself need the
timelock delay, since each timelock is its own admin); individual price feed
contracts behind the HyperLend oracle `0xC9Fb...630e` were not traced.

## Checked, not retained this run

| Candidate | TVL (DefiLlama) | Why not retained |
|---|---|---|
| stHYPE (Valantis) | $209.9M | Proxy admin, `Ownership` (non-enumerable `AccessControlDefaultAdminRules`) and an unbounded `syncSupply(newSupply, interval)` gated by `REBASER_ROLE` were read, but the role holders were not enumerated and the token proxy was not identified with certainty. Scoring it now would repeat the morning error |
| Felix CDP | $32.8M | Not re-opened; the draft's `CollateralRegistry.owner()` question remains |
| HIP-3 dexes `flx`, `vntl`, `hyna`, `abcd`, `cash`, `km` | n/a | Not re-checked; the draft found near-zero open interest |

## Rules needed before scoring_build (for METHODOLOGY.md)

1. **HyperEVM contract as HyperCore identity.** `userToMultiSigSigners` reads
   null for a contract address, so `kn()` returns "single key". Rule needed:
   when an authority address has EVM code, resolve the role that can call
   CoreWriter action 9 (add API wallet) and score that key. Live impact:
   `para` drops from 9 to 5.
2. **Bounded versus unbounded operator push** (kHYPE vs kmHYPE) for
   `oracleAuthorityScore` of HyperEVM staking tokens.
3. **Vault leader** (HLP): trading authority without custody.
4. **Spot treasury holding unissued supply** (Unit): on-chain single key
   versus documented off-chain MPC.
5. **Short dispute periods** (Bridge2 200 s): a number for 4.3's "low but
   non-zero".

## Cross-exposure found

| Shared root | Targets |
|---|---|
| Kinetiq 4-of-8 Safe `0x18A8...f8F1` | kHYPE, kmHYPE, `mkts` |
| Collateral dependency (listed reserves on HyperLend) | HyperLend inherits Kinetiq kHYPE rate authority and Unit UBTC/UETH/USOL treasury authority |
| Signer overlap | HyperLend Governance 4-of-8 and Emergency 3-of-8 share 5 signers |
