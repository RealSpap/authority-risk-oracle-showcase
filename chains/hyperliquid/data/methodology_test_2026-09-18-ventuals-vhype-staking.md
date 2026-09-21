# Hyperliquid methodology test: Ventuals vHYPE staking, a third HyperEVM-native target (2026-09-18)

Eighth Hyperliquid target overall, and the THIRD native to HyperEVM
rather than HyperCore (after Kinetiq's `HIP3StakingManager` and `para`
StakingVault, both 2026-09-17). Found while chasing a loose end from the
`para` promotion: `hyperevmscan.io` flagged a "Similar Match" contract
(`0x8888888635cb74f39505f91cf79551ac4fd75bc9`, also named `StakingVault`,
also verified) next to `para`'s own implementation, on the theory it
might be reused by another HIP-3 dex's deployer address. That specific
lead was a dead end: sweeping every one of the 10 tracked dexes'
deployer addresses for their OWN EIP-1967 implementation slot found none
of them point at that exact address. But the sweep itself (checking
`eth_getStorageAt` for the EIP-1967 implementation slot on every dex
deployer, not just `eth_getCode` -- the 2026-09-17 promotion only checked
the latter) found something more useful: HIP-3 dex `vntl` -- still
genuinely dormant, $0 open interest, unchanged from every prior re-sweep
-- ALSO carries live HyperEVM infrastructure, a real, NAMED liquid-staking
product this time: **Ventuals vHYPE**.

| Item | Value |
|---|---|
| Chain | HyperEVM (`https://rpc.hyperliquid.xyz/evm`) |
| Proxy (same address as HIP-3 dex `vntl`'s HyperCore-native deployer) | `0x8888888192a4a0593c13532ba48449fc24c3beda` |
| Implementation (verified, contract name `StakingVault`) | `0x000000046a8b917b5a62b446ac208f78412192d1` |
| RoleRegistry | `0x8888888f0651a534011d7ad277c302e7d2d77930` |
| MANAGER_ROLE holder -- proxy (verified, `StakingVaultManager`) | `0x88888880793f89ce85777ff2e0e2d366bf05b20c` |
| MANAGER_ROLE holder -- implementation (verified) | `0x0000000c21e635b59edff54e70fe21315fa9b245` |

## Product identity, independently cross-checked

`hyperevmscan.io` tags the contract creator "Ventuals vHYPE: Deployer" on
both the `StakingVault` and `StakingVaultManager` implementations. An
independent, unrelated signal confirms the same product name: the
official Hyperliquid spot-token list (`spotMeta`) carries a token
`VNTLS`, `fullName: "Ventuals"` -- found by searching all 501 live spot
tokens for the name, not assumed from the explorer tag alone.

`delegatorSummary()` on the proxy reads **7,328.99 HYPE currently
delegated** (raw: `732899248565`, HYPE's own `weiDecimals=8`) -- ~$610K
at the live $83.32/HYPE mid price (2026-09-18). Cross-checked against a
SECOND, independent on-chain read: `StakingVaultManager.totalBalance()`
(a different function, on a different contract, computing the vault's
total value from three separate balance sources) returns the identical
figure, `7328.992485655534`. `exchangeRate()` reads `1.0203` (vHYPE:HYPE),
consistent with a liquid-staking token that has accrued some yield since
launch.

## Two layers, unlike `para`'s single vault

- **`StakingVault`** (the proxy itself, `0x8888888192a4a0593c13532ba48449fc24c3beda`)
  -- the low-level custody contract. Same contract type, same source, as
  Kinetiq's and `para`'s own vaults: holds the real HYPE, calls
  `CoreWriterLibrary` for staking/delegation. Confirmed via its own file
  list on `hyperevmscan.io` (`CoreWriterLibrary.sol`, `ICoreWriter.sol`
  both present).
- **`StakingVaultManager`** -- a second contract IN FRONT of the vault,
  managing the liquid-staking economics: mints/burns the `vHYPE` ERC20
  (`VHYPE.sol`, imported), a withdrawal queue
  (`queueWithdraw`/`claimWithdraw`/`batchClaimWithdraws`/`cancelWithdraw`),
  and batch processing (`processBatch`/`finalizeBatch`). Confirmed via
  its own file list that it does NOT import `CoreWriterLibrary`/
  `ICoreWriter` at all -- it only calls INTO the underlying `StakingVault`
  (an `IStakingVault` reference), never CoreWriter directly.

## Every externally-callable function in `StakingVaultManager`, read and classified

Read live from `hyperevmscan.io`'s verified source (not just its ABI),
every `external`/`public` function's actual modifier:

| Function | Gate | Privileged? |
|---|---|---|
| `deposit`, `queueWithdraw`, `claimWithdraw`, `batchClaimWithdraws` | `whenNotPaused` only | No -- ordinary user actions on the caller's own position |
| `cancelWithdraw` | `whenNotPaused` + `msg.sender == withdraw.account` | No -- caller can only cancel their own withdrawal |
| `processBatch`, `finalizeBatch` | `whenNotPaused` + `whenBatchProcessingNotPaused` only | No -- permissionlessly callable by ANYONE, a standard keeper-processed queue design; this is how `MANAGER_ROLE` actually gets exercised (this contract, not the caller, is what's authorized on the underlying vault) |
| `setMinimumStakeBalance`, `switchValidator`, `setMinimumDepositAmount`, `setMinimumWithdrawAmount`, `setMaximumWithdrawAmount`, `setClaimWindowBuffer`, `setBatchProcessingPaused`, `resetBatch`, `finalizeResetBatch`, `applySlash`, `emergencyStakingWithdraw`, `emergencyStakingDeposit`, `windDown` | `onlyOwner` | **Yes** -- every one of these routes to the SAME `roleRegistry.owner()` |
| `initialize` | `initializer` (OpenZeppelin `Initializable`, plus `_disableInitializers()` in the constructor) | No -- the standard one-time proxy initializer, cannot be called a second time; not an ongoing admin lever. Omitted from the table above in the first draft of this document (caught by adversarial review) -- included here for a genuinely complete function inventory |

No function here reaches a HIP-3 dex-admin-equivalent action
(`haltTrading`/`setOracle`/`setSubDeployers`) -- consistent with Kinetiq's
and `para`'s own precedent.

## Three authority paths -- all three resolve to the IDENTICAL Safe

Unlike `para`, where the `MANAGER_ROLE` path had to be conservatively
scored as unresolved (its implementation isn't verified), THIS target's
`MANAGER_ROLE` holder (`StakingVaultManager`) IS verified, so its
practical authority was resolved by actually reading its source, not by
trusting a bare `roleRegistry()` getter call on its own (a getter
returning the right address proves nothing about actual access-control
gating -- exactly the "bytecode presence isn't sufficient evidence"
mistake this project's own earlier CoreWriter/Kinetiq overclaim already
made once and corrected).

| Path | Gates | Holder | Kind | adminKey | multisig | timelock |
|---|---|---|---|---|---|---|
| `RoleRegistry.owner()` | `_authorizeUpgrade` on both contracts, `grantRole`/`revokeRole`/`pause`/`unpause` | `0x72298a4cb6e571241331172fd90149d38feafe08` | Gnosis Safe, **2-of-3** | 50 | 35 | 0 |
| `OPERATOR_ROLE` | (no operational functions currently observed to route through this role on either contract) | `0x72298a4cb6e571241331172fd90149d38feafe08` (SAME Safe, directly -- not nested) | Gnosis Safe, **2-of-3** | 50 | 35 | 0 |
| `MANAGER_ROLE` | every `StakingVaultManager` admin function (table above), via its own `_authorizeUpgrade` | `0x88888880793f89ce85777ff2e0e2d366bf05b20c` (`StakingVaultManager` proxy) | **Verified**, manually confirmed `onlyOwner`-gated -> SAME Safe | 50 | 35 | 0 |

All three land on the identical 2-of-3 Safe. This is NOT automated into a
general rule ("trust any contract whose `roleRegistry()` call succeeds")
-- that would repeat the exact mistake this project already corrected
once. It is a one-off, manually-verified resolution for this ONE address,
hardcoded in `score_ventuals_vhype_staking` with an explicit address
check (`confirmed_verified_manager_role_holders`) -- an unexpected holder
at this role would NOT get this treatment, and would fall back to the
normal, conservative classification instead (covered by
`TestManagerRoleManualResolution` in the accompanying test file).

## Scoring

```
adminKeyScore  = min(50, 50, 50) = 50
multisigScore  = min(35, 35, 35) = 35
timelockScore  = min( 0,  0,  0) =  0
compositeScore = floor(0.4*50 + 0.3*35 + 0.3*0 + 0.5) = floor(31.0) = 31
oracleAuthorityScore = 100  (not applicable -- no price-oracle dependency)
crossExposureScore   = 100  (checked against all 10 HIP-3 dexes' own signer sets,
                              including every nested Safe-owner address -- zero overlap)
```

`compositeScore = 31` -- notably HIGHER (safer) than `para`'s
`compositeScore = 4`, precisely because this vault's operator did the
more responsible thing: verified their source, and used ONE consistent
2-of-3 Safe across every authority path, rather than leaving a
fund-moving role on an unverified contract. `l1CappedComposite =
min(31, 26) = 26` -- the L1 cap actually binds here, unlike Kinetiq's and
`para`'s own (both already below the L1's 26).

## Adversarial review, before any of this reached a commit

Matching the discipline already applied to Kinetiq's and `para`'s own
same-week promotions: an adversarial review workflow (3 dimensions --
facts-and-attribution, the manual-verification judgment call itself, and
scorer-code robustness -- each finding piped to an independent verifier)
returned 12 findings, 11 confirmed, 1 refuted (the refuted one traced to
a verifier agent that pulled data for the WRONG target -- `para`, not
this one -- while trying to independently re-check; the underlying
practical conclusion it was checking held up regardless). Six were real
fixes, all applied the same pass:

1. **The manual-verification shortcut had no runtime check that the
   verified implementation was still in place.** A UUPS proxy's own
   address never changes across an upgrade; only its backing
   implementation moves, and the SAME Safe this function already trusts
   is the sole entity that can push that upgrade. Without a runtime
   check, a routine, legitimate Safe-authorized upgrade could silently
   swap this contract's real logic while the code kept applying a manual
   verification that no longer described its behavior. Fixed: the
   `MANAGER_ROLE` holder's own EIP-1967 implementation slot is now read
   and compared against the verified implementation address on EVERY
   run, not trusted once and forgotten -- a mismatch falls through to the
   normal conservative path instead of continuing to trust a stale
   reading.
2. **The docstring's claim that "every privileged, fund-affecting admin
   action is gated `onlyOwner`" was overstated.** `finalizeBatch`/
   `processBatch` are themselves permissionless (`whenNotPaused` only)
   and DO directly call the underlying vault's `stake`/`unstake`/
   `transferHypeToCore` -- the exact functions `MANAGER_ROLE` gates on
   that vault. What actually preserves the score: every amount and
   destination those two functions move is computed purely from internal
   accounting and the `onlyOwner`-set `validator`, with zero caller
   discretion -- a keeper-style settlement step, not a privilege-
   escalation path. Reworded in both the code's docstring and this
   document's own function table to state the real distinction
   (discretionary actions `onlyOwner`-gated; the permissionless entry
   point non-discretionary) rather than a blanket claim.
3. **A new role-hash length-check crashed the whole target instead of
   degrading one role.** Added the same pass as the length check itself,
   it ran BEFORE the per-role `try/except` blocks that catch this exact
   `HyperEvmReadError` a few lines later for the sibling
   `read_role_registry_role_holders` failure -- breaking, for this one
   input, the graceful-degradation convention the function otherwise
   follows. Fixed by moving the check inside each role's own
   `try/except`.
4. **A role legitimately having zero holders was indistinguishable from
   "not checked."** Unlike Kinetiq's and `para`'s own scorers (both of
   which append a `"<ROLE>: 0 holders"` note), this function had no
   equivalent guard. Fixed: added the same note for both `OPERATOR_ROLE`
   and `MANAGER_ROLE`.
5. **The `"...:UNRESOLVED"` sentinel key leaked into the cross-exposure
   address set** as the literal string `"unresolved"` (via
   `key.split(":", 1)[1]`) -- harmless today (it can never match a real
   dex signer address) but a data-hygiene bug in a set meant to contain
   only addresses. Fixed here AND in `para`'s own sibling function, which
   had the identical gap.
6. **The same physical address holding both `RoleRegistry.owner()` and
   `OPERATOR_ROLE`** (exactly the live state here) was classified TWICE
   via two fully independent RPC sequences instead of reusing the
   already-computed result -- redundant work, plus a narrow,
   low-probability inconsistency risk if a Safe reconfiguration landed in
   the gap between the two independent `"latest"`-block reads. Fixed by
   short-circuiting to the already-computed classification when the
   address matches.

Five more findings were independently re-verified and confirmed as
NOT bugs (no code change needed): the hardcoded verified-holder set is
function-local with no leak risk; exact-string address matching is safe
against casing/typos; `role_paths` can never be empty when `min()` runs;
the `MANAGER_ROLE` proxy's own address is still captured in the
cross-exposure set via both branches of its if/else; and the identical-
to-Safe score is the conceptually correct value given what was verified
(the residual risk is temporal, addressed by fix #1 above, not a "weaker
authority today" fact a discounted score would express any better).

10 new unit tests were added, all exercising the real, complete
`score_ventuals_vhype_staking()` function end-to-end (not just its
individual pieces) via a comprehensive live-response fake, including
direct tests of the runtime implementation-mismatch fallback. Full
account: `data/correction_2026-09-18-ventuals-vhype-staking-adversarial-
review.md`.

## Honest limitations

- The 2-of-3 Safe's 3 owner addresses were not attributed to named
  individuals.
- Whether this same Safe (or `RoleRegistry`) controls any OTHER Ventuals
  contract beyond these two was not checked.
- The "Similar Match" contract that led to this discovery
  (`0x8888888635cb74f39505f91cf79551ac4fd75bc9`) remains unattributed --
  bytecode-similar to both `vntl`'s and `para`'s own `StakingVault`
  instances, deployed the same day as `vntl`'s (337 days ago per
  `hyperevmscan.io`), but its own EIP-1967 slot doesn't match any of the
  10 tracked HIP-3 dexes' deployer addresses. Possibly an earlier
  deployment, a test instance, or a vault for a different asset entirely
  -- set aside, not chased further this pass.
- `vHYPE`'s own ERC20 total supply was not independently read (this
  target's economic-value citation rests on `delegatorSummary()`/
  `totalBalance()`'s direct custody-side reads, cross-checked against
  each other, not against the token's own supply).

## Reproduction

```bash
cd chains/hyperliquid/scripts
python3 -c "
import json
from methodology_test import score_ventuals_vhype_staking
print(json.dumps(score_ventuals_vhype_staking(), indent=2))
"
```
