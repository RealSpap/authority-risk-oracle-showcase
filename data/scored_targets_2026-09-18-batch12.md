# Batch 12 (2026-09-18): PancakeSwap AMM (V2) Factory, plus a crossExposure correction on PancakeSwap V3 Factory it exposed

Scouted from DefiLlama's live protocol list (`https://api.llama.fi/protocols`,
`chains` containing "Robinhood Chain", 176 protocols listed), sorted by
Robinhood Chain TVL, skipping protocols already tracked directly or through a
shared authority chain (Morpho Blue, LayerZero V2, Spark Savings, PancakeSwap
AMM V3, Uniswap V2/V3/V4, Curve DEX, Pendle V2 were all already covered).

## PancakeSwap AMM (V2) Factory -- 2/100

| Field | Value |
|---|---|
| Target | `0x02a84c1b3BBD7401a5f7fa98a384EBC70bB5749E` |
| TVL | ~$1.9B across all chains DefiLlama attributes to "PancakeSwap AMM" (`pancakeswap-amm`); no per-chain Robinhood Chain breakdown published, but `allPairsLength()` = 156 real pairs confirms real usage, not a stub deployment |
| adminKeyScore | 5 |
| multisigScore | 0 |
| timelockScore | 0 |
| oracleAuthorityScore | 100 |
| crossExposureScore | 80 |
| compositeScore | 2 |

### Address source

DefiLlama's official adapter `DefiLlama-Adapters/projects/pancake-swap/index.js`,
`robinhood: defaultExport` where `defaultExport = { tvl: getUniTVL({ factory:
'0x02a84c1b3BBD7401a5f7fa98a384EBC70bB5749E', ... }) }` -- the same
deterministic factory address PancakeSwap reuses on Polygon zkEVM, Linea,
op_bnb, Arbitrum, Base and Monad (the same "identical address on many chains"
convention already used for `score_pancakeswap_v3_factory()`, which is a
**separate, already-tracked** `pancakeswap-amm-v3` protocol/factory, not this
one). Confirmed live on two independent RPCs
(`rpc.mainnet.chain.robinhood.com`, `robinhood.drpc.org`): 14,075 bytes of
deployed code, `allPairsLength()` = 156, identical on both.

### Authority chain

V2-style factories have no owner()/proxy admin -- pairs are immutable, the
only privileged surface is fee routing:

| Call | Result (both RPCs identical) |
|---|---|
| `factory.feeTo()` | `0xe4C0172679a2475e7De25bf1B933f774641388f4` (has code, not an EOA) |
| `factory.feeToSetter()` | `0xD09971D8ed6C6a5e57581e90d593ee5B94e348D4` |
| `feeToSetter`: bare EOA | `True` (0 bytecode) |
| `feeToSetter`: `getOwners()`/`getThreshold()` (Safe check) | both revert -- not a Safe |
| `feeToSetter` nonce (`eth_getTransactionCount`) | 20 -- real, actively-used key, not vanity/dormant |

One bare EOA can call `setFeeTo`/`setFeeToSetter` with zero delay. Pools are
not upgradeable and this address does not custody pooled funds, so the blast
radius is fee-routing control, not a rug -- same shape and same scoring
convention as `score_curve_dex()` (Curve DEX, 1/100).

### crossExposureScore finding: this key also sits on PancakeSwap V3's Safe

Before wiring this target into `scripts/lib/signer_overlap.py`, its
`feeToSetter` EOA was grepped against every already-tracked group's
`known_eoa`/`safes` lists in the whole repo -- no textual match. But
`compute_cross_exposure()`'s own live Safe-owner re-derivation (the
authoritative check, not the grep) found a real overlap once both groups
existed together:

| Check | Result (both RPCs identical) |
|---|---|
| PancakeSwap V3's governing Safe `0xfa206DAB60c014bEb6833004D8848910165e6047` `getOwners()` | 6 owners: `0xD09971D8ed6C6a5e57581e90d593ee5B94e348D4`, `0x27cb14cdfA31f6BE86701B429F81f0663fc99006`, `0x08fc23075B0D07132bdEa75864233062E9cc56B2`, `0x897fa2c8A2628b657Cb2b4C093CFCFF86212059B`, `0xb30dF86dE0e1b321451809cCCEbF5651dfF7B900`, `0x7766f6a776c046703263a5C84a5E684aBECD9a75` |
| `getThreshold()` | 3 |
| V2 `feeToSetter` is owner #1 of that Safe | `True` |

The same PancakeSwap-controlled key that alone sets V2's protocol fee is also
one of 3-of-6 required signers on the Safe that owns V3's factory-owner
wrapper. That is a real, live signer overlap between two tracked groups --
`compute_cross_exposure()` correctly drops both to `crossExposureScore = 80`
(`max(0, 100 - 20*1)`, one shared group each).

**PancakeSwap V3 Factory's published `crossExposureScore` was still 100**
(last pushed batch 9, before the V2 factory existed as a tracked target to
overlap with) -- corrected to 80 in the same transaction as this batch's new
target. Its other four fields (`adminKeyScore=65, multisigScore=60,
timelockScore=0, compositeScore=44`) are unchanged; only `crossExposureScore`
moved, and only because a new group now exists to overlap with, not because
anything about V3's own Safe changed.

### Scoring

Wired into `scripts/lib/scorers.py::score_pancakeswap_v2_factory()` (added to
`SIMPLE_SCORERS`) and into `scripts/lib/signer_overlap.py` as group
`pancakeswap_v2`. `_composite(5, 0, 0)` = `floor(0.4*5 + 0.5)` = `floor(2.5)`
= 2. `scripts/lib/tests` (187 tests) and `scripts/tests` (5 tests) both pass
unchanged after this edit (`python3 -m unittest discover`, no live RPC
needed for those).

Pushed to the testnet oracle in one `updateScores()` call covering both
addresses (the new V2 factory and the corrected V3 factory), restricted to
exactly those two -- no other tracked target touched. A run-local helper
outside the repo called this repo's own `score_pancakeswap_v2_factory()` /
`score_pancakeswap_v3_factory()` / `compute_cross_exposure()` live
immediately before sending, and refused to send if the re-derivation differed
from the hand-verified values above. Transaction
`0xeab5d37ea9f16645c2638da19cc36cea332925ba57fb195441b88ca13277ca28`
(testnet block 121239380, status 1). `trackedTargetsCount()` went from 45 to
46; `getScore()` re-reads (5, 0, 0, 100, 80, 2) for the new V2 factory and
(65, 60, 0, 100, 80, 44) for V3.

## Credible leads found but not pursued this run (budget/time)

Not forced to a round number -- these are disclosed as open, not silently
skipped:

- **Spark Liquidity Layer** (`spark-liquidity-layer`, ~$2.5B TVL across all
  chains, DefiLlama adapter gives the Robinhood-side ALM Proxy as
  `0xfD2fD4B046136B540A56C11c75ac679AE7d1dB24`). Confirmed live: 2,260 bytes
  of code, but no EIP-1967 admin slot set and no `owner()` -- this is not a
  standard TransparentUpgradeableProxy or Ownable shape. Spark's ALM
  contracts use a bespoke `rely`/`deny` (`wards` mapping) or a separate
  `ALMController`/rate-limits contract holding the real authority (per
  Spark's own `spark-alm-controller` architecture) -- not traced this pass.
  Needs reading the actual deployed source (Sourcify/Etherscan) before a real
  score can be assigned; scoring it from a guessed interface would be worse
  than leaving it open.
- **Steakhouse Financial** (`steakhouse-financial`, ~$3B TVL across all
  chains). DefiLlama's own adapter module returns 404 at
  `projects/steakhouse/index.js` (the `module` field the protocol list
  reports does not resolve) -- the already-tracked Morpho Steakhouse USDG
  vault's curator IS a Steakhouse Safe, so some of this TVL may already be
  covered by an existing tracked target; whether there are OTHER
  Steakhouse-curated vaults on this chain beyond that one was not
  established this pass.
- **up v3** (`up-v3`) -- same DefiLlama adapter-path 404 already noted as
  open in batch 11, still unresolved.
- **UNCX Network** (V2/V3/V4 token lockers, ~$180M combined TVL) -- a
  fundamentally different authority shape (a locker contract, not a
  protocol with an upgradeable admin) not evaluated against this
  methodology's dimensions this pass.
