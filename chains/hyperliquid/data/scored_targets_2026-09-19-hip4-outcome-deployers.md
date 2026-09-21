# Hyperliquid: HIP-4 outcome deployers, scoring_build pass (2026-09-19)

Phase: scoring_build for a new target family (the ecosystem as a whole is
already at `deploy_testnet`, see `../deploy/README.md`; this pass does not
change that). Read-only, mainnet-only: official HyperCore info API, HyperCore
block-explorer endpoint and HyperEVM RPC (chain 999). No transaction, no key, no
write. Every figure below was read on 2026-09-19 between 18:44 and 19:14 UTC
(sections 1 to 5), or at the time stated where a section says it was re-read
during the review (about 20:07 to 20:10 UTC), and will drift.

Everything in this file is a **proposal**: a new controller shape, a new sizing
method and a promote/hold decision. It has now been through the adversarial
review that `AGENTS.md` ("Before committing") requires before committing a new
controller shape: three independent review lenses, every finding re-verified by a
separate agent told to try to refute it. 15 objections were confirmed, 2 were
refuted; every confirmed one was applied (section 10 lists what changed). That
review is the check on the scorer and the sizing code. It does **not** advance
any phase and does not promote any venue: a phase transition is proposed through
the maker-checker pipeline, never decided in this file.

## 1. Result in one table

| Venue | Deployer (k-of-n) | Weakest settlement key | adminKey / multisig / timelock / oracle / crossExposure | composite | Collateral locked | Face volume, last 24h | Decision |
|---|---|---|---|---|---|---|---|
| `out` | 3-of-4 | bare key (2 sub-deployers) | 10 / 15 / 0 / 15 / 100 | 9 | $1.19M | $1.46M | **HOLD** (closest to the bar) |
| `txyz` | 2-of-3 | bare key (2 sub-deployers) | 10 / 15 / 0 / 15 / **80** | 9 | $0.40M | $30K | **HOLD** |
| `skew` | 3-of-5 | bare key (1 sub-deployer) | 10 / 15 / 0 / 15 / 100 | 9 | $8K | $6K | **HOLD** (near-dormant) |

**No venue is promoted into `score_all()`.** None reaches the written scouting
rule of about $5M, nor the open interest at which the lightest HIP-3 dex was
promoted (section 4). The
scorer `score_hip4_outcome_deployer(venue)` is nevertheless written, tested and
generic, exactly as `score_hip3_dex(name)` is for the six unpromoted HIP-3
dexes: promoting a venue later is a small change (section 6). The scores
in this table are what the scorer produces today; they are **not published** in
`api/scores.json` or pushed anywhere.

The single most likely point of disagreement is `out` (section 4.3). Against the
one number this repo has written down for the ecosystem, the scouting selection
rule of about $5M (section 4.1), it is at 24% ($1.19M; 57% on the deliberately
generous upper bound). It is 15% of the lightest promoted HIP-3 dex by open
interest. It would clear only a floor at about $600K or below, the size of the
lightest target of any kind this ecosystem tracks (2.0x). I took the reading that
follows the written number and flag the other one rather than pick a constant.

## 2. What was measured, and how

### 2.1 Authority (re-read live; the nested multisig on `out` is new)

`{"type":"outcomeMeta"}` returns `deployers[]` with each venue's deployer and
`subDeployers` as `[variant, [addresses]]`. `{"type":"userToMultiSigSigners"}`
gives each address's `(threshold, authorizedUsers)`, `null` meaning a bare key.

| Venue | Deployer | Sub-deployers (each holds all 5 grants) |
|---|---|---|
| `out` | `0x0c46eb73fae2816f219fcf11f50d6d3c59b5819e`, 3-of-4 (`0x000af433...fb07`, `0x3d014abc...a1bd`, `0x588deb78...c0e1`, `0xcb3efe89...3329`) | `0x6947a610ef50f8b5d4b59abcd94dd75aaaa645b9`, `0xf1923927d7d2847191fb7ef8b1a16028aa5ae754`, both bare keys |
| `txyz` | `0x7aca09667816a4817b8bc697fb239ad42ff9f553`, 2-of-3 (`0x04777fee...c977`, `0xdad9fea2...41db`, `0xf35dde41...701f`) | `0x77ef1bbc0467f0ddde42e5a0e9ccd80369c55cc8`, `0x786864b48a102a047b9796c2541256e5f08bbe70`, both bare keys |
| `skew` | `0x08e9c89f46dccee91bdb85c6532eb93a4c335efe`, 3-of-5 (`0x0feed220...b5f093`, `0x12c13eea...25ce`, `0x28e88fc6...8782`, `0x47663bf7...d8a3`, `0x4d4509d7...6941`) | `0x1c867861e0cffb0eba07d9d94f716189c130dac6`, bare key |

All 8 addresses (3 deployers + 5 sub-deployers) return `eth_getCode` = `0x` on
HyperEVM, so METHODOLOGY.md 3.7 (CoreWriter identity) does not apply. Each
deployer delegates about 500K HYPE (out 506,904; txyz 500,418; skew 502,357,
about $46M each at $92.25): those are `delegatorSummary` reads, not a documented
HIP-4 requirement (the official page states a staking requirement for active
deployers and gives no HIP-4 amount). The only enforcement the page documents is
that a market contradicting its template's semantic restriction is "malformed and
slashable by validators". It does not say a wrong or early settlement is
slashable, and it would not restrain the holder of a stolen sub-deployer key. The
stake is therefore context: it is not credited as a deterrent and it is not a
delay.

**`out`'s deployer is nested and cyclic.** The table shows a 3-of-4 over four
keys. One of those four, `0x588deb78...c0e1`, is itself a 3-of-4 HyperCore
multisig whose signers include the deployer `0x0c46eb73...819e` and
`0x226b997f...2ccb`, which is in turn a 3-of-4 listing the deployer and
`0x588deb78...c0e1` again (`userToMultiSigSigners` at three levels; 10 distinct
addresses in all versus 7 at one level; `txyz` has 6 and `skew` 7, none nested).
METHODOLOGY.md 4.2 rule 2 does not expand nested multisigs, so no score uses this,
and this pass does not evaluate what threshold such a cycle effectively imposes or
whether HyperCore honours a multisig as a signer of another. The scorer now
discloses it (`reads.nestedMultisigSigners` and a `NESTED MULTISIGS` note) so the
"3-of-4" label is never read as the whole story.

### 2.2 Economic weight (new)

An outcome is not leveraged, so open interest has no direct analog. The analog
of "money a compromised root key could redirect" is the **collateral locked
behind live outcomes**: a share pays at most 1 USDC and 1 Yes + 1 No = 1 USDC
(official HIP-4 overview), and `settleOutcome`/`settleQuestion2` decide how
that collateral is split.

Source: `{"type":"spotMetaAndAssetCtxs"}` returns a context for every outcome
side, coin `#<10*outcome+side>` (official asset-ids page), with
`circulatingSupply` and `dayBaseVlm`. `totalSupply` on these coins is a
protocol constant (`184467440737095.53125`) and is not used.

Collateral is not "Yes supply" for questions, so it is derived from the full
collateralization identity and **checked on every read**:

* standalone outcome: Yes supply == No supply, collateral = Yes supply;
* question with members i = 0..N (fallback included): exactly one settles Yes,
  so for every possible winner `w`, `Yes_w + sum(No_j, j != w)` equals the
  collateral. That is equivalent to `Yes_i - No_i` being the same number `D`
  for every member, with collateral = `sum(No_i) + D` (`negate`/`merge` move
  supply between sides without changing this).

Worked example, question 198 (EPL winner, 7 outcomes, read 18:44 UTC): Yes
supplies 30941, 39152, 35534, 34389, 37784, 31166, 31369; No supplies 0, 8211,
4593, 3448, 6843, 225, 428. `Yes - No` is 30941 for all seven; collateral =
23,748 + 30,941 = **54,689**, and every one of the seven winner cases pays
exactly 54,689. Summing Yes supplies would have said 240,335.

Result of the check on the live set (236 outcomes, 23 questions, all venues):
**0 violations**. That is the internal consistency test that stands in for a
second source (HyperCore has no second RPC operator, METHODOLOGY.md section 2).

Volume: the Yes and No coins of one outcome report the same trades (per-venue
`dayBaseVlm` sums are identical on both sides, and `dayNtlVlm` of the two sides
adds up to the shares traded), so one side is used. Shares are the face-value
volume in USDC.

### 2.3 What the official page documents about settlement, and what it does not

Read from the deployer-actions page on 2026-09-19 (it is still labelled
"Testnet-only", which live mainnet state contradicts).

* **Documented bounds.** `settleFraction` is a decimal in [0, 1]. A standalone
  outcome may settle to any fraction; an outcome that belongs to a question must
  settle to exactly 0 or 1, with exactly one winner (sequentially, or all at once
  with `settleQuestion2`). `nameAndDescription` and `sideNames` must match the
  outcome exactly and `details` must be empty. A sub-deployer can only settle its
  deployer's own outcomes and questions, so a compromised settle key reaches that
  venue's book and no other (which is what the sizing in section 3 measures).
* **Not documented.** Any delay, any check of the value against the market's
  underlying, any bound on when a settle may happen, any dispute step.
* **Consequence for the scoring analogy.** `setOracle` (HIP-3) is a continuous
  push that the protocol clamps (1% per update, 2.5 s apart, 10x from the day
  open, METHODOLOGY.md 4.4). A settlement is a one-shot, unclamped decision inside
  the bounds above. The analogy "the settle value is caller-supplied, like a
  `setOracle` push" used in the first version of this note is therefore only
  partial, and the wording is corrected everywhere it appeared. Section 8 records
  what the chain shows on top of the docs.
* **The registration variants.** `registerStandaloneOutcomeFromTemplate` and
  `registerQuestionFromTemplate` set `deployerFeeScale` in [0, 10] on the new
  market (users then pay the base fee times `scale + max(scale, 1)`, up to 20x, of
  which up to 10x goes to the deployer; the scale is visible per market in
  `outcomeMeta`). `registerAndAssociateNamedOutcomeFromTemplate` adds an outcome to
  a LIVE question and credits the holders of the question's fallback-YES token with
  an equal balance of the new outcome's YES ("so existing 'other' positions keep
  their meaning"). None of them is documented to decide who receives
  already-locked collateral. They are left out of the root set by analogy with
  HIP-3, where `score_hip3_dex` likewise leaves its non-halt sub-deployer variants
  (`registerAsset`, `setDeployerFees`, ...) out of the set. That is a choice, **not
  a finding that they are harmless**: the association mechanism is designed to be
  neutral for existing positions, which this pass did not verify beyond the docs.
  Live, this changes nothing (every sub-deployer holds all five grants).

## 3. Sizing results

Read live with `scoring_build_2026_09_19_hip4.py size` (collateral is exact
under the identity above; `both sides` is a deliberately generous upper bound
that counts every outstanding Yes and No share as 1 USDC).

| Venue | Live outcomes | With supply | Traded in 24h | Collateral locked | Both-sides upper bound | Face volume 24h |
|---|---|---|---|---|---|---|
| `out` | 99 (16 questions) | 95 | 73 | **$1,190,351** | $2,837,931 | $1,458,571 |
| `txyz` | 77 (6 questions) | 60 | 41 | **$397,475** | $795,916 | $30,446 |
| `skew` | 52 (0 questions) | 18 | 8 | **$7,945** | $15,890 | $6,230 |
| protocol-run recurring (no venue) | 8 (1 question) | 7 | 7 | $105,275 | $210,550 | $84,979 |

(Snapshot of 19:10:47 UTC. `fullyVerified` was true for every row.)

**Stability over the session.** Three full snapshots between 18:44 and 19:11
UTC: `out` $1,188,668 / $1,189,155 / $1,190,351; `txyz` $396,563 / $396,641 /
$397,475; `skew` $8,171 / $8,171 / $7,945. The counts of live outcomes did not
move (99 / 77 / 52). This shows no noise at the scale of the decision. It does
not show what happens over days.

**Re-read during the review, 20:07 UTC.** Collateral (exact identity) / both-sides
upper bound / face volume 24h: `out` $1,173,721 / $2,803,105 / $1,390,104 (99 live
outcomes); `txyz` $400,181 / $801,328 / $33,111 (77); `skew` $7,913 / $15,826 /
$6,271 (52). `fullyVerified` true for every row, no unverified group, 0 outcome
without market data. Same order of magnitude as the 19:10 snapshot; nothing
crosses any threshold discussed below.

**Sustained activity** (`size --history`; face volume per UTC day of the
venue's currently live outcomes, so a lower bound: outcomes that already
settled cannot be listed):

| Day (UTC) | out | txyz | skew |
|---|---|---|---|
| 09-12 | 728,252 | 6,726 | |
| 09-13 | 428,872 | 9,120 | |
| 09-14 | 670,620 | 24,772 | |
| 09-15 | 1,078,497 | 20,775 | |
| 09-16 | 1,399,676 | 21,978 | |
| 09-17 | 799,582 | 10,176 | 200 |
| 09-18 | 1,447,460 | 321,674 | 5,337 |
| 09-19 (to 19:10) | 1,122,491 | 21,021 | 1,289 |

`out` trades every day at $0.4M to $1.4M. `txyz` is $7K to $25K a day except
one $322K day. `skew` only has data for 3 days (its live markets are new).

**Where `out`'s collateral sits** (read about 19:20 UTC, total $1,190,484).
$904,515 (76%) is in 9 long-dated standalone BTC/HYPE markets that expire
2026-10-01 (largest: HYPE touch $100, $162,765; BTC touch $100,000, $135,504;
BTC binary $100,000, $117,041). Sports and policy questions hold $230,504
(tournament winners $154,667, match results $70,653, a policy-rate question
$5,184) and $55,465 is short-dated standalone markets. The 9 long-dated markets
settle in 12 days; whether the venue lists a comparable book afterwards is not
knowable from a snapshot. The venue is also at its structural cap:
`outcomeDeployerLimits` reports 1 active slot remaining (99 live), so the cap is
100 active outcomes per deployer (`txyz` 23 remaining with 77 live, `skew` 48
remaining with 52 live: also 100). The daily allowance is at least 500 new
outcomes (`txyz`, which deployed none today, reads 500 remaining).

A caution that applies to any supply-based figure: minted supply includes
inventory a market maker holds on both sides, so it is not all directional
user exposure. The same caveat applies to HIP-3 open interest.

## 4. The bar, and why nothing clears it

### 4.1 What is on record

The first version of this section said that no number had ever been written down
for the bar. That was wrong (adversarial review, significance lens, finding F1).
Three things are on record:

1. **A written number, for scouting.** `scouted_targets_2026-09-17-run2.md`,
   the run that produced this ecosystem's tracked HyperCore targets, states its
   selection rule as "DefiLlama TVL or HyperCore open interest above about $5M",
   plus an authority address from a primary source and the full authority chain
   read on chain. It is a scouting selection rule, not a promotion rule written
   into `scorers.py` (which states its promotion criterion only in words:
   "promote by real usage, not listed-market count"), but it is the only number
   the repo has written for this ecosystem.
2. **The promotion decisions**, re-read live at 19:13 UTC:

| HIP-3 dex | Open interest | Net deposit | Decision then |
|---|---|---|---|
| xyz | $3,750,722,006 | $1,063,261,416 | promoted (first target) |
| io | $56,325,711 | $39,888,740 | promoted |
| para | $16,386,484 | $10,740,744 | promoted |
| mkts | $7,696,651 | $5,193,299 | promoted (lowest promoted dex) |
| hyna | $0 | $244,177 | not promoted, dormant |
| cash | $0 | $97,402 | not promoted, dormant |
| km | $0 | $23,628 | not promoted, dormant |
| vntl | $0 | $7,042 | not promoted, dormant |
| flx | $0 | $5,648 | not promoted, dormant |
| abcd | $0 | $0 | not promoted, dormant |

   `mkts` needs a date on its number. When it was promoted on 2026-09-17 its open
   interest was recorded as "about $6.4M" in the scouting note and "about $6.7M"
   in the `scorers.py` docstring (two readings the same day); $7.7M is today's
   re-read, not its open interest at promotion. So the promoted set sits at about
   $6.4M to $7.7M for its lightest member, just above the written $5M rule, and
   the dormant dexes at $0.
3. **Floors of the same size elsewhere.** The lightest tracked target of any
   kind here is Ventuals vHYPE, a HyperEVM product: 6,317 HYPE delegated, about
   $583K. A different ecosystem's practice is similar: the Robinhood Chain
   rotation audit (repo-root `data/rotation_audit_2026-09-19-robinhood-chain-index14.md`)
   leaves leads unpursued when they are under "the ~$600k floor of the smallest
   prior addition" (a TVL-based practice for that chain, not a rule for this one).
   Other HyperCore-native targets are far heavier (HLP $187M, Unit
   UBTC/UETH/USOL $552M / $157M / $40M outstanding).

HIP-4 has no net-deposit figure (collateral only exists as outstanding shares),
so the like-for-like comparison is open interest, i.e. outstanding positions.

### 4.2 Applying it

| Venue | Collateral vs written $5M rule | Both-sides upper bound vs $5M | Collateral vs `mkts` open interest ($7.70M) | Collateral vs Ventuals ($583K) |
|---|---|---|---|---|
| `out` | 24% | 57% | 15% (37% on the upper bound) | 2.0x |
| `txyz` | 8% | 16% | 5% (10%) | 0.68x (1.4x on the upper bound) |
| `skew` | 0.16% | 0.32% | 0.1% (0.2%) | 0.01x |

Rule applied: **promote only what clears the bar, and the bar the repo has
written is about $5M of TVL or open interest, consistent with the lightest
promoted dex.** All three venues are below it, on the exact measure and on the
most generous one (`out`'s upper bound is $2.84M). The decision therefore no
longer rests on a gap the project "never ruled on"; it rests on a written number.
What stays a judgment call: that number was written for TVL and open interest,
and HIP-4 collateral is an analog of open interest (section 2.2), not the same
quantity, so a reviewer can still argue for an outcome-specific floor.

I did not choose one. Picking, say, $1M would be exactly the uncalibrated
constant the project's "don't guess a number" rule forbids.

### 4.3 The sensitivity that matters

If the reviewers or the maintainer hold that the floor is the **lightest tracked
target of any kind** (Ventuals, about $583K, close to the Robinhood practice of
about $600K) rather than the written $5M, then `out` clears ($1.19M, 2.0x) and
`txyz` does not on exact collateral (0.68x; it would on the both-sides upper
bound). `skew` fails under every reading: $8K of collateral, 8 of 52 markets
traded in 24h, comparable in kind to `flx`'s "near-zero".

Why I did not take that reading: it would override a written number with the
precedent of a different product family. Ventuals was promoted as a HyperEVM
product found by chasing a deployer's bytecode, with verified source, not through
the open-interest bar; the Robinhood floor is TVL on another chain. `out` is
clearly not dormant ($1.46M a day, 73 of 99 markets traded), so this is a
calibration question, not a doubt about the venue being real.

Re-open triggers, all checkable with the same command: `out` collateral
sustained above the heaviest number a reviewer accepts as the floor; or a
maintainer-set floor for outcome venues; or the 2026-10-01 markets being
re-listed at a similar size.

## 5. What the scorer computes (held venues, not published)

`score_hip4_outcome_deployer(venue)` in
[`../scripts/scoring_build_2026_09_19_hip4.py`](../scripts/scoring_build_2026_09_19_hip4.py).
No new formula and no new constant: `weakest`, `kn`, `admin_key_score`,
`key_score`, `composite` from `methodology_test.py`, unchanged.

| Field | Rule | Live value (all 3 venues) |
|---|---|---|
| root-control set | deployer + every `settleOutcome` / `settleQuestion` sub-deployer | includes the bare-key sub-deployers |
| weakest key | minimum of `(k, -n)` over the set (rule 4.2), ties resolved to the lowest address | a bare key `(1, 1)` |
| adminKeyScore | `admin_key_score(k, n)` (4.6) | 10 |
| multisigScore | `key_score(k, n)` (4.6) | 15 |
| oracleAuthorityScore | same weakest key: the settle key supplies `settleFraction` itself (a partial analogy with `setOracle`, section 2.3) | 15 |
| timelockScore | 0, no delay documented on `settleOutcome`, `settleQuestion2`, `setSubDeployers`; slashing is not credited (section 2.1) | 0 |
| crossExposureScore | `100 - 20 * (other HIP-3 dexes + other outcome venues sharing a root key)` | out 100, **txyz 80**, skew 100 |
| compositeScore | `composite(admin, multisig, timelock)` | 9 |
| l1CappedComposite | `min(9, 26)` (added by `score_all()`, not the scorer) | 9 |

The provisional numbers in the scouting note (10 / 15 / 15 / 0 / 9) are
reproduced exactly. What the scouting note did not have: the cross-exposure
number.

Judgment calls (the analogy is the only non-mechanical part; each is disclosed
in the scorer's docstring and notes):

1. **Settlement, not registration, is the root-control action.** The registration
   variants are left out of the root set by analogy with HIP-3, not because they
   are known to be harmless (section 2.3: fee scale up to 20x on new markets,
   outcomes added to a live question). A venue with split grants therefore carries
   `reads.ifRegistrationOnlyKeysWereCounted` (the score if those keys were
   counted) and a `SENSITIVITY` note, so the size of the choice is visible. A unit
   test covers a split grant; on all three live venues every sub-deployer holds all
   five grants, so no live number depends on it.
2. **The deployer stays in the set** even when it is stronger than every
   sub-deployer, because `setSubDeployers` is not in the sub-deployer variant
   list of the official page (deployer-only), so it can always grant itself the
   settle variants. Same reasoning as METHODOLOGY.md 4.2 rule 3.
3. **`oracleAuthorityScore` reuses the settlement key.** The settle key supplies
   the result itself and nothing documented binds it to the underlying, so the
   weakest settle key is the honest reading; the `setOracle` analogy is partial
   (no clamp, one-shot). It is not a `composite()` input, so it cannot move any
   headline number.
4. **A grant the scorer does not classify raises.** The page lists five variant
   names and says the `settleQuestion` grant authorizes `settleQuestion2`, so the
   naming has already drifted once. A non-empty grant outside the five makes the
   scorer raise (`Hip4ReadError`) instead of silently leaving its holder out of the
   root set.

## 6. Promoting a venue later (reference, not applied)

```python
# chains/hyperliquid/scorers.py
from scoring_build_2026_09_19_hip4 import score_hip4_outcome_deployer

def score_hip4_out(_unused_arg=None) -> dict:
    return score_hip4_outcome_deployer("out")

SIMPLE_SCORERS = [..., score_hip4_out]
```

and update `test_no_hip4_venue_is_registered_in_score_all_yet` in
`scripts/lib/tests/test_hyperliquid_hip4_outcome_deployers.py` in the same
commit. The tests `test_a_promoted_venue_gets_the_l1_cap_and_keeps_its_scores`
and `test_the_l1_cap_actually_binds_on_a_strong_promoted_venue` already show the
entry going through `score_all()`'s isolation and L1 cap (the second with a case
where the cap lowers the value).
If `txyz` is ever promoted, `score_hip3_dex("xyz")` should count it in
`crossExposureScore` too (100 becomes 80), since the relation is symmetric and
today `xyz` only compares against other dexes.

## 7. New facts and corrections to the scouting note

**A shared signer set between `txyz` and HIP-3 dex `xyz`.** The scouting note
said "zero address overlap" with the tracked roots. That compared deployer
addresses. Their multisig signers are the same three keys with the same
threshold: `txyz` deployer `0x7aca...f553` and `xyz` deployer `0x8880...0888`
are both 2-of-3 over `0x04777fee...c977`, `0xdad9fea2...41db`,
`0xf35dde41...701f`. That is consistent with the trade[XYZ] operator running both (its docs already
describe a `txyz` deployment), but the chain only shows the shared keys, not who
holds them. It is the one hit
of `scoring_build_2026_09_19_hip4.py cross-check`, which harvested every
address in the 15 tracked targets' reads and notes (54 addresses) and intersected
them with each venue's keys: `out` and `skew` have zero overlap, `txyz` overlaps
only `xyz`. The first run expanded signers and Safe owners one level (99
addresses). The review found that `out`'s deployer sits in a nested cycle, so the
tool was changed to expand recursively (4 levels, cycles cut) and re-run during
the review: 15 tracked targets, 54 harvested addresses, 100 after expansion, keys of
each venue at all levels `out` 10, `txyz` 6, `skew` 7, and the same result (`out`
and `skew` no overlap, `txyz` only `xyz`'s three signers). `crossExposureScore = 80`
for `txyz` comes from the runtime check (one level of signers); the cross-check
tool is a one-off, not a runtime input.

**Nested multisigs on `out`** (section 2.1): the deployer's signer set contains a
multisig that contains the deployer. Not a scouting-note claim, but the scouting
note's "3-of-4 deployer" description omitted it.

**trade[XYZ]'s own docs and the chain disagree on `txyz`.** The operator's docs
(`docs.trade.xyz`, a "HIP-4 metadata / Draft status" table) list the venue `txyz`
with outcome deployer `0x88806a71...0888` (the address the same docs list as the
HIP-3 dex `xyz` deployer), one settlement sub-deployer `0x8EF95FA2...9D57`, and
"Currently the `deployerFeeScale = 0`". Live, the `txyz` deployer is
`0x7aca0966...f553`, its sub-deployers are `0x77ef1bbc...5cc8` and `0x786864b4...be70`,
`0x8EF95FA2...9D57` appears nowhere in `outcomeMeta` or `perpDexs`, and `txyz`'s 77
outcomes carry no `deployerFeeScale` field in `outcomeMeta` (`out` and `skew` show
"1.0"). Nothing here settles which side is stale. What holds either way: `0x8880...`
and `0x7aca...` are both 2-of-3 over the same three signers.

**Two miscounts in the scouting note, corrected here.**

* "8 unique sub-deployers": the 8 are the 3 deployers plus **5** sub-deployers
  (out 2, txyz 2, skew 1). The claim that all sub-deployers are bare keys
  stands.
* Counts drifted: 249 outcomes / 25 questions / venues 100 / 87 / 54 on the
  first read became 236 / 23 / 99 / 77 / 52 by 18:44 UTC (markets settle and
  new ones list). 8 more outcomes belong to no deployer: the protocol-run
  recurring BTC/ETH/SOL outcomes ("automatically deployed and settled by the
  protocol", official page). Per the official page they are settled by the protocol
  itself, not by a deployer key, so they are out of this family; they hold $105K
  and are not scored here.

## 8. What the chain shows about settlement, and what is still not established

### 8.1 Observed on chain (read-only, re-derived during the review)

`scoring_build_2026_09_19_hip4.py history` reads the block explorer's
`userDetails` for each venue's deployer and sub-deployers. It returns the 300
latest transactions per address, so **every count is a lower bound over a window**,
not a total. Read 2026-09-19 at 20:09 UTC:

* **Volume of evidence.** 391 successful `settleOutcome` actions, 0 failed, across
  the 5 sub-deployers (and the 3 deployers, which never settle in the window).
* **Settlement is not gated by the market's stated time.** Of the 357 settles whose
  description carries a stated time (34 do not), 16 succeeded more than one hour
  before the stated time of their own market. One is
  legitimate under its template: `out`, outcome 1251, a `priceTouch` on HYPE with
  target 90 and stated time 2026-10-01, settled at 1 on 2026-09-18 10:34 UTC (the
  template says the market "can settle as soon as a touch occurs"). **The other 15
  are `binaryPrice` markets on `skew`, all settled at `0.5`, 62.8 to 170.7 hours
  before their stated time** (2026-09-18: 6 BTC markets at 15:13 to 15:14 UTC, 9 ZEC
  markets at 17:18 to 17:20 UTC).
* **The protocol accepts a value outside the template's Yes/No text.** The
  `binaryPrice` template description says the market resolves to Yes if the price
  is above the threshold at the stated time and otherwise to No, with a fallback
  only for a delisted perp. The 15 settles at 0.5 above executed with no error. The
  page allows any fraction for a standalone outcome. Whether a 0.5 settle counts as
  "malformed" under the template's `semanticRestriction` (for `binaryPrice`: the
  market must refer to the price of a Hyperliquid perp) is not stated; the only
  enforcement the page documents is validator slashing of malformed markets after
  the fact. So nothing at settlement binds the value to the Yes/No text, and
  nothing binds the moment to the stated time.
* **What this does not show.** Intent. The 9 ZEC settles carry the same thresholds
  as 9 ZEC registrations made at 17:13 to 17:15 UTC, and 9 new ZEC registrations
  with different thresholds follow at 17:24 to 17:26 UTC: that reads like the
  operator withdrawing its own mistakes. That is an inference from timing, not
  established. It also does not show whether the 0/1 settles that make up the rest
  were correct against the underlying (not re-checked here).
* **The bare sub-deployer keys are operated as always-online automation.** In the
  latest 300 transactions, `out`'s `0x6947a610...` signed 150 registrations and 150
  settles over about 31 hours (2026-09-18 13:15 to 09-19 20:00 UTC), each settle
  5.3 to 13.7 seconds after the market's stated time (median 8.3, n = 150); `skew`'s
  `0x1c867861...` settles its short-dated markets 20.4 to 164.4 seconds after the
  stated time (median 22.5, n = 125). `extraAgents` is empty and `userToMultiSigSigners`
  is `null` for all 5 sub-deployers, so it is the bare key itself that signs. The
  deployers' own multisigs act rarely: the last action of each was a
  `setSubDeployers` (`out` 2026-09-04, `txyz` 2026-09-17, `skew` 2026-08-29). The weak link is
  therefore a key in continuous use, not a cold one.

These observations settle two questions the first version of this note left open
("whether the protocol validates `settleFraction`", "whether settlement is
time-gated"): in the direction of the scores already computed (no validation and
no gate are credited), not against them.

### 8.2 Still not established

* **Who operates the keys**, and how the always-online sub-deployer keys are held
  (an HSM or KMS is invisible from the chain). Not attributed, not inferred.
* **Whether HyperCore honours a multisig as a signer of another multisig**, and
  the effective threshold of `out`'s nested cycle (section 2.1). Not evaluated.
* **Whether the registration-only powers are value-neutral in practice.** By the
  docs they do not decide who receives locked collateral; the association
  mechanism (`registerAndAssociateNamedOutcomeFromTemplate`) is designed to be
  neutral for existing positions but was not verified beyond the docs. No live
  number depends on it.
* **Which of trade[XYZ]'s docs or the chain is stale for `txyz`** (section 7).
* **The floor for outcome venues.** A written scouting rule of about $5M exists;
  whether it applies to HIP-4 collateral is the reviewers' or the maintainer's
  call (section 4.3).
* **HyperCore reads rest on one operator's API** (gap G9). The collateral identity
  holding on 236 outcomes with 0 violations is the consistency check, not an
  independent source. The explorer endpoint is the same operator.
* **Snapshots.** Economic weight is a point-in-time figure over live outcomes.
  Settled outcomes are not listed, so history is a lower bound.
* The one-off cross-check covers the 15 currently tracked targets as harvested
  from their reads/notes; a tracked address that appears in neither would be
  missed. It uses a regex, so it can only over-include. It expands signers
  recursively (4 levels, cycles cut); its orchestration function has no unit test,
  only its pure helpers do.
* Held venues are not run through `push_scores.py` (nothing is wired), so their
  oracle-key handling was not exercised beyond a unique deployer address.

## 9. Reproduction

```bash
# sizing, all venues (about 5 s); --history adds 7 UTC days per venue (about 2.5 min)
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py size
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py size --history

# the scorer on one venue, full JSON with reads and notes
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py venue out
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py venue txyz
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py venue skew

# what the venues' keys did with settleOutcome (explorer, 300 latest txs per address, a few seconds)
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py history
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py history skew

# one-off: every tracked address vs each venue's keys, signers expanded recursively
# (about 2.5 min, runs score_all(); check that trackedTargets is 15, a skipped scorer shrinks the universe silently)
python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py cross-check

# raw requests behind the numbers (POST https://api.hyperliquid.xyz/info)
{"type":"outcomeMeta"}                                   # venues, deployers, sub-deployers, questions
{"type":"spotMetaAndAssetCtxs"}                          # circulatingSupply, dayBaseVlm per "#<10*outcome+side>"
{"type":"outcomeDeployerLimits","venue":"out"}           # active / daily capacity left
{"type":"userToMultiSigSigners","user":"<address>"}      # (threshold, signers) or null
{"type":"delegatorSummary","user":"<deployer>"}          # slashable stake
{"type":"candleSnapshot","req":{"coin":"#12090","interval":"1d","startTime":..,"endTime":..}}
{"type":"outcomeTemplates"}                              # template texts (binaryPrice, priceTouch, ...)
# POST https://rpc.hyperliquid.xyz/explorer  {"type":"userDetails","user":"<address>"}   # 300 latest transactions
# HIP-3 comparison (section 4.1): scout_2026_09_17_run2.dex(<name>) for each name in {"type":"perpDexs"}

# tests and sensors
python3 -m unittest scripts/lib/tests/test_hyperliquid_hip4_outcome_deployers.py
python3 -m unittest discover -s scripts/lib/tests
python3 scripts/validate_all_scorers.py --ecosystem hyperliquid
```

Official sources: [HIP-4 overview](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-4-outcome-markets),
[HIP-4 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-4-deployer-actions),
[asset ids](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids),
read via `llms-full.txt` on 2026-09-19.

## 10. Adversarial review (2026-09-19): what was confirmed and what changed

Three independent lenses (formula and code, authority and evidence, significance
of the decision), each finding re-checked by a separate agent instructed to try to
refute it. 15 objections confirmed, 2 refuted; nothing was rubber-stamped, and the
two on-chain claims (settle timing, key cadence) were re-derived from the explorer
rather than copied, which is why `history` now exists as a subcommand. No venue
had to be removed from the scorer: none was published, and none of the confirmed
objections moves a score (all three venues still score 10 / 15 / 0 / 15 / 9, `txyz`
cross-exposure 80).

| Lens / id | Severity | Confirmed | What changed |
|---|---|---|---|
| significance F1 | major | A written scouting rule of about $5M exists; section 4 said no number was ever written | Sections 1, 4.1 to 4.3 rewritten around the written number; the decision (hold all three) is unchanged and now rests on it; the residual calibration question is stated as such |
| authority A1 | major | "validator-priced settlement" survived in the scouting finding for these venues; contradicted by the new justification; METHODOLOGY 4.4 had no HIP-4 row | Inline correction plus a third item in the scouting finding's update paragraph; new HIP-4 row in METHODOLOGY 4.4; `oracleAuthorityScore` wording corrected everywhere (partial analogy, no clamp, one-shot) |
| formula F2 | minor | Documented `settleFraction` constraints omitted; `setOracle` analogy imprecise | Section 2.3 (documented bounds, what is not documented); scorer docstring and oracle note; METHODOLOGY 4.1 and 4.4 |
| formula F3, authority A5, significance F5 | minor | "the only deterrent is ex-post slashing of the deployer's stake" overreached: the page documents slashing only for malformed markets | Timelock note, docstring, section 2.1 and METHODOLOGY reworded: slashing is context, never credited as a deterrent for settlement; the stake figure is a `delegatorSummary` read, not a documented requirement; a test locks the wording |
| formula F4 | minor | `mkts` "$7.7M" presented as its promotion baseline; it was about $6.4M / $6.7M then | Section 4.1 dates both numbers; `scorers.py` docstring states the promotion-time and current values |
| formula F5, authority A4 | minor | Registration variants "cannot redirect collateral / only create markets" stated categorically; the page documents fee scale up to 20x and association into a live question | Wording changed to "left out by analogy with HIP-3, not known to be harmless"; new `ifRegistrationOnlyKeysWereCounted` block and `SENSITIVITY` note for any venue with split grants; tests |
| formula F6 | minor | A holder of an unrecognised grant name was silently left out of the root set | Non-empty unclassified grant now raises `Hip4ReadError`; tests |
| formula F7 (a to h) | minor | Weak or missing tests (8 mutations survived) plus a dead `collateral < 0` guard | The HIP-4 test file went from 53 to 82 tests (full suite 844 to 873); the dead guard replaced by a real negative-supply check (excluded, flagged), the impossibility of a negative collateral is proved in the docstring; the L1-cap test now uses a case where the cap binds; 25 manual mutations of the scorer, all killed |
| authority A2 | minor | Two "not established" items were resolvable read-only on chain | Section 8.1 (15 `binaryPrice` settles at 0.5, 62.8 to 170.7 h early, all accepted; one legitimate early `priceTouch` settle); new `history` subcommand and tests; the verifier's "16 settles up to 12.6 days early" was re-derived: it is 15 plus the legitimate `priceTouch`, and the 12.6 days belongs to that one |
| authority A3 | minor | "Hot key" was said to be neither attributed nor inferred | Section 8.1: observed as always-online automation (cadence and count re-derived), operator still not attributed |
| significance F3 | minor | `out`'s deployer is a nested, cyclic multisig, undisclosed; `cross-check` expanded one level | Section 2.1 and 7; scorer discloses `nestedMultisigSigners`; `cross-check` recursive and re-run (same result); tests |
| significance F4 | minor | trade[XYZ]'s docs list another deployer address for `txyz` than the chain | Section 7 records the disagreement without resolving it |

**Not resolved by the review, on purpose.** (1) The floor for outcome venues is a
calibration call for the reviewers or the maintainer. (2) The exclusion of
registration-only keys is by analogy, now visible instead of asserted. (3) The
effective threshold of `out`'s nested cycle is not evaluated. (4) Which of the
operator's docs or the chain is stale for `txyz`. (5) The `cross-check`
orchestration function has no unit test (its pure helpers do). (6) Two further
objections were refuted by their independent verifiers and are not reproduced here.

**Phase and pipeline.** Nothing in this pass advances the ecosystem's phase or
touches `ecosystems.json` or the maker-checker pipeline. This review checked the
scorer and the sizing code; whether HIP-4 targets should ever enter `score_all()`,
and at which floor, remains a separate decision.
