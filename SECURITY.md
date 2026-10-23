# Reporting an error or a security issue

Thank you for taking the time. Every deployment here is on a testnet and the contracts hold no user funds: this repository is a publication point, not a custodian. Most reports are about a number or a statement that may be wrong, and those are welcome.

## How to reach us

- **Privately**, for anything that should not be public (a vulnerability, a fix still in progress, a secret committed by mistake, a correction you would rather not discuss in the open): write to contact@realspap.com and put `authority-risk-oracle-showcase` in the subject. If the Security tab of this repository offers it, a private GitHub security advisory ("Report a vulnerability") works as well.
- **Publicly**: open a GitHub issue on this repository.

## What is in scope

- `src/AuthorityRiskOracle.sol`, the oracle contract, deployed on 8 EVM testnets (Robinhood Chain, Ethereum Sepolia, Arbitrum Sepolia, Base Sepolia, Tempo Moderato, Plasma, Monad, Hyperliquid HyperEVM). The live addresses are in the README.
- `src/ExampleConsumer.sol`, the reference consumer. A bug in reference code that gets copied into a real integration is a real bug.
- `chains/solana/program/`, the Anchor program on Solana devnet (program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`): the registry and the score accounts.

The off-chain scoring pipeline (`scripts/`, `chains/*/scorers.py`) and the watch job hold no funds and have no privileged on-chain role beyond the updater key. A wrong number there is a data-quality question: report it as a normal GitHub issue, with the evidence, and it will be answered in public.

## What is not in scope

- The contracts and systems of the projects named here. If you found a flaw in one of them, please report it to that team through its own channel.
- Opinions on prices, tokens or investments. This is independent research, not a security audit and not advice.

## What is at stake today

Every deployment is on a testnet and the contracts hold no user funds. They are a publication point, not a custodian. One direct effect of a bug is a wrong or manipulated score served to a consumer, and a consumer should treat a score as one input. The scores are published by one updater key with no timelock; that is disclosed on the dashboard and in the methodology, and a consumer should weigh it before relying on a score.

## What to include

The place concerned, the statement or score you dispute, and whatever supports your reading that anyone can re-read: a transaction hash, a block number, an address with the call to make, a code reference or a public document.

## What happens next

- Reports are read as time allows; replies are best effort, with no promised delay.
- Corrections are made in public, in the files themselves; a change of method is written in [CHANGELOG.md](CHANGELOG.md) with its date.
- When a report concerns an issue that is not yet fixed, the relevant detail is withheld from this repository until the team concerned has had the chance to fix it.
- Credit is given on request. There is no funded bug bounty programme (see Rewards below).

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

This file covers the content of this repository only. The author does not act for, or speak on behalf of, any project named here.
