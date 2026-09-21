# Rotation audit (2026-09-19/20): Robinhood Chain, tracked target index 15, plus 1 new target (Saffron Vaults factory)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 15
going into this run. Same discipline as every prior rotation audit: the target
is read live from the testnet oracle (`trackedTargets(15)`), every authority
fact is re-derived from scratch on independent mainnet RPCs (never re-read
from `scripts/lib/scorers.py`'s own logic), then compared with `getScore()`.
`trackedTargetsCount()` was 57 going in and is 58 after this run's one push.

## Part 1 -- rotation audit, index 15

`trackedTargets(15)` = `0x894E1EC2D74FFE5AEF8Dc8A9e84686acCB964F2A`, the
"Robinhood Token: PLTR" entry of `STOCK_TOKEN_TARGETS`, the 3rd of 5
tokenized-stock beacon-proxy targets.

| Published (`getScore`) | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | lastUpdated |
|---|---|---|---|---|---|---|---|
| before this run | 3 | 0 | 0 | 100 | 100 | 1 | 1789572321 |
| re-derived this run | 3 | 0 | 0 | 100 | 100 | 1 | (not pushed) |

**No divergence in any field. Nothing pushed for this index.**
`methodologyHash` on chain = `keccak256("authority-risk-oracle-v3")`,
recomputed. `score_stock_token()` run live on two RPCs returns `(3, 0, 0, 100,
1)` on both; `compute_cross_exposure()` returns 100 for PLTR on both.

### What was re-derived, and what was new versus indexes 13 and 14

Mainnet reads only (chain 4663), RPC A = `rpc.mainnet.chain.robinhood.com`,
RPC B = `robinhood.drpc.org`, RPC C = `robinhood-rpc.publicnode.com` (found
this run: serves `eth_call`/`getCode`/`getStorageAt`, but refuses `eth_getLogs`
with a 403 "archive requests require a personal token").

| Check | Result |
|---|---|
| PLTR proxy runtime code | 283 bytes, hash `6c1fdd40...5630`, byte-identical to TSLA, AMZN, NFLX and AMD (A and B identical) |
| EIP-1967 beacon slot in the proxy's own storage (`keccak256("eip1967.proxy.beacon")-1`, computed live) | `0xe10b6f6B275de231345c20D14Ab812db62151b00`; implementation and admin slots are zero |
| **Beacon address as an immutable in the bytecode** (new) | the proxy's code has it as a `PUSH32` constant and calls `implementation()` (`0x5c60da1b`) on it; **the implementation's bytecode also hardwires the same address**. Indexes 13 and 14 only read the storage slot; both pinnings agree |
| PLTR proxy's own events, full history (RPC A) | among the 15 admin and role event topics queried, only `BeaconUpgraded(0xe10b...)` and `Initialized` at block 48285, no role events (an unfiltered `getLogs` is not possible: the proxy emits thousands of ordinary token events and exceeds RPC A's 10,000-log cap): **the token holds no role state of its own**, all authority is the beacon's |
| Beacon | 2,332 bytes, hash `8b465c0b...e90e`, implementation `0xb35490d6...5aE2` (11,614 bytes), `paused()` false, `owner()` reverts (not Ownable) |
| Admin `0xD6f8378F...B66d` | 0 bytecode and nonce 2 on A, B and C, balance ~0.0525 ETH (A) |

### The beacon's full role graph (new: prior audits only checked `DEFAULT_ADMIN_ROLE`)

Full-history `eth_getLogs` on the beacon address (no topic filter, 9 chunks on
RPC A, tip 67,411,652): 274 events. On RPC B
(free plan, `eth_getLogs` only accepts windows of about 100 blocks, so a full
replay was not possible there) the block 0 to 9,000 window was re-replayed in
90-block chunks: the 18 events in that window are identical to RPC A's.
Everything after block 9,000 that touches a role is bounded by the admin EOA's
nonce, not by a second log scan: after the deployer revoked its own
`DEFAULT_ADMIN_ROLE` (block 8695) the only address able to grant or revoke
anything is `0xD6f8...B66d`, whose nonce is exactly 2 on A, B and C, and its two
transactions are both accounted for below.

| Event type | Count |
|---|---|
| `Blocked(address)` | 246 |
| `Unblocked(address)` | 4 |
| `RoleGranted` | 16 |
| `RoleRevoked` | 3 |
| `Upgraded(address)` | 2 (blocks 7796 and 657134, both to `0xb35490d6...5aE2`) |
| `Paused()` / `Unpaused()` | 1 / 2 (blocks 610644, 611101, 611243) |
| `RoleAdminChanged` | 0 |

Current holders after replaying the 19 role events, each confirmed with a
live `hasRole()` on A and B (identical), each holder a **bare EOA (0 bytecode)
on both**:

| Role | Holder | Nonce | Granted at block |
|---|---|---|---|
| `DEFAULT_ADMIN_ROLE` | `0xD6f8378F...5B66d` | 2 | 7802 (deployer's own copy revoked at 8695) |
| `BEACON_UPGRADER_ROLE` (`upgradeTo`) | `0xCd8C6182...2Be094` | 1 | 8646 (deployer's copy revoked at 8692) |
| `PAUSER_ROLE` (beacon `pause`) | `0xe7BCB188...F22A` | 3 | 7833 |
| `TOKEN_PAUSER_ROLE` | `0xFCcF56B6...Ab23` | 3 | 7844 |
| `BLOCKER_ROLE` (`blockAccounts`) | `0x913cA873...28fD` | 250 | 8687 |
| `MINTER_ROLE` | `0x2b94105f...3A87` | 71,230 | 7817 |
| `BURNER_ROLE` | `0x6E40B50A...D8C1` | 9,401 | 7820 |
| role `0x25e7ebc8...8936` (name unknown) | `0x957B6de6...74D4` | 1 | 7828 |
| role `0x155fc2c2...aa11` (name unknown) | `0x7369d100...4aBC` | 7 | 8638 |
| role `0x5f077d4e...bbeb` (name unknown) | `0x5516B345...E000` | 204 | 8643 |
| role `0xb4e5de73...84f8` (name unknown) | `0x697e774d...e553` | 1 | 8654 |
| role `0x7158cf42...b615` (name unknown) | `0x92905e8d...8143` | 38 | 8675 |
| role `0x7f526084...a61e` (name unknown) | `0xcba16C2b...524A` | 6 | 8682 |

Role names come from `keccak256(name)` matches against the revert data of
simulated calls; the six unknown ones were not brute-forced further.
`getRoleAdmin()` returns `0x00` (`DEFAULT_ADMIN_ROLE`) for **all 13** role ids,
on A and B.

The admin's two transactions, both accounted for: block 616387 `grantRole(
MINTER_ROLE, 0x...dEaD)` and block 618536 `revokeRole` of the same. Other
authority is visibly exercised by these EOAs: `0xCd8C...` sent the block 657134
`upgradeTo` (to the implementation already installed, an exercise of the path,
not a code change), `0xe7BC...` sent all 3 pause-state changes, and all 250
`Blocked`/`Unblocked` transactions came from `0x913c...` (its nonce is exactly
250); replaying them, 175 of 177 ever-blocked addresses are blocked today.

### What the admin key can and cannot do directly (eth_call simulation)

| Simulated call | From admin EOA | From an arbitrary address | From the role's own holder |
|---|---|---|---|
| `upgradeTo` and `blockAccounts` (A, B and C identical); `pause`, `mint`, `burn` (RPC A only) | reverts `AccessControlUnauthorizedAccount(admin, <role>)` | reverts the same way | passes (`upgradeTo(current impl)`, `pause()`, `blockAccounts([0x22..22])` simulated OK) |
| `grantRole(<any of the 6 named roles>, itself)` (A, B and C identical) | **passes, no delay** | reverts | n/a |

So the phrasing in `data/scored_targets_2026-09-15-batch3.md` ("that one key
can ... `upgradeTo` ... `blockAccounts`") is imprecise: the admin cannot do
those directly, it needs one `grantRole` transaction first, and today the
upgrade, pause, block, mint and burn roles sit on 12 other bare EOAs. The
score does not change, and this is why: every one of those 13 keys is a bare
EOA, the whole tree is rooted at `DEFAULT_ADMIN_ROLE` (no `RoleAdminChanged`
ever), there is no Safe and no timelock anywhere in it. Docstring of
`score_stock_token()` corrected; batch3 text left as history, this file is the
correction.

`crossExposureScore`: none of the 12 non-admin EOAs appears anywhere in
`scripts/`, `chains/`, `data/` or `README.md` (grepped), and
`compute_cross_exposure()` on A and B returns 100 for all 5 stock tokens and
the same crossExposure as the chain for the 57 tracked targets. They are now
listed in the `stock_tokens` `known_eoa` list of `signer_overlap.py` so a
future overlap is caught (no score effect today).

## Part 2 -- new-target search

### How candidates were found

DefiLlama `api.llama.fi/protocols`, entries with any Robinhood-labelled
`chainTvls` key (176 at pull time), matched by name
against `scripts/lib/scorers.py`, `data/` and `README.md`. Everything above
the ~$600k floor already in the repo was either tracked or examined in an
earlier pass, except **Saffron Vaults** ($820,665). Below the floor and not
examined this run, listed so they are not mistaken for rejected: Gami Labs
($598k, "Risk Curators"), Orvex ($394k), Kittenswap Algebra ($388k), Meridian
Predict ($372k). GIGA V3, StonkBrokers, UNCX V4, DexFi Aggregator and
Accountable stay exactly as recorded in the index 14 file (not re-worked).

### Saffron Vaults factory `0xb24b143ad6bB5bE9559CcC75f34A2261b7456904`

**Identity.** DefiLlama slug `saffron-vaults`, module `saffron-v2/index.js`,
URL `saffron.finance`, twitter `saffron`. The GitHub org `saffron-finance`
has `blog: saffron.finance` (same check used for Arcus, UNCX, T3tris) and
publishes `saffron-uniswap-contracts`; `docs.saffron.finance/security/audits`
lists ChainSecurity (2025-12-15) and 0xleastwood (2026-01-14). The adapter's
`robinhood` entry names this factory and NFT manager `0x73991a25...de0d3`.

**TVL, recomputed on chain instead of trusted.** `nextVaultId` = 112 -> 111
vaults, `vaultInfo` identical on A and B for all 111; each vault's variable
asset balance plus, for the 13 vaults that hold a Uniswap V3 position, the
position amounts from `NonfungiblePositionManager.positions()` and the pool's
own `slot0()` (all 13 NFTs are owned by their own adapter, adapter
`liquidity()` equals the position's for 13 of 13). Priced from those pools'
spot against USDG = $1:

| Token | Amount | Price | Value | Share |
|---|---|---|---|---|
| STONKBROKER | 45,972,435 | $0.010019 | $460.6k | 57% |
| USDG | 239,672 | $1.00 | $239.7k | 30% |
| SFI (Saffron's own token) | 693.5 | $115.40 | $80.0k | 10% |
| NVDA / SPY / PONS / SGOV / ZZZ / WETH / CASHCAT | small | pool spot | $23.0k together | 3% |
| **Total** | | | **$803.3k** | |

Recomputed on B about 7.7k blocks later: same total to under 0.01%.
DefiLlama says $820.7k, 2.1% higher. Its own prices (coins.llama.fi: SFI
$118.29, STONKBROKER $0.009957) explain only about $1.7k of the $17.4k gap;
the rest is not attributed (snapshot timing on a live vault set is the likely
candidate, not verified). DexScreener independently quotes STONKBROKER
$0.01001 (several pools, one with $911k liquidity) and SFI $115.40. **The TVL
is real and chain-specific, but concentrated: 57% is one launchpad token in a
single-sided range, and only ~$260k is USDG plus the tokenized stocks/ETF.**
Nothing here is inflated by a bad price like the USAR case at index 14.

**Authority.** Not a proxy (all three EIP-1967 slots zero on A). `Ownable2Step`,
`owner()` = `feeReceiver()` = `0x58CA1eaED80896400122164Abe16d77B2b4ff7c9`,
`pendingOwner()` = 0. `feeBps()` = 1250. `eth_call` simulation: `createVault`,
`createAdapter` and `setFeeBps` revert "Ownable: caller is not the owner"
for an arbitrary caller, so this is the restricted variant (only the owner
creates vaults) and all 111 vaults list that same owner as `creatorAddress`;
`setFeeBps` passes for the owner with no queue or delay.

The owner is **not a bare EOA by `is_eoa()`**: it has 23 bytes of code,
`0xef0100` plus `0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B`. That is an
EIP-7702 delegation; the delegate answers `NAME()` = `EIP7702StatelessDeleGator`,
`VERSION()` = `1.3.0` (MetaMask Delegation Framework), a stateless
smart-account delegate where the account's own key signs. Repo's own
`classify_account()` returns `eip7702_delegated` on A, B and C. Per
`METHODOLOGY.md` that is one signing key, treated like a bare EOA rather than
traced as if a contract's logic controlled it; the key can always replace the
delegation with a native transaction. The key is active (nonce 414, ~0.038
ETH). `METHODOLOGY.md` recorded no 7702 root among tracked targets as of
2026-09-17, but that was stale: Fables PoolRegistry's sole admin
(`0x359856655934338D798f9CCE1f181486301D36a5`, tracked since batch 10, nonce 575,
confirmed 7702-delegated on A and B by the independent verifier) is one too, so
Saffron's owner is at least the second. This pass did not re-scan all 57
targets.

**Score.** Same-key convention of `score_curve_dex()` (`owner() ==
feeReceiver()` -> 2, lone EOA would be 5), multisig 0, timelock 0, oracle 100:
**2 / 0 / 0 / 100, crossExposure 100, composite 1**. crossExposure re-derived
live on A and B via `compute_cross_exposure()` (new group
`saffron_vault_factory`): 100, and the crossExposure of the 57 already-tracked
targets is unchanged. The owner and factory addresses appear nowhere else in
the repo, so this is a new authority root, not a duplicate.

**What the score does and does not claim.**
- It rests on the controller of the owner-gated surface only, like Curve and
  Alandale. The public source (`saffron-uniswap-contracts`, a single "Initial
  commit") says that surface can set fees, re-point `feeReceiver` (which every
  vault reads live from the factory) and publish new vault/adapter bytecode
  types, and that existing vaults have no owner. **That is not verified
  against the deployed code**: all 30 functions of `VaultFactory` are in the
  deployed factory's selector set, but no compiler was run to match bytecode,
  and 2 of the 5 PUSH4 constants in the deployed code are unidentified. The
  vault runtime code is uniform (one hash across all 111) and the vault type-1
  runtime appears inside the bytecode stored in the factory, but that says
  nothing about what it does. So no claim about blast radius is encoded, and
  a low score here does not mean user principal can be taken.
- Chain-specific TVL composition is above.

### Push

Live re-derivation on both read RPCs equalled the hand-derived tuple
`(2, 0, 0, 100, 100, 1)` immediately before sending; chain id 46630 asserted,
`hasRole(UPDATER_ROLE)` true, updater balance ~0.00986 testnet ETH (already
funded, no faucet, no funding requested), target not already tracked. Tx
`0x409b98f767c485c533a3fba9d1a108d7e3238440158b545229c93322d2b3149d`,
testnet block 121828009, `trackedTargetsCount` 57 -> 58, `getScore()` read
back and identical, `methodologyHash` correct. Robinhood Chain mainnet was
only read. The throwaway testnet key was read from the keys file and never
printed or committed. `public_repo_visibility_change_allowed` untouched.

### Code and tests

`score_saffron_vault_factory()` and `SAFFRON_VAULT_FACTORY` in
`scripts/lib/scorers.py` (added to `SIMPLE_SCORERS`, `classify_account`
imported); `saffron_vault_factory` group and the 13-address `stock_tokens`
`known_eoa` in `scripts/lib/signer_overlap.py`;
`scripts/lib/tests/test_robinhood_saffron_factory_and_stock_roles.py` (scorer
branches: 7702 same-key 2, bare EOA 2, different keys 5, real contract 40 with
warning, unresolved 40 without crashing, pendingOwner surfaced, wiring; and
the overlap-group invariants: 13 stock EOAs listed, valid checksums, each new
address in exactly one group).

### Limits of this pass, stated

- The AGENTS.md "adversarial review before committing" step was done as a
  self-refutation pass by the same agent (TVL, duplicate claim, owner type,
  score branch, blast-radius wording, each checked against a second source
  where one existed), **not** by a separate refuting agent: this run had no way
  to spawn one.
- The full-history log replay of the beacon exists on one RPC only (RPC B's
  free plan blocks it, RPC C refuses `eth_getLogs`); the second-RPC evidence
  is the block 0-9000 replay, the live `hasRole()` on two RPCs, and the
  nonce bound on the admin key.
- Saffron deployed-code-versus-source match not established (see above).
