# Ethereum L1 -- Sepolia testnet deployment (native contract)

Status: **deployed for real on 2026-09-18.** The funding blocker below is
closed -- the shared testnet key was rotated on 2026-09-18 (new address
`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`, replacing the old
`0xA08a76457b758aFF9702dBf5b870679E1232B715`, which was flagged as possibly
exposed in a local session transcript and is now abandoned with 0 funds --
see `keys/evm-testnet-shared.json`'s own `superseded_key_note` in the
pipeline's local config, not in this repo) and funded by Spap manually via a
Sepolia faucet. `AuthorityRiskOracle` and `ExampleConsumer` were deployed for
real to Sepolia, and the 9 scores below were pushed on-chain for real (not a
dry run). See "Real deploy record" below for addresses, tx hashes and
on-chain verification.

Latest state (CORRECTED 2026-09-21: this line said "twice ... 19 targets" and was
already stale when written): the oracle was pushed THREE times on 2026-09-20
(00:16, 18:37 then 19:39 UTC) and tracks 20 targets, 19 of them refreshed (the
retired Ethena minter, index 3, is the one that is not). Re-read live on two
independent Sepolia endpoints during the 2026-09-21 rotation audit.

**On-chain since 2026-09-20 18:37 UTC (maker-checker proposal, run by Spap):**
four more targets, Lido stETH, EigenLayer StrategyManager, Curve Stableswap-NG factory
and Rocket Pool RocketStorage, were appended as indexes 15 to 18 by one
`updateScores()` transaction. They are rows 15 to 18 of the table below. The prepared
command and its rehearsal are in [`data/maintenance_2026-09-20-run2.md`](../data/maintenance_2026-09-20-run2.md); the
index-1 rotation audit that run also recorded (zero divergence) needed no correction.
See "Current on-chain scores (re-push, 2026-09-20)" right below; the earlier tables are
kept as history.

**CORRECTED 2026-09-21 -- Aave V3 Horizon IS on-chain.** This paragraph used to read
"Scored, not on-chain (2026-09-20)". Horizon (composite 47, 65 / 70 / 0 / 100, cross 80) is the 19th
`score_all()` entry, appended last. It was merged into main on the owner's instruction while maker-checker
proposal still had no verifier decision. Spap then pushed it: `trackedTargetsCount()` went from 19 to 20
at 2026-09-20 19:39:42 UTC (tx `0x07320bc3...822fcb`, block 11746235), read live on two Sepolia endpoints
on 2026-09-21. See
[`data/scored_targets_2026-09-20-aave-horizon.md`](../data/scored_targets_2026-09-20-aave-horizon.md).

Everywhere this README previously said `0xA08a76457b758aFF9702dBf5b870679E1232B715`
it now says `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` -- the old address
was never funded (0 ETH/wei confirmed at time of replacement) so no funds
were at risk, but it should not be reused or funded going forward.

Before this, the deploy was blocked purely on deployer funding (not on code):
this phase's work was twice a full, reproducible dress rehearsal of the
entire deploy pipeline on a local anvil fork of Sepolia instead of a real
deploy -- see [`rehearsal_fork.sh`](rehearsal_fork.sh),
[`data/deploy_rehearsal_2026-09-17.md`](../data/deploy_rehearsal_2026-09-17.md),
[`data/deploy_rehearsal_2026-09-17-run2.md`](../data/deploy_rehearsal_2026-09-17-run2.md)
and the 2026-09-18 funding re-check
[`data/deploy_status_2026-09-18.md`](../data/deploy_status_2026-09-18.md).
Those rehearsals matched the live dry-run scores exactly for all 9 targets
(85/78/81/52/2/73/57/57/57) on the fork, which is exactly what the real
deploy below now reproduces on real Sepolia.

## Current on-chain scores (re-push, 2026-09-20)

> **CORRECTION 2026-09-21 (rotation audit, index 2).** This section, and the
> line further down saying `trackedTargetsCount()` reads 15, were both already
> published when a THIRD push landed. They are corrected here, not restated as
> a new finding: the live oracle tracks **20** targets, not 15 and not 19.
> A third `updateScores()` tx
> `0x07320bc3542f279d9e0fcb7974211b0faaa3dc4360d397db36cad2f986822fcb`
> (Sepolia block 11746235, status 1, gasUsed 440,593, 19 `ScoreUpdated` events,
> `lastUpdated` 1789933182 = 2026-09-20 19:39:42 UTC, sent by the shared
> deployer `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`) rewrote all 19 scored
> targets and appended a 20th, **Aave V3 Horizon PoolAddressesProvider
> `0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0`, composite 47** (row 19 below).
> So the note in commit `5ed49c6` -- Horizon "merged ahead of the verifier and
> not yet on the oracle" -- was true when written and is now stale: Horizon has
> been on the oracle since that push. Read live on two independent Sepolia
> endpoints on 2026-09-21 (publicnode `eth_getLogs` on block 11746235, Tenderly
> `eth_getTransactionReceipt` + `trackedTargetsCount()`); index 3, the retired
> Ethena minter, is still the only row not refreshed. Nothing was pushed by this
> audit -- it is read-only.

Two pushes are recorded in this table. The second one (18:37 UTC, proposal, tx
`0xc4873381005620ab0f560b5d8a1f998d316dd55081bba217297b95ad8e3cba46`, Sepolia block 11745959,
status 1, gasUsed 661,920, 18 `ScoreUpdated` events) took the oracle from 15 to 19
tracked targets; `getScore()` on all 18 scored targets equals the scorer output of
commit `1481133` (0 differences), checked by Spap's run and again independently.
The first one (00:16 UTC): 15 targets tracked, 14 refreshed. `updateScores()` tx
`0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`
(Sepolia block 11740952, status 1, gasUsed 353,396, `lastUpdated` 1789863398 =
2026-09-20 00:16:38 UTC) rewrote the 14 targets the scorer still scores.
Read back afterwards with plain `getScore()`: every one of those 14 equals
the scorer output of commit `042f805` exactly (0 differences). Index 3 is
the retired Ethena minter and is deliberately not refreshed, so it is the one
row that still carries its 2026-09-19 reading.

| # | Target | Address | admin | msig | tl | oracle | cross | composite |
|---|---|---|---|---|---|---|---|---|
| 0 | Uniswap V3 Factory | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | 80 | 100 | 75 | 100 | 80 | 85 |
| 1 | Aave V3 Ethereum Pool | `0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e` | 78 | 100 | 55 | 100 | **80** | 78 |
| 2 | MakerDAO / Sky MCD_PAUSE | `0xbE286431454714F511008713973d3B053A2d38f3` | 75 | 100 | 70 | 100 | 80 | 81 |
| 3 | Ethena EthenaMinting (RETIRED minter, not refreshed) | `0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3` | 55 | 100 | 0 | 100 | 20 | 52 |
| 4 | USDtb | `0xC139190F447e929f090Edeb554D95AbB8b18aC1c` | 5 | 0 | 0 | 100 | 100 | 2 |
| 5 | USDtb PSM | `0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728` | 65 | 100 | 55 | 100 | 20 | 73 |
| 6 | USDe OFTAdapter | `0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34` | 55 | 100 | 15 | 100 | 20 | 57 |
| 7 | sUSDe OFTAdapter | `0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2` | 55 | 100 | 15 | 100 | 20 | 57 |
| 8 | ENA OFTAdapter | `0x58538E6A46E07434d7E7375BC268D3cB839C0133` | 55 | 100 | 15 | 100 | 20 | 57 |
| 9 | Compound V3 cUSDCv3 | `0xc3d688B66703497DAA19211EEdff47f25384cdc3` | 78 | 100 | 60 | 100 | 100 | 79 |
| 10 | SparkLend PoolAddressesProvider | `0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE` | 75 | 100 | 60 | 100 | 80 | 78 |
| 11 | Uniswap V4 PoolManager | `0x000000000004444c5dc75cB358380D2e3dE08A90` | 80 | 100 | 75 | 100 | 80 | 85 |
| 12 | Morpho Blue, Ethereum | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | 65 | 95 | 0 | 100 | **80** | 55 |
| 13 | WBTC | `0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599` | 55 | 100 | 0 | 100 | 100 | 52 |
| 14 | Ethena EthenaMinting (USDe live minter, new) | `0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3` | **65** | **100** | **55** | **100** | **20** | **73** |
| 15 | Lido stETH (new, push #132) | `0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84` | 80 | 100 | 60 | 95 | 100 | 80 |
| 16 | EigenLayer StrategyManager (new, push #132) | `0x858646372CC42E1A627fcE94aa7A7033e7CF075A` | 60 | 100 | 20 | 100 | 100 | 60 |
| 17 | Curve Stableswap-NG factory (new, push #132) | `0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf` | 78 | 100 | 65 | 100 | 100 | 81 |
| 18 | Rocket Pool RocketStorage (new, push #132) | `0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46` | 55 | 0 | 0 | 100 | 100 | 22 |
| 19 | Aave V3 Horizon PoolAddressesProvider (added by the 19:39 UTC push, see the 2026-09-21 correction above) | `0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0` | 65 | 70 | 0 | 100 | 80 | 47 |

Changes vs the 2026-09-19 push (bold cells above):

- Rows 1 and 12: `crossExposureScore` 100 -> 80, composites unchanged (78 and 55).
  Consequence of the project convention decided 2026-09-20, which folds
  cross-ecosystem overlaps into the score (details in "2026-09-20 update" at
  the end of this file).
- Row 14 is new: the live USDe minter (`USDe.minter()` since 2024-07-08),
  appended by `updateScores()` because the oracle has no removal function.
- Row 3 (`0x2CC440b7...8Afc3`) is the retired minter and was not refreshed.
  Its `lastUpdated` is still 1789835973 (2026-09-19 16:39:33 UTC), so
  `isStale()` turns true for it after 2026-09-28 16:39:33 UTC (last update
  plus the 9-day `maxStaleness`). It stays tracked as a historical reading.
  `trackedTargetsCount()` read 15 when this line was written; it reads 20 since
  the 19:39 UTC push (see the 2026-09-21 correction at the top of this section).

Earlier records are kept below: the 2026-09-19 table and its full record in
[`data/maintenance_2026-09-19.md`](../data/maintenance_2026-09-19.md), branch
tests for the 5 targets added that day (15 tests in
[`chains/ethereum-l1/tests/`](../tests/)).

## Previous on-chain scores (maintenance run, 2026-09-19; superseded by the 2026-09-20 re-push)

14 targets tracked, pushed by `updateScores()` tx
`0xef181321e8516f14d505d473e00f96bd5d255a97bb0bae440b73eb325b39f0d8`
(Sepolia block 11738865, status 1) and read back with `getScore()` on 2
Sepolia RPCs. Kept unchanged as the record of that push.

| # | Target | Address | admin | msig | tl | oracle | cross | composite |
|---|---|---|---|---|---|---|---|---|
| 0 | Uniswap V3 Factory | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | 80 | 100 | 75 | 100 | 80 | 85 |
| 1 | Aave V3 Ethereum Pool | `0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e` | 78 | 100 | 55 | 100 | 100 | 78 |
| 2 | MakerDAO / Sky MCD_PAUSE | `0xbE286431454714F511008713973d3B053A2d38f3` | 75 | 100 | 70 | 100 | 80 | 81 |
| 3 | Ethena EthenaMinting | `0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3` | 55 | 100 | 0 | 100 | 20 | 52 |
| 4 | USDtb | `0xC139190F447e929f090Edeb554D95AbB8b18aC1c` | 5 | 0 | 0 | 100 | 100 | 2 |
| 5 | USDtb PSM | `0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728` | 65 | 100 | 55 | 100 | 20 | 73 |
| 6 | USDe OFTAdapter | `0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34` | 55 | 100 | 15 | 100 | 20 | 57 |
| 7 | sUSDe OFTAdapter | `0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2` | 55 | 100 | 15 | 100 | 20 | 57 |
| 8 | ENA OFTAdapter | `0x58538E6A46E07434d7E7375BC268D3cB839C0133` | 55 | 100 | 15 | 100 | 20 | 57 |
| 9 | Compound V3 cUSDCv3 (new) | `0xc3d688B66703497DAA19211EEdff47f25384cdc3` | 78 | 100 | 60 | 100 | 100 | 79 |
| 10 | SparkLend PoolAddressesProvider (new) | `0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE` | 75 | 100 | 60 | 100 | 80 | 78 |
| 11 | Uniswap V4 PoolManager (new) | `0x000000000004444c5dc75cB358380D2e3dE08A90` | 80 | 100 | 75 | 100 | 80 | 85 |
| 12 | Morpho Blue, Ethereum (new) | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | 65 | 95 | 0 | 100 | 100 | 55 |
| 13 | WBTC (new) | `0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599` | 55 | 100 | 0 | 100 | 100 | 52 |

Changes vs the 2026-09-18 push: 5 new targets; `crossExposureScore` of
Uniswap V3 and MakerDAO/Sky goes 100 -> 80 because they now share their
authority root with Uniswap V4 and SparkLend. That is a consequence of the
new targets, not a correction: the audit re-derivation of target 0 (Uniswap
V3) found no divergence.

> SUPERSEDED 2026-09-20: the table above is the state pushed to Sepolia on
> 2026-09-19 and is kept as that record. The 2026-09-20 re-push (tx
> `0x14b0466a...b7a98`, block 11740952) changed `crossExposureScore` of two
> rows, and only that field: row 1 (Aave V3 Ethereum Pool) is now
> 78 / 100 / 55 / 100 / **80** / 78, and row 12 (Morpho Blue, Ethereum) is now
> 65 / 95 / 0 / 100 / **80** / 55. Composites are unchanged. It also appended
> index 14. See "Current on-chain scores (re-push, 2026-09-20)" above and
> "2026-09-20 update" at the end of this file for the reason.

## Real deploy record (2026-09-18)

| Field | Value |
|---|---|
| `AuthorityRiskOracle` (deployed) | `0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906` |
| `ExampleConsumer` (deployed) | `0x16AC9ADef40365c9cb268d431489B5ce9e66A816` |
| Admin / updater | `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` |
| Deploy tx (`AuthorityRiskOracle` CREATE) | `0x931302ef254c16aeba89159cac51f5d012668dfbf4725ee0a5b76a0531584356` |
| Deploy tx (`ExampleConsumer` CREATE) | `0xc41d328197877d6e38cab054df4b3c3305d5bf66a27bb01aa3ef241767da5e31` |
| Deploy block | 11732364 |
| `updateScores()` tx (9 targets, real push) | `0xfbb1caf4ef05f303b7b231495baa58c5638de831f0f5cfe64e789bd249522e51` |
| `updateScores()` block | 11732374, status success, gasUsed 920027 |
| Deploy cost | ~0.00125 ETH |
| `updateScores()` cost | ~0.00097 ETH |
| Balance after both | ~0.01706 ETH (started at ~0.01928 ETH) |

Verified after deploy, not assumed:

- `eth_getCode` on both deployed addresses returned non-empty bytecode
  (oracle: 7239 hex chars; consumer: 2419 hex chars).
- `getScore()` read back directly from the deployed oracle for two targets
  matches exactly what was pushed: Uniswap V3 Factory
  (`0x1F98431c8aD98523631AE4a59f267346ea31F984`) composite `85`, USDtb
  (`0xC139190F447e929f090Edeb554D95AbB8b18aC1c`) composite `2`.
- The tx receipt for the `updateScores()` tx shows `status: 1 (success)` and
  9 `ScoreUpdated`-style log entries, one per target.

Not independently re-verified this pass: the other 7 of 9 pushed scores via
`getScore()` (only 2 were spot-checked live; all 9 are asserted correct by
the transaction succeeding and the encoded calldata matching the dry-run
record, but not each individually read back).

This README documents how
`src/AuthorityRiskOracle.sol` (reused unmodified from the repo root -- for an EVM
chain the native contract IS that contract, see the header of
[`chains/ethereum-l1/scorers.py`](../scorers.py) for why Ethereum L1 does not get its
own copy of the Solidity) will be deployed to Sepolia in the next phase
(`deploy_testnet`), plus the score-push path already proven end-to-end in dry-run.

## Target network

| Field | Value |
|---|---|
| Network | Ethereum Sepolia testnet |
| Chain ID | 11155111 (confirmed live via `cast chain-id`, see below) |
| Public RPC used | `https://ethereum-sepolia-rpc.publicnode.com` |
| Explorer | https://sepolia.etherscan.io |
| Deployer / updater key | `keys/evm-testnet-shared.json` (shared throwaway EVM testnet key, see that file's own `note` field -- never funded with real value, never reused for any mainnet deploy) |
| Deployer / updater address | `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` (rotated 2026-09-18; the old `0xA08a76457b758aFF9702dBf5b870679E1232B715` below is abandoned, 0 funds, do not reuse) |

Chain ID confirmed live (not assumed from docs):

```bash
cast chain-id --rpc-url https://ethereum-sepolia-rpc.publicnode.com
# -> 11155111
```

`https://rpc.sepolia.org` was tried first and is currently returning HTTP 404 (dead
endpoint as of 2026-09-16) -- `ethereum-sepolia-rpc.publicnode.com` is the one that
actually works and is what this README and script standardize on.

## Deployer address balance (Sepolia)

```bash
cast balance 0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5 --rpc-url https://ethereum-sepolia-rpc.publicnode.com --ether
# -> 0.019277997996992059 ETH (before deploy, 2026-09-18)
# -> 0.017055862746553917 ETH (after deploy + updateScores(), 2026-09-18)
```

**Funded and spent for real on 2026-09-18.** The key was rotated to
`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` after the previous address
(`0xA08a76457b758aFF9702dBf5b870679E1232B715`, which sat at 0 ETH through
2026-09-16 -- 2026-09-18, see
[`data/deploy_rehearsal_2026-09-17.md`](../data/deploy_rehearsal_2026-09-17.md),
[`data/deploy_rehearsal_2026-09-17-run2.md`](../data/deploy_rehearsal_2026-09-17-run2.md)
and [`data/deploy_status_2026-09-18.md`](../data/deploy_status_2026-09-18.md)
for that history) was flagged as possibly exposed in a session transcript.
Spap funded the new address manually via a Sepolia faucet on 2026-09-18. The
real deploy and score push below spent ~0.00222 ETH total, leaving
~0.01706 ETH on the address.

## Deploy (deploy_testnet phase -- run for real on 2026-09-18)

Reuses [`script/Deploy.s.sol`](../../../script/Deploy.s.sol) unmodified, same as the
Robinhood Chain deploy documented in the repo root README -- it already takes
`--rpc-url` as a flag rather than hardcoding a chain, so no Ethereum-L1-specific
Solidity or script is needed:

```bash
PRIVATE_KEY=<from keys/evm-testnet-shared.json, never printed/committed> \
forge script script/Deploy.s.sol \
  --rpc-url https://ethereum-sepolia-rpc.publicnode.com \
  --broadcast
```

This deployed `AuthorityRiskOracle` at `0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906`
(admin/updater = the deploying key, same MVP pattern as Robinhood Chain) and the demo
`ExampleConsumer` at `0x16AC9ADef40365c9cb268d431489B5ce9e66A816`, wired to it. See
"Real deploy record" above for tx hashes; the `AuthorityRiskOracle` address has been
recorded in `ecosystems.json`'s `ethereum-l1` entry (`oracle_address_testnet`).

## Score push script

[`update_scores_ethereum_l1.py`](update_scores_ethereum_l1.py) is parameterized on
the model of the repo root's [`scripts/update_scores.py`](../../../scripts/update_scores.py),
with this ecosystem's own read/write split:

- **Read** -- Ethereum L1 mainnet (chain 1), where the 4 scored targets
  (`chains/ethereum-l1/scorers.py`) actually live.
- **Write** -- Sepolia (chain 11155111), where the oracle will be deployed.

```bash
python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py --dry-run
```

`--dry-run` re-derives all 4 scores live from Ethereum L1 mainnet and ABI-encodes
the exact `updateScores(address[], AuthorityScore[])` calldata that would be sent --
**without opening any connection to Sepolia, without reading `PRIVATE_KEY`, and
without sending anything.** Verified this phase: the encoded calldata's function
selector (`0x5fb3feaf`) matches `cast sig "updateScores(address[],(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)[])"`
computed independently, and the ABI-decoded target list/scores in the calldata match
`data/scored_targets_2026-09-16-ethereum-l1.md` exactly.

The non-dry-run path (build/sign/send a real transaction) was run for real on
2026-09-18 against the deployed oracle:

```bash
ORACLE_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com \
ORACLE_ADDRESS=0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906 \
PRIVATE_KEY=<from keys/evm-testnet-shared.json, never printed/committed> \
READ_RPC_URL=https://ethereum.publicnode.com \
python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py \
  --oracle-address 0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906
```

Sent tx `0xfbb1caf4ef05f303b7b231495baa58c5638de831f0f5cfe64e789bd249522e51`,
confirmed in block 11732374, status success. See "Real deploy record" above.

Note: `crossExposureScore` is not yet computed by `chains/ethereum-l1/scorers.py`
(that needs a full cross-ecosystem signer-overlap pass, out of scope for this
phase) -- the push script defaults it to 100 only so the tuple shape matches the
on-chain struct for encoding; this is a placeholder, not a claimed finding.

> UPDATED 2026-09-20: that note describes the 2026-09-18 push and is out of
> date. `scorers.py` has computed `crossExposureScore` since 2026-09-17 (a
> within-L1 check), and since 2026-09-20 it also folds cross-ecosystem
> overlaps into it (see "2026-09-20 update" at the end of this file). Those
> values are on-chain since the 2026-09-20 re-push (tx `0x14b0466a...b7a98`,
> block 11740952).

## Build and test (already run and passing, see `claims_attempt1.txt`)

```bash
forge build --out <separate-out-dir> --cache-path <separate-cache-dir>
forge test --out <separate-out-dir> --cache-path <separate-cache-dir>
```

`src/AuthorityRiskOracle.sol` is shared, generic infrastructure (not
ecosystem-specific) -- these commands compile and test the whole repo, same as any
other ecosystem's deploy pass would.

## 2026-09-20 update: cross-ecosystem overlaps folded into crossExposureScore (pushed on-chain 2026-09-20)

Scorer output as of 2026-09-20 (`chains/ethereum-l1/scorers.py`, re-run
read-only against Ethereum mainnet, no key, no transaction), pushed to the
Sepolia oracle the same day (tx
`0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`,
block 11740952). Two targets move on `crossExposureScore` only; composites do
not change, because `crossExposureScore` is not an input of the composite.

| # | Target | admin | msig | tl | oracle | cross on the oracle before (2026-09-19 push) | cross on the oracle now (pushed 2026-09-20, equal to scorer) | composite (unchanged) |
|---|---|---|---|---|---|---|---|---|
| 1 | Aave V3 Ethereum Pool | 78 | 100 | 55 | 100 | 100 | **80** | 78 |
| 12 | Morpho Blue, Ethereum | 65 | 95 | 0 | 100 | 100 | **80** | 55 |

Why. The project decided on 2026-09-20 that a cross-ecosystem overlap is
folded into `crossExposureScore` on every ecosystem (root `METHODOLOGY.md`,
paragraph "Convention (decided 2026-09-20)"): a flat 80 when a target's root
committee is identical to a tracked target's on another ecosystem, combined
with `min()` so it never raises a value the within-L1 check already lowered,
and a scorer never calls another chain's RPC (it compares the owners it just
read against a hardcoded, dated snapshot). Ethereum L1 used to keep these
overlaps as notes only.

- Aave V3 Ethereum Pool: two independent cross-chain committees match. The
  `PayloadsController.guardian()` Safe (`0xCe52ab41...`, 9 signers) is the
  same committee as the Aave guardian Safes on Arbitrum, Base, Plasma and
  Monad. The `PROTOCOL_GUARDIAN` Safe (4-of-7, 7 signers, snapshot
  `_KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20`) has the same 7 owners as
  the emergency-admin Safes on Arbitrum, Base, Plasma and Monad. The fold is
  applied once (`min`), so the value is 80, not 60.
- Morpho Blue, Ethereum: the owner Safe has the same 9 Morpho Association
  signers as the Morpho Blue owner Safes on Base, Robinhood Chain and Tempo.

Every other Ethereum L1 target is unchanged. Done: the Sepolia oracle
`0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906` holds `crossExposureScore` 80 for
the two targets above since the 2026-09-20 re-push, read back with plain
`getScore()` and equal to the scorer output.

### Ethena minter: the scored contract changed (pushed on-chain 2026-09-20 as a new index 14)

Row 3 of the 2026-09-19 table ("Ethena EthenaMinting", `0x2CC440b7...8Afc3`, 55 / 100 / 0 / 100 / 20 / 52) scores
a contract that stopped being USDe's minter on 2024-07-08 (`USDe.minter()` has pointed at
`0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3` since block 20261016; `USDe.mint()` from the old
address reverts `OnlyMinter`, and it holds no collateral). `score_ethena_minting()` now scores the
live minter, read live on two RPCs and adversarially re-verified on 2026-09-20:

| Target | address | admin | msig | tl | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| Ethena EthenaMinting (USDe live minter) | `0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3` | 65 | 100 | 55 | 100 | 20 | 73 |

Same convention as the USDtb PSM: the minter's `DEFAULT_ADMIN_ROLE`, `USDe.owner()` and the timelock's only
proposer/canceller resolve to the `EthenaTimelockController` (24h) and its 5-of-10 Safe, and the six admin
selectors that would redirect funds or mint unbacked USDe, plus `USDe.setMinter`, are not whitelisted.
Instant lanes (`revokeRole`, add/remove whitelisted benefactor) and the Safe's direct
`COLLATERAL_MANAGER_ROLE` (sweep to 5 registered custodian EOAs), plus 4 bare-EOA gatekeepers, are disclosed in
the notes and not folded into the score. See `score_ethena_minting()`'s docstring.

The oracle has no removal function, so the retired target is retired by ceasing to refresh it. The 2026-09-20
re-push (tx `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`, block 11740952) appended the new
minter at index 14, read back as 65 / 100 / 55 / 100 / 20 / 73, equal to the scorer output. The oracle now tracks
15 targets, 14 of them refreshed. Index 3 keeps its 2026-09-19 reading (55 / 100 / 0 / 100 / 20 / 52, `lastUpdated`
1789835973 = 2026-09-19 16:39:33 UTC) and goes stale after `maxStaleness` (9 days), that is after
2026-09-28 16:39:33 UTC; until then `isStale()` still returns false for it, although the contract it scores no
longer mints USDe.
