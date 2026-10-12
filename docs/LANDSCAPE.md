# How this compares

Who else looks at authority risk, what they do better, and where this project is still thin. Facts as of 2026-09-17 to 2026-10-05.

The side-by-side comparison with the neighbouring tools has one source and one page: [realspap.github.io/oracle/compare](https://realspap.github.io/oracle/compare/).

The closest open-source scanner on the same question is [Hermes](https://github.com/saintparish4/hermes) (Rust, MIT, created 2026-08-17): it ranks upgrade authorities on Base and Ethereum from ERC-1967 storage slots, following Safe signers, timelocks and AccessControl role holders (role holders only when its index lists them, per its README), and answers "which proxies does a compromise of this key reach". It is a local tool and not an on-chain feed.

The conflict of interest when the rater is paid by the protocol it rates (Gauntlet, Chaos Labs, LlamaRisk) is not theoretical: the earlier research program this project grew out of
(`defi-admin-key-risk`) documented it in real incidents. And
[ERC-8241 "Protocol Control Disclosure"](https://paragraph.com/@0x0afe5e054249b19ae29075540d9e6951c66e49b7/making-the-case-for-erc-8241-protocol-control-disclosure)
(draft) standardizes exposing raw authority facts and leaves scoring to "external interpretation layers". This project is that layer.

## Closest precedent: SolGov

SolGov, built after the $285M Drift exploit, tracks 50 Solana protocols across 63 multisigs and 180+ programs: multisig
threshold, timelock delay, role separation, verified builds, key rotation. It is the strongest outside evidence that the thesis
is right: someone else independently hit the same gap and shipped a live product for it, on one ecosystem. This project
re-derived the same founding incident from the on-chain transactions, and also scored Drift's current, reformed authority
([backtest](../data/backtest_2026-09-17-drift-protocol-security-council-compromise.md)).

What SolGov does not do:

1. **It is a website, not a contract.** No lending market or DAO can call a SolGov score the way
   [`ExampleConsumer.sol`](../src/ExampleConsumer.sol) calls `getScore()` here.
2. **Solana only.** Authority risk is not ecosystem-specific; the same Safe and the same signers sit behind protocols on several chains.
3. **No cross-protocol signer overlap.** SolGov's columns are per protocol on one chain. `crossExposureScore` checks whether the same
   committee sits behind two protocols listed as independent, on one chain or across chains (first caught live on the Aave V3
   guardian Safe shared by Arbitrum and Base: [finding](../data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md)).

What SolGov does better, stated plainly: its safety benchmark columns (verified builds, nonce detection, hardware wallets, key
rotation, insurance fund, treasury segmentation) are a concrete signal list this project does not fully check on Solana yet
(26 Solana targets scored and published on-chain). It is a real open gap, not a completed step.

## Closest governance precedent: Aave x LlamaRisk

Chaos Labs stepped down from Aave risk management in April 2026. LlamaRisk has since run Aave's PT oracle and, in June 2026, got
a binding four-layer risk framework adopted that governs every asset listing, review and deprecation across Aave V3, V4 and
Aave Horizon. Two parts matter here: Layer 1 makes **undisclosed signer composition a hard-block condition** for listing an asset,
and Layer 3 requires "monitoring and automated risk-oracle systems ... codified as standing protocol infrastructure, not
optional tooling".

A major protocol's own risk manager arrived independently at close to this project's thesis. What it is not: Layer 3 names no
vendor or tool, and by LlamaRisk's own reporting the oracle is run manually, not as a live, on-chain, cross-protocol feed that
anyone can compose with. That gap, a governance-mandated checklist item enforced by votes and a paid risk manager versus a
permissionless score any contract can read, is where this project sits. If LlamaRisk or anyone turns that process into a named,
live, on-chain authority-risk oracle, that is a direct competitor; nothing found as of 2026-10-05 does.

## On-chain scores for adjacent metrics

- **Shentu Security Oracle** (`getSecurityScore(address, string)`, BSC): scores code-audit confidence, appears dormant since 2021-2023.
- **Chaos Labs Edge Risk Oracle**: pushes market-risk parameters into Aave's Risk Stewards, a closed loop between one provider and one protocol.
- **LlamaGuard PT**: on-chain, collateral risk, paid by the protocol. This project's contract was reviewed against it
  ([review](../data/contract_review_2026-09-17-llamaguard-comparison.md)).

Longer competitive passes, each with its sources and what it changed:
[`data/finding_2026-09-18-competitive-positioning-cross-chain-overlap.md`](../data/finding_2026-09-18-competitive-positioning-cross-chain-overlap.md),
[`data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`](../data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md),
[`data/finding_2026-09-18-erc8241-compatibility-evaluation.md`](../data/finding_2026-09-18-erc8241-compatibility-evaluation.md).
