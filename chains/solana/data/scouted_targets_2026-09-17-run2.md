# Solana: scouted targets, 2026-09-17 (run 2)

Status: **scouting output, not yet scored in `scorers.py`.** All reads are live against Solana
Mainnet Beta, read-only (JSON-RPC, no keys, no signing). Every account read was repeated on two
RPCs (`https://api.mainnet-beta.solana.com` and `https://solana-rpc.publicnode.com`); historical
transactions were re-read on `https://public.rpc.solanavibestation.com` because publicnode does
not serve old transactions. Reference slot: about 447,852,604 (block time 2026-09-17 17:31 UTC).

Method: [`../METHODOLOGY.md`](../METHODOLOGY.md) sections 3.3 (resolution ladder), 6.1 (formulas)
and 6.2 (full-power / bounded / restrict-only). Composites below are computed with the repo's
own `scorers._score_full_power_path` and `scorers._composite`. Already scored targets (Jupiter
Aggregator v6, Kamino Lend main market) are not repeated.

Reproducible checker: [`../scripts/scout_check.py`](../scripts/scout_check.py). Each
subcommand prints `OK` only if the assertion holds on both RPCs.

## What changed from the rejected morning draft

| Morning claim | What the chain actually shows | Evidence |
|---|---|---|
| Raydium AMM V4 "just migrated from a hot wallet" (tx at slot 447193824) | That tx set the authority of a **buffer**, not the ProgramData. The ProgramData authority was rotated on 2026-04-22 (slot 414,868,623) from Squads v3 `EXZY7F...` (authority `GThUX1...`, 2-of-3) to the current Squads v4 vault, through a Squads v3 execute. No hot wallet ever held it in the history read. The on-curve `BufAu6...` key only writes buffers and receives the spill lamports. | `scout_check.py event 47duNi... A7ZG7B... setAuthority GThUX1... FytDrV... SMPLec... EXZY7F...` |
| Jupiter Perps "setAuthority rotation at slot 445758654" | Also a buffer. The ProgramData rotation happened on 2026-02-11 (slot 399,483,202), from Squads v3 `7ZyDFz...` (the same 4-of-7 multisig that holds Jupiter Aggregator v6) to the current Squads v4 vault. Last upgrade: slot 413,092,478 (2026-04-14). | `scout_check.py event UYRvx1... C258Lj... setAuthority CvQZZ2... 5myNNm... SMPLec... 7ZyDFz...` |
| Save "not upgraded for about 440,000 slots, well over a year" | Wrong arithmetic. Last upgrade slot 350,614,570 = 2025-07-02, i.e. about 97 million slots and **442 days** before this run. The authority itself was rotated on 2026-04-04 (three direct `setAuthorityChecked` calls, slots 410,931,404 to 410,931,549, between two on-curve keys). | block times via `getBlockTime`, claim 12 |
| JitoSOL: "2 of 3 full-power paths unresolved, composite 8" | Both paths are now resolved and neither is full-power. `manager` is the native treasury of Jito DAO governance `8cEhMT...`; `staker` is a Steward program account. From the SPL Stake Pool source, both are bounded (fees with a two-epoch delay for epoch fees, delegation, deposit gating), so the only full-power path is the SPL Stake Pool upgrade authority. | section "JitoSOL" below |

## Summary table

Sub-scores are for the **upgrade-authority path**, which is full-power for every target. Where a
protocol's own config admin (market owner, group admin, pool state admin) was not decoded this
run, the composite is an **upper bound**: METHODOLOGY 6.2 takes the minimum over full-power paths,
so an undecoded admin path can only lower it. Decoded config admins are listed in the context column.

| # | Protocol | Program id(s) | Source of the address | TVL on Solana (DefiLlama, 2026-09-17) | Authority pattern (live) | admin / multisig / timelock | composite | Verification (claims file ids) | Mitigating / aggravating context |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Raydium (AMM v4, CLMM, CPMM, LaunchLab) | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`, `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`, `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`, `LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj` | raydium-io/raydium-sdk-V2 `src/common/programId.ts` | > $1.0B (`raydium-amm`, per-program split not verified) | One Squads v4 vault `FytDrV...` (vault 0 of `tr8rga...`) for all 4 programs, 3-of-4, `time_lock = 0`, autonomous | 50 / 75 / 0 | **43** (upper bound) | 1, 2, 3 | Aggravating: one 3-of-4 with no delay upgrades four programs. Mitigating: moved on 2026-04-22 from a Squads v3 2-of-3 to this 3-of-4 (a strict improvement, not a hot-wallet migration). Pool/config admins not decoded. |
| 2 | Orca Whirlpool | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | orca-so/whirlpools README | > $200M (`orca-dex`) | Squads v4 `BQsDWk...` vault 0, threshold 5, 13 members of which **9 voters**, `time_lock = 86400` | 80 / 97 / 50 | **76** (upper bound) | 4 | Mitigating: 24 h delay, 5-of-9 real quorum. `WhirlpoolsConfig` fee/reward authorities not decoded. |
| 3 | Marinade Liquid Staking | `MarBmsSgKXdrN1egZf5sqe1TMai9K1rChYNDJgjq7aD` | marinade-finance/liquid-staking-program `lib.rs` `declare_id!` | > $200M (`marinade-liquid-staking`) | Legacy serum-style multisig program `msigmtwz...` (immutable), account `magrsH...`, 6-of-13, signer PDA `551FBX...` re-derived with bump = stored nonce 253 | 60 / 100 / 0 | **54** (upper bound) | 5, 6 | Methodology gap H1 still open: this multisig type has no timelock field, scored like Squads v3. Marinade `State.admin_authority` not decoded. Shares a signer with the SPL Stake Pool committee and with Sanctum (see cross-exposure). |
| 4 | marginfi | `MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA` | mrgnlabs/marginfi-v2 `Anchor.toml` `[programs.mainnet]` | > $25M (`marginfi-lending`) | Squads v4 `7FCPip...` vault 0, 7-of-15, all voters, `time_lock = 0` | 60 / 100 / 0 | **54** (upper bound) | 7 | Aggravating: no delay on a lending program. `MarginfiGroup.admin` and oracle setup not decoded. |
| 5 | Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | MeteoraAg/dlmm-sdk `ts-client/src/dlmm/constants/index.ts` | > $150M (`meteora-dlmm`) | Squads v3 `CoEsyk...` authority index 1 (`JADaUV...`), 4-of-7 | 55 / 83 / 0 | **47** (upper bound) | 8 | Squads v3 has no delay field. Same authority as #6 and #7. Shares a signer with Jupiter. |
| 6 | Meteora DAMM v1 | `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` | MeteoraAg/damm-v1-sdk `ts-client/src/amm/constants.ts` `PROGRAM_ID` | > $30M (`meteora-damm-v1`) | same as #5 | 55 / 83 / 0 | **47** (upper bound) | 8 | Blast radius: one 4-of-7 without delay controls three Meteora DEX programs. |
| 7 | Meteora DAMM v2 | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | MeteoraAg/damm-v2 `programs/cp-amm/src/lib.rs` `declare_id!` | > $15M (`meteora-damm-v2`) | same as #5 | 55 / 83 / 0 | **47** (upper bound) | 8 | Last upgrade 2026-09-08 (actively maintained). |
| 8 | PumpSwap (and pump.fun bonding curve) | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`, `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | pump-fun/pump-public-docs `idl/pump_amm.json`, `idl/pump.json` (`address`) | > $250M (`pumpswap`; `pump.fun` itself lists 0 TVL) | Squads v4 `2yMoQq...` vault 0, 3-of-4, `time_lock = 0` | 50 / 75 / 0 | **43** (upper bound) | 9 | Aggravating: frequent upgrades (2026-09-12, 2026-09-15) with no delay; one multisig for both programs. `GlobalConfig` admin not decoded. |
| 9 | Save (ex Solend) | `So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo` | solendprotocol/solana-program-library `token-lending/program/src/lib.rs` | > $50M (`save`) | **Single on-curve key** `RY93CZ...`, no multisig wrapper | 5 / 0 / 0 | **2** | 10, 11, 12 | Mitigating: last upgrade 2025-07-02 (442 days before this run). Aggravating: the key was rotated on 2026-04-04 by direct signatures between two on-curve keys, so it is live and used; nothing on-chain prevents an instant upgrade of a lending program. |
| 10 | SPL Stake Pool program (shared infrastructure) | `SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy` | jito-foundation/jito-omnidocs "Deployed Programs"; `declare_id!` in igneous-labs/sanctum-spl-stake-pool | n/a (infrastructure behind JitoSOL and others) | Squads v3 `3yqoHF...` authority index 1 (`dPpFfa...`), 6-of-10 | 60 / 100 / 0 | **54** | 13, 25 | Jito docs describe the upgrade keys as "a committee of Solana Staking Ecosystem participants". Aggravating: 5 of its 10 signers are also signers of Sanctum's 6-of-11 (see cross-exposure). |
| 11 | Jito Liquid Staking (JitoSOL) | pool `Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb` on #10, mint `J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn` | jito-omnidocs "Deployed Programs" | > $900M (`jito-liquid-staking`) | Full-power: #10's upgrade authority. Bounded: manager = Jito DAO treasury, staker = Steward, stake deposit authority = Interceptor | 60 / 100 / 0 | **54** | 13, 14, 15, 16, 17 | See section below. Mint authority is the pool's withdraw PDA (no human key can mint JitoSOL). |
| 12 | Jupiter Perpetual Exchange | `PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu` | dev.jup.ag `docs/perps/position-account.md` (official) | > $600M (`jupiter-perpetual-exchange`) | Squads v4 `AxkJ8o...` vault 0, 4-of-8, `time_lock = 86400`, autonomous | 75 / 80 / 50 | **69** (upper bound) | 18, 19, 20 | Mitigating: 24 h delay since the 2026-02-11 move off the no-delay Squads v3 of Jupiter v6. Oracle ("Doves") authority not scored (open point). Shares a signer with Meteora. |
| 13 | Jupiter Lend (liquidity, lending, vaults, oracle) | `jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC`, `jup3YeL8QhtSx1e253b2FDvsMNC87fDrgQZivbrndc9`, `jupr81YtYssSyPt8jbnGuiWon5f6x9TcDEFxYe3Bdzi`, `jupnw4B6Eqs7ft6rxpzYLJZYSnrpRgPcr589n5Kv4oc` | jup-ag/jupiter-lend `target/idl/*.json` (`address`) and `docs/earn/cpi.md` mainnet table | > $900M (`jupiter-lend`) | Squads v4 `J3mJ3w...` vault 0 for all 4 programs, 4-of-6, `time_lock = 43200` (12 h) | 65 / 87 / 25 | **60** (upper bound) | 21 | Aggravating: the lending oracle program shares the same 4-of-6 as the lending logic, so one quorum can change both code and price source. Mitigating: 12 h delay. Protocol-level auths not decoded. |
| 14 | Kamino Liquidity (yvaults) | `6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc` | Kamino-Finance/kliquidity-sdk `src/@codegen/kliquidity/programs/yvaults.ts` | > $50M (`kamino-liquidity`) | Squads v4 `E7994U...` vault 0, 5-of-7, `time_lock = 86400` | 80 / 100 / 50 | **77** (upper bound) | 22 | All 7 members are also members of the Kamino Lend upgrade multisig already scored (same protocol group, so no cross-exposure penalty). Strategy admin not decoded. |
| 15 | Sanctum Infinity (S Controller) | `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx` | learn.sanctum.so "Deployed programs"; igneous-labs/S `s_controller_interface` `declare_id!` | > $150M (`sanctum-infinity`) | Upgrade: Squads v3 `AApfiP...` authority index 1 (`47SND7...`), 6-of-11. Pool admin (decoded): Squads v4 `8EamQU...` vault 0, 4-of-8, `time_lock = 0` | min(60,55) / min(100,80) / 0 = 55 / 80 / 0 | **46** | 23, 24 | Pool `admin` is full-power: `SetSolValueCalculator` and `SetPricingProgram` decide how every LST is valued. The 7 SOL value calculator and pricing programs share the same upgrade authority `47SND7...`. `rebalance_authority` is a single on-curve key but bounded: `EndRebalance` must follow in the same transaction and rejects any drop in pool SOL value. |
| 16 | Sanctum Validator LSTs (SanctumSpl, SanctumSplMulti stake pool programs) | `SP12tWFxD9oJsVWNavTTBZvMbA6gkAmxtVgxdqvyvhY`, `SPMBzsVUuoHA4Jm6KunbsotaahvVikZs1JyTW6iJvbn` | learn.sanctum.so "Deployed programs" | > $1.0B (`sanctum-validator-lsts`) | Same upgrade authority as #15 (Squads v3 6-of-11) | 60 / 100 / 0 | **54** | 23 | Per-LST pool managers (bounded class, like Jito) not enumerated. |

## JitoSOL: full authority chain

| Role | Holder (live read) | Controller | Class (METHODOLOGY 6.2) | Why |
|---|---|---|---|---|
| SPL Stake Pool upgrade | `dPpFfa...` | Squads v3 `3yqoHF...` 6-of-10, no delay | full-power | new code can move all pool stake |
| `manager` | `5eosrv...` | native treasury (bump 253) of governance `8cEhMT...` in the Jito DAO governance program `jtogvB...`, realm `jjCAwu...`: council threshold 51% of a council mint whose supply is 7 tokens (mint authority: the same treasury), voting 5 days, cool-off 2 days, hold-up 0 | bounded | `process_set_fee`: epoch and withdrawal fees go through `FutureEpoch::new` (two epochs) and withdrawal-fee increases are capped by `MAX_WITHDRAWAL_FEE_INCREASE`; deposit and referral fees apply immediately (up to 100%, so they hit new deposits only); `SetFundingAuthority` only gates SOL deposit, SOL withdraw and stake deposit, `WithdrawStake` stays permissionless |
| `staker` | `9BAmGV...` (owned by Steward `Stewardf95...`) | Steward upgrade authority `8EP3Vo...` = vault 0 of Squads v4 `AJVQRH...`, 4-of-7, `time_lock = 0`, **controlled** by `config_authority DG76d6...` | bounded | staker moves stake between validators and the reserve, it cannot withdraw it |
| `stake_deposit_authority` | `6hg6RM...` (owned by Interceptor `5TAiuA...`) | Interceptor upgrade authority is the same `8EP3Vo...` | bounded | deposits only |
| JitoSOL mint authority | `6iQKfE...` | PDA `[pool, "withdraw"]` of the SPL Stake Pool program | n/a | only the stake pool program can mint |

Context on `DG76d6...`: off-curve, no account, zero signatures at read time. Squads v4 source
(`config_transaction_create.rs`) rejects config transactions on a controlled multisig
(`NotSupportedForControlled`), so member and threshold changes of the Steward multisig can only
come from that key, which has never signed. Its holder stays unresolved (ladder rung 5), but the
path is bounded, so it does not change JitoSOL's composite. The Jito governance program
`jtogvB...` is itself upgradeable by the native treasury of the council-only governance
`EA4eoK...` (council 51%, voting 3 days, cool-off 2 days, hold-up 0).

## Cross-exposure (Solana groups only)

Groups: the 16 targets above plus the two already scored (Jupiter v6 and Kamino Lend, whose
multisigs are merged into the `jupiter` and `kamino` groups). Root signers are the on-curve
members of every multisig resolved for a group (no off-curve members were found). Formula from
`METHODOLOGY.md` section 4: `max(0, 100 - 20 x sharedGroupCount)`.

| Group | Shares on-curve signers with | Count | crossExposureScore (Solana only) |
|---|---|---|---|
| sanctum | spl-stake-pool committee (5 keys), marinade (2 keys) | 2 | 60 |
| spl-stake-pool committee (and JitoSOL, which inherits it) | sanctum (5 keys), marinade (`3LPh9L...`) | 2 | 60 |
| marinade | spl-stake-pool committee, sanctum | 2 | 60 |
| meteora | jupiter (`CHRDWW...`, in the Jupiter Perps 4-of-8) | 1 | 80 |
| jupiter | meteora | 1 | 80 |
| raydium, orca, marginfi, pump, save, jito (own multisigs), kamino | none | 0 | 100 |

Most notable: the SPL Stake Pool committee needs 6 of 10 signatures and 5 of those 10 keys also
sit on Sanctum's 6-of-11. Mitigating: the committee is documented as made of staking ecosystem
participants, of which Sanctum is one, so overlap is expected, but it means the stake pool
program behind JitoSOL and Sanctum's own stake pool programs are one extra signer apart in the
worst case. Not yet cross-checked against other ecosystems' Safes (keys are Ed25519, so an
overlap with EVM signers is impossible by construction; only other SVM groups could overlap).

## Candidates looked at and not retained

| Candidate | Reason |
|---|---|
| Drift v2 `dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH` | Authority resolved (Squads v4 `7qipzL...`, 4-of-7, 6 voters, `time_lock = 3600`) but DefiLlama `drift-trade` reports about $0.6M on Solana today, so the "real value" bar is not met without an explanation of that figure. |
| Binance Staked SOL, Jupiter Staked SOL, Phantom and other LST pools | Pool addresses need a primary source per pool; not collected this run. JupSOL-style pools inherit #16 once confirmed. |
| Token mints (USDC, PYUSD, JitoSOL) as separate targets | Asset-level authorities, a different target type; JitoSOL mint authority recorded above only as context. |

## Open points for scoring_build

- Decode the protocol config admins marked "not decoded" (Raydium AMM config, Whirlpools config, marginfi group, Marinade state, Pump global config, Save lending market owner, Jupiter Lend and Perps admins, Kamino strategy admin) before promoting an upper bound to a score.
- Methodology gap H1 (legacy serum-style multisig) and a rule for "controlled multisig with an unresolved `config_authority` on a bounded path" should be written into `METHODOLOGY.md`.
- Jupiter Perps oracle authority ("Doves") and Jupiter Lend oracle program need the 6.3 treatment.

## Reproduction

```
python3 chains/solana/scripts/scout_check.py authority 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 FytDrVzDybM1TwFQPGb8qaxZR7dBCzNeqT3vtQsceZQK
python3 chains/solana/scripts/scout_check.py v4 tr8rgazUrZzgdkfc6Q622nVJHMMzh29trdBE2uBHb4u 0 FytDrVzDybM1TwFQPGb8qaxZR7dBCzNeqT3vtQsceZQK 3 4 4 0
python3 chains/solana/scripts/scout_check.py v4 BQsDWkL417U4tVE2sDnPks469pKdm6YzFgKH77doiEjF 0 GwH3Hiv5mACLX3ufTw1pFsrhSPon5tdw252DBs4Rx4PV 5 13 9 86400
python3 chains/solana/scripts/scout_check.py coral magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed msigmtwzgXJHj2ext4XJjCDmpbcMuufFb5cHuwg6Xdt 551FBXSXdhcRDDkdcb3ThDRg84Mwe5Zs6YjJ1EEoyzBp 6 13
python3 chains/solana/scripts/scout_check.py v4 7FCPipJWVbPbdHymVt1gJYwKciakkJz5GahdQySemvHk 0 J3oBkTkDXU3TcAggJEa3YeBZE5om5yNAdTtLVNXFD47 7 15 15 0
python3 chains/solana/scripts/scout_check.py v3 CoEsykatDegLB7pcMJia79JSriDdi71nPnjgeSfw623k 1 JADaUV8kvDpDbJr55wxXJHVaBS3VCj8thZZHjfeuCVLd 4 7
python3 chains/solana/scripts/scout_check.py v4 2yMoQqQrtbhq3nQ3wFoQQawWS65qcqUXcwHEYha4rshW 0 7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8 3 4 4 0
python3 chains/solana/scripts/scout_check.py authority So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo RY93CZYe5g6drtG7W9PmHRPzaBLZ1uwihTzayQTmJfh
python3 chains/solana/scripts/scout_check.py v3 3yqoHFE4nBGchuVH5rJuZMFvsmnaDTuLLdvGPDUEJcbW 1 dPpFfahSWhm5M2RB3nVaHsXfnh9ooz5bWtR3WeUguDH 6 10
python3 chains/solana/scripts/scout_check.py gov 8cEhMTswovtkzQKWZx7h66bL2ZKF8fBADyzfL6MPt4PK 5eosrve6LktMZgVNszYzebgmmC7BjLK8NoWyRQtcmGTF 0 432000 172800
python3 chains/solana/scripts/scout_check.py jitopool 5eosrve6LktMZgVNszYzebgmmC7BjLK8NoWyRQtcmGTF Stewardf95sJbmtcZsyagb2dg4Mo8eVQho8gpECvLx8 6iQKfEyhr3bZMotVkW6beNZz5CPAkiwvgV2CTje9pVSS
python3 chains/solana/scripts/scout_check.py v4controlled AJVQRHk9rg25HzE2TompdcjfvQGuZdytPXhU1SgxUxBa 0 8EP3VommYzMRSdnSn88GnQpxjRwxg6nroTeUNJoqu9b8 4 7 0 DG76d6Akr3pzGUkE8gc3anBrSJUzH6EiXmqoX3P7ontL
python3 chains/solana/scripts/scout_check.py v4 AxkJ8oH5aDu4ZRWfsujPtxdb6Vhq4gDehpoReBgrUUSm 0 5myNNmEmPm3UAnJ2ggLEpnTFb9t9Gk8369wKw6n3uAKx 4 8 8 86400
python3 chains/solana/scripts/scout_check.py v4 J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P 0 4MsgBB5VPoTrUSp5XnfbViV386C1UnsTdifLBw33ZMSJ 4 6 6 43200
python3 chains/solana/scripts/scout_check.py v4 E7994UpSGhSpbpnuSepPXHBuMy3eRvHJL36DjTs1kb2b 0 3pAxu6C9ykZvyyzdknZvmz6CbWGZPTjRevjk4PRF5ib7 5 7 7 86400
python3 chains/solana/scripts/scout_check.py v3 AApfiPZgV5MoPU691GwhdDhq5sKEMMH1Uh8S4Z9xvP6b 1 47SND7bGKvNXrqfP1bjsLCbwTgZhFBzAgmZ42QSkRScz 6 11
python3 chains/solana/scripts/scout_check.py infinity-admin 8JS6XsMPo2u3EyeeY3p2jvzHEhdUtCKgarHpJ3PAonyv 5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm
python3 chains/solana/scripts/scout_check.py v4 8EamQU8L2ubwC4FHMxf5BfinEkUFknboK7gpPzvshWyo 0 8JS6XsMPo2u3EyeeY3p2jvzHEhdUtCKgarHpJ3PAonyv 4 8 8 0
```

Program authority reads for the other program ids in the table use the same `authority`
subcommand; the ProgramData history (upgrades and rotations, with the wrapping multisig) was
listed with `getSignaturesForAddress` on each ProgramData account and parsed `getTransaction`.
