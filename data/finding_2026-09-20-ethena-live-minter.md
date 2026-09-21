# Finding (2026-09-20): the Ethena target was USDe's retired minter, and the live minter now scores 65/100/55

Status: corrected in the scorer (`chains/ethereum-l1/scorers.py::score_ethena_minting`, commit
`042f805`) and **pushed on-chain 2026-09-20** as a new Ethereum L1 target, index 14 (transaction
`0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`, block 11,740,952, read back
65/100/55/100/20/73; the full transaction table is in
`data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md` section 9). The
old target, index 3, is retired. Found by the unscored-role sweep
(`data/finding_2026-09-20-unscored-role-sweep.md`, section 2), traced and then adversarially
re-verified on two public RPCs with a third RPC for event logs. No transaction, key or repository
edit was used by the verification.

## 1. What was wrong

`score_ethena_minting` scored `0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3` as "USDe's minting
authority" and concluded that a 5-of-10 Safe controls minting directly with no delay
(55/100/0/100/20/52). That reading was correct for that contract and irrelevant to USDe:

- USDe emitted exactly two `MinterUpdated` events in its life. Block 18,578,531 (2023-11-15) set
  the `0x2CC4...` contract; block 20,261,016 (2024-07-08 09:52:11 UTC) set the live minter
  `0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3`. None since, so `USDe.minter()` has not been
  `0x2CC4...` for over two years.
- `USDe.mint()` simulated from the old address reverts `OnlyMinter` on both RPCs, and the old
  contract holds no collateral and no USDe.
- Re-pointing USDe at it again would need `USDe.setMinter`, which is `onlyOwner`, and
  `USDe.owner()` is the 24h `EthenaTimelockController`. Not whitelisted, so a scheduled 24h
  operation from the 5-of-10 Safe, visible as `CallScheduled`.
- The old contract itself is intact and still owned by the Safe directly with no timelock, which
  is why it looked like a scary target. It is a watch item, not a live authority: if `setMinter`
  ever points USDe back at it, the new scorer notices (`USDe.minter()` no longer equals the scored
  contract) and degrades to 20/20/0 instead of keeping a confident number.

The oracle contract has no removal function, so the old target is retired by ceasing to refresh it
(see section 9 of the cross-exposure finding for what its on-chain entry does until it goes stale).

## 2. The live minter's verified authority

`EthenaMinting` `0xe3490297...b62D3`: deployed 2024-06-21 (block 20,142,841), not a proxy
(Sourcify `isProxy` false, EIP-1967 implementation slot empty), Sourcify exact match (solc 0.8.20,
25 sources). Single-admin AccessControl.

- **Admin.** `DEFAULT_ADMIN_ROLE` (also `owner()`) is the `EthenaTimelockController`
  `0xE8Dc0Fab349EA169283C48Ccfd09d797E6DB7c94` since block 25,522,488 (2026-07-13), moved from the
  Safe. `getMinDelay()` is 86400 s. No pending transfer.
- **Timelock.** The 5-of-10 Safe `0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862` is the only PROPOSER
  and the only CANCELLER, so the 24h delay is a visibility window and not a second key. EXECUTOR is
  held by the Safe, a bare EOA `0x352040dC...0E8f` and a separate 3-of-6 Safe. The delay is
  exercised: all 176 scheduled operations waited at least 86,628 s, the minimum delay never
  changed, zero `Cancelled` events.
- **The Safe.** 5-of-10, Safe v1.3.0, 10 bare-EOA owners (re-read), no modules, and an
  `EthenaSafeGuard` `0x74abe780...8D29` installed 2026-07-06: only its whitelisted executors (the
  EOA above and the 3-of-6 Safe) can submit the Safe's transactions, and removing the guard takes
  48h in public. A positive control, disclosed in the scorer notes and not scored.
- **Six redirect-class selectors plus `USDe.setMinter` are delayed.** `grantRole`,
  `transferAdmin`, `addCustodianAddress`, `addSupportedAsset`, `setTokenType`,
  `setStablesDeltaLimit` and `USDe.setMinter` (the strongest unbacked-mint control) all read
  `isWhitelisted` false on both RPCs. The replay of all 55 `FunctionWhitelisted` events shows
  none of them and none targeting USDe, and simulation of the Safe's path reverts
  `NotWhitelisted`.
- **Three instant lanes** (whitelist entries at blocks 25,350,325 and 25,631,325, the Safe alone,
  no delay): `revokeRole`, `addWhitelistedBenefactor`, `removeWhitelistedBenefactor`. Freeze or
  configuration type, none can mint.
- **Four dead whitelist entries**: `disableMintRedeem`, `removeMinterRole`, `removeRedeemerRole`,
  `removeCollateralManagerRole`. They are gated on `GATEKEEPER_ROLE`, which the timelock does not
  hold, so the inner call reverts (simulated). Latent, not harmless: one delayed
  `grantRole(GATEKEEPER, timelock)` would make all four live, which is why the scorer keeps a live
  `hasRole` read instead of hardcoding "dead".
- **Direct sweep, outside the timelock.** The same Safe holds `COLLATERAL_MANAGER_ROLE` on the
  minter directly (since block 21,772,174, 2025-02-04, never migrated to the timelock).
  `transferToCustody` can move everything the minter holds, about 93.1M USD at par on 2026-09-20
  (USDC 31.10M, USDT 31.03M, USDtb 30.99M, plus about 3.9k PYUSD, 11 USDG and under 1 USDm), to one
  of 5 registered custodian EOAs, instantly. It cannot pay an arbitrary address because
  `addCustodianAddress` is delay-gated; the 5 custodians (all bare EOAs, none ever removed) are
  the only destinations.
- **Hot keys.** 20 bare-EOA `MINTER_ROLE` holders (the same 20 hold `REDEEMER_ROLE`), unrotated
  since 2024-07, and 4 bare-EOA `GATEKEEPER_ROLE` holders that can halt mint and redeem and strip
  roles instantly. The Safe can instantly `revokeRole` all four gatekeepers through the whitelist,
  so they are not an independent brake on a compromised Safe.
- **A MINTER key alone cannot create unbacked USDe.** Reproduced by simulation on both RPCs:
  `mint()` needs a valid benefactor EIP-712 (or EIP-1271) signature from a whitelisted benefactor
  (596 of them), real collateral pulled from that benefactor to a registered custodian, and a
  stable-value check that lets USDe exceed collateral by under 1 bp. Even a simulated benefactor
  with a completely bypassed signature check reverts on the price check or on the ERC-20 allowance.
  The shortest instant path is the Safe plus one MINTER key, and it is still limited to backed
  mints. Per-block caps (200M USDe global, 4.1% of supply) bound a single block, not a sequence.
- **Seven collateral assets are active, all `STABLE`**: USDC, USDT, DAI, USDtb, PYUSD, USDm
  (MegaUSD, an upgradeable proxy with about 31.4k supply and 59 holders) and USDG. `STABLE` tokens
  are compared 1:1 by decimals and never priced, so the issuer or depeg risk of those tokens is
  the one route to a bad mint that needs no delayed admin action. That is market and issuer risk,
  not an authority hole, and it was not assessed here.

**What the first trace got wrong**, kept as a record. The first draft of this trace said three
collateral assets (USDC, USDT, DAI) and about 62M USD held. The verification pass corrected both:
seven active assets (the constructor set plus USDtb, PYUSD, USDm and USDG added in blocks
21,418,032, 23,397,891, 24,989,129 and 25,066,153, all before the admin moved to the timelock) and
about 93.1M USD (the earlier figure omitted USDtb). It also added the Safe guard, which the first
draft did not know about. The scorer's notes already carry the corrected figures.

## 3. The score

`65/100/55/100/20`, composite 73, target `0xe3490297...b62D3`, root group `ethena-safe-0x3b0aaf6e`.
Same convention as `score_usdtb_psm()`, which uses the same Safe and the same timelock.

| Field | Value | Why |
|---|---|---|
| adminKey | 65 | The convention's test is "redirect-class setters genuinely delayed", re-verified three ways (`isWhitelisted`, event replay, simulation). Drops to 30 if any redirect-class selector or `USDe.setMinter` becomes whitelisted, and reverts to 55 if the Safe is `DEFAULT_ADMIN` directly again. |
| multisig | 100 | `min(5*15 + 5*5, 100)`, 5-of-10, 10 bare-EOA owners. The guard does not move it, it is already at the cap. |
| timelock | 55 | Real 24h delay (`getMinDelay` 86400 on both RPCs), capped by the three disclosed instant lanes, and the same Safe is the only canceller. |
| oracle | 100 | No price-report authority applies. |
| cross | 20 | Same root group as USDtb PSM and the three Ethena LayerZero OFTAdapters, 4 other tracked L1 targets, so `100 - 4*20`. Unchanged from the retired target. |
| composite | 73 | `floor(0.4*65 + 0.3*100 + 0.3*55 + 0.5)`. The retired target read 52. |

Any unread or inconsistent guard (`USDe.minter()`, admin holders, timelock delay or proposer, the
Safe, the whitelist reads) degrades to 20/20/0 rather than keeping a confident number.

**Why 65/55 and not a harsher reading.** The instant path to move about 93M USD is real, and a
harsher reading of it is defensible: adminKey 55 to 60, which with the same other fields gives a
composite of 69 to 71 (computed, not pushed). 65 was kept because (1) the convention's own test,
that every fund-redirect and unbacked-mint selector is delayed, passes and nothing found refutes
it; (2) the instant sweep can only reach one of 5 already-registered custodians, and adding a
custodian is delayed; and (3) it is the same convention as `score_usdtb_psm()`, which sits behind
the same Safe and timelock, and nothing about this contract differs in the way the convention
tests. The instant sweep is disclosed in the scorer notes next to the score rather than folded
into it, the same treatment Aave's guardian and Compound's pause guardian get.

## 4. What is NOT settled

- **Role-holder completeness rests on indexer logs.** AccessControl is not enumerable, so the 20
  MINTER/REDEEMER, 4 GATEKEEPER and timelock role sets come from `eth_getLogs` replay (a third
  public RPC) cross-checked against Blockscout counts (510 timelock logs and 787 minter admin
  events, equal on both), plus `hasRole` on both RPCs for 46 net holders and 43 revoked accounts.
  Two independent indexers agree, but an unindexed holder cannot be excluded by RPC alone.
- **The timelock source is only a partial verification.** The timelock is a Blockscout partial
  match (solc 0.8.26), not a full match: its deployed bytecode equals `eth_getCode` on both RPCs,
  and its behaviour was checked by about 40 `eth_call` simulations, not by recompilation.
- **Nothing was recompiled locally.** No solc 0.8.20 was available and downloading a compiler was
  out of scope. The minter's source-to-bytecode link rests on Sourcify's own recompilation plus
  five checks done here (identical `eth_getCode` on two RPCs, a runtime diff whose 193 differing
  bytes all fall inside the 9 immutable slots, the creation transaction input starting with the
  recompiled creation bytecode, all 25 source hashes matching the metadata, and all 52 ABI
  selectors found in the bytecode). One claim
  from the first draft was removed as not reproduced: that the metadata's IPFS hash equals the
  CID of Sourcify's metadata JSON.
- **The controllers behind the keys are not attributable on-chain.** The 5 custodian EOAs, the 20
  minter/redeemer EOAs, the 4 gatekeepers, the executor EOA `0x3520...` and the 10 + 6 Safe owners
  are bare keys with no public owner. Whether the collateral is backed beyond the on-chain
  custodian hop is off-chain and not visible here.
- **The Safe guard was not exercised.** `eth_call` simulations spoof `from` and cannot run
  `execTransaction`, so the guard's effect was shown by calling `guard.checkTransaction` as the
  Safe and from the observed senders (30 of 30 whitelisted-lane transactions were submitted by the
  one executor EOA).
- **Stable-issuer and depeg risk of USDtb, PYUSD, USDm and USDG** (proxy admins, mint authority)
  was not assessed.
- **Observed and not analysed:** `setPeer(uint32,bytes32)` is an instant whitelisted lane on the
  USDe and sUSDe LayerZero OFTAdapters (used 2026-09-09 to set one endpoint's peer to zero). On a
  lock-and-release adapter a hostile peer is a redirect-class control. Out of scope for the minter
  and not part of this score, but relevant to any USDe-wide authority score.
- **The score is a dated reading.** It reflects 2026-09-20. A change to the timelock whitelist,
  the delay, the admin holder or the Safe guard moves it; the scorer re-reads all of those every
  run, and the drift audit is what catches a change between pushes.
