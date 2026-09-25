# Aave V3 Ethereum Pool: role-holder discovery extended to the flagship target

2026-09-25. Continues the "voit large" round 2 roadmap item 4 (extend the role-sweep pattern that
already found 2 real bugs on Radiant and Aave V3 Monad). `score_aave_v3_pool` -- $14.77B TVL, this
oracle's single largest tracked target by TVL -- had checked `isEmergencyAdmin` on exactly two
hardcoded addresses (the DAO executor, `PROTOCOL_GUARDIAN`) since it was written, with no mechanism
to discover a role holder added later. `score_aave_v3_horizon_pool` already closed this exact gap
(GitHub backlog item "limite de Horizon") on the much smaller Horizon instance, after 3 real defects
found and fixed by adversarial (maker-checker) review. Applied here for the first time on the main
pool, reusing `_replay_role_holders()` and the hasRole-confirmation pattern UNCHANGED -- not
re-derived from scratch.

## What was verified live before writing any code

1. **ACLManager creation block, binary-searched via `eth_getCode`** (Tenderly gateway;
   `ethereum-rpc.publicnode.com` returns 403 on historical state this far back): block `16,291,117`
   (2022-12-29), not looked up from memory or an indexer.
2. **Full RoleGranted/RoleRevoked replay from that block** (POOL_ADMIN, EMERGENCY_ADMIN,
   RISK_ADMIN, ASSET_LISTING_ADMIN, FLASH_BORROWER, BRIDGE) -- 38 seconds, no errors.

## Result

- **POOL_ADMIN: exactly 1 holder, the DAO executor.** Matches what this scorer already assumed.
  Confirms the existing classification is correct, not just unfalsified.
- **EMERGENCY_ADMIN: exactly 1 holder, PROTOCOL_GUARDIAN.** Same -- confirms, doesn't change.
- **RISK_ADMIN: 5 holders, none previously tracked, disclosed or scored by this project.**
  Cross-referenced (after the live finding, not before) against Aave DAO's own published
  `aave-dao/aave-permissions-book` (`out/ETHEREUM-V3.md`) for naming:
  - `Manual AGRS`
  - `PendleDiscountRateAgent`
  - `Gho Core Direct Minter`
  - `Core GHO Aave Steward`
  - `EModeCategoryAgent`

  3 of 5 read `owner()` = the same governance Executor directly (revocable by governance, matching
  Aave's own "Risk Steward" design: "bounded, revocable delegated authority... within fixed
  cooldowns and a maximum change allowed per update", per `aave-dao/aave-v3-risk-stewards`). The
  other 2 (`PendleDiscountRateAgent`, `EModeCategoryAgent`) don't expose a plain `owner()` --
  gated some other way, not opened this pass.
- ASSET_LISTING_ADMIN, BRIDGE: empty. FLASH_BORROWER: 13 holders, not disclosed here -- flash-loan
  fee-exempt integrations are an operational allowlist, not an authority-relevant permission over
  the pool (out of this project's own scope, same reasoning `not scored` already applies elsewhere).

## Why RISK_ADMIN is disclosed, not scored

RISK_ADMIN can change market parameters (collateral config, borrowing, caps) -- a DIFFERENT class
of risk from `adminKeyScore`/`multisigScore`/`timelockScore` (root-authority/fund concentration),
the same boundary this project already draws around Chaos Labs/Gauntlet-style market-parameter
risk (see today's competitor research: neither evaluates admin-key concentration, and this project
deliberately doesn't score their kind of risk either). Same treatment `score_aave_v3_horizon_pool`
already gives its own RISK_ADMIN holders -- consistent, not a new exception.

## What this changes and doesn't

`adminKeyScore`/`multisigScore`/`timelockScore`/`compositeScore` are **unchanged** (78/100/55/78,
live-verified before and after). Purely additive: two new disclosed findings in `notes` --
confirmation that no undisclosed POOL_ADMIN/EMERGENCY_ADMIN holder exists, and the 5 named
RISK_ADMIN holders. Off-chain notes only; nothing pushed.

## Verification

5 new unit tests (`scripts/lib/tests/test_ethereum_l1_scorers.py::TestScoreAaveV3PoolRoleDiscovery`):
clean replay names every known RISK_ADMIN holder, an extra POOL_ADMIN/EMERGENCY_ADMIN holder
confirmed via hasRole is disclosed, an UNCONFIRMED candidate is dropped as a phantom (not reported
as real -- the exact failure mode 3 real Horizon defects came from), an unnamed RISK_ADMIN holder
is flagged for manual review, a failed replay is disclosed honestly and doesn't crash or move the
score. Full suite (6 test directories, 2349 tests) green. Live dry-run
(`DRY=1 ONLY="l1" bash scripts/repush_all_oracles.sh`) confirms the target still encodes correctly.
