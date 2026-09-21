# Solana -- five more scouted targets scored, 2026-09-20

Promotes five targets of `scouted_targets_2026-09-17-run2.md` from a scouted upper bound to a re-runnable
scorer in `scorers.py`: **Save**, the **SPL Stake Pool program**, **JitoSOL**, **Sanctum Infinity** and the
**Sanctum validator LSTs**. Every one of them now has a `score_*` function, is in `SIMPLE_SCORERS` after
Marinade (so the oracle's tracked order stays stable: indexes 13 to 17), and is covered by
`scripts/lib/tests/test_solana_staking_and_save_scorers.py` (24 tests, hand-derived expectations).

## What "13 of 16" really meant

The 13 targets on the oracle are not "13 of the 16 scouted". Nine of them come from the scouted 16 and four
(Jupiter Aggregator v6, Kamino Lend, Solend DAO governance, Drift) from earlier passes. Of the scouted 16,
seven had no scorer on 2026-09-19. This pass covers five; the other two, Meteora DLMM and Meteora DAMM v1
(targets 5 and 6), stay **deliberately unscored**: their real source is not public, so no specific number
can be confirmed (`scored_targets_2026-09-18-defi-config-admins.md`, reaffirmed by the 2026-09-18 adversarial
review). With this pass, 18 targets have a score.

## Result

| Target | Full-power path(s) | admin / multisig / timelock | Composite | Status |
|---|---|---|---|---|
| Save (ex Solend) lending program `So1end...` | upgrade authority is one on-curve key | 5 / 0 / 0 | **2** | final (a bare key is the bottom rung) |
| SPL Stake Pool program `SPoo1K...` | Squads v3 `3yqoHF...` 6-of-10, no delay | 60 / 100 / 0 | **54** | final for the program |
| JitoSOL, pool `Jito4A...` | the same SPL Stake Pool upgrade path; pool roles bounded | 60 / 100 / 0 | **54** | final, roles re-checked every run |
| Sanctum Infinity `5ocnV1...` | upgrade Squads v3 `AApfiP...` 6-of-11 (60 / 100 / 0); pool admin Squads v4 `8EamQU...` 4-of-8, no delay (55 / 80 / 0) | 55 / 80 / 0 | **46** | final |
| Sanctum validator LSTs `SP12tW...` (and SanctumSplMulti) | both programs: Squads v3 `AApfiP...` 6-of-11 | 60 / 100 / 0 | **54** | **upper bound**: per-LST pool managers not enumerated |

These equal the scouted bounds exactly (2, 54, 54, 46, 54): nothing moved between 2026-09-17 and today.

## Re-verified today

All nine reproduction commands of the scouting file for these targets were re-run against Mainnet Beta on
2026-09-20 and print `OK` (Save authority, SPL Stake Pool authority and its 6-of-10, both Sanctum LST program
authorities, the S Controller authority, the 6-of-11, the pool admin and the 4-of-8 vault). The five scorers
were then run live and reproduce the table above.

## How each score is derived, and what it does not claim

- **Save.** The lending market `owner` was an open point. It cannot lower a bare-key score, which is already
  the lowest rung, so 2 is final whatever the owner is. Oracle authority is not scored (flat 100, like marginfi).
- **SPL Stake Pool program.** Shared infrastructure, scored on its upgrade path only. Jito's own docs call the
  upgrade keys a committee of Solana staking ecosystem participants; five of its ten signers are also signers of
  Sanctum's 6-of-11 (see cross-exposure below).
- **JitoSOL.** Three pool roles are classed **bounded** in the scouting file, with the `spl-stake-pool` source
  as evidence: `manager` (Jito DAO's native treasury: fee changes are delayed two epochs or capped,
  `WithdrawStake` stays permissionless), `staker` (a Steward program account) and the stake deposit authority.
  The mint authority is the pool's withdraw PDA, so no human key can mint JitoSOL. The scorer re-reads the
  manager, the staker's owner, the pool mint and the mint authority on every run and **raises** if any of them
  changed, so a drifted classification skips the target (which keeps its last on-chain value) instead of
  publishing a wrong score. The bounded classification itself is the 2026-09-17 reading; it was not re-derived
  from the program source today.
- **Sanctum Infinity.** The pool `admin` decides `SetSolValueCalculator` and `SetPricingProgram` for every LST
  and is full-power. `rebalance_authority` is a single on-curve key but bounded (`EndRebalance` must follow in
  the same transaction and rejects any drop in pool SOL value), so it is disclosed, not scored.
- **Sanctum validator LSTs.** An upper bound, labelled as one on its card and in its notes.

## Cross-exposure changed on the oracle, and why it looks harsh

`crossExposureScore` is `100 - 20 x (other targets sharing at least one signer)`, the repo-wide formula. Five
targets now sit in one signer cluster (the SPL Stake Pool committee, Sanctum's committee, and a key shared with
Marinade's council), so each of the five reads **20**, and **Marinade moves from 100 to 20**. No composite
changes (cross-exposure is not part of it): all 13 previously pushed composites are identical to the live
scorer today. The scouting file counted this cluster by group and got 60; the per-target formula counts SPL
Stake Pool and JitoSOL, and Sanctum Infinity and the LSTs, as separate targets even though each pair shares a
committee. That is a methodology question (group versus target), not a data error, and it is left as the
formula stands rather than tuned for these five.

## Not done

- **Not on-chain yet.** The oracle still holds 13 targets. Pushing these five (and refreshing the other 13,
  including Marinade's new cross-exposure) is a `update_scores_solana.py` run by Spap.
- **No independent verifier has approved these five yet.** They were verified here by re-running the scouting
  reproduction commands and by tests. The routine's maintenance verifier should re-derive them before the
  phase moves.
- Scouted-but-unscored targets that were never in the 16 (Binance Staked SOL, Jupiter Staked SOL, Phantom and
  other LST pools) still need a primary source per pool.

## Reproduction

```
python3 chains/solana/scripts/scout_check.py authority So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo RY93CZYe5g6drtG7W9PmHRPzaBLZ1uwihTzayQTmJfh
python3 chains/solana/scripts/scout_check.py v3 3yqoHFE4nBGchuVH5rJuZMFvsmnaDTuLLdvGPDUEJcbW 1 dPpFfahSWhm5M2RB3nVaHsXfnh9ooz5bWtR3WeUguDH 6 10
python3 chains/solana/scripts/scout_check.py v3 AApfiPZgV5MoPU691GwhdDhq5sKEMMH1Uh8S4Z9xvP6b 1 47SND7bGKvNXrqfP1bjsLCbwTgZhFBzAgmZ42QSkRScz 6 11
python3 chains/solana/scripts/scout_check.py infinity-admin 8JS6XsMPo2u3EyeeY3p2jvzHEhdUtCKgarHpJ3PAonyv 5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm
python3 chains/solana/scripts/scout_check.py v4 8EamQU8L2ubwC4FHMxf5BfinEkUFknboK7gpPzvshWyo 0 8JS6XsMPo2u3EyeeY3p2jvzHEhdUtCKgarHpJ3PAonyv 4 8 8 0
python3 -B -c "import sys; sys.path[:0]=['chains/solana/scripts','chains/solana']; import scorers; [print(r['label'], r['compositeScore']) for r in scorers.score_all('https://api.mainnet-beta.solana.com')]"
python3 -B -m unittest discover -s scripts/lib/tests -p "test_solana_staking_and_save_scorers.py"
```
