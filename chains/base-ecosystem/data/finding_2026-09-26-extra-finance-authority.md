# Extra Finance (Base): AddressRegistry owner is a real 3-of-6 Safe, NOT the 2-of-3 the tracker board cited

2026-09-26. Investigates the tracker board's open piste ("Extra Finance Lending
[backlog note]
[backlog note]"). Pure investigation, no scorer built -- adding Extra Finance is a new
target on an already-tracked ecosystem, Spap's decision.

## `LendingPool.owner()` is a dead end for authority purposes -- a deployment factory, not governance

`0xbb505c54D71E9e599cB8435b4F0cEEc05fc71cbd` (`LendingPool`, verified) exposes `owner()`/
`emergencyPauseAll()`/`unPauseAll()`/`renounceOwnership()`. Chased live, one hop at a time, checking
identity at each step rather than assuming: `owner()` -> `0x5a70429e...` (verified
`TransparentUpgradeableProxy`) -> its EIP-1967 admin slot -> `0x326bf61b...` (verified `ProxyAdmin`)
-> its own `owner()` -> `0xF3D7FD8F...` (verified `UpgradeableContractFactory`). Three hops land on a
deployment factory, not a Safe or any operational authority -- **this path answers "who can redeploy
new instances of this logic", not "who can change this pool's live risk parameters"**. Disclosed as
a dead end for THIS purpose rather than reported as if it were the real authority.

## `AddressRegistry.owner()` is the real, live authority: a verified 3-of-6 Gnosis Safe

`LendingPool.addressRegistry()` -> `0x85603119C938750Dfb5904f8a501b64F3F3A01D2` (verified
`AddressRegistry`) -> `owner()` -> `0x89F0885DA2553232aeEf201692F8C97E24715c83`, live-confirmed via
`getOwners()`/`getThreshold()` as a genuine Gnosis Safe: **3-of-6**, not the 2-of-3 the tracker board
cites. Neither the Safe's address nor its shape matches the board's stale citation -- either the
board recorded a DIFFERENT Safe entirely (a per-pool guardian, not this registry-level owner) or this
Safe was reconfigured (more owners added, threshold raised) since that note was written. Not
guessed at further: this is the address this pass actually found and verified live, stated as such,
not force-fit to match a 4+-day-old citation with a different address.

## No timelock found on this path either -- matches the board's own disclosure

No propose/execute pattern, no delay contract found between the Safe and `AddressRegistry`'s state --
a 3-of-6 signature is immediate. Consistent with what the tracker board already flagged ("aucun
[backlog note]").

## What this is and isn't

Disclosed only, no scorer built. If Extra Finance is added as a target later: `AddressRegistry.owner()`
is the real authority to score (3-of-6 Safe, no timelock), not `LendingPool.owner()` (a factory
artifact) -- this distinction is the main value of this pass, not just a number. Signer-overlap check
against other tracked Base Safes not done this pass (natural next step before scoring).

## Verification

All addresses read live against `https://mainnet.base.org`, each hop's identity confirmed via
Blockscout's verified contract name before following it further (never assumed from a bare address).
`getOwners()`/`getThreshold()` read directly on the final Safe. No key read, nothing sent.
