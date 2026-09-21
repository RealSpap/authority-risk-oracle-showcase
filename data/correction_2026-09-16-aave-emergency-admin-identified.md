# Correction: Aave V3 Ethereum's EMERGENCY_ADMIN_ROLE holder identified (2026-09-16)

## What this corrects

`chains/ethereum-l1/scorers.py`'s `score_aave_v3_pool()` originally shipped
(commit `4d74261`, same day) with an explicitly disclosed open gap: the
ACLManager's `EMERGENCY_ADMIN_ROLE` holder was checked and not identified --
`GOVERNANCE_GUARDIAN`-style probing failed, the ACLManager has no enumerable
role list (confirmed by reading Aave's own `ACLManager.sol` source: it extends
plain OpenZeppelin `AccessControl`, not `AccessControlEnumerable`), and a full
`RoleGranted` event replay from deployment (~9.7M blocks) hit archive-node
restrictions or block-range caps on every free public RPC tried
(publicnode, ankr, llamarpc, blastapi, 1rpc, drpc -- all either required a
paid archive tier or capped `eth_getLogs` ranges too small to be practical:
10-50 blocks per call on several, 10,000 on drpc's free tier).

## How it was resolved

Source-first instead of brute-force event replay: `bgd-labs/aave-address-book`
(the actively-maintained address registry Aave's own governance payloads
import) defines `PROTOCOL_GUARDIAN` in `src/MiscEthereum.sol`:

```solidity
// https://etherscan.io/address/0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30
address internal constant PROTOCOL_GUARDIAN = 0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30;
```

This was cross-checked LIVE, not trusted from the docs alone:
`ACLManager.isEmergencyAdmin(PROTOCOL_GUARDIAN)` returns `true`, confirmed on
2 independent RPCs (`ethereum-rpc.publicnode.com`, `eth.drpc.org`).
`PROTOCOL_GUARDIAN` is a real, live Gnosis Safe: **4-of-7**
(`getOwners()`/`getThreshold()` re-derived directly, not assumed).

**A real historical wrinkle, not a research error**: a 2023 governance payload
(`bgd-labs/aave-v3-ethereum-proposal`'s `AaveV3EthereumInitialPayload.sol`)
originally granted this role to a *different* address, `GUARDIAN_ETHEREUM`
(`0xCA76Ebd8617a03126B6FB84F9b1c1A0fB71C2633`, itself a real 5-of-10 Safe) --
`ACL_MANAGER.addEmergencyAdmin(GUARDIAN_ETHEREUM)` after revoking it from the
DAO's own Short Executor. Re-checked live: `isEmergencyAdmin(GUARDIAN_ETHEREUM)`
now reads **false** on both RPCs above. The role moved from the 2023 address to
`PROTOCOL_GUARDIAN` at some point since -- the frozen 2023 proposal repo is a
historical record, not current state, and was correctly NOT trusted as such.

## Score change

| Field | Before (commit `4d74261`) | After | Why |
|---|---|---|---|
| `adminKeyScore` | 70 | 78 | The previously-unknown emergency seat is now confirmed a real, reasonably-composed 4-of-7 Safe rather than an open unknown -- a modest improvement, not full marks, since 4-of-7 zero-delay authority is still a real concentration by design. |
| `timelockScore` | 55 | 55 (unchanged) | The emergency seat still structurally bypasses the PayloadsController's 1-day timelock entirely -- that bypass is a design fact independent of who holds the seat, so identifying the holder doesn't remove it. |
| `compositeScore` | 75 | 78 | `floor(0.4*78 + 0.3*100 + 0.3*55 + 0.5)` |

Both DAO executor (`isPoolAdmin=true`, `isEmergencyAdmin=false`) and
`PROTOCOL_GUARDIAN` (`isEmergencyAdmin=true`) re-verified live in the same
pass -- confirms the emergency seat really is separate from routine DAO
governance, not merely assumed.

## Not yet done

`PROTOCOL_GUARDIAN`'s 7 signers were not cross-checked against any other
tracked Ethereum L1 target for shared-key overlap -- `chains/ethereum-l1/`
does not yet have a `signer_overlap.py`/`GROUPS`-style cross-exposure registry
the way Robinhood Chain's `scripts/lib/signer_overlap.py` does. Worth building
once Ethereum L1 has enough tracked targets with Safe-rooted authority to make
a cross-exposure check meaningful (currently 2 of 4: Aave here, and Ethena's
5-of-10 Safe).
