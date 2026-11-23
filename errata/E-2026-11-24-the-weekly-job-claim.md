# E-2026-11-24: the changelog said a workflow pushes the scores every week

Date of this entry: 2026-11-24. Status: corrected in the two files below; the earlier text stays in the history of git.

## What I said

- `CHANGELOG.md`, entry "Recurring updater wired": the updater "Runs weekly via `.github/workflows/update_scores.yml`, or on demand".
- `chains/plasma-ecosystem/deploy/README.md`: "Robinhood Chain's weekly recurring `.github/workflows/update_scores.yml` cron".

## What is true

Read at 18:58Z on 25 November 2026. The file `.github/workflows/update_scores.yml` is not in this repository. The audit of 11 October 2026, `data/audit_2026-10-11-second-review.md`, says that this workflow pushed Robinhood Chain testnet only and failed its completeness check on 4 and 11 October 2026. The scores are prepared every week and pushed by hand, at the latest every nine days, as `METHODOLOGY.md` says. From 19 October to 20 November 2026, no push of the nine oracles fell on a Sunday. Between two pushes of the same oracle the gap was 6.0 to 9.9 days, 36 gaps in all. Two exceeded nine days: Ethereum L1 waited 9.3 days and Monad 9.9 days, both between 11 and 20 November 2026.

## Cause

The sentence stayed in the changelog after those failures. The error is mine.

## Replay

`curl -s https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/main/data/audit_2026-10-11-second-review.md | grep -c "failed at that check"` prints 1. `git clone -q https://github.com/RealSpap/authority-risk-oracle-showcase` then `git -C authority-risk-oracle-showcase ls-files | grep -c update_scores.yml` prints 0. The push times come from the history of `latest.json` on the branch watch-data: `git clone -q --single-branch -b watch-data --shallow-since=2026-10-24 https://github.com/RealSpap/authority-risk-oracle-showcase wd` then `git -C wd log -p --format= -- latest.json | grep -o 'lastUpdated": [0-9]*' | sort -u | cut -d' ' -f2 | xargs -I T python3 -c "import datetime as d;print(d.datetime.fromtimestamp(T,d.timezone.utc).strftime('%Y-%m-%d %a %H:%MZ'))" | sort` prints one line per distinct push time with its weekday. The oldest line, 2026-09-23, is a base value from before the window.

## What this entry does not claim

- That a schedule will run the pushes. The promise now is the one written: prepared every week, pushed by hand, at the latest every nine days; the date of each push is in `latest.json`.
