# Authority risk digest, 2026-10-15 21:31 UTC

## Needs a person, 2026-10-15T21:31:19Z: 32 item(s) (priority 1: 9, priority 2: 20, priority 3: 3); oldest 5.0 d

### Overdue: 1 priority-1 item(s) waiting for more than 2 day(s), back in the alarm
- **queued operation executable** arbitrum 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 (2.1 d): parameter change: updateUserSupplyConfigs((address,address,uint8,uint256,uint256,uint256)[]) via arbitrum timelock 0x4d6c…2346, found by the independent reader (1 tracked contract)

### Something happened: read before trusting the score (9)
- **queued operation executable** arbitrum 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 (2.1 d): parameter change: updateUserSupplyConfigs((address,address,uint8,uint256,uint256,uint256)[]) via arbitrum timelock 0x4d6c…2346, found by the independent reader (1 tracked contract). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** plasma 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 (1.8 d): parameter change: updateUserBorrowConfigs((address,address,uint8,uint256,uint256,uint256,uint256)[]) via plasma timelock 0x4d6c…2346, found by the independent reader (1 tracked contract). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana 3D6ojc8vBfDteLBDTTRznZbZRh7bkEGQaYqNkudoTCBQ (1.8 d): call: Squads proposal #210: call to 3D6ojc8vBfDteLBDTTRznZbZRh7bkEGQaYqNkudoTCBQ (not the tracked program) via Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana an address from a lookup table (1.3 d): call: Squads proposal #128: call to an address from a lookup table; call to an address from a lookup table; call to ProgM6JCCvbYkfKqJYHePx4xxSUSqJp7rh8Lyv7nk7S; call to ProgM6JCCvbYkfKqJYH (not the tracked program) via Squads v4 multisig 7FCP…mvHk (7-of-15, time lock 0 s), found by the independent r. To do: read the call before it lands. (pending_ops.json)
- **Safe AddedOwner** base 0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D (1.1 d): AddedOwner 0x9939…21ba (aerodrome_emergency_council). To do: who is the new signer / what changed; then note it in data/digest_acknowledged.json. (safe_changes.json)
- **queued operation executable** plasma 0x6F475642a6e85809B1c36Fa62763669b1b48DD5B (0.3 d): parameter change: setConfig(address,address,(uint32,uint32,bytes)[]) via plasma timelock 0xabd3…5072, found by the independent reader (1 tracked contract). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana 7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF (0.1 d): program upgrade: Squads proposal #105: Upgrade of program KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD via Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (0.1 d): call: Squads proposal #106: call to verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (not the tracked program) via Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **admin transfer in flight** robinhood 0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d (0.0 d): 0x9db4…1a53 designated (pendingOwner() on the contract (Ownable2Step), a contract). To do: identify the designated admin; when it accepts, the admin read changes. (second_opinion.json pending_admin)

### Decide (20)
- **Safe guard to identify** ethereum-l1 0x2cc440b721d2cafd6d64908d6d8c4acc57f8afc3 (5.0 d): 0x74ab…8d29: contract, owned by 0xa075…c344. To do: say what this guard checks and who can change it. (second_opinion.json guard_detail)
- **second opinion disagrees** arbitrum 0xe23b4ae3624fb6f7cdef29bc8ead912f1ede6886 (5.0 d): the timelock score says no delay (0), the holder's owner is a timelock of 72 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** arbitrum 0xff162c694eaa571f685030649814282ea457f169 (5.0 d): the score says one key does everything (10), the live read finds a timelock (1209600s) via EIP-1967 admin -> ProxyAdmin owner(); the timelock score says no delay (0), the live read finds a timelock of 336 h in the admin path via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** arbitrum 0xffa10065ce1d1c42fabc46e06b84ed8ffeb4bae5 (5.0 d): the multisig score says no real multisig (0), the live read finds a Safe 3-of-3 via owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** ethereum-l1 0x55555815a5595991c3a0ff119b59aef6c8b55555 (5.0 d): the timelock score says no delay (0), the contract enforces its own timelock of 336 h (timelock()). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** hyperliquid 0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec (5.0 d): the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** plasma 0x6695c0f8706c5ace3bdf8995073179cca47926dc (5.0 d): the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** plasma 0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66 (5.0 d): the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock()). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** robinhood 0x14b107cf534239c59571b066cb6497a321da897c (5.0 d): the timelock score says no delay (0), the live read finds a timelock of 24 h in the admin path via DEFAULT_ADMIN_ROLE member 1 of 3 (AccessControl). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** robinhood 0x5c98b2d892b37c9a1d3b69472bddc172a64cdc09 (5.0 d): the score says one key does everything (5), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana 2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ (5.0 d): the score says one key does everything (5), the upgrade authority is a Squads v4 via account owned by program whirLbMi… -> program -> ProgramData CtXfPz… -> upgrade authority (a program-derived address, off the curve: a Squads vault or a protocol PDA, no key can sign for it directly) -> Squads v4 va. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB (5.0 d): the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj (5.0 d): the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (5.0 d): the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **timelock queue unread** base 0xf93b7122450a50af3e5a76e1d546e95ac1d0f579 (5.0 d): base timelock 0xf93b…f579, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', 'no data')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** robinhood 0x5ff98717a18833de1a49e11b498866d6fa1c9296 (5.0 d): robinhood timelock 0x5ff9…9296, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** robinhood 0x826aeaeee9233fa8ba199518dd8621a5962b1d02 (5.0 d): robinhood timelock 0x826a…1d02, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **second opinion disagrees** hyperliquid 0x393d0b87ed38fc779fd9611144ae649ba6082109 (2.1 d): the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** hyperliquid 0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1 (1.3 d): the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **timelock queue unread** hyperliquid 0xc5ded4f7f53919c714059a17d31371ae847e23d2 (1.1 d): hyperliquid timelock 0xc5de…23d2, found by the independent reader (1 tracked contract): UNREAD (Web3RPCError: {'code': -32005, 'message': 'rate limited'}). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)

### Coverage to extend (3)
- **admin Safe never used** robinhood 0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010 (5.0 d): robinhood:0x0605…9728 has executed no transaction (nonce 0). To do: an admin path nobody has exercised: confirm the signers can still act. (safe_activity.json)
- **admin Safe never used** tempo 0x10ee9aac980a180dd4dcfc96c746d60b0ea88f97 (5.0 d): tempo:0x6458…fbbc has executed no transaction (nonce 0). To do: an admin path nobody has exercised: confirm the signers can still act. (safe_activity.json)
- **admin role holder seen** robinhood 0xfd2fd4b046136b540a56c11c75ac679ae7d1db24 (5.0 d): 1 known contract(s) hold DEFAULT_ADMIN_ROLE; the list is not complete. To do: compare with the published admin-key score; holders cannot be listed on this contract. (admin_probe.json)

## Act now: oracles turning stale
- **ACT NOW** Ethereum L1 (Sepolia): 34 targets, first entry already stale since 2026-10-02 16:16 UTC; oldest update 2026-09-23 16:16 UTC
- Hyperliquid (HyperEVM): 16 targets, first entry turns stale in 128 h (2026-10-21 05:46 UTC); oldest update 2026-10-12 05:46 UTC
- Base (Sepolia): 13 targets, first entry turns stale in 146 h (2026-10-21 23:32 UTC); oldest update 2026-10-12 23:32 UTC
- Plasma: 9 targets, first entry turns stale in 146 h (2026-10-21 23:56 UTC); oldest update 2026-10-12 23:56 UTC
- Monad: 9 targets, first entry turns stale in 147 h (2026-10-22 00:12 UTC); oldest update 2026-10-13 00:12 UTC
- Arbitrum (Sepolia): 13 targets, first entry turns stale in 147 h (2026-10-22 00:54 UTC); oldest update 2026-10-13 00:54 UTC
- Tempo (Moderato): 14 targets, first entry turns stale in 148 h (2026-10-22 01:57 UTC); oldest update 2026-10-13 01:57 UTC
- Solana (Devnet): 26 targets, first entry turns stale in 149 h (2026-10-22 02:46 UTC); oldest update 2026-10-13 02:46 UTC
- Robinhood Chain: 63 targets, first entry turns stale in 150 h (2026-10-22 03:26 UTC); oldest update 2026-10-13 03:26 UTC

## Safe authority changes, last 7 days
- base: AddedOwner 0x9939…21ba on 0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D (aerodrome_emergency_council), tx a17926b75e972ebc2d02fb3ae95b96df5eaf7f27400f77928440452554858479
- not attempted: tempo (public RPC returned no control events); monad (public RPC caps eth_getLogs near 100 blocks); hyperliquid (public RPC rate-limits the query)

## Timelock queue
- **executable or waiting** arbitrum timelock 0x4d6c…2346, found by the independent reader (1 tracked contract): 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 updateUserSupplyConfigs((address,address,uint8,uint256,uint256,uint256)[]) ready at 2026-10-13 19:06Z (ready)
- **executable or waiting** plasma timelock 0x4d6c…2346, found by the independent reader (1 tracked contract): 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 updateUserBorrowConfigs((address,address,uint8,uint256,uint256,uint256,uint256)[]) ready at 2026-10-13 19:08Z (ready)
- **executable or waiting** plasma timelock 0xabd3…5072, found by the independent reader (1 tracked contract): 0x6F475642a6e85809B1c36Fa62763669b1b48DD5B setConfig(address,address,(uint32,uint32,bytes)[]) ready at 2026-10-15 09:56Z (ready)
- **executable or waiting** Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program): 3D6ojc8vBfDteLBDTTRznZbZRh7bkEGQaYqNkudoTCBQ (no selector) ready at 2026-10-13 20:49Z (ready)
- **executable or waiting** Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program): 7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF (no selector) ready at 2026-10-15 16:34Z (ready)
- **executable or waiting** Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program): verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector) ready at 2026-10-15 16:34Z (ready)
- **executable or waiting** Squads v4 multisig 7FCP…mvHk (7-of-15, time lock 0 s), found by the independent reader (1 tracked program): an address from a lookup table (no selector) ready at 2026-10-14 11:48Z (ready)
- cleared, queued 2026-10-13: Compound Governance Timelock -> 0x40D16FC0246aD3160Ccc09B8D0D3A2cD28aE6C2f approve(address,uint256)
- cleared, queued 2026-10-13: Compound Governance Timelock -> 0x80226fc0Ee2b096224EeAc085Bb9a8cba1146f7D ccipSend(uint64,(bytes,bytes,(address,uint256)[],address,bytes))
- cleared, queued 2026-10-12: Ethena Timelock -> 0x1a44076050125825900e736c501f859c50fE728c setConfig(address,address,(uint32,uint32,bytes)[])
- cleared, queued 2026-10-14: robinhood timelock 0x0da1…001d, found by the independent reader (1 tracked contract) -> 0x14b107CF534239c59571B066cB6497a321Da897C 0xd86fac1b
- cleared, queued 2026-10-14: robinhood timelock 0x0da1…001d, found by the independent reader (1 tracked contract) -> 0x14b107CF534239c59571B066cB6497a321Da897C upgradeToAndCall(address,bytes)
- cleared, queued 2026-10-02: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> 5RWm5iSZx3XgcEQgEjdj7QYRsSRUhfHcAZE6fVKrNxhx (no selector)
- cleared, queued 2026-10-02: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw (no selector)
- cleared, queued 2026-10-02: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P (no selector)
- cleared, queued 2026-10-02: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ (no selector)
- cleared, queued 2026-10-02: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> Dsug6JqUcLJaTJCx7ufPREeHjnMakmVEAYSi5oaAEnzK (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> 5RWm5iSZx3XgcEQgEjdj7QYRsSRUhfHcAZE6fVKrNxhx (no selector)
- cleared, queued 2026-10-12: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ (no selector)
- cleared, queued 2026-10-13: Squads v4 multisig 2yMo…rshW (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P (no selector)
- cleared, queued 2026-10-12: Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program) -> XP1BRLn8eCYSygrd8er5P4GKdzqKbC3DLoSsS5UYVZy (no selector)
- cleared, queued 2026-10-13: Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program) -> ExponentnaRg3CQbW6dqQNZKXp7gtZ9DGMp1cwC4HAS7 (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> KvauGMspG5k6rtzrqqn7WNn3oZdyKqLKwK2XWQ8FLjd (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> KvauGMspG5k6rtzrqqn7WNn3oZdyKqLKwK2XWQ8FLjd (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-10-13: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> KvauGMspG5k6rtzrqqn7WNn3oZdyKqLKwK2XWQ8FLjd (no selector)
- cleared, queued 2026-10-13: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-10-12: Squads v4 multisig 7FCP…mvHk (7-of-15, time lock 0 s), found by the independent reader (1 tracked program) -> 4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8 (no selector)
- cleared, queued 2026-10-14: Squads v4 multisig 7FCP…mvHk (7-of-15, time lock 0 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig AEb1…dJGf (3-of-7, time lock 86400 s), found by the independent reader (1 tracked program) -> USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (no selector)
- cleared, queued 2026-10-04: Squads v4 multisig AEb1…dJGf (3-of-7, time lock 86400 s), found by the independent reader (1 tracked program) -> USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (no selector)
- cleared, queued 2026-10-15: Squads v4 multisig BQsD…iEjF (5-of-13, time lock 86400 s), found by the independent reader (1 tracked program) -> 2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ (no selector)
- cleared, queued 2026-10-02: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-05: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-13: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-14: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig J3mJ…vG8P (4-of-6, time lock 43200 s), found by the independent reader (1 tracked program) -> 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig J3mJ…vG8P (4-of-6, time lock 43200 s), found by the independent reader (1 tracked program) -> jup7TthsMgcR9Y3L277b8Eo9uboVSmu1utkuXHNUKar (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig J3mJ…vG8P (4-of-6, time lock 43200 s), found by the independent reader (1 tracked program) -> jup3YeL8QhtSx1e253b2FDvsMNC87fDrgQZivbrndc9 (no selector)
- cleared, queued 2026-10-09: Squads v4 multisig J3mJ…vG8P (4-of-6, time lock 43200 s), found by the independent reader (1 tracked program) -> 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (no selector)
- cleared, queued 2026-10-12: Squads v4 multisig J3mJ…vG8P (4-of-6, time lock 43200 s), found by the independent reader (1 tracked program) -> 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig tr8r…Hb4u (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> an address from a lookup table (no selector)

## Code behind tracked targets
- [CHANGED] Robinhood Chain:0x94bab9693ba2f6358507effcbd372b0660afff9d
- [CHANGED] Robinhood Chain:0x83341f891f898cb5e0cacc8a70501bba83d9cecf
- [CHANGED] Robinhood Chain:0x292fc50e4eb66c3f6514b9e402dbc25961824d62
- [CHANGED] Robinhood Chain:0x14b107cf534239c59571b066cb6497a321da897c
- 10 target(s) added since that snapshot are not fingerprinted yet (informational)

## Solana Squads v4 multisigs (members, threshold, time lock)
- [CHANGED] 51smH7pBDKJDgmVnVks3gMWaPQFfmQ5s4Fc223yHcjuH (EXPONENT_MS): time lock (s) 14400 -> 36000
- [CHANGED] 5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN (REWARD_SUPER_MS): member added CjEM…LZKY (permissions 7); member removed BWyV…1w9C
- [CHANGED] 5Y93cxqp8rGtjDhxGkehewfhFdxLkrCfPDWookCGeASF (JL_ADMIN_MS, ADMIN_MS): member removed 4Sqa…4Jqp; threshold 5 -> 4
- [CHANGED] AEb1u8FK8EuXLcPtprCy8s4NkqBNoP5mfbuEEop2dJGf (SOLSTICE_MS): member added 5kVC…SK1G (permissions 7); member added GG2k…Ub8E (permissions 7)
- [CHANGED] J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P (JL_UPGRADE_MS, UPGRADE_MS): member added 5tjC…LKzv (permissions 7); member removed 8BR8…rz9H

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
- Timelock queue, base timelock 0xf93b…f579, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', 'no data'))
- Timelock queue, hyperliquid timelock 0xc5de…23d2, found by the independent reader (1 tracked contract): UNREAD (Web3RPCError: {'code': -32005, 'message': 'rate limited'})
- Timelock queue, robinhood timelock 0x5ff9…9296, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x'))
- Timelock queue, robinhood timelock 0x826a…1d02, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x'))

Posture drift (published score vs live scorer) is not part of this digest; the dashboard's verify-all recomputes every score live.

**12 item(s) above; 4 source(s) not read.** Safe events are not covered for: tempo, monad, hyperliquid.
