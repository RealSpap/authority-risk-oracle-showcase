# Rotation audit (2026-09-19): Arbitrum Ecosystem, tracked target index 0 -- CORRECTION (GMX V2 RoleStore)

First maintenance-phase run for this ecosystem, rotation index 0.
`trackedTargets(0)` read live from the Arbitrum Sepolia oracle
`0x50840a7667baEa9D05ad4ae3dCeb384724b58720` on 2 RPCs
(`sepolia-rollup.arbitrum.io/rpc`, `arbitrum-sepolia-rpc.publicnode.com`):
`0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72`, the GMX V2 (Synthetics)
RoleStore. Every authority fact below was re-derived from scratch against
Arbitrum One mainnet (chain 42161, read-only) on 2 independent RPCs
(`arb1.arbitrum.io/rpc`, `arbitrum-one-rpc.publicnode.com`), with
standalone scripts that do NOT import `scorers.py` (kept in this pipeline's
run folder `runs/2026-09-19-cron/arbitrum-ecosystem/`, outside this repo).

## Published score (before this run)

| adminKey | multisig | timelock | oracleAuth | crossExposure | composite | lastUpdated |
|---|---|---|---|---|---|---|
| 65 | 90 | 60 | 100 | 100 | **71** | 1789755413 (2026-09-18) |

## Step 1: the published rule reproduces 71

Re-running the scorer's own rule (one TIMELOCK_MULTISIG holder, a 5-of-8
Safe, holding PROPOSER+EXECUTOR on `ConfigTimelockController`
`0xC77E6C0c...DEaF5`, `getMinDelay()` = 86,400 s) gives 65/90/60 -> 71 on
both RPCs. So no arithmetic divergence. The problem is what that rule
looks at.

## Step 2: tracing the real authority from the root finds two defects

Every row identical on both RPCs (blocks ~506,829,8xx-506,831,0xx):

| Check | Result |
|---|---|
| `RoleStore.getRoleMembers(ROLE_ADMIN)` (the role that can grant every role) | `0x4bd1cdAa...C94C0E` (GMX DAO timelock, 86,400 s), `0x2Dd99f39...BBD44`, `0xE7706986...D4F5` |
| Sourcify, `0x2Dd99f39...` | exact match, `contracts/config/ConfigTimelockController.sol` |
| Sourcify, `0xE7706986...` | exact match, `contracts/config/TimelockConfig.sol` |
| `TimelockConfig.timelockController()` | `0x2Dd99f39...` (so this, not `0xC77E...`, is the live controller) |
| `RoleStore.hasRole(0xC77E6C0c... , ROLE_ADMIN)` | **false**. The controller the scorer checked holds no role at all on this RoleStore (19 roles enumerated). |
| `RoleStore.getRoleMembers(TIMELOCK_ADMIN)` | 5-of-8 Safe `0x8D1d2e24...`, 4-of-6 Safe `0x58F58245...`, **`0xE014cbD6...C927483`** |
| `eth_getCode(0xE014cbD6...)` / nonce | 0 bytes (bare EOA, no EIP-7702 designator) / nonce 72 (an actively used key) |
| live controller `hasRole(PROPOSER/EXECUTOR/CANCELLER, 0xE014...)` | true / true / true |
| live controller `getMinDelay()` | 86,400 s |
| `TimelockConfig` source (Sourcify) | `signalGrantRole()` and `execute()` are both `onlyTimelockAdmin`. `revokeRole()` is `onlyTimelockMultisig`. |

Primary source cross-check: GMX's own `config/roleConfigs/arbitrum.ts`
(`gmx-io/gmx-synthetics`, main, last touched 2026-07-31) labels
`0xE014cbD6...` as `timelock_admin_2` in TIMELOCK_ADMIN. So this EOA is
there on purpose. The same file lists `ROLE_ADMIN` as the DAO,
`TimelockConfig 0x4A1D9e34...` and `ConfigTimelockController 0xC77E6C0c...`.
Live, the last two are **not** ROLE_ADMIN: the chain still has the
`0x2Dd99f39...`/`0xE7706986...` pair. The repo's `deployments/` and
`roleConfigs/` files are ahead of (or diverge from) the live role
assignment. The old scorer inherited that divergence by hardcoding the
repo address.

**What this means:** one bare EOA can call
`TimelockConfig.signalGrantRole(anyone, ROLE_ADMIN)` (or schedule the same
call directly on the controller), then execute it 24 h later. That gives
it control of every GMX V2 role. The defence is the 5-of-8
TIMELOCK_MULTISIG Safe: it holds CANCELLER on the live controller and can
`revokeRole()` immediately. That is a 24 h veto window, not a multisig
threshold. Mitigating context, stated as found: this is a deliberate GMX
design (keeper-style admin keys under a timelock plus multisig
watchdog), and nothing on-chain suggests misuse. Aggravating context:
the multisig protection depends on someone noticing and cancelling within
24 h. A compromise of one hot key would be enough to start the clock.

## Step 3: re-derived score (CORRECTION)

Scored under METHODOLOGY.md's existing rules. The weakest initiator sets
adminKey/multisig (same `(k, -n)` weakest-key ordering as
`chains/zcash/scorers.py`). A bare-EOA root is adminKey 2-10 and multisig
0. The top of the band (10) reflects that the EOA cannot act inside the
24 h window. The confirmed delay plus the confirmed Safe veto keep
timelockScore at 60. No other ROLE_ADMIN member has a zero delay (the DAO
timelock is 86,400 s), so no bypass was found.

| | adminKey | multisig | timelock | composite |
|---|---|---|---|---|
| Published 2026-09-18 | 65 | 90 | 60 | 71 |
| **Re-derived 2026-09-19** | **10** | **0** | **60** | **22** |

`composite = floor(0.4*10 + 0.3*0 + 0.3*60 + 0.5) = floor(22.5) = 22`.
Control test in `test_arbitrum_ecosystem_scorers.py`
(`test_safe_only_initiators_keep_the_old_strong_score`): with the EOA
removed from TIMELOCK_ADMIN, the new code gives back exactly 65/90/60 ->
71. So the drop comes from the EOA, not from a changed formula.

## What changed in code

`chains/arbitrum-ecosystem/scorers.py::score_gmx_v2_rolestore()` no longer
hardcodes a controller. It enumerates ROLE_ADMIN / TIMELOCK_ADMIN /
TIMELOCK_MULTISIG live, finds the controller through TimelockConfig,
checks that every other ROLE_ADMIN has a non-zero delay, classifies each
initiator (Safe / bare EOA / unresolved contract) and scores the weakest
one. 8 unit tests replace the 5 old ones, including a regression guard
proving the old hardcoded `0xC77E...` hop no longer resolves anything.

## Push and read-back

`updateScores()` tx `0xa934822b3ed2959761641e312b4646890243ede3f82648e433fecfea1d57d85b`
(Arbitrum Sepolia block 310,589,900, status 1, from the shared testnet
deployer `0x20630C6A...32f5`). The same batch re-pushed indices 1-4
(unchanged composites 31/69/64/71) and 4 new targets (see
`scored_targets_2026-09-19-maintenance.md`). `getScore(0x3c3d99FD...)`
read back on both Sepolia RPCs: 10/0/60/100/100 -> **22**,
`lastUpdated` 1789836263.

## Left open (not guessed)

- `scripts/lib/cross_ecosystem_overlap.py`'s `ARBITRUM_GROUPS["gmx_timelock_multisig"]`
  still lists only the 5-of-8 Safe. The TIMELOCK_ADMIN EOA and the 4-of-6
  Safe are not in it. That file is shared (outside `chains/arbitrum-ecosystem/`)
  and was not edited by this run.
- Why GMX's repo lists a newer TimelockConfig/ConfigTimelockController
  pair that is not yet ROLE_ADMIN live (a pending migration, or an
  abandoned one) was not resolved. The scorer follows the live chain
  either way.
