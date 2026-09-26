# Tempo pathUSD: re-verified live, composite 9 unchanged, tracker piste already covered

2026-09-26. Closes the tracker board's open piste "Tempo pathUSD: `ISSUER_ROLE` est un proxy UUPS
[backlog note]
[backlog note]". It was already covered (`scored_targets_2026-09-18-controller-types.md` classifies the
ISSUER_ROLE holder as an `AccessControlEnumerable` bridge controller resolved to the same single key;
`scouted_targets_2026-09-17-run2.md` records the `upgradeToAndCall` probe). This pass re-runs the
project's own `chains/tempo/scripts/methodology_test.py::score_token` against the live chain
(head block 41,358,915, both `rpc.tempo.xyz` and `tempo-rpc.publicnode.com` agreeing on every
`eth_call`) to check nothing has drifted since 17-20/09.

## Result: no drift, composite 9 stays exact

| Item | Live value 2026-09-26 |
|---|---|
| `DEFAULT_ADMIN_ROLE` | single EIP-7702-delegated EOA `0x79C6631FA15CdA38777FB9DD7a6348bAEe794a4E` (k=1, n=1) |
| `ISSUER_ROLE` | controller contract `0x8354D80EeA9978Faa04c3b36771c1e8b9c3e9058` (AccessControlEnumerable), whose own admin is that same `0x79C6...4a4E` |
| `PAUSE_ROLE` / `BURN_BLOCKED_ROLE` / `UNPAUSE_ROLE` | nobody holds them today. `roleAdminChanges` is empty, so `DEFAULT_ADMIN` administers them: the same single key can self-grant pause and seize in one transaction |
| Transfer policy | id 2, type BLACKLIST, admin `0x251d2711ebeB0a09fdB8992F5506f3D949175246` (a SECOND, distinct single EIP-7702 EOA that can blacklist any holder) |
| Scores | adminKey 10, multisig 15, timelock 0, oracleAuthority 100, **composite 9** (identical to the committed value) |

## Two things this read adds that the committed notes did not state

1. **Supply moved a lot**: `totalSupply` = 62,108,713.945041 pathUSD (6 decimals), `supplyCap`
   100,000,000. The 17/09 note cites ~$38.6M-39.3M. +58% in nine days, so any card or dashboard
   quoting the old figure is stale. The composite does not weight by TVL, so no score moves.
2. **Two independent single-key EOAs, one shared delegate**: the DEFAULT_ADMIN EOA and the blacklist
   policy admin EOA both delegate (EIP-7702) to `0x0000Fb7702036ff9f76044a501ac1aA74cbab16b`, the
   same delegate the 17/09 note already recorded for `0x79C6...4a4E` (a third-party registry lists it
   as a Fireblocks delegation; that registry is NOT a primary source and is not used as one). Whether
   the two EOAs share an operator is not established by this read: the same delegate implementation
   does not imply the same owner. Disclosed as an open point, not asserted.

## What this is and isn't

Pure re-verification, no scorer change, no new target, no push. The backlog item can be closed as
"already covered, re-confirmed live, unchanged". The 5 role holders and 3 policy/role admin keys were
read by the project's own scorer against two independent RPC endpoints, not re-derived by hand.

## Verification

`python3` importing `chains/tempo/scripts/methodology_test.py` and calling `scan_role_logs([pathUSD])`
then `score_token("pathUSD", pathUSD, None, events)`; read-only JSON-RPC, no key touched.
