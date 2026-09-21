# Tempo: authority-risk methodology (discovery draft)

Status: **promoted to a real scorer 2026-09-17, extended to 4 controller
types / 6 new targets 2026-09-18, deploy scaffolding added the same day
(`deploy/README.md`, `deploy/push_scores.py`, --dry-run only, see that
folder). A 5th extension, the Morpho Vault V2 target type (rule R8, 3 new
targets), closed the same day -- see section 8's changelog.**
Discovery output, 2026-09-16, amended the same day by the methodology test
(`chains/tempo/data/methodology_test_2026-09-16.md`, changes listed in section 8). This
document establishes the real authority primitives of Tempo from primary sources (official
docs at `tempo.xyz/developers/docs`, the official repository `github.com/tempoxyz/tempo` and
its TIP specifications, and direct JSON-RPC reads) and maps the project's five score
dimensions onto them. Score bands at the end are a starting proposal for the methodology
phase, not final weights. Section 4.1's rules are now live code in
[`scorers.py`](scorers.py) (`score_all()`, reusing `scripts/methodology_test.py`'s
already-tested read-and-score functions) -- see
[`data/scored_targets_2026-09-17.md`](data/scored_targets_2026-09-17.md) for the
live-verified numbers. Chain baseline/USDC.e/USDT0 match this document's methodology test
exactly; `pathUSD` (Tempo's own native, non-bridged stablecoin, ~$39.3M supply -- bigger
than USDT0's) was added the same day, with `score_token()` extended to handle a non-bridged
TIP-20 (`lz_oapp=None`) -- its `ISSUER_ROLE` resolves to an unresolved contract, giving it
the lowest composite score of any Tempo target found so far. Nothing has been deployed or
signed on-chain yet. (That sentence is the 2026-09-17 state. The oracle was deployed on
Moderato on 2026-09-19 and re-pushed on 2026-09-20 with 14 targets; see `deploy/README.md`
and the changelog in section 8.)

Every on-chain fact below was read with `cast` against the official endpoint
`https://rpc.tempo.xyz` and re-read against an independent provider
`https://tempo-rpc.publicnode.com`, unless noted. Mainnet head at time of reading: about
block 39,812,517. Active fork at head: `T11`.

## 1. What Tempo is, technically

| Question | Answer | Source |
|---|---|---|
| EVM chain? | Yes. A Layer 1 "fully compatible with the EVM, targeting the Osaka hard fork". Solidity, Foundry, Hardhat work; standard JSON-RPC works. | [quickstart/evm-compatibility](https://tempo.xyz/developers/docs/quickstart/evm-compatibility) |
| Native gas token? | **None.** Fees are paid in any USD TIP-20 stablecoin. `BALANCE`, `SELFBALANCE`, `CALLVALUE` always return 0. | [quickstart/evm-compatibility](https://tempo.xyz/developers/docs/quickstart/evm-compatibility), [protocol/fees/spec-fee](https://tempo.xyz/developers/docs/protocol/fees/spec-fee) |
| Consensus | Simplex BFT (Commonware), deterministic finality, about 0.5 to 0.6 s blocks, safety under less than 1/3 Byzantine. | [protocol/blockspace/consensus](https://tempo.xyz/developers/docs/protocol/blockspace/consensus) |
| Validator set | **Permissioned** ("institutional validators, also permissioned initially"), with a stated roadmap to permissionless. | same page |
| Smart contracts deployable? | Yes, any EVM bytecode, with higher state-creation gas (TIP-1000). Code cannot be created at the TIP-20 address prefix (TIP-1047). | [evm-compatibility](https://tempo.xyz/developers/docs/quickstart/evm-compatibility), [tip-1000](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1000.md), [tip-1047](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1047.md) |
| Where the core logic lives | In **precompiles** at fixed addresses (bytecode reads back as the single byte `0xef`), not in upgradeable Solidity proxies. | [quickstart/predeployed-contracts](https://tempo.xyz/developers/docs/quickstart/predeployed-contracts), on-chain `cast code` |

Consequence for scoring: Tempo has **two layers of authority** that must be scored
separately.

1. **Protocol layer**: precompiles (TIP-20 factory, FeeManager, Stablecoin DEX, TIP-403
   registry, ValidatorConfig, ZoneFactory). Their code only changes through a hardfork.
   Some of them nevertheless carry an `owner()` for configuration.
2. **Application layer**: ordinary EVM contracts (bridges, Safes, DeFi) with the usual
   EVM admin patterns, plus **TIP-20 tokens**, which are precompile instances whose
   authority is a role system (not code upgrades).

## 2. Networks (confirmed by direct RPC read)

| Network | Chain id | HTTP RPC | Explorer | Use in this project |
|---|---|---|---|---|
| Tempo Mainnet | `4217` | `https://rpc.tempo.xyz` | `https://explore.tempo.xyz` | read-only scoring |
| Tempo Testnet (Moderato) | `42431` | `https://rpc.moderato.tempo.xyz` | `https://explore.testnet.tempo.xyz` | oracle deployment target |
| Tempo Zones (testnet only) | `421700000 + zone_id` | per zone | n/a | out of scope for now |

Sources: [quickstart/connection-details](https://tempo.xyz/developers/docs/quickstart/connection-details)
(mainnet live since 2026-03-18), [protocol/zones/architecture](https://tempo.xyz/developers/docs/protocol/zones/architecture)
(zone chain id formula). Chain ids confirmed with `cast chain-id`. Moderato is funded by
the faucet (`tempo_fundAddress` on the testnet endpoint,
[protocol/rpc](https://tempo.xyz/developers/docs/protocol/rpc/)).

Note: the validator lifecycle guide uses `https://rpc.testnet.tempo.xyz` in its testnet
examples while the connection page lists `https://rpc.moderato.tempo.xyz`. This project
uses the latter (the one listed on the connection page).

## 3. Real authority primitives

### 3.1 Protocol upgrades: hardforks, decided off-chain

- Tempo changes protocol behaviour through named hardforks (`T0` ... `T11`, `T12` in
  preparation, see [tip-1116](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1116.md)).
  Each is activated by **timestamp** in the node's chainspec and shipped as a node release
  that operators must run before activation (e.g. T8 required v1.11.0,
  [protocol/upgrades/t8](https://tempo.xyz/developers/docs/protocol/upgrades/t8)).
- The live schedule is readable on-chain-adjacent via `tempo_forkSchedule`
  ([protocol/rpc](https://tempo.xyz/developers/docs/protocol/rpc/)).
- Decision process: [TIP-0000](https://github.com/tempoxyz/tempo/blob/main/tips/tip-0000.md)
  defines the lifecycle with a "Network Upgrade Call" decision gate and states
  **"External TIP submissions are not accepted at this time."** There is **no on-chain
  governance**; TIP-1010 explicitly says parameter changes happen through
  "Hard fork upgrades" and "Governance proposals (if on-chain governance is implemented)"
  ([tip-1010](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1010.md)).
- Enforcement point: a hardfork only takes effect if the permissioned validators run the
  release. The real veto is therefore the validator set (section 3.2).
- Protocol-managed runtimes (e.g. the ZonePortal implementation) "MUST NOT" be replaceable
  by the factory owner; "Any later runtime replacement MUST be specified by a hardfork"
  ([tip-1091](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1091.md)).

### 3.2 Validator set: `ValidatorConfigV2` precompile, owned by a Safe

- Precompile `0xCCCCCCCC00000000000000000000000000000001` (V1 at `...0000`), spec
  [tip-1017](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1017.md).
- `addValidator`, `transferOwnership`, `setNextFullDkgCeremony`, `migrateValidator` are
  **owner only**. Deactivate, rotate, IP and fee-recipient updates are "owner or
  validator". The validator guide confirms identity resets still require "coordinating
  with the Tempo team" ([guide/node/validator-lifecycle](https://tempo.xyz/developers/docs/guide/node/validator-lifecycle)).
- TIP-1070 adds the nuance: the owner "can change configured validator state, but cannot
  directly change the effective committee except through the normal DKG process"
  ([tip-1070](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1070.md)).

On-chain reads (both RPCs agree):

| Read | Mainnet | Moderato testnet |
|---|---|---|
| `ValidatorConfigV2.owner()` | `0xdC659efF2784cf79fbA88f85d26B1392270CcA33` | `0xe823Bb1aE947a0197929A0eA5FC49394Ca621483` |
| Owner type | Safe proxy, `VERSION()` = `1.4.1`, singleton `0x29fcB43b...C762` (canonical SafeL2 1.4.1 listed for chain 4217 in [safe-deployments](https://github.com/safe-global/safe-deployments/blob/main/src/assets/v1.4.1/safe_l2.json)) | EOA (no code) |
| Threshold / owners | **2 of 5**, all 5 signers are EOAs | n/a |
| Modules / guard | none / none | n/a |
| Safe nonce | 26 | n/a |
| `validatorCount()` | 21 entries | 39 entries |
| Active entries (`deactivatedAtHeight == 0`) | **14** | 19 |

Decoding note: the live `Validator` tuple decodes correctly as
`(bytes32,address,string,string,address,uint64,uint64,uint64)`, i.e. `feeRecipient` comes
before the three `uint64` fields, which differs from the field order printed in TIP-1017.
The scorer must use the live order.

Why it matters: in a BFT chain with permissioned membership, the key that admits validators
is ultimately the key that can assemble a 2/3 quorum over time. On mainnet this key is a
2-of-5 Safe with no timelock module.

### 3.3 Native multisig and quorum

| Level | Primitive | Source |
|---|---|---|
| Consensus quorum | Simplex BFT, 2/3 honest and online for liveness, less than 1/3 Byzantine for safety. 14 active registry entries on mainnet today. | [consensus](https://tempo.xyz/developers/docs/protocol/blockspace/consensus), on-chain read |
| Account multisig | **No native multisig account type.** Safe is supported as an ordinary EVM deployment (Safe deployer predeployed at `0x914d7Fec...43d7`). | [predeployed-contracts](https://tempo.xyz/developers/docs/quickstart/predeployed-contracts) |
| Account key delegation | AccountKeychain access keys (spending limits, expiry, call scopes) and, since T6, **admin access keys** that can add or revoke other keys. The root EOA key is implicitly admin. This is key delegation, not an M-of-N quorum. | [tip-1011](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1011.md), [tip-1049](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1049.md) |
| Zone sequencer set | `ZonePortal.setSequencerSet(newSequencers, newThreshold)`: an M-of-N settlement certificate threshold set by the portal admin (testnet only). | [zones/architecture](https://tempo.xyz/developers/docs/protocol/zones/architecture), [tip-1091](https://github.com/tempoxyz/tempo/blob/main/tips/tip-1091.md) |

Scoring rule inherited from EVM: a Safe is resolved with `getThreshold()`, `getOwners()`,
`getModulesPaginated()` and the guard slot, exactly as on other EVM chains, because the
Safe singleton on Tempo is the canonical one.

### 3.4 Delays

- **No protocol timelock** on any owner-gated precompile function: `transferOwnership`,
  `addValidator`, `setPolicyAdmin` and TIP-20 role changes take effect immediately (TIP-403
  spec: "The new admin immediately gains full control over the policy",
  [tip403/spec](https://tempo.xyz/developers/docs/protocol/tip403/spec)).
- **Hardfork lead time** is the only systemic delay: a public TIP, a node release, then
  testnet activation before mainnet. Measured by comparing `activationTime` in
  `tempo_forkSchedule` on Moderato and on mainnet, the testnet to mainnet lag over the full
  history is 0 to 7 days:

  | Forks | Testnet to mainnet lag |
  |---|---|
  | T1 | 7 days |
  | T1B | 0 days (same timestamp on both networks) |
  | T1C | 3 days |
  | T2, T3, T4, T5, T6, T7 | 5, 6, 4, 6, 5 and 7 days |
  | T8 | 3 days |
  | T9, T10, T11 (most recent) | 1 day each |

  The lag has shortened on recent forks. This is an operational practice, not an enforced
  minimum.
- **Validator exit**: deactivation phases out over two epochs (E+1 exiting, E+2 exited),
  per [validator-lifecycle](https://tempo.xyz/developers/docs/guide/node/validator-lifecycle).
- **TIP-20 quote token change** is two-step (`setNextQuoteToken` then
  `completeQuoteTokenUpdate`) but with no enforced wait between the two calls
  ([tip20/spec](https://tempo.xyz/developers/docs/protocol/tip20/spec)).
- Application contracts may add their own delay (OpenZeppelin `TimelockController`, Safe
  delay modules), detected exactly as on EVM.

### 3.5 Asset-level authority: TIP-20 roles and TIP-403 policies

TIP-20 stablecoins are precompile instances (address prefix `0x20c0...`), so the token
**code cannot be upgraded by the issuer**. Authority is a role system
([tip20/spec](https://tempo.xyz/developers/docs/protocol/tip20/spec),
[guide/issuance/manage-stablecoin](https://tempo.xyz/developers/docs/guide/issuance/manage-stablecoin)):

| Role | Power |
|---|---|
| `DEFAULT_ADMIN_ROLE` | change `transferPolicyId`, supply cap, quote token, grant/revoke roles |
| `ISSUER_ROLE` | mint and burn |
| `PAUSE_ROLE` / `UNPAUSE_ROLE` | freeze and unfreeze all transfers |
| `BURN_BLOCKED_ROLE` | burn balances of addresses blocked by policy |

Each token points at a **TIP-403 policy** in the registry precompile
`0x403c000000000000000000000000000000000000`: id 0 always-reject, id 1 always-allow, id 2+
custom whitelist or blacklist, each with a single `admin` address that can edit the list
and hand over admin rights immediately ([tip403/spec](https://tempo.xyz/developers/docs/protocol/tip403/spec)).
Role membership is readable with `hasRole(address account, bytes32 role)` (note the
argument order, `hasRole(bytes32,address)` reverts with `UnknownFunctionSelector`).

On-chain examples (mainnet, both RPCs):

| Token | `transferPolicyId` | Finding |
|---|---|---|
| pathUSD `0x20c0...0000` | 2 | policy 2 is a BLACKLIST (type 1) whose admin `0x251d2711...5246` is an EOA with an EIP-7702 delegation |
| USDC.e `0x20C0...8b50` | 1 (always-allow) | Stargate OFT `0x8c76e2F6...4392` holds `ISSUER_ROLE`; about 61.6 M USDC.e supply |
| USDT0 `0x20c0...eb73` | 3 | policy 3 is a BLACKLIST whose admin is the USDT0 Safe `0x4DFF9b5b...0bf8` (3-of-5), also the token's only `DEFAULT_ADMIN_ROLE` holder (resolved by the methodology test) |

### 3.6 Oracle authority

- The protocol itself uses **no price oracle**: the Fee AMM swaps at fixed rates (0.9970
  for fee swaps, 0.9985 for rebalancing) and the enshrined DEX is an order book
  ([fees/spec-fee-amm](https://tempo.xyz/developers/docs/protocol/fees/spec-fee-amm),
  [exchange/spec](https://tempo.xyz/developers/docs/protocol/exchange/spec)).
  Implicit assumption: every USD TIP-20 is worth about 1 USD.
- Validators choose their preferred fee token (`setValidatorToken` on FeeManager), so the
  validator set indirectly decides which stablecoins are demanded for fees
  ([fees/spec-fee](https://tempo.xyz/developers/docs/protocol/fees/spec-fee)).
- Application-level oracles exist as ordinary EVM contracts: Chainlink (Price Feeds, Data
  Streams, CCIP), Chronicle, RedStone are listed by Tempo
  ([ecosystem/data-analytics](https://tempo.xyz/developers/docs/ecosystem/data-analytics)).
  Their authority is scored with the existing EVM oracle logic (aggregator owner, feed
  proxy admin), resolved per target.

### 3.7 Cross-exposure

- **Bridged assets are TIP-20 tokens whose mint power sits on an external bridge
  contract.** USDC.e and EURC.e are minted by Stargate OFT contracts; USDT0, frxUSD, cUSD,
  stcUSD, GUSD, rUSD, wsrUSD by issuer-run LayerZero OFT adapters. LayerZero EndpointV2 on
  Tempo is `0x20Bb7C2E...Cc9C`, endpoint id `30410`; the Stargate `TokenMessaging` OApp is
  `0x19Ff94Fe...b9F5` ([guide/bridge-layerzero](https://tempo.xyz/developers/docs/guide/bridge-layerzero)).
  On-chain: USDC.e and EURC.e Stargate contracts share owner `0x09c865FA...3A1f`, a
  **LayerZero OneSig** multisig (`VERSION()` = `0.0.1`, `threshold()` = 5, `getSigners()` =
  7 EOAs, resolved by the methodology test), and the Stargate OFT holds `ISSUER_ROLE` on
  USDC.e.
- Other bridges listed by Tempo: Bungee and Relay
  ([guide/bridge-bungee](https://tempo.xyz/developers/docs/guide/bridge-bungee),
  [guide/bridge-relay](https://tempo.xyz/developers/docs/guide/bridge-relay)).
- **Shared protocol signers**: the ZoneFactory owner on mainnet is a different Safe
  (`0xc46a0C9a...1C0b`) with **the same 5 EOA signers and the same 2-of-5 threshold** as
  the ValidatorConfigV2 owner. A compromise of 2 of those 5 keys therefore reaches both the
  validator registry and zone creation.
- **Zones**: a zone validium locks mainnet TIP-20 in its ZonePortal; zone withdrawals depend
  on mainnet TIP-403 policies and pauses ("TIP-403 policy changes or token pauses on Tempo
  Mainnet will cause affected withdrawals to bounce back",
  [zones/architecture](https://tempo.xyz/developers/docs/protocol/zones/architecture)).
  Testnet only today.

## 4. The five dimensions, translated

| Dimension | EVM meaning in this project | Tempo meaning | Read path |
|---|---|---|---|
| `adminKeyScore` | who can upgrade or reconfigure the target | For EVM app contracts: unchanged (proxy admin, `owner()`, roles). For TIP-20 tokens: holders of `DEFAULT_ADMIN_ROLE`, `ISSUER_ROLE`, `PAUSE_ROLE`, `BURN_BLOCKED_ROLE` (code itself is not issuer-upgradeable). For protocol precompiles: `owner()` of ValidatorConfigV2 and ZoneFactory; precompile code only via hardfork. | `owner()`, `hasRole(address,bytes32)`, `RoleMembershipUpdated` events |
| `multisigScore` | quality of the M-of-N behind the admin | Safe 1.4.1 (canonical) resolved as on EVM; Tempo adds no native account multisig. AccountKeychain admin access keys count as **single-signer delegation**, not a quorum. Zone sequencer threshold is a separate M-of-N (testnet). | `getThreshold`, `getOwners`, modules, guard slot; `AccountKeychain` reads |
| `timelockScore` | enforced delay before admin action | No protocol-enforced delay on any owner or role action. Only app-level timelocks count. Hardfork testnet to mainnet lag (0 to 7 days over the full fork history, 1 day on the three most recent forks T9 to T11) is recorded as context for the chain baseline, not credited as a timelock. | `TimelockController.getMinDelay()`, Safe delay modules, `tempo_forkSchedule` |
| `oracleAuthorityScore` | who can move the price the target trusts | Protocol: no oracle, fixed-rate Fee AMM, so N/A at chain level (replaced by the 1 USD peg assumption and the validator fee-token choice). Apps: Chainlink / Chronicle / RedStone feed owners, resolved per target. TIP-403 policy admin is **not** an oracle but is a censorship authority and is scored under `adminKeyScore`. | feed `owner()`, aggregator proxy admin |
| `crossExposureScore` | dependence on authorities outside the target (numeric value: rule R6 of section 4.1, contract semantics plus the cross-ecosystem fold added 2026-09-20; the other items in this row go to `notes`) | Bridge issuer contracts holding `ISSUER_ROLE` on bridged TIP-20s (Stargate, issuer OFTs, LayerZero DVN config); the chain baseline (permissioned validators admitted by a 2-of-5 Safe); signer overlap between protocol Safes; for zone targets, mainnet TIP-403 and pause dependence. | `hasRole`, OApp `owner()`/delegate, EndpointV2 config, Safe owner set comparison |

### 4.1 Scoring rules and numeric mapping (added 2026-09-16 by the methodology test)

Orientation, fixed by the contract (`src/AuthorityRiskOracle.sol`): **every sub-score is
0 to 100 with higher meaning safer** (bare EOA low, real timelock high, 100 = no shared
signer). All rules below follow that orientation.

| Rule | Statement |
|---|---|
| R1. Root-control set of a TIP-20 | Current holders of `DEFAULT_ADMIN_ROLE`, `ISSUER_ROLE`, `PAUSE_ROLE`, `BURN_BLOCKED_ROLE`, plus the TIP-403 policy `admin` when `transferPolicyId >= 2`. `UNPAUSE_ROLE` is excluded (it can only restore transfers). If a `RoleAdminUpdated` event exists, the holders of the new admin role join the set. A role with no holder adds nothing, because `DEFAULT_ADMIN_ROLE` can grant it at once and is already in the set. |
| R1b. Enumerating holders | TIP-20 has no role enumeration getter. Candidates = every `account` of a `RoleMembershipUpdated` log on the token over the full chain history (`eth_getLogs` in 100,000-block windows, the official endpoint limit; token creation emits the first grant). Each candidate is then confirmed with `hasRole(address,bytes32)` on two endpoints. |
| R1c. Root-control set of the chain baseline | `owner()` of `ValidatorConfigV2` (`0xCCCC...0001`). |
| R2. Resolving a holder to a key `(k, n)` | EOA or EIP-7702 delegated EOA: `(1, 1)`. Safe: `(getThreshold, len(getOwners))`, with modules and guard recorded; an enabled module is a bypass and is scored as an unresolved contract until resolved. LayerZero OneSig: `(threshold(), len(getSigners()))`. Other contract: follow `owner()` and the EIP-1967 admin slot (then `owner()` of the ProxyAdmin), at most 2 hops, and keep the weakest controller. A contract that resolves to none of these is "unresolved". A bridge contract holding `ISSUER_ROLE` is therefore scored through its owner and its proxy admin; its message verification (DVN set) goes to `notes`. |
| R3. Weakest key | Same ordering as `chains/hyperliquid` rule 4.2: lower `k` is weaker, on equal `k` larger `n` is weaker; an unresolved contract is weakest of all. `adminKeyScore` and `multisigScore` are computed on the weakest key of the root-control set. |
| R4. adminKeyScore | 100 if the root-control set is empty; 65 if `k >= 3`; 50 if `k = 2`; 10 for a single key; 5 for 1-of-N with N > 1; 20 for an unresolved contract (repo convention). |
| R5. multisigScore | `k = 1`: 15 if `n = 1`, else `max(0, 14 - 2(n - 1))`. `k >= 2`: `max(16, min(100, 20k - (n - k)))`. Examples: 2-of-5 = 37, 3-of-5 = 58, 5-of-7 = 98. 100 if the set is empty, 0 if unresolved. The floor of 16 keeps any `k >= 2` above a single key for large `n`, which the Hyperliquid formula only guarantees for `n <= 10`. |
| R5b. timelockScore | Shortest enforced delay over every path in the root-control set: none = 0, under 24 h = 20, 24 to 48 h = 35, 48 h to 7 days = 60, 7 days or more = 80. TIP-20 role changes, TIP-403 admin changes, `ValidatorConfigV2` owner actions, Safe and OneSig executions all have no delay, so 0 unless a TimelockController or delay module sits on every path. Hardfork lag is never credited. |
| R5c. oracleAuthorityScore | 100 (repo "not applicable" convention) for a target that reads no price. A TIP-20 stablecoin and the validator registry read none. |
| R6. crossExposureScore | Contract semantics: `max(0, 100 - 20 x number of OTHER tracked Tempo targets sharing at least one root signer)`, root signers = union of the `signers` of every resolved key in R1. Tracked set = the Tempo targets scored in the same run, including the chain baseline. **Cross-ecosystem fold (added 2026-09-20; project convention in the root `METHODOLOGY.md`, paragraph "Convention (decided 2026-09-20)"):** when a target's root signer set is exactly equal to the committee of a tracked target on ANOTHER ecosystem, the value is `min(the formula above, 80)`, so a value already lowered by a within-Tempo overlap is never raised. The scorer never calls another chain's RPC: it compares the signer set it just read on Tempo against a hardcoded, dated snapshot of the other chain's committee. Today there is one snapshot, `_KNOWN_MORPHO_BLUE_OWNERS_2026_09_20` in `scripts/methodology_test.py`: the 9 owners of Morpho Association's governance Safe, which is also the owner Safe of the tracked Morpho Blue cores on Ethereum L1, Base and Robinhood Chain (the Safe address differs on Tempo, so the snapshot holds owners, not an address). A mismatch, or an empty or unresolved signer set, leaves the within-Tempo value untouched. |
| R6b. Notes carried with every score | `chainCappedComposite = min(compositeScore, chain baseline compositeScore)`; LayerZero inbound config of the issuer OApp (endpoint delegate, required and optional DVNs, confirmations) from `EndpointV2.getConfig(oapp, receiveLibrary, srcEid, 2)`; the same signer set controlling the same asset on other chains (read on those chains' RPCs). These stay out of the numeric score, with one exception (changed 2026-09-20): a root signer set equal to a snapshotted committee of a tracked target on another ecosystem is folded by R6 (`crossExposureScore` = `min(within-Tempo value, 80)`) and its finding is also written to `notes.crossChainSignerOverlap`. Signer reuse on another chain that has no snapshot in the scorer (for example the USDT0 Safe and the Stargate OneSig on the same asset elsewhere) stays a note only, and bridge, DVN and chain-cap items are unchanged notes. |
| R7. compositeScore | `floor(0.4 adminKey + 0.3 multisig + 0.3 timelock + 0.5)`, repo `_composite`. |
| R8. Morpho Vault V2 target type (added 2026-09-18) | A vault's root-control set is `{owner, curator}` only, each resolved through R2/R3 unchanged (both are plain addresses on `morpho-org/vault-v2` `src/VaultV2.sol`, confirmed against real source -- a Safe or an EOA on every live target found so far). Allocators and sentinels are excluded from the numeric set: both are real but bounded, non-originating powers (allocator moves funds only among adapters the curator already approved, within caps the curator already set; sentinel only revokes/decreases/deallocates), the same convention R1 already applies to TIP-20's `UNPAUSE_ROLE` and `_classify_timelock` applies to `EXECUTOR_ROLE`/`CANCELLER_ROLE`. `timelockScore` reads the minimum `timelock(bytes4)` over 5 "fund-destination" curator selectors (`addAdapter`, `removeAdapter`, `setAdapterRegistry`, `increaseAbsoluteCap`, `increaseRelativeCap`) EXCLUDING any selector where `abdicated(bytes4)` is true (permanently renounced, confirmed irreversible in `VaultV2.sol` -- a stronger guarantee than any finite delay, mapped to R5b's own 7-day-or-more band rather than a new one); if every tracked selector is abdicated, the delay used is 7 days flat, i.e. the same top band. `adminKeyScore`/`multisigScore`/`compositeScore` reuse R3/R4/R5/R7 unchanged on the weakest of `{owner, curator}`. |
| R9. Morpho Blue core target type (added 2026-09-19) | Root-control set = `{owner()}` of the core contract, resolved through R2/R3 unchanged. Real source (`morpho-org/morpho-blue` `src/Morpho.sol`): `onlyOwner` covers exactly `setOwner`, `enableIrm`, `enableLltv`, `setFee` (capped at `MAX_FEE` = 25% of interest) and `setFeeRecipient`; the contract is not a proxy, has no pause and no role able to move funds; market parameters, including the oracle, are fixed at the permissionless `createMarket`. No timelock on any owner function, so R5b gives the shortest delay over the set (0 for a Safe/EOA owner). `oracleAuthorityScore` = 100 under R5c: the core owner cannot touch any market price source; the per-market oracle authority (feed proxy admins) is a separate target shape, still open. |

Reference implementation: `chains/tempo/scripts/methodology_test.py`.

## 5. "Smart contract deployable" on Tempo

Yes. Tempo accepts standard EVM deployments (Foundry, Hardhat), so the oracle contracts of
this project can be deployed unchanged on Moderato (chain id 42431). Practical differences:
fees in a USD stablecoin (pathUSD from the faucet, used as fallback fee token for non-TIP-20
calls), state creation 250,000 gas per new slot, contract bytes 1,000 gas each, so a
deployment costs 5 to 10 times the Ethereum gas amount
([evm-compatibility](https://tempo.xyz/developers/docs/quickstart/evm-compatibility)).
`msg.value` is always 0, so any payable logic is meaningless.

## 6. Score bands (orientation corrected 2026-09-16, numbers in section 4.1)

The discovery draft labelled 0 to 20 as low risk and 80 to 100 as high risk, the reverse
of the on-chain contract. Corrected orientation, higher is safer:

| Dimension | 0 to 20 (weak) | 35 to 65 (middle) | 80 to 100 (strong) |
|---|---|---|---|
| admin key | EOA holds admin, issuer or pause role, or single-key TIP-403 admin on a blacklist token | admin is a 2-of-N or 3-of-N Safe or OneSig | no admin, renounced roles, or precompile with no owner |
| multisig | 1-of-N, EOA, or admin access key only | 2-of-5 or 3-of-5 | 5-of-7 or better, independent signers |
| timelock | no delay or under 24 h (0 or 20) | 24 h to 7 days (35 or 60) | enforced delay of 7 days or more (80) |
| oracle authority | single-key feed | feed with multisig admin | no oracle dependence, or decentralised feed with no admin override |
| cross exposure | root signers shared with 4 or more other tracked targets | shared with 2 or 3 | shared with none (80 when the committee also controls a tracked target on another ecosystem, rule R6; bridge and chain dependence go to `notes`, rule R6b) |

Chain baseline to carry into every Tempo score: permissioned validators, membership
controlled by a 2-of-5 Safe without timelock, no on-chain governance.

## 7. Open points carried into the methodology phase

1. Resolved 2026-09-16: the Stargate owner `0x09c865FA...3A1f` is a LayerZero OneSig
   5-of-7; the USDT0 policy 3 admin is the USDT0 Safe `0x4DFF9b5b...0bf8` (3-of-5).
2. Resolved for USDC.e and USDT0 (rule R1b; `https://rpc.tempo.xyz` caps `eth_getLogs` at
   100,000 blocks, the full history takes about 400 windows). pathUSD resolved the same day
   it was added as a scored target (2026-09-17). **The "other, not-yet-scouted bridged TIP-20
   tokens" half of this point is CLOSED 2026-09-19, by a negative result, not by adding a weak
   target**: the official Tempo token registry (`tokenlist.tempo.xyz/list/4217`) and the mainnet
   block explorer (`explore.tempo.xyz/tokens`) independently enumerate the same 34 TIP-20 tokens
   on Tempo mainnet today; 9 are already scored (USDC.e, USDT0, pathUSD, USDB, cbBTC, PRIME,
   DLUSD, EURC.e, cUSD). Of the remaining 25, `totalSupply()` (re-read on both RPC endpoints for
   the largest ones) is under $1,120 for 20 of them (several literally 0, single-digit-to-zero
   holders -- issuer test/demo mints against the live registry, not real usage); the 5 with a
   larger figure are either a near-single-wallet self-mint (`BRLA` 5 holders, `GBPA` 1 holder,
   each around $50k) or a receipt/wrapper token of an ALREADY-scored target under a different
   address (`senpathUSDE`, not bridged at all -- a Sentora receipt token against the already-
   scored Sentora pathUSD Vault V2; `stcUSD`, Cap Protocol's own staked wrapper of the already-
   scored cUSD). None clears the bar the weakest already-covered independent token sets (DLUSD:
   $3.66M supply, 639 holders). Full census, sources and per-token numbers in
   `data/scouted_bridged_tokens_2026-09-19.md`. Re-open only per that file's section 5 trigger,
   not on a fixed schedule. `https://tempo-rpc.publicnode.com` refused the bulk log scan for
   R1b (HTTP 403), so log enumeration has a single source; the resulting holders are confirmed
   with `hasRole` on both endpoints (unrelated to the token-census cross-check above, which used
   plain `totalSupply()` reads, not log scans).
3. **CLOSED 2026-09-17, by design, not by finding an address**: TIP-1070's
   `CURRENT_COMMITTEE_ADDRESS`/`getCommitteeMembers()` reverting on `ValidatorConfigV2` is not
   a missing-address problem -- the TIP's own primary source
   (`github.com/tempoxyz/tempo/tips/tip-1070.md`) is marked `status: Draft`,
   `protocolVersion: TBD`, with the deployment address itself literally written as `TBD` in
   the spec. Cross-checked live against the mainnet `tempo_forkSchedule` RPC: the active
   hardfork today is **T11**; T12 (the next one, `tip-1116.md`, also `status: Draft`) has no
   entry in the schedule at all, and TIP-1070 isn't listed as a change under either T11's or
   T12's meta-TIP. Conclusion: the "current effective committee" system contract this
   project's scorer would prefer to read from does not exist on Tempo mainnet yet at all --
   `getActiveValidators()`'s registry count (14) really is the only currently-queryable proxy
   for committee size, not a stopgap for an undiscovered address. Re-check when a future T-fork
   meta-TIP lists TIP-1070 as included.
4. **CLOSED 2026-09-17, confirmed unresolvable by design, not by more searching**: Tempo's own
   docs (`tempo.xyz/developers/docs/guide/node/validator`) state the validator set is
   permissioned and operator identity is not publicly listed -- "get in touch with the Tempo
   team" is the documented process for even becoming one. No primary source publishes operator
   identities; this is an intentional non-disclosure, consistent with section 3.2's own note
   that "identity resets still require coordinating with the Tempo team," not a gap this
   project's own RPC reads can close.
5. Moderato ValidatorConfigV2 owner is an EOA: irrelevant to mainnet scoring, but the oracle
   deployed on testnet must not present testnet authority as mainnet authority.

## Reproducing the reads

```bash
C=~/.foundry/bin/cast
R=https://rpc.tempo.xyz            # second source: https://tempo-rpc.publicnode.com
$C chain-id --rpc-url $R                                    # 4217
$C chain-id --rpc-url https://rpc.moderato.tempo.xyz       # 42431
$C rpc tempo_forkSchedule --rpc-url $R
$C call 0xCCCCCCCC00000000000000000000000000000001 "owner()(address)" --rpc-url $R
$C call 0xdC659efF2784cf79fbA88f85d26B1392270CcA33 "getThreshold()(uint256)" --rpc-url $R
$C call 0xdC659efF2784cf79fbA88f85d26B1392270CcA33 "getOwners()(address[])" --rpc-url $R
$C call 0x5AF2000000000000000000000000000000000000 "owner()(address)" --rpc-url $R
$C call 0xc46a0C9a0B778dfDB33cAB24A9C730152fef1C0b "getOwners()(address[])" --rpc-url $R
$C call 0xCCCCCCCC00000000000000000000000000000001 \
  "getActiveValidators()((bytes32,address,string,string,address,uint64,uint64,uint64)[])" --rpc-url $R
$C call 0x20C000000000000000000000b9537d11c60E8b50 "hasRole(address,bytes32)(bool)" \
  0x8c76e2F6C5ceDA9AA7772e7efF30280226c44392 $($C keccak ISSUER_ROLE) --rpc-url $R
$C call 0x403c000000000000000000000000000000000000 "policyData(uint64)(uint8,address)" 2 --rpc-url $R
```

Note for sandboxed environments: `cast` may fail TLS verification behind an intercepting
proxy; the reads above are plain read-only JSON-RPC calls.

## 8. Changelog

| Date | Change | Why |
|---|---|---|
| 2026-09-16 | Section 6 bands re-oriented to higher = safer | The discovery draft had them reversed relative to `src/AuthorityRiskOracle.sol` and every published score; found by the methodology test |
| 2026-09-16 | Added section 4.1 (rules R1 to R7) | Section 4 named read paths but gave no way to select one key among several role holders, no numbers, and no crossExposure formula; the test could not produce a score without them |
| 2026-09-16 | `crossExposureScore` pinned to the contract formula (R6); bridge, DVN and chain dependence moved to `notes` (R6b) | Section 4 described a qualitative bridge-dependence score that the on-chain field does not encode |
| 2026-09-16 | LayerZero OneSig added as a resolvable multisig (R2) | The USDC.e admin is a OneSig, not a Safe; without it the largest Tempo stablecoin resolved as "unresolved contract" |
| 2026-09-16 | Multisig floor of 16 for `k >= 2` (R5) | The Hyperliquid formula can drop a 2-of-N below a single key for `n > 20`; Safes have no `n <= 10` cap |
| 2026-09-16 | Open points 1 and 2 of section 7 resolved; sections 3.5 and 3.7 updated | Live reads of the test |
| 2026-09-18 | `classify()` (rule R2) now resolves 4 more real controller shapes: a plain OpenZeppelin `TimelockController` (log-scan fallback for role holders, no enumeration getter), Chainlink `RBACTimelock` + hierarchical `MCMS` (a bottom-up quorum-flattening algorithm reduces the group tree to the same `(k, n)` shape every other kind already produces), a UUPS `AccessControlEnumerable` "bridge controller" (`DEFAULT_ADMIN_ROLE` resolved via real on-chain enumeration), and a LayerZero OApp's endpoint delegate folded in as a THIRD parallel controller candidate inside the generic owner()/EIP-1967 branch (previously only recorded in `notes`, invisible to every numeric score). No new rule or formula -- all 4 resolve to the pre-existing `(k, n, signers)` shape R3/R4/R5 already score. Also fixed a real `TypeError` in `classify()`'s own internal weakest-controller selection (crashed on an unresolved sub-controller; the top-level `weakest()` had the correct None-safe form all along, now shared instead of duplicated). | `scouted_targets_2026-09-17-run2.md` section 8's open points 1 and 3, closed by `data/scored_targets_2026-09-18-controller-types.md`. |
| 2026-09-18 | Adversarial review of the above (same day, 17 agents/13 findings/11 confirmed): fixed `_classify_timelock` to also resolve `ADMIN_ROLE`/`DEFAULT_ADMIN_ROLE` as a controlling path (previously omitted entirely, though benign today since both live targets self-administer). Fixing that surfaced a second, self-caught regression before commit (not by the review itself): a self-held admin role recursed `classify()` back into the SAME contract, which re-derived the SAME self-held role, forever, until the depth cutoff returned "unresolved" and wrongly dragged the WHOLE result to that worst-case band -- fixed by filtering out any role holder equal to the resolving contract's own address before recursing. Also corrected this pass's own documentation: PRIME's weakest path is via `ISSUER_ROLE`, not `DEFAULT_ADMIN_ROLE` as first written (the RBACTimelock's `DEFAULT_ADMIN_ROLE` on PRIME was revoked on-chain 2026-07-30, a real governance change this project had not previously surfaced) -- the published composite was unaffected either way. | `chains/tempo/data/scored_targets_2026-09-18-controller-types.md`'s own "adversarial review" sections. |
| 2026-09-18 | Added rule R8: a Morpho Vault V2 target type (`score_vault_v2()`, `VAULT_V2_TARGETS`, `_vault_v2_timelock()` in `scripts/methodology_test.py`). Root-control set `{owner, curator}` resolved via unchanged R2/R3 (both plain addresses on real Vault V2 source); `timelockScore` reads the minimum `timelock(bytes4)` over 5 fund-destination curator selectors (computed from real `morpho-org/vault-v2` signatures, never hardcoded), excluding any selector `abdicated(bytes4)` reports as permanently renounced (mapped to R5b's own top band instead of a new one). Scored the 3 Morpho Vault V2 instances found on Tempo mainnet (Sentora pathUSD, its feeder vault, Tempo Earn). Independently re-derived scores for 2 of the 3 reproduce `scouted_targets_2026-09-17-run2.md` section 4's own "resolved reading (proposal)" column EXACTLY (Sentora pathUSD 10/15/60/27, Tempo Earn 65/56/60/61); the third (the feeder vault, owner=curator=one EOA) has no prior proposal to compare against and scores 10/15/0/9. Live-verified against Tempo mainnet 2026-09-18, see `data/scored_targets_2026-09-18-vault-v2.md`. | `scouted_targets_2026-09-17-run2.md` section 8, open point 4 ("Morpho Vault V2 ... need a written target type"), the one open point NOT already closed by the two 2026-09-18 entries above. |
| 2026-09-19 | Closed section 7 open point 2's "other, not-yet-scouted bridged TIP-20 tokens" clause by a negative result -- no code change. Cross-checked the official Tempo token registry (`tokenlist.tempo.xyz/list/4217`) against the mainnet block explorer (`explore.tempo.xyz/tokens`): both independently enumerate the identical 34 TIP-20 tokens live on Tempo mainnet today, 9 already scored. Read `totalSupply()`/`decimals()` for all 25 remaining on `rpc.tempo.xyz`, re-read the largest ones on `tempo-rpc.publicnode.com`; none clears the bar the weakest already-covered independent token (`DLUSD`, $3.66M/639 holders) sets -- the two closest by dollar value are effectively single-wallet self-mints (`BRLA` 5 holders, `GBPA` 1 holder), and the one with the most holders (`senpathUSDE`, 77) turns out not to be bridged at all, a Sentora receipt token against the already-scored Sentora pathUSD Vault V2. `TOKENS`/`scorers.py` unchanged; nothing pushed to Moderato. | `data/scouted_bridged_tokens_2026-09-19.md`, this pass's own token census. |
| 2026-09-19 | Added rule R9: a Morpho Blue core target type (`score_morpho_blue()`, `MORPHO_BLUE_TARGETS` in `scripts/methodology_test.py`), wired into `scorers.py::score_all()`. Scored Morpho Blue core on Tempo (`0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97`, address from docs.morpho.org and DefiLlama-Adapters `projects/morpho-blue/config.js`, DefiLlama TVL $42.6M on Tempo): owner Safe 1.4.1 5-of-9, no module or guard, 9 EOA signers (the same 9 signers and threshold as Morpho's Ethereum owner), 65/96/0/100 -> composite 55, read live on both RPCs. 14 tracked targets. | T4 of `scouted_targets_2026-09-17-run2.md`, left unwired since 2026-09-18; maintenance run 2026-09-19, see `data/scored_targets_2026-09-19-morpho-blue.md`. |
| 2026-09-20 | **Corrected** rules R6 and R6b, the section 4 `crossExposureScore` row and the section 6 cross exposure band: a cross-ecosystem overlap is now folded into `crossExposureScore` as `min(within-Tempo value, 80)` instead of being note-only. Effect on the one affected target, Morpho Blue core: 65 / 96 / 0 / 100 / 100 / 55 becomes 65 / 96 / 0 / 100 / **80** / 55 (composite and chain-capped composite unchanged; the finding is in `notes.crossChainSignerOverlap`). Every other Tempo target is unchanged. Also fixed `scorers.py::score_all()`, which used to overwrite each target's `notes` with `chainCappedComposite` and now merges instead, so the cross-chain finding survives. The original 2026-09-16 and 2026-09-19 text is kept in this changelog and in the dated data files. Pushed on-chain 2026-09-20 (`updateScores()` tx `0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b`, Moderato block 36054236, 14 targets): the Moderato oracle now holds `crossExposureScore` 80 for Morpho Blue core, read back with plain `getScore()` and equal to the scorer output on all 14 targets; the 2026-09-19 push (tx `0xe34510ed...029cc6`, 100) is superseded. | Project convention decided 2026-09-20 (root `METHODOLOGY.md`, paragraph "Convention (decided 2026-09-20)"): a committee shared across ecosystems scored 80 on Arbitrum, Base, Plasma and Monad but 100 on Ethereum L1, Robinhood Chain and Tempo, because those three kept cross-ecosystem overlaps as notes only. On Tempo the case is the Morpho Blue core owner committee. See `data/scored_targets_2026-09-19-morpho-blue.md` (CORRECTED 2026-09-20 lines). |
