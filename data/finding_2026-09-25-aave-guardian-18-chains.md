# One 7-signer committee holds Aave V3's emergency-pause seat on 18 of ~19 real deployments

2026-09-25. Roadmap item 9 ("voit large" round 2), continued after "continue". This project already
tracked, on 5 chains it monitors (Ethereum L1, Arbitrum, Base, Plasma, Monad), that the SAME 7 signers
hold Aave's `PROTOCOL_GUARDIAN`/`EMERGENCY_ADMIN` seat -- a different Safe address per chain, folded
into `crossExposureScore` as a flat 80 since 2026-09-20. The open question the backlog item asked:
does the SAME committee also control this seat on the ~18 Aave V3 deployments this oracle does not
track at all.

## Result: yes, on 13 more chains, live-verified, not assumed

**18 of 19 real (non-testnet) Aave V3 deployments checked share the exact same 7-signer, 4-of-7
committee.** Beyond the 5 already tracked: Avalanche, Optimism, Polygon, BNB, Celo, Gnosis, Linea,
Mantle, Metis, Scroll, Sonic, XLayer, Soneium.

The addresses came from Aave DAO's own published registry (`bgd-labs/aave-address-book`,
`src/Misc<Chain>.sol`, `PROTOCOL_GUARDIAN` constant) -- but the address alone was never trusted as
proof. Several of the 13 chains share the LITERAL SAME Safe address as each other (CREATE2
determinism): `0x56C1a4b5...` on Base/Avalanche/Optimism/Metis, `0xCb45E824...` on
Arbitrum/Polygon/BNB/Gnosis/Scroll, `0xEf323B19...` on Plasma/Soneium. Given this pass's own
earlier finding today (`data/finding_2026-09-25-controller-concentration.md`: the Steakhouse Safe
carries a DIFFERENT owner set on each of Ethereum L1/Base/Monad despite an identical CREATE2
address), an address match was never enough -- **every chain's owner set was read live from that
chain's own RPC** (`chains/ethereum-l1/scripts/check_aave_guardian_cross_chain.py`) before being
compared to the known 7.

## The one exception, disclosed not guessed

**zkSync's PROTOCOL_GUARDIAN address (`0xba845c27...`) has real bytecode (2,080 bytes) but does not
resolve as a standard Gnosis Safe** -- `getOwners()`/`getThreshold()` both fail. A different
multisig implementation (zkSync's native account abstraction differs from standard Safe bytecode is
one plausible reason, not independently confirmed) -- not opened this pass, reported as unread/
unresolved rather than silently skipped or forced into the pattern.

**Fantom and Harmony have no `PROTOCOL_GUARDIAN` entry at all** in their `Misc*.sol` files -- checked,
not found, plausibly frozen or deprecated markets, not investigated further.

## Why this matters

Aave's own "Risk Steward" design docs (read during today's earlier RISK_ADMIN research,
`data/finding_2026-09-25-aave-v3-pool-risk-admin-discovery.md`) describe emergency powers as
"bounded, revocable... governance-owned". The breadth found here is a different, structural point:
**the emergency-pause capability across virtually Aave's ENTIRE V3 multi-chain footprint (18 of 19
real deployments) sits with one small, unchanging group of 7 individuals, 4 of whom can act.**
Not a claim that this group has done anything wrong, or that 4-of-7 is an unreasonable threshold for
an emergency seat -- a structural fact about concentration, the same "genuine breadth, not decorative"
finding this pass has aimed at all day. None of the 5 competitors researched earlier today
(LlamaRisk, Chaos Labs, Gauntlet, Hypernative, Blockaid) publishes a comparable cross-chain
committee-identity map for any protocol.

## What this changes and doesn't

`crossExposureScore` is unchanged on every already-tracked target (the fold convention applies to
this oracle's OWN tracked targets sharing a root; these 13 new chains are not tracked targets, so
there is nothing to fold them into). The finding is disclosed in the definitional comment
(`chains/ethereum-l1/scorers.py::_KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20`) and
`chains/monad/scorers.py`'s own local copy, strengthening the CONTEXT of the already-published 80-cap
finding on the 5 tracked chains, not changing any number. No new ecosystem added, no new target
tracked, no on-chain push.

## Verification

`python3 chains/ethereum-l1/scripts/check_aave_guardian_cross_chain.py` -- read-only, `getOwners()`/
`getThreshold()` only on 14 chains, no key, no transaction. Re-derivable end to end; re-run after a
committee rotation. Full test suite (6 directories, 2367 tests) green, unaffected (this is a
disclosure-only research script, not wired into any `score_all()`).
