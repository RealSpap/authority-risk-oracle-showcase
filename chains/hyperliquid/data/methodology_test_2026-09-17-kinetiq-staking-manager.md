# Hyperliquid methodology test: Kinetiq HIP3StakingManager, the first HyperEVM-native target (2026-09-17)

Sixth Hyperliquid target, and the first one native to HyperEVM rather than
HyperCore. Surfaced as a byproduct of `data/finding_2026-09-17-hyperliquid-
hip3-evm-proxy-authority.md`'s investigation into whether HIP-3 dexes
`mkts`/`km`'s shared deployer address (which also carries live HyperEVM
bytecode) exposes a second root-control path over those perp markets. That
specific question resolved to "no" (the contract is Kinetiq's own kHYPE
liquid-staking manager, unrelated to dex-admin actions) -- but the
investigation independently verified a real, complete authority chain for
Kinetiq's own protocol, worth scoring in its own right.

**CORRECTED 2026-09-19 (this file's own "kHYPE" label above is stale,
left as-written rather than silently rewritten)**: the scored address
(`0x71f0019c...2429ec`) is Kinetiq's **kmHYPE** StakingManager, not
kHYPE's -- kHYPE and kmHYPE are two real, separately-deployed Kinetiq
products (general liquid staking vs. HIP-3 "Markets by Kinetiq" staking),
confirmed both by this project's own `scripts/scout_2026_09_17_run2.py`
`KINETIQ` address table and by a fresh live read of this exact contract
(its own `kHYPE()` getter resolves to a token whose on-chain `name()` is
literally "Reserve LST for kmHYPE accounting"). Already caught and fixed
in the score itself on 2026-09-18 (see `METHODOLOGY.md`'s changelog); this
note closes the last two stray "kHYPE" labels left in source comments. See
`data/finding_2026-09-19-hyperliquid-khype-kmhype-identity.md` for the
full re-verification.

**Correction (2026-09-17, same day, before this ever reached a commit)**:
a first version of this document and the scorer behind it stopped after
checking `DEFAULT_ADMIN_ROLE` and asserted every other operational role
"has zero current holders." An adversarial review of the new code caught
that this was never actually verified for `MANAGER_ROLE`/`OPERATOR_ROLE`/
`SENTINEL_ROLE`/`TREASURY_ROLE` -- the scorer simply never queried them.
Querying them live found it false for 2 of 4: `OPERATOR_ROLE` is held by a
BARE EOA, and `TREASURY_ROLE` by a SEPARATE Safe. This document now
reflects the corrected, multi-role picture and the much lower resulting
score (`compositeScore` 50 -> **4**). See "What changed and why" below for
the full account.

| Item | Value |
|---|---|
| Chain | HyperEVM (`https://rpc.hyperliquid.xyz/evm`) |
| Proxy (same address as HIP-3 dexes `mkts`/`km`'s HyperCore-native deployer) | `0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec` |
| Implementation (verified source on `hyperevmscan.io`, contract name `HIP3StakingManager`, creator tagged `Kinetiq: Deployer`) | `0x26264514cd6018d6f944eb30b782aee2794b70b8` |

## Every role this contract defines, checked -- not just the one that looked cleanest

`HIP3StakingManager` uses OpenZeppelin `AccessControlEnumerable` with five
roles. All five were queried live via `getRoleMemberCount`/`getRoleMember`,
and every holder found was classified (Gnosis Safe, bare EOA, or an
unresolved contract):

| Role | Holder | Kind | adminKey | multisig | timelock |
|---|---|---|---|---|---|
| `DEFAULT_ADMIN_ROLE` | `0x18a82c968b992d28d4d812920eb7b4305306f8f1` | Gnosis Safe, 4-of-8 | 65 | 80 | 0 |
| `MANAGER_ROLE` | `0x18a82c968b992d28d4d812920eb7b4305306f8f1` (same Safe) | Gnosis Safe, 4-of-8 | 65 | 80 | 0 |
| `OPERATOR_ROLE` | `0x4459872f33d7e3b61238a6edc7611463c25d82fa` | **bare EOA** (`eth_getCode` = `0x`) | **10** | **0** | 0 |
| `SENTINEL_ROLE` | -- | 0 holders | n/a | n/a | n/a |
| `TREASURY_ROLE` | `0x64bd77698ab7c3fd0a1f54497b228ed7a02098e3` | **separate** Gnosis Safe, 4-of-7 | 65 | 75 | 0 |

`OPERATOR_ROLE`'s bare EOA can call `withdrawFromSpot(uint64)` and
`processL1Operations(uint256)` / `processL1Operations()` -- confirmed
present in the contract's own fetched ABI, not assumed from the role name.
`TREASURY_ROLE`'s Safe shares only **1 of 7** owners with the `DEFAULT_
ADMIN_ROLE`/`MANAGER_ROLE` Safe -- a genuinely separate signer set, not a
renamed copy of the same one.

The EIP-1967 proxy-admin chain (`eth_getStorageAt(proxy, admin slot)` ->
an Ownable admin contract -> that contract's `owner()`) independently
confirms the SAME 4-of-8 Safe holds `DEFAULT_ADMIN_ROLE` -- kept as a
cross-check, not folded into the score a second time (it resolves to the
identical Safe the role read above already covers).

## Scoring: minimum across every currently-held role (METHODOLOGY.md 6.2)

METHODOLOGY.md 6.2's "several authorities per target" convention (already
applied this same day on the Solana side, Kamino/Drift) takes the MINIMUM
across every full-power authority path, not just the one that happens to
look cleanest. Reused here rather than inventing a new rule:

```
adminKeyScore  = min(65, 65, 10, 65) = 10   -- OPERATOR_ROLE's bare EOA
multisigScore  = min(80, 80,  0, 75) =  0   -- OPERATOR_ROLE's bare EOA
timelockScore  = min( 0,  0,  0,  0) =  0   -- every path here is 0 (no Safe in this set has a timelock)
compositeScore = floor(0.4*10 + 0.3*0 + 0.3*0 + 0.5) = 4
oracleAuthorityScore = 100  (not applicable -- no price-oracle dependency)
crossExposureScore   = 100  (checked against all 10 HIP-3 dexes' own signer sets -- zero overlap
                              on ANY role-holder address, not just the root Safe's owners)
```

`compositeScore = 4` -- CRITICAL band. `l1CappedComposite = min(4, 26) =
4` -- the L1 cap has no effect here (Kinetiq's own score is already far
below the L1's 26).

A single bare EOA sitting alongside two well-formed multisigs is exactly
the failure mode the minimum-over-paths convention exists to catch: a
reader who only checked `DEFAULT_ADMIN_ROLE` (the path this document's
first version stopped at) would have walked away with `compositeScore=50`
and no idea that `OPERATOR_ROLE`'s live-callable withdrawal/L1-operations
functions sit behind a single private key.

## The Safe(s) themselves: plain, no bypass

```
$ getOwners() -> 8 addresses (root Safe) / 7 addresses (treasury Safe)
$ getThreshold() -> 4 (both)
$ getModulesPaginated(0x1, 10) -> ([], 0x1)   -- zero modules enabled, both Safes
$ eth_getStorageAt(safe, GUARD_STORAGE_SLOT)  -> 0x0...0  -- no guard set, both Safes
```

No module, no guard on either Safe -- the exact precondition
`scripts/lib/scorers.py::_safe_rooted_scores`'s docstring requires before
trusting the raw threshold as the actual authority shape (a module or
guard can bypass or change what the threshold alone implies). Neither
Safe is the binding constraint on the final score regardless -- the bare
EOA is.

## Cross-exposure: checked live, not assumed

Every HIP-3 dex's own root/oracle signer set (deployer, `oracleUpdater`,
every `haltTrading`/`setOracle` sub-deployer, and each of THEIR resolved
k-of-n signers) was compared against EVERY role-holder address above (not
just the root Safe's 8 owners). Zero overlap across all 10 dexes --
`crossExposureScore = 100`, a real check (the same signer-overlap logic
`score_hip3_dex` already uses dex-to-dex), not a default left unchecked.

## A caught bug during derivation, not after

A first attempt at computing ABI function selectors used
`Web3.keccak(text=sig).hex()[2:10]`, silently producing every selector
shifted by one byte (`HexBytes.hex()` in this project's web3.py version
does NOT include a `"0x"` prefix, unlike `str(HexBytes(...))` -- an
assumption never verified before use). Caught by comparing the computed
`getOwners()` selector against the value already confirmed correct by
hand earlier in this same investigation (`0xa0e67e2b`) before writing the
selector helper into scorer code, not after a wrong result had already
been trusted.

## What changed and why (the same-day correction)

An adversarial-review workflow run against the FIRST version of this
scorer (before any of this was committed) returned seven findings. The
most severe: the scorer's own docstring claimed "every other role checked
... has zero current holders," but the code never called
`read_access_control_role_members` for anything except
`DEFAULT_ADMIN_ROLE` -- the claim was never actually checked, only
assumed to generalize from the one role that was. Independently
re-verified via fresh live `eth_call`s before touching any code: the
claim is false. `chains/hyperliquid/scripts/methodology_test.py::
score_kinetiq_staking_manager` was rewritten to query all five roles,
classify every holder, and take the minimum per METHODOLOGY.md 6.2 (see
"Scoring" above for the resulting numbers).

Two smaller, non-score-affecting fixes went in at the same time, both
also caught by the same review:
- Every "N bytes of code" figure previously cited in
  `data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md` used
  the hex STRING length rather than the actual byte count, inflating each
  by roughly 2x -- corrected in that file.
- That same file originally attributed all eight CoreWriter-calling
  functions it listed to a single library (`HIP3L1Write`); four of them
  are actually called via a separate sibling library (`L1Write.sol`), and
  three of the eight are dead code (defined, never invoked) -- corrected
  in that file, with no change to its conclusion.

A hardening fix went into the read helpers themselves, closing two related
gaps the same review flagged: `read_safe_hyperevm` previously had no
validation and could silently decode a non-Safe response into a
self-contradictory result (e.g. "5-of-0") with no warning; it now raises
`HyperEvmReadError` on a structurally impossible or too-short response,
and every raw `"0x" + hex[-40:]` address slice in this scorer now goes
through a shared `_address_from_hex` helper that raises the same error on
a too-short input (e.g. `"0x"`, a no-code address's real return value)
instead of silently producing a malformed `"0x0x..."` string that would
have failed confusingly several calls later.

## Honest limitations

- The intermediate Ownable admin contract (`0x6181cb...`) is not itself
  scored -- it is a pass-through; the Safe is the actual root, and scoring
  the pass-through separately would double-count the same authority.
- Whether any of the role-holder addresses above (either Safe, or the
  bare EOA) controls any OTHER Kinetiq contract beyond this one proxy was
  not checked.
- Neither Safe's owner addresses were attributed to named individuals,
  and the bare EOA holding `OPERATOR_ROLE` was not attributed either
  (e.g. to a specific Kinetiq operations key or service).
- This is Kinetiq's own protocol risk, not Hyperliquid's -- scored under
  the Hyperliquid ecosystem file because HyperEVM is Hyperliquid's own
  execution layer and the address itself was found via HIP-3 dex research,
  not because Kinetiq is affiliated with Hyperliquid's own team.

## Reproduction

```bash
cd chains/hyperliquid/scripts
python3 -c "
import json
from methodology_test import score_kinetiq_staking_manager
print(json.dumps(score_kinetiq_staking_manager(), indent=2))
"
```
