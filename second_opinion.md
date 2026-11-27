## Second opinion, 2026-11-27T19:10:57Z

### 1 upgrade(s) executed since the previous run (2026-11-27T13:10:01Z)

- **0x52aa899454998be5b000ad077a46bbe360f4e497** on plasma: implementation changed since the previous run: 0x3605004f3f40e7147300574e786206de8b342796 -> 0x8bdd171da967345a23af927051e8860e6b9fafe7 (EIP-1967 implementation slot); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 3 admin change(s) since the previous run (2026-11-27T13:10:01Z)

- **0x5c98b2d892b37c9a1d3b69472bddc172a64cdc09** on robinhood: admin read changed since the previous run: safe 0x9db4…1a53 3-of-7 [signers: 7 eoa] -> timelock 0x272468ec9610972fc42d4fee16e79dc9e0812ccd 86400s (via EIP-1967 admin -> ProxyAdmin owner())
- **0xd01c774d4a66408326bc65728ac5ae5aaf004032** on robinhood: admin read changed since the previous run: safe 0x9db4…1a53 3-of-7 [signers: 7 eoa] -> safe 0x9db42d3bda1525963db3b2372c4daabaf0491a53 3-of-5 (via owner()); signer composition changed since the previous run: 7 eoa -> 5 eoa (this holder governs 2 tracked contract(s) in all)
- **0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d** on robinhood: admin read changed since the previous run: safe 0x9db4…1a53 3-of-7 [signers: 7 eoa] -> safe 0x9db42d3bda1525963db3b2372c4daabaf0491a53 3-of-5 (via owner()); signer composition changed since the previous run: 7 eoa -> 5 eoa (this holder governs 2 tracked contract(s) in all)

The live admin of a tracked contract moved between two watch runs: the published score may be out of date before the next push. Read the case now.

### 4 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0x393d0b87ed38fc779fd9611144ae649ba6082109** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d** on robinhood: the score says one key does everything (2), the live read finds a Safe 3-of-5 via owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-5 via owner()

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
