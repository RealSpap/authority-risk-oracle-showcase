# Authority risk digest, 2026-11-11 06:44 UTC

## Needs a person, 2026-11-11T06:44:52Z: 15 item(s) (priority 1: 3, priority 2: 8, priority 3: 4); oldest 31.4 d

### Overdue: 1 priority-1 item(s) waiting for more than 2 day(s), back in the alarm
- **queued operation executable** ethereum 0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94 (4.5 d): parameter change: addToWhitelist(address,bytes4) via Ethena Timelock

### Something happened: read before trusting the score (3)
- **queued operation executable** ethereum 0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94 (4.5 d): parameter change: addToWhitelist(address,bytes4) via Ethena Timelock. To do: read the call before it lands. (pending_ops.json)
- **admin transfer in flight** robinhood 0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d (0.0 d): 0x9db4…1a53 designated (pendingOwner() on the contract (Ownable2Step), a contract). To do: identify the designated admin; when it accepts, the admin read changes. (second_opinion.json pending_admin)
- **upgrade executed** solana JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 (0.0 d): program redeployed since the previous run: slot 462802085 -> 468023491 (2026-11-11T06:31:04Z); the score reads who may upgrade, this is an upgrade that happened. To do: read what the new implementation does before trusting the score (the private pipeline's implementation check names selectors added and dropped); NO verified source on Sourcify for the new implementation: read the bytecode, or find a verified source on the chain's explorer. (second_opinion.json upgrades)

### Decide (8)
- **Safe guard to identify** ethereum-l1 0x2cc440b721d2cafd6d64908d6d8c4acc57f8afc3 (31.4 d): 0x74ab…8d29: contract, owned by 0xa075…c344. To do: say what this guard checks and who can change it. (second_opinion.json guard_detail)
- **second opinion disagrees** plasma 0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66 (31.4 d): the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock()). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **timelock queue unread** base 0xf93b7122450a50af3e5a76e1d546e95ac1d0f579 (31.4 d): base timelock 0xf93b…f579, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', 'no data')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** robinhood 0x5ff98717a18833de1a49e11b498866d6fa1c9296 (31.4 d): robinhood timelock 0x5ff9…9296, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** robinhood 0x826aeaeee9233fa8ba199518dd8621a5962b1d02 (31.4 d): robinhood timelock 0x826a…1d02, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** base 0xcc3e7c85bb0ee4f09380e041fee95a0caedd4a02 (24.5 d): base timelock 0xcc3e…4a02, found by the independent reader (1 tracked contract): UNREAD (RetryError: HTTPSConnectionPool(host='base.rpc.sentio.xyz', port=443): Max retries exceeded with url: / (Caused . To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **second opinion disagrees** hyperliquid 0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec (9.0 d): the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **timelock queue unread** hyperliquid 0xc5ded4f7f53919c714059a17d31371ae847e23d2 (3.4 d): hyperliquid timelock 0xc5de…23d2, found by the independent reader (1 tracked contract): UNREAD (Web3RPCError: {'code': -32005, 'message': 'rate limited'}). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)

### Coverage to extend (4)
- **admin Safe never used** robinhood 0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010 (31.4 d): robinhood:0x0605…9728 has executed no transaction (nonce 0). To do: an admin path nobody has exercised: confirm the signers can still act. (safe_activity.json)
- **admin Safe never used** tempo 0x10ee9aac980a180dd4dcfc96c746d60b0ea88f97 (31.4 d): tempo:0x6458…fbbc has executed no transaction (nonce 0). To do: an admin path nobody has exercised: confirm the signers can still act. (safe_activity.json)
- **admin role holder seen** robinhood 0xfd2fd4b046136b540a56c11c75ac679ae7d1db24 (31.4 d): 1 known contract(s) hold DEFAULT_ADMIN_ROLE; the list is not complete. To do: compare with the published admin-key score; holders cannot be listed on this contract. (admin_probe.json)
- **admin role holder seen** hyperliquid 0x393d0b87ed38fc779fd9611144ae649ba6082109 (0.0 d): 1 known contract(s) hold DEFAULT_ADMIN_ROLE; the list is not complete. To do: compare with the published admin-key score; holders cannot be listed on this contract. (admin_probe.json)

## Act now: oracles turning stale
- **ACT NOW** Ethereum L1 (Sepolia): 39 targets, first entry turns stale in 38 h (2026-11-12 20:50 UTC); oldest update 2026-11-03 20:50 UTC
- Solana (Devnet): 26 targets, first entry turns stale in 207 h (2026-11-19 21:46 UTC); oldest update 2026-11-10 21:46 UTC
- Tempo (Moderato): 14 targets, first entry turns stale in 207 h (2026-11-19 21:51 UTC); oldest update 2026-11-10 21:51 UTC
- Base (Sepolia): 13 targets, first entry turns stale in 207 h (2026-11-19 22:00 UTC); oldest update 2026-11-10 22:00 UTC
- Arbitrum (Sepolia): 13 targets, first entry turns stale in 208 h (2026-11-19 22:28 UTC); oldest update 2026-11-10 22:28 UTC
- Hyperliquid (HyperEVM): 16 targets, first entry turns stale in 208 h (2026-11-19 22:29 UTC); oldest update 2026-11-10 22:29 UTC
- Robinhood Chain: 63 targets, first entry turns stale in 208 h (2026-11-19 22:35 UTC); oldest update 2026-11-10 22:35 UTC
- Plasma: 9 targets, first entry turns stale in 208 h (2026-11-19 22:37 UTC); oldest update 2026-11-10 22:37 UTC
- Monad: 9 targets, first entry turns stale in 210 h (2026-11-20 00:41 UTC); oldest update 2026-11-11 00:41 UTC

## Safe authority changes, last 7 days
- none new in the ecosystems read
- not attempted: tempo (public RPC returned no control events); monad (public RPC caps eth_getLogs near 100 blocks); hyperliquid (public RPC rate-limits the query)

## Timelock queue
- **executable or waiting** Ethena Timelock: 0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94 addToWhitelist(address,bytes4) ready at 2026-11-06 09:54Z (ready)
- cleared, queued 2026-11-05: Compound Governance Timelock -> 0x316f9708bB98af7dA9c68C1C3b5e79039cD336E3 updateAssetBorrowCollateralFactor(address,address,uint64)
- cleared, queued 2026-11-05: Compound Governance Timelock -> 0x316f9708bB98af7dA9c68C1C3b5e79039cD336E3 updateAssetSupplyCap(address,address,uint128)
- cleared, queued 2026-11-05: Compound Governance Timelock -> 0x1EC63B5883C3481134FD50D5DAebc83Ecd2E8779 deployAndUpgradeTo(address,address)
- cleared, queued 2026-11-05: Compound Governance Timelock -> 0x866E82a600A1414e583f7F13623F1aC5d58b0Afa sendMessage(address,bytes,uint32)
- cleared, queued 2026-11-05: Compound Governance Timelock -> 0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f createRetryableTicket(address,uint256,uint256,address,address,uint256,uint256,bytes)
- cleared, queued 2026-11-07: arbitrum timelock 0x3fb4…f88a, found by the independent reader (1 tracked contract) -> 0xb21b06D71c75973babdE35b49fFDAc3F82Ad3775 fulfillBasicOrder_efficient_6GL6yc((address,uint256,uint256,address,address,address,uint256,uint256,uint8,uint256,uint256,bytes32,uint256,bytes32,bytes32,uint256,(uint256,address)[],bytes))
- cleared, queued 2026-11-07: arbitrum timelock 0x3fb4…f88a, found by the independent reader (1 tracked contract) -> 0xD10b40fF1D92e2267D099Da3509253D9Da4D715e fulfillBasicOrder_efficient_6GL6yc((address,uint256,uint256,address,address,address,uint256,uint256,uint8,uint256,uint256,bytes32,uint256,bytes32,bytes32,uint256,(uint256,address)[],bytes))
- cleared, queued 2026-11-07: arbitrum timelock 0x4d6c…2346, found by the independent reader (1 tracked contract) -> 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 addImplementation(address,bytes4[])
- cleared, queued 2026-11-08: arbitrum timelock 0x4d6c…2346, found by the independent reader (1 tracked contract) -> 0x87E765B0f76F9071B7Ff8bCa2A1EB8338AcD14C3 updateAuth(address,uint256)
- cleared, queued 2026-11-09: arbitrum timelock 0x4d6c…2346, found by the independent reader (1 tracked contract) -> 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 updateUserSupplyConfigs((address,address,uint8,uint256,uint256,uint256)[])
- cleared, queued 2026-11-02: ethereum-l1 timelock 0x2386…1f4c, found by the independent reader (1 tracked contract) -> 0x2386DC45AdDed673317eF068992F19421B481F4c fulfillBasicOrder_efficient_6GL6yc((address,uint256,uint256,address,address,address,uint256,uint256,uint8,uint256,uint256,bytes32,uint256,bytes32,bytes32,uint256,(uint256,address)[],bytes))
- cleared, queued 2026-11-08: plasma timelock 0x4d6c…2346, found by the independent reader (1 tracked contract) -> 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 updateUserBorrowConfigs((address,address,uint8,uint256,uint256,uint256,uint256)[])

## Code behind tracked targets
- [CHANGED] Robinhood Chain:0x94bab9693ba2f6358507effcbd372b0660afff9d
- [CHANGED] Robinhood Chain:0x83341f891f898cb5e0cacc8a70501bba83d9cecf
- [CHANGED] Robinhood Chain:0x292fc50e4eb66c3f6514b9e402dbc25961824d62
- [CHANGED] Robinhood Chain:0x14b107cf534239c59571b066cb6497a321da897c
- [CHANGED] Ethereum L1 (Sepolia):0xc3d688b66703497daa19211eedff47f25384cdc3
- [CHANGED] Arbitrum (Sepolia):0x9c4ec768c28520b50860ea7a15bd7213a9ff58bf
- [CHANGED] Arbitrum (Sepolia):0x52aa899454998be5b000ad077a46bbe360f4e497
- [CHANGED] Base (Sepolia):0xb125e6687d4313864e53df431d5425969c15eb2f
- 15 target(s) added since that snapshot are not fingerprinted yet (informational)

## Solana Squads v4 multisigs (members, threshold, time lock)
- [CHANGED] 51smH7pBDKJDgmVnVks3gMWaPQFfmQ5s4Fc223yHcjuH (EXPONENT_MS): time lock (s) 14400 -> 36000
- [CHANGED] 5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN (REWARD_SUPER_MS): member added 86mC…iMLg (permissions 6); member added CjEM…LZKY (permissions 7); member added FbcW…vHW7 (permissions 7); member removed 6Li1…ueL9; member removed BWyV…1w9C
- [CHANGED] 5Y93cxqp8rGtjDhxGkehewfhFdxLkrCfPDWookCGeASF (JL_ADMIN_MS, ADMIN_MS): member removed 4Sqa…4Jqp; threshold 5 -> 4
- [CHANGED] 74QKjjvoSrq2cGqFzzQNN8ox3gomYS1mBwcLsbiYaH8j (ADMIN_MS): member added 6vRh…apm9 (permissions 7); member removed 3Cxn…MEMB; member removed FwZd…YJCX
- [CHANGED] 7FCPipJWVbPbdHymVt1gJYwKciakkJz5GahdQySemvHk (UPGRADE_MS): member added 6vRh…apm9 (permissions 7); member removed 3Cxn…MEMB
- [CHANGED] 7VVPGwvWh37LyhL1tVm6pGUzm3S1u6p17H6ttT9ZEFex (DELEGATE_MS): member added DAk1…KiMf (permissions 7)
- [CHANGED] AEb1u8FK8EuXLcPtprCy8s4NkqBNoP5mfbuEEop2dJGf (SOLSTICE_MS): member added 5kVC…SK1G (permissions 7); member added GG2k…Ub8E (permissions 7)
- [CHANGED] BQsDWkL417U4tVE2sDnPks469pKdm6YzFgKH77doiEjF (UPGRADE_MS): member added 6M7B…99HV (permissions 2); member added CjEM…LZKY (permissions 5); member removed 2NfC…7gXb; member removed 9FtD…ZMn4
- [CHANGED] HvYoRSJdVcj6WRWV57yLu2Vmwh1ccqJRdkCwhNsSfRu4 (ADMIN_MS): time lock (s) 0 -> 21600
- [CHANGED] J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P (JL_UPGRADE_MS, UPGRADE_MS): member added 5tjC…LKzv (permissions 7); member removed 8BR8…rz9H

## Signer accounts (plain EOA, EIP-7702 delegation, contract)
- [CHANGED] base:0x8769…5838: eoa -> contract
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

## Configurations behind constant scores (Ramses CL V2, Longbow vaults, Spark executor: the scorer reads them, the score does not follow them)
- [CHANGED] ramses-clv2: 3 read(s)
- team_multisig_owner_count: expected 1, read 2 (scorer docstring (same sentence))

## Not read (no conclusion drawn for these)
- Safe changes, base: UNREAD (call budget exhausted)
- Timelock queue, base timelock 0xcc3e…4a02, found by the independent reader (1 tracked contract): UNREAD (RetryError: HTTPSConnectionPool(host='base.rpc.sentio.xyz', port=443): Max retries exceeded with url: / (Caused by ResponseError('to)
- Timelock queue, base timelock 0xf93b…f579, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', 'no data'))
- Timelock queue, hyperliquid timelock 0xc5de…23d2, found by the independent reader (1 tracked contract): UNREAD (Web3RPCError: {'code': -32005, 'message': 'rate limited'})
- Timelock queue, robinhood timelock 0x5ff9…9296, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x'))
- Timelock queue, robinhood timelock 0x826a…1d02, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x'))

Posture drift (published score vs live scorer) is not part of this digest; the dashboard's verify-all recomputes every score live.

**6 item(s) above; 6 source(s) not read.** Safe events are not covered for: tempo, monad, hyperliquid.
