# Arbitrum Ecosystem -- 4 new targets, 2026-09-19 (maintenance run, budget (b))

Budget ceiling was 50 new protocols. 4 were kept: each has real Arbitrum
TVL on DefiLlama (`api.llama.fi/protocols`, `chainTvls.Arbitrum`, pulled
2026-09-19), an address from the protocol's own repo or docs, an authority
chain traced live to its root, a scorer plus unit tests, and a push
confirmed by `getScore()` read-back. None was already in
`chains/arbitrum-ecosystem/` (grepped by address first).

Every composite below matched exactly on 2 independent Arbitrum One RPCs
(`arb1.arbitrum.io/rpc` and `arbitrum-one-rpc.publicnode.com`, via
`scripts/dry_run.py`'s built-in cross-check). Pushed in the same
`updateScores()` tx as the index-0 CORRECTION:
`0xa934822b3ed2959761641e312b4646890243ede3f82648e433fecfea1d57d85b`
(Arbitrum Sepolia block 310,589,900, status 1). They are appended after
indices 0-4, so existing indices keep their meaning (tested). The
read-back of all 9 targets is in `oracle_scores_2026-09-19.csv`.

## Summary

| Idx | Protocol | Address | TVL Arbitrum | adminKey | multisig | timelock | crossExp | composite |
|---|---|---|---|---|---|---|---|---|
| 5 | Compound V3 (Comet USDC) | `0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf` | $73.2M (all Arbitrum markets) | 75 | 100 | 65 | 100 | **80** |
| 6 | Pendle V2 (Router + MarketFactoryV6) | `0x888888888889758F76e7103c6CbF23ABbF58F946` | $147.6M | 65 | 55 | 0 | **60** | **43** |
| 7 | Fluid Liquidity | `0x52Aa899454998Be5b000Ad077a46Bbe360F4e497` | $146.9M (fluid-lending) | 65 | 55 | 55 | **80** | **59** |
| 8 | Uniswap V3 Factory | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | $144.5M | 80 | 100 | 75 | 100 | **85** |

## 5. Compound V3, Comet USDC market

- Source: `compound-finance/comet`, `deployments/arbitrum/usdc/roots.json`
  (comet `0x9c4ec768...`, bridgeReceiver `0x42480C37...`).
- Live chain: `governor()` = LocalTimelock `0x3fB4d38e...F88A` (`delay()` 86,400 s,
  `pendingAdmin()` = 0). EIP-1967 admin slot -> ProxyAdmin `0xD10b40fF...715e`,
  whose `owner()` is the same LocalTimelock (it controls parameters AND
  upgrades). `LocalTimelock.admin()` = bridge receiver `0x42480C37...`
  (matches roots.json). Its `govTimelock()` = `0x6d903f60...3925`, which
  is Compound's L1 Timelock: read on Ethereum mainnet during scouting,
  `delay()` 172,800 s, `admin()` `0x309a862b...C8C0`. Its
  `localTimelock()` closes back to the governor. The Configurator's proxy
  admin is the same ProxyAdmin.
- Disclosed, not scored: `pauseGuardian()` = 5-of-9 Safe `0x78E6317D...1a9d`.
  It can pause without the timelock (pause only). Same treatment as the
  Base sibling.
- Score: same convention as `score_compound_v3_comet_base_usdc` (75/100/65 -> 80).

## 6. Pendle V2

- Source: `pendle-finance/pendle-core-v2-public`, `deployments/42161-core.json`
  (`network.chainId` 42161; governance `0x7877AdFa...`, router, marketFactoryV6
  `0x49F2f700...`, proxyAdmin `0xA28c08f1...`, governanceProxy `0x2aD631F7...`).
- Live chain: all 3 paths converge. `Router.owner()`, MarketFactoryV6's
  ProxyAdmin `owner()`, and `DEFAULT_ADMIN_ROLE` on the governanceProxy
  (UUPS `PendleGovernanceProxy`, Sourcify exact match; `MarketFactoryV6.owner()`
  = governanceProxy) all resolve to one 3-of-5 Safe. No TimelockController
  on any path.
- Full `RoleGranted`/`RoleRevoked` scan of the governanceProxy (13 events,
  genesis to tip): DEFAULT_ADMIN was granted to the deployer `0x1FcCC097...`
  and to the Safe. The deployer's grant was then revoked. GUARDIAN (pause only)
  is currently held by `0xeea6F790...` (Pendle's `hardwareDeployer`),
  `0xd32aca68...`, `0xe397e617...` and `0xe81b3257...`. `0x34e55bf9...` was
  revoked. Disclosed, not scored: the proxy's scoped-access mapping
  (`aggregateWithScopedAccess`) cannot be enumerated with `eth_call`.
- **Cross-ecosystem finding:** the same Safe address with the identical 5
  owners and 3-of-5 threshold is live on Plasma (`rpc.plasma.to`) and on
  Robinhood Chain (`rpc.mainnet.chain.robinhood.com`), read 2026-09-19.
  Both are already tracked Pendle roots (`score_pendle_plasma`,
  `score_pendle_v2`). So `crossExposureScore = 100 - 20*2 = 60`
  (METHODOLOGY.md formula), compared against a dated snapshot in the
  scorer.

## 7. Fluid Liquidity

- Source: `Instadapp/fluid-contracts-public`, `deployments/deployments.md`
  (Liquidity `0x52Aa8994...` arbitrum row; Timelock `0x4d6CE4F4...` arbitrum
  row, constructor `(86400, [0x4F6F977a...], [0x196Ed45e...], 0x0)`).
- Live chain: `getAdmin()` equals the raw EIP-1967 admin slot, which is the
  TimelockController `0x4d6CE4F4...` (`getMinDelay()` 86,400 s). A full
  event scan of the timelock shows exactly 4 grants and no revocation:
  TIMELOCK_ADMIN to itself, PROPOSER + CANCELLER to `0x4F6F977a...`,
  EXECUTOR to `0x196Ed45e...`.
- `0x4F6F977a...` is an **Avocado Multisig** (`DOMAIN_SEPARATOR_NAME()` =
  "Avocado-Multisig"; `signers()` returns 12 signers, `requiredSigners()`
  returns 6). `0x196Ed45e...` is a Safe v1.4.1 (3-of-5). Plasma's sibling
  scorer left this signer set unresolved. It is resolved here, and the
  same 12 signers / 6 required are live on Plasma too, so
  `crossExposureScore = 80`.
- Disclosed immediate path: `LogUpdateAuths` events leave 4 active auths
  (`0x82a2a351...`, `0x71d8B000...`, `0x3C27B24E...`, `0x7C884e49...`). All
  are Fluid config-handler contracts listed in `deployments.md`, and each
  one's `TEAM_MULTISIG()` is the same Avocado multisig. `LogUpdateGuardians`
  leaves 1 guardian, which is the same Avocado multisig. These powers are
  bounded (config and pause), but they skip the delay, so timelockScore is
  capped at 55.
- multisig = the weaker of proposer (6-of-12 -> 100) and executor
  (3-of-5 -> 55) = 55. Same "weakest of the two sets the ceiling"
  convention as `scripts/lib/scorers.py`.

## 8. Uniswap V3 Factory

- Source: `Uniswap/docs`, `content/protocols/v3/deployments/v3-arbitrum-deployments.mdx`
  (UniswapV3Factory `0x1F98431c...`).
- Live chain: `Factory.owner()` = fee adapter `0xFF7aD5dA...0699` (7,266 bytes,
  Sourcify verified). Its `owner()` and `feeSetter()` both equal
  `0x2BAD8182...46CD`, the recomputed Arbitrum L1->L2 alias of Uniswap's L1
  Governance Timelock `0x1a9C8182...35BC`. Same root as the Robinhood Chain
  Uniswap targets (the 2026-09-16 bridge-alias correction). The scorer
  re-reads the L1 Timelock `delay()`/`admin()` and GovernorBravo
  `quorumVotes()` on its own Ethereum w3 and fails closed.
- Score: 80/100/75 -> 85, same convention as the Base sibling and the root
  `_score_uniswap_bridge_alias_root()`.

## Considered, not added (open leads)

- **Hyperliquid Bridge2** (~$599.8M, largest Arbitrum TVL): already scored
  by `chains/hyperliquid/` (`score_bridge2`). Not duplicated here.
- **USD AI** (`usd-ai`, ~$307.2M; USDai `0x0A1a1A10...`, per DefiLlama-Adapters
  `projects/usdai/index.js`): the upgrade path is solid. EIP-1967 ProxyAdmin
  -> TimelockController `0x0EEA1EE0...` with a 172,800 s delay; proposer
  and executor are 3-of-3 Safes sharing the same 3 signers. The token's
  `DEFAULT_ADMIN_ROLE` sits directly on a 3-of-3 Safe (blacklist/pause
  roles, no delay). **But** `mint()`/`burn()` are gated by an immutable
  `_bridgeAdapter` that has no public getter, and its own authority was
  not traced. The minting authority of a stablecoin is not resolved, so
  it was left out rather than scored with a gap in its core path.
- Spark Savings (~$283.6M), Morpho Blue (~$21.8M), Dolomite (~$21.1M):
  not attempted this run.
