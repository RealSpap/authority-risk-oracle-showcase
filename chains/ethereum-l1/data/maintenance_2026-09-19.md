# Ethereum L1 -- maintenance run, 2026-09-19

First run of the `maintenance` phase for this ecosystem (pipeline
`authority-risk-oracle-multichain-pipeline`, scheduled worker). Three parts:
(a) audit rotation, (b) new targets, (c) README figures check.

## (a) Audit rotation -- index 0: Uniswap V3 Factory

`trackedTargets(0)` on the Sepolia oracle `0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906`
= `0x1F98431c8aD98523631AE4a59f267346ea31F984`, published score before this run
(read on publicnode + Tenderly Sepolia, identical):
admin 80 / multisig 100 / timelock 75 / oracle 100 / crossExposure 100 / composite 85.

Re-derived from scratch on Ethereum mainnet (raw eth_call, not through
`scorers.py`), block 26012723, on 2 independent RPCs
(`ethereum-rpc.publicnode.com` and `eth.drpc.org`), identical results:

| Read | Value |
|---|---|
| `Factory.owner()` | `0xf2371551Fe3937Db7c750f4DfABe5c2fFFdcBf5A` (V3OpenFeeAdapter, Sourcify exact match, 7266 bytes of code) |
| `adapter.owner()` / `adapter.feeSetter()` | `0x1a9C8182C09F50C8318d769245beA52c32BE35BC` (Uniswap Timelock), both |
| `Timelock.delay()` / `MINIMUM_DELAY()` / `GRACE_PERIOD()` | 172800 / 172800 / 1209600 |
| `Timelock.admin()` / `pendingAdmin()` | GovernorBravo `0x408ED635...24C3` / `0x0` |
| `GovernorBravo.quorumVotes()` / `proposalThreshold()` / `proposalCount()` | 40M UNI / 1M UNI / 100 |
| `GovernorBravo.admin()` / `pendingAdmin()` | the Timelock / `0x0` |

Scoring those reads with the published rubric gives 80 / 100 / 75 -> composite
**85 -- no divergence**, no correction needed.

Partly closes the open thread in `score_uniswap_v3_factory()`'s docstring
("no check yet for an emergency-bypass mechanism"): no pending admin on either
the Timelock or the Governor, the delay already sits at its hard-coded 2-day
floor, the Governor has no `whitelistGuardian`, and every privileged function
on the fee adapter (`setFactoryOwner`, `setFeeSetter`, fee setters,
`transferOwnership`) is gated by the Timelock. The score was **not** raised
because of this: the timelock cap stays at 75 until the rubric itself is
reviewed (listed as an open lead, not changed by an audit pass).

**Knock-on change (not a correction of an error):** after this run the
on-chain `crossExposureScore` of Uniswap V3 goes 100 -> 80, because Uniswap V4
PoolManager (added below) is owned directly by the same Timelock. Same for
MakerDAO/Sky MCD_PAUSE (100 -> 80), which now shares its root with SparkLend.
Composites do not change (crossExposure is not part of the composite formula).

## (b) New targets (5)

Each address has a primary source; each authority hop was read live on 2 RPCs
(publicnode + `gateway.tenderly.co/public/mainnet`), and `score_all()` returned
identical sub-scores on both.

| Target | Address | Source of the address | TVL (DefiLlama, 2026-09-19) | Authority root (live) | admin/msig/tl/cross -> composite |
|---|---|---|---|---|---|
| Compound V3 cUSDCv3 | `0xc3d688B66703497DAA19211EEdff47f25384cdc3` | compound-finance/comet `deployments/mainnet/usdc/roots.json` | $1.36B (Compound V3, Ethereum) | Compound Timelock (2d, 2d floor) <- CompoundGovernor (608 proposals); ProxyAdmin + Configurator on the same Timelock; pauseGuardian = Safe 5-of-9 (instant pause incl. withdraw) | 78/100/60/100 -> **79** |
| SparkLend PoolAddressesProvider | `0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE` | sparkdotfi/spark-address-registry `src/SparkLend.sol` | $5.61B | SparkProxy; wards = MCD_PAUSE_PROXY (owner MCD_PAUSE, 2d), ESM (min = 2^256-1, cannot fire), StarGuard (ward = MCD_PAUSE_PROXY only); FreezerMom instant freeze via Chief hat + Safe 3-of-5 | 75/100/60/80 -> **78** |
| Uniswap V4 PoolManager | `0x000000000004444c5dc75cB358380D2e3dE08A90` | DefiLlama-Adapters `projects/uniswap-v4/index.js` | $743M | owner = Uniswap Timelock directly; V4FeeAdapter and V4FeePolicy owner + feeSetter = same Timelock | 80/100/75/80 -> **85** |
| Morpho Blue (Ethereum) | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | DefiLlama-Adapters `projects/morpho-blue/config.js` | $5.03B | owner = Safe 5-of-9 (v1.3.0, no module, no guard), no delay; same 9 signers as the Base and Robinhood Morpho Safes | 65/95/0/100 -> **55** |
| WBTC | `0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599` | DefiLlama-Adapters `projects/helper/coreAssets.json` | $9.50B (= 116,132 WBTC live supply x $81,764) | owner = Controller `0xCA06411b...` (token() points back); Controller.owner = legacy Gnosis MultiSigWallet 6-of-10 `0x972Eed35...` (not a Safe), no delay, 4 txs ever | 55/100/0/100 -> **52** |

> UPDATED 2026-09-20: the Morpho Blue row's cross exposure of 100 (the last
> value of its 65/95/0/100 tuple) is the value pushed on 2026-09-19.
> The row says the owner Safe has the same 9 signers as the Base and Robinhood
> Morpho Safes, and under the project convention decided 2026-09-20 (root
> `METHODOLOGY.md`, paragraph "Convention (decided 2026-09-20)") that
> cross-ecosystem overlap is folded into the score: `chains/ethereum-l1/scorers.py`
> now returns 65/95/0/100/**80** for it (composite 55 unchanged), and the
> same 9 signers also own Tempo's Morpho Blue core. Superseded by the
> 2026-09-20 re-push (tx
> `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`,
> Sepolia block 11740952): the oracle now holds 65/95/0/100/**80**/55 for this
> target, read back equal to the scorer output. The 100 in the row above stays
> as the record of the 2026-09-19 push. See "Current on-chain scores (re-push,
> 2026-09-20)" and the "2026-09-20 update" in `deploy/README.md`.

How each role/ward set was replayed (not just a single getter): Spark
ACLManager `RoleGranted/RoleRevoked` from block 16.7M, and SparkProxy /
FreezerMom / StarGuard `Rely/Deny`, all via the Tenderly public gateway
(publicnode returns 403 on `eth_getLogs`, drpc returns 400 on wide ranges).
Current holders on the Spark ACLManager: DEFAULT_ADMIN, POOL_ADMIN and
EMERGENCY_ADMIN = SparkProxy; EMERGENCY_ADMIN + RISK_ADMIN = FreezerMom;
RISK_ADMIN = KillSwitchOracle and CapAutomator (both Sourcify exact match,
owner = SparkProxy).

Rubric choices made this run (stated so they can be challenged):
- 60 = 2-day delay with a known **freeze/pause-only** instant bypass held
  by an identified Safe or hat (Compound, Spark). It sits between Aave's 55
  (1-day delay, same kind of bypass) and Maker's 70 / Uniswap's 75 (2 days, no
  bypass found).
- Morpho Blue follows the Base scorer's rule for the same protocol (65 for a
  threshold of 3 or more), so one protocol gets one convention across
  ecosystems. WBTC follows this file's Ethena convention (55: multisig over
  a multi-billion token with no DAO and no delay).

## On-chain push (Sepolia)

- First send `0x327864608f12ac446340f15421da4af3e7e4f496845f19de10d917e160752694`
  (gasPrice 0.93 gwei) stayed pending while the base fee was at 1.03 gwei. It was
  replaced with the same nonce (5) and the same calldata by
  `0xef181321e8516f14d505d473e00f96bd5d255a97bb0bae440b73eb325b39f0d8`
  (2.06 gwei): block 11738865, status 1, gasUsed 671736, 14 logs. The first
  hash no longer exists (`TransactionNotFound`). The push script now sends at
  2x `eth_gasPrice`.
- `trackedTargetsCount()` = 14. All 14 `getScore()` values were read back on 2
  Sepolia RPCs (publicnode + Tenderly) after the push and match `score_all()`
  exactly (lastUpdated 1789835973).
- Cost ~0.00139 ETH. Deployer balance after: ~0.01567 ETH.

## Open leads (not resolved this run)

- Lido (stETH / Dual Governance), EigenLayer (Executor multisig and
  Timelock), ether.fi, Rocket Pool, Curve, Pendle: high-TVL candidates, left
  for later because each has a multi-layer authority (Aragon ACL, dual
  governance, EigenLayer's 1-of-2 executor) that needs its own careful
  replay rather than a rushed score.
- `scripts/lib/cross_ecosystem_overlap.py` `ETHEREUM_L1_GROUPS` does not list
  the new Morpho Blue L1 Safe (same committee as the Base and Robinhood
  Safes). It is a shared repo-root file, so this worker did not edit it.
- Uniswap timelockScore cap (75): the reason for the cap ("no emergency-bypass
  check") is now mostly gone (see (a)). Raising it is a rubric decision, not an
  audit correction.
