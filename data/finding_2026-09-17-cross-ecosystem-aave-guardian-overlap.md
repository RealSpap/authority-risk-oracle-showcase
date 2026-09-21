# Cross-ecosystem finding (2026-09-17): Aave V3's emergency guardian is the SAME 9-person committee on Arbitrum and Base

## What this closes

This project's own README (SolGov comparison, point 3) states its
differentiator against every existing risk tool -- including its own
closest precedent, SolGov -- is checking whether the *same* key sits behind
two protocols tracked as independent: "SolGov's columns are all
per-protocol; it never checks whether the same key sits behind two
protocols it lists as independent." Until today, this project's own
`crossExposureScore` had the identical limitation one level up: every
non-Robinhood-Chain ecosystem (Ethereum L1, Arbitrum, Base) published a
flat `crossExposureScore = 100` for every target, explicitly disclosed as
"not computed this pass -- no cross-ecosystem signer-overlap dataset exists
yet" (`scripts/lib/cross_ecosystem_overlap.py`'s own `_CROSS_EXPOSURE_NOTE`).
The infrastructure to check existed (`scripts/lib/cross_ecosystem_overlap.py`,
`scripts/check_cross_ecosystem_overlap.py`) but had never been extended to
Arbitrum (added as a scored ecosystem after this module was first written)
and had gone stale for Ethereum L1 (its own "ethena" group only listed 1 of
the 5 targets this project tracks under that Safe as of today) and Base
(missing a known local guardian Safe its own scorer already reads the
address of, just never resolved the owners of).

## What was found

Extending the module to include Arbitrum for the first time, updating
Ethereum L1's stale group, adding Base's missing guardian group, and
re-running the full live check (33 groups across 4 EVM ecosystems: 23
Robinhood Chain, 3 Ethereum L1, 4 Arbitrum, 3 Base) found exactly one real
cross-ecosystem overlap:

**Arbitrum's and Base's Aave V3 `GOVERNANCE_GUARDIAN` Safes -- the
committee that can cancel a governance payload outside the normal
timelock delay on each chain -- share the EXACT SAME 9 owner addresses, at
5-of-9 threshold, at two different Safe addresses:**

| Chain | Safe address | Threshold | Owners |
|---|---|---|---|
| Arbitrum | `0x1A0581dd5C7C3DA4Ba1CDa7e0BcA7286afc4973b` | 5-of-9 | `0xDA5Ae43e...`, `0x1e380435...`, `0x4f967430...`, `0xebED04E9...`, `0xbd4DCfA9...`, `0xA3103D0E...`, `0x936CD965...`, `0x0D2394C0...`, `0x4C30E337...` |
| Base | `0x360c0a69Ed2912351227a0b745f890CB2eBDbcFe` | 5-of-9 | (identical set, same order) |

Zero other overlaps were found anywhere else in the 33 groups checked --
not within Robinhood Chain's own 23 groups (already known, re-confirmed),
not between Robinhood Chain and any of the other 3 ecosystems, not between
Ethereum L1's expanded Ethena group (now correctly covering all 5
Safe-governed targets) and anything else, not among Arbitrum's other three
groups (GMX, Camelot, the Arbitrum Security Council itself), and critically
**not** between Ethereum L1's own Aave `PROTOCOL_GUARDIAN` Safe (4-of-7,
`0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30`) and the Arbitrum/Base
committee -- confirmed live to share zero signers, a genuinely separate,
older, mainnet-only governance body.

No identical Safe *address* was found across ecosystems (the
`find_identical_safe_addresses` check, distinct from and stronger than a
signer-overlap check) -- this is signer-level overlap at two different
addresses, the CREATE2-redeployed-with-same-owner-set pattern, not a
literal cross-chain address collision.

## Why this matters

This is exactly the pattern this project's own cited sister research,
`multisig-overlap`, documented for ether.fi, Curve, Aave V3 and
others: a protocol that looks diversified because it's deployed on two
"independent" chains is not diversified against key compromise at all if
the same human committee holds the emergency-override key on both. Found
here, for the first time, in this project's own live tracked targets --
not cited from that sister research, independently re-derived.

Concretely: a `GOVERNANCE_GUARDIAN` compromise (9 signers, 5 needed) does
not just let an attacker cancel a pending Arbitrum governance payload --
the same 5-of-9 compromise cancels a pending Base payload too. Two chains'
"defense in depth" against a malicious or stalled governance proposal
collapses to one shared point of failure.

## What changed in the code

- `scripts/lib/cross_ecosystem_overlap.py`: added `ARBITRUM_GROUPS` (new),
  expanded `ETHEREUM_L1_GROUPS`'s `ethena` entry from 1 to 5 targets, added
  `usdtb_bare_eoa` as its own group for completeness, added
  `BASE_GROUPS["aave_guardian"]` (previously missing entirely).
- `scripts/check_cross_ecosystem_overlap.py`: wired in Arbitrum.
- `chains/arbitrum-ecosystem/scorers.py`'s `score_aave_v3_pool_arbitrum()`
  and `chains/base-ecosystem/scorers.py`'s `score_aave_v3_base()`: each now
  live-resolves its OWN guardian Safe's owners (Base's scorer previously
  only read the guardian's address, never its owners) and compares that
  set against a DATED snapshot of the sibling chain's owner set. On a
  match, `crossExposureScore` is now **80** (matching this project's
  existing `max(0, 100 - 20 * count)` convention for one other sharing
  target) instead of the previous flat 100, with a note explaining why.
  This is a live, single-chain-RPC check on each side (no new cross-chain
  RPC coupling introduced into either scorer's own run -- the sibling's
  owner set is a same-day dated constant, matching this project's existing
  "dated fact, re-verify on demand, not live-coupled every run" convention
  already used elsewhere, e.g. Zcash's median notice period).

## What this does NOT do

- Does not re-verify this finding automatically on every push. If either
  Safe's owner set changes, the hardcoded reference constant in the OTHER
  chain's scorer goes stale until someone re-runs
  `scripts/check_cross_ecosystem_overlap.py` and updates it -- a real,
  disclosed limitation of the dated-snapshot approach, not silently assumed
  permanent.
- Does not extend this same check to Solana/Hyperliquid/Tempo/Zcash --
  their signer formats (base58 pubkeys, NEAR account IDs, P2SH pubkeys) are
  not directly comparable to EVM addresses or to each other without a
  format-specific bridge this pass didn't build. `cross_ecosystem_overlap.py`
  remains EVM-only.
- Does not check Robinhood Chain's own ~44 targets against this Aave
  guardian committee specifically beyond the existing full 33-group sweep
  (which found no overlap there either).

## Reproduction

```
python3 scripts/check_cross_ecosystem_overlap.py
```

## CORRECTION (2026-09-20): the L1 PROTOCOL_GUARDIAN committee is not "mainnet-only"

This document (and `scripts/lib/cross_ecosystem_overlap.py`) treated Ethereum L1's Aave
`PROTOCOL_GUARDIAN` (4-of-7, zero overlap with the 9-signer committee above, which is
still correct) as a mainnet-only body. Read live on all five chains, the Safe holding
`isEmergencyAdmin` on each Aave ACLManager (Ethereum L1, Arbitrum, Base, Plasma, Monad) is
a 4-of-7 Safe with the IDENTICAL 7 owners, at a different Safe address per chain. On Monad
the same Safe also holds `isPoolAdmin`. See
`data/finding_2026-09-20-unscored-role-sweep.md` section 1.

## UPDATE (2026-09-20): the convention is decided, and two statements above are stale

- **The score convention.** This document describes Arbitrum and Base folding the overlap into
  `crossExposureScore` (80). That is now the rule everywhere: a cross-ecosystem committee match is
  folded into `crossExposureScore` on every EVM ecosystem (a flat 80, `min(within-ecosystem
  score, 80)` where a within-ecosystem score exists, dated snapshot, no second-chain RPC).
  Ethereum L1's Aave Pool, which read 100 while this committee sat on four other chains, now reads
  80, and that value is on-chain: pushed 2026-09-20 (Ethereum L1 oracle, tx
  `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`, block 11,740,952, read back
  78/100/55/100/80/78). See `data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`,
  section 9.
- **"Remains EVM-only ... Tempo".** Tempo's signers are ordinary EVM Safe owners and Tempo has been
  in `cross_ecosystem_overlap.py` since 2026-09-18 (its two resolvable Safes), and its Morpho Blue core
  now folds at 80. What is still not covered is Solana, Hyperliquid and Zcash (and Tempo's non-Safe
  controllers).
- **The committee count.** The 9-signer committee is on five chains (Ethereum L1, Arbitrum, Base,
  Plasma, Monad), not two; see `data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`.
