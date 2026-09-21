# Ethereum L1: Aave V3 Horizon scored, 2026-09-20

Adds `score_aave_v3_horizon_pool()` to `chains/ethereum-l1/scorers.py`, appended last in `SIMPLE_SCORERS`.
Aave Horizon is the RWA instance of Aave V3 on Ethereum (PoolAddressesProvider
`0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0`). The existing Aave target scores the main pool only. A read of
DeFiScan's public review of Aave V3 (defiscan.info/protocol/aave-v3) names a "Horizon Admin" 4-of-6 multisig
with takeover powers, and a search of this repo for "horizon" found no scorer, so the gap was ours.

## Result

| Target | admin / multisig / timelock / oracle | cross | composite |
|---|---|---|---|
| Aave V3 Horizon Pool | 65 / 70 / 0 / 100 | 80 | **47** |
| Aave V3 Ethereum Pool (unchanged) | 78 / 100 / 55 / 100 | 80 | 78 |

The main pool does not move: it was already at 80 (cross-ecosystem committee fold), and grouping it with Horizon
under one governance root gives the same 80. No other target moves.

## What was read (2026-09-20, two RPCs, publicnode and drpc)

- `owner()` and `getACLAdmin()` of the provider are the Aave governance Executor `0x5300A1a1...`, the same
  executor as the main pool. Only that executor holds `DEFAULT_ADMIN`, and every role is administered by
  `DEFAULT_ADMIN`, so only governance adds or removes a role holder.
- Two Safes hold roles directly, with no module (so no delay module), both Safe v1.4.1:

| Role | Holders now |
|---|---|
| `POOL_ADMIN` | Executor, Safe `0x13B57382...` **4-of-6** |
| `EMERGENCY_ADMIN` | Executor, the same 4-of-6 |
| `RISK_ADMIN` | Safe `0xE6ec1f0A...` **3-of-4**, contract `0x09e8E140...` (1620 bytes, not a Safe, not identified), the GHO direct minter |
| `ASSET_LISTING_ADMIN` | contract `0x09e8E140...` |
| role `0x1bcbc82a...` (name not identified) | the RWA aToken manager |

- The role history (16 `RoleGranted`/`RoleRevoked` events, from Blockscout because the public RPCs refuse
  `eth_getLogs`) replays to exactly this table, independently of the `hasRole` reads.
- The verified `PoolConfigurator` implementation source puts `updateAToken`, `updateVariableDebtToken`,
  `dropReserve`, `setReserveActive` and the flash-loan premium setters behind `onlyPoolAdmin`, and
  `UpdateATokenInput` carries a caller-supplied `address implementation`. So the 4-of-6 can, by reading the
  code, replace an aToken implementation immediately. That is the full-power path and the one scored.
- The two Safes share three signers (`0xb647...`, `0x2fe3...`, `0x606d...`), which is the whole 3-of-4 threshold.
  None of the seven Horizon signers is in the 9-signer or the 7-signer Aave committee already tracked here.

## Derivation

The Ethereum L1 Safe rule (the one `score_morpho_blue_l1` uses): admin 65 for a threshold of 3 or more,
multisig = min(100, 15t + 5(n - t)) = 60 + 10 = 70, timelock 0, composite = (4x65 + 3x70 + 3x0 + 5) // 10 = 47.
The 1-day delay on the governance path does not bind the Safe's path, so the timelock is 0.
The 3-of-4 risk Safe is bounded (it cannot swap a token implementation), so it is disclosed and not scored,
the same convention as Sanctum's rebalance authority on Solana.

## Not done, and what the score does not claim

- **Not on-chain.** The oracle does not track this target yet. By the 2026-09-20 rule the push is Spap's. The four
  targets it had to follow went on-chain at 18:37 UTC (proposal), so `trackedTargetsCount()` reads 19 today
  and would read 20 after it.
- **No independent verifier has decided yet.** Proposal #136 was still without a decision when this was merged into
  main, on the owner's instruction and not on approval. If it is rejected, the merge is to be reverted.
- **Access is confirmed by simulated calls; a full aToken swap is not.** `eth_call` from the 4-of-6 Safe (nothing is
  sent) passes the `onlyPoolAdmin` modifier of `dropReserve` and `updateAToken` on both RPCs, and reverts later
  on the dummy or real reserve it was given (error 82, or no reason). The 3-of-4 risk Safe and a stranger get
  error 1 (CALLER_NOT_POOL_ADMIN). `setSupplyCap` (`onlyRiskOrPoolAdmins`) passes for both Safes and fails with
  error 4 for a stranger. An `updateAToken` on the real USDC reserve with the current default aToken
  implementation also reverts without a reason after the modifier; the cause was not identified, so the claim
  is "the Safe holds the right to call it", not "the swap was executed or simulated to success". It is also
  assumed, as in the standard Aave V3 design, that the aToken proxy's admin is the configurator; that was not read.
- **Holders found by history, verified by state.** The scorer checks the known holders on every run, and raises if
  the executor root changes or the 4-of-6 loses `POOL_ADMIN`, but it cannot discover a holder added later.
- **Unidentified.** The contract `0x09e8E140...` and the signers behind both Safes. DeFiScan's "2 EOAs" for Aave do
  not appear among the Horizon role holders.
- DeFiScan's "$7.15B impact" for this Safe was not measured here.

## Reproduction (read-only, no key)

```
python3 chains/ethereum-l1/scripts/check_horizon_authority.py   # 26 checks, prints ALL CHECKS OK
python3 -B -m unittest discover -s scripts/lib/tests -p "test_aave_horizon_scorer.py"
```
