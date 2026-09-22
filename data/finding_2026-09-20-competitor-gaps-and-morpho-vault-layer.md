# Finding (2026-09-20): where competitors leave holes the oracle can fill, and one new territory found on the way

Requested directly: "cherche des trous chez les concurrents que l'on pourrait couvrir avec l'Oracle". This is not a
repeat of `finding_2026-09-18-competitive-positioning-cross-chain-overlap.md` (SolGov, Hypernative, Blockaid, Gauntlet,
Chaos Labs, LlamaRisk, DeFiSafety, ERC-8241, L2BEAT). It adds DeFiScan, Foreshock, Webacy, Exponential, Credora and
B.Protocol, and corrects two claims made earlier in this pass. Pure research plus one read-only scouting script; no
scorer, contract or on-chain state is changed by this document.

## Corrections first

- A "vault guard" consumer contract was proposed earlier today. `src/ExampleConsumer.sol` already does that job
  (`collateralFactorBps(target)`, `StaleScore(target)`), so it is not a gap and is dropped.
- "No one ships contract-callable ratings" is too strong. Credora (acquired by RedStone) rates vaults and lending
  markets A+ to D and, per RedStone's announcement, flows the ratings through oracle infrastructure to Morpho and Spark
  markets. That is on-chain delivery, for credit and market risk. The claim that survives is narrower: nobody was found
  delivering AUTHORITY risk (thresholds, delays, signers) on-chain.

## The market in three layers (what each source itself says)

| Layer | Who | What it gives | Where it stops (verified unless marked) |
|---|---|---|---|
| Facts | [DeFiScan](https://defiscan.info), ERC-8241 | Who controls what, per protocol | DeFiScan gallery filters: ecosystems BNB Chain, Base, Ethereum only; types dex, lending, liquid-staking, stablecoin, yield; about 20 listings; "no proprietary scores". Its Aave page lists Horizon's two Safes separately and I found no mention of their 3 shared signers (collapsed sections not opened). |
| Ratings, off-chain | [Webacy](https://www.webacy.com/blog/how-digital-asset-ratings-work-the-infrastructure-behind-onchain-risk-intelligence), Exponential, [Foreshock](https://foreshock.tech/), DeFiSafety | Letter or 0-100 grades, alerts | Webacy's governance signal is categorical flags ("EOA owner", "upgradeability without a timelock"): no signer threshold, delay length or signer identity disclosed; delivered by dashboard and REST API, not on-chain ([Arbitrum docs](https://docs.arbitrum.io/for-devs/third-party-docs/Webacy)). Foreshock: email alerts, CSV/JSON export, from $59 per month for 10 protocols, no on-chain output, chains not stated. Exponential: claims 8,000+ protocols (search snippet only, its page now redirects to yo.xyz/risk which returned HTTP 429). |
| Ratings, on-chain | Credora/RedStone, Chaos Labs Edge Risk Oracle, LlamaGuard, [B.Protocol](https://docs.bprotocol.org/risk-oracle) | Contract-readable notes | All measure credit or market risk. B.Protocol's six dimensions (liquidation exposure, bad debt, risky listings, caps, contract recency, price-oracle quality) include no governance or multisig; its design says a strategy contract "can even be coded to pull out funds" when a rating drops, which is this oracle's consumer pattern (liveness of B.Protocol not verified). |

De.Fi Scanner (a "Governance" tab and a "DeFi Score") was seen only in a search snippet; its page did not load. Treat as
unverified.

**Defensible position:** layer 3 for authority risk, with the depth layer 2 discloses only as flags (threshold, delay,
signers) and the cross-target signer overlap no source was found to compute.

## Holes the oracle already fills (positioning, no work needed)

1. DeFiScan lists three ecosystems; 132 of the 160 on-chain targets (Robinhood Chain 58, Solana 18, Hyperliquid 15,
   Tempo 14, Arbitrum 9, Plasma 9, Monad 9) plus Zcash's 7 sit on chains it does not list.
2. Ethereum heavyweights absent from its 20 listings and scored here: Morpho Blue, Sky/Maker, Curve, EigenLayer,
   Rocket Pool, Uniswap V4.
3. No score by design (DeFiScan), email-only (Foreshock), flags-only (Webacy): nothing a contract can read.

## Negative result

Compound V3's three Ethereum markets (cUSDCv3, cUSDTv3, cWETHv3) share one `governor()` and one `pauseGuardian()`
(read on-chain, `governor` 0x6d90..., `pauseGuardian` 0xbbf3...). Tracking only cUSDCv3 loses no authority information.

## New territory: the Morpho vault layer on Ethereum and Base

Users of Morpho deposit into curator-run vaults, and each vault has its own owner, curator, guardian and timelocks.
This oracle scores Morpho Blue's owner (fees and new markets only) and a few vaults on Monad and Robinhood Chain, and
none on Ethereum or Base. DeFiScan lists five vaults one by one. Two Morpho vault generations exist: V1 (MetaMorpho) and
V2, and V2 holds more (about $4.7B for vaults of $1M or more, against about $2.0B for V1 vaults of $2M or more).

Method, all read-only: vault lists from Morpho's public API (an indexer, not trusted for values), then every owner,
curator, guardian, timelock and V2 per-function timelock re-read on-chain, on two RPCs where a conclusion rests on it.
`chains/ethereum-l1/scripts/scout_morpho_vaults.py` (roles and signer overlap of the 40 largest V1 vaults) and
`chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py` (owner type of 153 vaults, V1 and V2, $5.71B).

### Concentration only a cross-vault comparison shows

| Controller | Vaults | Deposits | Signers |
|---|---|---|---|
| Steakhouse, same owner Safe address on both chains (V1) | 8 on Ethereum + 3 on Base | about $450M | owner 5-of-10 / 5-of-9, curator 2-of-7 / 2-of-6, sharing 6 to 7 signers with the owner Safe |
| Gauntlet (V1 and V2) | 11 on Ethereum + 2 on Base (V1) | about $546M | owner 4-of-7, curator 3-of-7, guardian 3-of-7, and **all three Safes share the same 7 signers**, on both chains |
| Yearn (V1) | 5 on Ethereum | about $35M | owner 4-of-7, curator 2-of-3, guardian 6-of-9 (3 modules), one shared signer: a real separation |

The guardian exists to veto what the owner and curator queue. For Gauntlet the same seven people hold all three roles,
so that separation is nominal. It is invisible in a per-vault review. (The Monad vault scorer already flags the same
collapse for one vault, `score_morpho_vault_monad`; the new part is seeing it across vaults and chains.)

### Who owns the vaults (153 vaults, on-chain, split by Morpho's own `listed` flag)

| Group | Vaults | Deposits | Owner is a single key (EOA, EIP-7702 EOA, or a 1-of-1 Safe with an EOA signer) |
|---|---|---|---|
| Listed on Morpho (shown in its app) | 126 | $5.04B | 17 vaults, $1,203M, 24% |
| Not listed (hidden by Morpho, many with red warnings) | 27 | $0.68B | 10 vaults, $513M, 76% |

Listed single-key owners: Sentora's Vault V2 family, **$1,069M over 6 vaults behind one 1-of-1 Safe** (signer an EOA;
its curator is also a 1-of-1 Safe), then Galaxy, Bitwise, Flowdesk and Keyrock V2 vaults of $8M to $24M each.

### What a single-key owner can and cannot do in Vault V2 (verified from the vault's own source and on-chain)

The V2 source states the model: "The owner cannot do actions that can directly hurt depositors. Though it can set the
curator and sentinels. The curator cannot do actions that can directly hurt depositors without going through a timelock."
On-chain, for Sentora's PayPal USD Main, RLUSD Main and PRIME Main (and Steakhouse Prime USDC on Ethereum and Base):

- Timelocked: `addAdapter` 3 days, `removeAdapter` 7, `increaseAbsoluteCap` 3, `increaseRelativeCap` 3,
  `increaseTimelock` 7, `abdicate` 7.
- Permanently disabled (abdicated): the receive-assets, send-shares and receive-shares gates and `setAdapterRegistry`.
  The source says the first two "can lock users out of exiting the vault", so exit cannot be gated in these vaults.
- **Timelock 0, not abdicated**: `setIsAllocator`, `setManagementFee`, `setPerformanceFee` and the two fee-recipient
  setters, `setForceDeallocatePenalty` and (Sentora, Sky) `setSendAssetsGate`, which only gates deposits. (The stored
  timelock of `decreaseTimelock` also reads 0 on every vault, but that is by design and not a hole: `submit` delays it
  by the timelock of the function being decreased, so shortening `addAdapter`'s 7 days itself takes 7 days.)
  An allocator can move funds only among existing markets within caps and can set the liquidity adapter, which can hinder
  deposits or withdrawals but not in-kind `forceDeallocate` exits.
- Gauntlet's V2 vaults are stricter on the same functions: `setIsAllocator` 7 days, fees 3 days.

So a single-key V2 owner is real concentration of governance, but the actions that reach principal wait 3 to 7 days and the
exit gates are switched off for good. The protection is the delay plus someone watching the queue of pending submissions.
That heterogeneity (same protocol, very different delays per curator) is a scorable dimension that a categorical flag
such as Webacy's "upgradeability without a timelock" does not capture.

### Retraction: 1337 USDC and Adpend USDC are not live drain risks

The first version of this note presented 1337 USDC ($173M, bare-EOA owner, timelock 0) and Adpend USDC ($325M,
EIP-7702 EOA owner) as live single-key exposures and called for a disclosure decision. That was wrong. Morpho's own API
marks both as **not listed**, with red warnings (1337: `short_timelock`, `oracle_unusable`; Adpend: `deposit_disabled`,
`oracle_unusable`), and their allocation is entirely in a single sdeUSD-collateral market ($173.1M and $324.6M). These
look like legacy or impaired vaults whose deposits sit in a defunct market, not vaults where new depositors are
exposed to a key. `totalAssets` is a nominal figure, not a measure of what could be withdrawn. By the vault's own source
(MetaMorphoV1_1) a timelock of 0 would let the owner add a market and accept it at once, but that says little when the
funds are already in one illiquid market. No disclosure is warranted on this evidence, and Morpho already flags them.

### The other chains (same sweep, vaults of $250k or more)

`python3 chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py --chains 4663,143,42161,999,4217,988,10,480,130,137 --min 250000`
reads Robinhood Chain, Monad, Arbitrum, HyperEVM, Tempo, Stable, OP, World Chain, Polygon and Unichain. Arc (RPC
`rpc.mainnet.arc.io`, chain id 5042 confirmed) and Katana (`rpc.katana.network`, 747474, reached with curl because this
Python's TLS library cannot) were added in a later pass: `--chains 5042,747474`.

| Chain | Vaults | Deposits | Listed vaults with a single-key owner | Not listed |
|---|---|---|---|---|
| **Arc** | 3 | $152M | **3 ($152M): Galaxy USDC $77M, Keyrock Prime USDC $75M, Galaxy EURC $1M, all bare EOAs** | 0 |
| Robinhood Chain | 3 | $513M | 0 | 2 ($26M) |
| Monad | 7 | $111M | 1 ($12M, a bare EOA: August USDC V2) | 0 |
| HyperEVM | 16 | $69M | 1 ($13M, K3 USDC, a 1-of-1 Safe) | 5 ($14M) |
| Tempo | 3 | $50M | 1 ($36M, Sentora pathUSD, a 1-of-1 Safe) | 1 ($14M) |
| Katana | 10 | $22M | 0 | 0 |
| World Chain, Stable, Arbitrum, OP, Polygon, Unichain | 21 | $80M | 0 | 7 ($36M) |

Across these chains 6 of 48 listed vaults ($213M, 24%) have a single-key owner, the same share as on Ethereum and Base. An
earlier version of this note said 8% because Arc was unread; Arc alone is $152M of it. On Arc, **both the owner and the
curator of all three vaults are bare EOAs** (Vault V2, read on-chain): fund-moving actions wait 7 days (Galaxy EURC:
`setIsAllocator` and fees 3 days), the receive-assets and send-shares gates are abdicated, and `setIsAllocator`, fees and
the force-deallocate penalty sit at timelock 0 on Galaxy USDC and Keyrock Prime USDC. Arc's mainnet opened on 2026-09-16, so
these vaults are days old. The same Sentora single-signer pattern appears on Tempo. Robinhood Chain's flagship (Steakhouse
USDG, $488M) is owned by a bespoke 8,609-byte contract, not a Safe.

### How much of this the oracle covers today (a gap in the repo, and one wrong claim)

Matching every vault found against the addresses our scorers reference: Robinhood Chain's 3 vaults ($514M, 100%) are
tracked, and **no other vault of the roughly $6.2B found on the other 13 chains is** ($3.63B Ethereum, $2.10B Base, then
Arc, Monad, HyperEVM, Tempo and the rest), so about 8% of the Morpho vault deposits found sit under a tracked target.
Address-literal matching could miss a vault referenced some other way.

`score_morpho_vault_monad` documents "the largest MetaMorpho vault on Monad mainnet by TVL", $108K, "the largest of only
26 vaults". The tracked vault (`0x32841A85...476D`, Grove x Steakhouse High Yield AUSD) is a V1 vault created 2025-11-26
with $0.108M today. Monad's six Vault V2 vaults, all created between January and July 2026, hold $110M (Steakhouse Prime
ETH $47.4M, Hyperithm USDC Apex $39.8M, August USDC V2 $11.7M). The claim holds only if V2 vaults are left out, so the
docstring should say V1, and Monad's Morpho exposure is about a thousand times larger than what is tracked.

## Not verified

- Which of the listed single-key V2 owners is a person, a custodian or an MPC: the signers are only "an EOA".
- Owner contracts of 2,085, 8,210 and 16,415 bytes (Spark, Steakhouse V2, others, about $2.0B) were not analysed.
- Whether sdeUSD-market vaults hold recoverable value (not analysed; irrelevant to the authority score).
- Deposits are the API's figures except where stated. One vault (Pangolins USDC, Base) returned disagreeing RPC answers
  in the first pass and is out of every conclusion.
- Signer overlap says the same keys appear, not that one person controls them or that a key is insecure.

## Improvement backlog this suggests (ranked, none started)

1. **Scorers for the largest listed vaults, starting with Monad's V2 vaults and the Ethereum and Base ones**, using what actually differentiates them: per-function
   timelocks (fund-moving actions and the timelock-0 list), abdicated gates, and the signers behind owner, curator and
   guardian. `score_morpho_vault_generic` (V2) already reads curator, owner and authority-selector timelocks; it does not
   read abdications or role-signer overlap. New targets on the Ethereum L1 and Base oracles need a push by Spap.
2. **A market-scale role-separation signal**: owner, curator and guardian signer overlap across a controller's vaults
   (Gauntlet's shared 7 signers; Sentora's single-signer Safes).
3. **A queue monitor for V2 `submit` events.** The 3 and 7 day windows are the protection, so a watcher that sees a
   pending `addAdapter` or cap increase is the natural monitoring feature (DeFiScan advertises 24/7 monitoring, which is
   where it is ahead today).
4. **A drift monitor** across the nine oracles (scorer versus on-chain values).
5. **Distribution through an existing rating channel** (Credora's ratings already reach Morpho curators through
   RedStone). Hypothesis only, nothing was checked with either party.
