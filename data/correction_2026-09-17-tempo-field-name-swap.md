# Correction (2026-09-17): Tempo's scorer used the opposite target/label field convention

## What was found

Building [`scripts/validate_all_scorers.py`](../scripts/validate_all_scorers.py)
(a new cross-ecosystem schema check, added the same day after two other real
bugs -- see `data/correction_2026-09-17-missing-crossexposure-field.md` --
were only caught by manual audit) and running it against every ecosystem
found that `chains/tempo/scorers.py`'s `score_all()` returned entries shaped
the OPPOSITE way from every other ecosystem in this project:

| Field | Every other ecosystem | Tempo (before this fix) |
|---|---|---|
| `target` | the on-chain address | the human-readable name (e.g. `"USDC.e"`) |
| `label` | the human-readable name | not present at all -- `"address"` held the real address instead |

This came from `chains/tempo/scripts/methodology_test.py`'s own return shape
(`{"target": "USDC.e", "address": "0x20C0...", ...}`), which predates today's
`scorers.py` wrapper and is documented and reproduced exactly that way in
`data/methodology_test_2026-09-16.md` -- not itself wrong, just a different
naming choice than the rest of this project's `target`=address convention.
Nothing caught the mismatch when `scorers.py` was written earlier today
because every manual dry-run print statement happened to read `r['target']`
and get a plausible-looking string either way (a label text is still a
string a human reads without noticing it isn't an address).

**Real consequence had this shipped**: any downstream consumer expecting
`target` to be an address (an on-chain `updateScores()` tuple, `api/scores.json`,
this project's own cross-ecosystem signer-overlap tooling) would have
received `"USDC.e"` where an address was expected.

## Fix

Added `_normalize_field_names()` to `chains/tempo/scorers.py`, applied at the
end of `score_all()` -- swaps `target`/`address` into `label`/`target` to
match the project-wide convention. `methodology_test.py` itself was left
unchanged (its own shape is already documented and reproduced in
`data/methodology_test_2026-09-16.md`; changing it would break that
document's own reproduction commands for no benefit -- the adapter layer is
exactly where this kind of translation belongs).

## A second, independent bug the same validator caught: module-name collisions

The validator's first working version imported every ecosystem's `scorers.py`
in-process. Several ecosystems' scorer files import a same-named sibling
module via a bare `import` relying on a `sys.path` insert -- Hyperliquid's
`scorers.py` does `from methodology_test import ...` and Tempo's does
`import methodology_test as mt`, pointing at two ENTIRELY DIFFERENT files
(`chains/hyperliquid/scripts/methodology_test.py` vs.
`chains/tempo/scripts/methodology_test.py`). Loading both into the same
Python process means the second one silently reuses the FIRST one's already-
cached module under that bare name.

This produced a real false "PASS" on the validator's own first real run:
Tempo's `score_all()` silently returned zero entries (its own
`except Exception` caught the resulting `AttributeError` and printed a
warning, not a crash), and the validator initially reported this as a clean
ecosystem with nothing to check -- exactly the kind of masked failure this
tool exists to prevent, produced by the tool itself before it was fixed.

Fixed by moving the validator to subprocess isolation: each ecosystem now
runs `score_all()` in its own fresh Python process (no shared `sys.modules`
cache possible), communicating results back as JSON over stdout.

## Verification

After both fixes, the validator was re-run against all 8 ecosystems:

- 7 EVM/non-EVM ecosystems (Ethereum L1, Arbitrum, Base, Solana, Hyperliquid,
  Tempo, Zcash) -- 29 targets total, zero schema problems.
- Robinhood Chain (42+ targets, a known ~600s run) -- see the commit for the
  final result once its longer validation completes.

65/65 existing unit tests remained green throughout (this fix only changed
Tempo's own field names and added a new standalone validator script, no
existing scoring logic changed).
