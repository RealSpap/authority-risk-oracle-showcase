# Finding (2026-09-18): an `unresolved_note` group in `signer_overlap.py` is exempt from being SCORED on overlap, but not from COUNTING as another group's overlap

Surfaced while writing the first test coverage `scripts/lib/signer_overlap.py`
has ever had (`scripts/lib/tests/test_signer_overlap.py`, confirmed via grep
that zero tests referenced this module before this pass, despite it being
real, load-bearing code: `scripts/lib/scorers.py`'s `score_all()` calls
`compute_cross_exposure()` every run to derive the published
`crossExposureScore` for every Robinhood Chain target). Found by one agent
while designing a test fixture, independently re-traced and confirmed by a
separate adversarial-verify agent against the real source before this file
was written up. Not fixed here -- a change to this module's scoring
algorithm needs its own adversarial review before committing, per
`AGENTS.md`'s "Before committing" section; `scripts/lib/signer_overlap.py`
is unmodified by this finding.

## The gap

`compute_cross_exposure()` has two structurally separate loops:

1. **Registry-building loop** (builds `registry: signer -> set of group
   keys` and `group_all_signers: key -> set of signers`): iterates every
   group in `GROUPS` and computes its `signers` set from `known_eoa` +
   whatever `safes` resolve to. It runs **unconditionally** -- it never
   checks `g.get("unresolved_note")` before computing that group's
   signers and adding them to the shared `registry`.
2. **Scoring loop**: this is the *only* place `unresolved_note` is
   checked, and only to force that one group's own `crossExposureScore`
   to a flat 100. It never touches `registry` or removes that group's
   signers from it.

Net effect: a group marked `unresolved_note` (meaning "this group's own
authority structure has no resolvable signer set to compare, so don't
score IT on overlap") is correctly exempted from being scored on overlap
-- but its `known_eoa`/`safes` entries, if it happens to have any
alongside the note, still populate the shared `registry`. Any OTHER,
normally-scored group that shares one of those signers gets its own
`shared_groups` count -- and therefore its own `crossExposureScore` --
penalized because of a group whose own overlap was explicitly declared
not applicable.

**Live impact today: zero.** The two real `unresolved_note` entries in
the current `GROUPS` registry (`spark_savings`, `ekubo`) both have empty
`known_eoa: []` and `safes: []` -- there is nothing for them to leak.
This is a structural gap in the module, not a currently-wrong published
score.

## Reproduction

`scripts/lib/tests/test_signer_overlap.py`'s
`TestUnresolvedNoteRegistryLeak.test_noted_groups_known_eoa_still_inflates_another_groups_shared_count`
reproduces it directly against the real, unmodified
`compute_cross_exposure()`: a synthetic `"noted"` group (with a
`known_eoa` entry AND `unresolved_note` set) sharing one signer with a
synthetic `"victim"` group. Result: `"noted"` scores 100 (correctly
exempt), but `"victim"` scores 80 (100 - 20, penalized for the shared
signer) -- proving the leak is real and reproducible against the current
source, not a hypothetical.

## What this does NOT do

- Does not change any currently-published `crossExposureScore` -- the
  real registry's two `unresolved_note` entries have no signers to leak.
- Does not modify `scripts/lib/signer_overlap.py`. A fix (the most direct
  one: skip `unresolved_note` groups in the registry-building loop too,
  so they neither score NOR count toward anyone else's score) is a real,
  well-scoped follow-up, but is a scoring-logic change and needs this
  project's own adversarial-review discipline before committing, not a
  unilateral fix from a test-writing pass.
- Does not sweep the rest of `GROUPS` for any OTHER instance of this
  shape (an entry with both `unresolved_note` and non-empty
  `known_eoa`/`safes`) -- confirmed only that the two entries existing
  today don't trigger it.
