# Security policy

## What is in scope

- `src/AuthorityRiskOracle.sol`, the oracle contract, deployed on 8 EVM testnets (Robinhood Chain, Ethereum Sepolia, Arbitrum Sepolia, Base Sepolia, Tempo Moderato, Plasma, Monad, Hyperliquid HyperEVM). The live addresses are in the README.
- `src/ExampleConsumer.sol`, the reference consumer. A bug in reference code that gets copied into a real integration is a real bug.
- `chains/solana/program/`, the Anchor program on Solana devnet (program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`): the registry and the score accounts.

The off-chain scoring pipeline (`scripts/`, `chains/*/scorers.py`) and the watch job hold no funds and have no privileged on-chain role beyond the updater key. A wrong number there is a data-quality question: report it as a normal GitHub issue, with the evidence, and it will be answered in public.

## What is at stake today

Every deployment is on a testnet and the contracts hold no user funds. They are a publication point, not a custodian. The worst on-chain outcome of a bug is a wrong or manipulated score served to a consumer. The scores are published by one updater key with no timelock; that is disclosed on the dashboard and in the methodology, and it is the first thing a consumer should weigh.

## How to report a vulnerability

1. Preferred: a private GitHub security advisory on this repository (Security tab, "Report a vulnerability"). If that option is not available on the repository yet, use the next one.
2. A GitHub issue titled "Security report", with enough detail to reproduce. For anything that should not be public, say so in the issue without the details and a private channel will be arranged.

Please allow 14 days before public disclosure. You will get an answer within 72 hours.

## Severity

The Immunefi Vulnerability Severity Classification System (smart contracts table) is used as is.

| Severity | For these contracts |
|---|---|
| Critical | Bypassing the updater or admin role to push an unauthorized score; permanently breaking `getScore` or `isStale` for every target; any path by which a score account on Solana can be written by someone other than the registry's updater. |
| High | Griefing `updateScore` or `updateScores` so that legitimate updates cannot land, leaving stale data served as current without `isStale` saying so. |
| Medium | Unbounded gas in any read or write path; a tracked-targets list that becomes impractical to enumerate. |
| Low | A deviation from the documented behaviour that does not break a security guarantee. |

## Rewards

There is no funded bug bounty programme today. A genuine finding is acknowledged publicly, with credit, and a modest reward is at the maintainer's discretion: it is a testnet, hackathon-stage project and it says so. If a funded programme opens later, it will be linked here.
