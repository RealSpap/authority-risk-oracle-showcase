# Between a quarter and a half of what the oracle publishes scores at or below Bybit's configuration before the hack (exposure, not prediction)

2026-09-26, revised 2026-09-27 after an independent review (the review's corrections are folded in below). `data/research_2026-09-21-authority-incidents-evidence-table.md` lists 23 authority incidents and concludes that the honest claim is "measured exposure of the authority path",
not prediction (there is no sample of protocols that were not hit). This measures that exposure. `scripts/incident_exposure.py` reads every published score from the deployed oracles, replays five incidents through the shared Safe-rooted convention
(`scripts/lib/scorers.py::_safe_rooted_scores` and the standard composite, no new formula), and counts the published targets at or below each. Read-only; 179 targets read, nothing unread.
The threshold of each incident is stated by its source; the owner count comes from the source, and for Bybit from an on-chain read of the Safe (`0x1db92e2E...`: 6 owners, threshold 3), because the cited page gives the threshold only.
**The timelock score of 0 is this project's reading of a plain Safe, which has no built-in delay; the sources do not state a delay either way** (only Drift and Echo have an absence written in their sources, per the evidence table).

## The published set today

179 targets on 9 oracles (Ethereum's 25 and Hyperliquid's 15 are the published numbers, one or more behind the scorers; Ethereum's 25 still include the retired Ethena minter, published at composite 52): **median composite 44; 107 targets (60%) have a timelock score of 0; 44 (25%) sit in the lowest band (composite 10 or less; mostly bare-key roots, 5 of the 44 are placeholders or partial scores).**
By oracle (targets, median composite, no timelock, lowest band): Robinhood Chain 63, 33, 39, 20; Ethereum L1 25, 60, 9, 3; Arbitrum 13, 55, 5, 2; Base 13, 66, 3, 0; Tempo 14, 39, 12, 4; Plasma 9, 52, 5, 0; Monad 9, 49, 6, 1; Hyperliquid 15, 9, 13, 10; Solana 18, 46, 15, 4.

## The incident configurations, replayed

| Incident | Configuration (threshold from the source; timelock read as none) | Replayed composite | Published targets at or below |
|---|---|---|---|
| Radiant Capital, 2024-10, $53M | Safe 3-of-11 | 52 | 112 of 179 |
| WazirX, 2024-07, $235M | Safe 4-of-6 | 47 | 101 of 179 |
| Bybit, 2025-02, $1.46B | Safe 3-of-6 | 44 | **91 of 179 (51%)** |
| Humanity Protocol (Ethereum), 2026-06, $32M to $36M | 3-of-6 multisig | 44 | 91 of 179 |
| Humanity Protocol (BNB Chain), 2026-06 | 3-of-5 multisig | 43 | 88 of 179 |

The table's other incidents (bare-EOA admins such as Munchables, DeltaPrime and UPCX, a verifier set of one at Kelp, a Solana Security Council at Drift) are not replayed here: this uses only the Safe convention the repository already documents. Drift has its own backtest (`data/backtest_2026-09-17-drift-protocol-security-council-compromise.md`).

## How to read it, and what it does not say

- It says: 51% of the targets this oracle publishes score no better than the multisig that held Bybit's wallet before it was drained, and 60% have no timelock score. That is a statement about the distribution of what is tracked, and **it depends on which oracles are counted and on the formulas behind them**:

  | Set | Targets | At or below Bybit's 44 | Timelock score 0 |
  |---|---|---|---|
  | All nine oracles | 179 | 91 (51%) | 107 (60%) |
  | Without Robinhood Chain | 116 | 49 (42%) | 68 (59%) |
  | Without Tempo, Solana and Hyperliquid (their own multisig formulas) | 132 | 61 (46%) | 67 (51%) |
  | Without those three and Robinhood Chain | 69 | 19 (28%) | 28 (41%) |

  So the honest range for "at or below Bybit's configuration" is **28% to 51%**, depending on the set.
- **The composites are not on one multisig formula.** The EVM oracles add 5 points per extra owner (the Safe convention replayed here); Tempo (rule R5, `20k-(n-k)`), Solana (the Squads ladder) and Hyperliquid (its 4.6 ladder) score multisigs differently, and Tempo and Solana scores go down as owners are added. The same multisig can land several points higher or lower in those ecosystems (a 4-of-42 Tempo committee is counted as 39 there and would replay to 56 in the EVM convention; three Solana Squads targets counted at or below WazirX's 47 would replay to 49 or 50). That is why the third row above exists.
- It does not say these targets will be hit, or that the score would have flagged those incidents beforehand. In Bybit, WazirX, Radiant and Humanity the threshold gave no protection (blind signing, a falsified interface, keys on one device); a higher score on paper is not the same as being safe from those.
- The set is not a sample of DeFi: it is what this project chose to track, heavy on small new protocols (Robinhood Chain's 63 targets have a median of 33; Hyperliquid's 15 are HIP-3 dexes, staking managers and treasuries with a median of 9).
- The scores are the ones published to the testnet oracles, so Ethereum and Hyperliquid can lag their live scorers (the count of targets, not the method, is what differs).
- A Safe replay ignores a module, a guard and the signers' independence; each real target may sit lower or higher for those reasons.

## Reproduce

`python3 scripts/incident_exposure.py --out <file>` (about a minute; eth_call on 8 testnet RPCs, `getProgramAccounts` on Solana devnet; the file now carries each row's target address; exits non-zero if any oracle or target could not be read). Tests: `scripts/lib/tests/test_incident_exposure.py`.
