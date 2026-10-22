# Business plan

## The market this sits in, with real numbers

DAOs already pay real, recurring money for live, on-chain risk infrastructure --
this isn't a hypothetical category:

- Aave pays outside providers for continuous risk management. Chaos Labs served as
  Aave's risk provider from November 2022 and announced its exit on 6 April 2026.
  According to press reports (CoinCentral, Unchained), its 2025 budget was about **$3M**
  (CoinCentral), Aave Labs offered $5M to keep it (CoinCentral; Unchained mentions a $5M renewal proposal), and Chaos said
  it needed at least $8M for V3 and V4 (Unchained); Chaos Labs' own departure message was
  not read. The accounts of the exit differ: according to press reports, Chaos Labs cited
  unprofitable economics, the V4 workload and a disagreement over risk priorities;
  according to Unchained, Aave had declined to grant Chaos exclusive-provider status.
- Curve DAO on-chain vote 1492 opened on **2026-08-26** and closed and was executed on
  **2026-09-02**: a 12-month mandate to yRisk for risk assessment and monitoring of
  crvUSD mint markets and Llamalend isolated markets, plus recommendations on PegKeeper
  limits. A press report (crypto.news) gives the requested annual budget as approximately
  **$250,000**.
  The vote approved two revocable one-year vesting streams, 125,000 frxUSD and 568,181
  CRV, about $336k at the CRV price that day (0.371 USD on 2 September, CoinGecko). Set
  against the requested $250k, the CRV leg corresponds to about 0.22 USD per CRV (our
  arithmetic). It was a real, dated, on-chain
  governance vote (621.17M veCRV for, 5.33 veCRV, essentially zero, against; 20 votes), not
  a press release.
- LlamaRisk's **LlamaGuard PT**, built on Chainlink CRE, is this project's target
  operating model running in production: an automated oracle that pushes risk
  parameters on-chain, owned by Aave governance, with LlamaRisk holding a bounded
  parameter-tuning role. It covers **collateral risk** (Pendle PT pricing). In what was
  read, nothing equivalent exists yet for **authority risk**.
- A related signal from Aave governance: LlamaRisk proposed a four-layer risk framework
  to Aave governance in June 2026 (announced 9 June, after the KelpDAO exploit; Unchained),
  for asset listing, review and deprecation across Aave V3, V4 and Aave Horizon. One
  October 2026 newsletter (Alea Research) says that Aave put a framework in place in August
  2026, without saying which; no vote date or tally was read. On 31 July 2026 Cointelegraph
  reported that LlamaRisk recommended winding down Aave V3 on six chains (Sonic, Scroll,
  zkSync, Metis, Soneium, Aptos); the plan needed a community vote, and it is not verified
  that it passed or was executed. Press coverage (Bitget, CoinCentral) lists undisclosed
  signer structures among Layer 1 hard blocks (not checked in the original text). Per
  Unchained, Layer 2 sets a mandatory baseline of at least three independent verifiers
  and Layer 3 covers monitoring and automated risk oracle systems; the framework also
  codifies two automated mechanisms, a freeze guardian and a supply and borrow cap oracle,
  built on Chainlink CRE and owned by the Aave DAO. Separately, LlamaRisk's LlamaGuard PT
  (Pendle PT pricing, a separate proposal per The Defiant) already runs as an automated
  oracle. In what was read, none of these is a
  live on-chain feed of administrator authority that a third-party contract can read. This
  project sits in that gap.

That's the gap: every live, paid, on-chain risk oracle found in this market covers
market/collateral risk (prices, liquidity, LTV). None covers admin-key concentration,
multisig weakness, timelock delay, or oracle-signer authority as a continuous,
on-chain, independently-computed product. The closest existing offerings --
Hypernative, Blockaid -- sell this as a closed enterprise dashboard, not a composable
on-chain primitive, and Gauntlet/Chaos Labs/LlamaRisk are paid *by the protocol they
rate*, the same conflict of interest this project's own prior research
(`defi-admin-key-risk`) documented in a real incident (Wasabi Protocol, $5.9M lost,
2026).

## Where this fits: the gap a real emerging standard leaves open

[ERC-8241 "Protocol Control Disclosure"](https://paragraph.com/@0x0afe5e054249b19ae29075540d9e6951c66e49b7/making-the-case-for-erc-8241-protocol-control-disclosure)
(a draft; not in the ethereum/ERCs repository as of 22 October 2026) standardizes exposing *raw* authority
facts -- who controls what, what powers they have, what delay protects a given action
-- and explicitly declines to include any score or trust rating, leaving that to
"external interpretation layers." This project is exactly that layer: the standard
defines the facts, this oracle turns them into a number a contract can act on.

## Honest state of demand today

No insurer or institution was found publicly paying for a continuous authority-risk
feed specifically (checked directly: Nexus Mutual, Sherlock, InsurAce, Chainproof
governance forums and docs -- nothing; not re-verified on 22 October 2026). Steakhouse Financial, a real curator already
active on Robinhood Chain, documents doing exactly this kind of monitoring **manually,
internally** for the vaults it allocates to (not re-verified on 22 October 2026) -- a need it
documents, not outsourced or automated in what was read. That's the honest gap between "clearly needed" and
"someone already pays for it": this is a bet on latent demand backed by a strong
comparable (yRisk/Curve), not a signed contract.

## Path to a real product

1. **Prove coverage where independent tooling was not found** (this hackathon build): score
   real authority risk on Robinhood Chain, a 2.5-month-old chain with real TVL
   (~$920M, DefiLlama live, corrected 2026-09-17 -- was cited as $1.3-1.4B, a
   ~30% overstatement caught in an internal audit) and no existing independent
   risk tooling found -- the same early-mover
   pattern this research program has used before (multisig-overlap, defi-admin-key-risk).
2. **Extend to a chain with an active governance-mandate market**: Arbitrum, Base, or
   Ethereum L1, where Aave/Curve-style RFPs already exist and a track record on
   Robinhood Chain becomes the credibility proof for a real proposal.
3. **Pitch the yRisk/Curve model directly**: a DAO forum post + governance proposal
   offering continuous authority-risk monitoring as a paid mandate, priced well under
   the Curve precedent (about $250k requested for the year, per a press report) to start, with the oracle's own on-chain history as
   the evidence of reliability (not a claim -- a `getScore()` call anyone can run).
   First retroactive proof point already built: Wasabi Protocol's real $5.9M
   deployer-key compromise (2026-04-30) resolves, live-verified today, to the exact
   same bare-EOA-no-Safe-no-timelock shape this project's formula already scores at
   1/100 for its worst currently-tracked targets -- same formula, real incident,
   `compositeScore = 2/100` (`data/backtest_2026-09-17-wasabi-protocol.md`).
4. **Consumer-side integration**: pitch lending protocols directly on using
   `getScore()`/`isStale()` to gate collateral factors automatically (as
   `ExampleConsumer.sol` demonstrates) -- this is the actual product-market fit test,
   since a protocol integrating the oracle on-chain is a much stronger signal than a
   DAO paying for a dashboard.

## What doesn't change the plan

This is deliberately not a token, not a DAO, not a fundraise. The ask, if this
progresses past the hackathon, is the same shape as yRisk's: a governance mandate paid
in the consuming protocol's own treasury assets, not external capital raised up front.
