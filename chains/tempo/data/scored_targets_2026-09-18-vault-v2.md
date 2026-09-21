# Tempo -- Morpho Vault V2 target type (rule R8), 3 targets scored, 2026-09-18

Closes `chains/tempo/data/scouted_targets_2026-09-17-run2.md` section 8's
open point 4 for Morpho Vault V2 ("Morpho Vault V2 and market oracles need
a written target type"). Unlike the same day's other R2 extension (4
controller shapes, `data/scored_targets_2026-09-18-controller-types.md`),
this is a genuinely NEW target type (rule R8, `METHODOLOGY.md` section
4.1) -- Vault V2's `owner`/`curator` were already resolvable by the
existing `classify()`/`weakest()` (rules R2/R3) without any change, since
both are plain addresses (a Safe or an EOA on every live target found so
far). What did not exist before this pass was: (a) the decision that the
root-control set for a vault is `{owner, curator}`, not just one of them,
and not the allocator/sentinel roles either; and (b) a delay dimension
based on Vault V2's own per-selector `timelock(bytes4)`/`abdicated(bytes4)`
mappings rather than a single `getMinDelay()`.

Reference implementation: `score_vault_v2()` / `_vault_v2_timelock()` /
`VAULT_V2_TARGETS` / `VAULT_V2_FUND_DESTINATION_SELECTORS`, all in
`chains/tempo/scripts/methodology_test.py`; wired into `score_all()` in
`chains/tempo/scorers.py`.

## Rule (METHODOLOGY.md section 4.1, R8)

- **Root-control set**: `{owner, curator}`. Both are public state-variable
  getters on `morpho-org/vault-v2` `src/VaultV2.sol` (confirmed against
  real source, tag matches the live bytecode's dispatcher for every
  selector used below). Allocators and sentinels are excluded from the
  NUMERIC set -- both are real but bounded, non-originating powers
  (confirmed against real source: `allocate`/`deallocate` can only move
  funds among adapters the curator has ALREADY approved, within caps the
  curator has ALREADY set; the sentinel role can only `revoke` a pending
  submission, decrease a cap, or `deallocate` -- never add a destination or
  raise a cap), the same convention R1 already applies to TIP-20's
  `UNPAUSE_ROLE` and `_classify_timelock` applies to
  `EXECUTOR_ROLE`/`CANCELLER_ROLE`.
- **Weakest key**: `weakest({classify(owner), classify(curator)})`, rule R3
  unchanged.
- **adminKeyScore / multisigScore**: R4/R5 unchanged, applied to that
  weakest key.
- **timelockScore (R5b, Vault-V2-specific)**: the minimum
  `timelock(bytes4)` over 5 "fund-destination" curator selectors --
  `addAdapter`, `removeAdapter`, `setAdapterRegistry`, `increaseAbsoluteCap`,
  `increaseRelativeCap` -- EXCLUDING any selector where `abdicated(bytes4)`
  is `true`. Confirmed against real source: `abdicate()` sets
  `abdicated[selector] = true` permanently, with no reverse function
  anywhere in the contract, so an abdicated selector is not merely delayed,
  it is permanently closed -- a STRONGER guarantee than any finite delay.
  Rather than invent a new score band, a fully-abdicated set is mapped to a
  7-day delay, i.e. R5b's own existing top band (`timelockScore = 80`),
  reusing the scale instead of adding a special case. Selectors are
  computed from the real function signatures (`selector("addAdapter(address)")`
  etc.), never hardcoded -- `selector("addAdapter(address)")` independently
  reproduces `0x60d54d41`, the exact value
  `scouted_targets_2026-09-17-run2.md`'s own verification command already
  used.
- **oracleAuthorityScore**: 100 (repo "not applicable" convention -- a
  vault reads no price itself; the market oracle it lends against, T5, is a
  separate, not-yet-wired target, see "Not yet promoted" below).

## Targets scored

| # | Target | Address | Owner | Curator | Weakest key | Fund-destination delay |
|---|---|---|---|---|---|---|
| T1 | Sentora pathUSD (Morpho Vault V2) | `0x9a044AE05E5e6290DcF56afd69548565e957a626` | Safe 1-of-1 `0xe8C9C99E...8008` (signer `0x295Df6B7...7E9`) | Safe 1-of-1 `0x9e396dE3...ac0` (signer `0x992592e0...ABE`) | (1,1) | 259,200 s (3 d) |
| T2 | Unnamed pathUSD Vault V2 feeding Sentora | `0x83a1491f3e7f8dAAB8F787a631334b9ca7a87023` | plain EOA `0x445F7a27...8Dc9` | same EOA (owner = curator) | (1,1) | 0 s |
| T3 | Tempo Earn (Morpho Vault V2, Gauntlet-curated) | `0xC609656Ed9ef219c98C8e549bF729144F211f06E` | Safe 4-of-7 `0x5a4E1984...D0` | Safe 3-of-7 `0x9E33faAE...585` (same 7 signers as owner) | (3,7), via curator | 259,200 s (3 d) |

All addresses, thresholds, owner sets and per-selector
`timelock`/`abdicated` reads above were read live against
`https://rpc.tempo.xyz` on 2026-09-18 (both via `cast call` and via this
project's own `call2()` dual-endpoint cross-check inside
`score_vault_v2()`), and match
`scouted_targets_2026-09-17-run2.md` section 3/5's own live tables exactly
(same owner/curator addresses and thresholds, same per-selector
delay/abdicated values for every one of the 5 selectors on all 3 vaults).

## Per-selector reads (live, both endpoints agree)

| Selector | T1 | T2 | T3 |
|---|---|---|---|
| `addAdapter` | 259200, not abdicated | abdicated | 604800, not abdicated |
| `removeAdapter` | 604800, not abdicated | abdicated | 604800, not abdicated |
| `setAdapterRegistry` | abdicated | 0, not abdicated | abdicated |
| `increaseAbsoluteCap` | 259200, not abdicated | 0, not abdicated | 259200, not abdicated |
| `increaseRelativeCap` | 259200, not abdicated | 0, not abdicated | 259200, not abdicated |
| **Minimum over non-abdicated** | **259200** | **0** | **259200** |

## Scores

| Target | adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | compositeScore |
|---|---|---|---|---|---|
| T1 Sentora pathUSD | 10 | 15 | 60 | 100 | **27** |
| T2 unnamed feeder vault | 10 | 15 | 0 | 100 | **9** |
| T3 Tempo Earn | 65 | 56 | 60 | 100 | **61** |

**Cross-check, not a coincidence**: T1 and T3 independently reproduce
`scouted_targets_2026-09-17-run2.md` section 4's own "resolved reading
(proposal)" column EXACTLY -- "T1 curator 1-of-1 + 3 days = 10 / 15 / 60 /
27" and "T3 curator 3-of-7 + 3 days = 65 / 56 / 60 / 61" -- even though
that column's numbers were hand-derived by a DIFFERENT research pass and
this pass's `score_vault_v2()` re-derives them independently from a live
`classify()` call, not by copying the target row. T2 has no example in
that column to compare against (the proposal table only worked through T1
and T3); its 10/15/0/9 is this pass's own first reading, disclosed as such
rather than presented as a reproduction.

crossExposureScore for these 3 targets is computed the same way as every
other Tempo target once they run inside the same `score_all()` batch as
the chain baseline and the 9 TIP-20s (rule R6, shared-root-signer count
across the WHOLE tracked set) -- not reproduced here as a standalone
number, since it depends on the other 10 targets' signer sets too.

## Not yet promoted / disclosed limitations

- Only T1-T3 (the 3 Morpho Vault V2 instances) are wired into
  `score_all()` by this pass. T4 (Morpho Blue core, owner-only
  fee/IRM-allowlist authority, a DIFFERENT shape with no curator/timelock
  concept at all) and T5 (the cbBTC/pathUSD market's RedStone oracle feeds,
  a plain EIP-1967 proxy-admin shape already resolvable by unmodified R2,
  not R8) are still open, exactly as `deploy/README.md`'s own "Not yet
  promoted" section already disclosed before this pass -- not silently
  folded into this rule.
- The allocator and sentinel addresses on T1/T2/T3 are not individually
  enumerated or scored here (no getter list; would need a
  `SetIsAllocator`/`SetIsSentinel` event-log replay analogous to
  `_role_members_via_logs`). Their power is bounded (see the rule
  statement above) but their identity is not recorded in `notes` this
  pass -- a real, disclosed gap, not a silent one.
