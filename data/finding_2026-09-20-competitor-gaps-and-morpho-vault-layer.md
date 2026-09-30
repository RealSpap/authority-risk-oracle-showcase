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

### Euler Earn (a fork of MetaMorpho V1), read the same way

`python3 chains/ethereum-l1/scripts/sweep_euler_earn.py`. Vaults are enumerated on-chain from Euler's factories (addresses
from Euler's own `euler-interfaces` registry; the old subgraphs are decommissioned), roles re-read with `eth_call`, deposits
priced with DefiLlama, and "verified" is the factory perspective's `isVerified`. 162 vaults on 11 chains, but only 17 hold
$250k or more ($238M in total), and 14 vaults hold an asset with no DefiLlama price, so their deposits are unknown. It is a
much smaller market than Morpho's, with its largest blocks on Plasma ($113M) and Monad ($103M), where this oracle is
deployed.

| Among the 17 vaults of $250k or more | Vaults | Deposits |
|---|---|---|
| Owner is a Safe with a threshold of 1 (any one signer acts): 1-of-2 (three vaults) and 1-of-3 (one) | 4 | $96.4M (40%) |
| Owner is a bare EOA | 2 | $6.2M |
| No guardian | 10 | $137M |
| Timelock 0 | 1 | $3.7M |

The two largest Monad vaults ($68.9M and $23.0M) share one owner Safe, `0x060DB084...`, with a threshold of 1 out of 2,
a 24-hour timelock and a guardian. The same Safe address owns vaults on BSC, HyperEVM, Base, Plasma and Ethereum.

### Controllers across vaults, chains and families

`python3 chains/ethereum-l1/scripts/analyze_controllers.py morpho_rows.json euler_rows.json` groups every owner and curator
address (dumps from the two sweeps with `--dump`). 381 listed or verified vaults, $6.22B, 178 distinct owner or curator
addresses.

- **Two curator Safes govern almost half of the curated deposits.** Steakhouse's curator Safe `0x827e8607...` (2-of-6 on
  Base, 2-of-7 on Ethereum) is the curator of 42 vaults, $1.84B, on 5 chains. Gauntlet's curator Safe `0x9E33faAE...`
  (3-of-7) is the curator of 46 vaults, $942M, on 8 chains. Together $2.78B of the $6.10B of deposits that have a curator
  (46%), a threshold of 2 or 3 signatures each.
- **Sentora: one entity, two single-signer Safes, two different keys.** The owner Safe (`0xe8C9C99E...`, signer
  `0x295Df6B7...`) and the curator Safe (`0x9e396dE3...`, signer `0x992592e0...`) are each 1-of-1 with a different active
  EOA (nonces 326 and 305). The same two addresses control 6 vaults, $1,104M, on Ethereum and Tempo. So the roles are
  separated, but each role is one key.
- **Institutional curators use bare-EOA pairs.** Galaxy: an owner EOA and a curator EOA on Ethereum and Base (5 vaults,
  $77M), a different EOA pair on Arc (2 vaults, $77M). Keyrock (Arc, $75M), Bitwise ($22M), Flowdesk ($13M) and August
  ($12M) follow the same pattern. Across all families the curator is a single key for $1.50B of the $6.10B (25%).
- **One curator EOA spans three families and four chains.** `0x75178137...` (Hyperithm, Apyx, Saturn vault names) is the
  curator of 13 vaults, $81M, on Ethereum, Monad, Plasma and Arbitrum, across Euler Earn, Morpho V1 and Morpho V2, with a
  2-of-3 Safe (`0xee7e9bb2...`) as owner. This is a cross-protocol signer reuse of the kind this oracle exists to surface.

Caveat for every "same address on several chains" line: an EOA is the same key everywhere, but a Safe at the same address
can have different signers per chain (Steakhouse's owner Safe is 5-of-10 on Ethereum and 5-of-9 on Base). Deposits are the
vaults' own figures (API for Morpho, DefiLlama-priced `totalAssets` for Euler), listed or verified vaults only.

### Demand signals and the agent-side competitor (second pass)

- **An explicit demand from a governance framework.** Aave's four-layer risk framework, prepared by LlamaRisk in June 2026
  and binding across V3, V4 and Horizon, is reported by
  [The Defiant](https://thedefiant.io/news/defi/aave-proposes-protocol-wide-risk-framework-after-kelpdao-exploit),
  [Unchained](https://unchainedcrypto.com/aave-proposes-binding-new-risk-framework-following-the-292-million-kelpdao-exploit/)
  and [The Block](https://www.theblock.co/post/404136/new-aave-risk-framework-proposed-following-kelpdao-exploit). Undisclosed signer
  structures and no timelocks on critical upgrade paths are hard-block conditions, and Layer 3 covers "monitoring and
  automated risk oracle systems". This is the closest thing found to a written requirement for what this oracle does.
- **An agent-side tool exists and is shallow.** VaultPilot MCP (`agenthill/vaultpilot-mcp`, 4 stars and 2 forks when read)
  exposes `check_permission_risks` and `get_protocol_risk_score` to AI agents. Read from its source on main:
  `checkPermissionRisks` reads `owner()` only, classifies the holder as EOA or contract, sets `isMultisig` from
  `getThreshold() > 0` (a Safe is detected, its threshold and signers are not kept) and reads a timelock delay from
  `getMinDelay()` or `delay()`; the code says role enumeration for AccessControl contracts is "not implemented in MVP".
  `getProtocolRiskScore` is built from DefiLlama TVL, a 30-day trend, contract age, a hard-coded bounty table and an audit
  count, with no authority component at all. So the need for a pre-transaction authority check is being met by someone,
  at one hop of depth. An MCP tool that reads this oracle is a hypothesis for distribution to agents, nothing was built or
  discussed with them.
- **Negative result.** A search for a DAO grant or RFP naming signer monitoring or admin-key tooling found none. That is
  not evidence that none exists.
- Search snippets on the 2026 incidents (a Stake DAO deployer-key mint, Drift) and on DeFi insurance pricing were not
  re-read and are not used as evidence here.

### Who else requires it, and who is paid for it (third pass)

- **Morpho.** Its public Listing Policy governs which vaults and curators the Apps display, and the interface shows RED
  warnings for a vault or curator that does not fit the criteria. In the API those warnings include `short_timelock`, `timelock`,
  `oracle_unusable`, `deposit_disabled` and `not_whitelisted`, so a timelock criterion is enforced in production. Its docs
  recommend a multisig as the initial owner. I did not find a signer-disclosure requirement in what I read, and I did not
  read the Listing Policy text itself.
- **Euler and Spark were not checked.** Whether they impose signer disclosure is unknown.
- **Aave.** The Horizon onboarding update requires a business case, a LlamaRisk risk assessment and an Aave Labs technical
  assessment; the extract mentions no admin-key or signer disclosure (that requirement sits in the June 2026 framework above).
- **The paid market is real, and its scope is market risk.** The Aave governance thread renewing LlamaRisk as risk service
  provider (epoch 4, submitted April 2025) lists, by an extraction I did not cross-check, $3.5M for one year ($1.5M in GHO
  up front, $1.5M in GHO streamed, 5,000 AAVE streamed). The scope named there is risk-managed price feeds, parameter
  automation, Risk Steward co-ownership, oracle design, payload review, monitoring and "Guardian signer duties"; it does not
  enumerate a signer or multisig verification deliverable. An earlier renewal (proposal 185) was $400,000 for six months.
  Chaos Labs reportedly left a $5M retention in April 2026 (bex.co headline, not re-read).
- **Reading, as a hypothesis.** Authority risk is a hard-block condition in the framework but does not appear as a priced
  deliverable in the extract, so the plausible buyer is a risk provider that needs an independent, continuously updated
  input for its listing due diligence, more than a DAO buying a dashboard. Nobody was asked.

### The listing criteria are written but not measured (fourth pass)

- **Morpho's Interface Listing Policy** (read in full, [docs.morpho.org](https://docs.morpho.org/get-started/resources/interface-listing-policy/))
  asks for "a sound owner/curator/guardian address architecture, appropriate use of multisig" and "no unmitigated single
  points of failure", an identifiable curator with a checkable track record, official factories, the official adapter
  registry with the ability to change it abdicated, and "the applicable timelock minimums on sensitive functions" or those
  functions permanently disabled. It gives no timelock value, does not say whether a multisig is mandatory, sets no signer
  count and requires no identity disclosure. Its separate security-considerations page recommends only a 3-day timelock for
  adding markets. My sweep found 17 listed vaults ($1,203M, 24%) with a single-key owner on Ethereum and Base; whether that is an
  "unmitigated single point of failure" is exactly the judgement an independent measure would inform (V2 timelocks and
  abdicated exit gates mitigate it, see above). This is a criterion with no metric, not a finding that any vault breaks it.
- **Euler Earn.** Its docs say a governed "perspective" has a governor who can add or remove vaults "according to whatever
  criteria they desire", and that the initial timelock may be 0 or 24 hours to 2 weeks. No published authority criterion
  was found (search extract, docs page not read in full).
- **Spark.** A search found governance-based review by a Spark Risk Council and no published authority criterion.
- **The assessors are also operators.** Gauntlet was a DAO risk consultant and has moved into vault curation (a July 2026
  Fortune headline reports a $125M raise, not re-read); in this sweep its curator Safe governs 46 vaults and $942M. DefiLlama's
  "Risk Curators" category is reported at $9.2B across 61 protocols. When the firms that write listing due diligence also run the
  vaults being listed, an independent, on-chain authority measure has a structural reason to exist.

### Who rates curators and vault controllers today, and how a score would be consumed (fifth pass)

- **Credora (RedStone).** Its Morpho vault rating looks at "the Curator's Morpho experience and track record, as well depositor
  protection configurations, including guardians and time locks" (Morpho forum post). It does not mention owner or curator
  addresses, multisig thresholds, signer identities or role separation. Ratings are shown on Morpho with the curator's
  approval, so a rated vault is one whose curator opted in. Steakhouse cites "5 of 6 A+" ratings on its own page.
- **DIA DeFi Vault Map** (an oracle provider's dashboard). Its depth is measured in the sixth pass below: labels per pool, no
  addresses and no signers.
- **Curators' own disclosures.** Steakhouse's page states an owner "Safe multisig with a quorum of five keys", a monitor on
  permission changes and "7-day timelocks (above the minimum, protocol-enforced 3-day timelock)". It does not name signers,
  describe the curator role or give per-vault timelocks. On-chain: the owner Safe is 5-of-10 on Ethereum and 5-of-9 on Base,
  which fits; the timelock is not uniform: the Base V2 Prime USDC vault ($427M) reads 3 days for `addAdapter` and cap
  increases, and the two Smokehouse V1 vaults (about $37M) read 3 days, while the Ethereum Prime USDC vault reads 7 days. The
  page's statement is general, so this is not a claim that it is false, but it shows a published claim that a continuous
  check would compare with the chain.
- **No cross-curator rating of signers found.** Curators publish their own methodologies; no platform found rates owner,
  curator and guardian signers across curators.
- **How a score is consumed today.** Press summaries say Credora's integrations "will let Morpho and Spark ingest dynamic scores
  to inform credit decisions and automated controls", carried by the same oracle infrastructure as prices, and that rated
  Morpho vaults grew up to 25% faster than unrated peers (a press claim, and rated vaults are opt-in). Aave's Risk Stewards take
  parameter updates pushed by risk providers' oracles. So the consumption channel in use is a push through an existing oracle
  network, not a contract polling a new provider. As a hypothesis, an authority score would reach consumers by riding an
  existing feed (RedStone, DIA, Chainlink CRE) rather than by asking each protocol to integrate a new oracle.

### DIA's depth measured, and three presentation functions worth imitating (sixth pass, 20 Sep)

**DIA DeFi Vault Map, measured.** The Governance Data page fills its table from a public GET the page itself calls,
`diadata.org/map/api/risk-scanner/?page=N&limit=50&sortBy=tvl_usd&sortDir=desc`; I read all 105 pages (5,244 rows, read only).
- Rows are DefiLlama pools ("Powered by DeFiLlama"), not vault addresses. Fields: `owner_type`, `multisig_threshold`,
  `multisig_owner_count`, `timelock_delay_seconds`, `guardian_type`, `is_proxy`, oracle provider/stale/hardcoded/pair,
  `concentration_risk`, `holder_count`, `max_drawdown_pct`, fee, utilization. **No contract address, no signer address, no role
  address, no history.** There is no per-vault page: `/governance/<slug>` redirects to the map's front page.
- Coverage: `owner_type` empty on 1,791 rows (34%), "unknown" on 684 (13%), read on 2,769 (53%); a multisig threshold on
  1,064 (20%); a timelock on 236 (4.5%). Its own summary block says 14% multisig, 8% EOA, 6% timelock, 24% guardian.
- Curators: the 98 rows carrying a curator or Yearn name (Yearn 84, Sentora Curator 6, Gauntlet 4, Steakhouse 3, yearn-v3 1)
  read "unknown" on 69, empty on 15, "contract" on 11 and "multisig" on 3; a threshold is read on 3 of the 98. The Sentora and
  Gauntlet rows have no owner type at all, the Steakhouse rows say "contract" (proxy, no threshold). Without addresses these rows
  cannot be tied to the vaults measured in this note.
- A 1-of-1 Safe cannot be told apart: no row has a `multisig_owner_count` of 1 (four rows have a threshold of 1 with several
  owners). Signer identity, role separation and overlap are not in the data at all.
- Quality: one row carries a TVL of 6.8e18 (Inverse Finance FiRM), an impossible figure that passes through unfiltered.
- What it has that this oracle does not: headline percentages, filters (owner type, stale oracle, chain, TVL band) and 5,244
  rows of breadth.

**DeFiScan, read per vault** (the five Morpho vault pages, opened Sentora PYUSD and Gauntlet USDC Prime; home counters 1,310
contracts, 166 admins, 3,588 "updates identified", 20 reports on its home page).
- Sentora PYUSD page: "Sentora Owner 1/1 Multisig" and "Sentora Curator/Guardian 1/1 Multisig" plus an allocator EOA, 3-day delay,
  "8 out of 14 functions with potential impact on funds have mitigations". It labels the 1/1 Safes but not whether the signer
  behind each is an EOA, or whether the two are distinct keys (they are: two different EOAs, per the sweep).
- Gauntlet USDC Prime page (Base): owner 4/7, curator 3/7, guardian 3/7, and the text "three independent multisigs of differing
  thresholds". **Read on-chain today** (owner `0x5a4E1984…`, curator `0x9E33faAE…`, guardian `0x7084bf4d…`): the three Safes have
  exactly the same 7 signers (union 7). "Independent" holds for the contracts, not for the keys, and a guardian veto held by the
  same signers as the owner and curator is not an independent check. This is the concrete, checkable hole neither DeFiScan nor DIA shows.
- Its activity feed already shows typed signer events, for example a `ROLE UPDATE` "Safe.owners slot 5 changed from … to …" on a
  Chainlink Safe that the Gauntlet vault depends on (19 Aug), so a signer-change detector exists at DeFiScan for the contracts it
  discovers; the "[Signer change] … AddedOwner" tickets seen on the tracker board have no source in six of the owner's repositories
  (0 results), so I do not claim that one of this project's own loops produces them.

**Three functions to imitate** (the oracle's job is to be a better read of the same facts, so these are presentation and
process features, not new data):
1. **A typed change feed per target, with freshness stamps (DeFiScan).** Each event has a type (data, role, removal), a category,
   a one-sentence before/after, a date and an address; the page header shows "latest activity 24 days ago" and "on-chain data 9
   hours ago". For the oracle: each score carries the age of its last read and the typed list of changes that moved it.
2. **Evidence share and a written reason for each change (Foreshock, read through a page summarizer, not the raw page).** The
   score comes with the share of the rubric verified against named sources, the assessment history records why a score moved,
   and alerts go out immediately or as a digest per protocol. For the oracle: show "timelock not read" instead of a silent
   default, and store the cause with each score change.
3. **A consequence sentence and powers per actor (L2BEAT, Base page).** The risk summary reads "funds can be stolen if a contract
   receives a malicious code upgrade; upgrades must be approved by 2 parties: … ; there is no delay", and each actor lists what it
   "can upgrade with no delay" and what it "cannot" do (a pauser that "cannot unpause or extend pauses"). For the oracle: one
   generated sentence per target plus the powers taxonomy already in the backlog.

### What a Safe's threshold does not say: modules, guards, handlers (seventh pass, 21 Sep)

Read-only, script `chains/ethereum-l1/scripts/sweep_safe_config.py` (inputs: the two row dumps of the vault sweeps): version,
enabled modules, guard, fallback handler and nonce of every distinct listed owner or curator Safe.
- **109 Safes on 15 chains, $9.13B** (a vault counts once per Safe address, so an owner and a curator Safe of one vault each
  carry it). Versions 1.4.1 (89) and 1.3.0 (20). **Guard: none on any of the 109.** Fallback handlers: three shared addresses
  (85, 13 and 7 Safes), 3 Safes without one; I did not identify the three addresses. Nonce (transactions ever executed): median
  31, 42 Safes under 20, 5 never used.
- **Modules: 10 Safes, $49M (0.5% of the total).** Nine are Zodiac **Roles** modules (two implementations, both named "Roles" and
  verified on Blockscout) on **kpk curator Safes, all 2-of-5**, $47M in all; one Safe (Stake DAO, owner, 3-of-5, $1.4M) has
  two Curve voting modules (GaugeVoter, GovCurveVoter). No Zodiac Delay module (none answers `txCooldown()`).
- **Who holds the Roles.** The full event history of each of the nine modules is on Blockscout (no next page). Each module has
  3 or 4 members, **every one a plain EOA**, named by role: MORPHO_REBALANCER_AGENT, MORPHO_SHUTDOWN_AGENT,
  MORPHO_MONITORING_AGENT (one Safe uses EULER_REBALANCER_AGENT and EULER_EXIT_AGENT, plus two TEST_EULER_* agents). Two EOAs
  (`0xD5800E37…`, `0x29061B1C…`) are members of two different modules. On the largest (Safe `0xf8182E58…`, curator of the kpk
  USDC Prime V2 vault, $21.2M) I decoded the allowed functions: the rebalancer may call `allocate` and `deallocate`; the shutdown
  agent may lower caps, call `updateWithdrawQueue`, `allocate`, `deallocate` and `setForceDeallocatePenalty`; the monitoring agent
  may call `submit(bytes)`, `setLiquidityAdapterAndData` and `setForceDeallocatePenalty`. One selector (`0x7299aa31`) is not
  identified. No parameter-scoping event appears in its history. The other eight were not decoded function by function.
- **What this means.** This is a reasonable least-privilege design, not a finding against kpk: the vault's own timelock and
  sentinel are the brake on `submit`. But the oracle reads "2-of-5" and the effective authority also includes three or four
  single keys with scoped powers, one of which can queue a curator action without any Safe signature. The threshold cannot show
  that; the module's role table can.
- **What the code does today.** `scripts/lib/scorers.py::_safe_guard_and_modules` reads modules and guard for the root-Safe
  scorer and only appends "WARNING: … re-check by hand"; it does not change the score. The Morpho vault scorers do not read
  modules at all, and no scorer resolves a Roles module to its members.
- **Why it matters beyond $49M.** Two 2026 incidents drained Safes with no owner signature because of an enabled module: the
  SquidRouterModule exploit (May 2026, roughly $3M to $4M from 86 Safes, amounts differ by outlet; Halborn and Common Prefix
  wrote it up) and the 15 September rsETH drain (2,882 rsETH, about $7.7M, from one Ethereum Safe through a custom Uniswap v4
  liquidity module; an MEV bot took the funds; several outlets). Both are bugs in the module itself, not delegations like kpk's, so
  they are a different failure from the one measured above, but they share the point: a threshold scorer would have shown both
  Safes as ordinary multisigs. Existing backtests cover Drift, Solend and Wasabi, and Echo Protocol's eBTC is a live target, so
  the unbacktested incident class is the module drain.
- **Same missing capability as Horizon.** Resolving a Roles module needs event logs, which the public RPCs refuse; I used
  Blockscout's per-address log endpoint. The Horizon limit (a role holder added later is not seen) and a signer-change feed need
  the same thing: a log source the oracle can trust and reproduce.
- **A slip of mine, corrected.** The first run of the script read the fallback handler from a mistyped slot name and reported
  none on all 109; the constant `0x6c9a6c4a…` is `keccak256("fallback_manager.handler.address")`. The guard constant was right.

### Known-vulnerable module code, exit capacity, the signer layer, and what incidents can calibrate (eighth pass, 21 Sep)

**1. Known-vulnerable module code (the most concrete item).** In June 2026 the Zodiac team disclosed a flaw in two modules,
Roles Modifier v2 and Delay Modifier v1.1.0: the ERC-1271 signature check read the returned data without checking that the
`staticcall` had succeeded. It was exploited against Gnosis Pay accounts on 1 June and a fix was flagged on 5 June; per the Gnosis
post-mortem (read through a page summarizer) the bug dates from version 3.4.0 (30 Oct 2023), and per Safe Labs' statement and press it
needs the module enabled and a Safe account with a vulnerable fallback handler set as a module or role member; Safe contracts and
the Safe{Wallet} app are not affected. I could not open Zodiac's own notice (the X post is behind a paywall).
- Measured on the nine kpk Roles modules: **seven are clones of the implementation deployed on 1 Dec 2023**, whose verified
  `SignatureChecker` has the failing pattern (`(, bytes memory returnData) = signer.staticcall(...); return bytes4(returnData) ==
  EIP1271_MAGIC_VALUE;`), on Safes carrying $40.1M; **two clone an implementation deployed on 12 June 2026** whose source reads
  `success && bytes4(returnData) == ...` (patched), on $7.0M. Both are the read of verified source on Blockscout, not a test.
- Does it matter for those Safes? The verified source returns false before the call when the signer has no code, and every member of the nine
  modules is an EOA, so the disclosed condition (a contract account as member) does not hold today. This is not a claim that they are
  exposed or that they are safe, and nothing was exercised.
- Why it matters for the oracle: nobody found tracks which module *implementations* are enabled where and matches them to advisories
  (novelty scan below). A registry keyed on implementation address or code hash (Roles pre-fix, Delay v1.1.0, SquidRouterModule, and
  whatever comes next), matched against every Safe the oracle reads, is cheap: `sweep_safe_config.py` already lists modules and resolves clones.

**2. Exit capacity next to the timelock.** A timelock protects depositors only if they can leave inside it. Script
`chains/ethereum-l1/scripts/sweep_exit_capacity.py` (Morpho's public API, an indexer; one instant, not a forecast): 167 listed vaults of
$1M or more, $5.95B (55 V1, 112 V2).
- Instantly withdrawable liquidity as a share of each vault's deposits: under 5%: 12 vaults, $775M (13.0% of deposits); 5 to 20%: 43, $1,870M
  (31.4%); 20 to 50%: 33, $1,481M (24.9%); 50% or more: 79, $1,821M (30.6%). V1 vaults hold 62.0% of their deposits as liquidity, V2 vaults 31.0%,
  or 42.1% when the in-kind exit that V2 offers (`forceDeallocatableLiquidityUsd`) is counted, which moves 10 of the 12 thinnest vaults out of the under-5% band.
- Timelocks (V1 `timelock`, V2 `addAdapter`): 108 vaults at 3 days (three days plus at most five minutes), 4 between 3 and 7 days, 52 at 7 days, 3 above.
- **Behind a timelock of about 3 days or less sit 108 vaults, $2,871M (48% of deposits); of them 44 vaults, $1,910M (32% of deposits) have
  instant liquidity under 20% of their deposits**, 29 vaults, $1,738M, when the in-kind exit is counted. The largest thin ones: Steakhouse USDG
  (Robinhood Chain, $488M, 7.5%, 7 days), Paypal USD Main ($431M, 5.0%, 3 days), Steakhouse High Yield USDC Edition (Base, $429M, 8.4%, 3 days),
  Sentora RLUSD Main ($369M, 8.0%, 3 days), Sentora PRIME Main ($186M, 2.0%, 3 days).
- Reading: a depositor who sees a malicious queued change on day 0 can pull at most the liquid share at once and the rest as borrowers repay or
  through the in-kind route; the sizing says how much of a vault's protection window is real, not that any change is pending. Low liquidity is
  normal for lending vaults. Limits: listed vaults of $1M or more only, Euler Earn and Aave not covered, liquidity moves with utilisation.
- Novelty (search only): L2BEAT has an "exit window" for rollups; Morpho V2's documentation describes in-kind exits; no product was found
  that puts a DeFi vault's timelock next to its exit capacity.

**3. The signer layer.** Script `sweep_safe_signers.py` (one hop: it opens each Safe's owners, not the Safes among them).
- 109 Safes, 560 signer slots, 381 distinct (chain, signer) pairs: **370 plain EOAs, 9 Safes, 1 other contract, 1 EIP-7702-delegated EOA** (a signer of an
  owner Safe, 4-of-7, $24.6M, delegating to `0x63c0c19a…`; the target was not identified or judged). One nested Safe (`0x8b884f…`) is a signer of nine kpk curator Safes.
- **Independent signer groups.** Merging Safes that share a plain-EOA signer address leaves **34 groups**. The two largest (13 Safes on 6 chains with
  11 distinct EOA signers; 17 Safes on 9 chains with 7 EOA signers, Gauntlet) hold half of the deposits counted per Safe, the five largest 79%. Each Sentora
  Safe pair (Ethereum and Tempo) is one group of one EOA, about $1.1B each. A vault appears once under its owner Safe and once under its curator Safe, so
  these shares are per role slot, not per vault.
- **Role separation at vault level.** For the 151 listed vaults ($3.22B) whose owner and curator are both Safes with readable signers: the
  same Safe holds both roles in 27 ($327M, 10%); **the signers the two Safes share are enough on their own to reach both thresholds in 85 vaults ($1,621M, 50%)**;
  they reach one threshold in 1 ($2M); some signers are shared but below both thresholds in 13 ($40M, 1%); **no signer is shared in 25 ($1,231M, 38%)**.
  Many of the 85 are small curators run by one team, so this says the same people can act in both roles, not that anyone did wrong; for V2 vaults
  the owner cannot hurt depositors directly and the guardian or sentinel matters more, and guardians are not in these dumps. It generalises the
  Gauntlet finding and answers DeFiScan's and DIA's "independent multisigs" wording with a testable criterion.

**4. Incidents, and what they can calibrate.** A research reviewer compiled 23 authority-related incidents from 2024 to September 2026 (about $2.75B);
I spot-checked three rows and corrected two details (AFX had a 200-second dispute period; Humanity's ProxyAdmin timelock is not stated), see
`data/research_2026-09-21-authority-incidents-evidence-table.md`. Findings that hold up: single-key or low-threshold admin in 9 of 23; thresholds
published in only 7 of 23; no documented timelock that existed and was bypassed; the threshold gave no protection in blind-signing, UI, pre-signing and
module cases and where the quorum was reached with stolen keys; **nothing visible separates victims from non-victims because there is no non-victim
sample, so the oracle should claim measured exposure, not prediction**. The useful signal is the lead time: Drift's timelock was removed days before the
drain, CrediX's role grants and SwissBorg's authority transfer came days before (the last two unverified), which is the evidence to rank the
posture-change monitor first.

**5. Novelty scan (a reviewer reviewer, search-based, some pages read only as snippets).** Open after honest search: a signer-hygiene rating (EIP-7702
signers, dormant signers, nested Safes, keys shared across protocols: SEAL publishes guidance, no rating); monitoring of module and Roles changes as a public
feature (Zodiac's June alert was one-off); a vault's timelock against its exit capacity. Partly covered: on-chain risk feeds (Credora on Morpho and Spark
puts governance in its probability of loss; Exponential rates A to F), oracle risk (a Chainlink hackathon "Oracle Hygiene" monitor and a GitHub feed monitor
that watch stale feeds, nothing rating who can change the oracle behind a vault), and empirical studies (Immunefi's scoreboard and Chainalysis put key
compromise at 43.8% of losses in 2024; a press analysis puts it at 82.7% of roughly $935M in the first half of 2026; no study breaks it down by threshold or
timelock). Two corrections to the reviewer: ERC-8241 is not absent, it is an early draft (PR 1706 to ethereum/ERCs, see the 18 Sep evaluation), and its
description of VaultPilot ("admin role enumeration") conflicts with my earlier reading of that repository's code (`checkPermissionRisks` reads only
`owner()`), which I did not re-open today. Lagoon's documentation presents Zodiac Roles as the intended way to scope a curator's permissions, so Roles modules are a pattern, not an accident.

### The layer under the vaults: who can change the price oracle (ninth pass, 21 Sep)

Script `chains/ethereum-l1/scripts/sweep_morpho_oracle_authority.py` (Morpho's public API for markets and oracles, then on-chain reads and
verified ABIs). A vault's depositors also trust whoever can change the price feeds of the markets it lends into. 171 listed markets with
$1M or more of supply, $5.86B:
- **By oracle type:** Morpho's Chainlink-based oracle (`ChainlinkOracleV2`) 143 markets, $4.60B (78.5%); "Unknown" (custom) 18 markets, $826M
  (14.1%); the older Chainlink oracle 4 markets, $384M (6.6%); none 6 markets, $49M (0.8%).
- **The custom oracles are mostly not admin-controlled.** The 16 custom contracts are all EIP-1167 clones of six implementations. Four
  implementations, behind 14 contracts and about $463M, are verified `MetaOracleDeviationTimelock` code (a challenge and heal flow between
  oracles) whose only state-changing functions are `challenge`, `heal`, their accept and revoke steps and a one-time `initialize`: no owner
  and no setter in the ABI. Two implementations, on Robinhood Chain ($342M) and Monad ($21M), were not read (no explorer queried for those chains).
- **The authority moves to the Chainlink feed proxies.** The Chainlink-based oracle reads feeds whose proxy contract is `EACAggregatorProxy`;
  its `proposeAggregator` and `confirmAggregator` are `onlyOwner`, and in the verified source (Chainlink `AggregatorProxy.sol`, v0.6) nothing delays
  the change: the owner can point the feed to a new aggregator. 143 markets use 113 distinct feed contracts. The owners read are
  **four Safes, all 4-of-9 with nine plain-EOA signers and no guard: `0x21f73D42…` on Ethereum (Safe v1.1.1, 26 feeds), `0xf0Db7318…5B1b` on Base
  (v1.3.0, 14 feeds), `0xeE27D5Ae…` on Robinhood Chain and one on Katana. The same 9 signers sit in all four.**
- **Concentration.** **75 markets, $3.59B, 61% of the listed market supply, depend on at least one feed owned by the four largest owner
  addresses** (the Ethereum, Base and Robinhood Chain Safes above, plus `0x81bc85f3…`, an unidentified contract on Ethereum with two feeds); counting the Katana Safe
  instead of that contract gives 76 markets and $3.58B, also 61%. A market counts once. On a further $0.89B (Ethereum feeds and others) `owner()` could not be read. By owner group: the Base Safe touches $1.80B of market
  supply, the Ethereum Safe $1.65B (a market that uses both counts under each). It is a trust assumption every user of these feeds accepts, not
  a flaw, and I have not looked at the signers' identities or at Chainlink's off-chain process around the keys.
- **The Base Safe is the one DeFiScan flagged.** On DeFiScan's Gauntlet USDC Prime page the "GnosisSafe (Chainlink)" at `0xf0Db…5B1b` shows a signer change on 19 Aug
  ("Safe.owners slot 5 changed"); that Safe is the owner of 14 feeds behind $1.8B of Morpho market supply. I did not check whether
  that change was applied on the other chains (today all four sets are identical).
- **Each of the three readable Safes has exactly one module**, a bespoke `ConfirmedTransactionModule` (Solidity 0.5.17, verified on Ethereum and Base; the
  Robinhood Chain one was not read): the Safe confirms a transaction hash and an address the Safe has set as executor can then trigger it. It adds no delay and no signer path
  outside the Safe's own confirmation; the executor set was not read.
- **Novelty (search only):** no product was found that rates who can change the oracle behind a vault; DeFiScan shows Chainlink as a dependency and follows its Safes'
  events, but no source found gives the concentration figure (61% of listed Morpho market supply behind one 9-signer group).

### Cross-chain verifiers: LayerZero OFTs five months after KelpDAO (tenth pass, 21 Sep)

Script `chains/ethereum-l1/scripts/sweep_layerzero_verifiers.py` (LayerZero's public metadata API for the OFT list, endpoints and DVN registry, then on-chain
reads; seven EVM chains with a public RPC: Ethereum, Base, BNB Chain, Arbitrum, Avalanche, Polygon, Optimism; Solana and other chains are not covered).
654 V2 OFT deployments (232 adapters that lock a token, 422 OFTs that mint one); 427 could be priced, $12.09B (adapters $9.17B locked, OFTs $2.92B supply).
For each of the 200 largest it reads, for every remote chain the token also lives on, the receive library and the resolved ULN configuration
(`getUlnConfig`) on the local EndpointV2: 903 inbound paths. The number that matters is how many verifiers must be compromised to forge a message
(required DVNs plus the optional threshold).
- **Weakest open inbound path.** A path whose verifier set contains a dead DVN (`LZDeadDVN` or the `0x…dEaD` address) can never be verified, so it is counted as blocked (28
  paths), not weak. Of the rest: **one verifier suffices on 8 deployments, $151M (1.2%), all OFTs, none an adapter**; two on 79 deployments, $2.28B (18.9%); three
  or more on 112 deployments, $9.61B (79.5%); one deployment unread.
- **The 8 single-verifier deployments** are rsETH on Arbitrum ($48M supply) and on Base ($34M), CYC on Ethereum and BNB Chain ($25M each), IMO ($10M), BONSAICOIN ($6M),
  HAI ($1M) and KERNEL. In every case the only verifier is LayerZero Labs' DVN. rsETH's L2 deployments are on **LayerZero's default configuration** for 8 to 9 inbound paths, while the
  Ethereum rsETH adapter ($84M locked) requires four DVNs (Horizen, LayerZero Labs, Canary, Nethermind or Google) on all 16 of its paths with its own configuration. Five of the others
  (CYC twice, IMO, BONSAICOIN, HAI) are the applications' own 1-of-1 choices, and KERNEL is on the default.
- **Correction (30 Sep): the single-verifier count above is overstated.** The script did not read `peers(uint32)`, and an OApp with no peer
  set for a chain rejects every inbound message from it (`OAppReceiver._getPeerOrRevert`): such a path is closed, not weak,
  until its owner sets a peer with one call (the 1-of-1 verifier configuration stays in place, so it is closed, not fixed). rsETH on Arbitrum
  has need=1 on 13 paths (mode, blast, base, optimism, scroll, zksync, zircuit, xlayer, swell, hemi, sonic, unichain, tac) and **all 13 have peer
  0x0**; its only open path (from Ethereum) needs 4 verifiers. Rerun with the fix on Ethereum and Arbitrum, top 60 ($11.33B): 103 of 316 paths
  have no peer, and one verifier suffices on **1 deployment, CYC on Ethereum ($35M, open path from BNB Chain, owner and delegate Safe 2-of-3)**.
  **Full rerun, same scope as 21 Sep (7 chains, 200 largest, $12.79B, 30 Sep):** 298 of 897 paths have no peer; one verifier suffices on
  **5 deployments, $93M** (CYC on Ethereum and BNB Chain, $35M each; BONSAICOIN and IMO on Base, owner and delegate a bare EOA; HAI), against
  8 and $151M on 21 Sep: rsETH on Arbitrum and Base and KERNEL were peerless paths. 8 deployments ($25M) have every read path closed. The
  delegate is a plain EOA while the owner is a Safe or contract in 24 deployments ($93M), against 29 ($91M).
- **What this on-chain reading cannot see.** LayerZero's incident report says its DVN "will refuse to sign as the sole required attestor on any channel" (read through a page
  summarizer). If that holds, a channel whose only verifier is that DVN cannot pass messages, so these paths are 1-of-1 on chain but probably fail closed, and the
  real state depends on an off-chain policy that no configuration reader shows. Kelp's counter-claim (CoinDesk, summarizer) is that the 1-of-1 was LayerZero's documented default,
  and 30% of the paths read here (268 of 903) are still on the default. Not verified: how the refusal applies to default configurations, or whether these channels carry traffic.
- **Concentration on one operator.** LayerZero Labs' DVN is used on at least one path of 172 of the 200 deployments (Nethermind 130, Canary 120, Horizen 105, Google 43, P2P 41). The
  same pattern as the Chainlink owner Safes: a single operator that everything depends on, here for liveness as much as for safety.
- **Who holds the keys.** The owner of the OFT is a Safe for 141 deployments ($5.51B), a contract for 28 ($6.49B), a plain EOA for 26 ($93M), a 1-of-N Safe for 4. The **delegate**
  (the address that can change the verifier set, the surface used in The Sandbox's SAND bridge exploit) is a plain EOA for 55 deployments ($184M) against 26 for the owner:
  **in 29 deployments ($91M) the delegate is a plain EOA while the owner is a Safe or contract**, for example DEUS on Base ($17M, owner Safe 2-of-3, delegate an EIP-7702-delegated EOA),
  PROMPT on Ethereum ($17M, Safe 3-of-6), SHELL on Ethereum and BNB Chain ($12M each, Safe 2-of-3) and SOMI ($7M, Safe 3-of-5). The 28 "contract" owners were not opened.
- **Against the repository.** The `layerzero_delegate_risk` module was checked only against the Robinhood Chain targets, none of which is an OApp. At this scale the pattern
  exists in 29 of the 200 largest deployments.
- **Limits.** One instant; 227 deployments could not be priced and are not covered; Solana OFTs are out of scope; supply of an OFT is exposure to an unbacked mint, not a loss
  figure (an adapter's locked balance is what a forged message could release); the DVNs' own security is not assessed, only how many must agree.
- **Novelty (search only).** The search for a public DVN-configuration monitor after the Kelp exploit returned only the incident write-ups and LayerZero's policy change; none was found.

### Token issuers under the vaults: what they can do to the balances (eleventh pass, 21 Sep)

Script `chains/ethereum-l1/scripts/sweep_asset_authority.py` (Morpho's public API for assets and values, verified ABIs on Blockscout, on-chain reads of the role
holders). A vault can have a sound owner, curator and guardian and still hold a token whose issuer can freeze the vault's address, seize a balance, pause every
transfer or replace the token's code. 138 distinct assets: the loan asset of every listed vault of $1M or more ($5.95B, 40 assets) and the collateral of every listed
market of $1M or more of supply ($9.05B, 103 assets). 99 were read (verified code on Ethereum, Base, Arbitrum, Optimism, Polygon); 39 could not be (no explorer
queried: Robinhood Chain, Arc, Monad, Hyperliquid), which is 15% of deposits (USDG $487M on Robinhood Chain, USDC $152M on Arc and $53M on Monad) and 10% of
collateral, so every share below is a lower bound. The four families are matched by function name: freeze (blacklist, blocklist, denylist, freeze), seize (wipe,
destroyBlackFunds, seize, clawback, forceTransfer), pause, upgrade.
- **Deposits ($5.95B):** freeze-capable assets hold $4.15B (69.8%); seize-capable $1.86B (31.3%); pause-capable 80.7%; upgradeable 75.4%; at least one of freeze, seize
  or pause 81.3%. **Collateral ($9.05B):** freeze 55.6%, seize 0.2%, pause 64.2%, upgradeable 63.3%, any of the three 65.7%.
- **Which tokens.** Deposit side: USDC $2.9B (Base $2.0B, Ethereum $0.89B), PYUSD $693M (`freeze`, `wipeFrozenAddress`), RLUSD $619M (`clawback`), USDT $374M
  (`addBlackList`, `destroyBlackFunds`), EURCV $142M (`wipeFrozenAddress`). Collateral side: cbBTC $3.95B (Base $3.09B, Ethereum $0.86B), 44% of all market collateral,
  with freeze, pause and upgrade; kBTC $518M; WBTC $434M (pause only; its owner is a contract). With none of the four families: wstETH ($705M), WETH, rETH, DAI, USDe on Base, the
  Pendle PT tokens and most vault-share tokens. One false positive is known: strUSD's `seizeCooldown` matches the seize family by name ($15M), so the seize figure is name-based.
- **Who holds the roles, read directly.** USDC on Ethereum: owner `0xfcb19e6a…`, blacklister `0x0a06be16…` (701 transactions sent) and pauser `0x4914f61d…` (never used) are
  accounts without code, the master minter is a contract. cbBTC on Base: owner, blacklister (545 transactions), pauser and master minter are all accounts without code. "No
  code" means a key-controlled account, not one person's key: custody (an HSM, an MPC scheme) is not visible on chain. USDC's proxy does not use the EIP-1967 admin slot, so
  its upgrade authority was not read. PYUSD is an AccessControl token (holders not enumerated, owner an EOA); USDT's owner is a 5.7 kB contract that is not a Safe and was not opened.
- **What it means.** After the curator, owner and guardian, the residual authority behind the largest vaults is the token issuer. This is capability read from the code, not a
  claim that any issuer has used it or intends to; the oracle currently has no field for it.
- **Novelty (search only).** The powers are documented (ERC-3643, ERC-7943, press on xStocks, OUSG, USDY) and RWA risk ratings exist (RedStone, Credora, Gauntlet 2026 report), but no
  per-vault measurement of the share of deposits in freezable assets was found.

### Hyperlane token routes, and the Aave guardian on 18 chains (twelfth pass, 21 Sep)

**Hyperlane.** Script `chains/ethereum-l1/scripts/sweep_hyperlane_isms.py` (the public `hyperlane-registry` repository for routes and chains, then on-chain reads with the
public RPCs the registry lists). A warp route is a router per chain; it accepts a message when its Interchain Security Module says so, and ISMs nest (routing, aggregation,
multisig). 342 route files, 897 EVM routers on 107 chains; 378 could be priced, **$0.43B** (collateral held $0.15B, synthetic supply $0.28B), which is about 28 times less than
the LayerZero OFTs above ($12.09B). For the 150 largest ($0.43B, so all the priced value) it resolves the ISM tree that applies to a message from each other chain of the route by
calling the ISM's view functions with a synthetic message (685 paths read). Counting rules: a multisig contributes its threshold, an aggregation its k cheapest modules, a
trusted-relayer ISM one party, a pausable ISM none (it adds no verification), and an origin for which the routing ISM reverts is refused, not weak (14 of 685 paths).
- **Weakest origin, parties that must be compromised:** one party on 4 routers ($0M); **two on 101 routers, $231M (53.7%)**; three on 30, $141M (32.7%); four or more on 13,
  $58M (13.5%); 2 routers unresolved. The two largest routes, NES (BNB Chain $147M, Ethereum $34M) and KII ($21M twice), use custom nested ISMs whose weakest origin still needs two or three
  validators beyond a pausable module.
- **Validators are shared.** 100 distinct validator addresses appear across the 150 routers; the most shared one is in 121 of them, and the next four in 114, 113, 74 and 69. 92 routers ($180M)
  use the Mailbox's default ISM. This is the same shape as the Gauntlet and Chainlink findings: one small group behind many contracts.
- **Who can replace the ISM:** the router's owner is a contract for 46 routers ($275M; several are 45-byte clones that were not opened), a Safe for 79 ($119M) and a plain EOA for 20 ($36M).
- **Limits.** Only routes listed in the registry; 519 of the 897 routers could not be priced; validators' identities are not mapped, so the sharing is by address; "two parties" is a threshold, not a
  statement that they can be compromised; only token routes were read, not Hyperlane's other message flows; nine ISMs answered no `moduleType()` and were left unresolved.
- **Slips of mine, corrected.** A route whose collateral is a vault-share token declared 6 decimals in the registry against 18 on chain, which produced a total of $12 quadrillion (decimals now come
  from the token); the pausable ISM was first counted as a verifier; a reverted route was first counted as a failed read; the nesting limit of 4 left 55% of the value unresolved.

**Aave's Governance Guardian.** Script `chains/ethereum-l1/scripts/sweep_aave_guardians.py` (the official `aave-address-book` for the addresses, on-chain reads). The GOVERNANCE_GUARDIAN of
Aave V3 is a **Safe 5-of-9 with exactly the same nine signers on all 18 chains read** (Ethereum, Base, Arbitrum, Optimism, Polygon, BNB Chain, Avalanche, Gnosis, Scroll, Linea, Mantle, Sonic, Celo,
Metis, zkSync, Ink, Soneium, Plasma), through 9 different Safe addresses (Safe 1.3.0 or 1.4.1, no guard). Those chains carry **$17.49B of Aave V3's $17.95B TVL (97%)** on DefiLlama. The repository's README
already found the identical signer set on Arbitrum and Base and on Plasma; this extends it to every chain in the address book. The GRANULAR_GUARDIAN on each chain is a contract (6.5 to 7.3 kB, 43.7 kB on zkSync)
that was not opened, and what the Governance Guardian can do on each chain was not re-derived here. By chain, the oracle already scores 93% of Aave V3's TVL (Ethereum, Base, Arbitrum, Plasma), so the
gap is not coverage but that the guardian is one group of nine people on every chain.

### Issuer powers across the big lenders, and Aave's granular guardian opened (thirteenth pass, 21 Sep)

**Lenders compared.** Script `chains/ethereum-l1/scripts/sweep_lending_asset_authority.py` (DefiLlama's public yields API for pools and the address of each underlying token, then verified code on
Blockscout, same four function families as the Morpho pass; the seize pattern here excludes `seizeCooldown`). 675 pools of $1M or more in 11 projects, $51.09B; tokens on chains with an explorer
(Ethereum, Base, Arbitrum, Optimism, Polygon) are read, the rest are not, so every share is a lower bound. Share of each project's pooled TVL in tokens that can be frozen, seized or paused, or whose code is upgradeable:

| Project | Pooled TVL | Read | Freeze | Seize | Pause | Any of three | Upgradeable |
|---|---|---|---|---|---|---|---|
| Morpho (pool level) | $14.85B | 89% | 62% | 13% | 72% | 73% | 69% |
| Aave V3 | $18.27B | 88% | 13% | 1% | 52% | 53% | 41% |
| Compound V3 | $1.41B | 100% | 10% | 3% | 47% | 47% | 13% |
| Fluid | $1.00B | 94% | 36% | 13% | 49% | 49% | 49% |
| Spark savings | $1.18B | 98% | 61% | 35% | 61% | 61% | 58% |
| Dolomite | $0.66B | 97% | 65% | 1% | 86% | 86% | 87% |
| Maple | $4.02B | 100% | 89% | 17% | 89% | 89% | 83% |
| Sky lending | $7.62B | 100% | 0% | 0% | 0% | 0% | 67% |

Venus (0% read, BNB Chain), Lista (3% read) and Euler V2 (12% read) are too little read to compare. Across the eleven projects 52% of the pooled TVL that could be read sits in tokens with at least one of the three.
The Morpho figure is lower than the 81% of the vault-deposit pass because this one counts pools (loan and collateral assets) rather than vault deposits, which are mostly stablecoins. Reading: what drives the number
is the asset mix. A lender whose assets are its own tokens and ETH (Sky) has none, a lender that mostly lends USDC and USDT (Maple) has most of it, Aave sits in between because of its staked-ETH and wrapped-BTC
assets. The tokens behind the numbers are the same few, identified by address: USDC ($4.49B on Ethereum, $2.04B on Base; freeze, pause and upgrade), cbBTC ($2.42B on Ethereum, $3.33B on Base; freeze,
pause and upgrade), USDT ($1.85B; freeze, seize, pause), PYUSD ($0.69B) and RLUSD, against wstETH ($4.29B), WETH ($2.92B) and Sky's USDS ($4.80B on Ethereum; upgradeable only) with none of freeze,
seize or pause. The names in the script's top-token list are contract names (proxies), not tickers.

**Aave's granular guardian opened.** `GranularGuardianAccessControl` (verified, `AccessControlEnumerable`, so role holders can be listed without event logs) exposes `retryEnvelope`, `retryTransaction`,
`solveEmergency`, `solveEmergencyDeprecated` and `updateGuardian`, with three roles. On all 18 chains: **SOLVE_EMERGENCY_ROLE is held by the Governance Guardian Safe** (the 5-of-9 with the same nine signers);
**RETRY_ROLE is held by a Safe 2-of-3 on every chain and, on 17 chains, by a Safe 1-of-2 at one and the same address (`0x2b99790c…`)**, whose signers are not among the nine (checked on Ethereum, Base, Arbitrum and Polygon);
**DEFAULT_ADMIN_ROLE is a contract that equals Aave's level 1 executor** on the six chains compared (Ethereum, Base, Arbitrum, Plasma, Mantle, zkSync), so governance itself can grant and revoke. What each function does is read from its
name only (retry re-sends cross-chain governance messages; the emergency and guardian-update functions are named for their purpose), not re-derived from the code. So the picture of Aave's guardian layer is: one group of nine for
emergencies on every chain, a separate two-Safe group for retries, and governance above both.

### Who holds the issuer powers: role events replayed, upgrade admins and multisigs opened (fourteenth pass, 21 Sep)

The eleventh pass found which tokens can be frozen, seized, paused or upgraded, and read the plain getters. Tokens built on OpenZeppelin AccessControl have no getter, so their holders were not listed. Script
`chains/ethereum-l1/scripts/sweep_token_role_holders.py`: it replays every `RoleGranted` and `RoleRevoked` event of a token (one `eth_getLogs` call over the whole history), names each role from the
`bytes32` constants of the verified ABI (or by hashing a list of common role names, marked `*`), checks every replayed holder on chain with `hasRole` (0 mismatches on all 28 assets whose events were read), and
classes each holder: account without code, Safe (t-of-n and signers), legacy multisig, weighted multisig, timelock, or another contract (with its `owner()` one level down). It also reads the proxy admin from the
EIP-1967 slot and from ZeppelinOS's `org.zeppelinos.proxy.admin` slot, which is where USDC and PYUSD keep it. Read on 30 assets (the 27 of the eleventh pass that use AccessControl or had no controller read, plus USDC, USDT, WBTC).

| Token (exposure) | Who holds what, read on chain 21 Sep |
|---|---|
| PYUSD ($0.69B) | **One account without code** holds DEFAULT_ADMIN, ASSET_PROTECTION (freeze and wipe) and PAUSE, and is `owner()`. A second account without code is the proxy's upgrade admin. |
| USDC, Ethereum ($0.89B) | Upgrade admin (non-standard slot) is **one account without code**; `owner()` is another. Blacklister and pauser were read in the eleventh pass. |
| kBTC ($0.52B) | **One account without code** holds DEFAULT_ADMIN, MINTER and BURNER, is `owner()`, owns the ProxyAdmin (1,836 B) and the CCIP pool. No pauser or freezer role appears in the events, so who may call the pause and freeze functions is not resolved (modifiers not read). |
| RLUSD ($0.62B) | Ripple's own weighted multisig (`MultiSign`, not a Safe): admin and upgrade are two contracts with **the same 11 signers**, quorum 7 of total weight 26 (weights 3 and 2, so 3 signers are enough); clawback and pause are one contract, **quorum 2 of 22** signers of weight 1, 7 of whom also sit among the 11; mint is quorum 2 of 32 signers. All 68 distinct signers across these multisigs have no code (checked directly with `eth_getCode`). 14 holders have the burner role: 13 are multisigs with quorum 2 and 10 to 32 signers, one is an NTT bridge manager whose owner is the 7-of-26 admin multisig. |
| WBTC ($0.45B) | Token owner is a `Controller`; its owner is a legacy multisig (`MultiSigWalletWithDailyLimit`) **6 of 10**, seven owners without code and three contracts (not opened). No owner in common with the USDT multisig. |
| USDT ($0.37B) | Owner is a legacy multisig **3 of 6**, six owners all without code. Answers the eleventh pass's open item on the 5.7 kB owner contract. |
| PRIME ($0.23B) | Admin and upgrade sit behind a 24 h timelock, but FREEZE_ADMIN and one of two PAUSER holders are **one account without code**; the other pauser is a Safe 4-of-7. |
| sUSDe ($0.11B) | Admin is a 24 h timelock; BLACKLIST_MANAGER is a Safe 5-of-10 **and two accounts without code**, each able to act alone. |

Counted across the 30 assets, at least one admin, upgrade, freeze, blacklist, pause or clawback power sits with a single account without code for **9 assets, $2.47B, 16% of the $14.99B** of the eleventh-pass
sample (USDC, PYUSD, kBTC, PRIME, sUSDe, and four small ones). Events were read for 28 assets, $4.26B (28%) of the sample. "Account without code" is what the chain shows; a key behind an HSM or an MPC service looks the
same, so this is the number of separate signing points, not a claim about how any of them is protected.

**Use, not only capability.** Three Ethena-style restriction roles are populated: **922 accounts hold sUSDe's FULL_RESTRICTED_STAKER_ROLE, 124 hold strUSD's, and 249 hold USDtb's BLACKLISTED_ROLE** (role names confirmed by
hashing). The sUSDe list includes a contract named `TornadoCash_Eth_01` (a name from Blockscout, not otherwise checked), which points to sanctions compliance as one use. This is the first place in these passes where a freeze power is
shown to have been exercised at scale rather than only present.

**Not readable by this method.** Eight assets (USDS, sUSDS, stUSDS, EURCV, apyUSD, siUSD, apxUSD, EUTBL; $0.31B) have no AccessControl (Sky's tokens use `wards`), so their holders need another read. Two small Base assets
(sUSN, weETH on Base) returned no logs from the Base gateway and are reported as not read.

**Errors on the way, so the method can be trusted.** (1) Blockscout's logs API allows 10 anonymous calls per window of about 37 minutes; a first run took its rate-limit answers for empty histories on 22 of 27
tokens, which showed as "no holder found" until a control (RLUSD returns 20 grants) exposed it. Full-range `eth_getLogs` is refused by publicnode (key), drpc (10,000 blocks), 1rpc (50 blocks) and Blockscout's
quota; Tenderly's public gateway answered the whole range and matched the control. (2) Parallel node calls that hit a rate limit returned nothing, and a missing weight was read as 0, so one 32-signer multisig showed a total weight
of 20. Fixed by retrying rate-limit errors, capping concurrency, and printing an unread weight as unread. The final run had 0 failed node calls and 0 unread holders.

### Who may call the freeze, seize, pause and upgrade functions, and one Wormhole bridge read (fifteenth pass, 21 Sep)

The eleventh pass read the capability from function NAMES, which cannot tell a `pause` that only an owner may call from one anyone may call. Script `chains/ethereum-l1/scripts/sweep_token_function_guards.py`
fetches the verified Solidity source (Blockscout v2, the implementation behind a proxy), finds each freeze, seize, pause and upgrade function definition, and reads its header modifiers
(`onlyOwner`, `onlyRole(PAUSER_ROLE)`, `onlyBlacklister`, ...) or, failing that, an inline check. View and pure functions are skipped (a getter named `denyList` freezes nothing) and interface declarations are
classed apart. A control runs first and stops the run if USDC's `blacklist` is not read as `onlyBlacklister` and `pause` as `onlyPauser`. With `--role-holders` and `--from-dump` it joins each guard to the accounts that satisfy it
(the eleventh pass's getters and the fourteenth pass's role holders).

**The capability is real.** All 58 tokens with a name-level capability on the five explorer chains were read (0 unread). Every freeze (44 definitions), seize (8) and pause (80 implemented) function is behind a
privileged guard; none is open to anyone. The eleventh pass's shares were not inflated by look-alike names. Direct functions (the ones that act, not `updateBlacklister` and `updatePauser`, which name who may act):
freeze 20 tokens, $9.12B (61% of the $14.99B sample); seize 8 tokens, $1.86B (12%); pause 35 tokens, $10.58B (71%).

**Who can trigger it, from what the chain shows.**

| Function | One account without code | Multisig, timelock or contract only | Guard found, holder not resolved |
|---|---|---|---|
| Freeze | **$8.08B (54%)** | $0.37B (2%) (USDT) | $0.67B (4%) |
| Seize | $0.69B (5%) (PYUSD) | $1.00B (7%) (RLUSD, USDT) | $0.17B (1%) |
| Pause | **$8.48B (57%)** | $1.45B (10%) | $0.64B (4%) |

The one-account cases are mostly Circle's FiatToken code, where `blacklist` is `onlyBlacklister` and `pause` is `onlyPauser` and each role is a separate account without code (five distinct addresses for cbBTC on Base): cbBTC ($3.09B Base,
$0.86B Ethereum), USDC ($2.01B Base, $0.89B Ethereum), cbXRP, then PYUSD (freeze, wipe, pause on one account), PRIME (freeze), sUSDe (two accounts beside a Safe), kBTC (pause is `onlyOwner`, the single owner). Separate accounts per
function family are still one signing point per function. Unresolved holders are guards that name a role account this pass did not read (kBTC's `onlyBlacklistOperator`, EURCV's `onlyRegistrar`, weETH's `onlyOperatingMultisig`).
Upgrade: 53 tokens, $10.07B; the guard is the proxy admin (`ifAdmin`, $7.78B), an owner ($2.30B), an AccessControl role ($1.58B) or a dedicated timelock account (weETH); three tokens (kBTC, AUSD, SolvBTC, $0.55B) show no guard on
their proxy functions because the check sits in the proxy's fallback or beacon, which this reading does not follow (kBTC's ProxyAdmin owner was read in the fourteenth pass).

**One Wormhole read: RLUSD's NTT manager on Ethereum.** The `NttManager` (an ERC-1967 proxy) holds RLUSD's MINTER and BURNER roles and is in burning mode. Its `getThreshold()` is **1** and it has **one transceiver** (a proxy whose
Wormhole core bridge is `0x98f3c9e6…`), so one attestation path lets a mint through. Five peer chains are registered (Wormhole ids 24 Optimism and 30 Base; 44, 46 and 57 not identified); the inbound limits are 1M RLUSD on three and 5M on two, **13M per 24 h in total,
0.98% of the 1.33B on Ethereum**, and the outbound limit is 15M. Owner and pauser are the same `NttProxyOwner`, itself owned by the 7-of-26 multisig of the fourteenth pass. So the bounded exposure of a compromised single path is the rate limit;
whether the owner can raise it was not read.

**Errors on the way.** (1) The first run counted `view` getters named `denyList` as freeze functions and interface declarations as "no guard found"; fixed, and "no guard found" fell to 0 for freeze, seize and pause (12 pause declarations remain interface-only). (2) NTT rate limits were first decoded as plain integers and
read as 0; the type is `(amount << 8) | decimals` with 8 trimmed decimals, and the untrimmed capacity (1e24 = 1M RLUSD at 18 decimals) confirmed the decoding. The script's joined figures equal an independent hand computation.

## Not verified

- Which of the listed single-key V2 owners is a person, a custodian or an MPC: the signers are only "an EOA".
- Owner contracts of 2,085, 8,210 and 16,415 bytes (Spark, Steakhouse V2, others, about $2.0B) were not analysed.
- Whether sdeUSD-market vaults hold recoverable value (not analysed; irrelevant to the authority score).
- Deposits are the API's figures except where stated. One vault (Pangolins USDC, Base) returned disagreeing RPC answers
  in the first pass and is out of every conclusion.
- Signer overlap says the same keys appear, not that one person controls them or that a key is insecure.
- Who owns each Roles module (who can change the roles), whether the two shared EOAs appear outside these Safes, and the allowed
  functions of eight of the nine modules were not read; the fallback-handler addresses were not identified; module incident sources
  are press and security-firm posts, not on-chain reads.
- Eighth pass: Zodiac's own notice was not opened; whether kpk has patched or plans to is unknown; the patched-versus-vulnerable reading rests on
  the two implementations' verified source and their deployment dates; the target of the 7702 delegation, guardian and sentinel overlap and the
  contents of the nine nested Safes were not read; 21 of 23 incident rows were not opened by me; CrediX's and SwissBorg's lead times are unverified.
- Ninth pass: the identities of the nine Chainlink-feed signers, whether the 19 Aug change reached the other chains, the executor set of the
  bespoke module, the Robinhood Chain module, the owners of the Ethereum feeds that could not be read ($0.89B) and the Robinhood Chain and Monad
  meta-oracle implementations were not read; Chainlink's off-chain monitoring is unknown.
- Tenth pass: LayerZero's refusal policy was read through a page summarizer (report, CoinDesk), not from the DVN's behaviour; 227 unpriced deployments, Solana and other non-EVM chains
  are not covered; the 28 contract owners were not opened; Hyperlane, Wormhole, Axelar and CCIP were not looked at.
- Eleventh pass: capability is read from function names in verified ABIs, not from the modifiers that restrict who may call; 39 assets on chains without an explorer
  are unread; AccessControl role holders are not enumerated (done in the fourteenth pass); the custody behind role accounts is invisible; USDC's upgrade authority and USDT's owner contract were not opened (opened in the fourteenth pass).
- Twelfth pass: Hyperlane validators' identities and the 45-byte owner clones were not opened; 519 routers are unpriced; the Aave GRANULAR_GUARDIAN contracts and the guardian's powers on each chain
  were not read; Monad, X Layer and MegaETH (Aave TVL $0.46B) were not in the address-book files fetched.
- Thirteenth pass: lenders on chains without an explorer (BNB Chain, Avalanche, Solana, Monad and others) are unread, so Venus, Lista and Euler V2 cannot be compared; DefiLlama's pool TVL is the exposure (not a per-address
  balance); the granular guardian's functions were read by name and the DEFAULT_ADMIN equality was checked on six of 18 chains.
- Fourteenth pass: who the signers of RLUSD's, USDT's and WBTC's multisigs are, the three WBTC owner contracts, and what is behind the accounts without code (HSM, MPC, hardware) were not read; `RoleAdminChanged` is not
  replayed; the guard of kBTC's pause and freeze functions was not read; eight assets without AccessControl (about $0.31B) and two Base assets are unread; a missing holder would not show as a `hasRole` mismatch, only a
  wrong one would; the exposure is the eleventh pass's snapshot, not refreshed.
- Fifteenth pass: guards are read from header modifiers and the first lines of a body, not from internal calls or a proxy's fallback; the holders behind `onlyBlacklistOperator`, `onlyRegistrar` and `onlyOperatingMultisig` are not resolved;
  the join uses the eleventh pass's getters for Circle-style tokens, and a key behind an HSM or MPC service looks like any account without code; only RLUSD's NTT manager was read (other NTT, Axelar and CCIP
  deployments were not enumerated), the Wormhole guardian set and whether the NTT owner can raise the limits were not read, and Wormhole ids 44, 46 and 57 are unidentified.
- DIA rows were not matched to vault addresses (the API has none); the source of the tracker's "[Signer change]" tickets is unknown;
  Foreshock's alert content comes from a page summarizer, not from an alert email.

## Improvement backlog this suggests (ranked, none started)

1. **Scorers for the largest listed vaults, starting with Monad's V2 vaults and the Ethereum and Base ones**, using what actually differentiates them: per-function
   timelocks (fund-moving actions and the timelock-0 list), abdicated gates, and the signers behind owner, curator and
   guardian. `score_morpho_vault_generic` (V2) already reads curator, owner and authority-selector timelocks; it does not
   read abdications or role-signer overlap. New targets on the Ethereum L1 and Base oracles need a push by Spap.
2. **Controller-level scoring.** The curator Safes above are the real concentration points (two Safes govern 46% of curated
   deposits), and a vault-by-vault target list hides that. A signal per controller (threshold, signer overlap between its
   roles, number of vaults and chains it governs) would follow the same convention as the cross-exposure score.
3. **A market-scale role-separation signal**: owner, curator and guardian signer overlap across a controller's vaults
   (Gauntlet's shared 7 signers; Sentora's single-signer Safes).
4. **A queue monitor for V2 `submit` events.** The 3 and 7 day windows are the protection, so a watcher that sees a
   pending `addAdapter` or cap increase is the natural monitoring feature (DeFiScan advertises 24/7 monitoring, which is
   where it is ahead today).
5. **A drift monitor** across the nine oracles (scorer versus on-chain values).
6. **Distribution through an existing rating channel** (Credora's ratings already reach Morpho curators through
   RedStone). Hypothesis only, nothing was checked with either party.
7. **Presentation and process features** taken from DeFiScan, Foreshock and L2BEAT (typed change feed with freshness stamps,
   evidence share and reasons, consequence sentence and powers per actor), see the sixth pass.
8. **Resolve a Safe's modules** (Roles: members and allowed functions; unknown module: flag) so that delegated single-key powers and
   module-drain risk enter the score instead of a hand-check warning. Small in dollars today ($49M of $9.13B), a class in
   2026 incidents, and dependent on a reproducible log source shared with the Horizon limit.
9. **A registry of known-vulnerable module implementations**, matched by implementation address or code hash against every Safe read (Roles
   pre-fix: 7 of 9 kpk modules today, $40.1M; Delay v1.1.0; SquidRouterModule; others as advisories appear). Cheap, unique, and it turns
   the June 2026 Zodiac alert into a standing check.
10. **Exit capacity beside the timelock** as a per-vault field (a "protection window"): 44 vaults, $1.9B, sit behind a 3-day timelock with under 20% instant liquidity.
11. **Signer-group scoring**: merge Safes by shared signers, test role separation at vault level (85 vaults, $1.6B, where the shared signers alone reach both
    thresholds), resolve nested Safe signers one level further, flag EIP-7702-delegated signers. Extends improvement 2 (score per controller).
12. **Posture-change alerts ranked by observed lead time**: timelock lowered or removed, role granted to a new address, owner added or threshold lowered, module
    enabled. Extends items 4 and 8; needs the same reproducible log source as the Horizon limit.
13. **Score the oracle layer under the vaults**: extend the controller score to the owners of the price feeds a vault's markets read (here, one
    9-signer group behind 61% of listed Morpho market supply), and watch those Safes' signer changes, since one of them changed on 19 Aug.
14. **A cross-chain verifier check** (LayerZero first): weakest open inbound path, default versus own configuration, delegate weaker than owner, single-operator dependence.
    Built on the delegate module the repository already has and the sweep script; the open question is how to show a path that is 1-of-1 on chain but refused off chain.
15. **An issuer-power tag per vault asset** (freeze, seize, pause, upgrade, and who holds the roles), weighted by the vault's deposits and, for markets, the collateral: 81% of listed
    vault deposits sit in a token with at least one of freeze, seize or pause. Cheap, because verified ABIs are public; needs a rule for tokens on chains with no explorer. The fourteenth pass shows the holder part is feasible: role events replay to the current holders and `hasRole` confirms them
    (single account without code on $2.47B of the sample, quorum 2 of 22 for RLUSD's clawback), and the restricted-list sizes (922, 249, 124) show the power in use. The fifteenth pass adds who may call each function: one account without code can trigger a freeze on 54% and a pause on 57% of the sample's exposure.
16. **Extend the cross-chain verifier check to Hyperlane's ISM trees** (parties to compromise on the weakest origin, validator sharing across routes, who can replace the ISM): small in dollars today
    ($0.43B) but the same failure shape as LayerZero.
17. **Score the Aave Governance Guardian as one group on 18 chains** (nine signers, 97% of Aave V3 TVL), with the oracle's existing cross-ecosystem signer-overlap module extended from 3 chains to all of them.
18. **Issuer-power tag for every lender, not only Morpho** (share of a protocol's pooled TVL in tokens that can be frozen, seized or paused: 73% Morpho, 53% Aave, 47% Compound V3, 0% Sky lending, 89% Maple), as one more
    term in a protocol's authority score, weighted by asset mix.
