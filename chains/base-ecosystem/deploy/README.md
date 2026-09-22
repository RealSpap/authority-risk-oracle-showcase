# Base Ecosystem -- deployment guide (Base Sepolia, chain 84532)

Phase: `maintenance` (since 2026-09-18; was `deploy_testnet`). This README documents how to
deploy the project's **existing** native EVM contract
(`src/AuthorityRiskOracle.sol`, reused as-is, not modified for Base) to Base
Sepolia testnet.

**Status as of 2026-09-18: deployed for real.** The funding blocker
described in earlier revisions of this file is resolved -- the shared
deployer was funded by Spap manually and the pipeline ran a real broadcast
to Base Sepolia for the first time this same day. Summary (full detail in
"Real deployment" below):

| | |
|---|---|
| `AuthorityRiskOracle` | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` |
| `ExampleConsumer` | `0xB7403b365a58B31Ae030DB423f6B703AD67f003a` |
| Deploy tx | `0xbf2875015bb893126cb117150ef9cbf7cef7573f5bfef616472012838572e746` (status: success, block 46993519) |
| `updateScores()` tx | `0xd7483e0a50f292e8da859dbc37895f3fd7f7f1bba2c413bb137f5c483ca897f0` (status: success, block 46993594) |

Previous rehearsals (on local anvil forks, no real transactions) are kept
for history in `data/deploy_rehearsal_2026-09-18.md`,
`data/deploy_rehearsal_2026-09-17-run2.md`,
`data/deploy_rehearsal_2026-09-17.md` -- those still correctly describe the
old shared deployer address that was in use at the time of each rehearsal;
they are not rewritten here.

## Network

| | |
|---|---|
| Network | Base Sepolia (testnet) |
| Chain ID | **84532** -- confirmed live this run via `cast chain-id --rpc-url https://sepolia.base.org` (returned `84532`) |
| Public RPC (official) | `https://sepolia.base.org` |
| Secondary public RPC | `https://base-sepolia-rpc.publicnode.com` |
| Explorer | https://sepolia.basescan.org |
| Faucets | https://www.alchemy.com/faucets/base-sepolia , https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet (Base's own docs list of Sepolia faucets: https://docs.base.org/base-chain/tools/network-faucets) |

Base mainnet (read-only, for the scorer -- never a deploy target) is chain
**8453**, also confirmed live this run (`cast chain-id --rpc-url
https://mainnet.base.org` returned `8453`).

## Contract

`src/AuthorityRiskOracle.sol` is used unmodified -- same contract already
deployed for Robinhood Chain testnet (see the repo root `README.md`'s
"Status" section). No Base-specific Solidity changes are needed: the
contract is chain-agnostic (`AccessControl`-gated `UPDATER_ROLE`,
`updateScore`/`updateScores`, `getScore`, `isStale`).

`script/Deploy.s.sol` (repo root, also reused unmodified) deploys
`AuthorityRiskOracle` with `admin = deployer` and a demo `ExampleConsumer`
wired to it.

## Build and test (already run this pass, read-only, no deploy)

Every ecosystem's agent shares this one clone -- always pass separate
`--out`/`--cache-path` so parallel agents never clobber each other's build
artifacts:

```
forge build \
  --out <this run's forge-out dir> \
  --cache-path <this run's forge-cache dir>

forge test \
  --out <this run's forge-out dir> \
  --cache-path <this run's forge-cache dir>
```

Result this run (2026-09-16, scoring_build attempt 1): `Compiler run
successful!`, 16/16 tests passed across `AuthorityRiskOracle.t.sol` and
`ExampleConsumer.t.sol` (0 failed, 0 skipped). See
`runs/2026-09-16-run2/base-ecosystem/claims_attempt1.txt` for the exact
re-runnable commands.

Re-confirmed 2026-09-17 evening (run 2, attempt 1): `Compiler run
successful!`, 20/20 tests passed (the afternoon session added 4 tests
project-wide, none of them in this ecosystem's own files). See
`runs/2026-09-17-run2/base-ecosystem/claims_attempt1.txt`.

Re-confirmed 2026-09-18: `Compiler run successful!`, 20/20 tests passed
(unchanged test count, no test files touched since 2026-09-17). See
`runs/2026-09-18/base-ecosystem/claims_attempt1.txt`.

## Deploy key and current balance

Uses the shared EVM testnet key, `keys/evm-testnet-shared.json`. **The
address changed on 2026-09-18**: the previous address,
`0xA08a76457b758aFF9702dBf5b870679E1232B715`, is abandoned -- it was flagged
as possibly written into a local session transcript on 2026-09-17, and was
regenerated as a precaution. It was never funded (confirmed 0 wei on Base
Sepolia at every check between 2026-09-16 and 2026-09-18), so no funds were
ever at risk; it should simply no longer be used or funded. Any reference to
`0xA08a76...B715` remaining elsewhere in this repo's history (rehearsal logs
from before 2026-09-18) describes what was actually true at that time and is
left as-is.

The current, funded address is:

```
0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5
```

Private key never copied into this repo, never printed to any output or
log; read from `keys/evm-testnet-shared.json` (outside this repo, in the
pipeline's local config directory) and passed only as the `PRIVATE_KEY`
environment variable to `forge`/`cast`/`push_scores.py`.

Funded by Spap manually (faucet) some time before 2026-09-18. Balance
checked live on 2 independent public RPCs immediately before the real
deploy:

| RPC | Chain ID | Balance |
|---|---|---|
| `https://sepolia.base.org` | 84532 | 0.015 ETH |
| `https://base-sepolia-rpc.publicnode.com` | 84532 | 0.015 ETH |

## Real deployment (2026-09-18) -- Base Sepolia, chain 84532

The deploy command below was run for real (not a rehearsal, not a fork).
Chain ID was confirmed live immediately before broadcasting: `cast chain-id
--rpc-url https://sepolia.base.org` returned `84532`.

```
PRIVATE_KEY=<read from keys/evm-testnet-shared.json, never echoed/logged> \
forge script script/Deploy.s.sol \
  --rpc-url https://sepolia.base.org \
  --broadcast \
  --out <isolated forge-out dir> \
  --cache-path <isolated forge-cache dir>
```

Result (`forge script` reported `ONCHAIN EXECUTION COMPLETE & SUCCESSFUL`;
addresses and tx hashes below are taken from the broadcast artifact,
`broadcast/Deploy.s.sol/84532/run-latest.json`, not from the console log):

| Contract | Address | Deploy tx | Block | Gas used | Status |
|---|---|---|---|---|---|
| `AuthorityRiskOracle` | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | `0xbf2875015bb893126cb117150ef9cbf7cef7573f5bfef616472012838572e746` | 46993519 | 912110 | success |
| `ExampleConsumer` | `0xB7403b365a58B31Ae030DB423f6B703AD67f003a` | `0x5af09dd155632c7b7adf5d5e541226f40d7c64980e1802976e7e51e04bdc1fe1` | 46993519 | 315937 | success |

Admin/Updater role on the oracle: `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`
(the deployer itself, per `script/Deploy.s.sol`).

Verified on-chain (not assumed) right after deployment:

```
cast code 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 --rpc-url https://sepolia.base.org
```

returned non-empty bytecode (7241 characters incl. the trailing newline, i.e.
real deployed code, not an empty/failed contract). Same check on
`ExampleConsumer` also returned non-empty bytecode (2421 characters).

## Pushing scores -- real send, 2026-09-18 (dry-run also still supported)

`deploy/push_scores.py`, modeled on the repo root's `scripts/update_scores.py`.
`--dry-run` re-derives every score from `chains/base-ecosystem/scorers.py`
against Base MAINNET (read-only) and encodes (but never sends) the
`updateScores(address[],AuthorityScore[])` calldata; no `PRIVATE_KEY` needed:

```
READ_RPC_URL=https://mainnet.base.org \
python3 chains/base-ecosystem/deploy/push_scores.py --dry-run
```

The real send (run for the first time on 2026-09-18, against the oracle
deployed above):

```
READ_RPC_URL=https://mainnet.base.org \
ORACLE_RPC_URL=https://sepolia.base.org \
ORACLE_ADDRESS=0x50840a7667baEa9D05ad4ae3dCeb384724b58720 \
PRIVATE_KEY=<read from keys/evm-testnet-shared.json, never echoed/logged> \
python3 chains/base-ecosystem/deploy/push_scores.py
```

Result: `Sent updateScores() tx:
0xd7483e0a50f292e8da859dbc37895f3fd7f7f1bba2c413bb137f5c483ca897f0`,
confirmed in block 46993594, status `success`. Scores re-derived live from
Base mainnet at push time and written on-chain for 5 targets:

| Target | Composite | Cross-exposure |
|---|---|---|
| Morpho Blue (singleton, Base) | 55/100 | 100/100 |
| Aave V3 Base (PoolAddressesProvider) | 71/100 | 80/100 |
| Aerodrome Finance PoolFactory (Base) | 46/100 | 100/100 |
| Uniswap V3 Factory (Base) | 85/100 | 100/100 |
| Compound V3 (Comet, USDC market, Base) | 80/100 | 100/100 |

`methodologyHash` written on-chain: `0x758072e35c77f0ad21afcf9baa2a5508bfbdbd2d0391c5704b6302cb74e7cb34`.

### On-chain readback (independent verification)

Read directly from the deployed oracle, not assumed from the push script's
own output:

```
cast call 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 \
  "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))" \
  0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D \
  --rpc-url https://sepolia.base.org
```

returned `(65, 100, 50, 100, 80, 71, 1789755472, 0x758072e35c77f0ad21afcf9baa2a5508bfbdbd2d0391c5704b6302cb74e7cb34)`
for Aave V3 Base -- `compositeScore = 71` and the `methodologyHash` both
match exactly what `push_scores.py` sent, confirming the write is real and
readable, not just a successful-looking transaction.

### Balance after deploy + push

| RPC | Balance |
|---|---|
| `https://sepolia.base.org` | 0.014989152697210186 ETH |
| `https://base-sepolia-rpc.publicnode.com` | 0.014989152697210186 ETH |

Total spent across the 2 deploy transactions + 1 `updateScores()` transaction:
~0.0000108 ETH (Base Sepolia gas is very cheap). Plenty of headroom remains
in the shared key for the other 2 EVM ecosystems still in `deploy_testnet`
(ethereum-l1, arbitrum-ecosystem) that share this same key file but deploy
on their own separate testnets.

## Maintenance run 2026-09-19 -- 9 tracked targets

Push tx `0xc412f6dc76299177db63ab207a9609ae5124215d2ac52ac280e98fa9a1c14fa1`
(block 47033666, status success). The 2026-09-18 table above ("5 targets") is kept
as the historical first push. Current on-chain state, read back live on both Base
Sepolia RPCs (`data/oracle_readback_2026-09-19.csv`):

| # | Target | Composite | Cross-exposure |
|---|---|---|---|
| 0 | Morpho Blue (singleton, Base) | 55/100 | 80/100 |
| 1 | Aave V3 Base (PoolAddressesProvider) | 71/100 | 80/100 |
| 2 | Aerodrome Finance PoolFactory (Base) | 46/100 | 80/100 (CORRECTION, was 100) |
| 3 | Uniswap V3 Factory (Base) | 85/100 | 100/100 |
| 4 | Compound V3 (Comet, USDC market, Base) | 80/100 | 100/100 |
| 5 | Aerodrome Slipstream CLFactory (Base) | 46/100 | 80/100 |
| 6 | Uniswap V2 Factory (Base) | 85/100 | 100/100 |
| 7 | Uniswap V4 PoolManager (Base) | 85/100 | 100/100 |
| 8 | Moonwell Comptroller (Unitroller, Base) | 71/100 | 100/100 |

Details, sources and the audit of index 0: `data/scored_targets_2026-09-19-maintenance.md`.
