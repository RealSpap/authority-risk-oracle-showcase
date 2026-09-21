# Business plan

## The market this sits in, with real numbers

DAOs already pay real, recurring money for live, on-chain risk infrastructure --
this isn't a hypothetical category:

- Aave paid Chaos Labs up to **$3M/year** for continuous risk management (a 3-year
  engagement, terminated by Chaos Labs itself in April 2026, citing the fee as
  unsustainable even at that size -- not a sign of weak demand, a sign the market is
  large enough that even a $3M/year contract was contested on *price*).
- Curve DAO voted, **2026-09-02**, a 12-month mandate to yRisk worth **~$250k/year**
  (125,000 frxUSD + 568,181 CRV) for "risk assessment and ongoing monitoring" on
  crvUSD, PegKeepers, and Llamalend -- confirmed via a real, dated, on-chain governance
  vote (621M veCRV for, 5 against), not a press release.
- LlamaRisk's **LlamaGuard PT**, built on Chainlink CRE, is exactly this project's
  target operating model already proven out in production: an automated oracle that
  pushes risk parameters on-chain, with LlamaRisk holding only an "Updater" role while
  Aave governance keeps ownership of every contract. It covers **collateral risk**
  (Pendle PT pricing). Nothing equivalent exists yet for **authority risk**.
- The strongest new evidence the thesis is right, not just plausible: LlamaRisk (which
  took over Aave's risk management after Chaos Labs stepped down, above) got a binding
  four-layer risk framework adopted in **June 2026** that now governs every asset
  listing/review/deprecation across Aave V3, V4 and Aave Horizon -- already enforced,
  Aave dropped six chains under it by end of July 2026. Layer 1 makes **undisclosed
  signer composition a hard-block condition** for listing at all; Layer 3 requires
  "automated risk-oracle systems... codified as standing protocol infrastructure, not
  optional tooling." No vendor or tool is named for Layer 3, and LlamaRisk is running
  it **manually** per its own reporting -- a governance-mandated checklist enforced by
  a paid risk manager, not a live on-chain feed any third-party contract can read. This
  project sits exactly in that gap.

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
(draft, active discussion on Ethereum Magicians) standardizes exposing *raw* authority
facts -- who controls what, what powers they have, what delay protects a given action
-- and explicitly declines to include any score or trust rating, leaving that to
"external interpretation layers." This project is exactly that layer: the standard
defines the facts, this oracle turns them into a number a contract can act on.

## Honest state of demand today

No insurer or institution was found publicly paying for a continuous authority-risk
feed specifically (checked directly: Nexus Mutual, Sherlock, InsurAce, Chainproof
governance forums and docs -- nothing). Steakhouse Financial, a real curator already
active on Robinhood Chain, documents doing exactly this kind of monitoring **manually,
internally** for the vaults it allocates to -- a real, confirmed need, not yet
outsourced or automated by anyone. That's the honest gap between "clearly needed" and
"someone already pays for it": this is a bet on latent demand backed by a strong
comparable (yRisk/Curve), not a signed contract.

## Path to a real product

1. **Prove coverage where nobody else has bothered** (this hackathon build): score
   real authority risk on Robinhood Chain, a 2.5-month-old chain with real TVL
   (~$920M, DefiLlama live, corrected 2026-09-17 -- was cited as $1.3-1.4B, a
   ~30% overstatement caught in an internal audit) and zero existing independent
   risk tooling -- the same "be first"
   pattern this research program has used before (multisig-overlap, defi-admin-key-risk).
2. **Extend to a chain with an active governance-mandate market**: Arbitrum, Base, or
   Ethereum L1, where Aave/Curve-style RFPs already exist and a track record on
   Robinhood Chain becomes the credibility proof for a real proposal.
3. **Pitch the yRisk/Curve model directly**: a DAO forum post + governance proposal
   offering continuous authority-risk monitoring as a paid mandate, priced well under
   the $250k/year Curve precedent to start, with the oracle's own on-chain history as
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
