# Redo it, Solana: one score, from public reads

Take one target, the Exponent core program on Solana (`ExponentnaRg3CQbW6dqQNZKXp7gtZ9DGMp1cwC4HAS7`), and rebuild its score yourself. No account, no key, no transaction, no third-party library: a Python 3 script that calls public Solana RPC methods and decodes the accounts by hand.

The score is held by the Authority Risk Oracle on Solana devnet (program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`), in an account derived from the seeds `["score", target]`. It is the value written at the last push; it is not a reading of today. The oracle is a devnet deployment.

## Run it
```bash
python3 rejouer_solana.py     # a handful of read calls, a few seconds
```
It prints each read and ends with `VERDICT: MATCH` when the program's upgrade authority is the vault of the expected Squads multisig and the recomputed scores equal the published ones, and never otherwise. A wrong multisig prints `NO MATCH`; a failed read prints `NOT READ` and `NO MATCH` (a failed read is never a match).

## What it prints (run on 2026-10-22)
```text
1. The published score (oracle account on devnet, PDA of seeds ["score", target]): admin, multisig, timelock, oracle-authority, cross-exposure, composite
   account H8EGbxFPxGFcsRBujnvocTmNUUNCJayC2Ai91s8uonMG: [60, 69, 21, 100, 100, 51]
2. The program and its upgrade authority (mainnet)
   program ExponentnaRg3CQbW6dqQNZKXp7gtZ9DGMp1cwC4HAS7 -> ProgramData BA7Hr379x6GD59VrFtW7zaYnuY64deZEkngHK93qrK7u -> upgrade authority = 2tX7aHkV1r7am6bnTPqQJNBbEkbqDpNWHBYPahSQb9TP
3. Is that authority the vault 0 of the Squads v4 multisig 51smH7pBDKJDgmVnVks3gMWaPQFfmQ5s4Fc223yHcjuH ?
   vault 0 re-derived offline = 2tX7aHkV1r7am6bnTPqQJNBbEkbqDpNWHBYPahSQb9TP -> same as the upgrade authority
   threshold = 3, members = 5 (with the Vote permission: 5), time lock = 36000 s, config authority = 11111111111111111111111111111111
4. The rule applied to what was read (chains/solana/scorers.py): multisig = min(100, round(15 t + 40 t / n)); admin = 40/50/60 + min(20, 5 (t - 1)) for a delay of 0 / under 24 h / 24 h or more; timelock = round(50 h / 24) under 24 h
   admin = 60, multisig = 69, timelock = 21 -> composite = floor(0.4*60 + 0.3*69 + 0.3*21 + 0.5) = 51
   Oracle-authority (100) and cross-exposure (100) are read from the oracle in step 1 and are not recomputed here.
VERDICT: MATCH (admin/multisig/timelock = 60 69 21, composite = 51, as published)
```

## How to read it
- **Step 2.** A Solana program is changed by its upgrade authority, stored in its ProgramData account. Here it is an address that no key can sign for: a program derived address.
- **Step 3.** That address is the vault 0 of a Squads v4 multisig. The script re-derives the vault address offline from the multisig address (seeds `["multisig", multisig, "vault", 0]` under the Squads v4 program) and checks that it equals the upgrade authority: a coincidence in a transaction would not pass this test. It then reads the multisig account: a threshold of 3, five members who may vote, a time lock of 36 000 seconds (10 hours) between an approval and its execution, and no config authority.
- **Step 4.** Our rule for a program whose upgrade authority is a Squads v4 vault (`chains/solana/scorers.py`, `_score_full_power_path` and `_delay_timelock_score`): `multisigScore` is `min(100, round(15 t + 40 t / n))` = 45 + 24 = 69; `adminKeyScore` is 50 + min(20, 5 (t - 1)) = 60 for a delay under 24 hours; `timelockScore` is `round(50 h / 24)` = 21 for 10 hours. The composite is `floor(0.4 x 60 + 0.3 x 69 + 0.3 x 21 + 0.5) = 51`, the number the oracle holds.

## What this does not show
It shows that one published number follows from public reads and a written rule. It does not show that the rule is right, who holds the five keys, or that the score predicts anything. The multisig address is a constant in our scorer (`EXPONENT_MS`); the script checks it against the chain instead of trusting it. For this target the scorer reads the program's upgrade path; the program's own in-state authorities are not traced (the scorer's notes say so). Cross-exposure and oracle-authority are read from the oracle, not recomputed.

If a number differs on your side, open an issue with the output of `rejouer_solana.py`.
