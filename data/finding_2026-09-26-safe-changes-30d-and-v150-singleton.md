# What changed on the tracked Safes in 30 days, and a Safe v1.5.0 blind spot it exposed

2026-09-26. New read-only tool `scripts/check_safe_changes.py` (+ `scripts/lib/safe_changes.py`, 7 tests): reads the Safe
management events (AddedOwner, RemovedOwner, ChangedThreshold, EnabledModule, DisabledModule, ChangedGuard, ChangedMasterCopy)
for every Safe in the overlap registry (93 Safes, the same registry `who_controls.py` indexes) over a recent window and ranks them,
module or singleton change first. Each ecosystem is checked against a CONTROL, the count of `ExecutionSuccess` events on the same Safes
and window: a control of zero, or logs that cannot be fetched, is reported UNREAD, never as a quiet month. Disclosed only: no score reads it.

## Window 2026-08-27 to 2026-09-26 (read live)

| Ecosystem | Safes | Control (executions) | Change events | Read |
|---|---|---|---|---|
| Robinhood Chain | 25 | 626 | 33 (9 Safes) | yes |
| Ethereum L1 | 14 | 62 | 2 | yes |
| Arbitrum | 14 | 48 | 4 | yes |
| Plasma | 11 | 45 | 1 | yes |
| Base | 7 | 67 | 0 | yes (Tenderly, 1,000-block windows: publicnode serves Base logs only near the head) |
| Tempo | 4 | 0 | 0 | **UNREAD**: control empty, so no conclusion (its 4 Safes may simply be idle: an idle Safe and a truncating RPC look the same) |
| Monad | 13 | | | **UNREAD**: the public RPC answers 413 above ~100 blocks per `eth_getLogs` (probed: 100 OK, 500 refused), about 6.5M blocks in 30 days, not feasible without an indexer |
| Hyperliquid | 5 | | | **UNREAD**: 1,000-block cap per call and the public RPC answers 'rate limited' even after backoff (7-day window tried) |

What moved (each one is an on-chain fact with a transaction hash in the tool's output):
- **Ethereum L1, Morpho Blue owner Safe `0xcBa28b38...`: 5-of-9 to 6-of-10 on 2026-09-22 00:01 UTC** (10th signer `0xaD0E1B38...`, the
  nine previous ones kept). Already recorded as a 55 -> 56 drift on 24-25/09; this dates and explains it. See the crossExposure note below.
- **Robinhood, ramses Safe `0x20D630cF...`: singleton changed to v1.5.0 SafeL2 on 2026-09-25 02:01 UTC**. The project had no v1.5.0 in its
  published-build list (below).
- Robinhood, three Safes moved to the canonical v1.4.1 SafeL2 (`0x29fcB43b...`) between 08-28 and 09-02 (pendle, grove_steakhouse, strato_bridge).
- Robinhood, one Pendle Safe (`0xE6F0489E...`): five owners added on 09-02, threshold 2 (09-04) then 3 (09-08), further churn; a second Pendle
  Safe (`0x7877AdFa...`) threshold 3 and one owner added on 09-02. **Checked afterwards**: the tracked cross-ecosystem Pendle committee is the
  second one, `0x7877AdFa...` (3-of-5), and its live signer set EQUALS the 09-19 snapshot the Arbitrum and Plasma scorers compare against (its change
  on 09-02 predates the snapshot); the churn is on `0xE6F0489E...` (now 3-of-6, one signer in common with that snapshot), a registry-only Safe that no
  scorer reads. So no Pendle score is affected by these changes.
- Robinhood, both `longbow` Safes replaced the same 3 signers with the same 3 new ones on 09-13; `symbiosis` and `orvex` one swap each.
- Arbitrum, gTrade emergency Safe `0xe8997C50...`: 2 signers replaced on 09-03.
- Plasma, Ethena Safe: guard set to `0x74abe780...` on 09-11, the EthenaSafeGuard already analyzed in `safe_modules.py` (same guard as on L1).

## The v1.5.0 blind spot (fixed, primary source checked)

`scripts/check_safe_modules_guards.py` flagged the ramses Safe: singleton `0xEdd160fE...` and fallback handler `0x3EfCBb83...` were "not a
published build" in `scripts/lib/safe_modules.py`, which listed builds up to v1.4.1. Consequence of that list: `safe_owners_and_threshold`'s
authority gate returns None for such a Safe, so a scorer that reads it would fall back to its conservative score instead of counting the owners.
Checked, not assumed: safe-global/safe-deployments v1.5.0 lists exactly these two addresses as canonical on chains 1 and 4663 (code hashes
`0x1801932271...` and `0x3c6a85bcf7...`), the live code hash on Robinhood Chain equals both, and Sourcify has an exact match named SafeL2 on
Ethereum for the singleton. Both were added to the canonical tables; the ramses Safe's own `VERSION()` reads 1.5.0. An unknown singleton still
classifies as unanalyzed (tested). Live re-score of the Ramses CL V2 targets with the fix: 15/5/0/100, composite 8, the Safe read as **1-of-1 with a
bare-EOA sole signer** (`0xbE0ca442...`) that is also proposer, canceller and executor of a 0-delay timelock. Without the fix the Safe would have
taken the conservative unresolved path; that path was not re-run, so no claim is made about the number it would have produced. The sweep now reads 93 registered Safes, 0 UNANALYZED, 91 on a published build (the 92nd is the analyzed
Robinhood Chainlink rebuild).

## The Chainlink Safe module, on four more chains

Adding the Chainlink feed-owner Safes (Ethereum, Base, Arbitrum, Monad) to the registry made the module sweep flag 4 UNANALYZED modules. Each is
byte-identical (5,451 bytes, same code hash) to the Confirmed Transaction Module analyzed on Robinhood Chain on 09-21, so the analysis of its logic
carries over; its state does not. manager() is the Safe itself on all five chains. **Unlike Robinhood's unused one, it is in active use on the other
three that could be replayed**: Ethereum 280 Confirmed, 90 Executed, 185 Revoked; Arbitrum 8 Confirmed, 8 Executed; Base 9 ExecutorUpdated. The
executor set was replayed from the `ExecutorUpdated` events (all pages) and matched against live `isExecutor()` for every address ever touched:
8 executors on Ethereum, 7 on Base, 8 on Arbitrum, almost the same addresses, two of them also signers of the Safe. An executor runs only what the
Safe's threshold confirmed. Monad has no explorer and was checked for `manager()` only. Added to `KNOWN_ANALYSES`, each with that caveat.

## One methodology point for Spap (not changed)

`score_morpho_blue_l1` compares the committee by exact set equality with a 9-signer snapshot. The 10th signer makes the equality false, so the
cross-ecosystem flag is dropped (crossExposureScore 80 -> 100) while 9 of the 10 signers remain shared with the Base, Robinhood and Tempo
Safes, whose sets did not move and keep 80: the same committee scored two ways. Whether to keep exact equality or test containment/overlap is a
calibration decision; a card was added. Pendle is not an instance of it today (see above); it is the same mechanism waiting to happen if the tracked Pendle Safe adds a signer.

## Verification

`python3 scripts/check_safe_changes.py --days 30`, Tenderly public gateways (Ethereum, Arbitrum, Base) and each chain's own RPC (Robinhood,
Plasma); `python3 scripts/check_safe_modules_guards.py` exit 0 after the additions; `python3 -m unittest` `test_safe_changes.py` (7) and
`test_safe_modules.py` (41). No key read, nothing sent.
