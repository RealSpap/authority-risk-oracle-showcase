# Euler V2 (eVaultFactory) on Base: same 8-signer DAO Safe as Plasma and Monad

2026-09-26. Closes the tracker board's open piste ("Euler V2 eVaultFactory `0x7F321498...9dDf8D0`,
[backlog note]"). Unlike
Fluid (one CREATE2 address shared across chains), Euler V2 addresses are genuinely PER-CHAIN,
sourced from Euler Labs' own official address book (`euler-xyz/euler-interfaces/addresses/<chainId>/`)
-- Base's own directory (`8453`), never guessed from the tracker's truncated citation or copied from
Plasma's addresses.

## The factory, confirmed live against Base's own official addresses

`eVaultFactory` = `0x7F321498A801A191a93C840750ed637149dDf8D0` (matches the address book's
`CoreAddresses.json` exactly, and the tracker board's own truncated citation). `eth_getCode` = 5,631
bytes -- the identical size `chains/plasma-ecosystem/scorers.py::score_euler_v2_evault_factory_plasma()`
documents for its own (differently-addressed) Plasma instance, consistent with the same
`GenericFactory` implementation. `owner()` reverts (GenericFactory has no `owner()`, confirmed
against Euler's own source in that same Plasma scorer's docstring) -- the real getter is
`upgradeAdmin()`, live-read as `0x605Aaf2CAD625dd5F855Bb055625cc1926f10A56`, matching
`GovernorAddresses.json`'s `eVaultFactoryGovernor` for Base exactly.

## A real cross-chain finding extended from 2 chains to 3

Plasma's scorer already found (2026-09-20) that Plasma's Euler DAO Safe (`0xfD30738f...`, 4-of-8) and
Monad's own Euler DAO Safe (a different address) share the identical 8-signer set. **This pass
independently re-checked Base's own DAO Safe live and found the same result**: Base's DAO
(`0x1e13B0847808045854Ddd908F2d770Dc902Dcfb8`, per the official address book) is ALSO a 4-of-8 Safe,
and its 8 owners are, as a set, IDENTICAL to Plasma's and Monad's -- verified by direct set comparison
against the already-documented `_KNOWN_EULER_DAO_SIGNERS_2026_09_19` constant, not eyeballed. **The
same 8-person committee now confirmed to govern Euler V2 on 3 of this oracle's 10 tracked ecosystems**
(Base, Plasma, Monad), each through a different Safe address (no CREATE2 sharing here, a genuine
per-chain re-deployment that happens to use the same underlying signers every time).

`eVaultFactoryTimelockController` on Base (`0x8452eF09799601b4993E1c0CADF65297587186B4`, per the
address book) has `getMinDelay()` = **345,600 seconds = exactly 4 days**, matching Plasma's documented
delay exactly. Not independently re-traced this pass: the Governor's `DEFAULT_ADMIN_ROLE`/PROPOSER/
EXECUTOR/CANCELLER role assignments (Plasma's scorer found PROPOSER = DAO Safe, EXECUTOR =
`address(0)`, CANCELLER = DAO + securityCouncil) -- reasonably expected to follow the same pattern
given every other data point matched exactly, but not asserted as confirmed without the live
`hasRole()` reads Plasma's own scorer performs; disclosed as the natural next verification step, not
guessed at.

## What this is and isn't

Pure investigation, no scorer built. `chains/base-ecosystem/scorers.py` has zero prior Euler
references. Adding this as a scored Base target would reuse the exact same pattern already built,
tested, and proven in `score_euler_v2_evault_factory_plasma()` (swap in Base's own addresses from the
official book above, re-verify the remaining role assignments live, retarget the RPC) -- not
duplicated wholesale this pass for the same reason Fluid wasn't (a genuinely new ~150+ line scorer
deserves its own dedicated test suite, not a rushed copy). Spap's go still needed to wire in a new
scored target.

## Verification

`eVaultFactory`/`upgradeAdmin`/DAO Safe/Timelock addresses all sourced from
`https://raw.githubusercontent.com/euler-xyz/euler-interfaces/master/addresses/8453/` (Core/Governor/
Multisig `Addresses.json`), never guessed from the tracker's truncated address citation. Every address
independently re-confirmed live against `https://mainnet.base.org`: `eth_getCode`, `upgradeAdmin()`,
`getOwners()`/`getThreshold()` on the DAO Safe (set-compared against the already-documented Plasma/
Monad signer set), `getMinDelay()` on the Timelock. No key read, nothing sent.
