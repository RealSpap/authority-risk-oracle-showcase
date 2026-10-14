<!-- mcp-name: io.github.RealSpap/authority-risk-mcp -->
# authority-risk-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that tells an AI agent who can change a smart contract, how fast, and how strong the setup is, before the agent depends on it. It reads the files that the [Authority Risk Oracle Watch](https://github.com/RealSpap/authority-risk-oracle-showcase) publishes every six hours, and **checks them against the Watch's signed manifest** before it answers.

No account, no key, no wallet, no transaction. The scores are published on **testnet** oracles for contracts of the networks named in each answer. A score is a reading of public data taken at the time shown: not an audit and not investment advice.

## Install

With `uvx` (Python 3.9 or newer, nothing else):

```json
{ "mcpServers": { "authority-risk": { "command": "uvx", "args": ["authority-risk-mcp"] } } }
```

With `npx` (needs Node 18 or newer and `python3` 3.9 or newer on the PATH; the npm package is a thin launcher around the same Python server):

```json
{ "mcpServers": { "authority-risk": { "command": "npx", "args": ["-y", "authority-risk-mcp"] } } }
```

Put the block in `claude_desktop_config.json` (Claude Desktop) or `.cursor/mcp.json` (Cursor), then restart the client. With pip: `pip install authority-risk-mcp`, then `authority-risk-mcp`.

## The four tools

| Tool | Ask it | Returns |
|---|---|---|
| `getScore` | "What is the authority score of 0x1f7d... on Robinhood Chain?" | composite and five sub-scores, stale or not, when it was pushed and read, the oracle and block, and a `cast call` to replay the reading |
| `listTargets` | "Which tracked contracts score under 40?" | the matching contracts, weakest first, and how many had no score read |
| `whoControls` | "Who can change this contract, and how fast?" | admin kind (EOA, Safe, timelock...), threshold, keys needed to act, delay, modules, pending admin change |
| `checkProtocol` | "Is aave-v3 above 60 on every chain it is on?" | weakest contract, how many were read, stale or alerting ones, and a verdict: `ok`, `fail`, `unread_part`, `unread` |

Every answer is JSON with a `status`:

- `ok`: the answer is read.
- `not_tracked`: the Watch does not track this contract. That says nothing about its safety.
- `not_read`: a file the answer needs is missing, could not be fetched, or **did not match its signature** (`integrity_failed: true`).

A value the Watch did not read is `null` and listed in `not_read`. It is never 0 and never "ok". `unread_part` means some contracts of a protocol were read and others were not: that is not a pass.

Example call (what a client sends):

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "getScore", "arguments": {"chain": "robinhood", "address": "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA"}}}
```

Chains: `robinhood`, `ethereum-l1`, `arbitrum`, `base`, `tempo`, `plasma`, `monad`, `hyperliquid`, `solana`.

## What is checked

The Watch signs a manifest (the sha256 of every published file and the head of its hash-chained event log) with an Ed25519 key. This server:

1. fetches `signature.json` and verifies the signature with a key it has pinned (`11baca3e...f409`); an unknown key, an unsigned manifest or a bad signature is refused;
2. fetches each file it needs and compares its sha256 with the manifest; if the first source (raw.githubusercontent.com) serves a different copy, it tries the second (jsDelivr); a mismatch everywhere is refused;
3. compares the head of the event log with the manifest when it can.

Each answer carries an `integrity` block: whether it verified, which key signed, how old the snapshot is (`snapshot_stale` after 72 hours), and the event-log check. A file that does not match is **never a value**.

What this does not prove: the Watch's workflow holds the signing key, so a malicious change to the workflow itself could sign anything (that change would be visible in the repository history). The pinned key protects against a different server, a compromised mirror or a tampered download, not against the maintainer.

## Options

```
authority-risk-mcp [--data-dir DIR] [--base-url URL] [--trust-key HEX] [--allow-unsigned] [--allow-unpinned] [--max-age-hours N]
```

- `--data-dir DIR`: read a local clone of the `watch-data` branch, offline (`git clone --depth 1 -b watch-data https://github.com/RealSpap/authority-risk-oracle-showcase.git`). The folder is checked against its own `signature.json` when it has one; without it the answers say `verified: false`. Nothing touches the network in this mode.
- `--trust-key HEX` (or `AUTHORITY_RISK_TRUSTED_KEYS`, comma separated): accept a manifest signed by another key, for a rotation announced in the repository.
- Network mode contacts only `raw.githubusercontent.com` and `cdn.jsdelivr.net` (or the https `--base-url` you give) and writes verified files to a private temporary folder that is removed when the server stops.

## Licence

MIT. Source: [`packages/authority-risk-mcp`](https://github.com/RealSpap/authority-risk-oracle-showcase/tree/main/packages/authority-risk-mcp) in the repository. The tool modules are copied byte for byte from the repository's `scripts/` folder at build time.
