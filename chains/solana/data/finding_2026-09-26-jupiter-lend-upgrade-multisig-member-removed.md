# Jupiter Lend: the published 55 vs live 56 is a real committee change, not a scorer bug

2026-09-26. The bounded-loop routine's Solana verifier reported a read-back mismatch on Jupiter Lend (index 8): on-chain composite 55, scorer 56. The
worker had logged an exit code 0 taken behind a `| grep | wc -l`; the verifier re-ran `read_scores_solana.py` without the pipe and got exit 1. This note
re-verifies it independently and traces the cause to the transaction.

## Re-run (2026-09-26 ~18:50 UTC)

`read_scores_solana.py --oracle-rpc-url https://api.devnet.solana.com --program-id 5VhiTAGL...Yh4W`: 17 of 18 targets match, **1 mismatch: Jupiter Lend,
`multisigScore` and `compositeScore`**. On-chain (pushed 2026-09-26 07:18:50 UTC, `lastUpdated` 1790407130): admin 65, multisig **83**, timelock 13, composite
**55**. `score_jupiter_lend()` against Solana mainnet now: 65 / **87** / 13, composite **56**.

## Cause, from the chain

Jupiter Lend's score is the minimum over two full-power paths (METHODOLOGY 6.2): the program-upgrade Squads v4 multisig `J3mJ3wz6...` and `Liquidity.authority`
(`5Y93cxqp...`, 5-of-10, delay 21,600 s). The upgrade multisig is now **4-of-6**, time lock 43,200 s. Recent transactions on it: **a `ConfigTransactionExecute` at
2026-09-26 08:41 UTC**, 82 minutes after the re-push. Decoding the executed `ConfigTransaction` account (Squads v4 layout: one action, `RemoveMember`) shows the
member `2KXsciM4...` was removed, and that key is absent from the live member list. `_score_full_power_path("squads_v4", threshold=4, voters=N, delay_s=43200)`
returns multisig 83 for N = 7, 87 for N = 6, 92 for N = 5: the pushed 83 is exactly the 4-of-7 state, the live 87 exactly 4-of-6. So the on-chain value was right
when pushed and the world changed afterwards. (The scorer rewards a higher threshold-to-voters ratio, so removing a member at a constant threshold raises the
score; disclosed, not a change of convention.)

## What it means

- No scorer defect and nothing to fix in code: the next Solana re-push (Spap's; the Solana oracle turns stale 2026-10-05 07:18 UTC) will publish 87 / 56.
- The routine's catch was real: rule B (no exit code read through a pipe) turned a hidden failure into a true finding.
- The gap it exposes is timing: nothing watched Squads multisigs between pushes. `scripts/check_squads_changes.py` now diffs the state of every `*_MS` multisig the
  Solana scorers name (members with permission masks, threshold, time lock, config authority) against `data/squads_snapshot.json`; the digest can include it.

## Verification

`getSignaturesForAddress` and `getTransaction` on `J3mJ3wz6...` and `5Y93cxqp...` (Solana mainnet, public RPC); the `ConfigTransaction` account decoded by hand
(discriminator, multisig, creator, index, bump, action vector); `sol_read.read_squads` for the live member list; the scorer's own `_score_full_power_path` for the
83 / 87 / 92 mapping. No key, nothing sent.
