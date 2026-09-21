# Base Ecosystem -- maintenance run, 2026-09-19

Phase: `maintenance` (first maintenance run, audit rotation index 0).
Evidence folder (pipeline side, outside this repo):
`authority-risk-oracle-multichain-pipeline/runs/2026-09-19-cron/base-ecosystem/`.

## (a) Audit rotation -- `trackedTargets(0)` re-derived from zero

`trackedTargets(0)` on the Base Sepolia oracle `0x50840a7667baEa9D05ad4ae3dCeb384724b58720`
= `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` (Morpho Blue), read on both
`https://sepolia.base.org` and `https://base-sepolia-rpc.publicnode.com`.

Re-derived with a standalone script (raw `eth_call` selectors, NOT the repo's
`scorers.py`) on two independent Base mainnet RPCs, `https://mainnet.base.org`
(block 51,522,868) and `https://base-rpc.publicnode.com` (block 51,522,870):

| Read | mainnet.base.org | base-rpc.publicnode.com |
|---|---|---|
| `MorphoBlue.owner()` | `0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa` | same |
| Safe `VERSION()` / `getThreshold()` / owners | 1.3.0 / 5 / 9 | same |
| Safe guard slot / enabled modules | none / 0 | same |
| `feeRecipient()` | `0x0` (no fee switched on) | same |

Robinhood Chain's own Morpho Blue owner Safe `0x060595638692de6CCd47ca04094F1772D3D39728`
re-read live on `https://rpc.mainnet.chain.robinhood.com` (chain 4663): 5-of-9,
the exact same 9 owners -> the published `crossExposureScore = 80` is still correct.

Re-derived: adminKey 65, multisig min(100, 5*15 + 4*5) = 95, timelock 0,
composite floor(0.4*65 + 0.3*95 + 0 + 0.5) = 55, crossExposure 80.
Published `getScore()` before this run: `(65, 95, 0, 100, 80, 55, ...)`.
**No divergence -- no correction needed for index 0.**

## (b) New targets (4)

Selection: DefiLlama `/protocols` Base TVL on 2026-09-19, non-duplicate
(each address grepped across `chains/`, `scripts/`, `data/` -- zero hits),
official source for every address, authority read live on both Base RPCs above.
Risk-curator/vault entries (Steakhouse, Gauntlet, Spark LL, Grove) deliberately
skipped: their Base TVL sits inside Morpho Blue, already tracked.

| Target | Address | Base TVL (DefiLlama) | Address source | Composite | Cross-exp. |
|---|---|---|---|---|---|
| Aerodrome Slipstream CLFactory | `0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A` | $217.0M (protocol, 4 factories) | aerodrome-finance/slipstream README "Initial Deployment"; DefiLlama-Adapters `projects/aerodrome-CL` | 46 | 80 |
| Uniswap V2 Factory | `0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6` | $89.1M | Uniswap/docs `content/protocols/v2/deployments.mdx`; Uniswap/sdk-core `addresses.ts` | 85 | 100 |
| Uniswap V4 PoolManager | `0x498581fF718922c3f8e6A244956aF099B2652b2b` | $59.3M | Uniswap/docs `content/protocols/v4/deployments.mdx`; DefiLlama-Adapters `projects/uniswap-v4` | 85 | 100 |
| Moonwell Comptroller (Unitroller) | `0xfBb21d0380beE3312B33c4353c8936a0F13EF26C` | $14.0M | moonwell-fi/moonwell-contracts-v2 `chains/8453.json`; DefiLlama-Adapters `registries/compound.js` | 71 | 100 |

### Aerodrome Slipstream -- same key as Aerodrome V1

`owner()`, `swapFeeManager()`, `unstakedFeeManager()` all = `0xE6A41fE61E7a1996B59d508661e3f524d6A32075`,
a 3-of-7 Safe, no timelock -- the SAME Safe already tracked as Aerodrome V1
PoolFactory `pauser()`/`feeManager()` and `Voter.governor()` (2026-09-18 finding).
One 3-of-7 key therefore governs both Aerodrome AMMs (~$354M combined Base TVL
by DefiLlama's two entries) plus gauge whitelisting. Powers per `CLFactory.sol`:
owner = setOwner / enableTickSpacing (fee <= 10%); fee managers = swap/unstaked fee
modules, `setDefaultUnstakedFee` capped at 50%. Pools are clones, no upgrade path found.
Open thread: the two later Slipstream factories (`0xaDe65c38...716a`, `0xf8f2eB49...61Ef`,
also counted in DefiLlama's TVL) were not scored.

### Uniswap V2 / V4 -- same DAO root as the tracked V3 Factory

`V2Factory.feeToSetter()` and `PoolManager.owner()` both = `0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9`,
the same forwarder the tracked V3 Factory's fee adapter points to: slot 0 = the
`L2CrossDomainMessenger` predeploy, slot 1 = Uniswap's L1 Timelock
`0x1a9C8182C09F50C8318d769245beA52c32BE35BC` (delay 172,800 s, admin GovernorBravo
`0x408ED6354d4973f66138C91495F2f2FCbd8724C3`, re-read live on Ethereum). Scored exactly
like V3 (80/100/75 -> 85). Blast radius is narrow (V2 fee switch; V4 protocol-fee
controller, capped fee) -- disclosed, not folded into the score, per project convention.
DAO-rooted, so not counted in `crossExposureScore` (no Safe signer set).

### Moonwell -- Wormhole-gated cross-chain governance with a guardian fast-track

`Unitroller.admin()` = TemporalGovernor `0x8b621804a7637b781e2BbD58e256a591F2dF7d51`.
`proposalDelay()` = 86,400 s. `allTrustedSenders(2)` (Wormhole chain 2 = Ethereum)
= `0x8769b70a...5838`, which moonwell-fi's own `chains/1.json` names
`MULTICHAIN_GOVERNOR_V2_PROXY`; chains 16/23/24/30 return empty. Guardian
(`owner()`) = 3-of-5 Safe `0x446342AF4F3bCD374276891C6bb3411bf2F8779E`,
`guardianPauseAllowed = true`: per `TemporalGovernor.sol` it can pause once and,
while paused, `fastTrackProposalExecution()` a valid trusted-sender VAA without the
delay. Scored like Aave V3 Base (65/100/50 -> 71). mToken sample
(`MOONWELL_USDC 0xEdc817A2...6c22`).admin() is the same TemporalGovernor.
Open threads: Ethereum-side governor (quorum, proxy admin) and Wormhole's guardian
set not verified; only Wormhole chain ids 2/16/23/24/30 were checked for senders.
Also disclosed: one guardian owner (`0xD791292655A1d382FcC1a6Cb9171476cf91F2caa`)
is listed as a non-contract `DEPRECATED_WARDEN_EMISSIONS_ADMIN` in Moonwell's own
`chains/8453.json` -- not investigated further.

## CORRECTION -- Aerodrome V1 PoolFactory `crossExposureScore` 100 -> 80

`score_all()` now runs an intra-Base overlap pass (`_apply_intra_base_overlap`,
contract definition: -20 per OTHER tracked target sharing a root signer, Safe-rooted
targets only). Adding Slipstream put two tracked targets on the same Safe, so
Aerodrome V1 (index 2) drops from 100 to 80. Composite unchanged (46): crossExposure
is not part of the composite. Pushed and read back on-chain (below).

## Push and readback

`updateScores()` tx `0xc412f6dc76299177db63ab207a9609ae5124215d2ac52ac280e98fa9a1c14fa1`,
Base Sepolia block 47,033,666, status 1, from the shared deployer
`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`. `trackedTargetsCount()` = 9; every
`getScore()` read back on both Base Sepolia RPCs matches what was sent -- full dump in
[`oracle_readback_2026-09-19.csv`](oracle_readback_2026-09-19.csv).

## Tests

`python3 -m unittest discover -s chains/base-ecosystem/tests -v` -- 13 new tests
(4 scorers + the overlap pass), all pass. Existing
`scripts/lib/tests/test_base_ecosystem_scorers.py` unchanged and still passes.
