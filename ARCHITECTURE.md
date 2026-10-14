# Architecture

One page: where things are, how the data is produced, where to read a score.

## The folders

```
src/         the oracle contract (AuthorityRiskOracle.sol) and the reference consumer (ExampleConsumer.sol)
test/        Foundry tests for both
script/      Deploy.s.sol, the Foundry deploy script (Foundry's convention is a folder named script)
scripts/     Python: the updater, the push guard, the watch tools, the audit, shared libraries (scripts/lib/) and their tests
chains/      one folder per ecosystem: its scorer, its deploy record and push script, dated audits (chains/README.md is the map)
data/        dated notes behind every number or claim: findings, corrections, backtests, snapshots (data/README.md is the index)
watch/       the files the Watch job rewrites every 6 hours (it reads, it never writes on-chain) (watch/API.md describes each file)
rules.json   the alert rules, forkable
docs/        landscape and operations notes
research/    standalone dated measurements, each with the command to replay it
dashboard/   the single-file dashboard (no backend)
api/         the JSON snapshot of the last on-chain push
```

`script/` (Foundry) and `scripts/` (Python) are two different folders on purpose: Foundry looks for `script/`, so it stays where it is.

## How a score is produced

1. A scorer in `chains/<ecosystem>/` reads the target's admin authority, multisig threshold and signers, timelock delay and price authority from a public RPC node, and derives five sub-scores and a composite (`METHODOLOGY.md`).
2. `scripts/update_scores.py` pushes the batch to that ecosystem's oracle contract. A real push is guarded (a large drop is held until a person accepts it, and a read that could not be completed is never written as a zero). A dry run recomputes and encodes without sending anything.
3. Anyone reads the result with `getScore(address)` and `isStale(address)` on the oracle contract, or from `api/scores.json`.

## How the Watch runs

A GitHub Actions job (`.github/workflows/watch.yml`, cron `17 */6 * * *`, UTC) re-reads every deployed oracle, compares with the previous run, and rewrites the files in `watch/`: scores, the money behind each target, the queue of changes behind watched timelocks, the alerts that fire, why a score moved, an independent second reading, and a hash-chained event log with a signed manifest. It holds no key that can send a transaction. The job commits its output to `main`, so the generated data is in `watch/`, never in a separate store.

## Where to read a score

| You want | Read |
|---|---|
| one score, from a contract | `cast call <oracle> "getScore(address)(...)" <target>`, see the README |
| every score, as a file | `api/scores.json`, or `watch/scores/<oracle>.json` |
| the dashboard | https://realspap.github.io/oracle/ |
| whether the published state is intact | `python3 scripts/audit_public.py` |
| what changed in the method | `CHANGELOG.md`, section "Changes for readers" |

Everything runs on testnets while the stack is validated; the contracts hold no user funds.
