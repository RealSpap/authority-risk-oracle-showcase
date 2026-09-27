# Five more custody protocols traced: edgeX, SoDEX, Aera V3, Valos, Derive (investigation, nothing scored)

2026-09-27. Second batch from the TVL-coverage list (`finding_2026-09-26-tvl-coverage-by-ecosystem.md`), picked because a grep of the repository found no prior work on any of them (after the duplicates of 26/09).
Method: for each, a reviewer tracer that greps the repository first, then an independent reviewer verifier told to distrust the trace and re-derive from scratch; read-only, no key, nothing sent. **No target added, no score changed.**
Verdicts: edgeX CONFIRMED, Valos CONFIRMED, SoDEX PARTIAL, Derive PARTIAL, **Aera REFUTED** (the tracer's weakest-path conclusion was wrong: two vault values were off by 1000x, USDC having 6 decimals).
Every figure marked "re-read" was read again by me on two public RPCs (identical answers, except Monad where only `rpc.monad.xyz` answers a plain `eth_call`); the rest is the verifier's own read and is labeled as such.

## edgeX Bridge (Arbitrum One): $48.8M behind a 2-of-3 Safe, no delay

Re-read: the vault `0xc64e528c...` holds **48,806,660.99 USDC**; it is a Circle smart account whose native owner is burned (`getNativeOwner()` = `0x...dEaD`), so no key can reconfigure it. The only spender is the `EdgexBridge` proxy `0x61A7EBc6...` (max allowance), whose `owner()` is
Safe `0xeb155e91...`: **2-of-3, no module**, three EOAs (Safe-signer nonces 1, 0, 0), not paused. Verifier: the owner can upgrade the proxy or call `emergencyWithdraw` with no delay (a 3 USDC test withdrawal was done on-chain), and because the USDC rate limit was never configured, the two withdrawal signers plus the releaser
(three more EOAs) can drain the vault through `withdraw` then `finalize` after only 300 seconds; only the Safe's `cancelBatch` or `pause` inside that window stops it. The allowance can never be revoked (the vault has no owner), so the whole trust is the bridge code and its Safe. Not read: the Ethereum, Arc and BSC deployments (DefiLlama lists Ethereum too, $12.7M).

## SoDEX Bridge (Base): about $68M behind one bare key

Re-read: proxy `0xCC7322A2...185B` (UUPS, no EIP-1967 admin), `owner()` = **`0xe464B756...127c`, a plain EOA (65 transactions)**, not paused. Verifier: that EOA also holds `DEFAULT_ADMIN_ROLE`; upgrade is `onlyOwner`; there is no Safe and no timelock; **13 `WITHDRAWER_ROLE` and 23 `CALLER_ROLE` holders, all plain EOAs**;
the withdraw rate limit is configured off (cap and window 0 for all five bridge tokens, which the library reads as unlimited), so any single withdrawer key can take up to `bridgedAmounts` (117.6M sMAG7.ssi, 2.0M MAG7.ssi, 0.4M USSI, 0.69M DEFI.ssi, 0.28M MEME.ssi, about $68.4M at DefiLlama coin prices, a document, not an oracle).
The tracer's role counts (18 and 19) and its "rate limit unread" were wrong. Not read: the token contracts' own mint and upgrade authority, and what a `CALLER_ROLE` key can do through the account factory.

## Aera V3 (Base): $80.7M in 21 vaults, two matter, no single key, but a 3-of-9 that also sets the price

Verifier (the tracer was refuted): summing all 21 factory vaults live gives $80.7M, matching DefiLlama; only **Gauntlet USD Alpha ($45.6M)** and **exaUSD ($35.0M)** hold material value. Owner-level control goes through timelocks (1 day and 6 hours); no single EOA can drain a vault.
Six Safes are 3-of-9 (five share the same nine signers) or 3-of-7 (all seven inside the nine), no module, no guard. For Gauntlet USD Alpha the ops Safe holds the exchange-rate path with **no delay**: an out-of-band `setUnitPrice` writes the price and pauses the vault, and the same Safe can unpause at that price.
Re-read by me: the vault `0x00000000...6640D5` is not paused and its `owner()` is a timelock with `getMinDelay()` = 86,400 s; the Safe and role maps are the verifier's. Not read: what the guardian hot keys can do with the Merkle roots, and how much a manipulated rate could extract given the provisioner's limits.

## Valos (Monad): a $105.5M receivable, and one EOA is both manager and borrower

Re-read: strategy proxy `0x8dCE15fc...` returns the same EOA `0xB83986E9...` (plain, 208 transactions) for `investmentManager()` and `borrower()`; the vault's `convertToAssets(totalSupply)` is **105.53M AUSD** while the vault itself holds only 7,693 idle AUSD. Verifier: the value is
about 100.66M of net principal lent out, 105.5M with interest; that EOA can `borrow()` all new deposits (no reserve threshold), and `upgradeToAndCall` on the strategy is `onlyManagerOrSecurityAdmin`; the registry and fee manager belong to a 2-of-3 Safe (nonce 97, one module) whose module lets a keeper EOA pause all 12 strategies. The EOA now holds 12.7K AUSD:
where the borrowed funds went is not traced. This is an RWA-style lending vault: most of the value is a claim on a borrower off-chain, so the on-chain authority is over the terms, not over the assets.

**Partly closed 2026-09-27** (the asset itself, "AUSD issuer controls" from the "not read" list): the vault's `asset()` is `0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a` (AUSD), a proxy whose EIP-1967 implementation `0xc1e3C7D4...` was read live (both RPCs identical), reusing this project's own bytecode-selector method
(`chains/monad/scripts/sweep_lending_asset_authority_monad.py::scan_selectors`, built for Monad because it has no live Blockscout instance to read verified source from). The implementation's runtime bytecode contains `mint(address,uint256)` and `burn(address,uint256)` selectors, but none of the freeze/seize/pause/upgrade family that
script already checks for, and none of `owner`, `blacklister`, `pauser`, `masterMinter`, `admin`, nor eight other plausible getter names (`minter`, `controller`, `issuer`, `authority`, `governor`, `operator`, `minterAdmin`, `custodian`, ...) answered with a live address. **Not established**: who can call `mint`/`burn`, since a selector present in the bytecode says
the function exists, not who is allowed to call it (the same limit the reused script's own docstring already states), and no getter this pass tried exposes that address. This needs verified source (unavailable for Monad here) or a live simulated call from a candidate address to go further.

## Derive (Base): $52.8M behind one 3-of-5 Safe, no timelock

Re-read: Safe `0x169a99B9...` is **3-of-5, no module**; the USDC vault's `owner()` is that Safe; the USDC vault holds 7.93M USDC and the WETH vault 8,757.31 WETH. Verifier: the same Safe owns all 16 Base vaults (about $52.8M) and all 27 Ethereum vaults (not valued); on the 3 old vaults (WETH, wstETH, USDC, $41.1M) `rescueFunds` is
`onlyOwner`; on the 13 newer ones it needs `RESCUE_ROLE`, revoked on 2026-04-21 from the two former holders, but the Safe can grant it to itself and call `rescueFunds` in the same Safe transaction, so the delay is still zero. The trace's Safe nonce and vault count were wrong (the Safe's own `nonce()` is 23 on Base and 79 on Ethereum per the verifier; the account transaction count of a Safe is not that number). Not read: Derive's other deployments (DefiLlama lists Hyperliquid L1 at about $52.6M, Optimism $31.9M, Ethereum $31.5M, Arbitrum $19.8M; the Ethereum vaults' balances were not read either), so the $52.8M is Base only, and the Hyperliquid L1 figure of the same size in the coverage note is a different deployment.

## What this adds to the picture

Of the eleven custody contracts traced on 26 and 27/09 (six on 26/09, these five), plus wBETH's token proxy: the weakest authority is a **single bare key** at SoDEX ($68M), at Valos (a $105M receivable whose manager and borrower are one EOA) and at wBETH's proxy admin. Next come Safes with no delay: 5-of-9 at the Polygon bridge, 3-of-5 at USDT0 and Derive, 2-of-3 at edgeX, and Aera's 3-of-9 that sets the exchange rate with no delay (its owner-level paths are timelocked), all in the range the Safe-rooted convention scores low.
Base's 2-of-2 of nested Safes needs the most signers but has no timelock either; ether.fi's 10-day upgrade timelock is the longest delay of the set, next to a no-delay 4-of-7 that can pause indefinitely. Spark's 1-of-2 allocator Safe is left out of this ranking because the proxy it controls holds nothing today. Nothing here has been scored, and adding any of them as a target is Spap's decision.

## Process note

Three of five traces (reviewer, high effort) had errors that changed the conclusion or key figures (Aera's decimals and weakest path, SoDEX's role counts and rate limit, Derive's value and rescue gating); the reviewer verifiers caught all of them. Same lesson as 26/09: a trace without an independent verifier is not usable.
