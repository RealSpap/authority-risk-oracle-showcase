## Second opinion, 2026-11-23T13:12:46Z

### 1 upgrade(s) executed since the previous run (2026-11-23T07:16:59Z)

- **7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF** on solana: program redeployed since the previous run: slot 461744249 -> 472935074 (2026-11-23T12:01:29Z); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 4 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0x393d0b87ed38fc779fd9611144ae649ba6082109** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d** on robinhood: the score says one key does everything (2), the live read finds a Safe 3-of-7 via owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via owner()

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
