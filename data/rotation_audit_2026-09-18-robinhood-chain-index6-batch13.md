# Rotation audit (2026-09-18): Robinhood Chain, tracked target index 6, plus batch 13

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 6
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(6)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

This run also closes the two leads batch 12 explicitly left open
(budget/time, not resolved): Spark Liquidity Layer and Steakhouse Financial.
Both turned into real, verifiable batch-13 additions -- see below.

## Part 1 -- rotation audit, index 6

`trackedTargets(6)` = `0x544BF81c855AE84c1e8b65d5E38770898D01EeE2` --
`MarketFactoryV6`, the on-chain identity of the target scored as "Pendle V2
(ProxyAdmin + devProxyAdmin + MarketFactoryV6)". `trackedTargetsCount()` = 46
going into this run.

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 70 | 45 | 0 | 100 | 100 | 42 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`.
Made raw `eth_call`/`eth_getLogs`/`eth_getStorageAt` calls directly, not
through `score_pendle_v2()`.

| Check | RPC A result | RPC B result |
|---|---|---|
| `ProxyAdmin.owner()` (`0xA28c08f1...c5E64`) | `0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac` -> Safe **3-of-5** (`getOwners()`/`getThreshold()`) | identical |
| `devProxyAdmin.owner()` (`0xD37eB2E6...54EA9`) | `0xE6F0489ED91dc27f40f9dbe8f81fccbFC16b9cb1` -> Safe **3-of-6** | identical |
| `MarketFactoryV6.owner()` | `0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e` (has code, not a Safe -- `getOwners()`/`getThreshold()` both revert) | identical |

The third hop (`MarketFactoryV6.owner()`) is the one `score_pendle_v2()`'s
own docstring flags as "not yet traced past its first hop -- disclosed as an
open sub-thread". Traced it this pass rather than leaving it open again:

- `eth_getCode` on `0x2aD631F7...` returns 225 bytes matching a hand-rolled
  EIP-1967-style proxy (reads the standard implementation slot
  `0x360894a1...382bbc` then delegatecalls). `eth_getStorageAt` on that slot
  resolves to implementation `0x41dd1bd3...5f74d6` (10,238 bytes); the
  EIP-1967 **admin** slot is zero on both RPCs -- no separate proxy-admin
  contract, matching batch 12's finding on Spark Liquidity Layer that not
  every proxy on this chain follows the textbook Transparent pattern.
- The implementation's own dispatcher (PUSH4 selector scan) exposes
  `DEFAULT_ADMIN_ROLE()`, `hasRole`, `grantRole`, `revokeRole`,
  `renounceRole`, `getRoleAdmin` -- OpenZeppelin **AccessControl**, not
  `Ownable` (which is why `owner()` on this second hop reverts: wrong
  interface, not a broken contract).
- `RoleGranted`/`RoleRevoked` full-history replay (`eth_getLogs`, full
  range, on `0x2aD631F7...`, role = `DEFAULT_ADMIN_ROLE` = `0x00...00`):
  granted to the deployer `0x1fCcc097...B1FB7` at block 52437932, granted to
  `0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac` at block 52652573, deployer's
  own grant revoked at block 54144495. Current holder set: exactly
  `{0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac}` -- **the same 3-of-5 Safe
  that already owns `ProxyAdmin`**, confirmed live via `hasRole()` on both
  RPCs (`True` for that Safe, `False` for the former deployer).

**Finding**: the "third, separate authority" is not actually separate. It
converges on a Safe already counted in this target's own `adminKeyScore`.
This does not change any sub-score (the formula's `safes` count was already
2 regardless of this third hop; see `score_pendle_v2()`), but it closes a
disclosed open item with a real answer instead of leaving it open again.

### Score check

`_composite(70, 45, 0)` = `floor(0.4*70 + 0.3*45 + 0.3*0 + 0.5)` =
`floor(42.0)` = 42 -- matches the published `compositeScore` exactly.
`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache): 100, matching. **No divergence anywhere. No
correction needed for this target; nothing pushed for index 6 itself.**

## Part 2 -- the two leads batch 12 left open

### Spark Liquidity Layer -- RESOLVED, new target added

Batch 12's note: "no EIP-1967 admin slot set and no `owner()` ... Spark's
ALM contracts use a bespoke `rely`/`deny` (`wards` mapping) or a separate
`ALMController`/rate-limits contract holding the real authority ... not
traced this pass." That assumption about the authority *shape* turned out to
be wrong once actually read -- corrected here based on what's deployed, not
on what a sibling Spark product (the PSM) uses elsewhere:

- `0xfD2fD4B046136B540A56C11c75ac679AE7d1dB24` (2,260 bytes) is **not a
  proxy**. Its dispatcher exposes `doCall(address,bytes)` (`0x3aada4d2`),
  `doDelegateCall(address,bytes)` (`0x8ce4a1f2`), `doCallWithValue(address,
  bytes,uint256)` (`0xd71f93f8`) -- the real selectors of Spark's own
  `spark-alm-controller` `ALMProxy.sol` -- gated by OpenZeppelin
  AccessControl, not the MakerDAO/Sky `wards` rely/deny pattern.
- A role constant embedded in the bytecode (selector `0xee0fc121`) returns
  `0x70546d1c92f8c2132ae23a23f5177aa8526356051c7510df99f50e012d221529`,
  which is exactly `keccak256("CONTROLLER")` -- confirms the role is named
  literally `CONTROLLER`, granted (per a full `RoleGranted`/`RoleRevoked`
  replay, both RPCs identical) to `0xCF8D58A6...76BA1e` at block 57749 --
  the operational relayer-logic role, not the root authority.
- `DEFAULT_ADMIN_ROLE` (the root authority) replay: deployer
  `0xB328BD52...DCc547` self-grants at block 31311, grants
  `0x826AEaeee9233FA8Ba199518dD8621A5962b1D02` at block 57755, deployer's
  own grant revoked at block 57807. **Current sole holder**: `0x826AEaee...
  1D02` -- re-confirmed live via `hasRole()` on both RPCs.

That holder address, and its 8,113-byte bytecode size, are an **exact
match** for the executor contract already fully traced in the previous
rotation audit (index 5, `data/rotation_audit_2026-09-18-robinhood-chain-index5.md`)
for **Spark Savings USDG** -- not a similar architecture, the literal same
deployed contract administering both products. Its properties were
re-verified live rather than assumed carried over: `delay()` = 0,
`gracePeriod()` = 604800, and the receiver contract
(`0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8`) `.l1Authority()` resolves to
the same Ethereum-mainnet Sky/MakerDAO "SubProxy" address
(`0x3300f198988e4C9C63F75dF86De36421f06af8c4`) already verified on Etherscan
for that other target.

**Scored identically to Spark Savings USDG, for the same underlying reason**
(same root contract, same governance chain): adminKeyScore 50, multisigScore
30, timelockScore 10 (`_composite` -> compositeScore **32**).
`crossExposureScore` stays 100 under this project's existing "unresolved" /
not-applicable convention (the shared root is a contract, not a Safe with
individually-resolved EOA owners, so the signer-overlap formula has no way
to score it as an overlap) -- disclosed explicitly in
`scripts/lib/signer_overlap.py`'s `spark_savings` group rather than silently
defaulted: **this is a real, confirmed shared single point of failure
between two tracked targets that the mechanical crossExposureScore field
cannot currently represent**, stated here plainly rather than left to look
like a clean 100.

New scorer: `score_spark_liquidity_layer_almproxy()` in `scripts/lib/scorers.py`,
added to `SIMPLE_SCORERS`.

### Steakhouse Financial -- RESOLVED, two new targets added

Batch 12's note: DefiLlama's per-protocol page (`projects/steakhouse/index.js`)
404s. Rather than treat that as a dead end, found the file the TVL number
actually comes from: DefiLlama-Adapters' `registries/curators.js` (a generic
curator registry, not a per-protocol adapter -- confirmed live at
`raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/registries/curators.js`,
`"steakhouse"` entry, `blockchains.robinhood.morpho`). It lists **4**
Robinhood-chain vault addresses; 2 (Steakhouse USDG, Ethena x Steakhouse
USDG) were already tracked. The other 2 were not:

- `0xBEEff039907422219Fb367e525954DDC092854d9` -- **Grove x Steakhouse USDG**
  (`groveUSDG`)
- `0xbeEfFF136E3684273e6aA75A1669B784B373A4FD` -- **Steakhouse Turbo USDG**
  (`bbqUSDGturbo`)

The registry file was only ever a place to look, not trusted on its own --
both confirmed live on 2 independent RPCs before being added: real deployed
code (21,808 bytes each), `asset()` = USDG (`0x5fc5360D...F1d168`,
`decimals()`=6) on both, `totalAssets()` = ~$100.0K (Grove) and ~$54.5K
(Turbo).

**Authority chain** (via `curator()`/`owner()`, traced one hop further where
`owner()` doesn't resolve directly to a Safe -- same method as every other
Morpho Vault V2 on this chain):

| Vault | `curator()` | `owner()` chain | `isSentinel()` (known sentinel) | `timelock(setOwner/setCurator/setIsSentinel)` |
|---|---|---|---|---|
| Grove x Steakhouse USDG | `0x622E19d6...14C0FC` -> Safe **2-of-2** (new "Grove" Safe, not previously tracked) | `0x261a3b7A...Cf2b1` -> `0xD062020d...15ef4` -> Safe **5-of-10** | `False` (no sentinel resolved this pass -- not assumed absent, just not enumerated) | `[0, 0, 0]` |
| Steakhouse Turbo USDG | `0x9023FBD6...D2Fb` -> Safe **3-of-7** (the *same* curator Safe as the already-tracked Steakhouse USDG vault) | `0x261a3b7A...Cf2b1` -> `0xD062020d...15ef4` -> Safe **5-of-10** | `True` (same sentinel as Steakhouse USDG) | `[0, 0, 0]` |

The `owner()` chain resolves to the exact same 5-of-10 Safe already
documented for the already-tracked Ethena x Steakhouse USDG vault (the
"largest raw multisig found on this chain" per README) -- both new vaults
share it too, confirmed live on both RPCs.

Scored via `score_morpho_vault_generic()` (the same generic scorer already
used operationally for `MORE_MORPHO_VAULTS`, not a one-off hand formula):
Grove x Steakhouse USDG = 60/56/10/100 -> composite **44**; Steakhouse Turbo
USDG = 60/64/10/100 -> composite **46**.

Both added to `MORE_MORPHO_VAULTS` in `scripts/lib/scorers.py`.

### crossExposure correction this discovery forced

Wiring the 2 new vaults into `scripts/lib/signer_overlap.py` (new groups
`steakhouse_turbo`, `grove_steakhouse`, both sharing signers with the
existing `steakhouse`/`ethena_steakhouse` groups via the 3-of-7 curator Safe
and/or the 5-of-10 owner Safe) and re-running `compute_cross_exposure()`
live revealed that **all four** Steakhouse-family vaults on this chain now
mutually overlap (each one's signer set touches the other three groups):

| Target | crossExposureScore before | crossExposureScore after |
|---|---|---|
| Steakhouse USDG (already tracked) | 80 | **40** |
| Ethena x Steakhouse USDG (already tracked) | 80 | **40** |
| Grove x Steakhouse USDG (new) | -- | 40 |
| Steakhouse Turbo USDG (new) | -- | 40 |

`compositeScore` is unaffected for the 2 pre-existing targets (crossExposure
is a separate field, never folded into compositeScore) -- confirmed live:
Steakhouse USDG stays 19, Ethena x Steakhouse stays 46. Checked this was the
*only* ripple effect: re-ran `compute_cross_exposure()` for every one of the
46 pre-existing targets and confirmed none of the other 42 changed (full
dump in this pass's own working notes, not reproduced here -- every
non-Steakhouse-family group's signer set is disjoint from the 12 signers
now shared across these 4 groups).

## Push

All 5 entries (2 corrections, 3 new) re-derived live immediately before
sending and compared against hand-verified expected values -- script refused
to send if any differed (none did). Pushed to the testnet oracle in one
`updateScores()` call:

Transaction [`0xee3163ea420d0ee5797f6083a7e41ebb31b63048240f011bbf8dd0961bc786a9`](https://explorer.testnet.chain.robinhood.com/tx/0xee3163ea420d0ee5797f6083a7e41ebb31b63048240f011bbf8dd0961bc786a9),
testnet block 121357512, status 1 (success). `trackedTargetsCount()` went
from 46 to 49. `getScore()` re-read after confirmation for all 5:

| Target | Result |
|---|---|
| Steakhouse USDG | `(10, 35, 15, 100, 40, 19)` |
| Ethena x Steakhouse USDG | `(60, 64, 10, 100, 40, 46)` |
| Grove x Steakhouse USDG | `(60, 56, 10, 100, 40, 44)` |
| Steakhouse Turbo USDG | `(60, 64, 10, 100, 40, 46)` |
| Spark Liquidity Layer (ALMProxy) | `(50, 30, 10, 100, 100, 32)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- confirmed `UPDATER_ROLE` held,
funded, distinct from `keys/evm-testnet-shared.json` used by the other EVM
ecosystems in this pipeline). Robinhood Chain **mainnet** was only ever read
from, never written to; no non-testnet key was used or requested.

`scripts/lib` tests (439 tests, `python3 -m unittest discover -s
scripts/lib/tests`) pass unchanged after these edits, no live RPC needed.

## Leads NOT pursued further

None left open from this run's original two leads -- both resolved (Spark
Liquidity Layer scored and pushed; Steakhouse Financial's 2 previously-untracked
vaults found, scored and pushed). `up v3` and `UNCX Network`, flagged open in
batch 12 for unrelated reasons (same 404 adapter path / fundamentally
different authority shape respectively), remain open -- not touched this run.

## Rotation state

`last_audited_target_index` advances from 6 to 7 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(7)` from
scratch.
