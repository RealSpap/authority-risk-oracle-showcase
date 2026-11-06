## Second opinion, 2026-11-06T19:37:22Z

### 1 admin change(s) since the previous run (2026-11-06T06:53:05Z)

- **4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8** on solana: admin read changed since the previous run: squads J3oBkTkDXU3TcAggJEa3YeBZE5om5yNAdTtLVNXFD47 7-of-16 (16 voters), time lock 0s -> squads J3oBkTkDXU3TcAggJEa3YeBZE5om5yNAdTtLVNXFD47 7-of-15 (15 voters), time lock 0s (via account owned by program MFv2hWf3… -> program -> ProgramData 4Q8u2n… -> upgrade authority (a program-derived address, off the curve: a Squads vault or a protocol PDA, no key can sign for it directly) -> Squads v4 vault 0 of multisig 7FCPipJWVbPbdHymVt1gJYwKciakkJz5GahdQySemvHk)

The live admin of a tracked contract moved between two watch runs: the published score may be out of date before the next push. Read the case now.

### 4 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0x393d0b87ed38fc779fd9611144ae649ba6082109** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB** on solana: the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
