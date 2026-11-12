# E-2026-11-12: the ValidationRegistry address in my post of 6 November is the team's testnet entry

Date of this entry: 2026-11-12. Status: corrected by this entry. Nothing was deleted: the post it concerns stays as written, and this entry is the correction.

## What I said

In post [#437 of the ERC-8004 thread on Ethereum Magicians](https://ethereum-magicians.org/t/25098/437), on 2026-11-06, I wrote that the third proxy is the ValidationRegistry at `0x8004Cb1BF31DAf7788923b405b754f57acEB4272`, that it exists "on Ethereum and Base only", and that on Base it "still points at the one it was created with", which has none of the three validation functions.

## What is true

- The address I named is not the registry's mainnet entry. In the team's own address file (`scripts/addresses.ts` of the `erc-8004/erc-8004-contracts` repository, read on 2026-11-12), `0x8004Cb1B...4272` is listed under `TESTNET_ADDRESSES`, and the mainnet entry for the validation registry, under `MAINNET_ADDRESSES`, is `0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58` (for Ethereum mainnet, Base mainnet and the other mainnets that file lists). I named the wrong one as "the" ValidationRegistry.
- Both addresses were read again on 2026-11-12 at about 20:10 UTC, on two public nodes per network, with `eth_chainId` read on each node. Result, per network:

| Network (chainId) | Testnet entry `0x8004Cb1B...4272` (the address I named) | Mainnet entry `0x8004Cc84...AB58` |
|---|---|---|
| Ethereum mainnet (1) | proxy code (130 bytes), implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Base mainnet (8453) | proxy code, implementation `0xd53de688e0b0ad436fbdbda00036832ff6499234` | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Arbitrum One (42161) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Polygon PoS (137) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Linea (59144) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Celo (42220) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Monad mainnet (143) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |

- On every network where an address has code (Ethereum mainnet and Base mainnet for both, and for the mainnet entry also Arbitrum One, Polygon PoS, Linea, Celo and Monad mainnet), `owner()` returns the same account, `0x547289319c3e6aedb179c0b8e8af0b5acd062603`. This is the account the same file declares as `EXPECTED_OWNER`. I did not check in this entry whether that account has code.
- What stays true from my post: the address I named has code on Ethereum mainnet and Base mainnet only, among the seven networks read, with the same owner on both. The team's file lists 23 mainnets and I read only seven of them, so "only" in my post is not established beyond those seven; on Ethereum mainnet it points to the same implementation as the mainnet entry; on Base mainnet it points to a different one.

## Cause

By my own notes: I took the address from a deployment guide that, as I read it, gave one address for all chains, and I did not check it against the per-network address file of the same repository. The error is mine. When I read the address again on 2026-11-11 I read the same address with the same method, which was not an independent check. On 2026-11-07, after my post, I read a later post of the same thread that lists both addresses, and I did not act on it until now.

## Replay

On Base mainnet (chainId 8453), with `<Base mainnet RPC>` any public node for that network; the implementation slot is the standard EIP-1967 one:

```bash
cast chain-id --rpc-url <Base mainnet RPC, expect 8453>
cast storage 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --rpc-url <Base mainnet RPC, chainId 8453>
cast storage 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --rpc-url <Base mainnet RPC, chainId 8453>
```

The first storage read returns a value ending in `db31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`, the second one a value ending in `d53de688e0b0ad436fbdbda00036832ff6499234`. To see the absence of code on another network, replace the RPC and run `cast codesize 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 --rpc-url <Arbitrum One RPC, chainId 42161>`: it returns 0 there and 130 on Ethereum mainnet and Base mainnet. The values above were read on 2026-11-12; a later upgrade would change them.

## Not established

- The upgrade history of either proxy: I did not read any `Upgraded` event, so "the one it was created with" in my post is not established.
- The team's intention for either address.
- Whether the implementation on Base mainnet for `0x8004Cb1B...4272` lacks the three validation functions: I did not re-derive that check for this entry.
