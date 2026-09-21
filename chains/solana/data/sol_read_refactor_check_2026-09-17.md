# sol_read.py refactor check (2026-09-17)

`scripts/sol_read.py` originally ran `main()` unconditionally at module
scope (no `if __name__ == "__main__":` guard), so nothing else in this
project could `import sol_read` without it immediately crashing on
`sys.argv`. Every decoder also lived inline in `main()`'s if/elif chain,
duplicating the byte layouts if any other file needed the same reads.

Refactored into one function per account type (`read_program`,
`read_squadsv3`, `read_squads`, `read_klend_market`, etc.), same byte
offsets, same decode order, `main()` now just dispatches to them and
prints. No logic changed.

## Live re-verification after the refactor

Ran the refactored CLI against Solana Mainnet Beta for every target used in
[`../data/methodology_test_2026-09-16.md`](../data/methodology_test_2026-09-16.md)
and compared to that file's already-recorded values:

| Command | Field | Methodology test value | Refactored CLI output | Match |
|---|---|---|---|---|
| `program ... JUP6Lk...TaV4` | `upgrade_authority` | `CvQZZ23q...tipQ` | `CvQZZ23qYDWF2RUpxYJ8y9K4skmuvYEEjH7fK58jtipQ` | yes |
| `squadsv3 ... 7ZyD...k8Sf 1` | `threshold` / `n_keys` / `authority_1` | 4 / 7 / `CvQZZ23q...tipQ` | 4 / 7 / `CvQZZ23qYDWF2RUpxYJ8y9K4skmuvYEEjH7fK58jtipQ` | yes |
| `keytype ... CvQZZ23q...tipQ` | `on_curve` / `owner` | `false` / System (PDA) | `false` / `11111111111111111111111111111111` | yes |
| `program ... KLend2g3...boSyAYavgmjD` | `upgrade_authority` | `GzFg...kzkW` | `GzFgdRJXmawPhGeBsyRCDLx4jAKPsvbUqoqitzppkzkW` | yes |
| `squads-vault - 6hhB...fQbM 0` | derived vault | `GzFg...kzkW` (exact match required) | `GzFgdRJXmawPhGeBsyRCDLx4jAKPsvbUqoqitzppkzkW` | yes |
| `klend-market ... 7u3H...5PfF` | `name` / `lending_market_owner` / `emergency_council` / `proposer_authority` / `global_admin` | `SOL/BTC Market` / `24Lj...ZMMT` / `4VtJ...Ma57` / `6pwk...cEUv` / `A9rQ...exCZ` | identical (full values in claims) | yes |
| `squads ... 6hhB...fQbM` | `threshold` / `members` / `time_lock_s` / `config_authority` | 5-of-10 / 86400 / default | 5 / 10 / 86400 / `11111...111` (default) | yes |

Every value matches exactly. The refactor is behavior-preserving; nothing
about the underlying reads or formulas changed, only how the code is
organized for reuse by `chains/solana/scorers.py`.
