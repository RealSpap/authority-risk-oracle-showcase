# Re-push of all nine oracles, 2026-09-20 evening

Run by the maintainer with `scripts/repush_all_oracles.sh` (two terminals: the eight shared-key oracles, and
Robinhood on its own key), read back by the assistant with plain `eth_call` and `getProgramAccounts`, no key.
Every step recomputed each target live before sending one `updateScores` transaction per oracle.

| Oracle | tracked targets after | transaction | block | first entry turns stale |
|---|---|---|---|---|
| Base (Sepolia) | 9 | `0xc54368c9af4390bff723587ab9ddaa3d530e5c2d3afd4ec518ea7835a8c6fded` | 47,082,398 | 2026-09-29 19:38 UTC |
| Plasma testnet | 9 | `0x8f69a4b491c7d3a296bf12a6be2569388b9d34b5e739354db545329a76a8b49a` | 34,104,451 | 2026-09-29 19:38 UTC |
| Monad testnet | 9 | `0x4daf1f9e777386a822bfcfcc3d0bea3906b6b3dca18854c7e7bab24a152d5404` | 64,250,470 | 2026-09-29 19:38 UTC |
| Arbitrum (Sepolia) | **10** (GMX V1 Vault added) | `0x2501756896f13956900699cf1d1af7a5149b21dddc05436f30d8eb0b1b7110ce` | 310,972,554 | 2026-09-29 19:39 UTC |
| Ethereum L1 (Sepolia) | **20** (Aave V3 Horizon added) | `0x07320bc3542f279d9e0fcb7974211b0faaa3dc4360d397db36cad2f986822fcb` | 11,746,235 | 2026-09-29 19:39 UTC, except the retired Ethena minter (index 3): 2026-09-28 16:39 UTC |
| Tempo (Moderato) | 14 | `0xcc4ee7d9785de7ae6ca6dc5cd13f7848fc1a6ce3b1603f155c3e86b0e5dd5acc` | 36,169,529 | 2026-09-29 19:49 UTC |
| Robinhood Chain testnet | **62** (four targets added, rotation audit index 16) | `0x3075f58821329f6ac9716006486bd3fef24282e34904c06d81d5a7996904112a` | 122,144,286 | 2026-09-29 19:59 UTC |
| Hyperliquid (HyperEVM testnet) | 15 | in the maintainer's terminal log | | 2026-09-29 19:51 UTC |
| Solana (Devnet program) | 18 | in the maintainer's terminal log | | 2026-09-29 19:52 UTC |

Live counts afterwards (`python3 scripts/live_target_counts.py`): 62+20+10+9+14+9+9+15+18 = **166 tracked
targets on 9 oracles, 165 of them actively refreshed** (the retired Ethena minter is the one that is not).
`python3 scripts/oracle_freshness.py` reads every entry of every oracle as fresh, the oldest refreshed one dated
2026-09-20 19:38 UTC. Before this run the counts were 160 (58+19+9+9+14+9+9+15+18): the run carried the targets that
other passes had scored and merged but not yet pushed, five in all.

Verified after the run (2026-09-20 22:00 to 22:40 CEST): the live scorers were recomputed and compared with each oracle's
scores, six fields per target. Base 9/9, Plasma 9/9, Monad 9/9, Arbitrum 10/10, Tempo 14/14 and Robinhood 62/62 read back
identical (0 differences); Ethereum L1 19 of 19 scored targets identical, the 20th on-chain entry being the retired
Ethena minter that is no longer refreshed. Not recomputed here: Hyperliquid and Solana (their own deploy records
carry the read-back for the earlier same-day pushes; this run's transactions were not diffed against a fresh recompute).

The next re-push is due before the earliest expiry above (2026-09-28 16:39 UTC for the retired Ethena entry, which
is left to expire on purpose, then 2026-09-29 19:38 UTC), and again around 2026-10-05 and 2026-10-11 to stay fresh
through the 2026-10-12 deadline.
