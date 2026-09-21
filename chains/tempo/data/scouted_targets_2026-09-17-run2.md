# Tempo: scouted targets, 2026-09-17 (run 2)

Phase: scouting. Read-only Tempo mainnet (chain id `4217`), official endpoint
`https://rpc.tempo.xyz`, facts re-read on `https://tempo-rpc.publicnode.com`. Ethereum reads
on `https://ethereum-rpc.publicnode.com`. No transaction, no key. Two authority checks use
`eth_call` simulations with a `from` address (`cast call --from`): they execute nothing on
chain, they only show whether the contract would accept the call from that address.

Log-scan head for role enumeration: block 39,969,540. Values below (supply, TVL, balances)
were read around blocks 39,968,900 to 39,970,200 and drift; the verification commands use
bounds, never exact equality on a moving value.

Already scored in `data/scored_targets_2026-09-17.md` and NOT counted here: chain baseline
(ValidatorConfigV2), USDC.e, USDT0, pathUSD.

## 1. What changed versus the refused morning draft

| Refusal reason (rotation state) | What this run did |
|---|---|
| cUSD: 24 h timelock missed | The `DEFAULT_ADMIN_ROLE` holder `0x0000000035A7744F...312a55` is an OpenZeppelin `TimelockController` (dispatcher selectors `schedule`, `execute`, `getMinDelay`, ...), `getMinDelay() = 86400`, listed as "Timelock Controller" in Cap's official `cap-docs/developers/addresses.md`. Its proposer, executor and canceller is the Cap Safe 3-of-5 `0xb8FC4940...8793`. Aggravating context found at the same time: the same 3-of-5 Safe is the LayerZero endpoint **delegate** of the cUSD OFT, which can change the OFT's receive library and DVN config with no delay (EndpointV2 `_assertAuthorized`). |
| Sentora and Morpho Vault V2 timelocks mis-qualified ("timelock 0") | Every curator selector's `timelock(bytes4)` and `abdicated(bytes4)` read live on all three vaults (section 5). Sentora: adding an adapter or raising a cap waits 3 days, the adapter registry is abdicated. Vault `0x83a1`: `addAdapter` and `removeAdapter` are abdicated, and its only adapter feeds the Sentora vault. The owner's instant powers (`setOwner`, `setCurator`, `setIsSentinel`) cannot move funds by themselves (VaultV2 source, unchanged in code since release tag `2025-12-04`). |
| Unstable reproduction script (strict equality on `totalAssets`) | No repo script this run. Every claim is one non-interactive shell command (`cast`, `curl` or `gh api`, piped into `grep`/`python3` assertions) with bounds on moving values (`> 30M`, not `== 36037745944443`). |
| Fabrication (a claim about developers.uniswap.org whose command read tempo.xyz) | Uniswap addresses are now checked against `Uniswap/contracts/deployments/4217.md` in the official repository, with a command that reads that exact file. |
| Held from the morning draft | Stablecoin DEX and Fee AMM precompile qualification (re-checked against the official Rust dispatch: no owner or admin entry point), EURC.e (same OneSig 5-of-7 as USDC.e), Uniswap V4/V2 governance relay (now resolved to the Ethereum Uniswap Timelock). |
| Dropped from the morning list | pathUSD (now scored in the repo). |

## 2. Funnel

| Step | Count | Detail |
|---|---|---|
| DefiLlama protocols with Tempo in `chains` (`api.llama.fi/protocols`) | 14 | Morpho Blue $45.3M, Sentora Curator $36.0M, Tempo Stablecoin Dex $11.6M, Uniswap V4 $3.69M, Gauntlet $288k, Uniswap V2 $72.5k, Tempo Fee AMM $44.2k, Symbiosis $21.1k, Uniswap V3 $242, 5 at $0 to $2 |
| Tokens on the official Tempo token list (`tokenlist.tempo.xyz/list/4217`, the list linked from the LayerZero bridge guide) | 35 | `totalSupply()` read on both endpoints for all 35 |
| Tokens already scored | 4 | USDC.e, USDT0, pathUSD (and the chain baseline) |
| New tokens clearing a real-value bar and fully resolved | 6 | USDB, cbBTC, PRIME, DLUSD, EURC.e, cUSD |
| New DeFi targets fully resolved | 9 | 3 Morpho Vault V2, Morpho Blue core, Morpho market cbBTC/pathUSD (oracle), Stablecoin DEX, Fee AMM, Uniswap V4, Uniswap V2 |
| **Retained (`cibles_traitees`)** | **15** | Section 3 |
| Checked and dropped | see section 7 | dust tokens, unresolved small issuer, curator labels, sub-$25k protocols |

## 3. Retained targets

Value sources: `api.llama.fi/protocols` (protocol TVL), `stablecoins.llama.fi/stablecoins`
(stablecoin circulating on Tempo), `coins.llama.fi` (cbBTC, EURC.e, PRIME price), on-chain
`totalSupply()` / `totalAssets()` / Morpho `market(id)`. Claim ids refer to
`claims_attempt1.txt` of this run (one command per claim).

| # | Protocol / target | Address or id | Address source | Value (source) | Root authority pattern (live) | Verification | Mitigating / aggravating context |
|---|---|---|---|---|---|---|---|
| T1 | Sentora pathUSD (Morpho Vault V2) | `0x9a044AE05E5e6290DcF56afd69548565e957a626` | Morpho API `vaultV2s`, confirmed by official VaultV2Factory `isVaultV2` | $36.04M `totalAssets` (24.60M idle pathUSD + 11.44M in the cbBTC market); DefiLlama "Sentora Curator" $36.03M | owner Safe 1-of-1, curator Safe 1-of-1 (also allocator and sentinel), extra allocator EOA, extra sentinel EOA | claims 1 to 5 | Mitigating: new adapter and cap increases wait 3 days, sentinels can revoke, adapter registry abdicated (only Morpho-registry adapters), exit gates abdicated. Aggravating: 1-of-1 Safes are single keys; allocators can move up to the 30M cap into the cbBTC market instantly; fees settable instantly (bounded 50% perf, 5%/yr mgmt) |
| T2 | Unnamed pathUSD Vault V2 feeding Sentora | `0x83a1491f3e7f8dAAB8F787a631334b9ca7a87023` | Morpho API, factory `isVaultV2` | $13.34M `totalAssets`, all of it held as Sentora shares (not distinct capital) | owner = curator = allocator = sentinel = one plain EOA `0x445F7a27...8Dc9` | claims 6, 7 | Mitigating: `addAdapter`, `removeAdapter` and all 4 gates abdicated, sole adapter = MorphoVaultV1Adapter into T1, so the EOA cannot redirect funds. Aggravating: instant fee setting (bounded), full exposure to T1's authority |
| T3 | Tempo Earn (Morpho Vault V2, Gauntlet-curated) | `0xC609656Ed9ef219c98C8e549bF729144F211f06E` | Morpho API, factory `isVaultV2`, `name()` = "Tempo Earn" | $281.8k; DefiLlama "Gauntlet" $287.6k = Tempo Earn + Gauntlet pathUSD Frontier ($5.8k, same Safes) | owner Safe 4-of-7, curator Safe 3-of-7 (same 7 signers), allocator EOA, sentinel EOA | claim 8 | Mitigating: `addAdapter` 7 days, caps 3 days, fees 1 day, registry abdicated. Context: 5 stale `Submit` entries (setName, setSymbol, setMaxRate, setIsSentinel, setCurator) are inert, those functions are not `timelocked()` |
| T4 | Morpho Blue core | `0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97` | docs.morpho.org addresses, Tempo tab | DefiLlama Morpho Blue $45.27M | owner Safe 5-of-9, no module or guard, same 9 signers as the Ethereum Morpho owner `0xcBa28b38...9AFa` | claim 13 | Mitigating: Morpho Blue owner can only enable IRMs/LLTVs and set fees (max 25% of interest) and fee recipient; markets are immutable. Fee recipient is currently zero |
| T5 | Morpho market cbBTC/pathUSD, oracle authority | market `0x75add2f6...14f5`, oracle `0xa59e9ACD8499343ae7b944df898fc20388ACD245` | Morpho API `markets`, `idToMarketParams` live, oracle from official ChainlinkOracleV2 factory | $11.46M supplied, $10.88M borrowed | Oracle immutable; its two feeds (RedStone cbBTC `0x6b1E...9084`, RedStone pathUSD `0xf552...4753`) are EIP-1967 proxies whose ProxyAdmin `0xFB1267A2...4AA5` is owned by a Safe 2-of-3, no module | claims 9 to 12 | Aggravating: a 2-of-3 feed upgrade with no delay can misprice collateral of the market that T1 and T3 lend into. Mitigating: feed addresses match RedStone's official `tempoMultiFeed.json` (0.5% deviation, 24 h heartbeat for cbBTC), shared adapter `0x368e...7ca4` used by RedStone on many chains |
| T6 | USDB (USDBridge), TIP-20 | `0x20c0000000000000000000003158081efd85bfc2` | official Tempo token list | 30.38M on-chain supply; DefiLlama stablecoins "USDBridge" 30.52M | `DEFAULT_ADMIN_ROLE` = 7702-delegated EOA `0x79C6631F...4a4E`; `ISSUER_ROLE` = plain EOA `0x42363cb9...5e89`, 7702 EOA `0x19810813...001E`, Bridge issuance controller `0x8354D80E...9058` | claims 18, 19, 21 | Aggravating: a plain EOA can mint directly (simulated `mint` succeeds from it, reverts from `0xdEaD`). Mitigating: `supplyCap` 200M |
| T7 | cbBTC (Coinbase Wrapped BTC via CCIP), TIP-20 | `0x20c000000000000000000000c412ec89d0c08be5` | official Tempo token list; Chainlink docs `ccip/v1_2_0/mainnet/tokens.json` (`tempo-mainnet`) | 258.9 BTC, about $19.9M at $76.8k | `DEFAULT_ADMIN_ROLE` = CCIP RBACTimelock `0xd31dB306...3EA1` (also owner of the CCIP Router and TokenAdminRegistry on Tempo); `ISSUER_ROLE` = BurnMintTokenPool 1.6.1 `0x3b54...c71E`, owned by the same timelock | claims 14 to 17 | Mitigating: 3 h min delay for proposals (proposer MCMS: 2 of 3 groups, 2 signatures each), pool inbound rate limit 79.2 BTC capacity. Aggravating: the BYPASSER_ROLE MCMS executes with no delay (root needs all 3 sub-groups, at least 8 signatures of 47); the admin path is not rate limited (it can grant `ISSUER_ROLE`), supply cap unlimited. Also the collateral of T5 |
| T8 | PRIME (Hastra PRIME via CCIP), TIP-20 | `0x20c00000000000000000000058d0b8b2cfdb358c` | official Tempo token list | 6.03M supply x $1.059 (`coins.llama.fi`, Solana mint `3b8X44fL...Uu7` read from the pool's `getRemoteToken`) = about $6.38M | `DEFAULT_ADMIN_ROLE` = Safe 4-of-7 `0x7039867c...2936`; `ISSUER_ROLE` = CCIP BurnMintTokenPool `0xffDF...571a` owned by the T7 RBACTimelock | claim 22 | Mitigating: pool inbound rate limit 13.49M PRIME. Context: the RBACTimelock held `DEFAULT_ADMIN_ROLE` on PRIME and revoked it at block 32,482,513. Pool not listed in Chainlink's docs token file (only on-chain reads) |
| T9 | DLUSD (Deel USD), TIP-20 | `0x20c0000000000000000000006fd9a167923ba194` | official Tempo token list | 3.77M supply; DefiLlama stablecoins "Deel USD" 3.79M | `DEFAULT_ADMIN_ROLE` = same EOA `0x79C6631F...4a4E` as T6 and pathUSD; `ISSUER_ROLE` = Bridge controller `0x8354...9058`; TIP-403 policy 2 (blacklist) admin = 7702 EOA `0x251d2711...5246` (same policy as pathUSD) | claims 19 to 21 | Aggravating: single key can upgrade the controller (simulated) and grant roles. Mitigating: `supplyCap` 50M, per-transaction mint limit 10M on the controller |
| T10 | EURC.e (Bridged EURC, Stargate), TIP-20 | `0x20c0000000000000000000001621e21F71CF12fb` | Tempo docs `guide/bridge-layerzero` | 1.459M EURC x $1.147 = about $1.67M; DefiLlama stablecoins EURC on Tempo 1.67M EUR-peg | `DEFAULT_ADMIN_ROLE`, `PAUSE_ROLE`, `BURN_BLOCKED_ROLE` = LayerZero OneSig 5-of-7 `0x09c865FA...3A1f`; `ISSUER_ROLE` = Stargate OFT `0x7753...dC71` owned by the same OneSig | claim 25 | Mitigating: 5-of-7. Aggravating (R6): same signer set as USDC.e, one compromise reaches both. LZ inbound: 3 required DVNs, 15 confirmations, delegate = the OneSig |
| T11 | cUSD (Cap USD), TIP-20 | `0x20c0000000000000000000000520792dcccccccc` | Tempo docs `guide/bridge-layerzero` | 50.3k supply (low value, kept as the correction of a refused claim) | `DEFAULT_ADMIN_ROLE` = Cap TimelockController (24 h) whose proposer/executor/canceller is Safe 3-of-5; `ISSUER_ROLE` = UUPS LayerZero OFT `0xbD12...2e43`, owner = the timelock | claims 23, 24 | Mitigating: 24 h on role and upgrade actions. Aggravating: OFT endpoint delegate = the same 3-of-5 Safe, which can reconfigure DVNs instantly, i.e. a zero-delay path to forged inbound mints |
| T12 | Tempo Stablecoin DEX (precompile) | `0xdec0000000000000000000000000000000000000` | Tempo docs `quickstart/predeployed-contracts` | DefiLlama $11.58M | none on chain: code `0xef`, official `stablecoin_dex/dispatch.rs` exposes only permissionless calls (`place`, `cancel`, `swap*`, `createPair`, `setBookIndex`); changes only by hardfork | claim 28 | Context: held from the morning draft. Score must be read through `chainCappedComposite` (chain baseline 31). Indirect dependence on each listed token's pause and TIP-403 policy |
| T13 | Tempo Fee AMM (FeeManager precompile) | `0xfeec000000000000000000000000000000000000` | Tempo docs `quickstart/predeployed-contracts` | DefiLlama $44.2k | none on chain: code `0xef`, dispatch exposes user and validator calls only | claim 28 | Same as T12. Validators choose their fee token (`setValidatorToken`) |
| T14 | Uniswap V4 PoolManager | `0x33620f62c5b9b2086dd6b62f4a297a9f30347029` | `Uniswap/contracts/deployments/4217.md` | DefiLlama $3.69M | `owner()` = Uniswap Wormhole Message Receiver `0xcfb43dc5...811b`, whose `messageSender` is Ethereum `0xf5f44962...615a`, owned by Uniswap Timelock `0x1a9C8182...35BC` (`delay()` = 2 days, admin GovernorBravo) | claims 26, 27 | Mitigating: owner powers limited to the protocol fee controller (currently unset), 2-day timelock plus on-chain governance, message timeout 2 days. Aggravating: relay trusts the Wormhole guardian set (not read here) |
| T15 | Uniswap V2 Factory | `0xf9ec577a4e45b5278bb7cf60fcbc20c3acaef68f` | `Uniswap/contracts/deployments/4217.md` | DefiLlama $72.5k | `feeToSetter()` = same Wormhole receiver as T14; `feeTo()` = zero | claims 26, 27 | Mitigating: only the fee switch; same governance path as T14 |

## 4. Score reading

Two readings are given on purpose. "Committed R1-R7" is what the repo's
`scripts/methodology_test.py` rules produce today. "Resolved reading" applies the same
formulas (R4, R5, R5b, R7) after resolving controllers that rule R2 cannot follow yet. The
resolved numbers are a proposal for `scoring_build`, not scores.

| # | Committed R1-R7 (admin / multisig / timelock / composite) | Why | Resolved reading (proposal) |
|---|---|---|---|
| T6 USDB | 20 / 0 / 0 / 8 | controller `0x8354` has no `owner()` and an empty EIP-1967 admin slot | weakest key is a plain EOA (1,1): 10 / 15 / 0 / **9** |
| T7 cbBTC | 20 / 0 / 0 / 8 | RBACTimelock and MCMS not resolvable by R2 | weakest `k` = proposer MCMS (4 signatures across 42), shortest delay = bypasser (0 s): 65 / 42 / 0 / **39** |
| T8 PRIME | 20 / 0 / 0 / 8 | same (pool owner is the RBACTimelock) | Safe 4-of-7 and MCMS 4-of-42, equal `k`, larger `n` weaker: 65 / 42 / 0 / **39** |
| T9 DLUSD | 20 / 0 / 0 / 8 | same as T6 | (1,1): 10 / 15 / 0 / **9** |
| T10 EURC.e | 65 / 98 / 0 / 55, crossExposure 80 | resolved by R2 already | unchanged |
| T11 cUSD | 20 / 0 / 0 / 8 | TimelockController has no `owner()` | Safe 3-of-5: 65 / 58 / 0 / **43** if the delegate path counts (no delay); 65 / 58 / 35 / **54** if only the 24 h role path counts |
| T12, T13 precompiles | 100 / 100 / 0 / 70, capped 31 | R4 empty root-control set | unchanged |
| T14, T15 Uniswap | 20 / 0 / 0 / 8 | receiver is not a local key set | governance relay; no numeric proposal (cross-chain root, fee-only powers) |
| T1 to T5 Morpho | no rule | Vault V2, Morpho Blue and market oracles are not a target type in METHODOLOGY.md 4.1 | pattern only, see section 5; indicative on the fund-destination path: T1 curator 1-of-1 + 3 days = 10 / 15 / 60 / 27; T3 curator 3-of-7 + 3 days = 65 / 56 / 60 / 61 |

Cross-exposure inside this batch (R6, before any numeric use): EOA `0x79C6631F` holds
`DEFAULT_ADMIN_ROLE` on pathUSD, USDB and DLUSD (about $73.5M of supply under one key); the
CCIP RBACTimelock controls cbBTC and PRIME issuance; the Stargate OneSig controls EURC.e and
USDC.e; T2 is fully exposed to T1; T1 and T3 lend only into T5, whose collateral is T7.

## 5. Per-target notes

### Morpho Vault V2 (T1 to T3): the full authority surface

Source read: `morpho-org/vault-v2` `src/VaultV2.sol`. Code identical (comments aside) between
release tag `2025-12-04` and `main`; every getter used below (`timelock`, `abdicated`,
`adapterRegistry`, gates) answers on chain, and the three vaults are `isVaultV2 = true` on
the Tempo VaultV2Factory `0x3DE400E3...82Db` (docs.morpho.org, Tempo tab).

| Role | Powers (source) | Delay |
|---|---|---|
| owner | `setOwner`, `setCurator`, `setIsSentinel`, `setName`, `setSymbol`; cannot move funds | none |
| curator | `submit` then execute: allocators, gates, adapter registry, add/remove adapter, timelocks, abdicate, fees, cap increases, force-deallocate penalty; `decreaseAbsoluteCap`/`decreaseRelativeCap` instant | per-selector `timelock`, or never if abdicated |
| allocator | `allocate`/`deallocate` among existing adapters within caps, liquidity adapter, `maxRate` | none |
| sentinel | `revoke` pending submissions, decrease caps, `deallocate` | none |

Live timelocks in seconds (`abd` = abdicated):

| Selector | T1 Sentora | T2 `0x83a1` | T3 Tempo Earn |
|---|---|---|---|
| `addAdapter` | 259200 | abd | 604800 |
| `removeAdapter` | 604800 | abd | 604800 |
| `increaseAbsoluteCap` / `increaseRelativeCap` | 259200 / 259200 | 0 / 0 | 259200 / 259200 |
| `setAdapterRegistry` | abd (registry = MorphoRegistry `0xB118...29E0`) | 0 (registry unset) | abd (MorphoRegistry) |
| `setIsAllocator` | 0 | 0 | 0 |
| `setReceiveSharesGate`, `setSendSharesGate`, `setReceiveAssetsGate` | abd | abd | abd |
| `setSendAssetsGate` (deposits only) | 0 | abd | 604800 |
| `increaseTimelock` / `abdicate` | 604800 / 604800 | 0 / 0 | 604800 / 604800 |
| fees (`setPerformanceFee`, `setManagementFee`) | 0 | 0 | 86400 |
| `setForceDeallocatePenalty` | 0 | 0 | 4320 |

Current non-zero caps (from `IncreaseAbsoluteCap`/`IncreaseRelativeCap` logs, confirmed with
live `absoluteCap`): T1 allows only the cbBTC/pathUSD market (market cap 30M pathUSD, cbBTC
collateral and adapter id uncapped); T3 the same market (market cap 20M, cbBTC cap 50M).
No pending submission on T1 or T2. T1's adapter `0x799c...fBE6` has its own timelocks
(`setSkimRecipient` and `burnShares` 3 days). T3's adapter has `setSkimRecipient`,
`increaseTimelock` and `abdicate` at 0 (skim only reaches tokens stranded in the adapter)
and `burnShares` at 3 days.

Why the morning "timelock 0" was wrong: the owner's instant powers are real but not
fund-moving; the path that could send depositor funds to a new destination (new adapter, or a
cap on a new market with a hostile oracle) is timelocked (T1, T3) or abdicated (T2).

### Bridge issuance controller `0x8354...9058` (pathUSD, USDB, DLUSD)

The committed R2 stops at "unresolved" here. The proxy (100 bytes, EIP-1967 implementation
`0x7742d1F4...a140`, `UPGRADE_INTERFACE_VERSION` 5.0.0) is UUPS with
AccessControlEnumerable. Selectors resolved from the implementation bytecode include
`mintBridgeEcosystem`, `mintWithApproval`, `setMinterAllowance`, `setTxnMintLimit`,
`setStablecoinPaused`, `upgradeToAndCall`, `getRoleMembers`. Live role members:
`DEFAULT_ADMIN_ROLE` and `MINT_RATE_LIMIT_SETTER_ROLE` = `0x79C6631F...4a4E` only;
`BURNER_ROLE` = `0x19810813...001E`; `PUBLISHER_ROLE` = `0xefd57792...ad08`; 4 `UNWRAPPER_ROLE`
holders; no `STABLECOIN_PAUSER_ROLE`. An `eth_call` of `upgradeToAndCall(currentImpl, 0x)`
from `0x79C6631F` returns success and reverts from `0xdEaD`, so this single key can replace
the minting logic. `0x79C6631F` is an EOA with an EIP-7702 delegation to
`0x0000Fb77...b16b` (all 12 dispatcher selectors resolve to execute, nonce and signature
helpers, none adds keys; a third-party registry lists it as a Fireblocks delegation, not
used as a primary source). This also changes the reading of the already-scored pathUSD:
its `ISSUER_ROLE` holder is a single-key-controlled UUPS contract, not an opaque contract
(open point 2).

### CCIP RBACTimelock `0xd31dB306...3EA1` (cbBTC, PRIME)

Dispatcher selectors: `scheduleBatch`, `executeBatch`, `bypasserExecuteBatch`,
`blockFunctionSelector`, `getMinDelay`, enumerable roles. Live: `getMinDelay() = 10800`;
ADMIN_ROLE = itself; PROPOSER = MCMS `0xd3f3...4c18`; EXECUTOR = call proxy `0x1560...4ad3`
(621 bytes, embeds the timelock address); CANCELLER = 3 MCMS; BYPASSER = MCMS
`0x7f02...9d71`; no blocked selector. It owns the CCIP Router `0xa132...ed01` and the
TokenAdminRegistry `0x60A9...57F3` listed for `tempo-mainnet` in Chainlink's docs, and is
the registry administrator of both cbBTC and PRIME. MCMS `getConfig()` (both endpoints
agree):

| MCMS | Signers | Root rule | Minimum signatures | Delay |
|---|---|---|---|---|
| Proposer `0xd3f3` | 42 | 2 of 3 groups, each 2-of-N (17, 18, 7) | 4 | 3 h (timelock) |
| Bypasser `0x7f02` | 47 | all 3 groups: 3 of 16 sub-groups (1 signature each), 1 of 5, both of two sub-groups (2-of-8 and 2-of-10) | 8 | none |
| Canceller `0xf58a` | 47 | 1 of 3 groups | 2 | cancel only |

cbBTC pool: remote chain selector `15971525489660198786`, remote token
`0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf` (cbBTC on Base, selector mapped to `ethereum-mainnet-base-1` in Chainlink's `chains.json`); inbound bucket 79.2 BTC.
PRIME pool: remote selector `124615329519749607` (`solana-mainnet` in the same file), Solana mint derived above; inbound bucket
13.49M PRIME; rate-limit admin = the Hastra 4-of-7 Safe.

### RedStone feeds behind T5

Both feeds are 2227-byte EIP-1967 proxies (implementations `0xDaEF...142B` and
`0x8122...50C1`, each embedding adapter `0x368e...7ca4`, itself a proxy with the same
ProxyAdmin). ProxyAdmin `0xFB1267A2...4AA5` owner = Safe 1.3.0 2-of-3, three EOA owners, no
module, no guard. No timelock on the upgrade path.

## 6. Verification

Every retained fact has a command in this run's claims journal (30 lines, all executed with
exit code 0 before submission). Examples:

```bash
C=$HOME/.foundry/bin/cast; R=https://rpc.tempo.xyz
$C call 0x9a044AE05E5e6290DcF56afd69548565e957a626 "timelock(bytes4)(uint256)" 0x60d54d41 --rpc-url $R   # addAdapter: 259200
$C call 0x83a1491f3e7f8dAAB8F787a631334b9ca7a87023 "abdicated(bytes4)(bool)" 0x60d54d41 --rpc-url $R    # true
$C call 0x21Fa111A254549Ee317d2Ad623C8d86AA21814E7 "morphoVaultV1()(address)" --rpc-url $R              # Sentora vault
$C call 0x8354D80EeA9978Faa04c3b36771c1e8b9c3e9058 "getRoleMembers(bytes32)(address[])" 0x$(printf '0%.0s' {1..64}) --rpc-url $R
$C call --from 0x42363cb98490128e7932a92c192dCf03d1115e89 0x20c0000000000000000000003158081efd85bfc2 \
  "mint(address,uint256)" 0x42363cb98490128e7932a92c192dCf03d1115e89 1 --rpc-url $R                       # succeeds (simulation only)
$C call 0xd31dB306E5D79F0018Ac92e08492284201493EA1 "getMinDelay()(uint256)" --rpc-url $R                # 10800
$C call 0x0000000035A7744F94e6949431CE20EA77312a55 "getMinDelay()(uint256)" --rpc-url $R                # 86400
$C call 0x20Bb7C2E2f4e5ca2B4c57060d1aE2615245dCc9C "delegates(address)(address)" 0xbD12E50Bfaa25735D074DBfDCF73208b9ccD2e43 --rpc-url $R
```

Single-source gaps, disclosed: role holders come from `RoleMembershipUpdated` logs on the
official endpoint only (publicnode refuses bulk `eth_getLogs`), each holder then confirmed
with `hasRole` on both endpoints; Morpho cap ids come from logs on the official endpoint,
each cap confirmed live; implementation bytecode of the Bridge controller, Cap timelock,
CCIP timelock and MCMS is unverified on any explorer, so their behaviour is inferred from
dispatcher selectors plus live reads and simulations, not from published source (the Cap
timelock's selectors match OpenZeppelin TimelockController's public interface).

## 7. Checked and dropped

| Candidate | Why dropped |
|---|---|
| senpathUSDE `0x20c0...f768` (110.9k) | `ISSUER_ROLE` is an unverified 23.9k-byte vault contract (operator, distributor, emergency guardian) not resolved end to end this run; below the value of retained targets |
| GBPA `0x20c0...a4c3` (50k GBP) | batch read raised `IndexError` and was not retried; small value |
| BRLA (50.1k BRL), stcUSD (23.9k), USD1, goUSD, syrupUSDC, USDY, reUSD, MACH, CADD, SBC, frxUSD, EURAU, USDe, sUSDe, YLDS, wYLDS, siUSD, wsrUSD, rUSD, GUSD, iUSD, CHFAU, SEKAU | supply under $25k equivalent, several at zero |
| "Sentora Curator", "Gauntlet" (DefiLlama) | labels for T1 and T3, not separate contracts |
| Symbiosis ($21.1k), Uniswap V3 ($242), Hinkal, GlueHook, LayerZero V2, Reservoir Protocol, Skate AMM | TVL under $25k |
| Morpho markets other than cbBTC/pathUSD (17) | supply under $5 each |

## 8. Open points for `scoring_build`

1. **R2 has no hop for four controller types found on real value**: UUPS +
   AccessControlEnumerable (Bridge controller), OpenZeppelin TimelockController (Cap),
   Chainlink RBACTimelock + hierarchical MCMS (CCIP), and the LayerZero endpoint delegate as
   a zero-delay path next to an owner timelock. All four currently collapse to "unresolved"
   (composite 8) although they are resolvable with live reads.
2. **pathUSD's committed score should be revisited**: its `ISSUER_ROLE` holder is the Bridge
   controller above, controlled by the same single key as its `DEFAULT_ADMIN_ROLE`.
3. **Bug in committed `classify()`** (`scripts/methodology_test.py`, nested-controller
   branch): `min(resolved, key=lambda r: (r["k"], -r["n"]))` raises `TypeError` when a
   depth-1 controller is unresolved (`k=None`). It triggered on cbBTC, PRIME and cUSD in this
   run (the local batch used rule R3's own ordering instead). Not fixed in the repo by this
   scouting run.
4. **CLOSED 2026-09-18 for Morpho Vault V2 (rule R8, METHODOLOGY.md section 4.1),
   market oracles (T5) still open**: root set = `{owner, curator}` (allocators
   excluded as a bounded, non-originating power, the same convention as
   TIP-20's `UNPAUSE_ROLE`); delay = per-selector `timelock(bytes4)` on the
   5 fund-destination selectors (`addAdapter`, `removeAdapter`,
   `setAdapterRegistry`, `increaseAbsoluteCap`, `increaseRelativeCap`);
   `abdicated(bytes4) = true` excludes that selector from the delay minimum
   (permanently closed, not merely delayed). Implemented in
   `score_vault_v2()`/`_vault_v2_timelock()`, `scripts/methodology_test.py`;
   scored T1-T3 live, see `data/scored_targets_2026-09-18-vault-v2.md`. T4
   (Morpho Blue core) and T5 (the cbBTC/pathUSD market oracle, a proxy-admin
   shape already resolvable by plain R2, not R8) are NOT yet wired into
   `score_all()` -- left for a future pass, not silently folded into R8.
5. EURC.e and USDC.e share one signer set (R6), and T6/T9/pathUSD share one key: the
   cross-exposure term will move once these targets are scored in the same run.
