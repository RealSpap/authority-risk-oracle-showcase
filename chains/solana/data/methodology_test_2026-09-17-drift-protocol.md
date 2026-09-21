# Solana methodology test: Drift Protocol (2026-09-17)

Fourth Solana target. Surfaced while researching a third retroactive
backtest (`data/backtest_2026-09-17-drift-protocol-security-council-
compromise.md`): Drift's own 2026-04-01 Security Council compromise is
independently, fully on-chain-verifiable (exact malicious transactions
decoded directly, not only cited), and the CURRENT authority state is a
genuine "before vs after" story worth a live score, not just a backtest.

**Adversarially reviewed the same day**, independently re-deriving every
checkable claim (the `read_governance_v2` byte decode against two real
accounts, every on-chain fact in the companion backtest file, and
`score_drift_protocol`'s own code paths): 1 real code bug found and fixed
(the program-upgrade path was missing `none_means_renounced=True`, which
would have inverted the risk signal if that authority were ever renounced
-- see the scorer's own "FIXED" docstring note) plus 2 real documentation
issues in the companion backtest file (an incomplete transaction-log
transcript; a composite-score arithmetic box that displayed single-path
inputs then jumped to the cross-path combined answer without showing the
`min()` step) -- both corrected there, not here (this file's own combined-
score derivation below was already self-consistent).

| Item | Value |
|---|---|
| Cluster | Solana Mainnet Beta |
| Primary RPC | `https://api.mainnet-beta.solana.com` |
| Program | `dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH` (drift-labs/protocol-v2) |
| Realm | `FVVXu18aNUqyFCfq8sGktPM62mqJAGaenv4z6UGUs5em` ("Drift DAO") |
| Drift's own governance program (dedicated, not the shared default instance) | `dgov7NC8iaumWw3k8TkmLDybvZBCmd1qwxgLAGAsWxf` |

Realm and governance program confirmed against Realms' own certified-DAO
registry (`Mythic-Project/governance-ui`'s `public/realms/mainnet-beta.json`).

## Two full-power authority paths (METHODOLOGY.md 6.2)

### Path A: the program's own loader-v3 upgrade authority -- Squads v4

```
$ sol_read.py program <rpc> dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH
upgrade_authority = 8jj7zJgdr5bDndc7evM74FMGwzLPmd4u4QxNzFi1BMai   last_deploy_slot 429731225 (2026-06-29, post-incident)

$ sol_read.py keytype <rpc> 8jj7zJgdr5bDndc7evM74FMGwzLPmd4u4QxNzFi1BMai
on_curve false (a PDA)

$ sol_read.py squads-vault - 7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM 0
vault = 8jj7zJgdr5bDndc7evM74FMGwzLPmd4u4QxNzFi1BMai   <- EXACT MATCH, offline re-derivation

$ sol_read.py squads <rpc> 7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM
threshold=4   members=7 (one member mask=1, no Vote permission -> 6 real voters)
time_lock_s=3600 (1 hour)   config_authority = system default (autonomous)
```

The candidate multisig was found via `resolve_controller_via_last_tx`
(a transaction-history lookup, not proof by itself) and is REQUIRED to
exactly match the live authority via the offline vault-PDA re-derivation
above, same discipline as every other Squads-controlled target in this
file -- confirmed, not assumed.

Classified per METHODOLOGY.md 6.1's Squads v4 formula (`0 < d < 24` band):

```
adminKey  = 50 + min(20, 5*(4-1)) = 65
multisig  = min(100, round(15*4 + 40*4/6)) = min(100, 87) = 87
timelock  = round(50 * (3600/3600) / 24) = round(50/24) = 2
```

### Path B: the Realm's own `authority` field -- self-governed (unlike Solend's bare EOA)

```
$ sol_read.py realm <rpc> FVVXu18aNUqyFCfq8sGktPM62mqJAGaenv4z6UGUs5em
community_mint DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7   council_mint 6R6fMZXw6H2tdaBTDZErfEspknVVgUnAdvED6xfKpGVa
authority EJ5kEb9XkQC4rbc7uM45xoLM8TiagGCLad5YpGtMyz4   name "Drift DAO"

$ sol_read.py keytype <rpc> EJ5kEb9XkQC4rbc7uM45xoLM8TiagGCLad5YpGtMyz4
on_curve false   owner = dgov7NC8iaumWw3k8TkmLDybvZBCmd1qwxgLAGAsWxf (Drift's OWN governance program)
```

Unlike Solend, Drift's realm authority is NOT a bare EOA -- it is a
`GovernanceV2` account owned by Drift's own governance program, i.e. the
Realm genuinely reached the spl-governance-recommended "self governed"
end state. Decoding that Governance account (modern struct layout, same
version family as the "Realms Security council 8" case documented in
`data/finding_2026-09-17-spl-governance-shared-instance-controller.md` --
NOT Solend's older layout):

```
community_vote_threshold      = YesVotePercentage(2%)
transactions_hold_up_time_s   = 86400  (1 day)
voting_base_time_s            = 345600 (4 days)
council_vote_threshold        = Disabled (the 5-seat council mint cannot pass ordinary votes here)
council_veto_vote_threshold   = YesVotePercentage(30%)  (the council CAN veto)
voting_cool_off_time_s        = 172800 (2 days, veto-only extension)
```

A community-token vote with a genuine council veto check, not a countable
council/community threshold in the sense METHODOLOGY.md 6.1's countable
branch models (that branch is for a vote a council itself PASSES; here the
council only vetoes what the community already decided) -- scored via the
existing flat "token voting" branch, with the council-veto nuance
disclosed in the scorer's own notes rather than folded into a bespoke new
number.

```
adminKey  = 70   multisig = 70   (token voting, no countable pass-threshold)
timelock  = 50 + min(30, round(10 * ((345600+172800+86400)/3600/24 - 1)))
          = 50 + min(30, round(10 * (168/24 - 1))) = 50 + min(30, 60) = 80
```

Note: Drift's own 5-seat council mint (separate from the Squads v4 members
above -- not independently checked for overlap this pass) exists to VETO,
not to pass, proposals through this Governance account -- a real
structural difference from Solend's countable-threshold case that this
project's Realms formula does not yet have a dedicated branch for.
Disclosed as an open point, not forced into an ill-fitting number.

## Combined score (METHODOLOGY.md 6.2: minimum over full-power paths)

```
adminKey  = min(65, 70)  = 65
multisig  = min(87, 70)  = 70
timelock  = min(2, 80)   =  2
compositeScore = floor(0.4*65 + 0.3*70 + 0.3*2 + 0.5) = 48
oracleAuthorityScore = 100 (not applicable -- no price-oracle dependency, same convention as Jupiter/Solend)
```

The program-upgrade Squads path dominates `timelock` (1 hour beats a 4-day+
governance vote by a wide margin in absolute terms, but this project's
formula scores the SHORT delay worse specifically because 1 hour gives
almost no reaction window compared to the multi-day governance path).

## Before vs. after: what actually changed post-incident

The 2026-04-01-era multisig (`2LW6PSEjp81xSEttWwXDB6Etb1eKdhYPbFEojYbyhx88`,
independently confirmed in the backtest file) was 2-of-5 with
`time_lock_s = 0` and a non-default `config_authority` -- composite `32`.
Today's replacement (`7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM`) is
4-of-7 (6 real voters) with a real 1-hour delay and an autonomous
(default) `config_authority` -- composite `48` for this path alone, `48`
combined (the governance path doesn't bind). A real, live-verified
improvement, not merely claimed -- but the still-short 1-hour delay is
exactly what keeps this well short of a strong score, and is the
project's own formula correctly declining to reward "some delay" the way
it would reward "a full day or more."

## Honest limitations

- The 5-seat Drift DAO council mint's actual holders were not
  cross-checked against the Squads v4 multisig's 7 members for overlap
  this pass -- a real, disclosed gap (would matter for `crossExposureScore`
  if the same people sit on both bodies).
- Drift's own protocol-level state (the `admin` pubkey field the 2026-04-01
  `UpdateAdmin` instruction targeted, and any per-market authorities
  analogous to Kamino's seven) was not independently re-derived for the
  CURRENT scorer -- this pass scores the two generic full-power paths
  (program upgrade, realm authority) common to every Realms-governed
  Solana target in this file, not a Drift-specific account layout. A
  stronger future pass would decode Drift's own `State`/`PerpMarket`
  accounts the way `chains/solana/scripts/sol_read.py::read_klend_market`
  already does for Kamino.
- The council-veto authority shape (community passes, council can only
  veto) has no dedicated METHODOLOGY.md 6.1 formula branch -- scored via
  the flat token-voting numbers, with the veto nuance disclosed rather
  than modeled numerically.

## Reproduction

```
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH
python3 chains/solana/scripts/sol_read.py squads https://api.mainnet-beta.solana.com 7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM
python3 chains/solana/scripts/sol_read.py squads-vault - 7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM 0
python3 chains/solana/scripts/sol_read.py realm https://api.mainnet-beta.solana.com FVVXu18aNUqyFCfq8sGktPM62mqJAGaenv4z6UGUs5em
python3 chains/solana/scripts/sol_read.py governance-v2 https://api.mainnet-beta.solana.com EJ5kEb9XkQC4rbc7uM45xoLM8TiagGCLad5YpGtMyz4
```
