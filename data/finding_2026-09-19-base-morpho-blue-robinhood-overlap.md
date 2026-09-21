# Finding (2026-09-19): Base's Morpho Blue and Robinhood Chain's Morpho Blue share the identical governance committee -- found by sweeping already-established ecosystems, no new chain involved

Direct follow-up to the standing directive to improve depth on ecosystems
already in scope (see [[feedback_oracle_depth_over_breadth]] and
[[feedback_ecosystem_addition_5point_discovery_gate]] in this pass's own
memory) and to the disclosed "worth a systematic sweep in a future depth
pass" line in
[`data/finding_2026-09-19-monad-cross-ecosystem-overlap.md`](finding_2026-09-19-monad-cross-ecosystem-overlap.md).
This finding involves **zero new ecosystems** -- Base was deployed
2026-09-18, Robinhood Chain is this project's original flagship. The only
thing that changed is actually reading the output
`scripts/check_cross_ecosystem_overlap.py` had already been producing for
days, rather than only skimming it for Monad-related rows.

## The finding

`chains/base-ecosystem/scorers.py::score_morpho_blue()`'s target -- Base's
Morpho Blue singleton, **the largest single target this entire project
tracks** ($3.90B TVL per its own docstring) -- has `owner()` resolving to
a real 5-of-9 Gnosis Safe (`0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa`).

`scripts/lib/signer_overlap.py`'s `GROUPS["morpho_blue"]` (Robinhood
Chain) tracks a DIFFERENT Safe address
(`0x060595638692de6CCd47ca04094F1772D3D39728`) for the same protocol.

Live-fetched `getOwners()`/`getThreshold()` against both chains, same
session: **the two Safes' owner sets are IDENTICAL as sets, at the
identical 5-of-9 threshold.** Not an overlap, not a subset -- the exact
same 9 individuals, on two of this project's tracked chains, at two
different (CREATE2-per-chain-deployed) addresses.

```
0x13cA8756E9470b71B8e998352c8741706217f963  0x264c86DBbD2E4165FbBf0C35b0ddf0e00AEc6b31
0x30E7c016fC702cDe9A50720a469d418490b7b652  0x69FcEFDe2B48503d675181448B3D4272128bca9c
0x84D3E4EE550DD5F99e76a548aC59a6BE1C8dCf79  0x8f02b4a44Eacd9b8eE7739aa0BA58833DD45d002
0xC100c251bdD297A66795112f04356E6BA5f89D80  0xCF263cEe139763114fAaFC5F52865135412F50Ec
0xe0aeb6811d33Df42A09066857CDaFca16b506086
```

Before this pass, both chains' `crossExposureScore` for this target read
100 ("no overlap found") -- factually wrong, not just unconfirmed, since
this specific comparison had never actually been run despite both sides
already being tracked for days.

## How this was actually found (methodology note)

Not a targeted hypothesis ("let's check if Morpho overlaps"). This came
out of `scripts/check_cross_ecosystem_overlap.py`'s full, generic output,
run originally to wire Monad in -- the SAME run also re-derives every
OTHER already-wired group (Robinhood's ~31 groups, Ethereum L1's 3,
Arbitrum's 4, Base's 4, Tempo's 2, Plasma's 5). The Base/Robinhood
`morpho_blue` overlap was sitting in that output the entire time; it was
simply not followed up on until this pass deliberately re-read the full
output line by line rather than only the Monad-related rows. This is
exactly the "scope before building, let the discovery justify the work"
process from [[feedback_ecosystem_addition_5point_discovery_gate]] --
applied retroactively to output that already existed, at zero additional
research cost.

## Is this actually surprising?

Partially expected, still worth scoring: Morpho Blue's singleton is
commonly owned by Morpho Association's own global protocol-governance
Safe, redeployed with a consistent signer set per chain by design -- a
professional protocol operator's legitimate pattern, not a mistake.
But "expected once you know Morpho's governance model" and "currently
scored as if it doesn't exist" are two different things, and this
project's own stated purpose is making exactly this kind of concentration
fact visible to someone who does NOT already know Morpho's internal
governance structure. $3.90B (Base) and whatever TVL Robinhood Chain's
own deployment secures are both, in practice, gated by the same 9 people.

## Action taken

- `chains/base-ecosystem/scorers.py::score_morpho_blue()` now computes
  `crossExposureScore` live against a hardcoded snapshot of Robinhood
  Chain's own Morpho Blue owner set (same idiom already used for this
  file's own `score_aave_v3_base()`, added 2026-09-17 for the
  Arbitrum-shared Aave guardian finding).
- 2 new tests (`scripts/lib/tests/test_base_ecosystem_scorers.py`), full
  suite 524/524 passing.
- **Re-pushed for real** to Base's already-deployed Sepolia oracle
  (`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`, chain 84532) -- tx
  `0x7b7ed211e327dcc7940aea129398a96e36d157066185fe24709c395cda392e62`,
  confirmed block 47,028,948. `getScore()` read back live:
  `crossExposureScore=80`, `compositeScore=55`, matching exactly what was
  sent. Base Sepolia's own gas price (~0.006 gwei) made this trivial
  compared to Monad's ~100 gwei -- no funding blocker here.
- Fixed the module-level `_CROSS_EXPOSURE_NOTE` comment in
  `chains/base-ecosystem/scorers.py`, which had gone stale (claimed no
  cross-ecosystem dataset existed at all for Base, no longer true since
  2026-09-17's Aave finding, let alone this one).

## What this does NOT do

- Robinhood Chain's own `morpho_blue` group/scorer was NOT modified --
  `scripts/lib/scorers.py` is the pipeline's own heavily and continuously
  edited file (weekly auto-push cron); this finding is the flag for that
  side to pick up in its own pass, same asymmetric-update boundary
  already used for the Monad/Robinhood Curve finding.
- **UPDATE 2026-09-20 (the first bullet above is now closed in code):** Robinhood Chain's Morpho Blue
  singleton group in `scripts/lib/signer_overlap.py` carries a hand-set, dated `cross_ecosystem` flag and
  scores `crossExposureScore` 80 (was 100); Ethereum L1's Morpho Blue and Tempo's Morpho Blue core fold
  the same 9-signer committee at 80 too. All three are on-chain since the 2026-09-20 re-push (Robinhood
  Chain tx `0x020cf83c8a007afaef0eadf7ecb271432c80f1ffd9bfafed984ab6eca17c4978`, block 121,858,777;
  Ethereum L1 tx `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`, block 11,740,952;
  Tempo tx `0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b`, block 36,054,236).
  See `data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`, section 9.
- The rest of `scripts/check_cross_ecosystem_overlap.py`'s output was
  NOT re-audited line-by-line this pass beyond this one row -- the
  already-known findings (Plasma/Robinhood Pendle, Ethereum L1/Plasma
  Ethena, Arbitrum/Base/Plasma Aave guardian) were spot-checked as
  "already documented" and not re-verified from scratch.

## Follow-up, same day: the genuinely complete sweep

The "worth a systematic sweep" gap above was closed immediately after:
added `find_subset_committees()` (does one group's signer set fully
contain another's, across every pair of groups from different
ecosystems -- the exact check that would have caught this Morpho Blue
finding automatically instead of requiring someone to notice it) plus an
identical-bare-EOA check (the same `find_identical_safe_addresses()`
logic, now also applied to `known_eoa` entries, not just `safes` -- the
exact gap that meant the Curve/Monad-Robinhood finding wasn't
tool-flagged either) to `scripts/lib/cross_ecosystem_overlap.py` and
`scripts/check_cross_ecosystem_overlap.py`.

Ran across all 56 groups in all 7 ecosystems. Full containment output:

```
plasma:pendle (5 signers) fully contained in robinhood:pendle
monad:morpho_vault_curator (6 signers) fully contained in robinhood:steakhouse [+3 more]
monad:morpho_vault_owner (8 signers) fully contained in robinhood:ethena_steakhouse [+2 more]
robinhood:morpho_blue (9 signers) fully contained in base:morpho_blue
arbitrum:aave_guardian (9 signers) fully contained in base:aave_guardian [+1 more]
base:aave_guardian (9 signers) fully contained in plasma:aave_guardian
ethereum-l1:ethena (10 signers) fully contained in plasma:ethena
```

Every single row is one of the findings already fixed this pass
(this one, or the two Monad ones) or an already-documented, already-
scored pre-existing finding (Pendle, the Aave guardian committee, the
Ethena committee) -- confirmed by re-checking each one's own scorer
docstring for a matching disclosure. **No additional, previously-unknown
finding came out of the complete sweep.** That's a real result, not a
null one: it means this project's cross-ecosystem signer-overlap
coverage is now internally consistent across everything currently
tracked, not just the two spots that happened to get manual attention
this pass. 19 new tests cover the two new functions
(`scripts/lib/tests/test_cross_ecosystem_overlap.py`).
