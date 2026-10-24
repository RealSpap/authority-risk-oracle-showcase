# Redo it: one score, from public reads

Take one target, the Pendle V2 Router on Ethereum mainnet (`0x888888888889758F76e7103c6CbF23ABbF58F946`), and rebuild its score yourself. No account, no key, no transaction: public RPC reads, with [Foundry](https://getfoundry.sh)'s `cast`.

The score is held by the Authority Risk Oracle on Ethereum L1 (Sepolia testnet), `0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906`. It was written at its last push (2026-10-20 00:07 UTC); it is not a reading of today. The oracle is a testnet deployment.

## Run it
```bash
bash commandes.sh      # about ten read calls, a few seconds
```
It prints the published score, then reads the chain and says `VERDICT: MATCH` when the reads end at ONE Safe and the recomputed scores equal the published ones, and never otherwise: any other outcome, including a dead RPC, prints `VERDICT: NO MATCH`.

## What it prints (run on 2026-10-22, Ethereum block about 26 246 600)
```text
1. The published score (oracle on Sepolia): admin, multisig, timelock, oracle-authority, cross-exposure, composite
   65 55 0 100 80 43 
2. Four paths that must all end at ONE Safe (0x8119EC16F0573B7dAc7C0CB94EB504FB32456ee1)
   Router.owner()                 = 0x8119EC16F0573B7dAc7C0CB94EB504FB32456ee1
   Router.pendingOwner()          = 0x0000000000000000000000000000000000000000   (zero: no transfer in flight)
   MarketFactory proxy admin      = 0xa28c08f165116587d4f3e708743b4dee155c5e64
   ProxyAdmin.owner()             = 0x8119EC16F0573B7dAc7C0CB94EB504FB32456ee1
   YieldFactory.owner()           = 0x8119EC16F0573B7dAc7C0CB94EB504FB32456ee1
   MarketFactory.owner()          = 0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e   (must be the governance proxy 0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e)
   governance proxy: Safe is DEFAULT_ADMIN?     true
   governance proxy: deployer is DEFAULT_ADMIN? false   (must be false)
   the four paths end at the Safe: yes
3. The Safe
   threshold = 3, owners = 5, version = "1.4.1", modules = []
   singleton (slot 0) = 0x00000000000000000000000041675c099f32341bf84bfc5382af534df5c7461a   (the published Safe v1.4.1 singleton ends in 5c7461a)
4. The rule applied to what was read (Safe rule of chains/ethereum-l1/scorers.py, score_convex_finance_booster; multisig formula in METHODOLOGY.md):
   admin = 65 if threshold >= 3, 50 if 2, else 10; multisig = min(100, 15t + 5(n - t)); timelock = 0 when no path read above goes through a delay
   admin = 65, multisig = 55, timelock = 0  ->  composite = floor(0.4*65 + 0.3*55 + 0.3*0 + 0.5) = 43
5. A timelock exists but is on none of the paths above, so it is not credited: TimelockController 0x68d8D192dF476bC01895E16b0ED3945673d777AC getMinDelay() = 172800 s
   Oracle-authority (100) and cross-exposure (80) are read from the oracle in step 1 and are not recomputed here.
VERDICT: MATCH (admin/multisig/timelock = 65 55 0, composite = 43, as published)
```

## How to read it
- **Step 2.** The score holds when the Router, its proxy admin, the factory and the governance proxy all answer to the same Safe. Four paths are read; a path that ended somewhere else would change the score (the scorer then gives a conservative one, nothing assumed).
- **Step 3.** The Safe is a 3-of-5 on Safe version 1.4.1 with no module enabled. A module would act as the Safe without the signatures, so the scorer would not score the threshold.
- **Step 4.** Our rule for this kind of target: `adminKeyScore` is 65 for a Safe threshold of 3 or more; `multisigScore` is `min(100, 15 t + 5 (n - t))`, here 15 x 3 + 5 x 2 = 55; `timelockScore` is 0 when no path read goes through a delay. The composite is `floor(0.4 x 65 + 0.3 x 55 + 0.3 x 0 + 0.5) = 43`, the number the oracle holds.
- **Step 5.** Pendle has a timelock (a 2-day `getMinDelay()`), but none of the paths read in step 2 goes through it, so it is not credited. This is written in the scorer's notes.

## What this does not show
It shows that one published number follows from public reads and a written rule. It does not show that the rule is right, that a 3-of-5 Safe is safe, who holds the five keys, or that the score predicts anything. The four-path check is done by our scorer, which is not yet in the public repository; step 2 above redoes it by hand. Cross-exposure (80) and oracle-authority (100) are read from the oracle and are not recomputed here.

If a number differs on your side, open an issue with the output of `commandes.sh`.
