# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 13, plus 1 new target (up v3 Factory)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 13
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(13)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 13

`trackedTargets(13)` = `0x322F0929c4625eD5bAd873c95208D54E1c003b2d` -- the
on-chain identity of the target scored as "Robinhood Token: TSLA", one of 5
tokenized-stock beacon-proxy targets in `STOCK_TOKEN_TARGETS`
(`scripts/lib/scorers.py`). `trackedTargetsCount()` = 55 going into this run
(before this run's own push).

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 3 | 0 | 0 | 100 | 100 | 1 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_getCode`/`eth_getStorageAt`/`eth_call` made directly against the TSLA
token proxy and the shared stock-token beacon -- not through
`score_stock_token()`'s own cached logic, and not assumed from the hardcoded
`STOCK_TOKEN_TARGETS` label alone.

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (TSLA token proxy) | 283 bytes | identical |
| EIP-1967 beacon slot (own storage, `keccak256("eip1967.proxy.beacon")-1`, computed live not hardcoded) | resolves to `0xe10b6f6B275de231345c20D14Ab812db62151b00` (the expected shared stock-token beacon) | identical |
| `beacon.hasRole(DEFAULT_ADMIN_ROLE, 0xD6f8378F...5B66d)` | `True` | identical |
| `eth_getCode` length (known admin) | 0 bytes (bare EOA) | identical |
| `eth_getTransactionCount` (known admin nonce) | 2 (a real, previously-used key, not dormant/vanity) | identical |

Confirms the target really is part of the shared beacon-proxy stock-token
family (its own EIP-1967 beacon storage slot read directly, not trusted
from the hardcoded target list) and that the known admin EOA still holds
`DEFAULT_ADMIN_ROLE` on the shared beacon and is still a bare, actively-used
key -- identical on both RPCs, matching every field `score_stock_token()`
itself checks.

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache) on both RPCs: **100**. Grepped
`scripts/lib/signer_overlap.py` for the known admin EOA before trusting
that: it appears exactly once, inside the `stock_tokens` group itself, not
shared with any other tracked group.

`methodologyHash` on-chain independently recomputed as
`keccak256("authority-risk-oracle-v3")` -- matches exactly, not stale.

### Score check

`score_stock_token()`'s branch for "role still held, admin still a bare
EOA" returns `admin_key = 3`. `_composite(3, 0, 0) = floor(0.4*3 + 0.5) =
floor(1.7) = 1` -- matches the published `compositeScore` exactly.
**No divergence in any field for index 13.** Nothing pushed for this index.

Re-ran the actual `score_stock_token()` function itself (not just the raw
primitives above) against both RPCs as a second cross-check: identical
`(3, 0, 0, 100, 1)` output on both, confirming the live code path -- not
just the underlying facts -- reproduces the published score.

## Part 2 -- open leads from prior passes (budget permitted this run)

Two leads carried over open across multiple rotation-audit passes (`up v3`
since index 8; `UNCX Network V4`/`unicrypt-v4` since index 10) were
re-investigated this run, per the task, before searching for anything else
new.

### `up v3` -- RESOLVED, new target added

**up v3** (DefiLlama slug `up-v3`, `https://up33.xyz/`, description "native
(3,3) exchange and liquidity marketplace of Robinhood Chain", twitter
`@uponrh`, `chainTvls["Robinhood Chain"]` ~$8.49M at pull time -- 65 daily
data points back to 2026-07-10) was left open at indices 8, 9, and 12
because `DefiLlama-Adapters/projects/up-v3/index.js` genuinely does not
exist -- every prior pass grepping for a bespoke adapter file came up
empty, and no GitHub org was findable under that exact name either.

Resolved this pass by looking in the right place instead of re-checking the
same dead path a fourth time: DefiLlama's own `api.llama.fi/protocols`
entry for `up-v3` names `tvlCodePath:
"registries/uniswapV3.js"` -- this protocol's TVL is read through the
SHARED Uniswap-V3-fork factory-log-replay registry used by many chains'
protocols at once, not a per-protocol adapter file. Fetched that registry
file fresh from `DefiLlama-Adapters` (not transcribed from memory) and
found its own `up-v3` entry:

```
'up-v3': {
  start: '2026-07-10',
  robinhood: {
    factory: '0x1ac9dB4a2608ba45D6127B1737949b51Bb54B7F3',
    fromBlock: 6184096,
    eventAbi: 'event PoolCreated(address indexed token0, address indexed token1, int24 indexed tickSpacing, address pool)',
    topics: ['0xab0d57f0df537bb25e80245ef7748fa62353808c54d6e528a9dd20887aed9ac2'],
  },
},
```

**Confirmed a genuine Uniswap-V3-fork factory before trusting the registry
label**, live on 2 independent RPCs:

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (factory) | 4,917 bytes | identical |
| `factory.owner()` | `0x0eEA30aBa3f07abFA20E4b544F55e0f917d9DFd8` | identical |
| `eth_getCode` length (owner) | 171 bytes (a real contract, not an EOA) | identical |
| `getOwners()` on owner | `['0xF0300684...C184D', '0x85Fb9f9B...96651', '0xBC6DF475...C47238', '0xD7D59A46...CDC62eb']` | identical |
| `getThreshold()` on owner | 2 | identical |
| Safe `getModulesPaginated()` | `[]` (no modules) | identical |
| Safe guard storage slot | `0x0` (no guard) | identical |

A real, plain 2-of-4 Gnosis Safe, no module, no guard -- an authority root
**independent of every other Uniswap-family target already tracked here**
(v3 Factory, v4 PoolManager, UniswapX, V2 feeToSetter all converge on the
same Arbitrum L1->L2 governance-bridge alias root; this Safe's address and
all 4 of its owners were grepped against every existing
`scripts/lib/signer_overlap.py` group and every hardcoded address in
`scripts/lib/scorers.py` before concluding that -- zero matches anywhere, a
genuinely new authority root, not a duplicate silently re-added).

**Score.** Via this project's existing `_safe_rooted_entry()` /
`_safe_rooted_scores()` convention (the same shared helper already used for
PancakeSwap V3, SushiSwap V3, Symbiosis Portal, and the STRATO bridge
router -- no bespoke discount invented for this being "just a DEX factory"):
`admin_key = 50` (threshold exactly 2), `multisig = min(100, 2*15 + 2*5) =
40`, `timelock_score = 0` (no `TimelockController` and no Safe guard/module
found) -> `compositeScore = _composite(50, 40, 0) = floor(20 + 12 + 0.5) =
32`.

`crossExposureScore` re-derived live via `compute_cross_exposure()` on both
RPCs after wiring a new `up_v3` group into `scripts/lib/signer_overlap.py`
(`safes: ["0x0eEA30aBa3f07abFA20E4b544F55e0f917d9DFd8"]`): **100** on both,
confirming the earlier grep -- no overlap with any existing group, and no
OTHER existing group's score moved as a side effect.

### `UNCX Network V4` / `unicrypt-v4` -- still NOT resolved (left open, not fabricated)

Re-investigated with a broader search than prior passes, not just a repeat
of the same lookup: UNCX's real, official GitHub organization
(`github.com/uncx-network`, the same org whose `liquidity-locker-univ3-contracts`
resolved the V3 locker at index 10) was re-fetched fresh this pass via its
public repo listing -- it publishes exactly 5 repos
(`liquidity-locker-univ2-contracts`, `liquidity-locker-univ3-contracts`,
`token-vesting-contracts`, `raydium-amm-lp-locker`,
`raydium-cp-swap-lp-locker`), still no `v4`/`unicrypt-v4` repo. A broader
GitHub code/repo search for `"unicrypt v4"` returned 0 results; a GitHub
org search for `"unicrypt"` surfaced only unrelated accounts -- `UniCryptoDev`
was checked and ruled out explicitly (its own `blog` field points to
`unicrypto.it`, a same-name-collision, unrelated Italian "UniCrypto"
project, not UNCX Network/Unicrypt Network). Direct source-verification
lookups on the deployed locker address itself
(`0x128A800cBc615cc110Bff16E475865c67631603A`) also came up empty this
pass: Sourcify's `check-all-by-addresses` endpoint and `repo.sourcify.dev`
both 404 for chain 4663, and three plausible Blockscout-style explorer API
paths (`explorer.robinhood.com/api`, `explorer.chain.robinhood.com/api`,
`robinhood.blockscout.com/api`) either failed the TLS handshake or returned
a bare "default backend 404" -- no working, discoverable verification API
found for this chain's explorer. Left open, same status as every prior
pass (indices 8, 9, 10, 12) -- not guessed at, not scored on an unverified
source.

## Push

The new target's tuple was re-derived live immediately before sending
(`score_up_v3_factory()` + a live `compute_cross_exposure()` call) and
compared against a hand-derived expected tuple `(50, 40, 0, 100, 100, 32)`
-- matched (`compositeScore` computed, not hand-typed), so the send
proceeded. Nothing was pushed for index 13 itself (no divergence found).
Pushed to the testnet oracle as a single-target `updateScores()` call (same
rationale as every prior single-new-target push in this rotation -- avoids
a 50min+ full run for 1 target):

Transaction [`0xfaa53839b3f8a0383e71a310c987f2c759d135ae46b740d57e3c9b01f65e3452`](https://explorer.testnet.chain.robinhood.com/tx/0xfaa53839b3f8a0383e71a310c987f2c759d135ae46b740d57e3c9b01f65e3452),
testnet block 121726193, status 1 (success). `trackedTargetsCount()` went
from 55 to 56 (`trackedTargets(55)` now reads the new factory address,
confirmed live after confirmation). `getScore()` re-read after
confirmation:

| Target | Result |
|---|---|
| up v3 Factory (Robinhood Chain) | `(50, 40, 0, 100, 100, 32)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before this note was written, balance confirmed non-zero
(~0.009857 testnet ETH) on Robinhood Chain Testnet). Robinhood Chain
**mainnet** was only ever read from, never written to; no non-testnet key
was used, generated, or requested at any point in this run.
`public_repo_visibility_change_allowed` not touched (remains `false`).

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as every prior single-target push in this rotation -- only
a full, non-dry-run `update_scores.py` run writes it). `getScore()` on-chain
remains the source of truth per this project's own documented convention.

New scorer `score_up_v3_factory()` added to `scripts/lib/scorers.py`,
appended to `SIMPLE_SCORERS`. New signer-overlap group `up_v3` in
`scripts/lib/signer_overlap.py`. 2 new unit tests in
`scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`
(`TestScoreUpV3Factory`: happy-path owner-resolves-to-a-real-Safe case
matching `_safe_rooted_scores()`'s own table, and the
owner-unresolvable-as-a-Safe conservative-degrade case). Full suite
re-run: 531 tests pass (`python3 -m unittest discover -s scripts/lib/tests`).

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` was
not run this pass (same pre-existing ~300-second per-ecosystem timeout gap
for this specific slow ecosystem already documented in `AGENTS.md`; a
`--dry-run --skip-slow` attempt this pass also did not complete in a
reasonable window and was abandoned rather than waited on indefinitely).
Not treated as a passing result and not substituted with a fabricated one
-- the live 2-RPC re-derivation (including re-running the actual
`score_up_v3_factory()`/`score_stock_token()` functions themselves against
both RPCs, not just the raw primitives), the hand-verified expected tuple
match immediately before sending, and the full unit-test suite are what
this push's correctness actually rests on, same reasoning as every prior
single-target push in this rotation.

## Git note

The local clone at `~/Desktop/workspace/authority-risk-oracle` hit
the known dataless-`.git`-pack-file-on-iCloud issue again this run
(`git status` fails with "Operation timed out" reading
`.git/objects/pack/pack-530e331d...pack`). Per this project's own known-issue
handling, no repair was attempted from this clone -- commit/push were done
from a fresh `gh repo clone` in a scratch directory, copying ONLY this
session's own modified/created files (`scripts/lib/scorers.py`,
`scripts/lib/signer_overlap.py`,
`scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`,
`README.md`, and this `.md` file) -- nothing else staged in the shared
local clone by other parallel sessions was picked up or touched.

## Rotation state

`last_audited_target_index` advances from 13 to 14 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(14)` from
scratch.
