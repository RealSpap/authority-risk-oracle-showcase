# Hyperliquid: authority-risk methodology

Status: **promoted to a real scorer 2026-09-17, extended to 3 targets the same day, extended again 2026-09-18 (scoring_build: 7 more targets scored, 5 new methodology rules closed -- see section 7's 2026-09-18 entries). 2026-09-19: 3 of section 6's open questions resolved (no score changed), plus a new scouting find (HIP-4 outcome markets, live on mainnet, 3 deployer venues), later the same day sized, given a scorer (`score_hip4_outcome_deployer`) and put through the adversarial review AGENTS.md requires (15 objections confirmed and applied, 2 refuted), with NO venue promoted and no phase advanced -- see section 4.1's and 4.4's HIP-4 rows, section 6 and section 7's 2026-09-19 entries).**
Discovery output 2026-09-16. Every primitive below is cited to a primary source (official
docs at `hyperliquid.gitbook.io`, the official `hyperliquid-dex` GitHub organization, or a
direct read of the official API / RPC). Snapshot values were read on 2026-09-16 around 17:00
UTC and will drift. Section 4.6's numeric mapping is now live code in
[`scorers.py`](scorers.py) (`score_l1`, `score_xyz_dex`, `score_io_dex`, `score_all`),
reusing `scripts/methodology_test.py`'s already-tested read-and-score functions -- see
[`data/scored_targets_2026-09-17.md`](data/scored_targets_2026-09-17.md) for the
live-verified numbers (xyz/L1 match this document's methodology test exactly; `io` was
added the same day after a live open-interest sweep found it, not `flx`, is the genuine
second-most-used HIP-3 dex -- see that file for why). Nothing has been pushed on-chain yet
(no testnet/devnet oracle deployed for Hyperliquid).

Scale convention is the repo's existing one (`src/AuthorityRiskOracle.sol`):
every sub-score is 0-100, higher is safer, and a dimension that genuinely does not
apply scores 100.

## 1. Two layers, one consensus

| Layer | What it is | Can third parties deploy code? | Source |
|---|---|---|---|
| HyperCore | Native exchange state machine (margin, order books, staking, spot tokens, vaults), executed by the L1 node binary | No. Only native, typed actions (`spotDeploy`, `perpDeploy`, `CValidatorAction`, ...) | [Overview](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/overview.md), [HIP-3 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions.md) |
| HyperEVM | EVM blocks built inside the same L1 execution, "not a separate chain" | Yes, standard EVM contracts | [HyperEVM](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperevm.md) |

Consequence: "smart contract admin key" only exists on HyperEVM. On HyperCore, the
authority objects are (a) the L1 itself (validator set plus node binary), and
(b) per-market deployer accounts created by HIPs, which are ordinary HyperCore
users that may or may not be native multisigs.

## 2. Networks and endpoints (confirmed)

| Network | HyperEVM chain id | EVM JSON-RPC | HyperCore API | Source and live check |
|---|---|---|---|---|
| Mainnet | 999 (`0x3e7`) | `https://rpc.hyperliquid.xyz/evm` | `https://api.hyperliquid.xyz/info` | [docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm.md), `eth_chainId` returned `0x3e7` |
| Testnet | 998 (`0x3e6`) | `https://rpc.hyperliquid-testnet.xyz/evm` | `https://api.hyperliquid-testnet.xyz/info` | same docs page, `eth_chainId` returned `0x3e6` |

Notes that change how scorers must be written:

- The default RPC serves `eth_call`, `eth_getCode` and `eth_getStorageAt` for the
  latest block only, and `eth_getLogs` over at most 50 blocks
  ([JSON-RPC](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm/json-rpc.md)).
  Event-history scans need an archive node or chunked queries.
- HyperCore has no third-party RPC market. The independent second source for
  HyperCore reads is a self-run non-validator with `--serve-info`, which supports
  `perpDexs`, `userToMultiSigSigners`, `validatorL1Votes`, `delegations` and more
  ([node README](https://github.com/hyperliquid-dex/node/blob/main/README.md)).
  Until one is run, HyperCore facts in this file rest on a single operator's API
  plus the docs, and are labeled as such.
- Testnet is a separate validator set (250 registered, 96 active on 2026-09-16 via
  `validatorSummaries` on the testnet API), so testnet deployments demonstrate
  mechanics only, never mainnet authority.
- The testnet faucet requires a prior mainnet deposit from the same address
  ([Testnet faucet](https://hyperliquid.gitbook.io/hyperliquid-docs/onboarding/testnet-faucet.md)).
  This is a blocker to note for any HyperEVM testnet deployment with the shared
  throwaway key.

## 3. Real authority primitives

### 3.1 L1 logic upgrades (HyperCore and HyperEVM system contracts)

| Fact | Source |
|---|---|
| Validators run `hl-visor`, which downloads `hl-node`, verifies it against the GPG key `pub_key.asc` in the official repo, and "will not upgrade on verification failure", i.e. upgrades are pulled automatically when a signed binary is published | [node README](https://github.com/hyperliquid-dex/node/blob/main/README.md) |
| The official `hyperliquid-dex` org publishes the node packaging (`Dockerfile`, `pub_key.asc`, pruner) but no `hl-node` source repository | [GitHub org repo list](https://api.github.com/orgs/hyperliquid-dex/repos) |
| No minimum notice period for network upgrades is documented; docs only mention a "post-only period of a network upgrade" | [llms-full.txt](https://hyperliquid.gitbook.io/hyperliquid-docs/llms-full.txt) |
| HyperEVM system contracts (CoreWriter `0x3333...3333`, HYPE bridge `0x2222...2222`, WHYPE `0x5555...5555`) are fixed bytecode, changeable only by an L1 upgrade; WHYPE is documented immutable | [Interacting with HyperCore](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm/interacting-with-hypercore.md), [Wrapped HYPE](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm/wrapped-hype.md), `eth_getCode` on both networks (544, 122, 2041 bytes) |

Interpretation: the effective "admin key" of HyperCore is the binary signing key
held by the core contributors, gated by validator adoption of the signed binary.
The consensus-level check is that a >2/3 stake quorum must run it.

### 3.2 Validator set and quorum

| Fact | Source |
|---|---|
| HyperBFT (HotStuff variant); a quorum is any validator set with more than 2/3 of stake | [Staking](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/staking.md) |
| Active set is the top 27 by stake; running a validator is permissionless; 10k HYPE self-delegation locked one year | [Running a validator](https://hyperliquid.gitbook.io/hyperliquid-docs/validators/running-a-validator.md), [Staking](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/staking.md) |
| The Foundation delegates stake to chosen validators and "reserves the right to cease delegation at any time" (KYC/KYB required) | [Delegation program](https://hyperliquid.gitbook.io/hyperliquid-docs/validators/delegation-program.md) |
| No automatic slashing of validators; jailing by quorum vote | [Staking](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/staking.md) |
| Live mainnet read: 35 registered, 27 active. Five validators self-named "Hyper Foundation 1..5" hold 47.98% of active stake. 3 validators exceed 1/3 of stake, 8 exceed 2/3 | `validatorSummaries` on `api.hyperliquid.xyz` |

Caveat before qualifying: validator names are self-set via `changeProfile`
([node README](https://github.com/hyperliquid-dex/node/blob/main/README.md)), so
the "Hyper Foundation" label is a claim by the key holder, consistent with the
docs' reference to "Foundation validators" but not independently proven. Mitigating
context: 47.98% is below both the 2/3 quorum and a simple majority, so the
Foundation-labeled set alone can halt liveness (>1/3) but cannot finalize alone.

### 3.3 Native multisig (HyperCore)

| Fact | Source |
|---|---|
| Multisig is a protocol primitive: `ConvertToMultiSigUser` sets authorized users and threshold; all later actions must be wrapped in `MultiSig`; max 10 authorized users | [Multi-sig](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/multi-sig.md) |
| Signer set and threshold are updated by a `MultiSig`-wrapped `ConvertToMultiSigUser`, with no delay documented | same |
| Converting to multisig "still leaves the HyperEVM user controllable by the original wallet" | same |
| Readable via info request `userToMultiSigSigners`, returning `{authorizedUsers, threshold}` or `null` | [node README](https://github.com/hyperliquid-dex/node/blob/main/README.md), live API read |

This is the HyperCore equivalent of `getOwners()` / `getThreshold()` on a Safe.

### 3.4 Delays

| Mechanism | Delay | Governs | Source |
|---|---|---|---|
| L1 binary upgrade | none documented | all HyperCore logic | 3.1 above |
| Multisig signer change | none documented | any HyperCore multisig user | [Multi-sig](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/multi-sig.md) |
| Staking to spot transfer | 7 days | exit of staked HYPE, keeps slashable stake in reach | [Staking](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/staking.md) |
| Validator epoch | 100k rounds (about 90 min) | validator set changes | same |
| HIP-3 deployer stake | 500k HYPE, kept at least 183 days | slashing collateral, not an action delay | [HIP-3](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals.md) |
| HIP-3 `setOracle` | at least 2.5 s between calls, no queue | deployer price pushes | [HIP-3 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions.md) |
| HIP-3 `haltTrading` | immediate, settles to mark price | deployer market halt | [HIP-3](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals.md) |
| Legacy Arbitrum bridge dispute period | `disputePeriodSeconds() = 200`, `lockerThreshold() = 2`, `epoch() = 7` | withdrawals and bridge validator set updates | [Bridge2.sol](https://github.com/hyperliquid-dex/contracts/blob/master/Bridge2.sol), `cast call` on two Arbitrum RPCs |

### 3.5 Oracle authority

| Market family | Who sets the price | Source |
|---|---|---|
| Validator-operated perps | Each validator computes a weighted median of 8 venues; the clearinghouse uses the stake-weighted median of validator submissions | [Oracle](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/oracle.md) |
| HIP-3 perps | The dex deployer, its `oracleUpdater`, or any sub-deployer allowed for the `setOracle` variant; validators can slash the 500k HYPE stake by stake-weighted vote | [HIP-3](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals.md), [HIP-3 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions.md) |
| Delisting, quote-asset status, aligned-quote-asset rate | Validator vote | [Delisting](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/delisting.md), [Aligned quote assets](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/aligned-quote-assets.md) |

### 3.6 Legacy USDC bridge on Arbitrum

`Bridge2` at `0x2df1c51e09aecf9cacb7bc98cb1742757f163df7` (address given in the
official docs). Not a proxy (EIP-1967 implementation slot is zero). All admin paths
(`changeDisputePeriodSeconds`, `invalidateWithdrawals`, `changeLockerThreshold`,
`emergencyUnlock`) require validator signatures with `3 * power > 2 * totalPower`
against the hot or cold validator set hash. Docs say it holds less than 10% of
HyperCore USDC and is deprecated in favor of Circle CCTP
([USDC](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/usdc.md)). Live
read: 446,417,470 USDC (`balanceOf` on native Arbitrum USDC).

### 3.7 HyperEVM-native smart contract admin keys (first real target 2026-09-17)

Section 1's own framing ("smart contract admin key only exists on HyperEVM")
was true in principle since this document's first draft (see 4.1's own
"HyperEVM contract" row, already anticipating "reuse `scripts/lib/
scorers.py` patterns"), but had no real target exercising it until
Kinetiq's `HIP3StakingManager` was found and scored (`data/
methodology_test_2026-09-17-kinetiq-staking-manager.md`) -- surfaced as a
byproduct of investigating whether a HIP-3 dex deployer address that also
carries HyperEVM bytecode exposes a second, EVM-side root-control path
(see `data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md` for
that separate, corrected investigation).

**The general risk this raises for ANY future target**: `CoreWriter`
(`0x3333...3333`, section 3.1's table) lets a HyperEVM smart contract send
a HyperCore-native action, and Hyperliquid's own docs confirm the
resulting action is attributed to the CALLING CONTRACT'S OWN ADDRESS, not
the EOA that triggered it. This means a HyperCore-native address (a HIP-3
deployer, a multisig user, anything with `userToMultiSigSigners`) that
ALSO turns out to carry HyperEVM bytecode must have that bytecode's actual
logic checked, not assumed benign just because it's "only EVM-side code" --
read the contract's VERIFIED SOURCE if available (a block explorer's
Source Code tab), not just its bytecode's presence of a system-contract
address, which is necessary but not sufficient evidence (this project's
own first attempt at this exact question overclaimed for exactly this
reason, then corrected itself the same day).

**Reading a HyperEVM Gnosis Safe / OpenZeppelin AccessControl authority
chain**: standard EVM primitives, read via plain `eth_call`/
`eth_getStorageAt` against `https://rpc.hyperliquid.xyz/evm` (no
HyperCore-specific API involved at all once you're past a plain HyperEVM
address) --

| Read | Selector / slot | Notes |
|---|---|---|
| EIP-1967 proxy admin/implementation | `keccak256("eip1967.proxy.admin") - 1` / `...implementation" - 1` | Do NOT call a transparent-proxy `admin()`/`implementation()` getter directly -- those revert unless called BY the current admin; read the storage slot instead. |
| Safe owners/threshold | `getOwners()` (`0xa0e67e2b`) / `getThreshold()` (`0xe75235b8`) | Same facts as HyperCore's own `userToMultiSigSigners` (3.3), different chain. |
| Safe modules/guard | `getModulesPaginated(address,uint256)` (`0xcc2f8452`) / `keccak256("guard_manager.guard.address")` (no `-1`, unlike EIP-1967's own slot convention) | A non-empty module list or non-zero guard means the raw threshold no longer describes who can act -- same caveat this project's Robinhood Chain scorer already documents. |
| AccessControl role members | `getRoleMemberCount(bytes32)` (`0xca15c873`) / `getRoleMember(bytes32,uint256)` (`0x9010d07c`) | Only works if the contract uses OpenZeppelin's `AccessControlEnumerable` (not plain `AccessControl`, which has no on-chain member list); `DEFAULT_ADMIN_ROLE` is always `bytes32(0)`. |

**A caught bug, disclosed rather than silently fixed**: a first attempt at
computing these selectors via `Web3.keccak(text=sig).hex()[2:10]` silently
produced every selector shifted by one byte -- this project's own web3.py
version's `HexBytes.hex()` does not include a `"0x"` prefix (unlike
`str(HexBytes(...))`), an assumption never checked before use. Caught by
comparing the computed `getOwners()` selector against a value already
confirmed correct by hand earlier in the same investigation, before
committing the selector helper into scorer code.

**Check every role an `AccessControlEnumerable` contract defines, not just
the one that resolves cleanest**: Kinetiq's `HIP3StakingManager` itself is
the cautionary example. A first pass checked only `DEFAULT_ADMIN_ROLE`,
found a well-formed 4-of-8 Safe with no module or guard, and (wrongly)
generalized "the other roles must be similarly benign" without checking
them. They weren't: `OPERATOR_ROLE` turned out to be held by a bare EOA,
and `TREASURY_ROLE` by a SEPARATE Safe sharing only 1 of 7 owners with the
"root" one -- see `data/methodology_test_2026-09-17-kinetiq-staking-
manager.md`'s own correction section for the full account. Section 6.2's
minimum-over-full-power-paths convention applies here exactly as it does
to a HyperCore target with several authority addresses: enumerate every
role, classify every current holder, and let the weakest one bind.

**A UUPS proxy's EIP-1967 admin slot reading zero is NOT evidence of "no
admin" -- only of "not a transparent proxy"**: HIP-3 dex `para`'s own
EVM-side proxy is the cautionary example, this time caught the SAME day
before it was ever taken as final rather than after a publish. A first
read of that proxy's zero admin slot concluded "consistent with an
IMMUTABLE proxy." Wrong: the EIP-1967 ADMIN slot is a TRANSPARENT-proxy
convention only (`TransparentUpgradeableProxy` + a separate `ProxyAdmin`
contract); a UUPS proxy (`UUPSUpgradeable`) never touches that slot at
all -- its upgrade authority lives inside the implementation's own
`_authorizeUpgrade` override, gated however that specific contract
chooses (an `onlyOwner` check, a role check, anything). Reading the admin
slot alone cannot distinguish "immutable" from "UUPS, real admin
elsewhere" -- only reading the implementation's own verified source (or,
short of that, probing `upgradeToAndCall`'s revert behavior) can. Full
account: `data/methodology_test_2026-09-17-para-staking-vault.md`.

**A second, independently-written HyperEVM access-control pattern,
generalizing the same methodology**: `para`'s own StakingVault defers
ALL access control to a separate `RoleRegistry` contract using Solady's
`EnumerableRoles` (`roleHolders(bytes32)` -- one call returns the full
holder array) plus `Ownable2StepUpgradeable`'s own `owner()`, rather than
OpenZeppelin's `AccessControlEnumerable` Kinetiq uses. Different
selectors, different ABI shape, same underlying discipline: enumerate
every role AND the plain `owner()` slot, classify every holder (Gnosis
Safe / bare EOA / unresolved contract), take the minimum. That this
generalizes cleanly to a second, unrelated implementation on the same day
is itself useful evidence the methodology isn't overfit to Kinetiq's one
contract.

**An RPC-level revert must degrade gracefully, not crash**: calling a
Safe-shaped selector (`getOwners()`) against a contract that ISN'T a Safe
(here, `para`'s `MANAGER_ROLE` holder -- itself a plain EIP-1967 proxy
delegating to something else entirely) returns a JSON-RPC error object,
not a malformed-but-present `result`. The read helper's own `evm()`
wrapper originally did a bare `["result"]` lookup, crashing with an
opaque `KeyError` instead of raising a catchable error the same way an
already-handled malformed response does. Fixed by adding a distinct
`HyperEvmRpcError`, raised explicitly when the RPC response carries no
`result` key -- `_classify_authority_holder` catches it identically to
`HyperEvmReadError`, degrading to the same conservative unresolved-
contract fallback (20/0/0) either way.

**An `owner()`-style slot reading the zero address means renounced --
the SAFEST state, not a weak key**: matches this project's own
`none_means_renounced` convention already fixed on the Solana side the
same day (Drift Protocol correction: a renounced upgrade authority was
scoring as a false MISMATCH instead of the safest band). `_classify_
authority_holder` gained the same flag, scoped ONLY to genuine
`owner()`/`Ownable`-style slots -- never to an enumerated role holder
list, where a zero address would be corrupt data, not a deliberate safety
signal.

**A `roleRegistry()` getter succeeding is NOT evidence a contract's
gating actually uses it -- only reading verified source is.** Found
2026-09-18 while promoting a THIRD HyperEVM target, Ventuals vHYPE
staking (found the same way as `para`'s and Kinetiq's own -- a dormant
HIP-3 dex's deployer address carrying live HyperEVM infrastructure): its
`MANAGER_ROLE` holder is itself a verified contract (`StakingVaultManager`)
whose OWN upgrade authority and every privileged admin function were
confirmed, by actually reading its source, to be gated by the SAME
`roleRegistry.owner()` Safe that already roots the other paths. This
resolution is deliberately NOT automated into a general rule ("any
contract whose `roleRegistry()` call succeeds shares its registry's
authority") -- a malicious or careless implementation could expose that
getter as a public state variable without using it for any actual access
control, so a bare successful call proves only that the value is
readable, not that it is enforced. `para`'s own analogous `MANAGER_ROLE`
holder is NOT verified and correctly stays at the conservative
unresolved fallback (20/0/0) for exactly this reason -- the two targets
are structurally identical, and score very differently (4 vs. 31) purely
because one operator published verified source for every layer and the
other didn't. This is the same "necessary but not sufficient evidence"
discipline this project's own earlier CoreWriter/Kinetiq overclaim
(since corrected) should have applied from the start, now applied
symmetrically in both directions -- neither assuming a plausible-looking
interface implies real gating, nor assuming an unverified contract must
be malicious, just unknown.

## 4. The five dimensions, translated

### 4.1 adminKeyScore

| Target type | Hyperliquid meaning | Scoring rule |
|---|---|---|
| HyperEVM contract | Unchanged: EOA / Safe / timelock owner | Reuse `scripts/lib/scorers.py` patterns against chain 999 |
| HyperCore L1 (single target) | Binary signing key plus validator adoption, closed source node | Score low (15): a single publisher key, auto-pull by `hl-visor`, no public source to audit a release against. Not 0 because a >2/3 stake quorum must actually run it |
| HIP-3 perp dex | Root = `deployer` (it grants and revokes `subDeployers` per action variant; `setFeeRecipient` and `haltTrading` are deployer actions) | Ladder of 4.6 applied to the weakest key (rule 4.2) of the root-control set `{deployer} + subDeployers[haltTrading]`, not to the deployer alone: a single-key `haltTrading` sub-deployer can settle every position at mark without the deployer multisig |
| HIP-1 spot token | Spot deployer: fee share (can only decrease), quote-token enable/disable, EVM link request | Lower weight: no freeze or mint privilege is documented after genesis |
| **HIP-3 deployer that is itself a HyperEVM contract** *(added 2026-09-18)* | `userToMultiSigSigners(deployer)` reads `null`, which the generic rule above would read as "single key" -- wrong when the deployer address carries HyperEVM bytecode. The address's real HyperCore-identity authority is whatever on-chain role gates the CoreWriter action-9 call (`addApiWallet`), not a bare key | Resolved PER TARGET by reading the deployer's verified source (never auto-generalized -- see 3.7's own `roleRegistry()` caution), then scoring the resolved role-holder's `(k, n)` under the SAME 4.6 ladder as any other HyperCore multisig. Live example, `para`: `addApiWallet` is `onlyOperator`; `OPERATOR_ROLE` resolves to a Safe with threshold=1 over 3 owners (2 bare EOAs + a nested 1-of-1 Safe, itself no stronger than a bare key) -- a genuine `(k=1, n=3)`, WEAKER than the naive "single key" `(1,1)` reading (rule 4.2.1: a 1-of-N with N>1 is strictly weaker than one key). `mkts` needed no override: its resolved root (`exWalletAdmin`, a bare EOA) happens to coincide with the generic single-key reading -- confirmed live, not assumed. Applied as a post-processing correction in `scorers.py::_apply_hyperevm_identity_overrides`, not inside `score_hip3_dex` itself (keeps the override list explicit and auditable in one place, the same architectural choice already made for `_apply_l1_cap`) |
| **HyperCore vault leader** *(added 2026-09-18)* | A vault's `leader` key controls trading and capital allocation across every depositor's pooled funds, but (per Hyperliquid docs and a live `leaderCommission=0` check) cannot withdraw depositor funds to itself -- a real but categorically DIFFERENT kind of power than a HIP-3 deployer's or a spot treasury's (which can redirect value directly) | Still scored, not marked "not applicable": a compromised leader key can still destroy real value through bad-faith trading or backstop-liquidation decisions, and a multi-day deposit lock (4 days for HLP) means depositors cannot exit ahead of a developing episode. Uses the SAME single-key ladder as any bare HyperCore key (`admin_key_score`/`key_score` at the leader's own `(k, n)`) -- no separate "vault leader" bonus or penalty invented; the distinction from custody-bearing targets is disclosed in `notes`, not encoded as a different formula |
| **HIP-1 spot treasury holding unissued supply** *(added 2026-09-18)* | HIP-1 has no mint after genesis, so the HyperCore address still holding the un-distributed genesis balance controls, in practice, new supply -- tokens it releases are indistinguishable on chain from already-backed ones | Scored on the TREASURY address's own `(k, n)` (a DIFFERENT address than the token's deployer) under the standard ladder. Where a project's docs claim an off-chain MPC/threshold scheme the chain itself cannot see (Unit: "2-of-3 MPC, Unit + Hyperliquid + Infinite Field"), score the CONSERVATIVE on-chain fact (a plain HyperCore single key, `userToMultiSigSigners` reads `null`) and record the documented-but-unverifiable claim as mitigating context in `notes` -- the SAME choice this document already makes for the L1's "Hyper Foundation"-labeled validators (3.2), applied here for consistency rather than inventing a new resolution rule per target type |
| **HIP-4 outcome-market deployer** *(proposed 2026-09-19; adversarial review ran, see section 7; scorer written, no venue promoted)* | Root = `deployer` plus every sub-deployer holding `settleOutcome` or `settleQuestion` (the grant that authorizes `settleQuestion2`): they decide how an outcome's locked collateral (1 Yes + 1 No = 1 USDC) is split between holders, so a compromised settle key can redirect it, for that venue's own book only. `setSubDeployers` is deployer-only, so the deployer always stays in the set (same reasoning as rule 4.2.3). The three registration variants are left out of the set by analogy with HIP-3's non-halt sub-deployer variants (`registerAsset`, `setDeployerFees`), NOT because they are known to be harmless: per the official page they create markets, set `deployerFeeScale` in [0, 10] on new markets (user fee up to 20x the base rate) and can add outcomes to a live question, and none is documented to decide who receives already-locked collateral; a venue with such keys carries a sensitivity block showing its score if they were counted. A non-empty sub-deployer grant outside the five documented names makes the scorer raise instead of guessing | The ladder of 4.6 applied to the weakest key (rule 4.2) of that set, exactly as for a HIP-3 dex: `admin_key_score`, `key_score`, `composite`, no new formula. `timelockScore` 0: no delay is documented on `settleOutcome`, `settleQuestion2` or `setSubDeployers`, and slashing (documented only for markets that contradict their template's semantic restriction) is context, never credited as a deterrent for settlement. `oracleAuthorityScore`: see the HIP-4 row of 4.4. Nested multisig signers are disclosed (`reads.nestedMultisigSigners`) and not expanded, per rule 4.2.2. Live 2026-09-19: all three venues (`out` 3-of-4, `txyz` 2-of-3, `skew` 3-of-5) land on a bare-key sub-deployer, 10/15/0/15, composite 9; `txyz` also shares its three deployer signers with HIP-3 dex `xyz` (`crossExposureScore` 80); `out`'s deployer is a nested, cyclic multisig. **Not promoted**: locked collateral ($1.19M / $0.40M / $8K) is below the written scouting rule of about $5M of TVL or open interest (`data/scouted_targets_2026-09-17-run2.md`, a scouting rule, not a promotion rule) and below the lightest promoted dex (`mkts`: about $6.4M to $6.7M of open interest at promotion, $7.7M re-read 2026-09-19); sizing, decision, the sensitivity that would flip `out` (an outcome-specific floor at about $600K or below) and the review record are in `data/scored_targets_2026-09-19-hip4-outcome-deployers.md`; code in `scripts/scoring_build_2026_09_19_hip4.py` |

### 4.2 multisigScore

Read `userToMultiSigSigners` for every authority address and map it to a pair
`(k, n)` = (threshold, number of authorized users). Rules:

1. Single keys. `null` (a plain single-key user) maps to `(1, 1)`. A native
   multisig with threshold 1 and exactly one authorized user is also `(1, 1)`:
   it is one key, scored the same as a bare EOA. Only a 1-of-N with N > 1 is
   strictly worse than one key, because any one of N keys can act alone.
2. Ordering between two k-of-n. Compare the threshold `k` first: lower `k` is
   weaker. On equal `k`, larger `n` is weaker (more key combinations can reach
   the threshold). So the weakest key of a set is the minimum by the sort key
   `(k, -n)`. Example order, weakest first: 1-of-6, 1-of-4, single key (1-of-1),
   2-of-3, 3-of-6, 3-of-5, 4-of-8, 4-of-6. Nested multisigs (a signer that is
   itself a multisig) are not expanded at this phase.
3. Authority set of a sensitive action. It is the deployer, plus every
   sub-deployer listed for that action variant in `perpDexs.subDeployers`, plus,
   for `setOracle` only, the `oracleUpdater`. When `oracleUpdater` is empty, the
   deployer is the oracle updater, per the SDK comment in the official docs:
   "If not provided, then deployer is assumed to be oracle updater"
   ([HIP-3 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions.md)).
   The deployer is always kept in the set, even when a separate `oracleUpdater`
   is designated: whether it can still call `setOracle` directly is not stated in
   the docs, but it can reassign `subDeployers` (`setSubDeployers`) at any time
   and so reach the action anyway. Sub-deployers bypass a strong deployer
   multisig.
4. The effective key of the action is the weakest member of that set under rule 2.

Live example (2026-09-16, `perpDexs` plus `userToMultiSigSigners`, recomputed with
the three rules above by one script, see section 5):

| Dex | Deployer | Weakest `setOracle` key | Weakest `haltTrading` key | Assets |
|---|---|---|---|---|
| xyz | 2-of-3 | 1-of-6 | single key | 120 |
| flx | 2-of-3 | 1-of-4 | 1-of-4 | 15 |
| vntl | single key | 1-of-4 | single key | 15 |
| hyna | 4-of-8 | single key (1-of-1 multisig `oracleUpdater`) | 4-of-8 | 24 |
| km | single key | single key | single key | 22 |
| abcd | single key | single key | single key | 0 |
| cash | 3-of-6 | single key | single key | 15 |
| para | single key | single key | single key | 27 |
| mkts | single key | single key | single key | 4 |
| io | 3-of-5 (deployer) | 3-of-5 (deployer, weaker than the 4-of-6 `oracleUpdater`) | 2-of-3 | 6 |

Where a column reads the deployer value, no weaker delegate exists for that action.
For the L1 target, the "multisig" is the validator stake distribution: score from
the number of distinct **entities** needed to exceed 1/3 (liveness veto) and 2/3
(finality). Validators whose self-set names share an operator prefix (today
"Hyper Foundation 1..5") are merged into one entity, because merging can only lower
the score (the conservative direction for an unproven label). Today: 3 and 8
validators, but 1 and 4 entities (see 4.6 and the 2026-09-16 test).

For a HIP-3 dex, multisigScore uses the same root-control set as adminKeyScore
(4.1). `setOracle` is scored only in 4.4, to avoid counting the same key twice.

### 4.3 timelockScore

HyperCore has no timelock primitive. What replaces it:

- For deployer actions (`setOracle`, `haltTrading`, `setSubDeployers`) and multisig
  signer changes: no delay exists, score 0 unless a delay is proven.
- The only deterrent in place of a delay is ex-post slashing (HIP-3 500k HYPE,
  7-day unstaking queue keeps it slashable; HIP-3 only: for HIP-4 the docs document
  slashing solely for malformed markets, so it is never credited there, see 4.1). It is recorded as mitigating context in
  `notes`, not as a timelock, because it does not give users an exit window before
  the action lands.
- For the L1 target: no documented upgrade notice, score 0 until a primary source
  shows otherwise.
- For the legacy bridge: 200 s dispute period with locker veto, low but non-zero. **Numeric value fixed 2026-09-18** (this section previously left it unassigned): `timelockScore = 15`, live-confirmed (`disputePeriodSeconds()=200`, `lockerThreshold()=2`) -- reuses `scripts/lib/scorers.py`'s own "present but short/weak" floor value (distinct from the 60 this project uses for a confirmed multi-day `TimelockController`, e.g. Radiant's 72h on Arbitrum), since 200 s is real protection but far short of that tier.
- HyperEVM contracts: unchanged EVM method (TimelockController, Safe modules). **A HyperEVM target governed by TWO independent `TimelockController`s of different length** (HyperLend Pooled, added 2026-09-18: a 7-day timelock for `POOL_ADMIN`/logic upgrades, a 6-hour timelock for `RISK_ADMIN`/`ASSET_LISTING_ADMIN`, both proposed by the same Governance Safe and executed by the same, separate, no-shared-owner Treasury Safe) is scored on the WEAKER path (6h -> `timelockScore=35`, a middle tier already used elsewhere in this project for "real delay, shorter than the usual multi-day tier", e.g. `scripts/lib/scorers.py::score_snuggle_maxfi_vault`), per 6.2's minimum-over-paths convention. The genuine AND-composition (proposer and executor are different Safes sharing no owner, live-checked; `openExecutor(address0)=false` so execution is not open to anyone) is disclosed as mitigating context in `notes`, not folded into a new formula -- this project has no prior numeric convention for scoring two independent Safes required together any higher than the weaker member alone, and this pass's time budget did not include calibrating one.

### 4.4 oracleAuthorityScore

| Target | Rule |
|---|---|
| Validator-operated perps | Stake needed to move a stake-weighted median: minimum entities (merged as in 4.2) with over 50% stake. Today the Foundation-labeled set holds 47.98%, so the Foundation-labeled set plus any one of the next largest validators (7.04%) could move it |
| HIP-3 dex | Weakest `setOracle` key from 4.2. This is the dimension where HyperCore is most distinct: the price is a direct deployer push, not a signed report checked on chain. Protocol clamps from the `SetOracle` doc comment (markPx moves at most 1% from the previous markPx per update, at least 2.5 s between updates, all prices within 10x of the start-of-day value) bound the speed of a move, not its direction, and are recorded in `notes`, not in the score: at 1% per 2.5 s a mark price can be halved in 69 updates, about 3 minutes |
| HIP-4 outcome venue *(proposed 2026-09-19, held)* | Weakest key (rule 4.2) of the settle root-control set of 4.1, the same key as `adminKeyScore`. The analogy with the HIP-3 row is partial: `setOracle` is a continuous push that the protocol clamps (above), while a settlement (`settleOutcome`, `settleQuestion2`) is a one-shot, unclamped decision inside documented bounds only: `settleFraction` is a decimal in [0, 1], exactly 0 or 1 with one winner for outcomes of a question, `nameAndDescription`/`sideNames` must match, and only the deployer's own book is reachable. Not documented: any delay, any check of the value against the market's underlying, any bound on when a settle may happen, any dispute step. Read-only on-chain history (`data/scored_targets_2026-09-19-hip4-outcome-deployers.md` section 8) shows the two absences are real: successful settles more than an hour before a market's stated time, and 15 Yes/No `binaryPrice` markets settled at 0.5. No on-chain check is credited. The 8 protocol-run recurring outcomes (no venue, settled by the protocol per the official page) are outside this row. `oracleAuthorityScore` is not a `composite()` input |
| HyperEVM consumers | Contracts reading HyperCore prices through the read precompiles (`0x...0800` and up) inherit the upstream score of the perp or spot market they read |
| **Liquid-staking `OracleManager` operator push** *(added 2026-09-18, closes the gap 3.7/6 left open: "the morning draft's single number (oracle 15 for both) does not separate these two cases")* | A single EOA (`OPERATOR_ROLE`) can push a reward/slash report at most once per validator per `MIN_UPDATE_INTERVAL` (86,400 s, live-confirmed for both Kinetiq kHYPE and kmHYPE) -- the base rate is the same `key_score(1,1)=15` any bare single key gets. What differs is whether a `ValidatorSanityChecker` BOUNDS the size of each push: kHYPE's checker caps each report at 3 bps reward / 1 bps slash of the validator's balance and rejects a balance more than 300 bps from the HyperCore-precompile-read delegation (`oracleAuthorityScore=15`, unchanged from the single-key floor -- the SIZE cap is exactly what makes a compromised single key survivable). kmHYPE has NO sanity checker (`sanityChecker() == address(0)`, live-confirmed) -- unbounded, a compromised operator can move the exchange rate by an arbitrary amount in one push (`oracleAuthorityScore=7`, a 50% penalty off the bounded floor -- a fresh judgment call for this rule, not previously calibrated against this project's other 4.6 numbers, disclosed as such in `scripts/scoring_build_2026_09_18.py::_kinetiq_oracle_authority_score` and worth revisiting if a sharper quantification is found later) |

### 4.5 crossExposureScore

Same idea as the existing signer-overlap logic, applied to HyperCore users:

- Signer overlap across multisigs. Live example: `0x4285...51b9` signs for both the
  flx deployer and the io deployer; five addresses sign for both `0x9475...fedd5`
  (oracle updater for flx and io, 4-of-6) and `0xaffd...bc2f` (hyna `setOracle`
  sub-deployer, 4-of-6), so those five signers alone meet the threshold of both.
- One oracle updater serving several dexes (`0x9475...fedd5` for flx and io) is a
  shared oracle root.
- Cross-layer bypass: a HyperCore multisig does not protect the same address on
  HyperEVM, where the original key still controls it
  ([Multi-sig](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/multi-sig.md)).
  Any target with roles on both layers is scored on its weaker side.
- Validator-level exposure: every HIP-3 slashing, delisting and quote-asset vote
  resolves to the same validator stake, so the L1 score caps every HyperCore
  target -- and, since HyperEVM's own blocks are built inside the same L1
  consensus (section 1), every HyperEVM-native target too (applied uniformly by
  `score_all()`'s own loop, not a HyperCore-specific special case; confirmed
  live for HIP-3 dex `io`, where the L1 cap actually binds: `l1CappedComposite
  = min(32, 26) = 26`. Kinetiq's `HIP3StakingManager`, section 3.7, was
  originally cited here as a second binding example at `compositeScore=50`,
  but its corrected score, `compositeScore=4` after accounting for every
  `AccessControlEnumerable` role rather than just `DEFAULT_ADMIN_ROLE`, is
  already below the L1's 26 -- the cap has no effect on it).
  Concretely: `compositeScore` stays the target's own score (repo semantics,
  `src/AuthorityRiskOracle.sol`), and `notes` carries
  `l1CappedComposite = min(compositeScore, L1 compositeScore)`.
- Numeric rule, same as the contract comment: `crossExposureScore = max(0, 100 - 20 *
  number of other tracked HyperCore targets sharing at least one root key)`, where the
  root keys of a HIP-3 dex are all its authority addresses (deployer, `oracleUpdater`,
  every sub-deployer) plus the authorized users of each one that is a multisig.
- **Extension (2026-09-21): HyperEVM root holders count.** The rule above counted only HyperCore targets, so Kinetiq's kHYPE
  `StakingManager` and its kmHYPE `HIP3StakingManager`, both rooted in the same 4-of-8 Safe (`DEFAULT_ADMIN_ROLE` and
  `MANAGER_ROLE` on each, read live), scored 100 while their own notes said the Safe roots both. The field means "does this
  target's root authority also control another tracked target", and a HyperEVM Safe is a root authority like any other. For a
  HyperEVM target the root holders are those of `DEFAULT_ADMIN_ROLE` (AccessControl) or `RoleRegistry.owner()`; the score is
  `min(existing, max(0, 100 - 20 * number of OTHER tracked targets sharing a root holder))`, applied by `score_all()` in
  `chains/hyperliquid/scorers.py`. Operational roles (`OPERATOR_ROLE`, `MANAGER_ROLE` alone) are not roots. Result: both
  Kinetiq managers 100 to 80, composites unchanged (4 and 4); para's StakingVault and Ventuals' vHYPE staking share no root
  holder and stay 100. HIP-3 dex `mkts`/`km` is NOT counted with them: its deployer address is the address of the
  HIP3StakingManager proxy, but `data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md` found no verified path from
  that contract to dex-admin actions.

### 4.6 Numeric mapping (added 2026-09-16 by the methodology test)

The sections above ordered keys but did not turn them into 0-100 numbers. For a
weakest key `(k, n)` selected by rule 4.2:

| Score | Formula | Examples |
|---|---|---|
| adminKeyScore (HIP-3) | 65 if k >= 3, 50 if k = 2, 10 if single key, 5 if 1-of-N with N > 1 | Same thresholds as `_safe_rooted_scores` in `scripts/lib/scorers.py`, plus the 1-of-N rule of 4.2 |
| multisigScore (HIP-3) and oracleAuthorityScore (HIP-3) | k = 1: 15 if n = 1, else max(0, 14 - 2 (n - 1)). k >= 2: min(100, 20 k - (n - k)) | 1-of-6 = 4, 1-of-4 = 8, single key = 15, 2-of-3 = 39, 3-of-6 = 57, 3-of-5 = 58, 4-of-8 = 76, 4-of-6 = 78 |
| adminKeyScore (L1) | 15 (4.1) | |
| multisigScore (L1) | min(100, 15 k_f + 5 k_l), k_f and k_l = entities to exceed 2/3 and 1/3 of active stake | 4 and 1 entities give 65 |
| oracleAuthorityScore (L1 validator perps) | min(100, 20 m), m = entities to exceed 1/2 of active stake | 2 entities give 40 |
| timelockScore | 0 when no delay is proven (4.3) | |
| compositeScore | floor(0.4 admin + 0.3 multisig + 0.3 timelock + 0.5), repo `_composite` | |

Why not reuse the repo's Safe formula `15 k + 5 (n - k)` for multisigScore: it rewards
a larger `n` at equal `k`, which contradicts the approved rule 4.2 ordering (larger
`n` weaker). Selecting the weakest key with one order and scoring it with the opposite
one can pick a key that is not the lowest score. The formula above never
contradicts rule 4.2 for n <= 10 (the HyperCore multisig maximum): it is
non-decreasing along the 4.2 order, and strictly increasing except where it hits the
0 floor (1-of-8 to 1-of-10) or the 100 cap (5-of-5 and every k >= 6). Cross-chain
comparability cost: a 2-of-3 scores 39 here against 35 under the Robinhood Chain Safe
formula.

### 4.7 Target identifiers

The on-chain oracle is keyed by `address`. A HIP-3 dex is keyed by its `deployer`
address (the dex name goes in the label). The L1 has no address: it is keyed by the
last 20 bytes of `keccak256("hyperliquid:hypercore-l1")`, i.e.
`0xeA394CD63CA3a5C8A130Bb2b955cC71C22E5ea6C`, which no key controls.

**Amendment 2026-09-19 (deploy_testnet rehearsal, CORRECTION of the push
path, no score changed)**: when a HIP-3 dex's `deployer` address is ALSO the
address of a separately-scored HyperEVM contract (today: `mkts` and Kinetiq's
HIP3StakingManager at `0x71f0...29ec`, `para` and para's StakingVault at
`0x8888...6ed3`), the two scores cannot share one oracle slot -- the oracle's
`_scores[target] = score` would silently keep only the last one pushed (reproduced:
15 scores in, `trackedTargetsCount() = 13`, mkts' 9 and para's 5 read back as 4).
Rule: the HyperEVM contract keeps its real address (an EVM consumer calling
`getScore(contract)` gets that contract's own score), and the colliding HIP-3 dex
moves to the last 20 bytes of `keccak256("hyperliquid:hip3-dex:<name>")`, the same
construction as the L1 key above: `mkts` -> `0xBF6d3bBCE71dBcE6f4121BfE2E2caD8C77bBc1fC`,
`para` -> `0x30E96FBD515243d47703e78581b88cba60f51360`. Any other collision is a
hard failure of `deploy/push_scores.py`, never a silent overwrite. Non-colliding
dexes (`xyz`, `io`) keep their deployer address. Implemented in
`deploy/push_scores.py::resolve_oracle_keys()`, tested in
`scripts/lib/tests/test_hyperliquid_push_keys.py`.

## 5. Reproduction commands

```bash
# HyperEVM chain ids
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' https://rpc.hyperliquid.xyz/evm
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' https://rpc.hyperliquid-testnet.xyz/evm

# HyperCore authority reads
curl -s -X POST -H 'Content-Type: application/json' -d '{"type":"validatorSummaries"}' https://api.hyperliquid.xyz/info
curl -s -X POST -H 'Content-Type: application/json' -d '{"type":"perpDexs"}' https://api.hyperliquid.xyz/info
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"type":"userToMultiSigSigners","user":"0x88806a71d74ad0a510b350545c9ae490912f0888"}' https://api.hyperliquid.xyz/info

# Section 4 applied end to end to two live targets (xyz HIP-3 dex, L1)
python3 chains/hyperliquid/scripts/methodology_test.py scores

# Section 4.2 table, recomputed (deployer + sub-deployers + oracleUpdater, weakest by (k, -n))
python3 chains/hyperliquid/scripts/rule_4_2.py

# Legacy bridge on Arbitrum
cast call 0x2df1c51e09aecf9cacb7bc98cb1742757f163df7 "disputePeriodSeconds()(uint64)" --rpc-url https://arb1.arbitrum.io/rpc
```

## 6. Open questions for the next phase

- Run a non-validator with `--serve-info` to get a second, independent source for
  every HyperCore read above.
- **RESOLVED 2026-09-19** (was: "Decode the calldata of the last `updateValidatorSet`
  on Bridge2 to compare the bridge hot/cold signer set (epoch 7) with the current 27
  active L1 validators"): decoded (the actual last call was `emergencyUnlock`, the
  cold-quorum path, not `updateValidatorSet` -- same request shape, corrected here).
  Zero address overlap between Bridge2's epoch-7 hot+cold set (4+4, equal weight) and
  any of the 27 active (or all 35 registered) L1 validators' `validator`/`signer`
  addresses. The bridge's own quorum is also categorically smaller than the L1's
  active set, not just differently keyed -- disclosed as an open interpretive
  question (intentional freeze vs. a sync process that stopped tracking L1 validator
  growth), not folded into any score. No change to `adminKeyScore`/`multisigScore`
  (both already derived from the bridge's own real 3-of-4 threshold, not from this
  comparison). Full derivation: [`data/finding_2026-09-19-section6-open-
  questions.md`](data/finding_2026-09-19-section6-open-questions.md) section 1.
- **RESOLVED 2026-09-19** (was: "Find a primary source for L1 upgrade notice practice
  (announcement channel, typical lead time) before fixing the L1 timelock score at
  0"): searched docs full text, docs sitemap, a guessed governance page (404), a
  guessed governance-forum subdomain (does not resolve), the `hyperliquid-dex` GitHub
  org's full repo list, `hyperliquid-dex/node`'s releases/tags (both empty) and last
  100 commits, and the `hl-node` README in full. No primary source states a minimum
  or typical upgrade notice period anywhere. `timelockScore = 0` for the L1 target is
  confirmed justified by an actual documented search, not merely left unresolved. No
  score change. Full search trail: [`data/finding_2026-09-19-section6-open-
  questions.md`](data/finding_2026-09-19-section6-open-questions.md) section 2.
- **RESOLVED 2026-09-19, HIP-4 half** (was: "HIP-4 outcome markets are testnet-only
  per the docs; add them once live on mainnet. Seen during the 2026-09-16 test:
  trade[XYZ] docs already describe a `txyz` HIP-4 deployment. To re-check..."):
  **live on mainnet**, and materially larger than the docs' own overview page
  describes (249 live outcome markets, 25 questions, spanning crypto price
  touch/threshold, sports contests, company IPO confirmation, and policy-rate
  markets) -- the "HIP-4 deployer actions" API reference page still headers itself
  "Testnet-only" as of 2026-09-19, contradicted by live mainnet state (confirmed
  mainnet and testnet are genuinely separate environments via `{"type":"meta"}`
  universe-size comparison). `txyz` (the exact deployment flagged unresolved here) is
  confirmed live, with a real 2-of-3 deployer. Two more mainnet outcome-deployer
  venues found the same way (`out` 3-of-4, `skew` 3-of-5) -- three genuinely new
  root-control targets, none yet in `scorers.py`, none overlapping any of this
  ecosystem's 15 already-tracked root addresses. Rule 4.2's sub-deployer-bypass logic
  applies unchanged: every sub-deployer on all three venues is a bare single key,
  weaker than its own venue's deployer multisig. Provisional 4.6 numbers computed by
  hand (composite 9 for all three) but deliberately NOT pushed to `scorers.py` this
  pass -- per `AGENTS.md`'s scouting/scoring_build phase gate and its
  new-controller-shape adversarial-review requirement, this stays scouting-phase
  output pending a dedicated scoring_build pass. Full derivation, addresses, and the
  recommended next-pass scope: [`data/finding_2026-09-19-section6-open-
  questions.md`](data/finding_2026-09-19-section6-open-questions.md) section 3. **Update 2026-09-19 (later, scoring_build and adversarial review; SCORER BUILT AND REVIEWED, NO VENUE PROMOTED):** that pass ran, and so did the adversarial review AGENTS.md requires before committing a new controller shape (three lenses, each finding re-checked by a separate agent trying to refute it: 15 objections confirmed and applied, 2 refuted). Economic weight sized (collateral locked, derived from a full-collateralization identity checked on every read: `out` $1.19M, `txyz` $0.40M, `skew` $8K), `score_hip4_outcome_deployer(venue)` written and tested with no new formula, and all three venues HELD: their collateral is below the written scouting rule of about $5M of TVL or open interest (`data/scouted_targets_2026-09-17-run2.md`; a scouting rule, not a promotion rule) and below the lightest promoted dex (`mkts`, about $6.4M to $6.7M at promotion, $7.7M re-read). `out` would clear only an outcome-specific floor at about $600K or below (the lightest tracked target, Ventuals, is about $583K); that calibration is the one question this bullet leaves OPEN, for the reviewers or the maintainer, and no constant was invented. Corrections to the scouting note: the "8 unique sub-deployers" are 3 deployers plus 5 sub-deployers; "zero overlap" was address-level only (`txyz`'s deployer has the same three signers as HIP-3 dex `xyz`'s); "validator-priced settlement" does not describe these venues (their own deployer and sub-deployer keys settle; only the 8 protocol-run recurring outcomes are settled by the protocol); and the "3-of-4" deployer of `out` is a nested, cyclic multisig. What the chain shows about settlement (settles accepted before a market's stated time, Yes/No markets settled at 0.5, sub-deployer keys in continuous automated use) is in section 8 of the data file. Nothing here advances the ecosystem's phase. Full account: [`data/scored_targets_2026-09-19-hip4-outcome-deployers.md`](data/scored_targets_2026-09-19-hip4-outcome-deployers.md).
- Whether `setMarginTableIds` and `setMarginModes` apply to already open positions
  (and so could force liquidations). Until a primary source says so, they stay out of
  the root-control set and are listed in `notes`. **Re-checked 2026-09-19, still
  OPEN** (docs only, no live test): the HIP-3 deployer-actions API page gives the
  types but no rule on open positions; the margin-tiers page says maintenance margin
  "depend[s] only on the margin tiers", which suggests (not proves) that a new table
  would apply to existing positions; the HIP-3 page says enabling cross margin is
  irreversible and validator-gated, which bounds `setMarginModes` in one direction
  only. Evidence and what would close it: [`data/finding_2026-09-19-margin-actions-
  docs-check.md`](data/finding_2026-09-19-margin-actions-docs-check.md).
- **RESOLVED 2026-09-19, HIP-3\* half** (was: "HIP-3\* (`isStar`, testnet-only per the
  docs) adds `sendAsset` proxy operations that move a user's collateral. If it
  reaches mainnet, it enters the root-control set."): re-checked live 2026-09-19 --
  still testnet-only. The live docs page's own section heading still reads "HIP-3\*
  (testnet-only)". No change; re-check again on a future pass since this is a
  point-in-time confirmation, not a permanent one.
- **New, found 2026-09-17 while promoting `para`/`mkts`, retried across two rounds,
  self-corrected on the second:** some HIP-3 dex deployer addresses ALSO carry live
  HyperEVM bytecode (EIP-1967 proxies) -- unlike `xyz`/`io`, which have none.
  `mkts`/`km`'s resolves, via a real, independently-verified admin chain, to a
  4-of-8 Gnosis Safe. Round one found Hyperliquid's own `CoreWriter` docs confirming
  a calling contract's OWN address becomes the HyperCore identity for the resulting
  action, plus the implementation's bytecode literally containing the CoreWriter
  system address -- read together, this first looked like strong evidence for a
  real second root-control path. Round two (reading the implementation's actual
  VERIFIED SOURCE on a block explorer, not stopping at the bytecode-level
  observation) corrected that: the contract is Kinetiq's own `HIP3StakingManager`
  (a kHYPE liquid-staking manager), and every CoreWriter call it exposes
  (`sendIocOrder`, `sendVaultTransfer`, `sendTokenDelegate`, `sendCDeposit`,
  `sendCWithdrawal`, `sendSpot`, `sendUsdClassTransfer`, `addApiWallet`) is a
  staking/trading helper available to any account, not a `haltTrading`/`setOracle`
  -type deployer-privileged action. NOT folded into any score either way (and even
  under the stronger, since-corrected reading, could not have lowered the
  composite: the direct HyperCore-native path is already a bare single key,
  `adminKeyScore=10`, near the floor). The general mechanism (a HyperEVM contract's
  own address becomes its HyperCore identity via CoreWriter) remains real and worth
  checking for any FUTURE target whose authority address turns out to be a smart
  contract -- read its actual source before concluding either way, the exact lesson
  this correction re-taught. See
  `data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md` for the full
  derivation and correction.

## 7. Changelog

| Date | Change | Trigger |
|---|---|---|
| 2026-09-16 | 4.1: HIP-3 adminKeyScore uses the root-control set (deployer plus `haltTrading` sub-deployers), not the deployer alone | Test on `xyz`: 2-of-3 deployer but two single-key `haltTrading` sub-deployers. The old 4.1 wording (deployer ladder) contradicted rule 4.2.3 (sub-deployers bypass the deployer) |
| 2026-09-16 | 4.2 and 4.4: L1 coefficients counted per entity (operator-prefix merge), not per validator | Test on the L1: 3 and 8 validators, but 1 and 4 entities; the Foundation-labeled set alone exceeds 1/3 |
| 2026-09-16 | 4.4: `SetOracle` clamps recorded as notes | Test on `xyz`: the clamps were not mentioned, so a reader could not tell whether a 1-of-6 push is bounded |
| 2026-09-16 | 4.5: numeric crossExposureScore rule and L1 cap made explicit | Test: "caps all HyperCore targets" had no defined arithmetic |
| 2026-09-16 | New 4.6 numeric mapping | Test: no dimension had a 0-100 formula, and the repo Safe formula contradicts rule 4.2 ordering |
| 2026-09-16 | New 4.7 target identifiers | Test: the L1 target has no address to key the oracle by |
| 2026-09-17 | Section 6: added, then corrected, the HIP-3 deployer EVM-side-proxy open question | Promoting `para`/`mkts` found live HyperEVM bytecode at their deployer addresses (unlike `xyz`/`io`), one resolving to a real 4-of-8 Gnosis Safe; reading the implementation's verified source corrected an over-strong first read (Kinetiq's own staking manager, not a dex-admin path) |
| 2026-09-17 | New 3.7: HyperEVM-native smart contract admin key methodology (Safe/AccessControl reads, the CoreWriter attribution caveat) | Scoring Kinetiq's `HIP3StakingManager` -- the first real HyperEVM-native target, closing 4.1's own long-standing "HyperEVM contract: reuse scripts/lib/scorers.py patterns" row with an actual worked example |
| 2026-09-17 | 3.7 corrected (same day, before commit): added "check every AccessControlEnumerable role, not just the one that resolves cleanest" | An adversarial review of the first Kinetiq scorer caught that only `DEFAULT_ADMIN_ROLE` was actually queried despite the docstring claiming every role was checked; the other roles turned out NOT to be uniformly benign (`OPERATOR_ROLE` = bare EOA, `TREASURY_ROLE` = a separate Safe) -- `compositeScore` corrected from 50 to 4 |
| 2026-09-17 | 3.7 extended: second HyperEVM target (`para` StakingVault), UUPS-vs-transparent-proxy admin-slot lesson, a second access-control read pattern (Solady `EnumerableRoles`), an RPC-revert-handling fix (`HyperEvmRpcError`), and the `none_means_renounced` convention ported from the same-day Solana Drift correction | Closing `para`'s own left-open EVM-proxy question found a real, separately-scored ~$41.7M vault and corrected an earlier wrong claim ("admin slot zero = immutable") in the same pass |
| 2026-09-18 | 3.7 extended again: third HyperEVM target (Ventuals vHYPE staking), "a `roleRegistry()` getter succeeding is not evidence of real gating -- only reading verified source is" | Promoting Ventuals vHYPE staking found a `MANAGER_ROLE` holder that IS verified (unlike `para`'s analogous case), letting its practical authority be resolved by reading source instead of staying conservative -- same targets' shape, different score (4 vs. 31) purely from verification status |
| 2026-09-18 | Ventuals vHYPE staking corrected (same day, before commit): a manual-verification shortcut now re-checks its own precondition every run instead of trusting it once; a docstring overstated "onlyOwner everywhere" when one permissionless-but-non-discretionary path exists; a new length check crashed instead of degrading; two smaller data-hygiene/completeness gaps closed | An adversarial review of the new scorer caught that its one hardcoded trust (a verified `MANAGER_ROLE` holder) had no runtime guard against a future implementation swap, among 5 other real gaps -- `compositeScore` unchanged at 31, all fixes closed dormant robustness gaps, not a live miscalculation |
| 2026-09-18 | **scoring_build**: 4.1 gained 3 new rows (HyperEVM contract as HyperCore identity, HyperCore vault leader, HIP-1 spot treasury holding unissued supply), 4.3 gained a numeric value for the bridge's 200s dispute period (15) and a two-timelock minimum-over-paths worked example (HyperLend), 4.4 gained a bounded-vs-unbounded oracle-push rule for liquid-staking `OracleManager`s -- closing all 5 gaps `data/scouted_targets_2026-09-17-run2.md`'s own "Rules needed before scoring_build" section listed | The `scoring_build` phase itself: writing scorers for the 8 targets that file had verified live but left unscored pending exactly these rules |
| 2026-09-18 | `para`'s HIP-3 dex score corrected: adminKeyScore 10->5, multisigScore 15->10, oracleAuthorityScore 15->10, compositeScore 9->5 (applied as a post-processing override in `scorers.py`, not a change to `score_hip3_dex` itself) | Applying the new "HyperEVM contract as HyperCore identity" rule: `para`'s deployer is a StakingVault contract, and its real `addApiWallet` authority (`OPERATOR_ROLE`, a 1-of-3 Safe) is weaker than the generic "null multisig = single key" reading assumed |
| 2026-09-18 | Existing `score_kinetiq_staking_manager()` (kmHYPE's proxy) `oracleAuthorityScore` corrected 100->7 (applied as a post-processing patch, the adversarially-reviewed function itself untouched); its own docstring's "(kHYPE liquid staking)" parenthetical is a mislabel -- the scored address (`0x71f0019c...2429ec`) is kmHYPE's StakingManager, confirmed against `scripts/scout_2026_09_17_run2.py`'s own `KINETIQ` address table, not kHYPE's (a separate contract, `0x393D0B87...2109`, scored for the first time this pass) | The new bounded-vs-unbounded oracle rule applies to this target too (kmHYPE has no sanityChecker, live-confirmed) -- `compositeScore` unchanged at 4 (oracleAuthorityScore is not a `composite()` input) |
| 2026-09-18 | 7 new targets scored: Kinetiq kHYPE StakingManager (composite 4), HLP vault (9), Unit UBTC/UETH/USOL treasuries (9 each), Bridge2 (48), HyperLend Pooled (61) | `scoring_build` phase deliverable -- see `chains/hyperliquid/scripts/scoring_build_2026_09_18.py` for every scorer and its full derivation |
| 2026-09-19 | 4.7 amended: a HIP-3 dex whose deployer address is also a scored HyperEVM contract gets a derived oracle key (`keccak256("hyperliquid:hip3-dex:<name>")`, last 20 bytes); `push_scores.py` now refuses any unresolved key collision | deploy_testnet rehearsal (an `eth_call` simulation on HyperEVM Testnet) showed the raw push stored 13 of 15 scores: `mkts` and `para` were overwritten by the HyperEVM contracts at the same address. No score value changed |
| 2026-09-19 | Section 6: 3 of 6 open questions resolved (Bridge2-vs-L1-validators overlap, L1 upgrade-notice source search, HIP-3\*/HIP-4 mainnet status). No score changed -- Bridge2's admin/multisig scores were already correct on independent re-derivation, and the L1 timelock's 0 is now backed by a documented, exhaustive-for-this-pass source search rather than left merely unresolved. One correction in passing: the epoch-7 Bridge2 tx is `emergencyUnlock`, not `updateValidatorSet` as this section previously named it (same decode either way) | Read-only research pass on the section 6 backlog, priority-ordered by the requesting session; see `data/finding_2026-09-19-section6-open-questions.md` and `scripts/scout_2026_09_19_section6.py` |
| 2026-09-19 | **New finding, not yet scored**: HIP-4 outcome markets are live on Hyperliquid MAINNET with 3 real, independent outcome-deployer venues (`out` 3-of-4, `txyz` 2-of-3, `skew` 3-of-5) and 249 live markets -- a genuinely new root-control-target family this repo has never scored, confirmed to have the same "sub-deployer bypasses deployer multisig" structural weakness already known from HIP-3 (every sub-deployer on all three venues is a bare single key). Deliberately left at scouting phase (not promoted into `scorers.py`) pending a dedicated `scoring_build` pass with real economic-weight sizing and an adversarial review, per `AGENTS.md`'s own phase-gate and new-controller-shape rules | Live mainnet check requested for METHODOLOGY.md section 6's HIP-4 open question turned up far more than the question anticipated -- the docs' own two pages on this (overview vs. API reference) disagree with each other, and live state settles it in favor of "already shipped" |
| 2026-09-19 | **HIP-4 outcome deployers, scoring_build (proposal; reviewed, see the next entry)**: 4.1 gained a HIP-4 row (root set = deployer + `settleOutcome`/`settleQuestion` sub-deployers, same 4.6 ladder, no new formula or constant); economic weight sized for `out`/`txyz`/`skew` and all three HELD (not wired into `score_all()`); scouting-note corrections (5 sub-deployers not 8; `txyz` shares its 3 deployer signers with HIP-3 dex `xyz`) | Follow-up to the same day's scouting find, which left the sizing, the scorer and the adversarial review open. The scorer and its tests exist so a venue can be promoted with a few lines once the real-usage floor for outcome venues is settled by the reviewers or the maintainer; see `data/scored_targets_2026-09-19-hip4-outcome-deployers.md` |
| 2026-09-19 | **HIP-4 outcome deployers, adversarial review applied**: 15 objections confirmed and applied, 2 refuted (three lenses, each finding re-checked by a separate agent trying to refute it). Corrections: the real-usage bar was NOT "never written" (a scouting selection rule of about $5M of TVL or open interest exists; all three venues stay HELD, now on that number, with the residual calibration question stated as such); slashing is never credited as a deterrent for settlement (the page documents it only for malformed markets); the `setOracle` analogy is partial and the HIP-4 oracle rule now has its own row in 4.4; registration variants are left out of the root set by analogy, no longer asserted harmless, with a visible sensitivity block; an unclassified sub-deployer grant now raises; `out`'s deployer is a nested cyclic multisig (disclosed; the one-off cross-check is now recursive, same result); settle timing and key cadence observed on chain (15 Yes/No markets settled at 0.5 before their stated time, keys in continuous automated use) with a `history` subcommand; the scouting finding's "validator-priced settlement" corrected; trade[XYZ]'s docs vs the chain recorded for `txyz`. No score changed, no venue promoted, no phase advanced, `ecosystems.json` and maker-checker untouched | AGENTS.md requires an adversarial review before committing a new controller-resolution shape, and lists real fixes over rubber-stamping; the full record (objection by objection, and what was deliberately left open) is section 10 of `data/scored_targets_2026-09-19-hip4-outcome-deployers.md` |
| 2026-09-21 | 4.5: HyperEVM root holders count toward crossExposureScore | Kinetiq's two StakingManagers share one root Safe and both read 100; the note said the rule covered only HyperCore keys |
