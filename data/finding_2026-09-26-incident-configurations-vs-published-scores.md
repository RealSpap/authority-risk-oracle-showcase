# A third to a half of what the oracle publishes scores at or below Bybit's configuration before the hack (exposure, not prediction)

2026-09-26. `data/research_2026-09-21-authority-incidents-evidence-table.md` lists 23 authority incidents and concludes that the honest claim is "measured exposure of the authority path", not prediction (there is no sample of protocols that were not hit).
This measures that exposure. `scripts/incident_exposure.py` reads every published score from the deployed oracles, replays the incidents whose Safe threshold and owner count the sources state through the shared
Safe-rooted convention (`scripts/lib/scorers.py::_safe_rooted_scores` and the standard composite, no new formula), and counts the published targets at or below each. Read-only; 179 targets read, nothing unread.

## The published set today

179 targets on 9 oracles (Ethereum's 25 and Hyperliquid's 15 are the published numbers, one or more behind the scorers): **median composite 44; 107 targets (60%) have a timelock score of 0; 44 (25%) sit in the bare-key band (composite 10 or less).**
By oracle (targets, median composite, no timelock, bare-key band): Robinhood Chain 63, 33, 39, 20; Ethereum L1 25, 60, 9, 3; Arbitrum 13, 55, 5, 2; Base 13, 66, 3, 0; Tempo 14, 39, 12, 4; Plasma 9, 52, 5, 0; Monad 9, 49, 6, 1; Hyperliquid 15, 9, 13, 10; Solana 18, 46, 15, 4.

## The incident configurations, replayed

| Incident | Configuration in the source | Replayed composite | Published targets at or below |
|---|---|---|---|
| Radiant Capital, 2024-10, $53M | Safe 3-of-11, no timelock | 52 | 112 of 179 |
| WazirX, 2024-07, $235M | Safe 4-of-6, no timelock | 47 | 101 of 179 |
| Bybit, 2025-02, $1.46B | Safe 3-of-6, no timelock | 44 | **91 of 179 (51%)** |
| Humanity Protocol (Ethereum), 2026-06, $32M to $36M | Safe 3-of-6, no timelock | 44 | 91 of 179 |
| Humanity Protocol (BNB Chain), 2026-06 | Safe 3-of-5, no timelock | 43 | 88 of 179 |

The table's other incidents (bare-EOA admins such as Munchables, DeltaPrime and UPCX, a verifier set of one at Kelp, a Solana Security Council at Drift) are not replayed here: this uses only the Safe convention the repository already documents. Drift has its own backtest (`data/backtest_2026-09-17-drift-protocol-security-council-compromise.md`).

## How to read it, and what it does not say

- It says: 51% of the targets this oracle publishes score no better than the multisig that held Bybit's wallet before it was drained, and 60% have no timelock at all. That is a statement about the distribution of what is tracked, and it depends on which oracles are counted:

  | Set | Targets | At or below Bybit's 44 | Timelock score 0 |
  |---|---|---|---|
  | All nine oracles | 179 | 91 (51%) | 107 (60%) |
  | Without Robinhood Chain | 116 | 49 (42%) | 68 (59%) |
  | Without Robinhood Chain and Hyperliquid | 101 | 36 (36%) | 55 (54%) |

- It does not say these targets will be hit, or that the score would have flagged those incidents beforehand. In Bybit, WazirX, Radiant and Humanity the threshold gave no protection (blind signing, a falsified interface, keys on one device); a higher score on paper is not the same as being safe from those.
- The set is not a sample of DeFi: it is what this project chose to track, heavy on small new protocols (Robinhood Chain's 63 targets have a median of 33; Hyperliquid's 15 are HIP-3 dexes, staking managers and treasuries with a median of 9). The table above shows what removing those two long tails does; the per-oracle line shows where the low scores are.
- The scores are the ones published to the testnet oracles, so Ethereum and Hyperliquid can lag their live scorers (the count of targets, not the method, is what differs).
- A Safe replay ignores a module, a guard and the signers' independence; each real target may sit lower or higher for those reasons.

## Reproduce

`python3 scripts/incident_exposure.py --out <file>` (about a minute; eth_call on 8 testnet RPCs, `getProgramAccounts` on Solana devnet). Tests: `scripts/lib/tests/test_incident_exposure.py`.
