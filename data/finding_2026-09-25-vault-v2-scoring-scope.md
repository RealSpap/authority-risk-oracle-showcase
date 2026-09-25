# Morpho Vault V2 scoring: scoped, not built -- a real methodology decision, not a mechanical extension

2026-09-25. Roadmap item 10 ("voit large" round 2), the last item on the ranked list, the one already
flagged as the largest chantier. Investigated with the same "verify before building" discipline
applied to items 2 and 3 today (both of which turned out to need no code change) -- this one is
different: there IS a real, sizeable gap ($110M+ untracked on Monad alone, a chain this oracle already
tracks), but closing it properly needs a genuine new scoring decision, not a mechanical wiring job.
Not built this pass. One concrete, low-risk fix applied instead: a stale docstring corrected.

## The gap, quantified

Per `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`'s own research: Monad has 6
Morpho Vault V2 vaults ($110M combined as of 18-19/09) that this oracle does not track at all --
`score_morpho_vault_monad` only covers a $0.108M Morpho V1 vault, and its own docstring used to
(wrongly) call it "the largest" vault on Monad. **Fixed here** (`chains/monad/scorers.py`, comment
only, no score changed): the docstring now says "largest V1 vault" and cites the untracked V2 total.
Re-checked live 2026-09-25: Monad's largest V2 vault today is Hyperithm USDC Apex, $39.4M (the
market has moved since the 09/20 research; Steakhouse Prime ETH, cited then at $47.4M, no longer
appears among the largest -- not investigated further, TVL moves).

Arc ($152M across 3 V2 vaults, per the same research) is explicitly OUT of scope regardless of V2
methodology: Arc is not one of this oracle's 10 tracked ecosystems, and adding a new ecosystem is a
separate decision this project has deliberately deferred until after the hackathon (see memory
`feedback_oracle_depth_over_breadth.md`, `feedback_ecosystem_addition_5point_discovery_gate.md`) --
"voit large" means going deeper on tracked ground, not adding new chains unilaterally.

## Why this isn't a mechanical extension of the V1 pattern

V1 vaults (owner/curator/guardian, each a Safe or bare key, a single vault-wide timelock) are what
every scorer built this pass already handles. V2's real architecture is different:
per-function timelocks (`addAdapter` 3 days, `removeAdapter` 7 days, `increaseAbsoluteCap` 3 days,
`abdicate` 7 days, in the vaults the 09/20 research read on-chain), permanently ABDICATED exit gates
(receive-assets/send-shares/receive-shares gates switched off for good -- a deliberate design choice
the vault's own source says exists so these gates "can[not] lock users out of exiting the vault"),
and several functions at timelock 0 by design (`setIsAllocator`, fee setters) that are not holes
(the source explicitly limits what an allocator or fee-setter can do to depositor principal).

**Checked live today, on Monad's current largest V2 vault (Hyperithm USDC Apex, $39.4M)**: `owner()`
resolves to a real 2-of-3 Gnosis Safe -- the SAME read this project's V1 scorers already use, genuinely
reusable. But `curator()` resolves to a bare EOA with zero bytecode -- not a Safe, not a role registry,
a single key. On Sentora's Vault V2 family (the 09/20 research's own example, not re-checked live
today), the curator is itself a 1-of-1 Safe. **The curator model is not uniform across V2 vaults the
way it is for V1's Steakhouse/Gauntlet templates this pass already built** -- each candidate vault
needs its own individual investigation before it can be scored, the same per-target rigor every other
target in this oracle already gets, not a template that generalizes cheaply.

## What a real build would require (a decision, not a default)

Three real design questions, each a genuine calibration choice:
1. **What does `timelockScore` mean for a per-function-timelock vault?** The current field assumes one
   delay covering the authority-changing action that matters. V2 has several delays of different
   lengths gating different actions (3 to 7 days across the functions read in the source research).
   Scoring the shortest, the longest, or a specific function (e.g. `addAdapter`, the cap-raising path
   closest to V1's own scored action) each tell a different story.
2. **Does an abdicated gate count as a protection, and how much?** A permanently-disabled exit gate is
   a real, verifiable, positive fact (funds cannot be locked in) -- but there is no existing field in
   this project's methodology for "a power was permanently renounced", only for "a power exists and is
   time-delayed or not".
3. **How to score a non-Safe, non-role-registry curator** (a bare EOA, as found live today) versus a
   Safe curator (as the 09/20 research found on Sentora) -- the SAME dispersion question already
   investigated and left open for controller-level scoring today
   (`data/finding_2026-09-25-nested-signers-formula-investigation.md`), now appearing again in a new
   context.

None of these should be answered unilaterally the way "voit large" authorized reusing already-settled
conventions (the controller-concentration report, the Hyperliquid registry extension, the exit-capacity
check) -- each of those reused a formula or pattern already decided elsewhere in the codebase; this one
would be inventing the pattern itself.

## What is buildable without answering those questions, if wanted

A DISCLOSED-only V2 vault inventory (owner Safe threshold, curator type -- Safe/EOA/other -- and the
raw per-function timelock durations from Morpho's own API, same query shape `check_exit_capacity.py`
already uses) is genuinely low-risk and reuses only already-settled conventions: no `timelockScore`/
`adminKeyScore` computed, just the same "off-chain, disclosed, no score" pattern as the controller-
concentration report and RISK_ADMIN discovery. Not built this pass -- flagged as the safe next step if
Spap wants forward progress on this item without first resolving the three design questions above.

## Conclusion

No new scorer added, no new score published. One documentation fix (Monad's V1 docstring, accurate
scope). This is the third roadmap item today (after nested-signers and bounded-power-cap) where
investigation-first discipline found a real question that deserves Spap's input rather than a
unilateral answer -- consistent, not a pattern of avoiding work: 5 other items were built and pushed
today with real, verified findings.
