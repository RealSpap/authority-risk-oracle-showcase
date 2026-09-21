# Rotation audit (2026-09-18): Robinhood Chain, tracked target index 7, plus 1 new target (Meridian Perps)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 7
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(7)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 7

`trackedTargets(7)` = `0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD` -- the
Curve DEX StableSwap-NG Factory, the on-chain identity of the target scored
as "Curve DEX (StableSwap-NG Factory + fee-receiver)". `trackedTargetsCount()`
= 49 going into this run.

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 2 | 0 | 0 | 100 | 100 | 1 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_call`/`eth_getCode`/`eth_getTransactionCount` made directly (selectors
computed by hand from `admin()`/`owner()`), not through `score_curve_dex()`.

| Check | RPC A result | RPC B result |
|---|---|---|
| `StableSwapNGFactory.admin()` (`0x8271e06E...0E8aD`) | `0xabc336d4C71ad275695744d32DdB1d8266Db1cbF` | identical |
| `fee-receiver/x-gov vault.owner()` (`0x193110Ce...c310D`) | `0xabc336d4C71ad275695744d32DdB1d8266Db1cbF` | identical |
| `factory.admin() == fee-receiver.owner()` | `True` | `True` |
| controller `eth_getCode` | `0x` (0 bytes, bare EOA) | identical |
| controller nonce on Robinhood Chain | `0` | identical |

Also independently re-checked the docstring's supporting claim ("287 tx on
Arbitrum, a real actively-used key, dormant here") rather than trusting it
unread: `eth_getTransactionCount` for `0xabc336d4...Db1cbF` on Arbitrum
mainnet (`arb1.arbitrum.io/rpc`) returns `0x11f` = **287**, an exact match.

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache): **100**, matching -- `0xabc336d4...Db1cbF`
appears in exactly one signer-overlap group (`curve`) in
`scripts/lib/signer_overlap.py`, no shared signer with any other tracked
target.

`methodologyHash` on-chain (`0xf2606acd...4133b8975`) matches
`keccak256("authority-risk-oracle-v3")`, the current `METHODOLOGY_VERSION`
in `scripts/update_scores.py` -- not stale.

### Score check

`_composite(2, 0, 0)` = `floor(0.4*2 + 0.5)` = `floor(1.3)` = `1` --
matches the published `compositeScore` exactly. **No divergence anywhere.
No correction needed for this target; nothing pushed for index 7 itself.**

## Part 2 -- new target search (budget permitted this run)

Pulled the full Robinhood Chain protocol list from DefiLlama
(`api.llama.fi/protocols`, filtered to `chains` containing `"Robinhood
Chain"`): 176 protocols. Cross-referenced against every label already in
`scripts/lib/scorers.py` (49 tracked targets) to find gaps, then fetched
**chain-specific** TVL (`chainTvls["Robinhood Chain"]`, not the
protocol's global TVL figure, which is misleading for multi-chain
protocols -- e.g. Lagoon's globally-reported $151M is **$9** on Robinhood
Chain specifically, Fusion by IPOR's $69M global is **$0** here; both
correctly skipped as not legitimate Robinhood Chain targets rather than
added on the strength of a global number). `UNCX Network` (different
authority shape) and `up v3` (dead DefiLlama adapter path) were left open
in batch 12 for reasons unrelated to TVL and were not re-opened this run.

Checked several mid-TVL untracked candidates
(gami-labs/d2-finance/termmax/native-credit-pool/neutral-trade/steer-protocol/
arcadia-v2/kittenswap-algebra/giga-v3/alandale-v3/ramses-legacy-v2/noxa-fun/
dexfi-aggregator/privacy-cash/kipseli/meridian-perps) for real, chain-specific
TVL. Two stood out and were investigated on-chain:

### Meridian Perps -- RESOLVED, new target added

RWA-focused perps/prediction-market protocol native to Robinhood Chain
(DefiLlama `meridian-perps`, `chainTvls["Robinhood Chain"]` ~$2.29M).
Addresses from DefiLlama-Adapters' own TVL adapter
(`raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/meridian-perps/index.js`,
confirmed live): an `ExchangeGateway` proxy holding user collateral
directly, a `merUSD` collateral token/vault, and a separate ERC-4626 LP
vault that trades from an account on that exchange.

Confirmed live on 2 independent RPCs, all real deployed code (not stubs):

| Address | Role | Bytecode size (both RPCs) |
|---|---|---|
| `0xD540F47F214dC7D6D244E62A6aE7e06B586Ef44A` | ExchangeGateway proxy | 163 bytes |
| `0xad221259d4a1f2d7376dc1012c561bc86640f009` | merUSD | 163 bytes |
| `0x24b84023c8e4Da635be228C380C09bfE5271BF9d` | LP vault (ERC-4626, "MLP") | 18,511 bytes |

The LP vault was checked first and traced no further: `owner()`,
`curator()`, `admin()`, `manager()`, `governance()`, `authority()`,
`vaultManager()`, `operator()`, `feeRecipient()`, `timelock()`,
`DEFAULT_ADMIN_ROLE()`, `hasRole(bytes32,address)` all revert -- it exposes
`asset()`/`name()`/`symbol()`/`decimals()`/`totalAssets()` only (a plain
permissionless ERC-4626 wrapper, `name()` = "Meridian Liquidity Provider").
No admin surface exists on the vault itself to score; the real custodial
authority is entirely in the exchange gateway and the collateral token,
which is what was scored instead.

`ExchangeGateway.owner()` and `merUSD.owner()` both resolve directly
(neither reverts -- confirms plain OpenZeppelin `Ownable`, not
`AccessControl`) to the exact **same** address on both RPCs:
`0x39C647fdd8524c69be3E05A754bD63E02b019D75` -- `eth_getCode` = `0x` (bare
EOA) on both, nonce **84** on Robinhood Chain on both (a real,
actively-used key, not dormant). EIP-1967 admin slot on the exchange proxy
is zero (no separate ProxyAdmin, same "owner() gates its own upgrade
directly" pattern already seen on Pendle's `MarketFactoryV6` and Spark's
`ALMProxy`). No TimelockController found gating either contract.

**This is the exact same "two independent contracts, one converging bare
EOA" pattern already tracked for Curve DEX (Part 1 above)** -- scored
identically, not a new number invented for this target: `admin_key = 2`
(the "same_key" branch), `multisig = 0`, `timelock = 0` ->
`compositeScore = 1`.

New scorer: `score_meridian_exchangegateway()` in `scripts/lib/scorers.py`,
added to `SIMPLE_SCORERS`. New signer-overlap group `meridian_perps` in
`scripts/lib/signer_overlap.py` (`known_eoa`:
`0x39C647fdd8524c69be3E05A754bD63E02b019D75`, no other tracked target
shares it -- `compute_cross_exposure()` re-run live confirms
`crossExposureScore = 100`, no ripple effect on any of the other 49
pre-existing targets). 4 new unit tests added to
`scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`
(`TestScoreMeridianExchangeGateway`, mirroring `TestScoreCurveDex`'s own 4
branches). Full suite: 457 tests pass (`python3 -m unittest discover -s
scripts/lib/tests`).

### Noxa Fun -- lead found, NOT resolved this run (left open, not fabricated)

Launchpad with a "Launch Locker" holding single-sided Uniswap V3 LP
positions "locked forever" per its own marketing (DefiLlama `noxa-fun`,
`chainTvls["Robinhood Chain"]` ~$5.3M -- higher than Meridian's, but
`doublecounted: true` in DefiLlama's own adapter, i.e. not new user funds
distinct from what's already counted as DEX TVL elsewhere). Adapter:
`DefiLlama-Adapters/projects/noxa-fun/index.js`, `robinhood` entry, locker
`0x7F03effbd7ceB22A3f80Dd468f67eF27826acD85`.

Confirmed live (both RPCs): `locker.owner()` resolves to a bare EOA
(`0x7E035Fb048a31e0481b88074557415b1C187242B`, 0 bytecode). A raw PUSH4
bytecode scan of the locker (47 selectors) positively matches
`owner()`/`renounceOwnership()`/`transferOwnership(address)`/
`initialize(address)`/`onERC721Received(...)` -- a standard OZ `Ownable`
proxy pattern -- but the remaining ~35 selectors were **not** identified
within this pass's time budget, so it is **not confirmed** whether the
owner key can actually move the "permanently locked" NFT LP positions (a
rescue/emergency-withdraw function) or whether `owner()` only gates
unrelated configuration. Calling candidate state-changing selectors
(`emergencyWithdraw`, `rescueTokens`, `sweep`, etc.) via `eth_call` from a
non-owner sender reverts regardless of whether the function exists (an
`onlyOwner` check fails before ABI dispatch either way), so that approach
cannot distinguish "doesn't exist" from "exists, wrong caller" -- explicitly
not treated as a negative result.

**Left open rather than scored on an unconfirmed guess** -- consistent with
how `Spark Liquidity Layer` and `Steakhouse Financial` were left open in
batch 12 until fully traced in batch 13. Flagged for a future rotation
pass: get the locker's verified source (Sourcify/the project's own repo, if
public) instead of a raw selector scan, to resolve the actual blast radius
of that owner key before assigning a score.

## Push

Meridian Perps' score re-derived live immediately before sending (via
`score_meridian_exchangegateway()` + a live `compute_cross_exposure()` call)
and compared against the hand-verified expected tuple `(2, 0, 0, 100, 100,
1)` -- matched, so the send proceeded. Pushed to the testnet oracle as a
single-target `updateScores()` call (the same "few-target manual push"
pattern already used for prior single/few-target additions in this
project, not a full `update_scores.py` run -- that script's own docstring
notes a complete run, including its 4 full-chain-history log-replay
scorers, has been clocked exceeding 50 minutes, and would re-verify 49
already-audited targets this rotation pass had no reason to touch):

Transaction [`0x14b0de5328b4c9ee6eb39081f9d41919eac61e679489775a80d71b316c25631e`](https://explorer.testnet.chain.robinhood.com/tx/0x14b0de5328b4c9ee6eb39081f9d41919eac61e679489775a80d71b316c25631e),
testnet block 121413937, status 1 (success). `trackedTargetsCount()` went
from 49 to 50. `getScore()` re-read after confirmation:

| Target | Result |
|---|---|
| Meridian Perps (ExchangeGateway) | `(2, 0, 0, 100, 100, 1)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before sending, balance confirmed non-zero on Robinhood
Chain Testnet before sending). Robinhood Chain **mainnet** was only ever
read from, never written to; no non-testnet key was used or requested.

`api/scores.json` was **not** regenerated by this push (it is only written
by a full, non-dry-run `update_scores.py` run, which this manual
single-target push deliberately did not do) -- it stays at its existing
42-entry snapshot (already behind the on-chain 50 from prior batches too;
a known, pre-existing gap in this project's own tooling, not introduced
this run). `getScore()` on-chain remains the source of truth per this
project's own documented convention.

## Leads NOT pursued further

Noxa Fun (see above -- genuinely unresolved, not a time trade-off against a
clear answer). `up v3` and `UNCX Network`, flagged open in batch 12 for
unrelated reasons, remain open -- not touched this run.

## Rotation state

`last_audited_target_index` advances from 7 to 8 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(8)` from
scratch.
