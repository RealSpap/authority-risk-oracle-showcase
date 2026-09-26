# What is queued behind the watched timelocks (2026-09-26): nothing executable, 24 dead entries, recent traffic listed

New read-only tool `scripts/check_pending_ops.py` (+ `scripts/lib/pending_ops.py`, 5 tests). A timelock's delay is a promise; the queue is the
fact. For each watched timelock it reads the queue events of the last N days (365 by default: an OpenZeppelin queue has no expiry), asks the
contract itself whether each operation is still pending (`isOperationPending` for OpenZeppelin `TimelockController`, `queuedTransactions` for the
Compound-style `Timelock`), and lists what becomes executable and when, plus what was queued in the last 14 days and is already gone. Disclosed only:
no score reads it. Ethereum and Arbitrum through Tenderly's public gateway (full-history `eth_getLogs`), calls through publicnode.

## Read live 2026-09-26 (6 timelocks, all read, 0 unread)

| Timelock | Family, delay | Queue events in 365 d | Latest | Executable pending now |
|---|---|---|---|---|
| Uniswap Governance Timelock (root of 11 tracked targets on 5 ecosystems) | Compound-style, 2 d (grace 14 d) | 54 | 2026-07-25 | 0 |
| Compound Governance Timelock | Compound-style, 2 d | 572 | 2026-09-22 | 0 (+24 expired) |
| Ethena Timelock | OpenZeppelin, 24 h | 186 | 2026-09-24 | 0 |
| Arbitrum L1 Timelock | OpenZeppelin, 3 d | 69 | 2026-09-18 | 0 |
| Arbitrum L2 Core Governor Timelock | OpenZeppelin, 8 d | 14 | 2026-09-04 | 0 |
| Arbitrum L2 Treasury Timelock | OpenZeppelin, 3 d | 6 | 2026-06-25 | 0 |

- **The 24 "expired" Compound entries are dead, not live**: their ETA passed 204 to 236 days ago, never executed nor cancelled, so past `eta + GRACE_PERIOD`
  (14 d), so they can never execute; the `queuedTransactions` mapping is never cleaned. They are counted and hidden by default (`--show-expired` lists
  them), because a queue listing that is 100% dead entries hides the one that could still happen. 17 are `updateAssetSupplyCap`, 5 `deployAndUpgradeTo`
  and 2 `ccipSend` (by function selector, targets not otherwise identified).
- Recent traffic already gone (executed or cancelled, the tool cannot tell which): Compound queued two cross-chain `sendMessage` calls on 09-22;
  **Ethena queued and cleared seven changes since 09-12, including LayerZero `setConfig` and `setPeer` on 09-16** (its OFT verifier configuration is
  what this project scores on Ethereum L1 and Plasma; the 25/09 full L1 dry-run found no Ethena divergence, so the published score matches); Arbitrum L1
  cleared a Seaport order on 09-18.

## What this is and isn't

A watchlist of 6 timelocks probed live (family and delay read from the contract), not every timelock the oracle scores: Aave's governance executors, Sky's
pause proxy, Morpho Vault V2 `submit`, Tempo and Robinhood timelocks are not covered yet and would each need their own event family. "0 pending" means 0
in the logs the RPC returned; a timelock whose log range is refused is reported UNREAD, never as an empty queue. A quiet timelock (Uniswap: 54 events in a
year, none since 07-25) and a truncating RPC look alike from outside, which is why every row shows its event count and latest date.

## Verification

`python3 scripts/check_pending_ops.py --days 365 --recent-days 14`, exit 0, 6/6 read. Unit tests on the decoding and status logic. No key, nothing sent.
