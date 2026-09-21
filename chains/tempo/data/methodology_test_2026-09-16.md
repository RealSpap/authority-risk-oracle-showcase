# Tempo: methodology test, 2026-09-16

Purpose: apply `chains/tempo/METHODOLOGY.md` end to end to real, significant Tempo
mainnet targets, read live, and record every place where the written rules were not
enough to produce a number. The fixes are in METHODOLOGY.md (new section 4.1, corrected
section 6, changelog in section 8).

Reads: 2026-09-16 around 22:10 to 22:40 local time, Tempo mainnet (chain id `4217`, head
about block 39.83 million), official endpoint `https://rpc.tempo.xyz`, every `eth_call`
fact re-read on the independent endpoint `https://tempo-rpc.publicnode.com` (the script
raises on any disagreement). Read only: no transaction, no key. Live values drift; the
orders of magnitude below are what matters.

## Does mainnet have real targets?

Yes. Tempo mainnet is live (since 2026-03-18 per the official connection page) and carries
real stablecoin value, so this test runs on mainnet, not on the Moderato testnet.

| Token (TIP-20) | Address | `totalSupply` (6 decimals) |
|---|---|---|
| USDC.e (Bridged USDC, Stargate) | `0x20C000000000000000000000b9537d11c60E8b50` | about 61.6 million |
| pathUSD | `0x20c0000000000000000000000000000000000000` | about 38.6 million |
| USDT0 | `0x20c00000000000000000000014f22ca97301eb73` | about 9.7 million |

Reproduce everything below with one command:

```bash
python3 chains/tempo/scripts/methodology_test.py          # full reads + scores (JSON), about 3 minutes
python3 chains/tempo/scripts/methodology_test.py scores   # scores only
```

## Result

| Target | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | chainCappedComposite (notes) |
|---|---|---|---|---|---|---|---|
| Tempo L1 validator registry (chain baseline) | 50 | 37 | 0 | 100 | 100 | 31 | n/a |
| USDC.e | 65 | 98 | 0 | 100 | 100 | 55 | 31 |
| USDT0 | 65 | 58 | 0 | 100 | 100 | 43 | 31 |

Not published on chain. This is a methodology test only. The chain baseline was scored
alongside the two tokens because rule R6b needs it as a cap.

## Target 1: USDC.e

### Why this target

Largest stablecoin on Tempo by supply (about 61.6 million), bridged from Ethereum through
Stargate. It exercises every TIP-20 specific part of the methodology: role system, TIP-403
policy, bridge contract as issuer, LayerZero message security.

### Identifier and sources

| Fact | Source 1 | Source 2 (independent) |
|---|---|---|
| Token `0x20C0...8b50` is USDC.e | Tempo docs, [guide/bridge-layerzero](https://tempo.xyz/developers/docs/guide/bridge-layerzero), token table | on-chain `name()` = "Bridged USDC (Stargate)" on both endpoints |
| Stargate OFT `0x8c76e2F6...4392` | same Tempo docs page, "Stargate contracts on Tempo" | on-chain `token()` of `0x8c76...` returns `0x20C0...8b50` |
| Owner `0x09c865FA...3A1f` is a LayerZero OneSig | bytecode answers `VERSION()` = `0.0.1`, `LEAF_ENCODING_VERSION()` = 1, `threshold()`, `getSigners()`, `executorRequired()` | official source [LayerZero-Labs/OneSig `OneSig.sol`](https://github.com/LayerZero-Labs/OneSig/blob/main/packages/onesig-evm/contracts/OneSig.sol) declares `VERSION = "0.0.1"` and `LEAF_ENCODING_VERSION = 1` |
| That OneSig is Stargate's | the Stargate USDC pool on Ethereum listed in the same Tempo docs page (`0xc0263958...89C7`) is owned by OneSig `0xBE634B03...5413`, whose `getSigners()` on Ethereum is the same set of 7 addresses, threshold 5 | read on `https://ethereum-rpc.publicnode.com` |

### Raw reads

Role holders enumerated from every `RoleMembershipUpdated` log of the token since genesis
(rule R1b), then confirmed with `hasRole` on both endpoints:

| Block | Event | Role | Account | Granted |
|---|---|---|---|---|
| 4,010,415 | creation grant | `DEFAULT_ADMIN_ROLE` | `0x5e6e4f23...9ed5` (EOA deployer) | yes |
| 4,013,280 | grant | `ISSUER_ROLE` | `0xA7d119b7...8543` (earlier Stargate OFT, other endpoint) | yes |
| 4,013,283 to 4,013,287 | grant | `PAUSE_ROLE`, `UNPAUSE_ROLE`, `BURN_BLOCKED_ROLE` | OneSig `0x09c865FA...3A1f` | yes |
| 4,013,608 | grant | `DEFAULT_ADMIN_ROLE` | OneSig `0x09c865FA...3A1f` | yes |
| 4,013,611 | revoke | `DEFAULT_ADMIN_ROLE` | `0x5e6e4f23...9ed5` | no |
| 5,140,155 | grant | `ISSUER_ROLE` | Stargate OFT `0x8c76e2F6...4392` | yes |
| 5,140,166 | revoke | `ISSUER_ROLE` | `0xA7d119b7...8543` | no |

No `RoleAdminUpdated` event. Current state (both endpoints):

| Read | Value |
|---|---|
| `hasRole` holders now | `DEFAULT_ADMIN_ROLE`, `PAUSE_ROLE`, `UNPAUSE_ROLE`, `BURN_BLOCKED_ROLE`: OneSig only. `ISSUER_ROLE`: Stargate OFT only. The deployer EOA and the earlier OFT hold nothing |
| `transferPolicyId()` | 1 (always-allow, no policy admin) |
| `paused()` / `supplyCap()` | false / `type(uint128).max` |
| `eth_getCode(token)` | `0xef` (precompile marker, code not issuer-upgradeable) |
| Stargate OFT `owner()` | OneSig `0x09c865FA...3A1f`; EIP-1967 implementation and admin slots empty (not a proxy) |
| OneSig `threshold()` / `getSigners()` | 5 / 7 addresses, all without code (EOAs) |
| OneSig `executorRequired()` / `getExecutors()` | true / 1 executor. Per `OneSig.sol`, `canExecuteTransaction` also accepts any signer, so the executor is a liveness gate, not an extra approval |
| OneSig delay | none: `OneSig.sol` has no delay or timelock; the signed Merkle root carries an `expiry`, a validity deadline, not a waiting period |
| LayerZero inbound from Ethereum (`EndpointV2.getConfig` for Stargate `TokenMessaging` `0x19Ff94Fe...b9F5`) | delegate = the same OneSig; 15 confirmations; 3 required DVNs, 0 optional: Nethermind, LayerZero Labs, Canary (names from the LayerZero metadata API `metadata.layerzero-api.com/v1/metadata/dvns`, `tempo` section) |

### Derivation

| Dimension | Rule | Derivation | Score |
|---|---|---|---|
| Root-control set | R1 | `DEFAULT_ADMIN_ROLE`, `PAUSE_ROLE`, `BURN_BLOCKED_ROLE` holder = OneSig; `ISSUER_ROLE` holder = Stargate OFT; policy 1 adds no admin | 4 entries |
| Key resolution | R2 | OneSig = `(5, 7)`; Stargate OFT is a contract, `owner()` = the same OneSig, not a proxy, so `(5, 7)` | |
| Weakest key | R3 | every entry is `(5, 7)` | 5-of-7 |
| adminKeyScore | R4 | `k >= 3` | 65 |
| multisigScore | R5 | `20 x 5 - (7 - 5)` = 98 | 98 |
| timelockScore | R5b | no delay on TIP-20 role actions, on OneSig execution, or on the OFT owner | 0 |
| oracleAuthorityScore | R5c | a stablecoin token reads no price | 100 |
| crossExposureScore | R6 | the 7 OneSig signers appear in no other tracked Tempo target (chain baseline, USDT0) | 100 |
| compositeScore | R7 | `floor(0.4 x 65 + 0.3 x 98 + 0.3 x 0 + 0.5)` = `floor(55.9)` | 55 |

Notes (R6b), outside the number: `chainCappedComposite` = min(55, 31) = 31. Mint
authority in practice is a LayerZero message verified by 3 of 3 required DVNs. The same 7
signers at threshold 5 also own the Stargate USDC pool on Ethereum, so one signer quorum
controls both the collateral side and the minted side of the route.

Mitigating context: a 5-of-7 threshold is the strongest key found on Tempo so far, and no
EOA retains any role. Aggravating context: `DEFAULT_ADMIN_ROLE` can grant `ISSUER_ROLE` to
any address instantly, so the OneSig can mint USDC.e outside the bridge with no delay.

## Target 2: USDT0

### Why this target

Tether's omnichain USDT on Tempo (about 9.7 million), issued through Tether's own OFT
rather than Stargate, with a live custom blacklist policy. It tests a different issuer
design, a proxy issuer, and a non-trivial TIP-403 policy.

### Identifier and sources

| Fact | Source 1 | Source 2 (independent) |
|---|---|---|
| Token `0x20c0...eb73`, type OFT | Tempo docs, [guide/bridge-layerzero](https://tempo.xyz/developers/docs/guide/bridge-layerzero) | USDT0 official docs, [technical-documentation/deployments](https://docs.usdt0.to/technical-documentation/deployments), section "Tempo" |
| OFT `0xaf37E8B6...47ff`, Safe `0x4DFF9b5b...0bf8` | USDT0 deployments page, section "Tempo" (Token, OFT, Safe, TempoOFTWrapper) | on-chain: OFT `token()` = the token, OFT `owner()` = the Safe |

### Raw reads

| Block | Event | Detail |
|---|---|---|
| 5,253,168 | `RoleMembershipUpdated` | `DEFAULT_ADMIN_ROLE` granted to Safe `0x4DFF9b5b...0bf8` at creation |
| 5,268,053 | `TransferPolicyUpdate` | policy set to 3 by the Safe |
| 5,276,863 | `RoleMembershipUpdated` | `ISSUER_ROLE` granted to OFT `0xaf37E8B6...47ff` by the Safe |

| Read (both endpoints) | Value |
|---|---|
| `hasRole` holders now | `DEFAULT_ADMIN_ROLE`: Safe. `ISSUER_ROLE`: OFT. `PAUSE_ROLE`, `UNPAUSE_ROLE`, `BURN_BLOCKED_ROLE`: nobody |
| `transferPolicyId()` / `policyData(3)` | 3 / type 1 = BLACKLIST (enum order `WHITELIST, BLACKLIST` in the [TIP-403 spec](https://tempo.xyz/developers/docs/protocol/tip403/spec)), admin = the same Safe |
| Safe | `VERSION()` 1.4.1, singleton `0x29fcB43b...C762` (canonical SafeL2), threshold 3, 5 owners all EOAs, no module, no guard, nonce 78 |
| OFT `0xaf37...` | EIP-1967 proxy: implementation `0x01bff417...1071`, ProxyAdmin `0xe7cd86e1...c82d` whose `owner()` is the same Safe; OFT `owner()` = the Safe |
| LayerZero inbound from Ethereum | delegate = the Safe; 65 confirmations; 3 required DVNs, 0 optional: LayerZero Labs, USDT0, Canary |
| Same Safe on other chains | `0x4DFF9b5b...0bf8` on Ethereum and Arbitrum One: threshold 3, same set of 5 owners as on Tempo |

### Derivation

| Dimension | Rule | Derivation | Score |
|---|---|---|---|
| Root-control set | R1 | `DEFAULT_ADMIN_ROLE` = Safe; `ISSUER_ROLE` = OFT; policy 3 admin = Safe; no pause or burn-blocked holder (the Safe can grant them) | 3 entries |
| Key resolution | R2 | Safe = `(3, 5)`; OFT: `owner()` = Safe and ProxyAdmin `owner()` = Safe, so `(3, 5)` | |
| Weakest key | R3 | every entry is `(3, 5)` | 3-of-5 |
| adminKeyScore | R4 | `k >= 3` | 65 |
| multisigScore | R5 | `20 x 3 - (5 - 3)` = 58 | 58 |
| timelockScore | R5b | no delay on role grants, TIP-403 admin edits, Safe execution, or the ProxyAdmin upgrade path | 0 |
| oracleAuthorityScore | R5c | no price read | 100 |
| crossExposureScore | R6 | the 5 Safe owners appear in no other tracked Tempo target | 100 |
| compositeScore | R7 | `floor(0.4 x 65 + 0.3 x 58 + 0 + 0.5)` = `floor(43.9)` | 43 |

Notes (R6b): `chainCappedComposite` = 31. One 3-of-5 key set can, with no delay, upgrade the
OFT, grant `ISSUER_ROLE`, and add any holder to the blacklist; the same key set holds the
same Safe address on Ethereum and Arbitrum One (and the USDT0 docs list that Safe address
on many more chains). Mitigating context: no EOA holds any role; pause and burn-blocked
powers are not currently assigned.

## Chain baseline: Tempo L1 validator registry

| Read (both endpoints) | Value |
|---|---|
| `ValidatorConfigV2` `0xCCCC...0001` code | `0xef` (precompile) |
| `owner()` | Safe `0xdC659efF...cA33`, 1.4.1 canonical singleton, 2-of-5, owners all EOAs, no module, no guard, nonce 26 |
| `getActiveValidators()` | 14 entries |

Derivation: R1c root set = the Safe; R4 `k = 2` gives 50; R5 `20 x 2 - 3` = 37; R5b no delay
gives 0; R5c 100; R6 no signer shared with USDC.e or USDT0 gives 100 (it does share all 5
signers with the ZoneFactory owner Safe, which is not a scored target); R7
`floor(20 + 11.1 + 0 + 0.5)` = 31.

## Methodology gaps found

| # | Gap | Effect on the test | Fix |
|---|---|---|---|
| 1 | Section 6 bands were inverted: "0 to 20 (low risk)", "80 to 100 (high risk)", while `src/AuthorityRiskOracle.sol` and every published score use higher = safer | A score derived from the draft bands would have been published upside down | Section 6 rewritten with the contract orientation |
| 2 | No rule to pick one key when several addresses hold roles, and no numeric mapping | No number could be produced from section 4 alone | Section 4.1 rules R1 to R5 and R7, aligned with the approved Hyperliquid mapping for cross-chain comparability |
| 3 | No way to enumerate TIP-20 role holders (no enumeration getter) | `hasRole` needs candidates | R1b: full-history `RoleMembershipUpdated` scan in 100,000-block windows, then `hasRole` on two endpoints |
| 4 | Bridge contracts holding `ISSUER_ROLE` had no resolution rule | the issuer would have counted as "unresolved contract" | R2: follow `owner()` and EIP-1967 admin up to 2 hops; DVN set in notes |
| 5 | LayerZero OneSig not recognised (open point 1 of the draft) | the USDC.e admin, the largest asset, would be unresolved | R2 adds OneSig; open point 1 closed |
| 6 | `crossExposureScore` described qualitatively (bridge, chain baseline) while the on-chain field has a fixed formula | two incompatible meanings for one field | R6 contract formula; bridge, DVN, chain cap and cross-chain signer reuse moved to notes (R6b) |
| 7 | The Hyperliquid multisig formula is only monotone for `n <= 10` | not triggered here (largest `n` = 7), but Safes have no signer cap | floor of 16 for `k >= 2` in R5 |

Remaining limits, not fixed in this run:

| Limit | Why it stays open |
|---|---|
| Role-holder enumeration has a single log source | `https://tempo-rpc.publicnode.com` answered HTTP 403 to the bulk `eth_getLogs` scan; holders found are confirmed on both endpoints, but a grant missing from the official endpoint's logs would not be found |
| Cross-chain signer reuse is not in any number | R6 counts only tracked Tempo targets; USDT0 and Stargate keys control the same asset on other chains. A multi-chain overlap rule is a project-level decision |
| Only the Ethereum inbound LayerZero path was read | other source chains of the same OApp may carry a weaker DVN set; to read per peer in scouting |
| DVN names come from the LayerZero metadata API | a first-party source, but not an on-chain read |
| The chain cap is a note, not a score change | consistent with `chains/hyperliquid`; whether consumers should apply it is a scoring_build decision |
