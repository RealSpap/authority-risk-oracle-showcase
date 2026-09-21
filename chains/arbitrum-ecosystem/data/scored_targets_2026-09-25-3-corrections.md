# Arbitrum Ecosystem -- 3 targets closed out by an independent verification pass, 2026-09-25

Not a scouting or maintenance run of this pass's own: an independent
verification pass re-checked three gaps this ecosystem's own prior notes had
explicitly left open, and handed back the missing facts. Implemented here
faithfully (not re-derived from scratch), then confirmed live against
`https://arb1.arbitrum.io/rpc` via `scripts/validate_all_scorers.py
--ecosystem arbitrum` before this was written up -- every read below matched
the given facts exactly on-chain today. Appended as indices 10-12 (after the
10 already-pushed/registered targets), so `trackedTargets()` indices 0-9 keep
their meaning. Nothing was pushed on-chain by this pass.

## 10. Dolomite Margin, `0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072`

CLOSES the gap in `data/scored_targets_2026-09-20-maintenance-gmx-v1.md`
("Scouted, traced, NOT scored"): the enumeration of `DEFAULT_ADMIN_ROLE`
holders on `DolomiteMargin.owner()` (`0xC2B66E24...`, "DolomiteOwnerV2",
AccessControl-based) rested on a single RPC's `eth_getLogs`. Now confirmed:
exactly one holder, a Gnosis Safe 1.4.1 **2-of-3** (`0xa75c21C5...`).
`owner().secondsTimeLocked()` = **300s** (5 minutes) -- real, but far short of
this project's 24h floor for full `timelockScore` credit.

This is a DIFFERENT pool/owner pair than the `DelayedMultiSig`
`0xE412991F...` (1-day delay) some earlier scouting passes traced: that pair
governs a separate, near-empty legacy pool `0x6a769862...` (6 markets, zero
balances) and is not read by this scorer. Grepped this repo: no prior entry
used the old pool/delay, so there was nothing to correct away from -- this is
a straight addition.

Score: 50 / 35 / 30 -> **40**. TVL (DefiLlama `dolomite`,
`chainTvls.Arbitrum`): ~$25.94M supplied / ~$11.49M borrowed.

## 11. USD AI mint/burn authority, `0xffA10065Ce1d1C42FABc46e06B84Ed8FfEb4baE5`

CLOSES the gap in `data/scored_targets_2026-09-19-maintenance.md`
("Considered, not added"): that note stopped at "`mint()`/`burn()` are gated
by an immutable `_bridgeAdapter` that has no public getter, and its own
authority was not traced". That adapter is now traced: a LayerZero V2
`OAdapter` (Sourcify exact match, plain `Ownable`), owned by a **3-of-3**
Gnosis Safe (`0x5F0BC72F...`), which also holds `DEFAULT_ADMIN_ROLE` on the
USDai token itself (disclosed context, not re-checked live -- no full token
address confirmed this pass). This project's only documented delay for USD
AI, a 48h `TimelockController` (`0x0EEA1EE0...`), gates the proxy UPGRADE
path only and does not cover mint/burn.

TVL corrected: ~$208.3M supplied / ~$401.5M borrowed (the 2026-09-19 note had
~$307.2M from an earlier read). DefiLlama `usd-ai`, `chainTvls.Arbitrum`.

**Live finding, not in the brief that closed this gap**: `owner()` resolves
to exactly the expected Safe, but this project's own module-authority gate
(`scripts/lib/safe_modules.py`, added 2026-09-21) currently finds one
unanalyzed module on it (`0x02878D80...`) and treats the whole Safe as
UNRESOLVED authority until that module is analyzed. So this scorer reads a
conservative **20 / 0 / 0 -> 8** live today, not the 65/45/0 -> 40 the raw
3-of-3 owners/threshold alone would suggest. That is the shared gate doing
its job, not a bug -- analyzing that module lifts it automatically.

## 12. Gains Network gTrade Diamond, `0xFF162c694eAA571f685030649814282eA457f169`

CLOSES the gap in `data/scored_targets_2026-09-20-maintenance-gmx-v1.md`
("Left for a next run rather than scored from one hop"), and corrects what a
shallower read of that note's own 14-day controller would have scored. The
Diamond's upgrade surface has THREE OpenZeppelin `TimelockController`s: 14
days (full `diamondCut()` via ProxyAdmin), 3 days (`GOV_TIMELOCK`), and a
previously-missed fourth, `GOV_EMERGENCY_TIMELOCK` `0x893FCf48...`,
`getMinDelay()` = **36,000s (10 hours)** -- the real weakest link.

`PROPOSER_ROLE`/`CANCELLER_ROLE` on that 10h timelock are held by three
parties: a 4-of-7 Safe (`0xc07EEd65...`), a 2-of-4 Safe (`0xe8997C50...`) and
a bare EOA (`0x80Fd0ACc...`, confirmed `eth_getCode` = `0x`).
`EXECUTOR_ROLE` is held by the two Safes only, not the EOA. Shortest real
path to a full `diamondCut()`: the bare EOA alone schedules, 10 hours pass,
the weaker 2-of-4 Safe executes -- shorter and weaker than the 3-day or
14-day paths, so this is what drives the score, per METHODOLOGY.md ("scored
on the gap, not the presence of a timelock somewhere").

Weakest PROPOSER initiator = bare EOA -> adminKey 10, multisig 0 (this
project's bare-EOA band). `timelockScore` = 0: the 10h delay is real but is
entered by a single key with no independent veto (the same EOA also holds
`CANCELLER_ROLE`, alongside the same two Safes that can also execute -- not
an independent check), and 10h is under this project's 24h floor for any
non-zero credit regardless.

Disclosed, not scored: the 4-of-7 Safe additionally holds
`TIMELOCK_ADMIN_ROLE` on all three timelocks and can reassign who may
propose or execute on any of them at will. It does not itself skip the 10h
delay on an already-scheduled call, so it is not folded into the score.

Score: 10 / 0 / 0 -> **4**. TVL (DefiLlama `gains-network`,
`chainTvls.Arbitrum`): ~$11.74M + ~$1.63M staking.

## Verification

`python3 -m unittest discover -s scripts/lib/tests` -- 2153 tests, 0
failures (skipped=6, expected failures=2, both pre-existing and unrelated).
`python3 scripts/validate_all_scorers.py --ecosystem arbitrum` -- 13/13
targets pass live against `arb1.arbitrum.io` (plus
`ethereum-rpc.publicnode.com` for the pre-existing Uniswap L1 check), 0
problems. New unit tests added in
`scripts/lib/tests/test_arbitrum_ecosystem_scorers.py` for all three
scorers, following this file's established fake-dispatch convention.
