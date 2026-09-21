# Solana -- 8 new DeFi targets scored, 2026-09-18 (closing the config-admin decode backlog)

Closes [`scouted_targets_2026-09-17-run2.md`](scouted_targets_2026-09-17-run2.md)'s
own "Open points for scoring_build" list: 16 real DeFi targets had been
fully scouted (live-verified program-upgrade authority chains, real TVL
figures) but published only as upper-bound composites, since
METHODOLOGY.md 6.2 takes the minimum over every full-power path and the
protocol-level application config admin (market owner, group admin, pool
state admin) hadn't been decoded yet for any of them. This pass closes
that gap for 8 of the 16 -- the ones with the highest TVL and/or the
highest upper-bound composites, where an unverified number carried the
most overclaim risk.

Every number below is re-derived live by `score_all()` against Solana
Mainnet Beta, not replayed from a prior pass -- and every multisig
identity, byte offset, and hardcoded constant cited in `scorers.py`'s own
docstrings was independently verified against live RPC reads (both
`https://api.mainnet-beta.solana.com` and `https://solana-rpc.
publicnode.com`) and each protocol's own published source/IDL before
being trusted, not assumed from the original scouting pass's own report.

## Summary table

| Target | adminKey | multisig | timelock | composite | Upper bound (2026-09-17) | Change |
|---|---|---|---|---|---|---|
| Raydium (AMM v4, CLMM, CPMM) | 45 | 57 | 0 | **35** | 43 | lower -- separate 2-of-3 `admin::ID` |
| marginfi (main lending group) | 60 | 88 | 0 | **50** | 54 | lower -- separate 5-of-17 `MarginfiGroup.admin` |
| Kamino Liquidity (yvaults) | 60 | 100 | 0 | **54** | 77 | lower -- same shape, zero delay |
| Jupiter Perpetual Exchange | 55 | 80 | 0 | **46** | 69 | lower -- separate Squads v3, no delay |
| Jupiter Lend | 65 | 87 | 13 | **56** | 60 | lower -- separate 5-of-10, shorter delay |
| PumpSwap (+ bonding curve) | 50 | 75 | 0 | **43** | 43 | **confirmed**, not lowered |
| Meteora DAMM v2 | 5 | 0 | 0 | **2** | 47 | **CRITICAL** -- hardcoded 2-key OR-gate |
| Orca Whirlpool | 5 | 0 | 0 | **2** | 76 | **CRITICAL** -- 1-of-8 reward super-authority |

Six of eight moved down from their published upper bound; two (Meteora
DAMM v2, Orca Whirlpool) collapsed from comfortably-scored to the same
near-floor CRITICAL band this project's Hyperliquid side already found
on Kinetiq/`para` StakingVault, for the structurally identical reason: a
single compromised key (or, for Whirlpool, a 1-of-8 multisig that scores
identically to one) is sufficient to seize real protocol power, no
matter how strong the CODE-upgrade path looks on its own.

## Why these findings matter more than a routine tightening

Every one of these 8 targets already had a real, live-verified,
reasonably strong PROGRAM UPGRADE authority (Squads v3 or v4, mostly with
real thresholds and several with real timelocks). None of that changed.
What changed is that this pass checked whether that was the ONLY
full-power path -- and for 6 of 8, it wasn't:

- **Raydium** and **Jupiter Perps** each have a hardcoded or
  IDL-exposed `admin`/`admin::ID` constant that is a genuinely SEPARATE,
  OLDER, weaker multisig than the current upgrade authority -- in both
  cases, the SAME multisig that used to control code upgrades before a
  since-completed migration to a stronger one, quietly left in place as
  the application-level admin.
- **Kamino Liquidity** and **Jupiter Lend** each have a separate admin
  vault with the SAME signer-threshold shape as their upgrade authority
  but with LESS delay (zero, in Kamino's case) -- the same "one path
  delayed, a same-signer-shape path with no delay at all" pattern this
  project's own `score_kamino_lend` already documented for that
  program's own Scope-oracle-admin path.
- **Meteora DAMM v2** and **Orca Whirlpool** are the most severe: a
  hardcoded 2-key OR-gate and a 1-of-8 multisig respectively, BOTH
  scoring at the exact same floor as a single bare private key, sitting
  quietly beneath a program upgrade authority that, read in isolation,
  looked like one of the stronger targets in this whole batch (Whirlpool
  was upper-bounded at 76, the highest score in the original 16-target
  scouting pass).

None of these are new methodology -- every one reuses
`_score_full_power_path`'s existing formulas and METHODOLOGY.md 6.2's
existing minimum-over-paths convention verbatim. What was missing was
simply reading far enough to find the second path.

## Two judgment calls, disclosed rather than silently made

- **Whirlpool's `reward_emissions_super_authority`** is scored as
  full-power (not bounded) because it can unilaterally reassign the
  per-pool `reward_authority` for ANY Whirlpool, which can then set that
  pool's reward emission rate directly -- a real economic parameter, not
  a protocol-owned balance. See `score_orca_whirlpool`'s own docstring
  for the full reasoning and the exact instruction sources this rests
  on; a future reviewer who disagrees with this classification has
  everything needed to push back on it.
- **DLMM and DAMM v1** (Meteora's other two programs, sharing DAMM v2's
  own upgrade authority) are DELIBERATELY NOT scored with DAMM v2's same
  collapsed number, even though transaction-forensic evidence strongly
  suggests the identical 2-key admin set controls equivalent roles on
  both. Neither program's real on-chain logic is public source, so this
  project's own "transaction evidence isn't source-level proof"
  discipline (the exact lesson from this same project's earlier
  CoreWriter/Kinetiq overclaim on the Hyperliquid side) keeps them at
  their prior upper-bound composite (47) instead of forcing an
  unverifiable number.

## Verification

- Every new multisig/vault identity is independently re-derived offline
  (PDA math or Squads v3 authority-index derivation, no trust in the
  hardcoded candidate alone) and required to exactly match the live-read
  authority every run -- the same discipline `_resolve_squads_v4`/
  `_resolve_squads_v3` already enforce for every pre-existing target in
  this file.
- Every new byte-decode offset was checked against the protocol's own
  published source or on-chain Anchor IDL before being trusted -- for
  Kamino Liquidity's `GlobalConfig.adminAuthority`, computed field-by-
  field from the actual Codama-generated codec
  (Kamino-Finance/kliquidity-sdk) and independently cross-checked by
  searching the live raw account bytes for the expected pubkey, landing
  at the identical offset both ways. For marginfi, `MarginfiGroup.admin`
  is confirmed via the on-chain Anchor IDL's own field-order listing,
  which ALSO revealed 7 more admin-named fields this pass deliberately
  did NOT chase (disclosed in `score_marginfi`'s own docstring) --
  METHODOLOGY.md 6.2's own minimum-over-paths rule means this function's
  own output remains an upper bound too, just a materially tighter one.
- Raydium's `admin::ID` is read LIVE from CLMM's on-chain Anchor IDL
  (`sol_read.read_anchor_idl`'s `hardcoded_addresses` mechanism, built
  for exactly this case) rather than hardcoded from a GitHub citation --
  the one case in this batch where METHODOLOGY.md 6.2's own "hardcoded
  keys invisible to account reads" caveat did NOT apply, because the
  program happens to publish an on-chain IDL that exposes it.
- Meteora DAMM v2's `ADMINS[]` genuinely IS invisible to any live
  account read (confirmed: its own on-chain IDL's `hardcoded_addresses`
  has 20 entries, none admin-related) -- hardcoded from
  MeteoraAg/damm-v2's own verified GitHub source, locked in by a
  dedicated regression test (`TestMeteoraDammV2HardcodedAdmins`) so a
  future edit can't silently drift from it.
- 9 new unit tests added (`scripts/lib/tests/test_solana_defi_config_
  admins.py`), covering all 6 new decoders -- 3 against the exact real
  bytes fetched live, 3 against synthetic-but-realistic-shape fixtures
  for the larger accounts (matching this project's own Hyperliquid test
  precedent for large ABI-encoded responses).
- `python3 -m unittest discover -s scripts/lib/tests`: 169/169 pass.
- `python3 scripts/validate_all_scorers.py --ecosystem solana`: 12/12
  targets pass (the 4 pre-existing plus these 8 new ones), `OVERALL:
  PASS`.

## Cross-exposure findings, live-detected

Adding these 8 targets to `score_all()`'s existing cross-exposure check
surfaced real, previously-invisible relationships (not assumed, computed
live from the actual signer sets):

- **Jupiter Aggregator v6 and Jupiter Perpetual Exchange share the
  SAME Squads v3 multisig** (`7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf`)
  -- Aggregator v6's own CURRENT program-upgrade authority, and Perps'
  own `Perpetuals.admin` (a role Perps itself migrated AWAY from for its
  own code-upgrade path, but never rotated for this application-level
  role). One compromised multisig now reaches two separate, large
  Jupiter products at once.
- **Kamino Liquidity's 7-signer admin multisig overlaps with Kamino
  Lend's own already-scored multisigs** -- consistent with, and now
  independently re-confirming, `scouted_targets_2026-09-17-run2.md`'s
  own note that all 7 members are shared across both Kamino products.
- **Meteora DAMM v2 shares a signer with Jupiter's own multisig group**
  (already documented in the original scouting pass's cross-exposure
  table, re-confirmed live here).

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/solana')
from scorers import score_all
for r in score_all('https://api.mainnet-beta.solana.com'):
    print(r['label'], r['compositeScore'], r['crossExposureScore'])
"
```

## Adversarial review, 2026-09-18

Before committing, all 8 new scorer functions and 6 new decoders were
reviewed by 4 independent dimensions (Raydium/marginfi facts;
Kamino Liquidity/Jupiter Perps/Jupiter Lend/PumpSwap facts; the Meteora
DAMM v2 `ADMINS[]` full-power classification and the deliberate
non-promotion of DLMM/DAMM v1; the Whirlpool `reward_emissions_super_
authority` full-power judgment call), each finding then independently
re-verified by a separate agent instructed to try to refute it via its
own live RPC calls and GitHub source fetches. 30 agents, 26 findings, 23
confirmed outright (mostly "matches exactly, no fix needed"), 3 flagged
for disposition:

- **marginfi's two "independent" multisigs share almost the same
  people.** The review caught that this pass's first draft understated
  the overlap between `MarginfiGroup.admin`'s multisig (5-of-17) and the
  program-upgrade multisig (7-of-15): all 15 Vote-permissioned members
  of the upgrade multisig are a live-verified STRICT SUBSET of the
  admin multisig's 17 members (2 extra members carry no Vote
  permission). The two accounts are genuinely distinct (different
  address, different `create_key`) but this is the same governing body
  voting under a lower bar, not two independent checks. Fixed:
  `score_marginfi`'s docstring now states this plainly, and the
  function now live-verifies and discloses the subset relationship in
  its own `notes` every run. The composite score (50) is unchanged --
  the threshold/voter counts were always read correctly; only the
  "how independent are these two paths" framing was incomplete.
- **A verifier's own re-derivation bug, caught by re-checking with the
  actual project code.** One verify-pass agent claimed Jupiter Perps'
  `admin` value could not be reproduced as the Squads v3 authority-index
  PDA of `7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf` (its own
  from-scratch PDA implementation searched indices 0-49 and found no
  match). Re-run directly against this project's own `sol_read.
  find_program_address`, index=1 matches exactly (bump 254) -- the
  verifier's own reimplementation had a bug, not `score_jupiter_perps`.
  No code change; this is recorded as a reminder that a verifier's
  refutation is itself just another claim to check, not automatically
  authoritative.
- **Meteora DLMM/DAMM v1 non-promotion, re-affirmed.** A finding
  proposed introducing an intermediate score tier (reusing
  `off_curve_unresolved`'s (20,0,0) shape) for DLMM/DAMM v1, arguing
  the current upper-bound-47 treatment ignores real transaction-forensic
  evidence. The verify-pass agent refuted this specific proposal --
  correctly, on independent re-derivation -- as a category error (that
  tier is defined for a confirmed on-chain authority field pointing at
  an unidentified off-curve PDA, not for a suspected mechanism with no
  public source at all) and as running against this project's own
  CoreWriter/Kinetiq lesson (an indirect-evidence overclaim that had to
  be walked back once real source was read). No change: DLMM/DAMM v1
  stay at their prior upper bound with the existing honest-limitations
  disclosure.

## Not yet promoted

The remaining 8 of the original 16 scouted targets (Meteora DLMM, Meteora
DAMM v1, Sanctum Infinity's own already-partially-decoded pool admin,
Sanctum Validator LSTs, JitoSOL, the SPL Stake Pool program, and 2 more)
remain at their scouted upper bounds -- either because (DLMM/DAMM v1)
their real source isn't public to confirm a specific number, or because
this pass prioritized the highest-TVL and highest-upper-bound targets
first and did not reach the rest. `chains/solana/data/scouted_targets_
2026-09-17-run2.md`'s own "Open points for scoring_build" section still
tracks what remains.
