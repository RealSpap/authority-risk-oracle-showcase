# Contributing

This repository publishes a measurement: who can change a contract, how fast anyone can react, and what a score says about it. There are three concrete ways to help. Each one ends in something anyone can re-read, not in an opinion.

Replies are best effort, with no promised delay.

## 1. Propose a target

A target is one contract (or one Solana program) that the oracle should read and score. Open a **New target** issue (Issues, New issue) and give:

- the chain and the address, exactly as an explorer shows them;
- the protocol and the role of the contract (what it holds or controls);
- where its admin, owner or upgrade roles are documented, if you know (an explorer page, a verified source, a governance post);
- why it should be tracked (what depends on it).

How it is read and scored: the scorer of the contract's ecosystem (`chains/<ecosystem>/scorers.py`) reads the admin authority, the multisig threshold and signers, the timelock delay, the price authority and any shared control, directly from a public RPC node. The five sub-scores and the composite are defined in [`METHODOLOGY.md`](METHODOLOGY.md). Adding a target ends with a test that pins its score and a dry run before anything is pushed on-chain; that is done by the maintainer, so please do not open a pull request that edits a score.

A target is accepted when it can be read from public data alone. A contract whose control cannot be read is written as not read, never as a zero.

## 2. Dispute a score

If a published score is wrong, use the **Dispute a score** issue form ([`.github/ISSUE_TEMPLATE/dispute.yml`](.github/ISSUE_TEMPLATE/dispute.yml)). One claim per dispute, with evidence anyone can re-read: an address and the call to make (`owner()`, `getThreshold()`, `getMinDelay()`), an explorer link or a transaction. Not a screenshot, not a private document.

The dispute and its resolution are public and recorded in `data/disputes.json` and in the hash-chained event log. No score is changed for a payment, a request or a deadline; evidence is the sole reason.

If you found an error in a reading that is not a score (a wrong label, a missing field, a number that does not match its source), open a **Reading error** issue instead.

## 3. Replay a reading

Every reading can be redone with public data.

- Read a score from an oracle contract: the command in the README section "Try it in 60 seconds" (`cast call ... getScore(address)`). The score returned must equal the published file for that target.
- Audit the published state: `python3 scripts/audit_public.py` checks the hash-chained event log, the signed manifest and the schemas, and re-reads scores from the oracles. Expected: `AUDIT PASSED`.
- Replay a dated measurement: [`research/aave-levels-2026-10-13/`](research/aave-levels-2026-10-13/) reads the privileged roles of Aave V3 Core reserves at a fixed block. Run `python3 mesure-aave-niveaux.py --block 26184127 --compact` from that folder (standard library, public RPC). Expected: the levels written in its README and zero calls in error. A different level at the same block is a finding: open a **Reading error** issue with both outputs.

If a replay differs from what is published, that is useful. Say which command, which block, and what you got.

## Run the tests

```bash
forge install foundry-rs/forge-std OpenZeppelin/openzeppelin-contracts --no-git
forge test

pip install -r scripts/requirements.txt
python3 -m unittest discover -s scripts/lib/tests
python3 -m unittest discover -s scripts/tests
```

The continuous integration also runs the tests under `chains/base-ecosystem`, `chains/ethereum-l1`, `chains/tempo` and `chains/hyperliquid` (`python3 -m unittest discover -s chains/<ecosystem>/tests`). None of them needs a live RPC.

## Out of scope

- A pull request that changes a score by hand. Scores come from the scorers and are pushed by the maintainer; a change of method is written in [`CHANGELOG.md`](CHANGELOG.md) with its date.
- Requests to raise or lower a score for any reason other than evidence.
- Anything that sends a transaction on a real network from this repository. It is a testnet project and says so.

## Pull requests

Keep them small and say what you ran. The pull request template asks three questions: what changes, how it was tested, and whether the result can be replayed. Security issues follow [`SECURITY.md`](SECURITY.md), not a public issue.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
