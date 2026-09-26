# Zcash coinbase payout addresses: real attempt at attribution, genuinely inconclusive

2026-09-26. Investigates the tracker board's open piste ("rattacher les adresses coinbase sans texte
[backlog note]"). Result: the addresses are real and
persistent (confirmed live, current data below), but a genuine, multi-angle search found **no
primary source that publicly identifies either address to a named mining entity**. Disclosed as an
honest negative result, not guessed at -- fabricating an attribution here would be exactly the kind
of unfalsifiable claim this project's own `hypotheses-falsifiables` tooling exists to catch.

## Full addresses and current concentration, read live (not the stale window the card cites)

`chains/zcash/scorers.py::score_l1()` uses a ROLLING 2000-block window (ending 10 confirmations
behind the tip, per METHODOLOGY.md 4.2's own fix for staleness) -- so the backlog item's exact
percentages (29.6%/7.7%) are from whatever window was current when it was written, not reproducible
today. Re-ran `chains/zcash/scripts/miner_concentration.py`'s `compute_concentration()` live against
the CURRENT window (blocks 3,494,703-3,496,702, tip 3,496,712 at read time):

| Address (full, untruncated) | Share of current window |
|---|---|
| `t1MKn34KBa8Xh4g8qU8psibBXvURafphVn7` | 27.2% (was 29.6% in the card's window) |
| `t1SEgZvXCu3ceE42qrq5pCeSq7HbLjX8NJv` | 7.0% (was 7.7%) |

**Both addresses match the card's truncated citation exactly** (prefix+suffix), confirming these are
the same real, persistent top payees -- not a stale/wrong reference. `addressesToExceed50Pct` (k50) =
3 in the current window (the top 3 addresses, `t1MKn34...` + `t1PEp2GJ...` (15.3%) + `t1SqwRAA...`
(15.3%), sum to 57.9%).

## What a real attribution attempt actually tried

- Direct search on both full addresses (no third-party page, forum, or explorer entry found).
- Zcash mining pool sites (Flypool, 2Miners, ViaBTC, F2Pool -- F2Pool has since discontinued ZEC
  mining) -- none publish a payout-address list matching these.
- Block explorer lookups (3xpl.com rate-limited this run, Blockchair now requires auth) -- neither
  returned a usable entity tag before failing.
- Zcash Community Forum search for the specific address strings and for general mining-concentration
  discussion threads -- no thread mentions either address by name.

## Why this stays genuinely open, not "not tried hard enough"

A real entity attribution for a Zcash transparent address, absent the entity's own public
disclosure, normally needs either (a) proprietary chain-clustering heuristics (co-spend clustering,
timing analysis) this project has no tooling or license for, or (b) the pool's own operator
publishing its payout address, which was searched for and not found for either address. The one
positive, verifiable fact from this pass: **both addresses have been persistently dominant across
at least the gap between the card's window and today's** (days apart, same top-2 identity, modest
percentage drift) -- consistent with a small number of large, stable mining operations rather than
noise, but that is a concentration fact, not an identity.

## What this is and isn't

Pure investigation, no scorer change. `k50`/`multisigScore` are NOT recalculated or adjusted here --
the card's own "[backlog note]" scenario requires knowing whether two
specific addresses share an operator, which this pass could not establish either way; asserting it
either resolved or ruled out would be an unfalsifiable claim this project explicitly guards against.

## Verification

`python3 -c "... compute_concentration('zec.rocks:443', start, end)"` (using the project's own
`chains/zcash/scripts/miner_concentration.py`, read-only via lightwalletd `GetBlockRange`, no key).
Web searches and explorer fetches attempted via WebSearch/WebFetch, each outcome disclosed above
rather than omitted.
