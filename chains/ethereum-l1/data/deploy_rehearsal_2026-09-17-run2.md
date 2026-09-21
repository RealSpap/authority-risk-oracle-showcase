# Ethereum L1 -- deploy_testnet fork rehearsal, run 2 (2026-09-17 evening)

## Why a second rehearsal today

The morning's rehearsal (`deploy_rehearsal_2026-09-17.md`) proved the pipeline
against a 4-target scorer (composite 85/78/81/52, `crossExposureScore` still
a flat 100 placeholder). Between that run and this one, an interactive
session pushed 17 commits (14:39-18:51) that changed `chains/ethereum-l1/scorers.py`
materially:

- Promoted USDtb, USDtb PSM and the 3 Ethena LayerZero OFTAdapters
  (USDe/sUSDe/ENA) from backlog to real scorers -- 4 -> 9 tracked targets.
- Fixed `crossExposureScore` from a hardcoded 100 to a real computed value
  (5 of the 9 targets share Ethena's root Safe and now read 20, not 100).
- Fixed a live Safe-threshold read that used to be discarded in favour of a
  hardcoded `multisigScore=100`.

None of that touched `src/AuthorityRiskOracle.sol`, `script/Deploy.s.sol`, or
`update_scores_ethereum_l1.py`'s encoding logic, but since the scorer output
itself changed since the last fork run, this run re-verifies the full
pipeline end to end against the CURRENT scorer state rather than assuming
the morning's pass still applies.

## Starting fact: deployer balance still 0 ETH on real Sepolia

Re-checked live on 2 independent RPCs at the start of this run (see
`claims_attempt1.txt` ids B01/B02):

| RPC | Result |
|---|---|
| `https://ethereum-sepolia-rpc.publicnode.com` | `cast balance` -> `0` wei |
| `https://sepolia.gateway.tenderly.co` | `cast balance` -> `0` wei |

No faucet was used (agent policy), no funds were requested. Per the run
brief, since the scorer changed materially since the last fork rehearsal,
the pipeline was rehearsed again on a fresh anvil fork rather than merely
re-stating the morning's result.

## What this rehearsal proves

Script: [`rehearsal_fork.sh`](../deploy/rehearsal_fork.sh) (updated this run:
its `getScore()` read-back loop was extended from the original 4 hardcoded
targets to all 9 the scorer now tracks -- it had gone stale after this
afternoon's promotions).

| Step | Result |
|---|---|
| Fork source chain id (`ethereum-sepolia-rpc.publicnode.com`) | `11155111` |
| Local anvil fork chain id (port 8546) | `11155111` |
| `forge script script/Deploy.s.sol --broadcast` against the fork | `ONCHAIN EXECUTION COMPLETE & SUCCESSFUL` |
| Deployed `AuthorityRiskOracle` address (fork only, ephemeral) | `0x60B97BB35c2bFB8D3A3c509EcC2352ca72421a1a` |
| Deployed `ExampleConsumer` address (fork only, ephemeral) | `0x29809c3e19d45DBEACFe670a1524DD95240FDC31` |
| Deployer / admin / updater (anvil's well-known default dev account #0, NOT the real throwaway key) | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` |
| `hasRole(UPDATER_ROLE, deployer)` on the fresh oracle | `true` |
| `update_scores_ethereum_l1.py` dry-run target count | `9` (was 4 in the morning run) |
| `updateScores()` push tx | `0xa7b69ec27985ca7b45c5b026acea02df7101a239c348620a2c7286decebd0d4e`, confirmed block `11725084`, status `success` |
| Read RPC chain id check inside the script | `1` (Ethereum L1 mainnet, as required) |
| Oracle RPC chain id check inside the script | `11155111` (Sepolia, as required) |

## getScore() read back vs. the live dry-run scores (all 9 targets)

| Target | Label | Dry-run composite | On-chain composite (`getScore`) | Match |
|---|---|---|---|---|
| `0x1F98431c8aD98523631AE4a59f267346ea31F984` | Uniswap V3 Factory | 85 | 85 | yes |
| `0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e` | Aave V3 Ethereum Pool | 78 | 78 | yes |
| `0xbE286431454714F511008713973d3B053A2d38f3` | MakerDAO / Sky (MCD_PAUSE) | 81 | 81 | yes |
| `0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3` | Ethena EthenaMinting | 52 | 52 | yes |
| `0xC139190F447e929f090Edeb554D95AbB8b18aC1c` | USDtb | 2 | 2 | yes |
| `0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728` | USDtb PSM | 73 | 73 | yes |
| `0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34` | USDe OFTAdapter | 57 | 57 | yes |
| `0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2` | sUSDe OFTAdapter | 57 | 57 | yes |
| `0x58538E6A46E07434d7E7375BC268D3cB839C0133` | ENA OFTAdapter | 57 | 57 | yes |

`crossExposureScore` read back on-chain confirms the real computed value,
not the old flat-100 placeholder: Uniswap, Aave, Maker and USDtb (the ERC20
token contract itself) read `100`; Ethena EthenaMinting, USDtb PSM and the 3
OFTAdapters (5 of the 9 targets, the ones the scorer resolves as sharing the
root Ethena Safe) all read `20`, matching `scorers.py`'s live cross-exposure
computation exactly. Note USDtb PSM reads `20` while the USDtb token
contract itself reads `100` -- the scorer treats the PSM and the token as
different authority surfaces, not a documentation slip.

## What this does and does not close

- Closes: re-confirms the deploy -> role check -> live score push -> on-chain
  read-back pipeline is still correct end to end after this afternoon's
  scorer changes (9 targets, real `crossExposureScore`), not just for the
  original 4-target state.
- Does not close: the real Sepolia deployment. Still blocked on funding --
  `0xA08a76457b758aFF9702dBf5b870679E1232B715` remains at 0 ETH on real
  Sepolia (confirmed live again this run, 2 independent RPCs). No faucet
  use, no funds moved, no real-Sepolia or mainnet transaction sent this run.
- All contract interaction above happened on an ephemeral local anvil fork
  using anvil's own public, well-known default dev private key (never the
  real throwaway key). Anvil was stopped at the end of the run; the fork
  oracle address above will not resolve on any real network.

## Recommended transition

`deploy_testnet -> deploy_testnet` (maintained, not advanced) -- the
deployer balance is still 0 ETH on real Sepolia, so no real deploy happened.
The pipeline itself is re-proven correct against the current scorer state.
