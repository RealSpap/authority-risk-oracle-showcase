# Controller-level concentration over this oracle's own tracked Morpho V1 vaults

2026-09-25. Backlog item 2 of `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`
("A signal per controller... would follow the same convention as the cross-exposure score"),
retained on the GitHub tracker board (`Spap - research & outreach tracker`, cards #9/#10) but never
built. Built here as `scripts/lib/controller_concentration.py` + `scripts/check_controller_concentration.py`,
off-chain only (no `AuthorityScore` field added, same precedent as `l1CappedComposite`,
METHODOLOGY.md), over the 9 Morpho V1 vaults this oracle tracks on Ethereum L1, Base and Monad
(the 8 added earlier today, commit `15543f2`, plus Monad's pre-existing one).

## Why this is not decorative

`llamarisk`, `Chaos Labs`, `Gauntlet` and `Hypernative`/`Blockaid` were researched live today
(9-agent workflow, sources cited per competitor) specifically to check this: none of the five
publishes a public, continuous, per-CONTROLLER score. Gauntlet is the concrete case this closes a
gap against -- it is itself a Morpho vault curator (fee revenue) while also advising the governance
of DAOs whose risk parameters it sets, a conflict independent commentary (KuCoin, Hindenrank C+/36)
says curators "can't do this reporting themselves" about. A per-controller rollup, computed by a
party that curates nothing, is exactly the missing external check.

## Result, live-verified 2026-09-25

```
9 tracked Morpho V1 vaults, $1663.4M total TVL (Morpho API, live), 13 distinct controller addresses
```

**Top 2 controllers by TVL govern $763.6M of $1663.4M tracked (46%)** -- independently reproducing,
on this oracle's own scoped target set, the same 46% figure the wider-scope 20/09 research
(`chains/ethereum-l1/scripts/analyze_controllers.py`, over the whole Morpho ecosystem, not just
tracked targets) had already found. Not a coincidence being asserted as a new discovery: a
different script, a narrower scope (9 tracked vaults vs. the whole ecosystem), the same number --
noted as a cross-check, not claimed as independent confirmation of causation.

**Ranked:**

| Controller | Safe shape (per chain) | Vaults | Chains | TVL governed | Flag |
|---|---|---|---|---|---|
| Steakhouse owner Safe `0x0a0e559b..` | L1 5-of-10, Base 5-of-9, Monad 5-of-8 | 5 | 3 | $381.8M | same address, different config per chain |
| Steakhouse curator/guardian Safe `0x827e8607..` | L1 2-of-7, Base 2-of-6, Monad 2-of-7 | 5 | 3 | $381.8M | holds curator AND guardian on the Monad vault -- no independent check |
| Gauntlet owner Safe `0x5a4e1984..` | Base 4-of-7 | 1 | 1 | $415.7M | |
| Gauntlet curator Safe `0x9e33faae..` | Base 3-of-7 | 1 | 1 | $415.7M | same 7 signers as owner and guardian (already scored per-vault) |
| Gauntlet guardian Safe `0x7084bf4d..` | Base 3-of-7 | 1 | 1 | $415.7M | |
| Adpend USDC owner/curator (bare EOA) `0xf630d85a..` | L1 unresolved | 1 | 1 | $361.2M | holds owner AND curator -- no independent check |
| Spark curator Safe `0x0f963a8a..` | Base 3-of-5 | 1 | 1 | $312.0M | |
| Spark guardian Safe `0xf5748bbe..` | Base 3-of-5 | 1 | 1 | $312.0M | disjoint from curator -- genuine separation |
| (6 more single-vault, single-role controllers, $66.2M-$192.6M each) | | 1 | 1 | | |

## Two findings this tool surfaced while being built, neither assumed going in

**1. A real bug in the tool's first version, caught before publishing any number.** The first
implementation resolved a controller's Safe config (owners, threshold) ONCE per address and applied
it to every chain that address appeared on. Live-checked before trusting the output: the Steakhouse
owner Safe (`0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD`) reads 5-of-10 on Ethereum L1, 5-of-9 on
Base, 5-of-8 on Monad -- three DIFFERENT owner sets behind the same CREATE2 address, independently
reconfigured per chain, no cross-chain sync. The naive version would have silently reported the
wrong signer count and threshold for two of the three chains. Fixed by resolving per (ecosystem,
address), never assumed shared -- `scripts/lib/controller_concentration.py`'s own docstring records
this so the next reader doesn't rediscover it by shipping the same bug.

**2. A stronger cross-chain finding than what was coded for Monad, found as a side effect.**
`chains/monad/scorers.py::score_morpho_vault_monad` already scored a `crossExposureScore` of 80 for
this vault, reasoning from SIGNER-SET CONTAINMENT: its curator/owner Safes were said to be a subset
of Robinhood Chain's "steakhouse" committee (a snapshot dated 2026-09-19). Building this tool found,
live, that the vault's owner and curator/guardian are not merely subset-related -- they are the
LITERAL SAME Safe addresses as this pass's own new Ethereum L1 and Base Steakhouse vaults
(`_KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25` / `_KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25`). No score
changed (the flat-80 ceiling from METHODOLOGY.md's `min(within-ecosystem, 80)` convention already
applied), but the docstring's stale "2-of-6"/"5-of-8" wording -- true only when originally written,
since drifted -- is corrected, and the stronger same-address relationship is now recorded rather
than only the weaker subset one. See `chains/monad/scorers.py`'s own updated docstring.

## What this is not

Not a new `AuthorityScore` field, not pushed on-chain, not a new 0-100 scale. A read-only rollup
over already-published, already-scored targets -- the same "controller" framing the tracker board
asked for, built the same way `l1CappedComposite` was: off-chain, additive, reversible.

## What this does not cover, on purpose

- Euler Earn vaults, Morpho V2 vaults, and vaults not yet tracked by this oracle (backlog item 1,
  larger, separate, listed as a further candidate).
- Robinhood Chain's Morpho targets (a different registry mechanism, `signer_overlap.py`'s `GROUPS`,
  not the `owner()`/`curator()`/`guardian()` triple this module reads directly) -- would need its
  own wiring, not attempted this pass.
- Arbitrum, Plasma, Tempo, Hyperliquid, Solana, Zcash have no tracked Morpho vaults today.

## Verification

`python3 scripts/check_controller_concentration.py` -- read-only, live `eth_call` + Morpho's public
API for TVL, no key, no transaction. 15 new unit tests (`scripts/lib/tests/test_controller_concentration.py`,
pure logic, no RPC) specifically cover the per-chain-config bug above (`test_same_address_different_chains_merges_but_keeps_per_chain_safe`).

## Test suite: 3 more stale fixtures found and fixed while running the full suite before this commit

Not part of this feature's own logic -- pre-existing gaps left by earlier commits today
(`15543f2`, the 8-vault addition) whose own test suites were not fully run before pushing, the same
category of issue already found once today (commit `5c7a425`) and now found to be incomplete:

- `scripts/lib/tests/test_base_scorer_bodies.py`: Compound V3 Base's `PUBLISHED_READBACK` row still
  had the pre-`d6dca5e` timelockScore (65, composite 80) -- a THIRD fixture file with this same
  stale value, missed by `5c7a425`'s earlier pass on the other two. Fixed via a
  `TIMELOCK_COMPOSITE_SINCE_PUBLISHED` override, same pattern as the existing
  `CROSS_EXPOSURE_SINCE_PUBLISHED` -- `PUBLISHED_READBACK` itself stays pinned verbatim to the
  committed 2026-09-19 CSV (`TestFixtureProvenance` checks this byte for byte; an earlier attempt at
  this fix edited the row in place and broke that check, caught by re-running the suite before
  committing).
- Same file: the 4 new Morpho vault scorers issued reads `ReaderFake`'s strict mode had not been
  told to expect, failing every test in `TestScoreAllPublishedReadback` at cleanup. Wired via a new
  `wire_morpho_vaults()` helper and a separate `MORPHO_VAULTS_READBACK` list (not folded into
  `PUBLISHED_READBACK`, for the same historical-CSV reason above).
- `scripts/lib/tests/test_aave_horizon_scorer.py::TestRegistry`: pinned Horizon at
  `SIMPLE_SCORERS[-2]` and a total count of 18 -- stale since the same 4-vault addition appended
  after Horizon and Convex. Fixed to `[-6]`/`[-5]` and count 22.

Full suite (6 test directories, 2344 tests) green after all three fixes.
