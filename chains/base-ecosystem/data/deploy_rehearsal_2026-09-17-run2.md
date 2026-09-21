# Base Ecosystem -- deploy_testnet rehearsal, 2026-09-17 evening (run 2, attempt 1)

Phase: `deploy_testnet`. This is the second rehearsal for Base Ecosystem, run
after the afternoon session (17 commits, 14:39-18:51) changed
`chains/base-ecosystem/scorers.py` twice since the morning's rehearsal (see
`data/correction_2026-09-17-adversarial-bug-hunt.md`'s per-target failure
isolation fix, and the same-day cross-ecosystem Aave guardian overlap fix
that changed Aave V3 Base's `crossExposureScore` from a flat 100 to a
live-derived 80). Re-run in full rather than reused, because the scorer
itself changed.

## 1. Real Base Sepolia balance check (2 independent public RPCs)

| RPC | Chain ID returned | Balance (wei) |
|---|---|---|
| `https://sepolia.base.org` | 84532 | 0 |
| `https://base-sepolia-rpc.publicnode.com` | 84532 | 0 |

Deployer address: `0xA08a76457b758aFF9702dBf5b870679E1232B715`
(`keys/evm-testnet-shared.json`; private key never printed, logged, or
written to this repo). Still 0 wei, same as the morning's finding. No
faucet used (all listed Base Sepolia faucets require a captcha or an
account login, both explicitly out of scope for an agent).

## 2. Build and test (fresh out/cache dirs, this pass)

`forge build` -- `Compiler run successful!`, no errors (a few pre-existing
lint warnings only, unrelated to this ecosystem's files).

`forge test` -- 20/20 tests passed, 0 failed, 0 skipped, across
`AuthorityRiskOracle.t.sol` (15 tests) and `ExampleConsumer.t.sol` (5 tests).
(The morning's rehearsal reported 16; the afternoon session added 4 more
tests project-wide -- confirmed unrelated to Base Ecosystem's own files by
reading the afternoon's commit list, which touched only `scripts/lib/`,
`chains/arbitrum-ecosystem/`, `chains/ethereum-l1/`, `chains/hyperliquid/`,
`chains/solana/`, `chains/tempo/`, `chains/zcash/` for its test additions.)

## 3. Fresh dry-run against live Base mainnet (chain 8453)

`python3 chains/base-ecosystem/scripts/dry_run.py`, run live this pass
against `https://mainnet.base.org`, block ~51,437,802:

| Protocol | adminKey | multisig | timelock | crossExposure | composite |
|---|---|---|---|---|---|
| Morpho Blue (singleton) | 65 | 95 | 0 | 100 | **55** |
| Aave V3 Base (PoolAddressesProvider) | 65 | 100 | 50 | **80** | **71** |
| Aerodrome Finance PoolFactory | 65 | 65 | 0 | 100 | **46** |
| Uniswap V3 Factory (Base) | 80 | 100 | 75 | 100 | **85** |
| Compound V3 (Comet, USDC market) | 75 | 100 | 65 | 100 | **80** |

All 5 composite scores match `data/scored_targets_2026-09-16.md` exactly.
The one real change since that file was written: Aave V3 Base's
`crossExposureScore` is now live-derived at **80** (was a flat,
not-computed 100) -- the scorer now live-reads the `PayloadsController`
guardian Safe's owners and compares them against a dated snapshot of
Arbitrum's own Aave V3 guardian Safe, finding the identical 9-signer,
5-of-9 committee behind both chains' emergency-cancel path (see
`scripts/lib/cross_ecosystem_overlap.py` and
`data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md` at the
repo root for the full finding). `compositeScore` itself is unaffected
(crossExposureScore is a separate dimension, deliberately not folded into
it), but the underlying evidence is materially different from the morning's
rehearsal, which is why this rehearsal was re-run rather than reused.

## 4. Full dress rehearsal on a local Base Sepolia fork (anvil)

Because the deployer is still unfunded on real Base Sepolia AND the scorer
changed since the morning's rehearsal, the full `deploy_testnet` pipeline
was rehearsed end to end again on a fresh local anvil fork of real Base
Sepolia state (`chains/base-ecosystem/deploy/rehearsal_fork.sh`, port 8547,
confirmed free before and after the run -- no collision with the parallel
Ethereum L1 agent's own fork on port 8546). Anvil's own well-known public
default dev account (`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`) was used
to sign the fork-local deploy and push transactions -- **not**
`keys/evm-testnet-shared.json`, which was never touched, read into a
variable, or referenced by this script at all.

Steps and live results (see
`runs/2026-09-17-run2/base-ecosystem/rehearsal_run_output.txt` for the full
raw output):

1. Fork source confirmed as Base Sepolia (chain 84532) before forking.
2. Anvil fork started on port 8547; fork itself confirmed as chain 84532.
3. `script/Deploy.s.sol` deployed the unmodified, shared
   `AuthorityRiskOracle` + `ExampleConsumer` contracts to the fork:
   - `AuthorityRiskOracle`: `0x5411fB039b41edc1C30d89797D56A0fc075EC7Ea`
   - `ExampleConsumer`: `0xF95Fd90bFC30351e899AdAd98Fe1e5363786a6eE`
4. Confirmed live: `hasRole(UPDATER_ROLE, deployer) = true` on the freshly
   deployed oracle.
5. `chains/base-ecosystem/deploy/push_scores.py` re-derived all 5 scores
   live from real Base mainnet (chain 8453, block ~51,437,849 -- one block
   later than step 3's read, expected since these are two separate live
   reads a few seconds apart) and pushed them via `updateScores()` to the
   fork oracle. Transaction confirmed in block 46948377, status success.
6. Read back `getScore()` for all 5 targets from the fork oracle and
   compared each to an independently, freshly re-derived score computed in
   the same script run: **all 5 matched exactly**, including Aave V3 Base's
   `crossExposureScore=80`.
7. Anvil stopped cleanly at the end of the run (port 8547 free both before
   and after).

## 5. What this does and does not prove

Proves: the exact same contracts, the exact same `Deploy.s.sol`, and the
exact same `push_scores.py` that would run against real Base Sepolia work
correctly end to end, including the newly-changed Aave cross-exposure logic,
against a faithful fork of that same network's current state. The only
thing not exercised is signing with the real shared throwaway key and
broadcasting to the real public Base Sepolia network -- which cannot happen
without a funded deployer.

Does not prove: nothing about real Base Sepolia network conditions (gas
price volatility, real block times) that a fork with instant mining
approximates but does not reproduce exactly.

## Reproduction

```
bash chains/base-ecosystem/deploy/rehearsal_fork.sh
```

Re-run any time; every step is deterministic given the same live chain
state, and the script refuses to proceed if the fork source or the local
fork ever report a chain ID other than 84532.
