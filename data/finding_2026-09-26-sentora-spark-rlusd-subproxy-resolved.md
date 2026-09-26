# Sentora x Spark RLUSD's $250M SubProxy owner: resolved, not a mystery

2026-09-26. Closes the one genuinely open point `data/finding_2026-09-25-vault-v2-inventory.md`
explicitly left unresolved rather than guessed at: `Sentora x Spark RLUSD` ($250.0M, Ethereum L1
Vault V2)'s owner, `0x3300f198988e4C9C63F75dF86De36421f06af8c4`, is a verified `SubProxy` contract
whose `owner()` call reverts and whose EIP-1967 admin/implementation slots both read zero -- neither
of this project's two known access-control conventions applied, and the 09/25 pass correctly stopped
rather than force a guess.

## What it actually is

The contract is not a proxy at all despite the name and despite living at a proxy-shaped address --
Blockscout's own `proxy_type: null` was the correct signal. It's **Sky/MakerDAO's own `SubProxy`
contract** (`src/SubProxy.sol`, © Dai Foundation, author `@amusingaxl`), a well-documented, standard
piece of Sky governance infrastructure: *"the SubDAO-level PauseProxy... Contracts that must be
controlled by SubDAO governance must authorize the SubProxy contract instead of the governance
contract itself."* It uses the classic Maker/Sky `wards` authorization pattern (`mapping(address =>
uint256) public wards`, `rely`/`deny`/`auth` modifier, an `exec(target, args)` that `delegatecall`s
on behalf of whichever address currently holds ward status) -- not `owner()`, which is why neither of
this project's two known conventions (single-owner getter, EIP-1967 proxy admin) matched.

## Who actually holds ward status, replayed from the full on-chain history (5 events total, not a sample)

Blockscout's decoded-logs endpoint returned the contract's ENTIRE `Rely`/`Deny` history (5 events,
confirmed complete -- `items_count=50` returned exactly 5, no pagination needed), replayed in block
order:

| Block | Event | Address | Verified name |
|---|---|---|---|
| 17344560 | Rely | `0xd1236a6A...` | (deployer, self-relied at construction) |
| 17344564 | Rely | `0xBE8E3e36...` | **DSPauseProxy** |
| 17344566 | Deny | `0xd1236a6A...` | (deployer's own ward revoked -- handoff complete) |
| 17514251 | Rely | `0x09e05fF6...` | **ESM** (Emergency Shutdown Module) |
| 23719448 | Rely | `0x6605aa12...` | **StarGuard** |

**3 currently active wards, all named, all verified contracts (re-checked independently via raw
`eth_getCode` before trusting Blockscout's decoded log -- all 3 have non-zero bytecode)**:
`DSPauseProxy` (Sky's main governance timelock's own execution proxy -- main Sky/MKR governance can
act through this SubProxy), `ESM` (the emergency shutdown module -- can act under its own emergency
conditions), and `StarGuard` (a bespoke spell-execution guard, its own bytecode contains codehash/
expiry checks and a hardcoded reference back to this exact SubProxy address -- almost certainly the
SubDAO-specific governance gate for day-to-day `exec()` calls, as opposed to main-Sky emergency
paths).

## What this is and isn't

A real, named answer to a real open question -- not a new score, no code shipped (this was a one-off
chase for one $250M data point, same scope the 09/25 finding set for it, not a reusable tool: the
technique -- Blockscout's decoded-logs endpoint for `Rely`/`Deny` history -- is documented here for
reuse if another `wards`-pattern contract needs the same treatment). Going a further hop into
DSPauseProxy's own Sky/MKR governance chain or StarGuard's specific spell-authorization logic was
judged out of scope, same reasoning as stopping the AUSD chase at role-member resolution rather than
also decoding each role's own internal permissions -- this is Sky's own long-public governance stack,
not something specific to this oracle's tracked vault.
