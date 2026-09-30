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
**Closed 2026-09-27**: no module, no guard (confirmed live, both RPCs identical; Safe v1.4.1, its own nonce 159 -- a Safe's nonce counts its OWN executed transactions, unrelated to its owners' individual EOA nonces above), no timelock anywhere in the path.
Verifier: two independent zero-delay routes to the balance (upgrade the adapter through the ProxyAdmin, or, as owner and delegate, repoint a peer or the DVN configuration without any upgrade); initialization is locked on the proxy and the implementation;
Tether's separate 3-of-6 owner of USDT can blacklist the adapter (a freeze by a third party). What this does not show: how the five keys are held (a nonce of 0 says nothing about custody), or any misuse.

## Polygon PoS bridge (Ethereum side): a 5-of-9 Safe, and a "timelock" with delay 0

Re-read by me: Safe `0xFa7D2a99...` is **5-of-9** (two of its nine owners are 171-byte contracts, seven are EOAs), **no module** (confirmed live, both RPCs); the timelock `0xCaf0aa76...` has `getMinDelay()` = **0**; that Safe holds `DEFAULT_ADMIN_ROLE` on
RootChainManager `0xA0c68C63...` (`hasRole` true); the EtherPredicate `0x8484Ef72...` holds **95,092 ETH**. Verifier: the Safe is also the only proposer and executor of that timelock; it can swap the
checkpoint manager directly (checked by simulation), which allows forged exits, and the same Safe can upgrade the bridge proxies through the zero-delay timelock.

**Closed 2026-09-27** (this section's two "not read" items): the two 171-byte owners are themselves Gnosis Safes: `0x4e981bAe...` is **2-of-5**, `0x9d851f8b...` is **2-of-7** -- the outer 5-of-9 threshold can in practice be reached with
fewer than 5 independently-held keys if either nested Safe's own 2 signers act as one. **ERC-20 balances of the ERC20Predicate `0x40ec5B33...`** (read live, both RPCs identical): **1,016,666,585.53 USDC, 481,089,339.88 DAI, 7,995,358.41 USDT, 1,942.7
WBTC, 52.51 WETH** -- at listed prices this is over $1.7B, several times the 95,092 ETH (~$316M) already noted for the EtherPredicate, so the bridge's total exposure to this Safe is closer to **$2B+**, not the ETH figure alone. Not read: who holds the
two nested Safes' 12 combined signers, or every other ERC-20 the predicate holds beyond these five.

## ether.fi (eETH, weETH): a real 10-day upgrade delay, an indefinite no-delay pause

Re-read by me: upgrade timelock `0x9f26d4C9...` `getMinDelay()` = **864,000 s (10 days)**; its proposer Safe `0xcdd57D11...` is **6-of-10**; the operating Safe `0x2aCA7102...` is **4-of-7**; the liquidity pool accounts
**2,297,396 ETH** in total. Two addresses (`0xDE3bf1...`, `0x5c8c76...`) sit on both Safes. Verifier: upgrades and role changes need that timelock; the 4-of-7 operating Safe holds every operational role including an indefinite
`pause()` with no delay; a guardian Safe is 1-of-6 and an EOA also holds the guardian role; two timelocks, no open executor. The contract addresses in the original trace were implementations, the live ones are in the verifier's output.

**Closed 2026-09-27** (this section's own "not read" item): `GUARDIAN_ROLE` on the RoleRegistry proxy (`0x62247D29...`, read live, both RPCs identical) has exactly 3 holders -- a bare EOA `0x9AF12989...` (40 transactions), the 4-of-7
operating Safe `0x2aCA7102...`, and a separate Safe `0x427989Bb...`, **1-of-6**. `SUPER_GUARDIAN_ROLE` has 2 holders, the same operating Safe and the same 1-of-6 Safe. The 1-of-6 Safe's six owners are `0x31430A3C...`, `0xE63794CF...`,
`0x5dfb8BC4...`, `0xFa238cB3...`, `0x46Cba1e9...`, `0x566E58ac...` -- **four of those six also sit on the 4-of-7 operating Safe** (`0xE63794CF...`, `0x5dfb8BC4...`, `0xFa238cB3...`, `0x566E58ac...`). So the "separate" 1-of-6 guardian path is not
independent of the operating Safe: a single one of those four shared keys already satisfies the 1-of-6 guardian threshold on its own, and the same four count toward the 4-of-7. Not read: who holds the bare EOA `0x9AF12989...` or the two
guardian-Safe-only owners (`0x31430A3C...`, `0x46Cba1e9...`).

## Spark Liquidity Layer, ALMProxyFreezable `0xe5c63184...`: a 1-of-2 Safe can call anything, but it holds nothing

Re-read by me: Safe `0x8a25A24E...` is **1-of-2** (two EOAs with nonces 92,066 and 769) and `hasRole(ALLOCATOR_ROLE)` on the proxy is true; the proxy holds 0 ETH. Verifier: it holds no USDC, USDS or USDT either; `doCall` lets an
allocator act on any target with no delay; a second allocator is a 2-of-5 Safe; the only brake is a 2-of-4 freezer Safe that reacts, it cannot prevent; the contract is immutable (no proxy admin) and the admin role sits behind a 48 h pause. Scope: this is the freezable proxy the tracer named, **not** Spark's main ALM proxy, which was not read.

**Incomplete, 30 Sep** (found through the DeFiScan v2 diff, `finding_2026-09-30-defiscan-diff-triage.md`): "holds nothing" is true of balances, not of
privileges. Replaying `RoleGranted` shows the proxy holds `SETTER_ROLE` on four Spark Savings V2 vaults this repository does not track (spUSDC about
$300.6M, spUSDT about $447.0M, a staking-derivative token about 21,169 WETH, spPYUSD) and the only `UPDATE_ROLE` on the CapAutomator. So the 1-of-2 and 2-of-5 allocator
Safes can, with no delay, set those vaults' savings rate anywhere inside bounds set by SparkProxy ([0%, 10%] APR, [0%, 5%] for a staking-derivative token) and move caps
deterministically. A yield and liability risk, not a principal one: no `TAKER_ROLE`.

## Maple

**Closed 2026-09-27**: found the exact contract via `maple-labs/address-registry` (Maple's own canonical GitHub registry) and re-read everything live, both RPCs identical. GovernorTimelock `0x2eFFf88747EB5a3FF00d4d8d0f0800E306C0426b`:
`MIN_DELAY` = 86,400 s and `MIN_EXECUTION_WINDOW` = 86,400 s are hard floors in the contract; the live `defaultTimelockParameters()` in force is **(259,200 s delay, 172,800 s execution window)** -- 3 days and 2 days, confirming the verifier's number.
Role holders replayed from `RoleUpdated` events (Tenderly full history) and matched to the live role-constant getters: **`PROPOSER_ROLE`** held only by the DAO Safe `0xd6d4Bcde...` (**4-of-7**, confirmed live); **`EXECUTOR_ROLE`** held by OperationalAdmin
`0xCe1cE7c7...` (**3-of-5**, no module) and by EOA `0x6D9F3a38...`; **`CANCELLER_ROLE`** held only by SecurityAdmin `0x6b1A78C1...` (**3-of-6**, no module); **`ROLE_ADMIN`** held by the DAO Safe and by EOA `0xa04Bddfb...`. Both EOAs are plain (no code)
and have **never sent a transaction (nonce 0)**, confirmed live. This matches the original trace exactly and names the two EOAs it had left anonymous.

## Base bridge (Ethereum side): 766,354 ETH behind a 2-of-2 of two nested Safes, upgrade with no timelock

Read by me directly (both RPCs identical, every line): the OptimismPortal `0x49048044...` holds **766,354 ETH**; the L1StandardBridge `0x3154Cf16...` holds 6.04M USDC and no ETH. The portal, the bridge, SystemConfig and the DisputeGameFactory
all share EIP-1967 admin `ProxyAdmin 0x0475cBCA...`, whose owner is Safe `0x7bB41C30...`: **2-of-2, no module**, with no timelock in between. The same Safe is the portal's `guardian()` and the DisputeGameFactory's owner. Its two owners are themselves Safes (no module on either):
one **3-of-6** (`0x98550547...`, six EOAs) and one **8-of-11** (`0x20AcF55A...`, eleven EOAs, all with nonce 0, which for a Safe signer only means it has never sent a transaction). So an upgrade needs at least 3 of 6 and 8 of 11 signers, 11 people at minimum, acting at once and immediately.
SystemConfig has a separate owner, Safe `0x14536667...`, **3-of-12** (twelve EOAs, four with nonce 0). Not read: which organization holds which nested Safe (the chain does not say), the guard slot, and the L2 side. Of the six, this is the strongest authority structure by the number of signers it needs (at least 11 people across the two nested Safes); it has no timelock, which the composite weights at 30%, and it is also the one holding the most value. "Strongest" here means most signers required, not the best composite.

## Arbitrum bridge

Already tracked (Arbitrum's own registry: the 9-of-12 Security Council and the L1 timelock). The verifier's corrected addresses agree with it; nothing new.

## What would come next (not done)

Add USDT0, the Polygon PoS bridge, ether.fi and Maple as scored L1 targets, or leave them as disclosed: Spap's call. Each would need its signers in the overlap registry and the timelock queue watch would gain the
Polygon and ether.fi timelocks. Not read at all: the Spark main ALM proxy, ether.fi's guardian Safe, the L2 side of both rollup bridges.

## Verification

`scripts/lib/web3_utils.call_raw`/`read_slot_as_address` against `ethereum-rpc.publicnode.com` and `eth.drpc.org` (blocks about 26,063,900), one script, every figure marked "re-read" above appeared identically on both.
The rest is the verifier's own read (Blockscout logs and sources, replayed roles), unreproduced here and labeled so. No key, nothing sent.
