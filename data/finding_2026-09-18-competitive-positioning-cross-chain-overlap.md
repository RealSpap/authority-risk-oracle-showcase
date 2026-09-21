# Finding (2026-09-18): four targeted competitive checks, not a repeat of the general scan

Requested directly: "cherche des nouveaux terrain que la concurrence couvre
pas pour l'oracle" (find new territory competition doesn't cover), after two
earlier, broader competitive scans this week already covered SolGov,
Hypernative/Blockaid, Gauntlet/Chaos Labs/LlamaRisk, DeFiSafety, ERC-8241,
RWA platforms, L2Beat's Stage rubric, Aave's internal governance levels,
restake.watch, and DORA/MiCA. This pass deliberately asked four NARROW,
falsifiable questions instead of repeating that general sweep, run as four
independent research agents. Pure research -- no scorer file or contract is
modified by this finding itself (the one concrete code change it led to,
extending `cross_ecosystem_overlap.py` to Tempo and Arbitrum, is a separate,
disclosed action documented in `README.md`'s "Cross-ECOSYSTEM signer
overlap" section, not silently bundled into this doc).

## Question 1: is "an on-chain score other contracts can call" already claimed?

Checked SolGov, L2Beat, Gauntlet, Hypernative, Blockaid, DeFiSafety, and
Credora/RedStone: all publish via dashboard, API, or a closed loop with one
specific protocol's own contracts -- none expose a generic, callable
on-chain score. Two real counter-examples exist for ADJACENT metrics, not
authority risk: Shentu's Security Oracle
(`getSecurityScore(address, string) -> uint8`, deployed on BSC at
`0xE7F15597B7594E1516952001f57d022bA799b479`, [GitHub](https://github.com/shentufoundation/security-oracle-smart-contracts))
scores code-audit confidence, appears dormant since 2021-2023. Chaos Labs'
Edge Risk Oracle pushes live market-risk parameter updates directly into
Aave's own Risk Stewards contract
([Chaos Labs](https://chaoslabs.xyz/posts/risk-oracles-real-time-risk-management-for-defi)),
but it's a closed loop between Chaos Labs and Aave specifically, not a
generic third-party-integrable primitive, and it scores market risk, not
admin-key/governance risk.

**Conclusion**: the architectural pattern (on-chain, contract-callable risk
score) is proven for adjacent metrics, so the idea itself isn't unclaimed --
but no one has shipped it for authority/governance risk as a generalized
primitive third parties can integrate against. `ExampleConsumer.sol`
demonstrates exactly that, in a real gap.

## Question 2: who has actually paid for authority-risk-adjacent data?

Checked DAO grant/treasury committees, DeFi insurance protocols, RWA
compliance/custody providers, and institutional risk desks. No documented
RFP or paid engagement found for admin-key/multisig/timelock assessment
specifically gating a DAO listing or grant (Aave pays Gauntlet/Chaos Labs
~$1.6-2.57M/yr, but for market/liquidation risk, not authority risk --
[Messari](https://messari.io/report/gauntlet-proposal-for-aave-protocol-risk-management-failure-and-future),
[Aave governance](https://governance.aave.com/t/chaos-labs-x-aave-dao-early-renewal-proposal/22346)).
RWA issuers (Ondo) pay for general smart-contract security audits (Cantina,
Zellic, FYEO, Cyfrin, Spearbit -- [Ondo audits](https://docs.ondo.finance/audits)),
not a distinct authority-risk product. Institutional desks (Fireblocks,
CertiK SkyInsights) sell bundled "security risk" products where
authority-risk isn't separately priced.

**The one clear, documented, recurring paid market found**: Sherlock prices
DeFi coverage premiums (protocols pay USDC per coverage period) using
research that explicitly includes "upgradability risks" and "emergency
mechanisms" as pricing inputs
([Sherlock docs](https://docs.sherlock.xyz/coverage/protocols/pricing)).
This is live money moving today, not a hypothetical DAO mandate -- the
closest real precedent for who would pay for this oracle's data as an
ongoing feed rather than a one-time report.

## Question 3: is cross-chain signer/committee overlap detection already covered by anyone?

The most consequential question, given KelpDAO's 2026-04-18 $292M exploit
(a 1-of-1 LayerZero DVN verifier -- see the dashboard's own incident panel).
Checked L2Beat's Stage framework, DeFiSafety, post-KelpDAO LayerZero-DVN
risk tooling specifically, and academic literature.

**No project found does systematic, at-scale, cross-chain signer-identity
overlap detection wired into a live score.** L2Beat's Stage framework scores
governance decentralization per-project; the Superchain Security Council's
shared multisig across OP-stack chains is self-disclosed, not discovered by
an automated cross-check
([L2Beat Stages](https://medium.com/l2beat/introducing-stages-a-framework-to-evaluate-rollups-maturity-d290bb22befe)).
Most tellingly: the tooling that emerged specifically IN RESPONSE to
KelpDAO -- a Dune/Defiant analysis finding 47% of ~2,665 LayerZero OApps run
1-of-1 DVN configs, and Blockaid's DVN-configuration auditor
([Dune/Defiant](https://thedefiant.io/news/security/dune-layerzero-oapp-dvn-security-analysis-1bklaq),
[Blockaid gist](https://gist.github.com/IdoBn/7753f16fdb6810b11c5c87cdf11f8aa0))
-- only checks `requiredDVNCount + optionalDVNThreshold <= 1` WITHIN a
single OApp. It has no logic comparing DVN operator identities ACROSS
different OApps or bridges. The exact failure class KelpDAO exposed
(concentrated verification authority) produced tooling that measures
threshold risk, never committee-overlap risk.

This project's own sister research, `multisig-overlap`
([GitHub](https://github.com/RealSpap/multisig-overlap-showcase)), already
does same-chain and cross-L2 signer-identity overlap at real scale (75
mainnet + 79 Superchain Safes, 6+ confirmed cross-protocol/cross-chain
cases). Nothing comparable in scale or systematicity turned up anywhere
else, for even the same-chain version of this check. Honest caveat: private
tooling at firms like Chainalysis, TRM Labs, or Forta Enterprise could do
this without public indexing -- not ruled out, just not found.

## Question 4: is there a real, uncontested chain/vertical white space?

Ranked candidates, most to least compelling:

1. **Payment/stablecoin-settlement L1s as a class** (Plasma, Tempo, Arc).
   These are standalone L1s, not Ethereum L2s, so L2Beat structurally
   excludes them (it only tracks chains deriving security from L1
   Ethereum -- confirmed against L2Beat's own tracked-projects list).
   Gauntlet/Chaos Labs activity found on these chains is app-level
   (e.g. Aave-on-Plasma lending-market risk), not chain-level
   validator/upgrade-key risk. All three publicly disclose currently
   centralized validator sets: Plasma launched with a small,
   Tether-aligned set; Tempo's testnet ran on four team-operated
   validators; Arc runs proof-of-authority among ~11 institutions where
   Circle can hold up to two-thirds of voting power
   ([Forkast on Arc](https://forkast.news/circle-arcs-validator-set-tells-you-who-will-control-the-next-settlement-layer/)).
   Real scale: Plasma DeFi TVL $600M-$1.7B through 2026; Tempo live since
   March 2026 off a $500M raise/$5B valuation; Arc's public mainnet opened
   2026-09-16 (two days before this research) with 100+ live apps
   including Aave, Morpho, Uniswap. **Tempo is already tracked by this
   project** -- the most immediately actionable of the three.
2. **Backed Finance / xStocks** (tokenized-equity issuer, ~58% market
   share of tokenized stocks, ~$60M-$438M TVL depending on measurement
   date). No public smart-contract audits or bug bounty found from any
   major firm, and no coverage found from L2Beat, DeFiSafety, Gauntlet,
   Chaos Labs, LlamaRisk, Hypernative, or Blockaid. Admin keys control
   mint/burn/pause via upgradeable proxies with no disclosed timelock.
   Distinct from and more open than Ondo Global Markets, which already
   has partial independent coverage (DeFiSafety notes, a Hindenrank "C"
   rating) -- Ondo should NOT be claimed as white space. Not yet acted
   on; a real candidate for a future scouting pass, not this one.
3. **Prediction markets as a scored category.** No provider treats this
   as a category. Real incidents exist (a March 2025 UMA
   governance-vote-concentration attack forcing a wrong $7M resolution;
   a May 2026 $700K Polymarket admin-wallet compromise), but the category
   itself remains uncovered by anyone, including this project. Weaker
   candidate than 1-2: fewer, smaller incidents, no single dominant
   protocol the way Backed/xStocks dominates tokenized equities.

**Honesty check on this list**: Robinhood Chain itself (the chain, not the
xStocks-style issuer layer) already has L2Beat bridge/rollup-risk coverage
(TVS ~$1.08B) -- not claimable as white space, a fact this research
confirmed rather than assumed.

## What this does NOT do

- Does not change any published score or scorer formula.
- Does not claim Question 3's finding rules out private/proprietary
  cross-chain-overlap tooling at large security firms -- explicitly
  disclosed as unchecked.
- Does not act on Question 4's #2/#3 candidates (Backed Finance/xStocks,
  prediction markets) -- flagged for a future pass, not scouted or
  implemented here.
- The one concrete action taken the same day as a direct result of this
  research (extending `cross_ecosystem_overlap.py` to Tempo and Arbitrum,
  and re-running it live) is documented separately in `README.md`, not
  bundled into this research finding.
