# Rotation audit (2026-09-18): Robinhood Chain, tracked target index 5

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 5
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(5)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`, corrected if it diverged.

## Target

`trackedTargets(5)` = `0xde770c84FE66E063336b31737cFE9790f18c4087` -- Spark
Savings USDG (spUSDG). `trackedTargetsCount()` = 45 going into this run.

## Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 50 | 30 | 10 | 100 | 100 | 32 |

## Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`.
Deliberately did not import or call `scorers.py::score_spark_savings_usdg()`
-- made the raw `eth_call`/`eth_getLogs` calls directly.

| Check | RPC A result | RPC B result |
|---|---|---|
| `DEFAULT_ADMIN_ROLE` grant/revoke log replay from genesis (`eth_getLogs`, full range, target = spUSDG) | 3 events: grant to deployer `0xB328BD52...C547` (block 31331, self-granted at deploy), grant to executor `0x826AEaee...1D02` (block 57748, by deployer), revoke from deployer (block 57805, by deployer) -- current holder set: `{0x826AEaee...1D02}` | same (wide-range `eth_getLogs` on this RPC returns a 400 "ranges over 10000 blocks not supported on free plan" -- full replay done on RPC A only; RPC B used for direct-call cross-checks below) |
| `target.hasRole(DEFAULT_ADMIN_ROLE, 0x826AEaee...1D02)` live | `True` | `True` |
| executor `0x826AEaee...1D02`: bare EOA | `False` (has code) | `False` |
| `executor.delay()` | `0` | `0` |
| `executor.gracePeriod()` | `604800` | `604800` |
| receiver `0xc12B1e59...387E8`.`l1Authority()` | `0x3300f198988e4C9C63F75dF86De36421f06af8c4` | same |
| receiver `getOwners()`/`getThreshold()` (Safe check) | both revert -- not a Safe | same |
| receiver bare EOA | `False` (ArbitrumReceiver-pattern contract) | same |

Every fact matches what `score_spark_savings_usdg()`'s docstring and
`scripts/lib/scorers.py` already record: a self-administering L2 executor
(not a Safe, not a bare EOA) gated by an L1-authenticated receiver resolving
to Sky/MakerDAO's own verified "SubProxy" contract on Ethereum mainnet, local
delay confirmably 0. No drift since the last time this target was scored.

## Score check

`_composite(50, 30, 10)` = `floor(0.4*50 + 0.3*30 + 0.3*10 + 0.5)` =
`floor(32.5)` = 32 -- matches the published `compositeScore` exactly. No
divergence found anywhere in the five sub-scores. **No correction needed for
this target; nothing pushed for index 5.**

## Side observation (not a score correction)

`totalAssets()` on the vault reads **~$14.54M** live (both RPCs agree, raw
`14535565525633` / `14535565541489` at `decimals()=6` -- the ~16 USDG-unit
difference between the two RPCs is normal same-block-height read skew, not a
disagreement). README's row for this target still shows "~$16.8M TVL,
corrected 2026-09-17". TVL is not a field the oracle contract stores or that
`compositeScore` depends on -- it is descriptive context in the README table
only -- and a ~14% drop over one day in a savings vault is ordinary flow, not
the kind of stale/wrong figure the 2026-09-17 TVL correction was about (that
one was a genuine measurement bug, not fluctuation). Left as-is rather than
treated as a "correction"; flagging here so it isn't mistaken for something
this run verified as current.

## Rotation state

`last_audited_target_index` advanced from 5 to 6 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside this
repo). Next rotation audit should re-derive `trackedTargets(6)` from scratch.
