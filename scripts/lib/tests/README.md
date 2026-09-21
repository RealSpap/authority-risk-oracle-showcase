# Tests for scripts/lib/

Unit tests for the pure/mockable logic in `scripts/lib/` -- the part of this
project's codebase that had zero automated coverage before 2026-09-17, which
is exactly where the 11 findings fixed in commit `4afe9d4` came from (a
silently-swallowed RPC failure producing the same confident score as a real
success, a stale inline comment, an unguarded batch call). These tests don't
replace the project's existing `--dry-run` scripts (`scripts/update_scores.py
--dry-run`, `chains/*/scripts/dry_run.py`) -- those are still the only way to
verify a scorer is actually reading the right on-chain state. What's covered
here is the surrounding logic those scripts depend on but never individually
exercise: composite-score rounding, retry control flow, alert thresholds,
the Arbitrum bridge-alias arithmetic, and per-target failure isolation.

## Run

```bash
pip install -r scripts/requirements.txt
python3 -m unittest discover -s scripts/lib/tests -v
```

No live RPC, no network, no `--dry-run` credentials needed -- every test
here runs against mocked/synthetic inputs and finishes in milliseconds.

## What a mock test can and cannot show

Since 2026-09-20 most individual scorer functions (`score_uniswap_v3_factory`, `score_aave_v3_pool`, ...) have unit
tests that run their real bodies with the chain reads patched (`test_<ecosystem>_scorers.py`, and the
`test_*_scorer_bodies.py` files). Their fixtures come from documented real observations or from hand arithmetic on the
written formula, never from the function's own output, and each file was checked by mutation: a copy of the scorer is
sabotaged and the tests must notice. Known bugs and open questions are pinned with `unittest.expectedFailure`, so
fixing one turns its test into an unexpected success that must be looked at.

What such a test cannot show is whether the interpretation of a protocol's live on-chain state is right: a mock
returns whatever it was told to. For that the project's existing discipline stays the actual verification method
(live re-derivation, cross-checked on a second RPC for high-severity claims, `--dry-run` compared against the
already-published on-chain score); see `METHODOLOGY.md` at the repo root. Coverage of the scorers is measured with
`coverage` (not a project dependency): `python3 -m coverage run --source=chains,scripts --omit='*/tests/*' -m unittest
discover -s scripts/lib/tests -t .`.
