# Finding (2026-09-18): the DAO-via-bridge sub-model and the cross-chain multisig grid, quantified

Requested by a tracked GitHub Projects item bundling two related
cross-ecosystem questions. Pure investigation -- no scorer file
(`chains/*/scorers.py`, `scripts/lib/scorers.py`) is modified by this
finding. A change to any of these formulas needs this project's own
adversarial-review discipline before committing, per `AGENTS.md`.

## Part 1: "external DAO governance via bridge" -- 4 real instances, only 1 shares code

`chains/arbitrum-ecosystem/scorers.py:60-69` already names this exact
gap in a comment: *"Not built this pass; each scorer below discloses
its own slice of the gap individually."* Confirmed, with exact numbers:

| Instance | File:line (formula) | admin_key confirmed/degraded | multisig | timelock confirmed/degraded |
|---|---|---|---|---|
| Aave V3 Pool (Arbitrum) | `chains/arbitrum-ecosystem/scorers.py:443-445` | 65 / 30 | 100 | 50 / 0 |
| Aave V3 (Base) | `chains/base-ecosystem/scorers.py:221-223` | 65 / 30 | 100 | 50 / 0 |
| Compound V3 Comet USDC (Base) | `chains/base-ecosystem/scorers.py:483-485` | 75 / 35 | 100 | 65 / 0 |
| Uniswap V3 Factory (Base) | `chains/base-ecosystem/scorers.py:413-424` | 80 / 20 | 100 | 75 / 0 |

Aave (Arbitrum and Base) is the exact same BGD-Labs Aave-Governance-V3
relay shape, byte-identically duplicated across the two ecosystem
files, and lands on the same numbers (65/100/50) -- consistent with
itself, just not with a shared helper. Compound-Base (75/100/65) and
Uniswap-Base (80/100/75) are each independently hardcoded to DIFFERENT
numbers for what the tracker item calls "the same" confirmed-L1-DAO-
via-bridge authority shape.

The one place this pattern DOES have a shared helper is Robinhood
Chain's own Uniswap stack: `_score_uniswap_bridge_alias_root()`
(`scripts/lib/scorers.py:124-174`), called by 4 scorers, returns a
consistent `(80, 100, 75)` confirmed / `(5, 0, 0)` degraded. Coincidentally
the SAME numbers as Base's independently-hardcoded Uniswap scorer --
by explicit stated convention (each docstring says so), not shared code.

**Open question**: is the 65 vs 75 vs 80 admin_key spread justified by
a real difference in each target's authority chain (a defensible
per-target judgment call, the way this project scores most things), or
is it accidental drift from writing each scorer independently without
cross-checking the others? This finding does not decide that --
tracing each target's real authority chain closely enough to know is
the next step, not attempted here.

## Part 2: the 2-of-3 multisig grid -- one divergence is deliberate and documented, one is genuinely unexplained

The tracker item's own framing ("2-of-3 = 39 Hyperliquid vs 35 Safe")
is accurate for `multisigScore`, not `compositeScore` -- worth
correcting before anyone reasons from it. Three independently verified
formulas for a confirmed 2-of-3:

| Ecosystem | multisigScore formula | 2-of-3 multisig | admin_key (k=2) | Composite (timelock=0) |
|---|---|---|---|---|
| Hyperliquid (HIP-3) | `min(100, 20k-(n-k))`, `chains/hyperliquid/METHODOLOGY.md:408` | **39** | 50 | **32** |
| Robinhood Chain Safe (`_safe_rooted_scores`) | `min(100, 15k+5(n-k))`, `scripts/lib/scorers.py:1106` | **35** | 50 | **31** |
| Solana (Squads) | `min(100, round(15k+40k/n))`, `chains/solana/scorers.py:76-91` | **57** | 45 | **35** |

**Important correction to the tracker item's implicit framing**:
Hyperliquid's divergence from the Safe formula is not an oversight --
`chains/hyperliquid/METHODOLOGY.md:415-423` documents the actual reason
IN THE METHODOLOGY ITSELF: the Safe formula `15k+5(n-k)` rewards a
larger `n` at equal `k`, which contradicts HIP-3's own approved
ordering rule (a larger `n` at equal `k` should score WEAKER, since any
one of more keys being compromised is a bigger attack surface). The
doc states the tradeoff explicitly: *"a 2-of-3 scores 39 here against
35 under the Robinhood Chain Safe formula"* -- a conscious, justified,
already-disclosed choice, not a gap.

Solana's 57 is the real outlier, and IS closer to "ad hoc" as the
tracker item says: its constants (`15k + 40k/n`) trace to a one-off
calibration against a real 5-of-7 Realms council
(`chains/solana/METHODOLOGY.md:379-389`), not a stated first-principles
ordering argument the way Hyperliquid's is. At the composite level the
practical gap is smaller than the raw multisig numbers suggest (32 vs
31 vs 35 -- a 4-point spread, not the ~20-point spread the raw
`multisigScore` numbers alone would imply), since `admin_key` and the
0.4/0.3/0.3 weighting compress it.

## What this does NOT do

- Does not change any published score in any ecosystem.
- Does not modify any scorer file.
- Does not decide whether the Arbitrum/Base DAO-via-bridge scorers
  should be unified into one shared helper (Part 1), or whether
  Solana's multisig formula should be re-derived to match one of the
  other two ecosystems' stated ordering principle (Part 2) -- both are
  real design questions for an adversarial-review pass, not settled
  here.
