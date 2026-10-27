## Second opinion, 2026-10-27T13:04:43Z

### 13 disagreement(s) with the published score

- **0xff162c694eaa571f685030649814282ea457f169** on arbitrum: the score says one key does everything (10), the live read finds a timelock (1209600s) via EIP-1967 admin -> ProxyAdmin owner(); the timelock score says no delay (0), the live read finds a timelock of 336 h in the admin path via EIP-1967 admin -> ProxyAdmin owner()
- **0xe23b4ae3624fb6f7cdef29bc8ead912f1ede6886** on arbitrum: the timelock score says no delay (0), the holder's owner is a timelock of 72 h
- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0x393d0b87ed38fc779fd9611144ae649ba6082109** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1** on hyperliquid: the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **0x6695c0f8706c5ace3bdf8995073179cca47926dc** on plasma: the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner()
- **0x14b107cf534239c59571b066cb6497a321da897c** on robinhood: the timelock score says no delay (0), the live read finds a timelock of 24 h in the admin path via DEFAULT_ADMIN_ROLE member 1 of 3 (AccessControl)
- **0x5c98b2d892b37c9a1d3b69472bddc172a64cdc09** on robinhood: the score says one key does everything (5), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner()
- **GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB** on solana: the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h
- **H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj** on solana: the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h
- **2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ** on solana: the score says one key does everything (5), the upgrade authority is a Squads v4 via account owned by program whirLbMi… -> program -> ProgramData CtXfPz… -> upgrade authority (a program-derived address, off the curve: a Squads vault or a protocol PDA, no key can sign for it directly) -> Squads v4 vault 0 of multisig BQsDWkL417U4tVE2sDnPks469pKdm6YzFgKH77doiEjF; the multisig score says no real multisig (0), the Squads multisig is a 5-of-13; the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h
- **USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx** on solana: the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
