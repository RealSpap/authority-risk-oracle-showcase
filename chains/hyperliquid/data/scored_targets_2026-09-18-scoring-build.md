# Hyperliquid: scoring_build pass, 2026-09-18

Closes the 5 "Rules needed before scoring_build" gaps
[`scouted_targets_2026-09-17-run2.md`](scouted_targets_2026-09-17-run2.md)
left open, and writes the scorer for every target that file verified live
at 3/3 but could not yet score. See
[`../METHODOLOGY.md`](../METHODOLOGY.md) section 4 for the 5 new/extended
rules (added inline, not a separate section) and
[`../scripts/scoring_build_2026_09_18.py`](../scripts/scoring_build_2026_09_18.py)
for every scorer's full derivation and live reads. All numbers below were
read live on 2026-09-18 and will drift (TVL, open interest, treasury
balances); the authority-chain facts (roles, thresholds, delays) are the
part expected to be stable.

## Summary table

| Target | adminKey | multisig | timelock | oracle | composite | l1Capped |
|---|---|---|---|---|---|---|
| HIP-3 dex `para` (**corrected**) | 5 | 10 | 0 | 10 | **5** (was 9) | 5 |
| Kinetiq HIP3StakingManager / kmHYPE (**oracle corrected**) | 10 | 0 | 0 | 7 (was 100) | 4 (unchanged) | 4 |
| Kinetiq kHYPE StakingManager (new) | 10 | 0 | 0 | 15 | **4** | 4 |
| Hyperliquidity Provider (HLP) vault (new) | 10 | 15 | 0 | 100 | **9** | 9 |
| Unit UBTC treasury (new) | 10 | 15 | 0 | 100 | **9** | 9 |
| Unit UETH treasury (new) | 10 | 15 | 0 | 100 | **9** | 9 |
| Unit USOL treasury (new) | 10 | 15 | 0 | 100 | **9** | 9 |
| Hyperliquid legacy USDC bridge (Bridge2) (new) | 65 | 59 | 15 | 100 | **48** | 26 |
| HyperLend Pooled (new) | 65 | 80 | 35 | 100 | **61** | 26 |

`l1Capped` = `min(compositeScore, 26)`, the Hyperliquid L1's own composite
(unchanged this pass) -- binds for every target above except `para`
(already below 26) and the four Kinetiq/HLP/Unit targets whose own
composite is already far below it.

## The 5 rules closed, and what each changed

1. **HyperEVM contract as HyperCore identity.** `para`'s deployer is a
   HyperEVM `StakingVault` (UUPS proxy), not a bare key -- `userToMultiSig
   Signers` reading `null` only means "not a HyperCore-native multisig," not
   "single key." Its real `addApiWallet` authority (CoreWriter action 9) is
   gated `onlyOperator`; `OPERATOR_ROLE` resolves (live, 2026-09-18) to a
   Safe with threshold=1 over 3 owners (2 bare EOAs + a nested 1-of-1 Safe,
   itself no stronger than a bare key) -- a genuine `(k=1, n=3)`, WEAKER
   than the generic single-key `(1,1)` reading (METHODOLOGY.md 4.2 rule 1:
   a 1-of-N with N>1 is strictly weaker than one key). `adminKeyScore`
   10->5, `multisigScore` 15->10, `oracleAuthorityScore` 15->10 (para's
   `oracleUpdater` field is empty, so the deployer is its own oracle
   updater -- same resolved key applies), `compositeScore` 9->5. `mkts`
   needed NO override: its own resolved single-EOA root (`exWalletAdmin`)
   happens to coincide with the generic single-key reading -- reconfirmed
   live this pass, not assumed from the prior scouting note.

2. **Bounded vs unbounded oracle push** (Kinetiq `OracleManager`s). A
   single EOA can push a reward/slash report once per validator per 24h for
   both kHYPE and kmHYPE (live-confirmed `MIN_UPDATE_INTERVAL=86400`).
   kHYPE's `ValidatorSanityChecker` (a real, live contract) caps each push
   to 3 bps reward / 1 bps slash of the validator's balance and a 300 bps
   balance-drift anchor -- `oracleAuthorityScore=15` (the ordinary
   single-key floor, since the size cap is what makes a compromised key
   survivable). kmHYPE has `sanityChecker() == address(0)` (live-confirmed)
   -- no cap at all -- `oracleAuthorityScore=7`. Patched into the EXISTING,
   already-committed `score_kinetiq_staking_manager()` (kmHYPE's own
   result) as a post-processing correction in `scorers.py`, not a change to
   that adversarially-reviewed function's source; does not touch
   `compositeScore` (oracleAuthorityScore is not a `composite()` input).

3. **Vault leader, trading authority without custody** (HLP). Scored on
   the standard single-key ladder (`leader` reads `userToMultiSigSigners`
   null -> `(1,1)` -> `adminKeyScore=10`, `multisigScore=15`) --
   `leaderCommission=0` (live) confirms the leader cannot skim depositor
   funds to itself, disclosed as the reason this is TRADING risk, not
   custody risk, rather than invented as a separate formula.
   `compositeScore=9`.

4. **Spot treasury holding unissued supply** (Unit UBTC/UETH/USOL). HIP-1
   has no mint after genesis, so the treasury address (a DIFFERENT address
   than the token's deployer) is the practical mint authority. All three
   treasuries read `userToMultiSigSigners=null` live -> single key ->
   `compositeScore=9` each. Unit's own docs claim an off-chain 2-of-3 MPC
   scheme (Unit + Hyperliquid + Infinite Field) the chain itself cannot
   verify -- recorded as mitigating context in `notes`, not folded into the
   score, the same choice already made for the L1's "Hyper Foundation"
   validator labels (METHODOLOGY.md 3.2).

5. **Short dispute periods** (Bridge2). `disputePeriodSeconds()=200`
   (live) -> `timelockScore=15` (a new numeric value; METHODOLOGY.md 4.3
   previously left this unassigned). Root control is a live-decoded 3-of-4
   equal-weight hot/cold set (`admin_key_score(3,4)=65`,
   `key_score(3,4)=59`) -- these two numbers match
   `scouted_targets_2026-09-17-run2.md` target #9's own pre-computed
   provisional figures exactly. `compositeScore=48`.

HyperLend Pooled needed no NEW rule (a standard Aave-v3-fork +
`TimelockController` pattern, same shape `chains/arbitrum-ecosystem/
scorers.py::score_radiant_lendingpool` already established) but had not
been scored yet: two independent timelocks (7-day for `POOL_ADMIN`/logic
upgrades, 6-hour for `RISK_ADMIN`/`ASSET_LISTING_ADMIN`), same
Governance-Safe-proposes/Treasury-Safe-executes pair on both, live-checked
to share no owner (`openExecutor(address0)=false`, so execution genuinely
needs the Treasury Safe's own cooperation, not open to anyone). Scored on
the weaker (6h) timelock path per METHODOLOGY.md 6.2's minimum-over-paths
convention -- `timelockScore=35`. `PoolAddressesProvider.owner()` is a
two-hop chain (`ExecutorLive` -> `TimelockA`), both hops live-verified
during this pass (an earlier draft of the scorer's own notes mislabeled
the first hop as "expected TimelockA" directly -- caught and fixed before
this was committed, the same self-correction discipline this project
applies throughout). `EMERGENCY_ADMIN` (two Safes, no delay) can only
pause in Aave v3 semantics, not move funds -- disclosed as aggravating
context, not folded into the score, mirroring
`score_radiant_lendingpool`'s own precedent for a real-but-different-kind
of risk. `compositeScore=61`.

## A found (and fixed) mislabel, disclosed rather than silently corrected

`score_kinetiq_staking_manager()`'s own docstring parenthetical read
"(kHYPE liquid staking)" -- but the address it actually scores
(`0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec`) is kmHYPE's `StakingManager`,
confirmed against `scripts/scout_2026_09_17_run2.py`'s own `KINETIQ`
address table and independently against `scored_targets_2026-09-17.md`'s
own table row ("SAME address as `mkts`/`km`"). The SCORE was always
correct (right address, right reads); only the docstring's product-name
annotation was wrong. Not edited in place (the function itself is
untouched this pass, per the "post-processing correction, not a rewrite"
choice above) -- disclosed here and in METHODOLOGY.md's changelog instead,
for whoever next touches that function to fix in the same pass they're
already editing it.

## What this does NOT cover yet

- `OPERATOR_ROLE`'s exact gated functions on kHYPE's own `StakingManager.
  sol` were inferred by structural analogy to kmHYPE's sibling contract
  (same Kinetiq codebase, same role name, same 4-of-8 root), not
  independently re-verified by reading kHYPE's own verified source line by
  line. Worth closing on a future pass, though it could not change
  `compositeScore` either way for the reason the module docstring gives
  (`OPERATOR_ROLE`'s bare-EOA holder is already the near-floor binding
  constraint on this contract).
- Bridge2's 8 hot/cold addresses were live-checked against every active L1
  validator/signer address (zero overlap) but NOT swept against every
  HIP-3 dex/Kinetiq/Unit signer set on HyperCore/HyperEVM -- different
  network in practice, though the address FORMAT is identical and reuse is
  not structurally impossible. Left as an open item given this pass's time
  budget, not assumed clean.
- Whether `RISK_ADMIN`'s 6-hour-timelocked power on HyperLend (asset caps,
  new listings) could, in the worst case, be used to indirectly endanger
  depositor funds (e.g. listing a manipulable asset) was not modeled
  quantitatively -- scored only via the timelock-length convention above.
- No new contract or program was deployed this pass (see the accompanying
  `deploy/` work) -- this file covers scoring only.

## Reproduction

```
python3 chains/hyperliquid/scripts/scoring_build_2026_09_18.py
python3 -c "
import sys; sys.path.insert(0, 'chains/hyperliquid')
from scorers import score_all
for r in score_all():
    print(r['label'], r['compositeScore'], r.get('l1CappedComposite'), r['oracleAuthorityScore'])
"
```
