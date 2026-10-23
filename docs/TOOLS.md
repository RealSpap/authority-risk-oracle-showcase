# All the tools

Everything the repository can answer, beyond the front page of the [README](../README.md): the watch files, the audit scripts, the questions you can ask of every tracked contract. Standard library only unless a line says otherwise.

**Where the Watch's files are.** The Watch commits what it reads to the [`watch-data` branch](https://github.com/RealSpap/authority-risk-oracle-showcase/tree/watch-data), not to `main`, so that the history of `main` is the history of the work. The `watch/` folder named below is the root of that branch: `watch/status.json` here is `status.json` there, and `https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/<file>` serves it. To run the commands below on the latest state after cloning, run `bash scripts/watch_branch.sh prepare`: it clones the branch into `watch/` (do not commit that folder). On `main`, `watch/` holds the documents and a short notice at each old address.

**3. Audit it yourself, then ask it questions.** Standard library only, no network unless a line says so.

- `python3 scripts/tour.py` is the thirty-second tour: run it first after cloning.
- `python3 scripts/prove.py` replays, in one command and about ten seconds, the numbers this repository publishes against the chain, the changelog, the back-test and the Authority Facts twins; each line says OK, DIFFERENCE or UNREAD.
- `python3 scripts/audit_public.py` checks the hash-chained event log, the signed manifest and the schemas, and re-reads scores from the oracles. `watch/status.json` is the run health in one record. The manifest is signed with the maintainer's Ed25519 key `11baca3ef6a69de4901c185f6cbbd3f93318fbb74f9961a8d39aead841adf409` (the dashboard pins it): a manifest signed by another key is not ours.
- `python3 scripts/consistency.py` checks that the published files describe the same contracts and the same counts (each file passes its schema on its own; this is the check between them).
- `python3 scripts/dossier.py base 0x...` prints everything the watch knows about one contract, in words, from a clone and with no network.
- `python3 scripts/brief.py morpho-blue` writes a one-page brief for a protocol on all its chains: weakest deployment, fewest keys, shortest reaction, money counted once per chain, and what was not read.
- `python3 scripts/find.py --kind eoa --min-money 1e8` asks a question of every tracked contract at once. A value the watch did not read excludes the row and is counted, never matched as a zero; `--csv` gives the rows to a spreadsheet; `--watchlist mine.txt --alert --fail-if-any` is a gate for a cron job that exits 3 when a rule fires on one of your contracts.
- `python3 scripts/compare.py morpho-blue aave-v3 lido` sets protocols side by side, or chains with `--chains`; every figure says on how many contracts it was read. Each protocol can show its own badge in its README (`watch/badge/protocol/<slug>.json`, its weakest tracked deployment).
- `python3 scripts/whatif.py base 0x... --timelock 75` shows what the published formula gives if a sub-score changed (arithmetic, not a prediction).
- `python3 scripts/authority_check.py --chain base --address 0x... --min-score 60` is a CI gate: it fails when a contract you depend on is not tracked, is stale, is under your minimum or is falling (`--max-drop 10`). As a GitHub Action: `uses: RealSpap/authority-risk-oracle-showcase@main` with `chain`, `address`, `min-score` (see [`action.yml`](../action.yml)).
- `python3 scripts/conformance.py <twin.json | folder>` checks any implementation's JSON labels against the open Authority Facts v0.1 format ([`watch/schema/label.schema.json`](../watch/schema/label.schema.json)): fields, band, formula, and that an unread value is `null`, never 0 (see [`CONFORMANCE.md`](CONFORMANCE.md)). The local MCP server (`scripts/mcp_server.py`) has a `check` tool for an agent that must decide before depending on a contract.
- `python3 scripts/mcp_server.py --watch watch` is the same data as a local, read-only MCP server for an AI agent (stdio, no account, no key, no network).
- `python3 scripts/watch_age.py --max-hours 14` is a watchdog for a cron or an uptime monitor: exit 1 if the last run is too old, 2 if its age cannot be established.
- `python3 scripts/mutate.py` replays the mutations listed in `scripts/tests/mutations.json` (break the code one way, see whether the tests notice) and counts a mutant that does not run as invalid, never as caught. The `Mutation` workflow replays them every week and turns red when one survives.
- `python3 scripts/demo.py` replays four invented events (a pause, a shorter delay announced, an idle admin Safe waking up, a balance collapse) on a copy of the data and runs the real scripts, so you can see the alerts, the review queue and the dossier react.
- One Atom feed per protocol (`watch/feed/protocol/<slug>.xml`) lets a team follow every chain of its protocol at once.
- For programs and monitors: `watch/catalog.json` lists every published file with the question it answers, `watch/metrics.prom` is the run in the Prometheus text format (a stopped watch is `time() - aro_run_timestamp_seconds > 8 * 3600`), and the site publishes an `llms.txt`.

**4. Pull Robinhood Chain's table as JSON** (63 of the tracked targets; `python3 scripts/live_target_counts.py` counts every oracle), with the transaction that produced it so you can cross-check it:

```bash
curl -s https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/main/api/scores.json | jq '.txHash, (.scores | length)'
```

**5. Ask a question the score alone does not answer** (read-only, public RPC, no key):

```bash
pip install -r scripts/requirements.txt
python3 scripts/who_controls.py --top 20          # the most connected signers across every tracked protocol (about a minute: it reads nine oracles live)
python3 scripts/incident_exposure.py              # how many targets score at or below the multisig behind a documented incident (about two to three minutes)
```
