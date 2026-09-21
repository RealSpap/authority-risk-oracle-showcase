# Solana methodology test: Solend DAO governance (2026-09-17)

Third Solana target, and the first Realms-governed one -- closes the
"(untested: no Realms-governed target scored yet)" flag on METHODOLOGY.md
6.1's `Realms governance` row. Surfaced as a byproduct of
[`data/backtest_2026-09-17-solend-governance-emergency-powers.md`](../../../data/backtest_2026-09-17-solend-governance-emergency-powers.md)'s
retroactive incident research: reverse-engineering `RealmV2`/`GovernanceV2`
byte layouts to independently re-verify the 2022 SLND1/SLND2 vote tallies
surfaced a **second, live, more severe authority path** the backtest itself
didn't need to score -- the Realm's own `authority` field.

**Revised after adversarial review (same day):** the first version of this
test, and the scorer it fed, covered only Path A and Path B below. An
adversarial review workflow (5 findings, 5 confirmed, 0 refuted -- see
`chains/solana/scorers.py`'s changelog comment and METHODOLOGY.md's
2026-09-17 adversarial-review changelog row) found a real, missing THIRD
full-power path -- Path C -- and two unreconciled methodology gaps (the
Realms timelock curve vs. the Squads v4 curve at short delays; the flat
adminKey/multisig=70 constant's lack of a documented derivation). Path C is
now included below; the other two remain open (METHODOLOGY.md section 7),
not silently patched over with an unvalidated new formula.

| Item | Value |
|---|---|
| Cluster | Solana Mainnet Beta |
| Primary RPC | `https://api.mainnet-beta.solana.com` |
| Realm | `7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn` ("Solend DAO") |
| Governance program (Solend's own dedicated deployment, NOT the shared default instance) | `A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr` |

Both confirmed against Realms' own certified-DAO registry
(`Mythic-Project/governance-ui`'s `public/realms/mainnet-beta.json`) and
independently re-derived byte-for-byte from the raw account (below).

## Three full-power authority paths (METHODOLOGY.md 6.2)

### Path A: Realm `authority` -- a bare, on-curve EOA

```
$ sol_read.py realm <rpc> 7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn
account_type 16 (RealmV2)   community_mint SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp
council_mint None   authority EsLAEeKA1dUJRiPpbTAm7r94KqGDAKe1ivH8PLAAuSxV   name "Solend DAO"

$ sol_read.py keytype <rpc> EsLAEeKA1dUJRiPpbTAm7r94KqGDAKe1ivH8PLAAuSxV
on_curve true   owner 11111111111111111111111111111111 (System Program -- a real wallet, not a PDA)
lamports 973806080 (~0.97 SOL)   5 most recent signatures span 2022-12-28 to 2024-01-13 (real, actively-used key)
```

Per spl-governance's own doc comment on this field (`state/realm.rs`):
*"The authority must sign transactions which update the realm config...
The authority should be transferred to Realm Governance to make the Realm
self governed through proposals."* Solend has not done this: `authority`
is still a single team wallet, not the DAO's own Governance PDA, meaning
this one EOA can unilaterally change which mint counts for voting power,
swap in a council mint, or change the minimum weight to create a
governance -- **no token-holder vote required at all.** This is a
full-power path (METHODOLOGY.md 6.2: "can replace code, move or re-value
user funds, or change risk parameters") since it can rewrite the rules the
token-vote path (below) operates under.

Classified per the existing on-curve-key row (METHODOLOGY.md 6.1, no new
formula needed): **adminKey=5, multisig=0, timelock=0.**

### Path B: `GovernanceV2` over the SLND mint -- token-vote-gated

```
$ sol_read.py governance <rpc> 4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc
account_type 20 (MintGovernanceV2)   realm 7sf3tcWm...Z1Hn   governed_account SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp
proposals_count 15   community_vote_threshold YesVotePercentage(1)   [see caveat below]
min_community_weight_to_create_proposal 250000000000 (250,000 SLND)
transactions_hold_up_time_s 0   voting_base_time_s 259200 (3 days)
```

This is the **only** `GovernanceV2`-family account under the realm (444
realm-linked accounts enumerated via `getProgramAccounts` + `memcmp` on the
realm pubkey: 443 `TokenOwnerRecordV2`, exactly 1 `GovernanceV2`), and is
the same account SLND1 and SLND2 both voted through in 2022 (confirmed in
the backtest file). `transactions_hold_up_time_s = 0` independently
confirms, via the live config field itself rather than only realized
proposal timestamps, the backtest's `timelockScore = 0` claim for the 2022
incident. `voting_base_time_s` has since grown from whatever it was in
2022 to the current 259,200s (3 days) -- consistent with the DAO's own
later follow-up proposal, "SLND7: Increase Voting Time From 1 Day to 3
Days" (cited in the backtest), though that intermediate 1-day value is not
independently re-decoded from a historical snapshot.

**Caveat, disclosed rather than silently trusted:** `community_vote_threshold`
decodes to `YesVotePercentage(1)` -- a 1% yes-vote-of-total-eligible-supply
bar, an unusually low number. This is *consistent* with the realized vote
data (SLND1's ~1.19M SLND combined yes+no vote, against a total supply on
the order of 3.3M SLND today, clears a 1% bar by a wide margin either way)
but not independently confirmed by a second decoding method this pass --
flagged as an open point rather than asserted with full confidence. It is
NOT used as a score input regardless (see formula below), so this
uncertainty has no effect on the published score.

No council mint exists on this realm, so this is pure community
token-weighted voting -- METHODOLOGY.md 6.1's "or 70 for token voting"
branch applies to both adminKey and multisig, not a countable `t`-of-`n`.

Applying METHODOLOGY.md 6.1's `Realms governance` row (generalized this
pass to the `hold-up time = 0` case -- see METHODOLOGY.md's own updated
formula and changelog entry):

```
adminKey  = 70                                            (token voting, no countable t)
multisig  = 70                                            (token voting, no countable t)
timelock  = 50 + min(30, 10 * ((259200/3600 + 0)/24 - 1))
          = 50 + min(30, 10 * (72/24 - 1)) = 50 + min(30, 20) = 70
```

### Path C: the governance program's own upgrade authority -- ALSO a bare, on-curve EOA

Added after adversarial review found its absence was a real inconsistency
with every other multi-authority target in this file
(`score_jupiter_aggregator_v6`/`score_kamino_lend` both score their own
target program's upgrade authority as a matter of course; a DAO's
dedicated governance program deserves the same treatment METHODOLOGY.md
3.6 already gives the shared default instance -- "the default instance
itself is upgradeable by a PDA... a DAO on the shared instance inherits
that authority as a dependency").

```
$ sol_read.py program <rpc> A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr
owner BPFLoaderUpgradeab1e11111111111111111111111   executable true
programdata DBvb9pnKMCjfQsCzhExQwKUCRAVRxNAyiHFyFKbaPJrC   last_deploy_slot 138109469
upgrade_authority 6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT

$ sol_read.py keytype <rpc> 6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT
on_curve true   owner 11111111111111111111111111111111 (System Program -- a real wallet, not a PDA)
```

Whoever holds this key can replace the governance program's code outright
-- rewriting vote-counting or execution logic itself, bypassing both Path A
and Path B entirely. Classified identically to Path A (bare on-curve key,
no vote required): **adminKey=5, multisig=0, timelock=0.**

## Combined score (METHODOLOGY.md 6.2: minimum over full-power paths)

```
adminKey  = min(5, 70, 5)  =  5
multisig  = min(0, 70, 0)  =  0
timelock  = min(0, 70, 0)  =  0
compositeScore = floor(0.4*5 + 0.3*0 + 0.3*0 + 0.5) = 2   -- CRITICAL band
oracleAuthorityScore = 100 (not applicable -- no price-oracle dependency, same convention as Jupiter Aggregator v6)
```

TWO of the three full-power paths independently land on the same bare-EOA
band and dominate the result regardless of exactly how well-calibrated the
token-voting formula turns out to be -- Path B's numbers are still computed
and published in full (matching Kamino Lend's precedent of publishing
every full-power path's own numbers, not just the winning one), both
because they complete the methodology's first real Realms-governance
validation and because either EOA being replaced by a self-governing PDA
would make the remaining paths the ones that actually matter.

## What this adds to the retroactive backtest

The backtest (`data/backtest_2026-09-17-solend-governance-emergency-powers.md`)
scored the 2022 incident's own authority shape (the token-vote path,
`timelockScore=0` from a 6-hour window with no hold-up) at `compositeScore
= 8/100`. This live scorer finds the DAO's *current* authority surface is
worse than that incident-specific estimate, not better: the same bare-EOA
realm authority that could always have unilaterally rewritten the voting
rules is still live today, unrelated to and unfixed by either 2022 reversal
proposal (SLND2) or the later voting-time increase (SLND7) -- neither
proposal touched the realm's own `authority` field, only the Governance
account's config.

## Reproduction

```
python3 chains/solana/scripts/sol_read.py realm https://api.mainnet-beta.solana.com 7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn
python3 chains/solana/scripts/sol_read.py governance https://api.mainnet-beta.solana.com 4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr
python3 chains/solana/scripts/sol_read.py keytype https://api.mainnet-beta.solana.com EsLAEeKA1dUJRiPpbTAm7r94KqGDAKe1ivH8PLAAuSxV
python3 chains/solana/scripts/sol_read.py keytype https://api.mainnet-beta.solana.com 6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT
```
