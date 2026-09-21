# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 9, plus 1 new target (NOXA Fun Launch Locker)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 9
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(9)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 9

`trackedTargets(9)` = `0x8bcEaA40B9AcdfAedF85AdF4FF01F5Ad6517937f` -- the
on-chain identity of the target scored as "Uniswap V2 Factory feeToSetter".
`trackedTargetsCount()` = 51 going into this run.

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 80 | 100 | 75 | 100 | 100 | 85 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_call`/`eth_getCode` made directly against the factory contract, not
through `score_uniswap_v2_factory_feetosetter()`'s own cached logic.

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (factory) | 13,859 bytes (real deployed code) | identical |
| `feeToSetter()` | `0x2BAD8182C09F50c8318d769245beA52C32Be46CD` | identical |
| `feeTo()` | `0x2aC03e14Cfe755426DaAEe0a4994184Ce81482F8` | identical |
| `allPairsLength()` | 47,242 | identical |
| `eth_getCode` length (feeToSetter) | 0 bytes (bare EOA) | identical |

`feeToSetter()` resolves to the exact same root address already confirmed
controlling the v3 Factory, v4 PoolManager and UniswapX reactor on this
chain -- the same "Arbitrum L1->L2 bridge alias" identity, not a fourth
independent key. Re-verified the alias claim from scratch rather than
trusting the prior correction:

```
computed_alias = (int(UNISWAP_L1_TIMELOCK, 16) + 0x1111...1111) mod 2**160
UNISWAP_L1_TIMELOCK = 0x1a9C8182C09F50c8318d769245bEA52c32BE35BC
computed_alias  = 0x2BAD8182C09F50c8318d769245beA52C32Be46CD
resolved_root   = 0x2BAD8182C09F50c8318d769245beA52C32Be46CD
match: True
```

Independently re-confirmed the real Ethereum L1 Timelock + GovernorBravo
live, on 2 DIFFERENT L1 RPCs than the ones the scorer itself uses
(`ethereum-rpc.publicnode.com` and `1rpc.io/eth`, not just re-running the
scorer's own single L1 RPC):

| Check | L1-A (publicnode) | L1-B (1rpc.io) |
|---|---|---|
| `eth_getCode` length (Timelock) | 6,856 bytes (real deployed code) | identical |
| `delay()` | 172,800s (2.00 days) | identical |
| `admin()` | `0x408ED6354d4973f66138C91495F2f2FCbd8724C3` (GovernorBravo) | identical |
| `admin.quorumVotes()` | 40,000,000 UNI | identical |

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache): **100** -- the `uniswap_stack` group (this
target plus v3 Factory, v4 PoolManager, UniswapX reactor, all sharing the
same L1-alias root) does not share a root signer with any OTHER tracked
group.

`methodologyHash` on-chain independently recomputed as
`keccak256("authority-risk-oracle-v3")` -- matches exactly, not stale.

### Score check

`_score_uniswap_bridge_alias_root()`'s "L1 reconfirmed" branch returns
`(80, 100, 75)` when the alias matches and the L1 Timelock/GovernorBravo
re-confirm live -- both held this run. `_composite(80, 100, 75)` =
`floor(0.4*80 + 0.3*100 + 0.3*75 + 0.5)` = `floor(85.0)` = `85` -- matches
the published `compositeScore` exactly. **No divergence anywhere. No
correction needed for this target; nothing pushed for index 9 itself.**

## Part 2 -- new target search (budget permitted this run)

Rather than re-running the full DefiLlama Robinhood Chain protocol sweep
from scratch again, this run picked up the two credible leads index 8's
own audit explicitly left open rather than touched: `up v3` and `UNCX
Network`. Both were investigated; only one reached a confidently
resolvable conclusion this run.

### UNCX Network -- investigated, still NOT resolved (left open, not fabricated)

Sourced both lockers from `DefiLlama-Adapters/projects/unicrypt-v3/index.js`
and `unicrypt-v4/index.js` (`robinhood` entries): V3 locker
`0xF28704c691290547924e2129D407dA36bda8ce0f`, V4 locker
`0x128A800cBc615cc110Bff16E475865c67631603A`. Confirmed live on both RPCs:
both lockers' `owner()` resolve to the exact SAME real Gnosis Safe
(`0x31c44A17aa2E639B40f33DA805CB1DB55d969693`, 171 bytes, confirmed
`getOwners()`/`getThreshold()` = 2-of-3, owners
`['0x85BD8EBF668e598DC7caF76Fc78cBB644a199579',
'0xcF936235d2f60809D328a7DA6AD630056d477E58',
'0xB3FAbECA3A6dBbc9a88109182d0E333295825385']`, identical on both RPCs).

That much is solid. What blocked scoring it this run: this project's own
discipline (see `score_morpho_blue_singleton()`, `data/scored_targets_2026-09-18-batch12.md`'s
own note on this exact target) requires knowing what the owner role
actually GOVERNS before assigning a formula, not just who holds it. UNCX's
locker source is not on Sourcify for chain 4663 (`repo.sourcify.dev`
returned 404 for both `full_match`/`partial_match`), no public GitHub repo
for the "UNCX_LiquidityLocker" contracts was found, and the chain's own
Blockscout explorer (`explorer.mainnet.chain.robinhood.com`) serves every
route as the same client-rendered shell with no discoverable server-side
API endpoint reachable from a plain HTTP client -- so, unlike NOXA Fun
below, a full bytecode-selector inventory could not be cheaply cross-
checked against 4byte.directory in this pass's time budget (a locker
this size/complexity likely has import libraries inflating the selector
count well past NOXA Fun's 36). Scoring a 2-of-3 Safe on a locker whose own
governed powers are unknown would repeat exactly the mistake this
project's discipline exists to prevent (see `data/maker_checker_2026-09-19-overdue-actions-review.md`
action's fabricated-annex-claim history) -- left open rather than
guessed at. Flagged for a future pass: try Sourcify with the exact
compiler-metadata hash instead of a bare address lookup, or find UNCX's
own verified-source mirror if one exists off GitHub.

### NOXA Fun Launch Locker -- RESOLVED, new target added

Launchpad "Launch Locker" holding single-sided Uniswap V3 LP positions
"locked forever" per its own marketing (DefiLlama `noxa-fun`,
`chainTvls["Robinhood Chain"]` ~$5.27M -- `doublecounted: true` in
DefiLlama's own adapter, disclosed not hidden: it shares the same
underlying Uniswap V3 position manager as UNCX's own V3 locker on this
chain, `0x73991a25C818Bf1f1128dEAaB1492D45638DE0D3`, so this TVL already
counts toward DEX TVL elsewhere). Address `0x7F03effbd7ceB22A3f80Dd468f67eF27826acD85`
sourced from `DefiLlama-Adapters/projects/noxa-fun/index.js` (`robinhood`
entry).

This is a lead index 7's own audit found but deliberately left open
(`data/rotation_audit_2026-09-18-robinhood-chain-index7.md`): `owner()`
confirmed as a bare EOA on both RPCs, but a manual raw-selector scan only
positively identified 5 of ~47 candidate PUSH4 selectors (standard OZ
`Ownable`/NFT-receiver pattern) -- leaving genuinely unknown whether that
key could move the "permanently locked" LP positions, since probing
candidate names (`emergencyWithdraw`, `rescueTokens`, `sweep`) via
`eth_call` can't distinguish "doesn't exist" from "exists, wrong caller".

Resolved properly this run instead of repeating the same guess-and-probe
approach: deterministically extracted **every** PUSH4 selector from the
locker's full runtime bytecode (4,823 bytes total -- 36 selectors found,
the complete set, not a sample) and looked each one up against the public
`4byte.directory` signature database instead of hand-guessing candidate
names:

| Selector | Identified as |
|---|---|
| `0x8da5cb5b` | `owner()` |
| `0x715018a6` | `renounceOwnership()` |
| `0xf2fde38b` | `transferOwnership(address)` |
| `0xc4d66de8` | `initialize(address)` |
| `0x150b7a02` | `onERC721Received(address,address,uint256,bytes)` |
| `0x9a4a3b90` | `setFeeCollector(address,bool)` |
| `0xcb5cd391` | `feeCollectors(address)` |
| `0xe521cb92` | `setProtocolFeeRecipient(address)` |
| `0x64df049e` | `protocolFeeRecipient()` |
| `0xf742919b` | `setProtocolFeeShare(uint256)` |
| `0x960b26a2` | `protocolFeeShare()` |
| `0xa480ca79` | `collectFees(address)` |
| `0xfc6f7865` | `collect((uint256,address,uint128,uint128))` (Uniswap V3 position-manager style fee collection, not principal) |
| `0xc45a0155` | `factory()` |
| `0x9b81a8ba` | `deployerTokens(address,uint256)` |
| remaining 21 | OZ/Solidity built-in errors (`OwnableUnauthorizedAccount`, `OwnableInvalidOwner`, `ReentrancyGuardReentrantCall`, `Panic(uint256)`, `ZeroAddress()`, `NotAuthorized()`) and ERC20 `transfer(address,uint256)` (ambiguous 4byte hash collisions on the remaining few did not resolve to any plausible additional function) |

**No selector in the complete 36-selector inventory matches any
principal-moving function** -- no `withdraw`, `unlock`, `migrate`,
`decreaseLiquidity`, `rescueTokens`, `sweep`, or equivalent. This is a real
negative result now (the full selector set of a small contract,
cross-checked against a real signature database), not the same
inconclusive partial scan as index 7's pass. The only state-changing
surface found is a coherent fee-management module (who collects fees,
where they're sent, what share) -- consistent with, not contradicting, the
project's marketing claim that positions are "locked forever".

Independently corroborated on-chain that the locker is real and live (not
just trusting DefiLlama's TVL figure): `balanceOf(locker)` on the shared
Uniswap V3 position manager returned **60,142** on both RPCs, and the
first several `tokenId`s spot-checked via `positions()` all show real
nonzero `liquidity` (e.g. token 7: `liquidity=36819258015569838458222`),
identical on both RPCs.

`owner()` = `0x7E035Fb048a31e0481b88074557415b1C187242B`, identical on both
RPCs, 0 bytecode (bare EOA) on both. Nonce 45 / balance
0.0488 native token on both RPCs -- a real, actively-used key, not a
dormant/vanity address.

**Not a new one-off number**: scored via the same standalone-bare-EOA
convention already established in this file (`score_curve_dex()`'s own `5
if controller_is_eoa` branch, used when there is no second contract to
corroborate a same-key convergence bonus): `adminKeyScore = 5`,
`multisigScore = 0`, `timelockScore = 0`. Per this project's own existing
convention (see `score_morpho_blue_singleton()`'s identical reasoning),
the root authority MECHANISM is scored as-is regardless of how narrow its
actual operational blast radius turns out to be -- no bespoke discount was
invented for the fee-only scope found above. `compositeScore =
_composite(5, 0, 0) = 2`.

`crossExposureScore` independently re-derived live via
`compute_cross_exposure()` after wiring a new `noxa_fun` group into
`scripts/lib/signer_overlap.py` (`known_eoa:
["0x7E035Fb048a31e0481b88074557415b1C187242B"]`): **100** -- this EOA does
not appear in any other tracked signer-overlap group. Re-checked that this
is the ONLY effect of wiring the new group in: spot-checked 9 pre-existing
groups (`ekubo`, `steakhouse`, `spark_savings` x2, `curve`,
`meridian_perps`, `ramses` x4, `pendle`, `morpho_blue`, `uniswap_stack` x4)
before and after -- every one unchanged (`steakhouse` still 40, matching
the value already corrected in batch 13; everything else still 100).

New scorer `score_noxa_fun_launch_locker()` in `scripts/lib/scorers.py`,
added to `SIMPLE_SCORERS`. New signer-overlap group `noxa_fun` in
`scripts/lib/signer_overlap.py`. 3 new unit tests in
`scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`
(`TestScoreNoxaFunLaunchLocker`: bare-EOA happy path, real-contract-owner
degraded case, unresolved-owner degraded case). Full suite: 464 tests pass
(`python3 -m unittest discover -s scripts/lib/tests`).

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` was
not run this pass (same pre-existing 300-second per-ecosystem timeout gap
for this specific slow ecosystem already documented in `AGENTS.md`'s
`--skip robinhood-chain,tempo` note). Not treated as a passing result and
not substituted with a fabricated one -- the live 2-RPC re-derivation, the
hand-verified expected tuple match immediately before sending (below), and
the full unit-test suite are what this push's correctness actually rests
on, same reasoning as index 7/8's own single-target pushes.

## Push

NOXA Fun's score re-derived live immediately before sending (via
`score_noxa_fun_launch_locker()` + a live `compute_cross_exposure()` call)
and compared against the hand-derived expected tuple `(5, 0, 0, 100,
100)` -- matched (`compositeScore` computed as 2, not hand-typed), so the
send proceeded. Pushed to the testnet oracle as a single-target
`updateScores()` call (same rationale as index 7/8's own single-target
pushes):

Transaction [`0xc93fcb228114021080695da0de95dd69ea7a1dcd7462f71cbbd9bc7e20973e72`](https://explorer.testnet.chain.robinhood.com/tx/0xc93fcb228114021080695da0de95dd69ea7a1dcd7462f71cbbd9bc7e20973e72),
testnet block 121454086, status 1 (success). `trackedTargetsCount()` went
from 51 to 52. `getScore()` re-read after confirmation:

| Target | Result |
|---|---|
| NOXA Fun Launch Locker (Robinhood Chain) | `(5, 0, 0, 100, 100, 2)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before sending, balance confirmed non-zero (~0.00986
testnet ETH) on Robinhood Chain Testnet before sending). Robinhood Chain
**mainnet** was only ever read from, never written to; no non-testnet key
was used, generated, or requested at any point in this run.

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as index 7/8 -- only a full, non-dry-run `update_scores.py`
run writes it). `getScore()` on-chain remains the source of truth per this
project's own documented convention.

## Leads NOT pursued further

`up v3` (dead DefiLlama adapter path, `projects/up-v3/index.js` returns no
resolvable `address`/`module` source for a contract address) remains open,
same status as every prior pass -- no new information found this run to
resolve it, not touched further given the time already spent resolving
NOXA Fun and investigating UNCX Network above.

## Rotation state

`last_audited_target_index` advances from 9 to 10 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(10)` from
scratch.
