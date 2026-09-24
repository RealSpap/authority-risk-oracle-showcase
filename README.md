# Authority Risk Oracle

![License](https://img.shields.io/badge/license-MIT-blue)
![Hackathon](https://img.shields.io/badge/Colosseum-Crypto%20World's%20Fair%202026-6b46c1)
![Network](https://img.shields.io/badge/network-testnet%20only-orange)
![Ecosystems](https://img.shields.io/badge/ecosystems-10%20tracked-informational)


A live, on-chain oracle that scores **authority risk** -- admin key concentration,
multisig weakness, timelock delay, oracle-signer authority, and cross-protocol signer
overlap -- for DeFi protocols, so other contracts can read it directly instead of
trusting a closed dashboard or a risk provider paid by the protocol it rates.

Built for [Colosseum's Crypto World's Fair](https://colosseum.com/worldsfair) hackathon.

## Try it

- **Dashboard**: [`dashboard/index.html`](dashboard/index.html) -- open it in a browser,
  reads every deployed oracle live via raw `eth_call`, nothing to trust but the RPC.
- **Read a score yourself**, no install beyond `cast` (Foundry):
  ```bash
  cast call 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \
    "getScore(address)(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)" \
    <target-address> --rpc-url https://rpc.testnet.chain.robinhood.com/rpc
  ```
  (`adminKey, multisig, timelock, oracleAuthority, crossExposure, composite, lastUpdated, methodologyHash` --
  exact field order from [`src/AuthorityRiskOracle.sol`](src/AuthorityRiskOracle.sol)'s own `AuthorityScore` struct.)
- **Methodology**: [`METHODOLOGY.md`](METHODOLOGY.md) -- what each sub-score measures and
  what the oracle cannot see. **Deployed addresses & current target counts**: see
  [Status](#status) below.

## The gap this fills

| | On-chain / composable | Independent of the rated protocol | Covers authority risk specifically |
|---|---|---|---|
| Hypernative, Blockaid | No -- closed dashboard | Yes | Partial |
| Gauntlet, Chaos Labs, LlamaRisk | No (LlamaGuard PT is on-chain, but covers *collateral* risk) | **No** -- paid by the protocol rated | No |
| DeFiSafety | No -- static periodic report | Yes | Partial |
| [SolGov](https://solgov.xyz) | No -- website, not a contract | Yes | Yes, Solana only |
| **This project** | **Yes** -- `getScore()`/`isStale()`, any contract can call it | **Yes** -- independently computed, no protocol pays for its own score | **Yes**, across 10 ecosystems |

The conflict of interest in row 2 isn't theoretical: this project's own prior research
(`defi-admin-key-risk`) documented it in real incidents. And
[ERC-8241 "Protocol Control Disclosure"](https://paragraph.com/@0x0afe5e054249b19ae29075540d9e6951c66e49b7/making-the-case-for-erc-8241-protocol-control-disclosure)
(draft, active discussion on Ethereum Magicians) standardizes exposing *raw* authority
facts and explicitly leaves scoring to "external interpretation layers" -- this project
is exactly that layer.

### Closest real precedent: SolGov

[SolGov](https://solgov.xyz), built after the $285M Drift exploit, tracks 50 Solana
protocols across 63 multisigs and 180+ programs -- multisig threshold, timelock
delay, role separation, verified builds, key rotation. It's the strongest outside
evidence that this project's thesis is right: someone else independently hit the
same gap and shipped a real, live product for it, on one ecosystem. This project
independently re-derived that same founding incident from the actual on-chain
transactions, not the press coverage SolGov's own motivation cites -- and unlike
SolGov, went one step further by live-scoring Drift's current (reformed)
authority too, not just the historical incident: see the backtest below.

What it doesn't do, concretely:
1. **It's a website, not a contract.** No lending market, no DAO, no other protocol
   can call a SolGov score the way `ExampleConsumer.sol` calls `getScore()` here --
   there is nothing to integrate against, only a page to read.
2. **Solana only.** This project targets 10 ecosystems (Robinhood Chain, Ethereum
   L1, Arbitrum, Base, Hyperliquid, Solana, Zcash, Tempo, Plasma, Monad) for the same reason
   `multisig-overlap` and `defi-admin-key-risk` scaled across chains instead of
   staying on one: authority risk is not ecosystem-specific.
3. **No cross-protocol signer overlap, on-chain or cross-chain.** SolGov's columns are
   all per-protocol on one chain; it never checks whether the *same* key sits behind
   two protocols it lists as independent, let alone two protocols on two different
   chains. `crossExposureScore` does the within-chain version for free, by reusing
   `multisig-overlap`'s existing dataset, and this project also runs a real
   cross-*ecosystem* check across every EVM target. Rule since 2026-09-20 (see
   `METHODOLOGY.md`): any root committee shared with another tracked target, on the
   same chain or a different one, is capped at `crossExposureScore=80` instead of a
   blind 100 -- first caught live on Arbitrum/Base's shared Aave V3 guardian Safe
   (`data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md`).
4. **Methodology depth is capped by one maintainer's time.** SolGov's "safety
   benchmark" columns (verified builds, nonce detection, hardware wallets, key
   rotation, insurance fund, treasury segmentation) are a real, useful, concrete
   signal list this project does not fully check yet on Solana (18 targets scored,
   `chains/solana/scorers.py`) -- a genuinely open gap, not a completed step. See
   `CHANGELOG.md` for how that count got there.

### The closest thing to a governance precedent for this thesis: Aave x LlamaRisk

Chaos Labs stepped down from Aave risk management in April 2026 (see BUSINESS.md);
LlamaRisk has since run Aave's PT oracle and, in June 2026, got a binding four-layer
risk framework adopted that now governs every asset listing/review/deprecation
across Aave V3, V4 and Aave Horizon (already enforced -- Aave dropped six chains
under it by end of July 2026). Two parts of it matter directly here: Layer 1 makes
**undisclosed signer composition a hard-block condition** for listing an asset at
all, and Layer 3 requires "monitoring and automated risk-oracle systems...
codified as standing protocol infrastructure, not optional tooling."

Worth stating plainly rather than leaving for a reader to find first: this is a
major protocol's own risk manager independently arriving at close to this
project's thesis -- authority/signer disclosure should be a mandatory, continuously
enforced part of risk infrastructure, not an optional check. What it still isn't:
Layer 3 names no vendor or tool, and per LlamaRisk's own reporting it is running
that oracle **manually**, not as a live, on-chain, cross-protocol, third-party-
composable feed. That gap -- a governance-mandated checklist item enforced through
Snapshot votes and a paid risk manager, versus a permissionless score any contract
can read -- is exactly where this project sits. If LlamaRisk (or anyone) turns that
manual Layer 3 process into a named, live, on-chain authority-risk oracle, that
would be a direct competitor; nothing found as of 2026-09-17 does that yet.

## How it works

The scoring methodology is not new: it reuses this research program's existing,
independently-verified classification logic (`classify_holder()`, `resolve_roles()`,
`getUniqueSignersThreshold()` from `defi-admin-key-risk` and `oracle-signer-authority`)
against 2+ independent RPCs. What's new is publication: an off-chain updater pushes
the resulting score on-chain, where any contract can read it.

**[`METHODOLOGY.md`](METHODOLOGY.md)** documents exactly what each of the five
sub-scores measures, the inputs it reads on-chain, the aggregation formula, and --
just as important -- what this oracle cannot see. A DAO or judge shouldn't have to
trust a number it can't reconstruct.

```
┌─────────────────────┐     eth_call / eth_getLogs      ┌──────────────────┐
│ off-chain scorer     │ ───────────────────────────────▶│ 2+ independent   │
│ (existing methodology)│◀─────────────────────────────── │ RPCs             │
└──────────┬───────────┘                                  └──────────────────┘
           │ updateScore() / updateScores()
           ▼
┌─────────────────────────┐     getScore() / isStale()    ┌──────────────────┐
│ AuthorityRiskOracle.sol  │◀───────────────────────────── │ consumer contract│
│ (this repo)              │                                │ (e.g. a lending  │
└──────────────────────────┘                                │  market)         │
                                                             └──────────────────┘
```

## Contracts

- [`src/AuthorityRiskOracle.sol`](src/AuthorityRiskOracle.sol) -- the oracle itself.
  `AccessControl`-gated `UPDATER_ROLE` pushes per-target scores (admin key, multisig,
  timelock, oracle-authority, cross-exposure sub-scores plus a composite); any
  contract can read `getScore(target)` and `isStale(target)`.
- [`src/ExampleConsumer.sol`](src/ExampleConsumer.sol) -- demonstrates a lending-style
  contract deriving a collateral factor from a live score, freezing collateral behind
  a weak authority and refusing a stale read outright.

**Contract security review against the LlamaGuard PT pattern (2026-09-17)**: the
pitch is "we flag who has too much unchecked power," so this project's own
contract was checked against the same standard first --
[`data/contract_review_2026-09-17-llamaguard-comparison.md`](data/contract_review_2026-09-17-llamaguard-comparison.md).
Found and fixed a real gap: nothing on-chain previously enforced the documented
0-100 range on any sub-score -- `ExampleConsumer.sol`'s own `collateralFactorBps()`
would compute a collateral factor of **~196%** (2.5x its own stated maximum) from
a pushed `compositeScore` of 255, whether from an off-chain bug or a compromised
`UPDATER_ROLE` key. Fixed with an on-chain `ScoreOutOfRange` revert.

**[`SECURITY.md`](SECURITY.md)** -- how to report a vulnerability (private GitHub
Security Advisories drafted as the preferred path, but **not yet enabled on this
repo** -- checked live, needs a Settings toggle first; use a normal GitHub issue
until then. A funded Immunefi bug bounty is drafted too -- scope, severity tiers
mapped to Immunefi's own v2.3 classification, suggested reward amounts sized
honestly for a testnet, no-custodied-funds contract -- but not yet live pending
the maintainer funding and setting up the actual program).

## Status

**Deployed oracles at a glance, 2026-09-20 20:41 CEST** (addresses from each ecosystem's
own deploy record, counts read live with `python3 scripts/live_target_counts.py`):

| Ecosystem | Network | Oracle | Targets |
|---|---|---|---|
| Robinhood Chain | Testnet, chain 46630 | [`0x9BF4...7f52`](https://explorer.testnet.chain.robinhood.com/address/0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52) | 58 |
| Ethereum L1 | Sepolia, chain 11155111 | [`0xB6F8...f906`](https://sepolia.etherscan.io/address/0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906) | 19 |
| Arbitrum | Sepolia, chain 421614 | [`0x5084...8720`](https://sepolia.arbiscan.io/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Base | Sepolia, chain 84532 | [`0x5084...8720`](https://sepolia.basescan.org/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Tempo | Moderato, chain 42431 | [`0x5084...8720`](https://explore.testnet.tempo.xyz/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 14 |
| Plasma | Testnet, chain 9746 | [`0x5084...8720`](https://testnet.plasmascan.to/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Monad | Testnet, chain 10143 | [`0x5084...8720`](https://testnet.monadvision.com/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Hyperliquid | HyperEVM Testnet, chain 998 | `0x5084...8720` (no public explorer is listed for this network) | 15 |
| Solana | Devnet, native Anchor program | [`5VhiTA...Yh4W`](https://explorer.solana.com/address/5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W?cluster=devnet) (Registry PDA `CDHtBT...ZBEib`) | 18 |
| Zcash | Testnet, no contract | latest OP_RETURN commitment, [`462de12b...701c`](https://testnet.cipherscan.app/tx/462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c) | 6 live (not in the total) |

The seven EVM oracles at `0x5084...8720` are one address by construction: a CREATE address
is `keccak(deployer, nonce)`, and the same shared deployer key was at nonce 0 on each chain.
Robinhood Chain and Ethereum L1 have their own addresses. **160 targets on the 9 on-chain
oracles**, plus Zcash's 6 attested (not counted in the total, different mechanism).

**[`dashboard/index.html`](dashboard/index.html)** reads every score directly from each
deployed oracle in your own browser via raw `eth_call` -- no backend, nothing to trust but
the RPC and the contract itself.

**Recurring updater**: [`scripts/update_scores.py`](scripts/update_scores.py) re-derives
every target's score directly from live chain state (not a cached value) and pushes a fresh
`updateScores()` batch; `bash scripts/repush_all_oracles.sh` re-pushes all nine oracles in
one run (`DRY=1` recomputes and encodes without reading a key or sending). Runs weekly via
`.github/workflows/update_scores.yml`. Mainnet target:
[Robinhood Chain](https://docs.robinhood.com/chain) (Arbitrum Orbit rollup, mainnet since
2026-07-01) -- next step is moving the whole stack there, migrating the updater key to a
real multisig rather than the single deploy key used for testnet validation.

## Full history

[`CHANGELOG.md`](CHANGELOG.md) carries the complete batch-by-batch, correction-by-correction
narrative this section used to hold directly -- every rotation audit, every backtest, every
cross-ecosystem overlap finding, moved out unedited to keep this README a pitch plus a
current-state summary, the same split [`onchain-postmortems`](https://github.com/RealSpap/onchain-postmortems)
already uses between its own README and each incident's own files. A handful of other files
in this repo point to a named subsection "in README.md's Status section" (`SECURITY.md`, and
several dated `data/*.md` research notes) -- those subsections now live in `CHANGELOG.md`
under the identical heading text, nothing renamed or reworded.

## Consuming this off-chain

`getScore(address)` on the deployed oracle is the source of truth -- the dashboard
reads it directly, and any contract should too. Not every consumer wants to run its
own RPC integration for that, so every real (non-dry-run) push also writes
[`api/scores.json`](api/scores.json): a plain, versioned JSON snapshot of exactly
what was just confirmed on-chain, safe to `fetch()` or `curl` directly from this
repo without touching an RPC at all.

```json
{
  "oracle": "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52",
  "chainId": 46630,
  "methodologyVersion": "authority-risk-oracle-v3",
  "methodologyHash": "0x...",
  "generatedAt": 1758000000,
  "txHash": "0x...",
  "blockNumber": 12345,
  "scores": [
    { "target": "0x...", "label": "Ekubo Core", "adminKeyScore": 100, "multisigScore": 100,
      "timelockScore": 100, "oracleAuthorityScore": 100, "crossExposureScore": 100, "compositeScore": 100 }
  ]
}
```

This file is a convenience cache, not a second source of truth -- `txHash` and
`blockNumber` are included specifically so any consumer can cross-check it against
the transaction that produced it, rather than trusting the JSON on its own.

**Alerts.** [`scripts/lib/alerts.py`](scripts/lib/alerts.py) diffs each run's fresh
scores against the previous `api/scores.json` and flags anything that got
meaningfully worse: an existing target whose `compositeScore` drops 10+ points, an
existing target whose risk band gets worse even on a smaller move, or a brand-new
target first published already below 40/100. Improvements never alert -- this is a
risk feed, not a changelog. If `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set
(as GitHub Actions secrets, or locally), matching alerts are pushed to that chat;
unset, the run still prints them to the log and nothing else changes -- alerting is
strictly additive, never a dependency of the scoring pipeline itself. No bot token
is provisioned yet: create one via [@BotFather](https://t.me/BotFather), add it and
the target chat ID as repo secrets, to actually turn this on.

## Business case

See [`BUSINESS.md`](BUSINESS.md) for the market this sits in (DAOs already pay
$250k-3M/year for continuous risk services -- none of it covers authority risk
specifically), how it positions against the emerging ERC-8241 disclosure standard,
and a realistic path from hackathon demo to a paid governance mandate.

## Development

```bash
forge build
forge test
```

Python side (`scripts/lib/`, the code path the real weekly production cron
actually runs): unit tests for the pure/mockable logic (composite-score
rounding, retry control flow, alert thresholds, the Arbitrum bridge-alias
arithmetic) added 2026-09-17 -- see [`scripts/lib/tests/`](scripts/lib/tests/):

```bash
pip install -r scripts/requirements.txt
python3 -m unittest discover -s scripts/lib/tests -v
```

Both suites run in [`.github/workflows/test.yml`](.github/workflows/test.yml)
on push/PR (currently not firing -- GitHub Actions is disabled account-wide;
run them locally with the commands above until that changes).

**Cross-ecosystem schema check** ([`scripts/validate_all_scorers.py`](scripts/validate_all_scorers.py),
added 2026-09-17): runs every ecosystem's `score_all()` (each in its own
subprocess, to avoid same-named-module collisions between ecosystems --
see `data/correction_2026-09-17-tempo-field-name-swap.md`) and checks every
returned entry has the shape every downstream consumer already assumes
(`target`/`label`/all five sub-scores present, each an int in [0,100],
`compositeScore` matching the repo formula, no internal `_`-prefixed field
leaking out). Found and fixed two real bugs the same day this way that a
live re-derivation alone would not have caught (a missing field, a swapped
field name) -- see `data/correction_2026-09-17-missing-crossexposure-field.md`
and `data/correction_2026-09-17-tempo-field-name-swap.md`.

```bash
python3 scripts/validate_all_scorers.py                      # every ecosystem
python3 scripts/validate_all_scorers.py --ecosystem solana   # one ecosystem
python3 scripts/validate_all_scorers.py --skip robinhood-chain  # it's the slow one (measured 2026-09-19: ~25 min, 56 targets)
```

Deploy (requires `PRIVATE_KEY` in the environment, never committed):

```bash
forge script script/Deploy.s.sol --rpc-url robinhood --broadcast
```

## License

MIT.
