# Nested-signers multisig formula: investigated, no live bug found, not applied

2026-09-25. Roadmap item 3 ("voit large" round 2), one of the two items deliberately held back
pending Spap's explicit go (given 2026-09-25, "Oui tu as le feu vert continue"). The earlier
competitor-research synthesis described this as a near-mechanical fix: "`scripts/lib/
nested_signers.py` (`min_eoa_keys`) exists already, resulting `multisigScore` for 27 of 405 tracked
signers is not corrected for a nested Safe being counted as one signer... surestime la dispersion
[backlog note]" Investigated
in full before writing any code -- it is not a mechanical fix, and applying it as described would
have inflated scores based on a debatable reading of what "dispersion" should mean, not corrected a
bug.

## What was checked

`python3 scripts/check_nested_signers.py`, all 20 real-world Safe-with-nested-owner cases across 7
ecosystems, `min_eoa_keys` (the tree's own true minimum EOA-key count to reach quorum) compared
against each Safe's raw `threshold` (what the CURRENT formula actually uses).

## Result: `min_eoa_keys` equals the raw threshold in every case that is actually scored

19 of 20 cases: identical. The Aave PROTOCOL_GUARDIAN case the synthesis cited by name (present on
5 chains: Arbitrum, Base, Ethereum L1 x2, Monad, Plasma) is a real example --
**4-of-7 outer Safe, 3 of the 7 seats are nested 1-of-3 Safes, 13 distinct EOAs can contribute in
total, but `min_eoa_keys` is still exactly 4.** Verified live: 13 truly distinct leaf addresses, no
overlap between the three nested Safes. The reason the required-key count doesn't change: every one
of the 3 nested Safes is itself only 1-of-3, so filling that ONE outer seat costs exactly 1 key --
identical to a bare EOA seat. Treating it as "1 owner" (what the current formula already does) is
not a bug; it is the correct cost for that seat.

**The one real exception, `monad/euler_security_council` (2-of-3 outer, `min_eoa_keys` = 4 because
all 3 seats are themselves nested Safes with no cheap bare-EOA seat available) -- is NOT used to
score anything.** Read `chains/monad/scorers.py::score_euler_finance_factory_monad`: the scored
root is a SEPARATE Safe, `dao_safe` (0xdA3da5c8..., a plain 4-of-8 with no nested owners).
`sec_council` is read and disclosed in `notes` only ("its real function (if any) on this deployment
is an open point, not assumed either way") -- the docstring itself already says this. Zero live
scores are affected by this mismatch today.

## Why "unify the formula" is not the mechanical fix it looked like

The synthesis's framing ("counting a nested Safe as one signer overestimates real dispersion")
implicitly assumes the fix is to credit the OUTER Safe's `multisigScore` dispersion term
(`max(0, owners-threshold)*5`) using the TRUE distinct leaf-EOA count (13 for the Aave case) instead
of the raw immediate-owner count (7). Working through what that would actually mean: it does NOT
correct an overestimate -- it would INCREASE the dispersion bonus (7->13 raises `max(0,owners-
threshold)*5` from 15 to 45 for the Aave case, pushing several already-published `multisigScore`
values toward the 100 cap). And it is not clearly justified: having 3 candidate keys behind one
outer seat is not the same kind of redundancy as 3 independently-required signatures -- an attacker
only needs to compromise ONE of the 3 to fill that seat, so "13 possible contributors" is arguably
closer to more attack surface on that seat than to genuine added collusion-resistance. Crediting it
as if it were straightforward dispersion would be inventing a new, debatable piece of methodology,
not fixing a bug -- exactly the kind of thing this project's own discipline treats as a real
calibration decision, not something to apply unilaterally even with a general go-ahead to keep
building.

## Conclusion

No code changed. No score is wrong today because of this pattern -- verified across every real case
in the current registry, not assumed. If Spap wants a genuine "sub-committee dispersion" formula
(crediting a nested Safe's own redundancy in some principled way, distinct from simply summing leaf
keys), that is a new calibration choice worth a dedicated discussion, not a silent formula change.
`scripts/lib/nested_signers.py` and `scripts/check_nested_signers.py` remain exactly as they were --
correct, tested, and already doing their real job (cross-ecosystem overlap detection, where
`leaf_keys()` is the right tool and is already used).
