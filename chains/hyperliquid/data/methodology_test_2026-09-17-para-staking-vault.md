# Hyperliquid methodology test: para StakingVault, a second HyperEVM-native target (2026-09-17)

Seventh Hyperliquid target, and the second one native to HyperEVM rather
than HyperCore (after Kinetiq's `HIP3StakingManager`, same day). Closes
this project's own open question about HIP-3 dex `para`'s EVM-side proxy
(`data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md` had
explicitly left `para`'s own implementation source unread, calling it "an
open, symmetrical gap" to Kinetiq's) -- and, in closing it, CORRECTS that
same file's earlier claim that `para`'s proxy's EIP-1967 admin slot
reading zero was "consistent with an IMMUTABLE proxy." It wasn't: this is
a UUPS proxy, which never uses the EIP-1967 ADMIN slot at all (only a
TRANSPARENT proxy does) -- reading zero there was never evidence of "no
admin," only evidence of "not a transparent proxy." The real authority is
gated inside the implementation's own `_authorizeUpgrade`.

| Item | Value |
|---|---|
| Chain | HyperEVM (`https://rpc.hyperliquid.xyz/evm`) |
| Proxy (same address as HIP-3 dex `para`'s HyperCore-native deployer) | `0x8888888c43cbb7e1c4132542e46831bffd866ed3` |
| Implementation (verified source on `hyperevmscan.io`, contract name `StakingVault`, creator `0x1947299Ba117613837E6321c7F0B6074371384d3`) | `0x00000006711dce34e37ec3e1b18f21a3d5399fbe` |
| RoleRegistry (external contract this vault and `Base.sol` defer all access control to) | `0x8888888b418d2a2dec293fa30e1e202586f19fc0` |

## What this vault is

Read via `initialize(address _roleRegistry, address[] _whitelistedValidators)`
and its own functions: a HYPE custody/staking vault --
`deposit`/`stake`/`unstake`/`tokenRedelegate`/`spotSend`/
`transferHypeToCore` move funds; `addValidator`/`removeValidator`/
`addApiWallet` manage operational configuration. `delegatorSummary()`
reads **500,801.29 HYPE currently delegated to validators** (raw:
`50080128590863`, HYPE's own `weiDecimals=8` per the official
`spotMeta` API) -- **~$41.7M** at the live $83.324/HYPE mid price
(`allMids`, 2026-09-17). That is larger than several already-promoted
HIP-3 dexes' own open interest (`mkts` ~$6.7M, `para` itself ~$15.1M).

Checked all 501 entries in the official `spotMeta` token list for any
token whose `evmContract` matches this proxy or its implementation --
zero matches. This is a custody/treasury vault, not a wrapped
liquid-staking token with its own tradeable spot asset.

## Three independent authority paths -- every one resolved, not assumed

Unlike Kinetiq's `HIP3StakingManager` (OpenZeppelin `AccessControlEnumerable`,
5 roles), this vault defers ALL access control to a separate `RoleRegistry`
contract using Solady's `EnumerableRoles` plus `Ownable2StepUpgradeable` --
a DIFFERENT library, DIFFERENT read pattern (`roleHolders(bytes32)` returns
the full holder array in one call; no `getRoleMemberCount`/`getRoleMember`
loop), independently written, and it generalizes the same underlying
methodology (check every role a HyperEVM access-control system defines,
classify every holder, take the minimum) to a second, unrelated
implementation on the same day.

| Path | Gates | Holder | Kind | adminKey | multisig | timelock |
|---|---|---|---|---|---|---|
| `RoleRegistry.owner()` | `_authorizeUpgrade` on BOTH the vault and RoleRegistry itself, plus `grantRole`/`revokeRole`/`pause`/`unpause` | `0x8d23a255656f4c8e26d1010e0aa2b6d20885ca91` | Gnosis Safe, **1-of-1** | 10 | 15 | 0 |
| `MANAGER_ROLE` | `deposit`/`stake`/`unstake`/`tokenRedelegate`/`spotSend`/`transferHypeToCore` -- every fund-moving function | `0x8888888745a9155d012f0e546de03ff142b2f92c` | **UNVERIFIED contract** (EIP-1967 proxy delegating to `0x000000091e2d27aa3e7a0afe9a71338f58910f5d`, 14,610 bytes, no verified source on `hyperevmscan.io`) | **20** | **0** | 0 |
| `OPERATOR_ROLE` | `addValidator`/`removeValidator`/`addApiWallet` | `0x5a24d40ef0b6856aefeefe65c332ce7cc7d9ba04` | Gnosis Safe, **1-of-3** (one of its 3 owners is the SAME address as the `RoleRegistry.owner()` Safe above) | 10 | 25 | 0 |

The `MANAGER_ROLE` holder is itself a tiny (76-byte) EIP-1967-style proxy
whose own implementation slot was read to find the real 14,610-byte
contract behind it -- confirmed via `eth_getCode` and `hyperevmscan.io`'s
own "Are you the contract creator? Verify and Publish your contract
source code today!" banner that this implementation has NO verified
source. Rather than guess at unverified bytecode's semantics (the exact
mistake this project's own earlier Kinetiq/CoreWriter overclaim made and
then corrected), `_classify_authority_holder` degrades this to the
existing conservative unresolved-contract fallback (20/0/0) -- the same
convention `scripts/lib/scorers.py::_safe_rooted_entry` already uses for
the identical situation on the Robinhood Chain side.

## Scoring: minimum across every currently-held path (METHODOLOGY.md 6.2)

```
adminKeyScore  = min(10, 20, 10) = 10
multisigScore  = min(15,  0, 25) =  0   -- the unverified MANAGER_ROLE holder
timelockScore  = min( 0,  0,  0) =  0
compositeScore = floor(0.4*10 + 0.3*0 + 0.3*0 + 0.5) = 4
oracleAuthorityScore = 100  (not applicable -- no price-oracle dependency)
crossExposureScore   = 100  (checked against all 10 HIP-3 dexes' own signer sets --
                              zero overlap on ANY of the 5 role-holder addresses above)
```

`compositeScore = 4` -- CRITICAL band. `l1CappedComposite = min(4, 26) =
4` -- the L1 cap has no effect (this vault's own score is already far
below the L1's 26).

The unverified `MANAGER_ROLE` holder is the binding constraint on both
`adminKeyScore` and `multisigScore` at once, not just one dimension --
whatever this contract's real logic is, it can currently move the vault's
~$41.7M without any published source to audit it against. Whether that
logic is itself further gated (e.g. it might internally re-check the same
`RoleRegistry.owner()`, in which case the practical risk is lower than
this conservative score implies) was NOT determined -- it was
deliberately not guessed at from raw bytecode alone.

## No dex-admin path found here either (closes the original open question)

Read `StakingVault.sol` line by line (not just its ABI): every
`CoreWriterLibrary` call site (`stakingDeposit`, `stakingWithdraw`,
`tokenDelegate`, `spotSend`, `addApiWallet`) is a staking/delegation/
API-wallet helper. None reaches `haltTrading`/`setOracle`/
`setSubDeployers`, and no function constructs a raw/arbitrary CoreWriter
action. This closes the specific question this file's own predecessor
left open for `para` -- matching the Kinetiq precedent exactly: a real,
separate authority chain exists on the EVM side, but it does not grant
any additional HIP-3 dex-admin privilege over the perp market itself.

## Honest limitations

- The unverified `MANAGER_ROLE` holder's actual logic was not
  reverse-engineered from its bytecode -- deliberately, to avoid repeating
  this project's own earlier CoreWriter/Kinetiq overclaim. If it is
  itself gated by `RoleRegistry.owner()` (plausible, since it correctly
  reads from the same registry), the practical risk may be lower than
  this conservative 20/0/0 implies -- not assumed either way.
- The `RoleRegistry.owner()` Safe's single owner
  (`0xbc6ee95eed24d7b76e018ec4fa07e105462d8ad5`) and the `OPERATOR_ROLE`
  Safe's other 2 owners were not attributed to named individuals.
- A "Similar Match" contract was flagged by `hyperevmscan.io` at a
  different `0x8888888...`-prefixed address, suggesting this same
  `StakingVault`/`RoleRegistry` pattern may be reused by another,
  still-dormant HIP-3 dex from the same operator -- not chased further
  this pass.
- Whether this same `RoleRegistry` (or its owner Safe) controls any OTHER
  contract beyond this one vault was not checked.
- This is `para`'s own operator's infrastructure risk, not a HIP-3
  dex-admin risk -- scored under the Hyperliquid ecosystem file because
  HyperEVM is Hyperliquid's own execution layer and the address itself
  was found via HIP-3 dex research, same rationale already applied to
  Kinetiq's promotion.

## Bugs caught during derivation, and via adversarial review, not after

`read_role_registry_role_holders` is a NEW ABI read (Solady's
`EnumerableRoles.roleHolders(uint256)`, wrapped by this project's own
`RoleRegistry.roleHolders(bytes32)`) -- a different interface than
OpenZeppelin's `AccessControlEnumerable` (`getRoleMemberCount`/
`getRoleMember`) already used for Kinetiq. Its first live use surfaced a
real gap in the SHARED helper code, not this new function: calling
`getOwners()` on the `MANAGER_ROLE` holder (which isn't a Safe at all, so
the call reverts) crashed with a raw `KeyError: 'result'` inside `evm()`,
which did a bare `["result"]` dict lookup with no handling for a JSON-RPC
error response. Fixed by adding `HyperEvmRpcError` and having `evm()`
raise it explicitly on any response with no `result` key;
`_classify_authority_holder` now catches it the same way it already
catches `HyperEvmReadError`, degrading to the conservative unresolved
fallback instead of crashing. A second, smaller fix landed alongside it:
`_classify_authority_holder` gained a `none_means_renounced` parameter
(matching this project's own `_resolve_squads_v4`
`none_means_renounced` convention on the Solana side, from the Drift
Protocol correction earlier the same day) so that `RoleRegistry.owner()`
returning the zero address would score as the safest possible state
(renounced, 100/100/100) rather than as a weak bare EOA -- not currently
triggered (the live owner is not zero) but a real correctness gap for a
future state change, caught before it could matter rather than after.

Before any of this reached a commit, an adversarial review workflow (3
independent dimensions -- byte-decode correctness, on-chain-facts-and-
attribution, scorer-code robustness -- each finding piped to an
independent verifier) returned 18 findings; 14 were confirmed via fresh,
independent re-verification and 4 were refuted (the refuted ones traced
to reviewer agents checking their claims against the live PUBLIC repo,
which didn't yet contain this pre-commit code -- a limitation of the
review's setup, not a real defect). Of the 14 confirmed, most verified
existing facts/arithmetic as correct with no action needed; five were
real code gaps, all fixed the same pass:

- **`bytes.fromhex()` raised a bare, uncategorized `ValueError`** on
  malformed hex (odd length, non-hex characters -- plausible from a
  glitching or non-compliant RPC provider), which slipped past every
  `except (HyperEvmReadError, HyperEvmRpcError)` clause in this file --
  including inside `read_safe_hyperevm` itself, which still had this gap
  even after its OWN prior hardening pass (that pass validated shape
  AFTER the conversion, not around the conversion itself). Fixed with a
  shared `_bytes_from_hex` helper, used in both `read_safe_hyperevm` and
  `read_role_registry_role_holders`.
- **`MANAGER_ROLE()`/`OPERATOR_ROLE()`'s returned role hash had no length
  check** before being spliced into `.rjust(64, "0")` -- a short or empty
  response (e.g. a future RoleRegistry upgrade returning no data instead
  of reverting for a since-renamed getter) would silently zero-pad into
  `bytes32(0)`, this project's own `DEFAULT_ADMIN_ROLE` sentinel value
  elsewhere, querying a completely different, unintended role with no
  error, no warning -- a silently WRONG result rather than a crash. Fixed
  with an explicit length check immediately after each role hash is
  fetched.
- **A single role failing to read crashed the ENTIRE target's score**,
  unlike a single unresolvable HOLDER, which `_classify_authority_holder`
  already degraded gracefully. Fixed: `read_role_registry_role_holders`'s
  call inside the per-role loop is now wrapped, degrading that ONE role
  to a conservative unresolved path (20/0/0) with a clear note, so the
  other roles still contribute to the minimum-over-paths computation. (The
  four top-level setup reads -- finding the RoleRegistry itself, its two
  role constants, its owner -- were deliberately left unwrapped: if those
  fail there is genuinely nothing to score this run, and `score_all()`'s
  own per-scorer try/except already isolates that to a single "SKIPPED"
  line, the same convention every other scorer's setup already relies on.)
- **The cross-exposure check only ever compared TOP-LEVEL role-holder
  addresses**, never the individual owner addresses nested one level
  inside a role holder that resolved to a Gnosis Safe -- so an owner
  appearing only INSIDE a Safe (a real case here: one of the `OPERATOR_
  ROLE` Safe's 3 owners is the SAME address as the separate `RoleRegistry.
  owner()` Safe's own sole owner) was invisible to the check. Fixed:
  `_classify_authority_holder`'s Gnosis Safe branch now also returns the
  actual owner address list (`ownerAddresses`, alongside the existing
  `owners` count), and the cross-exposure check unions those in. Re-ran
  live after the fix: `crossExposureScore` is unchanged at 100 -- no new
  overlap found, this was a completeness gap, not a live miss.
- Two purely editorial fixes to THIS document and the earlier finding
  file: the "corrects an earlier claim that was wrong" framing overstated
  what happened (that file's own text had already hedged this exact point
  and explicitly flagged the follow-up as an open gap) -- reworded to
  "closes an explicitly flagged gap, and adds a methodology point"; and
  "an unverified contract" as a headline description blurred together a
  verifiable, standard EIP-1967 proxy with its genuinely-unverified
  implementation -- reworded throughout to distinguish the two.

11 new unit tests were added covering all five code fixes
(`scripts/lib/tests/test_para_staking_vault_hyperevm.py`). Full account:
`data/correction_2026-09-17-para-staking-vault-adversarial-review.md`.

## Reproduction

```bash
cd chains/hyperliquid/scripts
python3 -c "
import json
from methodology_test import score_para_staking_vault
print(json.dumps(score_para_staking_vault(), indent=2))
"
```
