# Arbitrum Ecosystem -- scored targets, 2026-09-17 (scoring_build phase, attempt 1)

> **CORRECTION 2026-09-19:** the GMX V2 RoleStore row below (composite 71)
> is superseded. It is now 22: a bare EOA holds TIMELOCK_ADMIN, and the
> controller this pass checked holds no role on the live RoleStore. See
> `rotation_audit_2026-09-19-index0-gmx-rolestore.md`.

> **CORRECTION 2026-09-20:** the Radiant Capital row below (55 / 100 / 55,
> composite 69) is superseded. The scorer now returns admin 65 / multisig 95
> / timelock 0 / oracle 100 / cross 100, composite 55: the pool admin is a
> 4-of-11 Safe that the 72 h timelock does not bind. See the "CORRECTED
> 2026-09-20" paragraph at the end of section 3. The text of section 3 is
> kept unchanged as the record of what was believed on 2026-09-17. The
> Sepolia oracle was re-pushed on 2026-09-20 (tx
> `0x308ad2c8fa527a0e5c30139b6b154ff48462cd046df9840a17f25775c21fbd23`,
> block 310697409) and now holds the corrected Radiant values, read back equal
> to the scorer output.

Phase: scoring_build. Scores the exact 5 targets approved 3/3 in the scouting
pass (maker-checker action 22), documented in full trace in
`data/scouted_targets_2026-09-16.md`. Every number below is re-derived live
by `chains/arbitrum-ecosystem/scorers.py` against `https://arb1.arbitrum.io/rpc`
(chain 42161, block ~506,054,985), re-run via
`chains/arbitrum-ecosystem/scripts/dry_run.py` -- not replayed from the
scouting pass's hand-run `cast` calls. Every compositeScore below was also
independently re-derived against a second, unrelated public RPC
(`https://arbitrum-one-rpc.publicnode.com`) in the same run and matched
exactly (`dry_run.py`'s built-in cross-check step). Re-running `dry_run.py`
re-derives every score from live chain state; if a target's real on-chain
configuration changes (a key rotated, a Safe reconfigured, a delay tuned),
the next run picks that up automatically.

Scoring grid and weighting reused exactly from `scripts/lib/scorers.py` /
`chains/ethereum-l1/scorers.py` / `chains/base-ecosystem/scorers.py`:
`compositeScore = floor(0.4*adminKeyScore + 0.3*multisigScore +
0.3*timelockScore + 0.5)`. `oracleAuthorityScore` is 100 for all 5 (not
applicable -- none of these targets is itself an oracle/price-feed
authority). `crossExposureScore` is also 100 for all 5, but for a different,
explicitly disclosed reason: no cross-ecosystem signer-overlap dataset has
been built yet between Arbitrum and the other tracked ecosystems (that
machinery, `scripts/lib/signer_overlap.py`, is scoped to Robinhood Chain's
own target set today) -- treated as "not applicable" per this project's
stated convention, not as a confirmed clean result.

> UPDATED 2026-09-20: that paragraph describes 2026-09-17 and is no longer
> the current state. Since 2026-09-17 the Aave V3 Arbitrum scorer compares
> its guardian Safe's owners against a dated snapshot of the Base sibling
> (crossExposure 80), and the 2026-09-20 project convention folds a
> cross-ecosystem overlap into `crossExposureScore` on every ecosystem
> (flat 80, `min()` with the within-ecosystem value, dated snapshots, no
> second-chain RPC inside a scorer; see the root `METHODOLOGY.md`, paragraph
> "Convention (decided 2026-09-20)"). Radiant's `crossExposureScore` stays
> 100: checked live 2026-09-20 against 70 root-signer groups on 7 ecosystems,
> no overlap found ("found none", not proof of none).

## Summary table

| Protocol | Address | TVL (Arbitrum) | adminKey | multisig | timelock | composite |
|---|---|---|---|---|---|---|
| GMX V2 (Synthetics) RoleStore | `0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72` | ~$194M | 65 | 90 | 60 | **71** |
| Camelot AMMv3 (Algebra) Factory | `0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B` | ~$6.2M | 50 | 35 | 0 | **31** |
| Radiant Capital LendingPool (V2 Core) | `0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886` | ~$184K / ~$97.7K borrowed | 55 | 100 | 55 | **69** |
| Arbitrum Security Council Emergency Safe | `0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641` | n/a (chain-level authority) | 55 | 100 | 40 | **64** |
| Aave V3 Pool (Arbitrum) | `0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb` | ~$489.2M / ~$339.6M borrowed | 65 | 100 | 50 | **71** |

TVL figures are the same DefiLlama reads already independently confirmed in
the scouting pass (`data/scouted_targets_2026-09-16.md`), current as of that
pass -- not re-pulled this run (this run is a live on-chain authority
re-scan, not a TVL refresh); treat as an order of magnitude, not an exact
live figure.

## 1. GMX V2 (Synthetics) RoleStore -- composite 71/100

Authority: a custom `AccessControl`-style role system (`RoleStore`), not a
plain `owner()`. `getRoleMembers(TIMELOCK_MULTISIG, 0, 10)` returns exactly 1
address -- a real Gnosis Safe, **5-of-8**, confirmed live. That Safe
independently holds `PROPOSER_ROLE` and `EXECUTOR_ROLE` (both confirmed
`true` live) on `ConfigTimelockController`, whose `getMinDelay()` is a real,
live-confirmed **1 day (86,400s)**.

The `TIMELOCK_MULTISIG` role identifier is not carried over from the
scouting pass as a fixed constant -- it is re-derived live in this scorer via
`keccak256(abi.encode("TIMELOCK_MULTISIG"))` (GMX's own `Role.sol` pattern),
independently cross-checked this run against `cast abi-encode`+`cast keccak`
run directly in the shell (see claims file): both methods produce the
identical byte-for-byte hash.

`adminKeyScore=65` (chain-closed, Safe threshold >= 3), `multisigScore=90`
(5 x 15 + 3 extra owners x 5), `timelockScore=60` (confirmed real 1-day
delay with both roles verified live on the same Safe).

## 2. Camelot AMMv3 (Algebra) Factory -- composite 31/100

Authority: `owner()` -> a real Gnosis Safe, **2-of-3**, confirmed live, with
no `TimelockController` layer found in front of it. All 3 owners
independently confirmed live this run to be bare EOAs (zero-length
bytecode), i.e. real individually-held keys, not smart-contract signers.

The weakest of the 5 targets in this batch on both dimensions that matter
most: only 3 total signers and no delay of any kind. Scored as-is rather
than smoothed over -- this is a genuinely thinner authority setup than the
other 4 targets, not a scoring artifact. `adminKeyScore=50` (2-of-N),
`multisigScore=35` (2 x 15 + 1 extra owner x 5), `timelockScore=0` (no delay
found anywhere in this chain).

## 3. Radiant Capital LendingPool (V2 Core) -- composite 69/100 as scored 2026-09-17 (scorer now 55/100, see the CORRECTED 2026-09-20 paragraph below)

Authority chain, re-confirmed live this pass: `PoolAddressesProvider
.getLendingPool()` returns the exact address expected from Radiant's own
docs (matches, confirmed live) -- this is the same correction already
established in scouting (a DefiLlama-Adapters address had pointed to a
stale, non-live contract). `PoolAddressesProvider.owner()` -> an
OpenZeppelin `TimelockController`, whose `getMinDelay()` is a real, live
**72 hours (259,200s)**, matching Radiant's own "Security Timelock" docs
page.

`adminKeyScore=55` (chain closed and confirmed, but capped below GMX's
combined Safe+timelock: no separate multisig layer is traced on this
timelock's own proposer/executor set this pass -- it is not
`AccessControlEnumerable`, an open item already flagged in scouting),
`multisigScore=100` (not applicable, `TimelockController` is not a Safe),
`timelockScore=55` (confirmed real 72h delay, capped for the same reason).

**Aggravating context, disclosed rather than folded into the score**: on
2024-10-16, Radiant Capital was exploited for ~$50M across Arbitrum and BSC
via compromise of multiple multisig-signer devices (blind signing),
corroborated by two independent sources already re-confirmed in scouting
(DefiLlama's public hacks dataset and Radiant's own remediation docs, exact
date match). A timelock delays a proposal from a compromised signer set --
it does not stop the signers themselves from being compromised. This is a
historical event, not a live-chain fact re-derived by this scorer, so it is
disclosed here rather than turned into an extra point deduction (this
project scores the CURRENT authority mechanism, consistent with every other
target in this file), but it directly bears on how much trust to place in
this target's admin-key dimension.

**CORRECTED 2026-09-20 -- composite 69 -> 55 (admin 55 -> 65, multisig 100 ->
95, timelock 55 -> 0).** The paragraphs above scored only the path through
`PoolAddressesProvider.owner()`, the 72 h TimelockController
`0x27fC8f3B...Aff92`. That is the root for the provider's own `onlyOwner`
functions, but not for the LendingPoolConfigurator's `onlyPoolAdmin`
functions (token-proxy upgrades, freeze, caps, rate strategy, reserve init).
Those are gated by `PoolAddressesProvider.getPoolAdmin()`, which is
`0x111CEEee040739fD91D29C34C33E6B3E112F2177`, a 4-of-11 Safe with no delay in
front of it. The same Safe holds PROPOSER and CANCELLER on the timelock and 6
of its 11 owners hold EXECUTOR, so the timelock delays that committee on the
provider-level path but does not bind the fund-affecting token-upgrade path.
It is now scored as a Safe with no timelock: admin 65 (threshold >= 3),
multisig min(100, 4 x 15 + 7 x 5) = 95, timelock 0, composite
`floor(0.4 x 65 + 0.3 x 95 + 0.5)` = 55. The emergency admin
(`0xDdF60973...0928`, a 1-of-5 Safe, all 5 owners also owners of the
4-of-11) can only pause: disclosed, not scored. `crossExposureScore` stays
100. The 72 h delay above remains accurate for the provider-level path, and
the 2024-10-16 incident context above still applies as disclosure.
The scorer output was re-run read-only against Arbitrum One on 2026-09-20;
the Sepolia oracle was updated by the 2026-09-20 re-push (tx `0x308ad2c8...fbd23`,
block 310697409) and reads 65 / 95 / 0 / 100 / 100 / 55 for Radiant.

## 4. Arbitrum Security Council Emergency Safe -- composite 64/100

Not a protocol with its own TVL: this Safe is the emergency-upgrade
authority for Arbitrum One's own core protocol contracts, relevant to every
protocol on the chain, confirmed live this run to be a real Gnosis Safe,
**9-of-12**. It independently holds `EXECUTOR_ROLE` (confirmed `true` live)
on the L2 `UpgradeExecutor`, which can bypass the ordinary L2 core
`TimelockController`'s real, live-confirmed **8-day (691,200s)** delay for
emergency action -- a standard, publicly-documented part of Arbitrum's own
security model, not a discovered flaw.

`adminKeyScore=55` and `timelockScore=40` are both capped below what the raw
9-of-12 threshold and 8-day nominal delay alone would suggest: this Safe IS
the chain's own emergency root, and its entire purpose is to bypass the
ordinary delay when invoked, so the delay is not the actual binding
constraint the way it is for GMX or Aave. A compromise here is also
maximally systemic (every protocol on the chain, not one), reflected as a
cap rather than a bonus. `multisigScore=100` (9 x 15 capped at 100).

## 5. Aave V3 Pool (Arbitrum, PoolAddressesProvider) -- composite 71/100

Authority chain, fully re-confirmed live this pass, same shape as the Base
sibling scorer: `PoolAddressesProvider.owner()` == `.getACLAdmin()` ->
`EXECUTOR_LVL_1` <-> `PayloadsController` (mutual `owner()` pointers, a
genuine closed pair confirmed live, standard BGD Labs Aave Governance V3
cross-chain infra, not a loop hiding the real authority).
`PayloadsController.getExecutorSettingsByAccessControl(1)` returns
`(EXECUTOR_LVL_1, 86400)` -- a real, live-confirmed **1-day** delay at this
access-control level. `ACLManager.hasRole(DEFAULT_ADMIN_ROLE,
EXECUTOR_LVL_1)` confirmed `true` live. `PayloadsController.guardian()`
resolves to a real Gnosis Safe (`GOVERNANCE_GUARDIAN`, confirmed live
**5-of-9**) that can cancel proposals outside the timelock.

`adminKeyScore=65` (closed executor/payloads-controller pair, real infra,
capped below a "confirmed active DAO" score for the gap below),
`multisigScore=100` (not applicable, no Safe layer on the primary authority
path), `timelockScore=50` (confirmed real 1-day delay, capped for the open
gap below plus the guardian's cancel-path outside the timelock).

**Open thread, disclosed rather than guessed**: this scorer confirms the
Arbitrum-side executor/payloads-controller pair matches the official
`bgd-labs/aave-address-book` exactly, but does NOT independently re-verify
the Ethereum-mainnet Aave DAO root (the `CROSS_CHAIN_CONTROLLER` relay, L1
proposal counts/quorum) -- that root lives on L1 and is covered separately by
`chains/ethereum-l1/scorers.py`'s `score_aave_v3_pool()`. This is the same
open item already flagged in the Arbitrum scouting pass for both this target
and its own Uniswap V3 copy, and for Uniswap's L1-aliased governance
elsewhere in this project (Base, Robinhood Chain) -- worth one shared
"external L1 DAO governance via bridge" sub-model rather than scoring each
case ad hoc; not built this pass. There is already an open transverse "A
faire" card on the tracker board for exactly this.

## Reproduction

```
python3 chains/arbitrum-ecosystem/scripts/dry_run.py
```

Re-run at any time against either public RPC
(`https://arb1.arbitrum.io/rpc` or `https://arbitrum-one-rpc.publicnode.com`)
to re-derive every score above from live chain state. The script itself also
runs both RPCs in the same invocation and diffs every compositeScore.
