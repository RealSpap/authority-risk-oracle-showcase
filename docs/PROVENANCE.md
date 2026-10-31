# Provenance: what is public, what is private, what comes from elsewhere

*Written on 30 October 2026. It says where each part of this work comes from, under which licence it is published, and what you cannot reproduce from this repository. It does not claim more.*

## Public: in this repository

| What | Licence | Where |
|---|---|---|
| Code: `scripts/`, `chains/`, `src/`, tests and workflows | MIT | [LICENSE-CODE](../LICENSE-CODE) |
| The installable package `authority-risk-mcp` | MIT, its own license file | [packages/authority-risk-mcp/LICENSE](../packages/authority-risk-mcp/LICENSE) |
| The Watch files (`watch/`, the `watch-data` branch), the share pages and their JSON twins | CC BY 4.0 | [LICENSE](../LICENSE) |
| Notes, `METHODOLOGY.md`, the other texts, the datasets in `data/` and the score history | CC BY 4.0 | [LICENSE](../LICENSE) |
| The specification text in `docs/` | CC0, as the document itself says | the document |

The licence table of the README is the reference; this page repeats it so that provenance is read in one place. Attribution for data and text: "Authority Risk Oracle, realspap.github.io/oracle" with a link. Earlier copies were released under the MIT licence.

The rules that turn a reading into a score are in the scorers of this repository, including the values set by hand (see Known gaps in CHANGELOG.md); the runs that prepare the pushes are made in a private working repository (below). The `methodologyHash` of an oracle is a digest of the scoring code that produced its scores (`scripts/lib/methodology.py`). The static pages under `/oracle/` are generated when the site is published; no site generator is part of this repository, and those pages are copies of what the oracles and the Watch files say, not a source of their own.

## Private: not in this repository

- The working repository where scoring runs are prepared before they are pushed to the oracles (the Zcash attestations name it as a private repository).
- Research notes and sweeps that are not published, among them the index of which signer can reach which contract, which is never published (`watch/API.md`).
- The keys: the signing key of the Watch is a secret of the workflow, and the updater key of the oracles is held by the maintainer. Neither is in a repository.
- The alarm channel: a finding that needs a person opens an issue in a private repository, and only when its token is set (`watch/API.md`).

A figure that comes from private material cannot be reproduced from this repository. A number that is not backed by a file here should be read as a claim, not as a result you can replay.

## External: read, not produced here

| Source | Used for |
|---|---|
| Public RPC endpoints of each chain | every read of the chain: scores, roles, owners, thresholds, delays, code |
| Sourcify, and the OtterSec verified-build registry for Solana | whether the source of an implementation is verified |
| DefiLlama (TVL) and coins.llama.fi (prices) | the money figures |
| A public signature database | the names of function selectors in queued operations, cached in `selectors.json` |
| GitHub (repository, Actions, Pages) | hosting, the schedule of the Watch, the site |
| `web3`, `pynacl`, `Pillow` (Python); OpenZeppelin contracts and forge-std (Solidity) | the code runs on them |

An external source can be wrong, late or unavailable. When it does not answer, the Watch keeps the previous record marked stale or writes the line as not read; it does not write a zero. The scorers listed in Known gaps (CHANGELOG.md) are an exception: for them a failed read can leave a fixed score.

**Dependencies.** `scripts/requirements.txt` gives ranges (`web3>=7.0.0,<9`, `pynacl>=1.5,<2`, `Pillow>=10,<13`), not exact versions, so two installs can differ. The Solidity libraries are not committed: `foundry.toml` points to a `lib/` folder that `forge install` fills (CONTRIBUTING.md). As of 30 October 2026 no list of exact versions with hashes is published.

## What you can replay, and what you cannot

You can replay from this repository: the numbers the oracles hold, against the chain (`scripts/prove.py`); the signed manifest, the hash chain and a sample of scores (`scripts/audit_public.py`); a label against the specification (`scripts/conformance.py`). You cannot replay from it: the private research behind a finding that this repository does not carry the data of, and the decisions behind a push. `scripts/prove.py` prints what it does not prove; that list is not repeated or shortened here.

## Independence

The independence rules are in section 4 of [AUTHORITY-FACTS-SPEC.md](AUTHORITY-FACTS-SPEC.md): a rated party cannot pay for, edit or remove its own label, and can dispute it in public; any commercial relationship with a rated party is disclosed next to the label; sponsorship of monitoring is allowed only if the sponsor list is public and the formula and method hash do not move because of it; a method change gets a new hash and a dated entry.

What makes a change visible rather than a promise: the Watch manifest is signed (since 2026-10-11 21:18 UTC), the event log is hash-chained (since 2026-10-10), a change of method is dated in CHANGELOG.md, and a dispute is public and listed in `disputes.json`. These make a silent edit detectable by someone who checks; they do not show who funds the work. This repository does not carry a statement of who funds it; this page does not make one either.
