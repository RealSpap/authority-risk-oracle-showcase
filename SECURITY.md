# Security policy

## Scope

- [`src/AuthorityRiskOracle.sol`](src/AuthorityRiskOracle.sol) -- the oracle contract.
- [`src/ExampleConsumer.sol`](src/ExampleConsumer.sol) -- reference consumer, ships as
  part of this repo and is in scope for the same reason: a bug in reference code that
  gets copied into a real integration is a real bug.
- The off-chain scoring pipeline (`scripts/`) is **out of scope** for a funds-at-risk
  bounty (it holds no funds and has no privileged on-chain role of its own beyond
  `UPDATER_ROLE`, already covered above) -- report data-integrity bugs there as a
  normal GitHub issue or a private security advisory (see below), not a paid finding.

Currently deployed on [Robinhood Chain Testnet](https://explorer.testnet.chain.robinhood.com)
only (see `README.md`'s "Status" section for the live address) -- **no real user funds
are held by this contract today**. It is a publication point, not a custodian: the
worst-case on-chain impact of a bug here is a wrong or manipulated *score* being
served to a consumer, not a direct fund drain from this contract itself. Reward tiers
below are set accordingly, and are explicitly disclosed as modest for that reason, not
hidden behind a vague "case by case" answer.

## Reporting a vulnerability

**Preferred, no account needed anywhere**: open a private GitHub Security Advisory
on this repo (Security tab -> Advisories -> "Report a vulnerability"). GitHub's own
advisory flow keeps the report private between you and the maintainer until a fix
ships, and doesn't require sharing an email address or setting up a bounty-platform
account first. **Checked live 2026-09-17**: this feature (private vulnerability
reporting) is **not yet enabled** on this repo (`GET
/repos/{owner}/{repo}/private-vulnerability-reporting` returns 404) -- toggle it on
under Settings -> Security -> "Private vulnerability reporting" before relying on
this path; not done automatically by this pass since it's a repo settings change,
not a docs change. Until then, open a normal (public, since this repo is private
and only invited collaborators can see it anyway) GitHub issue instead.

**Funded bug bounty (Immunefi)**: a formal program with real, immunefi.com-escrowed
rewards is planned but **not live yet** as of 2026-09-17 -- funding and account setup
are still pending on the maintainer's side. Once live, it will be linked here and on
[immunefi.com](https://immunefi.com). Until then, report through the GitHub advisory
above; a retroactive reward for a genuine finding reported before the program formally
launches is at the maintainer's discretion, not guaranteed.

## What counts as in scope, and severity (Immunefi Vulnerability Severity
Classification System v2.3, Smart Contracts table -- adopted as-is rather than
inventing a bespoke scale)

| Severity | What it means for THIS contract |
|---|---|
| **Critical** | Bypassing `UPDATER_ROLE`/`DEFAULT_ADMIN_ROLE` access control to push an unauthorized score; permanently bricking `getScore()`/`isStale()` for every target; any path that lets `updateScore()`/`updateScores()` write a score outside the documented 0-100 range despite the `ScoreOutOfRange` check added 2026-09-17 (see `data/contract_review_2026-09-17-llamaguard-comparison.md` for why that specific class of bug is treated as Critical here -- it directly caused a ~196% collateral factor in `ExampleConsumer.sol`'s own math before the fix). |
| **High** | A way to grief `updateScore()`/`updateScores()` so legitimate updates can't land (e.g. an unbounded-gas griefing vector in `_updateScore()`), leaving stale data being served as if current without `isStale()` catching it. |
| **Medium** | Gas griefing, unbounded gas consumption in any view/write path, `trackedTargets` array growth that becomes impractically expensive to enumerate. |
| **Low** | Anything that doesn't compromise a security guarantee but deviates from documented behavior. |

Out of scope by design, not oversight: the OFF-CHAIN methodology's correctness (is a
given protocol's `adminKeyScore` the right number?) is a data-quality question, not a
smart-contract vulnerability -- see `METHODOLOGY.md`'s own Limitations section, and
report those as a normal GitHub issue instead.

## Suggested reward tiers (draft, not yet funded)

Deliberately modest, reflecting the contract's actual current stakes (testnet, no
custodied funds, hackathon-stage project), not copied from a large, live DeFi
protocol's bounty table:

| Severity | Suggested reward |
|---|---|
| Critical | $500-$2,000 |
| High | $200-$500 |
| Medium | $50-$150 |
| Low | Public acknowledgment |

These are a starting proposal for the maintainer to fund and adjust, not a live,
binding commitment -- confirm the actual funded amounts on the live Immunefi program
page once it exists, not this file.
