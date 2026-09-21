# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 12, plus 1 new target (T3tris Finance WBTC vault)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 12
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(12)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 12

`trackedTargets(12)` = `0x4472C69d299382F8847ebCE4FC6Ed8e295510E3e` -- the
on-chain identity of the target scored as "Arcus pBTC3x", the third and
last member of the Arcus pToken family (factory audited at index 10,
pBTC (1x) at index 11, this is pBTC3x). `trackedTargetsCount()` = 54 going
into this run (before this run's own push).

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 65 | 55 | 0 | 100 | 80 | 43 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_getCode`/`eth_getStorageAt`/`eth_call` made directly against the pBTC3x
token, the shared beacon, the beacon's owner Safe, and the factory's own
AccessControl -- not through `score_arcus_ptoken()`'s own cached logic.

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (pBTC3x token) | 229 bytes | identical |
| EIP-1967 beacon slot (own storage, `keccak256("eip1967.proxy.beacon")-1`, computed live not hardcoded) | resolves to `0x33846348...73A76` | identical |
| EIP-1967 implementation slot (own storage) | zero (no direct impl -- routed via the beacon) | identical |
| EIP-1967 admin slot (own storage) | zero (no transparent-proxy admin -- beacon-governed) | identical |
| `eth_getCode` length (beacon `0x33846348...73A76`) | 590 bytes | identical |
| `beacon.owner()` | `0x81B80499C396a9931b9e44953425a82C1b2541bd` | identical |
| `eth_getCode` length (beacon owner) | 171 bytes (real contract, not an EOA) | identical |
| `getOwners()` on beacon owner | `['0x4f1d777b...05ebe2', '0x57D32496...4f5b78', '0xEAb7F386...f989d7']` | identical |
| `getThreshold()` on beacon owner | 2 | identical |
| Safe `getModulesPaginated()` | `[]` (no modules) | identical |
| Safe guard storage slot (`keccak256("guard_manager.guard.address")`, computed live) | `0x0` (no guard) | identical |
| factory `getRoleMemberCount(DEFAULT_ADMIN_ROLE)` (independent 2nd trace of the SAME root, via the factory's own AccessControl rather than the beacon) | 1 | identical |
| factory `getRoleMember(DEFAULT_ADMIN_ROLE, 0)` | `0x81B80499C396a9931b9e44953425a82C1b2541bd` (same Safe) | identical |

Confirms both halves of the original finding, independently, from scratch,
for THIS specific target (index 12 is the pBTC3x token itself, the last
un-audited member of the family): the pBTC3x token's own EIP-1967 beacon
slot points at the shared beacon, that beacon's `owner()` **and** the
factory's own separate `DEFAULT_ADMIN_ROLE` both resolve to the exact same
real, active 2-of-3 Gnosis Safe already confirmed at index 10 (factory) and
index 11 (pBTC 1x) -- one Safe, one `upgradeTo()` call on the beacon,
rewrites the implementation shared by the factory and every pToken issued
through it. All three Arcus pToken family members are now individually
audited from scratch; none has ever diverged from its published score.

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache) on both RPCs: **80**, matching the published
value exactly (the correction made at index 11, when the Arcus Perps
BridgeVault's shared signer was found, already accounted for this target).

`methodologyHash` on-chain independently recomputed as
`keccak256("authority-risk-oracle-v3")` -- matches exactly, not stale.

### Score check

`score_arcus_ptoken()`'s "Safe found" branch returns `admin_key=65`,
`multisig = threshold*25+5 = 2*25+5 = 55` when the beacon owner resolves to
a Gnosis Safe. `_composite(65, 55, 0) = floor(0.4*65 + 0.3*55 + 0.5) =
floor(43.0) = 43` -- matches the published `compositeScore` exactly.
**No divergence in any field for index 12.** Nothing pushed for this index.

## Part 2 -- new target search (budget permitted this run)

DefiLlama's `chainTvls["Robinhood Chain"]` protocol list was re-pulled
(`api.llama.fi/protocols`, filtered on any `chainTvls` key containing
"robinhood", 216 entries) and cross-checked label-by-label against every
target/group already present in `scripts/lib/scorers.py` and
`scripts/lib/signer_overlap.py`. Several higher-TVL candidates were checked
and ruled out before finding a genuinely new one -- documented here rather
than silently skipped:

- **up v3** (~$8.6M, the highest-TVL open lead carried over from indices 8
  and 9) -- re-checked, still no DefiLlama adapter file and no GitHub org
  findable. Left open, not resolved this pass either.
- **UNCX Network V4 / unicrypt-v4** (~$794k, open since index 10's own V3
  locker resolution) -- not re-attempted this pass (no new source found
  last time either); still open.
- **Neutral Trade** (~$2.27M aggregate) -- its own DefiLlama adapter
  (`projects/neutral-trade/index.js`, `doublecounted: true`) names exactly
  one Robinhood-chain address in `ACCOUNTABLE_STRATEGIES.robinhood`:
  `0xF62c201e9A28F6A57C4262004dd2e8B8e95bB1eC`. Checked live on-chain before
  assuming it was new: its `vault()` getter returns
  `0x24b84023c8e4Da635be228C380C09bfE5271BF9d` -- the EXACT SAME Meridian
  Perps LP vault already examined and explicitly disclosed (index 7 audit,
  `score_meridian_exchangegateway()`'s own docstring) as having NO exposed
  owner/curator/admin/manager/governance surface. Confirmed a genuine
  duplicate, not a new target -- ruled out, not added.
- **What The Hook** (~$1.15M aggregate) -- its adapter
  (`projects/what-the-hook/index.js`) reads liquidity directly out of the
  already-tracked Uniswap v4 `PoolManager` (`0x8366a39CC670B4001A1121B8F6A443A643e40951`,
  the same address already in the `uniswap` signer-overlap group) via a v4
  hook. Custody sits entirely in the already-tracked PoolManager -- ruled
  out.
- **STONX** (~$1.13M + $391k staking, Ekubo family) -- its adapter
  (`projects/stonx/index.js`) reads liquidity out of the already-tracked
  Ekubo `Core` singleton (`0x00000000000014aa86c5d3c41765bb24e11bd701`,
  confirmed permissionless with zero owner/admin/governor surface at index
  8) via a `Ve33`/`Ve33Positions` extension. Custody sits in the
  already-tracked, ownerless Core -- ruled out (a separate question, not
  pursued this pass for lack of time: whether `Ve33`/`Ve33Positions`
  themselves have their own owner over the extension logic).
- **EARN** (~$462k) -- its adapter (`doublecounted: true`) sums TVL sitting
  in Steer Finance smart-pool vaults wrapping the already-tracked
  Uniswap/SushiSwap DEXes. Not pursued further this pass (Steer's own vault
  manager key, if any, is a real separate question left open, same as the
  STONX extension above).
- **Native Credit Pool** (~$357k + $189k borrowed) -- DefiLlama names no
  adapter file resolvable this pass (`projects/native-credit-pool` and
  `projects/native` 404/omit a Robinhood Chain entry); left open.

### T3tris Finance WBTC vault -- RESOLVED, new target added

**T3tris Finance** (DefiLlama slug `t3tris-finance`,
`chainTvls["Robinhood Chain"]` ~$819.2k at pull time) sources its TVL
dynamically rather than from a hardcoded adapter list:
`DefiLlama-Adapters/projects/t3tris-finance/index.js` calls T3tris's own
`https://ecosystem.t3tris.finance/vaults` API each run and sums
`getGrossTVL()` across every entry with `verified: true` and
`blacklisted: false` for `chainId: 4663`. That live registry was read
directly (not trusted secondhand) and lists exactly 4 Robinhood Chain
vaults at the time of this audit:

| Vault | Asset | Live `getGrossTVL()` | Notes |
|---|---|---|---|
| `0x3d3728d7...bce7d67` | (USDG) | 0 | empty, not scored |
| `0x5b93dd3e...bda49e672` | USDG | 24.878912 | ~$25, immaterial, not scored |
| `0xd4d60723...0bb63c63bf` | USDG | 210,824.976188 | ~$210.8k, a DIFFERENT admin EOA than the vault below -- left open, not folded into this finding |
| `0xd5c6c79692715145098a65d1eb1f2a10c524f8e8` | WBTC | 7.49041449 | ~$610k at pull-time WBTC spot price -- **the target scored below** |

**TVL cross-check (2 independent sources, per this run's mandate).** Source
1: DefiLlama's own reported `chainTvls["Robinhood Chain"]` for
`t3tris-finance`, ~$819.2k. Source 2: summing all 4 registry vaults' live
`getGrossTVL()` on-chain (confirmed identical on both
`rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`) and converting
at DefiLlama's own `coins.llama.fi` spot WBTC price (~$81,474 at pull time):
210,824.976 + 24.879 + 7.49041449 x 81,474 ~= $821.1k -- matches DefiLlama's
independently-reported figure within normal snapshot-timing drift, the same
convention already used for Arcus Perps BridgeVault's TVL cross-check at
index 11.

**GitHub verification.** T3tris's GitHub org (`t3tris-finance`) confirmed
genuinely theirs via its own `blog` field pointing to `t3tris.finance` (the
exact same verification method already used for `github.com/arcus-xyz` and
`github.com/uncx-network`). Disclosed gap, not smoothed over: the org
publishes only a `DefiLlama-Adapters` fork plus 2 unrelated repos, no actual
vault source -- the same kind of gap already accepted for Arcus Perps
BridgeVault (ABI/behavior confirmed live on-chain; exact source-level
function-to-role mapping is not).

**Shared implementation, independently-keyed vaults.** All 4 registry
vaults are minimal EIP-1967-style proxies (141 bytes each, byte-identical)
delegating to the exact same implementation
(`0x0000000000AC46824E664881581f0E105Bb5e492`, read from the standard
EIP-1967 implementation slot live on both RPCs; no admin/beacon slot set on
any of the 4). Checked explicitly rather than assumed: each proxy's own
storage exposes OZ AccessControl's `DEFAULT_ADMIN_ROLE` currently held by a
DIFFERENT address per vault (confirmed via `RoleGranted`/`RoleRevoked`
full-history replay from genesis on the WBTC vault, and spot-checked for
the other 2 non-empty vaults) -- this is a marketplace of independently
curated vaults sharing only implementation code, not one shared authority
chain the way the Arcus pToken beacon is. The 3 sibling vaults are each
therefore left untracked this pass rather than folded into one finding: the
empty vault has nothing to score, the ~$25 vault is immaterial, and the
~$210.8k USDG vault has its own separate admin key that would need its own
separate finding (noted here as an open lead for a future pass, not
fabricated as already covered).

**Root-authority tracing on the WBTC vault, live on 2 RPCs.**
`RoleGranted`/`RoleRevoked` events replayed from genesis (one-time discovery
work for this pass; the scorer itself only does a live `hasRole()` check
going forward, the same `known_admin` convention `score_stock_token()`
already uses): `DEFAULT_ADMIN_ROLE` granted exactly once, at deployment
(block 16593422), to `0x65D02Bb13f515DD105Fb733E9E31f11A2F65e57f`, never
revoked. The SAME address self-granted itself 47 other narrower,
function-level roles at deployment (block 16593422/16593820/16594138), later
revoking 6 of those 47 from itself (a real partial self-hardening event,
confirmed via `RoleRevoked` logs, not fabricated) -- but keeping
`DEFAULT_ADMIN_ROLE` and 41+ of the granular roles. Live `hasRole()`
re-confirmed identical on both RPCs: **True**. `eth_getCode` on that address
returns 0 bytes on both RPCs (a real bare EOA, not a contract), nonce 63 on
both -- an actively-used key, not dormant or vanity-mined. No
`TimelockController` and no Gnosis Safe found anywhere in this authority
chain.

**Cross-exposure check.** Grepped `scripts/lib/signer_overlap.py` for both
the vault address and the admin EOA before wiring in a new group -- neither
appeared anywhere else in the existing 32 groups. New group
`t3tris_wbtc_vault` added; `compute_cross_exposure()` re-run live on both
RPCs over the full, now-33-group registry after wiring it in: the new
target itself scores **100** (no overlap), and confirmed the ONLY entries
that moved off 100 anywhere in the registry are exactly the same 10 already
established by prior audits (`steakhouse` family at 40, `arcus`/
`arcus_perps_bridgevault` family at 80, PancakeSwap V2/V3 at 80) -- nothing
else shifted.

### Score

Scored with the same standalone-bare-EOA convention already established for
a single (non-alias, non-multi-contract-converging) EOA root elsewhere in
this file (`score_curve_dex()`'s/`score_noxa_fun_launch_locker()`'s own `5`
branch), not a bespoke discount or penalty for holding 41+ granular roles
instead of just one: `admin_key = 5`, `multisig = 0`, `timelock_score = 0`
(no `TimelockController` found) -> `compositeScore = _composite(5, 0, 0) =
2`.

New scorer `score_t3tris_vault()` added to `scripts/lib/scorers.py`,
appended to `SIMPLE_SCORERS`. New signer-overlap group `t3tris_wbtc_vault`
in `scripts/lib/signer_overlap.py`. 3 new unit tests in
`scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`
(`TestScoreT3trisVault`: bare-EOA-holds-role happy path, role-holder-is-now-
a-contract degrade, role-rotated-away-from-known-admin degrade). Full suite
re-run: 527 tests pass (`python3 -m unittest discover -s scripts/lib/tests`).

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` was
not run this pass (same pre-existing 300-second per-ecosystem timeout gap
for this specific slow ecosystem already documented in `AGENTS.md`). Not
treated as a passing result and not substituted with a fabricated one --
the live 2-RPC re-derivation, the hand-verified expected tuple match
immediately before sending (below), and the full unit-test suite are what
this push's correctness actually rests on, same reasoning as every prior
single-target push in this rotation.

## Push

The new target's tuple was re-derived live immediately before sending
(`score_t3tris_vault()` + a live `compute_cross_exposure()` call) and
compared against a hand-derived expected tuple `(5, 0, 0, 100, 100, 2)` --
matched (`compositeScore` computed, not hand-typed), so the send proceeded.
Nothing was pushed for index 12 itself (no divergence found). Pushed to the
testnet oracle as a single-target `updateScores()` call (same rationale as
every prior single-new-target push in this rotation -- avoids a 50min+ full
run for 1 target):

Transaction [`0xa9006ffe1e51ac4338ac0a8a4e2026b69dbb589fd0b553642871353d896d407f`](https://explorer.testnet.chain.robinhood.com/tx/0xa9006ffe1e51ac4338ac0a8a4e2026b69dbb589fd0b553642871353d896d407f),
testnet block 121718149, status 1 (success). `trackedTargetsCount()` went
from 54 to 55 (`trackedTargets(54)` now reads the new vault address,
confirmed live after confirmation). `getScore()` re-read after
confirmation:

| Target | Result |
|---|---|
| T3tris Finance WBTC vault (Robinhood Chain) | `(5, 0, 0, 100, 100, 2)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before sending, balance confirmed non-zero (~0.00986
testnet ETH) on Robinhood Chain Testnet before sending). Robinhood Chain
**mainnet** was only ever read from, never written to; no non-testnet key
was used, generated, or requested at any point in this run.
`public_repo_visibility_change_allowed` not touched (remains `false`).

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as every prior single-target push in this rotation -- only
a full, non-dry-run `update_scores.py` run writes it). `getScore()` on-chain
remains the source of truth per this project's own documented convention.

## Git note

The local clone at `~/Desktop/workspace/authority-risk-oracle` hit
the known dataless-`.git`-pack-file-on-iCloud issue again this run
(`git status` fails with "Operation timed out" reading
`.git/objects/pack/pack-530e331d...pack`). Per this project's own known-issue
handling, no repair was attempted from this clone -- commit/push were done
from a fresh `gh repo clone` in a scratch directory, copying ONLY this
session's own modified/created files (`scripts/lib/scorers.py`,
`scripts/lib/signer_overlap.py`,
`scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`, and this
`.md` file) -- nothing else staged in the shared local clone by other
parallel sessions was picked up or touched.

## Rotation state

`last_audited_target_index` advances from 12 to 13 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(13)` from
scratch.
