# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 11, plus 1 new target (Arcus Perps BridgeVault)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 11
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(11)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 11

`trackedTargets(11)` = `0x925F92F055EDB79C42B5d45E64A1b74143b90eA0` -- the
on-chain identity of the target scored as "Arcus pBTC (1x)", one of the two
pTokens issued through the Arcus pToken factory/beacon already audited at
index 10 (`data/rotation_audit_2026-09-19-robinhood-chain-index10.md`).
`trackedTargetsCount()` = 53 going into this run.

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 65 | 55 | 0 | 100 | 100 | 43 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_getCode`/`eth_getStorageAt`/`eth_call` made directly against the pToken,
the beacon, the beacon's owner Safe, and the factory's own AccessControl --
not through `score_arcus_ptoken()`'s own cached logic.

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length (pBTC 1x token) | 229 bytes | identical |
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
for THIS specific target (index 11 is the pBTC token itself, not the
factory audited at index 10): the pBTC (1x) token's own EIP-1967 beacon
slot points at the shared beacon, that beacon's `owner()` **and** the
factory's own separate `DEFAULT_ADMIN_ROLE` both resolve to the exact same
real, active 2-of-3 Gnosis Safe -- one Safe, one `upgradeTo()` call on the
beacon, rewrites the implementation shared by the factory and every pToken
issued through it, pBTC (1x) included.

`crossExposureScore` independently re-run via `compute_cross_exposure()`
live (not read from a cache) on both RPCs: **80** -- NOT 100. This is not a
divergence in this target's own root-authority tracing (see Part 2 below
for why the number itself is different from index 10's own audit, which
found 100 for the same `arcus` group before this run's own correction).

`methodologyHash` on-chain independently recomputed as
`keccak256("authority-risk-oracle-v3")` -- matches exactly, not stale.

### Score check

`score_arcus_ptoken()`'s "Safe found" branch returns `admin_key=65`,
`multisig = threshold*25+5 = 2*25+5 = 55` when the beacon owner resolves to
a Gnosis Safe. `_composite(65, 55, 0) = floor(0.4*65 + 0.3*55 + 0.5) =
floor(43.0) = 43` -- matches the published `compositeScore` exactly.
**No divergence in `adminKeyScore`/`multisigScore`/`timelockScore`/
`compositeScore` for index 11.** `crossExposureScore` legitimately drops
from 100 to 80 this run -- a real correction pushed alongside the new
target found in Part 2, not a fabricated or unexplained change.

## Part 2 -- new target search (budget permitted this run)

DefiLlama's `chainTvls["Robinhood Chain"]` protocol list was re-pulled
(`api.llama.fi/protocols`, filtered on any `chainTvls` key containing
"robinhood") and cross-checked against every label already present in
`scripts/lib/scorers.py` to find real, chain-specific TVL not yet tracked.
Two DefiLlama-listed "UNCX Network V4"/"up v3" leads already flagged open
from prior passes remain open (no new source found for either this pass);
this pass instead surfaced a materially larger, previously-unnoticed gap.

### Arcus Perps BridgeVault -- RESOLVED, new target added

**`Arcus Perps`** (DefiLlama slug `arcus-perps`, `chainTvls["Robinhood
Chain"]` ~$24.13M at time of research) is a DIFFERENT Arcus product from
the already-tracked Arcus pToken family audited above and at index 10 --
`parentProtocol: parent#arcus` links the two on DefiLlama, but they do not
share an on-chain authority chain. Arcus Perps is a dYdX-team-built,
Robinhood-Crypto-partnered perpetual-futures venue (per its own
`arcus.xyz` site) that runs its own validator-consensus settlement layer
bridged into Robinhood Chain.

**Address sourcing.** DefiLlama's `arcus-perps` protocol entry names its
own `tvlCodePath` as `registries/sumTokens.js`, not a per-project adapter
file (`projects/arcus-perp/index.js` 404s). The `sumTokens.js` registry's
own `'arcus-perp'` entry lists `robinhood.owner: '0x14b107cf...da897c'`
(commented only `// bridge`) and 2 tracked tokens (`arcUSDG`, and USDG
itself). Live-confirmed on 2 independent RPCs before doing anything else:
`balanceOf(0x14b107cf...)` on the `arcUSDG` token (symbol/decimals also
read live, not assumed) = 24,131,741.638017 (6 decimals) -- matching
DefiLlama's reported chain-specific TVL within normal snapshot-timing
drift, confirming this is genuinely the right address, not a coincidental
match.

**Root-authority tracing, from scratch, live on 2 RPCs.** The address is a
109-byte proxy (same code length pattern as the Arcus pToken factory at
index 10) whose own `owner()`/`admin()`/`governor()`/`guardian()` all
revert -- but it exposes OZ AccessControl's `getRoleMemberCount()`/
`getRoleMember()`, and its `DEFAULT_ADMIN_ROLE` resolves (identically on
both RPCs) to **three separate contracts**, not one Safe and not one EOA:

| Address | Role (per Arcus's own public repo, see below) | What it actually does |
|---|---|---|
| `0x0dA180B1...caa1001D` | `TimelockController` (real OpenZeppelin) | `getMinDelay()` = 86400s (24h) |
| `0x9d032106...b4e55Da8` | `ValidatorConsensus` | Validator-set + signature-threshold consensus for block acceptance AND arbitrary governance actions |
| `0xA3D46D24...123DF487` | `CheckpointManager` | State-root checkpoint commitments for the L2 |

**Found Arcus's real, official GitHub org this pass**: `github.com/arcus-xyz`
-- confirmed as genuinely theirs (not a similarly-named impostor) via the
org's own public `blog` field, which points to `https://arcus.xyz/`, their
real product site (same verification method already used for
`github.com/uncx-network` at index 10). It publishes
`rootchain-contracts-abis`: ABIs + a `deployments.json` naming Robinhood
mainnet (chain 4663) contract addresses. Critically, **the 3 addresses
above were discovered ON-CHAIN first**, via this scorer's own live
`getRoleMemberCount()`/`getRoleMember()` read against `DEFAULT_ADMIN_ROLE`
-- the GitHub repo was consulted AFTER, to explain facts already found live,
not the other way around. All 3 addresses (plus the BridgeVault address
itself, and a 4th, `BlockExecutor`, found below) match the repo's own
`deployments.json` exactly. Only ABIs are published, not Solidity source --
disclosed explicitly as a real, unresolved gap below, not smoothed over.

**`ValidatorConsensus.threshold()` = 2, `VALIDATOR_ROLE` has exactly 3
members, all confirmed bare EOAs on both RPCs**:
`0xfd2b8e05...9bee51`, `0x19f45260...6D009b`, `0x0f517FD3...52717FF7`.
Its `EXECUTOR_ROLE` has exactly 1 member, `0xA49f3170...664c9e123` -- which
Arcus's own repo names `BlockExecutor` ("Relays the validator vote quorum
on-chain via `executeBlockWithSigs`") -- a narrower, ordinary-checkpointing
role, confirmed distinct from `DEFAULT_ADMIN_ROLE` (not one of the 3
BridgeVault admin holders).

**The critical finding**: `ValidatorConsensus` exposes
`executeGovernanceAction(actionNumber, parentActionHash, calls, deadline)`
where `calls` is an arbitrary `(target, data)[]` list -- i.e. a 2-of-3
validator-signature quorum can direct this contract to call **any**
function on **any** target, gated only by an upper-bound `deadline`
(expiry), not a minimum delay. Since `ValidatorConsensus` independently
holds `DEFAULT_ADMIN_ROLE` on BridgeVault (and `BridgeVault`'s own ABI
exposes exactly ONE role-name constant, `DEFAULT_ADMIN_ROLE()` -- no
`UPGRADER_ROLE`, `OPERATOR_ROLE`, or similar -- strongly suggesting
`DEFAULT_ADMIN_ROLE` itself gates every one of BridgeVault's privileged
functions directly, including `upgradeToAndCall()`, `setWithdrawalsPaused()`,
`setDepositsPaused()`, `grantRole()`), a 2-of-3 validator quorum can reach
BridgeVault's full admin surface with **zero minimum delay**.

The `TimelockController` (the real, 24h one) is also `DEFAULT_ADMIN_ROLE`
on BridgeVault, and was deployed at block 814616 -- hundreds of thousands
of blocks after the other two (~159135-159162), i.e. added as a later
governance layer, not part of the original bootstrap. But its own
`PROPOSER_ROLE`/`EXECUTOR_ROLE`/`CANCELLER_ROLE` (re-derived live,
identical on both RPCs) are held by `ValidatorConsensus` +
`CheckpointManager` (the same 2 contracts) **plus exactly one EOA**,
`0x4f1d777bf36E259F3cB66f2cE969f4c5De05ebe2` -- which is not a new,
Perps-specific individual. That address is one of the 3 owners of the
2-of-3 Gnosis Safe already tracked for the Arcus pToken family (the exact
Safe re-confirmed in Part 1 above and at index 10). A real, live-confirmed
cross-protocol signer overlap between Arcus's two different products.

**Scoring judgment call (disclosed, not smoothed over).** This project's
own `METHODOLOGY.md` states `timelockScore` is "0 if no delay mechanism is
found, **or if one exists but doesn't cover the action that actually
matters** ... scored on the gap, not the presence of a timelock somewhere
in the contract." The 24h Timelock here is real, but does not cover the
action that matters: `ValidatorConsensus` independently holds the identical
`DEFAULT_ADMIN_ROLE` and can reach it via `executeGovernanceAction()` with
no minimum delay. Contrast `score_rollup_l1_authority()` (Robinhood Chain's
OWN L1 bridge), where the "instant" holder is a NAMED, publicly-disclosed
7-of-8 institutional Security Council (Robinhood x2, BitGo, Chainlink Labs,
Fireblocks, Offchain Labs, Paxos, Talos) -- here the instant holder is an
undisclosed 2-of-3 set of bare EOAs functioning as the protocol's own
day-to-day operational key (it is how blocks/checkpoints get finalized at
all), not a break-glass body. Scored on that operative 2-of-3 mechanism
using this project's existing threshold-aware convention (the same formula
already established for `score_morpho_blue_singleton()`/
`score_uncx_v3_locker()`), with `timelockScore = 0` rather than crediting a
delay that doesn't actually constrain the fastest available path.

**Disclosed gap.** Only ABIs are published by Arcus, not Solidity source --
this project's own rule ("a getter/interface succeeding is not evidence of
real gating; only reading the actual source is") means the EXACT role
gating each individual BridgeVault function is inferred (from
`DEFAULT_ADMIN_ROLE` being the only role-name constant its ABI exposes),
not confirmed from source the way UNCX's locker was at index 10. The live
facts this score rests on -- the 2-of-3 threshold, all-EOA validator set,
and the identical `DEFAULT_ADMIN_ROLE` independently held by both
`ValidatorConsensus` and the Timelock -- are chain-verified regardless of
that gap; the inference about exactly which functions it gates is not.

### Score

`adminKeyScore = 50` (2-of-3, threshold-aware convention), `multisigScore =
min(100, 2*15 + 1*5) = 35`, `timelockScore = 0` (see judgment call above) ->
`compositeScore = _composite(50, 35, 0) = 31`.

`crossExposureScore` independently re-derived live via
`compute_cross_exposure()` on both RPCs after wiring a new
`arcus_perps_bridgevault` group into `scripts/lib/signer_overlap.py`
(`known_eoa`: the 3 validator EOAs + the 1 shared Timelock-role EOA;
`targets`: the BridgeVault address): **80**, not 100 -- the shared EOA with
the `arcus` group. This is a real, disclosed correction to the 3 ALREADY-
published Arcus pToken targets too (factory, pBTC 1x, pBTC3x all move from
crossExposureScore 100 to 80; `compositeScore` unchanged at 43 for all 3,
since `compositeScore` does not depend on `crossExposureScore` -- same
mechanic as the PancakeSwap V2/V3 and Steakhouse 4-vault crossExposure
corrections already in this project's history). Grepped
`signer_overlap.py` for all 4 new-group addresses before wiring it in --
none appeared anywhere else; re-ran `compute_cross_exposure()` over the
full, now-32-group registry and confirmed the ONLY entries that moved off
100 beyond the pre-existing ones (`steakhouse` family at 40, PancakeSwap
V2/V3 at 80) are exactly these 4 -- nothing else shifted.

New scorer `score_arcus_perps_bridgevault()` in `scripts/lib/scorers.py`,
added to `SIMPLE_SCORERS`. New signer-overlap group
`arcus_perps_bridgevault` in `scripts/lib/signer_overlap.py`. 4 new unit
tests in `scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`
(`TestScoreArcusPerpsBridgevault`: 2-of-3 happy path, 3-of-N threshold
scaling, `DEFAULT_ADMIN_ROLE` holder-set divergence guard, non-EOA
validator degraded case). Full suite: 522 tests pass (`python3 -m
unittest discover -s scripts/lib/tests`).

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` was
not run this pass (same pre-existing 300-second per-ecosystem timeout gap
for this specific slow ecosystem already documented in `AGENTS.md`). Not
treated as a passing result and not substituted with a fabricated one --
the live 2-RPC re-derivation, the hand-verified expected tuple match
immediately before sending (below), and the full unit-test suite are what
this push's correctness actually rests on, same reasoning as every prior
single-target push in this rotation.

## Push

All 4 entries (3 crossExposure corrections + 1 new target) re-derived live
immediately before sending (`score_arcus_ptoken()` x3 +
`score_arcus_perps_bridgevault()` + a live `compute_cross_exposure()` call)
and compared against hand-derived expected tuples -- all 4 matched
(`compositeScore` computed, not hand-typed), so the send proceeded. Pushed
to the testnet oracle as a single 4-target `updateScores()` call (same
rationale as every prior batch push in this rotation -- avoids a 50min+
full run for 4 targets):

Transaction [`0x0e6d41855d42012f7f8c16db7eb1d90df163b047df2dc5723efc604c134df464`](https://explorer.testnet.chain.robinhood.com/tx/0x0e6d41855d42012f7f8c16db7eb1d90df163b047df2dc5723efc604c134df464),
testnet block 121699881, status 1 (success). `trackedTargetsCount()` went
from 53 to 54. `getScore()` re-read after confirmation:

| Target | Result |
|---|---|
| Arcus pToken factory | `(65, 55, 0, 100, 80, 43)` |
| Arcus pBTC (1x) | `(65, 55, 0, 100, 80, 43)` |
| Arcus pBTC3x | `(65, 55, 0, 100, 80, 43)` |
| Arcus Perps BridgeVault (Robinhood Chain) | `(50, 35, 0, 100, 80, 31)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before sending, balance confirmed non-zero (~0.00986
testnet ETH) on Robinhood Chain Testnet before sending). Robinhood Chain
**mainnet** was only ever read from, never written to; no non-testnet key
was used, generated, or requested at any point in this run.

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as every prior batch push in this rotation -- only a
full, non-dry-run `update_scores.py` run writes it). `getScore()` on-chain
remains the source of truth per this project's own documented convention.

## Rotation state

`last_audited_target_index` advances from 11 to 12 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(12)` from
scratch.

## CORRECTION (2026-09-19, later): the "shared EOA" is a Safe

This document (Part 2 and the score section) calls
`0x4f1d777bf36E259F3cB66f2cE969f4c5De05ebe2` a bare EOA. An independent
re-verification found otherwise, and it was re-read by hand on both Robinhood
mainnet RPCs: the address has 171 bytes of code and is a **2-of-4 Gnosis Safe**.
The crossExposureScore of 80 stands, because the same ADDRESS holds the
timelock's proposer/executor/canceller roles here and is one of the three owners
of the Arcus pToken 2-of-3 Safe. Its four owners (`0x19687776...`,
`0x32aD2818...`, `0x41111c5E...`, `0x95B70f0e...`) are all bare EOAs (0 bytes of
code) and appear in no other tracked signer group, so no further overlap hides
behind it. See
`data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`.
