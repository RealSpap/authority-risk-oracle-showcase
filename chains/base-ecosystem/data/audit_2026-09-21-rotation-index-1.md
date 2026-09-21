# Rotation audit, Base tracked index 1 - 2026-09-21

Target: Aave V3 Base `PoolAddressesProvider` `0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D`,
index 1 of the 9 targets on the Base Sepolia oracle `0x50840a7667baEa9D05ad4ae3dCeb384724b58720`.

**Result: no divergence.** The six components re-derived from the live chains equal the six
read back live with `getScore()`: 65 / 100 / 50 / 100 / 80, composite 71.

Script: [`../scripts/audit_rotation_index1_2026-09-21.py`](../scripts/audit_rotation_index1_2026-09-21.py)
(`--check-address-book` also re-checks the two hardcoded entry points against
bgd-labs/aave-address-book over HTTPS). Exit 0 = no divergence, 2 = divergence, 1 = a read failed.

## Why this script exists - two method failures it corrects

Both are corrections of *audit method*, not of any published score. The published numbers have
not moved.

1. **2026-09-20**: the audit loaded `chains/base-ecosystem/scorers.py` by `importlib` and called
   `score_aave_v3_base()`, then compared that output to the score the same function had produced.
   That checks RPC stability, never a methodology error.
2. **2026-09-21, first attempt**: the `importlib` call was dropped but the circularity was not -
   the Arbitrum guardian owner set was a constant copy-pasted out of the scorer
   (`from historical snapshot used in scorer`). It also used `(adminKey + multisig + timelock) // 3`
   instead of the documented `floor(0.4a + 0.3m + 0.3t + 0.5)` - the two agree on index 1 by
   coincidence and disagree on three of the nine published rows - and it read a frozen CSV
   instead of the deployed oracle. A sibling script written the same hour did query Arbitrum, but
   at `0x1A0581dd4876E9b432aa10f8CA2bA7Ac10fE7df3`, which has no code on Arbitrum One
   (`eth_getCode` length 0 on both `arb1.arbitrum.io/rpc` and `arbitrum-one-rpc.publicnode.com`).
   The real Arbitrum `GOVERNANCE_GUARDIAN` is `0x1A0581dd5C7C3DA4Ba1CDa7e0BcA7286afc4973b`
   (171 bytes of code), and this script does not hardcode it either: it derives it by tracing
   Arbitrum's own `PoolAddressesProvider` → `EXECUTOR_LVL_1` → `PayloadsController` → `guardian()`.

## What was read, live, this run

Base (chain 8453, `base.publicnode.com` + `mainnet.base.org`), Arbitrum One (42161,
`arb1.arbitrum.io/rpc` + `arbitrum-one-rpc.publicnode.com`), Base Sepolia (84532,
`sepolia.base.org` + `base-sepolia-rpc.publicnode.com`). Every read must return the same value on
both RPCs of its chain or the script stops.

| Component | Derived from | Value |
|---|---|---|
| `adminKeyScore` | `owner()` = `getACLAdmin()` = `EXECUTOR_LVL_1` `0x9390B1735def18560c509E2d0bc090E9d6BA257a`, whose `owner()` is `PayloadsController` `0x2DC219E716793fb4b21548C0f009Ba3Af753ab01`, whose `owner()` closes back on the executor | 65 |
| `multisigScore` | `getOwners()` and `getThreshold()` both revert on *both* halves of the root pair, so there is no Safe layer at the root - "not applicable", derived rather than assumed | 100 |
| `timelockScore` | `getExecutorSettingsByAccessControl(1)` returns a real 86,400 s delay; `guardian()` resolves to a live 5-of-9 Safe that can cancel outside that delay | 50 |
| `oracleAuthorityScore` | `latestAnswer` / `decimals` / `aggregator` / `latestRound` all revert on the target, and its `getPriceOracle()` (`0x2Cc0Fc26eD4563A5ce5e8bdcfe1A2878676Ae156`) is not one of the nine tracked targets | 100 |
| `crossExposureScore` | zero of the five other Base root Safes, the three other Base root EOAs, or the eight other tracked targets' `owner()` shares anything with index 1's root; Arbitrum's guardian, traced live, is a **different Safe address with the identical nine owners at the same 5-of-9 threshold** | 80 |
| `compositeScore` | `floor(0.4·65 + 0.3·100 + 0.3·50 + 0.5)` | 71 |

The documented composite formula reproduces all nine published composites read live;
`(a + m + t) // 3` misses three of the nine (indices 0, 2, 5).

## Context checked before calling anything notable

- The shared Aave committee across Base and Arbitrum is **not a new finding**: it was found and
  recorded on 2026-09-17 and is already the reason index 1 is published at 80 rather than 100.
  This run re-establishes it from Arbitrum itself instead of from a snapshot.
- The oracle's `lastUpdated` for all nine targets is `1789933081` = 2026-09-20T19:38:01Z, not the
  2026-09-19T16:33:37Z of `oracle_readback_2026-09-19.csv`. Comparing all nine rows, the
  2026-09-20 re-push wrote **the same six values everywhere**; the frozen CSV happened to still be
  accurate. That is luck, not method: a frozen file cannot detect a drift, which is why the
  baseline here is `getScore()`.
- Indices 3, 6 and 7 (Uniswap V3 / V2 / V4) still read `crossExposureScore` 100 on chain while
  `finding_2026-09-20-uniswap-one-timelock-eleven-targets.md` sets them to 80. That file states
  the new values "reach the chains at the next re-push", so this is a known pending push, not a
  divergence found here. Index 1 is unaffected.
- `methodologyHash` read live is `0x758072e3…cb34`, identical on both Base Sepolia RPCs.
