## Second opinion, 2026-11-07T22:00:27Z

### 1 upgrade(s) executed since the previous run (2026-11-07T13:10:43Z)

- **0xc3d688b66703497daa19211eedff47f25384cdc3** on ethereum-l1: implementation changed since the previous run: 0x63e749153baf1838f63ca22c275370bd2b1ceb15 -> 0x0b07565a8ef48170e15918b251ebd95109b23255 (EIP-1967 implementation slot); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 4 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0x393d0b87ed38fc779fd9611144ae649ba6082109** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB** on solana: the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
