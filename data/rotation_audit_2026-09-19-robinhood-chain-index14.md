# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 14, plus 1 new target (Alandale V3 Factory)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 14
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(14)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 14

`trackedTargets(14)` = `0x12f190a9F9d7D37a250758b26824B97CE941bF54` -- the
on-chain identity of the target scored as "Robinhood Token: AMZN", the 2nd of
5 tokenized-stock beacon-proxy targets in `STOCK_TOKEN_TARGETS`
(`scripts/lib/scorers.py`). `trackedTargetsCount()` = 56 going into this run
(before this run's own push).

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 3 | 0 | 0 | 100 | 100 | 1 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_getCode`/`eth_getStorageAt`/`eth_call` made directly against the AMZN
token proxy and the shared stock-token beacon -- not through
`score_stock_token()`'s own cached logic, and not assumed from the hardcoded
`STOCK_TOKEN_TARGETS` label alone (that function never reads the target's own
storage at all -- it goes straight to the shared beacon address for every
token -- so the target's own beacon slot is the one fact only this audit
checks).

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (AMZN token proxy) | 283 bytes | identical |
| EIP-1967 beacon slot (own storage, `keccak256("eip1967.proxy.beacon")-1` = `0xa3f0ad74...3d50`, computed live not hardcoded) | resolves to `0xe10b6f6B275de231345c20D14Ab812db62151b00` (the expected shared stock-token beacon) | identical |
| `eth_getCode` length (beacon) | 2,332 bytes | identical |
| `beacon.hasRole(DEFAULT_ADMIN_ROLE, 0xD6f8378F...5B66d)` | `True` | identical |
| `eth_getCode` length (known admin) | 0 bytes (bare EOA) | identical |
| `eth_getTransactionCount` (known admin nonce) | 2 (a real, previously-used key, not dormant/vanity) | identical |

Confirms the target really is part of the shared beacon-proxy stock-token
family and that the known admin EOA still holds `DEFAULT_ADMIN_ROLE` on the
shared beacon and is still a bare, actively-used key -- identical on both
RPCs, and byte-for-byte the same facts already confirmed for index 13 (TSLA)
on the same beacon.

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache) on both RPCs: **100**. The known admin EOA
appears exactly once in `scripts/lib/signer_overlap.py` (inside the
`stock_tokens` group itself), not shared with any other tracked group.

`methodologyHash` on-chain (`0xf2606acd...8975`) independently recomputed as
`keccak256("authority-risk-oracle-v3")` -- matches exactly, not stale.

### Score check

`score_stock_token()`'s branch for "role still held, admin still a bare
EOA" returns `admin_key = 3`. `_composite(3, 0, 0) = floor(0.4*3 + 0.5) =
floor(1.7) = 1` -- matches the published `compositeScore` exactly.
**No divergence in any field for index 14.** Nothing pushed for this index.

Re-ran the actual `score_stock_token()` function itself (not just the raw
primitives above) against both RPCs as a second cross-check: identical
`(3, 0, 0, 100, 1)` output on both, confirming the live code path -- not
just the underlying facts -- reproduces the published score.

## Part 2 -- new-target search (budget permitted this run)

### How candidates were found

DefiLlama's `api.llama.fi/protocols`, filtered on protocols with a
Robinhood-labelled `chainTvls` key: 216 entries at pull time (includes the
`-staking`/`-borrowed`/`-pool2` variants). The entries above ~$1M were matched
by name and address against `scripts/lib/scorers.py` first (not from memory),
and the ones already tracked set aside; the long tail below that was not
walked entry by entry. For DEX-type entries, the factory addresses came from
DefiLlama-Adapters' shared registries (`registries/uniswapV3.js`,
`registries/uniswapV2.js`, `registries/traderJoeV2.js`), each fetched fresh
-- the same "look in the shared registry, not for a per-protocol adapter"
lesson recorded at index 13. Ten candidate factories were then probed on 2
independent RPCs for `owner()`/`feeToSetter()`/`admin()`/`pauser()`/... and the
EIP-1967 slots, before anything was scored.

| Lead | DefiLlama TVL (Robinhood Chain) | Outcome |
|---|---|---|
| Lighter Robinhood Perps | $101.2M | **Duplicate** of the already-tracked zkLighter escrow (index 3), see below |
| **Alandale V3** (Algebra factory `0x16494A80...D82F8`) | $1.99M listed, **~$1.14M** once one wrong price is corrected | **ADDED**, see Part 3 |
| up v2 (`0xFA5429AE...bc28`) | $1.16M | **Duplicate authority root** of the already-tracked up v3, see below |
| Ramses DLMM (`0xdcD5F776...AbAc`) / Ramses Legacy V2 (`0x43B2Bf9f...8e66`) | $815k / $145k | **Duplicate authority root**: `owner()` / `accessHub()` = `0x83341F89...9CecF`, the Ramses CL V2 AccessHub already tracked |
| GIGA V3 (`0xEce6eCd6...E20B`) | $1.24M | **Left open**, source unverifiable, see below |
| UNCX Network V4 (`0x128A800c...603A`) | $829k | **Still open**, one new fact, see below |
| StonkBrokers | $1.85M (plus $13.0M of its own token in staking, not counted) | **Left open**: 3 contracts share ONE bare-EOA owner, source not public, see below |
| DexFi Aggregator / Accountable | $1.45M / $51k (plus $2.2M borrowed) | Seen, not investigated: per-user / per-strategy vault factories deployed across many chains, authority is per vault, not one root |
| Raphael CL / Raphael AMM, BrownFi V3, GIGA V2, Alandale V2 | $246k / $213k / $352k / $323k / $51k | Not pursued (each under the ~$600k floor of the smallest prior addition, T3tris) |

### Lighter Robinhood Perps -- duplicate of index 3, not a new target

DefiLlama slug `lighter-robinhood-perps` ($101.2M), methodology "Counts
tokens deposited by users into the Lighter ZK rollup contract". Its adapter
source could NOT be read: the API's `module` field says `lighter-rh/index.js`,
but the full DefiLlama-Adapters git tree (fetched fresh) contains no such
path -- its only `lighter` entry is `projects/lighter/index.js`, which exports
`arbitrum` only. So the duplicate ruling rests on on-chain evidence, not on
reading the adapter: the already-tracked zkLighter escrow proxy
(`0x94bAB969...AFfF9d`, index 3) holds, at one pinned block (67,242,464) and
identical on both RPCs, balances that match DefiLlama's own token list for this
entry. 17 of its 29 listed tokens were checked: 9 equal to the last decimal
shown (PONS 1,423,418.22; USAR 9,923.87; SLV 2,599.06; SPCX 1,360.81; TSLA
1,310.00; GOOGL 896.10; AAPL 846.41; MSFT 526.48; MU 454.26), 7 within 1%
(USDG 83,868,278.83 on-chain vs 83,887,161.35 listed, ratio 0.9998; NVDA,
BABA, PLTR, AMZN, SPY, SNDK), and 1 (USO) 11.6% higher on-chain than the
snapshot, consistent with a deposit made after the snapshot. The other 12
listed tokens were not checked (not resolvable from the token list in hand).
Same authority, same contract, no new root: not added.

### up v2 -- one Safe governs the whole stack, already tracked as up v3

up v2 is up's ve(3,3) V2 exchange. Every authority getter across its stack
resolves, identically on 2 RPCs, to `0x0eEA30aBa3f07abFA20E4b544F55e0f917d9DFd8`
-- the same 2-of-4 Safe that is `owner()` of the already-tracked up v3 Factory
(index 55):

| Contract | Getter | Result |
|---|---|---|
| V2 PoolFactory `0xFA5429AE...` | `pauser()`, `feeManager()` | that Safe |
| Voter `0x7F749fDD...` | `governor()`, `emergencyCouncil()`, `epochGovernor()` | that Safe |
| VotingEscrow `0x5d321dE3...` | `team()` | that Safe |
| Minter `0x912EC7A9...` | `team()` (`pendingTeam()` = zero) | that Safe |
| FactoryRegistry `0xbBb4FbD1...` | `owner()` | that Safe |

Not a separate authority root, so not added as its own target; a comment on
the `up_v3` group in `scripts/lib/signer_overlap.py` now records that any
future up v2 address belongs in that same group. Worth knowing for anyone
reading the up v3 score (32/100): that Safe controls up's emissions, voting and
factory pause/fee levers too, not only the v3 factory.

### GIGA V3 -- left open, not scored

`factory.owner()` = `0x4a9cEF84...9163D`, a 1,074-byte
`TransparentUpgradeableProxy` (not a Safe), over a 24,364-byte implementation
with roughly 250 selectors -- a bespoke "apex controller" (farm registration,
emission control, fee receivers, `setCLGlobalProtocolFee`, `setTreasury`,
`stopAllEmissions`, `sweepUnallocated`, `rescueFeeReceiverToken`,
`payReward`...). Its ProxyAdmin owner and its sole `DEFAULT_ADMIN_ROLE` holder
are both `0x72f4DF35...cd4A6`, a 2-of-3 Safe -- but `FEE_OPERATOR` (2 bare
EOAs, nonces 7,545 and 127), `EMISSION_OPERATOR` (2 bare EOAs and 1 contract)
and `VAULT_OPERATOR` (1 bare EOA at nonce 1 and 1 contract) are held outside
that Safe, and which of those roles can move what is unknowable from
unverified bytecode of that size. Left open rather than scored on a guess (same
discipline as the UNCX V4 case, and as `AGENTS.md` prescribes: a getter that
resolves is not evidence of real gating). All facts identical on both RPCs.

### StonkBrokers -- left open, not scored

DefiLlama slug `stonkbrokers` ($1.85M main TVL on Robinhood Chain; a further
$13.0M "staking" is its own STONKBROKER token in an escrow, outside the
criterion used throughout this rotation). Its adapter was read directly
(`DefiLlama-Adapters/projects/stonkbrokers/index.js`, `doublecounted: true`):
TVL is the WETH side of LP position NFTs locked in two "Safety Deposit Box"
lockers -- the Uniswap V3 box locker `0xFc96CF67...1223` (7,886 bytes) and the
up. DEX box locker `0xc1AfA59e...a076` (14,400 bytes) -- plus the Smart LP
vault registry `0xE8749183...0146` (1,457 bytes). On 2 RPCs, identically,
`owner()` of all three is one address, `0xb668382cF44038a3E8140E789060F6A809787CDa`,
a bare EOA (0 bytecode) at nonce 33,067, with no proxy (EIP-1967 slots zero).
That is the standalone-bare-EOA shape scored 5/0/0 (composite 2) for NOXA Fun
and T3tris -- but not scored here, because the same test those two passed was
not passed: the lockers' visible owner-gated surface is only OpenZeppelin
Ownable plus `setFeeExempt` / `setProtocolFeeRecipient`, yet 16 (V3 locker) and
20 (up locker) of their 43 / 71 PUSH4 selectors are identified by no signature
database (some will be custom errors, some may be functions), and whether
`releasePosition`, `decreaseLockedLiquidity` or `collectFees` can be triggered
by the owner on other people's locks cannot be settled from bytecode. The
project's GitHub organization (`Clutch-L4bs`, whose twitter handle
`ClutchMarkets` matches DefiLlama's listing) publishes 4 repositories -- the
token, a launchpad UI mock, Solana programs, a perps DEX -- and none for the
lockers. Left open rather than scored on a guess; the TVL (WETH side of NFT
positions) was not independently recomputed either.

### UNCX Network V4 -- still open; one new fact for whoever picks it up

Not resolved. New this pass: the earlier passes' explorer hostnames were
wrong. `explorer.mainnet.chain.robinhood.com` (the mainnet counterpart of the
testnet explorer already used in this repo, and of the RPC naming) answers with
a 301 to **`robinhoodchain.blockscout.com`** -- not `robinhood.blockscout.com`
or `explorer.chain.robinhood.com`, which were the guesses that failed at index
13. That real host serves Blockscout's v2 API, but sits behind a Cloudflare
managed challenge ("Just a moment...", HTTP 403 to a non-browser client).
Solving or evading a bot challenge is out of scope for this project, so the
V4 locker's verified source (if it has one there) remains unreadable
programmatically. A human with a normal browser can read it in seconds at
`https://robinhoodchain.blockscout.com/address/0x128A800cBc615cc110Bff16E475865c67631603A?tab=contract`
-- that is the one manual step that would unblock this lead.

## Part 3 -- new target: Alandale V3 Factory

**Alandale V3** (`alandale.xyz`, twitter `@alandalexyz`, DefiLlama slug
`alandale-v3`): "a ve(3,3) DEX on Robinhood Chain", Robinhood-Chain-only.
Factory address from DefiLlama-Adapters' `registries/uniswapV3.js`, entry
`'alandale'` (`robinhood.factory: 0x16494A80E08Bcb9285D87b67149d7b01774D82F8`,
`fromBlock: 27941500`, `isAlgebra: true`), fetched fresh.

### TVL -- corrected, and why the DefiLlama figure is not relied on

DefiLlama lists ~$1.99M ($1,987,912). Recomputing it from the chain:

| Step | Result |
|---|---|
| Pools enumerated from the factory's own `Pool(address,address,address)` events, block 27,941,500 to tip | 59 pools (`rpc.mainnet.chain.robinhood.com`, 8 `eth_getLogs` calls of 5M blocks) |
| Every pool re-read via `factory.poolByPair(token0, token1)` + `eth_getCode`, on BOTH RPCs | 59/59 correct on both |
| Token balances of all 59 pools summed at one pinned block (67,244,938), both RPCs | identical on all 47 tokens |
| Priced with coins.llama.fi (DefiLlama's own price feed) | $1,990,743, within 0.15% of DefiLlama's figure |
| Same, but USAR at its on-chain price instead of coins.llama.fi's | **$1,136,756** |
| DexScreener's own liquidity sum, independent of both (58 of the 59 pools known to it) | **$1,135,966**, 0.07% from the line above |

The whole $0.85M gap is one token, USAR. coins.llama.fi lists it at $757.70
(confidence 0.9) -- within 0.4% of SPY's own price ($760.72), which looks like a
price-mapping error -- while the on-chain Uniswap USAR/USDG pool
(`0x04391780...25C4`) reports, via `slot0()` and identically on both RPCs,
1 USDG = 0.064156 USAR, i.e. 1 USAR ~ $15.59, and DexScreener quotes $15.53 to
$16.26 across 5 pairs on Uniswap, Alandale and Ramses. 1,150.75 USAR sit in
Alandale's pools: $871,923 at the DefiLlama price, $17,937 at the on-chain one.
The first agreement above (my recomputation vs DefiLlama) is therefore NOT an
independent confirmation -- both use the same wrong price; the second one
(DexScreener) is. Honest headline: **~$1.14M TVL specific to Robinhood Chain**,
on 2 independent sources. Limitation: the pool list rests on one RPC's log scan
(`robinhood.drpc.org` rejected `eth_getLogs` at every range tried, 10k to 2M
blocks, HTTP 400), and one pool (`0xB2b48A76...bC8D`) is unknown to
DexScreener; neither is enough to move the figure materially.

Side observation for anyone screening this chain by DefiLlama TVL: any figure
that includes USAR is inflated by that same factor. Lighter Robinhood Perps'
9,923.87 USAR are $7.52M at DefiLlama's price versus ~$155k at the on-chain one
(no effect on the duplicate ruling above, but a caution on trusting `chainTvls`
totals without a price sanity check).

### Identity of the contract

The factory is a proxy over an 8,149-byte implementation. Compared against the
official `cryptoalgebra/Algebra` repository (GitHub-verified organization, `blog`
= algebra.finance), `IAlgebraFactory.sol` selectors plus OpenZeppelin
Ownable2Step/AccessControlEnumerable's own:

| Release compared | Reference selectors found in the deployed implementation |
|---|---|
| `integral-v1.0` (and `dev`, `beam-dex-integral-v1.0`, `lst-plugin-integral-v1.0`, identical interface) | **35 / 35** |
| `integral-v1.1` | 34 / 39 |
| `integral-v1.2`, `1.2.1`, `1.2.2`, `1.2.3`, `1.3`, `master` | 33 / 39 |

So the base is Algebra Integral v1.0, but the deployment is **not stock**: it
carries 10 extra function selectors -- `initialize(address)`, `createPlugin`,
`createVaultForPool`, `getVaultForPool`, `deploy`, `isPublicPoolCreationMode`,
`setIsPublicPoolCreationMode`, `POOLS_CREATOR_ROLE`, plus 2 that no signature
database resolves (`0x5a05180f`, `0x7965db0b` -- the same two also appear in
GIGA V3's controller above) -- plus solc's own `Panic(uint256)`. Its verified
source was not reachable (Sourcify 404, and the real explorer is behind the
Cloudflare challenge noted above), so **the score rests only on the
ownership/upgrade chain, never on assumptions about what those extras do**.

### Authority chain (identical on both RPCs)

| Fact | Result |
|---|---|
| Factory proxy | 2,210 bytes; runtime embeds OpenZeppelin v4's `TransparentUpgradeableProxy: admin cannot fallback to proxy target`, `ERC1967: new admin is the zero address`, `ERC1967: new implementation is not a contract`, both EIP-1967 slot constants and a `DELEGATECALL` -- an OZ v4-style transparent proxy whose EIP-1967 admin slot is the only upgrade path |
| EIP-1967 admin slot | `0x95c0bE4a...2f71`, 1,690 bytes; carries all 8 standard OZ v4 `ProxyAdmin` selectors (`upgrade`, `upgradeAndCall`, `changeProxyAdmin`, `getProxyAdmin`, `getProxyImplementation`, `owner`, `transferOwnership`, `renounceOwnership`, each verified by hashing the signature) |
| EIP-1967 implementation slot | `0x8C3bbDAB...8684`, 8,149 bytes |
| `ProxyAdmin.owner()` | `0x2a04c1D26767dD30f62712DCFCF1222f733A2B0E` |
| `factory.owner()` / `pendingOwner()` | the same address / zero |
| `DEFAULT_ADMIN_ROLE` holders (`getRoleMemberCount`) | 1, the same address |
| `POOLS_CREATOR` holders | 3: that Safe, one of its signers, and one further bare EOA (nonce 173); pool-creation permission only |
| The Safe | v1.4.1, **3-of-5**, nonce 132, no module (`getModulesPaginated` empty), guard slot zero |
| Its 5 owners | all bare EOAs (0 bytecode); nonces 241, 234, 28, 100, 147 -- real, actively used keys |
| TimelockController anywhere in the chain | none found |

One plain 3-of-5 Safe holds the factory's ownership (fee/plugin/vault-routing
levers over every pool) AND, through the ProxyAdmin, the right to replace the
factory's logic outright. It does not custody user funds (pools are separate
contracts), so the `shared_custody_and_upgrade` discount is not applied, same
as PancakeSwap V3, SushiSwap V3 and up v3.

**No overlap with any tracked target.** The factory, ProxyAdmin, Safe and all
5 signers were grepped against every address in this repo -- zero matches -- and
`compute_cross_exposure()` re-derived live on both RPCs after wiring the new
`alandale_v3` group (it re-reads every other tracked Safe's owners on-chain, so
it catches overlaps a grep of hardcoded lists cannot): `crossExposureScore`
**100**, and the same 10 pre-existing entries as before stay the only ones
below 100 (Steakhouse family 40s, Arcus 80s, PancakeSwap V2/V3 80s) -- no
other group moved.

### Score

Via the existing `_safe_rooted_entry()` / `_safe_rooted_scores()` convention
(the same proxy-admin-hop shape as `score_symbiosis_portal()`, scored on the
upgrade authority with a WARNING if it ever diverges from the factory owner):
`admin_key = 65` (threshold 3), `multisig = min(100, 3*15 + 2*5) = 55`,
`timelock_score = 0` -> `compositeScore = floor(0.4*65 + 0.3*55 + 0.3*0 + 0.5)
= floor(43.0) = 43`. Tuple `(65, 55, 0, 100, 100, 43)`, hand-derived first, then
matched by the live scorer on both RPCs before the push.

### Scope, stated rather than implied

This scores the CL factory's owner and upgrade authority only. Alandale's
ve(3,3) layer (Voter, Minter, VotingEscrow, gauges), each pool's plugin, and the
separate ~$51k Alandale V2 classic-pool factory (its own proxy) were **not**
traced this pass.

## Push

Re-derived live on both read RPCs immediately before sending, compared against
the hand-derived tuple `(65, 55, 0, 100, 100, 43)` -- matched (the script
refuses on any disagreement or mismatch), and asserted: oracle RPC
`eth_chainId` = 46630 (Robinhood Chain **Testnet**), `hasRole(UPDATER_ROLE, ...)`
= `True`, updater balance non-zero (~0.009857 testnet ETH), factory not already
tracked. Nothing was pushed for index 14 itself (no divergence found). Pushed to
the testnet oracle as a single-target `updateScores()` call (same rationale as
every prior single-new-target push in this rotation -- avoids a 50min+ full run
for 1 target):

Transaction [`0x2aad6395bf90681108a03eb80928461a806bc19044939c59146591a71755c813`](https://explorer.testnet.chain.robinhood.com/tx/0x2aad6395bf90681108a03eb80928461a806bc19044939c59146591a71755c813),
testnet block 121750260, status 1 (success). `trackedTargetsCount()` went from
56 to 57 (`trackedTargets(56)` now reads the new factory address, confirmed
live after confirmation). `getScore()` re-read after confirmation:

| Target | Result |
|---|---|
| Alandale V3 Factory (Robinhood Chain) | `(65, 55, 0, 100, 100, 43)`, `methodologyHash` = `keccak256("authority-risk-oracle-v3")` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` throwaway updater key). Robinhood Chain
**mainnet** was only ever read from, never written to; no non-testnet key was
used, generated, or requested at any point in this run.
`public_repo_visibility_change_allowed` not touched (remains `false`).

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as every prior single-target push in this rotation -- only a
full, non-dry-run `update_scores.py` run writes it). `getScore()` on-chain
remains the source of truth per this project's own documented convention.

New scorer `score_alandale_v3_factory()` added to `scripts/lib/scorers.py`,
appended to `SIMPLE_SCORERS`. New signer-overlap group `alandale_v3` in
`scripts/lib/signer_overlap.py`, plus a comment on `up_v3` recording the up v2
finding. 3 new unit tests in
`scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`
(`TestScoreAlandaleV3Factory`: same-Safe happy path asserting the hand-derived
`(65, 55, 0)` / composite 43, the divergent-owner WARNING branch scored on the
upgrade authority, and the unresolved-ProxyAdmin-owner conservative-degrade
branch that must NOT silently fall back to the stronger-looking factory
owner). Full suite re-run in the fresh clone: 759 tests pass, and 788 after the final
rebase onto the latest `origin/main` (`python3 -m unittest discover -s
scripts/lib/tests`; the 29 extra are other sessions' tests).

A full-set live sensor did run this time, in the background, without hitting
the timeout that made the previous pass abandon it:
`python3 scripts/update_scores.py --dry-run --skip-slow` against the same two
endpoints the real updater uses (no transaction, no `api/scores.json` write,
exit 0). It scored 45 of the 57 tracked targets -- including the new Alandale V3
Factory at 43/100, crossExposure 100/100, through `score_all()` itself, not just
my one-off script -- and **all 45 match the published on-chain composite and
crossExposure exactly, 0 divergences**. The 12 it does not cover are exactly the
targets of the four documented full-history log-replay scorers that
`--skip-slow` omits by design (6 rollup-L1-authority targets, 4 Ramses CL V2
targets, Fables PoolRegistry, Beefy SPY-WETH vault), so this is a fast partial
sensor, not a complete run, and is reported as such.

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` DID run
this time, after rebasing onto `origin/main` (which now carries the upstream
fix `a84b1f6` giving this ecosystem a 3600-second default timeout instead of
the flat 300 seconds that made every earlier pass here record it as a
pre-existing gap): **57 targets checked, 0 problems, OVERALL: PASS**, wall-clock
about 26 minutes, every target `ok` including the new Alandale V3 Factory and
the 12 targets of the four slow full-history scorers that `--skip-slow` omits.
It is a schema/shape check of the full `score_all()` output, not a factual
re-derivation -- that is what the live 2-RPC checks above are for -- and is
reported as exactly that. The live 2-RPC re-derivation (including re-running
the actual `score_stock_token()` and `score_alandale_v3_factory()` functions
themselves against both RPCs, not just the raw primitives), the hand-verified
expected tuple match immediately before sending, the partial full-set dry run,
this full validator run and the unit-test suite are what this push's
correctness rests on.

## Git note

The local clone at `~/Desktop/workspace/authority-risk-oracle` hit the
known dataless-`.git`-pack-file-on-iCloud issue again this run (`git status`
fails with "Operation timed out" reading `.git/objects/pack/pack-530e331d...pack`).
Per this project's own known-issue handling, no repair was attempted from that
clone. Every edit, test run and the commit were done in a fresh `gh repo clone`
in a scratch directory (so the edits are based on the real `origin/main`, not on
the shared clone's possibly-stale copy), touching ONLY this pass's own files
(`scripts/lib/scorers.py`, `scripts/lib/signer_overlap.py`,
`scripts/lib/tests/test_robinhood_simple_and_saferooted_scorers.py`, `README.md`,
and this `.md` file) -- nothing staged in the shared local clone by other
parallel sessions was picked up or touched.

## Rotation state

`last_audited_target_index` advances from 14 to 15 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside this
repo). Next rotation audit should re-derive `trackedTargets(15)` from scratch
(the 3rd of the 5 stock-token targets, Robinhood Token: PLTR, if the on-chain
order still holds -- read it live, don't assume).
