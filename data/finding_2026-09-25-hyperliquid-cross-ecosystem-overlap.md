# Hyperliquid added to the cross-ecosystem signer-overlap registry

2026-09-25. Roadmap item 5 ("voit large" round 2): `scripts/lib/cross_ecosystem_overlap.py`'s
GROUPS-based registry (used by `check_cross_ecosystem_overlap.py`, `check_safe_modules_guards.py`
and `check_nested_signers.py`) covered Robinhood Chain, Ethereum L1, Arbitrum, Base, Tempo, Plasma
and Monad -- 7 ecosystems -- but never Hyperliquid. README.md already claims this exact capability
("no cross-protocol signer-overlap detection") as a differentiator over SolGov; this closes the gap
for real, internally, rather than leaving it true on paper for 7 of 10 tracked ecosystems.

## A wrong premise caught before building anything

An earlier internal research pass (today's competitor-gap workflow) claimed Hyperliquid needed a
"key-format normalization bridge" alongside Solana and Zcash before this could be extended -- grouped
as if all three were equally out of reach. Checked live before trusting it: **Hyperliquid is a
standard EVM chain (HyperEVM)**, the same 0x/Gnosis-Safe address space every other covered ecosystem
already uses. There was no format barrier -- the registry had simply never been built for it. Solana
(base58 pubkeys) and Zcash (shielded/transparent, non-EVM) remain genuinely out of scope; conflating
Hyperliquid with them would have left a real, closeable gap undone on a false premise.

## Scope: only the 4 real Gnosis Safes

Most Hyperliquid targets are HyperCore-native (`userToMultiSigSigners`, a different on-chain
multisig concept entirely, not readable via `safe_owners_and_threshold()`). Only 4 tracked targets
are rooted in an actual HyperEVM Gnosis Safe -- every address below is the live root-role holder
(`DEFAULT_ADMIN_ROLE` or `RoleRegistry.owner()`), read via
`chains/hyperliquid/scripts/methodology_test.py`'s own scorer functions, not guessed from a
docstring:

| Group | Root Safe | Shape |
|---|---|---|
| Kinetiq staking (kHYPE + kmHYPE) | `0x18a82C968B992D28D4D812920Eb7B4305306f8F1` | 4-of-8 |
| para StakingVault | `0x8D23a255656f4C8E26D1010e0Aa2B6D20885Ca91` | 1-of-1 (a Safe, not a bare EOA) |
| Ventuals vHYPE staking | `0x72298a4cB6E571241331172FD90149D38fEAfE08` | 2-of-3 |
| stHYPE liquid staking | `0x97Dee0eA4CA10560F260a0f6F45BDC128A1d51F9` | 4-of-6 |

Kinetiq's own kHYPE/kmHYPE overlap (they share the SAME Safe) was already folded into
`crossExposureScore` by `chains/hyperliquid/scorers.py::_apply_hyperevm_shared_root_exposure`
(2026-09-21) -- that is an INTRA-Hyperliquid check. This registry answers the separate CROSS-
ecosystem question: does any of these 4 Safes' signers also appear on Robinhood Chain, Ethereum L1,
Arbitrum, Base, Tempo, Plasma or Monad.

## Result: checked, no overlap

Verified twice, independently: (1) a standalone comparison of all 21 unique signer addresses across
the 4 Safes against 342 known signer/EOA addresses collected live from the other 7 ecosystems'
registries -- zero matches; (2) the full `check_cross_ecosystem_overlap.py` sweep with Hyperliquid
wired in (`Resolved 99 groups across 8 ecosystems (..., hyperliquid: 4)`) -- no signer overlap,
identical-Safe-address match, or committee containment involving any Hyperliquid group. A real,
checked negative, not "never looked" -- the exact distinction this project's own discipline (and
`check_cross_ecosystem_overlap.py`'s own docstring) insists on.

`check_safe_modules_guards.py`: none of the 4 Safes carries a module or guard. `check_nested_signers.py`:
all 4 resolve cleanly, no unanalyzed nested signer, no unanalyzed module/guard/singleton anywhere in
the now-82-Safe registry.

## What this does not change

No `crossExposureScore` moves -- there was nothing to fold (the checked result is a real negative,
not an unconfirmed absence). No new scoring dimension, no new calibration. Purely a registry/tooling
extension: `HYPERLIQUID_GROUPS` in `scripts/lib/cross_ecosystem_overlap.py`, wired into the 3 tools
that already consumed the other 7 ecosystems' registries the same way. Full test suite (2206 tests)
green, unaffected.

## What remains out of scope

Solana and Zcash's genuinely incompatible key formats. Hyperliquid's own HyperCore-native root keys
(the majority of its tracked targets) -- a different, non-Safe multisig concept this registry's
mechanism cannot read; extending coverage to those would need a different comparison method, not
attempted this pass.
