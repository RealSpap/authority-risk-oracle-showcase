# Arbitrum Ecosystem -- deployment guide (Arbitrum Sepolia, chain 421614)

Phase: `deploy_testnet` -- **deployed for real on 2026-09-18**. The funding
blocker documented in every earlier attempt below is resolved: the shared
EVM testnet key was refunded (after being rotated to a new address, see
"Deploy key" below) and this run actually ran
`forge script script/Deploy.s.sol --broadcast` against Arbitrum Sepolia,
confirmed the deployed bytecode on-chain via `eth_getCode`, pushed real
scores via `deploy/push_scores.py` (no `--dry-run`), and read at least one
score back via `getScore()` to confirm the written data matches. See "Real
deployment (2026-09-18)" below for addresses, tx hashes, and balances. The
sections further down (build/test, prior dry-runs) are kept as the
historical record of the `scoring_build` -> `deploy_testnet` work that led
here.

Latest state: the oracle was re-pushed on 2026-09-20 (Radiant LendingPool
re-scored, tx `0x308ad2c8...fbd23`, block 310697409). The current on-chain
table is in "2026-09-20 re-push" at the end of this file.

## Network

| | |
|---|---|
| Network | Arbitrum Sepolia (testnet) |
| Chain ID | **421614** -- confirmed live this run via `cast chain-id --rpc-url https://sepolia-rollup.arbitrum.io/rpc` (returned `421614`) |
| Public RPC (official) | `https://sepolia-rollup.arbitrum.io/rpc` |
| Explorer | https://sepolia.arbiscan.io |
| Faucets | https://www.alchemy.com/faucets/arbitrum-sepolia , Arbitrum's own docs list of Sepolia faucets: https://docs.arbitrum.io/build-decentralized-apps/reference/node-providers#faucets |

Arbitrum One mainnet (read-only, for the scorer -- never a deploy target) is
chain **42161**, also confirmed live this run (`cast chain-id --rpc-url
https://arb1.arbitrum.io/rpc` returned `42161`).

## Contract

`src/AuthorityRiskOracle.sol` is used unmodified -- same contract already
deployed for Robinhood Chain testnet (see the repo root `README.md`'s
"Status" section) and prepared identically for Base Sepolia. No
Arbitrum-specific Solidity changes are needed: the contract is chain-agnostic
(`AccessControl`-gated `UPDATER_ROLE`, `updateScore`/`updateScores`,
`getScore`, `isStale`).

`script/Deploy.s.sol` (repo root, also reused unmodified) deploys
`AuthorityRiskOracle` with `admin = deployer` and a demo `ExampleConsumer`
wired to it.

The `updateScores(address[],AuthorityScore[])` function selector was
verified live this run via
`cast sig "updateScores(address[],(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)[])"`
-> `0x5fb3feaf`, matching the same selector present in the calldata that
`deploy/push_scores.py --dry-run` actually encodes below (byte-for-byte, not
assumed).

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

Result this run (2026-09-17, scoring_build attempt 1): `Compiler run
successful!`, 16/16 tests passed across `AuthorityRiskOracle.t.sol` and
`ExampleConsumer.t.sol` (0 failed, 0 skipped) -- identical test count and
result to the Base Ecosystem sibling pass, confirming the unmodified
contract behaves the same regardless of which chain's deploy this README
targets. See `runs/2026-09-17/arbitrum-ecosystem/claims_attempt1.txt` for
the exact re-runnable commands.

## Real deployment (2026-09-18)

**Deploy key.** Uses the shared EVM testnet key, `keys/evm-testnet-shared.json`.
**Public address is now `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`.** The
address documented in every earlier section of this README and in
`data/deploy_rehearsal_*.md`,
`0xA08a76457b758aFF9702dBf5b870679E1232B715`, is a **superseded, abandoned
key** (rotated 2026-09-18 after it was possibly exposed in a transcript; it
holds 0 funds and is never used again). Wherever this file still mentions
the old address below, it is preserved as a dated historical record of what
that attempt actually ran, not a current instruction. The private key
itself was never printed, logged, or committed at any point.

**Deployed addresses** (from
`broadcast/Deploy.s.sol/421614/run-latest.json`, not assumed):

| Contract | Address |
|---|---|
| `AuthorityRiskOracle` | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` |
| `ExampleConsumer` | `0xB7403b365a58B31Ae030DB423f6B703AD67f003a` |

**Deploy transactions** (both `status: 1`, i.e. success, confirmed via
`cast receipt`):

- `AuthorityRiskOracle` create: `0x85011d733a0cb4c007bf991678e5f4d3bb87e2a3664c0b199faa7b04576039a8` (block 310267811, gasUsed 918616)
- `ExampleConsumer` create: `0x12992165e062ae5006310135e426b4a5a57ebff08e742895c72bf2a74e470a0f` (block 310267821)

**On-chain bytecode check:** `cast code 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 --rpc-url https://sepolia-rollup.arbitrum.io/rpc`
returns a 7,241-character hex string of non-empty runtime bytecode (3,619
bytes; `ExampleConsumer` returns a 2,421-character/1,209-byte string) -- the
contract genuinely exists on-chain, not just in the broadcast log.

**Score push (real, not `--dry-run`):**
`ORACLE_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc ORACLE_ADDRESS=0x50840a7667baEa9D05ad4ae3dCeb384724b58720 READ_RPC_URL=https://arb1.arbitrum.io/rpc PRIVATE_KEY=<from keys/evm-testnet-shared.json> python3 chains/arbitrum-ecosystem/deploy/push_scores.py`
sent `updateScores()` tx
`0x1c6f9bb9644eaaed87d21ee5fe9d594d9b04bc35b6e374541ba4caf089a85649`,
confirmed in block 310268519, `status: 1` (success), 5 `ScoreUpdated`-style
log events (one per target), independently re-confirmed via `cast receipt`.
Composites pushed: 71 (GMX V2 RoleStore), 31 (Camelot AMMv3 Factory), 69
(Radiant LendingPool), 64 (Arbitrum Security Council Safe), 71 (Aave V3
Pool) -- identical to every prior dry-run's numbers, confirming the scorer
didn't drift between the last dry-run and the real push.

> SUPERSEDED 2026-09-20: the Radiant composite of 69 above is the value pushed
> on 2026-09-18 and is kept as the record of that push. The 2026-09-20 re-push
> (tx `0x308ad2c8...fbd23`, block 310697409) replaced it: the Sepolia oracle now
> holds 55 for the same target, equal to what `score_radiant_lendingpool()`
> returns (see "2026-09-20 re-push" at the end of this file).

Two earlier send attempts in this same run failed with `"max fee per gas
less than block base fee"` (RPC error -32000) -- Arbitrum Sepolia's base fee
was observed swinging roughly 192M-208M wei across calls a few seconds
apart, and a bare `oracle_w3.eth.gas_price` sample intermittently landed
below the base fee by the time the tx was actually submitted (the live
Arbitrum One scoring round-trip in between takes a few seconds). Both
failed attempts were rejected by the node **before** being included in a
block -- confirmed via `cast nonce` staying at 2 (matching the post-deploy
state) and the balance being unaffected between attempts, so nothing was
silently lost. `deploy/push_scores.py` was patched to multiply the sampled
gas price by 1.25x to absorb that drift (see the comment at its `gas_price`
line); the third attempt with that fix succeeded on the first try.

**Read-back verification.** `getScore()` called directly against the
deployed contract for all 5 targets matches what was pushed, e.g. for GMX
V2 RoleStore (`0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72`):
`cast call 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))" 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 --rpc-url https://sepolia-rollup.arbitrum.io/rpc`
returns `(65, 90, 60, 100, 100, 71, 1789755413, 0x6acfe9c5f210a6d1e4cd50a30ea19b8436bcee1b948e633d2de153bd4dd78915)`
-- `compositeScore=71` and `methodologyHash` both match what
`push_scores.py` printed before sending. `isStale()` on the same target
returns `false`. All 5 targets were checked, not just this one; all 5
`compositeScore` values matched (71, 31, 69, 64, 71).

**Balance after deploy + push:** started this run at 0.015 ETH (15,000,000,000,000,000
wei, confirmed via two independent RPCs before touching anything), ended at
**0.014658615923490000 ETH** after the deploy (2 creates) and the one
successful `updateScores()` send -- roughly 0.00034 ETH spent in total,
consistent with the ~0.00063 ETH estimated by `forge script`'s simulation
(no `--broadcast`) run beforehand. No funding was requested at any point;
the balance was already sufficient going in.

## Deploy key and current balance (historical -- 2026-09-17/18, before funding)

The paragraphs below are preserved as-written from the attempts before the
2026-09-18 real deploy above; they describe the **old, now-abandoned**
deployer address `0xA08a76457b758aFF9702dBf5b870679E1232B715` and its 0
balance, not the current state.

Uses the shared EVM testnet key, `keys/evm-testnet-shared.json` (public
address `0xA08a76457b758aFF9702dBf5b870679E1232B715`; private key never
copied into this repo, never printed to any output or log). Balance on
Arbitrum Sepolia, checked live this run via
`cast balance 0xA08a76457b758aFF9702dBf5b870679E1232B715 --rpc-url https://sepolia-rollup.arbitrum.io/rpc`:

**0 wei.**

Re-checked this run (2026-09-17 evening, `deploy_testnet` attempt 1) on two
independent public RPCs, both agreeing on chain ID 421614 and 0 balance:

```
cast balance 0xA08a76457b758aFF9702dBf5b870679E1232B715 --rpc-url https://sepolia-rollup.arbitrum.io/rpc
# -> 0
cast balance 0xA08a76457b758aFF9702dBf5b870679E1232B715 --rpc-url https://arbitrum-sepolia-rpc.publicnode.com
# -> 0
```

Still an **open thread, not a blocker**: the address needs Arbitrum Sepolia
ETH from a faucet (see table above, no captcha/login faucet used, none
requested autonomously) before the actual `forge script ... --broadcast`
deploy can run. No deploy attempted this pass; transition stays
`deploy_testnet -> deploy_testnet` (maintained).

### What was done instead this run (balance still 0)

The scorer (`chains/arbitrum-ecosystem/scorers.py`) changed twice since the
composites documented below were last recorded (commits `37d7d81` "Fix 18
real bugs..." and `e4016a6` "Extend cross-ecosystem signer overlap to
Arbitrum...", both same day, both touching this file) -- most notably
`score_aave_v3_pool_arbitrum()` now live-resolves the Aave V3 Arbitrum
GOVERNANCE_GUARDIAN Safe's owners and compares them against Base's sibling
Safe, changing that target's `crossExposureScore` from a flat 100 to 80.
Since the scorer changed since the last repetition, this run redid the
dry-run against live Arbitrum One mainnet AND repeated it against a pinned
Arbitrum One fork (`anvil --fork-url https://arb1.arbitrum.io/rpc
--fork-block-number 506161882`) to confirm the scorer is deterministic and
reproducible, not just "ran once and looked right":

```
READ_RPC_URL=https://arb1.arbitrum.io/rpc python3 chains/arbitrum-ecosystem/deploy/push_scores.py --dry-run
READ_RPC_URL=http://127.0.0.1:8547 python3 chains/arbitrum-ecosystem/deploy/push_scores.py --dry-run
```

Both runs, live and forked at the same pinned block, produced identical
composite scores (71, 31, 69, 64, 71) and identical `crossExposureScore`
per target (100, 100, 100, 100, 80 for GMX/Camelot/Radiant/Security
Council/Aave respectively) and byte-identical `updateScores()` calldata
apart from the `lastUpdated` timestamp field (which is `time.time()` at
call time by design, not chain state). The composite scores are unchanged
from the `scoring_build`-phase figures in "Pushing scores" below --
`crossExposureScore` is not one of the three inputs to `_composite()`
(`0.4*adminKey + 0.3*multisig + 0.3*timelock`) for this ecosystem's
scorers, so the cross-exposure fix changed a disclosed field without
moving the number that would be pushed on-chain. Full output saved in
`runs/2026-09-17-run2/arbitrum-ecosystem/dryrun_live_attempt1.txt` and
`runs/2026-09-17-run2/arbitrum-ecosystem/dryrun_anvil_fork_attempt1.txt`
(outside this repo, per this pipeline's run-folder convention).

> UPDATED 2026-09-20: the Radiant composite of 69 in the list above is what
> the scorer returned on that date. The scorer now returns 55 for Radiant
> (admin 65, multisig 95, timelock 0), and the Sepolia oracle holds that value
> since the 2026-09-20 re-push. Nothing else in the Arbitrum scorer output
> moved on 2026-09-20 (the GMX 71 -> 22 correction is the separate 2026-09-19
> change described below). See "2026-09-20 re-push" at the end of this file.

## Deploy command (historical wording -- this now HAS run, see "Real deployment" above)

This is the exact command that was actually run on 2026-09-18, with the new
key's address as the resulting `admin`/`Updater`:

```
PRIVATE_KEY=<from keys/evm-testnet-shared.json, never echoed/logged> \
forge script script/Deploy.s.sol \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --broadcast \
  --out <this run's forge-out dir> \
  --cache-path <this run's forge-cache dir>
```

Resulting addresses are recorded in "Real deployment (2026-09-18)" above,
taken from `broadcast/Deploy.s.sol/421614/run-latest.json`.

## Pushing scores (real send now works -- see "Real deployment" above; dry-run still available)

See `deploy/push_scores.py`, modeled on the repo root's
`scripts/update_scores.py` and the Base Ecosystem sibling script. Supports
`--dry-run`, which re-derives every score from
`chains/arbitrum-ecosystem/scorers.py` against Arbitrum One MAINNET (read
target state) and encodes the `updateScores(address[],AuthorityScore[])`
calldata that WOULD be sent to the oracle on Arbitrum Sepolia, printing the
calldata hex without ever building a transaction, signing, or sending
anything. No `PRIVATE_KEY` is required for `--dry-run`.

```
READ_RPC_URL=https://arb1.arbitrum.io/rpc \
python3 chains/arbitrum-ecosystem/deploy/push_scores.py --dry-run
```

Confirmed on 2026-09-17 (historical, see the 2026-09-19 section at the end for the current 9 targets): 5 targets scored (composite scores 71, 31, 69, 64, 71 --
see `data/scored_targets_2026-09-17.md`), calldata encoded to 1,572 bytes,
selector `0x5fb3feaf` at the start of the calldata matching the `cast sig`
value above exactly.

The oracle is now deployed and the key is funded (see "Real deployment"
above), so the same script, without `--dry-run` and with
`ORACLE_RPC_URL`/`ORACLE_ADDRESS`/`PRIVATE_KEY` set, has sent the real
transaction, following the exact same pattern as `scripts/update_scores.py`.
`--dry-run` remains available and still works exactly as described above
for re-deriving/encoding without sending.

## 2026-09-18 run, attempt 2 (historical -- earlier same day, still pre-funding)

Re-checked from scratch rather than assumed: `git log a58cde8..HEAD --
chains/arbitrum-ecosystem/` is empty, so nothing about this ecosystem's
scorer or deploy script changed since the 2026-09-17 evening run below --
this pass exists to re-confirm the balance and the pipeline still reproduce,
not to chase new drift.

- Balance re-checked on both RPCs: still **0 wei** on
  `https://sepolia-rollup.arbitrum.io/rpc` and
  `https://arbitrum-sepolia-rpc.publicnode.com` (chain ID 421614 on both).
  Same open thread as every prior attempt: needs Arbitrum Sepolia ETH from a
  faucet before `forge script ... --broadcast` can run; no captcha/login
  faucet used or requested.
- `forge build` / `forge test`: `Compiler run successful!`, 20/20 tests
  passed (15 in `AuthorityRiskOracle.t.sol` + 5 in `ExampleConsumer.t.sol`,
  0 failed, 0 skipped) -- same suite, same result as prior passes.
- `push_scores.py --dry-run` replayed against live Arbitrum One mainnet
  (block 506442526) and again against a pinned anvil fork of that exact
  block: identical composites (71, 31, 69, 64, 71), identical
  `crossExposureScore` per target (100, 100, 100, 100, 80), and
  byte-identical 1,572-byte `updateScores()` calldata apart from the
  `lastUpdated` timestamp field (which is wall-clock time at call time by
  design). Selector `0x5fb3feaf` and `methodologyHash` re-verified
  independently via `cast sig` and a standalone `Web3.keccak` call, both
  matching. Full output and the re-runnable claims log are in
  `runs/2026-09-18/arbitrum-ecosystem/` (outside this repo, per this
  pipeline's run-folder convention).
- No transaction built, signed, or sent; no `PRIVATE_KEY` read (`--dry-run`
  returns before that line, confirmed by source inspection). No `forge
  script ... --broadcast` attempted, no broadcast artifacts produced. The
  anvil fork process was stopped after use. Transition stays
  `deploy_testnet -> deploy_testnet` (maintained) -- proposed via
  maker-checker, not decided unilaterally.

## 2026-09-18 run, attempt 3 (same day, later -- the real deploy)

Later the same day, the key was rotated (old address abandoned, presumed
possibly exposed in a transcript) and the new address
`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` was actually funded with
0.015 ETH on Arbitrum Sepolia -- the first time any balance check in this
file's history came back non-zero. That funding made the real deploy and
push possible; see "Real deployment (2026-09-18)" near the top of this file
for the addresses, tx hashes, the gas-price bug hit and fixed, the
`getScore()` read-back, and the resulting balance. `deploy_testnet` is
complete for this ecosystem as of this attempt.

## 2026-09-19 maintenance run: rotation audit index 0 (CORRECTION) + 4 new targets

This is the first maintenance-phase run. Full traces are in
`data/rotation_audit_2026-09-19-index0-gmx-rolestore.md` and
`data/scored_targets_2026-09-19-maintenance.md`.

- **CORRECTION, index 0 (GMX V2 RoleStore): 71 -> 22.** The old scorer
  checked a `ConfigTimelockController` (`0xC77E...`) that holds no role on
  the live RoleStore. The live path runs through TimelockConfig
  `0xE7706986...` -> controller `0x2Dd99f39...`. `TIMELOCK_ADMIN` on the
  RoleStore includes a bare EOA (`0xE014cbD6...`, GMX's own
  `timelock_admin_2`) that can queue a grant of any role and execute it
  after 24 h. The 5-of-8 Safe has only a veto. Verified on 2 RPCs.
- **4 new targets**, appended as indices 5-8: Compound V3 Comet USDC (80),
  Pendle V2 (43, crossExposure 60: same 3-of-5 Safe as the tracked Plasma
  and Robinhood Chain Pendle roots), Fluid Liquidity (59, crossExposure 80:
  same 6-of-12 Avocado multisig as Plasma's Fluid proposer), Uniswap V3
  Factory (85, L1 DAO via the Arbitrum bridge alias).
- `updateScores()` tx `0xa934822b3ed2959761641e312b4646890243ede3f82648e433fecfea1d57d85b`
  (block 310,589,900, status 1). `trackedTargetsCount()` is now 9.
  `getScore()` read back on 2 Sepolia RPCs matches every pushed value.
- Tests: `scripts/lib/tests/test_arbitrum_ecosystem_scorers.py` now has 43 tests, all passing
  (the full `scripts/lib/tests` suite passed as well).

Scores on the oracle after the 2026-09-19 push (read back 2026-09-19, record
in `data/oracle_scores_2026-09-19.csv`, 9 targets). Kept as history: row 2
(Radiant) was superseded by the 2026-09-20 re-push, the current table is in
the last section of this file.

| Idx | Target | adminKey | multisig | timelock | crossExp | composite |
|---|---|---|---|---|---|---|
| 0 | GMX V2 RoleStore | 10 | 0 | 60 | 100 | **22** (CORRECTED from 71) |
| 1 | Camelot AMMv3 Factory | 50 | 35 | 0 | 100 | **31** |
| 2 | Radiant LendingPool | 55 | 100 | 55 | 100 | **69** |
| 3 | Arbitrum Security Council Emergency Safe | 55 | 100 | 40 | 100 | **64** |
| 4 | Aave V3 Pool (PoolAddressesProvider) | 65 | 100 | 50 | 80 | **71** |
| 5 | Compound V3 Comet USDC | 75 | 100 | 65 | 100 | **80** |
| 6 | Pendle V2 Router + MarketFactoryV6 | 65 | 55 | 0 | 60 | **43** |
| 7 | Fluid Liquidity | 65 | 55 | 55 | 80 | **59** |
| 8 | Uniswap V3 Factory | 80 | 100 | 75 | 100 | **85** |

Earlier sections of this file that say "5 targets" or give composite 71
for GMX describe the 2026-09-17/18 state. They are kept as history.

> SUPERSEDED 2026-09-20: the table above is the state pushed to the Sepolia
> oracle on 2026-09-19 and stays correct as that record. Its row 2 (Radiant)
> is no longer on the oracle: the 2026-09-20 re-push wrote 65 / 95 / 0 / 100 /
> 100 / **55**. See the next section.

## 2026-09-20 re-push: Radiant LendingPool re-scored and pushed on-chain

| Field | Value |
|---|---|
| Oracle | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` (Arbitrum Sepolia) |
| `updateScores()` tx (9 targets) | `0x308ad2c8fa527a0e5c30139b6b154ff48462cd046df9840a17f25775c21fbd23` |
| Block | 310697409, status 1, gasUsed 183,371 |
| `lastUpdated` | 1789863454 = 2026-09-20 00:17:34 UTC (all 9 targets) |
| What changed | Only Radiant LendingPool (index 2): 55 / 100 / 55 / 100 / 100 / 69 -> 65 / 95 / 0 / 100 / 100 / **55**. The other 8 targets were re-written with unchanged values. |
| Read back | Plain `getScore()` on all 9 targets equals the scorer output of commit `042f805` exactly (0 differences). `trackedTargetsCount()` = 9. |

Scorer output as of 2026-09-20 (`chains/arbitrum-ecosystem/scorers.py`,
re-run read-only against Arbitrum One, no key, no transaction). Only Radiant
moved; every other Arbitrum target is unchanged.

| Idx | Target | adminKey | multisig | timelock | oracle | crossExp | composite |
|---|---|---|---|---|---|---|---|
| 2 | Radiant LendingPool (`0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886`), on the oracle before (2026-09-19 push) | 55 | 100 | 55 | 100 | 100 | **69** |
| 2 | Radiant LendingPool, on the oracle now (pushed 2026-09-20, equal to scorer output) | 65 | 95 | 0 | 100 | 100 | **55** |

Why it moved. `PoolAddressesProvider.getPoolAdmin()` is
`0x111CEEee040739fD91D29C34C33E6B3E112F2177`, a 4-of-11 Safe, which is a
DIFFERENT address from `provider.owner()`, the 72 h TimelockController
`0x27fC8f3B...Aff92` (`getMinDelay()` = 259,200 s). The old scorer scored
only the timelock path. The pool-admin Safe holds PROPOSER and CANCELLER on
the timelock and 6 of its 11 owners hold EXECUTOR, but the timelock does not
bind the pool-admin path (the token-upgrade path), so the target is now
scored as a Safe with no timelock: admin 65 (threshold >= 3), multisig
min(100, 4 x 15 + 7 x 5) = 95, timelock 0. The timelock still gates the
provider-level owner functions, which the scorer notes disclose.
`getEmergencyAdmin()` is `0xDdF60973...0928`, a 1-of-5 Safe whose 5 owners are
all owners of the 4-of-11: an availability-only path, disclosed, not scored.
If the pool admin or the provider owner cannot be read, the scorer now
degrades to 20 / 0 / 0 instead of keeping a confident score (the old
unread-owner fallback was 25 / 100 / 0).

`crossExposureScore` stays 100 for Radiant. It was checked against 70
root-signer groups on 7 ecosystems and no overlap was found. That is "found
none", not proof of none, and it is a dated snapshot, not something the
scorer re-runs. Arbitrum already folded cross-ecosystem overlaps before the
2026-09-20 convention decision (Aave V3 Arbitrum 80, Pendle V2 60, Fluid 80),
so the convention change moved no other Arbitrum score. The rule is in the
root `METHODOLOGY.md`, paragraph "Convention (decided 2026-09-20)".

### On-chain scores after the FIRST 2026-09-20 re-push (index 0 superseded)

Read back with plain `getScore()` on 2026-09-20 after that push; 9 targets,
record in `data/oracle_scores_2026-09-20.csv`. The 2026-09-19 table above is
kept as history.

**Row 0 below is history, not current state.** A second push the same day at
14:12 lowered GMX V2 RoleStore to timelock 50 / composite 19 -- see the section
"2026-09-20 (later): GMX DAO timelock has its own bare-EOA proposer" further
down, which is the current state, confirmed live on two RPCs on 2026-09-20 and
recorded in `data/correction_2026-09-20-arbitrum-oracle-scores-csv-stale-gmx.md`.
The other eight rows were not touched by that second push and are current.

| Idx | Target | adminKey | multisig | timelock | oracle | crossExp | composite |
|---|---|---|---|---|---|---|---|
| 0 | GMX V2 RoleStore (superseded, see below) | 10 | 0 | 60 | 100 | 100 | **22** |
| 1 | Camelot AMMv3 Factory | 50 | 35 | 0 | 100 | 100 | **31** |
| 2 | Radiant LendingPool | **65** | **95** | **0** | 100 | 100 | **55** |
| 3 | Arbitrum Security Council Emergency Safe | 55 | 100 | 40 | 100 | 100 | **64** |
| 4 | Aave V3 Pool (PoolAddressesProvider) | 65 | 100 | 50 | 100 | 80 | **71** |
| 5 | Compound V3 Comet USDC | 75 | 100 | 65 | 100 | 100 | **80** |
| 6 | Pendle V2 Router + MarketFactoryV6 | 65 | 55 | 0 | 100 | 60 | **43** |
| 7 | Fluid Liquidity | 65 | 55 | 55 | 100 | 80 | **59** |
| 8 | Uniswap V3 Factory | 80 | 100 | 75 | 100 | 100 | **85** |

In row 2, bold marks the fields that changed against the 2026-09-19 table
(adminKey, multisig, timelock, and the composite 69 -> 55). No other row
changed.

### 2026-09-20 (later): GMX DAO timelock has its own bare-EOA proposer (pushed on-chain)

The unscored-role sweep (`data/finding_2026-09-20-unscored-role-sweep.md` section 4) flagged, without
naming the holder, that a bare EOA holds PROPOSER, EXECUTOR and CANCELLER on the GMX DAO timelock
`0x4bd1cdAab4254fC43ef6424653cA2375b4C94C0E`, one of the three `ROLE_ADMIN` holders of the RoleStore.
Re-derived by hand on 2026-09-20 on two RPCs (`arb1.arbitrum.io`, `arbitrum-one-rpc.publicnode.com`) after an
indexer log replay of the timelock: the holders are the bare EOA `0xE7BfFf2aB721264887230037940490351700a068`
(2,870 transactions, about 2 ETH) and the Governor contract `0x03e8f708e9C85EDCEaa6AD7Cd06824CeB82A7E68`;
`getMinDelay()` is 86,400s; the 5-of-8 Safe `0x8D1d2e24...` holds none of the three roles there. By `eth_call`
(no transaction): `schedule(RoleStore, grantRole(x, ROLE_ADMIN), ...)` does not revert from that EOA and reverts
from a random address and from the Safe.

So one key can queue and, 24h later, execute a `ROLE_ADMIN` grant with no Governor vote and no Safe veto: the same
class of path as the `TIMELOCK_ADMIN` EOA that produced the 2026-09-19 correction, but without the Safe's veto
window. `adminKeyScore` (10) and `multisigScore` (0) were already at the bare-EOA floor, so only the veto credit
moves: `score_gmx_v2_rolestore` credits the Safe veto (timelock 60) only when it covers every EOA-initiated path,
otherwise 50.

| Idx | Target | adminKey | multisig | timelock | oracle | crossExp | composite |
|---|---|---|---|---|---|---|---|
| 0 | GMX V2 RoleStore, before that re-push | 10 | 0 | 60 | 100 | 100 | 22 |
| 0 | GMX V2 RoleStore, on the oracle since the 2026-09-20 re-push | 10 | 0 | **50** | 100 | 100 | **19** |

Pushed by Spap on 2026-09-20 (Arbitrum Sepolia, tx `0xd0437c358c6eb0a6e1b21ad13c433172ec4ccf9acd08d9e106bbb1ca66ecfafe`, block 310,866,307, status 1); the full 9-target scorer output read back identical to the oracle (0 differences), GMX now 10/0/50/100/100/19. Also done in
the same pass: Radiant's two Safes (pool admin 4-of-11, emergency admin 1-of-5) are now the registry group
`radiant_pool_admin` in `scripts/lib/cross_ecosystem_overlap.py`, and the live sweep (71 groups, 7 ecosystems) finds
no overlap involving them, so Radiant's `crossExposureScore` stays 100.

### 2026-09-20 (later still): the record file was stale, and a tenth target is ready to push

Two separate things, both from the maintenance run of 2026-09-20. **Nothing was pushed on-chain by that
run** -- the 9 live scores were read, not written, and the tenth target below is prepared, not sent.

**1. Correction to an already-published record.** `data/oracle_scores_2026-09-20.csv` and the
"Current on-chain scores" table above both still carried the *first* push of 2026-09-20 for index 0
(timelock 60, composite 22) after the 14:12 re-push had moved it to 50 / 19. The oracle itself was
never wrong. `getScore()` on all 9 `trackedTargets`, read on
`sepolia-rollup.arbitrum.io/rpc` and `arbitrum-sepolia-rpc.publicnode.com`, returns identical values
on both, `lastUpdated` = 1789906343 on all 9, and index 0 is `10 / 0 / 50 / 100 / 100 / 19`. The other
8 rows matched the CSV exactly. The CSV row and the table heading are corrected; full write-up in
`data/correction_2026-09-20-arbitrum-oracle-scores-csv-stale-gmx.md`. The live scorer agrees with the
chain on all 9, so there is nothing to re-push for them.

**2. Tenth target prepared: GMX V1 Vault** `0x489ee077994B6658eAfA855C308275EAd8097C4A`, appended after
the 9 so `trackedTargets()` indices 0-8 keep their meaning.

| Idx | Target | adminKey | multisig | timelock | oracle | crossExp | composite |
|---|---|---|---|---|---|---|---|
| 9 | GMX V1 Vault (prepared, NOT pushed) | 55 | 70 | 45 | 100 | 80 | **57** |

`Vault.gov()` is GMX's bespoke Timelock (`buffer()` = 86,400s), whose `admin()` is a 4-of-6 Safe -- but
whose `tokenManager()` is a *different* 5-of-8 Safe that can call `setAdmin(address)` with no signal and
no buffer (`onlyTokenManager` in GMX's own `Timelock.sol`; confirmed by `eth_call` from all three of the
tokenManager Safe, the admin Safe and a random address). That same 5-of-8 Safe holds proposer, executor
and canceller on the GMX V2 timelock that is a `ROLE_ADMIN` of the tracked RoleStore at index 0, which is
where `crossExposureScore` 80 comes from. `requestGov()` was checked and ruled out (zero
`SignalSetGovRequester` events ever). Full record, including the symmetric open item on index 0 that was
deliberately left for a decision rather than silently applied:
`data/scored_targets_2026-09-20-maintenance-gmx-v1.md`.

Push command, prepared and dry-run only (the send is Spap's, per the 2026-09-20 rule):

```
# read-only, no key, no transaction -- this is what was run
READ_RPC_URL=https://arb1.arbitrum.io/rpc \
  python3 chains/arbitrum-ecosystem/deploy/push_scores.py --dry-run
# -> 10 targets, updateScores() calldata encoded (3012 bytes),
#    methodologyHash 0x6acfe9c5f210a6d1e4cd50a30ea19b8436bcee1b948e633d2de153bd4dd78915
```
