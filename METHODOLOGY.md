# Methodology

What every score means, what it reads on-chain to get there, and what it
cannot see. Written so a DAO delegate, a hackathon judge, or a protocol team
being scored can check any number below against the live chain themselves,
not take it on trust.

This document covers the **core model** - the one live on Robinhood Chain
today and used (in slightly adapted form) by the EVM `scoring_build`-phase
ecosystems (Ethereum L1, Base, Arbitrum). **Updated 2026-09-17**: every
non-EVM ecosystem (Hyperliquid, Solana, Tempo, Zcash) also reached
`scoring_build` this same day - none is left in a pure `methodology`-only
phase. Each has its own `chains/<ecosystem>/METHODOLOGY.md` adapting these
same five dimensions to a non-EVM or non-Safe authority model, plus its own
`scorers.py` and `data/scored_targets_2026-09-17.md` with the live-verified
numbers - see those files for the chain-specific translation and the exact
targets covered so far (2-3 flagship targets per ecosystem, not full
coverage). This document doesn't duplicate them.

## The five dimensions

Every scored target gets five sub-scores, each 0-100, **higher is safer**. A
dimension that genuinely does not apply to a target (no oracle role, no
cross-protocol signer data available yet) scores 100 - full marks, not
penalized as if it were a real weakness. This is a project-wide convention,
not a per-target choice.

| Dimension | Question it answers |
|---|---|
| `adminKeyScore` | Who can act as this contract's ultimate authority, and how hard is that authority to compromise or coerce? |
| `multisigScore` | If that authority is a multisig (Gnosis Safe or a bespoke equivalent), how strong is it - threshold, signer count? |
| `timelockScore` | Is there a real, enforced delay between an authority action being queued and taking effect? |
| `oracleAuthorityScore` | Who can change the prices this target reports (a provider) or relies on (a lending market that reads feeds)? (100 = not applicable, or not yet computed for a price consumer outside the rule's current scope; see "oracleAuthorityScore for price consumers") |
| `crossExposureScore` | Does this target's root authority also control another *tracked* target? A shared compromised key becomes a systemic risk, not an isolated one. (100 = no overlap found, or not computed for that target; for Solana, Hyperliquid and Zcash that means within the ecosystem only, not yet checked across ecosystems; see Convention below and Limitations) |

### Aggregation

```
compositeScore = floor(0.4 * adminKeyScore + 0.3 * multisigScore + 0.3 * timelockScore + 0.5)
```

(`scripts/lib/scorers.py::_composite()`, mirrored per-ecosystem.) Standard
round-half-up, deliberately not Python's built-in `round()` (banker's
rounding produced a value one point off an already-published score once -
see that function's own docstring).

`oracleAuthorityScore` and `crossExposureScore` are published on-chain and
on the dashboard but are **not** folded into `compositeScore`. Each is a
distinct fact a consuming contract might weight differently - a lending
protocol gating collateral factors by `getScore()` may care far more about
`crossExposureScore` on a target whose Safe also secures three other
protocols it's exposed to than about that target's own `compositeScore`
in isolation. Collapsing five numbers into one would throw that choice away.

## What each dimension actually reads

**`adminKeyScore`** - trace the target's authority getter(s) (`owner()`,
`admin()`, `hasRole(DEFAULT_ADMIN_ROLE, ...)`, an EIP-1967 admin slot, or a
bespoke pattern like a `PoolAddressesProvider`/`ACLManager` role system) to
its root: a bare EOA (near-worst case), a Gnosis Safe or bespoke multisig
(scored better, see `multisigScore`), or a real, live, active DAO (Governor
Bravo + Timelock, or equivalent) reached directly or via a legitimate
cross-domain bridge mechanism (an L1→L2 address alias, an OP-stack
`L2CrossDomainMessenger` predeploy check) - see
`data/correction_2026-09-16-uniswap-bridge-alias.md` for a case where this
distinction mattered: a bridge alias reads identically to a bare EOA under a
mechanical `is_eoa()` check (no bytecode), and treating the two the same
is a real scoring bug, not just an imprecision. A resolved external-DAO
root scores in the 75-85 range depending on how directly its quorum/delay
were independently re-confirmed live; a bare EOA scores 2-10; an unresolved
contract (a real contract exists, but its own controller wasn't traced this
pass) scores 20 as an explicit "unknown, not assumed safe" placeholder, never
silently treated as either extreme.

**`multisigScore`** - for a Safe-rooted target, reads `getOwners()` and
`getThreshold()` live (or the bespoke `getSigners()`/`threshold()` pattern
found on non-Safe multisigs). The general shape used across most targets:
`min(100, threshold * 15 + max(0, ownerCount - threshold) * 5)` - a higher
threshold matters more than a larger owner count at a fixed threshold, since
more owners at the same threshold means more key combinations can reach it.
**Not every target uses this exact formula** - several scorer functions use
a tuned variant reflecting that specific target's context (see Limitations).

**Safe authority gate (added 2026-09-21).** A Safe's owners and threshold only say who can
act if nothing else can. A module executes as the Safe without the owners' signatures, and a
Safe on unknown logic is not the Safe the threshold describes. So the shared resolver every
scorer uses (`safe_owners_and_threshold`) now also reads the Safe's modules and singleton, and
returns "unresolved" (the same result as "not a Safe", which every scorer already scores at
the conservative unresolved-authority floor) when **a module is enabled that has not been
analyzed**, or **the singleton is neither a published Safe build nor analyzed**. Analyzed
means read, understood and recorded with its evidence in `scripts/lib/safe_modules.py`
(`KNOWN_ANALYSES`, `KNOWN_SINGLETON_ANALYSES`); five modules or guards and one odd singleton
are recorded today. Three deliberate limits: a module list that could not be *read* leaves the
score as computed and adds a note, so a flaky RPC cannot collapse a score; a guard or a
fallback handler never degrades, since they can block or answer calls but not act as the Safe;
and an *analyzed* module that can act as the Safe by design (Arbitrum's `UpgradeExecutor` on the
Security Council Safe) is accepted, its power disclosed in the notes rather than scored. The
gate adds a note to every affected result saying which Safe and why. Owner-only tools
(the cross-ecosystem sweep, the modules sweep) pass `check_modules=False` so a gated Safe's
signers stay visible. Record: `data/finding_2026-09-21-safe-modules-and-guards.md`.
Score is 0 if no Safe/multisig layer exists (the root is a bare EOA or a
plain contract), 100 if not applicable (the root is a real, active DAO with
no Safe layer - a token-vote quorum is a different strength model than a
Safe threshold, deliberately not conflated with one here).

**`timelockScore`** - looks for a real `TimelockController`/`Timelock`-shaped
contract (or a bespoke per-function delay mapping) gating the specific
authority-changing action(s) this target's root can take, and reads its
configured `delay()` live. 0 if no delay mechanism is found, or if one
exists but doesn't cover the action that actually matters (e.g. `setOwner`
excluded from an otherwise-real 7-day delay on other functions - scored on
the gap, not the presence of *a* timelock somewhere in the contract). A
confirmed real delay scores 60-75 depending on length and whether an
emergency-bypass path was checked for and ruled out; capped below 100
whenever that bypass check wasn't done this pass, rather than assumed clean. A
confirmed bypass that is bounded (it can change configuration or pause, not
upgrade or withdraw) caps the score at 55. Fluid Liquidity on Arbitrum is scored
this way (four config-handler auths that point at the team multisig, plus a guardian
that is that multisig, act without the 24h delay). Fluid on Plasma has the same shape,
enumerated on chain, and takes the same cap; that its handler contracts' powers are
bounded is inherited from the Arbitrum analysis, not re-derived for them.

**`oracleAuthorityScore`**: who can change the prices a target reports or
relies on. Each derivation in use: the Robinhood Chainlink admin Safe scores its
own composite (since 2026-10-04); Lido stETH scores its HashConsensus quorum;
Solana's Drift and Kamino Lend score the minimum over their oracles' composites;
Hyperliquid's targets follow `chains/hyperliquid/METHODOLOGY.md` section 4.4 (the
HIP-3 dexes' oracle key, the L1 validator set, Kinetiq's operator push); ten EVM lending markets score
the price paths upstream of them (see "oracleAuthorityScore for price consumers"
below). Every other target publishes 100: not applicable for a target that
neither reports nor reads a price, and not yet computed for a price consumer
outside that rule's current scope (listed there). Not applicable includes a target that reads prices
only through oracles nobody holding a key on it can change: each Morpho Blue market's oracle is fixed by
its creator when the market is created, and its bad debt stays in that market, so the singletons publish
100 and the exposure is scored at the vaults that choose the markets.

**`crossExposureScore`** - computed once per `score_all()` run, after every
individual target is scored (`scripts/lib/signer_overlap.py`): re-derives
every tracked group's root signer set live, and checks whether any signer
also appears in another tracked group's signer set. `crossExposureScore =
max(0, 100 - 20 * sharedGroupCount)`. This reuses the same discipline as
this project's sister research program, `multisig-overlap` (337 protocols,
547 confirmed Safes tracked for exactly this pattern at a larger scale),
scoped down to this oracle's own tracked target set. A separate module,
[`scripts/lib/cross_ecosystem_overlap.py`](scripts/lib/cross_ecosystem_overlap.py),
extends the same check ACROSS ecosystems (does a Robinhood Chain Safe's owner
also sit on an Ethereum L1 or Base Safe this project tracks?) and runs
standalone (`scripts/check_cross_ecosystem_overlap.py`).

**Convention (decided 2026-09-20): a cross-ecosystem overlap IS folded into
`crossExposureScore`, everywhere.** The field's documented meaning is "100 = no
root signer shared with any other tracked target", and "any other tracked
target" is not limited to the same chain. So when a target's root committee is
identical to the committee of a tracked target on ANOTHER ecosystem, its score
is a flat 80, on every EVM ecosystem, and 100 when nothing overlaps. "Identical"
is read strictly and is not loosened to "shares a signer": almost every scorer
requires the owner set it just read to equal the snapshot's owner set exactly, as
a set (the Safe address and threshold may differ). Three shapes differ, each
stated here rather than hidden: Monad's Steakhouse Morpho vault accepts
containment (its curator or owner Safe is a subset of the Robinhood Chain
Steakhouse committee); Monad's Curve factory needs the same factory address AND
the same admin EOA; and Robinhood Chain has no cross-ecosystem comparison in code at all, only a
hand-set, dated `cross_ecosystem` flag on the group in
`scripts/lib/signer_overlap.py`, to be removed by hand if that committee rotates.
Two rules keep this honest: (1) on the ecosystems changed 2026-09-20
(Ethereum L1, Robinhood Chain, Tempo) the fold is `min(within-ecosystem score,
80)`, so a target already lowered by an in-ecosystem overlap is never raised back
up (on Plasma the three targets folded that day, Pendle and the two Euler
targets, are set to a flat 80 with no `min`, since none of them has a
within-Plasma overlap that could be lower; Fluid Liquidity on Plasma joined them
later that day, once its proposer signer set was resolved and found identical to the
Arbitrum one); (2) a scorer does not call a second chain's RPC. It compares the owner set it
just read on its own chain against a hardcoded, dated snapshot of the other
chain's committee (same idiom as the Aave guardian scorers), with the date in the
snapshot constant's name and, in most scorers, in the note, so a rotation on the
other chain is caught by `scripts/check_cross_ecosystem_overlap.py` and by the
next drift audit rather than silently trusted. One deviation from a flat
80 was closed on 2026-09-21: the older Arbitrum scorers deducted 20 per matching
snapshot, so Arbitrum's Pendle (the same Safe is tracked on Plasma and on Robinhood
Chain) read 60 while the same committee read 80 on the other two. It is now 80 too.
Base still deducts 20 more for each overlap inside Base. Before this decision Ethereum
L1, Robinhood Chain and Tempo did not fold cross-ecosystem overlaps while
Arbitrum, Base, Plasma (for Aave and Ethena only) and Monad did, so the same committee scored 80 on four
chains and 100 on the others. The values this moved, the rationale and how each
was verified are in
[`data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`](data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md).
These values were pushed on-chain on 2026-09-20 (six transactions, all status 1,
read back with `getScore()` on all 7 oracles with 0 differences; the transaction
table is section 9 of that finding). Before the push they were scorer output and
the deployed testnet oracles held the previous values.

**Extension (2026-09-20, same day): a shared contract root counts like a shared committee.** Uniswap's Ethereum L1
Governance Timelock is the root of 11 tracked targets on 5 ecosystems (L1 2, Arbitrum 1, Base 3, Robinhood Chain 4, Monad 1),
reached through a bridge alias, an OP-stack forwarder or a Wormhole relay. These were left at `crossExposureScore` 100 (nine
of them) by an older rule that DAO or Timelock rooted targets, having no Safe signer set, were "not counted"; that rule was a
limit of the sweep, which could only compare Safe owners, not a decision. The Timelock is one root identity confirmed live by
each scorer, so the same flat 80 applies (`min(within-ecosystem, 80)`, composite unchanged). Each scorer folds only on a root it
confirmed that run, and the Robinhood Chain group carries a hand-set dated flag like Pendle, Morpho Blue and Curve. Details and
the live drift check:
[`data/finding_2026-09-20-uniswap-one-timelock-eleven-targets.md`](data/finding_2026-09-20-uniswap-one-timelock-eleven-targets.md).
Scorer output only until the next re-push of Arbitrum, Base, Monad and Robinhood Chain.

**`l1CappedComposite`** (added 2026-09-17, off-chain only) - no protocol
built on Robinhood Chain can be meaningfully safer than the L1 authority
that can upgrade or reconfigure the rollup itself
(`score_rollup_l1_authority()`, currently 57/100: a real 7-of-8 Security
Council Safe plus a 7-day Timelock whose proposer and canceller roles sit on
the same address, itself a Safe whose own signers overlap 75% with the
Security Council -- revised 2026-09-17 from 60 once that cross-Safe overlap
was live-verified and wired in). `l1CappedComposite = min(target's own compositeScore,
Robinhood Chain's own L1 rollup authority compositeScore)`, computed once
per `score_all()` run and attached to every entry. Deliberately published as
a SEPARATE field, never overwriting `compositeScore` -- same reasoning as
`crossExposureScore` above: `compositeScore` keeps meaning exactly what it
has always meant (this target's own authority setup, in isolation), and a
consumer who cares about the chain-level ceiling reads the new field instead
of losing the original number. **Off-chain only**: the deployed oracle
contract's `AuthorityScore` struct has no field for this yet (adding one is
a contract migration, a bigger, separate decision) -- published in
[`api/scores.json`](api/scores.json), not pushed on-chain, and deliberately
not read by `dashboard/index.html` either, so the dashboard's own stated
design ("reads every score directly from the deployed oracle... nothing to
trust but the RPC and the contract itself") stays true without a silent
exception.

**Two dimensions considered and checked, deliberately not scored (2026-09-17)**:

- *Cross-chain messaging delegate risk* (the surface The Sandbox's SAND bridge
  exploit used -- a LayerZero OApp's `delegate` can reconfigure its entire
  security stack independent of its owner). Checked live against every address
  this project tracks anywhere
  ([`scripts/lib/layerzero_delegate_risk.py`](scripts/lib/layerzero_delegate_risk.py)):
  zero are registered LayerZero OApps with a delegate set today. Not added as a
  `score_all()` field -- a dimension with nothing to say for any current target
  is clutter, not a real sub-score. The check itself is real and reusable.
- *Governance-capture risk* (the surface Term Finance's Meta Vault exploit used --
  a real timelock didn't help because the VOTE was capturable). Real facts
  gathered live against Uniswap's GovernorBravo (quorum, proposalThreshold, and
  the last 5 real proposals' actual turnout) and published as disclosed notes on
  that scorer, not as a 0-100 score: turning "quorum is 4% of supply, recent
  turnout clears it with margin" into a defensible capture-risk NUMBER needs
  real delegate-concentration data (who could coordinate to self-vote alone),
  which needs a full event-log replay back to genesis -- the same
  infeasible-on-free-RPCs problem this project has hit before at this scale. A
  confident-looking score invented without that data would be exactly the
  fabricated-but-plausible-looking number this project's own discipline exists
  to catch -- see the Limitations section above.

## oracleAuthorityScore for price consumers

DECIDED by Spap on 2026-10-04, after `data/finding_2026-10-01-aave-capo-price-authority.md` and its
2026-10-04 addendum showed that a lending market's riskiest lever often sits outside its own governance:
whoever can swap a Chainlink aggregator, re-point a rate provider or lift a price limit moves every
borrower's health factor at once. Until that date the score was 100 for every EVM lending market and the
paths were only described in a finding. Code: [`scripts/lib/price_authority.py`](scripts/lib/price_authority.py),
called by the Aave V3 (Ethereum Core and Horizon, Base, Arbitrum, Plasma, Monad), SparkLend (Ethereum, an Aave V3
fork), Aave V2 (Radiant on Arbitrum), GMX (V2 Synthetics and the V1 Vault, Arbitrum), Compound V3 (Ethereum, Base,
Arbitrum), Moonwell (Base, a Compound V2 fork), Morpho V1 (Adpend, 1337, Steakhouse USDT and USDC on Ethereum, four
vaults on Base, one on Monad), Morpho Vault V2 (Steakhouse Prime USDC and EURCV on Ethereum, six vaults on Robinhood
Chain), Euler V2 (the eVaultFactory on Plasma and on Monad, the TelosC Surge EulerEarn vault on Plasma), Fluid Liquidity
(Arbitrum, Plasma) and Dolomite (Arbitrum) scorers. Kamino Liquidity and Jupiter Lend on Solana follow the same rule in
`chains/solana/scorers.py`, with the Solana formula.

```
oracleAuthorityScore = min, over the MATERIAL price paths ONE HOP upstream, of each path's own composite
```

- **Material**: a path that reaches at least 1% of the target's priced supply (Aave: every reserve's
  aToken supply at the oracle price; Compound: the base supply plus every collateral total at
  `getPrice`; Aave V2 (Radiant): every reserve's aToken supply at the oracle price, plus one row for the
  AaveOracle's fallback oracle when one is set (it prices any reserve whose source answers zero or less);
  GMX V2: per token, its pool amounts and the open interest it indexes, read from the DataStore, with
  the provider the Oracle accepts for it, plus, while atomic withdrawals are on, one row per token of each
  market for the Chainlink feed an atomic action reads (these rows overlap the provider rows, so the
  priced supply is the provider rows' sum); GMX V1: every whitelisted token's pool at the Vault's price,
  plus one row for its VaultPriceFeed over the whole pool; Morpho V1: the vault's current allocation per market, on the singleton its `MORPHO()`
  names; Euler V2 eVaultFactory: one row per vault that lends against at least one collateral with a
  borrow or liquidation LTV (one still ramping down counts), its `totalAssets()` in USD (a vault in another unit of account is valued by
  the first USD-priced vault oracle that quotes its asset, and is unknown when none does), the row reaching
  its oracle and, through a pinned EulerRouter build, the adapter the router resolves for its asset and
  for each such collateral and every ERC4626 vault it converts through on the way (a collateral the router
  rejects with `PriceOracle_NotSupported` secures nothing and is noted; any other revert, a stale rate for
  instance, or a conversion chain that cannot be read, is an UNREAD part of the row, its other parts still
  walked); EulerEarn: the same per strategy, weighted by the Earn
  vault's allocation; Kamino Liquidity: every Scope feed its CollateralInfos name, each counted as material; Morpho Vault V2: per adapter, a market adapter's own positions, a V1-vault adapter's share of that
  vault's markets, and one row with no source for any other adapter holding assets, each market
  adapter's rows (its idle markets included) checked against its `realAssets()` (a gap above 1% is a row
  with no source); idle assets are unpriced and left out). A row whose value cannot be read counts as
  material (fail-closed). A Vault V2 adapter with no priced allocation today (idle-market supply aside)
  but live absolute and relative caps gets a note: allocators can fill it without a timelock, subject to
  its market caps, so the field follows today's allocation.
- **One hop**: the walk goes through the target's own price contracts (an Aave adapter whose
  `ACL_MANAGER()` is the market's own ACLManager; a wrapper whose `manager()` is the target's governor,
  or, since 2026-10-05, whose `owner()` is, or whose `DOLOMITE_MARGIN()` is the target, provided no beacon
  and no proxy admin outside the target's own governance can swap its code; the target's own governance means
  accounts whose power over the wrapper is no greater than what the composite already scores, so a Morpho V1 or
  Vault V2 vault and an EulerEarn pass none of their roles: their owner and curator act at once on a contract they
  control, while the vault's composite credits its timelocks)
  and through provably immutable wrappers (no proxy slot, no storage write, no `DELEGATECALL`); an
  EulerRouter is the target's own when its `governor()` is the target's own governance, else its governor
  is scored (it re-points any price at once), and a zero governor freezes it. It stops
  at the first contract someone else controls: a Chainlink proxy, a rate provider, an upgradeable feed.
  That contract is scored by who can change what it reports. A wrapper that is neither the target's own
  nor provably immutable, and has no readable `owner()`, proxy admin slot or `manager()`, is UNREAD; so
  is an adapter that answers to another ACLManager, and an own adapter whose input the walk cannot see,
  unless a spec names it as own configuration (Aave Monad's fixed mUSD adapter, set by the market's own
  POOL_ADMIN holders). The walk follows the getters it knows; an input read through any other getter is
  not seen. Two narrow extensions, each pinned: an EIP-1167 clone of a listed implementation (code hash
  pinned, no proxy slot) is walked through the getters listed for it (Steakhouse's
  MetaOracleDeviationTimelock: `primaryOracle`, `backupOracle`); and a build recognized by its masked
  template (its code with every 32-byte operand zeroed) may declare one more input getter (the Robinhood
  Chain stock-token oracle's `token()`), only while its 32-byte operands match a pinned layout site by
  site (each the exact value a named getter returns, or a pinned constant), so no held address can be
  moved to another use. The inputs of a scored contract (the Stader manager behind rsETH, the L1
  cbETH owner behind a Base exchange-rate feed) are disclosed in a finding, not scored. Going deeper would score each protocol by the weakest link of every token it
  lists, which no reader could check by hand.
- **A Chainlink proxy** scores the owner of the proxy (`proposeAggregator` and `confirmAggregator` are
  `onlyOwner` with no delay) and, when different, the owner of the current aggregator (`setConfig`). An
  aggregator whose `owner()` cannot be read is UNREAD unless its code is a provable constant, and a
  contract answering `aggregator()` that also has a proxy admin slot scores that admin too.
- **The controller** of a path: a bare EOA or an EIP-7702 EOA scores (5, 0, 0) = 2, and so does a price
  source that is itself such an account; a Safe with no timelock above it scores
  `_safe_rooted_scores(threshold, n)` (a 4-of-9 Safe gives 52), and a Safe the module gate cannot clear
  is UNREAD; a contract with `owner()` or `admin()` is followed for two hops; anything else is UNREAD. A
  controlled contract is scored through its `owner()`, its proxy admin slot (EIP-1967 or the older
  Zeppelin slot), its `manager()` and, for a beacon proxy, its beacon's owner.
- **Behind a shorter timelock** (decided 2026-10-05): a timelock shorter than the target's own delay is
  no longer UNREAD by itself. The accounts that can schedule on it are scored, each behind that delay,
  with timelockScore `delay_points(seconds)` (the notice-period curve of section 6.1, 50 x hours / 24
  below a day then +10 a day, capped at 60, the EVM level of a real delay whose bypass paths were not
  ruled out), and the weakest one counts. For an OpenZeppelin TimelockController these are the
  PROPOSER_ROLE holders and the holders of its admin role other than itself; the roles are not
  enumerable, so each set is replayed from block 0, pinned with its proof block in `TIMELOCK_HOLDERS`,
  and re-checked every run (its runtime code hash, `hasRole`, and no grant or revoke of those roles
  since; a change is UNREAD until re-pinned). Only a timelock whose code is verified as a plain
  TimelockController, or byte-identical to one that is, is pinned: an unverified build could let
  another role schedule. A Compound Timelock (it answers `GRACE_PERIOD`, `MINIMUM_DELAY`, `MAXIMUM_DELAY`) is
  scheduled by its `admin()`, and by its `pendingAdmin()` when one is set. Delays add up through nested
  timelocks, and an account behind enough delay is governance-grade. Pinned on 2026-10-05: EtherFi's
  OPERATION (2 days, a 4-of-7 Safe) and UPGRADE (10 days, a 6-of-10 Safe) timelocks and one 7-day
  Chronicle timelocks on Monad (one byte-identical to Chronicle's verified CouncilTimelock on Ethereum, the
  other matching the verified ChronicleTimelockController on Ethereum Sepolia apart from its metadata); four Euler
  timelocks on Monad and two on Plasma are unverified, so not pinned.
- **A DAO's delay** is the whole window its code imposes from the first public on-chain step to execution
  (decided 2026-10-05). Lido: the Aragon vote's `voteTime()` (the pinned Voting implementation cannot
  execute before the vote is closed) plus Dual Governance's afterSubmit and afterSchedule delays, with
  Voting the only Dual Governance proposer: 5 + 3 + 1 = 9 days on 2026-10-05. While Dual Governance's emergency
  protection is on (until 2027-06-19 on 2026-10-05), the emergency committees can execute a scheduled proposal
  without the afterSchedule wait, so the window counted is 5 + 3 = 8 days, still governance-grade for the 7-day
  Morpho vaults. A DAO with no minimum vote duration counts its timelock only: Sky's 2-day pause is
  below a 7-day bar, so Sky governance is scored with the convention of `score_makerdao_sky_pause`
  (adminKeyScore 75 while the DSChief hat reads, multisigScore 100, timelockScore 70): 81. sUSDS, a Morpho
  vault input, is read by a spec: its rate can only rise (`ssr >= RAY`) and SP-BEAM's buds move it inside
  a code-bounded range (bounded); its upgrade and SP-BEAM's configuration belong to Sky governance (wards
  of both replayed from block 0 and re-checked every run; SPBEAMMom can only halt).
- **Several feeds behind one price** (decided 2026-10-05): a median, or any other combination, scores its
  weakest feed, each one walked. Chronicle's OracleAggregator drops a feed older than 25 hours and then
  averages the other two, so one controller can move the price alone. **A lever bounded by code** (a band
  around another feed that only the target's own governance can widen) is disclosed as bounded; **a
  downward-only lever** (one that can mark a price down at once and force liquidations) is scored.
- **A Morpho Vault V2 read for its share price** (a BASE_VAULT of the pinned build): its curator, and its owner
  (who installs a curator at once: `setCurator` has no timelock), behind the vault's minimum live timelock over
  fund-redirecting functions and exit gates, governance-grade at or above the target's delay; its own markets' oracles are one hop further, disclosed. Allocators
  and fees are not behind that delay: `setIsAllocator` and the fee setters carry a 0-second timelock on the live vaults,
  and an allocator can call `setMaxRate` at once. Those levers are bounded by code constants (the fee and the maximum
  rate are capped, the share price can stop rising but not fall at once) and are disclosed, not scored; if the owner
  rules a frozen share price a lever to score, the two Steakhouse Prime V2 vaults would follow their curator Safe
  instead (about 31).
- **Disclosed, not scored**, when the path is (a) provably bounded, by a spec that re-reads its facts
  live every run (osETH: non-upgradeable code pinned by hash, rate can only rise); (b) governance-grade,
  behind a timelock at least as long as the target's own governance delay (Aave: the PayloadsController
  delay for the ACL admin executor; Compound: `governor().delay()`; Morpho V1: `vault.timelock()`; Morpho
  Vault V2: the minimum live timelock over its fund-redirecting functions and exit gates, none when all are
  abdicated; Aave V2: its AaveOracle owner's `getMinDelay()`, 0 when that owner is not a timelock, and an
  owner the market's composite does not score, or an owner that cannot be read, is a row with no source; GMX V2: the live
  ConfigTimelockController's `getMinDelay()`; GMX V1: the Vault governor's `buffer()`; Euler V2
  eVaultFactory: the `getMinDelay()` of the sole DEFAULT_ADMIN timelock of its `upgradeAdmin()`; EulerEarn:
  its `timelock()`; Kamino Liquidity: its GlobalConfig admin's Squads `time_lock`), such
  as the EtherFi UPGRADE timelock and the Lido stETH rate path; a target with no delay of its own, such
  as a Morpho V1 vault whose `timelock()` is 0, has no governance-grade bar, so its timelocked paths are
  scored through who can schedule on them. Since 2026-10-05 a timelock's delay counts only when its runtime code is
  a verified build (`VERIFIED_TIMELOCKS`: plain OpenZeppelin TimelockControllers and Chronicle's, each matched to
  verified source, or a `TIMELOCK_HOLDERS` pin): another contract answering `getMinDelay()` or `delay()` may let some
  role act at once (GMX's ConfigTimelockController adds functions, Dolomite's owner has a bypass role), so it is
  UNREAD; or (c)
  a provable constant
  (no storage write, no call of any kind, no read of balances, of other accounts' code or of transient
  storage, no gas or block-builder value, no proxy slot; the compiler's metadata trailer, and constant data
  such as a revert string that solc places between the last INVALID and that trailer, are not read as code:
  the scan stops at the first INVALID past which no valid JUMPDEST is a jump target pushed before it, the
  EVM's own JUMPDEST analysis reproduced). A provably immutable wrapper is held to the same
  test, except that it may call the contracts it reads and read `EXTCODESIZE`, `ORIGIN`, `CALLER` and
  `GAS` (Solidity before 0.8.10 checks `EXTCODESIZE` before every external call); or (d) an input-less
  MorphoChainlinkOracleV2: its template pinned, its six feed and vault getters reading zero, `price()`
  equal to `SCALE_FACTOR()`, and its 32-byte operands matching a pinned layout site by site (zero at
  every feed and vault site, `SCALE_FACTOR` only where the build multiplies by it), so its price is that
  immutable (it is not a provable constant: it makes calls).
- **The target's own config path** (its own `ACL_MANAGER`, its own governor) is already in
  `compositeScore` and is not scored again.
- **Unknown is not safe**: a material path that cannot be read (a rate provider without a verified
  spec, a timelock shorter than the target's delay whose schedulers are not pinned or changed since their
  pin, a failed RPC read)
  caps the score at 20 (the minimum of 20 and the scored paths), never 100. No material path: 100.

Every classification is re-read live each run; a spec names what to check and which answer keeps the
classification, and any other answer is UNREAD. One fact cannot be re-read directly: the rsETH
LRTConfig is not enumerable, so its admin set was replayed from the logs on 2026-10-04, and each run
re-reads that holder with `hasRole` and checks that no admin grant or revoke happened since. The push
guard (`scripts/lib/push_guard.py`) holds, before a real send, an entry whose published
`oracleAuthorityScore` drops by more than 15 points, moves while a material path is UNREAD or after a
failed walk, or rises to 100 from a lower value (a path that stopped counting), so the first push under
this rule (several markets from 100 to 52) is accepted by a person, once.

**Families added on 2026-10-05**, each from the read-only study of that day and the decisions above:

- **SparkLend** (Ethereum): the Aave V3 rows. Its delay is MCD_PAUSE's (172800 s), used only while every link above
  it reads as verified: provider owner and ACL admin = SparkProxy (a SubProxy, sole DEFAULT_ADMIN and POOL_ADMIN of the
  ACLManager, ASSET_LISTING_ADMIN never granted), SparkProxy's wards MCD_PAUSE_PROXY, the ESM and StarGuard (whose
  only ward is MCD_PAUSE_PROXY), code hashes pinned, role and ward sets replayed from block 0 and re-checked for
  changes. Chronicle's OracleAggregator (Aggor: a median of Chronicle, Chainlink and RedStone, immutable) is walked
  feed by feed and the weakest binds. A **Chronicle Scribe** is scored through its wards, enumerable with `authed()`
  and required to equal the verified set exactly, code pinned: a Kisser or kiss operator can only add readers
  (bounded); a governance accessor acts only for its immutable spell executor, whose immutable owner is a timelock; a
  timelock ward goes through `controller_path`. Validator keys (`bar` signatures) and ScribeOptimistic's challenge
  period are disclosed, like a Chainlink DON. The Monad Scribes are unverified on Monad; each contract was matched to a
  verified build on another chain, 32-byte operand by operand, and its code is pinned.
- **Spec scope.** A verdict that is only true for one target's own governance (Moonwell's bounded LBTC band and
  price override, Dolomite's own-configuration oracles) is added by that target's entry point alone, never by a
  registry every consumer of the chain passes: a Morpho vault reaching Moonwell's LBTC oracle sees the
  TemporalGovernor as a foreign controller. Moonwell's own set is the Unitroller's admin only while it is the pinned
  TemporalGovernor. Sky's pause is Sky governance only while `MCD_PAUSE.owner()` is zero: DSPause also lets its owner
  plot spells without DSChief.
- **Moonwell** (Base): every market of `getAllMarkets()`, worth (cash + borrows - reserves) x `getUnderlyingPrice`;
  the source is what the pinned ChainlinkOracle reads (`getFeed` of the underlying's symbol, or the oracle's own price
  override, own while the oracle's admin is the TemporalGovernor). Delay: the TemporalGovernor's `proposalDelay()`
  (its guardian fast-track stays in the composite). The 14 ChainlinkOEVWrappers are own (owner the TemporalGovernor,
  feed fixed at construction). The LBTC/BTC ChainlinkBoundedCompositeOracle uses its RedStone primary only inside
  [0.98, 1.02] BTC, set by the TemporalGovernor alone: the primary is bounded (decision 4), the Chainlink fallback is
  a path. Disclosed: the primary's controller (a 2-of-3 Safe through its ProxyAdmin) can make every LBTC read revert,
  which freezes that market, and can hold LBTC anywhere in the band while the real price leaves it.
- **Fluid Liquidity** (Arbitrum, Plasma): Liquidity reads no price; one row per vault of the VaultResolver, its debt
  in USD (token amounts read on chain, USD prices from Fluid's API for weights only; an unpriced vault is material).
  Each vault's oracle is walked by build: 24 Fluid oracle and CappedRate builds are pinned by masked template, a
  build's inputs are the contracts its immutables name, an unknown build is UNREAD. A CappedRate is judged on its own
  caps, never as a class. The VaultFactory auths, which can re-point any vault's oracle at once, were replayed from
  block 0 and are own while the factory's owner is the pinned VaultFactoryOwner (its auth setters are behind the
  Liquidity timelock); the fee auths only set rates, and the team multisig, an Instadapp Avocado (6-of-12 on
  both chains), re-points any vault's oracle and configures any DEX with no delay: it is scored from
  `requiredSigners()` and `signers()` with the Safe-rooted formula (56). The Liquidity composite still calls those
  instant powers a bounded bypass of its 24-hour timelock, which this reading contradicts. Delay: the Liquidity admin
  TimelockController's `getMinDelay()`, counted only because that contract is a verified build. An oracle input that
  is an account with no code is a bare key (2), and a build that names no input is UNREAD. The reUSD NAV feed (Arbitrum) is a spec: its aggregator swap and markdowns are
  governance-grade, its reports bounded, its ADMIN (a 3-of-5 Safe, replayed from block 0) scored.
- **Dolomite** (Arbitrum): one row per market with supply, at supply x `getMarketPrice`; an OracleAggregatorV2 market
  reaches every entry of `getOraclesByToken` at the whole market value (the aggregator sums with no cap); a market
  whose price reverts (a frozen market) is a row of unknown value. Own: DolomiteMargin and the oracles whose
  `DOLOMITE_MARGIN()` it is. Delay: 0, because accounts holding both EXECUTOR and BYPASS_TIMELOCK roles on
  DolomiteOwnerV2 (replayed from block 0, re-checked with `hasRole`) execute any queued call at once. The GM markets
  read GMX's Reader and DataStore: decision 7's key-by-key proof found keys a GMX config keeper sets at once with no
  tight bound (OPEN_INTEREST_RESERVE_FACTOR, OPTIMAL_USAGE_FACTOR with BORROWING_EXPONENT_FACTOR, MAX_PNL_FACTOR and
  others), so that path stays UNREAD. Disclosed: DolomiteOwnerV2's DEFAULT_ADMIN Safe (2-of-3) can swap any market's
  oracle at once through AdminPauseMarket (pause, then unpause with a new oracle, both through the bypass), which the
  composite's 300-second credit does not reflect; and one of three bare keys or a 2-of-5 Safe can pause any market,
  which freezes it (price 0 reverts) without moving its price.
- **Jupiter Lend** (Solana): one row per VaultConfig, worth its collateral (on-chain amounts, USD prices from
  Jupiter's API for weights only), reaching every source of its Oracle account (which has no update instruction).
  Delay: the `time_lock` of the VaultAdmin authority's Squads multisig. A Chainlink Store feed scores its single
  serum-multisig committee (feed owner, OCR2 config owner and the three program upgrades must all be that multisig's
  signer); a Pyth push feed scores the wormhole guardian quorum it is verified against (n / 2 + 1 per Pyth's published
  core-bridge source), the receiver's governance multisig and the Pyth DAO that upgrades it (Realms convention); a stake
  pool scores its program's upgrade multisig; the Huma PST pool scores its loss authority (a downward-only lever,
  decision 4), its pool owner and its programs' upgrades.
- **Proxyless Safe** (Purinta USDG, Robinhood Chain): a Safe whose slot-0 singleton is zero passes the Safe gate
  only when keccak of its runtime code is listed in `scripts/lib/safe_modules.py` KNOWN_PROXYLESS_SAFES, after its
  verified sources were compared with the official Safe release it vendors (decision 6). API3's
  GnosisSafeWithoutProxy: 15 vendored safe-contracts 1.3.0 files byte-identical to tag v1.3.0; only a constructor is
  added. The dAPI name setter behind API3's Api3ServerV1 (a 4-of-4 signer set) is one hop deeper: disclosed.
- **spUSDG** (Spark Savings USDG, Robinhood Chain, read by Steakhouse Turbo): its share rate only rises at `vsr`,
  which its setters move inside [minVsr, maxVsr] <= MAX_VSR, a code constant: bounded. Its upgrade and roles belong to
  the Spark Executor, reached only through the bridge alias of Spark's SubProxy on Ethereum, so to Sky governance
  (`sky_governance_path`); both chains' role and ward sets are replayed and re-checked.

**Scope.** Decided for the ten markets above and the Robinhood Chainlink admin, and extended on
2026-10-05 to Aave V3 Horizon, the Morpho V1 vaults (Steakhouse USDT and USDC on Ethereum, four on Base,
one on Monad), the Morpho Vault V2 vaults (two on Ethereum, six on Robinhood Chain), Radiant and GMX
(V2 and V1) on Arbitrum, and later that day, after the decisions above, to SparkLend, Moonwell, Fluid Liquidity
(Arbitrum, Plasma), Dolomite and Jupiter Lend: every tracked target that reads prices is now computed. Euler V2 and
Kamino Liquidity were added on 2026-10-05 from the same study; the Euler
AccessControlEmergencyGovernor on Plasma stays at 100, not applicable: a governance relay that holds no
funds and reads no price, whose vaults are rows of the eVaultFactory. The Morpho Blue singletons are not price consumers in this sense: each
market's oracle is fixed at creation, and bad debt stays in that market. A read-only study of 2026-10-05 (each recipe re-checked live by
a second reader) found how to read each of them; the choices it raised were decided the same day (see the bullets above
and `data/finding_2026-10-05-price-consumer-scope-study.md`).

Results on 2026-10-04 (live dry runs): Aave Core, Base, Arbitrum, Plasma and Monad 52; Compound Ethereum,
Base and Arbitrum 52; Morpho Adpend and 1337 31 (a RedStone deUSD feed behind a 2-of-3 Safe ProxyAdmin); the
Robinhood Chainlink admin 52 (its own composite). The 52s are the Chainlink proxy owners, a 4-of-9 Safe
with no delay. On 2026-10-05: Aave Horizon and the four Morpho V1 vaults on Base 52; Robinhood Chain
Steakhouse USDG 2 (its mGLO market is priced by `setRoundData` from a single bare EOA) and NetNet Credit 2
(the stock tokens' admin role sits with a bare EOA); Ethena x Steakhouse and Grove x Steakhouse 100 (no
allocation today, live caps noted); Steakhouse Turbo, Purinta, the two Ethereum Vault V2 vaults, the
Steakhouse USDT and USDC V1 vaults and the Monad vault 20 (material paths UNREAD, listed in
`data/finding_2026-10-05-price-consumer-scope-study.md`); Radiant 52 and GMX V2 52 (Chainlink and the
Chainlink Data Streams verifier, each behind a 4-of-9 Safe), GMX V1 2 (the `admin()` of its
PriceFeedTimelock, a bare EOA, can switch every token to keeper prices at once). Later on 2026-10-05: the
Euler eVaultFactory on Plasma 2 (the sdeUSD that one router converts through is upgradeable by a bare EOA)
and on Monad 2 (the vUSD strategy's investmentManager is a bare EOA), the TelosC Surge EulerEarn vault 43 (a
Pendle SY upgrade behind a 3-of-5 Safe; 34 after the review below, when the Earn's curator stopped counting as the
target's own and the EulerRouters it governs, a 2-of-5 Safe acting at once, were scored), Kamino Liquidity 45 (the Scope admin, a 4-of-10 Squads with no
delay, the same path score_kamino_lend publishes). After the decisions of 2026-10-05 (every wired target re-run live
on the final code): the Steakhouse USDT and USDC V1 and Prime USDC and EURCV V2 vaults 52 (Chainlink binds; EtherFi's
OPERATION proposer 67, Sky 81, Lido governance-grade); SparkLend 31 (RedStone inside each Chronicle Aggor median, a 2-of-3
Safe ProxyAdmin); the Monad Morpho vault 49 (Chronicle's 7-day timelocks, each scheduled by a 2-of-3 Safe, against 14
days); Moonwell 52; Fluid Plasma 52 and Fluid Arbitrum 20 (its sUSDai rate, 75% of debt, has no spec, and 23 dust vaults
the API does not price count as material); Dolomite 20 (the GMX keeper keys, the three GMX ROLE_ADMIN timelock paths
and two frozen markets of unknown value are all UNREAD); Jupiter Lend 35 (the Huma PST loss authority, a 2-of-3 Squads with no delay); Purinta 50 (a proxyless 4-of-8
Safe); Steakhouse Turbo 52. Every other target is unchanged. Open points are listed at the end of the finding. The deeper
inputs left out by the one-hop rule are listed in `data/finding_2026-10-04-price-paths-beyond-one-hop.md`.

## Morpho Vault V2 scoring

ADDED 2026-09-26, on Spap's explicit go-ahead after `data/finding_2026-09-25-vault-v2-scoring-scope.md`
scoped this as "a real methodology decision, not a mechanical extension" and deliberately left it
unbuilt three weeks running rather than answer it unilaterally. V2's architecture differs from every
V1 vault already scored here: per-function timelocks instead of one vault-wide delay, gates that can
be permanently abdicated (a power renounced forever, not just delayed), and a curator role that is
NOT uniformly a Safe the way V1's Steakhouse/Gauntlet templates are. Three decisions, each reasoned
below, each checked against the vault's own verified source before being finalized -- not assumed
from the September research that first scoped this.

**1. What `timelockScore` means for a per-function-timelock vault.** Score the MINIMUM delay among
the functions that can redirect capital or change what the vault can invest in: `addAdapter`,
`removeAdapter`, `setAdapterRegistry`, `increaseAbsoluteCap`, `increaseRelativeCap`, and the four exit
gates (`setReceiveSharesGate`/`setSendSharesGate`/`setReceiveAssetsGate`/`setSendAssetsGate`) where
still live (not yet abdicated -- see decision 2). Excluded, matching this project's own established
practice for V1 (Compound V3's pauseGuardian gets the same "bounded blast radius, not scored as a
bypass" treatment): pure fee setters (`setPerformanceFee`/`setManagementFee`/their recipients) and
`setIsAllocator`/`setForceDeallocatePenalty`, all correctly documented at 0-day delay by the vault's
own design because an allocator or fee-setter cannot redirect principal or drain funds outright.

**Clarification of 2026-10-04, confirmed by Spap the same day.** A fund-redirecting function that is permanently
abdicated (`abdicated(selector)` true) can never be called again, so its own timelock protects nothing
and is left out of the minimum, exactly as an abdicated exit gate already is. Live case: 5 of the 6
Robinhood Chain V2 vaults and both Ethereum L1 V2 vaults abdicated `setAdapterRegistry`; its own timelock
reads 0 only on Purinta USDG (7 or 3 days elsewhere), where counting it gave a false 0-day minimum. If every listed function and gate is
abdicated, the vault takes the top band (75). A failed `timelock()` or `abdicated()` read makes the
minimum UNREAD, scored 0 with a note, never read as "0 days". Shared reader:
[`scripts/lib/morpho_v2.py`](scripts/lib/morpho_v2.py), used on Ethereum L1 and Robinhood Chain.

**A real bypass was suspected and DISPROVEN by reading the actual source before writing anything
down.** `decreaseTimelock`'s own listed delay reads 0 days in Morpho's API, which looked at first like
a way to instantly zero out any OTHER function's 7-day protection (submit `decreaseTimelock(addAdapter,
0)`, wait 0 days, then call `addAdapter` immediately). Read `VaultV2.sol`'s actual `submit()` function
before trusting that reading: `_timelock = selector == decreaseTimelock.selector ? timelock[bytes4(data[4:8])]
: timelock[selector]` -- decreasing a FUNCTION's timelock is itself gated by THAT function's CURRENT
timelock, not by `decreaseTimelock`'s own. Decreasing `addAdapter`'s 7-day delay to 0 requires waiting
the full current 7 days first. No bypass exists; the nominal per-function delays are real.

**2. Whether an abdicated gate counts as a protection.** Not folded into `timelockScore` or any other
existing 0-100 field -- this project's methodology has no dimension for "a power was permanently
renounced," and inventing a numeric weighting for that would be exactly the unilateral-invention this
finding was scoped to avoid. Disclosed instead as a plain fact per gate, read live via the vault's own
public `abdicated(bytes4)` getter -- checked per-function, not assumed uniform: on Steakhouse Prime
USDC/EURCV specifically, 3 of the 4 exit gates (`setReceiveSharesGate`, `setSendSharesGate`,
`setReceiveAssetsGate`) are permanently abdicated; `setSendAssetsGate` is NOT -- it remains a live,
curator-controlled, 7-day-timelocked lever. A vault-wide "gates abdicated: yes/no" would have been
wrong for this exact vault; always read all four individually.

**3. How to score a non-Safe, non-role-registry curator (a bare EOA) versus a Safe curator.** No new
formula needed -- V1 already answers this identically: a bare-EOA owner or curator is scored with the
SAME near-worst-case treatment already used for Adpend USDC and 1337 USDC (`adminKeyScore`/
`multisigScore` near the floor), and a Safe curator uses the SAME `min(100, threshold*15 + max(0,
n-threshold)*5)` formula already applied to every V1 Safe curator. The "nested/dispersed signer"
question this decision cross-references was independently investigated on 2026-09-25
(`data/finding_2026-09-25-nested-signers-formula-investigation.md`) and found NOT a real gap in 19 of
20 real cases -- reuse the existing formula verbatim, don't invent a V2-specific one.

**Scope, deliberately incremental, not a single mass rollout.** V2's own scoping finding stressed
"each candidate vault needs its own individual investigation... not a template that generalizes
cheaply" -- the same per-target rigor every other scorer in this file already gets. Built first:
Steakhouse Prime USDC and EURCV on Ethereum L1 (`score_morpho_steakhouse_prime_usdc_v2`/`_eurcv_v2`),
chosen because their owner/curator resolve (via the already-documented `VaultV2Supervisor` one-hop) to
the EXACT SAME Steakhouse Safes this file already tracks and scores for 4 V1 vaults -- reusing
already-verified infrastructure, not introducing two brand-new unverified multisigs on the first pass.
The remaining Vault V2 targets on Ethereum L1, Robinhood Chain, Monad and Tempo (per
`data/finding_2026-09-25-vault-v2-inventory.md`'s $2.87B inventory) are the natural continuation of
this same methodology, one verified vault at a time, not assumed to generalize automatically.
**Robinhood Chain, 2026-10-04 (Spap's go).** Its 6 V2 vaults now follow decisions 1 to 3 with the same reader
and owner bands as Ethereum L1 (`scripts/lib/morpho_v2.py`, `scripts/lib/scorers.py::_v2_owner_admin_key`),
each owner shape read live that day. A 1-of-1 Safe owner (NetNet) is one key and scores as a bare EOA (5), the
convention the earlier manual analysis of these vaults used. Grove x Steakhouse's owner became, on 2026-10-02,
an executor contract with a 1-day `delay()` whose roles are not read yet: it stays unresolved (20) until they are.

## Data collection discipline

- **Never trust a name, a docs page, or a block explorer's "verified
  contract" label as the final answer about who controls what.** Every
  sub-score is re-derived from a live `eth_call`/`eth_getStorageAt`/
  `eth_getLogs` this run, not cached, not copied from a prior pass, not
  inferred from a variable name (`DELTA_FINANCIAL_MULTISIG` has, in
  practice elsewhere, resolved to a single EOA on the actual live contract -
  a name is a hypothesis, not ground truth).
- **A transient RPC failure degrades the score, it never silently keeps the
  prior confident value.** Every live-read helper in `scripts/lib/web3_utils.py`
  retries with backoff before giving up; if it still fails, the calling
  scorer treats that as `None`, not as "assume the last known value still
  holds" - the affected sub-score drops to a conservative default with a
  note explaining why, "fail closed" for a risk scorer. A single failing
  target no longer takes the rest of that run's batch down with it either
  (`scripts/lib/scorers.py::score_all()`'s per-target isolation).
- **A high-severity or surprising claim gets checked on a second,
  independent RPC before being trusted** - `scripts/lib/web3_utils.py::cross_checked()`
  runs a read against every RPC in a list and raises on disagreement; used
  where a single-source read would otherwise be the sole basis for a score
  that materially changes a target's risk band.
- **`methodologyHash` is tied to the code that produces the push** (from the first
  push after 2026-09-30). It is `keccak256("<label>:<code digest>")` on EVM and
  `sha256("<label>:<code digest>")` on Solana; the code digest is a sha256 over every
  repository file reached by import from the ecosystem's scorer and from its push
  script (which decides which score goes to which key), plus
  [`scripts/lib/methodology.py`](scripts/lib/methodology.py) itself. **Same hash, same
  code. A different hash means one of those files changed**: a fix of our method, but
  also an added target or a refreshed snapshot kept in a scorer file. A change of the
  target's own keys never moves it. Library versions (web3, eth_abi, Python) are not
  covered. A real push pins the digest before scoring, refuses to run unless the files
  equal the HEAD commit, and refuses again if they change during the run, so every
  published hash matches a commit (reproducible by others once that commit is on
  GitHub). **Before that date the hash was a hand-typed label that was never bumped**:
  of the 22 composite changes published under an unchanged hash up to 2026-09-30 on the
  6 oracles with a fast log source, 21 were fixes of our own scorer and 1 was mixed
  (Morpho Blue: a real Safe change that also flipped an exact-committee comparison of
  ours); none was a pure change of a target's keys. Monad, read in full on 2026-10-01,
  adds 2: one fix of ours (Aave V3) and the first pure change of a target's keys (a
  Morpho vault's curator Safe went from 2-of-6 to 2-of-7, 60 to 61). HyperEVM is still
  unread (its public RPC refuses archive reads past a daily quota). Each is classified
  with its commit or on-chain source in
  [`data/score_change_causes.json`](data/score_change_causes.json), which also lists the
  6 Robinhood Chain changes published with the v2 to v3 label change (mixed);
  `python3 scripts/score_history.py` lists them from the chain.
- **A "has code" check alone doesn't mean "independently controlled."** An
  EIP-7702-delegated EOA has code (23 bytes: the `0xef0100` designator plus a
  delegate address) but is still controlled by one signing key, not the
  contract logic it delegates to.
  [`scripts/lib/account_classification.py::classify_account()`](scripts/lib/account_classification.py)
  distinguishes this from both a bare EOA and a real, independently-deployed
  contract, rather than letting `is_eoa()`'s binary check silently conflate
  "has code" with "safer" - checked against every tracked target's authority
  chain 2026-09-17, none found yet. *Update 2026-09-20: two are now tracked --
  Fables PoolRegistry's sole admin and Saffron's owner (found by the index-15
  rotation audit; the first claim of it being the first was corrected by its
  independent verifier).*
- **An AccessControl role's admin can be itself.** `getRoleAdmin(role) == role`
  means any current holder can grant or revoke that role unilaterally, with no
  threshold and no separate governance layer above it - a "1-of-N roles"
  failure structurally identical to a 1-of-N Safe but invisible to a check
  that only counts Safe signers.
  [`scripts/lib/account_classification.py::check_self_escalation_risk()`](scripts/lib/account_classification.py)
  checks this directly rather than assuming a role hierarchy is sound because
  a delay or a Safe exists somewhere else in the chain.

- **One score per oracle key, checked before every push.** The oracle stores a
  single score per address (a single PDA per target on Solana), so two scored
  entries that share a key silently overwrite each other: `updateScores()`
  succeeds, the tracked count is lower than the number of scores pushed, and the
  first entry can no longer be read back. This was seen for real on Hyperliquid
  (2026-09-19: 15 scores pushed, 13 stored), the only case observed: none of the other
  push scripts checked for it before this change, so nothing establishes that it never
  happened elsewhere. It was fixed on Hyperliquid with derived keys for the colliding
  HIP-3 dexes. The eight per-ecosystem push scripts (Arbitrum, Base,
  Monad, Plasma, Tempo, Ethereum L1, Robinhood Chain and Solana, the last one in its
  dry-run too) now run
  [`scripts/lib/oracle_keys.py::assert_unique_oracle_keys()`](scripts/lib/oracle_keys.py)
  before they read a key or build a transaction and refuse the whole push, naming each
  colliding key and entry, if two entries map to the same key (EVM addresses compared
  case-insensitively and with or without the `0x` prefix, Solana public keys exactly; a
  derived `oracleKey` does not hide a collision there, those scripts push `target`).
  Hyperliquid keeps its own resolution (derived keys plus a hard refusal), Zcash's
  attestation bundle already refuses duplicate target ids
  (`chains/zcash/scripts/attest_scores.py::build_bundle`), and the one-off prepared push
  script for four Robinhood targets is not guarded.
  [`scripts/check_oracle_key_collisions.py`](scripts/check_oracle_key_collisions.py)
  runs the same check over every ecosystem's live `score_all()` at once; its first
  run is in
  [`data/audit_oracle_key_collisions_2026-09-20.md`](data/audit_oracle_key_collisions_2026-09-20.md).

- **A read whose answer has the wrong size is refused, not truncated.** The ABI decoder
  behind every scorer read (`eth_abi.decode`, web3's `contract.functions.f().call()`) returns
  the first 32-byte word of the answer and ignores the rest, so a getter that returns a struct
  or several values, read with a shorter ABI, gives its first values instead of failing (seen
  on 2026-09-20: `getScore(address)` read as `uint256` gave `adminKeyScore` in place of
  `compositeScore`). The scorers that read through `scripts/lib/web3_utils.py`, and the Tempo
  and Hyperliquid scorers, which use their own primitives, now install
  [`scripts/lib/abi_returndata_guard.py`](scripts/lib/abi_returndata_guard.py): an answer whose
  size is not what the declared outputs require (exactly, for static outputs, and for outputs
  with a dynamic type a head plus a layout that re-encodes to the length returned) is refused,
  logged once per call site to stderr, and the helpers that swallow exceptions read it as an unresolved read.
  [`scripts/audit_abi_returndata.py`](scripts/audit_abi_returndata.py) runs
  every ecosystem's live `score_all()` with the guard in record mode; its first run, in
  [`data/audit_abi_returndata_2026-09-21.md`](data/audit_abi_returndata_2026-09-21.md), checked
  1,758 decodes and found no size or layout mismatch (eight empty-data probes of bare addresses, listed in the note). It does not cover a wrong ABI of the right size, raw
  `eth_call` reads that slice their own answer (all of Hyperliquid's), or Solana and Zcash (no
  ABI).

## Limitations - what this oracle cannot see, and where it isn't consistent yet

Publishing this list is deliberate: a number nobody can falsify isn't worth
much, and a DAO deciding whether to rely on this oracle needs to know its
edges, not just its claims.

- **The score measures exposure, it does not predict who gets hit.** A
  pre-registered backtest (2026-10-01,
  [`data/finding_2026-10-01-backtest-victims-vs-controls.md`](data/finding_2026-10-01-backtest-victims-vs-controls.md))
  read 5 incident victims on Ethereum and 18 untouched peers of similar
  size one month before each incident: the composite did not separate them
  (victims at 43 to 49, several peers rooted in a single bare key). The
  attacks went around the configuration (spoofed signing interface,
  compromised devices, a service key), so watching changes matters as much
  as the static score. Five sets can only rule out a large, regular gap.
- **Off-chain and social-layer control is invisible by construction.** A
  Safe's 3 owners could be 3 employees of the same entity, or the same
  person's 3 wallets - this oracle has no way to see that from chain state
  alone, and does not claim to. `multisigScore` measures cryptographic
  threshold strength, not real-world independence of the signers.
- **A signer is not always one key.** `multisigScore` counts each owner as one signer. Of the 405 distinct signers of the
  registered root Safes, 27 are themselves Safes, one is a TimelockController and one is an EOA delegated through EIP-7702.
  `scripts/check_nested_signers.py` resolves them: the effective number of EOA keys equals the top-level threshold for 15 of
  the 17 Safes with such a seat and is higher for the other two, so no committee is weaker than its threshold says; a nested
  1-of-N seat makes the dispersion bonus overstate strength (Aave's protocol guardian: 4 keys needed, 13 can contribute). The
  formula still counts a nested Safe as one owner; unifying that is not done. Record:
  `data/finding_2026-09-21-who-really-signs.md`.
- **A "real EOA" signer's own key hygiene is out of scope.** Whether an
  address is protected by a hardware wallet, a leaked seed phrase, or an
  exchange's hot wallet all read identically on-chain as "one key."
- **The multisig-strength formula is not identical across every tracked
  target.** Most Safe-rooted targets use the general
  `threshold*15 + (owners-threshold)*5` shape described above, but several
  scorer functions use a tuned variant reflecting that specific authority
  chain's context (see that function's own docstring and the relevant
  `data/scored_targets_*.md` entry for the reasoning). This project has not
  forced every target through one single formula, which means two
  structurally similar Safes can land a few points apart depending on which
  target's scorer they're read through. Flagged here rather than glossed
  over; unifying this is open follow-up work, not done.
- **Not every proxy-upgrade path or admin-capable getter is checked for
  every target.** A scorer traces the specific authority chain relevant to
  the action it's scoring (e.g. `setOwner`/`setCurator` for a vault) - it
  does not enumerate every AccessControl role or every getter that could
  plausibly grant some privileged capability. A role sitting on a completely
  separate bare EOA from the one actually traced would not be caught unless
  that specific role happens to be part of the traced chain. This has already
  cost two scores (see `data/finding_2026-09-20-unscored-role-sweep.md`, found
  by replaying `RoleGranted`/`RoleRevoked` history and trying to refute each hit
  with `eth_call` simulation). Radiant on Arbitrum was scored only through its
  72h `TimelockController` (`provider.owner()`), but `getPoolAdmin()` is a
  separate 4-of-11 Safe that can upgrade the token proxies with no delay, so it
  now scores as a Safe with no timelock (admin 65, multisig 95, timelock 0,
  composite 55, was 69); a 1-of-5 emergency-admin Safe that can only pause is
  disclosed, not scored. Aave V3 on Monad was scored as the DAO Executor behind a
  1-day delay, but its `PROTOCOL_GUARDIAN` 4-of-7 Safe also holds `POOL_ADMIN`
  there, so it now scores admin 65, multisig 75, timelock 0, composite 49 (was
  71). Both are on-chain since the 2026-09-20 re-push (Arbitrum tx
  `0x308ad2c8fa527a0e5c30139b6b154ff48462cd046df9840a17f25775c21fbd23`, block
  310,697,409; Monad tx
  `0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019`, block
  64,022,942). The same sweep found a third case of a different shape: the Ethereum
  L1 Ethena target was USDe's retired minter, inert since 2024-07-08, not the live
  one. The live minter (admin a 24h timelock behind a 5-of-10 Safe) now scores
  65/100/55, composite 73, as a new target, and the old one is no longer refreshed (it turns stale after 2026-09-28 16:39 UTC)
  (`data/finding_2026-09-20-ethena-live-minter.md`). The sweep covered the
  AccessControl-shaped contracts the scorers already touch, so the same pattern may
  still hide in an authority shape it did not enumerate.
- **`crossExposureScore` is not computed the same way across every
  ecosystem, and its cross-ecosystem half is a dated snapshot, not a live
  check.** Inside one ecosystem it is a live check on Robinhood Chain (20+
  signer groups), Ethereum L1 (by root group), Base (among its own Safe-rooted
  targets), Hyperliquid, Tempo and Zcash (among their own tracked targets, e.g.
  Zcash's two funds against each other), and Solana (checked, no overlap found
  between Jupiter and Kamino); the Arbitrum, Plasma and Monad scorers run only
  the cross-ecosystem comparison. **Updated 2026-09-20**: under the convention
  described in the `crossExposureScore` section above, a cross-ecosystem overlap
  is now folded into the score on every EVM ecosystem: Robinhood Chain,
  Ethereum L1, Arbitrum, Base, Plasma and Monad, plus Tempo, whose signers are
  ordinary EVM Safe owners (its Morpho Blue core now folds at 80, the same 9
  Morpho Association signers as Ethereum L1, Base and Robinhood Chain). The
  cross-ecosystem check itself began 2026-09-17
  (`scripts/lib/cross_ecosystem_overlap.py`,
  `scripts/check_cross_ecosystem_overlap.py`) and immediately found a real
  overlap: Arbitrum's and Base's Aave V3 emergency `GOVERNANCE_GUARDIAN` Safes
  share the exact same 9 signers at 5-of-9, two different addresses, the same
  CREATE2-redeployed-shared-committee pattern this project's sister research
  already documented for ether.fi/Curve (see
  `data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md`, since
  extended to five chains). What it does not do, stated plainly:
  - **It is not re-run live against the other chain.** A scorer compares its own
    fresh read against a dated snapshot, by design, so that one chain's RPC
    reliability cannot degrade another chain's push. A committee rotation on the
    other chain is only caught when the sweep script or the drift audit is re-run
    and the snapshot (on Robinhood Chain, the hand-set flag) is updated; until
    then a stale 80 can outlive the overlap and a new overlap can go unflagged.
  - **A scorer folds only the committees it holds a snapshot of.** An overlap the
    sweep script finds but nobody wired into a scorer stays out of the score, and
    "no overlap found" is a dated result, not proof of none. Radiant's pool-admin
    Safe, for example, was compared by hand against every tracked group on
    2026-09-20 (no match) but is not in the sweep script's registry, so the script
    itself does not yet cover it.
  - **Solana, Hyperliquid and Zcash are not in the sweep at all.** Solana and
    Zcash use signer formats (base58 keys, P2SH redeem-script keys, NEAR account
    IDs) that are not comparable to EVM addresses without a bridge, and
    Hyperliquid's signer sets have not been added to the registry. Tempo's two
    resolvable Safes are covered; its LayerZero OneSig and Chainlink MCMS
    controllers are not Gnosis Safes and are not comparable yet. A known,
    disclosed gap, not a confirmed clean result for those.
- **A live re-derivation only proves the state at the block it was read,
  not that nothing changes before the next scheduled run.** Robinhood
  Chain's scores are re-derived and pushed weekly; a signer rotation the day
  after a push would not surface until the following week's run (or a
  manual `--dry-run`/push) picks it up.
- **This oracle scores authority *structure*, not authority *intent*.** A
  well-governed DAO with a real timelock can still vote to do something
  harmful; a bare EOA can belong to a careful, trustworthy operator. The
  score is a statement about how much unchecked power exists and how it's
  gated, not a prediction about whether it will be misused.

## Reproducing a score

```bash
pip install -r scripts/requirements.txt
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from lib.web3_utils import get_w3
from lib.scorers import score_all
for r in score_all(get_w3('https://rpc.mainnet.chain.robinhood.com')):
    print(r['label'], r['compositeScore'], r['notes'])
"
```

Every number printed is re-derived from live chain state in that run - never
replayed from a cached value. See `scripts/update_scores.py --dry-run` for
the same re-derivation against the exact code path the weekly production
cron actually runs.

To check which code produced a published score, check out the commit recorded with the
push (`methodologyCommit` in `api/scores.json` for Robinhood Chain, in the push record
for Solana, in the push log otherwise) and recompute the hash; it must equal the
`methodologyHash` returned by `getScore()`:

```bash
python3 scripts/lib/methodology.py arbitrum-ecosystem --label authority-risk-oracle-arbitrum-ecosystem-v1
```

The label of each ecosystem is `METHODOLOGY_VERSION` in its push script:
`authority-risk-oracle-v3` (Robinhood Chain, `scripts/update_scores.py`) and
`authority-risk-oracle-<ecosystem>-v1` for `ethereum-l1`, `arbitrum-ecosystem`,
`base-ecosystem`, `tempo`, `plasma-ecosystem`, `monad`, `hyperliquid` and `solana`
(`chains/<ecosystem>/deploy/`).
