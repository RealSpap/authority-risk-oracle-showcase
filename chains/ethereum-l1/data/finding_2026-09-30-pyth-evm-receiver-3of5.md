# Pyth on EVM: prices and upgrades now verified by 3 of 5 Pyth keys, not Wormhole's 13 of 19 (terrain, no tracked market exposed, nothing scored)

2026-09-30. Found by the "titan" competitor pass (`work/2026-09-30-feuille-de-route-titan.md`), re-read here directly. Read-only.

## What changed on 26 August

| | Before 26/08/2026 | Now |
|---|---|---|
| What Pyth's EVM contract trusts (`wormhole()`) | Wormhole Core, guardian set 7, **13 of 19** (`quorum(19)`) | A Pyth-specific receiver per chain, guardian set index 1, **5 keys, quorum 3** |
| Receiver (Ethereum / Base / Arbitrum) | n/a | `0x3a2dd09b...1820` / `0x581aaf05...6c55` / `0x8d289cdd...46f8` |
| Keys (same on every chain read) | 19 Wormhole guardians | `0x41534bb1`, `0x6502987b`, `0x44a3e8f6`, `0x13edc776`, `0x3af08885` |

- Read by me on Ethereum (publicnode, drpc), Base (publicnode, drpc) and Arbitrum (publicnode, arb1.arbitrum.io): Pyth `0x4305FB66...` /
  `0x8250f4aF...` / `0xff1a0f47...` → `wormhole()` → `getCurrentGuardianSetIndex()` = 1 → `getGuardianSet(1)` = the 5 keys above, no expiry.
  The pass also read Monad (`0x2880aB15...`, receiver `0xCAC639d1...`) and HyperEVM (`0xe9d69CdD...`, receiver `0x6b81963B...`): same set.
- **Quorum 3 of 5:** `quorum()` reverts ("unsupported") on the receiver, so it is not read directly. The pass matched the keccak of the
  implementation bytecode to the `ReceiverImplementationHalf (3-of-5)` fingerprint published in OP-PIP-132 (quorum n/2+1). Not re-hashed by me.
- **Governance too:** Pyth's `owner()` is zero; upgrades are governance VAAs from the Pythian Council's emitter on Solana, and OP-PIP-132
  ("all subsequent governance ... is verified against the Pyth Pro guardian set") routes them through the same receiver. So 3 keys can sign a
  price update or a contract upgrade, on every EVM chain that moved (33 deployments, 19 mainnet, per the proposal; not re-read one by one).
- **An unannounced rotation:** set 0 (the proposal's keys, 4th and 5th `0xd9D7D452`, `0x1663a5A8`) expired 05/09/2026 16:48:47 UTC, so set 1
  replaced two of five keys around 04/09. The switch itself is public (OP-PIP-132, 25/08); no forum post was found for the rotation, and the
  rotation transaction was not found (archive logs not served for free).

## Exposure in what this oracle tracks: zero, measured

`scripts/check_morpho_market_oracles.py` rerun today: 153 feed rows of the Morpho markets ≥ $5M on the 6 tracked EVM chains ($5.65B). Every feed
and price contract (80 on the chains where Pyth is deployed) was asked `pyth()`: **80 of 80 reverted** (real reverts, not network errors),
none is Pyth's contract. No tracked target and no tracked Morpho market reads a Pyth price. The Aave V3 reserves were not checked.

## Why it is still worth writing down

It is a real, recent change of authority shape for a major oracle provider (from a 13-of-19 external network to 3 of 5 of the provider's own
keys, prices and upgrades), with an unannounced key rotation, and no source found tracks it. Nothing here depends on it today, so it is
terrain, not a score. **Adding Pyth (or a Pyth consumer) as a target is Spap's decision.** Next steps if it becomes one: check Aave V3
reserves (`getSourceOfAsset`) and non-Morpho lenders for Pyth wrappers; find the set-1 rotation transaction on an archive RPC.
