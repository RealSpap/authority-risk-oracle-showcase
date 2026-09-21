# Hyperliquid -- scored targets, 2026-09-17

**Updated 2026-09-18**: added an 8th target, Ventuals vHYPE staking (a
third HyperEVM-native target, found the same way as the two added the
day before) -- see this file's own entry below and `chains/hyperliquid/
data/methodology_test_2026-09-18-ventuals-vhype-staking.md` for the full
derivation. Everything else on this page is unchanged from 2026-09-17.

Promotes [`../METHODOLOGY.md`](../METHODOLOGY.md) section 4's numeric
mapping (4.6) into the standard `scorers.py` / `score_all()` shape every
other ecosystem in this project uses: [`../scorers.py`](../scorers.py).
The underlying read-and-score logic was already fully implemented and
live-tested in `scripts/methodology_test.py` on 2026-09-16 -- this pass
adds `score_all()`, per-target failure isolation, and the
`l1CappedComposite` field METHODOLOGY.md 4.5 specifies but the methodology
test script did not yet compute.

## Summary table

| Target | Key | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | l1CappedComposite |
|---|---|---|---|---|---|---|---|---|
| Hyperliquid L1 (HyperCore validator set) | `0xeA394CD63CA3a5C8A130Bb2b955cC71C22E5ea6C` (synthetic, no key controls it -- METHODOLOGY.md 4.7) | 15 | 65 | 0 | 40 | 100 | **26** | n/a (this IS the L1) |
| HIP-3 dex `xyz` (trade[XYZ]) | `0x88806a71d74ad0a510b350545c9ae490912f0888` (deployer) | 10 | 15 | 0 | 4 | 100 | **9** | **9** (min(9, 26), no effect this run) |
| HIP-3 dex `io` | `0x320c8988e3d1b5198f335802d7bfd2728a8fcac6` (deployer) | 50 | 39 | 0 | 58 | 60 | **32** | **26** (min(32, 26) -- the L1 cap actually binds here, unlike xyz) |
| HIP-3 dex `para` | `0x8888888c43cbb7e1c4132542e46831bffd866ed3` (deployer) | 10 | 15 | 0 | 15 | 100 | **9** | **9** (min(9, 26), no effect this run) |
| HIP-3 dex `mkts` | `0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec` (deployer, shared with `km`) | 10 | 15 | 0 | 15 | 80 | **9** | **9** (min(9, 26), no effect this run) |
| Kinetiq HIP3StakingManager (HyperEVM) | `0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec` (SAME address as `mkts`/`km`, but this is its HyperEVM smart-contract identity, a different authority surface -- see `data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md`) | 10 | 0 | 0 | 100 | 100 | **4** | **4** (min(4, 26), the L1 cap has no effect -- Kinetiq's own score is already far below it) |
| para StakingVault (HyperEVM) | `0x8888888c43cbb7e1c4132542e46831bffd866ed3` (SAME address as HIP-3 dex `para`, but this is its HyperEVM smart-contract identity, a different authority surface -- see `data/methodology_test_2026-09-17-para-staking-vault.md`) | 10 | 0 | 0 | 100 | 100 | **4** | **4** (min(4, 26), the L1 cap has no effect) |
| Ventuals vHYPE staking (HyperEVM) | `0x8888888192a4a0593c13532ba48449fc24c3beda` (SAME address as still-dormant HIP-3 dex `vntl`, but this is its HyperEVM smart-contract identity -- see `data/methodology_test_2026-09-18-ventuals-vhype-staking.md`) | 50 | 35 | 0 | 100 | 100 | **31** | **26** (min(31, 26) -- the L1 cap actually binds here) |

`xyz`/L1 match `data/methodology_test_2026-09-16.md`'s hand-derived numbers
exactly. `io` (added 2026-09-17, same day, as a follow-up promotion),
`para` (added the same day, as a second follow-up), and `mkts` (added the
same day, as a third follow-up) are all new -- see
below for why each was picked.

## Why these targets specifically

`xyz` is the largest HIP-3 perp dex by listed assets (120 assets, ~$3.9B
open interest) -- chosen because it exercises every HyperCore-specific
mechanic the methodology had to solve (native multisig, sub-deployer
delegation, deployer oracle push). The Hyperliquid L1 itself is scored
because METHODOLOGY.md 4.5 makes it the authority ceiling for every other
HyperCore target (`l1CappedComposite`), the same role
`score_rollup_l1_authority()` plays for Robinhood Chain.

`io` was added as a second HIP-3 dex after a live open-interest sweep
across all 10 existing dexes found it is the genuine second-most-used one
by real economic weight (~$55.4M open interest, ~$39.5M net deposit) -- NOT
`flx`, which METHODOLOGY.md 4.2's live table lists with more assets (15 vs.
`io`'s 10) but which turned out, on this same live check, to carry ZERO
open interest and near-zero net deposit (essentially dormant). Picking a
target by listed-asset count alone would have promoted a dormant dex; this
project's own precedent (declining to promote fUSD/aBTC as Ethereum L1
flagship targets despite a real finding attached to them) is the same
discipline applied here. `io` is also structurally distinct from `xyz`: its
weakest oracle-authority path is the DEPLOYER itself (3-of-5), not a
bypassable sub-deployer -- its 4-of-6 `oracleUpdater` is actually the
stronger key, but rule 4.2.3 keeps the deployer in the oracle-authority set
regardless (it can reassign sub-deployers at will and reach `setOracle`
that way), so the deployer's own weaker threshold is what actually binds.
`io` also shares root keys with `flx` and `hyna` (`crossExposureScore=60`),
matching METHODOLOGY.md 4.5's own already-documented finding about the
shared oracle-updater signer set -- re-derived live here, not assumed.

`para` was promoted the same day, as a second follow-up: this file's own
earlier draft had already flagged it (`para` ($15.0M OI) ... reasonable
future candidate) without acting on it -- this pass re-swept live (fresh
numbers: ~$15.1M open interest, ~$10.5M total net deposit across 35
listed assets, confirming the earlier flag wasn't a stale or noisy
reading) and promoted it. `para`'s root-control key is a BARE SINGLE KEY
(k=1, n=1) -- structurally identical in shape to `xyz`'s own single-key
deployer, but with roughly $3.9B less capital sitting behind that same
weak-key pattern. `dexesSharingARootKey` (already computed by
`score_hip3_dex`) confirms `para`'s deployer does NOT overlap with any
other tracked dex's root key, despite superficially similar vanity
"0x8888888..." address prefixes shared with a couple of other (still
unpromoted, still zero-OI) dexes -- `crossExposureScore=100`.

`mkts` was promoted the same day, as a third follow-up: the closest real
runner-up to `para` in the same sweep (~$6.7M open interest, ~$5.2M total
net deposit across 24 listed assets). `mkts`'s root-control key is ALSO a
bare single key (k=1, n=1) -- and, unlike `para`, it genuinely IS shared
with another tracked dex: `dexesSharingARootKey` returns `["km"]`
(`km` itself still reads $0 open interest, i.e. dormant) --
`crossExposureScore=80`, a real, live-detected finding, not a coincidence:
the same key that controls a dormant market also controls a real,
actively-traded one, so a compromise of that one key is not a "small dex"
problem. Both `para` and `mkts`/`km`'s deployer addresses also turned out
to carry live HyperEVM bytecode (unlike `xyz`/`io`, which have none) --
`mkts`/`km`'s resolves, via a real EIP-1967 admin chain, to a 4-of-8
Gnosis Safe. A first pass (Hyperliquid's own CoreWriter docs plus the
implementation's bytecode containing the CoreWriter system address) read
as strong evidence this was a second root-control path over the perp
markets themselves; reading the implementation's actual VERIFIED SOURCE
corrected that -- it is Kinetiq's own kHYPE staking-manager contract, and
every CoreWriter call it makes is a staking/trading helper, not a
dex-admin action. Not folded into either score either way (and even under
the stronger, corrected-away reading, could not have lowered it: the
direct HyperCore-native single key already scores adminKeyScore=10, near
the floor) -- full derivation and correction in
`data/finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md`.

Kinetiq's `HIP3StakingManager` was promoted the same day, as a sixth
target and the FIRST HyperEVM-native one this project scores -- every
target before it was HyperCore-native. The staking manager defines five
OpenZeppelin `AccessControlEnumerable` roles; all five were queried live,
not just the one (`DEFAULT_ADMIN_ROLE`) that happened to resolve to a
well-formed 4-of-8 Gnosis Safe with zero modules and no guard. The other
three turned out NOT to be uniformly benign: `MANAGER_ROLE` is held by
the same Safe, but `OPERATOR_ROLE` is held by a BARE EOA and
`TREASURY_ROLE` by a SEPARATE 4-of-7 Safe sharing only 1 of 7 owners with
the "root" one. Per METHODOLOGY.md 6.2's minimum-over-full-power-paths
convention (already applied the same day on the Solana side), the bare
EOA is the binding constraint: `adminKeyScore=10`, `multisigScore=0`,
`compositeScore=4` (CRITICAL band). This is a same-day, pre-commit
self-correction: a first version of the scorer checked only
`DEFAULT_ADMIN_ROLE` and its docstring wrongly generalized "the rest must
be similarly benign" -- an adversarial review caught that this was never
actually checked, and re-verifying live found it false. `l1CappedComposite
=4` (min(4, 26), no effect -- Kinetiq's own score is already far below the
L1's). Cross-checked live against every HIP-3 dex's own signer set (every
role-holder address, not just the root Safe's owners): zero overlap,
`crossExposureScore=100`. Full derivation, including the caught
role-coverage gap and a caught selector-computation bug (a web3.py
`HexBytes.hex()` prefix assumption that silently shifted every ABI
selector by one byte, caught before it reached scorer code):
`chains/hyperliquid/data/methodology_test_2026-09-17-kinetiq-staking-
manager.md`.

`para StakingVault` was promoted the same day, as a seventh target and
the SECOND HyperEVM-native one -- closing this project's own explicitly
left-open question about `para`'s EVM-side proxy (previously read only as
"admin slot zero, consistent with an immutable proxy," per this file's
own earlier text). That earlier read was wrong: this is a UUPS proxy,
which never uses the EIP-1967 admin slot at all -- reading zero there was
never evidence of "no admin." The real implementation (contract name
`StakingVault`, verified source) manages a real custody/staking vault --
`delegatorSummary()` reads 500,801.29 HYPE currently delegated (~$41.7M
at the live $83.324/HYPE price) -- with its access control deferred
entirely to an external `RoleRegistry` contract (Solady `EnumerableRoles`
+ `Ownable2StepUpgradeable`, a DIFFERENT library than Kinetiq's
OpenZeppelin `AccessControlEnumerable`, independently confirming the same
"check every role, take the minimum" methodology generalizes). Three
paths resolved: `RoleRegistry.owner()` (a 1-of-1 Safe), `MANAGER_ROLE`
(every fund-moving function -- resolves to a standard, verifiable
EIP-1967 proxy delegating to an implementation with NO verified source,
degraded to this project's existing conservative unresolved-authority
fallback rather than guessed at), and `OPERATOR_ROLE` (a separate 1-of-3
Safe). `compositeScore=4` (CRITICAL), dominated by the unverified
implementation behind `MANAGER_ROLE`. An adversarial review of this
addition (before any of it reached a commit) confirmed 14 findings and
refuted 4 (the refuted ones traced to reviewer agents checking against
the live public repo, which didn't yet have this pre-commit code) --
surfacing several real, general fixes to the SHARED HyperEVM read
helpers: an uncaught RPC-revert crash, a bare `ValueError` escaping every
project-defined exception type, a `none_means_renounced` gap ported from
the same day's Solana Drift correction, missing role-hash length
validation, and a cross-exposure check that only compared top-level
Safe/proxy addresses, never owner addresses nested one level inside a
resolved Safe. None of these were triggered by Kinetiq's own target;
all were closed before this reached a commit. Full derivation:
`chains/hyperliquid/data/methodology_test_2026-09-17-para-staking-
vault.md` and `data/correction_2026-09-17-para-staking-vault-adversarial-
review.md`.

**Ventuals vHYPE staking was promoted 2026-09-18**, an eighth target and
a THIRD HyperEVM-native one -- found while chasing a "Similar Match"
contract this file previously flagged next to `para` StakingVault's own
implementation (that specific lead was a dead end; see the updated
bullet below). Sweeping every HIP-3 dex deployer for its OWN EIP-1967
implementation slot (not just whether it has code at all) found that
still-dormant dex `vntl` ALSO carries live HyperEVM infrastructure -- a
real, NAMED liquid-staking product this time (`hyperevmscan.io`'s
contract-creator tag "Ventuals vHYPE: Deployer", independently confirmed
by a `VNTLS`/"Ventuals" token in the official spot-token list), managing
~$610K in delegated HYPE. Structurally identical to `para`'s own case
(a `RoleRegistry` rooting `owner()` plus two operational roles) but with
one crucial difference: this target's `MANAGER_ROLE` holder IS a
verified contract, so its practical authority was resolved by actually
reading its source (confirming every privileged function routes to the
SAME `roleRegistry.owner()`) rather than staying at the conservative
unresolved fallback `para`'s analogous, UNVERIFIED holder correctly
uses. All three paths land on the same 2-of-3 Gnosis Safe --
`compositeScore=31`, notably safer than `para`'s `4`, purely because this
operator published verified source for every layer. `l1CappedComposite
=min(31,26)=26` -- the L1 cap actually binds here. Full derivation:
`chains/hyperliquid/data/methodology_test_2026-09-18-ventuals-vhype-
staking.md`.

## What this does NOT cover yet

- 6 other HIP-3 dexes exist (flx, vntl, hyna, km, abcd, cash -- `km` is
  `mkts`'s dormant same-key sibling, not itself a separate scored target;
  see METHODOLOGY.md 4.2's live table for their raw k-of-n shapes). A
  fresh live re-sweep on 2026-09-17 (same day `para`/`mkts` were promoted)
  confirmed all six are STILL at exactly $0 open interest -- genuinely
  dormant, not a stale reading carried over from the first sweep.
  `score_hip3_dex(name)` already generalizes to any of these without new
  code, only a new `SIMPLE_SCORERS` entry, should a future sweep find
  real usage. `vntl` itself remains unpromoted as a HIP-3 dex on this
  basis -- its HyperEVM-side infrastructure (Ventuals vHYPE) was
  promoted separately, the same distinction already drawn for
  `mkts`/Kinetiq: the underlying perp market is dormant, but the
  EVM-side product sharing its deployer address is real.
- HyperCore reads still rest on the single official operator API (gap G9 in
  the methodology test): no third-party RPC market exists for HyperCore,
  and the independent second source described in METHODOLOGY.md section 2
  (a self-run non-validator node with `--serve-info`) has not been stood
  up. This is a disclosed, structural limitation of the ecosystem itself,
  not something a longer retry loop can fix -- unlike the Solana
  second-RPC rate-limit from the same day's Solana promotion, which was a
  transient availability issue on an existing independent source.
- Whether `mkts`/`km`'s, `para`'s, or `vntl`'s deployer addresses'
  HyperEVM bytecode has ANY bearing on the HIP-3 dex authority itself (as
  opposed to the separately-scored staking-manager/vault contracts behind
  each) is now CLOSED for all three -- none of their verified source
  reaches any dex-admin-privileged CoreWriter action. **This gap is now
  FULLY closed for all 10 tracked dexes, not just these three** (a stale
  reading, corrected 2026-09-18): the sweep that found Ventuals vHYPE
  checked `eth_getCode` on all 10 dexes' deployer addresses, live --
  `xyz`, `flx`, `hyna`, `abcd`, `cash`, and `io` all read `0x` (no code at
  all, not just an unchecked EIP-1967 slot -- a non-contract address has
  no proxy pattern to find), re-confirmed fresh rather than assumed. Only
  `vntl`/`km`/`mkts`/`para` carry any HyperEVM bytecode, and all four are
  now fully investigated. Worth re-checking on any future Hyperliquid
  re-scout, since a currently-EOA deployer address could always gain code
  later, but nothing is currently unchecked. See `data/finding_2026-09-17-
  hyperliquid-hip3-evm-proxy-authority.md`.
- Kinetiq's own protocol beyond its one `HIP3StakingManager` contract,
  `para`'s operator's own infrastructure beyond its one `StakingVault`,
  and Ventuals' own infrastructure beyond its `StakingVault`/
  `StakingVaultManager` pair -- whether any of these targets' role-holder
  addresses (Kinetiq's 4-of-8 Safe, its intermediate Ownable admin
  contract, its `OPERATOR_ROLE` bare EOA, its separate `TREASURY_ROLE`
  Safe; `para` StakingVault's 1-of-1 owner Safe, its unverified
  `MANAGER_ROLE` holder, its 1-of-3 `OPERATOR_ROLE` Safe; Ventuals vHYPE's
  2-of-3 Safe) controls any OTHER contract was not checked. Nor were any
  of these addresses attributed to named individuals or entities. `para`
  StakingVault's unverified `MANAGER_ROLE` holder's actual logic remains
  deliberately not reverse-engineered from bytecode alone -- Ventuals
  vHYPE's own analogous case (2026-09-18) shows this caveat is not merely
  theoretical: an identically-shaped `MANAGER_ROLE` holder turned out,
  once its VERIFIED source was actually read, to resolve to the exact
  same authority as the rest of that target, materially changing its
  score (4 -> 31 in shape, though these are two different targets, not
  the same one recomputed).
- A "Similar Match" contract `hyperevmscan.io` flagged alongside `para`
  StakingVault's implementation (`0x8888888635cb74f39505f91cf79551ac4fd75bc9`,
  also named `StakingVault`, also verified) led directly to finding
  Ventuals vHYPE (2026-09-18) -- but NOT because that specific contract
  turned out to be in use by another dex: sweeping all 10 dexes' own
  EIP-1967 implementation slots found none of them point at that exact
  address. It remains unattributed -- bytecode-similar to both `vntl`'s
  and `para`'s own vaults, deployed the same day as `vntl`'s per
  `hyperevmscan.io`, but not currently reachable from any tracked dex's
  deployer address. Possibly an earlier deployment, a test instance, or a
  vault for a different asset entirely -- set aside, not chased further.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/hyperliquid')
from scorers import score_all
for r in score_all():
    print(r['label'], r['compositeScore'], r.get('l1CappedComposite'))
"
```
