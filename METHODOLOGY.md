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
| `oracleAuthorityScore` | For a target that itself provides price/state data to others, who controls what it reports? (100 = not applicable) |
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

**`oracleAuthorityScore`** - only meaningful for a target that is itself a
price/state oracle (a Chainlink feed admin, an AMM's TWAP-adjacent config) or
whose own numbers are consumed as an oracle elsewhere. Scores who can change
what it reports. 100 (not applicable) for every target that neither provides
nor depends on an oracle role this project tracks.

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
- **Methodology changes are hashed and versioned on-chain**
  (`methodologyHash`/`methodologyVersion` fields on every pushed score) so a
  consumer can tell whether two scores were computed under the same rules
  before comparing them.
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
