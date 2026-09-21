# Tempo -- 4 controller types resolved, 6 new targets scored, 2026-09-18

Closes `chains/tempo/data/scouted_targets_2026-09-17-run2.md` section 8's
open points 1, 2 and 3 in one pass, since all three turned out to share
one root cause: rule R2's `classify()` had no resolution path for 4 real,
live controller SHAPES it had never needed before (a plain OpenZeppelin
`TimelockController`, Chainlink's `RBACTimelock` + hierarchical `MCMS`,
a UUPS `AccessControlEnumerable` "bridge controller", and a LayerZero
OApp's endpoint delegate as a parallel zero-delay path) -- every target
that routed through one of these collapsed to `"unresolved contract"`
(the worst band, composite 8), and a real bug in `classify()`'s own
weakest-controller selection (`TypeError` on an unresolved sub-controller)
made the gap worse, not just incomplete.

No new score DIMENSION or formula was added -- R1 through R7 are
unchanged. `classify()` now simply resolves more real on-chain shapes to
the existing `(k, n)` pair every other kind already produces, so
`admin_key_score`/`multisig_score`/`timelock_score` all run unmodified.

## Summary table

| Target | Before (2026-09-17) | After (2026-09-18) | Change |
|---|---|---|---|
| Tempo L1 validator registry | 31 | 31 | unchanged (no new controller type on this path) |
| USDC.e | 55 | 55 | unchanged |
| USDT0 | 43 | 43 | unchanged |
| pathUSD | **8** (unresolved) | **9** (10/15/0) | closes open point 2 -- resolves to the same bare EOA `0x79C6631F...4a4E` behind the Bridge controller |
| USDB (new) | n/a | **9** (10/15/0) | same Bridge controller as pathUSD |
| DLUSD (new) | n/a | **9** (10/15/0) | same Bridge controller as pathUSD |
| cbBTC (new) | n/a | **39** (65/42/0) | CCIP RBACTimelock, weakest path = proposer MCMS 4-of-42; BYPASSER (0-delay) drags timelock to 0 |
| PRIME (new) | n/a | **39** (65/42/0) | reaches the same RBACTimelock/MCMS set as cbBTC, but via a DIFFERENT root role -- see caveat below |
| EURC.e (new) | n/a | **55** (65/98/0) | LayerZero OneSig, already resolvable by the pre-existing R2 -- no new controller type needed |
| cUSD (new) | n/a | **43** (65/58/0) | Cap TimelockController (24h) on the owner() path, but the SAME Cap Safe is also the OFT's LayerZero delegate with NO delay -- that zero-delay path dominates R5b's min-over-paths rule |

Every number above matches `scouted_targets_2026-09-17-run2.md` section
4's own hand-derived "Resolved reading" proposal EXACTLY (independently
re-derived here from a real, running `classify()`, not copied from that
table).

## The four controller shapes, how each is resolved now

**1. OpenZeppelin `TimelockController`** (Cap's cUSD admin, 24h delay,
proposer/executor/canceller = Cap Safe 3-of-5). Detected via
`getMinDelay()` + `PROPOSER_ROLE()` both succeeding. It is a plain
`AccessControl` contract (NOT `AccessControlEnumerable` -- confirmed
against real OpenZeppelin source), so there is no on-chain enumeration
getter; `PROPOSER_ROLE` holders are found by scanning the standard
`RoleGranted`/`RoleRevoked` events since deployment (a new, generic
log-scanner, `_role_members_via_logs`, separate from `scan_role_logs`'s
TIP-20-specific event names) and confirmed with `hasRole`. EXECUTOR and
CANCELLER are deliberately NOT treated as controlling roles (they can
only execute an already-scheduled, already-delayed action, or cancel one
-- purely defensive/non-originating, the same convention that already
excludes TIP-20's `UNPAUSE_ROLE` from the root-control set).

**2. Chainlink `RBACTimelock` + hierarchical `MCMS`** (CCIP's cbBTC/PRIME
admin, 3h delay). `RBACTimelock` is a modified `TimelockController`
v4.7.0 (confirmed against `smartcontractkit/ccip-owner-contracts`' real
source) with a 5th role, `BYPASSER_ROLE`, that skips the delay entirely --
detected the same way as (1), plus an extra `BYPASSER_ROLE()` probe.
Unlike Cap's timelock, `RBACTimelock` genuinely IS
`AccessControlEnumerable`, so its role holders (the PROPOSER and BYPASSER
MCMS addresses) are read directly via `getRoleMemberCount`/`getRoleMember`,
no log scan needed. Each MCMS itself is a hierarchical group-quorum
multisig (`ManyChainMultiSig.sol`): every signer belongs to exactly one
of 32 groups, each group has its own quorum and a parent group, and the
root (group 0) must be satisfied recursively. `_mcms_flatten_quorum`
computes the cheapest way to satisfy the root as a plain bottom-up
dynamic program (a k-of-n group's cheapest cost is the sum of its k
cheapest children's costs) and returns a single `(min_signatures,
total_signers)` pair, so the rest of the pipeline (`admin_key_score`,
`multisig_score`, `weakest()`) never needs to know MCMS exists as a
distinct shape. Independently re-derived (own from-scratch decode of live
`getConfig()` data, separate from both the research pass that first
characterized this shape and the original scouting pass's hand
computation) and confirmed to reproduce the exact same numbers all three
ways: proposer 4-of-42, bypasser 8-of-47, canceller 2-of-47 (canceller not
currently scored -- purely defensive, same reasoning as EXECUTOR/CANCELLER
above).

**3. UUPS `AccessControlEnumerable` "Bridge controller"** (pathUSD/USDB/
DLUSD's `ISSUER_ROLE` holder, `0x8354D80EeA9978Faa04c3b36771c1e8b9c3e9058`).
No `getMinDelay`/`PROPOSER_ROLE` (not a timelock at all), but
`DEFAULT_ADMIN_ROLE` (`bytes32(0)`, OZ's own convention) IS enumerable.
Resolves to the same bare, EIP-7702-delegated EOA
(`0x79C6631FA15CdA38777FB9DD7a6348bAEe794a4E`) already found manually by
the scouting pass -- confirming, not just assuming, that this one key can
replace the minting logic on all three tokens it controls.

**4. LayerZero endpoint delegate as a parallel, zero-delay path.** A
registered OApp's `delegate` (a completely separate authority concept
from `owner()`) can reconfigure its inbound message verification (receive
library, DVN set) in ONE transaction with no owner-timelock gating at all
(`LayerZero-Labs/LayerZero-v2`'s `EndpointV2._assertAuthorized` treats
`msg.sender == delegate` as fully equivalent to `msg.sender == oapp`
itself). Previously this only reached `notes` (rule R6b), invisible to
every numeric score. Now folded in as a third parallel controller
candidate inside `classify()`'s generic contract branch, exactly like
`owner()` and the EIP-1967 admin slot already are -- a no-op for any
contract that isn't a registered OApp (`delegates()` returns the zero
address). For cUSD's OFT this is the whole story: `owner()` resolves to
the well-delayed 24h Cap timelock, but the SAME Cap Safe is ALSO the
endpoint delegate with zero delay, and R5b's "shortest delay over every
path" rule means that zero-delay path is what actually counts.

## `_classify_timelock`'s missing admin path, found by adversarial review

The first draft of `_classify_timelock` only treated `PROPOSER_ROLE` and
`BYPASSER_ROLE` as controlling roles, omitting `ADMIN_ROLE`
(RBACTimelock) / `DEFAULT_ADMIN_ROLE` (plain TimelockController) entirely
-- a real gap, since an `ADMIN_ROLE` holder can call `bypasserExecuteBatch`
directly (confirmed against real source: no schedule/delay check at all,
same immediacy as `BYPASSER_ROLE`) AND grant/revoke any role including
itself. Confirmed independently, three separate ways, that this had NOT
changed any published number: both live targets (Cap's TimelockController
and CCIP's RBACTimelock) are self-administered -- their own admin role is
held only by their own address, confirmed via a full-history log scan (Cap)
and live enumeration (CCIP), so there was nothing weaker to miss today.
Fixed anyway, since a future target with an externally- or weakly-held
admin role would otherwise have silently scored safer than it really is,
with no signal that a role was even considered. `ADMIN_ROLE` is credited
delay=0 (matches `BYPASSER_ROLE`'s immediacy); `DEFAULT_ADMIN_ROLE` is
credited the timelock's own `min_delay` (seizing role membership still
requires a fresh scheduled action to actually execute anything).

## The `classify()` bug, fixed

`scouted_targets_2026-09-17-run2.md` section 8, open point 3: the
internal weakest-controller line inside `classify()`'s generic contract
branch called `min(resolved, key=lambda r: (r["k"], -r["n"]))` directly --
crashes with `TypeError` the instant ANY controller in that list is
unresolved (`k` is `None`, and `None` can't compare with an `int`). This
hit cbBTC, PRIME and cUSD in the scouting run (worked around there by
using rule R3's own ordering by hand instead of running the real code).
The top-level `weakest()` function already had the correct, None-safe
form; the fix shares that same logic (`_weakest_sort_key`) in both
places instead of leaving two copies that can drift apart again.

## PRIME's real weakest path, precisely (caught by adversarial review)

The table above says PRIME "reaches the same RBACTimelock/MCMS set as
cbBTC" -- true, but the FIRST draft of this doc said it did so via
`DEFAULT_ADMIN_ROLE`, mirroring cbBTC. That's stale: PRIME's
`DEFAULT_ADMIN_ROLE` was granted to the RBACTimelock at block 32,152,683
and REVOKED at block 32,482,513 (2026-07-30 21:26:47 UTC, confirmed live
via `eth_getBlockByNumber` and a full-history role-log scan) -- already
correctly noted in `scouted_targets_2026-09-17-run2.md`'s own T8 row, just
not carried forward precisely into this file's first draft. PRIME's
`DEFAULT_ADMIN_ROLE` is CURRENTLY a plain, un-timelocked 4-of-7 Safe
(`0x7039867c5DE7364100c3DF0DD56A62a16AEa2936`, the "Hastra 4-of-7 Safe" the
scouting pass already named). The path that actually reaches the RBACTimelock/
MCMS set for PRIME is `ISSUER_ROLE` -> the CCIP `BurnMintTokenPool`
(`0xffDF3b641b4A90cdc4b6CFEC8f68386C877B571a`) -> its `owner()` -> the same
RBACTimelock. `weakest()`'s own "equal k, larger n is weaker" rule (R3)
picks that MCMS path (k=4, n=42) over the Safe's (k=4, n=7) anyway, so
**the published composite (39) is unaffected** -- but the provenance in
the table above was wrong until this correction. Worth its own note
regardless of scoring impact: PRIME's admin governance silently changed
hands (RBACTimelock -> an unrelated Safe) about 7 weeks before this pass,
a real on-chain event this project had not previously surfaced on its own.

## Cross-exposure, changed by adding real targets to the same run

pathUSD's `crossExposureScore` moves from 100 (previously scored alone,
nothing to share a signer with) to 60 now that USDB and DLUSD are scored
in the same run and are confirmed to share the exact same bare EOA
(`0x79C6631F...4a4E`) behind the same Bridge controller -- about $120.0M
of combined supply under one uncontested key as of 2026-09-18 (pathUSD
$39.8M + USDB $76.5M + DLUSD $3.7M, live `totalSupply()` reads, found by
adversarial review to be materially higher than this pass's first draft
figure of ~$73.5M -- USDB's own supply alone grew from ~$30.4M to ~$76.5M
in about 24h, well within its `supplyCap` but a fast enough move to be
worth timestamping any dollar figure here rather than treating it as
fixed), exactly the aggravating context `scouted_targets_2026-09-17-
run2.md` section 4 already flagged before any of the three were promoted
to a real score. cbBTC and PRIME share the same CCIP RBACTimelock/MCMS
set (crossExposure 80 each) -- via different root roles, see the PRIME
section above. This is rule R6's existing contract-semantics formula,
unmodified -- it simply had more tracked targets to compare against this
run.

## Verification

- Every new resolution path was tested independently against the target's
  OWN real on-chain data (not synthetic-only) before it was trusted:
  `classify()` run directly against the Cap TimelockController, the CCIP
  RBACTimelock, all 3 of its MCMS instances, the Bridge controller, and
  cUSD's OFT -- every result checked against the scouting pass's own
  hand-derived numbers and matched exactly.
- The MCMS quorum-flattening algorithm was independently re-derived by
  THREE separate paths that all agree: (a) this project's own from-scratch
  Python decode of live `getConfig()` data, (b) a separate research agent's
  own independent decode, (c) the original scouting pass's hand
  computation -- all three land on 4-of-42 (proposer), 8-of-47 (bypasser),
  2-of-47 (canceller).
- 13 new unit tests (`scripts/lib/tests/test_tempo_controller_types.py`):
  pure-function coverage for `_mcms_flatten_quorum` (flat, nested,
  disabled-group and unsatisfiable-root cases, plus a shape-regression
  pin matching cbBTC's real 3-group structure) and the `weakest()`/
  `_weakest_sort_key` bug fix, plus mocked end-to-end `classify()` tests
  for all 4 new branches (including the MCMS-inside-RBACTimelock
  ordering that avoids the `owner()`-based circular reference a naive
  implementation would hit, since an MCMS's own `owner()` is the very
  timelock that names it as proposer/bypasser).
- `python3 -m unittest discover -s scripts/lib/tests`: 186/186 pass.
- `python3 scripts/validate_all_scorers.py --ecosystem tempo`: 10/10
  targets pass (Tempo is normally skipped from the default `validate_all_
  scorers.py` run for being slow -- a full run now takes about 7.5
  minutes, mostly the Cap TimelockController's full-history `RoleGranted`
  log scan, since it is the one new controller type without on-chain
  enumeration; unchanged from before this pass for every other target).

## Not yet promoted / disclosed limitations

- CANCELLER-role holders (on both the Cap and CCIP timelocks) are
  resolved-capable but deliberately not folded into the score, matching
  the EXECUTOR/UNPAUSE_ROLE precedent (defensive-only powers).
- The Bridge controller's `getRoleMembers(bytes32)` batch getter (found
  during research, genuine OZ v5.3.0 `AccessControlEnumerableUpgradeable`
  addition, not a Tempo-custom function as first assumed) is not used --
  `_role_members_enumerable` uses the classic per-index getters instead,
  which work identically and are the same primitive already needed for
  `RBACTimelock`.
- `tempo-rpc.publicnode.com`'s free tier refuses `eth_getLogs` on a full
  historical range ("Archive requests require a personal token") --
  `_role_members_via_logs`, like the pre-existing `scan_role_logs`, uses
  only the official `rpc.tempo.xyz` endpoint for the scan itself, then
  confirms each candidate's CURRENT role membership with `hasRole` on
  both endpoints, the same single-source-for-discovery-but-dual-source-
  for-confirmation discipline METHODOLOGY.md section 7, open point 2
  already established for TIP-20's own log scan.
- `classify()` has no memoization: the same address reached via two
  different root-role paths for one target (e.g. cUSD's Cap Timelock,
  reachable both directly and through its own PROPOSER_ROLE recursion)
  gets resolved twice, independently. Correctness is unaffected (both
  resolutions agree), only wall-clock time -- disclosed rather than
  "fixed" this pass, since Tempo's full run (~7.5 minutes, dominated by
  Cap's TimelockController needing a full-history log scan) is already
  in the project's own default-skip list for slow ecosystems.
- The `depth > 3` hard stop in `classify()` is defensive headroom, not
  something the current target set actually needs: adversarial review
  traced the REAL depth reached in production (via `score_token`'s actual
  root-role-first entry point, not an isolated `classify()` call on a
  timelock address directly) at 2 for cbBTC/PRIME (ISSUER_ROLE's
  BurnMintTokenPool -> RBACTimelock -> MCMS) and 2 for cUSD (OFT ->
  Cap Timelock -> its own PROPOSER_ROLE -> the Cap Safe) -- comfortably
  under the cutoff, but less headroom than an earlier draft of this
  review claimed (which tested the timelock address in isolation and
  undercounted by one hop).

## Adversarial review, 2026-09-18

4-dimension review before commit (TimelockController/RBACTimelock facts;
the MCMS quorum-flattening algorithm -- the highest-stakes, most novel
code in this whole change; `classify()`'s branch ordering and the
`TypeError` bug fix; end-to-end scoring and `timelockScore` wiring), each
finding independently re-verified by a separate agent instructed to try
to refute it. 17 agents, 13 findings, 11 confirmed, 2 refuted. Real fixes
applied, described in their own sections above: `_classify_timelock` now
also resolves `ADMIN_ROLE`/`DEFAULT_ADMIN_ROLE` (found 3 independent
times across dimensions, MEDIUM, no scoring impact today); PRIME's
provenance corrected (`ISSUER_ROLE`, not `DEFAULT_ADMIN_ROLE` -- the
RBACTimelock's role on PRIME was revoked on-chain 2026-07-30, MEDIUM,
no scoring impact); the $73.5M -> $120.0M supply figure and the stale
module docstring, both LOW. The MCMS quorum-flattening algorithm itself
came back fully CONFIRMED CORRECT -- the review's own independent
from-scratch decode and flattening reproduced 4-of-42/8-of-47/2-of-47
exactly, the strongest possible outcome for the highest-stakes dimension.

**Self-caught, not review-caught**: fixing the `ADMIN_ROLE` gap above
surfaced a second, more serious bug before it ever reached the review or
a commit -- a self-administered admin role (both real targets: the
timelock holds its own admin role) recursed `classify()` back into the
same contract, which re-derived the same self-held role, forever, until
the depth cutoff returned "unresolved" and wrongly dragged the WHOLE
result (including the already-correct `PROPOSER_ROLE`/`BYPASSER_ROLE`
resolution) to that worst-case band. Caught by re-running `classify()`
live against both real targets immediately after writing the `ADMIN_ROLE`
fix, before trusting it -- exactly the "never trust a change without
re-running it live" discipline this project applies throughout. Fixed
(filter out self-referencing holders before recursing) and locked in with
a dedicated regression test.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/tempo')
from scorers import score_all
for r in score_all():
    print(r['label'], r['compositeScore'], r.get('crossExposureScore'))
"
```
