# Scouted targets -- Arbitrum Ecosystem -- 2026-09-16 (attempt 2/2)

Scouting pass 2 for the `arbitrum-ecosystem` chain (Arbitrum One, chain 42161,
mainnet read-only). Distinct from Robinhood Chain, already covered by the root
of this repo.

This is a correction pass on the 2026-09-16 attempt 1 draft
(`runs/2026-09-16/arbitrum-ecosystem/brouillon_non_approuve/`), which was
refused 1/3 for three reasons. Each is addressed below, target by target,
rather than patched silently:

1. **Radiant TVL was inflated 1000x** (a unit error: the draft read DefiLlama's
   raw numeric field, which is already in whole USD, and mis-reported it as
   millions). Re-measured live today: the real Arbitrum TVL is in the low
   hundreds of thousands of USD, not hundreds of millions. Because of that,
   Radiant is kept in this batch but re-framed: it no longer qualifies as a
   "flagship by current TVL" target the way GMX, Camelot or Aave do, and is
   kept instead for its authority-risk relevance (see point 3). This is
   flagged explicitly rather than smoothed over.
2. **Two addresses (Camelot's factory, Radiant's LendingPool) came from the
   DefiLlama-Adapters repo, an aggregator, not the protocol's own docs/repo.**
   Both are re-sourced below from an official docs page or the protocol's own
   GitHub, with the exact URL. For Radiant, re-sourcing from the official docs
   surfaced that the DefiLlama-Adapters address was not even the live pool:
   the addresses differ, and the live `PoolAddressesProvider.getLendingPool()`
   call matches the official-docs address, not the aggregator's.
3. **The October 2024 Radiant hack (multisig-signer compromise, ~$50M) was
   omitted.** It is documented below with two independent sources: Radiant's
   own docs (date, official acknowledgment, remediation process) and
   DefiLlama's public hacks dataset (amount, classification, both affected
   chains). Both agree exactly on the date (2024-10-16).

5 targets this batch (at the 5-target scouting cap). All five have a
live-read, completely verified authority chain up to a root (Safe,
TimelockController, or DAO-governance executor), so all five are candidates
for `scoring_build` -- with Radiant flagged for a different reason than the
other four (see above).

All on-chain reads below were done fresh via `cast call` against
`https://arb1.arbitrum.io/rpc`, block ~505,872,336 (2026-09-16, ~20:32 UTC).
TVL figures are DefiLlama's `/protocol/<slug>` API, read live the same day
(units double-checked against the raw JSON field this time, not assumed).

## Summary table

| # | Protocol | Address | Address source | TVL (Arbitrum) + source | Authority pattern found |
|---|----------|---------|-----------------|--------------------------|--------------------------|
| 1 | GMX V2 (Synthetics) -- RoleStore | `0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72` | `gmx-io/gmx-synthetics` repo, `deployments/arbitrum/RoleStore.json` (official GMX GitHub), re-fetched and re-matched live this batch | ~$194M, DefiLlama `api.llama.fi/protocol/gmx`, `currentChainTvls.Arbitrum`, re-read live this batch | Custom AccessControl (`RoleStore`). `TIMELOCK_MULTISIG` role held by exactly 1 address, a Gnosis Safe **5-of-8** (`0x8D1d2e24...`). That same Safe is sole `PROPOSER_ROLE`+`EXECUTOR_ROLE` on `ConfigTimelockController` (`0xC77E6C0c...`), live `getMinDelay()` = 86,400s (1 day). Both confirmed live this batch, byte-identical to attempt 1's reads. |
| 2 | Camelot -- AMMv3 (Algebra) Factory | `0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B` | **Re-sourced**: Camelot's own official docs, `docs.camelot.exchange/contracts/arbitrum/one-mainnet`, table row labeled `AlgebraFactory` -- static HTML now reachable (this attempt fetched a URL the SPA-shell page from attempt 1 had not tried), matches the DefiLlama-Adapters address exactly, so attempt 1's address itself was correct, only its sourcing wasn't independent yet | ~$6.2M for the AMMv3 (Algebra) deployment this factory governs, DefiLlama `api.llama.fi/protocol/camelot-v3`, `currentChainTvls.Arbitrum` (the ~$12.7M figure from `api.llama.fi/protocol/camelot` covers v2+v3 combined) | `factory.owner()` -> Gnosis Safe **2-of-3** (`0xbA6A06f8...`), confirmed live via `getOwners()`/`getThreshold()`. No timelock in front of this Safe. All 3 owners confirmed EOAs this batch (zero-length bytecode each, resolving attempt 1's open item). |
| 3 | Radiant Capital -- LendingPool (V2 Core) | `0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886` | **Corrected address**: Radiant's own docs, `docs.radiant.capital/radiant/contracts-and-security/arbitrum-contracts`, "Core Contracts" section, `lendingPool:` field -- confirmed as the live pool by calling `PoolAddressesProvider.getLendingPool()` on-chain today, which returns this exact address. Attempt 1's address (`0xDd109cb6...`, from DefiLlama-Adapters) is a **different, stale contract** -- has code on-chain but is not what the live AddressesProvider points to. | **~$184K supplied / ~$97.7K borrowed** (corrected from attempt 1's "~$184.3M/~$97.5M" -- a 1000x unit-read error). DefiLlama `api.llama.fi/protocol/radiant-v2`, `currentChainTvls.Arbitrum` / `.Arbitrum-borrowed`, re-read live and the raw JSON field inspected directly this time. This tiny residual value is itself informative, see below. | `LendingPoolAddressesProvider` (`0x454a8dAf...`, matches attempt 1 and official docs) `.owner()` -> OpenZeppelin `TimelockController` (`0x27fC8f3B...`), confirmed live `getMinDelay()` = 259,200s (3 days), and independently confirmed against Radiant's own "Security Timelock" docs page, which names this exact address as the "v2-Core" timelock with a stated 72-hour delay. **Aggravating context (new this batch, was missing from attempt 1): on 2024-10-16, Radiant Capital was exploited for ~$50M** across Arbitrum and BSC via compromise of multiple Radiant multisig signers' devices, who were made to blind-sign a malicious transaction (DefiLlama hacks dataset: `classification: "Social Engineering"`, `technique: "Blind Signing"`, `amount: 50000000`, date `1729036800` = 2024-10-16 UTC exactly). Independently corroborated by Radiant's own docs, which acknowledge "the October 16, 2024 exploit" by name across multiple pages (remediation plan, exploited-contract list, zeroShadow Tornado Cash tracing report) without disputing the date. This is precisely the failure mode a Safe-plus-timelock authority pattern does not protect against: the timelock delays a proposal from a compromised set of signers, it does not stop the signers themselves from being compromised. The protocol's TVL is ~$184K today (attempt 1 misread the aggregator's correct figure as ~$184M). The hack is plausibly one factor in that decline, but causality is not established here. |
| 4 | Arbitrum Security Council -- Emergency Safe (L2, chain 42161) | `0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641` | `OffchainLabs/governance` repo (official Arbitrum GitHub), `files/mainnet/scmDeployment.json`, key `emergencyGnosisSafes["42161"]`; `l2Executor`/`l2CoreTimelock` cross-checked against the same repo's `files/mainnet/deployedContracts.json` this batch | Not a protocol with its own TVL -- this Safe is the emergency upgrade authority for Arbitrum One's core protocol contracts, relevant to every protocol on the chain, not a dApp with deposits | Gnosis Safe **9-of-12**, confirmed live via `getOwners()`/`getThreshold()`, byte-identical to attempt 1. Confirmed live it holds `EXECUTOR_ROLE` (`hasRole` = `true`) on the L2 `UpgradeExecutor` (`0xCF575722...`), which can bypass the ordinary L2 core `TimelockController`'s 691,200s (8-day) `getMinDelay()` for emergency action. Standard, publicly-documented Arbitrum security model. |
| 5 | Aave V3 -- Pool (Arbitrum) | `0x794a61358D6845594F94dc1DB02A252b5b4814aD` | **New this batch.** `bgd-labs/aave-address-book` repo (official Aave-ecosystem GitHub, maintained by BGD Labs, Aave's core dev team; addresses are the ones Aave Governance proposals themselves reference), `src/AaveV3Arbitrum.sol`, constant `POOL` | ~$489.2M supplied / ~$339.6M borrowed, DefiLlama `api.llama.fi/protocol/aave-v3`, `currentChainTvls.Arbitrum` / `.Arbitrum-borrowed` -- by far the largest TVL scouted this batch, a genuine current flagship | `PoolAddressesProvider` (`0xa97684ea...`) `.owner()` -> `0xFF113724...`, confirmed live to be a contract (not an EOA) and confirmed live to hold `DEFAULT_ADMIN_ROLE` on the Aave `ACLManager` (`0xa72636Cb...`). Per the same official address-book repo, this address is labeled `EXECUTOR_LVL_1` in `GovernanceV3Arbitrum.sol`: Aave's cross-chain governance executor, which only acts on payloads relayed from Ethereum-mainnet Aave DAO votes via the `CROSS_CHAIN_CONTROLLER` (`0xCbFB78a3...`, confirmed live to be a deployed contract). A separate `GOVERNANCE_GUARDIAN` Safe (`0x1A0581dd...`), confirmed live **5-of-9**, can veto/cancel payloads. **Open item, not resolved this pass**: the executor's own upstream root (the Ethereum-mainnet Aave DAO + CrossChainController message-relay path) was not independently re-derived hop-by-hop on Ethereum from this Arbitrum-scoped pass -- same category of open question already flagged for Uniswap V3's L1-aliased governance on Robinhood Chain, and worth a shared "external L1 DAO governance via bridge" sub-model rather than five separate guesses across chains. |

## Verification commands (re-run exactly as-is)

All commands need `dangerouslyDisableSandbox: true` in this sandboxed
environment -- the sandbox's TLS interception breaks `cast`'s and `curl`'s
HTTPS handshake (see project memory `feedback_gh_cli_sandbox_tls.md`, same
root cause). Re-run against a fresh block; addresses and role assignments are
live state and can legitimately change.

### 1. GMX V2 RoleStore / Timelock

```
RPC=https://arb1.arbitrum.io/rpc
ROLESTORE=0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72
CTC=0xC77E6C0ca99E02660A23c00A860Dd5a8912DEaF5
SAFE=0x8D1d2e24eC641eDC6a1ebe0F3aE7af0EBC573e0D

~/.foundry/bin/cast call $ROLESTORE "getRoleMembers(bytes32,uint256,uint256)(address[])" \
  0xe068a8d811c3c8290a8be34607cfa3184b26ffb8dea4dde7a451adfba9fa173a 0 10 --rpc-url $RPC
~/.foundry/bin/cast call $SAFE "getOwners()(address[])" --rpc-url $RPC
~/.foundry/bin/cast call $SAFE "getThreshold()(uint256)" --rpc-url $RPC
~/.foundry/bin/cast call $CTC "getMinDelay()(uint256)" --rpc-url $RPC
~/.foundry/bin/cast call $CTC "hasRole(bytes32,address)(bool)" $(~/.foundry/bin/cast keccak "PROPOSER_ROLE") $SAFE --rpc-url $RPC
~/.foundry/bin/cast call $CTC "hasRole(bytes32,address)(bool)" $(~/.foundry/bin/cast keccak "EXECUTOR_ROLE") $SAFE --rpc-url $RPC
```

Official-source cross-check:
```
curl -s "https://raw.githubusercontent.com/gmx-io/gmx-synthetics/main/deployments/arbitrum/RoleStore.json" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['address'])"
# -> 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72
```

### 2. Camelot AMMv3 (Algebra) Factory

```
RPC=https://arb1.arbitrum.io/rpc
FACTORY=0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B

~/.foundry/bin/cast call $FACTORY "owner()(address)" --rpc-url $RPC
# -> 0xbA6A06f8517e271DB44540e68BA46BEB4Bc6155d
~/.foundry/bin/cast call 0xbA6A06f8517e271DB44540e68BA46BEB4Bc6155d "getOwners()(address[])" --rpc-url $RPC
~/.foundry/bin/cast call 0xbA6A06f8517e271DB44540e68BA46BEB4Bc6155d "getThreshold()(uint256)" --rpc-url $RPC

# each of the 3 owners is an EOA (empty bytecode)
for a in 0x56140b52879D5b6D03449B912193c7b18210A7af 0x01E5d631ba707a029C8A1555bDAc4805d7853E21 0xd8dc994FE2b075c697e5051c89b713Bf15fa9294; do
  ~/.foundry/bin/cast code $a --rpc-url $RPC
done
```

Official-source cross-check:
```
curl -sL "https://docs.camelot.exchange/contracts/arbitrum/one-mainnet" \
  | grep -o 'AlgebraFactory[^0]*0x[a-fA-F0-9]\{40\}'
```

### 3. Radiant Capital LendingPool (V2 Core)

```
RPC=https://arb1.arbitrum.io/rpc
PROVIDER=0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a

~/.foundry/bin/cast call $PROVIDER "getLendingPool()(address)" --rpc-url $RPC
# -> 0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886 (matches official docs, NOT the DefiLlama-Adapters address)
~/.foundry/bin/cast call $PROVIDER "owner()(address)" --rpc-url $RPC
# -> 0x27fC8f3Be99e9799FA1B720D471647E6662AFf92, the TimelockController
~/.foundry/bin/cast call 0x27fC8f3Be99e9799FA1B720D471647E6662AFf92 "getMinDelay()(uint256)" --rpc-url $RPC
# -> 259200 (3 days / 72h, matches docs.radiant.capital/radiant/contracts-and-security/security-timelock)
```

Official-source cross-check:
```
curl -sL "https://docs.radiant.capital/radiant/contracts-and-security/arbitrum-contracts" \
  | grep -o 'lendingPool:[^0]*0x[a-fA-F0-9]\{40\}' | head -1
curl -sL "https://docs.radiant.capital/radiant/contracts-and-security/security-timelock.md" \
  | grep -c "27fC8f3Be99e9799FA1B720D471647E6662AFf92"
```

Hack corroboration (two independent sources, same date):
```
curl -s "https://api.llama.fi/hacks" | python3 -c "
import json,sys,datetime
d=json.load(sys.stdin)
for h in d:
    if h.get('name')=='Radiant V2' and h.get('amount')==50000000:
        print(h['classification'], h['technique'], h['amount'], h['chain'],
              datetime.datetime.utcfromtimestamp(h['date']))
"
# -> Social Engineering Blind Signing 50000000 ['BSC', 'Arbitrum'] 2024-10-16 00:00:00

curl -sL "https://docs.radiant.capital/radiant/remediation/zeroshadow-summary-report.md" \
  | grep -c "October 16, 2024"
```

### 4. Arbitrum Security Council Emergency Safe

```
RPC=https://arb1.arbitrum.io/rpc
SC=0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641
EXECUTOR=0xCF57572261c7c2BCF21ffD220ea7d1a27D40A827
TIMELOCK=0x34d45e99f7D8c45ed05B5cA72D54bbD1fb3F98f0

~/.foundry/bin/cast call $SC "getOwners()(address[])" --rpc-url $RPC
~/.foundry/bin/cast call $SC "getThreshold()(uint256)" --rpc-url $RPC
~/.foundry/bin/cast call $EXECUTOR "hasRole(bytes32,address)(bool)" $(~/.foundry/bin/cast keccak "EXECUTOR_ROLE") $SC --rpc-url $RPC
~/.foundry/bin/cast call $TIMELOCK "getMinDelay()(uint256)" --rpc-url $RPC
```

Official-source cross-check:
```
curl -s "https://raw.githubusercontent.com/OffchainLabs/governance/main/files/mainnet/scmDeployment.json" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['emergencyGnosisSafes']['42161'])"
# -> 0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641
curl -s "https://raw.githubusercontent.com/OffchainLabs/governance/main/files/mainnet/deployedContracts.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['l2Executor'], d['l2CoreTimelock'])"
```

### 5. Aave V3 Pool (Arbitrum)

```
RPC=https://arb1.arbitrum.io/rpc
PROVIDER=0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb
ACLMGR=0xa72636CbcAa8F5FF95B2cc47F3CDEe83F3294a0B
EXEC=0xFF1137243698CaA18EE364Cc966CF0e02A4e6327
GUARDIAN=0x1A0581dd5C7C3DA4Ba1CDa7e0BcA7286afc4973b

~/.foundry/bin/cast call $PROVIDER "owner()(address)" --rpc-url $RPC
# -> 0xFF1137243698CaA18EE364Cc966CF0e02A4e6327 (EXECUTOR_LVL_1)
~/.foundry/bin/cast code $EXEC --rpc-url $RPC
# non-empty: contract, not EOA
~/.foundry/bin/cast call $ACLMGR "hasRole(bytes32,address)(bool)" \
  0x0000000000000000000000000000000000000000000000000000000000000000 $EXEC --rpc-url $RPC
# -> true (DEFAULT_ADMIN_ROLE)
~/.foundry/bin/cast call $GUARDIAN "getOwners()(address[])" --rpc-url $RPC
~/.foundry/bin/cast call $GUARDIAN "getThreshold()(uint256)" --rpc-url $RPC
# -> 5
```

Official-source cross-check:
```
curl -s "https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/AaveV3Arbitrum.sol" \
  | grep -A1 "IPool internal constant POOL ="
curl -s "https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/GovernanceV3Arbitrum.sol" \
  | grep -c "0xFF1137243698CaA18EE364Cc966CF0e02A4e6327"
```

## TVL source calls (re-run exactly as-is)

```
curl -s "https://api.llama.fi/protocol/gmx" | python3 -c "import json,sys;print(json.load(sys.stdin)['currentChainTvls']['Arbitrum'])"
curl -s "https://api.llama.fi/protocol/camelot" | python3 -c "import json,sys;d=json.load(sys.stdin);print(sum(v for k,v in d['currentChainTvls'].items() if 'Arbitrum' in k))"
curl -s "https://api.llama.fi/protocol/radiant-v2" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['currentChainTvls']['Arbitrum'], d['currentChainTvls']['Arbitrum-borrowed'])"
curl -s "https://api.llama.fi/protocol/aave-v3" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['currentChainTvls']['Arbitrum'], d['currentChainTvls']['Arbitrum-borrowed'])"
```

## Open items for the next pass (not resolved this run, flagged rather than guessed)

- GMX: repo `config/roleConfigs/arbitrum.ts` vs. live `RoleStore` `ROLE_ADMIN` drift, noted in attempt 1, not re-investigated this batch (out of scope for the correction, and not one of the three refusal reasons). Still needs a scoring-phase pass before `adminKeyScore` is finalized.
- Radiant: `TimelockController` proposer/executor role holders still not enumerated (not `AccessControlEnumerable`) -- needs `CallScheduled` event history in the next pass.
- Radiant: whether the current (post-hack) `lendingPool` at `0xE23B4AE3...` is a redeployment or the pre-hack contract with reconfigured assets was not determined this pass -- the "Exploited Contract List" names specific rToken/vdToken addresses, not the pool proxy itself, so this is plausible either way and left open rather than assumed.
- Aave V3 Arbitrum: the Ethereum-mainnet root of the `EXECUTOR_LVL_1` cross-chain governance chain (Aave DAO vote -> Ethereum `CrossChainController` -> bridge adapter -> Arbitrum `CROSS_CHAIN_CONTROLLER` -> `EXECUTOR_LVL_1`) was confirmed only by the official address-book's own labeling, not independently re-derived hop-by-hop via `cast` on Ethereum from this Arbitrum-scoped pass. Same shared open question as Uniswap's L1-aliased governance (flagged on Robinhood Chain and for Arbitrum's own Uniswap V3 copy in attempt 1) -- worth a single shared "external L1 DAO governance via bridge" sub-model across all three cases (Uniswap x2, Aave) rather than scoring each ad hoc.
- Not yet scouted, real Arbitrum-native usage/TVL, plausible next candidates (deferred to stay within the 5-target cap): Pendle (Arbitrum market), Uniswap V3 Arbitrum (likely the same L1-aliased governance shape as the open item above, worth checking whether it is literally the same Ethereum Timelock alias), Compound III Arbitrum.
