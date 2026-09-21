# Correction (2026-09-17): testnet oracle was still serving the pre-correction Uniswap score

## Context

This is a follow-up to `data/correction_2026-09-16-uniswap-bridge-alias.md`. That
correction, and the same day's later "RESOLVED 2026-09-17" addendum in the same
file, fixed `scripts/lib/scorers.py`, `README.md`, and `dashboard/index.html` to
describe Uniswap v4 PoolManager's root authority correctly (a legitimate Arbitrum
L1->L2 bridge alias of Uniswap's real Governance Timelock, not a bare EOA) and
computed the corrected score (85/100, up from 2/100) via a dedicated scoring path
(`_score_uniswap_bridge_alias_root()`). Those commits explicitly left it open
whether the corrected number had actually been pushed on-chain.

## What today's maintenance audit (rotation index 2) found

This run's audit target (`trackedTargets(2)` on the testnet
`AuthorityRiskOracle`) resolved to `0x8366a39CC670B4001A1121B8F6A443A643e40951`
(Uniswap v4 PoolManager). Independently re-derived from scratch, without reading
`scorers.py`'s cached results first:

- `poolManager.owner()` on Robinhood Chain mainnet = `0x2BAD8182C09F50c8318d769245beA52C32Be46CD`
- Re-computed the Arbitrum L1->L2 alias formula by hand: `(0x1a9C8182C09F50c8318d769245bEA52c32BE35BC + 0x1111000000000000000000000000000000001111) mod 2^160` = `0x2bad8182c09f50c8318d769245bea52c32be46cd` -- matches `owner()`, case-insensitive
- Robinhood-Chain-mainnet bytecode at the owner address: empty (`0x`), consistent with an L1->L2 alias, never itself a deployment target
- Ethereum-mainnet Governance Timelock (`0x1a9C8182...BE35BC`): real bytecode (13,715 bytes), `.delay()` = 172,800s (2 days), `.admin()` = `0x408ED6354d4973f66138C91495F2f2FCbd8724C3` (GovernorBravo), `.quorumVotes()` = 40,000,000 UNI -- all re-read live via `cast call` against `https://ethereum-rpc.publicnode.com`

This matches the 2026-09-16/17 correction's own findings exactly (recouped, not
just recalled). Applying the grid already coded in `scorers.py`
(`_score_uniswap_bridge_alias_root`, `admin_key=80/multisig=100/timelock=75`,
composite = `floor(0.4*80 + 0.3*100 + 0.3*75 + 0.5)` = 85) gives the same 85/100
that `README.md` has stated since yesterday's "RESOLVED" note.

**But `getScore(target)` on the testnet oracle still returned the stale
pre-correction score**: `(adminKeyScore=5, multisigScore=0, timelockScore=0,
oracleAuthorityScore=100, crossExposureScore=100, compositeScore=2,
lastUpdated=1789572321 -- 2026-09-16T15:25:21Z)`, i.e. from before yesterday's
correction commit. The repo's own methodology (code, docs) had been fixed, but
the on-chain publication -- the thing this whole project exists to make
trustworthy -- had not been re-run since.

## What changed in this commit

Nothing in `scorers.py`, `README.md`, or `dashboard/index.html` -- all three
already stated the correct 85/100 figure and needed no further edit. The only
action was publishing that already-correct, already-documented score on-chain,
via a one-off local push script kept outside this repo (not
`scripts/update_scores.py`, which batch-pushes all tracked targets and was
intentionally not run here to avoid touching the other 41 entries) -- dry-run
first, then live, following the same env-var contract documented for
`scripts/update_scores.py` (`READ_RPC_URL` / `ORACLE_RPC_URL` /
`ORACLE_ADDRESS` / signing key).

The on-chain result is the source of truth, not the script that produced it:
the confirmed transaction
(`0x52ccd2e50a663dc04e38da498f251f1dfb9149368748e2145e703daa7949746e` on
Robinhood Chain Testnet, block 120739543) decodes, via `cast decode-calldata`
against the exact `updateScores(address[],(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)[])`
signature from `src/AuthorityRiskOracle.sol`, to a single-element call:
`updateScores([0x8366a39CC670B4001A1121B8F6A443A643e40951], [(80, 100, 75,
100, 100, 85, 1789638498, 0xf260...b8975)])` against the testnet oracle
(`0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52`) -- touching only this one
target, no other tracked target's on-chain entry was modified by this run.

Confirmed via `getScore()` (`cast call`) after the transaction confirmed:
`(80, 100, 75, 100, 100, 85, ...)`.

## What this does NOT mean

- The other three Uniswap-stack surfaces (v3 Factory, UniswapX reactor, V2
  Factory feeToSetter) share the exact same root authority and the exact same
  `_score_uniswap_bridge_alias_root()` scoring path, so they are very likely in
  the same stale-on-chain-value state as v4 PoolManager was -- but this run only
  audited and pushed index 2 (v4 PoolManager), per this maintenance rotation's
  scope. The other three were NOT re-pushed here and should be checked/pushed
  on a future audit pass (or the next full `update_scores.py` run, which
  re-derives and pushes all 42+ tracked targets in one batch).

## Addendum (same day, post-run stale-number check): the other three surfaces are now pushed too

After the maintenance audit above, the pipeline's stale-number check compared
every tracked target's on-chain `getScore()` (all 44, read via `cast call`
against the testnet oracle) with a full `scripts/update_scores.py --dry-run`
re-derivation from Robinhood Chain mainnet. 41 of 44 composites matched. The
3 that did not were exactly the surfaces flagged as "very likely stale" above:

| Target | Address | On-chain before | Re-derived |
|---|---|---|---|
| Uniswap v3 Factory | `0x1f7d7550B1b028f7571E69A784071F0205FD2EfA` | 2/100 | 85/100 |
| UniswapX V3DutchOrderReactor | `0x000000007A1C8e570011EeDF86A2A35593013cBA` | 2/100 | 85/100 |
| Uniswap V2 Factory feeToSetter | `0x8bcEaA40B9AcdfAedF85AdF4FF01F5Ad6517937f` | 2/100 | 85/100 |

This is a **correction of already-published on-chain values**, not a new
finding: the scores themselves were fixed in the repo by the 2026-09-16
bridge-alias correction, only their publication was missing (the
`update_scores.yml` GitHub Action has never run on this repo, so no batch push
happened in between).

Pushed as a single `updateScores()` call touching only these 3 targets
(sub-scores `80/100/75/100/100`, composite 85, same `_score_uniswap_bridge_alias_root()`
path, crossExposure 100 as in the full dry-run): tx
`0xee1ae9863868566f6c16567f9256c5deadf437b8c95d2a1c5e7bcc2a2c40f78f`, Robinhood
Chain Testnet block 120784821, status 1. `getScore()` re-read afterwards for
each of the 3 addresses returns `(80, 100, 75, 100, 100, 85, ...)`.
`trackedTargetsCount()` is unchanged at 44. All 44 on-chain composites now
equal the live re-derivation, which is what `README.md` states.
