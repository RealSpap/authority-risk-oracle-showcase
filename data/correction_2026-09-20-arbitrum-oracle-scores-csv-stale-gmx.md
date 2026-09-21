# Correction (2026-09-20) -- the Arbitrum score record published for 2026-09-20 was stale for index 0

**This corrects an entry that was already published in this repository**, it is not a new
finding. Nothing changed on any chain because of it: the correction is to a record file that
had drifted away from the state the oracle has actually been serving since 14:12 that day.

## What was wrong

`chains/arbitrum-ecosystem/data/oracle_scores_2026-09-20.csv` was committed in `f7af724`
(2026-09-20 03:10:58 +0200) as the read-back record of the first 2026-09-20 re-push. Later the
same day, `f8a6229` (14:14:33 +0200) recorded a **second** Arbitrum push that lowered GMX V2
RoleStore from timelock 60 / composite 22 to timelock 50 / composite 19, after the unscored-role
sweep found a bare EOA holding PROPOSER, EXECUTOR and CANCELLER on the GMX DAO timelock with no
Safe veto over that path. That commit updated `chains/arbitrum-ecosystem/deploy/README.md` but
**not** the CSV, and not the README's own "Current on-chain scores (re-push, 2026-09-20)" table
further up the same file. So the repository stated three different things at once:

| Source | index 0 timelock | index 0 composite |
|---|---|---|
| `data/oracle_scores_2026-09-20.csv` (before this correction) | 60 | 22 |
| `deploy/README.md`, "Current on-chain scores" table (before this correction) | 60 | 22 |
| `deploy/README.md`, later 2026-09-20 section | **50** | **19** |
| The oracle itself, read live | **50** | **19** |

Only the last two were right.

## How the live state was established

`getScore()` on all nine `trackedTargets` of the Arbitrum Sepolia oracle
`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`, read on two independent RPCs
(`sepolia-rollup.arbitrum.io/rpc` and `arbitrum-sepolia-rpc.publicnode.com`). Both return
identical values for all nine targets, index 0 included:

```
cast call 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 \
  "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))" \
  0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc
# (10, 0, 50, 100, 100, 19, 1789906343, 0x6acfe9c5...)
```

`lastUpdated` is 1789906343 on all nine targets -- 2026-09-20 14:12 +0200, the second push. No
write of any kind was made from this pass.

The live scorer agrees with the chain: `chains/arbitrum-ecosystem/scripts/dry_run.py` (read-only,
mainnet, self-cross-checked on two Arbitrum One RPCs) produces `10 / 0 / 50 / 100 / 100 / 19` for
GMX and reproduces the other eight rows exactly. So there is **nothing to re-push** -- the chain
and the scorer already agree, and only the paper record was behind.

## What was changed

1. `chains/arbitrum-ecosystem/data/oracle_scores_2026-09-20.csv`, row index 0: `60 -> 50`,
   `22 -> 19`. The eight other rows were already correct and are untouched.
2. `chains/arbitrum-ecosystem/deploy/README.md`: the "Current on-chain scores (re-push,
   2026-09-20)" heading is renamed to mark it as the state after the **first** push of that day,
   with a forward pointer to the later section, so the file no longer presents a superseded row
   as current.

## Why it happened, and the cheap guard against a repeat

The record file is written once per push and is not regenerated when a **second** push lands the
same day. A same-day second push is exactly the case the filename (`..._2026-09-20.csv`) cannot
distinguish. A record whose name carries only a date is only ever a snapshot; treating it as a
mirror of current state is what produced the three-way disagreement above. The durable fix is to
read the chain when current state is the question -- which is what
`chains/arbitrum-ecosystem/scripts/dry_run.py` plus a `getScore()` read-back already give -- and to
treat these CSVs as dated evidence of one push.
