# Authority risk digest, 2026-10-11 21:18 UTC

## Needs a person, 2026-10-11T21:18:15Z: 33 item(s) (priority 1: 10, priority 2: 20, priority 3: 3); oldest 1.0 d

### Something happened: read before trusting the score (10)
- **Safe AddedOwner** robinhood 0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A (1.0 d): AddedOwner 0xB3bf…1c9B (ramses). To do: who is the new signer / what changed; then note it in data/digest_acknowledged.json. (safe_changes.json)
- **queued operation executable** solana 1oopBoJG58DgkUVKkEzKgyG9dvRmpgeEm1AVjoHkF78 (1.0 d): program upgrade: Squads proposal #1022: Upgrade of program 1oopBoJG58DgkUVKkEzKgyG9dvRmpgeEm1AVjoHkF78 via Squads v4 multisig C4aw…SuPk (4-of-9, time lock 86400 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana 1oopBoJG58DgkUVKkEzKgyG9dvRmpgeEm1AVjoHkF78 (1.0 d): program upgrade: Squads proposal #1026: Upgrade of program 1oopBoJG58DgkUVKkEzKgyG9dvRmpgeEm1AVjoHkF78 via Squads v4 multisig C4aw…SuPk (4-of-9, time lock 86400 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn (1.0 d): loader ExtendProgram: Squads proposal #112: ExtendProgram of program FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn via Squads v4 multisig Gb33…qyXF (3-of-7, time lock 0 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn (1.0 d): program upgrade: Squads proposal #128: Upgrade of program FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn via Squads v4 multisig Gb33…qyXF (3-of-7, time lock 0 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj (1.0 d): program upgrade: Squads proposal #20: Upgrade of program PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu via Squads v4 multisig AxkJ…UUSm (4-of-8, time lock 86400 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana XP1BRLn8eCYSygrd8er5P4GKdzqKbC3DLoSsS5UYVZy (1.0 d): program upgrade: Squads proposal #209: Upgrade of program XP1BRLn8eCYSygrd8er5P4GKdzqKbC3DLoSsS5UYVZy (not the tracked program) via Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana beamVVkNmKeXcuZ6zLpC9eM5YgVyAn4Z9xdPrz3gCW2 (1.0 d): program upgrade: Squads proposal #1021: Upgrade of program beamVVkNmKeXcuZ6zLpC9eM5YgVyAn4Z9xdPrz3gCW2 (not the tracked program) via Squads v4 multisig C4aw…SuPk (4-of-9, time lock 86400 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **queued operation executable** solana 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (0.6 d): multisig config: Squads proposal #60: multisig configuration: remove member via Squads v4 multisig J3mJ…vG8P (4-of-7, time lock 43200 s), found by the independent reader (1 tracked program). To do: read the call before it lands. (pending_ops.json)
- **admin transfer in flight** robinhood 0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d (0.0 d): 0x9db4…1a53 designated (pendingOwner() on the contract (Ownable2Step), a contract). To do: identify the designated admin; when it accepts, the admin read changes. (second_opinion.json pending_admin)

### Decide (20)
- **Safe guard to identify** ethereum-l1 0x2cc440b721d2cafd6d64908d6d8c4acc57f8afc3 (1.0 d): 0x74ab…8d29: contract, owned by 0xa075…c344. To do: say what this guard checks and who can change it. (second_opinion.json guard_detail)
- **second opinion disagrees** arbitrum 0xe23b4ae3624fb6f7cdef29bc8ead912f1ede6886 (1.0 d): the timelock score says no delay (0), the holder's owner is a timelock of 72 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** arbitrum 0xff162c694eaa571f685030649814282ea457f169 (1.0 d): the score says one key does everything (10), the live read finds a timelock (1209600s) via EIP-1967 admin -> ProxyAdmin owner(); the timelock score says no delay (0), the live read finds a timelock of 336 h in the admin path via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** arbitrum 0xffa10065ce1d1c42fabc46e06b84ed8ffeb4bae5 (1.0 d): the multisig score says no real multisig (0), the live read finds a Safe 3-of-3 via owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** ethereum-l1 0x55555815a5595991c3a0ff119b59aef6c8b55555 (1.0 d): the timelock score says no delay (0), the contract enforces its own timelock of 336 h (timelock()). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** hyperliquid 0x393d0b87ed38fc779fd9611144ae649ba6082109 (1.0 d): the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** hyperliquid 0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec (1.0 d): the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** hyperliquid 0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1 (1.0 d): the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** plasma 0x6695c0f8706c5ace3bdf8995073179cca47926dc (1.0 d): the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** plasma 0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66 (1.0 d): the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock()). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** robinhood 0x14b107cf534239c59571b066cb6497a321da897c (1.0 d): the timelock score says no delay (0), the live read finds a timelock of 24 h in the admin path via DEFAULT_ADMIN_ROLE member 1 of 3 (AccessControl). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** robinhood 0x5c98b2d892b37c9a1d3b69472bddc172a64cdc09 (1.0 d): the score says one key does everything (5), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner(). To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana 2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ (1.0 d): the score says one key does everything (5), the upgrade authority is a Squads v4 via account owned by program whirLbMi… -> program -> ProgramData CtXfPz… -> upgrade authority (a program-derived address, off the curve: a Squads vault or a protocol PDA, no key can sign for it directly) -> Squads v4 va. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB (1.0 d): the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj (1.0 d): the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **second opinion disagrees** solana USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (1.0 d): the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h. To do: review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json. (second_opinion.json disagreements)
- **timelock queue unread** base 0xf93b7122450a50af3e5a76e1d546e95ac1d0f579 (1.0 d): base timelock 0xf93b…f579, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', 'no data')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** robinhood 0x5ff98717a18833de1a49e11b498866d6fa1c9296 (1.0 d): robinhood timelock 0x5ff9…9296, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** robinhood 0x826aeaeee9233fa8ba199518dd8621a5962b1d02 (1.0 d): robinhood timelock 0x826a…1d02, found by the independent reader (1 tracked contract): UNREAD (ContractLogicError: ('execution reverted', '0x')). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)
- **timelock queue unread** hyperliquid 0xc5ded4f7f53919c714059a17d31371ae847e23d2 (0.9 d): hyperliquid timelock 0xc5de…23d2, found by the independent reader (1 tracked contract): UNREAD (Web3RPCError: {'code': -32005, 'message': 'rate limited'}). To do: find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen. (pending_ops.json)

### Coverage to extend (3)
- **admin Safe never used** robinhood 0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010 (1.0 d): robinhood:0x0605…9728 has executed no transaction (nonce 0). To do: an admin path nobody has exercised: confirm the signers can still act. (safe_activity.json)
- **admin Safe never used** tempo 0x10ee9aac980a180dd4dcfc96c746d60b0ea88f97 (1.0 d): tempo:0x6458…fbbc has executed no transaction (nonce 0). To do: an admin path nobody has exercised: confirm the signers can still act. (safe_activity.json)
- **admin role holder seen** robinhood 0xfd2fd4b046136b540a56c11c75ac679ae7d1db24 (1.0 d): 1 known contract(s) hold DEFAULT_ADMIN_ROLE; the list is not complete. To do: compare with the published admin-key score; holders cannot be listed on this contract. (admin_probe.json)

## Act now: oracles turning stale
- **ACT NOW** Ethereum L1 (Sepolia): 34 targets, first entry already stale since 2026-10-02 16:16 UTC; oldest update 2026-09-23 16:16 UTC
- **ACT NOW** Hyperliquid (HyperEVM): 16 targets, first entry already stale since 2026-10-03 19:43 UTC; oldest update 2026-09-24 19:43 UTC
- Base (Sepolia): 13 targets, first entry turns stale in 188 h (2026-10-19 17:38 UTC); oldest update 2026-10-10 17:38 UTC
- Plasma: 9 targets, first entry turns stale in 189 h (2026-10-19 18:03 UTC); oldest update 2026-10-10 18:03 UTC
- Monad: 9 targets, first entry turns stale in 189 h (2026-10-19 18:15 UTC); oldest update 2026-10-10 18:15 UTC
- Arbitrum (Sepolia): 13 targets, first entry turns stale in 190 h (2026-10-19 18:57 UTC); oldest update 2026-10-10 18:57 UTC
- Tempo (Moderato): 14 targets, first entry turns stale in 191 h (2026-10-19 19:56 UTC); oldest update 2026-10-10 19:56 UTC
- Solana (Devnet): 26 targets, first entry turns stale in 191 h (2026-10-19 20:00 UTC); oldest update 2026-10-10 20:00 UTC
- Robinhood Chain: 63 targets, first entry turns stale in 191 h (2026-10-19 20:41 UTC); oldest update 2026-10-10 20:41 UTC

## Safe authority changes, last 7 days
- robinhood: AddedOwner 0xB3bf…1c9B on 0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A (ramses), tx 6d4610f18f429737dbc1c8714b52a7adccc2494f344ca067afe4c9095f5714de
- not attempted: tempo (public RPC returned no control events); monad (public RPC caps eth_getLogs near 100 blocks); hyperliquid (public RPC rate-limits the query)

## Timelock queue
- **executable or waiting** Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program): XP1BRLn8eCYSygrd8er5P4GKdzqKbC3DLoSsS5UYVZy (no selector) ready at 2026-10-10 21:11Z (ready)
- **executable or waiting** Squads v4 multisig AxkJ…UUSm (4-of-8, time lock 86400 s), found by the independent reader (1 tracked program): H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj (no selector) ready at 2026-08-08 10:27Z (ready)
- **executable or waiting** Squads v4 multisig C4aw…SuPk (4-of-9, time lock 86400 s), found by the independent reader (1 tracked program): beamVVkNmKeXcuZ6zLpC9eM5YgVyAn4Z9xdPrz3gCW2 (no selector) ready at 2026-08-01 14:30Z (ready)
- **executable or waiting** Squads v4 multisig C4aw…SuPk (4-of-9, time lock 86400 s), found by the independent reader (1 tracked program): 1oopBoJG58DgkUVKkEzKgyG9dvRmpgeEm1AVjoHkF78 (no selector) ready at 2026-08-01 14:30Z (ready)
- **executable or waiting** Squads v4 multisig C4aw…SuPk (4-of-9, time lock 86400 s), found by the independent reader (1 tracked program): 1oopBoJG58DgkUVKkEzKgyG9dvRmpgeEm1AVjoHkF78 (no selector) ready at 2026-08-18 20:46Z (ready)
- **executable or waiting** Squads v4 multisig Gb33…qyXF (3-of-7, time lock 0 s), found by the independent reader (1 tracked program): FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn (no selector) ready at 2026-07-08 14:27Z (ready)
- **executable or waiting** Squads v4 multisig Gb33…qyXF (3-of-7, time lock 0 s), found by the independent reader (1 tracked program): FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn (no selector) ready at 2026-07-22 00:45Z (ready)
- **executable or waiting** Squads v4 multisig J3mJ…vG8P (4-of-7, time lock 43200 s), found by the independent reader (1 tracked program): 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (no selector) ready at 2026-10-11 04:43Z (ready)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xDcB34b56842F853A69E86De5A0c22c49d97C130C setWithdrawExpiration(uint40)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xDcB34b56842F853A69E86De5A0c22c49d97C130C setWithdrawCooldown(uint40)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xefeD08b791423C7D7937507Cf840E86a7ddC11c1 grantRole(bytes32,address)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0xefeD08b791423C7D7937507Cf840E86a7ddC11c1 schedule(address,uint256,bytes,bytes32,bytes32,uint256)
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0x730ea0A8Ff6Ad107efFD1aFd45CAA9A1733b6b4E 0x
- cleared, queued 2026-10-07: Compound Governance Timelock -> 0x25ace71c97B33Cc4729CF772ae268934F7ab5fA1 sendMessage(address,bytes,uint32)
- cleared, queued 2026-10-05: Ethena Timelock -> 0x1a44076050125825900e736c501f859c50fE728c setConfig(address,address,(uint32,uint32,bytes)[])
- cleared, queued 2026-10-06: Ethena Timelock -> 0x1a44076050125825900e736c501f859c50fE728c setConfig(address,address,(uint32,uint32,bytes)[])
- cleared, queued 2026-10-07: Ethena Timelock -> 0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34 setRateLimits((uint32,uint256,uint256)[])
- cleared, queued 2026-10-05: plasma timelock 0xabd3…5072, found by the independent reader (1 tracked contract) -> 0x6F475642a6e85809B1c36Fa62763669b1b48DD5B setConfig(address,address,(uint32,uint32,bytes)[])
- cleared, queued 2026-10-07: plasma timelock 0xabd3…5072, found by the independent reader (1 tracked contract) -> 0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34 setRateLimits((uint32,uint256,uint256)[])
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
- cleared, queued 2026-09-30: Squads v4 multisig 51sm…cjuH (3-of-5, time lock 36000 s), found by the independent reader (1 tracked program) -> ExponentnaRg3CQbW6dqQNZKXp7gtZ9DGMp1cwC4HAS7 (no selector)
- cleared, queued 2026-10-01: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> KvauGMspG5k6rtzrqqn7WNn3oZdyKqLKwK2XWQ8FLjd (no selector)
- cleared, queued 2026-10-01: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> KvauGMspG5k6rtzrqqn7WNn3oZdyKqLKwK2XWQ8FLjd (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> KvauGMspG5k6rtzrqqn7WNn3oZdyKqLKwK2XWQ8FLjd (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig 6hhB…fQbM (5-of-10, time lock 86400 s), found by the independent reader (1 tracked program) -> verifycLy8mB96wd9wqq3WDXQwM4oU6r42Th37Db9fC (no selector)
- cleared, queued 2026-09-29: Squads v4 multisig 7qip…cJtM (4-of-7, time lock 3600 s), found by the independent reader (1 tracked program) -> distAitdwx9mDm3SaPMtGZRjpXMPUenLhmPwoySV3Hp (no selector)
- cleared, queued 2026-09-29: Squads v4 multisig 7qip…cJtM (4-of-7, time lock 3600 s), found by the independent reader (1 tracked program) -> rdemKHu2ueeKkhwmM2GfJFaqD3zsrj7s3oGMN3dQMJT (no selector)
- cleared, queued 2026-09-28: Squads v4 multisig 7qip…cJtM (4-of-7, time lock 3600 s), found by the independent reader (1 tracked program) -> distAitdwx9mDm3SaPMtGZRjpXMPUenLhmPwoySV3Hp (no selector)
- cleared, queued 2026-09-29: Squads v4 multisig 7qip…cJtM (4-of-7, time lock 3600 s), found by the independent reader (1 tracked program) -> ProgM6JCCvbYkfKqJYHePx4xxSUSqJp7rh8Lyv7nk7S (no selector)
- cleared, queued 2026-09-30: Squads v4 multisig 7qip…cJtM (4-of-7, time lock 3600 s), found by the independent reader (1 tracked program) -> rdemKHu2ueeKkhwmM2GfJFaqD3zsrj7s3oGMN3dQMJT (no selector)
- cleared, queued 2026-09-30: Squads v4 multisig 7qip…cJtM (4-of-7, time lock 3600 s), found by the independent reader (1 tracked program) -> distAitdwx9mDm3SaPMtGZRjpXMPUenLhmPwoySV3Hp (no selector)
- cleared, queued 2026-09-29: Squads v4 multisig AEb1…dJGf (3-of-7, time lock 86400 s), found by the independent reader (1 tracked program) -> USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (no selector)
- cleared, queued 2026-09-29: Squads v4 multisig AEb1…dJGf (3-of-7, time lock 86400 s), found by the independent reader (1 tracked program) -> eUSXyKoZ6aGejYVbnp3wtWQ1E8zuokLAJPecPxxtgG3 (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig AEb1…dJGf (3-of-7, time lock 86400 s), found by the independent reader (1 tracked program) -> USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (no selector)
- cleared, queued 2026-10-04: Squads v4 multisig AEb1…dJGf (3-of-7, time lock 86400 s), found by the independent reader (1 tracked program) -> USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (no selector)
- cleared, queued 2026-09-28: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-02: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-05: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig CxnE…unP1 (4-of-7, time lock 600 s), found by the independent reader (1 tracked program) -> Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig J3mJ…vG8P (4-of-7, time lock 43200 s), found by the independent reader (1 tracked program) -> 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig J3mJ…vG8P (4-of-7, time lock 43200 s), found by the independent reader (1 tracked program) -> jup7TthsMgcR9Y3L277b8Eo9uboVSmu1utkuXHNUKar (no selector)
- cleared, queued 2026-10-06: Squads v4 multisig J3mJ…vG8P (4-of-7, time lock 43200 s), found by the independent reader (1 tracked program) -> jup3YeL8QhtSx1e253b2FDvsMNC87fDrgQZivbrndc9 (no selector)
- cleared, queued 2026-10-09: Squads v4 multisig J3mJ…vG8P (4-of-7, time lock 43200 s), found by the independent reader (1 tracked program) -> 7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z (no selector)
- cleared, queued 2026-10-01: Squads v4 multisig tr8r…Hb4u (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C (no selector)
- cleared, queued 2026-09-29: Squads v4 multisig tr8r…Hb4u (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK (no selector)
- cleared, queued 2026-10-08: Squads v4 multisig tr8r…Hb4u (3-of-4, time lock 0 s), found by the independent reader (1 tracked program) -> an address from a lookup table (no selector)

## Code behind tracked targets
- [CHANGED] Robinhood Chain:0x94bab9693ba2f6358507effcbd372b0660afff9d
- [CHANGED] Robinhood Chain:0x83341f891f898cb5e0cacc8a70501bba83d9cecf
- [CHANGED] Robinhood Chain:0x292fc50e4eb66c3f6514b9e402dbc25961824d62
- 10 target(s) added since that snapshot are not fingerprinted yet (informational)

## Solana Squads v4 multisigs (members, threshold, time lock)
- [CHANGED] 51smH7pBDKJDgmVnVks3gMWaPQFfmQ5s4Fc223yHcjuH (EXPONENT_MS): time lock (s) 14400 -> 36000
- [CHANGED] 5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN (REWARD_SUPER_MS): member removed BWyV…1w9C
- [CHANGED] AEb1u8FK8EuXLcPtprCy8s4NkqBNoP5mfbuEEop2dJGf (SOLSTICE_MS): member added 5kVC…SK1G (permissions 7); member added GG2k…Ub8E (permissions 7)
- [CHANGED] J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P (JL_UPGRADE_MS, UPGRADE_MS): member added 5tjC…LKzv (permissions 7)

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

**14 item(s) above; 4 source(s) not read.** Safe events are not covered for: tempo, monad, hyperliquid.
