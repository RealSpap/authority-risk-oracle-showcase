# Finding (2026-09-18): should `score_morpho_vault_generic` treat a 1-of-1 Safe as EOA-equivalent? Evidence for the decision, not a fix

Requested by a tracked GitHub Projects item: "scorer Morpho generique --
traiter un Safe 1-of-1 comme une EOA ? (NetNet Credit 22 on-chain vs 8 a
la main)." Pure investigation -- `scripts/lib/scorers.py` is unmodified
by this finding. A change to this scorer's formula needs this project's
own adversarial-review discipline before committing, per `AGENTS.md`'s
"Before committing" section, not a unilateral edit from a research pass.

## What the code does today, and why

`score_morpho_vault_generic` (`scripts/lib/scorers.py:392-452`) already
discloses this exact gap in its own docstring: *"It does not
special-case a 1-of-1 Safe as functionally EOA-equivalent... confirmed:
NetNet Credit scores 22 here vs. 8 by hand."* Tracing the actual branch
(lines 431-434):

```python
if owner_is_eoa:
    admin_key = 10
elif owner_safe:
    admin_key = 30 + owner_safe[1] * 6  # threshold=1 -> 36, no special case
```

For NetNet Credit (`0x99347d5F70D3838763f6Bddcf80304C8aa953B57`), owner
and curator are the SAME confirmed 1-of-1 Safe:
`admin_key = 30 + 1*6 = 36`, `multisig = 1*8 + 1*8 = 16`, `timelock_score
= 10` (all three authority selectors have delay 0). `_composite(36, 16,
10) = 22`. **Re-verified live against Robinhood Chain mainnet today
(2026-09-18): unchanged, still 36/16/10 -> 22.** Not stale, still a live
gap.

## This project's own precedent is NOT one consistent rule

Two different conventions coexist, and both are more conservative than
this scorer's current `36/16`:

- `_safe_rooted_scores` (`scripts/lib/scorers.py:1085-1106`, the "batch
  9" convention used by 4+ other Robinhood Chain scorers): threshold==1
  -> `admin_key=10` -- **identical to the bare-EOA constant this same
  file uses everywhere else** -- but `multisig=15`, not 0. Admin risk is
  treated as EOA-equivalent; multisig strength is still counted as a
  small, nonzero, real (if weak) signal.
- The hand-derived precedent for a confirmed 1-of-1 "Team Multisig"
  (Ramses CL V2, `data/scored_targets_2026-09-15-batch4.md`): admin=15,
  multisig=5, composite=8 -- the exact "8 by hand" figure this tracker
  item cites for NetNet Credit's own manual score. Close to, not
  identical to, a bare EOA's usual 5-10 range.

Two OTHER ecosystems have an explicit, already-written rule that goes
further, treating it as full literal identity:
- `chains/hyperliquid/METHODOLOGY.md:293-294`: *"A native multisig with
  threshold 1 and exactly one authorized user is also (1,1): it is one
  key, scored the same as a bare EOA."*
- `chains/solana/METHODOLOGY.md:264`: the methodology table gives
  "on-curve key" and "any multisig with t=1" the literal same row
  (`5/0/0`).

So: Hyperliquid and Solana chose full identity (adminKey AND multisig
both collapse to the bare-EOA value). Robinhood Chain's own two existing
precedents (`_safe_rooted_scores`, and the hand-derived Ramses number)
both instead keep adminKey matched to the EOA value but leave multisig
small-and-nonzero -- reflecting that a Safe transaction still routes
through a separate contract mechanism (a real, if minor, structural
difference from an EOA signing directly), not a distinction this project
invented for this finding.

`data/scored_targets_2026-09-16-batch9.md:117-123` already flags this
exact tension as an open, deliberately-unresolved question -- this
finding is corroborating and quantifying that flag with live numbers,
not raising a new one.

## What this does NOT do

- Does not change `compositeScore` for NetNet Credit or any other
  Morpho-generic-scored vault (Purinta, Ethena x Steakhouse).
- Does not modify `score_morpho_vault_generic` or `_safe_rooted_scores`.
- Does not decide between "full identity" (Hyperliquid/Solana's rule)
  and "EOA-matched adminKey, small nonzero multisig" (this project's own
  two Robinhood Chain precedents) -- both are real, already-used
  conventions in this codebase, applied inconsistently across
  ecosystems. That choice, and whether `score_morpho_vault_generic`
  should be rewritten to match `_safe_rooted_scores`'s existing formula
  outright rather than invent a third number, is for the actual fix's
  adversarial-review pass to decide.
