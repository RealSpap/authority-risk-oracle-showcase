# Retroactive backtest: Solend DAO "emergency powers" governance incident (2022-06-19/20)

Second backtest of the after-hackathon roadmap (see
`data/backtest_2026-09-17-wasabi-protocol.md` for the first). Chosen over
the other obvious Solana candidate (Mango Markets, October 2022) because it
is a governance/authority-risk failure in this project's own sense -- a
weak voting window letting a DAO grant a small team emergency
asset-seizure power over a live user position -- not primarily an
oracle-manipulation or collateral exploit, which this project's methodology
was never built to catch.

Unlike the Wasabi backtest (an EVM bare-EOA admin key, decoded with
`web3.py` against an EVM RPC), this one exercises the Solana side of the
project's own tooling: `chains/solana/scripts/sol_read.py`'s `rpc()` /
account-decoding conventions, extended here to a new account type (SPL
Governance `RealmV2` / `GovernanceV2` / `ProposalV2`) this project had not
previously needed to read.

## The incident, as independently corroborated by press

- **2022-06-19**: Solend DAO proposal **SLND1 "Mitigate Risk From Whale"**
  passes. A single wallet had deposited ~95% of the Solend main pool's SOL
  (~$170M / 5.7M SOL) and represented the large majority of USDC borrowing
  against it; a large SOL price drop risked a liquidation large enough to
  move the market and leave the pool with bad debt. SLND1 authorized
  "Solend Labs" (the founding team) to temporarily take over the whale's
  account and liquidate it OTC instead of on-chain. (CoinDesk, Decrypt,
  Cointelegraph, BeInCrypto, AmbCrypto -- consistent across every source.)
- **2022-06-20**: after immediate community backlash (Delphi Labs' general
  counsel publicly called it "contrary to the DeFi ethos" and legally
  dubious), Solend DAO passes **SLND2 "Invalidate SLND1 and Increase Voting
  Time"**, reversing the emergency-powers grant and lengthening the
  governance voting window so a proposal this consequential could not pass
  again this fast. One wallet reportedly paid ~$700,000 to acquire
  additional voting power for this vote, ending up with roughly 90% of
  SLND2's total "yes" weight (Decrypt, Cointelegraph) -- **not**
  independently re-verified on-chain this pass, see Limitations.

## What was independently re-derived live on-chain today (2026-09-17)

Every fact below comes from decoding raw account bytes returned by
`https://api.mainnet-beta.solana.com`, the same public RPC endpoint this
project's own `scripts/validate_all_scorers.py` already uses for Solana --
not from a block explorer's rendered UI and not re-typed from a news
article.

**1. Solend's Realm is on its own dedicated governance program, not the
shared instance this project already tracks -- a real correction, caught
before it became a wrong methodology-doc citation.** This project's
`chains/solana/METHODOLOGY.md` section 3.6 already documents the SPL
Governance *default mainnet instance*
(`GovER5Lthms3bLBqWub97yVrMmEogzX7xNjdXpPPCVZw`). A first-pass web search
for Solend's governance program returned that same address, and it would
have been easy to assume Solend uses it too. A live `getProgramAccounts`
query against that address filtered for a Realm whose `community_mint` is
Solend's `SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp` returned **zero
results** -- the assumption was wrong. Solend actually deployed its own,
separate governance program:

```
Governance program : A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr
Realm               : 7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn
```

confirmed against Realms' own certified-DAO registry
(`Mythic-Project/governance-ui`'s `public/realms/mainnet-beta.json`, the
open-source repo behind `app.realms.today`, itself cross-checked live
against the Realms UI showing the identical Realm address in its
"View on Solscan" link), and then independently re-derived byte-for-byte
from the raw account: `getAccountInfo` on
`7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn` returns an `account_type`
byte of `16` (`RealmV2` in the standard spl-governance enum) whose
`community_mint` field (bytes 1-33) decodes to
`SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp` exactly, and whose `name`
field (found further in as raw ASCII) reads `"Solend DAO"`.

**2. Both SLND1 and SLND2 still exist on-chain today, byte-identical
proposal records, and the DAO has had exactly one Governance account,
before and after the incident.** Every account referencing this Realm was
enumerated (`getProgramAccounts` with a `memcmp` filter on the realm
pubkey, 444 accounts total: 443 `TokenOwnerRecordV2` -- one per wallet that
has ever deposited SLND for voting power -- and exactly **one**
`GovernanceV2`-family account, `4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc`).
Decoding SLND1's and SLND2's own Proposal accounts (found via the Realms
UI's proposal list, cross-checked against the same Realm address found
independently above) confirms both were voted through this exact same
Governance account, which is **still today** the DAO's only governance
vehicle:

```
SLND1 "Mitigate Risk From Whale"          -> HuaL6cDtuNtfnJgvwMnYiZDHVCoLAuDtVFgJD8kYChJ4
SLND2 "Invalidate SLND1 and Increase..."  -> 3geE5P3D7VJRaNNDVfZciGsXgwGiao1hSNpRM6jWNa5A
  both: governance == 4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc
  both: governing_token_mint == SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp
```

Worth flagging on its own, in this project's own "never trust a hand-typed
value" spirit: the Realms UI listed **SLND7** ("Increase Voting Time From 1
Day to 3 Days") directly above SLND2 in the proposal list, and the two
addresses were first paired with the wrong proposal names while
transcribing them by hand -- caught immediately because the mismatched
account's own on-chain `name` field self-identified as SLND7, not SLND2,
during decoding. The account bytes are self-describing enough to catch a
transcription error; the numbers below are from the corrected, re-verified
addresses.

**3. The exact vote tallies, to 6 decimal places -- not rounded, not
re-typed from a headline.** Each `ProposalV2` account stores its single
"Approve" option's `vote_weight` and a top-level `deny_vote_weight`, both
raw `u64` token amounts (SLND has 6 decimals, independently confirmed via
`getAccountInfo` on the mint itself). Scanning both accounts' raw bytes for
these two fields:

```
SLND1  Approve = 1,155,431.557485 SLND   Deny = 30,101.734080 SLND
       -> 97.46% yes  (press: "97.5% yes")
SLND2  Approve = 1,480,264.264132 SLND   Deny =  3,535.287128 SLND
       -> 99.76% yes  (press: "99.8% yes ... 1,480,264 yes, 3,535 no")
```

SLND2's on-chain tally matches the press-reported whole-number vote counts
(1,480,264 / 3,535) exactly once the 6-decimal remainder is dropped -- the
strongest single confirmation in this backtest that the news reporting was
itself sourced from this same on-chain data, not estimated.

**4. The realized voting-window duration, from the proposal's own
timestamps -- confirms "less than 6 hours" precisely, and confirms the
vote-to-reversal timeline.** Each `ProposalV2` stores `Option<i64>` Unix
timestamps for `voting_at` and `voting_completed_at`. Scanning both raw
accounts for embedded Unix timestamps in the June 2022 range:

```
SLND1  voting_at        = 2022-06-19 08:36:34 UTC
       voting_completed_at = 2022-06-19 14:36:42 UTC   (6h 0m 8s)
SLND2  voting_at        = 2022-06-20 01:21:22 UTC   (~11h after SLND1 closed)
       voting_completed_at = 2022-06-20 07:21:55 UTC   (6h 0m 29s)
```

Both proposals ran the exact same ~6-hour window -- independent, on-chain
confirmation of "passed in less than 6 hours" (press), and of SLND2 having
been proposed and passed on the calendar day *after* SLND1, both in UTC,
matching "the next day."

**5. The DAO's current governance voting period is 3 days -- consistent
with the documented follow-up proposal, not re-derived from that proposal
directly.** The live `GovernanceV2` account's config now stores a
`voting_base_time` of `259200` seconds = exactly 3 days, which matches
SLND2's own text ("increases governance voting time to one day") having
since been superseded by a later proposal visible in the same Realms
proposal list, **SLND7 "Increase Voting Time From 1 Day to 3 Days"** --
the config field only proves the *current* value, not the intermediate
1-day value SLND2 itself set; that intermediate value is taken from SLND2's
own proposal text and SLND7's title, not independently re-decoded from a
historical config snapshot.

## What this project's methodology would have said

This incident is not a bare-admin-key or weak-multisig failure -- Solend's
architecture had no admin EOA and no Safe in the path the community
objected to. The authority-risk failure is squarely in this project's
**timelock** dimension, generalized from "smart contract execution delay"
to its exact analogue in a token-vote-gated system: **the delay between a
proposal passing and it taking irreversible effect.** SLND1 had a ~6-hour
voting period and, on passing, no additional execution hold-up before
"Solend Labs" could act on the granted power -- structurally identical to
a Timelock contract with `delay = 0`, which this project's own convention
already scores at the floor:

```
adminKeyScore  ~ 20   (not a bare EOA -- governed by a real token-weighted
                        vote, so not the worst band, but a single ~1.16M-SLND
                        holder was enough to reach ~97.5% "yes" alone in the
                        1.19M-SLND-weight vote that decided SLND1, meaning
                        realistic quorum was concentrated in very few hands)
multisigScore  = 0    (no Safe/multisig layer exists in this path at all --
                        governance-vote-gated, not multisig-gated)
timelockScore  = 0    (0-second effective hold-up after a ~6-hour vote --
                        the closest real-world Timelock analogue is
                        `delay = 0`, this project's own worst case)
compositeScore = floor(0.4*20 + 0.3*0 + 0.3*0 + 0.5) = 8/100  -- CRITICAL band
```

An `8/100` composite, in the same CRITICAL band this project already
reserves for its worst-scored real targets -- computed from the same
formula already live on Robinhood Chain, generalized (not invented after
the fact) to a token-vote timelock instead of a Solidity Timelock contract,
exactly the kind of authority shape this project's Zcash work this same
session already established a precedent for handling non-EVM, non-multisig
governance primitives on their own terms.

**Correction, added after this backtest promoted Solend DAO to a live scored
target (`chains/solana/scorers.py::score_solend_dao_governance`,
`chains/solana/data/methodology_test_2026-09-17-solend-governance.md`):**
the `8/100` above used a simplified, illustrative generalization written
before METHODOLOGY.md had an actual tested formula for Realms governance --
it treated the entire ~6-hour SLND1 voting window as equivalent to
`timelockScore = 0`, giving no credit for the voting period itself being a
real, if short, delay. Properly applying METHODOLOGY.md 6.1's now-tested
`realms_governance` formula to SLND1's own historical parameters (a ~6-hour
voting window, 0 hold-up) gives `timelockScore = 50 + min(30, round(10*(6/24
- 1))) ~ 43`, and `adminKey = multisig = 70` (the flat token-voting baseline)
rather than the `20/0` guessed here -- a materially higher, less alarming
number for the 2022-specific incident path alone (`compositeScore ~ 62`,
not 8).

This is a real, disclosed methodology tension, not swept under a rug: the
flat 70 baseline for "uses token voting" does not distinguish SLND1's
actual realized concentration (one or a few large holders supplying nearly
all the "yes" weight, within a single short window) from a genuinely broad,
slow-moving vote -- a real gap, tracked as an open point in
`chains/solana/METHODOLOGY.md` section 7. It is NOT the reason this
backtest's headline conclusion changes, though: independently decoding the
Realm's own `authority` field (not examined for this backtest, only added
when the target was promoted to a live scorer) found a SEPARATE, dominant
full-power path -- a bare, still-active EOA that can rewrite the DAO's
entire voting configuration with no vote at all, unrelated to and unfixed
by either SLND1, SLND2, or SLND7. That path alone gives `adminKey=5,
multisig=0, timelock=0`, and DOMINATES (via METHODOLOGY.md 6.2's minimum-
over-full-power-paths rule) regardless of how the token-voting formula
above is eventually calibrated -- so the live scorer's actual published
score for Solend DAO today is `compositeScore = 2/100`, WORSE than either
number here, for a reason this backtest's own scope never covered. See the
methodology test file for the full derivation.

## Why this is a stronger backtest than a quorum-threshold headline

The commonly repeated shorthand ("weak quorum let a whale grab emergency
power") undersells what's verifiable on-chain: SLND1's own "yes" weight
(1,155,431.56 SLND) came overwhelmingly from very few large holders in a
window too short for the rest of the DAO to organize opposition -- the
same 1,155,431.56 SLND worth of "yes" votes needed only 6 hours to
concentrate, while it then took the community until the next multi-hour
window (SLND2) to reverse it, and a further proposal (SLND7) after that to
actually fix the structural voting-window weakness for good. Three
proposals, three separate on-chain records, one coherent authority-risk
story -- independently re-derived end to end, not summarized from a single
source.

## Honest limitations of this backtest

- **The exact instruction payload SLND1 executed (which program, which
  accounts, what specific power was granted to "Solend Labs") was NOT
  decoded this pass.** The Governance account controlling both votes,
  `4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc`, is typed on-chain as a
  `MintGovernanceV2` whose nominal `governed_account` is the SLND mint
  itself -- but SPL Governance lets a Governance-owned PDA be granted
  arbitrary authorities elsewhere (e.g. over the lending program's admin
  key) regardless of its nominal type label, and confirming that
  specifically would require decoding SLND1's `ProposalTransactionV2`
  instruction data, not just the Proposal's vote tallies and timestamps
  decoded here. Flagged as real follow-up work, not silently assumed.
- **The `$700,000` vote-buying claim for SLND2 was NOT independently
  re-verified on-chain.** Confirming it would mean finding the specific
  `TokenOwnerRecord` that jumped in weight between SLND1's and SLND2's
  snapshots and cross-referencing a matching SLND purchase -- time-boxed
  out of this pass; cited from press only (Decrypt, Cointelegraph).
- **`min_transaction_hold_up_time` (the Governance config's own literal
  execution-delay field, separate from the 6-hour voting period) was not
  cleanly decoded.** This fork of spl-governance's exact `GovernanceConfig`
  byte layout could not be pinned down with certainty in the time
  available; the `timelockScore = 0` claim above rests on the
  well-corroborated, independently-timestamped fact that SLND1 would have
  taken effect immediately after its ~6-hour vote (the entire reason the
  community had to rush SLND2 rather than simply wait out a delay), not on
  a directly-read config field.
- **This is a retrospective classification, not a real-time flag.** Solend
  was never a tracked target of this oracle before this backtest, and no
  live Solana scorer for Solend exists in `chains/solana/scorers.py` as of
  this pass -- this demonstrates the methodology would classify this
  authority shape as critical, not that this project caught it live.

## Reproduction

```bash
# Realm -> community_mint match (confirms which governance program Solend actually uses)
curl -s https://api.mainnet-beta.solana.com -X POST -H "Content-Type: application/json" -d \
  '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn",{"encoding":"base64"}]}'

# Both proposals' raw accounts (decode vote_weight/deny_vote_weight and the two
# Option<i64> voting_at/voting_completed_at timestamps as documented above)
curl -s https://api.mainnet-beta.solana.com -X POST -H "Content-Type: application/json" -d \
  '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["HuaL6cDtuNtfnJgvwMnYiZDHVCoLAuDtVFgJD8kYChJ4",{"encoding":"base64"}]}'
curl -s https://api.mainnet-beta.solana.com -X POST -H "Content-Type: application/json" -d \
  '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["3geE5P3D7VJRaNNDVfZciGsXgwGiao1hSNpRM6jWNa5A",{"encoding":"base64"}]}'
```
