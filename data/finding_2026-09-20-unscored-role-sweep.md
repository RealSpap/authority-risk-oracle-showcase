# Finding (2026-09-20): an unscored-role sweep of every EVM ecosystem, and a second Aave committee on five chains

## Why this sweep exists

On 2026-09-19 an independent verification pass found that the Euler V2 eVaultFactory
Governor's `PAUSE_GUARDIAN_ROLE` was held by two bare EOAs and that no scorer or note in
the repo had ever seen it, because the scorers checked the role NAMES they knew to look
for and never enumerated what had actually been granted. That is a general bug class, so
this pass hunts for other instances everywhere: for every AccessControl-shaped authority
contract each scorer touches, replay the `RoleGranted`/`RoleRevoked` history, resolve the
role names by `keccak256`, read the current holders, classify each (bare EOA / Safe k-of-n
/ timelock / other), and keep every role held by a bare EOA or a Safe that the scorer and
its notes never mention. Then a SECOND, independent agent per ecosystem tried to refute
each candidate with fresh on-chain reads and `eth_call` simulations (a holder versus a
random control address; no transaction was ever sent).

Result: 104 candidates went through refutation; **42 CONFIRMED,
48 PARTLY_CONFIRMED, 14 REFUTED** (the refuters
overturned or downgraded a real share of the first agents' claims, e.g. a MINTER_ROLE on
Ethena that turned out to be on a retired contract). The full backlog is at the bottom.
Most entries are availability/freeze or config-only seats; the four below are the ones
that matter for scores or for cross-chain overlap. Items marked **[by hand]** were
re-read by me directly on-chain after the agents reported them; the rest are
agent-reported and verifier-checked, not individually re-derived.

## 1. [by hand] Aave's PROTOCOL_GUARDIAN is a second cross-chain committee, on FIVE chains

The repo (`scripts/lib/cross_ecosystem_overlap.py`,
`data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md`) described Ethereum L1's
`PROTOCOL_GUARDIAN` (4-of-7) as "a genuinely separate, older, mainnet-only governance body".
It is not mainnet-only. Read live, one call per chain: the Safe that holds
`isEmergencyAdmin` on each chain's Aave ACLManager is a **4-of-7 Safe with the identical 7
owners**, at a different Safe address per chain:

| Chain | Safe | ACLManager `isEmergencyAdmin` |
|---|---|---|
| Ethereum L1 | `0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30` | true |
| Arbitrum | `0xCb45E82419baeBCC9bA8b1e5c7858e48A3B26Ea6` | true |
| Base | `0x56C1a4b54921DEA9A344967a8693C7E661D72968` | true |
| Plasma | `0xEf323B194caD8e02D9E5D8F07B34f625f1c088f1` | true |
| Monad | `0xc887455536CBD4e615B745e70CaCde15B3117e74` | true |

Owners (same set everywhere): `0x3fa960f8...`, `0xe6838d83...`, `0xc2674c1a...`,
`0xd4af2e86...` (bare EOAs) and `0xa2dcdd6e...`, `0xb291232f...`, `0x4ab2bed1...` (nested 1-of-3
Safes). Zero overlap with the 9-signer GOVERNANCE_GUARDIAN committee. What the seat can
do: `EMERGENCY_ADMIN` pauses/freezes the pool instantly, an availability power (no fund
movement, no risk-parameter change). None of the five chains' Aave scorers mentions it;
`crossExposureScore` reflects only the 9-signer committee.

**Monad is worse.** That Safe ALSO holds `POOL_ADMIN` there (`isPoolAdmin` true, next to the
DAO Executor). By `eth_call` simulation with a state override (verifier, no transaction) it
can swap any reserve's aToken / variableDebtToken implementation immediately, a path the
1-day Executor delay does not gate. The scorer models Monad's admin path as Executor +
delay only (`adminKeyScore` 65, `timelockScore` 50). The Executor holds `DEFAULT_ADMIN` and
could revoke the seat, and the Safe cannot grant roles. On Ethereum L1 the same Safe has
`isPoolAdmin` false; Base and Plasma were read for `EMERGENCY_ADMIN` only.

Changed in this pass (no score moves): `aave_protocol_guardian` groups added to the
Arbitrum, Base, Plasma and Monad registries, so the overlap sweep now reports each of the 7
owners on 5 chains and the containment rows; the wrong "mainnet-only" comment is corrected;
`score_aave_v3_monad` now notes the seat and the POOL_ADMIN path (4 tests).

## 2. [by hand] The Ethena scorer scores a retired minter

`score_ethena_minting` scores `0x2CC440b7...` as "USDe minting authority", concluding "a
direct Safe controls minting ... with no delay". Read live: `USDe.minter()` is
`0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3`, NOT `0x2CC440b7...`. The scored contract's
`owner()` is still the 5-of-10 Safe, but the LIVE minter's `owner()` is the
`EthenaTimelockController` `0xE8Dc0Fab...` (`getMinDelay()` = 86400s), a contract the same
file already scores for USDtb PSM and the OFTAdapters. The verifier's log replay: `USDe`
has had exactly two `MinterUpdated` events (2023-11-15 sets `0x2CC440b7...`; 2024-07-08 sets
`0xe3490297...`, sent through the 5-of-10 Safe), the old contract has had no Mint/Redeem
since, and the last 11 USDe mints (2026-09-19) were all to `0xe3490297...`. The old
contract's roles the sweep listed (20 MINTER EOAs, 4 GATEKEEPER EOAs) therefore have no
live power. The LIVE minter has its own, different sets (20 bare-EOA MINTER holders with
zero overlap with the old 20, 20 REDEEMER, 4 GATEKEEPER EOAs, two shared with the old set,
`COLLATERAL_MANAGER` = a Safe); those holder COUNTS were read but nothing on it was
simulated or scored. Decision for the maintainer, NOT made here: replace or add the live
minter as a target (changes the tracked set and needs an on-chain push).

**UPDATE 2026-09-20 (resolved and pushed on-chain): the Ethena item is decided and done.** The
decision this section left for the maintainer was made the same day: the live minter
`0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3` is scored instead of the retired `0x2CC440b7...`.
It was traced and adversarially re-verified on two RPCs (timelock 24h, 5-of-10 Safe with an
`EthenaSafeGuard`, the six redirect-class selectors and `USDe.setMinter` delayed, three instant
lanes, seven `STABLE` collateral assets), scored **65/100/55/100/20, composite 73**, and pushed as a
new Ethereum L1 target, index 14 (tx `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`,
block 11,740,952; read back exactly). The old target, index 3 (55/100/0/100/20/52), is retired:
it is no longer refreshed, and because the oracle has no removal function it stays as a
historical reading until it turns stale nine days after its last update (the 2026-09-19 push).
Ethereum L1 now tracks 15 targets, 14 of them actively refreshed. This section's own text above is
left as written; it only counted the live minter's role holders, and the later trace added what it
did not have (the full authority path, seven `STABLE` collateral assets, about 93M USD held).
Full record, score reasoning and open points: `data/finding_2026-09-20-ethena-live-minter.md`.

## 3. Radiant (Arbitrum): a 4-of-11 Safe upgrades tokens outside the timelock the scorer credits

agent-reported, verifier-checked, not re-derived by hand. `score_radiant_lendingpool`
scores `provider.owner()`, an OZ TimelockController with a 72h delay. But
`getPoolAdmin()` on the same provider is `0x111CEEee...F2177`, a 4-of-11 Safe, and the
LendingPoolConfigurator's `onlyPoolAdmin` functions (`updateAToken`,
`updateStableDebtToken`, `updateVariableDebtToken`, freeze, caps, rate strategy) call
`upgradeToAndCall` / act immediately: simulated from that Safe they pass, from the timelock
and a random address they revert `CALLER_NOT_POOL_ADMIN`. The pool-admin Safe also holds
PROPOSER and CANCELLER on that timelock, and a separate 1-of-5 `emergencyAdmin` Safe (all
five owners are also owners of the 4-of-11) can pause the pool alone. Exposure is small
(about $72k of underlying), but the 72h timelock does not bind these functions. The repo
already discloses the 2024-10-16 signer-compromise incident.

**UPDATE 2026-09-20 (decided, implemented and pushed on-chain): Radiant, Monad Aave and the
convention question.** Everything this section and section 1 left for the maintainer on Radiant and
on Monad's Aave is now decided and coded, and the `crossExposureScore` convention question that
`data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`
section 1 left open is decided too (cross-ecosystem overlaps are folded, on every EVM ecosystem).
All of it was pushed on-chain the same day (six transactions, all status 1, read back with
0 differences; table in `data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`
section 9). This section's own text above is left as written on the day of the sweep.

- **Radiant.** Re-read live on 2026-09-20: `getPoolAdmin()` is the 4-of-11 Safe `0x111CEEee...F2177`,
  different from `provider.owner()` (the 72h timelock `0x27fC8f3B...Aff92`); the pool-admin Safe holds
  PROPOSER and CANCELLER on the timelock and 6 of its 11 owners hold EXECUTOR, but the timelock does not
  bind the pool-admin path. `score_radiant_lendingpool` now scores it as a Safe with no timelock:
  55/100/55/100/100/69 became **65/95/0/100/100/55** (admin 65, multisig `min(100, 4*15+7*5)` = 95,
  timelock 0). The 1-of-5 emergency-admin Safe (owners all among the 11) can only pause, disclosed and
  not scored. `crossExposureScore` stays 100 (compared with 70 root-signer groups on 7 ecosystems, none
  matched, "found none" not proof of none).
- **Monad Aave** (section 1's "Monad is worse"). The PROTOCOL_GUARDIAN Safe `0xc887455536...e74`
  (4-of-7, live) holds `POOL_ADMIN` (`isPoolAdmin` true), so `score_aave_v3_monad` now scores the
  Safe-no-timelock path: 65/100/50/100/80/71 became **65/75/0/100/80/49** (multisig `min(100, 4*15+3*5)`
  = 75). If `isPoolAdmin` reads false it keeps 65/100/50; unread it degrades to 20/20/0.
- **Convention.** The Aave 9-signer committee and the Morpho Association committee that were 80 on some
  chains and 100 on others now read 80 everywhere; nine other targets moved by that alone. The full
  before/after table, the exact rule, how each was verified and the residual gaps are in
  `data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`.
- **Pushed.** The values above are on-chain since 2026-09-20 (Radiant on Arbitrum: tx
  `0x308ad2c8fa527a0e5c30139b6b154ff48462cd046df9840a17f25775c21fbd23`, block 310,697,409; Monad Aave:
  tx `0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019`, block 64,022,942).
  **Still not done:** Radiant's two Safes are not yet in the `cross_ecosystem_overlap.py` sweep
  registry. Section 2 (Ethena) has its own update above; section 4 (GMX) is not covered by any
  update.

## 4. GMX (Arbitrum): a bare EOA holds PROPOSER, EXECUTOR and CANCELLER on the DAO timelock

agent-reported, verifier-checked, not re-derived by hand. The GMX `GovTimelockController`
(`0x4bd1cdAa...`, 24h delay): one bare EOA holds all three roles, so it can queue and
execute an operation itself after 24h, without a Governor vote, and cancel Governor-queued
operations. Not named in the repo.

## What was NOT changed

No score, no scorer logic and no on-chain state changed in this pass beyond the notes and
registry groups named above. Sections 2 to 4 each change a score or the tracked target set
and so need a maintainer decision and a real push. The 90-row backlog below is a review
list, not a list of confirmed vulnerabilities: most rows are "role X held by EOA/Safe Y is
not mentioned", and a large share are availability-only or already dominated by a root
authority the scorer already scores.

**UPDATE 2026-09-20:** the Radiant item (section 3), the Monad Aave path (section 1) and the Ethena
item (section 2) are no longer pending: they are decided, coded and pushed on-chain the same day, see
the updates at the end of sections 2 and 3. The GMX item (section 4) and the rest of the backlog are
unchanged. The "not changed" statement above described the sweep pass itself and was true of it.

## Backlog (every candidate that survived refutation)

| Chain | Contract | Role | Verdict | Severity (verifier's words, clipped) |
|---|---|---|---|---|
| arbitrum | 0x4bd1cdAab4254fC43ef6424653cA2375b4C94C0E GMX DAO GovTimeloc… | PROPOSER_ROLE 0xb09aa5aeb3702cfd5… | CONFIRMED | fund-moving/upgrade path (24 h delay, no Governor vote). Stronger than the candidate states: t… |
| arbitrum | 0x4bd1cdAab4254fC43ef6424653cA2375b4C94C0E GMX DAO GovTimeloc… | EXECUTOR_ROLE 0xd8aa0f3194971a2a1… | CONFIRMED | fund-moving/upgrade path only in combination with PROPOSER (the EOA both queues and executes).… |
| arbitrum | 0x4bd1cdAab4254fC43ef6424653cA2375b4C94C0E GMX DAO GovTimeloc… | CANCELLER_ROLE 0xfd643c72710c63c0… | CONFIRMED | availability/governance veto only. The EOA can cancel any pending op including Governor-queued… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | CONFIG_KEEPER 0x901fb3de937a1dcb6… | CONFIRMED | availability/freeze plus instant risk-parameter authority (zero delay); not a direct token tra… |
| arbitrum | 0xa72636CbcAa8F5FF95B2cc47F3CDEe83F3294a0B Aave V3 Arbitrum A… | EMERGENCY_ADMIN 0x5c91514091af31f… | CONFIRMED | availability/freeze only (Aave v3 emergency admin cannot move funds or change risk parameters)… |
| arbitrum | 0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a Radiant LendingPoo… | poolAdmin, provider.getPoolAdmin(… | CONFIRMED | fund-moving/upgrade path with no delay: a 4-of-11 Safe can upgrade aToken and debt-token imple… |
| arbitrum | 0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a Radiant LendingPoo… | emergencyAdmin, provider.getEmerg… | CONFIRMED | availability/freeze by a single key (pool-wide pause and unpause), no delay. |
| base | Aave V3 Base ACLManager 0x43955b0899Ab7232E3a454cf84AedD22Ad4… | EMERGENCY_ADMIN (0x5c91514091af31… | CONFIRMED | availability/freeze only (medium). No upgrade, listing, cap, rate, fee or fund-moving power. I… |
| ethereum-l1 | 0xC139190F447e929f090Edeb554D95AbB8b18aC1C (USDtb proxy, Tran… | PAUSER_ROLE | CONFIRMED | availability/freeze only (instant, whole-token: pause halts all transfers, mint and burn of a… |
| ethereum-l1 | 0xC139190F447e929f090Edeb554D95AbB8b18aC1C (USDtb proxy) | BLOCKLISTER_ROLE | CONFIRMED | availability/freeze (censorship of any holder or protocol contract, not theft). Recoverable on… |
| ethereum-l1 | 0x9D39A5DE30e57443BfF2A8307A4256c8797A3497 (Ethena StakedUSDe… | BLACKLIST_MANAGER_ROLE | CONFIRMED | availability/freeze with a large blast radius (any single holder can FULL-restrict any address… |
| monad | Aave V3 Monad ACLManager 0xa9fEe192...3d95B | POOL_ADMIN (0x12ad05bd...9b7b; ke… | CONFIRMED | Fund-moving / upgrade path (aToken and variableDebtToken proxy implementation upgrade for ever… |
| monad | Aave V3 Monad ACLManager 0xa9fEe192...3d95B | EMERGENCY_ADMIN (0x5c915140...82f… | CONFIRMED | Availability/freeze only (pool and reserve pause, freeze family), instant, no timelock. Redund… |
| monad | Euler accessControlEmergencyGovernor 0x6d0C0184...2742 | HOOK_EMERGENCY_ROLE (0x6d27321c..… | CONFIRMED | Availability/freeze: on 32 of 134 vaults every deposit, withdrawal, borrow, repay and liquidat… |
| monad | Euler accessControlEmergencyGovernor 0x6d0C0184...2742 | CAPS_EMERGENCY_ROLE (0x63c206f8..… | CONFIRMED | Low availability: only blocks NEW supply or borrow on the 32 governed vaults; existing positio… |
| plasma | 0xE468f1dA5B22b0d9A832De14a8f6158cD721b102 (Euler ACEG Wildca… | PROPOSER_ROLE | CONFIRMED | medium mechanism (any selector on ACEG-governed vaults after 2 days, cancellable by DAO/Labs);… |
| plasma | 0x6695c0f8706c5ace3bdf8995073179cca47926dc (yzUSD), 0xc8a8df9… | PAUSE_MANAGER_ROLE | CONFIRMED | availability/freeze only, but instant and single-key: TVL about $61.5M per the scorer's DefiLl… |
| plasma | 0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c (Euler AccessContr… | HOOK_EMERGENCY_ROLE | CONFIRMED | availability/freeze only. Restore requires a WILD_CARD or selector-role holder via a 2-day tim… |
| plasma | 0xa860355F0ccFdC823F7332ac108317b2a1509C06 (Aave V3 Plasma AC… | EMERGENCY_ADMIN | CONFIRMED | availability/freeze only: instant pause of the whole Aave V3 Plasma pool (about $496M per the… |
| plasma | 0x5f3D29Ef17700F8658C566dac7fbd76E0d86B78C (Yuzu 12h Timelock… | CANCELLER_ROLE | CONFIRMED | low (governance liveness: a single key can veto any queued action on the timelock that owns AD… |
| plasma | 0x2130457539612AE9838E0314cDa1A8abBdb7CFBc (Yuzu 2-day Timelo… | CANCELLER_ROLE | CONFIRMED | low (a single signer-EOA can cancel any queued upgrade or role change; governance liveness, no… |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (stock-token beaco… | BEACON_UPGRADER_ROLE 0x5ab8bd2847… | CONFIRMED | fund-moving/upgrade path (swaps the shared implementation of ~230 tokens). Ceiling unchanged,… |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (stock-token beaco… | MINTER_ROLE 0x9f2df0fed2c77648de5… | CONFIRMED | fund-moving (uncapped mint on every stock token; the real-world damage depends on where unback… |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (stock-token beaco… | BURNER_ROLE 0x3c11d16cbaffd01df69… | CONFIRMED | fund-moving (burns any non-blocked holder's balance with no allowance) |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (stock-token beaco… | ADMIN_BURNER_ROLE 0x25e7ebc863fa4… | CONFIRMED | fund-moving (burn from any account, ignoring pause and block-list) |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (stock-token beaco… | PAUSER_ROLE 0x65d7a28e3265b37a647… | CONFIRMED | availability/freeze (all stock tokens at once) |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (stock-token beaco… | BLOCKER_ROLE 0x8f2e0057cd5e353970… | CONFIRMED | availability/censorship (blocks any address across ~230 tokens) |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (role registry) ac… | TOKEN_PAUSER_ROLE 0xe95e22ec6dbf4… | CONFIRMED | availability/freeze (per token only; the role is registry-wide so it can pause every token one… |
| robinhood | 0xcf8d58a6eef2a1cae2ce69bc463b1178fb76ba1e (Spark ALM control… | FREEZER 0x0ac42a08299cbc4428ec38a… | CONFIRMED | availability/freeze only (kill-switch: can remove a relayer, cannot add or move funds) |
| robinhood | 0xAEa9f5dE56e6C20383a1fcc2c3629Dca0A92cE41 (ALMProxyFreezable… | ALLOCATOR_ROLE 0x68bf109b95a5c15f… | CONFIRMED | config-only (the proxy's only known privilege is bounded setVsr; the proxy holds no assets) |
| robinhood | 0xAEa9f5dE56e6C20383a1fcc2c3629Dca0A92cE41 (ALMProxyFreezable) | FREEZER_ROLE 0x92de27771f92d69426… | CONFIRMED | availability/freeze only (removeAllocator) |
| robinhood | 0x83341F891f898cb5E0cacC8a70501BBa83d9CecF (Ramses AccessHub… | SWAP_FEE_SETTER 0x0cee480c05aeaba… | CONFIRMED | config/fees, but with a wide range: swap fee accepted up to at least 100% on a live V3 pool wi… |
| robinhood | 0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB (Arcus pToken fact… | PTOKEN_ADMIN_ROLE 0xb91dda2cc93a6… | CONFIRMED | fund-moving-adjacent (unquantified): one Safe owner alone can reassign the pToken manager, and… |
| robinhood | 0xa362d98b33a7bb5b5e2180a05f995a70fb404f30 (Fables AccessMana… | roleId 4 (label PAUSER; admin rol… | CONFIRMED | availability/freeze (pause hooks holding ~$21.8M TVL per the repo). Ceiling unchanged: role 6… |
| robinhood | 0xa362d98b33a7bb5b5e2180a05f995a70fb404f30 (Fables AccessMana… | roleId 1 (label FEE_POKER; admin… | CONFIRMED | config/fees (dynamic fee 'pokes'; fee bounds not determined). Two of the three holders are hot… |
| robinhood | 0xa362d98b33a7bb5b5e2180a05f995a70fb404f30 (Fables AccessMana… | roleId 2 (label CALENDAR_OPS) | CONFIRMED | config-only, low (market-hours calendar parameters, and a 1-hour execution delay). Ceiling unc… |
| robinhood | 0x4208d6e27538189bb48e603d6123a94b8abe0a0b (LayerZero V2 Exec… | DEFAULT_ADMIN_ROLE 0x00..00 | CONFIRMED | availability/freeze (setPaused). The Executor currently holds 0 ETH and 0 USDG. Also: a single… |
| robinhood | 0x4208d6e27538189bb48e603d6123a94b8abe0a0b (LayerZero V2 Exec… | ADMIN_ROLE 0xa49807205ce4d355092e… | CONFIRMED | availability/pricing and fee-funds (14 selectors); Executor balance is currently 0, so fee-wit… |
| tempo | 0x76FaFF60799021B301B45dC1BbEDE53F261F9961 (LayerZero DVN 'La… | ADMIN_ROLE (keccak256("ADMIN_ROLE… | CONFIRMED | LOW: availability/freeze only. No fund-moving or upgrade path and no unilateral forging of ver… |
| tempo | 0x0D875bD6c833cEDef7Fca4FE154d023cDB8eb1cb (LayerZero DVN 'Ne… | ADMIN_ROLE (0xa49807205ce4d355092… | CONFIRMED | LOW: availability/freeze only, same power set as the LZ Labs DVN; not fund-moving, cannot forg… |
| tempo | 0xB30B5B27Cb23356DE1D3100E0e120D481Da97b1f (LayerZero DVN 'Ca… | ADMIN_ROLE (0xa49807205ce4d355092… | CONFIRMED | LOW: availability/freeze only; same power set as the other DVNs. |
| tempo | 0x7701172A790129fdFdB802b091BEDC4A6bC877de (LayerZero DVN 'US… | ADMIN_ROLE (0xa49807205ce4d355092… | CONFIRMED | LOW: availability/freeze only; same power set. Highest fee-siphon exposure is the smallest of… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore | LIMITED_CONFIG_KEEPER 0xb49beded4… | PARTLY_CONFIRMED | config-only/availability, strict subset of CONFIG_KEEPER: can set pool caps or open-interest c… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | ORDER_KEEPER 0x40a07f8f0fc57fcf18… | PARTLY_CONFIRMED | operational/liveness. executeOrder is wrapped in withOraclePrices, which calls oracle.setPrice… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | MARKET_KEEPER 0xd66692c70b60cf133… | PARTLY_CONFIRMED | config-only. Creating a market does not enable trading (needs caps and oracle provider config)… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | CLAIM_ADMIN 0x3816efacf145d41a12d… | PARTLY_CONFIRMED | config-only: cannot withdraw or redirect vault funds; can only deposit its own funds, set clai… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | CONTRIBUTOR_KEEPER 0xfa89e7b5ea0a… | PARTLY_CONFIRMED | bounded fund-flow. It picks recipients and amounts, capped by controller-set totals: MAX_TOTAL… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | FEE_KEEPER 0xe0ff4cc0c6ecffab6db3… | PARTLY_CONFIRMED | config/fees only. withdrawFees sends to DataStore[FEE_RECEIVER], which is not allow-listed for… |
| arbitrum | 0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72 GMX V2 RoleStore (… | RISK_ORACLE 0x60854122629f5aff9fb… | PARTLY_CONFIRMED | zero-delay risk-parameter authority bounded to 22 allow-listed keys (claim said 20; includes p… |
| arbitrum | 0x34d45e99f7D8c45ed05B5cA72D54bbD1fb3F98f0 Arbitrum L2 core T… | PROPOSER_ROLE 0xb09aa5ae... (repr… | PARTLY_CONFIRMED | informational: dominated by the already-scored Emergency Safe path (same 12 signers, and the d… |
| ethereum-l1 | 0x1676b80EDD36B18a3C3432c11Ed25D37FdE9c92A (fUSD, Falcon Fina… | UPGRADER_ROLE | PARTLY_CONFIRMED | low. It is an upgrade path, but on a dust token (totalSupply 58.23, 5 holders) that the repo d… |
| ethereum-l1 | 0xe5c6318456a7Cb6f74f93B4eee4616dB5fcef699 (Spark ALMProxyFre… | ALLOCATOR_ROLE | PARTLY_CONFIRMED | config only, bounded (rate-setting in an admin-set band and cap refresh). No fund-moving or up… |
| ethereum-l1 | 0xe5c6318456a7Cb6f74f93B4eee4616dB5fcef699 (Spark ALMProxyFre… | FREEZER_ROLE | PARTLY_CONFIRMED | negligible (a safety brake: it can only remove an allocator, which stops keeper rate-setting a… |
| monad | Aave V3 Monad ACLManager 0xa9fEe192...3d95B | RISK_ADMIN (0x8aa855a9...8167; ke… | PARTLY_CONFIRMED | Config-only and bounded (caps, rates, Pendle discount rates, GHO caps; per-update max change a… |
| monad | Euler accessControlEmergencyGovernor 0x6d0C0184...2742 | LTV_EMERGENCY_ROLE (0x0ee15ff7...… | PARTLY_CONFIRMED | Availability only. The claim that it can 'push positions toward liquidation' is refuted: liqui… |
| monad | Euler wildcard timelock 0xc605f5A2...F88f | PROPOSER_ROLE (0xb09aa5ae...9cc1;… | PARTLY_CONFIRMED | Timelocked (2 days, cancellable by DAO, Labs and 0xF8ef itself) but the scope is full vault go… |
| monad | Euler eVaultFactoryGovernor 0x515C9ff6...4f0e | UNPAUSE_ADMIN_ROLE (0x93ccdda7...… | PARTLY_CONFIRMED | Availability only, and adds no new holder (the Labs Safe is already tracked as a pause-guardia… |
| monad | Euler eVaultFactoryTimelockController 0x7Fe335AD...E439 | CANCELLER_ROLE (0xfd643c72...f783… | PARTLY_CONFIRMED | Not a risk: a blocking (veto) power held by an independent council, a positive for timelockSco… |
| monad | Euler capRiskSteward 0xb1533b53...3d1F | DEFAULT_ADMIN_ROLE (0x00..00) | PARTLY_CONFIRMED | Config-only, idle and bounded (cap and IRM changes within 2.0x per 1-day charge interval, on t… |
| monad | Curvance DAOTimelock 0x26777386...8C08 | PROPOSER_ROLE (0xb09aa5ae...9cc1)… | PARTLY_CONFIRMED | Unclear resolved to low marginal risk. The scorer scores the zero-delay Emergency Council path… |
| monad | Curvance DAOTimelock 0x26777386...8C08 | CANCELLER_ROLE (0xfd643c72...f783… | PARTLY_CONFIRMED | Availability/veto only and redundant: the Council already has zero-delay authority over the sa… |
| plasma | 0x5f3D29Ef17700F8658C566dac7fbd76E0d86B78C (Yuzu 12h Timelock… | PROPOSER_ROLE | PARTLY_CONFIRMED | high (fund-diversion through setTreasury, role grants and pause-related toggles, 3-of-5 thresh… |
| plasma | 0xabD3645ba0bb60C238bedE64378826E1206f5072 (EthenaTimelockCon… | WHITELISTED_EXECUTOR_ROLE | PARTLY_CONFIRMED | low today (dormant: the same Safe is already the direct owner() of all three OFTs); medium onl… |
| plasma | 0xc8a8df9b210243c55d31c73090f06787ad0a1bf6 (Yuzu syzUSD); the… | DISTRIBUTOR_ROLE | PARTLY_CONFIRMED | low-medium (bounded fund-moving: only the in-flight yield stream, about 58.1K yzUSD now and at… |
| plasma | 0xebfc8c2fe73c431ef2a371aea9132110aab50dca (Yuzu yzPP; the sa… | POOL_MANAGER_ROLE | PARTLY_CONFIRMED | medium (oracle-like NAV authority over the yzPP first-loss pool, poolSize 5,317,776,603,952 ra… |
| plasma | 0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c (Euler AccessContr… | LTV_EMERGENCY_ROLE | PARTLY_CONFIRMED | low (restrict-only: lowers borrowLTV with liquidationLTV unchanged. Existing positions are not… |
| plasma | 0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c (Euler AccessContr… | CAPS_EMERGENCY_ROLE | PARTLY_CONFIRMED | low (restrict-only: lowers supply and borrow caps. It stops new deposits and borrows but not w… |
| plasma | 0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e (Pendle PendleGove… | GUARDIAN | PARTLY_CONFIRMED | availability/freeze only, single-key, instant. 36 of 38 Plasma market SYs can be frozen by any… |
| plasma | 0xE468f1dA5B22b0d9A832De14a8f6158cD721b102 (Euler ACEG Wildca… | CANCELLER_ROLE | PARTLY_CONFIRMED | low (cancel-only. It is an extra canceller, which if anything strengthens the DAO/Labs veto. T… |
| plasma | 0x939cA204c892932aA91810EeE50253a0427dd33D (Euler eVaultFacto… | UNPAUSE_ADMIN_ROLE | PARTLY_CONFIRMED | informational. This is a restorative role: it can only restore the pre-pause implementation (s… |
| plasma | 0x66b3Bf9d8187227799809065bf7D1e2B8B784607 (Euler CapRiskStew… | DEFAULT_ADMIN_ROLE | PARTLY_CONFIRMED | low / config-only (bounded and dormant). The DAO Safe, which is already scored, could skip the… |
| plasma | 0xA9C251f8304b1B3Fc2B9e8FCAE78D94eFF82Ac66 (TelosC Surge Eule… | allocator (isAllocator mapping, N… | PARTLY_CONFIRMED | low incremental (liquidity/allocation only, no withdraw-to-arbitrary path). The owner==curator… |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (role registry) ac… | ORACLE_PAUSER_ROLE 0x155fc2c2b00b… | PARTLY_CONFIRMED | config-only / signal flag: no on-chain effect inside the stock token, only downstream consumer… |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (role registry) ac… | MULTIPLIER_UPDATER_ROLE 0x7158cf4… | PARTLY_CONFIRMED | config-only (display multiplier; raw balances and transfers unaffected) |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (role registry) ac… | METADATA_UPDATER_ROLE 0x7f5260842… | PARTLY_CONFIRMED | config-only (cosmetic name/symbol; impersonation or phishing nuisance) |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (role registry); g… | TOKEN_DEPLOYER_ROLE 0x5f077d4e72b… | PARTLY_CONFIRMED | config-only to low: can only create new tokens attached to the shared registry. No effect on t… |
| robinhood | 0xe10b6f6b275de231345c20d14ab812db62151b00 (role registry); g… | FACTORY_UPGRADER_ROLE 0xb4e5de734… | PARTLY_CONFIRMED | config-only to low: affects future deployments only. The factory holds no role on the registry… |
| robinhood | 0xde770c84FE66E063336b31737cFE9790f18c4087 (SparkVault spUSDG… | TAKER_ROLE 0x508ee82d0bdf04e00030… | PARTLY_CONFIRMED | availability/liquidity (vault withdrawals fail while USDG sits in ALMProxy). The arbitrary-des… |
| robinhood | 0xde770c84FE66E063336b31737cFE9790f18c4087 (SparkVault spUSDG… | SETTER_ROLE 0x61c92169ef077349011… | PARTLY_CONFIRMED | config-only (setVsr bounded in [0%, 6.00%] APR; current 3.50%) |
| robinhood | 0xcf8d58a6eef2a1cae2ce69bc463b1178fb76ba1e (Spark ALM control… | RELAYER 0xab4f864e5201b0fde9b5ee3… | PARTLY_CONFIRMED | availability/liquidity plus whitelisted-only routing. The fund-moving-theft claim is not suppo… |
| robinhood | 0x83341F891f898cb5E0cacC8a70501BBa83d9CecF (Ramses AccessHub) | PROTOCOL_OPERATOR 0xb3072e349cf62… | PARTLY_CONFIRMED | config-only in the source, but broader than fees (setNewGovernorInVoter, treasury redirects in… |
| robinhood | 0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB (Arcus pToken fact… | NAV_SIGNER_ROLE 0x2fc965e6d3b4285… | PARTLY_CONFIRMED | unclear: gated function not identified, so no severity can be assigned. Do not assume a signed… |
| robinhood | 0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB (Arcus pToken fact… | unresolved role, getter selector… | PARTLY_CONFIRMED | unclear: four gated selectors are unresolved (4byte and openchain: no entries). Used operation… |
| robinhood | 0xa49f317086368da903ea40a286ad675664c9e123 (Arcus Perps Block… | OPS_EXECUTOR_ROLE 0xeb8c85c773f27… | PARTLY_CONFIRMED | relayer, not extra authority (as far as shown): sits on the arbitrary-call governance path, bu… |
| robinhood | 0x0000000000cc53b5fd649b80f08b05405779cc71 (T3tris platform f… | DEFAULT_ADMIN_ROLE 0x00..00 (plus… | PARTLY_CONFIRMED | unclear: the shared-key fact is real and contradicts the scorer text, but power over existing… |
| robinhood | 0x0000000000cc53b5fd649b80f08b05405779cc71 (T3tris platform f… | UPGRADE_ROLE 0x88aa719609f728b0c5… | PARTLY_CONFIRMED | unclear: upgradeToAndCall gate confirmed. Blast radius appears limited to future vault creatio… |
| robinhood | 0xd5c6c79692715145098a65d1eb1f2a10c524f8e8 (T3tris WBTC vault… | GOVERNANCE_ADMIN_ROLE 0xe7e0b301d… | PARTLY_CONFIRMED | unclear to none demonstrated: real and self-administered, but it gates no selector and cannot… |
| robinhood | 0x5fc5360d0400a0fd4f2af552add042d716f1d168 (USDG token, Paxos… | ASSET_PROTECTION_ROLE 0xe3e4f9d75… | PARTLY_CONFIRMED | fund-moving in mechanism (freeze, unfreeze, wipe frozen balances) but this is the standard reg… |
| robinhood | 0x5fc5360d0400a0fd4f2af552add042d716f1d168 (USDG token) | PAYOUT_GROUP_ADMIN_ROLE 0x2a0ee64… | PARTLY_CONFIRMED | limited fund-moving: per Roles.sol natspec, PAYOUT_GROUP_ADMIN and CLAIM_ADMIN can redirect re… |
| robinhood | 0xcfa0388f5ddf905fdc08c45c716c15dc10a14c6f (USDG DEFAULT_ADMI… | PROPOSER_ROLE 0xb09aa5aeb3702cfd5… | PARTLY_CONFIRMED | upgrade path of the token, but with a real public 24h delay; no independent veto exists. Not a… |

## UPDATE 2026-09-20 (later): GMX decided, Radiant in the registry, Aave POOL_ADMIN checked on the other four chains

- **GMX (section 4), re-derived by hand.** The sweep did not name the holder; it is the bare EOA
  `0xE7BfFf2aB721264887230037940490351700a068` (2,870 transactions, about 2 ETH), next to the Governor contract
  `0x03e8f708e9C85EDCEaa6AD7Cd06824CeB82A7E68`, on the DAO timelock `0x4bd1cdAa...` (24h delay). Confirmed with `hasRole`
  on two RPCs; the RoleStore's 5-of-8 Safe holds none of PROPOSER, EXECUTOR or CANCELLER there; `eth_call`
  simulation: `schedule(RoleStore, grantRole(x, ROLE_ADMIN))` passes from the EOA, reverts from a random address and from
  the Safe. Consequence: a single-key path to a `ROLE_ADMIN` grant with no Governor vote and no Safe veto. adminKey (10)
  and multisig (0) were already at the bare-EOA floor, so the scorer now only drops the Safe-veto credit: timelock
  60 to 50, composite 22 to 19 (`score_gmx_v2_rolestore`, 8 new tests). Pushed on-chain the same day (Arbitrum Sepolia, tx
  `0xd0437c358c6eb0a6e1b21ad13c433172ec4ccf9acd08d9e106bbb1ca66ecfafe`, block 310,866,307; the oracle reads 10/0/50/100/100/19, and all 9 Arbitrum targets read back
  identical to the scorer).
- **Radiant's two Safes** are now the registry group `radiant_pool_admin`; the live sweep (71 groups on 7 ecosystems) finds
  no overlap involving them, so the by-hand "none matched" is now a tool result.
- **Aave POOL_ADMIN on the other chains.** Section 1 found the PROTOCOL_GUARDIAN Safe holding `POOL_ADMIN` on Monad and
  read Base and Plasma for `EMERGENCY_ADMIN` only. Read live on 2026-09-20 with `isPoolAdmin` / `isRiskAdmin` /
  `isAssetListingAdmin` on each ACLManager: the PROTOCOL_GUARDIAN Safe holds `POOL_ADMIN` on Monad only; on Ethereum L1,
  Arbitrum, Base and Plasma it holds `EMERGENCY_ADMIN` and nothing else, and `POOL_ADMIN` there is the DAO Executor
  (the ACL admin). The ACLManager is not enumerable, so this checks the known guardian and admin addresses, not every
  possible holder. No other Aave score changes.

**UPDATE 2026-09-20 (Yuzu, plasma rows above):** the Yuzu rows (12h timelock PROPOSER / CANCELLER, syzUSD
DISTRIBUTOR, yzPP POOL_MANAGER) are resolved by a full live trace and an adversarial re-verification, see
`data/finding_2026-09-20-yuzu-authority-trace.md`. The placeholder score (adminKey 20) was a false negative
from an OpenZeppelin-4 role hash tested on OpenZeppelin-5 timelocks; the real chain scores 65/55/0, composite
43 (was 55), because the 3-of-5 Safe holds an instant pool-valuation seat on yzPP. Pushed on-chain the same day
(Plasma testnet, tx `0x490f5bb8ec6c6a436bfde4aee358928e24b8ac5597e74b72cd2f0c5f01adbb1a`, block 34,083,939; read back identical).
