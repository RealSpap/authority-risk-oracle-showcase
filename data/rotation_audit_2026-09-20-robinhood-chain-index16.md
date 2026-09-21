# Rotation audit (2026-09-20): Robinhood Chain, tracked target index 16, plus 4 new targets

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 16
going into this run. Same discipline as every prior rotation audit: the target
is read live from the testnet oracle (`trackedTargets(16)`), every authority
fact is re-derived from scratch on two independent mainnet RPCs (never re-read
from `scripts/lib/scorers.py`'s own logic), then compared with `getScore()`.
`trackedTargetsCount()` is 58 going in and is still 58 after this run, because
nothing was pushed: the 4 new targets are prepared for Spap to broadcast (rule
of 2026-09-20 -- the agent prepares, the user pushes).

## Part 0 -- CORRECTION of this same run's first attempt

This file supersedes the numbers produced by the first, rejected attempt at
this audit (2026-09-20, same rotation index, never committed). **This is a
correction of figures published inside this run, not a new finding.** Two
separate mistakes there cancelled each other out and manufactured a false
agreement:

1. **`getScore()` was decoded with the wrong ABI.** `getScore(address)`
   returns the `AuthorityScore` **struct** (`src/AuthorityRiskOracle.sol`
   l.25 and l.119), not a `uint256`. Decoded as `outputs: uint256` it yields
   the first 32-byte word of the ABI-encoded struct, which is
   `adminKeyScore = 3` -- never `compositeScore`. The first attempt therefore
   reported "published composite = 3". Re-read here with the real tuple ABI,
   the published entry is:

   ```
   cast call 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \
     'getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))' \
     0xE0444EF8BF4eD74f74FD73686e2ddF4C1c5591E8 \
     --rpc-url https://rpc.testnet.chain.robinhood.com/rpc
   -> (3, 0, 0, 100, 100, 1, 1789864661, 0xf2606acd...8975)
   ```

   The published `compositeScore` is **1**. `api/scores.json` l.397 already
   said so (`compositeScore` 1, `l1CappedComposite` 1); only the on-chain
   read was misdecoded.

2. **The composite was recomputed with a formula that does not exist in this
   project.** The first attempt used `max(adminKey, multisig, timelock)`.
   `METHODOLOGY.md` l.39 defines
   `compositeScore = floor(0.4*adminKey + 0.3*multisig + 0.3*timelock + 0.5)`
   (`scripts/lib/scorers.py::_composite()`, exact integer arithmetic). For
   this target that is `floor(0.4*3 + 0.5) = 1`.

Both errors are fixed below. The *conclusion* of the first attempt ("no
divergence, nothing to push") turns out to be right, but it was right by
accident, not established -- and the numbers it printed were wrong on both
sides of the comparison. The independent verifier who rejected that attempt
found this; the authority facts it reported (beacon, `hasRole`, bare EOA,
nonce 2) were correct and are re-derived again here anyway.

## Part 1 -- rotation audit, index 16

`trackedTargets(16)` = `0xE0444EF8BF4eD74f74FD73686e2ddF4C1c5591E8`, read
live -- **not** assumed from `STOCK_TOKEN_TARGETS`. Confirmed on chain to be
the NFLX token: `symbol()` = `"NFLX"`, `name()` = `"Netflix • Robinhood
Token"`, identical on both mainnet RPCs. It is the 4th of the 5
tokenized-stock beacon proxies.

| | adminKey | multisig | timelock | oracleAuthority | crossExposure | **composite** | lastUpdated |
|---|---|---|---|---|---|---|---|
| Published (`getScore`, real tuple ABI) | 3 | 0 | 0 | 100 | 100 | **1** | 1789864661 |
| Re-derived this run | 3 | 0 | 0 | 100 | 100 | **1** | (not pushed) |

**No divergence in any field. Nothing pushed for this index.**
`methodologyHash` on chain = `keccak256("authority-risk-oracle-v3")` =
`0xf2606acddcba40931e80d6e2a5a45ff06a0788ef4db7a53b60e19de4133b8975`,
recomputed live.

### What was re-derived, from zero

Mainnet reads only (chain 4663), RPC A = `rpc.mainnet.chain.robinhood.com`,
RPC B = `robinhood.drpc.org`. The re-derivation script is
`work/rederive_index16.py` in this run's scratchpad: it imports **no** scoring
logic from this repo, reads every fact itself, transcribes the
`METHODOLOGY.md` formula by hand, and exits non-zero on any divergence.

| Check | Result (A and B identical) |
|---|---|
| Proxy runtime code | 283 bytes, keccak `0x6c1fdd40002dcb440c7fff6a84171404d279ccb057803b65826f7546acd65630` |
| EIP-1967 **beacon** slot, recomputed live as `keccak256("eip1967.proxy.beacon")-1` = `0xa3f0ad74...3d50` | `0xe10b6f6B275de231345c20D14Ab812db62151b00` |
| EIP-1967 implementation and admin slots | both zero -- pure beacon proxy, the token holds no authority of its own |
| Beacon | 2,332 bytes, `implementation()` = `0xb35490d6f9163DE4F80d88dc75c3516eb64C5aE2`; `owner()` reverts (not Ownable); `getRoleMemberCount()` reverts (not AccessControlEnumerable) |
| `beacon.hasRole(DEFAULT_ADMIN_ROLE, 0xD6f8378F...5B66d)` | `true` |
| Admin `0xD6f8378F8e440c65F8382F5f2728c78DfD55B66d` | **0 bytes of code** -- so a bare EOA, and specifically *not* an EIP-7702 delegation, which would leave 23 bytes beginning `0xef0100`. Nonce 2 |
| Is that root a Safe? | `getOwners()` / `getThreshold()` return empty. (A call to a codeless address *succeeds* with empty returndata rather than reverting -- the first version of the check treated "no revert" as "getter exists" and wrongly classified the bare EOA as both a Safe and a timelock. Fixed: only non-empty returndata counts) |
| Is there a timelock anywhere on the path? | `getMinDelay()` / `delay()` empty on the root, revert on the beacon -- none |

Derivation from those facts, per `METHODOLOGY.md`: bare-EOA root -> `adminKey`
in the documented 2-10 band, 3 (the value the 4 sibling stock tokens carry); no
multisig layer -> `multisig` 0; no enforced delay -> `timelock` 0; the token
reports no price or state to anyone -> `oracleAuthority` 100 (not applicable).
`floor(0.4*3 + 0.3*0 + 0.3*0 + 0.5) = 1`.

`crossExposureScore` re-derived live via `compute_cross_exposure()` on both
RPCs: 100 for NFLX on both, 58 targets computed, 13 of them below 100,
no difference between the two RPCs. That 100 is not an oversight even though
NFLX shares its root with 4 other tracked targets: the penalty in
`signer_overlap.py` counts *other groups* sharing a signer, and all 5 stock
tokens are one group (`stock_tokens`).

### Aggravating context, looked for rather than assumed

One key, `0xD6f8378F...5B66d`, holds `DEFAULT_ADMIN_ROLE` on a beacon that is
shared by the whole tokenized-stock family, so this is not a per-token risk.
The index-15 audit established the fuller shape (13 bare EOAs holding the
granular `BEACON_UPGRADER` / `PAUSER` / `BLOCKER` / `MINTER` / `BURNER` roles
on that same beacon, `getRoleAdmin()` = `DEFAULT_ADMIN_ROLE` for all 13, no
`RoleAdminChanged` ever), which is re-cited here rather than re-replayed --
the full-history log replay behind it was done once and its conclusion is
bounded by the admin's nonce, still 2 on both RPCs this run. Mitigating: that
admin cannot call `upgradeTo` or `blockAccounts` directly; it needs one
`grantRole` transaction first. That does not change the score, because the
whole tree is rooted in it and there is no Safe and no delay anywhere in it.

## Part 2 -- new-target search (budget 10, 4 retained)

Discipline: chain-specific TVL from DefiLlama's `chainTvls["Robinhood Chain"]`
key (never the protocol-wide total), addresses from a primary source
(`DefiLlama-Adapters`), every authority fact confirmed on 2 independent RPCs,
and the owner-gated surface established by read-only `eth_call` simulation
rather than by assuming what a getter implies.

178 protocols carry a Robinhood-labelled `chainTvls` key
(`api.llama.fi/protocols`, pulled fresh this run). Everything above $200k was
matched by name against `scripts/`, `data/`, `README.md` and `chains/`.

### UNCX Network V4 -- OPEN SINCE INDEX 8, RESOLVED

`0x128A800cBc615cc110Bff16E475865c67631603A`, $831,087 specific to Robinhood
Chain (ETH $465k + WETH $365k + USDG $1k -- **no USAR**, so the index-14
mispricing does not inflate it; the protocol-wide figure across its 7 chains
is ~$2.4M and is *not* what is used here).

**The blocker four passes hit is real and is not claimed to be solved.** The
V4 locker's verified source is only readable through
`robinhoodchain.blockscout.com`, behind a Cloudflare managed challenge this
project does not bypass, and the official `uncx-network` GitHub org (profile
`blog` = `https://uncx.network/`, the same identity check used at index 10)
publishes 5 repositories -- univ2, univ3, two Raydium, vesting -- and **no
Uniswap-V4 locker**, re-checked this run. What changed is that the source is
not needed: the authority root is readable directly on chain, and
`score_uncx_v3_locker()` / `score_morpho_blue_singleton()` already set the
convention of scoring the root mechanism.

| Check | Result (both RPCs identical) |
|---|---|
| Address source | `DefiLlama-Adapters/projects/unicrypt-v4/index.js`, `robinhood` entry, `lockers[0]`, `fromBlock` 20591817 |
| Primary source cross-confirmed **by the contract itself** | `locker.positionManager()` = `0x58daec3116aae6D93017bAAea7749052E8a04fA7` = exactly the adapter's `nftAddress`. `poolManager()` = `0x8366a39C...0951` |
| `owner()` | `0x31c44A17aa2E639B40f33DA805CB1DB55d969693` -- **the same Safe that already roots the tracked UNCX V3 locker** |
| That Safe | real Gnosis Safe `VERSION()` 1.4.1, singleton `0x29fcb43b...c762`, **2-of-3**, nonce 7, `getModulesPaginated` empty, guard slot zero |
| Owner-gated surface, from a 120-selector PUSH4 inventory of the runtime + simulation | `adminRescueTokens(address,address,uint256)`, `setMigrator(address)`, `setHookWhitelist(address,bool)`, `setFees`/`setFlatFee`/`setFeeAddresses`, `setBaseURI`. From an arbitrary address each reverts `OwnableUnauthorizedAccount`; from the Safe, `setMigrator` and `setHookWhitelist` pass and `adminRescueTokens` gets **past** the ownership gate (it reverts later on the fake token, `SafeERC20FailedOperation`) |
| `MIGRATOR()` | zero address -- the migrate path is configured but **unarmed** today |

**Score 50 / 35 / 0 / 100, crossExposure 100, composite 31** -- identical to
what the already-published V3 locker carries (read back live this run for
`0xF28704c6...ce0f`: `(50, 35, 0, 100, 100, 31)`), because it is literally the
same root Safe. It joins the **existing** `uncx_v3_locker` overlap group, which
is what that group's own comment asked for ("if/when it is scored, add its
address to this SAME group rather than a new one"). Consequence, verified: no
crossExposureScore anywhere moves, because the penalty counts other *groups*.

Stated limit: 54 of the 120 selectors resolve to no 4byte signature and were
not brute-forced, so that inventory is a **lower** bound on the owner's powers.
The score rests on the root, which is why the gap does not move it. The TVL was
not independently recomputed on chain this pass.

### Orvex -- never examined before, 3 targets, and the notable finding of this run

DefiLlama slug `orvex`, `chains == ['Robinhood Chain']` (it exists nowhere
else), **$389,945**: USDG $214k, WETH $57k, NVDA $33k, SPY $31k, USDE $21k,
rest small. No USAR in the basket. That is below the ~$600k floor earlier
passes used; it is picked up here because the rotation brief listed Orvex
explicitly as one of the never-examined candidates. Addresses from
`DefiLlama-Adapters/projects/orvex/index.js`, which names `docs.orvex.fi` as
the contract source and states chainId 4663 explicitly. TVL **not**
independently recomputed on chain this pass.

Two roots, both re-read live on both RPCs, identical on both:

| Role | Address | What it is |
|---|---|---|
| operational owner of the V2 factory **and** of the V4 Vault | `0x3b2b572C56dD96B351ceB95c53e7EdB97BF42F14` | **bare EOA**, 0 bytecode (not a 7702 delegation), nonce 454 |
| owner of the V4 PoolManager, owner of the V2 ProxyAdmin, and `pendingOwner` of the V4 Vault | `0x9DB42D3BDA1525963db3B2372C4DAABaf0491A53` | real Gnosis Safe 1.3.0, singleton `0x3e5c6364...d36e`, **3-of-7**, nonce 59, no module, guard slot zero |

**Orvex V4 Vault `0xFe7E25dE55e5cBbEcCcb661F3679F873f72B9b0D` -- the finding.**
This is the contract that actually holds every Orvex V4 concentrated-liquidity
token balance. Its owner-gated surface is **not** fee-only: a 33-selector
PUSH4 inventory shows `registerApp(address)` alongside `mint`/`burn`/`take`/
`transfer` on vault balances, i.e. a registered "app" is precisely the thing
allowed to move vault reserves (`isAppRegistered(0xd01C774d...4032)`, the V4
PoolManager, is true today). Simulated read-only on **both** RPCs, identically:
`registerApp(0x1111...1111)` reverts `OwnableUnauthorizedAccount` from an
arbitrary address, reverts `OwnableUnauthorizedAccount` **from the 3-of-7
Safe**, and **passes from the bare EOA**. One key, no delay, no second
signature, can authorise an arbitrary contract against the vault's reserves.

Because that surface is principal-moving rather than fee-only, the 5/0/0
convention used for NOXA Fun and T3tris does not apply; `METHODOLOGY.md` puts a
bare EOA in the 2-10 band and this entry takes the bottom of it, 2 -- the same
value `score_curve_dex()` and `score_saffron_vault_factory()` use for their
worst single-key shape. **2 / 0 / 0 / 100, crossExposure 100, composite 1.**

*Mitigating, dated, and worth re-reading next pass:* `pendingOwner()` is the
3-of-7 Safe. This is OpenZeppelin `Ownable2Step` and `acceptOwnership()` has
**not** been called -- the transfer is offered, not completed, as of
2026-09-20, which is exactly why the Safe still reverts on `registerApp`. If it
is accepted, this target re-scores 65/65/0 (composite 46) with no code change;
the scorer detects it on its own and a unit test pins that behaviour.

**Orvex V2 `PairFactoryUpgradeable` `0x5c98b2d892b37c9a1D3b69472bdDc172A64CdC09`.**
A Solidly/Velodrome-fork factory, and the only Orvex surface that is a proxy:
EIP-1967 implementation `0x950f3baE...ea72` (20,341 bytes), EIP-1967 admin
`0x2DFa221c...0006`, a 1,683-byte OpenZeppelin ProxyAdmin whose `owner()` is
the 3-of-7 Safe. `factory.owner()` is the bare EOA.

This is a **split root**, and it is the first one this repo has actually met:
`score_alandale_v3_factory()` (via `_safe_rooted_entry`) scores the *upgrade*
authority and appends a WARNING when the two diverge, but on Alandale they did
not diverge, so that branch has never been exercised. Scoring the Safe here
would publish 65/65/0 (composite 46) for a contract one single key can
reconfigure today, which is not what `adminKeyScore` is defined to answer.
**Deliberate, stated deviation: this entry scores the weaker of the two roots**,
the bare EOA, and records the Safe upgrade path in the notes rather than in the
number. An 83-selector inventory of the implementation plus simulation gives
the EOA's surface as `setPause(bool)`, `setFee(bool,uint256)`,
`setReferralFee`, `setDibs`, `setFeeManager` -- `setPause(true)` reverts from an
arbitrary address and passes from the EOA, on both RPCs; `isPaused()` is false
today. No `withdraw`/`rescue`/`sweep`/`migrate` selector exists on the factory
and Solidly pairs hold their own reserves, so this is the fee-and-pause-only
shape: **5 / 0 / 0 / 100, crossExposure 100, composite 2.** Halting every
pair's swaps is real; seizure of principal is not shown. 3 of the 83 selectors
are unidentified and were not brute-forced -- a lower bound again.

**Orvex V4 CL PoolManager `0xd01C774d4A66408326Bc65728Ac5Ae5aAf004032`.**
20,885 bytes, not a proxy (all three EIP-1967 slots zero on both RPCs).
`owner()` = the 3-of-7 Safe. **65 / 65 / 0 / 100, crossExposure 100,
composite 46.** Scope stated rather than implied: the PoolManager is the
accounting surface, the tokens sit in the Vault above, so a consumer reading
*this* entry for custody risk is reading the wrong one of the two. That is why
both are tracked separately instead of collapsed into one "Orvex V4" score, and
the caveat is carried in the entry's own notes.

### Cross-exposure side effects -- checked, none

`compute_cross_exposure()` re-run live before and after the change (the
before-run on a `git stash`ed tree, same RPC, same session): 58 targets before,
62 after, **0 of the 58 existing targets changed value**, 0 removed, and all 4
new ones at 100. This has moved other groups by accident in past passes, so it
is verified rather than assumed.

### Candidates seen and NOT retained, stated so they are not mistaken for rejected

| Candidate | Robinhood-Chain TVL | Why not |
|---|---|---|
| StonkBrokers (`0xFc96CF67...1223`, `0xc1AfA59e...a076`, `0xE8749183...0146`) | $1.76M | **Still open**, for the same reason index 14 gave. Re-confirmed this run on both RPCs: all three have `owner()` = `0xb668382cF44038a3E8140E789060F6A809787CDa`, a bare EOA now at nonce 33,255 (was 33,067 at index 14 -- the key is active), `protocolFeeRecipient()` = `0x55642A3F...692c` on the two lockers. The blocker is unchanged: 16 of 43 and 20 of 71 selectors unidentified on the lockers, no public source (`Clutch-L4bs` publishes the token, a launchpad UI mock, Solana programs and a perps DEX, none of them the lockers), so whether the owner can touch other people's locks is not settled. Not scored on a guess |
| GIGA V3 (`giga-dex-cl`), Gami Labs, Kittenswap Algebra, Meridian Predict, up v3 | $1.14M / $593k / $376k / $375k / $7.79M | No adapter file at `projects/<module>/index.js` on `DefiLlama-Adapters` `main` (404), so no primary-source address. A `master`-branch retry could not run (the sandbox lost `curl` inside that loop; not retried, low value). Left open, not rejected |
| STONX (`0xD18685A5...9953`, `0xda38ac72...f068`) | $1.16M | A Ve33 layer over Ekubo Core, which is already tracked. `Ve33Positions.owner()` = `0xcd87828F...EAAb`, a 2,011-byte contract whose own `owner()` is `0x1E0EF416...E9CC` -- one more hop than this run had budget for. Genuinely open |
| Snuggle / MaxFi, NOXA Fun, Ekubo Core | $7.3M / $4.9M / $1.7M | Already tracked (their adapter addresses resolve to entries already in `scorers.py`) |
| Everything else above $200k | -- | Already tracked or already examined in an earlier pass |

Budget spent: 4 of a possible 10. The reserve of candidates with both a
primary-source address and a resolvable root is what ran out, not the budget.

## Part 3 -- push, prepared not sent

**Nothing was broadcast by this pass, on any chain.** Per the rule of
2026-09-20, the push is prepared and left for Spap:

`scripts/prepared_pushes/2026-09-20-robinhood-index16-4-new-targets.py`

It refuses to send unless the oracle RPC reports chain id **46630** (a mainnet
chain id aborts), the signer holds `UPDATER_ROLE`, all 4 scores re-derive
identically on both mainnet read RPCs *and* match the table above, and none of
the 4 targets is already tracked; afterwards it reads every pushed score back
with the correct struct ABI and compares field by field. The dry run was
executed this pass and sent nothing: chain id 46630 confirmed,
`trackedTargetsCount()` 58, all 8 live re-derivations agreeing, none of the 4
already tracked, and the exact `updateScores` calldata printed.

Read-only on the testnet oracle: `UPDATER_ROLE` =
`keccak256("UPDATER_ROLE")` = `0x73e573f9...5dab`, and
`hasRole(UPDATER_ROLE, 0x646968c33d8F6D5A343B68A6F8b1cE52f13414BA)` = `true`,
balance 0.00984 testnet ETH, nonce 30. No `RoleRevoked` event has ever been
emitted by the oracle. **No key file was opened at any point** -- role
membership was established with `hasRole()`, which is what that check is for.

Index 16 itself is deliberately **not** in the batch: its score matches what is
published, so there is nothing to correct on chain.

## Part 4 -- code, tests, limits

* `scripts/lib/scorers.py`: `score_uncx_v4_locker()`,
  `score_orvex_v2_pair_factory()`, `score_orvex_v4_pool_manager()`,
  `score_orvex_v4_vault()`, all four registered in `SIMPLE_SCORERS`.
* `scripts/lib/signer_overlap.py`: `0x128A800c...603A` appended to the
  **existing** `uncx_v3_locker` group; new `orvex` group holding all 3 Orvex
  targets, the shared bare EOA and the shared Safe.
* `scripts/lib/tests/test_robinhood_uncx_v4_and_orvex.py`: 23 tests covering
  every branch of the four scorers (Safe root, threshold sensitivity,
  unresolvable owner, adapter drift warning, split-root deviation, the
  principal-moving 2-vs-5 distinction, the offered-but-unaccepted Ownable2Step
  transfer, the automatic re-score once it is accepted) plus the wiring and
  overlap-group invariants.
* Full suite: `python3 -m unittest discover -s scripts/lib/tests` -> **1730
  tests, OK, 3 skipped, 2 expected failures**.

Limits, stated rather than glossed:

* No TVL was independently recomputed on chain this pass, for any of the 4 new
  targets. The DefiLlama chain-specific figures are reported as such, with the
  USAR check done (none of the 4 baskets contains it) but no second-source
  reconciliation of the totals.
* Both selector inventories are lower bounds: 54 of 120 (UNCX V4) and 3 of 83
  (Orvex V2) selectors resolve to no 4byte signature and were not brute-forced.
* No verified source was read for any of the 4 -- the Cloudflare challenge on
  `robinhoodchain.blockscout.com` is unchanged and was not bypassed. Every
  claim about what an owner can do rests on the deployed bytecode's selectors
  plus read-only `eth_call` simulation, never on source.
* The adversarial-review step of `AGENTS.md` was done as a self-refutation pass
  by the same agent, not by a separate refuting agent; this run had no way to
  spawn one.
* 6 addresses already in `signer_overlap.GROUPS` before this change are stored
  in a casing `to_checksum_address()` does not produce (`arcus_perps_bridgevault`,
  `t3tris_wbtc_vault`, `chainlink_admin` x2, `fables` x2). All 6 are the same
  20 bytes and every comparison in that module lowercases first, so nothing is
  broken. Deliberately left untouched -- they belong to other audits.
