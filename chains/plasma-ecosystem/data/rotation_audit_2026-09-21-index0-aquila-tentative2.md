# Rotation audit 2026-09-21 - Plasma Ecosystem, index 0 (Aquila validator-set authority)

**Attempt 2.** Attempt 1 reached the right numbers through a broken proof
chain and was rejected by an independent verifier. This file replaces it:
same conclusion, entirely new evidence, every claim re-run here and
replayable by a third party from any directory with `cast` and public RPCs
only - no access to this private repository is needed for any of the 25
commands in `runs/2026-09-21/plasma-ecosystem/claims_tentative2.txt`.

## Correction of attempt 1 (stated as a correction, not as a new finding)

Attempt 1 wrote the target-0 address as
`0x6c50b8ca8eea1c75dee5b5ea79772acabc92f48` - 41 characters, i.e. 39 hex
digits instead of 40, one `a` missing after `8ee`. The real value returned
by `trackedTargets(0)` is
`0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48`. Because of that single
character, the six `getScore` commands in its claims journal could never
run: `Web3.to_checksum_address` raises `ValueError` on a 39-hex string, so
all six exited 1 with empty output. The scores it reported were therefore
not produced by the commands it cited. Claim 7 of the new journal is that
correction, and it fails if the two strings are ever the same length or
equal.

Attempt 1 also proved "target 0 is Aquila" with `echo "<literal string>"`.
A command that re-prints its own input exits 0 whatever the truth of the
statement, so it proved nothing by construction. Claim 8 replaces it: it
takes the address **returned by the oracle** on testnet 9746 and asks that
same address on mainnet 9745 to identify itself through selector
`0x54fd4d50`, asserting the reply is the ASCII string
`plasma-validator-set/v1`. Nothing is typed by hand in the comparison.

## What was read, on two independent endpoints per network

Oracle half - Plasma testnet, chain 9746:
`https://testnet-rpc.plasma.to` (official) and `https://plasma-testnet.drpc.org`
(independent). `AuthorityRiskOracle 0x50840a7667baEa9D05ad4ae3dCeb384724b58720`,
`trackedTargetsCount() = 9`, `trackedTargets(0) = 0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48`,
`getScore(target) = (50, 50, 0, 100, 100, 35)`, `lastUpdated = 1789933100`
(2026-09-20T19:38:20Z, the re-push Spap ran that evening), `isStale = false`,
`methodologyHash = 929c8482…a722cd`, identical to the hash carried by the
index-1 entry. Byte-for-byte identical on both RPCs.

Authority half - Plasma mainnet, chain 9745, **read-only**:
`https://rpc.plasma.to` (official) and `https://plasma.gateway.tenderly.co`
(independent). Aquila carries 109 bytes of proxy bytecode; `owner()` is
`0xCA6fE51bEd6269e3A325d85131Df9B475ecf8F53`, a Safe reporting
`VERSION() = "1.4.1"`, `getThreshold() = 3`, `getOwners()` = 4 addresses, all
four with no bytecode and nonce 0 - bare EOAs. `getMinDelay()` on that Safe
reverts on both RPCs: not a `TimelockController`, the authority chain
terminates at the Safe. Identical on both RPCs.

## Independent re-derivation

Derived from the mainnet state above, without reading `scorers.py` first:

| Component | Derivation | Derived | On-chain |
|---|---|---|---|
| adminKeyScore | threshold == 3 | 50 | 50 |
| multisigScore | min(100, 3×15 + 1×5) | 50 | 50 |
| timelockScore | no TimelockController anywhere in the chain | 0 | 0 |
| oracleAuthorityScore | target is not itself a price/oracle authority | 100 | 100 |
| crossExposureScore | no shared committee with another tracked target | 100 | 100 |
| compositeScore | floor((4×50 + 3×50 + 3×0 + 5) / 10) | 35 | 35 |

**No divergence.** Nothing to re-push on-chain, no script prepared for Spap,
no new target proposed this pass.

## Falsifiability of the method

Every command is an assertion: it exits 0 only if the stated fact holds.
Three negative controls were run to prove the commands are not vacuously
true - expecting composite 36 instead of 35 fails; asserting a contract
address is a bare EOA fails; asserting `getThreshold()` reverts fails.

The verifier of attempt 1 noted that the verifier had returned
green on an English-language journal only because its success-word list is
French, so its first step never engaged. This journal is written in French
and the engagement was checked directly: flipping all 25 exit codes to 1
makes the tool report 25 fabrications, so the green on the real journal
(25 steps, 0 fabrication) is a real green and not a language artifact.

No key material was read, no transaction was signed or sent, nothing was
written to any mainnet.
