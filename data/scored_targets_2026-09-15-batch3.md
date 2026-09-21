# Scored targets - batch 3, 2026-09-15

Ten more scores pushed in one `updateScores()` call (tx
[`0xb0908404...`](https://explorer.testnet.chain.robinhood.com/tx/0xb0908404de2984f1eb60e92d9e062dc634bc24a55613ef7ea4199736b67f5ed0)),
expanding coverage from 7 to **17 targets**. This batch found the single worst score
on the whole chain so far -- and it belongs to the chain's own flagship product.

## Robinhood's own tokenized stock/ETF line - 1/100 (TSLA, AMZN, PLTR, NFLX, AMD scored; ~230 tokens share this authority)

Robinhood Chain's defining feature is tokenizing real-world equities and ETFs --
`docs.robinhood.com/chain/contracts` lists roughly 230 live stock/ETF token contracts
(TSLA, AMZN, PLTR, NFLX, AMD, AAPL, NVDA, plus tokenized SPY/QQQ/SGOV/SLV and others).
Every one of them, confirmed by pulling and comparing raw bytecode on five samples
(TSLA `0x322F09...`, AMZN `0x12f190...`, PLTR `0x894E1E...`, NFLX `0xE0444E...`, AMD
`0x86923f...`), is a byte-identical 283-byte beacon proxy pointing at one shared
beacon: `0xe10b6f6b275de231345c20d14ab812db62151b00`.

**The beacon is OpenZeppelin AccessControl, not Ownable.** `DEFAULT_ADMIN_ROLE`'s full
grant/revoke history was walked from genesis via event logs: granted to the deployer
EOA at block 7662, reassigned to `0xd6f8378f8e440c65f8382f5f2728c78dfd55b66d` at block
7802, deployer's own admin role revoked at block 8695 -- leaving exactly one current
holder, confirmed via `hasRole()` (independently re-verified: `true`) and confirmed a
bare EOA (`eth_getCode` empty, codesize 0).

That one key can, with zero delay and no second signer anywhere in the chain:
- `upgradeTo(address)` -- rewrite the shared implementation for all ~230 tokens at once.
- `pause()`/`unpause()`.
- `blockAccounts(address[])`/`unblockAccounts(address[])` -- freeze any holder's
  balance, confirmed as real selectors present in the deployed bytecode, not inferred
  from a name.

**This scores worse than every other target found on this chain**, including the
already-known Uniswap vanity-EOA finding (2/100), despite a blast radius (the chain's
entire tokenized-equity product line, not just a fee-tier setting) far larger than
anything else scored. Pushed identically on the 5 sampled tokens; the remaining ~225
share the same beacon and would score identically if scored individually.

## UniswapX V3DutchOrderReactor (`0x000000007A1C8e570011EeDF86A2A35593013cBA`) - 2/100

`owner()` resolves to `0x2BAD8182C09F50c8318d769245beA52C32Be46CD` -- the **exact
same** bare, vanity-ground EOA already found controlling the Uniswap v3 Factory and
v4 PoolManager (see batch 2). This extends that one key's control to a third protocol
surface: order settlement, not just AMM fee switches. `feeController()` currently
reads `address(0)` (inactive), and `setProtocolFeeController` has no delay.

## Morpho vaults - four more, and the chain-wide gap holds on every one

All four share the same finding already established on the Steakhouse vault: real
`timelock(bytes4)` checks on `setOwner`/`setCurator`/`setIsSentinel` return **0** on
every vault below, regardless of how strong the curator/owner Safes are. It's an
architectural pattern in how Morpho Vault V2 is deployed on this chain, not a
per-vault misconfiguration.

| Vault | Address | Curator / Owner | TVL | Score |
|---|---|---|---|---|
| NetNet Credit | `0x99347d5F70...953B57` | Curator = Owner = the **same** 1-of-1 Safe, sole signer is a bare EOA -- functionally one private key wearing a Safe wrapper | ~$1.82M | **8/100** |
| Purinta USDG | `0x37788ff0c1...121d0A8` | Curator: real 3-of-5 Safe. Owner: a *different* real 3-of-5 Safe, 3-of-5 members overlapping | ~$50.4K | **38/100** |
| Ethena x Steakhouse USDG | `0xbEeFF0fb1D...16160737` | Curator: same 3-of-7 Safe as the already-scored Steakhouse vault. Owner: 2 hops through a non-Safe contract to a real **5-of-10 Safe** -- the largest raw multisig found on this chain | **~$23.56M (largest single TVL found on this chain)** | **44/100** |
| Spark Savings USDG (spUSDG) | `0xde770c84FE...18c4087` | AccessControl (not the assumed Sky `wards` pattern -- checked and ruled out via bytecode selector absence). Admin role held by an 8,113-byte contract with `queue`/`execute` selectors (BridgeExecutor-shaped), but its own controlling party was **not identified this pass**, and no delay getter (`getMinDelay`, `MINIMUM_DELAY`, `getDelay`) resolved -- flagged lower-confidence | ~$37.4M | **22/100** (see caveat) |

**Purinta and Ethena x Steakhouse are the two best-governed targets found on this
chain to date** -- real, distinct multisigs at both curator and owner, no bare-EOA
exposure at any traced hop. Both still cap in the 38-44 range because the
`setOwner`/`setCurator` zero-delay gap is systemic across every Morpho vault checked,
not something either vault's own governance choices could fix.

**Spark Savings caveat, stated plainly**: this is the one score in this batch pushed
with acknowledged incomplete tracing. The admin-role holder is a real, non-Safe,
non-EOA contract whose own authority was not resolved -- a real second pass (one more
hop: who controls `0x826aeaeee9233fa8ba199518dd8621a5962b1d02`) is needed before this
should be treated as final-confidence, the same honesty standard this project applies
to every open gap it carries forward rather than forces closed.

## Running total

17 targets now scored across 3 batches. Range: 1/100 (Robinhood's own stock-token
beacon) to 54/100 (Lighter). The chain's own flagship, on-theme product scoring the
single worst result found anywhere on it is the headline finding of this pass.
