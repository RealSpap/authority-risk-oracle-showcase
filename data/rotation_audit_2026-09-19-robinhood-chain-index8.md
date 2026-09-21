# Rotation audit (2026-09-19): Robinhood Chain, tracked target index 8, plus 1 new target (Morpho Blue singleton)

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 8
going into this run. Same discipline as every prior rotation audit in this
project: `trackedTargets(8)` read live from the testnet oracle, then every
authority fact re-derived from scratch against two independent RPCs (never
re-read from `scripts/lib/scorers.py`'s own cached logic), compared against
`getScore()`.

## Part 1 -- rotation audit, index 8

`trackedTargets(8)` = `0x00000000000014aA86C5d3c41765bb24e11bd701` -- the
on-chain identity of the target scored as "Ekubo Core". `trackedTargetsCount()`
= 50 going into this run.

### Published score (before this run)

| adminKeyScore | multisigScore | timelockScore | oracleAuthorityScore | crossExposureScore | compositeScore |
|---|---|---|---|---|---|
| 100 | 100 | 100 | 100 | 100 | 100 |

### Independent re-derivation

Two independent read RPCs against Robinhood Chain MAINNET (chain 4663,
read-only): `rpc.mainnet.chain.robinhood.com` and `robinhood.drpc.org`. Raw
`eth_call`/`eth_getCode`/`eth_getStorageAt` made directly with hand-computed
selectors, not through `score_ekubo_core()`.

| Check | RPC A result | RPC B result |
|---|---|---|
| `eth_getCode` length | 18,797 bytes (real deployed code) | identical |
| EIP-1967 implementation/admin/beacon slots | all zero (not a proxy of any kind) | identical |
| `owner()` (`0x8da5cb5b`) | reverts, empty data `0x` | identical |
| `admin()` (`0xf851a440`) | reverts, empty data `0x` | identical |
| `governor()` (`0x0c340a24`) | reverts, empty data `0x` | identical |
| `0xdeadbeef` (fake selector) | reverts, empty data `0x` | identical |
| `swap_6269342730()` (real function, hand-computed selector `0x00000000` -- Ekubo vanity-mines its selectors the same way it vanity-mined this contract's own leading-zero address) | reverts with decoded data `0x9cc3dd4a` | identical |

`0x9cc3dd4a` independently computed (`keccak256("InvalidSqrtRatioLimit()")[:4]`)
against every zero-argument error in `ICore.sol` -- matches `InvalidSqrtRatioLimit()`
exactly, out of 10 candidate errors checked. This reproduces the project's own
"differential test" claim (batch 5, `data/scored_targets_2026-09-15-batch5.md`)
from scratch rather than trusting the docstring: a real function dispatches to
real revert logic (non-empty, decodable error data) while `owner()`/`admin()`/
`governor()`/a garbage selector all hit the EVM's default "no matching
function, no fallback" path (empty revert data) -- confirming the dispatcher
routes correctly and the "authority" selectors genuinely don't exist as
functions, not that they exist and revert for some unrelated reason.

Also independently re-fetched `EkuboProtocol/evm-contracts`' own
`src/interfaces/ICore.sol` from GitHub and grepped it for `owner|admin|upgrade|
governor`: zero matches in the 18-function `ICore` interface (only the routine
mention of `IFlashAccountant`/`IExposedStorage` inheritance) -- confirms the
project's batch-5 source-level claim directly rather than re-citing it.

`crossExposureScore` independently re-run via `compute_cross_exposure()` live
(not read from a cache): **100** -- `ekubo` is its own signer-overlap group in
`scripts/lib/signer_overlap.py` with empty `known_eoa`/`safes` (no authority
surface to cross-reference, by design).

`methodologyHash` on-chain (`0xf2606acd...4133b8975`) independently
recomputed as `keccak256("authority-risk-oracle-v3")` -- matches
`scripts/update_scores.py`'s current `METHODOLOGY_VERSION` exactly, not stale.

### Score check

adminKeyScore/multisigScore/timelockScore are all `100` by architecture (no
authority surface exists at all, not "not applicable"): `_composite(100, 100,
100)` = `100` -- matches the published `compositeScore` exactly. **No
divergence anywhere. No correction needed for this target; nothing pushed for
index 8 itself.**

## Part 2 -- new target search (budget permitted this run)

Rather than re-running the full DefiLlama Robinhood Chain protocol sweep from
scratch (176 protocols, already exhaustively worked through across batches
8-13 and index 7's own pass), this run started from re-checking whether
batch 10's own "already covered" claims actually held up under this
project's "never trust a hand-typed claim without independently re-deriving
it" rule (`AGENTS.md`) -- the same discipline this project's `correction_*.md`
files exist to enforce.

### Morpho Blue (singleton) -- RESOLVED, batch 10's "covered" claim corrected, new target added

`data/scored_targets_2026-09-17-batch10.md` states: *"the Morpho vaults cover
Morpho Blue/Steakhouse Financial"*, closing it out as a non-gap. Re-checked
this directly rather than accepting it: by chain-specific TVL
(`api.llama.fi/protocols`, `chainTvls["Robinhood Chain"]`), **Morpho Blue is
the single largest authority surface on this chain at ~$538M** -- larger than
every other tracked target's TVL combined. The claim conflates two distinct
authority layers:

- A Morpho **vault**'s own `owner()`/`curator()` governs that vault's fund
  allocation *across markets* -- already tracked individually (Steakhouse
  USDG, NetNet Credit, Purinta, Ethena x Steakhouse, Grove x Steakhouse,
  Steakhouse Turbo).
- The **Morpho Blue singleton** itself has its own, separate `owner()` that
  can enable new IRMs/LLTVs (for future markets) and set the protocol fee +
  fee recipient for *every* market on the chain -- including Longbow's 55
  isolated markets, which don't even go through a MetaMorpho/VaultV2 wrapper
  at all. No vault's own score says anything about who controls this. This
  was never actually traced on Robinhood Chain; batch 10's claim was wrong,
  not a genuine non-gap.

Address `0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010` sourced from
`DefiLlama-Adapters/projects/morpho-blue/config.js` (`robinhood` entry,
`fromBlock: 286`) -- the same primary-source convention already used for
every other DefiLlama-adapter-sourced target in this project (e.g. Meridian
Perps, index 7). Confirmed live on 2 independent RPCs, all real deployed code:

| Address | Role | Bytecode size (both RPCs) |
|---|---|---|
| `0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010` | Morpho Blue singleton | 15,582 bytes |
| `0x060595638692de6CCd47ca04094F1772D3D39728` | `owner()` | 171 bytes (Gnosis Safe proxy) |

`owner()` resolves identically on both RPCs to `0x060595638692de6CCd47ca04094F1772D3D39728`.
`feeRecipient()` = zero address on both (no fee currently set -- the same
"fee recipient currently zero" state independently found for Tempo's own
not-yet-coded Morpho Blue scouting entry, `chains/tempo/data/
scouted_targets_2026-09-17-run2.md`, a consistent cross-chain Morpho
deployment default, not a Robinhood-specific anomaly). `owner()` resolves to a
real Gnosis Safe: **5-of-9**, confirmed via live `getOwners()`/`getThreshold()`
on both RPCs (identical owner lists). `getModulesPaginated()` returns empty on
both RPCs; the Safe's guard storage slot (EIP-1967 guard slot) is zero on
both -- no module, no guard.

**Not a new one-off number**: scored with the exact formula this project
already established for this exact same protocol on Base
(`chains/base-ecosystem/scorers.py::score_morpho_blue`, itself carrying the
identical "owner() is scope-limited to future markets, immutable core"
caveat) rather than reusing an unrelated family's formula (e.g. Arcus's
`threshold*25+5`): `adminKeyScore = 65` (threshold >= 3), `multisigScore =
min(100, threshold*15 + extra*5) = min(100, 75+20) = 95`, `timelockScore = 0`
(no TimelockController or Safe guard/module anywhere in this chain).
`compositeScore = _composite(65, 95, 0) = 55`.

`crossExposureScore` independently re-derived live via `compute_cross_exposure()`
after wiring a new `morpho_blue` group into `scripts/lib/signer_overlap.py`
(`safes: ["0x060595638692de6CCd47ca04094F1772D3D39728"]`): **100** -- none of
the 9 Safe owners appear in any other tracked signer-overlap group. Re-checked
that this is the ONLY effect of wiring the new group in: spot-checked 7
pre-existing groups (`ekubo`, `steakhouse`, `spark_savings`, `curve`,
`meridian_perps`, `ramses`, `pendle`) before and after -- every one unchanged
(`steakhouse` still 40, matching the value already corrected in batch 13;
everything else still 100).

New scorer `score_morpho_blue_singleton()` in `scripts/lib/scorers.py`, added
to `SIMPLE_SCORERS`. New signer-overlap group `morpho_blue` in
`scripts/lib/signer_overlap.py`. 4 new unit tests in
`scripts/lib/tests/test_robinhood_vault_and_infra_scorers.py`
(`TestScoreMorphoBlueSingleton`: the confirmed 5-of-9 case matching the Base
sibling's formula exactly, a 2-of-3 case, an unresolved-Safe degraded case,
and a multisig-score-cap regression test). Full suite: 461 tests pass
(`python3 -m unittest discover -s scripts/lib/tests`).

`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` was run
but hit its own 300-second per-ecosystem timeout (a pre-existing tooling
limitation for this specific slow ecosystem -- the same "two slow ones" gap
`AGENTS.md` already documents for the `--skip robinhood-chain,tempo` flag,
not something this pass introduced). Not treated as a passing result and not
substituted with a fabricated one -- the live 2-RPC re-derivation, the
hand-verified expected tuple match immediately before sending (below), and
the full unit-test suite are what this push's correctness actually rests on,
same as index 7's own single-target push used the same reasoning to justify
skipping the 50-minute full `update_scores.py` run.

## Push

Morpho Blue's score re-derived live immediately before sending (via
`score_morpho_blue_singleton()` + a live `compute_cross_exposure()` call) and
compared against the hand-derived expected tuple `(65, 95, 0, 100, 100)` --
matched (`compositeScore` computed as 55, not hand-typed), so the send
proceeded. Pushed to the testnet oracle as a single-target `updateScores()`
call (same rationale as index 7's Meridian Perps push):

Transaction [`0x3d59ce9ef8582dd226f5d12bb1a7c34cca250846c7b1dbc4b333c07e4b4d920e`](https://explorer.testnet.chain.robinhood.com/tx/0x3d59ce9ef8582dd226f5d12bb1a7c34cca250846c7b1dbc4b333c07e4b4d920e),
testnet block 121428547, status 1 (success). `trackedTargetsCount()` went
from 50 to 51. `getScore()` re-read after confirmation:

| Target | Result |
|---|---|
| Morpho Blue (singleton, Robinhood Chain) | `(65, 95, 0, 100, 100, 55)` |

Sent from `0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba` (the
`robinhood-chain-testnet.json` updater key -- `hasRole(UPDATER_ROLE, ...)`
confirmed `True` before sending, balance confirmed non-zero
(~0.00987 testnet ETH) on Robinhood Chain Testnet before sending). Robinhood
Chain **mainnet** was only ever read from, never written to; no non-testnet
key was used, generated, or requested at any point in this run.

`api/scores.json` was **not** regenerated by this push (same documented,
pre-existing gap as index 7 -- only a full, non-dry-run `update_scores.py` run
writes it, which this manual single-target push deliberately did not do).
`getScore()` on-chain remains the source of truth per this project's own
documented convention.

## Leads NOT pursued further

The rest of batch 10's "already covered" list (Uniswap stack, Longbow, Pendle
V2, Curve DEX, Ekubo, Ramses CL V2, PancakeSwap AMM V3, SushiSwap V3,
LayerZero V2, Spark Savings, Symbiosis) was spot-checked against the current
tracked-target list and does hold up -- each is a real, individually-traced
authority root already on this oracle, unlike Morpho Blue's singleton/vault
conflation above. `up v3`, `UNCX Network`, and `Noxa Fun` (flagged open in
batch 12 / index 7 for reasons unrelated to this run) remain open, not
touched this pass.

## Rotation state

`last_audited_target_index` advances from 8 to 9 (see
`authority-risk-oracle-multichain-pipeline/rotation_state.json`, outside
this repo). Next rotation audit should re-derive `trackedTargets(9)` from
scratch.
