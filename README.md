<p align="center">
  <img src="docs/assets/logo.svg" width="96" alt="Authority Risk Oracle logo">
</p>

<h1 align="center">Authority Risk Oracle</h1>

<p align="center"><b>Who can really move a DeFi protocol's funds? Read the answer on-chain, and check it yourself.</b></p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <a href=".github/workflows/test.yml"><img alt="Tests" src="https://github.com/RealSpap/authority-risk-oracle-showcase/actions/workflows/test.yml/badge.svg"></a>
  <a href=".github/workflows/watch.yml"><img alt="Watch" src="https://github.com/RealSpap/authority-risk-oracle-showcase/actions/workflows/watch.yml/badge.svg"></a>
  <a href=".github/workflows/mutation.yml"><img alt="Mutation" src="https://github.com/RealSpap/authority-risk-oracle-showcase/actions/workflows/mutation.yml/badge.svg"></a>
  <img alt="Ecosystems" src="https://img.shields.io/badge/ecosystems-10-informational">
  <a href="https://realspap.github.io/oracle/"><img alt="Targets read by the watch" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FRealSpap%2Fauthority-risk-oracle-showcase%2Fwatch-data%2Fbadge.json"></a>
  <img alt="Network" src="https://img.shields.io/badge/deployed-testnets-orange">
  <a href="watch/API.md"><img alt="Watch integrity" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FRealSpap%2Fauthority-risk-oracle-showcase%2Fwatch-data%2Fbadge%2Fintegrity.json"></a>
</p>

A DeFi contract that can be upgraded or reconfigured has someone who can do it: a key, a multisig, a vote. This project reads from public chain state who that is, how fast they can act and what stands in the way (keys, a multisig, a timelock), and publishes the answer as a score that any contract can read on-chain, so a lending market, a DAO or a wallet does not have to trust anyone's website. It measures exposure, not the chance of an attack: we read 55 incident write-ups, 7 were about who controls a contract, and our published requirements flagged 2 of them ([what the score says and does not say](docs/WHAT-THE-SCORE-SAYS.md)). Live on testnets today. Not an audit, not investment advice.

## Three commands

**1. Check our numbers against the chain** (no key, public RPCs, about ten seconds). The script reads the chain with its own code, separate from the Watch's, so a difference is worth checking. Output of the run of 22 October 2026:

```bash
git clone https://github.com/RealSpap/authority-risk-oracle-showcase && cd authority-risk-oracle-showcase
python3 scripts/prove.py
```

```text
OK         8 oracles: targets per oracle on the chain = Watch (63 + 39 + 13 + 13 + 14 + 9 + 9 + 16)
OK         176 targets: six sub-scores, push date and methodology hash identical on the chain and in the Watch
OK         Solana (devnet): 26 accounts read, scores and hash identical to the Watch's
OK         8 EVM oracles: methodology hash, target count and push date = CHANGELOG (1 target(s) keep an older hash, which the CHANGELOG says)
OK         README example: getScore(0x1f7d…2efa) = 80, 100, 75, 100, 80, 85
OK         api/scores.json = the chain (63 Robinhood targets)
OK         back-test: 55 incidents read, 7 are about who controls a contract: 2 flagged, 2 missed, 3 not measurable; rate 2/7 flagged (2/4 of the measurable cases)
OK         Authority Facts v0.1: 202 JSON twins of the site conform (conformance.py)
8 OK, 0 DIFFERENCE, 0 UNREAD in 3 s. Does not prove: that the scores are right, that they predict an incident, that the oracles' administrator keys are safe.
```

**2. Read a score from the chain** (needs [Foundry](https://getfoundry.sh); Robinhood Chain testnet, a tracked Uniswap v3 factory):

```bash
cast call 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \
  "getScore(address)(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)" \
  0x1f7d7550B1b028f7571E69A784071F0205FD2EfA \
  --rpc-url https://rpc.testnet.chain.robinhood.com/rpc
# adminKey, multisig, timelock, oracleAuthority, crossExposure, composite, lastUpdated, methodologyHash
# 80, 100, 75, 100, 80, 85, 1792448928, 0x7a8280d6...   (read live on 2026-10-22; the last two values change at every push)
```

**3. Gate a decision on a label in 14 lines:**

```bash
python3 integrations/authority_facts_gate.py https://realspap.github.io/oracle/p/robinhood-0x1f7d7550b1b028f7571e69a784071f0205fd2efa.json
```

## Two ways in

| If you decide: delegates, risk managers, DAO committees | If you build: developers, integrators |
|---|---|
| 1. Open the [dashboard](https://realspap.github.io/oracle/): 202 contracts on 9 chains, the money behind them where one was read, the delay before a change applies. | 1. Read a score from a contract: `getScore(address)` and `isStale(address)`, as in command 2 ([`ExampleConsumer.sol`](src/ExampleConsumer.sol)). |
| 2. Read [one contract's label](https://realspap.github.io/oracle/p/robinhood-0x1f7d7550b1b028f7571e69a784071f0205fd2efa.html): who can move it, how many keys, how long everyone else has to react, what was not read. The format is open: [Authority Facts v0.1](docs/AUTHORITY-FACTS-SPEC.md). | 2. Gate on a label in 14 lines (command 3): [`integrations/authority_facts_gate.py`](integrations/authority_facts_gate.py). |
| 3. Follow a protocol on every chain: one Atom feed per protocol, or, after `bash scripts/watch_branch.sh prepare` (it fetches the Watch's data), `python3 scripts/brief.py morpho-blue` for a one-page brief. | 3. Put it in CI: `uses: RealSpap/authority-risk-oracle-showcase@main` with `chain`, `address`, `min-score` ([`action.yml`](action.yml)), or an agent through the local MCP server. |

## Everything else

[Reference](docs/REFERENCE.md) (what it scores, deployed oracles, how it works, limits) · [All the tools](docs/TOOLS.md) · [Methodology](METHODOLOGY.md) · [How it compares](docs/LANDSCAPE.md) · [Operate it](docs/OPERATIONS.md) · [What a score says and does not say](docs/WHAT-THE-SCORE-SAYS.md)

The score reads **exposure**, how much one compromise can do. It does not predict who gets hit. Submitted to Colosseum's [Crypto World's Fair](https://colosseum.com/worldsfair) on 12 October 2026. MIT licence.
