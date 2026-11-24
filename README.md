# Authority Risk Oracle

**Who can really move a DeFi protocol's funds? Read the answer on-chain, and check it yourself.**

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-blue)](LICENSE) [![Code: MIT](https://img.shields.io/badge/Code-MIT-blue)](LICENSE-CODE) [![Tests](https://github.com/RealSpap/authority-risk-oracle-showcase/actions/workflows/test.yml/badge.svg)](.github/workflows/test.yml) [![Watch](https://github.com/RealSpap/authority-risk-oracle-showcase/actions/workflows/watch.yml/badge.svg)](.github/workflows/watch.yml)

A DeFi contract that can be upgraded or reconfigured has someone who can do it: a key, a multisig, a vote. I read from public chain state who that is, how fast they can act and what stands in the way (keys, a multisig, a timelock), and publish the answer as a score that any contract can read on-chain. It measures exposure, not the chance of an attack. Live on testnets today. Not an audit, not investment advice.

**Don't trust me. Redo it.** Command 1 re-reads the chain and compares it with what I publish: no key, public RPCs, under a minute. A line may say UNREAD when a public node is silent: that is not a failure of the check, it is the check saying it could not read.

## Three commands

**1. Check my numbers against the chain.**

```bash
git clone https://github.com/RealSpap/authority-risk-oracle-showcase && cd authority-risk-oracle-showcase && python3 scripts/prove.py
```

Every line says OK, DIFFERENCE or UNREAD. It does not prove that the scores are right, that they predict an incident, or that the oracles' administrator keys are safe.

**2. Read a score from the chain** (needs [Foundry](https://getfoundry.sh)). The oracle is on Robinhood Chain testnet (chain ID 46630); the contract it scores here is on Robinhood Chain mainnet (chain ID 4663):

```bash
# oracle 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 on Robinhood Chain testnet (chain ID 46630)
# target 0x1f7d7550B1b028f7571E69A784071F0205FD2EfA on Robinhood Chain mainnet (chain ID 4663)
cast call 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \
  "getScore(address)(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)" \
  0x1f7d7550B1b028f7571E69A784071F0205FD2EfA \
  --rpc-url https://rpc.testnet.chain.robinhood.com/rpc
# adminKey, multisig, timelock, oracleAuthority, crossExposure, composite, lastUpdated, methodologyHash
# the values change at every push: read the current ones for this target in api/scores.json, they must equal what the chain returns
```

**3. Gate a decision on a label**, with an age limit and the strict mode:

```bash
python3 integrations/authority_facts_gate_strict.py https://realspap.github.io/oracle/p/robinhood-0x1f7d7550b1b028f7571e69a784071f0205fd2efa.json --max-age-hours 72 --strict
# label of a Uniswap v3 factory on Robinhood Chain mainnet (chain ID 4663)
```

This command is expected to end with a refusal (exit 1): the label says it did not read how many keys it takes to move this contract, and `--strict` refuses a label that lists anything it did not read. A refusal is a message, not a score, and not a failure of the command.

The label is that same Uniswap v3 factory on Robinhood Chain mainnet (chain ID 4663).

- **A score is not a status.** A contract can score 100 and be `UNVERIFIED`, and none of these commands reads the status: [details](docs/LIMITS.md#a-score-is-not-a-status).
- **The composite on the chain is not the cap.** For Robinhood Chain rollup contracts, `l1CappedComposite` (lower than the on-chain composite of command 2, both in `api/scores.json`) is published in `api/scores.json` only: [details](docs/LIMITS.md#the-composite-on-the-chain-is-not-the-cap).
- **One key can replace the Solana devnet program.** Its upgrade authority is a plain account (`BcwteMtYL5wL8dvMYWedPT2V6oh1hTgd8vgKEkQyy9yx`), so one signature can push the scores and replace the program: [replay](docs/LIMITS.md#who-can-replace-the-oracle-itself).

## Two ways in

| If you decide | If you build |
|---|---|
| Open the [dashboard](https://realspap.github.io/oracle/): 202 contracts on 9 oracles (8 EVM testnets and Solana devnet), each record names its network | Read a score: `getScore(address)` and `isStale(address)`, see [src/ExampleConsumer.sol](src/ExampleConsumer.sol) |
| Read one contract's label (the Uniswap v3 factory on Robinhood Chain mainnet, chain ID 4663; [page](https://realspap.github.io/oracle/p/robinhood-0x1f7d7550b1b028f7571e69a784071f0205fd2efa.html)): who can move it, how many keys, how long everyone else has to react | Gate on a label: [integrations](integrations); the open format is [Authority Facts v0.1](docs/AUTHORITY-FACTS-SPEC.md) |
| Follow a protocol: one Atom feed per protocol | Put it in CI with [action.yml](action.yml), or use the local MCP server in [packages](packages) |

## Everything else

[Reference](docs/REFERENCE.md) · [Methodology](METHODOLOGY.md) · [What a score says and does not say](docs/WHAT-THE-SCORE-SAYS.md) · [Limits](docs/LIMITS.md) · [How it compares](docs/LANDSCAPE.md) · [Data contract](watch/API.md) · [History of this repository](docs/HISTORY.md)

The history of this repository was rewritten on 30 September 2026, and every commit up to 6 October 2026 is a snapshot or carries a round time, so the dates of these commits prove nothing. [docs/HISTORY.md](docs/HISTORY.md) says what can still be checked.

## Help

Propose a target, dispute a score, report a reading error: use the issue forms, see [CONTRIBUTING](CONTRIBUTING.md). Security reports: [SECURITY](SECURITY.md). Cite with [CITATION.cff](CITATION.cff).

## Licences

| What | Licence | File |
|---|---|---|
| Code: `scripts/`, `chains/`, `src/`, tests and workflows | MIT | [LICENSE-CODE](LICENSE-CODE) |
| The MCP package (`packages/authority-risk-mcp`) | MIT, with its own license file | [packages/authority-risk-mcp/LICENSE](packages/authority-risk-mcp/LICENSE) |
| The Watch files (`watch/`, the `watch-data` branch) | CC BY 4.0 | [LICENSE](LICENSE) |
| The share pages and their JSON twins (`/oracle/p/`) | CC BY 4.0 | [LICENSE](LICENSE) |
| Notes, METHODOLOGY and the other texts | CC BY 4.0 | [LICENSE](LICENSE) |
| Datasets (`data/`, the score history) | CC BY 4.0 | [LICENSE](LICENSE) |
| The specification text in `docs/` | CC0, as the document itself says | the document |

Attribution for data and text: "Authority Risk Oracle, realspap.github.io/oracle" with a link. Earlier copies were released under the MIT licence.

**Signing key of the Watch** (Ed25519, public): `11baca3ef6a69de4901c185f6cbbd3f93318fbb74f9961a8d39aead841adf409`. The same key is written in [`watch/API.md`](watch/API.md), in `scripts/audit_public.py` and on [realspap.github.io/oracle/provenance/](https://realspap.github.io/oracle/provenance/); compare the copies, then check a run with `python3 scripts/audit_public.py`. A key change would be announced first (see [KEY-ROTATION](docs/KEY-ROTATION.md)).
