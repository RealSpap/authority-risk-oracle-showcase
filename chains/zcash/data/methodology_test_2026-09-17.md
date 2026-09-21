# Zcash methodology test on real targets, 2026-09-17 (second run)

Full tables are in [METHODOLOGY.md section 7.3](../METHODOLOGY.md). This file is the
short record of what was tested, what held and what changed.

## What was re-derived, and how

| Target | Primary source read | Independent of the published run? |
|---|---|---|
| ZIP 271 fund `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo` | `GetTaddressTxids` 3,146,400 to 3,486,770 and `GetTaddressBalance` on `zec.rocks`, `zcash.mysideoftheweb.com`, `na.zec.rocks`; ZIP 271 text | Yes: a from-scratch gRPC, transaction and script parser (not this folder's `scripts/`), scores computed by hand from METHODOLOGY.md 4.6 |
| ZCG fund `t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow` (control) | Same calls, window 3,476,771 to 3,486,770 (not the scorer's window) | Yes |
| `L1` concentration input | `GetBlockRange` coinbase outputs, published window and a fresh window 3,484,771 to 3,486,770, two operators; coinbase input text of 200 sampled blocks via `GetTransaction` | Yes |
| ZIP 0 citations | `zips/zip-0000.rst` on `main` and the rendered `zips.z.cash/zip-0000` | Yes |

## Result

| Check | Outcome |
|---|---|
| Fund thresholds, pubkeys, balances | Match: both 2-of-3, keys disjoint, `t3ev37...` balance 78,183.4093 ZEC on three operators |
| Fund scores by hand | 50 / 39 / 0 / 100 / 100, composite 32, capped 32: match |
| `L1` `k50` / `k25` | 3 / 1 on both windows, both operators, all blocks and attributed-only blocks: match, `multisigScore` 50 |
| `L1` lineage and synthetic key | 1 independent lineage (Zakura still a declared fork), key `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3`: match |

## Rules changed by the test

| Open point | Resolution |
|---|---|
| Unspent P2SH rule | "score 0" replaced by an unresolved-P2SH floor (adminKey 5, multisig 16, composite 7), also applied to unrecognised script shapes and operator disagreement. The old code placeholder (20/20) ranked an unknown script above a known 1-of-3 |
| Double counting of miner concentration | Scored once, in `L1` `multisigScore`; `oracleAuthorityScore` discloses it without scoring; the lightwalletd lineage input stays in `adminKeyScore` only |
| Exact ZIP 0 citation | Exact sentences now quoted; "must always hold a ZIP Editor seat" corrected to ZIP 0's "The current design of the ZIP Process dictates ..." |
| Found during the test | Script suffix validation added; concentration window made tip-relative and two-operator |

None of these changes moves a published score today. Sensitivity (not scored): if the
two untagged payout addresses ranked 1st and 5th belonged to one entity, `L1`
`multisigScore` would be 35 and the `L1` composite 29.
