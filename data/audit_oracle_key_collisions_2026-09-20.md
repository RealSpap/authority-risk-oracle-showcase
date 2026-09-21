# Oracle key collision audit, all ecosystems, 2026-09-20

Phase: `maintenance` (transverse). Nothing about any score changes and nothing is pushed. This adds a pre-push guard to every
push script and a tool that audits every ecosystem at once, and records the first result.

## Why

The oracle stores one score per key (`_scores[target] = score` in `src/AuthorityRiskOracle.sol`, one PDA per target on Solana). Two
scored entries on the same key therefore overwrite each other without any error: `updateScores()` succeeds, the tracked count is
lower than the number of scores pushed, and the first entry can no longer be read back. On 2026-09-19 a Hyperliquid rehearsal showed
this for real (15 scores pushed, 13 stored: the HIP-3 dexes `mkts` and `para` sit at the same address as two scored HyperEVM
contracts), fixed there with derived keys and a hard refusal (`chains/hyperliquid/deploy/push_scores.py::resolve_oracle_keys`).
The other seven EVM push scripts built their key list with `Web3.to_checksum_address(entry["target"])` and no check at all, and the
Solana one did the same with `b58decode` (Zcash's attestation bundle already refuses duplicate target ids), so the same class of loss
was possible on any of them the day two targets shared an address. The Morpho vault layer planned in
`data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md` (one score per vault and one per controller, controllers shared
by many vaults) is exactly the shape that would trigger it.

## Method

`python3 scripts/check_oracle_key_collisions.py` runs every ecosystem's `score_all()` live, each in its own subprocess (the same
isolation and ecosystem table as `scripts/validate_all_scorers.py`), and groups the entries by oracle key: EVM addresses lowercased,
Solana and Zcash identifiers exactly. Hyperliquid goes through its push script's own resolution first. An ecosystem that cannot be run
or returns nothing is reported FAILED, never clean. Read-only: public RPC reads, no key, no transaction. The on-chain counts below come
from `scripts/live_target_counts.py` (`trackedTargetsCount()` on each testnet oracle, the Solana registry for Solana), read the same day.

## Result (score_all() as of 2026-09-20, evening)

| Ecosystem | Entries | Distinct keys | On-chain tracked | Unresolved collision |
|---|---|---|---|---|
| Robinhood Chain | 62 | 62 | 62 | none |
| Ethereum L1 | 19 | 19 | 20 | none (see below) |
| Arbitrum | 10 | 10 | 10 | none |
| Base | 9 | 9 | 9 | none |
| Solana | 18 | 18 | 18 | none |
| Hyperliquid | 15 | 15 after derived keys | 15 | none (2 known address pairs, resolved) |
| Tempo | 14 | 14 | 14 | none |
| Plasma | 9 | 9 | 9 | none |
| Monad | 9 | 9 | 9 | none |
| Zcash (no on-chain oracle, attestation batch) | 6 | 6 | n/a | none |

`RESULT: NO UNRESOLVED KEY COLLISION` over 171 entries. Hyperliquid's two colliding addresses are the known ones
(`0x71f0...29ec`: HIP-3 dex `mkts` and Kinetiq HIP3StakingManager, `0x8888...6ed3`: HIP-3 dex `para` and para StakingVault); both are
resolved by the push script's derived keys, as before.

Ethereum L1 shows 20 tracked on-chain against 19 scored. The extra one is not a collision (a collision would lower the stored count):
it is row 3 of the L1 deploy table, the retired Ethena minter `0x2CC440b7...8Afc3`, disclosed in `chains/ethereum-l1/deploy/README.md`
as "the retired minter, not refreshed" (read on-chain today: 55 / 100 / 0 / 100 / 20 / 52, last updated 2026-09-19). The other eight
oracles hold exactly as many tracked keys as the scorers produce.

## What the guard does

`scripts/lib/oracle_keys.py::assert_unique_oracle_keys()` runs before any key is read and before any transaction is built and raises
`SystemExit`, naming every colliding key and the entries on it, so the whole push is refused instead of silently dropping scores. It is
called in the push scripts of Arbitrum, Base, Monad, Plasma, Tempo, Ethereum L1, Robinhood Chain (`scripts/update_scores.py`) and Solana
(exact comparison, base58 is case-sensitive; also in its `--dry-run`). Those scripts push `entry["target"]`, so the guard compares
`target` (EVM forms are unified the way `Web3.to_checksum_address` unifies them: case, `0x` prefix, spaces, bytes) and a derived
`oracleKey` does not hide a collision. Hyperliquid keeps its own resolution, which pushes `oracleKey` and already refuses any collision
it cannot resolve. One behaviour change to be aware of on Solana: the live read of the scores (`score_all`) now happens at the start of
`push_live()`, before the payer key is loaded and before the `initialize` transaction, instead of after it, so that a collision is
refused before anything is signed. Nothing else in the flow moved.
Tests: `scripts/lib/tests/test_oracle_keys.py` (the helper, an AST check that in each script the guard is a top-level statement that
precedes the first line that builds a key, reads the private key or builds a transaction, the behaviour of the six assemblers in a
subprocess each, the behaviour of Robinhood's `_run()` and Solana's `push_live()` and `--dry-run` with the network and the key
replaced by stand-ins, and the audit tool).

## Not claimed

- This is the state of `score_all()` and of the oracles today. It says nothing about earlier pushes.
- A collision between a scored target and an address that is on the oracle for another reason (an orphan such as the L1 retired
  minter) is not detected by a check on the scored set alone. The count comparison above catches a difference in size, not a swap.
- `scripts/prepared_pushes/2026-09-20-robinhood-index16-4-new-targets.py` builds its four keys from a fixed list, is a one-off, and is
  not guarded.
- Zcash has no on-chain oracle: uniqueness is checked on the target identifiers of the attestation batch, not on a storage slot.
