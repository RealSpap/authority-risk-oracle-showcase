## Second opinion, 2026-11-11T06:27:58Z

### 1 upgrade(s) executed since the previous run (2026-11-10T22:06:24Z)

- **JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4** on solana: program redeployed since the previous run: slot 462802085 -> 468023491 (2026-11-11T06:31:04Z); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 2 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
