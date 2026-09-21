# Finding (2026-09-20): Yuzu Money's placeholder score rested on a false negative; the real authority chain is a 3-of-5 Safe with an instant pool seat

## Why this exists

`score_yuzu_money_plasma` scored Yuzu Money's yzUSD (about $61.5M TVL on Plasma: yzUSD 56.2M plus
the yzPP first-loss pool 5.3M) with a PLACEHOLDER: adminKey 20 ("unresolved contract"), multisig 100
("not applicable"), timelock 55, composite 55. The scorer's own docstring said the timelock was "NOT
self-administered" and that its controller "was not traced this pass". The unscored-role sweep
(`data/finding_2026-09-20-unscored-role-sweep.md`) and the 2026-09-19 verifier notes named the
missing pieces without resolving them. This pass traced the whole chain live and had a second agent
try to refute it.

## 1. The premise of the placeholder was a false negative

The scorer asked `hasRole(TIMELOCK_ADMIN_ROLE, timelock)` with the OpenZeppelin-4 role hash
(`0x5f58e3a2...6ca5`) and got False. Both Yuzu timelocks are OpenZeppelin 5, which administers through
`DEFAULT_ADMIN_ROLE` (`0x00`). Read by hand on two RPCs (`rpc.plasma.to`, `plasma.gateway.tenderly.co`,
Plasma block 32,971,177): `hasRole(0x00, T)` is **True** for both timelocks and each is its own ONLY
admin; the OZ4 hash is not even in their bytecode. Nothing was unresolved.

## 2. The chain, re-derived by hand (both RPCs, identical)

| Piece | Address | What it is |
|---|---|---|
| yzUSD / syzUSD / yzPP | `0x6695c0f8706c5ace3bdf8995073179cca47926dc` / `0xc8a8df9b210243c55d31c73090f06787ad0a1bf6` / `0xebfc8c2fe73c431ef2a371aea9132110aab50dca` | OZ5 TransparentUpgradeableProxy contracts; `owner()` = T2 |
| ProxyAdmins (one per token) | e.g. yzUSD `0x6ccfD86e...D2Aa` | `owner()` = T2: only T2 can upgrade the logic |
| T2 | `0x2130457539612AE9838E0314cDa1A8abBdb7CFBc` | OZ5 TimelockController, delay 172,800s (2 days); only proposer Safe S2 |
| T1 | `0x5f3D29Ef17700F8658C566dac7fbd76E0d86B78C` | OZ5 TimelockController, delay **43,200s (12 hours)**; holds `ADMIN_ROLE` on every token; only proposer Safe S1 |
| S1 | `0xe61ad2De346db42879B6ee3c7cF0C6a2cDC0530d` | Gnosis Safe **3-of-5** |
| S2 | `0xa2a9700407934e913C840556B3D29F19cf6f203d` | Gnosis Safe **4-of-5**, the SAME five bare-EOA owners as S1 (verified as sets) |

`S1` also holds `POOL_MANAGER_ROLE` and `DISTRIBUTOR_ROLE` on yzPP, and `POOL_MANAGER_ROLE` on syzUSDx,
DIRECTLY, with no delay. Neither timelock has a bypass: byte-identical 5,448-byte OZ5 code, all 28
standard selectors and none extra, no whitelist, `updateDelay` self-only, the open executor
(`address(0)`) was revoked on both (2026-08-31 on T2, 2026-09-10 on T1). Their only cancellers are the
proposer Safe and one of its own signer EOAs, so the delay is a public visibility window, not an
independent veto.

## 3. What each path can do (from the verified source and `eth_call` simulation, no transaction)

| Path | Gate | Power |
|---|---|---|
| Upgrade (all four tokens) | T2, 2 days, 4 of 5 keys | replace the logic wholesale |
| `ADMIN_ROLE` (all tokens) | T1, 12 hours, 3 of 5 keys | `setTreasury` (every deposit is forwarded straight to that bare-EOA treasury), fee, cap, throttle and restriction levers; by granting roles to one key, a NAV markdown plus an effectively free yzUSD mint up to an unbounded cap (source-derived, not simulated end to end) |
| **Instant Safe S1 seat** | **none**, 3 of 5 keys | uncapped `updatePool` on yzPP (and syzUSDx): the first-loss pool's value can be written up or down in one Safe batch (it must first end the live weekly distribution, which S1 can also do); used every Friday by four of the five signers |
| Bare-EOA `ORDER_FILLER`, `DISTRIBUTOR` on syzUSD | none | bounded (yield stream about 50k yzUSD) or liveness |
| `PAUSE_MANAGER` (S1, S2, EOAs) | none | availability only |

Weakest fund-affecting path: the S1 instant pool seat; the 12h path is weaker than the 2-day upgrade
path; all three are reached by the same five keys. The reserve itself sits with bare-EOA treasury
custody outside any contract authority (a counterparty risk, disclosed and not scored).

## 4. The score

By the repo convention (an instant Safe seat decides, as for Radiant and Monad's Aave): adminKey 65
(threshold >= 3), multisig `min(100, 3*15 + 2*5)` = 55, timelock 0, oracle 100, cross 100:
**composite 43, down from 55** (the old multisig 100 was "not applicable" and adminKey 20 rested on the
false negative). Without the S1 seat, the 12h path would decide: 65/55/55 = 59, the alternative if a
maintainer scopes the score to the yzUSD contract alone (where S1's pool seat is inert). A strict floor
that counted every bare-EOA power would be 4; not recommended, since the custody EOAs are a
counterparty and the EOA distributor powers are bounded. Any unread role (POOL_MANAGER, ADMIN_ROLE,
PROPOSER) or unresolved link degrades to 20/0/0 rather than being taken as "no such seat".

Pushed on-chain the same day by Spap (Plasma testnet, tx `0x490f5bb8ec6c6a436bfde4aee358928e24b8ac5597e74b72cd2f0c5f01adbb1a`, block 34,083,939, status 1): the oracle reads 65/55/0/100/100/43 for yzUSD and all 9 Plasma targets read back identical to the scorer.

## 5. What the adversarial pass changed

A second agent re-derived every load-bearing fact from scratch (458 live grants, 5,704 `hasRole`
checks, zero disagreements) and corrected the first map: the T1 path is worse than "cut redemption
value, never inflate" (a NAV markdown plus an unbounded-cap mint, same score); `updatePool` first
needs the live distribution ended; the custody EOAs held about 0 of the collateral, not the figures
first quoted; the timelock alternative is 55/59 not 60/61; the "no overlap" claim was redone live, not
by text search. It also added facts the first map lacked: the same five keys own Safes on Ethereum and
Monad (Yuzu is not tracked there, no crossExposure change), two unused 4-of-6 Safes co-owned by two of
the signers (no role today), a bare-EOA `DISTRIBUTOR` on syzUSDx, and a 4.5-month-old signer alignment
between S1 and S2.

## 6. Registry and cross-exposure

S1 and S2 are registered as ONE group, `yuzu`, in `scripts/lib/cross_ecosystem_overlap.py` (two groups
would make the target overlap itself). The live sweep now covers 72 groups on 7 ecosystems and finds no
signer or Safe address shared with any other tracked group, so `crossExposureScore` stays 100 (a
dated result, not proof of none).

## What is NOT established

- Source versus bytecode rests on the explorer's verification plus selector-set equality, with no local
  recompile.
- Whether any Plasma protocol reads yzPP, syzUSDx or syzUSD NAV (none is tracked in this repo): it
  would decide whether the pool seat also lowers `oracleAuthorityScore`.
- The real-world independence and key hygiene of the five signers, and who controls the treasury EOAs
  and where the roughly $56M reserve sits: the largest unscored risk.
- Whether a 12-hour window is enough for users to exit (the on-chain buffer is about zero).
- Whether T1 or T2 hold authority over other Yuzu contracts not among these tokens.
- The layout is recent (2026-04-11 to 2026-09-07): re-score on any event from T1, T2, the ProxyAdmins or
  a change of S1 or S2 owners.
