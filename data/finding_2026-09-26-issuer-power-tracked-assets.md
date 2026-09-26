# Issuer power on the 4 assets this oracle's own tracked vaults actually hold

2026-09-26. Backlog item 15 (`data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md:499-
519,717-719`: "An issuer-power tag per vault asset (freeze, seize, pause, upgrade, and who holds the
roles)... Cheap, because verified ABIs are public"). That research was a market-wide sweep
(`chains/ethereum-l1/scripts/sweep_asset_authority.py`, 500+ assets) never scoped to what THIS oracle
tracks. Built the scoped version: `scripts/lib/issuer_power.py` (17 unit tests) +
`scripts/check_issuer_power.py`.

## Scope: only 4 distinct tokens behind the 9 tracked Morpho V1 vaults

Queried Morpho's public GraphQL API live (2026-09-26) for each tracked vault's underlying asset:
USDC on Base (4 vaults), USDT on Ethereum L1 (1 vault), USDC on Ethereum L1 (3 vaults), AUSD verified
on Ethereum L1 as `AgoraDollarErc1967Proxy` (1 vault, held on Monad).

## Bug caught before it shipped: Blockscout 403s bare `urllib.request`

First draft used Python's stdlib `urllib.request` directly and got 4/4 reads silently failing with
"not verified or ABI unreadable" -- looked like a real gap until a raw `curl` to the same URL returned
full JSON instantly. Root cause: Blockscout returns HTTP 403 to requests with no `User-Agent` header
(`urllib.request`'s default `Python-urllib/3.9` UA), not to the request itself. Fixed by adopting the
exact pattern `sweep_asset_authority.py`'s own `curl()` helper already uses: shell out to
`curl -A "Mozilla/5.0"` instead of `urllib.request`. Re-verified independently before writing this
down: re-ran the read as raw curl, confirmed identical output, only then trusted the tool's own
results below.

## USDC (Base and Ethereum L1): owner, admin, blacklister, pauser are all bare EOAs

Both USDC deployments (Circle's `FiatTokenProxy`) expose the same freeze/pause/upgrade surface:
`blacklist`/`unBlacklist`/`updateBlacklister`, `pause`/`unpause`/`updatePauser`,
`upgradeTo`/`upgradeToAndCall`. Live-read controller addresses, independently re-verified with a raw
`eth_getCode` call (not just trusted from the tool's own output) -- all 4 return `0x` (zero
bytecode, confirmed EOA, no Safe/multisig wrapper at all):

- Base: `owner` `0x3ABd6f64A422225E61E435baE41db12096106df7`, `admin`
  `0x4fc7850364958d97B4d3f5A08f79db2493f8cA44`, `blacklister`
  `0x1f2e3A640175d20ac31ed523B6733B977173E277`, `pauser`
  `0xD3571B3bc51CECFf49194AD67aFFFC648d5e07b4` -- all EOA. `masterMinter` is the one exception: a
  7667B-and-5470B-class contract on the two chains respectively, not a bare key.
- Ethereum L1: `owner` `0xFcb19e6a322b27c06842A71e8c725399f049AE3a`, `blacklister`
  `0x0A06BE16275B95a7d2567fBdAE118b36C7DA78F9`, `pauser`
  `0x4914f61d25e5C567143774B76EdbF4D5109a8566` -- all EOA.

Stated precisely, not overclaimed: a bare on-chain EOA does not necessarily mean a single human with a
seed phrase -- Circle may operate these through internal custody/HSM controls invisible on-chain. What
IS a verified, disclosable fact: **the smart contract itself enforces no multisig threshold on
freeze/pause/upgrade for either USDC deployment** -- a single signature at these addresses is
on-chain-sufficient to blacklist any address, pause the entire token, or push a new implementation.
This is a genuinely different risk shape from every vault-layer controller this oracle already scores
(Steakhouse, Gauntlet, etc. all sit behind real multisigs) -- the vault's own governance can be a 5-of-10
Safe while the token it holds can be frozen by one EOA signature.

## USDT (Ethereum L1): owner is a 5705-byte non-Safe "Owner" contract, doesn't resolve further

`TetherToken`'s `owner()` resolves to `0xC6CDE7C39eB2f0F0095F41570af89eFC2C1Ea828`, a verified
5705-byte contract -- not a bare EOA, but also not a Gnosis Safe (`safe_owners_and_threshold` returns
no match). Chased one hop, matching this project's established owner-resolution convention
(`score_aave_v3_pool`'s executor chain, the Vault V2 inventory's `VaultV2Supervisor` hop): tried
`owner`/`admin`/`getOwner` on that contract, all three return nothing. A genuine, checked dead end --
Tether's bespoke ownership contract, not further resolvable with the getters this project already
knows -- disclosed as such, not guessed at. Function surface: `addBlackList`/`removeBlackList`
(freeze), `destroyBlackFunds` (seize -- the only asset of the 4 with a disclosed seize function),
`pause`/`unpause`. No `upgradeTo*` exposed (Tether's proxy pattern differs from the OZ-style USDC/AUSD
upgrade path).

## AUSD (Ethereum L1, held by the Monad vault): role-gated, but resolved outright -- not OZ AccessControl

`AgoraDollarErc1967Proxy` exposes `batchFreeze`/`batchUnfreeze`/`grantFreezerRole`/`revokeFreezerRole`
(freeze) and `grantPauserRole`/`revokePauserRole`/`setIsBridgingPaused`/`setIsBurnFromPaused` (pause).
First pass (above) found no match in `KNOWN_CONTROLLER_GETTERS` and assumed this needed
`_replay_role_holders()`-style event-log replay, the technique `score_aave_v3_pool`'s RISK_ADMIN
discovery already uses elsewhere in this project (OpenZeppelin AccessControl, `RoleGranted`/
`RoleRevoked` events). **Wrong assumption, checked before building the replay**: Agora's contract is
not OZ AccessControl at all -- it's a bespoke role registry with direct `address[]` getters
(`getFreezerRoleMembers()`, `getPauserRoleMembers()`, `getMinterRoleMembers()`,
`getBurnerRoleMembers()`, `getBridgeMinterRoleMembers()`, `getBridgeBurnerRoleMembers()`,
`getRateLimitManagerRoleMembers()`, `getAccessControlManagerRoleMembers()`) -- no event replay needed,
a single live call resolves the full member set. Added `KNOWN_ROLE_MEMBER_GETTERS` +
`read_address_array_getter()` (new generic helper in `scripts/lib/web3_utils.py`, mirroring
`read_address_getter()` for `address[]`-returning getters, 3 new unit tests) to cover this family.

**Live-read and independently re-verified (raw `eth_getCode`), every role has exactly ONE member,
and every one of them is a bare EOA except one**: `FREEZER_ROLE` (`0xcF7D2a5...`), `PAUSER_ROLE`
(`0x0b8Dd71...`), `MINTER_ROLE` (`0x65e2866...`), `BURNER_ROLE` (`0x4375170...`),
`RATE_LIMIT_MANAGER_ROLE` (`0x72744c5...`), and -- most notable -- **`ACCESS_CONTROL_MANAGER_ROLE`
itself (`0x68898B7...`), the role that grants/revokes every other role, is also a single bare EOA**.
Only `BRIDGE_MINTER_ROLE`/`BRIDGE_BURNER_ROLE` (both the same address, `0x9CaB7Ed...`) resolve to a
1200-byte contract, not further classified this pass (not a recognized Safe). AUSD's entire access
surface -- freeze, pause, mint, burn, and the role that controls all of those roles -- sits behind
single keys, no multisig anywhere in the chain, a stronger and more precisely-stated version of the
same shape already found on USDC.

## Same-day follow-up: `sweep_token_function_guards.py` run scoped to the 4 tracked assets

Closed the exact limit the previous section flagged: ran the source-modifier reader (already built,
market-wide) scoped to just these 4 tokens. USDC (both chains) and USDT confirm exactly the
well-known, standard guards (`onlyBlacklister`/`onlyPauser`/`onlyOwner`/`ifAdmin`) -- nothing new
there. **AUSD's `changeAdmin`/`upgradeToAndCall` came back "NO GUARD FOUND" -- checked before writing
it down, and it's a false negative, not a real gap.** The regex reader matched a concrete-looking
function body from OpenZeppelin's OWN vendored `TransparentUpgradeableProxy.sol`, bundled in
Blockscout's `additional_sources` as a compilation dependency -- not AUSD's actual deployed logic.
Read the real source directly: AUSD's proxy overrides `_fallback()` with its own inline check
(`if (msg.sender == PROXY_ADMIN_ADDRESS) { if (msg.sig != ...upgradeToAndCall.selector) revert
ProxyDeniedAdminAccess(); ... }`) -- genuinely gated, just via fallback dispatch rather than a named
external function with a modifier, a pattern neither this project's ABI-based reader nor the
regex-based one is built to recognize.

**Chased `PROXY_ADMIN_ADDRESS` live, one hop at a time, and it connects straight back to today's own
earlier finding**: `proxyAdminAddress()` = `0xB8fCC66d613e5f54ee6A425DDbf4a2fDBE4Dedee`, a verified
`AgoraProxyAdmin` contract (Ownable2Step, not a Safe). Its `owner()` = `0x68898B77EbF7b55dCA8A2e62d6Fd74959a2930e2`
-- **the exact same bare EOA already found above holding `ACCESS_CONTROL_MANAGER_ROLE`** (the role
that grants/revokes every business-logic role on this token). One single key therefore controls both
AUSD's entire role registry AND the ability to replace the contract's implementation outright --
a stronger, now fully-connected version of the "single key, multiple hats" pattern this project has
found repeatedly this week (Gauntlet USDC Prime's 3-roles-same-Safe, the VaultV2Supervisor->Steakhouse-Safe
link).

## What this is and isn't

Disclosed only, same precedent as every other extension this week (`l1CappedComposite`,
controller-concentration, exit-capacity, Vault V2 inventory): no `adminKeyScore`/`multisigScore`/
`timelockScore` computed, no `AuthorityScore` field, no on-chain push. A vault's owner/curator/guardian
score says nothing about the token it holds -- this is a different, additive risk surface.

## Verification

`python3 scripts/check_issuer_power.py` -- read-only, Blockscout's verified-contract API (via `curl`,
not `urllib.request`) for ABI + controller getters, each chain's own RPC for `eth_getCode`/Safe
resolution. Exit 0, 4/4 assets read this run. `python3 chains/ethereum-l1/scripts/sweep_token_function_guards.py
--token 8453:0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 --token 1:0xdAC17F958D2ee523a2206206994597C13D831ec7
--token 1:0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --token 1:0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a`
for the guard-level pass (control check passed: USDC's own blacklist/pause guards read correctly
before trusting the rest). AgoraProxyAdmin's `owner()` chase done live with this project's own
`read_address_getter`/`safe_owners_and_threshold` helpers, no new code needed. 19 unit tests for the
pure classification logic
(`scripts/lib/tests/test_issuer_power.py`) + 3 for the new `read_address_array_getter()` helper
(`scripts/lib/tests/test_web3_utils.py`). Full suite (6 directories) green.
