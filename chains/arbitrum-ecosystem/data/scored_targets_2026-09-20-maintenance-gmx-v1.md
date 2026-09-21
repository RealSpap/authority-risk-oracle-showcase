# Arbitrum maintenance run, 2026-09-20 (travailleur2) -- one target added, one scouted and not scored

Budget for this run was up to 10 new targets. One was added. That is the honest
result, not a target: the one added carries a real authority finding that needed
the time, and the second candidate traced (Dolomite) is left explicitly unscored
rather than half-scored. Two other candidates were probed and dropped, and that
is recorded below too.

Everything here was read live on Arbitrum One (chain 42161) on two independent
RPCs, `https://arb1.arbitrum.io/rpc` and `https://arbitrum-one-rpc.publicnode.com`.
Nothing was pushed on-chain by this pass.

## Added: GMX V1 Vault, `0x489ee077994B6658eAfA855C308275EAd8097C4A`

Address source: DefiLlama-Adapters `registries/gmx.js`,
`arbitrum: { vault: '0x489ee077994B6658eAfA855C308275EAd8097C4A' }`.

| Dimension | Score |
|---|---|
| adminKeyScore | 55 |
| multisigScore | 70 |
| timelockScore | 45 |
| oracleAuthorityScore | 100 |
| crossExposureScore | 80 |
| compositeScore | **57** |

Authority chain, each hop read live:

```
Vault.gov()             = 0x718507c37AA801A4b37aAE70dF8B2cB0bd4674b5   (GMX's bespoke Timelock)
Timelock.buffer()       = 86400                                         (24h on the signalled actions)
Timelock.admin()        = 0x58F582455b54d7c83d03BCeed95FAf72B37fdDD7   (Safe 1.4.1, 4-of-6)
Timelock.tokenManager() = 0x8D1d2e24eC641eDC6a1ebe0F3aE7af0EBC573e0D   (Safe 1.4.1, 5-of-8)
```

### The finding: a second committee can replace the timelock admin with no delay

In GMX's own `contracts/peripherals/Timelock.sol` (`gmx-io/gmx-contracts`),
`setAdmin(address)` is `onlyTokenManager` and assigns `admin` with no signal and
no buffer. This is not taken from the source alone. Two independent live checks:

1. The deployed bytecode at the timelock carries the `setAdmin(address)`
   selector `0x704b6c02` (and `requestGov(address[])`, `signalSetGov(...)`,
   `govRequesters(address)`, `setBuffer(uint256)` -- the deployed shape matches
   that source file).
2. By `eth_call` (no transaction, on both RPCs): `setAdmin` returns `0x` from
   the tokenManager Safe, and reverts `forbidden` both from the timelock's own
   admin Safe and from `0x...dEaD`.

So the 24h buffer really gates `signalSetGov` / `withdrawToken` / `mint` /
`approve`, but not who is allowed to queue them. That is why `timelockScore` is
45 and not in the 60-75 "bypass checked and ruled out" band of `METHODOLOGY.md`,
and why `multisigScore` takes the weaker of the two Safes (4-of-6 = 70, rather
than the tokenManager's 5-of-8 = 90): compromising either committee is enough.

### Context searched for, both directions

Aggravating, and the reason `crossExposureScore` is 80 rather than 100: that same
tokenManager Safe `0x8D1d2e24...` holds `PROPOSER_ROLE`, `EXECUTOR_ROLE` **and**
`CANCELLER_ROLE` (all three `true`, read live) on the GMX V2 timelock
`0x2Dd99f39f58445CDDC57AA5E0DB2C367335BBD44`, which is one of the three
`ROLE_ADMIN` holders of the already-tracked GMX V2 RoleStore (index 0). One
committee, two tracked targets. The two Safes also share 2 signers outright
(`0xc22aDD51...`, `0xeAA56005...`, 2 of 6 and of 8).

Attenuating, found by looking for it:

- `requestGov(address[])` is an instant gov-handover path, but it is
  `onlyGovRequester`, that registry is only writable through the *delayed*
  `setGovRequester`, and the timelock has emitted **zero**
  `SignalSetGovRequester` events since deployment. No requester was ever
  registered; the path is dormant, not open.
- `SignalSetGov` has never been emitted either: the delayed gov-change path has
  never been exercised.
- `Vault.isSwapEnabled()` and `Vault.isLeverageEnabled()` are both `false`. V1 is
  wound down for new trading. Disclosed in the scorer notes, and deliberately
  **not** scored: the vault is not empty (whitelisted WBTC 5.899, WETH 6.575,
  USDC 263,320, LINK 11,257, UNI 1,857 on 2026-09-20), so this is still live
  authority over real collateral.

### Open item this creates, not silently resolved

By the `crossExposureScore` convention ("each OTHER tracked target on the SAME
ecosystem sharing at least one resolved root signer costs 20 points"), the
overlap above is symmetric: GMX V2 RoleStore (index 0) would also move from 100
to 80. That is **not** done here. Index 0's 100 is an explicit "not computed
this target this pass" (`_CROSS_EXPOSURE_NOTE`), not a claim of no overlap, and
changing it means re-pushing an already-published score. Left as a decision, with
the exact change it would require stated: `score_gmx_v2_rolestore()` would need
its own live check of whether its ROLE_ADMIN committee reaches another tracked
target, and index 0's `crossExposureScore` would go 100 -> 80 with no move in
`compositeScore` (cross-exposure is not folded into the composite).

## Scouted, traced, NOT scored: Dolomite Margin `0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072`

Address source: DefiLlama-Adapters `projects/dolomite/index.js`,
`arbitrum: { margin: '0x6bd780e7fdf01d77e4d475c821f1e7ae05409072' }`.

What was established live:

- `DolomiteMargin.owner()` = `0xC2B66E247daE5Ee749Ae1d827190115F3653dE06`, an
  AccessControl-based delayed multisig (its bytecode carries `hasRole`,
  `getRoleAdmin`, `confirmTransaction`, `transactionCount`; `transactionCount()`
  = 1015).
- `secondsTimeLocked()` = **300**. Five minutes.
- Replaying `RoleGranted`/`RoleRevoked` and re-confirming each candidate with a
  live `hasRole()`: `DEFAULT_ADMIN_ROLE` has exactly **one** live holder,
  `0xa75c21C5BE284122a87A37a76cc6C4DD3E55a1D4`, a Safe 1.4.1 that is **2-of-3**
  (confirmed on both RPCs). The other six roles are held by contracts only.

Why it is not scored this run, stated plainly rather than papered over: the
enumeration step rests on one RPC. No free public Arbitrum endpoint other than
`arb1.arbitrum.io` would serve a full-range `eth_getLogs` for this contract
(`publicnode` 403, `drpc` 400, `1rpc`/`nodies` cap at 50 blocks,
`meowrpc` does not implement the method), so "exactly one DEFAULT_ADMIN_ROLE
holder" has a live second-RPC confirmation for the holder found, but not for the
claim that no other holder exists. That is the project's 2-checkpoint rule, and
it is not met yet. A 2-of-3 Safe with a 300-second delay over a lending
protocol's core is worth finishing with a log-capable endpoint.

## Probed and dropped

- **Balancer V2 Vault** `0xBA12222222228d8Ba445958a75a0704d566BF2C8`:
  `getAuthorizer()` = `0x6B1Da720Be2D11d95177ccFc40A917c2688f396c`, 770 bytes,
  which answers none of the usual authority getters. Needs its own
  TimelockAuthorizer sub-model; not started.
- **Gains Network gTrade** `0xFF162c694eAA571f685030649814282eA457f169`: EIP-1967
  admin `0xe18be011...`, whose `owner()` is a controller with
  `getMinDelay()` = **1,209,600s (14 days)** -- on the face of it the strongest
  delay seen on Arbitrum so far. Left for a next run rather than scored from one
  hop.
