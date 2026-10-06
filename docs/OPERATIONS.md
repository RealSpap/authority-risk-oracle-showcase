# Operating the oracle

## Recurring updater

[`scripts/update_scores.py`](../scripts/update_scores.py) re-derives every target's score from live chain state (not a cached
value) and pushes a fresh `updateScores()` batch. `bash scripts/repush_all_oracles.sh` re-pushes all nine oracles in one run;
`DRY=1` recomputes and encodes without reading a key or sending anything.

A real push is guarded before it is sent:

- a score that drops by more than 15 points, or follows a read that could not be completed, is **held** until a person accepts that address
  (`--accept-held=0xA,0xB`);
- the `methodologyHash` is derived from the scorer files by [`scripts/lib/methodology.py`](../scripts/lib/methodology.py) and pinned
  before scoring; a real push refuses to run if the digest differs from the one computed from the HEAD commit;
- every sub-score is range-checked again on-chain (`ScoreOutOfRange`).

Mainnet target: [Robinhood Chain](https://docs.robinhood.com/chain) (Arbitrum Orbit rollup, mainnet since 2026-07-01). The next step is
moving the stack there and the updater key to a multisig instead of the single deploy key used for testnet validation.

## Consuming it off-chain

`getScore(address)` on the deployed oracle is the source of truth. Every real push also writes [`api/scores.json`](../api/scores.json):
a versioned JSON snapshot of what was just confirmed on-chain, with `txHash` and `blockNumber` so a consumer can cross-check it.

```json
{
  "oracle": "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52",
  "chainId": 46630,
  "methodologyHash": "0x...",
  "generatedAt": 1758000000,
  "txHash": "0x...",
  "blockNumber": 12345,
  "scores": [
    { "target": "0x...", "label": "Uniswap v3 Factory", "adminKeyScore": 80, "multisigScore": 100,
      "timelockScore": 75, "oracleAuthorityScore": 100, "crossExposureScore": 80, "compositeScore": 85 }
  ]
}
```

## Alerts

[`scripts/lib/alerts.py`](../scripts/lib/alerts.py) diffs each run against the previous `api/scores.json` and flags anything that
got meaningfully worse: a `compositeScore` drop of 10 points or more, a worse risk band even on a smaller move, or a new target
first published below 40/100. Improvements never alert. With `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set, alerts go to that
chat; unset, the run prints them and nothing else changes.

## Watching beyond the score

Read-only tools (public RPC, no key, nothing sent) that answer what a score alone does not. Each states in its header what it
could not read; an unread source is never reported as quiet.

| Question | Command |
|---|---|
| One dated report: which oracle turns stale, what changed on the Safes, what is queued in the timelocks, has tracked code changed | `python3 scripts/daily_digest.py` |
| What can this one key touch, and who are the most connected signers | `python3 scripts/who_controls.py 0xADDRESS`, `--top 20`, `--code-scan` |
| Which protocol families reuse the exact same committee across ecosystems | `python3 scripts/who_controls.py --families` |
| What changed on the tracked Safes in the last N days | `python3 scripts/check_safe_changes.py --days 30` |
| What is queued behind the watched timelocks, and what cleared recently | `python3 scripts/check_pending_ops.py` |
| Did a Squads v4 multisig behind a Solana target change members, threshold or time lock | `python3 scripts/check_squads_changes.py` |
| Did a root signer turn from a plain EOA into an EIP-7702 delegated account | `python3 scripts/check_signer_kinds.py` |
| What share of each ecosystem's DefiLlama TVL do the tracked targets cover | `python3 scripts/check_tvl_coverage.py` |
| How many published targets score at or below the multisig behind a documented incident (Bybit, WazirX, Radiant, Humanity) | `python3 scripts/incident_exposure.py` |
| Who can move the price each Morpho market trusts | `python3 scripts/check_morpho_market_oracles.py` |
| Which Morpho markets price from a number a role holder posts, and how far they can move it | `python3 scripts/check_posted_price_feeds.py` |
| Who can move the price each reserve of Aave V3 Ethereum Core uses (CAPO adapters, risk admins) | `python3 scripts/check_lending_price_authority.py` |
| Live target count of every deployed oracle | `python3 scripts/live_target_counts.py` |

## Cross-ecosystem schema check

[`scripts/validate_all_scorers.py`](../scripts/validate_all_scorers.py) runs every ecosystem's `score_all()` (each in its own
subprocess) and checks each entry has the shape every consumer assumes: all five sub-scores present, an integer in [0, 100],
`compositeScore` matching the formula, no internal field leaking out. It found two real bugs the day it was written
([missing field](../data/correction_2026-09-17-missing-crossexposure-field.md), [swapped field name](../data/correction_2026-09-17-tempo-field-name-swap.md)).

```bash
python3 scripts/validate_all_scorers.py                          # every ecosystem
python3 scripts/validate_all_scorers.py --ecosystem solana       # one ecosystem
python3 scripts/validate_all_scorers.py --skip robinhood-chain   # the slow one, about 25 minutes
```
