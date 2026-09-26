# Six large Ethereum L1 custody contracts: who can move them (investigation, nothing scored)

2026-09-26. The L1 TVL-coverage run listed the biggest untracked Ethereum protocols. Six were traced read-only by a workflow (a tracer, then an independent verifier per
protocol); five came back, and the sixth (the Base bridge, whose trace failed on its output schema) I then read directly, twice, on the same two RPCs. **No target is added and no score changes**: a new scored L1 target is Spap's decision. What follows separates what I re-read myself, on two
public RPCs (publicnode and drpc, identical answers) from what only the verifier reported.

## The process finding first

The tracers' addresses were wrong in every trace. For ether.fi, four of six "contract" addresses were implementations or non-proxy contracts, not the live proxies; for the
Arbitrum and Polygon bridges **all eight addresses had no code or were 39 hex characters long**; the Spark trace pointed at a contract that is not the admin. The verifiers rebuilt each
map from the chain. Verdicts: 4 REFUTED, 1 PARTIAL, 0 confirmed as traced. A trace without a from-scratch verifier is not usable, which is what the routine's maker-checker rule already says;
this is one more measured case.

## USDT0 adapter (Ethereum): $3.48B behind a 3-of-5 Safe of bare keys, no delay

Re-read by me: the OFT adapter `0x6C96dE32...` holds **3,482,875,521 USDT**. Its EIP-1967 admin is ProxyAdmin `0x4de7096B...`, whose owner is Safe `0x4DFF9b5b...`, **3-of-5**. That same Safe is the LayerZero
EndpointV2 delegate of the adapter (`delegates(adapter)`). All five owners are plain EOAs (no code), **three have never sent a transaction** (nonce 0), the other two have nonce 7 and 1.
Verifier, not re-read by me: no module, no guard, no timelock; two independent zero-delay routes to the balance (upgrade the adapter through the ProxyAdmin, or, as owner and delegate, repoint a peer or the DVN
configuration without any upgrade); initialization is locked on the proxy and the implementation; Tether's separate 3-of-6 owner of USDT can blacklist the adapter (a freeze by a third party).
What this does not show: how the five keys are held (a nonce of 0 says nothing about custody), or any misuse.

## Polygon PoS bridge (Ethereum side): a 5-of-9 Safe, and a "timelock" with delay 0

Re-read by me: Safe `0xFa7D2a99...` is **5-of-9** (two of its nine owners are 171-byte contracts, seven are EOAs); the timelock `0xCaf0aa76...` has `getMinDelay()` = **0**; that Safe holds `DEFAULT_ADMIN_ROLE` on
RootChainManager `0xA0c68C63...` (`hasRole` true); the EtherPredicate `0x8484Ef72...` holds **95,092 ETH**. Verifier: the Safe is also the only proposer and executor of that timelock and has no module; it can swap the
checkpoint manager directly (checked by simulation), which allows forged exits, and the same Safe can upgrade the bridge proxies through the zero-delay timelock. ERC-20 balances were not measured.

## ether.fi (eETH, weETH): a real 10-day upgrade delay, an indefinite no-delay pause

Re-read by me: upgrade timelock `0x9f26d4C9...` `getMinDelay()` = **864,000 s (10 days)**; its proposer Safe `0xcdd57D11...` is **6-of-10**; the operating Safe `0x2aCA7102...` is **4-of-7**; the liquidity pool accounts
**2,297,396 ETH** in total. Two addresses (`0xDE3bf1...`, `0x5c8c76...`) sit on both Safes. Verifier: upgrades and role changes need that timelock; the 4-of-7 operating Safe holds every operational role including an indefinite
`pause()` with no delay; a guardian Safe is 1-of-6 and an EOA also holds the guardian role; two timelocks, no open executor. The contract addresses in the original trace were implementations, the live ones are in the verifier's output.

## Spark Liquidity Layer, ALMProxyFreezable `0xe5c63184...`: a 1-of-2 Safe can call anything, but it holds nothing

Re-read by me: Safe `0x8a25A24E...` is **1-of-2** (two EOAs with nonces 92,066 and 769) and `hasRole(ALLOCATOR_ROLE)` on the proxy is true; the proxy holds 0 ETH. Verifier: it holds no USDC, USDS or USDT either; `doCall` lets an
allocator act on any target with no delay; a second allocator is a 2-of-5 Safe; the only brake is a 2-of-4 freezer Safe that reacts, it cannot prevent; the contract is immutable (no proxy admin) and the admin role sits behind a 48 h pause. Scope: this is the freezable proxy the tracer named, **not** Spark's main ALM proxy, which was not read.

## Maple

Not re-read by me except the DAO Safe (`0xd6d4Bcde...`, **4-of-7**); my `delay()` read returned nothing (the timelock uses another interface), so the 3-day delay is the verifier's alone. Verifier: the Globals governor and proxy
admin is a governor timelock with a 3-day delay (execution window 2 days), not the DAO Safe; the DAO Safe holds only the proposer and role-admin roles there; an EOA holds ROLE_ADMIN and can propose role updates that the contract
marks as not cancellable; SecurityAdmin (3-of-6) and OperationalAdmin (3-of-5) are Safes with no module or guard and no signer overlap with the DAO Safe. The two role-holding EOAs have never sent a transaction.

## Base bridge (Ethereum side): 766,354 ETH behind a 2-of-2 of two nested Safes, upgrade with no timelock

Read by me directly (both RPCs identical, every line): the OptimismPortal `0x49048044...` holds **766,354 ETH**; the L1StandardBridge `0x3154Cf16...` holds 6.04M USDC and no ETH. The portal, the bridge, SystemConfig and the DisputeGameFactory
all share EIP-1967 admin `ProxyAdmin 0x0475cBCA...`, whose owner is Safe `0x7bB41C30...`: **2-of-2, no module**, with no timelock in between. The same Safe is the portal's `guardian()` and the DisputeGameFactory's owner. Its two owners are themselves Safes (no module on either):
one **3-of-6** (`0x98550547...`, six EOAs) and one **8-of-11** (`0x20AcF55A...`, eleven EOAs, all with nonce 0, which for a Safe signer only means it has never sent a transaction). So an upgrade needs at least 3 of 6 and 8 of 11 signers, 11 people at minimum, acting at once and immediately.
SystemConfig has a separate owner, Safe `0x14536667...`, **3-of-12** (twelve EOAs, four with nonce 0). Not read: which organization holds which nested Safe (the chain does not say), the guard slot, and the L2 side. Of the six, this is the strongest authority structure; it is also the one holding the most value.

## Arbitrum bridge

Already tracked (Arbitrum's own registry: the 9-of-12 Security Council and the L1 timelock). The verifier's corrected addresses agree with it; nothing new.

## What would come next (not done)

Add USDT0, the Polygon PoS bridge, ether.fi and Maple as scored L1 targets, or leave them as disclosed: Spap's call. Each would need its signers in the overlap registry and the timelock queue watch would gain the
Polygon and ether.fi timelocks. Not read at all: the Spark main ALM proxy, ether.fi's guardian Safe, the L2 side of both rollup bridges.

## Verification

`scripts/lib/web3_utils.call_raw`/`read_slot_as_address` against `ethereum-rpc.publicnode.com` and `eth.drpc.org` (blocks about 26,063,900), one script, every figure marked "re-read" above appeared identically on both.
The rest is the verifier's own read (Blockscout logs and sources, replayed roles), unreproduced here and labeled so. No key, nothing sent.
