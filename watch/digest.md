# Authority risk digest, 2026-10-08 21:12 UTC

## Act now: oracles turning stale
- **ACT NOW** Robinhood Chain: 63 targets, first entry already stale since 2026-10-05 07:42 UTC; oldest update 2026-09-26 07:42 UTC
- **ACT NOW** Ethereum L1 (Sepolia): 25 targets, first entry already stale since 2026-10-02 16:16 UTC; oldest update 2026-09-23 16:16 UTC
- **ACT NOW** Arbitrum (Sepolia): 13 targets, first entry already stale since 2026-10-05 07:20 UTC; oldest update 2026-09-26 07:20 UTC
- **ACT NOW** Base (Sepolia): 13 targets, first entry already stale since 2026-10-05 07:19 UTC; oldest update 2026-09-26 07:19 UTC
- **ACT NOW** Tempo (Moderato): 14 targets, first entry already stale since 2026-09-29 19:49 UTC; oldest update 2026-09-20 19:49 UTC
- **ACT NOW** Plasma: 9 targets, first entry already stale since 2026-09-29 19:38 UTC; oldest update 2026-09-20 19:38 UTC
- **ACT NOW** Monad: 9 targets, first entry already stale since 2026-10-03 17:20 UTC; oldest update 2026-09-24 17:20 UTC
- **ACT NOW** Hyperliquid (HyperEVM): 15 targets, first entry already stale since 2026-10-03 19:43 UTC; oldest update 2026-09-24 19:43 UTC
- **ACT NOW** Solana (Devnet): 18 targets, first entry already stale since 2026-10-05 07:18 UTC; oldest update 2026-09-26 07:18 UTC

## Safe authority changes, last 7 days
- robinhood: AddedOwner 0xB3bf…1c9B on 0x20D6…BE1A (ramses), tx 6d4610f18f429737dbc1c8714b52a7adccc2494f344ca067afe4c9095f5714de
- not attempted: tempo (public RPC returned no control events); monad (public RPC caps eth_getLogs near 100 blocks); hyperliquid (public RPC rate-limits the query)

## Timelock queue
- **executable or waiting** Compound Governance Timelock: 0x25ac…5fA1 sendMessage(address,bytes,uint32) ready at 2026-10-09 22:29Z (waiting)
- **executable or waiting** Ethena Timelock: 0x1a44076050125825900e736c501f859c50fE728c setConfig(address,address,(uint32,uint32,bytes)[]) ready at 2026-10-07 14:30Z (ready)
- cleared, queued 2026-10-03: Uniswap Governance Timelock -> 0x5B453493D2328E7F747eb2e66446eFe707728be7 setIsSentinel(address,bool)
- cleared, queued 2026-10-03: Uniswap Governance Timelock -> 0xb8274eFADB953FE9ae052D481a3FC5B6A3ceD703 setIsSentinel(address,bool)
- cleared, queued 2026-10-03: Uniswap Governance Timelock -> 0x98D2b241DA14c5dd848812708Eb8A1F3c5512f9d setIsSentinel(address,bool)
- cleared, queued 2026-10-03: Uniswap Governance Timelock -> 0x7597C40Fd3df66b750C14ad4D90524e247499011 setWormholePeer(uint16,bytes32)
- cleared, queued 2026-10-03: Uniswap Governance Timelock -> 0x6569925Aac77D6B8Bb085F31F9828ff80D5a0c44 setPeer(uint16,bytes32,uint8,uint256)
- cleared, queued 2026-10-03: Uniswap Governance Timelock -> 0xf5F4496219F31CDCBa6130B5402873624585615a sendMessage(address[],uint256[],bytes[],address,uint16)
- cleared, queued 2026-10-04: Compound Governance Timelock -> 0xd19d4B5d358258f05D7B411E21A1460D11B0876F sendMessage(address,uint256,bytes)
- cleared, queued 2026-10-04: Compound Governance Timelock -> 0x676A795fe6E43C17c668de16730c3F690FEB7120 sendMessage(address,bytes,uint32)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xDcB34b56842F853A69E86De5A0c22c49d97C130C setWithdrawExpiration(uint40)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xDcB34b56842F853A69E86De5A0c22c49d97C130C setWithdrawCooldown(uint40)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xefeD08b791423C7D7937507Cf840E86a7ddC11c1 grantRole(bytes32,address)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xefeD08b791423C7D7937507Cf840E86a7ddC11c1 schedule(address,uint256,bytes,bytes32,bytes32,uint256)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0x730ea0A8Ff6Ad107efFD1aFd45CAA9A1733b6b4E 0x
- cleared, queued 2026-10-05: Ethena Timelock -> 0x1a44076050125825900e736c501f859c50fE728c setConfig(address,address,(uint32,uint32,bytes)[])
- cleared, queued 2026-10-06: Ethena Timelock -> 0x1a44076050125825900e736c501f859c50fE728c setConfig(address,address,(uint32,uint32,bytes)[])
- cleared, queued 2026-10-07: Ethena Timelock -> 0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34 setRateLimits((uint32,uint256,uint256)[])

## Code behind tracked targets
- [CHANGED] Robinhood Chain:0x94bab9693ba2f6358507effcbd372b0660afff9d
- [CHANGED] Robinhood Chain:0x83341f891f898cb5e0cacc8a70501bba83d9cecf
- [CHANGED] Robinhood Chain:0x292fc50e4eb66c3f6514b9e402dbc25961824d62

## Solana Squads v4 multisigs (members, threshold, time lock)
- [CHANGED] 51smH7pBDKJDgmVnVks3gMWaPQFfmQ5s4Fc223yHcjuH (EXPONENT_MS): time lock (s) 14400 -> 36000
- [CHANGED] 5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN (REWARD_SUPER_MS): member removed BWyV…1w9C
- [CHANGED] AEb1u8FK8EuXLcPtprCy8s4NkqBNoP5mfbuEEop2dJGf (SOLSTICE_MS): member added 5kVC…SK1G (permissions 7); member added GG2k…Ub8E (permissions 7)

## Signer accounts (plain EOA, EIP-7702 delegation, contract)
- [CHANGED] monad:0xb41f…55ef: eoa -> EIP-7702 delegated to 0x63c0…e32b
- [GONE] ethereum-l1:0x2ed1…f27b: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0x0d61…9c5b: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0x387c…5344: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0x8ae8…422b: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0xcc77…959f: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0xd2b8…38e8: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0xd8ba…ca77: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0xe3fc…5120: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0xf83d…81d6: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update
- [GONE] monad:0xfc61…1279: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update

## Not read (no conclusion drawn for these)
- every attempted source was read

Posture drift (published score vs live scorer) is not part of this digest; the dashboard's verify-all recomputes every score live.

**15 item(s) above; 0 source(s) not read.** Safe events are not covered for: tempo, monad, hyperliquid.
