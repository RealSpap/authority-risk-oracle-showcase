# Cross-exposure consistency audit (2026-09-21)

Question asked of the 8 ecosystems' scorer output, with no new target and no new chain: **does the same relation get the same
number wherever it appears?** Two token-free scans (a same-protocol table across ecosystems, and every address named by two or
more targets inside one ecosystem) found four real inconsistencies, all now fixed, and three open points.

## Fixed

| Target | Before | After | Why |
|---|---|---|---|
| GMX V2 RoleStore (Arbitrum) | cross 100 | **80** | Sharing a root is symmetric. The tracked GMX V1 Vault already read 80 because its `tokenManager` Safe holds proposer, executor and canceller on the GMX V2 timelock that is a `ROLE_ADMIN` of this RoleStore. The RoleStore, on the other end of the same relation, read 100. It now reads the same fact (live: PROPOSER, EXECUTOR and CANCELLER all true for that Safe on the timelock). |
| Pendle Router (Arbitrum) | cross 60 | **80** | The 2026-09-20 convention is a flat 80 for a committee shared with another ecosystem. This scorer deducted 20 per matching snapshot, so the same Safe read 60 here and 80 on Plasma and Robinhood Chain. A disclosed deviation, closed. Note the direction: this value goes **up**, the oracle now reports less exposure for it than before. |
| Uniswap V4 PoolManager (Monad) | shared root on a dated snapshot | shared root **read live** | The Ethereum side of the Wormhole hop was taken from a note. It is now read: `messageSender()` on the Monad receiver is the known Ethereum sender, whose `owner()` is the Timelock (read on Ethereum with its own RPC, together with the Timelock's `delay()` and `admin()`). The fold to 80 switches itself off if either hop stops matching. The scorer's docstring named the getter `sender()`, which reverts; it is `messageSender()`. |

| Kinetiq kHYPE and HIP3 StakingManagers (Hyperliquid) | cross 100 each | **80** each | Both are rooted in the same 4-of-8 Safe (DEFAULT_ADMIN_ROLE and MANAGER_ROLE on each, read live) and their own notes said so, but HL methodology 4.5 counted only HyperCore keys. Extended to HyperEVM root holders (`chains/hyperliquid/METHODOLOGY.md` 4.5, `_apply_hyperevm_shared_root_exposure`); para's vault and Ventuals share no root and stay 100. Fixed 2026-09-21 on request. |

Composites are unchanged on all four (19, 43, 80 and 4/4). A live drift check on 2026-09-21 shows on Arbitrum exactly four
`crossExposureScore` differences (these two plus the Compound and Uniswap ones already recorded) and on Monad exactly one
(Uniswap).

## Open, not changed

1. **Within-ecosystem sharing is counted per target on Ethereum L1 and per signer group on Base and Robinhood Chain.** Ethena's
   Safe over 5 L1 targets reads 20, while Robinhood Chain's four Uniswap targets in one group and Base's three Uniswap targets
   read no within-ecosystem deduction. Documented in METHODOLOGY.md as a limitation, still unreconciled.
2. **Uniswap on Monad has timelockScore 60, the four other ecosystems 75.** The Monad path adds Wormhole's guardian set as a
   trust assumption the canonical bridges do not have, and the scorer did not re-read GovernorBravo's quorum. This may be
   deliberate; nothing in the code says which. Left as is.
3. **Morpho Blue core on Tempo reads multisigScore 96, the same 5-of-9 committee reads 95 elsewhere.** A different multisig
   formula on Tempo (documented limitation). One point, composite identical (55).

Closed the same day on request: Kinetiq on Hyperliquid (table above) and Robinhood Chain's Chainlink and LayerZero multisig
formula (`data/correction_2026-09-21-chainlink-layerzero-multisig-formula.md`).

## Not on-chain yet

Scorer output only. The deployed testnet oracles hold the previous values until the next re-push of Arbitrum, Monad and Hyperliquid.
