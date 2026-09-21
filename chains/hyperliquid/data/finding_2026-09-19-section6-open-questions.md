# Hyperliquid: closing three of METHODOLOGY.md section 6's open questions (2026-09-19)

Read-only, mainnet-only pass (no testnet/devnet write, no key, no funding
request). Live reads: `python3 chains/hyperliquid/scripts/scout_2026_09_19_section6.py bridge-vs-l1`
and `... hip4-deployers` (new script, reuses
`scout_2026_09_17_run2.py`'s own HTTP/RPC helpers rather than duplicating
them), plus direct `curl`/docs reads recorded inline below for the second
question, which has no live endpoint to script against. Values below were
read 2026-09-19 around 00:50-01:10 UTC and will drift (validator set,
outcome-market inventory).

Scope note: the "run a non-validator with `--serve-info`" item, the
`setMarginTableIds`/`setMarginModes` item, and the already-resolved-in-place
"para/mkts EVM-proxy" narrative bullet in section 6 are NOT touched by this
pass -- only the three items this pass was asked to resolve.

## 1. Bridge2 validator set (epoch 7) vs the current 27 active L1 validators

**Resolved: zero overlap, and the bridge's own quorum is structurally much
smaller than the L1's active validator set -- not just differently keyed.**

The last validator-set-changing call on `Bridge2` was decoded from tx
[`0x62a66b84...246b4`](https://arbiscan.io/tx/0x62a66b841b44845f9aa6a2c40b7aea017eedb791b95a5f20bd312960320246b4)
(Arbitrum One, block 399539914, 2025-11-12T16:59:15Z). One correction to
the open question's own wording: this call is `emergencyUnlock(...)`
(selector `0x9770e2c8`, the cold-quorum path used to atomically unlock and
replace the validator set together), **not** `updateValidatorSet(...)`
(selector `0xe3e6c441`, the ordinary hot-quorum path, which requires a
separate later `finalizeValidatorSetUpdate()` after the 200 s dispute
period). Both take the identical `ValidatorSetUpdateRequest` shape and
both ultimately write the same `hotValidatorSetHash`/`coldValidatorSetHash`
via the same internal `updateValidatorSetInner`, so the decode and the
comparison below are unaffected by which of the two functions was used --
but "the last `updateValidatorSet`" is not quite the right function name,
and is corrected here rather than silently carried forward.

Confirmed this IS still the live, current, fully-finalized state (not
superseded by a later, undecoded call): live `epoch()` reads `7` (matches
the decoded tx), and `pendingValidatorSetUpdate().updateTime` reads `0`
(no unfinalized change in flight) while its `updateBlockNumber` (399539914)
matches the epoch-7 tx's own block exactly.

Decoded epoch-7 set: 4 hot addresses, 4 cold addresses, equal power (1
each) -- the same 3-of-4 structure `scripts/scoring_build_2026_09_18.py::
score_bridge2()` already scores (`admin_key_score(3,4)=65`,
`key_score(3,4)=59`), confirmed independently here from a fresh decode
rather than assumed from that prior pass:

| Set | Addresses |
|---|---|
| Hot | `0xEF2364...37Fc`, `0xda6816...d79B`, `0x58E1b0...132e`, `0x263294...1504` |
| Cold | `0x8003FD...90E91`, `0x86d6AE...52F628`, `0xE346B4...74C6e7`, `0x5a92b4...305ede` |

Compared against live `validatorSummaries` (35 registered, 27 active) --
both the `validator` identity address and the `signer` hot-key address of
every entry, active or not: **zero overlap**, in either direction.

This confirms and slightly extends what `score_bridge2()`'s own notes
already disclosed (that specific check was already live-verified in the
2026-09-18 scoring_build pass; this pass independently re-derives it from
a fresh decode and a fresh `validatorSummaries` read, rather than trusting
the prior pass's number). The extension: the bridge's hot/cold set is not
merely a DIFFERENTLY-KEYED subset of the L1 validators -- it is a fixed
**4-member equal-weight committee**, categorically smaller than the
27-validator, stake-weighted active set the L1 itself now runs. `Bridge2.sol`'s
own header comment describes a design where "each validator has a hot and
cold wallet" and where set updates are meant to track L1 validator
membership changes at each epoch -- the live state does not match that
description. Whether this reflects an intentional freeze (the docs already
say the bridge is deprecated in favor of Circle CCTP, <10% of HyperCore
USDC) or a sync process that simply stopped keeping pace with a growing L1
validator set cannot be determined from the chain alone; no primary source
states which. Recorded here as a disclosed, unresolved interpretive
question -- not folded into the score either way.

**Effect on `adminKeyScore`/`multisigScore`**: none. Both are already
derived from the bridge's own real 3-of-4 on-chain threshold (not from a
comparison to the L1 validator set, which the formula never used as an
input), and that structure is now independently re-confirmed rather than
merely carried forward. `crossExposureScore` also stays 100 (unaffected --
that field tracks overlap with OTHER *tracked* Hyperliquid targets in this
oracle, a check already run and already zero; see `score_all()`'s live
output, reproduced below).

## 2. L1 upgrade notice / lead-time practice

**Resolved: no primary source exists. The score stays 0, and here is the
actual search trail so a future pass does not have to repeat it blind.**

Checked, all 2026-09-19:

- Full docs text (`hyperliquid.gitbook.io/hyperliquid-docs/llms-full.txt`,
  9,137 lines): every occurrence of "upgrade" read in context. The only
  operationally specific statement is the existing one METHODOLOGY.md 3.1
  already cites (orders "do not fill during the post-only period of a
  network upgrade") -- no lead time, no advance-notice commitment, no
  minimum window.
- Docs sitemap (`sitemap-pages.xml`, `support/sitemap-pages.xml`): no
  changelog, release-notes, governance, or roadmap page exists in the
  index at all.
- `hyperliquid-docs/governance` (a guessed path): 404.
- `forum.hyperliquid.xyz`, `gov.hyperliquid.xyz`: DNS does not resolve
  (connection failure, not a page-not-found) -- no governance-forum
  subdomain exists.
- GitHub org `hyperliquid-dex`: full repo list re-enumerated (10 repos,
  unchanged from METHODOLOGY.md 3.1's own finding) -- no
  changelog/release/governance repo among them.
- `hyperliquid-dex/node` releases and tags (GitHub API): **both empty
  arrays** -- there is no tagged/versioned release history for the node
  binary to derive a cadence or announcement lead time from, consistent
  with the binary itself being closed-source and auto-pulled via
  `hl-visor`'s signature check (METHODOLOGY.md 3.1).
  `hyperliquid-dex/node`'s last 100 commits (fetched live) are entirely
  seed-node/config documentation and validator-onboarding README edits,
  none referencing an upgrade schedule or notice policy.
- `hl-node` README itself (`raw.githubusercontent.com/hyperliquid-dex/
  node/main/README.md`, 565 lines): re-read in full for "notice",
  "advance", "coordinate", "announce" -- no hits beyond the same
  post-only-period-adjacent binary-verification passage already cited.
- Status page guesses (`status.hyperliquid.xyz`): does not resolve.
  `hyperliquid.xyz/status`, `hyperliquid.xyz/governance`: both 403
  (Cloudflare-gated, not inspectable via a plain unauthenticated request;
  disclosed as a genuine access limitation, not silently treated as "no
  page exists" -- the sitemap and docs-index checks above are the stronger
  evidence for the "no page" conclusion, this one is just inconclusive).
- Discord/Telegram are the documented community channels (`llms-full.txt`
  lines 22, 163, 1972, 2130) for informal announcements, but neither is a
  primary source with a stated, citable lead-time commitment, and this
  project does not treat an informal chat announcement as equivalent to a
  documented policy (same standard already applied throughout this file to
  the "Hyper Foundation" validator-label question in METHODOLOGY.md 3.2).

**Conclusion**: no primary source -- official docs, the validator/node
GitHub org, or a governance forum -- states a minimum or typical notice
period before an L1 upgrade. `timelockScore = 0` for the L1 target (already
the value in `scorers.py`/`methodology_test.py`) is confirmed justified,
not merely unresolved. No score change.

## 3. HIP-3\* and HIP-4 mainnet status

**HIP-3\* (`isStar`): still testnet-only. No change.** The live docs page
(`for-developers/api/hip-3-deployer-actions`, section "## HIP-3\*") states
this explicitly in its own heading as of 2026-09-19 ("HIP-3\* (testnet-only)").
No further live check contradicts it (no mainnet `perpDexs` entry exposes
`isStar: true` -- none of the 10 live mainnet HIP-3 dexes' schemas need
re-checking for this since the feature is a deploy-time flag documented as
gated to testnet at the protocol level, not a per-dex opt-in visible after
the fact). Section 6's own open item on this stands: re-check again once
mainnet actually ships it.

**HIP-4 (outcome markets): live on MAINNET, and materially larger than the
docs' own description of it -- a genuinely new, previously-undocumented
root-control surface, not yet in `scorers.py`.**

The outcome-markets overview page itself already hints at this ("Multi-
outcome markets ... are not part of the **initial** mainnet release",
implying an initial release exists), but the separate API reference page
"HIP-4 deployer actions" still headers itself "Testnet-only" as of
2026-09-19 -- the two pages disagree. Live mainnet state resolves the
disagreement: `POST {"type":"outcomeMeta"}` against
`https://api.hyperliquid.xyz/info` (mainnet, confirmed distinct from
`-testnet.xyz` by comparing `{"type":"meta"}` universe sizes: 234 mainnet
vs 212 testnet, live) returns:

- **249 live outcome markets** and **25 questions**, spanning far more than
  "the first market is a recurring binary [BTC] outcome": crypto price
  touch/threshold markets (BTC, HYPE, and Pyth-sourced indices like
  `XYZ100`), sports contests (winner/draw/participant/tournament, e.g. EPL,
  UEFA Champions League, NFL, MLB), company IPO confirmation, and central
  bank policy-rate direction markets.
- **3 active outcome-deployer venues**, each a real address with the SAME
  `outcomeDeploy`/`setSubDeployers` shape "HIP-4 deployer actions" (the
  page still marked testnet-only) documents -- i.e. the mechanism that page
  describes has already shipped in practice, docs label notwithstanding:

  | Venue | Deployer | (k, n) | Outcomes live | Weakest `settleOutcome`/`settleQuestion` key |
  |---|---|---|---|---|
  | `out` | `0x0C46eB73...5819E` | 3-of-4 | 100 | single key (2 sub-deployers, both bare EOAs, `userToMultiSigSigners` null) |
  | `txyz` | `0x7ACa0966...9f553` | 2-of-3 | 87 | single key (2 sub-deployers, both bare EOAs) |
  | `skew` | `0x08e9c89F...335eFe` | 3-of-5 | 54 | single key (1 sub-deployer, bare EOA) |

  `txyz` is the exact deployment section 6's own prior text had flagged as
  unresolved ("trade\[XYZ\] docs already describe a `txyz` HIP-4
  deployment. To re-check against the Hyperliquid docs before relying on
  either.") -- now independently confirmed live and read in full, not just
  cited from a third-party doc.

- **Rule 4.2's own logic (deployer plus every sub-deployer granted for the
  sensitive action, weakest by `(k, -n)`) applies unchanged to all three**:
  every one of the 8 unique sub-deployer addresses across the 3 venues
  reads `userToMultiSigSigners = null` (a bare single key), which is
  strictly weaker than each venue's own multisig deployer threshold (3-of-4,
  2-of-3, 3-of-5) -- so on THIS methodology, a compromised single
  `settleOutcome`/`settleQuestion` sub-deployer key could settle a live
  market's payout on ANY of these 3 venues, bypassing that venue's own
  deployer multisig entirely. Structurally identical to the
  already-documented HIP-3 "sub-deployers bypass a strong deployer
  multisig" caution (METHODOLOGY.md 4.2 rule 3), now confirmed to apply
  cleanly to a second, independently-designed action family the first time
  it is checked.
- All 8 unique deployer/sub-deployer addresses carry **zero HyperEVM
  bytecode** (`eth_getCode` on chain 999 returns `0x` for every one) --
  unlike `para`/`mkts`/Ventuals, none of these resolve through a HyperEVM
  contract identity, so the 3.7 CoreWriter-identity caution does not apply
  here; each is a plain HyperCore key or native multisig, exactly as
  `userToMultiSigSigners` reports it.
- **Zero address overlap** between these 8 addresses and any of the 12
  root addresses already tracked across this ecosystem's 15 live scored
  targets (re-run `score_all()` live this pass to get the current list;
  see below) -- these would be 3 genuinely new, unconnected targets, not a
  restatement of an existing one.
- **Economic weight not yet sized** (no OI/volume figure computed this
  pass -- would need per-market book/trade reads across up to 241
  non-recurring outcomes, out of this pass's scope) -- this is exactly the
  gap the existing HIP-3-dex promotion discipline (METHODOLOGY.md's own
  `scorers.py` docstring: promote by real usage, not listed-market count)
  would need closed before scoring these for real, the same bar `flx`
  failed and `io`/`para`/`mkts` cleared.

**Provisional numbers under the existing 4.6 ladder (NOT pushed to
`scorers.py` this pass)**, single key at the weakest node for all three:
`adminKeyScore=10`, `multisigScore=15`, `oracleAuthorityScore=15` (this is
a validator-priced settlement -- HyperCore mark price interpolation, same
family as 4.4's "validator-operated perps" row for the underlying price
feed itself, but the SETTLEMENT action, i.e. who calls `settleOutcome`/
`settleQuestion2` and finalizes the payout split, is the venue's own weak
sub-deployer key computed above, not the L1 validator set -- disclosed as
a genuinely new authority shape this pass does not have a prior 4.6 row
for) **[CORRECTED 2026-09-19, see the Update paragraph below: the parenthesis above
is wrong for these three venues. Their settlement value is supplied by the venue's
own settle key, with no protocol price computation behind it (their markets name
free-text price sources such as "the Pyth BTC/USD price"); "validator-priced"
applies only to the 8 protocol-run recurring outcomes, which are outside this
family]**, `timelockScore=0` (no delay documented for `settleOutcome`),
`compositeScore=composite(10,15,0)=9` for all three (same formula, same
result, since all three land on an identical weakest-key shape despite
different deployer-level thresholds).

**Why this is NOT promoted into `scorers.py` in this same pass**: per
`AGENTS.md`'s own phase discipline (`scouting -> scoring_build ->
deploy_testnet`) and its "before committing" rule ("a new
controller-resolution shape... run an adversarial review before
committing, not after"), this is scouting-phase output -- three brand-new
targets of a genuinely new authority-shape family (an outcome-market
deployer/settlement authority, never scored anywhere in this repo before),
verified live and independently but NOT yet run through the
maker-checker/adversarial-review pass this repo requires before a new
controller-resolution shape is treated as settled. Recommended next step:
a dedicated `scoring_build` pass (same shape as
`scoring_build_2026_09_18.py`) that (a) sizes real economic weight for
`out`/`txyz`/`skew` the way `io`/`para`/`mkts` were sized before
promotion, (b) writes and unit-tests `score_hip4_outcome_deployer(venue)`
reusing `admin_key_score`/`key_score`/`composite` exactly as done here by
hand, and (c) runs the adversarial-review pattern before committing --
consistent with how every other new-shape addition in this file's own
changelog (section 7) was handled.

**Update, later 2026-09-19 (scoring_build pass and adversarial review):** the sizing,
the scorer, the review record and the decision are in
`scored_targets_2026-09-19-hip4-outcome-deployers.md`. Three statements above are
corrected there: the "8 unique sub-deployer addresses" are 3 deployers plus 5
sub-deployers; "zero address overlap" held for addresses only (`txyz`'s deployer is
backed by the same three signers as HIP-3 dex `xyz`'s deployer); and the
"validator-priced settlement" attribution for `oracleAuthorityScore=15` is wrong
for these venues (their own keys settle; the score stays 15 because the weakest
settle key is a bare key, but the reason is the key, not a validator price). The
"3-of-4" deployer of `out` is also a nested, cyclic multisig, which the
description above omits, and the `Economic weight not yet sized` paragraph is
closed by the sizing (all three venues HELD). The outcome counts above are the
first read's and have drifted (236 outcomes, 23 questions, venues 99 / 77 / 52 at
18:44 UTC).

## Reproduction

```bash
# Bridge2 vs L1 validators
python3 chains/hyperliquid/scripts/scout_2026_09_19_section6.py bridge-vs-l1

# HIP-4 outcome deployers (live inventory + k/n + HyperEVM code check)
python3 chains/hyperliquid/scripts/scout_2026_09_19_section6.py hip4-deployers

# Existing 15 targets, re-run live for the cross-exposure check above
python3 -c "
import sys; sys.path.insert(0,'scripts/lib'); sys.path.insert(0,'chains/hyperliquid')
from scorers import score_all
for r in score_all(): print(r['label'], r['target'], r['compositeScore'])
"

# Mainnet vs testnet outcome-market environments are genuinely separate
curl -s -X POST -H 'Content-Type: application/json' -d '{"type":"meta"}' https://api.hyperliquid.xyz/info
curl -s -X POST -H 'Content-Type: application/json' -d '{"type":"meta"}' https://api.hyperliquid-testnet.xyz/info
```
