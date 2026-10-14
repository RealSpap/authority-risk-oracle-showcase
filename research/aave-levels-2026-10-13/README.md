# Aave V3 Ethereum Core: level 0-5 of every role read on chain (2026-10-13)

**Summary.** The Technical Asset Listing Framework adopted by Aave governance (July 2026) classes each privileged role of a listed asset from level 0 (single key, no delay) to level 5 (on-chain DAO governance with timelock); levels 0 and 1 are "weak". This folder reads those roles on chain for 25 of the 67 reserves of Aave V3 Core (Ethereum), plus BTC.b and USDe, at block 26,184,127, with a negative witness on every call. Read this way, five listed assets are at level 0 or 1: USDC and cbETH (single keys), USDT (MultiSigWallet 3 of 6), BTC.b (a single key, second pauser a Safe 2 of 11), USDe (single keys inside its minter contract; level 1 without it). Several assets expose no role through standard getters and six route their power through Aragon, the Vat or a registry: they are left unclassified, not called safe. Not read: 40 reserves, Aragon ACLs, the RolesAuthority of PAXGy, the freeze status of reserves. Rerun: `python3 mesure-aave-niveaux.py --block 26184127 --compact` (standard library, public RPC).

**Status.** 27 of the 67 Core reserves are read here (the first 25 in list order, plus BTC.b and USDe) at block 26,184,127; the other 40 are not read yet.

**Rendered page:** https://realspap.github.io/oracle/research/aave-levels/

---

**Frozen block: 26184127 (0x18f89bf)**, read with `eth_blockNumber` on Tenderly on 2026-10-13 around 14:20 UTC. Every call (`eth_call`, `eth_getStorageAt`, `eth_getCode`, `eth_getLogs` up to that block) carries this block.
Read-only measurement: no key, no transaction. Script: `mesure-aave-niveaux.py` (in this folder, standard library only).
Volume of the final pass: 1,248 `eth_call`, 290 `eth_getStorageAt`, 135 `eth_getCode`, 70 `eth_getLogs`. **NOT READ: 0.**

## What was read

- Core Pool `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2`, `getReservesList()`: **67 reserves**. The **first 25** in list order are measured. That order is the order of listing: the first 25 are mostly the historical assets (WETH to KNC). The frozen or active status of each reserve was not read.
- In addition, flagged as such in the table: **BTC.b** (reserve no. 63) and **USDe** (no. 30), listed on Core but outside the first 25, and **USAT** and **PAXGy**, not listed on Core, measured as method witnesses because they have a LlamaRisk sheet on Ethereum written under the framework.
- For each token: EIP-1967 slots (implementation, admin, beacon), ZeppelinOS slots (admin, implementation), getters `owner()`, `admin()`, `minter()`, `controller()`, `authority()`, `masterMinter()`, `pauser()`, `blacklister()`, `guardian()`, `RISK_COUNCIL()`. For AccessControl: every `RoleGranted` event of the contract (block 0 to the frozen block), then `hasRole(role, account)` at the frozen block to keep current holders only, cross-checked with `getRoleMemberCount` when the contract exposes it (no mismatch). For Maker-style tokens: `wards` through `Rely` and `LogNote rely` events. For FiatTokens (USDC, cbETH): besides the named roles, the minters through `MinterConfigured` then `isMinter()`.
- For each holder: `eth_getCode` (empty = EOA; prefix `0xef0100` = EOA delegated by EIP-7702, none met), `getThreshold()`/`getOwners()` (Safe) or `required()`/`getOwners()` (legacy MultiSigWallet, the one Tether uses), `getModulesPaginated` (no measured Safe has a module), `getMinDelay()` (OpenZeppelin TimelockController, then its PROPOSER, EXECUTOR and admin roles through `RoleGranted`), `delay()` + `admin()`/`owner()`/`authority()` (Compound Timelock or DSPause), `votingPeriod()` (Governor), `hat()` (DSChief), `kernel()` (Aragon app). A contract that is none of these is followed one step up through its own controllers, up to 5 steps.

## Classification rules applied (read before quoting a number)

- 0 = EOA; 1 = multisig whose threshold s satisfies s ≤ n/2; 2 = multisig with s > n/2 and no delay; 3 = a 2 behind a timelock < 48 h; 4 = same with ≥ 48 h; 5 = on-chain DAO with a timelock.
- An Aave Executor (lvl1 `0x5300…192a`, lvl2 `0x17Dd…6957`) counts as 5 only if its `owner()` read at the block is the PayloadsController `0xdAba…aEc5` (checked for both). A Governor that holds a role with no timelock in front is "outside the grid" (no case met: the two Governors seen, UNI and ENS, sit behind a 48 h timelock).
- Timelock: every proposer and every admin of the timelock is classified. If the EXECUTOR role is restricted, a proposer only goes through with an executor, so the higher of the two levels is taken (the weakest counting executor). An EOA or a minority multisig behind a timelock **keeps its level 0 or 1**: the grid does not cover this case, and I chose the conservative reading.
- Asset level = the lowest of all roles read. "unclassified" = at least one holder whose mechanism cannot be derived by these reads (Aragon, registry, contract with no readable controller): it is neither a 0 nor a 5.
- `0x0` = renounced or empty role (MKR `owner()`, 1INCH `owner()`), not a holder.

## Table (output of the script's `--compact` mode: holders of the same role and type are grouped)

| asset | address | proxy? | role | holder | type | level | asset level |
|---|---|---|---|---|---|---|---|
| WETH | 0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2 | no | - | - | no privileged role read by the standard reads | - | no role read |
| wstETH | 0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0 | no | - | - | no privileged role read by the standard reads | - | no role read |
| WBTC | 0x2260fac5e5542a773aa44fbcfedf7c193bc2c599 | no | owner() | 0xca06..beb7 | contract <- owner() 0x972e..70de MultiSigWallet 6/10 | 2 | 2 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | proxy admin (zosAdmin) | 0x807a..95d2 | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | owner() | 0xfcb1..ae3a | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | masterMinter() | 0xe982..de17 | contract <- owner() 0xc1d9..c704 EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | pauser() | 0x4914..8566 | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | blacklister() | 0x0a06..78f9 | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 27 holders | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0x2222..c205 | contract <- owner() 0x3c54..aab6 EOA ; pauser() 0x6fa3..e6fb EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0x7777..00ee | contract <- owner() 0x2a6a..58c5 EOA ; pauser() 0x9812..5b19 EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0xa669..48bd | contract <- owner() 0x162a..31b5 EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0xc492..e907 | contract <- owner() 0x0143..8dc8 EOA ; pauser() 0x817a..a09f EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0xfd78..d002 | contract <- owner() 0x7d15..ae0e EOA ; pauser() 0x4e89..ac69 EOA | 0 | 0 |
| DAI | 0x6b175474e89094c44da98b954eedeac495271d0f | no | wards (rely) | 0x9759..1a28 | contract with no controller read (immutable or registry not read) | ? | unclassified |
| LINK | 0x514910771af9ca656af840dff83e8264ecf986ca | no | - | - | no privileged role read by the standard reads | - | no role read |
| AAVE | 0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9 | yes (admin1967,impl1967) | proxy admin (admin1967) | 0x86c3..b517 | contract <- owner() 0x17dd..6957 DAO Aave Executor lvl2 (owner = PayloadsController) | 5 | 5 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | proxy admin (zosAdmin) | 0xeee4..9577 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | owner() | 0x4b87..ea03 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | admin() | 0xeee4..9577 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | masterMinter() | 0x7dd4..b77a | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | pauser() | 0x9596..dcc2 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | blacklister() | 0xbe3c..eb0a | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0x6d44..8280 | contract <- owner() 0x4cd6..bbe5 EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | yes (zosAdmin,zosImpl) | minter (FiatToken) | 0x9bf9..a372 | EOA | 0 | 0 |
| USDT | 0xdac17f958d2ee523a2206206994597c13d831ec7 | no | owner() | 0xc6cd..a828 | MultiSigWallet 3/6 | 1 | 1 |
| rETH | 0xae78736cd615f374d3085123a210448e74fc6393 | no | - | - | no privileged role read by the standard reads | - | no role read |
| LUSD | 0x5f98805a4e8be255a32880fdec7f6728c6568ba0 | no | - | - | no privileged role read by the standard reads | - | no role read |
| CRV | 0xd533a949740bb3306d119cc777fa900ba034cd52 | no | admin() | 0x4090..9968 | Aragon app (kernel 0xad06..d72d), ACL not derived | ? | unclassified |
| CRV | 0xd533a949740bb3306d119cc777fa900ba034cd52 | no | minter() | 0xd061..fce0 | contract <- controller() 0x2f50..46bb (contract, level ?) [partly unclassified] | ? | unclassified |
| MKR | 0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2 | no | owner() = 0x0 (renounced or empty) | 0x0 | no holder | ? | unclassified |
| MKR | 0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2 | no | authority() | 0x6eeb..dfb8 | contract with no controller read (immutable or registry not read) | ? | unclassified |
| SNX | 0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f | no | owner() | 0xeb31..7769 | Safe 4/7 | 2 | 2 |
| BAL | 0xba100000625a3754423978a60c9317c58a424e3d | no | MINTER_ROLE | 0xf302..414f | contract with no controller read (immutable or registry not read) | ? | unclassified |
| BAL | 0xba100000625a3754423978a60c9317c58a424e3d | no | SNAPSHOT_ROLE | 0xf302..414f | contract with no controller read (immutable or registry not read) | ? | unclassified |
| UNI | 0x1f9840a85d5af5bf1d1762f925bdaddc4201f984 | no | minter() | 0x1a9c..35bc | Timelock delay() 172800 s (48 h) <- admin() 0x408e..24c3 DAO Governor (votingPeriod 40320) | 5 | 5 |
| LDO | 0x5a98fcbea516cf06857215779fd812ca3bef1b32 | no | controller() | 0xf73a..3249 | Aragon app (kernel 0xb8ff..88dc), ACL not derived | ? | unclassified |
| ENS | 0xc18360217d8f7ab5e7c516566761ea12ce7f9d72 | no | owner() | 0xfe89..44b7 | TimelockController 172800 s (48 h) <- PROPOSER 0x323a..b7e3 DAO Governor (votingPeriod 45818) ; PROPOSER 0x2acb..e051 (contract, level 2) ; open executor | 4 | 4 |
| 1INCH | 0x111111111117dc0aa78b770fa6a738034120c302 | no | owner() = 0x0 (renounced or empty) | 0x0 | no holder | ? | no role read |
| FRAX | 0x853d955acef822db058eb8505911ed77f175b99e | no | COLLATERAL_RATIO_PAUSER | 0x8412..39ca | Timelock delay() 172800 s (48 h) <- admin() 0xb174..3f27 Safe 3/5 | 4 | 2 |
| FRAX | 0x853d955acef822db058eb8505911ed77f175b99e | no | DEFAULT_ADMIN_ROLE | 0xb174..3f27 | Safe 3/5 | 2 | 2 |
| FRAX | 0x853d955acef822db058eb8505911ed77f175b99e | no | COLLATERAL_RATIO_PAUSER | 0xb174..3f27 | Safe 3/5 | 2 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | no | DEFAULT_ADMIN_ROLE | 0x5300..192a | DAO Aave Executor lvl1 (owner = PayloadsController) | 5 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | no | FACILITATOR_MANAGER_ROLE | 0x5300..192a | DAO Aave Executor lvl1 (owner = PayloadsController) | 5 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | no | BUCKET_MANAGER_ROLE | 0x5300..192a | DAO Aave Executor lvl1 (owner = PayloadsController) | 5 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | no | BUCKET_MANAGER_ROLE | 0x46aa..5409 | contract <- RISK_COUNCIL() 0x8513..4b60 Safe 2/3 ; owner() 0x5300..192a DAO Aave Executor lvl1 (owner = PayloadsController) | 2 | 2 |
| RPL | 0xd33526068d116ce69f19a9ee46f0bd304f21a51f | no | - | - | no privileged role read by the standard reads | - | no role read |
| sDAI | 0x83f20f44975d03b1b09e64809b757c47f942beea | no | - | - | no privileged role read by the standard reads | - | no role read |
| STG | 0xaf5191b0de278c7286d6c7cc6ab6bb8a73ba2cd6 | no | owner() | 0xbe63..5413 | contract with no controller read (immutable or registry not read) | ? | unclassified |
| KNC | 0xdefa4e8a7bcba345f687a2f1456f5edd9ce97202 | yes (admin1967,impl1967) | proxy admin (admin1967) | 0x5001..f559 | contract <- owner() 0x7d4d..d9d9 (contract, level ?) [partly unclassified] | ? | 2 (+ unclassified) |
| KNC | 0xdefa4e8a7bcba345f687a2f1456f5edd9ce97202 | yes (admin1967,impl1967) | owner() | 0x3eb0..f650 | MultiSigWallet 3/5 | 2 | 2 (+ unclassified) |
| KNC | 0xdefa4e8a7bcba345f687a2f1456f5edd9ce97202 | yes (admin1967,impl1967) | minter() | 0x7d4d..d9d9 | contract with no controller read (immutable or registry not read) | ? | 2 (+ unclassified) |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | proxy admin (admin1967) | 0xcee8..0095 | contract <- owner() 0x055e..7e59 TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | owner() | 0x055e..7e59 | TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | MINTER_ROLE | 0x451c..0a2d | contract <- owner() 0x055e..7e59 TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 ; proxy admin (admin1967) 0x6b06..cbb1 (contract, level 3) | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | MINTER_ROLE | 0x9ece..21ac | contract <- CLAIMER_ROLE 0xcd1b..c01b EOA ; OPERATOR_ROLE 0xcd1b..c01b EOA ; role 0x843c3a00 0x8236..4494 (contract, level 0) ; + 6 other(s) | 0 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | CLAIMER_ROLE | 0xcd1b..c01b | EOA | 0 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | OPERATOR_ROLE | 0xcd1b..c01b | EOA | 0 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | PAUSER_ROLE | 0x251a..4892 | Safe 3/5 | 2 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | DEFAULT_ADMIN_ROLE | 0x055e..7e59 | TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | yes (admin1967,impl1967) | PAUSER_ROLE | 0xad67..fd44 | Safe 2/11 | 1 | 0 |
| USDe | 0x4c9edd5852cd905f086c759e8383e09bff1e68b3 | no | owner() | 0xe8dc..7c94 | TimelockController 86400 s (24 h) <- PROPOSER 0x3b0a..1862 Safe 5/10 ; EXECUTOR 0x3520..0e8f EOA ; 0xa075..c344 Safe 3/6 ; 0x3b0a..1862 Safe 5/10 | 1 | 0 |
| USDe | 0x4c9edd5852cd905f086c759e8383e09bff1e68b3 | no | minter() | 0xe349..62d3 | contract <- GATEKEEPER_ROLE 0xab91..a7dc EOA ; GATEKEEPER_ROLE 0x0f56..5bd9 EOA ; GATEKEEPER_ROLE 0x4960..8996 EOA ; + 44 other(s) | 0 | 0 |
| USAT | 0x07041776f5007aca2a54844f50503a18a72a8b68 | yes (admin1967,impl1967) | proxy admin (admin1967) | 0x3e4c..d9c7 | contract <- owner() 0x62b3..c5cb MultiSigWallet 3/5 | 2 | 2 |
| USAT | 0x07041776f5007aca2a54844f50503a18a72a8b68 | yes (admin1967,impl1967) | owner() | 0x62b3..c5cb | MultiSigWallet 3/5 | 2 | 2 |
| PAXGy | 0x6c6494fd9962eb98b94ffa48f6679058f820700e | no | owner() | 0x0dcc..df08 | TimelockController 86400 s (24 h) <- PROPOSER 0x0000..3f2f Safe 3/5 ; EXECUTOR 0x1d60..9312 EOA ; 0x317e..a024 EOA ; 0xfbf7..1a5e EOA ; + 3 other(s) | 3 | 3 |
| PAXGy | 0x6c6494fd9962eb98b94ffa48f6679058f820700e | no | authority() | 0xc444..99dd | contract <- owner() 0x0dcc..df08 TimelockController 86400 s (24 h) <- PROPOSER 0x0000..3f2f Safe 3/5 ; EXECUTOR 0x1d60..9312 EOA ; 0x317e..a024 EOA ; 0xfbf7..1a5e EOA ; + 3 other(s) | 3 | 3 |

## Level per asset

| asset | origin | level | what sets the level |
|---|---|---|---|
| WETH | reserve 0 | no role read | no getter, no proxy slot |
| wstETH | reserve 1 | no role read | same |
| WBTC | reserve 2 | 2 | owner = Controller contract, whose owner is a MultiSigWallet 6/10 |
| USDC | reserve 3 | **0** | proxy admin, owner, pauser, blacklister: EOAs; masterMinter = contract whose owner is an EOA; 32 minters, 27 of them EOAs |
| DAI | reserve 4 | unclassified | sole ward = DaiJoin `0x9759…1a28`, with no readable controller (the power goes through the Maker Vat, not read) |
| LINK | reserve 5 | no role read | |
| AAVE | reserve 6 | 5 | proxy admin = ProxyAdmin whose owner is the Executor lvl2 |
| cbETH | reserve 7 | **0** | proxy admin, owner, masterMinter, pauser, blacklister: EOAs |
| USDT | reserve 8 | **1** | owner = MultiSigWallet 3/6 (3 of 6 is not a majority) |
| rETH | reserve 9 | no role read | Rocket Pool power sits in RocketStorage, not read by these getters |
| LUSD | reserve 10 | no role read | |
| CRV | reserve 11 | unclassified | admin = Aragon agent (`kernel()` readable, ACL not derived) |
| MKR | reserve 12 | unclassified | owner = 0x0; authority `0x6eeb…dfb8` with no readable controller |
| SNX | reserve 13 | 2 | owner = Safe 4/7 |
| BAL | reserve 14 | unclassified | MINTER and SNAPSHOT held by `0xf302…414f`, Balancer authorizer not read |
| UNI | reserve 15 | 5 | minter = 48 h Timelock whose admin is the Uniswap Governor |
| LDO | reserve 16 | unclassified | controller = Aragon app |
| ENS | reserve 17 | 4 (mechanical), 5 after reading the bytecode | see "Differences" below |
| 1INCH | reserve 18 | no role read | owner = 0x0 |
| FRAX | reserve 19 | 2 | DEFAULT_ADMIN and COLLATERAL_RATIO_PAUSER held by a Safe 3/5 with no delay |
| GHO | reserve 20 | 2 | BUCKET_MANAGER also held by the steward `0x46aa…5409`, whose RISK_COUNCIL is a Safe 2/3; the other roles belong to the Executor lvl1 (5) |
| RPL | reserve 21 | no role read | |
| sDAI | reserve 22 | no role read | |
| STG | reserve 23 | unclassified | owner = contract `0xbe63…5413` with no readable controller |
| KNC | reserve 24 | 2 (+ unclassified) | owner = MultiSigWallet 3/5; proxy admin and minter lead to `0x7d4d…d9d9`, unclassified |
| BTC.b | reserve 63, outside the first 25 | **0** | OPERATOR_ROLE and CLAIMER_ROLE held by the EOA `0xcd1b…c01b`; second PAUSER = Safe 2/11 (level 1); upgrade and admin = 24 h timelock (level 3) |
| USDe | reserve 30, outside the first 25 | **0** | `minter()` = contract `0xe349…62d3` whose MINTER_ROLE and GATEKEEPER_ROLE are held by EOAs; owner = 24 h timelock whose sole proposer is a Safe 5/10 (level 1) |
| USAT | not listed, witness | 2 | owner and ProxyAdmin owner = MultiSigWallet 3/5, no delay |
| PAXGy | not listed, witness | 3 | owner and authority owner = 24 h timelock, proposer Safe 3/5 |

## Levels 0 and 1: what the framework would class as "weak security configuration" today

Among the first 25 reserves read:

1. **USDC**: level 0. The proxy admin `0x807a96288a1a408dbc13de2b1d087d10356395d2`, the owner `0xfcb19e6a322b27c06842a71e8c725399f049ae3a`, the pauser `0x4914f61d25e5c567143774b76edbf4d5109a8566` and the blacklister `0x0a06be16275b95a7d2567fbdae118b36c7da78f9` have empty code at the frozen block (re-read with a separate `curl`, outside the script).
2. **cbETH**: level 0, same FiatToken pattern (proxy admin, owner, masterMinter, pauser, blacklister: EOAs).
3. **USDT**: level 1. Owner `0xc6cde7c39eb2f0f0095f41570af89efc2c1ea828`, a MultiSigWallet, `required()` = 3, `getOwners()` = 6 addresses (re-read with `curl`).

Reserves listed outside the first 25 and measured: **BTC.b** (0) and **USDe** (0 through the `minter()` contract; 1 even without it, through the Safe 5/10 that proposes to the timelock).

Reading: a level 0 or 1 only says that a privileged role is held by a single key or by a minority multisig. For USDC and cbETH the custody may be off chain (HSM, procedures): the framework classes the on-chain configuration, and that is what is read here. The framework also states that pause and blacklist may call for faster paths than mint or upgrade; it does not take them out of the grid.

Reserves 25 to 66 (42) were not run, except BTC.b and USDe: 40 remain to be measured with `--limit 67`.

## Differences with the LlamaRisk and Aave Labs sheets

Sheets read on governance.aave.com (Discourse JSON API), all published by LlamaRisk under the framework:

| asset | sheet | what the sheet says | what is read at the block | agreement |
|---|---|---|---|---|
| BTC.b | t/25652 (2026-09-16) | upgrades under LombardTimeLock 1 day, executor Multisig1 3/5; PROPOSER = "EOA 2, Multisig1"; PAUSER = "Multisig1, Multisig2"; OPERATOR and CLAIMER = "EOA 1". Summary: "robust administrative safeguards" | timelock `getMinDelay` = 86,400 s; PROPOSER = EOA `0x3f6b…a079` and Safe 3/5 `0x251a…4892`; EXECUTOR = that Safe alone; PAUSER = that Safe and a Safe **2/11** `0xad67…fd44`; OPERATOR and CLAIMER = EOA `0xcd1b…c01b` | **agreement on the facts**; the sheet does not give the threshold of Multisig2 (2/11, level 1). **Difference in level**: role by role, OPERATOR and CLAIMER as an EOA give 0 and the second pauser gives 1; the sheet's summary does not translate this into a level |
| USAT | t/25832 (2026-10-12) | transparent proxy, ProxyAdmin `0x3e4C…9C7` and owner = legacy MultiSigWallet `0x62b3…c5cb` 3 of 5; no timelock | ProxyAdmin `0x3e4c…d9c7`, owner `0x62b3…c5cb`, MultiSigWallet 3/5, no delay | **agreement** (level 2) |
| PAXGy | t/25831 (2026-10-12) | 24 h TimelockController owns all contracts; Safe 3/5 `0x0000000000417626…3f2F` is sole proposer and canceller; the Safe and its 5 signers can execute; a single operator key holds the freeze role on the role registry | owner `0x0dcc…df08`, 86,400 s, PROPOSER Safe 3/5 `0x0000…3f2f`, EXECUTOR that Safe plus 5 EOAs | **agreement** on the owner chain (level 3). **Not measured**: the RolesAuthority roles (the operator freeze key), which my getters do not read; according to the sheet, that role would be level 0 |
| USDe | no Ethereum sheet found | USDe sheets on Monad (t/25255), Avalanche (t/25669), X Layer (t/25827): other deployments, other administrators | see table | not comparable |
| PAXG | t/25359 | asset not listed on Core, not measured | | |

Manual correction outside the script:

- **ENS**: the script gives 4 because the timelock `0xfe89…44b7` (48 h, execution open to anyone) has two proposers, the ENS Governor `0x323a…b7e3` and the contract `0x2acbf518b3759f6e1fa163294eda55bf1d0ae051` (owner Safe 5/8, `expiration()` = 1847389751). The bytecode of that second contract contains the selectors of `veto(bytes32)` and `cancel(bytes32)`, not those of `schedule`; it can only cancel. Real level: 5. Searching for selectors in bytecode is a heuristic (a selector shifted by via-IR can slip through), hence a correction written separately and not coded.

## Limits (what a green or a number here does not prove)

- Mechanisms outside the standard getters are not read: RolesAuthority (PAXGy), Aragon ACL (CRV, LDO), the Maker Vat (DAI), Balancer authorizer (BAL), RocketStorage (rETH), the WBTC custodian and Factory, GHO facilitators. "no role read" is not "no power".
- USDe: the MINTER_ROLE holders of the `minter()` contract (Ethena's mint contract, name not re-read on chain) submit orders bounded per block; level 0 is mechanical and does not measure those bounds.
- The classification of a timelock (executor rule, conservative reading for an EOA behind a delay) is a reading choice of the grid, written above.
- The frozen or active status of each reserve was not read.
- Adoption of the framework: thread t/24988 announces the move to Snapshot on 2026-07-09; the adoption date (2026-07-13) was given to me and was not re-read at the source.

## Witnesses

- getThreshold() on 0x...dEaD -> ok 0x : as expected
- hasRole(FACILITATOR_MANAGER_ROLE, 0x519a3fedec3659ad4c36e1d11386f1bb68944e77) on GHO -> False : as expected
- keccak256 in pure Python is checked when the script loads, against keccak(""), keccak("PAUSER_ROLE"), `owner()` = 0x8da5cb5b and the topic0 of `RoleGranted`.
- Two full passes of the script at the same block give the same levels for the 29 assets.

## NOT READ

Final pass: **0 calls in error**. Provider errors (Tenderly "rate limit exceeded" code -32005, HTTP 429) were absorbed by the script's retries before any classification.
While building the script: a trial pass had `eth_getCode 0xca06411bd7a7296d7dbdd0050dfc846e95febeb7` (WBTC Controller) NOT READ (HTTP 525 on eth.llamarpc.com); the retry logic was fixed and the call re-read afterwards (contract, owner MultiSigWallet 6/10). A cross-check on a second provider failed: publicnode HTTP 403 and llamarpc HTTP 525 when this report was written; the cross-checks cited above were therefore made with a separate `curl` on Tenderly, not on an independent provider.

## Rerun

```
python3 mesure-aave-niveaux.py --block 26184127 --compact
```

Options: `--limit 67` for all reserves, `--no-extra` without BTC.b, USDe, USAT and PAXGy, `--json out.json` for every row with full addresses. About 5 minutes. Endpoints tried in order: Tenderly, eth.llamarpc.com, ethereum-rpc.publicnode.com; the environment's HTTPS proxy is used if one is set.
