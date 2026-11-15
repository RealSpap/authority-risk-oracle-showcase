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

## Update, 15 November 2026

Readings are dated; run the command to refresh them.

Thanks to @achemperety, who in [post 443](https://ethereum-magicians.org/t/erc-8004-trustless-agents/25098/443) of the ERC-8004 thread on 12 November pointed out that the address in my post of 6 November is the one listed for testnet in the team's file, and who in post 446 of the same thread on 13 November asked whether the `Upgraded` events of both proxies had been read on the seven networks: this entry exists because of those two posts, and the readings below answer the second.

This update adds three things to the entry: the upgrade history of the mainnet entry on the five networks that the section of 13 November does not cover, one table for all seven networks, and one replay command per network. Everything below was read by me on public nodes with no key, with `eth_chainId` read on each node before its answers were used.

### What the readings say

On Ethereum mainnet (chain ID 1) and on the six other networks of the table below, the mainnet entry `0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58` emitted two `Upgraded` events within twelve minutes of each other: first to `0xcb7af40c0be4fb92e183942b6dbb6b14a888f067` (2188 bytes on each of the seven networks, with none of the three validation selectors), then to `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`, which is the implementation today. The testnet entry `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` has code only on Ethereum mainnet (chain ID 1) and Base mainnet (chain ID 8453), and no code on Arbitrum One (chain ID 42161), Polygon PoS (chain ID 137), Linea (chain ID 59144), Monad mainnet (chain ID 143) and Celo (chain ID 42220).

On Ethereum mainnet (chain ID 1), the testnet entry was created at block 24204475 with `0xd53de688e0b0ad436fbdbda00036832ff6499234`, which holds none of the three selectors. On Ethereum mainnet (chain ID 1), at block 24204487 it moved to `0x106e3d8500b92a86d669702e75097e945c2e2b0e`, which holds all three, and at block 24339656 to `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`. So on Ethereum mainnet (chain ID 1) the address I named has pointed to code with the validation functions since block 24204487 (2026-01-10, 13:06:11 UTC). On Base mainnet (chain ID 8453) it has pointed to `0xd53de688e0b0ad436fbdbda00036832ff6499234` since its creation at block 41619242, and that code holds none of the three selectors.

### The seven networks

Implementations on Ethereum mainnet (chain ID 1), Base mainnet (chain ID 8453) and the five other networks of the table: A is `0xcb7af40c0be4fb92e183942b6dbb6b14a888f067`, B is `0xdb31f5d9167f8ebc8b30fbbf814c4d297c2d7f99`, C is `0xd53de688e0b0ad436fbdbda00036832ff6499234` and D is `0x106e3d8500b92a86d669702e75097e945c2e2b0e`. In each row, for the network of that row, for example Ethereum mainnet (chain ID 1), the testnet entry is `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` and the mainnet entry is `0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58`.

| Network (chainId) | Testnet entry: `Upgraded` events and implementation today | Mainnet entry: `Upgraded` events (block, UTC time, new implementation) | Mainnet entry today |
|---|---|---|---|
| Ethereum mainnet (1) | 24204475 (2026-01-10, 13:03:47 UTC) C; 24204487 (13:06:11 UTC) D; 24339656 (2026-01-29, 09:37:11 UTC) B; today B | 24339874 (2026-01-29, 10:20:59 UTC) A; 24339931 (10:32:23 UTC) B | B |
| Base mainnet (8453) | 41619242 (2026-02-02, 10:23:51 UTC) C; today C | 41663785 (2026-02-03, 11:08:37 UTC) A; 41663802 (11:09:11 UTC) B | B |
| Arbitrum One (42161) | no code | 428895484 (2026-02-05, 13:16:11 UTC) A; 428895794 (13:17:28 UTC) B | B |
| Polygon PoS (137) | no code | 82458489 (2026-02-02, 12:56:24 UTC) A; 82458535 (12:57:56 UTC) B | B |
| Linea (59144) | no code | 28662556 (2026-02-06, 07:27:00 UTC) A; 28662568 (07:27:30 UTC) B | B |
| Monad mainnet (143) | no code | 52952798 (2026-02-03, 11:36:05 UTC) A; 52952906 (11:36:48 UTC) B | B |
| Celo (42220) | no code | 58396736 (2026-02-05, 13:18:14 UTC) A; 58396801 (13:19:19 UTC) B | B |

Selectors: `validationRequest(address,uint256,string,bytes32)` is `0xaaf400c4`, `validationResponse(bytes32,uint8,string,bytes32,string)` is `0x3d659a96` and `getValidationStatus(bytes32)` is `0xff2febfc`, computed with `cast sig`. Searched in the deployed code on Ethereum mainnet (chain ID 1) and Base mainnet (chain ID 8453) at 15:55Z on 15 November: A and C hold none of the three, B and D hold all three. On Arbitrum One (chain ID 42161), Polygon PoS (chain ID 137), Linea (chain ID 59144), Monad mainnet (chain ID 143) and Celo (chain ID 42220), the same search was made at 18:56Z on 15 November on two nodes each: A is 2188 bytes and holds none of the three, B is 5876 bytes and holds all three.

### How each reading was made, and its limits

- Ethereum mainnet (chain ID 1), read between 15:24Z and 15:57Z on 15 November: the `Upgraded` events of both proxies from the first block with code to the head, in one request on one node, then by bisecting the implementation slot on the same node, then each block read alone on two nodes. The three methods give the same blocks.
- Base mainnet (chain ID 8453), read at the same time: by bisecting the implementation slot on one node, then each event read alone on four nodes. A change made and undone between two sampled blocks would not show in a bisection.
- Arbitrum One (chain ID 42161), read at 18:05Z on 15 November: every block from 0 to the head scanned for the events, in 53 requests of ten million blocks on one node, none refused. No second node serves event queries or old state, so the two blocks are confirmed by one node.
- Celo (chain ID 42220), Linea (chain ID 59144), Monad mainnet (chain ID 143) and Polygon PoS (chain ID 137), read between 18:00Z and 18:05Z on 15 November: by bisecting the implementation slot on one node, then each event read alone on two nodes (three on Monad mainnet, one on Polygon PoS, where the other node refuses event queries). The implementation today was read on two nodes on each of the five networks.
- The team's file `scripts/addresses.ts` is the only place I found that lists both addresses; its last commit is dated 6 March 2026, and the README of the repository lists the identity and reputation registries only (read at 15:13Z on 15 November). I do not know who decides when an address enters the file.
- The team's intention for either address is not recorded on a chain, and I make no statement about it.

### Replay

Each command is one line. Replace `RPC_URL` with a public node of the network named before it; it must serve event queries over the range given. Run `cast chain-id --rpc-url RPC_URL` first to see the chain ID it answers with.

- Ethereum mainnet (chain ID 1), the testnet entry, first two events: `cast logs --rpc-url RPC_URL --from-block 24204475 --to-block 24204487 --address 0x8004Cb1BF31DAf7788923b405b754f57acEB4272 "Upgraded(address)"`
- Ethereum mainnet (chain ID 1), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 24339874 --to-block 24339931 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`
- Base mainnet (chain ID 8453), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 41663785 --to-block 41663802 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`
- Arbitrum One (chain ID 42161), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 428895484 --to-block 428895794 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`
- Polygon PoS (chain ID 137), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 82458489 --to-block 82458535 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`
- Linea (chain ID 59144), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 28662556 --to-block 28662568 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`
- Monad mainnet (chain ID 143), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 52952798 --to-block 52952906 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`
- Celo (chain ID 42220), the mainnet entry: `cast logs --rpc-url RPC_URL --from-block 58396736 --to-block 58396801 --address 0x8004Cc8439f36fd5F9F049D9fF86523Df6dAAB58 "Upgraded(address)"`

Each command prints the events of its range; the second topic of each event ends in the implementation address. The values above were read on 15 November; a later upgrade would change them.
