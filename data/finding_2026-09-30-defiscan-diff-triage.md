# DeFiScan v2 diff, first triage: 4 real coverage gaps, no published score changes, 5 DeFiScan errors (investigation, nothing scored)

2026-09-30. `python3 scripts/check_registry_diff_defiscan.py` lists the live keys (EOA, multisig, timelock, upgradeable, unknown) that
DeFiScan v2 attaches to value and that this repository never mentions. The top groups on protocols we already cover were triaged by five
verifiers (read on chain on two RPCs, verified sources, our scorer code), and three claims re-read by me on both RPCs (marked **).
**No published score changes**: none of these keys holds a power our scores rest on (upgrade, POOL_ADMIN/EMERGENCY_ADMIN, the timelock path).

## Real gaps (disclosure, not score)

| Key | What it can do, read on chain | Bound | Value |
|---|---|---|---|
| Ethena `0x21F9236e...` and `0x49e9f81A...`, bare EOAs ** | `BLACKLIST_MANAGER_ROLE` on sUSDe (both) and sENA (the second): freeze any holder's shares instantly, including a lending market holding sUSDe as collateral | freeze only, reversible, for the two EOAs; seizing (`redistributeLockedAmount`) needs `DEFAULT_ADMIN_ROLE`. **Corrected 1 Oct:** that ends at the Ethena timelock for sUSDe (not a proxy), but **sENA is an upgradeable proxy whose ProxyAdmin `0xf849D779...` is owned by the Ethena Safe 5-of-10 with no timelock read on that path**, so for sENA the Safe can replace the code, seizing included | sUSDe 1,267.2M USDe **, sENA 1,185.7M ENA |
| Lido Safe `0x8772e3a2...` 3-of-6 ** | live pauser of the CircuitBreaker for 7 contracts, including the WithdrawalQueue and the ValidatorsExitBusOracle: pause stETH-to-ETH withdrawals for 21 days, no delay; extendable by the Reseal Committee (5-of-6) outside Dual Governance's Normal state | no funds move; one pause, then the pauser is cleared | WithdrawalQueue 26,160 ETH |
| Lido Aragon Voting via the Finance app | can pay out the DAO treasury (Agent: 121.5M LDO, 23,365 stETH) without Dual Governance's stETH veto or the 0xCE04 timelock | the 5-day Aragon vote (2 of them objection) | DAO treasury, not users' stETH |
| Aave Recovery Guardian Safe `0x53cb4BB8...` 3-of-5 ** | `DEFAULT_ADMIN_ROLE` on Umbrella: can grant itself every Umbrella role, set slashing and cooldowns, pause, even revoke the Executor's admin | slashed funds go to the fixed Collector; Umbrella's ProxyAdmin stays with the Executor (no upgrade) | Umbrella stakers, about $282M per DeFiScan (not re-read) |

Plus a correction to our own earlier work: `finding_2026-09-26-l1-custody-authority-traces.md` said Spark's ALMProxyFreezable "holds nothing".
True of balances, not of privileges: it holds `SETTER_ROLE` on four untracked Spark Savings V2 vaults (rate settable inside [0%, 10%] APR with no
delay by a 1-of-2 and a 2-of-5 Safe) and the only `UPDATE_ROLE` on the CapAutomator. Addendum written there.

## Already covered or minor

Lido's Emergency Activation (4-of-7) and Execution (5-of-7) committees are the emergency path `score_lido_steth` already caps timelockScore at 60 for;
the source shows them weaker than feared (execute only proposals already scheduled, reset keeps the 4-day delay), so the cap is prudent. Sky's Chief
is derived live by `MCD_PAUSE.authority()`. Aave's GHO Risk Council and Risk Stewards Council (2-of-2) are the steward class already disclosed with
RISK_ADMIN. Aave Clinic Cleanup Safe and bot, Spark's freezer and incentives Safe, Lido's Community Staking and Reseal committees, Aave's
EmissionManager: bounded, small or brake-only.

## DeFiScan errors found on the way (so the second source is checked too)

- Lido emergency protection ends 20/06/2027 on chain, not 2026-06-20.
- Sky's pause delay is 48 h on chain, not 24 h.
- Aave `0xFCE5...171E` (RiskSteward, $19.29B reachable) lost RISK_ADMIN at block 25199939, one day after the 28/05 review; its successor is already in our known RISK_ADMIN set.
- Aave EmissionManager: its proxy admin is the PoolAddressesProvider, not itself.
- (Earlier today) Steakhouse owner Safe is 5-of-10, not "5/8"; `0x0000aeB7` is an allocator, not the guardian.

## Next, if wanted (Spap's call, none started)

A disclosure line for the Ethena blacklist keys on the Ethena family, and for Umbrella on the Aave family; checking which tracked Morpho markets take
sUSDe as collateral (a frozen holder could stall liquidations).
