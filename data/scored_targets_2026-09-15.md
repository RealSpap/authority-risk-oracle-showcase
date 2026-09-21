# Scored targets - 2026-09-15

First real score pushed through the oracle end-to-end (testnet). Every number below
comes from a direct `eth_call` against Robinhood Chain mainnet, not from Morpho's own
app UI or any secondhand description - the UI's "7-day timelock" claim for this vault
turned out to only be half true, which is exactly why this project always re-derives
authority facts from the chain itself rather than trusting a dashboard's paraphrase.

## Morpho Steakhouse USDG vault (`0xBeEff033F34C046626B8D0A041844C5d1A5409dd`, Robinhood Chain mainnet)

**Method**: `curator()`, `owner()`, `isSentinel(address)`, and `timelock(bytes4)` called
directly against the vault, cross-checked by tracing `owner()` one hop further where
it pointed at another contract rather than an EOA. Morpho Vault V2's real interface
(`IVaultV2.sol`, `morpho-org/vault-v2`) replaces V1.1's single global `timelock()` and
`guardian()` getters with a per-function-selector `timelock(bytes4)` and an
`isSentinel(address)` role check - the naive V1.1-shaped calls (`guardian()`,
`timelock()`) revert on this vault, which is what first flagged that the architecture
differs from what secondhand research assumed.

**Authority chain, as it actually resolves on-chain:**
- `curator()` → `0x9023FBD6A08C666491A2d1648737E400cF42D2Fb`, a Safe with 7 owners,
  threshold **3**.
- `isSentinel(0x5642BCd50fC751fF2d04f155423e4D0E25C2a744)` → `true`. That Safe has
  the *same 7 owners* as the curator Safe, threshold **1** - any single one of those
  seven people alone can act as sentinel.
- `owner()` → `0xCa50D23F1c18C1Dfaff5d3cae3aa4B9dC5C8db73` (a contract, 8,609 bytes
  of code) → that contract's own `owner()` → `0x337feFE49514fb901eB455A501b8Be76CDeF7660`,
  confirmed a **bare EOA** (`eth_getCode` returns empty). Two hops down from the vault,
  a single private key sits at the root.

**Per-function timelocks (`timelock(bytes4)`, seconds):**

| Function | Timelock |
|---|---|
| `setOwner(address)` | **0** |
| `setCurator(address)` | **0** |
| `setIsSentinel(address,bool)` | **0** |
| `decreaseAbsoluteCap(bytes,uint256)` | **0** |
| `addAdapter(address)` | 604,800 (7 days) |
| `removeAdapter(address)` | 604,800 (7 days) |
| `increaseAbsoluteCap(bytes,uint256)` | 604,800 (7 days) |
| `increaseRelativeCap(bytes,uint256)` | 604,800 (7 days) |

**The finding**: the 7-day timelock genuinely exists, but it only covers operational
parameters (adapters, cap increases) - not the vault's own authority. Whoever controls
that root EOA can call `setOwner`, `setCurator`, or `setIsSentinel` and have it take
effect **immediately**, with no delay and no on-chain warning window. A curator/sentinel
layer that looks like real multisig protection sits behind a root that isn't
multisig-protected at all.

**Score pushed** (`updateScore`, tx
[`0x10f06cc4...`](https://explorer.testnet.chain.robinhood.com/tx/0x10f06cc409c34101fd589e605373fcf03c5e447e72e1b8cde0292f9ff545c2a9)):

| Sub-score | Value | Why |
|---|---|---|
| `adminKeyScore` | 10/100 | Root authority resolves to a bare EOA two hops down from the vault |
| `multisigScore` | 35/100 | Curator (3-of-7) and sentinel (1-of-7) are real but modest, and sit behind the EOA-controlled owner rather than replacing it |
| `timelockScore` | 15/100 | The real 7-day delay never covers `setOwner`/`setCurator`/`setIsSentinel` -- the functions that matter most for authority risk |
| `oracleAuthorityScore` | 100/100 | N/A for a lending vault (no oracle-signing role to score) -- not-applicable is scored as full marks rather than penalized, documented here as the project's convention |
| **`compositeScore`** | **19/100** | 0.4×adminKey + 0.3×multisig + 0.3×timelock, `oracleAuthorityScore` excluded from the weighting when not applicable |

Read live via `ExampleConsumer.collateralFactorBps()`: **0** (frozen) -- confirmed by a
direct `eth_call` against the deployed testnet consumer, since 19 is below
`MIN_SAFE_SCORE` (60).

## Not yet scored

Four more real, on-chain-verified targets are queued from earlier research and still
need the same live re-derivation before pushing a score (the Uniswap v4 PoolManager
case in particular looks like it may be a bare-EOA owner with no code at all -- worth
checking before assuming it matches the summary from the earlier research pass):

- Uniswap v3 Factory (`0x1f7d7550B1b028f7571E69A784071F0205FD2EfA`)
- Uniswap v4 PoolManager (`0x8366a39CC670B4001A1121B8F6A443A643e40951`)
- Lighter Escrow (`0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d`)
- Arcus pToken factory (`0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB`)
