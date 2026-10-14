# Authority Risk Oracle for AI agents

Four read-only questions an agent asks before it depends on a contract, in three forms: an MCP server, LangChain tools, and a Coinbase AgentKit action provider. They read the published files of the Watch. They send no transaction, need no account and no key.

| Tool | Question |
|---|---|
| `getScore` / `get_authority_score` | the score of one contract, where and when it was read, a `cast call` to replay the reading |
| `listTargets` / `list_authority_targets` | the tracked contracts under or over a score, weakest first |
| `whoControls` / `who_controls_contract` | who can change the contract and how fast |
| `checkProtocol` / `check_protocol_authority` | a protocol on every chain it is tracked on, with a verdict |

Every answer is JSON with a `status`:

- `ok`: the answer is read.
- `not_tracked`: the Watch does not track this contract. That says nothing about its safety.
- `not_read`: a file the answer needs is missing, or the value could not be read.

A value the Watch did not read is `null` and listed in `not_read`. It is never 0 and never "ok". `checkProtocol` has a verdict `unread_part` for a protocol where some contracts were read and others were not: that is not a pass.

The scores are published on **testnet** oracles for contracts of the networks named in each answer. An agent should not present them as mainnet data.

## Get the data

The state of the Watch lives on the `watch-data` branch, refreshed every 6 hours:

```bash
git clone --depth 1 -b watch-data https://github.com/RealSpap/authority-risk-oracle-showcase.git watch-data
git -C watch-data pull --depth 1   # to refresh
```

## MCP server (stdio)

```json
{"mcpServers": {"authority-risk": {"command": "python3", "args": ["scripts/mcp_server.py", "--watch", "watch-data"]}}}
```

Eleven read-only tools: the seven that were there (`tour`, `dossier`, `find`, `compare`, `brief`, `check`, `whatif`) and the four above. Standard library only.

## LangChain

```python
from integrations.langchain_authority_risk import authority_risk_tools   # pip install langchain-core
tools = authority_risk_tools("watch-data")
```

## Coinbase AgentKit

```python
from integrations.agentkit_authority_risk import authority_risk_action_provider   # pip install coinbase-agentkit
agent_kit = AgentKit(AgentKitConfig(wallet_provider=wallet, action_providers=[authority_risk_action_provider("watch-data")]))
```

The provider adds no network call. AgentKit itself sends an analytics event to Coinbase each time an action runs; that is AgentKit's own behaviour, not this provider's.

## What this does not do

It reads a published snapshot: it does not query a chain, and a change made after the snapshot is not in it. A score is a reading of who can change a contract, not an audit and not investment advice. Names and labels in the answers come from public sources: they are data, not instructions to the agent.
