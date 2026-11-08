## Second opinion, 2026-11-08T22:16:03Z

### 3 upgrade(s) executed since the previous run (2026-11-08T13:33:48Z)

- **0x9c4ec768c28520b50860ea7a15bd7213a9ff58bf** on arbitrum: implementation changed since the previous run: 0x5d3dfd6b0c855dcfe2cb768bb0800d16553c758b -> 0x9398741a8481787ee064293e2da4ad795fa11b7a (EIP-1967 implementation slot); the score reads who may upgrade, this is an upgrade that happened
- **0x52aa899454998be5b000ad077a46bbe360f4e497** on arbitrum: implementation changed since the previous run: 0xa57d7cef617271f4cea4f665d33ebcfcba4929f6 -> 0x8bdd171da967345a23af927051e8860e6b9fafe7 (EIP-1967 implementation slot); the score reads who may upgrade, this is an upgrade that happened
- **0xb125e6687d4313864e53df431d5425969c15eb2f** on base: implementation changed since the previous run: 0xc1455ae6df6cd808ed677f048e434e22892682a7 -> 0xb6ef22a5d7c3214c767b39213556e11e46ff8f3e (EIP-1967 implementation slot); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 3 disagreement(s) with the published score

- **0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec** on hyperliquid: the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()
- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())
- **GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB** on solana: the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
