# E-2026-11-12: the ValidationRegistry address in my post of 6 November is the team's testnet entry

Date of this entry: 2026-11-12. Revised: 2026-11-15, when the readings below were done again and the upgrade history was added; the list of what changed is at the end. Status: corrected by this entry. Nothing was deleted: the post it concerns stays as written, and this entry is the correction.

## What I said

In post [#437 of the ERC-8004 thread on Ethereum Magicians](https://ethereum-magicians.org/t/25098/437), on 2026-11-06, I wrote that the third proxy is the ValidationRegistry at `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` (on Ethereum mainnet, chain ID 1, and Base mainnet, chain ID 8453), that it exists "on Ethereum and Base only", and that on Base it "still points at the one it was created with", which has none of the three validation functions.

## What is true

- The address I named is not the registry's mainnet entry. In the team's own address file (`scripts/addresses.ts` of the `erc-8004/erc-8004-contracts` repository, read at 20:10Z, on 15 November), `0x8004Cb1B...4272` is listed under `TESTNET_ADDRESSES` (for Sepolia, chain ID 11155111, and the other testnet chain IDs that file lists), and the mainnet entry for the validation registry, under `MAINNET_ADDRESSES`, is `0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58` (for Ethereum mainnet, chain ID 1, Base mainnet, chain ID 8453, and the other mainnet chain IDs that file lists). I named the wrong one as "the" ValidationRegistry.
- The two entries below are `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` (testnet) and `0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58` (mainnet), read on Ethereum mainnet (chain ID 1), Base mainnet (chain ID 8453) and the five other networks of the table, each with its chain ID in its row. Both addresses were read at 20:08Z, on 15 November, on one public node per network, with `eth_chainId` read on each node, and the implementation slot (the standard EIP-1967 one) was read on a second node on every network where an address has code; on Polygon PoS (137) I read it again at 20:08Z, on 15 November, on three other public nodes, which return the same implementation as the first node. Result, per network:

| Network (chainId) | Testnet entry (the address I named) | Mainnet entry |
|---|---|---|
| Ethereum mainnet (1) | proxy code (130 bytes), implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Base mainnet (8453) | proxy code, implementation `0xd53de688e0b0ad436fbdbda00036832ff6499234` | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Arbitrum One (42161) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Polygon PoS (137) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Linea (59144) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Celo (42220) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |
| Monad mainnet (143) | no code | proxy code, implementation `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` |

- On every network where an address has code (Ethereum mainnet and Base mainnet for both, and for the mainnet entry also Arbitrum One, Polygon PoS, Linea, Celo and Monad mainnet), `owner()` returns the same account, `0x547289319c3e6aedb179c0b8e8af0b5acd062603`. This is the account the same file declares as `EXPECTED_OWNER`. Read at 20:08Z, on 15 November, this account has no code on any of the seven networks above: it is a plain account on each of them.
- What stays true from my post: among the seven networks read, the address I named has code on two of them, Ethereum mainnet (chain ID 1) and Base mainnet (chain ID 8453), with the same owner on both. The team's file lists 23 mainnet chain IDs and I read seven of them: I withdraw the word "only" of my post, which goes beyond what I read. On Ethereum mainnet (1) the address I named points to the same implementation as the mainnet entry; on Base mainnet (8453) it points to a different one.

## Upgrade history, read on 15 November

Method: the implementation slot of each proxy was read at sampled blocks (a bisection from block 1 to the head) on two sets of public nodes with no node in common, and each change found was confirmed by the `Upgraded(address)` event of that same block, read with a one-block `eth_getLogs`. On Ethereum mainnet (1) every `Upgraded` event of both proxies from block 24000000 to the head was also read directly with `eth_getLogs` on one public node, and gave the same blocks. Head blocks: Ethereum mainnet 26422690 (read at 20:06Z), Base mainnet 57914730 (read at 20:08Z), both on 15 November.

- Ethereum mainnet (1), testnet entry `0x8004Cb1B...4272`: 3 `Upgraded` events. Block 24204475 (2026-01-10): implementation `0xd53de688e0b0ad436fbdbda00036832ff6499234`. Block 24204487 (2026-01-10): `0x106e3d8500b92a86d669702e75097e945c2e2b0e`. Block 24339656 (2026-01-29): `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`, the implementation today.
- Ethereum mainnet (1), mainnet entry `0x8004Cc84...AB58`: 2 `Upgraded` events. Block 24339874 (2026-01-29): `0xcb7af40c0be4fb92e183942b6dbb6b14a888f067`. Block 24339931 (2026-01-29): `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`, the implementation today.
- Base mainnet (8453), testnet entry `0x8004Cb1B...4272`: one change of the stored implementation, at block 41619242 (2026-02-02), when the proxy was created with `0xd53de688e0b0ad436fbdbda00036832ff6499234`. The slot holds the same value at every block the bisection sampled up to the head, and it is that value today. So "still points at the one it was created with" is true of that address on Base mainnet at the sampled blocks. The read on Base is by bisection and not by scanning every event, because the free public nodes accept event queries over 1,000 blocks at most (50 on some), and a change undone between two sampled blocks would not show in it.
- Base mainnet (8453), mainnet entry `0x8004Cc84...AB58`: two changes. Block 41663785 (2026-02-03) on Base mainnet (chain ID 8453): `0xcb7af40c0be4fb92e183942b6dbb6b14a888f067`. Block 41663802 (2026-02-03) on Base mainnet (chain ID 8453): `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`, the implementation today. Each of these blocks holds the matching `Upgraded` event.

## The three validation functions

The three functions of the ERC-8004 validation interface, with their selectors computed by `cast sig`: `validationRequest(address,uint256,string,bytes32)` is `0xaaf400c4`, `validationResponse(bytes32,uint8,string,bytes32,string)` is `0x3d659a96`, `getValidationStatus(bytes32)` is `0xff2febfc`. Read at 20:10Z, on 15 November, with the selectors searched in the deployed bytecode of each implementation:

- `0xd53de688e0b0ad436fbdbda00036832ff6499234` is 2188 bytes on Ethereum mainnet (1) and on Base mainnet (8453), and holds none of the three selectors. This is the implementation the address I named points to on Base mainnet.
- `0xcb7af40c0be4fb92e183942b6dbb6b14a888f067` is 2188 bytes on Ethereum mainnet (1) and on Base mainnet (8453), and holds none of the three selectors.
- `0x106e3d8500b92a86d669702e75097e945c2e2b0e` (6044 bytes, Ethereum mainnet (1)) and `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99` (5876 bytes, on Ethereum mainnet (1) and on Base mainnet (8453)) hold all three. The code of `0x106e3d8500b92a86d669702e75097e945c2e2b0e` on Base mainnet (8453) is empty.

So my statement that the implementation behind the address I named on Base has none of the three validation functions is true; the error is that this address is the team's testnet entry.

## Cause

I took the address from a deployment guide that gave one address for all chains. The per-network address file of the same repository lists both addresses, and the check belonged there. When I read the address again on 2026-11-11 I used the same method as for the post, which cannot catch this error. On 2026-11-07 I saw a later post of the same thread that lists both addresses; this entry is the first action on it. The error is mine.

## Replay

Each command is one line. Replace `RPC_URL` with any public node of the network named in front of it, and run the first line to see the chain ID it answers with.

On Base mainnet (chainId 8453); the implementation slot is the standard EIP-1967 one:

- `cast chain-id --rpc-url RPC_URL` prints 8453.
- On Base mainnet (chain ID 8453), the mainnet entry: `cast storage 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --rpc-url RPC_URL` returns a value ending in `db31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`.
- On Base mainnet (chain ID 8453), the testnet entry: `cast storage 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --rpc-url RPC_URL` returns a value ending in `d53de688e0b0ad436fbdbda00036832ff6499234`.
- On Base mainnet (chain ID 8453), the testnet entry at its creation: `cast storage 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --block 41619241 --rpc-url RPC_URL` returns zero, and the same command with `--block 41619242` returns the value ending in `d53de688e0b0ad436fbdbda00036832ff6499234` (a node that serves old state is needed).

On Arbitrum One (chainId 42161): `cast codesize 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 --rpc-url RPC_URL` returns 0 there, and 130 on Ethereum mainnet (1) and on Base mainnet (8453).

On Ethereum mainnet (chainId 1): `cast logs --from-block 24339656 --to-block 24339656 --address 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 'Upgraded(address indexed)' --rpc-url RPC_URL` returns one event whose second topic ends in `db31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`.

The values above were read on 15 November; a later upgrade would change them.

## What this entry does not claim

- The team's intention for either address: an intention is not recorded on a chain, so no read can show it, and I make no statement about it.
- Networks beyond the seven read above, for the existence of code at either address.

## What changed on 2026-11-15

The version of 2026-11-12 listed the upgrade history, the functions of the Base implementation and the account type of the owner as points that were open. This version states what was read: the upgrade history on both networks, the selectors in each implementation, the owner account having no code, and the team's file read again. The word "only" of my post is withdrawn. The commands of the Replay section no longer contain angle brackets, so they can be copied.
