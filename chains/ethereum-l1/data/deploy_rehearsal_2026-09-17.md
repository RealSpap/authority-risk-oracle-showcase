# Ethereum L1 -- deploy_testnet fork rehearsal (2026-09-17)

## Why a rehearsal instead of a real Sepolia deploy

The shared throwaway deployer `0xA08a76457b758aFF9702dBf5b870679E1232B715`
(`keys/evm-testnet-shared.json`) still has **0 ETH on real Sepolia**, confirmed
live on 2 independent RPCs at the start of this run:

| RPC | Result |
|---|---|
| `https://ethereum-sepolia-rpc.publicnode.com` | `cast balance` -> `0` wei |
| `https://sepolia.gateway.tenderly.co` | `cast balance` -> `0` wei |

(A third RPC, `https://sepolia.drpc.org`, was tried per the run brief and
returned an unrelated error -- "chain is not available on free plan" -- not a
balance reading, so it was not counted as a confirmation either way.)

This matches the run's known starting fact and the open "A faire" card asking
Spap to fund the address via a faucet. An agent cannot use a faucet, so no
transaction was attempted on real Sepolia this run. Per the phase brief, the
alternative is a full, reproducible dress rehearsal against a local anvil
fork of Sepolia -- proving the entire pipeline works end to end so the real
deploy is a known-good, mechanical step once Spap funds the address.

## What the rehearsal proves

Script: `rehearsal_fork.sh` (re-runnable, `bash
chains/ethereum-l1/deploy/rehearsal_fork.sh`). One run, 2026-09-17:

| Step | Result |
|---|---|
| Fork source chain id (`cast chain-id` against `ethereum-sepolia-rpc.publicnode.com`) | `11155111` |
| Local anvil fork chain id (port 8546) | `11155111` |
| `forge script script/Deploy.s.sol --broadcast` against the fork | `ONCHAIN EXECUTION COMPLETE & SUCCESSFUL` |
| Deployed `AuthorityRiskOracle` address (fork only, ephemeral) | `0x60B97BB35c2bFB8D3A3c509EcC2352ca72421a1a` |
| Deployed `ExampleConsumer` address (fork only, ephemeral) | `0x29809c3e19d45DBEACFe670a1524DD95240FDC31` |
| Deployer / admin / updater (anvil's well-known default dev account #0, NOT the real throwaway key) | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` |
| `hasRole(UPDATER_ROLE, deployer)` on the fresh oracle | `true` |
| `update_scores_ethereum_l1.py --oracle-address <fork oracle> --oracle-rpc-url http://127.0.0.1:8546` (READ_RPC_URL = `https://ethereum-rpc.publicnode.com`, real mainnet) | `Confirmed in block 11722919: success` (exact fork block number varies slightly run to run; every run of `rehearsal_fork.sh` has confirmed `success`, see `claims_attempt1.txt`) |
| Read RPC chain id check inside the script | `1` (Ethereum L1 mainnet, as required) |
| Oracle RPC chain id check inside the script | `11155111` (Sepolia, as required) |

## getScore() read back vs. the calculated scores

Read live from the fork oracle after the push, compared to
`data/scored_targets_2026-09-16-ethereum-l1.md` (the committed source of
truth for these 4 targets):

| Target | Committed composite | On-chain composite (`getScore` after push) | Match |
|---|---|---|---|
| Uniswap V3 Factory `0x1F98431c8aD98523631AE4a59f267346ea31F984` | 85 | 85 | yes |
| Aave V3 Ethereum Pool `0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e` | 78 | 78 | yes |
| MakerDAO / Sky (MCD_PAUSE) `0xbE286431454714F511008713973d3B053A2d38f3` | 81 | 81 | yes |
| Ethena EthenaMinting `0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3` | 52 | 52 | yes |

The sub-scores (adminKey/multisig/timelock) read back from `getScore()` also
match the per-target breakdown in `data/scored_targets_2026-09-16-ethereum-l1.md`
exactly (e.g. Uniswap 80/100/75, Aave 78/100/55, Maker 75/100/70, Ethena
55/100/0) -- the scores were re-derived live from real Ethereum L1 mainnet
during this run (not replayed from a file), and matched the committed values
because mainnet authority state for these 4 targets has not changed since
2026-09-16.

`crossExposureScore` reads back as `100` (the placeholder default) for all 4
targets, consistent with the known open thread documented in
`chains/ethereum-l1/deploy/README.md` and `update_scores_ethereum_l1.py` --
the cross-ecosystem signer-overlap pass has not been built yet, so this is
not a new finding.

## What this does and does not close

- Closes: the deploy -> role check -> live score push -> on-chain read-back
  pipeline is proven correct end to end for Ethereum L1, mechanically
  reproducible, and matches the committed scoring exactly. Nothing about the
  real deploy path (`script/Deploy.s.sol`, `update_scores_ethereum_l1.py`
  non-dry-run branch) needed to change to make this pass.
- Does not close: the real Sepolia deployment itself. That still requires
  Spap to fund `0xA08a76457b758aFF9702dBf5b870679E1232B715` on Sepolia (see
  the open "A faire" card) -- no faucet use by an agent, no funds were moved,
  no mainnet or real-Sepolia transaction was sent this run.
- All contract interaction above happened on an ephemeral local anvil fork,
  using anvil's own public, well-known default dev private key (never the
  real throwaway key from `keys/evm-testnet-shared.json`, never printed here
  in full). Anvil was stopped at the end of the run; the fork oracle address
  above will not resolve on any real network.

## Recommended transition

`deploy_testnet -> deploy_testnet` (maintained, not advanced), justified by
the deployer balance still being 0 ETH on real Sepolia. The pipeline itself
is rehearsed and ready; only funding is blocking the real push.
