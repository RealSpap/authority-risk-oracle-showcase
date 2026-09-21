# Batch 7 -- 2026-09-16

Two changes in this batch, both structural rather than "one more protocol":

1. **A new 5th dimension, `crossExposureScore`**, added to every tracked target
   -- does the same real signer (root EOA, or Gnosis Safe owner) also control
   ANOTHER tracked target? Requested directly by Spap after a genuine gap was
   pointed out: this oracle's own methodology citation names
   `defi-admin-key-risk` only, never `multisig-overlap` -- so cross-protocol
   signer concentration, exactly the failure mode multisig-overlap (343
   protocols, 570 confirmed Safes) exists to catch, was never checked here at
   all. `compositeScore` is deliberately left untouched (still exactly
   0.4*adminKey + 0.3*multisig + 0.3*timelock, this target's own authority
   setup in isolation) -- `crossExposureScore` publishes as its own field
   because it's a property of the tracked SET, not of any one target.

2. **A second, independently-discovered gap closed in the same pass**: while
   building the signer registry needed for (1), 15 of the 34 tracked targets
   (all of batch 4 and batch 5's findings -- the L1 rollup authority group, six
   targets; Ramses CL V2, four targets; Ekubo Core; Longbow's three vaults; and
   Uniswap V2's `feeToSetter`) turned out to have **no scorer function in
   `scorers.py` at all**. They were pushed once, by hand, when first found, and
   never wired into `score_all()` -- meaning every recurring `update_scores.py`
   run since batch 5 silently left them frozen at their original score,
   never re-verified. Five new scorer functions close this: `score_rollup_l1_authority`,
   `score_ramses_clv2`, `score_ekubo_core`, `score_longbow_vault`,
   `score_uniswap_v2_factory_feetosetter`.

## crossExposureScore: methodology

Convention matches the rest of this project (100 = safest): for each tracked
target's GROUP (targets sharing one authority chain -- e.g. the 5 Robinhood
stock tokens all under one beacon), `crossExposureScore = max(0, 100 - 20 *
sharedGroupCount)`, where `sharedGroupCount` counts how many OTHER groups
share at least one resolved root signer (a bare EOA, or a Gnosis Safe's
individual owner address) with this one. Computed fresh every run in
`scripts/lib/signer_overlap.py` -- every Safe's `getOwners()` is re-read live,
never trusted from a prior pass, same discipline as everything else in this
project.

**Every root signer set was re-derived live this pass**, including cases not
previously fully resolved:
- NetNet Credit's 1-of-1 Safe sole signer: `0xe7e867518C5B3d929CA63622f314FF9Dc60E96f6`.
- Ramses' "Team Multisig" sole signer: `0xbE0ca442D6B7D81E0FAa7dbFd09331019F893f89`
  (confirmed a bare EOA).
- Longbow's owner/curator Safe addresses (never individually recorded before):
  `0x396ae0BD5623c3750e15fd222770F1e972153ED4` (owner) and
  `0xe600452658762042749eb8e11955542B7EBeA4Bb` (curator), on the Core vault --
  confirmed identical 3 owners, 2-of-3, matching the finding already
  documented for all three vaults in batch 5.
- The L1 rollup's 7-of-8 Safe: `0x7Ae50886c7EA0394613aa7Dcc287a5c9650784b6`,
  re-derived via a fresh `EXECUTOR_ROLE` `RoleGranted`/`RoleRevoked` replay
  from genesis on **Ethereum mainnet** (`gateway.tenderly.co/public/mainnet`
  -- most public Ethereum RPCs cap `eth_getLogs` ranges too small to be
  practical for this scan; several were tried and rejected before finding one
  that actually returns full results, noted in `signer_overlap.py`). One of
  its 8 seats, `0x0fc5c64074641e677Fb86bCE80303a2eE64344Ac`, is itself a
  nested 3-of-7 Safe -- its 7 owners are the real root signers for that seat,
  giving 14 total root signers for this group (7 direct EOA seats + 7 nested).

## The one real overlap found

**Morpho Steakhouse USDG vault and Morpho Ethena x Steakhouse USDG vault share
the identical curator Safe** (`0x9023FBD6A08C666491A2d1648737E400cF42D2Fb`,
3-of-7) -- all 7 owners appear on both groups' root signer sets. Both targets'
`crossExposureScore` drops from 100 to **80** (one shared group).

**Context checked before calling this notable, per this project's own
standing discipline**: this is not a coincidental, hidden overlap -- it is
the exact same curator entity managing two Morpho vaults on the same chain,
which is a normal, visible business relationship (Steakhouse Financial curates
both). Not a "gotcha" finding. But it is still a real, quantifiable
systemic-risk fact worth publishing rather than omitting: a lending market
that treats these two vaults as independently-governed collateral is wrong --
a single compromised signer on that one Safe can act on both at once. That is
precisely the failure mode `crossExposureScore` exists to surface, whether or
not the underlying relationship is legitimate.

No other overlap was found across any of the other 13 groups (Pendle's own
two ProxyAdmins share one signer with EACH OTHER, but that's the same
target's own internal structure, not a cross-protocol overlap, and is
correctly excluded).

**Confidence caveats, stated plainly**:
- Spark Savings USDG has no resolvable EOA signer set this pass (its
  authority is a self-administering contract, not a Safe; the SubProxy
  upstream controller on L1 remains untraced per batch 6) -- excluded from
  cross-referencing, `crossExposureScore` reads 100 by the project's
  not-applicable convention, not because it was checked and found clean.
- Ekubo Core has no authority surface at all -- same convention, same reason.
- Ramses' `RamsesTimelock.getMinDelay()=0` finding (batch 4) was not
  re-derived from scratch this pass; the exact `RamsesTimelock` address
  (distinct from `AccessHub`) was not re-identified in this pass's own
  records, flagged here rather than silently re-asserted as freshly checked.

## Contract change

`AuthorityScore` gained a 5th field, `crossExposureScore` (uint8), between
`oracleAuthorityScore` and `compositeScore` -- a breaking ABI change,
redeployed to a **new testnet address** (see README "Status" for the current
one; the previous testnet address is superseded, not upgraded in place).
Chosen deliberately: this is exactly the moment to make a breaking struct
change cheaply, before any mainnet deployment exists to migrate. 16 Foundry
tests pass against the new struct (2 new, one asserting `crossExposureScore`
is stored and read back independently of `compositeScore`).

## Running total

34 targets, now all genuinely covered by `score_all()` (up from 19 of 34
before this batch -- the other 15 were frozen since batch 4/5). Every target
also carries a live-recomputed `crossExposureScore` for the first time.
