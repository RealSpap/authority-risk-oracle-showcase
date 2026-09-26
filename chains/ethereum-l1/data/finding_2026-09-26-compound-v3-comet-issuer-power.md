# Issuer power extended to all 3 tracked Compound V3 Comet markets (L1, Base, Arbitrum)

2026-09-26. Extends today's `check_issuer_power.py`/`check_aave_v3_pool_issuer_power.py` pattern to
this oracle's 3 already-tracked, already-scored Compound V3 Comet markets
(`score_compound_v3_cusdc` on Ethereum L1, `score_compound_v3_comet_arbitrum_usdc`,
`score_compound_v3_comet_base_usdc`) -- their own composite scores say nothing about what the base
(borrowed) asset or any of the collateral assets they list can do to depositors/borrowers
independent of Compound's governance. Built `scripts/check_compound_v3_comet_issuer_power.py`,
reusing `check_issuer_power.py`'s functions directly (`check_issuer_power.py`'s own
`BLOCKSCOUT`/`RPC` dicts extended with chain 42161 for this, purely additive).

## Scope: every base+collateral asset read live from each Comet, never hardcoded

`baseToken()` + `numAssets()`/`getAssetInfo(i)` on all 3 Comets, live, 2026-09-26 -- 30 asset
instances (13 collateral + 1 base on L1, 5+1 on Base, 9+1 on Arbitrum), 30 distinct (chain, address)
pairs (no cross-chain address collisions this run -- unlike the Morpho/Aave sweeps, no CREATE2-shared
token address appeared twice with a different chain here). 0 unread.

## Headline: 13 of 30 (43%) freeze/seize/pause-capable

**USDC's controllers are COMPLETELY DIFFERENT on each of the 3 chains** (distinct `owner`/`admin`/
`blacklister`/`pauser`/`masterMinter` addresses on L1, Base, and Arbitrum) -- Circle runs fully
separate operational keys per deployment, all bare EOAs except `masterMinter` (a small contract on
each). This is the same shape already disclosed for USDC in this morning's Aave/Morpho findings,
now confirmed identical on a third chain (Arbitrum's native USDC, not previously checked).

**CBBTC's controllers are only PARTIALLY shared across chains**: L1 and Base CBBTC share the
identical `owner`/`admin`/`masterMinter`/`pauser` addresses (all bare EOAs), but a DIFFERENT
`blacklister` address per chain (`0x5130bF38...` on L1 vs `0x158cFA49...` on Base) -- a real,
specific data point not disclosed before (the earlier Aave finding only checked Base's CBBTC).

**Real multisigs, not bare keys, on several less-common collateral assets**:
- `TBTC` (Threshold's tBTC): a **6-of-9 Safe** owns it on BOTH Base and Arbitrum (same threshold,
  not independently checked for identical signers), while L1's tBTC owner is a non-Safe 15,123-byte
  contract (not chased further this pass).
- `TETH` (Arbitrum collateral): a **5-of-7 Safe** holds BOTH `owner()` and `blacklister()`.
- `deUSD`/`sdeUSD` (Elixir, both tracked as L1 collateral): the SAME **3-of-5 Safe**
  (`0xD7CDBde6C9DA34fcB2917390B491193b54C24f24`) owns both the base asset and its staked wrapper --
  one key controls two listed collateral assets.

**Unresolved, disclosed as open rather than guessed at**: `ARB`, `EZETH`, `GMX` (Arbitrum collateral)
resolve `owner()` to contracts (2593B/2739B, and GMX has no owner getter that resolved) not yet
classified as Safe or otherwise -- would need the same one-hop chase already used elsewhere in this
project if pursued further. `WEETH`'s `blacklister()` is a 142-byte contract, also not chased.

## What this is and isn't

Disclosed only, same precedent as every other extension this week: no `adminKeyScore`/
`multisigScore`/`timelockScore` change, no `AuthorityScore` field, no on-chain push. Not TVL-weighted
per asset this pass (same honest limit as the Aave extension). No new pure logic added -- this script
imports and reuses `check_issuer_power.py`'s already-tested functions, same pattern
`check_controller_concentration.py`/`check_aave_v3_pool_issuer_power.py` already established today.

## Verification

`python3 scripts/check_compound_v3_comet_issuer_power.py` -- read-only, live `getAssetInfo()` +
Blockscout's verified-contract API (via `curl`) + each chain's own RPC. 30/30 instances read this
run, 0 unread. Full suite (6 directories) stays green after extending `check_issuer_power.py`'s
chain dicts.
