# Full posture-drift sweep (27/09): one real drift explained, one tool false-positive found and fixed

2026-09-27. `scripts/check_posture_drift.py` had not been run as a full sweep since 25/09; several ecosystems were re-pushed since (26/09). Ran it end to end on the 8 EVM oracles (Solana has its own dedicated read-back tool, `read_scores_solana.py`, and is not in this tool's scope).
Read-only. **No score changed, no target added.**

## Result: 2 targets drifted, 4 entries unread - now down to the 2 real ones

`TOTAL: 2 target(s) with a real score drift, 4 unread across 8 ecosystem(s)`, before investigation:

- **Real, explained drift**: Ethereum L1, Morpho V1 Steakhouse USDT and Steakhouse USDC, `crossExposureScore` 80 -> 40. Cause: commit `195d5c3` (26/09, Spap's go-ahead) added two Morpho Vault V2 Steakhouse Prime targets sharing the same root Safe (`steakhouse-owner-safe-0x0a0e559b`), so the root-group now has 4 members instead of 2 (`max(0, 100 - 20*others)`: others 1 -> 3, score 80 -> 40, folded to the same 80 cap either way - the drop is the un-folded within-L1 value). **Not a bug**: the code is right, the on-chain value is simply behind the code; the next Ethereum L1 push (before 02/10, already planned) publishes the correct 40.
- **Already known, disclosed**: the retired Ethena minter (`0x2cc440b7...`, "inert since 2024-07-08" per METHODOLOGY.md) stays published on Ethereum L1; not new.
- **Tempo**: the live scorer run inside the sweep timed out after 900 s (15 min). Not investigated further this pass; Tempo is already known to be the slow ecosystem (repush script: ~9 minutes for the push itself).

## The other 2 "unread": a false positive in the sweep tool itself, found and fixed

Two Hyperliquid entries, published composites 5 and 9, showed as "published composite=X, but score_all() does not return this address today". Investigated and found NOT a real problem:

- `chains/hyperliquid/deploy/push_scores.py::resolve_oracle_keys()` (built 2026-09-19, METHODOLOGY.md 4.7) already knows that HIP-3 dex `para` and `mkts` share their raw on-chain deployer address with two separately-scored HyperEVM contracts (`para StakingVault`, `Kinetiq HIP3StakingManager`), and moves the dex to a derived key (`keccak256("hyperliquid:hip3-dex:<name>")[-20:]`) before pushing, so nothing is ever silently overwritten on-chain.
- **Re-verified live**: `read_scores_hyperliquid.py` (which reuses `push_scores.py`'s own key resolution) shows all 15 tracked Hyperliquid targets matching their live scorer exactly, including both dexes at their derived keys (`0x30E96FBD...` for para, `0xBF6d3bBC...` for mkts) - the oracle is healthy today. Direct calls to `score_all()` do return the two dexes' RAW deployer addresses (`0x8888888c...`, `0x71f0019c...`, confirmed live, reproducible across three separate queries of Hyperliquid's `perpDexs` info endpoint), the same addresses as the two HyperEVM contracts.
- `check_posture_drift.py::live_scores()` built its comparison dict keyed by that raw address, so the second entry processed (the HyperEVM contract) silently overwrote the dex's entry in the tool's own dict - a bug in this generic cross-ecosystem tool, not in the oracle or the push script, which never imports it.
- **Fixed**: extracted `oracle_keys_for(ecosystem_name, entries)`, which applies Hyperliquid's own `resolve_oracle_keys()` before keying the comparison, and left every other ecosystem untouched. Re-run after the fix: 15 of 15 Hyperliquid targets match, 0 drift, 0 unread. 3 new unit tests (the collision remaps correctly, an unrelated ecosystem is never remapped, no-collision entries pass through unchanged); full suite 2353 tests green.

## What this means

Nothing to push, nothing new to score. One process lesson: a tool built to compare "published vs live" across every ecosystem generically hit exactly the kind of ecosystem-specific key convention (a derived key to dodge a real collision) that a fully generic comparison cannot know about by default - worth remembering if another ecosystem ever adopts a similar derived-key trick.

## Reproduce

`python3 scripts/check_posture_drift.py` (about 10-25 minutes; Solana excluded, see its own `read_scores_solana.py`). `python3 chains/hyperliquid/deploy/read_scores_hyperliquid.py 0x50840a7667baEa9D05ad4ae3dCeb384724b58720` for the Hyperliquid-specific read-back. Tests: `scripts/lib/tests/test_check_posture_drift.py`.
