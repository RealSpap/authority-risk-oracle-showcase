# watch/

**Where the files are.** The state of the Watch is committed to the [`watch-data` branch](https://github.com/RealSpap/authority-risk-oracle-showcase/tree/watch-data), not to `main` (the root of that branch is this folder). On `main` this folder keeps the documents written by hand and a few small notices at the old addresses (`status.json`, `latest.json`, `signature.json`, `badge.json`, `badge/integrity.json`, `alerts.xml`, `feed.xml`) so that an old link tells you where the live file is. Raw files: `https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/<file>`.

The files a read-only GitHub Action rewrites every 6 hours (cron `17 */6 * * *` UTC): every deployed oracle re-read, the money behind each
target, the queue of changes behind the watched timelocks, the rules that fire, why a score moved. The dashboard at
https://realspap.github.io/oracle/ reads these files for what it shows, plus live RPC calls when you press “verify”.

Since 2026-10-10 the folder also carries what lets anyone check it from outside: a hash-chained event log (`events.jsonl`, `chain.json`), a signed manifest of every published file (`signature.json`), a second opinion on every admin key from a reader that shares nothing with the scorer (`second_opinion.json`), one Atom feed per contract (`feed/`), the oracles watching their own keys (`latest.json`, `self_watch`) one health record per run (`status.json`) the public disputes of a score with their resolutions (`disputes.json`, each one a line of the chained log), and every score over time with the oracle's calibration against the authority actions the watch observed (`score_series.json`). One command audits all of it: `python3 scripts/audit_public.py` (it also says whether the watch is alive: a last run older than two 6-hour schedules fails the audit, and the dashboard says it in red).

What each file is, with its schema: [API.md](API.md). Rules of the alerts: [../rules.json](../rules.json). The job: [../.github/workflows/watch.yml](../.github/workflows/watch.yml).

Not published on purpose: the index of root signers (who can reach what). Root-signer addresses are shortened in the files here (a tracked contract that also signs elsewhere keeps its full address: it is the row's key).
