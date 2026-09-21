# Base Ecosystem -- deploy_testnet rehearsal, 2026-09-18

Phase: `deploy_testnet` (maintained, not yet advanced). Third rehearsal for
Base Ecosystem, run after `6db58ac` ("base: trace Aerodrome Voter's
authority, close open question") changed `chains/base-ecosystem/scorers.py`
since the previous rehearsal (`data/deploy_rehearsal_2026-09-17-run2.md`).
That commit closes a standing open question about Aerodrome's `Voter`
contract (confirms `Voter.governor()` is the exact same Safe already scored
as `pauser()`/`feeManager()`, and discloses `emergencyCouncil()` as a
separate, bounded authority) but explicitly does not change any composite
score. Re-run in full anyway, same discipline as the previous two
rehearsals: re-run whenever the scorer changes, don't reuse a stale result.

## 1. Real Base Sepolia balance check (2 independent public RPCs)

| RPC | Chain ID returned | Balance (wei) |
|---|---|---|
| `https://sepolia.base.org` | 84532 | 0 |
| `https://base-sepolia-rpc.publicnode.com` | 84532 | 0 |

Deployer address: `0xA08a76457b758aFF9702dBf5b870679E1232B715`
(`keys/evm-testnet-shared.json`; private key never printed, logged, or
written to this repo -- checked mechanically below). Still 0 wei, unchanged
since 2026-09-16. No faucet used (every listed Base Sepolia faucet requires
a captcha or an account login, both out of scope for an agent; per this
key's own file, funding is Spap's call to make manually, never requested
autonomously).

Base mainnet (read-only, never a deploy target) reconfirmed live as chain
**8453** via `cast chain-id --rpc-url https://mainnet.base.org`.

## 2. Build and test (fresh out/cache dirs, this pass)

`forge build` -- `Compiler run successful!`, no errors (a handful of
pre-existing lint warnings only, unrelated to this ecosystem's files).

`forge test` -- 20/20 tests passed, 0 failed, 0 skipped, across
`AuthorityRiskOracle.t.sol` (15 tests) and `ExampleConsumer.t.sol` (5 tests),
same count as 2026-09-17 run 2 -- no test files changed since.

## 3. Fresh dry-run against live Base mainnet (chain 8453)

`python3 chains/base-ecosystem/scripts/dry_run.py`, run live this pass
against `https://mainnet.base.org`, block ~51,473,443:

| Protocol | adminKey | multisig | timelock | crossExposure | composite |
|---|---|---|---|---|---|
| Morpho Blue (singleton) | 65 | 95 | 0 | 100 | **55** |
| Aave V3 Base (PoolAddressesProvider) | 65 | 100 | 50 | **80** | **71** |
| Aerodrome Finance PoolFactory | 65 | 65 | 0 | 100 | **46** |
| Uniswap V3 Factory (Base) | 80 | 100 | 75 | 100 | **85** |
| Compound V3 (Comet, USDC market) | 75 | 100 | 65 | 100 | **80** |

All 5 composite scores are **unchanged** from `data/scored_targets_2026-09-16.md`
and from the 2026-09-17 run-2 rehearsal, exactly as commit `6db58ac`'s message
said they would be. The Aerodrome row now additionally live-verifies
`Voter.governor()` against `pauser()`/`feeManager()` every run (see the
commit and `data/finding_2026-09-18-aerodrome-voter-governor-identity.md`
for the full trace) and reads `emergencyCouncil()` for disclosure, but this
is a scope-of-disclosure change, not a scoring change. `dry_run.py` reported
zero targets with an unexplained "None" note.

## 4. Full dress rehearsal on a local Base Sepolia fork (anvil)

Because the deployer is still unfunded on real Base Sepolia AND the scorer
changed since the last rehearsal, the full `deploy_testnet` pipeline was
rehearsed end to end again on a fresh local anvil fork of real Base Sepolia
state (`chains/base-ecosystem/deploy/rehearsal_fork.sh`, port 8547,
confirmed free before and after the run -- the parallel Arbitrum agent's own
fork this run used port 8548, no collision). Anvil's own well-known public
default dev account (`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`) signed
the fork-local deploy and push transactions -- **not**
`keys/evm-testnet-shared.json`, which was never touched, read into a
variable, or referenced by this script at all.

Steps and live results (see
`runs/2026-09-18/base-ecosystem/rehearsal_run_output.txt` for the full raw
output):

1. Fork source confirmed as Base Sepolia (chain 84532) before forking.
2. Anvil fork started on port 8547; fork itself confirmed as chain 84532.
3. `script/Deploy.s.sol` deployed the unmodified, shared
   `AuthorityRiskOracle` + `ExampleConsumer` contracts to the fork:
   - `AuthorityRiskOracle`: `0x0ec06f497458916BF527Cf79584e96d2d0f88e89`
   - `ExampleConsumer`: `0x1ae0DeC051D518C412740cd6AFBAE3023B2Ad4Ef`
4. Confirmed live: `hasRole(UPDATER_ROLE, deployer) = true` on the freshly
   deployed oracle.
5. `chains/base-ecosystem/deploy/push_scores.py` re-derived all 5 scores
   live from real Base mainnet (chain 8453, block ~51,473,443) and pushed
   them via `updateScores()` to the fork oracle. Transaction
   `0x7bc2f9ca17a0ae3f0aff76c6bdc92e4db757d9885bf948687f2c75dce8fd712a`
   confirmed in block 46983971, status success.
6. Read back `getScore()` for all 5 targets from the fork oracle and
   compared each to an independently, freshly re-derived score computed in
   the same script run: **all 5 matched exactly** (55/71/46/85/80).
7. Anvil stopped cleanly at the end of the run (port 8547 free both before
   and after).

## 5. What this does and does not prove

Proves: the exact same contracts, the exact same `Deploy.s.sol`, and the
exact same `push_scores.py` that would run against real Base Sepolia work
correctly end to end against a faithful fork of that network's current
state, including today's Aerodrome disclosure change. The only thing not
exercised is signing with the real shared throwaway key and broadcasting to
the real public Base Sepolia network -- which cannot happen without a
funded deployer.

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
