# Tempo rotation audit, 2026-09-21: index 1 (USDC.e), non-circular re-derivation

**Result: no divergence.** The six dimensions published on the Moderato oracle for
`USDC.e` (`0x20C0...8b50`) -- adminKey 65, multisig 98, timelock 0, oracleAuthority 100,
crossExposure 80, composite 55 -- were each re-derived from Tempo mainnet without running
any of this repository's scoring code, and compared against `getScore()` read live inside
the same script.

## Why this file replaces the previous two audit attempts

| Attempt | What it actually did | Why it did not establish the result |
|---|---|---|
| 2026-09-20 | `re_derive_score.py` imported `scripts/methodology_test.py` and called `score_token()` | Re-runs the code that produced the published number, so it agrees with itself. The on-chain side was a `print` of a hardcoded `55`. |
| 2026-09-21, attempt 1 | `mt.score_token()` again, plus a decorative `audit_usdc_independent.py` committed at the repo root | The committed script reverted on its first `eth_call` (invented `transferPolicyId` selector `0x64aa9f91`), carried three invented role hashes, a three-argument `RoleMembershipUpdated` signature, `burn(uint256)`'s selector labelled `threshold()`, a hardcoded `weakest_k=5, weakest_n=7` "placeholder", and a hardcoded on-chain `65`. It never produced a line of the audit its commit message claimed. `crossExposureScore` was not covered at all. |
| 2026-09-21, attempt 2 (this file) | `chains/tempo/scripts/audit_rotation_index.py` | Imports nothing from the repo; derives every hash and selector at runtime with a keccak-256 implemented in the file; reads the chain for every fact; reads `getScore()` itself; covers all six dimensions including `crossExposureScore`. |

`audit_usdc_independent.py` is removed by the same commit: leaving a dead script with
false cryptographic constants at the repo root invites a future run to treat it as a
reference.

## What the re-derivation reads, rule by rule

| Rule (METHODOLOGY.md 4.1) | Read |
|---|---|
| R1 / R1b | `RoleMembershipUpdated(bytes32,address,address,bool)` over the full chain history (0 to head, 100,000-block windows), then `hasRole(address,bytes32)` on three providers for each candidate. `transferPolicyId() = 1` (always-allow), so no TIP-403 policy admin joins the set. |
| R2 / R3 | `0x09c865FA...3A1f` resolves as a LayerZero OneSig via `threshold()` and `getSigners()` (5 of 7, all seven with empty code); `0x8c76e2F6...4392` (ISSUER_ROLE) resolves through `owner()` to that same OneSig. Weakest key: k=5, n=7. |
| R4 / R5 | k >= 3 gives 65; `max(16, min(100, 20*5 - (7-5)))` gives 98. |
| R5b | No `getMinDelay()` / `delay()` / `minDelay()` on any root holder, so 0. |
| R5c | 100: a TIP-20 stablecoin reads no price. |
| R6 | The 14 tracked targets are enumerated from the oracle's own `trackedTargets` array. For each of the 13 others, an authority closure (owner, curator, Safe owners, OneSig signers, EIP-1967 admin, LayerZero delegate, enumerable role members, plus role-log candidates for TIP-20 precompiles) is compared with this target's seven root signers. Exactly one -- EURC.e -- intersects, so 100 - 20 = 80. A disjoint closure is a superset disjointness proof: the exact signer set is a subset of the closure. |
| R7 | `floor(0.4*65 + 0.3*98 + 0.3*0 + 0.5) = 55`. |

## RPC honesty

The 2026-09-20 and 2026-09-21 attempts both claimed "two independent RPC endpoints
verified (rpc.tempo.xyz and tempo-rpc.publicnode.com)" for the role derivation. That was
false for the decisive part. Measured again today and printed by the script:

* `tempo-rpc.publicnode.com` serves `eth_call` fine, and serves `eth_getLogs` on recent
  blocks (HTTP 200 on the last ten), but answers **HTTP 403 on any historical block**,
  including block 4,010,415 where USDC.e's first role grant sits. It cannot be the second
  source of a full-history scan. (This refines the earlier "403 on everything" finding
  rather than repeating it.)
* The second source used here is `tempo.drpc.org`, a genuinely independent provider
  (chain id 4217 confirmed). Its log ranges are narrow in practice (100 blocks fine, 500
  rejected), so the verification re-reads **each event block individually** and requires
  an identical log set. All 54 role logs of the 10 tracked TIP-20 targets matched.
* Every `eth_call` that feeds a published number is double-read, and the `hasRole`
  confirmations are read on all three providers.

## New targets: 0, established live

`chains/tempo/scripts/check_new_targets_live.py` reads the official registry, the oracle's
tracked set and the live `totalSupply()` of all 25 untracked tokens on two providers, then
applies the trigger written in `data/scouted_bridged_tokens_2026-09-19.md` section 5.
Registry unchanged (1.0.34, 34 tokens, timestamp 2026-09-10T16:41:24.740Z); no untracked
token moved by the documented two orders of magnitude.

**One correction to the 2026-09-19 reasoning, stated as a correction and not as a new
finding.** That document excluded `senpathUSDE` partly on the ground that it is issued by
the "same issuer, same root-authority family" as the already-scored Sentora pathUSD Morpho
Vault V2. A live authority read does not support that: `senpathUSDE`'s only root holder is
`ISSUER_ROLE` = `0xd730394f...fa4f`, a contract with no `owner()` at all (the call reverts)
that resolves as **unresolved** under R2, and whose authority closure shares no address
with any of the 14 tracked targets. `senpathUSDE` also sits above the weakest covered
token by value (118,450 vs cUSD's 50,337). The documented trigger is still not armed -- it
has moved about 1.7 percent since 2026-09-19, not two orders of magnitude -- so no target
is added by this maintenance run. It is recorded as an open lead for a scouting pass.

## Full output, `audit_rotation_index.py 1` (exit 0)

```
== 0. derived constants (nothing below is hardcoded) ==
   keccak256('')                                            = 0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470
   role hash DEFAULT_ADMIN_ROLE   = 0x0000000000000000000000000000000000000000000000000000000000000000
   role hash ISSUER_ROLE          = 0x114e74f6ea3bd819998f78687bfcb11b140da08e9b7d222fa9c1f1ba1f2aa122
   role hash PAUSE_ROLE           = 0x139c2898040ef16910dc9f44dc697df79363da767d8bc92f2e310312b816e46d
   role hash BURN_BLOCKED_ROLE    = 0x7408fdc0d31c7bcb349eab611f5d1168acd4303574993f8cdc98b1cd18c41cae
   role hash UNPAUSE_ROLE         = 0x265b220c5a8891efdd9e1b1b7fa72f257bd5169f8d87e319cf3dad6ff52b94ae
   selector hasRole(address,bytes32)     = 0xac4ab3fb
   selector transferPolicyId()           = 0x9c4bad29
   selector threshold()                  = 0x42cde4e8
   selector getSigners()                 = 0x94cf795e
   selector getThreshold()               = 0xe75235b8
   selector getOwners()                  = 0xa0e67e2b
   selector owner()                      = 0x8da5cb5b
   selector getScore(address)            = 0xd47875d0
   selector trackedTargets(uint256)      = 0x9481e5e0
   selector trackedTargetsCount()        = 0x835e2172
   selector totalSupply()                = 0x18160ddd
   topic0   RoleMembershipUpdated(bytes32,address,address,bool) = 0x4811f35680ba814bed6b0b926a2949c8a1000f4f2443cfe9978745d46a251aec

== 1. networks ==
   https://rpc.tempo.xyz                  chainId=4217
   https://tempo.drpc.org                 chainId=4217
   https://tempo-rpc.publicnode.com       chainId=4217
   https://rpc.moderato.tempo.xyz         chainId=42431

== 2. target taken from the oracle's own trackedTargets array ==
   oracle 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 trackedTargetsCount() = 14
   trackedTargets(1) = 0x20c000000000000000000000b9537d11c60e8b50

== 3. target identity, read live ==
   name='Bridged USDC (Stargate)' symbol='USDC.e' decimals=6
   totalSupply = 83,940,465.60
   eth_getCode = 0xef  (TIP-20 precompile instance marker 0xef: True)
   transferPolicyId() = 1  ->  always-allow (no policy admin in the root set, R1)

== 4. R1b: historical role-event scan (candidates) ==
   TIP-20 precompile instances among the 14 tracked targets: 10 (they expose no role enumeration, so their holders only exist in logs)
   head block 40,556,990, scanned 0..40,556,990 in 100,000-block windows on https://rpc.tempo.xyz
   9 RoleMembershipUpdated log(s) on 0x20c000000000000000000000b9537d11c60e8b50
     block    4,010,415  role=0x0000000000000000000000000000000000000000000000000000000000000000  account=0x5e6e4f234c7ad525700fcf5b7862589950589ed5  granted=True
     block    4,013,280  role=0x114e74f6ea3bd819998f78687bfcb11b140da08e9b7d222fa9c1f1ba1f2aa122  account=0xa7d119b72f4ce3315b46c281b9da5bd0496d8543  granted=True
     block    4,013,283  role=0x139c2898040ef16910dc9f44dc697df79363da767d8bc92f2e310312b816e46d  account=0x09c865fafb64d8cbcbf673d61a11e066063e3a1f  granted=True
     block    4,013,285  role=0x265b220c5a8891efdd9e1b1b7fa72f257bd5169f8d87e319cf3dad6ff52b94ae  account=0x09c865fafb64d8cbcbf673d61a11e066063e3a1f  granted=True
     block    4,013,287  role=0x7408fdc0d31c7bcb349eab611f5d1168acd4303574993f8cdc98b1cd18c41cae  account=0x09c865fafb64d8cbcbf673d61a11e066063e3a1f  granted=True
     block    4,013,608  role=0x0000000000000000000000000000000000000000000000000000000000000000  account=0x09c865fafb64d8cbcbf673d61a11e066063e3a1f  granted=True
     block    4,013,611  role=0x0000000000000000000000000000000000000000000000000000000000000000  account=0x5e6e4f234c7ad525700fcf5b7862589950589ed5  granted=False
     block    5,140,155  role=0x114e74f6ea3bd819998f78687bfcb11b140da08e9b7d222fa9c1f1ba1f2aa122  account=0x8c76e2f6c5ceda9aa7772e7eff30280226c44392  granted=True
     block    5,140,166  role=0x114e74f6ea3bd819998f78687bfcb11b140da08e9b7d222fa9c1f1ba1f2aa122  account=0xa7d119b72f4ce3315b46c281b9da5bd0496d8543  granted=False
   second source https://tempo.drpc.org: re-read 53 individual block(s) covering all 54 role log(s) of the 10 TIP-20 targets -> IDENTICAL log set
   honesty control on the third provider https://tempo-rpc.publicnode.com:
     eth_getLogs on the 10 most recent blocks        -> HTTP 200
     eth_getLogs on the OLDEST role-event block 139,171 -> HTTP 403
     it serves recent logs but refuses historical ones, so it CANNOT be a second
     source for this full-history scan -- only for eth_call, where it is used above.

== 5. R1: root-control set (hasRole confirmed on 3 providers) ==
   DEFAULT_ADMIN_ROLE   -> ['0x09c865fafb64d8cbcbf673d61a11e066063e3a1f']
   ISSUER_ROLE          -> ['0x8c76e2f6c5ceda9aa7772e7eff30280226c44392']
   PAUSE_ROLE           -> ['0x09c865fafb64d8cbcbf673d61a11e066063e3a1f']
   BURN_BLOCKED_ROLE    -> ['0x09c865fafb64d8cbcbf673d61a11e066063e3a1f']
   UNPAUSE_ROLE         -> ['0x09c865fafb64d8cbcbf673d61a11e066063e3a1f']   [excluded from root set, R1]
   root-control set = ['0x09c865fafb64d8cbcbf673d61a11e066063e3a1f', '0x8c76e2f6c5ceda9aa7772e7eff30280226c44392']

== 6. R2/R3: resolving each root holder to a key ==
   0x09c865fafb64d8cbcbf673d61a11e066063e3a1f -> LayerZero OneSig k=5 n=7 delay=0s
      signers (7): ['0xfd3f88eca6cc5301b6d7068a09dc924ae9dfa3c3', '0x00bd5c12508a346e4355c8ee085ae2bcb742e814', '0xf02cc4dc84ac59bd6089baddceb9d4ef3aefb0f0', '0x79e2b9c1f6c9ed1375c93aaf139e6c4537f48523', '0x69784c33e460ab284b32eea886c2eb5ba8b5aa01', '0xa37b4a8a5538d2f21c4ea8a27db8eda8c6260d1d', '0xc6a38f3da88ff791e296c6e05cd669d22a979e03']
      signers with empty code (EOA): 7/7
   0x8c76e2f6c5ceda9aa7772e7eff30280226c44392 -> contract -> owner() -> LayerZero OneSig k=5 n=7 delay=0s
      resolved signer set (7): ['0x00bd5c12508a346e4355c8ee085ae2bcb742e814', '0x69784c33e460ab284b32eea886c2eb5ba8b5aa01', '0x79e2b9c1f6c9ed1375c93aaf139e6c4537f48523', '0xa37b4a8a5538d2f21c4ea8a27db8eda8c6260d1d', '0xc6a38f3da88ff791e296c6e05cd669d22a979e03', '0xf02cc4dc84ac59bd6089baddceb9d4ef3aefb0f0', '0xfd3f88eca6cc5301b6d7068a09dc924ae9dfa3c3']
   weakest key (R3): k=5 n=7 kind=LayerZero OneSig

== 7. R5b: enforced delay on every path ==
   timelock getters found on the root set: none

== 8. re-derived dimensions (formulas R4/R5/R5b/R5c/R7) ==
   adminKeyScore       = 65   (R4 on k=5)
   multisigScore       = 98   (R5: max(16, min(100, 20*5 - (7-5))))
   timelockScore       = 0   (R5b on minimum enforced delay 0s)
   oracleAuthorityScore= 100   (R5c: target reads no price)
   compositeScore      = 55   (R7: floor(0.4*65+0.3*98+0.3*0+0.5))

== 9. R6: crossExposureScore, re-derived over the whole tracked set ==
   this target's root signers (7): ['0x00bd5c12508a346e4355c8ee085ae2bcb742e814', '0x69784c33e460ab284b32eea886c2eb5ba8b5aa01', '0x79e2b9c1f6c9ed1375c93aaf139e6c4537f48523', '0xa37b4a8a5538d2f21c4ea8a27db8eda8c6260d1d', '0xc6a38f3da88ff791e296c6e05cd669d22a979e03', '0xf02cc4dc84ac59bd6089baddceb9d4ef3aefb0f0', '0xfd3f88eca6cc5301b6d7068a09dc924ae9dfa3c3']
   [ 0] 0xcccccccc00000000000000000000000000000001 closure=  7 addr  -> disjoint
   [ 2] 0x20c00000000000000000000014f22ca97301eb73 closure=  9 addr  -> disjoint
   [ 3] 0x20c0000000000000000000000000000000000000 closure=  5 addr  -> disjoint
   [ 4] 0x20c0000000000000000000003158081efd85bfc2 closure=  6 addr  -> disjoint
   [ 5] 0x20c000000000000000000000c412ec89d0c08be5 closure=  6 addr  -> disjoint
   [ 6] 0x20c00000000000000000000058d0b8b2cfdb358c closure= 14 addr  -> disjoint
   [ 7] 0x20c0000000000000000000006fd9a167923ba194 closure=  4 addr  -> disjoint
   [ 8] 0x20c0000000000000000000001621e21f71cf12fb closure= 13 addr  -> SHARES ['0x00bd5c12508a346e4355c8ee085ae2bcb742e814', '0x69784c33e460ab284b32eea886c2eb5ba8b5aa01', '0x79e2b9c1f6c9ed1375c93aaf139e6c4537f48523', '0xa37b4a8a5538d2f21c4ea8a27db8eda8c6260d1d', '0xc6a38f3da88ff791e296c6e05cd669d22a979e03', '0xf02cc4dc84ac59bd6089baddceb9d4ef3aefb0f0', '0xfd3f88eca6cc5301b6d7068a09dc924ae9dfa3c3']
   [ 9] 0x20c0000000000000000000000520792dcccccccc closure= 11 addr  -> disjoint
   [10] 0x9a044ae05e5e6290dcf56afd69548565e957a626 closure=  5 addr  -> disjoint
   [11] 0x83a1491f3e7f8daab8f787a631334b9ca7a87023 closure=  2 addr  -> disjoint
   [12] 0xc609656ed9ef219c98c8e549bf729144f211f06e closure= 10 addr  -> disjoint
   [13] 0x10ee9aac980a180dd4dcfc96c746d60b0ea88f97 closure= 11 addr  -> disjoint
   OTHER tracked targets sharing >=1 root signer: 1 -> crossExposureScore = 80
   (a disjoint closure is a SUPERSET disjointness proof: no traversal of that target
    reaches any of this target's root signers, so no exact resolution can either)

== 10. published score read from the oracle IN THIS SCRIPT ==
   eth_call 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 getScore(0x20c000000000000000000000b9537d11c60e8b50) on https://rpc.moderato.tempo.xyz
   {
      "adminKeyScore": 65,
      "multisigScore": 98,
      "timelockScore": 0,
      "oracleAuthorityScore": 100,
      "crossExposureScore": 80,
      "compositeScore": 55,
      "lastUpdated": 1789933789,
      "methodologyHash": "0xe653d28506a2817ef2eca397d999966bd56a35d9024e25cdfccbb618d1a3909a"
}

== 11. comparison ==
   adminKeyScore          re-derived=65   published=65   OK
   multisigScore          re-derived=98   published=98   OK
   timelockScore          re-derived=0    published=0    OK
   oracleAuthorityScore   re-derived=100  published=100  OK
   crossExposureScore     re-derived=80   published=80   OK
   compositeScore         re-derived=55   published=55   OK

== VERDICT ==
   index 1 (0x20c000000000000000000000b9537d11c60e8b50): all 6 published dimensions re-derived from the chain, NO DIVERGENCE
```

## Full output, `check_new_targets_live.py` (exit 0)

```
== 1. official Tempo token registry, read live ==
   https://tokenlist.tempo.xyz/list/4217
   name='Tempo Mainnet' version=1.0.34 timestamp=2026-09-10T16:41:24.740Z
   tokens listed: 34

== 2. covered set, read from the oracle on Moderato (not from this repo) ==
   oracle 0x50840a7667baEa9D05ad4ae3dCeb384724b58720 trackedTargetsCount() = 14
   tracked TIP-20 addresses among them: 9
   registry tokens NOT tracked by the oracle: 25

== 3. live totalSupply() of every untracked token, on two providers ==
   senpathUSDE  0x20c000000000000000000000baac91f6ca72f768  totalSupply=      118,450.1057  <== above the weakest covered token  (2026-09-19: 116,422.5000, x1.02)
   BRLA         0x20c000000000000000000000f047dd7018e50367  totalSupply=       50,100.0000  (2026-09-19: 50,100.0000, x1.00)
   GBPA         0x20c0000000000000000000000a6da882d075a4c3  totalSupply=       50,001.0000  (2026-09-19: 50,001.0000, x1.00)
   stcUSD       0x20c0000000000000000000008ee4fcff88888888  totalSupply=       23,869.6000  (2026-09-19: 23,869.6000, x1.00)
   USD1         0x20c000000000000000000000111111111e910f0f  totalSupply=        1,119.8623  (2026-09-19: 1,119.9000, x1.00)
   goUSD        0x20c0000000000000000000006d194f9810e6f886  totalSupply=        1,117.0000  (2026-09-19: 1,117.0000, x1.00)
   syrupUSDC    0x20c0000000000000000000008191667423f70e67  totalSupply=          886.1051  (2026-09-19: 886.1000, x1.00)
   USDY         0x20c000000000000000000000d479b9f6ec0ceff9  totalSupply=          468.8792  (2026-09-19: 468.9000, x1.00)
   reUSD        0x20c000000000000000000000383a23bacb546ab9  totalSupply=          233.7375  (2026-09-19: 233.7000, x1.00)
   MACH         0x20c000000000000000000000f37de3740adec032  totalSupply=          156.2338  (2026-09-19: 156.2000, x1.00)
   CADD         0x20c000000000000000000000d65b4808c85dbb81  totalSupply=           99.0000  (2026-09-19: 99.0000, x1.00)
   SBC          0x20c000000000000000000000ae247a1130450f09  totalSupply=           96.2600  (2026-09-19: 96.3000, x1.00)
   frxUSD       0x20c0000000000000000000003554d28269e0f3c2  totalSupply=           44.5272  (2026-09-19: 44.5000, x1.00)
   EURAU        0x20c0000000000000000000009a4a4b17e0dc6651  totalSupply=           41.0000  (2026-09-19: 41.0000, x1.00)
   USDe         0x20c0000000000000000000002f52d5cc21a3207b  totalSupply=           22.2560  (2026-09-19: 22.3000, x1.00)
   sUSDe        0x20c000000000000000000000bd95bfb69fbe6ce3  totalSupply=            5.5765  (2026-09-19: 5.6000, x1.00)
   YLDS         0x20c0000000000000000000003337951a5a9d94b2  totalSupply=            5.5000  (2026-09-19: 5.5000, x1.00)
   wYLDS        0x20c00000000000000000000030fdd4a919e93fcf  totalSupply=            5.0500  (2026-09-19: 5.1000, x0.99)
   siUSD        0x20c000000000000000000000048c8f36df1c9a4a  totalSupply=            4.0448  (2026-09-19: 4.0000, x1.01)
   wsrUSD       0x20c000000000000000000000aeed2ec36a54d0e5  totalSupply=            3.9386  (2026-09-19: 3.9000, x1.01)
   rUSD         0x20c0000000000000000000007f7ba549dd0251b9  totalSupply=            0.0000  (2026-09-19: 0.0000, x1.00)
   GUSD         0x20c0000000000000000000005c0bac7cef389a11  totalSupply=            0.0000  (2026-09-19: 0.0000, x1.00)
   iUSD         0x20c000000000000000000000ab02d39df30bd17e  totalSupply=            0.0000  (2026-09-19: 0.0000, x1.00)
   CHFAU        0x20c00000000000000000000042109aef2f8b28e1  totalSupply=            0.0000  (2026-09-19: 0.0000, x1.00)
   SEKAU        0x20c0000000000000000000002e2829d90e7da7fa  totalSupply=            0.0000  (2026-09-19: 0.0000, x1.00)

== 3b. live authority read on every untracked token above that bar ==
   senpathUSDE 0x20c000000000000000000000baac91f6ca72f768
     role holders now: {'DEFAULT_ADMIN_ROLE': [], 'ISSUER_ROLE': ['0xd730394f3bb85a4828e35fc5e361dcc9f894fa4f'], 'PAUSE_ROLE': [], 'BURN_BLOCKED_ROLE': []}
     root-control set (R1): ['0xd730394f3bb85a4828e35fc5e361dcc9f894fa4f']
     0xd730394f3bb85a4828e35fc5e361dcc9f894fa4f -> unresolved k=None n=None
     authority closure shares an address with tracked target(s): NONE

== 4. re-scout trigger (data/scouted_bridged_tokens_2026-09-19.md section 5) ==
   registry version (1, 0, 34) vs baseline (1, 0, 34): unchanged
   token count 34 vs baseline 34: unchanged
   untracked tokens up x100 or more since the 2026-09-19 snapshot: none
   (context, not a trigger) untracked tokens above the weakest covered token (50,337.23): ['senpathUSDE']

== VERDICT ==
   0 new targets. Registry unchanged at 1.0.34 / 34 tokens,
   and none of the 25 untracked tokens moved x100 since 2026-09-19.
   See section 3b above for what the live authority read says about the tokens that
   merely sit above the weakest covered token -- that is context for a future scouting
   pass, not a target this maintenance run may add on its own.
```

## Replaying this

```bash
D=$(mktemp -d) && git clone --quiet https://github.com/RealSpap/authority-risk-oracle.git "$D/r"
python3 "$D/r/chains/tempo/scripts/audit_rotation_index.py" 1     # exit 0, "NO DIVERGENCE"
python3 "$D/r/chains/tempo/scripts/check_new_targets_live.py"     # exit 0, "0 new targets"
```

The 36 individual claims behind this report, each a command runnable as-is from any
directory, are in `runs/2026-09-21/tempo/claims_tentative2.txt`.
