# Base Ecosystem -- scored targets, 2026-09-16 (scoring_build phase, attempt 1)

Phase: scoring_build. Scores the exact 5 targets approved 3/3 in the scouting
pass (maker-checker action 9), documented in full trace in
`data/scouted_targets_2026-09-16.md`. Every number below is re-derived live
by `chains/base-ecosystem/scorers.py` against `https://mainnet.base.org`
(chain 8453, block ~51,400,700), re-run via `chains/base-ecosystem/scripts/dry_run.py`
-- not replayed from the scouting pass's hand-run `cast` calls. Re-running
`dry_run.py` re-derives every score from live chain state; if a target's real
on-chain configuration changes (a key rotated, a Safe reconfigured, a delay
tuned), the next run picks that up automatically.

Scoring grid and weighting reused exactly from `scripts/lib/scorers.py` /
`chains/ethereum-l1/scorers.py`: `compositeScore = floor(0.4*adminKeyScore +
0.3*multisigScore + 0.3*timelockScore + 0.5)`. `oracleAuthorityScore` is 100
for all 5 (not applicable -- none of these targets is itself an oracle/
price-feed authority). `crossExposureScore` is also 100 for all 5, but for a
different, explicitly disclosed reason: no cross-ecosystem signer-overlap
dataset has been built yet between Base and the other tracked ecosystems
(that machinery, `scripts/lib/signer_overlap.py`, is scoped to Robinhood
Chain's own target set today) -- treated as "not applicable" per this
project's stated convention, not as a confirmed clean result.

> UPDATED 2026-09-20: that paragraph describes 2026-09-16 and is no longer
> the current state; the table below is left as that day's record. Base
> already folds cross-ecosystem overlaps into `crossExposureScore`: Aave V3
> Base reads 80 since 2026-09-17 (its guardian Safe has the same 9 owners as
> Arbitrum's), and Morpho Blue reads 80 in the 2026-09-19 maintenance run
> (same 9 owners as the Ethereum L1 and Robinhood Chain Morpho Safes; see
> `scored_targets_2026-09-19-maintenance.md`). The project-wide rule, decided
> 2026-09-20 to make every ecosystem behave this way, is the root
> `METHODOLOGY.md` paragraph "Convention (decided 2026-09-20)". The 2026-09-20
> sweep changed no Base score.

## Summary table

| Protocol | Address | TVL (Base) | adminKey | multisig | timelock | composite |
|---|---|---|---|---|---|---|
| Morpho Blue (singleton) | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | ~$3.9B | 65 | 95 | 0 | **55** |
| Aave V3 Base (PoolAddressesProvider) | `0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D` | ~$500M | 65 | 100 | 50 | **71** |
| Aerodrome Finance PoolFactory | `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` | ~$323M | 65 | 65 | 0 | **46** |
| Uniswap V3 Factory (Base) | `0x33128a8fC17869897dcE68Ed026d694621f6FDfD` | ~$271M | 80 | 100 | 75 | **85** |
| Compound V3 (Comet, USDC market) | `0xb125E6687d4313864e53df431d5425969c15Eb2F` | ~$25M | 75 | 100 | 65 | **80** |

TVL figures are the same DefiLlama reads already independently confirmed in
the scouting pass (`data/scouted_targets_2026-09-16.md`), current as of that
pass -- not re-pulled this run (this run is a live on-chain authority re-scan,
not a TVL refresh); treat as an order of magnitude, not an exact live figure.

## 1. Morpho Blue (singleton) -- composite 55/100

Authority chain: `owner()` -> a real Gnosis Safe, **5-of-9**, one hop, fully
closed. `adminKeyScore=65` (threshold >= 3, per this project's
Safe-rooted-authority convention), `multisigScore=95` (5 required signatures
x 15 + 4 extra owners x 5), `timelockScore=0` (no `TimelockController` or
delay found anywhere in this chain).

Scope caveat, disclosed rather than folded into the score: Morpho Blue's
immutable-core design means this `owner()` can only set protocol fees and
enable new IRMs/LLTVs for FUTURE markets -- it cannot move funds already
deposited in existing markets. Scored on the authority root mechanism (the
Safe) itself, consistent with how every other Safe-rooted target in this
project is scored, not on the narrower operational blast radius.

## 2. Aave V3 Base (PoolAddressesProvider) -- composite 71/100

Authority chain, fully re-confirmed live this pass: `PoolAddressesProvider
.owner()` == `.getACLAdmin()` -> `EXECUTOR_LVL_1` <-> `PayloadsController`
(mutual `owner()` pointers, a genuine closed pair, not a loop hiding the real
authority -- standard BGD Labs Aave Governance V3 cross-chain infra).
`PayloadsController.getExecutorSettingsByAccessControl(1)` returns
`(EXECUTOR_LVL_1, 86400)` -- a real, live-confirmed **1-day** delay at this
access-control level. `PayloadsController.guardian()` also resolves to a
real address that can cancel proposals outside the timelock.

`adminKeyScore=65` (the closed executor/payloads-controller pair is real
infra, not an unresolved contract, but capped below a "confirmed active DAO"
score -- see gap below), `multisigScore=100` (not applicable, no Safe layer),
`timelockScore=50` (confirmed real 1-day delay, capped for the open gap below
plus the guardian's cancel-path outside the timelock).

**Open thread, disclosed rather than guessed**: this scorer confirms the
Base-side executor/payloads-controller pair matches the official
`bgd-labs/aave-address-book` exactly, but does NOT independently re-verify
the Ethereum-mainnet Aave DAO root (the `CROSS_CHAIN_CONTROLLER` relay, L1
proposal counts/quorum) -- that root lives on L1 and is covered separately by
`chains/ethereum-l1/scorers.py`'s `score_aave_v3_pool()`. **CORRECTED
2026-09-17**: the line above used to say the L1 side's `EMERGENCY_ADMIN_ROLE`
holder "was not identified" -- that was true when this file was first
written but stale by the time it was committed; the L1 scorer's own gap was
closed the same day (see `data/correction_2026-09-16-aave-emergency-admin-identified.md`
and `chains/ethereum-l1/scorers.py`'s `score_aave_v3_pool()` docstring --
`PROTOCOL_GUARDIAN`, a real 4-of-7 Safe, confirmed live). This file's own
in-scope open thread (independently re-verifying the L1 DAO root from this
Base-side vantage point) remains genuinely open for a future pass.

## 3. Aerodrome Finance PoolFactory -- composite 46/100

Authority: `owner()` reverts (confirmed live, expected -- no single-owner
design). `pauser()` and `feeManager()` both resolve, live, to the SAME
address: a real Gnosis Safe, **3-of-7**. `adminKeyScore=65` (threshold >= 3),
`multisigScore=65` (3 x 15 + 4 x 5), `timelockScore=0` (no delay found).

`voter()` was also read live this pass (`0x1661...480A5`, matches the
official README's Voter row exactly) but is NOT traced further by this
scorer -- it governs AERO emissions, arguably the higher-value lever than
pause/fee control, and is flagged as an open second authority root for a
future scoring pass rather than silently folded into this composite.

**CLOSED 2026-09-18**: `Voter.governor()` -- confirmed live, no longer an
open question. See `data/finding_2026-09-18-aerodrome-voter-governor-
identity.md` for the full trace: `governor()` is the EXACT SAME Safe as
`pauser()`/`feeManager()` above (not a coincidental shared signer -- the
identical address), so this composite already reflects its real
strength; what was missing was the disclosed SCOPE (whitelistToken,
createGauge with both public-path safety checks bypassed, and
self-reassigning `setGovernor`, none previously named here) and the
separate, genuinely different `emergencyCouncil` Safe (3-of-5, bounded
to killGauge/reviveGauge, disclosed but not scored).

## 4. Uniswap V3 Factory (Base) -- composite 85/100

Authority chain, more directly verifiable than the Robinhood/Arbitrum sibling
cases elsewhere in this project: `Factory.owner()` -> a real fee-adapter
contract (7,266 bytes, not a bare EOA) -> a second contract (1,419 bytes)
whose own getters all revert, but whose raw storage doesn't need guessing:
slot 0 = the canonical OP-stack `L2CrossDomainMessenger` predeploy
(`0x4200...0007`, confirmed live), slot 1 = `0x1a9C8182...BE35BC` --
Uniswap's real Ethereum-mainnet Governance Timelock.

Unlike the other 4 scorers in this file, this one deliberately opens its OWN
Ethereum-mainnet Web3 instance (ignoring the Base RPC for that one hop) to
independently re-confirm the L1 Timelock live, rather than trusting a prior
session's note: `delay()` = **172,800s (2 days)**, `admin()` =
`0x408ED635...724C3` (Uniswap's real GovernorBravo) -- both re-read live this
run, not assumed.

`adminKeyScore=80` (real, active L1 DAO reached via an explicit, readable
cross-domain authorization check, independently re-confirmed live),
`multisigScore=100` (not applicable, pure DAO+Timelock construction),
`timelockScore=75` (confirmed real 2-day delay live; capped below 100, no
emergency-bypass check done this pass, same caveat carried from the
Ethereum-L1 sibling scorer).

## 5. Compound V3 (Comet, USDC market) -- composite 80/100

Authority chain, fully closed and internally consistent, re-confirmed live:
`Comet.governor()` -> `LocalTimelock` (`0xCC3E7c85...`). The EIP-1967 admin
slot on the Comet proxy resolves to a separate `ProxyAdmin` contract
(`0xbdE8F31D...`), and that `ProxyAdmin.owner()` resolves BACK to the same
LocalTimelock -- confirming the same authority controls both parameter
changes and upgrades. `LocalTimelock.delay()` = **86,400s (1 day)**, the
actually-enforced LOCAL Base delay, re-confirmed live. `LocalTimelock.admin()`
-> `BaseBridgeReceiver` (`0x18281dfC...`, matches the official
`compound-finance/comet` `roots.json`'s `bridgeReceiver` field exactly).
`BaseBridgeReceiver.govTimelock()` -> Compound's well-known Ethereum-mainnet
Governance Timelock; `.localTimelock()` closes the loop back to the same
LocalTimelock. Genuine Compound mainnet-governance -> OP-stack cross-domain
message -> BaseBridgeReceiver -> LocalTimelock -> Comet, fully closed.

`adminKeyScore=75` (real, identifiable, fully-closed cross-domain governance
chain), `multisigScore=100` (not applicable, not a Safe), `timelockScore=65`
(confirmed real 1-day LOCAL delay live; the separate L1 Compound Timelock's
own delay was not queried by this Base-RPC-only scorer, same reasoning
disclosed for the Aave gap above).

## Reproduction

```
python3 chains/base-ecosystem/scripts/dry_run.py
```

Re-run at any time against either public RPC
(`https://mainnet.base.org` or `https://base-rpc.publicnode.com`) to
re-derive every score above from live chain state.
