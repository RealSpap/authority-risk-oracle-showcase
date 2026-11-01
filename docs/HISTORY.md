# History of this repository, and what does not depend on it

Written on 30 October 2026.

## What happened

The history of this repository was rewritten on 30 September 2026, and every commit up to 6 October 2026 is a snapshot or carries a round time, so the dates of these commits prove nothing. The first public commit is a snapshot dated 21 September 2026; it summarises work done from 15 September 2026 and holds it in one commit. The 11 commits after it, up to 5 October 2026, are snapshots that each hold the changes of one day (a day without changes has none); their commit time is 23:00:00 +0200, not the time the work was done, and the commit of 6 October is also on a round time (08:00:00 +0200). `git log --reverse --format='%h %ad %s' --date=iso` lists them. Commits carry the time recorded when they were made from 7 October 2026. A clone made before the rewrite does not share its history with this repository: clone it again.

The rewrite concerns the git history only. The oracle contracts and the data they hold live on the chains, not in git; the rewrite could not change them. This page does not describe the content of the commits that were replaced.

## What can still be checked

1. **Dated transactions on the chains, which do not depend on git.** The table below gives, for each of the nine oracles, what a public node still served on 30 October 2026: the deployment block (six of the eight EVM oracles), the block and time of the first score written (all eight; the methodology hash of that first score for seven of them) and, for Solana, the oldest signature the public node serves. Anyone can read the same blocks and transactions on an explorer or with a node that keeps that history.
2. **The event log of the Watch is hash-chained since 10 October 2026**: each line commits to the previous one (`chain.json` and `events.jsonl` on the `watch-data` branch, checked by `scripts/verify_chain.py`).
3. **The Watch manifests are signed since 11 October 2026** (Ed25519, `signature.json` on the `watch-data` branch, `scripts/audit_public.py`); the pinned key is written in `watch/API.md`.
4. **The methodology hash is tied to the code for every push after 30 September 2026**: it is the hash of a label and of a digest of the scoring and push code (`scripts/lib/methodology.py`). Before that date it is the hash of a hand-typed label (`api/score_history.json` says so), which is the case of every first hash in the table below.

## Dated witnesses read on the chains

| Oracle | Address | Deployment block, time (UTC) | First score written: block, time (UTC), methodologyHash | How it was read |
|---|---|---|---|---|
| Robinhood Chain testnet | `0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52` | not read (the public node keeps no state that old) | 120201857, 2026-09-16T02:01:03Z, `0xc68de93c6cdfb927296ad0e266a649c6410dcbf9916fc6b0f36a72cff37bcd86` | first score: first log the public node returned, scanning getLogs from block 0 or from the deploy block, tx `0x458f30e0bc52b31d8026dc707983d51784bf17c187e38e8d4a58f0affdba71e8` |
| Ethereum Sepolia | `0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906` | 11732364, 2026-09-18T18:13:00Z | 11732374, 2026-09-18T18:15:00Z, methodologyHash not read | deploy: block header of the block that holds the deploy tx 0x931302ef25... (the tx hash is named in the project's deploy record; its block number and the header were read from the node; the receipt was not served); first score: first updateScores transaction named in the project's deploy record, its block and header read from the node; the log was not served, so the methodologyHash is not read, tx `0xfbb1caf4ef05f303b7b231495baa58c5638de831f0f5cfe64e789bd249522e51` |
| Arbitrum Sepolia | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | not read (the public node keeps no state that old) | 310268519, 2026-09-18T18:16:55Z, `0x6acfe9c5f210a6d1e4cd50a30ea19b8436bcee1b948e633d2de153bd4dd78915` | first score: first log the public node returned, scanning getLogs from block 0 or from the deploy block, tx `0x1c6f9bb9644eaaed87d21ee5fe9d594d9b04bc35b6e374541ba4caf089a85649` |
| Base Sepolia | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | 46993519, 2026-09-18T18:15:26Z | 46993594, 2026-09-18T18:17:56Z, `0x758072e35c77f0ad21afcf9baa2a5508bfbdbd2d0391c5704b6302cb74e7cb34` | deploy: eth_getCode searched block by block; first score: first log the public node returned, scanning getLogs from block 0 or from the deploy block, tx `0xd7483e0a50f292e8da859dbc37895f3fd7f7f1bba2c413bb137f5c483ca897f0` |
| Tempo Moderato | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | 35905341, 2026-09-18T23:45:39Z | 35906259, 2026-09-18T23:54:47Z, `0xe653d28506a2817ef2eca397d999966bd56a35d9024e25cdfccbb618d1a3909a` | deploy: eth_getCode searched block by block; first score: first log the public node returned, scanning getLogs from block 0 or from the deploy block, tx `0x286ef2c4b03cde0174c4afa00dda96f5d34b4ed1260cc89db94ab35da736c49d` |
| Plasma testnet | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | 33941499, 2026-09-18T22:22:31Z | 33941556, 2026-09-18T22:23:28Z, `0x929c84827d35d9d79906aeab3d4731d1129a3df97d4a6cfc7df1748b62a722cd` | deploy: eth_getCode searched block by block; first score: first log the public node returned, scanning getLogs from block 0 or from the deploy block, tx `0xcb5c8a3ae7e27eddf0376328a7a27cb9aa28bc2971c878f965a3e1edfb300b99` |
| Monad testnet | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | 63764900, 2026-09-19T02:36:20Z | 63775006, 2026-09-19T03:27:12Z, `0x8e05d88ce076e117dd169362399b9f417b8e7f33cc6c73d844139b9b1a7604c7` | deploy: receipt of the deploy tx 0x1019fb1be3...; first score: first updateScores transaction named in the project's deploy record; its ScoreUpdated log read, tx `0xbd9913e225c3a1a1738bc3d5fd5292a7105841d0b091a39c53f029b1e809846b` |
| HyperEVM testnet | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` | 64778486, 2026-09-20T13:21:06Z | 64778632, 2026-09-20T13:23:30Z, `0xfbf38ff91abf710728e2df3d5370bf18eeb2a9085168612fa03955b13cc958ad` | deploy: receipt of the deploy tx 0x3d49452aa7...; first score: first updateScores transaction named in the project's deploy record; its ScoreUpdated log read, tx `0x9c8a758f3fbf20f3484485b531c736684da8dec81bc4f02c009ee1dc4def0a9d` |

Solana devnet program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`: earliest signature the public devnet RPC still serves for it: slot 501396104, 2026-09-20T13:11:19Z, `YkP6oYbt8tXk3aaD4nCxB1K14HrEAda269nwfmu9ahGDdcJDYqsvXijNt3kr28zdXBqEvDwBxKYA4TuJXfcL8Ej` (the project's deploy record names this same signature as the deploy transaction).

| Zcash testnet commitment | Block height | Block time (UTC) | Transaction | Block hash |
|---|---|---|---|---|
| ARO1 | 4366645 | 2026-09-19T03:34:34Z | `f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5` | `000018eb54ab9f49172b5a55c585d2817948d3c496e52051dc4406061185894e` |
| ARO2 first anchor | 4368539 | 2026-09-19T21:17:12Z | `18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37` | `00000210bf1892ea9c7dc2635482e713cb76d5ef3aa5f17c706ebec21f318e40` |
| ARO2 re-anchor | 4368633 | 2026-09-19T23:15:28Z | `eeaa894c3c46814f7228a7ecf2be84c0006c1154b5101688dd413d9a419689c0` | `00000d6960abf93df5238e78314466e677841bcf926d015fdb7e6271c7fd7140` |
| ARO2 six live | 4371248 | 2026-09-20T19:23:45Z | `462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c` | `0008f26aee7dfade565abe2fcfd9adcc4a31e723068cdcaaea330c4fa2d319c3` |


How to re-read a row: take the transaction or block named in it and look it up on an explorer of that chain, or ask a node for the block (`eth_getBlockByNumber`) or the receipt (`eth_getTransactionReceipt`). A cell that says "not read" is a value that the public node used for the reading no longer serves, or that its log scan did not reach; it is not a claim that nothing exists. For Robinhood Chain and Arbitrum the first score is the first log that the public node returned. For Ethereum Sepolia, Monad and HyperEVM the first score is the first `updateScores` transaction named in the project's deploy record, with its block (and, where the node served it, its log) read; an earlier push between deployment and that block is not excluded by this reading. The Solana row is the oldest signature that the public devnet node still serves for the program, which is the signature the deploy record names as the deploy transaction. The Zcash rows are transactions that carry the commitments of the scores, read from a public explorer of that network (height, block hash and time; the content of the commitments was not re-read on 30 October).

## What this page does not prove

A dated transaction shows that something was written to a chain at that time; it does not show what the repository contained then. This page gives no reason for the rewrite.
