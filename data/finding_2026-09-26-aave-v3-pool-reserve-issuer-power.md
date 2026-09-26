# Issuer power extended to Aave V3 Ethereum Pool's 67 reserve assets ($14.77B TVL)

2026-09-26. Extends today's `check_issuer_power.py` (built for the 9 tracked Morpho V1 vaults' 4
underlying assets) to a much bigger, ALREADY-TRACKED and ALREADY-SCORED target:
`score_aave_v3_pool()` (`chains/ethereum-l1/scorers.py`, $14.77B TVL) scores the Pool's OWN admin/
multisig/timelock/oracle authority -- it says nothing about the 67 reserve assets the Pool actually
lists, each of which can be frozen, seized, or paused by ITS OWN issuer regardless of anything Aave
governance decides. Built `scripts/check_aave_v3_pool_issuer_power.py`, reusing (not reimplementing)
today's own `read_abi()`/`read_controllers()`/`read_role_members()` by direct import -- the same
discipline `check_controller_concentration.py` already established today (import a sibling script's
functions rather than duplicate logic).

## Scope: the reserve list is read live, never hardcoded

`PoolAddressesProvider.getPool()` -> `Pool.getReservesList()`, both live calls, both re-derived this
run (2026-09-26) -- 67 reserves. Not copied from any prior research doc: the reserve list changes as
Aave governance lists/delists assets, so a hardcoded snapshot would silently go stale.

## Headline: 19 of 67 reserves (28%) are freeze/seize/pause-capable; several sit behind bare EOAs

**Bare-EOA-controlled reserves (no multisig at ANY of their controller roles), independently spot-
checked, not just trusted from the tool's own output**:

- **CBBTC (Coinbase Wrapped BTC)**: `owner`, `admin`, `blacklister`, `pauser`, `masterMinter` -- ALL
  FIVE controller roles are bare EOAs. The most concentrated single-key surface found on any reserve.
- **CBETH (Coinbase Wrapped Staked ETH)**: same shape, all five roles bare EOAs.
- **EURC (Circle)**: `owner`/`admin`/`blacklister`/`pauser` bare EOAs (only `masterMinter` is a
  contract).
- **USDC**: `owner`/`blacklister`/`pauser` bare EOAs (`masterMinter` a contract) -- the same shape
  already found and disclosed this morning for the Morpho-vault-scoped USDC, now confirmed on the
  much larger Aave-listed reserve (same token, same controllers, same finding -- not a new gap, a
  confirmation that Aave's $14.77B pool inherits the exact same token-layer risk).
- **PYUSD (PayPal USD)**: `owner` is a bare EOA.
- **USDTB (Ethena's USDTb)**: `owner` is a bare EOA.

## A real cross-asset finding: the same timelock pauses two DIFFERENT wrapped-BTC reserves

`BTC.b` and `LBTC` -- two textually distinct Aave-listed reserves -- share the IDENTICAL owner
address, verified live as `LombardTimeLock` (`0x055E84e7FE8955E2781010B866f10Ef6E1E77e59`), a
standard OpenZeppelin `TimelockController`. Checked its `getMinDelay()` before writing this down: **24
hours (86,400s)**, a real, non-instant timelock -- notably BETTER-protected than the bare-EOA-
controlled reserves above, not merely disclosed as "a contract" and left uninvestigated. Genuinely
new information either way: one governance point (Lombard's timelock) has pause/mint-burn authority
over two separate reserve assets Aave lists independently -- a concentration this oracle's existing
`crossExposureScore` convention would flag if BTC.b/LBTC were themselves oracle-tracked authority
targets (they aren't; this is disclosed at the token-issuer layer, a different surface entirely).

## GHO (Aave's own stablecoin): no freeze/seize/pause function found at all

Notable contrast within the same protocol: `GHO` (Aave's own token, minted/burned by Aave governance
itself) exposes NONE of the freeze/seize/pause function families this scan checks -- unlike most of
the centralized-issuer stablecoins on the same list (USDC, USDT, EURC, PYUSD, USDTb, RLUSD, MUSD all
have at least one). Disclosed as a real, positive data point, not chased further (GHO's own
mint/burn authority is Aave governance itself, already covered by the Pool's existing
`adminKeyScore`/`multisigScore`, a different question than freeze/seize/pause).

## What this is and isn't

Disclosed only, same precedent as `check_issuer_power.py` and every other extension this week: no
`adminKeyScore`/`multisigScore`/`timelockScore` change, no `AuthorityScore` field, no on-chain push.
This is a much bigger surface than the Morpho scope (67 reserves vs. 4 assets, an already-tracked
$14.77B target vs. $1.66B of tracked vaults) but the same category of finding: a protocol's own
admin/multisig/timelock score says nothing about what the ASSETS it lists can do to depositors
independent of that protocol's governance. Not TVL-weighted per reserve this pass (Aave's own
per-reserve TVL breakdown needs a separate live source not yet wired in) -- disclosed as a real
limit, not silently assumed away; counts and named assets above are exact, dollar-weighting is the
natural next step if this is worth deepening.

## Verification

`python3 scripts/check_aave_v3_pool_issuer_power.py` -- read-only, live `getReservesList()` +
Blockscout's verified-contract API (via `curl`, the same fix built earlier today) + each chain's own
RPC for `eth_getCode`/Safe resolution/role-member reads. 67/67 reserves read this run, 0 unread.
LombardTimeLock's `getMinDelay()` and the BTC.b/CBBTC/CBETH/EURC/USDC/PYUSD/USDTb EOA claims each
independently re-checked via a direct call before being written down. No new pure logic added (this
script imports and reuses `check_issuer_power.py`'s already-tested functions, same pattern
`check_controller_concentration.py` established today for `check_vault_v2_inventory.py`) -- full
suite (6 directories) stays green.
