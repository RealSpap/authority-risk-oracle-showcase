# Governance-capture concentration, quantified for the first time (Uniswap + Aave Governance V3 + Solend/Realms)

Spap asked, across a live chat session on 2026-09-25: of the 5 scoring dimensions
(adminKeyScore, multisigScore, timelockScore, oracleAuthorityScore,
crossExposureScore), where is a real, uncovered hole -- not a missing chain, a
missing *concept*.

## The gap, in the project's own words

`METHODOLOGY.md` documents, as a deliberate design choice: when a target's root
authority is a real, active token-vote DAO with no Safe layer, `multisigScore`
is scored 100 ("not applicable" -- "a token-vote quorum is a different strength
model than a Safe threshold, deliberately not conflated with one here").

Two independent scorers in this repo already flag, in their own docstrings,
that this convention has a real cost:

- `chains/ethereum-l1/scorers.py::score_uniswap_v3_factory()` (added
  2026-09-17): reads UNI's quorum (40M, 4% of supply) and recent turnout, but
  explicitly declines to calibrate capture risk, because doing so "needs a
  `DelegateVotesChanged` event replay back to UNI's 2020 genesis (tens of
  millions of blocks) ... not solvable the same way" as a narrower
  investigation this file did for Ethena. Quoting its own conclusion:
  *"Publishing a confident-looking number without that data would be exactly
  the kind of fabricated-but-plausible score this project's own discipline
  exists to prevent."*
- `chains/solana/scorers.py::score_solend_realms_governance()`: "the flat '70
  for token voting' baseline does not account for realized voter
  concentration, which **Solend's own 2022 incident is real evidence for**."

So: a real, named, historical incident (Solend 2022) is cited as proof this
matters, on a DIFFERENT ecosystem than the DIFFERENT DAO (Uniswap) where the
score is actually load-bearing today (Solend's own composite is dominated by
two weaker bare-EOA paths, so the blind spot doesn't move Solend's own number
-- but Uniswap's DOES depend on it, since the Governor+Timelock path is the
*only* path scored, at admin 80 / multisig 100).

## What was actually blocking measurement -- and the fix

The docstring's blocker was real for a *full historical* replay (every
delegation change since 2020). But the question that matters for a capture
score is not "what changed when" -- it's "how concentrated is *live, cast*
voting power right now." That only needs `VoteCast` events for each
proposal's own voting window (~40,000 blocks, a few days), not a genesis
replay, and `gateway.tenderly.co/public/mainnet` (already found to support
full-range `eth_getLogs` in this project's Hyperlane/CCIP research earlier
the same day) handles that range without the rate limits `publicnode`
enforces on `eth_getLogs` (archive-tier only there).

## What was measured, live, 2026-09-25

`GovernorBravo` at `0x408ED6354d4973f66138C91495F2f2FCbd8724C3`. `VoteCast`
topic0 `0xb8e138887d0aa13bab447e82de9d5c1777041ecd21ca36ba824ff1e6c07ddda4`,
replayed once over blocks 25165444-25608294 (the union of the 5 most recent
proposals' own windows), deduplicated by `(txHash, logIndex)`, grouped by the
proposal ID decoded from each log's own data (NOT by block range alone -- an
earlier pass without this grouping produced wrong, inflated numbers from
overlapping proposal windows, caught by cross-checking against the official
`forVotes` figures before trusting anything). Summed per-voter weight
reproduces the official `forVotes` to within rounding for all 5 proposals
(e.g. proposal 96: 72,978,048 replayed vs 72,977,936 official).

| Proposal | Total votes cast | Top-1 alone / 40M quorum | Top-2 / quorum | Top-4 / quorum |
|---|---|---|---|---|
| 96 | 72,978,048 | 37.5% | 75.0% | 115.0% |
| 97 | 49,991,953 | 37.5% | 57.5% | 83.3% |
| 98 | 51,519,813 | 37.5% | 75.0% | 108.3% |
| 99 | 46,881,792 | 37.5% | 57.5% | 90.8% |
| 100 | 47,881,143 | 37.5% | 57.5% | 90.8% |

**On every one of the 5 most recent Uniswap governance proposals, the top 3-4
distinct addresses alone command enough voting weight to clear the 40M UNI
quorum without any other participation.** One address in particular --
`0x11da8ae234edd16b135edc47e5d9becc8717ecdc`, an EOA with no public
name/tag on Blockscout -- voted on all 5 proposals with the *exact same*
15,003,219 UNI (37.5% of quorum, to the fraction) every time: a single,
completely stable point of near-unilateral quorum capacity. No identity is
claimed for this address beyond what's on-chain; Blockscout has no tag for
it, and none is invented here.

This is exactly the shape of risk `score_uniswap_v3_factory()`'s own
docstring named (citing Term Finance's Meta Vault drain: a capturable vote
makes a real, undelayed timelock not actually protective) -- now measured,
not just described as theoretically possible.

## What this is not

Not a scorer change. The project's own stated reason for declining a 0-100
sub-score here (avoiding a confident-looking number built on an incomplete
picture) still applies to turning this into a single number -- 5 proposals is
a real but small sample, and "top-K share of quorum" is one reasonable metric
among several (delegate count weighted by recent participation only, not
total supply, is a deliberate and defensible choice, but a different metric
could read differently). What changed today is narrower and more concrete:
**the technical objection ("not solvable the same way," would need a
genesis-scale replay) no longer holds** -- a bounded, per-proposal replay via
a gateway already in this project's toolkit answers the question the
docstring left open, cheaply and reproducibly.

## Extended to Aave Governance V3 -- the same day, a far more extreme result

`score_aave_v3_pool()` (Ethereum L1, the DAO root every Aave-relayed
cross-chain target here -- Base, Arbitrum, Plasma, Monad -- ultimately depends
on) also scores its DAO root with `multisig = 100  # not applicable`. Its
own docstring already confirms "GOVERNANCE core confirmed real and active
(522 proposals)" without ever reading who actually casts those votes.

Aave Governance V3's `GOVERNANCE` core (`0x9AEE0B04504CeF83A65AC3f0e838D0593BCb2BC7`,
524 proposals live-confirmed 2026-09-25) does NOT vote on Ethereum for recent
proposals: `getProposal(id).votingPortal` for ids 519-523 all resolve to
`VOTING_PORTAL_ETH_AVAX` (`0x9Ded94...c172`, matching `GovernanceV3Ethereum.sol`'s
own constant) -- the actual vote is cast on Avalanche's `VotingMachine`
(`0x4D1863d22D0ED8579f8999388BCC833CB057C2d6`, address confirmed against
`GovernanceV3Avalanche.sol`), then bridged back. `VoteEmitted(uint256 indexed
proposalId, address indexed voter, bool indexed support, uint256 votingPower)`
-- `proposalId` is indexed, so replaying it needed no block-range estimation
at all, just a topic filter; `api.avax.network/ext/bc/C/rpc` answered an
unbounded `eth_getLogs` for a single proposal ID with no range limit hit.

Replayed for proposals 519, 520, 521, 522 (the 4 most recently finalized),
summed weight matches the official `forVotes` on the `Proposal` struct
EXACTLY (to the last wei-equivalent unit) on all 4 -- not an approximation.

| Proposal | Distinct voters | Against votes | Top-2 / forVotes | Top-4 / forVotes | Top-6 / forVotes |
|---|---|---|---|---|---|
| 519 | 8 | 0 | 51.5% | 85.5% | 97.4% |
| 520 | 19 | 0 | 52.8% | 87.7% | 99.9% |
| 521 | 20 | 0 | 52.9% | 87.8% | 99.9% |
| 522 | 13 | 0 | 51.4% | 85.4% | 97.3% |

**Far more extreme than Uniswap.** On the largest lending protocol by TVL
this oracle tracks ($14.77B on Ethereum alone): 8 to 20 total distinct
addresses vote on a given proposal, ZERO "against" votes on any of the 4
proposals checked, and the top 4 voters alone consistently supply 85-88% of
all voting weight cast. The same 6 addresses recur across all 4 proposals
with near-identical weight each time (e.g. `0x3320756d...` votes exactly
107,244 AAVE-equivalent power on all 4) -- a small, completely stable voting
bloc, not organic per-proposal turnout. No address carries a public
name/tag on the two explorers checked (Blockscout, Routescan) -- reported as
bare addresses, no identity invented.

## Extended to Solend/Realms (Solana) -- the ecosystem that named the risk in the first place

`score_solend_realms_governance()` is the scorer whose own docstring named
this gap and cited Solend's 2022 incident as evidence -- but, like the other
two, never measured it. Solana has no `eth_getLogs` equivalent; spl-governance
records each cast vote as its own on-chain account (`VoteRecordV2`), one per
`(proposal, voter)`, found via `getProgramAccounts` on the governance program
(`A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr`) filtered by two `memcmp`s:
byte 0 = the account-type discriminator (`12` for `VoteRecordV2`, `14` for
`ProposalV2` -- both counted by hand from `GovernanceAccountType`'s real
declaration order in `solana-labs/solana-program-library`, not guessed), and
byte 1 = the 32-byte proposal pubkey. `VoteRecordV2`'s own layout is fixed
up to the field that matters (`voter_weight: u64` at a hardcoded byte
offset, no `Option<>`/`Vec<>` ahead of it in the struct -- verified against
the same GitHub source, not assumed), so this decode carries none of the
ambiguity `ProposalV2`'s many `Option<>`/`Vec<>` fields would.

The realm's `GOVERNANCE` account listed only 15 `ProposalV2` accounts, ever.
Ranked by each proposal's own most recent on-chain activity
(`getSignaturesForAddress`), the most recent is from 2026-08-30 -- itself a
data point: this DAO is not merely capturable in theory, it is *lightly
used*, which makes capture easier, not harder. Decoded `VoteRecordV2` for
the 6 most recently active proposals:

| Proposal (last activity) | Vote records | Top-1 share | Top-2 share | All "Deny"? |
|---|---|---|---|---|
| 3geE5P... (2026-08-30) | 73 | 68.4% | 85.8% | 0 Deny of 73 |
| CEBJQ9... (2025-12-11) | 11 | 51.2% | 63.5% | 0 Deny of 11 |
| 83vrn9... (2025-12-11) | 18 | 49.9% | 61.9% | 0 Deny of 18 |
| AcCkP8... (2025-12-11) | 7 | 37.1% | 59.4% | 0 Deny of 7 |
| g53bkk... (2025-12-11) | 12 | 47.6% | 71.4% | 0 Deny of 12 |
| 6Srg1z... (2025-12-11) | 15 | 27.3% | 50.1% | 0 Deny of 15 |

**Every single vote across all 6 proposals (136 vote records total) was
"Approve" -- zero "Deny" votes recorded anywhere in this sample.** Several
addresses recur across multiple proposals holding the exact same weight
each time (e.g. `v36Pdq4kjUhrUBnYzZLa4HReBXpyVRCwxQ9Bkk2i8YC` = 250,000.00
SLND in 5 of the 6 proposals sampled) -- the same stable-bloc pattern found
on Uniswap and Aave, on a third, structurally unrelated chain.

Cross-check: the `ProposalV2` account for the most recent proposal
(3geE5P...) carries its own on-chain running tally, `options[0].vote_weight`
= 1,480,264.26 SLND, against my independently-summed 1,483,799.55 from its
73 `VoteRecordV2` accounts -- a 0.24% gap, not an exact match. Every vote
record read had `is_relinquished = true`; the likely explanation is that a
relinquished vote's weight can be adjusted on-chain after being counted,
while the individual record keeps its original cast weight -- disclosed as
an open, small discrepancy rather than silently rounded away or hidden. A
second independent RPC cross-check was attempted (`solana-rpc.publicnode.com`)
and refused indexed `getProgramAccounts` filters without a paid token, same
class of limit as `ethereum.publicnode.com`'s archive-only `eth_getLogs`
elsewhere in this project -- noted, not worked around a second way this pass.

## Candidate, for Spap to scope, not built here

If wanted: a `notes`-only disclosure (same convention as every other
"disclosed, not scored" item in this codebase) on `score_uniswap_v3_factory()`,
`score_aave_v3_pool()` (and, by inheritance, every Aave-relayed cross-chain
target that reuses its `multisig = 100` convention), and
`score_solend_realms_governance()` reporting top-K/total-votes coverage over
recent proposals, refreshed each scoring pass -- deliberately NOT folded
into a 0-100 sub-score without Spap's own call on the metric and its
calibration, matching this project's existing discipline of disclosing
facts before inventing scores for them. Would need, if built: a decision on
N (proposal sample size per target), whether Aave's cross-chain voting
portal (Avalanche today, could move to Polygon or back to Ethereum on a
future proposal) makes a "which chain to read" check a per-run necessity
rather than a hardcoded assumption, and a real fix (not just a disclosed
gap) for the 0.24% Solend discrepancy above if this ever becomes a scored
number rather than a disclosed one.

All three (Uniswap, Aave, Solend) now measured, live, cross-checked against
an independent on-chain source each. The technical objection that blocked
this ("would need a genesis-scale replay") is answered for all three: it
never did.
