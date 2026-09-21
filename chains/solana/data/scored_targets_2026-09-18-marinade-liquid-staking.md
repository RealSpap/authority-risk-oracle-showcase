# Solana -- Marinade Liquid Staking scored, 2026-09-18

Closes two open points at once from `scouted_targets_2026-09-17-run2.md`
(target #3, upper-bound composite 54): "decode `State.admin_authority`"
and Methodology gap H1 ("legacy serum-style multisig has no timelock
field, needs to be written into `METHODOLOGY.md`"). Both apply to this
one target, so this pass closes them together.

Of the original 16 scouted targets, Marinade was the only one still
carrying a clean "(upper bound)" tag with no config-admin path decoded --
Meteora DLMM/DAMM v1 (targets #5/#6) remain deliberately un-promoted for a
different reason (no public source to confirm a specific number, reaffirmed
by the 2026-09-18 adversarial review of the previous batch), not a
backlog item.

## Result

| Dimension | adminKey | multisig | timelock |
|---|---|---|---|
| Program upgrade (legacy multisig, Path A) | 60 | 100 | 0 |
| `State.admin_authority` (council governance, Path B) | 70 | 69 | 70 |
| **Combined (min per dimension)** | **60** | **69** | **0** |

**compositeScore = 45** (down from the published upper bound of 54).

## Two full-power paths, both re-derived live every run

**Path A -- program upgrade authority.** A 2021-era "serum-style" multisig
(`marinade-finance/multisig`, program `msigmtwzgXJHj2ext4XJjCDmpbcMuufFb5cHuwg6Xdt`,
a verbatim fork of the now-archived `project-serum/multisig` template --
the multisig PROGRAM's own upgrade authority was burned in 2021, so the
multisig program itself is immutable; only the Marinade program it
controls is still live). Multisig account
`magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed`, 6-of-13, any owner can sign
(no permission bitmask), and there is **no timelock field anywhere in the
struct** -- confirmed against the real source
(`marinade-finance/multisig@v0.7.0`'s `execute_transaction` only checks
`did_execute` and `sig_count >= threshold`), not merely absent from the
decoded bytes. Signer PDA re-derived with seeds `[multisig_pubkey]`,
bump = the on-chain `nonce` field (253, not searched for) -- exact match
to the live program-upgrade authority
`551FBXSXdhcRDDkdcb3ThDRg84Mwe5Zs6YjJ1EEoyzBp`.

**Path B -- `State.admin_authority`.** NOT a multisig at all: a
Realms/SPL-Governance native-treasury PDA
(`42VJbDihcS81YJPbuhHnHgvo1ehu42j8VK9sNwrnAarR`) of a dedicated Governance
record in Marinade's own DAO deployment
(`GovMaiHfpVPw8BAM1mbdzgmSZYDw2tdP32J2fapoQoYs`, realm "Marinade DAO",
governance `M5Fg6GipNvPzWgXNr5wj1EDcp8GB9J53cgyE7YGYLbL`). This specific
Governance record has COMMUNITY (MNDE token-holder) voting structurally
DISABLED (`community_vote_threshold = Disabled`) -- only its COUNCIL can
vote (`council_vote_threshold = YesVotePercentage(50%)`).

The council mint's entire 5-token supply sits, as expected for
spl-governance's normal deposit-pooling design, in the realm's own pooled
`Governing Token Holding` PDA -- this is NOT evidence of concentration in
one wallet, it's the standard mechanism (independently re-derived and
confirmed: this exact PDA, seeds `["governance", realm, council_mint]`).
The real voters are one level deeper, in each member's own
`TokenOwnerRecordV2`, enumerated LIVE (not hardcoded) via
`sol_read.list_token_owner_records`: **5 distinct owners, 1 token each**,
a genuine one-seat-per-member council. A 50% `YesVotePercentage` threshold
over 5 equal-weight seats is `ceil(0.50 * 5) = 3` -- an effective 3-of-5
council, using the exact same `ceil(pct * total_weight)` method this
project's own `data/finding_2026-09-17-spl-governance-shared-instance-
controller.md` already established and calibrated (there: a 60% threshold
over 7 seats -> 5-of-7).

## The judgment call: full-power, not bounded, and why

`admin_authority` gates `ChangeAuthority` (single signature, no timelock,
can reassign itself and every other top-level authority field on `State`
at will) and `ConfigMarinade` (reward_fee, hard-capped <=10% by an in-code
constant the admin cannot itself raise -- clearly bounded on its own).

The full-power case rests on a TRANSITIVE path: `ChangeAuthority` lets
`admin_authority` instantly self-grant `validator_system.manager_authority`,
which then gates `SetValidatorScore` and `EmergencyUnstake`/`PartialUnstake`
-- the ability to force-redirect up to 100% of ALL depositors'
currently-staked SOL away from one validator per epoch. Found by the
adversarial review below, stronger than first written here: the
per-epoch movement cap `admin_authority` also controls via
`ConfigMarinade` has NO enforced ceiling at all (`config_marinade.rs`
explicitly comments out the >=100% check) -- not "raisable to 100%,"
there is no upper bound to raise it to.

No instruction moves user PRINCIPAL to an admin-controlled address -- the
only value admin can extract is the same hard-capped reward-fee skim, so
this is not a fund-custody bypass. But validator selection is the primary
counterparty/slashing-risk determinant for a liquid-staking protocol, the
closest real analogue this target has to METHODOLOGY.md 6.2's own
full-power example of a "price source": it lets one signature redirect
where real, live, already-deployed user value is exposed, not merely
which fees get skimmed. This is disclosed, not silently decided --
`score_marinade`'s own docstring lays out the counter-argument (a reviewer
who weighs "SOL never technically leaves a Marinade-owned account" more
heavily may reasonably classify this as bounded instead) and exactly which
instructions that disagreement should be argued from.

## Methodology gap H1, closed

The legacy serum-style multisig shape (`owners: Vec<Pubkey>, threshold: u64,
nonce: u8, owner_set_seqno: u32`, no timelock field, signer PDA =
`[multisig_pubkey]` with bump = the stored nonce) is structurally
identical, for scoring purposes, to Squads v3 (fixed threshold-of-members,
zero enforced delay) -- it reuses that same formula rather than needing a
new `_score_full_power_path` kind. No new branch was added; this closes
the gap by documenting the reuse, not by writing new code.

## Cross-exposure, live-detected

Owner `8HVYKgq2PA4SCDuPZSfHBH1aupTBJYPVru6kq3UfuSX9` sits on BOTH the
6-of-13 program-upgrade multisig AND holds one of the 5 council seats
gating `admin_authority` -- one compromised key reaches both full-power
paths on this single target. Live-detected via the same `_signers`-set
mechanism as every other cross-exposure finding in this file, not assumed
from the scouting pass.

## Verification

- Every identity re-derived offline and required to match the live-read
  value exactly: the legacy multisig's signer PDA (seeds
  `[multisig_pubkey]`, bump = stored nonce, not searched for), and the
  native-treasury PDA (seeds `["native-treasury", governance_pubkey]` --
  corrected 2026-09-18 by adversarial review, which caught this sentence
  conflating it with the DIFFERENT governing-token-holding PDA's seeds,
  `["governance", realm, council_mint]`; the scorer code itself always
  used the right seeds, only this sentence had them swapped).
- `read_governance_v2` (the modern layout) was tried and matched sane
  values on the first attempt; `read_governance` (the legacy layout, still
  used by Solend's own decade-old deployment) was also tried against the
  same account and produced clearly-garbage values (a 388-day voting
  period, a threshold byte of 255) -- confirming this is a MODERN
  governance deployment, not a version-detection guess.
- The council census (5 distinct `TokenOwnerRecordV2` owners, 1 token
  each) is enumerated live via `getProgramAccounts` + `memcmp` filters,
  not hardcoded -- a future re-run picks up real membership changes.
  Independently spot-checked 2 of the 5 records by hand (own decode +
  PDA re-derivation) before trusting the full live enumeration.
- FIXED 2026-09-18 (adversarial review): the council-threshold ceiling's
  denominator was originally the SUM of TokenOwnerRecord deposits, not
  spl-governance's own real vote-tallying denominator (the council mint's
  total on-chain SUPPLY, per `state/proposal.rs`'s
  `get_max_voter_weight_from_mint_supply`). The two happen to coincide
  today (mint supply = 5 = deposit sum), but the mint's own
  `mintAuthority` is not renounced and deposits can be partially
  withdrawn, so this could silently drift and UNDERSTATE the threshold on
  a later run. Fixed: `score_marinade` now reads the mint's real supply
  live and aborts (raises) rather than silently scoring if it ever
  diverges from the deposit sum, matching this function's existing
  discipline for its `community_vote_threshold`/`council_vote_threshold`
  staleness checks.
- Prior scouting's multisig PROGRAM id
  (`msigmtwzgvzHPfstAUAxBKxz65vopEEqBg5RXujD65`) turned out to be invalid
  (31 bytes, not a real pubkey) -- caught and corrected by tracing a real
  on-chain upgrade transaction rather than trusting the citation; the
  multisig ACCOUNT address, signer PDA prefix, and 6-of-13 threshold from
  the original scouting pass all checked out exactly.
- 4 new unit tests added (`scripts/lib/tests/test_marinade_liquid_
  staking.py`), covering all 3 new decoders -- 2 against exact bytes
  fetched live, 1 against a synthetic fixture for the large `State`
  account (plus an offset-is-not-coincidental regression guard).
- `python3 -m unittest discover -s scripts/lib/tests`: 173/173 pass.
- `python3 scripts/validate_all_scorers.py --ecosystem solana`: 13/13
  targets pass, `OVERALL: PASS`.
- Also fixed, found along the way: `score_solend_dao_governance`'s own
  docstring/comment claimed the countable council-threshold branch of
  `_score_full_power_path("realms_governance", ...)` "deliberately raises
  NotImplementedError" -- stale since 2026-09-17, when that branch was
  actually calibrated and implemented (see that day's changelog). Fixed
  the comment; `score_marinade` is now that branch's first real,
  working example.

## Adversarial review, 2026-09-18

3-dimension review before commit (legacy-multisig/Path-A/Path-B facts;
council census and threshold derivation; the full-power judgment call and
cross-exposure), each finding independently re-verified by a separate
agent instructed to try to refute it. 14 agents, 11 findings, 9 confirmed
(mostly "matches exactly"), 2 flagged for disposition and applied above:
the council-threshold denominator fix (deposit sum -> live mint supply,
with an abort-on-divergence guard) and the `max_stake_moved_per_epoch`
wording fix (no enforced ceiling at all, not "raisable to 100%" -- the
review found the ORIGINAL docstring UNDERSTATED the real risk, not
overstated it). A third finding proposing to reframe the full-power
docstring around METHODOLOGY.md 6.2's "move user funds" clause instead of
its "price source" clause was itself refuted on independent re-check --
"price source" is one of 6.2's own three enumerated full-power examples,
not a weaker external analogy, and the docstring already explicitly
raises and rejects the "moves funds" framing before choosing it (no
instruction moves user principal to an admin-controlled address). No
change to composite (45) from either of the two real fixes.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/solana')
from scorers import score_marinade
r = score_marinade('https://api.mainnet-beta.solana.com')
print(r['label'], r['compositeScore'])
for n in r['notes']: print(' -', n)
"
```
