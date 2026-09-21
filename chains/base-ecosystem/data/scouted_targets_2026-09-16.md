# Base Ecosystem -- scouted targets, 2026-09-16 (scouting phase, run 1)

Phase: scouting, Base mainnet (chain 8453), read-only. First research pass for this
ecosystem -- no prior candidate backlog to draw from. Reuses the exact methodology
already used for Robinhood Chain and Ethereum L1 (`scripts/lib/scorers.py`,
`web3_utils.py`): live `eth_call` against two independent public RPCs, address sourced
from the protocol's own official docs or GitHub repo, TVL from DefiLlama, authority
traced to its root (owner/AccessControl/Safe getOwners+getThreshold/TimelockController
delay), EIP-1967 proxy slots checked where relevant.

RPCs used for every call below, cross-checked for byte-identical results on both:
`https://mainnet.base.org` (block ~51,394,888) and `https://base-rpc.publicnode.com`
(block ~51,394,889-51,394,890). Both are confirmed in `scripts/update_scores.py`-style
public-RPC conventions used elsewhere in this repo (no archive/paid tier needed for any
call in this run -- all reads are current-state `eth_call`/`eth_getStorageAt`).

No new git commit made -- per run instructions the orchestrator commits after
garde-fous. Nothing outside `chains/base-ecosystem/` was touched.

## 1. Morpho Blue (singleton) -- fully verified, largest target found on Base

- **Target**: `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` (the Morpho Blue core
  singleton -- one immutable contract holding every market on the chain).
- **Source of address**: official `morpho-org/morpho-blue-deployment` GitHub repo,
  `broadcast/DeployMorpho.sol/8453/run-latest.json` -- the actual CREATE2 deployment
  transaction receipt for chain 8453, not a docs page transcription.
- **TVL**: $3,904,486,744.74 on Base (DefiLlama `api.llama.fi/protocol/morpho-blue`,
  `currentChainTvls.Base`, read live this run) -- by far the largest single contract
  by value found in this pass, ~4x the next-largest target below.
- **Authority chain, traced live**:
  1. `MorphoBlue.owner()` -> `0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa` (171-byte
     contract).
  2. Confirmed a real Gnosis Safe: `getOwners()` returns 9 addresses, `getThreshold()`
     = 5 -> a **5-of-9** Safe, no further hop (Morpho Blue's `owner()` can only set
     protocol fees and enable IRMs/LLTVs for new markets -- it cannot touch existing
     markets' funds directly, by the immutable-core design documented in Morpho's own
     README).
- **Verification commands** (re-run against either RPC):
  ```
  cast call 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb "owner()(address)" --rpc-url https://mainnet.base.org
  cast call 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb "owner()(address)" --rpc-url https://base-rpc.publicnode.com
  cast call 0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa "getOwners()(address[])" --rpc-url https://mainnet.base.org
  cast call 0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa "getThreshold()(uint256)" --rpc-url https://mainnet.base.org
  ```

## 2. Aave V3 Base (PoolAddressesProvider) -- fully verified root, executor delay open

- **Target**: `0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D` (Aave V3 Base
  `PoolAddressesProvider`).
- **Source of address**: official `bgd-labs/aave-address-book` GitHub repo,
  `src/AaveV3Base.sol` on `main`, `POOL_ADDRESSES_PROVIDER` constant.
- **TVL**: $500,790,366.71 on Base (DefiLlama `api.llama.fi/protocol/aave-v3`,
  `currentChainTvls.Base`, read live this run).
- **Authority chain, traced live**:
  1. `PoolAddressesProvider.owner()` -> `0x9390B1735def18560c509E2d0bc090E9d6BA257a`
     (also returned by `getACLAdmin()`, same value) -- confirmed via
     `bgd-labs/aave-address-book`'s `src/GovernanceV3Base.sol` to be the exact
     `EXECUTOR_LVL_1` constant (Aave Governance V3's short-timelock local executor
     on Base), not a random address.
  2. `EXECUTOR_LVL_1.owner()` -> `0x2DC219E716793fb4b21548C0f009Ba3Af753ab01` --
     confirmed via the same address-book file to be `PAYLOADS_CONTROLLER`
     (`IPayloadsControllerCore`).
  3. `PayloadsController.owner()` -> back to `EXECUTOR_LVL_1`. This is a genuine,
     by-design mutual reference between the two contracts (not a bug or a loop that
     hides the real authority): standard BGD Labs Aave Governance V3 cross-chain
     infra -- Ethereum-mainnet Aave DAO votes approve a "payload", the
     `CROSS_CHAIN_CONTROLLER` (`0x529467C76f234F2bD359d7ecF7c660A2846b04e2` per the
     same address-book file, not separately called live this run) relays it to the
     `PayloadsController` on Base, which then triggers `EXECUTOR_LVL_1` to execute
     against the Pool.
- **Open thread, disclosed rather than guessed**: the L1 Aave Governance DAO itself
  (proposal counts, quorum, the mainnet Timelock/Executor chain) was not re-verified
  live from Base this run -- this pass confirms the Base-side executor/payloads-
  controller pair matches the official address book exactly, not the L1 root. Left
  open for a cross-chain-specific scorer, same discipline as the Ethereum-L1 scouting
  file's Aave entry (its own `EXECUTOR_LVL_1` delay getter was also left open there).
- **Verification commands**:
  ```
  cast call 0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D "owner()(address)" --rpc-url https://mainnet.base.org
  cast call 0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D "getACLAdmin()(address)" --rpc-url https://mainnet.base.org
  cast call 0x9390B1735def18560c509E2d0bc090E9d6BA257a "owner()(address)" --rpc-url https://mainnet.base.org
  cast call 0x2DC219E716793fb4b21548C0f009Ba3Af753ab01 "owner()(address)" --rpc-url https://mainnet.base.org
  ```

## 3. Aerodrome Finance PoolFactory -- fully verified, Base-native

- **Target**: `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` (Aerodrome `PoolFactory`,
  creates every classic-AMM pool).
- **Source of address**: official `aerodrome-finance/contracts` GitHub repo, `README.md`
  on `main`, Base mainnet deployment addresses table (also cross-referenced: the
  README's `Voter` row, `0x16613524e02ad97eDfeF371bC883F2F5d6C480A5`, matches
  `PoolFactory.voter()` read live below).
- **TVL**: $322,731,495 on Base (DefiLlama `api.llama.fi/protocol/aerodrome`,
  `currentChainTvls.Base`, read live this run) -- the largest Base-native (not
  multichain-ported) protocol found this pass.
- **Authority chain, traced live**:
  1. `PoolFactory.owner()` reverts -- this factory has no single `owner()`. Instead it
     exposes `pauser()` and `feeManager()` separately (both read live, same value):
     `0xE6A41fE61E7a1996B59d508661e3f524d6A32075` (171-byte contract).
  2. Confirmed a real Gnosis Safe: `getOwners()` returns 7 addresses, `getThreshold()`
     = 3 -> a **3-of-7** Safe. This Safe can pause all pools and change protocol fees,
     but cannot create/destroy pools or redirect emissions (that is `Voter`'s job,
     `0x16613524e02ad97eDfeF371bC883F2F5d6C480A5`, not separately traced this pass --
     flagged as an open second authority root for `scoring_build` to pick up, since
     Voter governs AERO emissions which is arguably the higher-value lever here).
- **Verification commands**:
  ```
  cast call 0x420DD381b31aEf6683db6B902084cB0FFECe40Da "pauser()(address)" --rpc-url https://mainnet.base.org
  cast call 0x420DD381b31aEf6683db6B902084cB0FFECe40Da "feeManager()(address)" --rpc-url https://mainnet.base.org
  cast call 0x420DD381b31aEf6683db6B902084cB0FFECe40Da "voter()(address)" --rpc-url https://mainnet.base.org
  cast call 0xE6A41fE61E7a1996B59d508661e3f524d6A32075 "getOwners()(address[])" --rpc-url https://mainnet.base.org
  cast call 0xE6A41fE61E7a1996B59d508661e3f524d6A32075 "getThreshold()(uint256)" --rpc-url https://mainnet.base.org
  ```

## 4. Uniswap V3 Factory (Base) -- fully verified, genuine L1-governance forwarder

- **Target**: `0x33128a8fC17869897dcE68Ed026d694621f6FDfD` (UniswapV3Factory, Base).
- **Source of address**: official `docs.uniswap.org` Base Deployments reference page
  (`/contracts/v3/reference/deployments/base-deployments`), which links each address to
  the exact `Uniswap/uniswap-v3-core` GitHub contract source.
- **TVL**: $271,048,197.48 on Base (DefiLlama `api.llama.fi/protocol/uniswap-v3`,
  `currentChainTvls.Base`, read live this run).
- **Authority chain, traced live -- more directly verifiable than the Robinhood/
  Arbitrum sibling case**:
  1. `Factory.owner()` -> `0xaBEA76658b205696d49B5F91b2a03536cB8A3bE1` (7,266-byte
     contract, exposes `enableFeeAmount` itself -- a fee-tier adapter/wrapper, same
     shape as the Arbitrum and Ethereum-L1 cases already in this repo).
  2. `adapter.owner()` -> `0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9` (1,419-byte
     contract). Its own getters (`owner`, `getMinDelay`, `admin`, `l1Timelock`) all
     revert -- but its raw storage does not need guessing: `slot 0` =
     `0x4200000000000000000000000000000000000007`, the canonical OP-stack
     `L2CrossDomainMessenger` predeploy address on every OP-stack chain including
     Base; `slot 1` = `0x1a9C8182C09F50c8318d769245bEA52c32BE35BC`.
  3. `0x1a9C8182C09F50c8318d769245bEA52c32BE35BC` is the SAME address the
     Robinhood-chain `scorers.py` correction note (2026-09-16) already identified, and
     the Ethereum-L1 scouting file (this run) already confirmed directly on mainnet as
     **Uniswap's real Governance Timelock** (`delay()` = 172,800s / 2 days,
     `admin()` -> Uniswap's real GovernorBravo). This Base contract's bytecode
     explicitly checks (`require`) that any incoming call's `msg.sender` is the
     `L2CrossDomainMessenger` AND that the messenger's `xDomainMessageSender()`
     equals this stored L1 address -- an explicit, readable authorization check, not
     an address-derived alias that has to be reverse-computed. Same root DAO as the
     Arbitrum/Ethereum-L1 cases, reached by a different (arguably more transparent)
     mechanism on OP-stack chains.
- **Verification commands**:
  ```
  cast call 0x33128a8fC17869897dcE68Ed026d694621f6FDfD "owner()(address)" --rpc-url https://mainnet.base.org
  cast call 0xaBEA76658b205696d49B5F91b2a03536cB8A3bE1 "owner()(address)" --rpc-url https://mainnet.base.org
  cast storage 0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9 0 --rpc-url https://mainnet.base.org
  cast storage 0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9 1 --rpc-url https://mainnet.base.org
  cast storage 0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9 0 --rpc-url https://base-rpc.publicnode.com
  cast storage 0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9 1 --rpc-url https://base-rpc.publicnode.com
  ```

## 5. Compound V3 (Comet, USDC market on Base) -- fully verified, cross-chain governor

- **Target**: `0xb125E6687d4313864e53df431d5425969c15Eb2F` (Comet, Base USDC market).
- **Source of address**: official `compound-finance/comet` GitHub repo,
  `deployments/base/usdc/roots.json` on `main`.
- **TVL**: $24,907,860.32 on Base (DefiLlama `api.llama.fi/protocol/compound-v3`,
  `currentChainTvls.Base`, read live this run).
- **Authority chain, traced live**:
  1. `Comet.governor()` -> `0xCC3E7c85Bb0EE4f09380e041fee95a0caeDD4a02` (3,480-byte
     contract, Compound's `LocalTimelock`). Also confirmed as the `owner()` of the
     Comet/Configurator proxies' shared `ProxyAdmin`
     (`0xbde8f31d2ddda895264e27dd990fab3dc87b372d`, read from the EIP-1967 admin slot
     of both proxies -- both proxies share one admin).
  2. `LocalTimelock.admin()` -> `0x18281dfC4d00905DA1aaA6731414EABa843c468A` -- this
     matches the `bridgeReceiver` field in the official `roots.json` exactly.
  3. `BaseBridgeReceiver.govTimelock()` -> `0x6d903f6003cca6255D85CcA4D3B5E5146dC33925`
     -- this is Compound's well-known Ethereum-mainnet Governance Timelock address.
     `BaseBridgeReceiver.localTimelock()` -> `0xCC3E7c85...` confirms the loop closes
     correctly (bridge receiver points back at the same LocalTimelock that is
     Comet's governor).
- **Conclusion**: genuine Compound mainnet-governance -> OP-stack cross-domain
  message -> BaseBridgeReceiver -> LocalTimelock -> Comet chain, fully closed and
  internally consistent, not left open.
- **Verification commands**:
  ```
  cast call 0xb125E6687d4313864e53df431d5425969c15Eb2F "governor()(address)" --rpc-url https://mainnet.base.org
  cast storage 0xb125E6687d4313864e53df431d5425969c15Eb2F 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103 --rpc-url https://mainnet.base.org
  cast call 0xCC3E7c85Bb0EE4f09380e041fee95a0caeDD4a02 "admin()(address)" --rpc-url https://mainnet.base.org
  cast call 0x18281dfC4d00905DA1aaA6731414EABa843c468A "govTimelock()(address)" --rpc-url https://mainnet.base.org
  cast call 0x18281dfC4d00905DA1aaA6731414EABa843c468A "localTimelock()(address)" --rpc-url https://mainnet.base.org
  ```

## Not pursued this run

Budget was 5 max; stopped at exactly 5. Moonwell (native Base+Optimism lending,
~$23.2M TVL on Base per DefiLlama `protocol/moonwell`) and Seamless Protocol
(~$0.6M TVL on Base per DefiLlama `protocol/seamless-protocol` -- its docs page now
mostly lists newer Morpho-vault products, the original Aave-v3-fork
`PoolAddressesProvider` at `0x0E02EB705be325407707662C6f6d3466E939f3a0`, sourced from
`seamless-protocol/lending-deployment`'s `script/Constants.sol`, was found but not
verified live since its TVL looks stale/superseded) were both scouted but dropped in
favor of the 5 above, which cover more value and a wider spread of authority patterns
(plain Safe, Aave Governance V3 cross-chain infra, Base-native pauser Safe, OP-stack
L1-governance forwarder, Compound cross-domain LocalTimelock). Left as open candidates
for a future scouting pass rather than scored on unverified/likely-stale addresses.

## Summary table

| Protocol | Address | Address source | TVL (Base) | TVL source | Authority pattern found |
|---|---|---|---|---|---|
| Morpho Blue | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | morpho-org/morpho-blue-deployment GitHub (deploy receipt) | $3,904,486,744.74 | DefiLlama `protocol/morpho-blue` | owner = 5-of-9 Gnosis Safe, one hop, fully closed |
| Aave V3 Base | `0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D` | bgd-labs/aave-address-book GitHub | $500,790,366.71 | DefiLlama `protocol/aave-v3` | PoolAddressesProvider -> EXECUTOR_LVL_1 <-> PAYLOADS_CONTROLLER (Aave Governance V3 cross-chain infra, matches address book exactly); L1 DAO root not re-verified this pass |
| Aerodrome Finance | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` | aerodrome-finance/contracts GitHub README | $322,731,495 | DefiLlama `protocol/aerodrome` | no owner(); pauser=feeManager = 3-of-7 Gnosis Safe; Voter (emissions) not yet traced -- open |
| Uniswap V3 Factory | `0x33128a8fC17869897dcE68Ed026d694621f6FDfD` | docs.uniswap.org Base Deployments | $271,048,197.48 | DefiLlama `protocol/uniswap-v3` | Factory -> fee-adapter -> explicit L2CrossDomainMessenger-gated forwarder naming Uniswap's real L1 Governance Timelock as L1Owner (storage-verified on both RPCs) |
| Compound V3 (Comet, USDC) | `0xb125E6687d4313864e53df431d5425969c15Eb2F` | compound-finance/comet GitHub `roots.json` | $24,907,860.32 | DefiLlama `protocol/compound-v3` | Comet.governor() = LocalTimelock -> admin = BaseBridgeReceiver -> govTimelock = Compound's real Ethereum-mainnet Timelock; loop closes correctly |
