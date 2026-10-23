# Reporting an error or a security issue

Thank you for taking the time. Every deployment here is on a testnet and the contracts hold no user funds: this repository is a publication point, not a custodian. Most reports are about a number or a statement that may be wrong, and those are welcome.

## How to reach us

- **Privately**, for anything that should not be public (a vulnerability, a fix still in progress, a secret committed by mistake, a correction you would rather not discuss in the open): write to contact@realspap.com and put `authority-risk-oracle-showcase` in the subject. If the Security tab of this repository offers it, a private GitHub security advisory ("Report a vulnerability") works as well.
- **Publicly**: open a GitHub issue on this repository.

## What is in scope

- `src/AuthorityRiskOracle.sol`, the oracle contract, deployed on 8 EVM testnets (Robinhood Chain, Ethereum Sepolia, Arbitrum Sepolia, Base Sepolia, Tempo Moderato, Plasma, Monad, Hyperliquid HyperEVM). The live addresses are in `docs/REFERENCE.md`.
- `src/ExampleConsumer.sol`, the reference consumer. A bug in reference code that gets copied into a real integration is a real bug.
- `chains/solana/program/`, the Anchor program on Solana devnet (program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`): the registry and the score accounts.

The off-chain scoring pipeline (`scripts/`, `chains/*/scorers.py`) and the watch job hold no funds and have no privileged on-chain role beyond the updater key. A wrong number there is a data-quality question: report it as a normal GitHub issue, with the evidence, and it will be answered in public.

## What is not in scope

- The contracts and systems of the projects named here. If you found a flaw in one of them, please report it to that team through its own channel.
- Opinions on prices, tokens or investments. This is independent research, not a security audit and not advice.

## What is at stake today

Every deployment is on a testnet and the contracts hold no user funds. They are a publication point, not a custodian. One direct effect of a bug is a wrong or manipulated score served to a consumer, and a consumer should treat a score as one input. The scores are published by one updater key with no timelock; that is disclosed on the dashboard and in the methodology, and a consumer should weigh it before relying on a score.

## Known limits of the scripts that read the published files

Reviewed on 22 October 2026. These scripts read what the Watch publishes. What each one checks, and what it does not:

- `scripts/audit_public.py` checks the signed manifest, the hash chain, the schemas and a sample re-read on chain. It trusts one signing key, pinned in the script (`PINNED_KEYS`, the key written in `watch/API.md`): a valid signature by any other key fails unless you pass `--pin KEY`. A local folder with no `signature.json` is reported as a NOTE, not as a failure. A name in the manifest that is not a plain relative path of ASCII letters, digits and `. _ @ + = , ~ -` (`..`, an absolute path, an empty part, a trailing dot or space, a newline, a non-ASCII or full-width character, a `?` or `%`), two names that are the same file once case or Unicode normalization is ignored, or more than 5000 names, stop the fetch before anything is written. A file larger than 5 MB, or a listed file that cannot be fetched or written, makes the audit INCOMPLETE (exit 3); for a local folder, a listed file that is absent is a NOTE.
- `scripts/sign_run.py` writes `run_utc` next to the signed manifest, not inside it, so the signature does not cover it. The age of a reading is the `readAt` of each score file, which sits in a hashed file. `--verify` fails on a published file the manifest does not list. A symbolic link, a folder that is a link, and a `private` folder do not enter the manifest. Signing stops with `REFUSED TO SIGN` (exit 1, nothing written) when a published name is one the audit refuses (a space, a non-ASCII character, a Windows device name such as `con.json`, an 8.3 short name such as `BASE-S~1.JSO`, or two names that differ by case), when a file is over 5 MB, when there are more than 5000 files or when the files total more than 100 MB. Names that start with a dot are not published. If signing is refused the Watch run goes on and publishes the run with the signature.json of the run before: `watch/status.json` then says `signature_status: stale` (state `alarm`), the integrity badge says `signature stale`, and `scripts/audit_public.py` exits with code 4 (a signature from an earlier run than latest.json). The job does not fail, so a publication is not lost. The Windows rules are a list of known patterns, not a full model of Windows file names.
- `scripts/authority_check.py` (the CI gate and the GitHub Action) does not verify `signature.json`: it trusts the https transport, or the folder given with `--source`. A file with no `readAt`, a `stale` flag that is not a boolean, a composite that is not a whole number from 0 to 100, or a contract listed twice is reported UNREAD (exit 3), not as a pass. Its default age limit is 48 hours: pass `--max-age-hours` to choose another. The installable package `authority-risk-mcp` (version 0.1.0) uses 72 hours and flags an older snapshot (`snapshot_stale`) without refusing it; the published package has no `preflight` answer; one with a 12-hour limit is being tested and may come in a later version.
- `scripts/watch_age.py` refuses a limit that is not a finite number above 0. It reads `run_utc` from `latest.json` without verifying the signature.
- `scripts/mcp_server.py`, the local helper in this repository, reads a folder and does not verify `signature.json`. Its `check` tool applies the 48-hour age limit of `authority_check.py` (a file older than that is UNREAD); its other tools do not check the age of the files. The installable package `authority-risk-mcp` verifies the signature and flags a stale snapshot.
- `scripts/agent_tools.py`, used by that helper and by the brief and tour scripts, keeps the earlier line when a contract appears twice in a score file, and does not read `tvl_scope.json`, so a target marked retired there is still shown. Both points are open.

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
