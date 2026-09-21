# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 10, plus 1 new target (UNCX Network V3 Locker)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 10
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(10)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 10

`trackedTargets(10)` = `0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB` -- the
on-chain identity of the target scored as "Arcus pToken factory".
`trackedTargetsCount()` = 52 going into this run.

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 65 | 55 | 0 | 100 | 100 | 43 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_call`/`eth_getCode`/`eth_getStorageAt` made directly against the
factory, the beacon, and the two live pTokens -- not through
`score_arcus_ptoken()`'s own cached logic.

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (factory) | 109 bytes | identical |
| `eth_getCode` length (beacon, `0x33846348...73A76`) | 590 bytes | identical |
| `beacon.owner()` | `0x81B80499C396a9931b9e44953425a82C1b2541bd` | identical |
| `eth_getCode` length (beacon owner) | 171 bytes (real contract, not an EOA) | identical |
| `getOwners()` on beacon owner | `['0x4f1d777b...05ebe2', '0x57D32496...4f5b78', '0xEAb7F386...f989d7']` | identical |
| `getThreshold()` on beacon owner | 2 | identical |
| Safe `getModulesPaginated()` | `[]` (no modules) | identical |
| Safe guard storage slot | `0x0` (no guard) | identical |
| factory `getRoleMemberCount(DEFAULT_ADMIN_ROLE)` | 1 | identical |
| factory `getRoleMember(DEFAULT_ADMIN_ROLE, 0)` | `0x81B80499C396a9931b9e44953425a82C1b2541bd` (same Safe) | identical |
| pBTC EIP-1967 beacon slot | `0x33846348...73A76` (matches the beacon above) | identical |
| pBTC3x EIP-1967 beacon slot | `0x33846348...73A76` (matches the beacon above) | identical |

Confirms both halves of the original manual finding
(`data/scored_targets_2026-09-15-batch2.md`) independently, from scratch:
the beacon's `owner()` **and** the factory's own AccessControl
`DEFAULT_ADMIN_ROLE` resolve to the exact same real, active 2-of-3 Gnosis
Safe, and both live pTokens (pBTC, pBTC3x) point at the identical beacon via
their own EIP-1967 beacon slot -- one Safe, one `upgradeTo()` call, rewrites
the implementation shared by the factory and every pToken issued through it.

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache): **100** on both RPCs -- the `arcus` group's
Safe does not share a signer with any other tracked group.

`methodologyHash` on-chain independently recomputed as
`keccak256("authority-risk-oracle-v3")` -- matches exactly, not stale.

### Score check

`score_arcus_ptoken()`'s "Safe found" branch returns `admin_key=65`,
`multisig = threshold*25+5 = 2*25+5 = 55` when the beacon owner resolves to
a Gnosis Safe. `_composite(65, 55, 0) = floor(0.4*65 + 0.3*55 + 0.5) =
floor(43.0) = 43` -- matches the published `compositeScore` exactly. **No
divergence anywhere. No correction needed for this target; nothing pushed
for index 10 itself.**

## Part 2 -- new target search (budget permitted this run)

Per the task, resumed the UNCX Network lead left open at index 9 rather than
re-running the full DefiLlama sweep from scratch again.

### UNCX Network V3 Locker -- RESOLVED, new target added

Index 9's audit (`data/rotation_audit_2026-09-19-robinhood-chain-index9.md`)
had already confirmed, live on 2 RPCs, that both of UNCX's Robinhood Chain
lockers (`unicrypt-v3`/`unicrypt-v4` DefiLlama adapters) are owned by the
same real 2-of-3 Gnosis Safe (`0x31c44A17aa2E639B40f33DA805CB1DB55d969693`,
owners `['0x85BD8EBF...199579', '0xcF936235...d477E58', '0xB3FAbECA...825385']`)
but left it unscored: Sourcify returned 404 for chain 4663, no public GitHub
repo was found for "UNCX_LiquidityLocker" at the time, and the chain's own
Blockscout explorer serves only a client-rendered shell -- scoring a Safe
whose actual governed powers were unknown would have repeated exactly the
mistake this project's discipline exists to prevent (maker-checker action
#7's fabricated annex claim).

This pass searched again with a different approach (the org's own site
rather than a bare address lookup on a source-verification service) and
found UNCX Network's real, official GitHub organization:
`github.com/uncx-network` -- confirmed as their own account (not a
similarly-named impostor) via the org's public profile `blog` field, which
points to `https://uncx.network/`, their real product site. It publishes 5
public repos, including `liquidity-locker-univ3-contracts`
(`contracts/UNCX_LiquidityLocker_UniV3.sol`).

**Verified this is genuinely the deployed source**, not just an
org-name match: extracted every candidate PUSH4 selector from the V3
locker's runtime bytecode (`0xF28704c691290547924e2129D407dA36bda8ce0f`) via
raw opcode disassembly -- 62 candidates, identical bytecode (23,902 bytes) on
both RPCs -- and independently computed the 4-byte selectors for the 26
functions/errors named in the GitHub source. **25 of 26 matched exactly**:

| Selector | Signature |
|---|---|
| `0xab9ae180` | `adminRefundEth(uint256,address)` |
| `0x280f3867` | `adminRefundERC20(address,address,uint256)` |
| `0x23cf3118` | `setMigrator(address)` |
| `0x8b52a6ee` | `setMigrateInContract(address)` |
| `0x5a04fb69` | `transferLockOwnership(uint256,address)` |
| `0xb25128db` | `acceptLockOwnership(uint256,address)` |
| `0xac4521c6` | `setAdditionalCollector(uint256,address)` |
| `0xb707a288` | `setCollectAddress(uint256,address)` |
| `0xb2fb30cb` | `relock(uint256,uint256)` |
| `0xd68f4dd1` | `getLock(uint256)` |
| `0x489c18b0` | `getLocksLength()` |
| `0x611f6fe6` | `getNumUserLocks(address)` |
| `0x9f185a0b` | `getUserLockAtIndex(address,uint256)` |
| `0x9b774840` | `nftPositionManagerIsAllowed(address)` |
| `0x544534e7` | `allowNftPositionManager(address)` |
| `0xfae2e648` | `setFeeResolver(address)` |
| `0xd5fdb732` | `removeFee(string)` |
| `0x83fb69ad` | `getFeeOptionAtIndex(uint256)` |
| `0x038975a1` | `getFeeOptionLength()` |
| `0xef248944` | `setUCF(uint256,uint256)` |
| `0x260e12b0` | `collect(uint256,address,uint128,uint128)` |
| `0x454b0608` | `migrate(uint256)` |
| `0x8da5cb5b` | `owner()` |
| `0xf2fde38b` | `transferOwnership(address)` |
| `0x715018a6` | `renounceOwnership()` |

(`withdraw(uint256,address)`'s own selector, `0x00f714ce`, was not found
among the 62 candidates extracted this way -- the one signature out of 26
that did not match. No alternative explanation was verified for this single
miss rather than guessed at; disclosed as a real gap, not smoothed over. 25
of 26 direct matches, all of them from real, distinctive, multi-parameter
signatures rather than short/common ones, is still strong confirmation this
is the same source and not a coincidence -- but this is a real, disclosed
gap, not a clean 26/26.)

**What the source shows the Safe can and cannot do**, read directly rather
than assumed:

- `withdraw()` and `migrate()` both gate on `isLockAdmin()`
  (`require(userLock.owner == msg.sender)`) -- the individual lock's own
  owner, **not** the contract's `onlyOwner`. The Safe cannot pull any user's
  locked LP position directly.
- `adminRefundERC20()`/`adminRefundEth()` are `onlyOwner`, but the source's
  own comment states plainly: *"Since this contract is only for locking NFT
  liquidity, this allows removal of ERC20 tokens and cannot remove locked
  NFT liquidity"* -- the NFT's `safeTransferFrom` interface differs from
  `IERC20.transfer`, so attempting to pass a `tokenId` through
  `adminRefundERC20` reverts.
- The Safe's real `onlyOwner` powers: fee configuration
  (`setFeeParams`/`addOrEditFee`/`removeFee`/`setFeeResolver`), which NFT
  position managers are `allow`ed, `setUCF` (can only **decrease** a lock's
  fee-tracking value, per its own `require(_ucf < l.ucf)`), and
  `setMigrator`/`setMigrateInContract` -- these point a *future*
  `migrate()` call at an address of the Safe's choosing. Because `migrate()`
  itself still requires the individual lock owner to call it, this is a
  real but indirect rug vector (a malicious `MIGRATOR` a lock owner is
  tricked into using), not a direct seizure of anyone's position.

Both lockers confirmed non-upgradeable (EIP-1967 implementation/admin slots
both zero on both RPCs) -- a plain `Ownable` contract, not a proxy.

**UNCX's second locker (`unicrypt-v4`, `0x128A800cBc615cc110Bff16E475865c67631603A`)
is explicitly NOT scored this pass.** It shares the identical owner Safe
(confirmed live again this run), but its bytecode is a different, larger
contract -- 120 candidate PUSH4 selectors vs. the V3 locker's 62, and only 9
of the same 26 known signatures were found in it. This is UNCX's own next
locker generation (the DefiLlama adapter name "v4" refers to UNCX's product
versioning, not Uniswap V4), and its own source was not located this pass.
Left open rather than guessed at, for a future rotation pass.

### Score

Root authority mechanism: a confirmed 2-of-3 Gnosis Safe, no timelock.
Scored using the threshold-aware `adminKeyScore` convention introduced for
`score_morpho_blue_singleton()` (65 for threshold >= 3, 50 for exactly
2-of-N, 10 unresolved) rather than the older, coarser flat branch in
`score_arcus_ptoken()` (which does not vary by threshold) -- both formulas
exist in `scripts/lib/scorers.py` today; this new scorer deliberately uses
the more recent, threshold-aware one, matching the most rigorous existing
precedent for "a Safe found as owner of a non-upgradeable contract."

`adminKeyScore = 50`, `multisigScore = min(100, 2*15 + 1*5) = 35`,
`timelockScore = 0` -> `compositeScore = _composite(50, 35, 0) = 31`. No
bespoke discount for the bounded (fee/config-only, principal-excluded)
scope found above -- same convention as NOXA Fun and Morpho Blue Singleton:
the root authority mechanism is scored as-is.

`crossExposureScore` independently re-derived live via
`compute_cross_exposure()` after wiring a new `uncx_v3_locker` group into
`scripts/lib/signer_overlap.py` (`safes:
["0x31c44A17aa2E639B40f33DA805CB1DB55d969693"]`): **100** on both RPCs.
Confirmed this Safe and its 3 owners do not already appear anywhere else in
`signer_overlap.py` before wiring the group in (grepped the file for all 4
addresses -- no prior match).

New scorer `score_uncx_v3_locker()` in `scripts/lib/scorers.py`, added to
`SIMPLE_SCORERS`. New signer-overlap group `uncx_v3_locker` in
`scripts/lib/signer_overlap.py`. 3 new unit tests in
`scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`
(`TestScoreUncxV3Locker`: 2-of-3 happy path, larger-Safe threshold/owner
scaling, unresolved-owner degraded case). Full suite: 467 tests pass
(`python3 -m unittest discover -s scripts/lib/tests`).

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` was
not run this pass (same pre-existing 300-second per-ecosystem timeout gap
for this specific slow ecosystem already documented in `AGENTS.md`). Not
treated as a passing result and not substituted with a fabricated one -- the
live 2-RPC re-derivation, the hand-verified expected tuple match immediately
before sending (below), and the full unit-test suite are what this push's
correctness actually rests on, same reasoning as every prior single-target
push in this rotation.

## Push

UNCX V3 Locker's score re-derived live immediately before sending (via
`score_uncx_v3_locker()` + a live `compute_cross_exposure()` call) and
compared against the hand-derived expected tuple `(50, 35, 0, 100, 100)` --
matched (`compositeScore` computed as 31, not hand-typed), so the send
proceeded. Pushed to the testnet oracle as a single-target `updateScores()`
call (same rationale as every prior single-target push in this rotation --
avoids a 50min+ full run for one target):

Transaction [`0x945dcbd3c139d819785c529766a9e2d5e8c352aa75c0cdb5d23a286fec88d10c`](https://explorer.testnet.chain.robinhood.com/tx/0x945dcbd3c139d819785c529766a9e2d5e8c352aa75c0cdb5d23a286fec88d10c),
testnet block 121470191, status 1 (success). `trackedTargetsCount()` went
from 52 to 53. `getScore()` re-read after confirmation:

| Target | Result |
|---|---|
| UNCX Network V3 Locker (Robinhood Chain) | `(50, 35, 0, 100, 100, 31)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before sending, balance confirmed non-zero
(~0.00986 testnet ETH) on Robinhood Chain Testnet before sending). Robinhood
Chain **mainnet** was only ever read from, never written to; no non-testnet
key was used, generated, or requested at any point in this run.

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as every prior single-target push in this rotation -- only
a full, non-dry-run `update_scores.py` run writes it). `getScore()` on-chain
remains the source of truth per this project's own documented convention.

## Rotation state

`last_audited_target_index` advances from 10 to 11 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(11)` from
scratch.

## CORRECTION (2026-09-19, later): the "25 of 26 selectors" miss was a scan artifact

An independent re-verification found the one unmatched selector, `withdraw()`
(`0x00f714ce`), is not absent from the locker: it starts with a zero byte, so
solc pushes it as PUSH3 and a PUSH4-only scan cannot see it. Re-read on both
Robinhood mainnet RPCs: 47 of 47 signatures derived from the source and its
interface ARE present, and `withdraw()` simulated from the owner Safe reverts
`OWNER` on every existing lock. The conclusion above is unchanged (same source),
just cleaner. The same pass also found a scope point this document did not
state: `setFeeParams` names the auto-collect account (a bare EOA today), which
may `collect()` on any lock, and `setUCF` can lower a lock's fee to 0, so the
owner Safe can redirect any lock's UNCOLLECTED trading fees (confirmed by
`eth_call` simulation with state overrides, no transaction). Principal stays
out of reach. Score (31) unchanged. See
`data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`.
