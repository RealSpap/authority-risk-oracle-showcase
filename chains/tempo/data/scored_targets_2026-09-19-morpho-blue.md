# Tempo maintenance run, 2026-09-19: rotation audit index 0 + Morpho Blue core (rule R9)

> **CORRECTED 2026-09-20:** the Morpho Blue core's `crossExposureScore` is 80,
> not 100. The 9-signer committee shared with Morpho's Ethereum L1, Base and
> Robinhood Chain owner Safes, treated below as context that stays out of the
> score, is now folded into the score (rule R6, project convention decided
> 2026-09-20). Scorer output 2026-09-20: 65 / 96 / 0 / 100 / **80** / 55
> (composite 55 and chain-capped composite 31 unchanged). The original text
> below is kept as the record of what was believed and pushed on 2026-09-19.
> Pushed on-chain 2026-09-20 (`updateScores()` tx
> `0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b`,
> Moderato block 36054236): the Moderato oracle now holds
> `crossExposureScore` 80 for this target, read back equal to the scorer
> output.

Phase: `maintenance`. Mainnet reads read-only (Tempo Mainnet, chain 4217, `https://rpc.tempo.xyz`
and the independent `https://tempo-rpc.publicnode.com`). Testnet write only to the project's own
oracle on Moderato (chain 42431).

## 1. Rotation audit, index 0: no divergence

`trackedTargets(0)` on the Moderato oracle `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` =
`0xCCCCCCCC00000000000000000000000000000001` (Tempo L1 validator registry, `ValidatorConfigV2`).

Re-derived from scratch with a standalone script (plain `web3.py`, no import of this repo's
scorer code), every read made on both RPCs and required to agree:

| Read | Value (both RPCs) |
|---|---|
| `eth_chainId` | 4217 on both |
| `owner()` of the registry | `0xdc659eff2784cf79fba88f85d26b1392270cca33` (a contract, 171 bytes of code) |
| owner `VERSION()` / `getThreshold()` / `getOwners()` | Safe 1.4.1, 2-of-5, 5 EOA owners |
| owner modules / guard slot | none / zero |

R4/R5/R5b/R7 on (2, 5), no delay: admin 50, multisig 37, timelock 0, composite 31. Published
`getScore()` before this run: `(50, 37, 0, 100, 100, 31)`. **Identical, no correction.**
`crossExposureScore` 100 was also re-confirmed by a full live run of
`scripts/methodology_test.py scores` (13 targets, before the Morpho Blue addition): every one of the
13 published tuples was reproduced exactly, the audited index included.

## 2. New target: Morpho Blue core

| Field | Value |
|---|---|
| Address | `0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97` |
| Address sources | docs.morpho.org/get-started/resources/addresses (Tempo), DefiLlama-Adapters `projects/morpho-blue/config.js` (`tempo.morphoBlue`, `fromBlock` 12653218) |
| Value | DefiLlama `api.llama.fi/protocols`, "Morpho Blue" Tempo TVL $42.6M (read 2026-09-19), the largest protocol on Tempo by DefiLlama TVL |
| Previously scouted | T4 of `scouted_targets_2026-09-17-run2.md` (owner Safe 5-of-9), never wired into `score_all()` until now |
| Proxy | none, both EIP-1967 slots empty (immutable contract) |
| `owner()` | Safe 1.4.1 `0x645890a0b5632e2cf4cb774994ebeab01230fbbc`, threshold 5, 9 owners, all EOAs, no module, zero guard slot |
| `feeRecipient()` | zero address (no fee switched on) |
| Cross-chain context (R6b, not in the score) | Morpho's Ethereum owner `0xcBa28b38103307ec8da98377fff9816c164f9afa` is also 5-of-9 with the **same 9 signers** (read on 2 Ethereum RPCs: publicnode, 1rpc) |

> CORRECTED 2026-09-20: the row label "(R6b, not in the score)" above is out of
> date. A signer set equal to a tracked target's committee on another
> ecosystem is now folded into `crossExposureScore` by rule R6 (flat 80,
> `min()` with the within-Tempo value), and the finding is also written to the
> target's `notes.crossChainSignerOverlap`. The committee is the same 9 owners
> on Tempo (Safe `0x645890a0...0fbbc`), Ethereum L1 (`0xcBa28b38...9AFa`), Base
> (same address as L1) and Robinhood Chain (`0x0605956...9728`), each 5-of-9,
> independently re-confirmed live 2026-09-20; the scorer compares the owners it
> reads on Tempo against a dated snapshot, it does not query the other chains.

Owner powers, from `morpho-org/morpho-blue` `src/Morpho.sol`: `setOwner`, `enableIrm`,
`enableLltv`, `setFee` (max 25% of interest, `ConstantsLib.MAX_FEE`), `setFeeRecipient`. It cannot
move user funds, pause, or change any existing market's oracle, IRM or LLTV.

Score under new rule R9 (METHODOLOGY.md 4.1): admin 65 (k >= 3), multisig 96 (20 x 5 - 4),
timelock 0 (no delay on owner calls), oracle authority 100 (R5c: the core owner has no power over
any price source), cross exposure 100 (none of the 9 signers is a root signer of another tracked
Tempo target), **composite 55** (chain-capped 31).

> CORRECTED 2026-09-20: cross exposure is **80**, not 100. The sentence above
> is right that none of the 9 signers is a root signer of another tracked
> TEMPO target, but the field's meaning is "the same root signer also controls
> another tracked target", and the same 9 signers are the owners of the
> tracked Morpho Blue cores on Ethereum L1, Base and Robinhood Chain. The
> tuple the scorer returns now is 65 / 96 / 0 / 100 / 80 / 55; the tuple
> `getScore()` read back in section 3 below (65 / 96 / 0 / 100 / 100 / 55) is
> the state pushed on 2026-09-19 and is superseded on-chain by the 2026-09-20
> re-push (tx `0xcdc3cc09...aa44b`, block 36054236), which wrote 80.

Mitigating: the owner's powers are narrow and fee-capped; 5-of-9 is a real quorum.
Aggravating: no delay at all on those powers; the per-market oracle authority, which is where the
real price risk of Morpho markets sits (T5 in the 2026-09-17 scouting: RedStone feed proxies behind
a 2-of-3 Safe ProxyAdmin), is **not** captured by this score and stays an open point.

## 3. Push and read-back

`deploy/push_scores.py` (real send) re-derived all 14 targets live, pushed them in one
`updateScores()` transaction: `0xe34510ed23b72647195fc312d0de7156840fa8280de38d029ef50516e6029cc6`,
block 36006957, status 1, from the shared throwaway key `0x20630C6A...32f5`. Read-back after the
push: `trackedTargetsCount()` = 14, `trackedTargets(13)` = Morpho Blue core with
`(65, 96, 0, 100, 100, 55)`, and the 13 older targets unchanged in every score field (only
`lastUpdated` moved), `methodologyHash` unchanged.

## 4. Checked and not added this run

| Candidate (DefiLlama, Tempo) | TVL | Why not added |
|---|---|---|
| Sentora Curator, Gauntlet | $36.2M, $288k | Curator labels, their Tempo vaults are already tracked (R8) |
| Tempo Stablecoin DEX, Tempo Fee AMM | $11.0M, $44.6k | Precompiles with no owner, authority already in the chain baseline (decided 2026-09-17) |
| Uniswap V4, V2, V3 | $8.5M, $71k, $242 | Owner is a Wormhole message receiver governed from Ethereum (2-day timelock); cross-chain root not modelled by R2, left open rather than scored wrong |
| Symbiosis | $20.9k | Below the $25k floor used in the 2026-09-17 scouting |
| Hinkal, GlueHook, Skate AMM, Reservoir, LayerZero V2 | $0 to $2 | No real value |
| Morpho cbBTC/pathUSD market oracle (T5) | part of Morpho Blue TVL | Needs an oracle-authority target type (feed proxy admin -> oracleAuthorityScore mapping), not written yet |
