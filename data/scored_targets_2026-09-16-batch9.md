# Batch 9 -- 2026-09-16 (automated pipeline run)

Source of candidates: the local candidate backlog prepared on 2026-09-16 (4 entries,
each already sourced from 2+ independent sources with `eth_getCode` confirmed, but
explicitly NOT yet verified live -- two of them had unresolved hops). No new web
research this batch; no tracker-board leads were consumed.

Every read below was done fresh on Robinhood Chain **mainnet** on two independent
RPCs, `https://rpc.mainnet.chain.robinhood.com` (block ~64,530,134) and
`https://robinhood.drpc.org` (block ~64,530,605), with byte-identical results on
both. `robinhood.drpc.org` is new to this project: it is the first working
second RPC found for this chain (Alchemy/Ankr/thirdweb public endpoints refuse it),
which also let this batch close the Curve second-RPC caveat (see end).

## Scoring convention used for all four (new helper `_safe_rooted_scores`)

All four authority chains end in one plain Gnosis Safe with no module, no guard,
and no timelock anywhere in the chain. One shared heuristic, stated rather than hidden:

- `adminKeyScore`: 65 if threshold >= 3, 50 if threshold == 2, 10 if threshold == 1;
  minus 5 when the same Safe both holds user funds and can upgrade the code guarding them.
- `multisigScore`: 15 per required signature + 5 per extra owner, capped at 100.
- `timelockScore`: 0. `oracleAuthorityScore`: 100 (not applicable).

This lands the four in the same range as the closest existing shapes (Arcus 2-of-3 = 43,
Longbow 2-of-3 = 33, Chainlink 4-of-9 = 36, LayerZero 5-of-7 = 34). Like every other
formula in `scorers.py`, it is a heuristic, not a measured risk.

## 1. PancakeSwap V3 Factory -- 44/100

- Target: `0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865` (PancakeSwap docs
  `developer.pancakeswap.finance/contracts/v3/addresses`, DefiLlama `pancakeswap-v3`
  adapter; deterministic CREATE3 address shared across PancakeSwap chains).
- `Factory.owner()` -> `0x543aDA9EABa5D8c2B1097C3540Ac970DCDBf1C2a`, a 183-byte proxy
  (EIP-1967 implementation slot -> `0xCcAc755fdA315D253f51629Cd13aF85c9A6d9E4b`, no admin
  slot). The implementation's bytecode contains `upgradeTo`, `upgradeToAndCall`,
  `proxiableUUID`, `owner`, `transferOwnership`: a UUPS owner wrapper, upgraded by its own owner.
- `wrapper.owner()` -> `0xfa206DAB60c014bEb6833004D8848910165e6047`, Safe v1.3.0,
  **3-of-6**, nonce 12, no modules, no guard, all 6 owners bare EOAs.
- The backlog's open hop ("owner is a proxy, controller unknown") is resolved: the
  Safe controls both factory ownership and upgrades of the wrapper.
- Context found: the same Safe address exists on Ethereum, Arbitrum, Base and BSC as a
  **3-of-7** with the same 6 owners plus `0xC1273815A5a9f8be595170F697734e3f0b8fc07d`.
  So this is PancakeSwap's own cross-chain ops Safe; the Robinhood copy has one owner
  fewer (same threshold). Not an unknown key.
- Scores: 65 / 60 / 0 -> composite 44. crossExposure: verified, no shared signer -> 100.

## 2. SushiSwap V3 Factory -- 31/100

- Target: `0xE51960f1B45f1C9FB6D166E6a884F866fC70433B` (sushi-labs/sushi
  `src/evm/config/features/sushiswap-v3.ts` ROBINHOOD entry, DefiLlama dimension-adapters).
- `Factory.owner()` -> `0xefbcE7A940274e58Cbce5EBCD0D11014048f5239`, a 3,956-byte
  non-proxy contract whose bytecode contains `setFactoryOwner`, `enableFeeAmount`,
  `setProtocolFee`, `pendingOwner`/`acceptOwnership`: an Ownable2Step fee-manager wrapper.
- `wrapper.owner()` -> `0x6fA4080b70eed82Cf48570DDE705026905a64657`, Safe v1.4.1,
  **2-of-3**, nonce 10, no modules, no guard, all 3 owners bare EOAs
  (`0xde9B0969...`, `0xb193d7Cb...`, `0xB64Eb68D...`).
- The backlog's open hop is resolved.
- Context searched, none found: neither the Safe nor the wrapper exists at the same
  address on Ethereum, Arbitrum, Base, BSC or Optimism, and no public document naming
  these signers was found. Blast radius is limited: factory and pools are immutable,
  so this Safe controls fee tiers, protocol fees and factory ownership, not custody.
- Scores: 50 / 35 / 0 -> composite 31. crossExposure: verified, no shared signer -> 100.

## 3. Symbiosis Portal -- 43/100

- Target: `0x292fC50e4eB66C3f6514b9E402dBc25961824D62` (DefiLlama-Adapters
  `symbiosis-finance/config.js` robinhood block; bytecode identical to the Optimism
  Portal at the same address; still absent from Symbiosis' own js-sdk, disclosed).
- TransparentUpgradeableProxy: admin slot -> ProxyAdmin
  `0x1dA522b35363C1eDA4833Bc121C8f3c67b2Caa75`, implementation
  `0xf39D9a9AbB98593cEAc395D7A37c572dA48fCfD5` (Pausable/Ownable).
- `ProxyAdmin.owner()` and `Portal.owner()` both -> `0x0605963420C4E8566fCEf2Cf65Dcd575662Bf53d`,
  Safe v1.4.1, **3-of-5**, nonce 4, no modules, no guard, all owners bare EOAs.
  The backlog noted "threshold not read yet": now read.
- One Safe controls upgrades AND pause/business logic of the contract holding locked
  cross-chain assets. The scorer re-reads both hops every run and warns if they diverge.
- Context: this Safe was not found at the same address on Ethereum/Arbitrum/Base/BSC/Optimism.
- Scores: 65 / 55 / 0 -> composite 43. crossExposure: verified, no shared signer -> 100.

## 4. STRATO Bridge depositRouter (Robinhood side) -- 29/100

- Target: `0x0dc846db6a4ec7b5a3e542f7db88049e9add2541` (STRATO's own Cirrus API
  `BlockApps-MercataBridge-chains`, key 4663 enabled; DefiLlama `strato-bridge` reads the
  same API). **Not** Robinhood's canonical bridge.
- 170-byte proxy, implementation `0x3E487139b6e5e7B22350b04D01a8157952e6498F`, no admin
  slot. The implementation contains `upgradeToAndCall`, `proxiableUUID`,
  `UPGRADE_INTERFACE_VERSION`, `owner`, `pause`: UUPS, upgraded by its owner.
  The backlog's open hop ("upgrade controlled outside the proxy, via the factory") is
  resolved differently: upgrade is gated by `owner()` inside the implementation.
- `depositRouter.owner()` -> `0x8c458F866e603335ef179A63a2528F357732f5d5`, which **is the
  custody Safe itself**: Safe v1.4.1, **2-of-3**, nonce 5, no modules, no guard.
- Aggravating context found: the identical Safe (same 3 owners, same 2-of-3) also exists
  at the same address on Ethereum and Base, consistent with the backlog's note that custody
  is reused across STRATO's source chains. Two keys control custody of bridged funds and
  the upgrade of the deposit path, across several chains.
- Scores: 45 (50 - 5 for shared custody+upgrade) / 35 / 0 -> composite 29.
  crossExposure: verified, no shared signer -> 100.

## Signer overlap (D.3 point 4)

All 17 existing `GROUPS` entries were resolved live and compared against the 17 root
signers of the four new Safes, and the four were compared with each other: **zero shared
signers**. The four new groups were added to `signer_overlap.py`, so their 100 is a
verified value, not the not-applicable default.

## Review of an existing target (D.6): index 0, Morpho Steakhouse USDG vault -- confirmed

Re-derived from scratch on both RPCs: `owner()` = `0xCa50D23F...` (8,609-byte contract)
-> `owner()` = `0x337feFE4...`, bare EOA (nonce 3); `curator()` = 3-of-7 Safe
`0x9023FBD6...`; `isSentinel(0x5642BCd5...)` = true, a 1-of-7 Safe with the same 7
owners; `timelock(setOwner/setCurator/setIsSentinel)` = 0/0/0 (`addAdapter` and
`increaseAbsoluteCap` = 7 days, `setIsAllocator` = 0). Matches the published
10/35/15, composite 19, crossExposure 80 (the curator Safe is shared with the Ethena x
Steakhouse vault). `GROUPS["steakhouse"]` entries still exact. Nothing to change.

## Other corrections in this batch

- **README table row for Morpho NetNet Credit read 8/100; the oracle has served 22 since
  batch 7.** Batch 7 moved this vault onto `score_morpho_vault_generic`, whose documented
  limitation is not treating a 1-of-1 Safe as EOA-equivalent (22 vs 8 by hand). The table
  was never updated. Row corrected to the on-chain value, with the reason stated. Whether
  the generic scorer should special-case 1-of-1 Safes (which would bring it back to ~8)
  is left as an open question, not changed silently here.
- **Curve controller `0xabc336d4...`**: second-RPC cross-check done (identical on
  drpc). The address has nonce 0 on Robinhood Chain but 287 transactions on Arbitrum
  and no code anywhere checked: a real, actively-used EOA key, dormant on this chain.
  Score unchanged (1/100); scorer note and README caveat updated.

## Running total

42 targets (up from 38). All 38 pre-existing composites re-derived unchanged in the dry-run.

## On-chain confirmation

Pushed in one `updateScores()` transaction on Robinhood Chain Testnet (chain 46630):
`0x6147bf6bddb12fe42b6f8e03d5daf72221a17b1c21ad40649968f0850566bb04`, block 120,425,411,
status success. Independently re-read afterwards (separate calls, not the push script's
output): `trackedTargetsCount()` = 42; `getScore()` for indexes 38-41 returns
65/60/0/100/100/44, 50/35/0/100/100/31, 65/55/0/100/100/43, 45/35/0/100/100/29
(admin/multisig/timelock/oracleAuthority/crossExposure/composite), matching the table above.

## Falsification

Any of these would falsify a batch-9 score: a Safe's `getThreshold()`/`getOwners()`
changing, a module or guard appearing on any of the 4 Safes, `Portal.owner()` diverging
from `ProxyAdmin.owner()`, `depositRouter.owner()` no longer being the custody Safe, or a
timelock being inserted anywhere in these chains.
