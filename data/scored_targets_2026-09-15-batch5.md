# Scored targets - batch 5, 2026-09-15

Four more scores pushed (tx
[`0x8d2b4a82...`](https://explorer.testnet.chain.robinhood.com/tx/0x8d2b4a82284960dbf0834cc39e5c3e209377a03506c0058ae3e6afe702edead0)),
bringing the total to **32 targets**. This batch closes out two of the four
candidates left honestly unresolved in batch 4, and deepens the confidence behind
the single most consequential finding of the whole project.

## Correction: the L1 rollup Safe's signers are not anonymous

Batch 4 flagged "signer identities not yet established" for the 7-of-8 Safe
(`0x7ae50886...`) holding `EXECUTOR_ROLE` on Robinhood Chain's L1 upgrade authority.
That framing was imprecise. Robinhood's own governance docs
(`docs.robinhood.com/chain/governance/`), independently corroborated by L2BEAT's
Discovery-based permissions data for this exact chain, name the Security Council
explicitly: **Robinhood (2 seats), BitGo Inc., Chainlink Labs, Fireblocks Trust
Company, Offchain Labs, Paxos, and Talos** -- a named, public, credentialed group,
not an anonymous signer set. Routine actions need 6-of-8 plus the 7-day timelock;
emergency actions need 7-of-8 and bypass it -- exactly matching the on-chain finding
that the 7-of-8 Safe holds direct, undelayed `EXECUTOR_ROLE`.

What remains genuinely unresolved: no public source maps any *specific* one of the
8 addresses to a *specific* named institution (checked and came up empty: Etherscan
public tags, ENS reverse resolution on 2 RPCs, L2BEAT's own labels, general web
search). **New detail this pass also found**: one of the 8 "owner" seats
(`0x0fc5c640...`) is itself a nested 3-of-7 Gnosis Safe, not a single key --
independently confirmed on-chain (`getOwners()`/`getThreshold()`, cross-checked
against L2BEAT). The real distribution is broader than "7-of-8 individual keys"
suggests.

## Ekubo Core - 100/100, the first perfect score on this project

`0x00000000000014aA86C5d3c41765bb24e11bd701`, ~$1.92M chain TVL. Previously flagged
unresolved (batch 4) because `owner()`/`admin()`/5 other plausible selectors all
reverted. This pass confirmed **why**, three independent ways:

1. **Source** (`github.com/EkuboProtocol/evm-contracts`, `Core.sol`/`ICore.sol`):
   zero authority concepts (`owner`/`admin`/`upgrade`/`governor`) anywhere in the
   18-function external interface. No constructor logic beyond storage, explicit
   anti-self-delegatecall documentation.
2. **Official docs** (`docs.ekubo.org`): stated explicitly -- "on EVM it is
   ownerless -- there is no privileged account at all," contrasted directly against
   Ekubo's Starknet Core, which *is* owner-upgradeable.
3. **On-chain differential test, independently re-run**: `owner()` and a
   deliberately fake selector (`0xdeadbeef`) both revert with **identical empty
   data** (`0x`) -- while a real function on the same contract
   (`swap_6269342730()`) reverts with **real, decoded error data**
   (`InvalidSqrtRatioLimit`). This proves the dispatcher routes correctly and that
   the 9 "authority" selectors tried genuinely don't exist as functions, rather
   than existing and reverting for some other reason.

No admin key, no multisig, no timelock gap -- because there's no authority surface
at all to attack. Scored `adminKeyScore=100`, `multisigScore=100`,
`timelockScore=100` (all three dimensions maximally safe by architecture, not
"not applicable") -- composite **100**, ahead of the L1 rollup authority's 57 as
the best score on the whole project. An ownerless, immutable core genuinely beats
even a well-governed 7-of-8 multisig.

**Adjacent, not scored this pass**: Ekubo's Positions contract (the NFT position
manager LPs actually interact with, `0x02D9876A21AF7545f8632C3af76eC90b5ad4b66D`)
*does* have a real `Ownable` owner -- traced to an EIP-7702 delegation to Uniswap's
audited Calibur smart-wallet singleton with zero additional signer keys registered,
i.e. still single-key custody underneath. Its power is narrow (skim accrued
protocol fees, edit NFT metadata; the fee rate itself is immutable, no LP-principal
access) -- flagged as a separate future target given its different risk profile
from Core, not folded into Core's score.

## Longbow - Core, Frontier, ETH vaults - 33/100 each

`0x026df18f...5Ca1` (Core), `0x65dC90cd...78F7` (Frontier), `0xe129D4Cb...5f61`
(ETH). A Morpho-based lender with $3.83M chain TVL that turned out invisible to
Morpho's own `vaultV2s` API (Longbow creates 55 isolated markets directly on the
shared Morpho Blue singleton -- TVL is computed market-by-market, not vault-by-vault,
confirmed via DefiLlama's actual adapter source). Resolved instead via Longbow's own
live production API (`longbow.cash/api/v2/vaults`), every address independently
verified on-chain on 2 RPCs before use.

**Methodology catch worth noting**: Longbow's own static JS bundle also embeds a
fourth address as a stale SSR fallback ("Longbow USDG Core") that resolves to a
real, different VaultV2 contract -- but isn't one the live API actually serves.
Discarded as a decoy rather than scored, exactly the kind of secondhand trap this
project's "never trust a single source" standard exists to catch.

**Authority, identical across all three vaults**: `owner()` and `curator()` resolve
to two *separately deployed* Gnosis Safe contracts -- independently confirmed --
but with the **identical 3 owners and identical 2-of-3 threshold**. Two Safe
addresses, one governing group; curator and owner are not actually separated.
`setOwner`/`setCurator`/`setIsSentinel` timelocks confirmed at **0** on all three
vaults (the same chain-wide gap already found on every other Morpho vault scored),
while `addAdapter` (3 days) and `removeAdapter` (7 days) carry a real delay that
doesn't cover what matters. Scored below Purinta (38, two genuinely distinct
Safes) and Ethena x Steakhouse (44, a real 5-of-10), above NetNet Credit (8, a
1-of-1) and Steakhouse (19, a bare EOA two hops down) -- reflecting a real but thin
3-person, 2-of-3 group with no separation of duties between the two roles that are
supposed to check each other.

## Running total

32 targets scored across 5 batches. Range: 1/100 (Robinhood's own stock-token
beacon) to **100/100 (Ekubo Core, verified ownerless)**. Two of batch 4's six
unresolved candidates closed this pass (Longbow, Ekubo); four remain open
(PancakeSwap, SushiSwap, Pendle, Symbiosis, Curve DEX, STRATO Bridge -- no address
found yet for any).
