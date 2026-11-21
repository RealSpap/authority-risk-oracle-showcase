## Second opinion, 2026-11-21T01:08:33Z

### 1 upgrade(s) executed since the previous run (2026-11-20T19:09:27Z)

- **ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw** on solana: program redeployed since the previous run: slot 469811067 -> 471854493 (2026-11-20T19:28:12Z); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 2 admin change(s) since the previous run (2026-11-20T19:09:27Z)

- **0x0dc846db6a4ec7b5a3e542f7db88049e9add2541** on robinhood: admin read changed since the previous run: safe 0x8c45…f5d5 2-of-3 [signers: 3 eoa] -> safe 0x8c458f866e603335ef179a63a2528f357732f5d5 3-of-7 (via owner()); signer composition changed since the previous run: 3 eoa -> 7 eoa
- **0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d** on robinhood: admin read changed since the previous run: eoa 0x3b2b…2f14 (transfer pending to 0x9db4…1a53) -> safe 0x9db4…1a53 3-of-7 (via owner()) (this holder governs 3 tracked contract(s) in all)

The live admin of a tracked contract moved between two watch runs: the published score may be out of date before the next push. Read the case now.

### 4 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0x393d0b87ed38fc779fd9611144ae649ba6082109** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **0xfe7e25de55e5cbbecccb661f3679f873f72b9b0d** on robinhood: the score says one key does everything (2), the live read finds a Safe 3-of-7 via owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via owner()

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
